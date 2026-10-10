from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.contracts.commands import CommitBundle
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.call_ledger import (
    CallLedgerService,
    CancelUndispatched,
    PermitDispatch,
    ReserveCall,
    SettleCall,
)
from kineticloop.persistence.planning import (
    AcquireLease,
    AdmitOrReviseIntent,
    PlanningIdentity,
    RenewLease,
)
from kineticloop.persistence.planning import PlanningWorkflowService as LeaseService
from kineticloop.persistence.planning_progress import ContextService, capture_context
from kineticloop.persistence.planning_progress import PlanningWorkflowService as ProgressService
from kineticloop.persistence.protocol_execution import ProtocolExecutionService
from kineticloop.persistence.transactions import (
    GuardRequired,
    RepositoryTransaction,
    RepositoryTransactionError,
)
from kineticloop.persistence.worker_reaper import PlanningWorkflowService as ReaperService
from kineticloop.protocol.authorization import canonical_certificate_timestamp
from kineticloop.protocol.execution import ExecutionIdentity, PublishReady, command_digest
from kineticloop.workflow.call_ledger import AccountingIdentity, LedgerDenied, ReliableReceipt
from kineticloop.workflow.planning import PlanningDenied, digest
from kineticloop.workflow.planning_progress import (
    POLICY_BLOCKS,
    AdvanceAttempt,
    ProgressBasis,
    ProgressIdentity,
    RecordSnapshot,
)
from kineticloop.workflow.worker_reaper import ReapIntent, TestWorker, WorkerSchedule

ROOT = Path(__file__).resolve().parents[2]


def load(path: str) -> Any:
    spec = spec_from_file_location("kl036_" + Path(path).stem, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MIGRATIONS = load("tests/db/test_migrations.py")
_NAMESPACE = load("tests/unit/workflow/test_worker_reaper.py")
# All identities are isolated, and all finite bounds below use trusted database time.
(
    SUBJECT,
    POLICY,
    PROGRAM,
    FACTSET,
    PROJECTION,
    BUILD,
    ROOT_ARTIFACT,
    STATIC,
    POLICY_ARTIFACT,
    BASIS_EVENT,
) = [UUID(f"00000000-0000-8000-8000-{36000 + n:012x}") for n in range(10)]
ENVIRONMENT = UUID("00000000-0000-8000-8000-000000008cab")
IDENTITY = ExecutionIdentity(
    RoleIdentity(str(UUID("00000000-0000-8000-8000-000000008cac")), ActorRole.TEST),
    SUBJECT,
    POLICY,
    ENVIRONMENT,
    "kl_test_subject_1_login",
)
DEPS: list[dict[str, Any]] = [
    {"kind": "COLLECTION", "key": "admitted-facts", "collection": "all-admitted-v1"},
    {"kind": "ENGINE", "key": "exposure-engine:v1", "collection": None},
    {"kind": "FACTSET", "key": "current-factset", "collection": None},
    {"kind": "POLICY", "key": "active-policy", "collection": None},
    {"kind": "PROGRAM", "key": "active-program", "collection": None},
]
POLICY_BODY: dict[str, Any] = {
    "planning_admission": {
        "version": "kl024-v1",
        "purposes": ["TRAINING"],
        "triggers": ["USER_REQUEST"],
        "auto_root_triggers": [],
        "max_active_per_day": 1,
        "capacity_available": True,
        "hourly_roots": 10,
        "daily_roots": 10,
        "deadline_seconds": 3600,
        "calendar_policies": ["test:UTC-v1"],
        "root_limits": {"calls": 3, "tokens": 1000, "tools": 10},
    },
    "execution_calendar": {"policy": "test:UTC-v1", "timezone": "UTC"},
    "max_authorization_ttl_seconds": 3600,
    "authorization_action_scopes": {"TRAINING": "TEST_ONLY"},
    "t2_invalidation_scopes": {"ApplyControl": "TEST_ONLY", "ClearControl": "TEST_ONLY"},
    "manifest_projection_requirements": {
        "EXPOSURE": {"projection_kind": "EXPOSURE", "dependencies": DEPS}
    },
}
TARGETS = (
    "decision_manifests",
    "manifest_projection_bindings",
    "daily_plan_heads",
    "daily_bundle_revisions",
    "prescription_revisions",
    "bundle_prescription_members",
    "authorization_issuances",
    "authorization_artifact_closure",
    "authorization_events",
    "workout_sessions",
    "execution_bindings",
)



BUILDER = UUID("00000000-0000-8000-8000-000000008cad")
POLICY_BODY["planning_context"] = {block: {"status": "TEST_INPUT_ONLY", "value": []} for block in POLICY_BLOCKS}
POLICY_BODY["planning_context_byte_budget"] = 65536
POLICY_BODY["planning_context_builder"] = {"id": str(BUILDER), "hash": digest("context-builder")}
POLICY_BODY["worker_recovery"] = {"version": "kl036-v1", "lease_expiry": "CANCEL"}
PROGRESS = ProgressIdentity(IDENTITY.actor, SUBJECT, POLICY, ENVIRONMENT, IDENTITY.principal)
REAPER = replace(PROGRESS, actor=RoleIdentity(str(UUID("00000000-0000-8000-8000-000000008cae")), ActorRole.TEST))
WORKER2 = replace(PROGRESS, actor=RoleIdentity(str(UUID("00000000-0000-8000-8000-000000008caf")), ActorRole.TEST))
CONTEXT = mp.get_context("spawn")
CHILDREN: list[Any] = []


class LocalDsn(str):
    def __repr__(self) -> str:
        return "[REDACTED_LOCAL_TEST_DSN]"


class ConnectionUrls(dict[str, str]):
    def __repr__(self) -> str:
        return "<owned isolated PostgreSQL connections; credentials redacted>"


def connect(url: str, **kwargs: Any) -> Any:
    __tracebackhide__ = True
    try:
        return psycopg.connect(url, options="-c statement_timeout=10000 -c lock_timeout=8000", **kwargs)
    except psycopg.Error:
        raise AssertionError("owned isolated PostgreSQL connection failed; credentials redacted") from None


def evidence(item: Mapping[str, Any]) -> None:
    print("WORKER_REAPER_EVIDENCE " + json.dumps(item, sort_keys=True, default=str), flush=True)


def validate_database(urls: dict[str, str]) -> None:
    tested = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    selected = _NAMESPACE.worker_namespace(ROOT, tested)
    with connect(urls["admin"]) as db:
        row = db.execute("SELECT current_database(),current_user,session_user").fetchone()
        assert row == (selected.database_name, "kineticloop", "kineticloop")


def inventory() -> dict[str, Any]:
    """Supported read-only inventories; never record commands, DSNs or credentials."""
    def run(args: list[str]) -> str:
        return subprocess.check_output(args, text=True).strip()

    containers = [json.loads(line) for line in run([
        "docker", "container", "ls", "--all", "--format", "{{json .}}"
    ]).splitlines()]
    databases = {}
    for row in containers:
        if "postgres" in row["Names"] and row["State"] == "running":
            databases[row["ID"]] = sorted(run([
                "docker", "exec", row["ID"], "psql", "-U", "kineticloop", "-d", "postgres",
                "-Atc", "SELECT datname FROM pg_database ORDER BY datname"
            ]).splitlines())
    projects = json.loads(run(["docker", "compose", "ls", "--format", "json"]))
    return {
        "containers": sorted((r["ID"], r["Names"], r["Labels"]) for r in containers),
        "projects": sorted(r["Name"] for r in projects),
        "volumes": sorted(run(["docker", "volume", "ls", "--format", "{{.Name}}"]).splitlines()),
        "networks": sorted(run(["docker", "network", "ls", "--format", "{{.ID}} {{.Name}}"]).splitlines()),
        "databases": databases,
    }


def process_inventory() -> list[dict[str, Any]]:
    rows = subprocess.check_output(["ps", "-axo", "pid=,ppid=,comm="], text=True)
    result = []
    for line in rows.splitlines():
        pieces = line.strip().split(maxsplit=2)
        if len(pieces) == 3:
            result.append({"pid": int(pieces[0]), "ppid": int(pieces[1]), "executable": pieces[2]})
    return result


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    _NAMESPACE.test_identity_and_namespace()  # Must pass before any lifecycle I/O.
    tested = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    lifecycle = _NAMESPACE.WorkerLifecycle(ROOT, tested)
    selected = lifecycle.namespace
    before = inventory()
    assert selected.project_name not in before["projects"]
    assert not any(selected.project_name in str(rows) for rows in before.values())
    evidence({"kind": "before_inventory", "tested_commit": tested,
              "resolved_root": str(ROOT), "namespace": asdict(selected), "inventory": before,
              "pid": os.getpid(), "reserved_resources": ["transaction_interfaces", "user_coordination", "planning_ledger"]})
    processes = process_inventory()
    evidence({"kind": "before_process_inventory", "pid": os.getpid(), "processes": processes,
              "owned_children": []})
    created = False
    try:
        lifecycle.validate_target()
        # Record ownership before bootstrap so partial setup is cleaned as well.
        created = True
        try:
            urls = ConnectionUrls({key: LocalDsn(value) for key, value in
                                   _MIGRATIONS.bootstrap_two_phase(lifecycle).items()})
        except Exception as error:
            raise AssertionError("owned bootstrap failed: " + type(error).__name__) from None
        validate_database(urls)
        with connect(urls["admin"]) as db:
            head = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert head == _MIGRATIONS.HEAD_REVISION
        evidence({"kind": "migrated_namespace", "namespace": asdict(selected), "migration": head,
                  "service_user": "kineticloop", "session_user": "kineticloop",
                  "registered_client": IDENTITY.principal, "subject": SUBJECT, "policy": POLICY,
                  "environment": ENVIRONMENT, "instrumentation": "privileged isolated TEST service; no caller SQL capability"})
        yield urls
    finally:
        for child in CHILDREN:
            if child.is_alive():
                child.terminate()
            child.join(10)
        if created:
            lifecycle.validate_target()
            lifecycle.destroy()
        after = inventory()
        assert before == after
        final_processes = process_inventory()
        assert all(not child.is_alive() for child in CHILDREN)
        assert not {c.pid for c in CHILDREN} & {p["pid"] for p in final_processes}
        evidence({"kind": "after_inventory", "namespace": asdict(selected), "inventory": after,
                  "foreign_unchanged": True, "owned_children": [{"pid": c.pid, "exitcode": c.exitcode}
                                                              for c in CHILDREN],
                  "owned_resources_removed": True})
        evidence({"kind": "after_process_inventory", "pid": os.getpid(), "processes": final_processes,
                  "owned_worker_reaper_children_removed": True,
                  "instrumentation_helpers_exit_with_pytest": True})


def reset(urls: dict[str, str], *, deadline_seconds: int = 60, lease_recovery: bool = True) -> None:
    validate_database(urls)
    POLICY_BODY["planning_admission"]["deadline_seconds"] = deadline_seconds
    if lease_recovery:
        POLICY_BODY["worker_recovery"] = {"version": "kl036-v1", "lease_expiry": "CANCEL"}
    else:
        POLICY_BODY.pop("worker_recovery", None)
    seed_inputs(urls)
    with connect(urls["admin"], autocommit=True) as db:
        now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        db.execute(
            "INSERT INTO kineticloop.safety_artifacts(id,artifact_kind,artifact_identity,artifact_version,"
            "content_hash,validity_kind,valid_from,valid_until,ref_s48_id,typed_payload) "
            "VALUES (%s,'RUNTIME','test:kl036-builder','1',%s,'BOUNDED',%s,%s,%s,%s)",
            (BUILDER, digest("context-builder"), now-timedelta(minutes=1), now+timedelta(hours=1),
             STATIC, Jsonb({"operation": "CONTEXT_BUILDER"})),
        )
    publish(urls)


def admit(urls: dict[str, str], key: str = "admit") -> Mapping[str, Any]:
    with connect(urls["admin"]) as db:
        now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        db.commit()
        return LeaseService(db, PlanningIdentity(IDENTITY.actor, SUBJECT)).admit_or_revise(
            AdmitOrReviseIntent(SUBJECT, key, now.date(), "TRAINING", "test:UTC-v1", {"minutes": 30}))


def facts(urls: dict[str, str], root: Mapping[str, Any], key: str = "reap") -> ReapIntent:
    with connect(urls["admin"]) as db:
        row = db.execute(
            "SELECT i.current_request_revision_id,r.request_revision,i.current_attempt_id,i.lease_owner,"
            "i.fence_token,i.deadline,i.lease_expires_at,i.status,a.status "
            "FROM kineticloop.planning_intents i JOIN kineticloop.planning_request_revisions r "
            "ON r.id=i.current_request_revision_id AND r.subject_id=i.subject_id "
            "JOIN kineticloop.planning_attempts a ON a.id=i.current_attempt_id AND a.subject_id=i.subject_id "
            "WHERE i.subject_id=%s AND i.id=%s", (SUBJECT, root["intent_id"]),
        ).fetchone()
    return ReapIntent(subject_id=SUBJECT, key=key, intent_id=UUID(root["intent_id"]),
                      **dict(zip(("request_id", "request_revision", "attempt_id", "expected_owner", "fence",
                                  "deadline", "lease_expires_at", "intent_status", "attempt_status"), row, strict=True)))


def wait_elapsed(urls: dict[str, str], request: ReapIntent, field: str = "lease_expires_at") -> None:
    bound = getattr(request, field)
    assert bound is not None
    limit = time.monotonic() + 10
    with connect(urls["admin"], autocommit=True) as db:
        while time.monotonic() < limit:
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
            if now > bound:
                evidence({"kind": "elapsed_server_time", "bound": bound, "observed": now, "field": field})
                return
    raise AssertionError("trusted expiry not witnessed within bounded control deadline")


def persisted(urls: dict[str, str]) -> dict[str, Any]:
    """Complete sorted relation contents, including revision provenance and T6 closure."""
    with connect(urls["admin"]) as db:
        tables = db.execute("SELECT tablename FROM pg_tables WHERE schemaname='kineticloop' ORDER BY tablename").fetchall()
        return {name: sorted(json.dumps(r[0], sort_keys=True, default=str) for r in db.execute(
            sql.SQL("SELECT to_jsonb(t) FROM kineticloop.{} t").format(sql.Identifier(name))).fetchall())
                for (name,) in tables}


def no_effect(urls: dict[str, str], action: Any) -> None:
    before = persisted(urls)
    with pytest.raises((RepositoryTransactionError, PlanningDenied, LedgerDenied)):
        action()
    assert persisted(urls) == before
    evidence({"kind": "zero_effects", "relations": len(before), "sha256": digest(before)})


def reap(urls: dict[str, str], request: ReapIntent, identity: ProgressIdentity = REAPER) -> Mapping[str, Any]:
    with connect(urls["admin"]) as db:
        return ReaperService(db, identity).reap_intent(request)


def acquire(urls: dict[str, str], request: ReapIntent, identity: ProgressIdentity = PROGRESS,
            seconds: int = 2, key: str = "lease") -> Mapping[str, Any]:
    with connect(urls["admin"]) as db:
        return LeaseService(db, PlanningIdentity(identity.actor, SUBJECT)).acquire_lease(AcquireLease(
            SUBJECT, key, request.intent_id, request.expected_owner, request.fence,
            request.request_revision, request.attempt_id, seconds))


def advance(urls: dict[str, str], request: ReapIntent, *, source: str = "CREATED",
            target: str = "LEASED", identity: ProgressIdentity = PROGRESS) -> Mapping[str, Any]:
    with connect(urls["admin"]) as db:
        manifest = db.execute("SELECT current_manifest_id FROM kineticloop.user_decision_state WHERE subject_id=%s", (SUBJECT,)).fetchone()[0]
        db.commit()
        return ProgressService(db, identity).advance_attempt(AdvanceAttempt(
            subject_id=SUBJECT, key=f"advance:{source}:{target}:{uuid4()}", intent_id=request.intent_id,
            request_id=request.request_id, request_revision=request.request_revision,
            attempt_id=request.attempt_id, expected_owner=identity.key, fence=request.fence,
            manifest_id=manifest, epoch=0, source_state=source, target_state=target, sources={}))


def child_main(urls: dict[str, str], kind: str, identity: ProgressIdentity, request: Any,
               gate: Any, output: Any, ready: Any = None, stop: Any = None, manifest: Any = None,
               preflight_gate: Any = None, ordinary_work: Any = None,
               stale_gate: Any = None) -> None:
    try:
        with connect(urls["admin"]) as db:
            if kind == "settle":
                request = SettleCall(**{**request, "receipt": ReliableReceipt(**request["receipt"])})
            output.put({"kind": "child_ready", "role": kind, "pid": os.getpid(),
                        "backend_pid": db.info.backend_pid, "at": datetime.now().isoformat()})
            if not gate.wait(10):
                raise AssertionError("bounded process barrier expired")
            if kind == "reap":
                result = ReaperService(db, identity).reap_intent(request)
            elif kind == "acquire":
                class ObservedLease(LeaseService):
                    def _replay(self, command: Any, owner: str, request_hash: str) -> Mapping[str, Any] | None:
                        prior = super()._replay(command, owner, request_hash)
                        if preflight_gate is not None:
                            assert db.info.transaction_status == TransactionStatus.IDLE
                            output.put({"kind": "preflight_released", "pid": os.getpid(), "idle": True})
                            assert preflight_gate.wait(10)
                        return prior
                result = ObservedLease(db, PlanningIdentity(identity.actor, SUBJECT)).acquire_lease(request)
            elif kind == "renew":
                result = LeaseService(db, PlanningIdentity(identity.actor, SUBJECT)).renew_lease(request)
            elif kind == "worker":
                assert db.info.transaction_status == TransactionStatus.IDLE
                if ordinary_work is not None:
                    request, manifest = ordinary_work.get(timeout=10)
                    output.put({"kind": "ordinary_work_received", "pid": os.getpid(), "idle": True})
                result = TestWorker(db, identity, WorkerSchedule(2, 0.25, 100)).run(
                    request, manifest_id=manifest, epoch=0, stop=stop, ready=ready)
            elif kind == "reaper_loop":
                result = ReaperService(db, identity).run(stop=stop, ready=ready)
            elif kind == "admit":
                now = db.execute("SELECT clock_timestamp()").fetchone()[0]
                db.commit()
                result = LeaseService(db, PlanningIdentity(identity.actor, SUBJECT)).admit_or_revise(
                    AdmitOrReviseIntent(SUBJECT, "independent-admission", now.date(), "TRAINING", "test:UTC-v1", {"minutes": 30}))
            elif kind == "commit":
                execution_identity = ExecutionIdentity(identity.actor, SUBJECT, POLICY, ENVIRONMENT, identity.principal)
                class ObservedExecution(ProtocolExecutionService):
                    def _replay(self, owner: str, key: str, request_hash: str) -> Mapping[str, Any] | None:
                        prior = super()._replay(owner, key, request_hash)
                        if preflight_gate is not None:
                            assert db.info.transaction_status == TransactionStatus.IDLE
                            output.put({"kind": "preflight_released", "pid": os.getpid(), "idle": True})
                            assert preflight_gate.wait(10)
                        return prior
                result = ObservedExecution(db, execution_identity).commit(request)
            elif kind == "accounting_loop":
                from unittest.mock import patch

                class ObservedAccounting(CallLedgerService):
                    paused = False

                    def _replay(self, command: Any, owner: str, request_hash: str) -> Mapping[str, Any] | None:
                        prior = super()._replay(command, owner, request_hash)
                        if not self.paused:
                            self.paused = True
                            assert db.info.transaction_status == TransactionStatus.IDLE
                            output.put({"kind": "accounting_discovery_released", "pid": os.getpid(),
                                        "reservation_id": str(command.reservation_id),
                                        "expected_revision": command.expected_revision, "idle": True})
                            assert preflight_gate.wait(10)
                        return prior

                    def mark_unknown(self, command: Any) -> Mapping[str, Any]:
                        try:
                            return super().mark_unknown(command)
                        except GuardRequired:
                            assert db.info.transaction_status == TransactionStatus.IDLE
                            output.put({"kind": "stale_accounting_rollback", "pid": os.getpid(),
                                        "reservation_id": str(command.reservation_id), "idle": True,
                                        "complete_relation_sha256": digest(persisted(urls))})
                            assert stale_gate.wait(10)
                            raise

                with patch("kineticloop.persistence.worker_reaper.CallLedgerService", ObservedAccounting):
                    result = ReaperService(db, identity).run(stop=stop, ready=ready, max_scans=1,
                                                            poll_seconds=0.01)
            elif kind in {"permit", "cancel", "settle"}:
                class ObservedLedger(CallLedgerService):
                    def _replay(self, command: Any, owner: str, request_hash: str) -> Mapping[str, Any] | None:
                        prior = super()._replay(command, owner, request_hash)
                        if preflight_gate is not None:
                            assert db.info.transaction_status == TransactionStatus.IDLE
                            output.put({"kind": "preflight_released", "pid": os.getpid(), "idle": True})
                            assert preflight_gate.wait(10)
                        return prior
                ledger = ObservedLedger(db, PlanningIdentity(identity.actor, SUBJECT),
                    receipt_verifier=(lambda receipt: receipt == request.receipt) if kind == "settle" else None)
                if kind == "permit":
                    permission = ledger.permit(request)
                    result = {"sendable": permission.sendable, "replayed": permission.replayed}
                elif kind == "cancel":
                    result = ledger.cancel(request)
                else:
                    result = ledger.settle(request)
            else:
                raise AssertionError("unknown bounded child role")
            assert db.info.transaction_status == TransactionStatus.IDLE
            output.put({"kind": "child_result", "result": dict(result), "pid": os.getpid(),
                        "idle": True, "at": datetime.now().isoformat()})
    except (RepositoryTransactionError, PlanningDenied, LedgerDenied) as error:
        with connect(urls["admin"]) as observer:
            state = observer.execute("SELECT status,clock_timestamp() FROM kineticloop.planning_intents WHERE id=%s",
                                     (request.intent_id,)).fetchone()
        output.put({"kind": "child_denial", "error_type": type(error).__name__, "reason": str(error),
                    "pid": os.getpid(), "post_rollback_root_state": state})


def spawn(urls: dict[str, str], kind: str, identity: ProgressIdentity, request: Any,
          **kwargs: Any) -> tuple[Any, Any, Any, dict[str, Any]]:
    gate, output = CONTEXT.Event(), CONTEXT.Queue()
    child = CONTEXT.Process(target=child_main, args=(urls, kind, identity, request, gate, output), kwargs=kwargs)
    child.start()
    CHILDREN.append(child)
    observation = output.get(timeout=15)
    assert observation["kind"] == "child_ready" and observation["pid"] == child.pid
    assert child.pid != os.getpid()
    evidence(observation)
    return child, gate, output, observation


def finish(child: Any, output: Any, *, denial: bool = False) -> dict[str, Any]:
    result = output.get(timeout=15)
    child.join(10)
    evidence({**result, "exitcode": child.exitcode})
    assert child.exitcode == 0 and not child.is_alive()
    assert result["kind"] == ("child_denial" if denial else "child_result"), result
    return result


def blocked(urls: dict[str, str], pid: int, blocker: int) -> None:
    deadline = time.monotonic() + 8
    with connect(urls["admin"], autocommit=True) as db:
        while time.monotonic() < deadline:
            row = db.execute("SELECT state,wait_event_type,pg_blocking_pids(pid),xact_start "
                             "FROM pg_stat_activity WHERE pid=%s", (pid,)).fetchone()
            if row and row[1] == "Lock" and blocker in row[2]:
                locks = db.execute("SELECT locktype,mode,granted,relation::regclass::text "
                                   "FROM pg_locks WHERE pid=%s ORDER BY locktype,mode,granted", (pid,)).fetchall()
                assert any(not r[2] for r in locks)
                evidence({"kind": "postgres_blocker", "pid": pid, "blocker": blocker,
                          "state": row, "pg_locks": locks})
                return
    raise AssertionError("real PostgreSQL blocker witness missing")


def hold_subject(urls: dict[str, str]) -> Any:
    db = connect(urls["admin"])
    db.execute("SELECT subject_id FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE", (SUBJECT,))
    return db


def scan(urls: dict[str, str]) -> tuple[ReapIntent, ...]:
    with connect(urls["admin"]) as db:
        result = ReaperService(db, REAPER).scan()
        assert db.info.transaction_status == TransactionStatus.IDLE
        with connect(urls["admin"]) as observer:
            state = observer.execute("SELECT state,xact_start FROM pg_stat_activity WHERE pid=%s",
                                     (db.info.backend_pid,)).fetchone()
        assert state == ("idle", None)
        evidence({"kind": "scan_released", "backend_pid": db.info.backend_pid, "state": state,
                  "candidates": len(result), "pids": [os.getpid()]})
        return result


def read_root(urls: dict[str, str], request: ReapIntent) -> tuple[Any, ...]:
    with connect(urls["admin"]) as db:
        return db.execute("SELECT status,deadline,typed_payload,lease_owner,fence_token "
                          "FROM kineticloop.planning_intents WHERE id=%s", (request.intent_id,)).fetchone()


def reserve(urls: dict[str, str], request: ReapIntent, slot: str = "call") -> Mapping[str, Any]:
    with connect(urls["admin"]) as db:
        return CallLedgerService(db, PlanningIdentity(PROGRESS.actor, SUBJECT)).reserve(ReserveCall(
            SUBJECT, "reserve:"+slot, request.intent_id, request.attempt_id, request.request_revision,
            request.fence, slot, AccountingIdentity("test-provider", "model", "cfg", "count-v1"),
            {"calls": 1, "tokens": 100, "tools": 1}))


def permit_request(request: ReapIntent, reservation: Mapping[str, Any], key: str = "permit") -> PermitDispatch:
    return PermitDispatch(SUBJECT, key, request.intent_id, UUID(reservation["reservation_id"]),
                          request.attempt_id, request.request_revision, request.fence)


def stale_denials(urls: dict[str, str], request: ReapIntent, reservation: Mapping[str, Any] | None = None,
                  commit: CommitBundle | None = None) -> None:
    no_effect(urls, lambda: acquire(urls, request, key="stale-acquire"))
    no_effect(urls, lambda: advance(urls, request))
    with connect(urls["admin"]) as db:
        manifest = db.execute("SELECT current_manifest_id FROM kineticloop.user_decision_state WHERE subject_id=%s",
                              (SUBJECT,)).fetchone()[0]
        db.commit()
        basis = ProgressBasis(subject_id=SUBJECT, key="old-snapshot", intent_id=request.intent_id,
                              request_id=request.request_id, request_revision=request.request_revision,
                              attempt_id=request.attempt_id, expected_owner=PROGRESS.key, fence=request.fence,
                              manifest_id=manifest, epoch=0, source_state="BUILDING_CONTEXT")
        context = capture_context(db, basis, BUILDER)
        snapshot = RecordSnapshot(**asdict(basis), builder_id=BUILDER, **context)
        no_effect(urls, lambda: ContextService(db, PROGRESS).record_snapshot(snapshot))
        if reservation:
            no_effect(urls, lambda: CallLedgerService(db, PlanningIdentity(PROGRESS.actor, SUBJECT)).permit(
                permit_request(request, reservation, "old-permit")))
        if commit:
            no_effect(urls, lambda: ProtocolExecutionService(db, IDENTITY).commit(commit))


def test_takeover_fences_distinct_processes(database_urls: dict[str, str]) -> None:
    urls = database_urls
    reset(urls)
    root = admit(urls)
    unowned = facts(urls, root)
    original = AcquireLease(SUBJECT, "original-worker", unowned.intent_id, None, 0, 1, unowned.attempt_id, 1)
    child, gate, output, old_pid = spawn(urls, "acquire", PROGRESS, original)
    gate.set()
    assert finish(child, output)["result"]["fence"] == 1
    old = facts(urls, root)
    reservation = reserve(urls, old)
    basis = read_root(urls, old)
    wait_elapsed(urls, old)
    worker3 = replace(WORKER2, actor=RoleIdentity(str(UUID("00000000-0000-8000-8000-000000008cb0")), ActorRole.TEST))
    request = AcquireLease(SUBJECT, "takeover", old.intent_id, old.expected_owner, old.fence, 1, old.attempt_id, 20)
    a_gate, b_gate = CONTEXT.Event(), CONTEXT.Event()
    a = spawn(urls, "acquire", WORKER2, request, preflight_gate=a_gate)
    b = spawn(urls, "acquire", worker3, replace(request, key="other-takeover"), preflight_gate=b_gate)
    for process in (a, b):
        process[1].set()
        observed = process[2].get(timeout=10)
        assert observed["kind"] == "preflight_released"
        evidence(observed)
        idle_witness(urls, process[3]["backend_pid"])
    assert len({old_pid["pid"], a[3]["pid"], b[3]["pid"]}) == 3
    assert len({old_pid["backend_pid"], a[3]["backend_pid"], b[3]["backend_pid"]}) == 3
    before = persisted(urls)
    with hold_subject(urls) as holder:
        a_gate.set()
        blocked(urls, a[3]["backend_pid"], holder.info.backend_pid)
        b_gate.set()
        blocked(urls, b[3]["backend_pid"], a[3]["backend_pid"])
        holder.commit()
    winner = finish(a[0], a[2])["result"]
    finish(b[0], b[2], denial=True)
    assert winner["fence"] == 2 and winner["owner"] == WORKER2.key
    after = persisted(urls)
    for table in before:
        if table not in {"planning_intents", "command_receipts", "domain_events", "outbox_deliveries", "revision_records"}:
            assert after[table] == before[table]
    for table in ("command_receipts", "domain_events", "outbox_deliveries"):
        assert len(after[table]) == len(before[table]) + 1
    current = facts(urls, root)
    assert read_root(urls, current)[1:3] == basis[1:3]
    stale_denials(urls, old, reservation)
    advance(urls, current, identity=WORKER2)
    no_effect(urls, lambda: advance(urls, replace(current, request_revision=2), identity=WORKER2))
    no_effect(urls, lambda: advance(urls, replace(current, attempt_id=uuid4()), identity=WORKER2))
    # Exact T6 stale-fence denial on coherent, explicitly instrumented upstream preparation.
    reset(urls)
    with connect(urls["admin"]) as db:
        manifest = db.execute("SELECT current_manifest_id FROM kineticloop.user_decision_state WHERE subject_id=%s", (SUBJECT,)).fetchone()[0]
    command = upstream(urls, {"manifest_id": str(manifest)}, lease_seconds=2)
    root2 = {"intent_id": str(command.intent_id)}
    old2 = facts(urls, root2)
    wait_elapsed(urls, old2)
    current2 = facts(urls, root2)
    take = AcquireLease(SUBJECT, "t6-takeover", old2.intent_id, old2.expected_owner, old2.fence, 1, old2.attempt_id, 20)
    c = spawn(urls, "acquire", WORKER2, take)
    c[1].set()
    finish(c[0], c[2])
    stale_denials(urls, current2, commit=command)


def test_reaper_rechecks_after_lock(database_urls: dict[str, str]) -> None:
    urls = database_urls
    reset(urls)
    root = admit(urls)
    acquire(urls, facts(urls, root), seconds=1)
    old = facts(urls, root)
    wait_elapsed(urls, old)
    candidates = scan(urls)
    assert len(candidates) == 1
    candidate = candidates[0]
    operation_gate = CONTEXT.Event()
    a = spawn(urls, "acquire", WORKER2, AcquireLease(SUBJECT, "recover", old.intent_id,
        old.expected_owner, old.fence, 1, old.attempt_id, 20), preflight_gate=operation_gate)
    b = spawn(urls, "reap", REAPER, candidate)
    a[1].set()
    released = a[2].get(timeout=10)
    assert released["kind"] == "preflight_released"
    evidence(released)
    idle_witness(urls, a[3]["backend_pid"])
    with hold_subject(urls) as holder:
        operation_gate.set()
        blocked(urls, a[3]["backend_pid"], holder.info.backend_pid)
        b[1].set()
        blocked(urls, b[3]["backend_pid"], a[3]["backend_pid"])
        holder.commit()
    finish(a[0], a[2])
    before = persisted(urls)
    finish(b[0], b[2], denial=True)
    assert persisted(urls) == before
    assert scan(urls) == ()
    # Renewal invalidates a previously read exact live basis too. This is a
    # declared false-positive discovery input; expiry scanning above is real.
    current = facts(urls, root)
    renewed = spawn(urls, "renew", WORKER2, RenewLease(SUBJECT, "renew", current.intent_id,
        current.fence, 1, current.attempt_id, 30))
    renewed[1].set()
    finish(renewed[0], renewed[2])
    no_effect(urls, lambda: reap(urls, current))
    no_effect(urls, lambda: reap(urls, replace(candidate, request_revision=2)))


class InjectedFailure(RuntimeError):
    pass


class FaultCursor:
    def __init__(self, cursor: Any, connection: Any, point: str) -> None:
        self.cursor, self.connection, self.point = cursor, connection, point

    def __getattr__(self, name: str) -> Any:
        return getattr(self.cursor, name)

    def execute(self, statement: Any, args: Any = None) -> Any:
        text = statement if isinstance(statement, str) else statement.as_string(self.connection)
        needles = {"receipt": "INSERT INTO kineticloop.command_receipts", "event": "INSERT INTO kineticloop.domain_events",
                   "outbox": "INSERT INTO kineticloop.outbox_deliveries", "s29": 'UPDATE "kineticloop"."planning_attempts"',
                   "ack": "UPDATE kineticloop.command_receipts SET status='SUCCEEDED'"}
        if needles[self.point] in text:
            if self.point == "ack":
                self.cursor.execute(statement, args)
            raise InjectedFailure(self.point)
        return self.cursor.execute(statement, args)


class FaultConnection:
    def __init__(self, connection: Any, point: str) -> None:
        self.connection, self.point = connection, point

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connection, name)

    def cursor(self) -> Any:
        return FaultCursor(self.connection.cursor(), self.connection, self.point)


def fault_rollback(urls: dict[str, str], request: ReapIntent, point: str) -> None:
    before = persisted(urls)
    with connect(urls["admin"]) as db:
        with pytest.raises(InjectedFailure):
            instrumented: Any = FaultConnection(db, point)
            ReaperService(instrumented, REAPER).reap_intent(request)
        assert db.info.transaction_status == TransactionStatus.IDLE
    assert persisted(urls) == before
    evidence({"kind": "complete_rollback", "point": point, "relations": len(before), "sha256": digest(before)})


def test_unowned_admitted_deadline(database_urls: dict[str, str]) -> None:
    urls = database_urls
    reset(urls, deadline_seconds=1)
    root = admit(urls)
    current = facts(urls, root)
    assert (current.intent_status, current.expected_owner, current.fence, current.attempt_status) == (
        "ADMITTED", None, 0, "CREATED")
    no_effect(urls, lambda: reap(urls, current))
    wait_elapsed(urls, current, "deadline")
    for wrong in (replace(current, request_revision=2), replace(current, attempt_id=uuid4()),
                  replace(current, request_id=uuid4()), replace(current, deadline=current.deadline+timedelta(seconds=10))):
        no_effect(urls, lambda wrong=wrong: reap(urls, wrong))
    for point in ("receipt", "event", "outbox", "s29", "ack"):
        fault_rollback(urls, current, point)
    child = spawn(urls, "reap", REAPER, current)
    child[1].set()
    result = finish(child[0], child[2])["result"]
    assert (result["intent_status"], result["attempt_status"]) == ("DEADLINE_EXCEEDED", "LEASE_LOST")
    after = persisted(urls)
    replay = reap(urls, current)
    assert replay == {**result, "replayed": True} and replay["executable"] is False
    assert persisted(urls) == after
    no_effect(urls, lambda: acquire(urls, current))
    # Legacy PENDING is only a declared negative/compatibility input, never
    # admission evidence. The actual admission path above produced ADMITTED.
    reset(urls, deadline_seconds=1)
    legacy = admit(urls)
    with connect(urls["admin"], autocommit=True) as db:
        db.execute("UPDATE kineticloop.planning_intents SET status='PENDING' WHERE id=%s", (legacy["intent_id"],))
    pending = facts(urls, legacy)
    wait_elapsed(urls, pending, "deadline")
    assert reap(urls, pending)["intent_status"] == "DEADLINE_EXCEEDED"
    evidence({"kind": "legacy_pending_alias", "instrumentation_only": True})
    reset(urls, deadline_seconds=2)
    root = admit(urls)
    unowned = facts(urls, root)
    acquire(urls, unowned, seconds=1)
    leased = facts(urls, root)
    wait_elapsed(urls, leased, "deadline")
    no_effect(urls, lambda: reap(urls, unowned))
    assert reap(urls, leased)["intent_status"] == "DEADLINE_EXCEEDED"


def test_reaper_atomicity_and_history(database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    urls = database_urls
    reset(urls)
    root = admit(urls)
    acquire(urls, facts(urls, root), seconds=1)
    current = facts(urls, root)
    reservation = reserve(urls, current)
    wait_elapsed(urls, current)
    candidate = scan(urls)[0]
    for point in ("receipt", "event", "outbox", "s29", "ack"):
        fault_rollback(urls, candidate, point)
    original = RepositoryTransaction._prepared_reaper
    for logical, forbidden in (("S27", "FAILED"), ("S29", "DEADLINE_EXCEEDED")):
        def wrong(tx: RepositoryTransaction, logical: str = logical, forbidden: str = forbidden) -> dict[str, Any]:
            prepared = original(tx)
            prepared[logical]["status"] = forbidden
            return prepared
        with monkeypatch.context() as patch:
            patch.setattr(RepositoryTransaction, "_prepared_reaper", wrong)
            no_effect(urls, lambda: reap(urls, candidate))
    before = persisted(urls)
    a, b = spawn(urls, "reap", REAPER, candidate), spawn(urls, "reap", REAPER, candidate)
    with hold_subject(urls) as holder:
        a[1].set()
        blocked(urls, a[3]["backend_pid"], holder.info.backend_pid)
        b[1].set()
        blocked(urls, b[3]["backend_pid"], a[3]["backend_pid"])
        holder.commit()
    first = finish(a[0], a[2])["result"]
    second = finish(b[0], b[2])["result"]
    assert second == {**first, "replayed": True}
    assert (first["intent_status"], first["attempt_status"]) == ("CANCELLED", "CANCELLED")
    trace = first["lock_trace"]
    assert [r[0] for r in trace] == sorted(r[0] for r in trace)
    assert [r[0] for r in trace] == [20, 40, 50, 80, 90]
    assert str(reservation["reservation_id"]) in trace[2][1]
    after = persisted(urls)
    for table in ("command_receipts", "domain_events", "outbox_deliveries"):
        assert len(after[table]) == len(before[table]) + 1
    assert after["call_reservations"] == before["call_reservations"]
    assert after["call_ledger_events"] == before["call_ledger_events"]
    no_effect(urls, lambda: reap(urls, replace(candidate, request_revision=2)))
    no_effect(urls, lambda: reap(urls, replace(candidate, key="absent-receipt")))
    no_effect(urls, lambda: reap(urls, candidate, replace(REAPER, environment_id=uuid4())))
    no_effect(urls, lambda: reap(urls, candidate, replace(REAPER, policy_id=uuid4())))
    assert reap(urls, candidate) == {**first, "replayed": True}
    no_effect(urls, lambda: acquire(urls, candidate, identity=WORKER2, key="terminal-takeover"))
    assert persisted(urls) == after

    reset(urls, deadline_seconds=2, lease_recovery=False)
    root = admit(urls)
    acquire(urls, facts(urls, root), seconds=1)
    expired = facts(urls, root)
    wait_elapsed(urls, expired)
    no_effect(urls, lambda: reap(urls, scan(urls)[0]))
    wait_elapsed(urls, expired, "deadline")
    assert reap(urls, scan(urls)[0])["intent_status"] == "DEADLINE_EXCEEDED"


def test_unknown_call_preserves_budget(database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    urls = database_urls
    reset(urls)
    with connect(urls["admin"]) as db:
        manifest = db.execute("SELECT current_manifest_id FROM kineticloop.user_decision_state WHERE subject_id=%s", (SUBJECT,)).fetchone()[0]
    commit = upstream(urls, {"manifest_id": str(manifest)}, lease_seconds=5)
    root = {"intent_id": str(commit.intent_id)}
    current = facts(urls, root)
    dispatched, reserved = reserve(urls, current, "sent"), reserve(urls, current, "never-sent")
    reservation = UUID(dispatched["reservation_id"])
    cancel = CancelUndispatched(SUBJECT, "post-permit-cancel", current.intent_id, reservation)
    permit_gate, cancel_gate = CONTEXT.Event(), CONTEXT.Event()
    permission = spawn(urls, "permit", PROGRESS, permit_request(current, dispatched), preflight_gate=permit_gate)
    contender = spawn(urls, "cancel", REAPER, cancel, preflight_gate=cancel_gate)
    for process in (permission, contender):
        process[1].set()
        observed = process[2].get(timeout=10)
        assert observed["kind"] == "preflight_released"
        evidence(observed)
        idle_witness(urls, process[3]["backend_pid"])
    with hold_subject(urls) as holder:
        permit_gate.set()
        blocked(urls, permission[3]["backend_pid"], holder.info.backend_pid)
        cancel_gate.set()
        blocked(urls, contender[3]["backend_pid"], permission[3]["backend_pid"])
        holder.commit()
    granted = finish(permission[0], permission[2])["result"]
    assert granted == {"sendable": True, "replayed": False}
    before = persisted(urls)
    finish(contender[0], contender[2], denial=True)
    assert persisted(urls) == before
    with connect(urls["admin"]) as db:
        ledger = CallLedgerService(db, PlanningIdentity(PROGRESS.actor, SUBJECT))
        assert ledger.permit(permit_request(current, dispatched)).sendable is False
        assert persisted(urls) == before
    wait_elapsed(urls, current)
    terminal = reap(urls, scan(urls)[0])
    assert terminal["intent_status"] == "CANCELLED"
    locked_reservations = [row[1].split(":", 1)[1] for row in terminal["lock_trace"] if row[0] == 50]
    assert len(locked_reservations) == 2 and locked_reservations == sorted(locked_reservations)
    after_reap = persisted(urls)
    occupied = read_root(urls, current)[2]["reserved"]
    from kineticloop.persistence.call_ledger import MarkUnknown
    with connect(urls["admin"]) as db:
        instrumented: Any = FaultConnection(db, "outbox")
        with pytest.raises(InjectedFailure):
            CallLedgerService(instrumented, PlanningIdentity(REAPER.actor, SUBJECT)).mark_unknown(
                MarkUnknown(SUBJECT, "interrupted-cleanup", current.intent_id, reservation))
    assert persisted(urls) == after_reap
    with connect(urls["admin"]) as db:
        assert ReaperService(db, REAPER).mark_outstanding_unknown() == 1
        assert ReaperService(db, REAPER).mark_outstanding_unknown() == 0
    after_unknown = persisted(urls)
    for table in after_reap:
        if table not in {"planning_intents", "call_reservations", "call_ledger_events",
                         "command_receipts", "domain_events", "outbox_deliveries", "revision_records"}:
            assert after_unknown[table] == after_reap[table]
    assert read_root(urls, current)[2]["reserved"] == occupied
    with connect(urls["admin"]) as db:
        state = db.execute("SELECT status,settlement_revision FROM kineticloop.call_reservations WHERE id=%s",
                           (reservation,)).fetchone()
        assert state == ("OUTCOME_UNKNOWN", 2)
        db.commit()
        no_effect(urls, lambda: CallLedgerService(db, PlanningIdentity(PROGRESS.actor, SUBJECT)).permit(
            permit_request(current, dispatched, "resend")))
        no_effect(urls, lambda: CallLedgerService(db, PlanningIdentity(REAPER.actor, SUBJECT)).cancel(cancel))
        CallLedgerService(db, PlanningIdentity(REAPER.actor, SUBJECT)).cancel(CancelUndispatched(
            SUBJECT, "cancel-reserved", current.intent_id, UUID(reserved["reservation_id"])))
    assert read_root(urls, current)[2]["reserved"] == {"calls": 1, "tokens": 100, "tools": 1}
    reliable = ReliableReceipt(reservation, AccountingIdentity("test-provider", "model", "cfg", "count-v1"),
        {"calls": 1, "tokens": 40, "tools": 0}, "RECONCILIATION", "verified-test-receipt", "provider-request",
        "test:declared-trusted-reconciliation")
    before_late = persisted(urls)
    with connect(urls["admin"]) as db:
        ledger = CallLedgerService(db, PlanningIdentity(REAPER.actor, SUBJECT), receipt_verifier=lambda r: r == reliable)
        command = SettleCall(SUBJECT, "late-settle", current.intent_id, reservation, reliable)
        ledger.settle(command)
        after_late = persisted(urls)
        ledger.settle(command)
        assert persisted(urls) == after_late
    for table in before_late:
        if table not in {"planning_intents", "call_reservations", "call_ledger_events",
                         "command_receipts", "domain_events", "outbox_deliveries", "revision_records"}:
            assert after_late[table] == before_late[table]
    assert read_root(urls, current)[0] == "CANCELLED"
    assert read_root(urls, current)[2]["reserved"] == {"calls": 0, "tokens": 0, "tools": 0}
    assert read_root(urls, current)[2]["settled"] == {"calls": 1, "tokens": 40, "tools": 0}
    stale_denials(urls, current, dispatched, commit=commit)
    evidence({"kind": "accounting_only_late_settlement", "unknown_occupation": occupied,
              "terminal_preserved": "CANCELLED", "separate_owner_transactions": True})


    accounting_settlement_race(urls, monkeypatch)


def accounting_settlement_race(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    reset(urls)
    root = admit(urls)
    acquire(urls, facts(urls, root), seconds=2)
    current = facts(urls, root)
    reservations = [reserve(urls, current, slot) for slot in ("race-a", "race-b")]
    with connect(urls["admin"]) as db:
        ledger = CallLedgerService(db, PlanningIdentity(PROGRESS.actor, SUBJECT))
        for n, reservation in enumerate(reservations):
            assert ledger.permit(permit_request(current, reservation, f"race-permit:{n}")).sendable
    wait_elapsed(urls, current)
    assert reap(urls, scan(urls)[0])["intent_status"] == "CANCELLED"
    before = persisted(urls)
    # An unchanged candidate must not conceal an unrelated owner guard failure.
    def unrelated_failure(self: Any, command: Any) -> Mapping[str, Any]:
        raise GuardRequired("injected unchanged-candidate guard failure")
    def unexpected_read(self: Any, reservation: Any) -> Any:
        raise AssertionError("unrelated owner guard must not trigger a stale-candidate reread")
    with monkeypatch.context() as injection, connect(urls["admin"]) as db:
        injection.setattr(CallLedgerService, "mark_unknown", unrelated_failure)
        injection.setattr(CallLedgerService, "read", unexpected_read)
        with pytest.raises(GuardRequired, match="injected unchanged-candidate"):
            ReaperService(db, REAPER).mark_outstanding_unknown()
    assert persisted(urls) == before

    accounting_gate, stale_gate = CONTEXT.Event(), CONTEXT.Event()
    worker = spawn(urls, "accounting_loop", REAPER, current, preflight_gate=accounting_gate,
                   stale_gate=stale_gate, stop=CONTEXT.Event(), ready=CONTEXT.Event())
    worker[1].set()
    discovered = worker[2].get(timeout=10)
    assert discovered["kind"] == "accounting_discovery_released" and discovered["expected_revision"] == 1
    evidence(discovered)
    idle_witness(urls, worker[3]["backend_pid"])
    settled_id = UUID(discovered["reservation_id"])
    reliable = ReliableReceipt(settled_id, AccountingIdentity("test-provider", "model", "cfg", "count-v1"),
        {"calls": 1, "tokens": 40, "tools": 0}, "RECONCILIATION", "race-verified-test-receipt",
        "race-provider-request", "test:declared-trusted-reconciliation")
    # Immutable receipt mappings become typed again inside the spawned process.
    command = {"subject_id": SUBJECT, "key": "race-settle", "intent_id": current.intent_id,
               "reservation_id": settled_id, "expected_transition": "DISPATCH_INTENT", "expected_revision": 1,
               "receipt": {"reservation_id": settled_id, "accounting": reliable.accounting,
                           "actual": dict(reliable.actual), "source": reliable.source,
                           "receipt_id": reliable.receipt_id, "provider_request_id": reliable.provider_request_id,
                           "provenance": reliable.provenance}}
    settle_gate = CONTEXT.Event()
    settlement = spawn(urls, "settle", REAPER, command, preflight_gate=settle_gate)
    assert worker[3]["pid"] != settlement[3]["pid"]
    assert worker[3]["backend_pid"] != settlement[3]["backend_pid"]
    settlement[1].set()
    released = settlement[2].get(timeout=10)
    assert released["kind"] == "preflight_released"
    evidence(released)
    idle_witness(urls, settlement[3]["backend_pid"])
    with hold_subject(urls) as holder:
        settle_gate.set()
        blocked(urls, settlement[3]["backend_pid"], holder.info.backend_pid)
        accounting_gate.set()
        blocked(urls, worker[3]["backend_pid"], settlement[3]["backend_pid"])
        holder.commit()
    assert finish(settlement[0], settlement[2])["result"]["status"] == "SETTLED"
    rolled_back = worker[2].get(timeout=10)
    assert rolled_back["kind"] == "stale_accounting_rollback" and rolled_back["reservation_id"] == str(settled_id)
    evidence(rolled_back)
    after_settlement = persisted(urls)
    assert rolled_back["complete_relation_sha256"] == digest(after_settlement)
    idle_witness(urls, worker[3]["backend_pid"])
    with connect(urls["admin"]) as db:
        assert db.execute("SELECT count(*) FROM kineticloop.command_receipts WHERE client_key=%s",
            (f"reaper-unknown:{settled_id}:1",)).fetchone()[0] == 0
    stale_gate.set()
    assert finish(worker[0], worker[2])["result"] == {"reaped": 0, "unknown": 1, "executable": False}
    after_cleanup = persisted(urls)
    accounting_tables = {"planning_intents", "call_reservations", "call_ledger_events",
                         "command_receipts", "domain_events", "outbox_deliveries", "revision_records"}
    for table in before:
        if table not in accounting_tables:
            assert after_cleanup[table] == after_settlement[table] == before[table]
    with connect(urls["admin"]) as db:
        states = dict(db.execute("SELECT id,status FROM kineticloop.call_reservations").fetchall())
    assert states.pop(settled_id) == "SETTLED" and list(states.values()) == ["OUTCOME_UNKNOWN"]
    payload = read_root(urls, current)[2]
    assert payload["reserved"] == {"calls": 1, "tokens": 100, "tools": 1}
    assert payload["settled"] == {"calls": 1, "tokens": 40, "tools": 0}
    assert read_root(urls, current)[0] == "CANCELLED"
    stale_denials(urls, current, reservations[0])
    evidence({"kind": "accounting_settlement_race_continued", "reaper_pid": worker[3]["pid"],
              "settlement_pid": settlement[3]["pid"], "unknown_completed": 1,
              "stale_mark_unknown_zero_effects": True, "terminal_preserved": "CANCELLED",
              "reliable_receipt_verifier": "declared trusted isolated TEST reconciliation"})


def idle_witness(urls: dict[str, str], backend: int) -> None:
    with connect(urls["admin"]) as db:
        row = db.execute("SELECT state,xact_start FROM pg_stat_activity WHERE pid=%s", (backend,)).fetchone()
        locks = db.execute("SELECT locktype,mode FROM pg_locks WHERE pid=%s AND granted AND locktype='tuple'",
                           (backend,)).fetchall()
    assert row == ("idle", None) and locks == []
    evidence({"kind": "outside_transaction_wait", "backend_pid": backend, "state": row, "tuple_locks": locks})


def wait_terminal(urls: dict[str, str], request: ReapIntent) -> None:
    bound = time.monotonic() + 10
    with connect(urls["admin"], autocommit=True) as db:
        while time.monotonic() < bound:
            row = db.execute("SELECT status,clock_timestamp() FROM kineticloop.planning_intents WHERE id=%s",
                             (request.intent_id,)).fetchone()
            if row[0] == "CANCELLED":
                evidence({"kind": "independent_terminal", "status": row[0], "server_time": row[1]})
                return
    raise AssertionError("independent reaper did not progress within bounded supervisor deadline")


def test_independent_reaper_survives_worker_loss(database_urls: dict[str, str]) -> None:
    import queue

    urls = database_urls
    reset(urls)
    root = admit(urls)
    current = facts(urls, root)
    with connect(urls["admin"]) as db:
        manifest = db.execute("SELECT current_manifest_id FROM kineticloop.user_decision_state WHERE subject_id=%s", (SUBJECT,)).fetchone()[0]
    worker_ready, worker_stop = CONTEXT.Event(), CONTEXT.Event()
    ordinary = CONTEXT.Queue(maxsize=1)
    ordinary.put((current, manifest))
    worker = spawn(urls, "worker", PROGRESS, None, ready=worker_ready, stop=worker_stop,
                   ordinary_work=ordinary)
    worker[1].set()
    received = worker[2].get(timeout=10)
    assert received == {"kind": "ordinary_work_received", "pid": worker[0].pid, "idle": True}
    evidence(received)
    assert worker_ready.wait(10)
    idle_witness(urls, worker[3]["backend_pid"])
    ordinary.put((current, manifest))
    with pytest.raises(queue.Full):
        ordinary.put_nowait("more-work")
    # Registered admission uses its independent channel while ordinary capacity is full.
    admission = spawn(urls, "admit", PROGRESS, None)
    admission[1].set()
    joined = finish(admission[0], admission[2])["result"]
    assert joined["intent_id"] == root["intent_id"]
    reaper_ready, reaper_stop = CONTEXT.Event(), CONTEXT.Event()
    reaper = spawn(urls, "reaper_loop", REAPER, None, ready=reaper_ready, stop=reaper_stop)
    idle_witness(urls, reaper[3]["backend_pid"])
    reaper[1].set()
    assert reaper_ready.wait(10)
    heartbeat_bound = time.monotonic() + 8
    with connect(urls["admin"], autocommit=True) as observer:
        while time.monotonic() < heartbeat_bound:
            heartbeat = observer.execute(
                "SELECT count(*),clock_timestamp() FROM kineticloop.command_receipts "
                "WHERE command_kind='RenewLease' AND status='SUCCEEDED'"
            ).fetchone()
            if heartbeat[0] > 0:
                evidence({"kind": "heartbeat_committed", "receipts": heartbeat[0],
                          "server_time": heartbeat[1], "worker_pid": worker[0].pid})
                break
        else:
            raise AssertionError("worker heartbeat did not commit within bounded observation")
    worker[0].terminate()
    worker[0].join(10)
    assert worker[0].exitcode is not None and worker[0].exitcode < 0
    lost = facts(urls, root)
    wait_elapsed(urls, lost)
    wait_terminal(urls, lost)
    reaper_stop.set()
    result = finish(reaper[0], reaper[2])["result"]
    assert result["reaped"] == 1
    no_effect(urls, lambda: acquire(urls, lost, identity=WORKER2, key="after-terminal"))
    ordinary.close()
    ordinary.join_thread()
    evidence({"kind": "worker_loss", "worker_pid": worker[0].pid, "exitcode": worker[0].exitcode,
              "reaper_pid": reaper[0].pid, "admission_pid": admission[0].pid,
              "ordinary_capacity_saturated": True, "ordinary_worker_consumed_job": True,
              "independent_channels": True})
    # Restart/takeover before termination, preserving the original root limits.
    reset(urls)
    root = admit(urls)
    acquire(urls, facts(urls, root), seconds=1)
    old = facts(urls, root)
    initial = read_root(urls, old)
    wait_elapsed(urls, old)
    cached = scan(urls)[0]
    with connect(urls["admin"]) as db:
        manifest = db.execute("SELECT current_manifest_id FROM kineticloop.user_decision_state WHERE subject_id=%s", (SUBJECT,)).fetchone()[0]
    ready, stop = CONTEXT.Event(), CONTEXT.Event()
    restarted = spawn(urls, "worker", WORKER2, old, ready=ready, stop=stop, manifest=manifest)
    restarted[1].set()
    assert ready.wait(10)
    stop.set()
    assert finish(restarted[0], restarted[2])["result"]["fence"] == 2
    assert read_root(urls, old)[1:3] == initial[1:3]
    no_effect(urls, lambda: reap(urls, cached))
    stale_denials(urls, old)


def test_reaper_cannot_reverse_t6_success(database_urls: dict[str, str]) -> None:
    urls = database_urls
    reset(urls)
    root = admit(urls)
    acquire(urls, facts(urls, root), seconds=1)
    old = facts(urls, root)
    wait_elapsed(urls, old)
    cached = scan(urls)[0]
    lease = acquire(urls, old, seconds=30, key="reacquire-for-preparation")
    with connect(urls["admin"]) as db:
        manifest = db.execute("SELECT current_manifest_id FROM kineticloop.user_decision_state WHERE subject_id=%s", (SUBJECT,)).fetchone()[0]
    # Immutable T6 inputs plus COMMIT_READY are explicit upstream instrumentation;
    # no bundle/head/auth/success/receipt winner is ever seeded.
    command = upstream(urls, {"manifest_id": str(manifest)}, existing=(root, lease))
    before = persisted(urls)
    assert before["daily_plan_heads"] == [] and before["authorization_issuances"] == []
    operation_gate = CONTEXT.Event()
    commit = spawn(urls, "commit", PROGRESS, command, preflight_gate=operation_gate)
    reaper = spawn(urls, "reap", REAPER, cached)
    commit[1].set()
    released = commit[2].get(timeout=10)
    assert released["kind"] == "preflight_released"
    evidence(released)
    idle_witness(urls, commit[3]["backend_pid"])
    with hold_subject(urls) as holder:
        operation_gate.set()
        blocked(urls, commit[3]["backend_pid"], holder.info.backend_pid)
        reaper[1].set()
        blocked(urls, reaper[3]["backend_pid"], commit[3]["backend_pid"])
        holder.commit()
    committed = finish(commit[0], commit[2])["result"]
    after = persisted(urls)
    denied = finish(reaper[0], reaper[2], denial=True)
    assert denied["post_rollback_root_state"][0] == "FOUND_VALID_PLAN"
    assert persisted(urls) == after
    assert len(after["daily_plan_heads"]) == len(after["authorization_issuances"]) == 1
    assert read_root(urls, old)[0] == "FOUND_VALID_PLAN"
    with connect(urls["admin"]) as db:
        assert db.execute("SELECT status FROM kineticloop.planning_attempts WHERE id=%s", (old.attempt_id,)).fetchone()[0] == "COMMITTED"
        db.commit()
        replay = ProtocolExecutionService(db, IDENTITY).commit(command)
        assert replay["bundle_id"] == committed["bundle_id"] and replay["executable"] is False
    assert scan(urls) == ()  # commit-before-scan preserves the same complete history.
    assert persisted(urls) == after
    no_effect(urls, lambda: reap(urls, cached))
    stale_denials(urls, old, commit=changed(command, idempotency_key="expired-old-commit", expected_fence=old.fence))
    assert persisted(urls) == after
    evidence({"kind": "t6_success_preserved", "owner": "ProtocolExecutionService.commit/T6CommitCoordinator",
              "instrumented_inputs": ["S26", "S34-S37", "COMMIT_READY"],
              "seeded_success": False, "complete_relation_sha256": digest(after),
              "scan_before_commit_and_commit_before_scan": True})

def seed_inputs(urls: dict[str, str]) -> None:
    """Declared trusted upstream inputs only; never tested owner outputs."""
    validate_database(urls)
    with connect(urls["admin"], autocommit=True) as db:
        tables = db.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='kineticloop'"
        ).fetchall()
        db.execute(
            psycopg.sql.SQL("TRUNCATE {} CASCADE").format(
                psycopg.sql.SQL(",").join(
                    psycopg.sql.Identifier("kineticloop", r[0]) for r in tables
                )
            )
        )
        db.execute("SET session_replication_role=replica")
        now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        db.execute(
            "INSERT INTO kineticloop.safety_registry_state(id,registry_revision) VALUES (1,0)"
        )
        db.execute(
            "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) VALUES (%s,%s,'test:kl036','1',%s,%s)",
            (POLICY, SUBJECT, digest(POLICY_BODY), Jsonb(POLICY_BODY)),
        )
        db.execute(
            "INSERT INTO kineticloop.program_versions(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test:kl036',1)",
            (PROGRAM, SUBJECT),
        )
        db.execute(
            "INSERT INTO kineticloop.command_receipts(id,subject_id,status,command_kind,client_key,actor_scope,request_hash) VALUES (%s,%s,'SUCCEEDED','TRUSTED_UPSTREAM_INPUT','baseline','fixture','baseline')",
            (BASIS_EVENT, SUBJECT),
        )
        db.execute(
            "INSERT INTO kineticloop.domain_events(id,subject_id,aggregate_type,aggregate_identity,aggregate_revision,event_type,ref_s02_id) VALUES (%s,%s,'INPUT','trusted-upstream',1,'TRUSTED_UPSTREAM_INPUT',%s)",
            (BASIS_EVENT, SUBJECT, BASIS_EVENT),
        )
        db.execute(
            "INSERT INTO kineticloop.factset_revisions(id,subject_id,factset_identity,status,storage_mode,member_revision,completed_member_revision,membership_digest,sealed_at,typed_payload) VALUES (%s,%s,'test:kl036','SEALED','FULL',0,0,'empty',%s,%s)",
            (
                FACTSET,
                SUBJECT,
                now,
                Jsonb({"captured_input_frontier": digest("frontier"), "captured_epoch": 0}),
            ),
        )
        db.execute(
            "INSERT INTO kineticloop.user_decision_state(subject_id,input_frontier_hash,current_factset_id,active_policy_bundle_id,active_program_id,execution_basis_event_id) VALUES (%s,%s,%s,%s,%s,%s)",
            (SUBJECT, digest("frontier"), FACTSET, POLICY, PROGRAM, BASIS_EVENT),
        )
        db.execute(
            "INSERT INTO kineticloop.evaluation_releases(id,subject_id,release_namespace,release_version,content_hash) VALUES (%s,%s,'test:kl036','1',%s)",
            (STATIC, SUBJECT, digest("test:static")),
        )
        for artifact, kind, name, end, approval in (
            (ROOT_ARTIFACT, "POLICY_BUNDLE", "test:engine", now + timedelta(hours=2), None),
            (STATIC, "PROMPT", "test:static", None, str(POLICY_ARTIFACT)),
            (POLICY_ARTIFACT, "POLICY", "test:policy", now + timedelta(hours=3), None),
        ):
            db.execute(
                "INSERT INTO kineticloop.safety_artifacts(id,artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,timeless_approval_policy,timeless_approval_reason,ref_s05_id,ref_s48_id) VALUES (%s,%s,%s,'1',%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    artifact,
                    kind,
                    name,
                    digest(POLICY_BODY) if artifact != STATIC else digest(name),
                    "TIMELESS" if end is None else "BOUNDED",
                    now - timedelta(minutes=1),
                    end,
                    approval,
                    "approved static rules" if approval else None,
                    POLICY if artifact != STATIC else None,
                    STATIC if artifact == STATIC else None,
                ),
            )
        for a, b in ((ROOT_ARTIFACT, STATIC), (STATIC, POLICY_ARTIFACT)):
            db.execute(
                "INSERT INTO kineticloop.safety_artifact_dependencies(artifact_id,dependency_artifact_id) VALUES (%s,%s)",
                (a, b),
            )
        db.execute(
            "INSERT INTO kineticloop.projection_versions(id,subject_id,projection_kind,input_basis_hash,computed_at,valid_until) VALUES (%s,%s,'EXPOSURE',%s,%s,%s)",
            (PROJECTION, SUBJECT, digest("projection"), now, now + timedelta(minutes=45)),
        )
        dependencies = []
        for item in DEPS:
            refs = {
                "policy": POLICY if item["kind"] == "POLICY" else None,
                "program": PROGRAM if item["kind"] == "PROGRAM" else None,
                "factset": FACTSET if item["kind"] in {"COLLECTION", "FACTSET"} else None,
            }
            db.execute(
                "INSERT INTO kineticloop.projection_dependencies(id,subject_id,dependency_kind,dependency_semantic_key,collection_signature,ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    SUBJECT,
                    item["kind"],
                    item["key"],
                    item["collection"],
                    refs["policy"],
                    refs["program"],
                    refs["factset"],
                    PROJECTION,
                ),
            )
            dependencies.append(
                {
                    "projection_id": str(PROJECTION),
                    **item,
                    "policy": str(refs["policy"]) if refs["policy"] else None,
                    "program": str(refs["program"]) if refs["program"] else None,
                    "factset": str(refs["factset"]) if refs["factset"] else None,
                    "fact": None,
                    "catalog": None,
                    "mapping": None,
                }
            )
        dependency_hash = digest(
            {
                "projections": [
                    {
                        "id": str(PROJECTION),
                        "role": "EXPOSURE",
                        "projection_kind": "EXPOSURE",
                        "validated_basis_hash": digest("projection"),
                        "dependencies": sorted(dependencies, key=lambda v: (v["kind"], v["key"])),
                    }
                ],
                "catalog_id": None,
                "mapping_id": None,
            }
        )
        artifacts = []
        for row in db.execute(
            "SELECT id,artifact_kind,artifact_identity,artifact_version,content_hash,revision,validity_kind,valid_from,valid_until,timeless_approval_policy,timeless_approval_reason FROM kineticloop.safety_artifacts ORDER BY id"
        ):
            artifacts.append(
                dict(
                    zip(
                        (
                            "artifact_id",
                            "artifact_kind",
                            "artifact_identity",
                            "artifact_version",
                            "content_hash",
                            "artifact_revision",
                            "validity_kind",
                            "valid_from",
                            "valid_until",
                            "timeless_approval_policy",
                            "timeless_approval_reason",
                        ),
                        (
                            str(row[0]),
                            *row[1:7],
                            canonical_certificate_timestamp(row[7], "from"),
                            canonical_certificate_timestamp(row[8], "until") if row[8] else None,
                            row[9],
                            row[10],
                        ),
                    )
                )
            )
            artifacts[-1]["dependency_ids"] = [
                str(r[0])
                for r in db.execute(
                    "SELECT dependency_artifact_id FROM kineticloop.safety_artifact_dependencies WHERE artifact_id=%s ORDER BY dependency_artifact_id",
                    (row[0],),
                )
            ]
        candidate = {
            "manifest_hash": digest("manifest"),
            "dependency_basis_hash": dependency_hash,
            "artifact_dependency_closure_hash": digest(artifacts),
            "artifact_closure_ids": sorted(
                str(a) for a in (ROOT_ARTIFACT, STATIC, POLICY_ARTIFACT)
            ),
            "artifact_root_ids": [str(ROOT_ARTIFACT)],
            "projection_bindings": [
                {"id": str(PROJECTION), "role": "EXPOSURE", "basis_hash": digest("projection")}
            ],
        }
        db.execute(
            "INSERT INTO kineticloop.manifest_builds(id,subject_id,build_identity,status,captured_epoch,captured_input_frontier,ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id,typed_payload) VALUES (%s,%s,'test:kl036','READY',0,%s,%s,%s,%s,%s,%s)",
            (
                BUILD,
                SUBJECT,
                digest("frontier"),
                POLICY,
                PROGRAM,
                FACTSET,
                PROJECTION,
                Jsonb(candidate),
            ),
        )
        db.execute("SET session_replication_role=origin")
    with connect(urls["trusted_admin"], autocommit=True) as db:
        db.execute(
            "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
            (SUBJECT, POLICY, ENVIRONMENT, IDENTITY.principal),
        )
    with connect(urls["admin"]) as db:
        assert all(
            db.execute(f"SELECT count(*) FROM kineticloop.{table}").fetchone()[0] == 0
            for table in TARGETS
        )
        assert db.execute(
            "SELECT current_manifest_id,decision_generation FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone() == (None, 0)

def service(db: Any, identity: ExecutionIdentity = IDENTITY) -> ProtocolExecutionService:
    return ProtocolExecutionService(db, identity)

def publish_request(urls: dict[str, str], key: str = "publish") -> PublishReady:
    with connect(urls["admin"]) as db:
        c = db.execute(
            "SELECT typed_payload FROM kineticloop.manifest_builds WHERE id=%s", (BUILD,)
        ).fetchone()[0]
    return PublishReady(
        SUBJECT,
        key,
        BUILD,
        FACTSET,
        digest("frontier"),
        0,
        PROGRAM,
        POLICY,
        c["dependency_basis_hash"],
        c["artifact_dependency_closure_hash"],
    )

def publish(urls: dict[str, str]) -> Mapping[str, Any]:
    with connect(urls["admin"]) as db:
        return service(db).publish(publish_request(urls))

def wire(kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": "kineticloop-command-v1",
        "command_kind": kind,
        "boundary": "T6" if kind == "CommitBundle" else "T7",
        "command_id": str(uuid4()),
        "actor": {
            "schema": "kineticloop-role-identity-v1",
            "identity_id": IDENTITY.actor.identity_id,
            "role": "test",
        },
        "idempotency_key": kind,
        "request_hash": "0" * 64,
        "subject_id": str(SUBJECT),
        "explicit_scope": None,
        "authorization_scope": {
            "scope": "test_only",
            "subject_id": str(SUBJECT),
            "policy_id": str(POLICY),
            "environment_id": str(ENVIRONMENT),
            "subject_boundary": "isolated_non_production",
            "policy_boundary": "isolated_non_production",
            "environment_boundary": "isolated_non_production",
            "direct_write_allowed": False,
            "command_owner_guard_required": True,
        },
        **extra,
    }

def signed(model: Any, payload: dict[str, Any]) -> Any:
    first = model.model_validate_json(json.dumps(payload))
    return model.model_validate_json(json.dumps({**payload, "request_hash": command_digest(first)}))

def changed(command: Any, **values: Any) -> Any:
    return signed(type(command), {**command.model_dump(mode="json"), **values})

def upstream(urls: dict[str, str], published: Mapping[str, Any], existing: Any = None, lease_seconds: int = 1200) -> CommitBundle:
    """Real admission/lease, then explicitly synthetic missing upstream owner inputs."""
    if existing is None:
        with connect(urls["admin"]) as db:
            with db.transaction():
                now = db.execute("SELECT clock_timestamp()").fetchone()[0]
            planning = LeaseService(db, PlanningIdentity(IDENTITY.actor, SUBJECT))
            admitted = planning.admit_or_revise(
                AdmitOrReviseIntent(
                    SUBJECT, "admit", now.date(), "TRAINING", "test:UTC-v1", {"minutes": 30}
                )
            )
            lease = planning.acquire_lease(
                AcquireLease(
                    SUBJECT,
                    "lease",
                    UUID(admitted["intent_id"]),
                    None,
                    0,
                    1,
                    UUID(admitted["attempt_id"]),
                    lease_seconds,
                )
            )
    else:
        admitted, lease = existing
        with connect(urls["admin"]) as db:
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
    intent, request, attempt, manifest = (
        UUID(admitted["intent_id"]),
        UUID(admitted["request_id"]),
        UUID(admitted["attempt_id"]),
        UUID(published["manifest_id"]),
    )
    snapshot, proposal, demand, resolution, validation = (uuid4() for _ in range(5))
    context = {
        "mandatory_context": True,
        "manifest_id": str(manifest),
        "request_id": str(request),
        "attempt_id": str(attempt),
    }
    content = {
        "kind": "TRAINING",
        "prescribed_minutes": 30,
        "semantic_class": "PRESCRIBED_QUANTITY",
    }
    body = {"prescription": content, "demand_hash": digest("demand")}
    resolved = {
        "coverage": "COMPLETE_FOR_POLICY",
        "consistency": "CONSISTENT",
        "truncation_status": "NOT_TRUNCATED",
        "admission_freshness": [
            {
                "identity": "trusted:admission",
                "revision": 1,
                "valid_from": (now - timedelta(seconds=1)).isoformat(),
                "valid_until": (now + timedelta(minutes=30)).isoformat(),
            }
        ],
    }
    cert = {
        "snapshot_id": str(snapshot),
        "context_hash": digest(context),
        "proposal_hash": digest(body),
        "demand_hash": digest("demand"),
        "resolution_hash": digest(resolved),
        "semantic_validation": "PASS",
        "policy_envelope": "PASS",
        "execution_basis_event_id": str(BASIS_EVENT),
    }
    with connect(urls["admin"], autocommit=True) as db:
        db.execute("SET session_replication_role=replica")
        db.execute(
            "INSERT INTO kineticloop.decision_snapshots(id,subject_id,revision,captured_epoch,context_hash,ref_s24_id,ref_s28_id,ref_s29_id,typed_payload) VALUES (%s,%s,1,0,%s,%s,%s,%s,%s)",
            (snapshot, SUBJECT, digest(context), manifest, request, attempt, Jsonb(context)),
        )
        db.execute(
            "UPDATE kineticloop.planning_attempts SET snapshot_id=%s,status='COMMIT_READY',fence_token=%s WHERE id=%s AND subject_id=%s",
            (snapshot, lease["fence"], attempt, SUBJECT),
        )
        db.execute(
            "INSERT INTO kineticloop.proposal_revisions(id,subject_id,proposal_family_identity,proposal_kind,producer_artifact,demand_feature_id,ref_s26_id,ref_s29_id,content_hash,typed_payload) VALUES (%s,%s,%s,'FITNESS','trusted-synthetic',%s,%s,%s,%s,%s)",
            (
                proposal,
                SUBJECT,
                str(proposal),
                demand,
                snapshot,
                attempt,
                digest(body),
                Jsonb(body),
            ),
        )
        db.execute(
            "INSERT INTO kineticloop.prescription_demand_features(id,subject_id,method_version,feature_hash,basis_hash,ref_s34_id,content_hash) VALUES (%s,%s,'trusted-synthetic',%s,%s,%s,%s)",
            (demand, SUBJECT, digest("demand"), digest(context), proposal, digest("demand")),
        )
        db.execute(
            "INSERT INTO kineticloop.evidence_resolutions(id,subject_id,action_type,action_parameters_hash,resolver_version,query_basis_hash,resolution_expires_at,ref_s05_id,ref_s24_id,typed_payload) VALUES (%s,%s,'TRAINING',%s,'trusted-synthetic',%s,%s,%s,%s,%s)",
            (
                resolution,
                SUBJECT,
                digest(content),
                digest(context),
                now + timedelta(minutes=35),
                POLICY,
                manifest,
                Jsonb(resolved),
            ),
        )
        db.execute(
            "INSERT INTO kineticloop.validation_results(id,subject_id,result,validator_artifact,valid_until,ref_s03_id,ref_s05_id,ref_s24_id,ref_s28_id,ref_s29_id,ref_s34_id,ref_s35_id,ref_s36_id,typed_payload) VALUES (%s,%s,'PASS','trusted-synthetic',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                validation,
                SUBJECT,
                now + timedelta(minutes=40),
                BASIS_EVENT,
                POLICY,
                manifest,
                request,
                attempt,
                proposal,
                demand,
                resolution,
                Jsonb(cert),
            ),
        )
        db.execute("SET session_replication_role=origin")
        assert all(
            db.execute(f"SELECT count(*) FROM kineticloop.{t}").fetchone()[0] == 0
            for t in TARGETS[2:]
        )
        assert (
            db.execute(
                "SELECT status FROM kineticloop.planning_intents WHERE id=%s", (intent,)
            ).fetchone()[0]
            == "RUNNING"
        )
    return signed(
        CommitBundle,
        wire(
            "CommitBundle",
            intent_id=str(intent),
            attempt_id=str(attempt),
            manifest_id=str(manifest),
            expected_generation=1,
            expected_authorization_epoch=0,
            expected_request_revision=1,
            expected_owner_id=IDENTITY.actor.identity_id,
            expected_fence=lease["fence"],
            validation_id=str(validation),
            execution_basis_event_id=str(BASIS_EVENT),
            policy_id=str(POLICY),
            artifact_dependency_closure_hash=publish_request(urls).artifact_dependency_closure_hash,
            commit_identity=str(uuid4()),
            result_fingerprint=digest(
                {
                    "proposal_id": str(proposal),
                    "proposal_hash": digest(body),
                    "validation_id": str(validation),
                }
            ),
        ),
    )
