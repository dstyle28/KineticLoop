"""KL026 owner-driven DC races. Synthetic upstream inputs are explicitly bounded."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier, Event
from typing import Annotated, Any, ClassVar, Literal
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, StringConstraints

from kineticloop.contracts.commands import (
    CanonicalId,
    CommitBundle,
    NonNegativeInt,
    PositiveInt,
    RevokeArtifact,
    StartSession,
)
from kineticloop.contracts.safety_registry import revocation_payload_hash
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.call_ledger import (
    CallLedgerService,
    CancelUndispatched,
    PermitDispatch,
    ReserveCall,
)
from kineticloop.persistence.factsets import (
    BeginBuild,
    BuilderIdentity,
    CanonicalViewService,
    CompleteFactset,
    SealFactset,
    WriteCandidate,
)
from kineticloop.persistence.planning import (
    AcquireLease,
    AdmitOrReviseIntent,
    PlanningIdentity,
    PlanningWorkflowService,
)
from kineticloop.persistence.protocol_execution import ProtocolExecutionService
from kineticloop.persistence.safety_registry import revoke_artifact
from kineticloop.persistence.transactions import (
    EventWrite,
    GuardRequired,
    IdempotencyConflict,
    ReplayNotFound,
    RepositoryTransaction,
    RepositoryTransactionError,
    RestrictedSqlSession,
    execute_command,
    query_execution_eligibility,
    replay_outcome,
)
from kineticloop.protocol.authorization import canonical_certificate_timestamp
from kineticloop.protocol.execution import ExecutionIdentity, PublishReady, command_digest, digest
from kineticloop.protocol.factsets import EvidenceBasis, Member
from kineticloop.workflow.call_ledger import AccountingIdentity

ROOT = Path(__file__).resolve().parents[2]


def load(path: str) -> Any:
    spec = spec_from_file_location("kl026_" + Path(path).stem, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MIGRATIONS = load("tests/db/test_migrations.py")
_NAMESPACE = load("tests/unit/protocol/test_interleaving_namespace.py")


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
) = [UUID(f"00000000-0000-8000-8000-{26000 + n:012x}") for n in range(10)]

ENVIRONMENT = uuid4()

IDENTITY = ExecutionIdentity(
    RoleIdentity(str(uuid4()), ActorRole.TEST),
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

POLICY_BODY = {
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
    "factset_max_delta_depth": 8,
    "authorization_action_scopes": {"TRAINING": "TEST_ONLY"},
    "t2_invalidation_scopes": {
        "ApplyControl": "TEST_ONLY",
        "ClearControl": "TEST_ONLY",
        "AcceptFactRevision": "TEST_ONLY",
    },
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


def seed_inputs(urls: dict[str, str], deadline_seconds: int = 3600) -> None:
    """Declared trusted upstream inputs only; never tested owner outputs."""
    policy_body = json.loads(json.dumps(POLICY_BODY))
    policy_body["planning_admission"]["deadline_seconds"] = deadline_seconds
    with connect(urls["admin"], autocommit=True) as db:
        assert_database(db)
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
            "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) VALUES (%s,%s,'test:kl026','1',%s,%s)",
            (POLICY, SUBJECT, digest(policy_body), Jsonb(policy_body)),
        )
        db.execute(
            "INSERT INTO kineticloop.program_versions(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test:kl026',1)",
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
            "INSERT INTO kineticloop.factset_revisions(id,subject_id,factset_identity,status,storage_mode,member_revision,completed_member_revision,membership_digest,sealed_at,typed_payload) VALUES (%s,%s,'test:kl026','SEALED','FULL',0,0,'empty',%s,%s)",
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
            "INSERT INTO kineticloop.evaluation_releases(id,subject_id,release_namespace,release_version,content_hash) VALUES (%s,%s,'test:kl026','1',%s)",
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
                    digest(policy_body) if artifact != STATIC else digest(name),
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
            "INSERT INTO kineticloop.manifest_builds(id,subject_id,build_identity,status,captured_epoch,captured_input_frontier,ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id,typed_payload) VALUES (%s,%s,'test:kl026','READY',0,%s,%s,%s,%s,%s,%s)",
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


def upstream(
    urls: dict[str, str],
    published: Mapping[str, Any],
    lease_seconds: int = 1200,
    evidence_seconds: int = 1800,
) -> CommitBundle:
    """Real admission/lease, then explicitly synthetic missing upstream owner inputs."""
    with connect(urls["admin"]) as db:
        with db.transaction():
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        planning = PlanningWorkflowService(db, PlanningIdentity(IDENTITY.actor, SUBJECT))
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
                "valid_until": (now + timedelta(seconds=evidence_seconds)).isoformat(),
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
            if t != "authorization_events"
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


def committed(urls: dict[str, str]) -> tuple[CommitBundle, Mapping[str, Any]]:
    command = upstream(urls, publish(urls))
    with connect(urls["admin"]) as db:
        return command, service(db).commit(command)


def start_command(result: Mapping[str, Any]) -> StartSession:
    return signed(
        StartSession,
        wire(
            "StartSession",
            session_id=str(uuid4()),
            action_key="first-start",
            prescription_id=result["prescription_id"],
            authorization_id=result["authorization_id"],
            binding_revision=1,
            expected_authorization_epoch=0,
            content_hash=result["content_hash"],
            artifact_dependency_closure_hash=result["artifact_dependency_closure_hash"],
        ),
    )


def snapshot(urls: dict[str, str]) -> dict[str, Any]:
    with connect(urls["admin"]) as db:
        tables = db.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='kineticloop' ORDER BY tablename"
        ).fetchall()
        return {
            t[0]: db.execute(
                f"SELECT to_jsonb(t) FROM kineticloop.{t[0]} t ORDER BY to_jsonb(t)::text"
            ).fetchall()
            for t in tables
        }


def head_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def assert_database(db: Any) -> None:
    selected = _NAMESPACE.interleaving_namespace(ROOT, head_sha())
    assert db.execute("SELECT current_database()").fetchone() == (selected.database_name,)


def connect(url: str, **kwargs: Any) -> Any:
    from urllib.parse import urlsplit

    selected = _NAMESPACE.interleaving_namespace(ROOT, head_sha())
    if urlsplit(url).path != "/" + selected.database_name:
        raise ValueError("KL026 connection targets foreign/default database")
    return psycopg.connect(url, **kwargs)


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    # Deterministic destructive-entrypoint proof runs before the first real lifecycle.
    with pytest.MonkeyPatch.context() as patch:
        _NAMESPACE.namespace_core(patch, ROOT.parent / "kl026-peer-never-created")
    lifecycle = _NAMESPACE.OwnedLifecycle(ROOT, head_sha())
    started = time.monotonic()
    try:
        urls = _MIGRATIONS.bootstrap_two_phase(lifecycle)
        with connect(urls["admin"]) as db:
            assert_database(db)
            revision = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert revision == _MIGRATIONS.HEAD_REVISION
        yield urls
    finally:
        lifecycle.destroy()
        # Capture namespace inventory without URLs/credentials.
        emit_raw(
            "\nKL026_LIFECYCLE "
            + json.dumps(
                {
                    "tested_commit": lifecycle.owned_sha,
                    "root": str(ROOT),
                    "project": lifecycle.namespace.project_name,
                    "database": lifecycle.namespace.database_name,
                    "commands": lifecycle.inventory,
                    "cleanup": "completed",
                    "elapsed": time.monotonic() - started,
                },
                default=str,
            )
            + "\n"
        )


@pytest.fixture()
def urls(database_urls: dict[str, str]) -> dict[str, str]:
    seed_inputs(database_urls)
    return database_urls


def snapshot_connection(db: Any, tables: tuple[str, ...] | None = None) -> dict[str, Any]:
    return {
        row[0]: db.execute(
            f"SELECT to_jsonb(t) FROM kineticloop.{row[0]} t ORDER BY to_jsonb(t)::text"
        ).fetchall()
        for row in (
            [(table,) for table in tables]
            if tables is not None
            else db.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='kineticloop' ORDER BY tablename"
            ).fetchall()
        )
    }


def read(urls: dict[str, str], sql: str, args: Any = ()) -> Any:
    with connect(urls["admin"]) as db:
        return db.execute(sql, args).fetchall()


def bounded_denial(
    urls: dict[str, str], operation: Callable[[Any], Any], *, match: str | None = None
) -> None:
    before = snapshot(urls)
    with connect(urls["admin"], options="-c statement_timeout=15000") as db:
        with pytest.raises((RepositoryTransactionError, ValueError, psycopg.Error), match=match):
            operation(db)
    assert snapshot(urls) == before  # every relation, receipt, event, outbox, pointer and root


def observe_block(db: Any, winner: int, loser: int) -> dict[str, Any]:
    deadline = time.monotonic() + 0.8
    while time.monotonic() < deadline:
        row = db.execute(
            "SELECT pg_blocking_pids(%s),clock_timestamp(),(SELECT xact_start FROM pg_stat_activity WHERE pid=%s)",
            (loser, loser),
        ).fetchone()
        if winner in row[0]:
            return {
                "winner_pid": winner,
                "loser_pid": loser,
                "blockers": row[0],
                "observed_at": row[1],
                "transaction_start": row[2],
            }
    raise AssertionError("bounded PostgreSQL lock wait was not observed")


def race(
    urls: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    requirement: str,
    first: Callable[[Any], Any],
    second: Callable[[Any], Any],
    *,
    first_registry: bool = False,
    second_registry: bool = False,
    second_denies: bool = False,
    duplicate_preflight: bool = False,
) -> tuple[Any, Any]:
    """Pause real winner after owned mutation/finish, still uncommitted; observe loser."""
    from threading import local

    thread = local()
    locked, release, contender_ready = Event(), Event(), Event()
    pids: dict[str, int] = {}
    owned: dict[str, dict[str, Any]] = {}
    original = RepositoryTransaction.finish
    original_replay = replay_outcome
    preflights = Barrier(2)
    baseline = snapshot(urls)

    def held(db: Any, name: str) -> None:
        if (name == "winner" and first_registry) or (name == "loser" and second_registry):
            # Management login intentionally has no SELECT grants. Preserve the full
            # prior user state; global outputs are asserted independently after commit.
            owned[name] = owned.get("winner", baseline)
        else:
            owned[name] = snapshot_connection(db)
        if name == "winner":
            locked.set()
            assert release.wait(8), "winner release deadline"

    def finish(tx: RepositoryTransaction) -> None:
        original(tx)
        if getattr(thread, "db", None) is not None:
            held(thread.db, thread.name)

    def synchronized_replay(*args: Any, **kwargs: Any) -> Any:
        try:
            return original_replay(*args, **kwargs)
        except ReplayNotFound:
            # Both idle-connection lookups actually miss before either mutation.
            # Delay only the loser after its real lookup, so it must use the fresh
            # S01 receipt recheck after the winning commit (ACK-loss window).
            assert args[0].info.transaction_status is TransactionStatus.IDLE
            preflights.wait(8)
            if thread.name == "loser":
                assert locked.wait(8), "same-key preflight winner deadline"
            raise

    class RegistryCursor(psycopg.Cursor[Any]):
        def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
            result = super().execute(query, params, **kwargs)
            if "registry_revoke_artifact(" in str(query):
                held(self.connection, thread.name)
            return result

    def run(operation: Callable[[Any], Any], name: str, registry: bool) -> Any:
        try:
            with connect(
                urls["trusted_admin"] if registry else urls["admin"],
                cursor_factory=RegistryCursor if registry else psycopg.Cursor,
                application_name="kl026-" + name,
                options="-c statement_timeout=15000",
            ) as db:
                thread.db, thread.name = db, name
                pids[name] = db.info.backend_pid
                if name == "loser":
                    contender_ready.set()
                return operation(db)
        except (RepositoryTransactionError, ValueError, psycopg.Error) as error:
            return error

    started = time.monotonic()
    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
        patch.setattr(RepositoryTransaction, "finish", finish)
        if duplicate_preflight:
            patch.setattr(sys.modules[__name__], "replay_outcome", synchronized_replay)
        winner = pool.submit(run, first, "winner", first_registry)
        if duplicate_preflight:
            loser = pool.submit(run, second, "loser", second_registry)
        try:
            assert locked.wait(8), (
                f"winner never reached owned finish: {winner.result(timeout=1) if winner.done() else 'still running'}"
            )
            if not duplicate_preflight:
                loser = pool.submit(run, second, "loser", second_registry)
            assert contender_ready.wait(8)
            with connect(urls["admin"], autocommit=True) as observer:
                witness = observe_block(observer, pids["winner"], pids["loser"])
        finally:
            release.set()
        a, b = winner.result(timeout=8), loser.result(timeout=8)
    assert not isinstance(a, Exception), a
    if second_denies:
        assert isinstance(b, Exception), b
        assert_race_snapshot(urls, owned["winner"], registry=first_registry)
    else:
        assert not isinstance(b, Exception), b
        assert_race_snapshot(urls, owned["loser"], registry=second_registry)
    assert time.monotonic() - started < 12
    emit_raw(
        "\nKL026_DC "
        + json.dumps(
            {
                "requirement": requirement,
                "tested_commit": head_sha(),
                "witness": witness,
                "second_denies": second_denies,
                "outcomes": [a, str(b) if isinstance(b, Exception) else b],
                "persisted": snapshot(urls),
                "elapsed": time.monotonic() - started,
            },
            default=str,
        )
        + "\n"
    )
    return a, b


def apply_control(db: Any, key: str) -> Any:
    receipt, event, control = uuid4(), uuid4(), uuid4()

    def operation(tx: RepositoryTransaction) -> Any:
        tx.lock_subject()
        epoch, policy = db.execute(
            "SELECT authorization_epoch,active_policy_bundle_id FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone()

        def mutation(session: RestrictedSqlSession) -> Any:
            session.insert(
                "S17",
                {
                    "id": control,
                    "subject_id": SUBJECT,
                    "control_identity": str(control),
                    "control_revision": 1,
                    "scope": "TEST_ONLY",
                    "status": "STOP",
                    "ref_s02_id": receipt,
                    "ref_s05_id": policy,
                },
            )
            session.insert(
                "S18",
                {
                    "id": uuid4(),
                    "subject_id": SUBJECT,
                    "control_identity": str(control),
                    "execution_scope": "TEST_ONLY",
                    "head_revision": 1,
                    "status": "ACTIVE",
                    "ref_s17_id": control,
                },
            )
            session.insert(
                "S43",
                {
                    "id": uuid4(),
                    "subject_id": SUBJECT,
                    "event_kind": "EPOCH_INVALIDATED",
                    "scope": "TEST_ONLY",
                    "causation_key": key,
                    "invalidated_epoch": epoch + 1,
                    "ref_s17_id": control,
                    "ref_s02_id": receipt,
                },
            )
            session.update(
                "S01",
                {"authorization_epoch": epoch + 1, "last_control_event_id": control},
                {"subject_id": SUBJECT},
            )
            return {"control_id": str(control), "epoch": epoch + 1}

        return tx.idempotent_outcome(
            receipt_id=receipt,
            actor_scope=IDENTITY.key,
            client_key=key,
            request_hash=digest(key),
            mutation=mutation,
            invalidation_scope="TEST_ONLY",
            event=EventWrite(event, "CONTROL", key, 1, "CONTROL_APPLIED", "execution", uuid4()),
        )

    return execute_command(db, "ApplyControl", SUBJECT, operation)


def revoke_command(urls: dict[str, str], key: str) -> tuple[RevokeArtifact, datetime]:
    with connect(urls["admin"]) as db:
        content_hash = db.execute(
            "SELECT content_hash FROM kineticloop.safety_artifacts WHERE id=%s", (POLICY_ARTIFACT,)
        ).fetchone()[0]
        effective = db.execute("SELECT clock_timestamp()").fetchone()[0]
    command = RevokeArtifact.model_validate_json(
        json.dumps(
            {
                "schema_version": "kineticloop-command-v1",
                "command_kind": "RevokeArtifact",
                "boundary": "T2-GLOBAL",
                "command_id": str(uuid4()),
                "actor": {
                    "schema": "kineticloop-role-identity-v1",
                    "identity_id": str(uuid4()),
                    "role": "admin",
                },
                "idempotency_key": key,
                "request_hash": digest(key),
                "subject_id": None,
                "explicit_scope": "global:safety-registry",
                "artifact_id": str(POLICY_ARTIFACT),
                "artifact_content_hash": content_hash,
                "revocation_payload_hash": revocation_payload_hash(
                    effective_at=effective, reason_code="TEST"
                ),
                "causation_incident_id": str(uuid4()),
            }
        )
    )
    return command, effective


def assert_bookkeeping(urls: dict[str, str], kind: str, count: int = 1) -> None:
    rows = read(
        urls,
        "SELECT r.status,r.id,e.id,o.id FROM kineticloop.command_receipts r JOIN kineticloop.domain_events e ON e.ref_s02_id=r.id JOIN kineticloop.outbox_deliveries o ON o.ref_s03_id=e.id WHERE r.command_kind=%s",
        (kind,),
    )
    assert len(rows) == count and all(row[0] == "SUCCEEDED" for row in rows), rows
    assert len({row[1] for row in rows}) == count


def assert_historical(
    urls: dict[str, str], invoke: Callable[[Any], Any], result: Mapping[str, Any]
) -> None:
    before = snapshot(urls)
    with connect(urls["admin"]) as db:
        replay = invoke(db)
    assert replay["replayed"] and not replay["executable"]
    assert all(
        replay[k] == value for k, value in result.items() if k not in {"replayed", "executable"}
    )
    assert snapshot(urls) == before


def assert_current_denied(urls: dict[str, str], issued: Mapping[str, Any]) -> None:
    new = changed(start_command(issued), idempotency_key="current-after-invalidation")
    bounded_denial(urls, lambda db: service(db).start(new))


def test_publish_vs_user_revoke(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    for revoke_first in (True, False):
        seed_inputs(urls)
        request = publish_request(urls)

        def publication(db):
            return service(db).publish(request)

        def control(db):
            return apply_control(db, "stop")

        a, _ = race(
            urls,
            monkeypatch,
            "I01@DC",
            control if revoke_first else publication,
            publication if revoke_first else control,
            second_denies=revoke_first,
        )
        assert_bookkeeping(urls, "ApplyControl")
        assert read(urls, "SELECT authorization_epoch FROM kineticloop.user_decision_state") == [
            (1,)
        ]
        if revoke_first:
            assert read(urls, "SELECT count(*) FROM kineticloop.decision_manifests") == [(0,)]
            assert read(
                urls,
                "SELECT current_manifest_id,decision_generation FROM kineticloop.user_decision_state",
            ) == [(None, 0)]
            assert_bookkeeping(urls, "PublishManifest", 0)
        else:
            historical = snapshot(urls)["decision_manifests"]
            assert len(historical) == 1 and len(snapshot(urls)["manifest_projection_bindings"]) == 1
            assert_historical(urls, publication, a)
            # Real admission/lease plus synthetic old-epoch inputs cannot regain T6 authority.
            command = upstream(urls, a)
            bounded_denial(urls, lambda db: service(db).commit(command))
            assert snapshot(urls)["decision_manifests"] == historical
            assert_bookkeeping(urls, "PublishManifest")


def test_start_vs_user_revoke(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    for revoke_first in (True, False):
        seed_inputs(urls)
        _, issued = committed(urls)
        command = start_command(issued)

        def start(db):
            return service(db).start(command)

        def control(db):
            return apply_control(db, "stop")

        a, _ = race(
            urls,
            monkeypatch,
            "I02@DC",
            control if revoke_first else start,
            start if revoke_first else control,
            second_denies=revoke_first,
        )
        assert_bookkeeping(urls, "ApplyControl")
        assert read(urls, "SELECT count(*) FROM kineticloop.workout_sessions") == [
            (0 if revoke_first else 1,)
        ]
        assert read(urls, "SELECT count(*) FROM kineticloop.execution_bindings") == [
            (0 if revoke_first else 1,)
        ]
        assert_bookkeeping(urls, "StartSession", 0 if revoke_first else 1)
        if not revoke_first:
            assert_historical(urls, start, a)
            assert_current_denied(urls, issued)
            assert_continue_denied(urls, issued, UUID(a["session_id"]))


def artifact_race(
    urls: dict[str, str], monkeypatch: pytest.MonkeyPatch, kind: str, requirement: str
) -> None:
    for revoke_first in (True, False):
        seed_inputs(urls)
        command: Any
        issued: Any = None
        if kind == "publish":
            command = publish_request(urls)
        elif kind == "commit":
            command = upstream(urls, publish(urls))
        else:
            _, issued = committed(urls)
            command = start_command(issued)

        def invoke(db):
            return getattr(service(db), kind)(command)

        revoke, effective = revoke_command(urls, "transitive-revoke")

        def revoke_fn(db):
            return revoke_artifact(db, revoke, effective_at=effective, reason_code="TEST")

        a, _ = race(
            urls,
            monkeypatch,
            requirement,
            revoke_fn if revoke_first else invoke,
            invoke if revoke_first else revoke_fn,
            first_registry=revoke_first,
            second_registry=not revoke_first,
            second_denies=revoke_first,
        )
        assert read(
            urls, "SELECT ref_s49_id,registry_revision FROM kineticloop.artifact_revocation_events"
        ) == [(POLICY_ARTIFACT, 1)]
        assert read(urls, "SELECT registry_revision FROM kineticloop.safety_registry_state") == [
            (1,)
        ]
        # Exact transitive graph, actual revoked grandchild and no S01 fanout.
        assert read(
            urls,
            "SELECT artifact_id,dependency_artifact_id FROM kineticloop.safety_artifact_dependencies ORDER BY artifact_id",
        ) == sorted([(ROOT_ARTIFACT, STATIC), (STATIC, POLICY_ARTIFACT)])
        target = {
            "publish": "decision_manifests",
            "commit": "authorization_issuances",
            "start": "execution_bindings",
        }[kind]
        assert len(snapshot(urls)[target]) == (0 if revoke_first else 1)
        assert_bookkeeping(
            urls,
            {"publish": "PublishManifest", "commit": "CommitBundle", "start": "StartSession"}[kind],
            0 if revoke_first else 1,
        )
        if not revoke_first:
            assert_historical(urls, invoke, a)
            if kind == "commit":
                issued = a
                assert {
                    row[0]
                    for row in read(
                        urls, "SELECT artifact_id FROM kineticloop.authorization_artifact_closure"
                    )
                } == {ROOT_ARTIFACT, STATIC, POLICY_ARTIFACT}
            if issued:
                assert_current_denied(urls, issued)
                if kind == "start":
                    assert_continue_denied(urls, issued, UUID(a["session_id"]))
            else:
                # T3 remains immutable; the exact transitive revoked artifact also denies T6.
                commit = upstream(urls, a)
                bounded_denial(urls, lambda db: service(db).commit(commit))
        before = snapshot(urls)
        with connect(urls["trusted_admin"]) as db:
            assert (
                revoke_artifact(
                    db, revoke, effective_at=effective, reason_code="TEST"
                ).registry_revision
                == 1
            )
        assert snapshot(urls) == before


def test_artifact_revoke_vs_issue(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    artifact_race(urls, monkeypatch, "commit", "I05@DC")


def test_artifact_revoke_vs_start(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    artifact_race(urls, monkeypatch, "start", "I06@DC")


def test_artifact_revoke_vs_publish(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    artifact_race(urls, monkeypatch, "publish", "I07@DC")


Key = Annotated[str, StringConstraints(min_length=1, max_length=512, pattern=r"^\S(?:.*\S)?$")]


class TestCancelIntentRequest(BaseModel):
    __test__: ClassVar[bool] = False
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    command_kind: Literal["CancelIntent"]
    boundary: Literal["T8"]
    subject_id: CanonicalId
    policy_id: CanonicalId
    environment_id: CanonicalId
    principal: Key
    key: Key
    intent_id: CanonicalId
    attempt_id: CanonicalId
    reservation_id: CanonicalId
    expected_request_revision: PositiveInt
    expected_fence: NonNegativeInt


def bind(request, identity, policy, environment, principal, registration):
    """Trusted owner supplies identity and actual registration; request supplies no authority/hash."""
    if (
        type(request) is not TestCancelIntentRequest
        or type(identity) is not PlanningIdentity
        or identity.actor.role is not ActorRole.TEST
        or type(identity.subject_id) is not UUID
        or type(policy) is not UUID
        or type(environment) is not UUID
        or principal not in {"kl_test_subject_1_login", "kl_test_subject_2_login"}
        or request.subject_id != str(identity.subject_id)
        or (request.policy_id, request.environment_id, request.principal)
        != (str(policy), str(environment), principal)
        or registration != ("TEST", policy, environment, principal)
    ):
        raise GuardRequired("exact registered TEST cancellation identity required")
    request = TestCancelIntentRequest.model_validate(request.model_dump(mode="python"))
    return identity.key, request.key, digest(request.model_dump(mode="json"))


def locked_basis(request, row):
    """Pure feasibility predicate for fresh SELECT-only S01->S27->S31 observations."""
    if (
        row["subject_id"] != UUID(request.subject_id)
        or row["intent_id"] != UUID(request.intent_id)
        or row["attempt_id"] != UUID(request.attempt_id)
        or row["reservation_id"] != UUID(request.reservation_id)
        or row["reservation_root"] != row["intent_id"]
        or row["reservation_attempt"] != row["attempt_id"]
    ):
        raise GuardRequired("exact root/attempt/reservation required")
    if row["status"] == "FOUND_VALID_PLAN":
        return "COMPLETED_FACT"
    if (
        row["status"] not in {"ADMITTED", "RUNNING"}
        or row["request_revision"] != request.expected_request_revision
        or row["fence"] != request.expected_fence
        or row["reservation_status"] not in {"RESERVED", "DISPATCH_INTENT"}
    ):
        raise GuardRequired("terminal/stale cancellation basis")
    return "CANCELLED"


def historical(request, receipt):
    """Bounded successful S02 observation under S01, before current live-root checks."""
    if receipt is None:
        return None
    request_hash, status, payload = receipt
    if (
        request_hash != digest(request.model_dump(mode="json"))
        or status != "SUCCEEDED"
        or "outcome" not in payload
    ):
        raise IdempotencyConflict("command key request hash/outcome mismatch")
    return {**payload["outcome"], "replayed": True, "executable": False}


def cancellation_registration(db: Any, subject: UUID) -> Any:
    return db.execute(
        "SELECT scope.namespace,scope.policy_id,scope.environment_id,binding.principal_name "
        "FROM kineticloop.subject_scopes scope JOIN kineticloop.subject_principal_bindings binding "
        "ON binding.subject_id=scope.subject_id AND binding.namespace=scope.namespace "
        "WHERE scope.subject_id=%s",
        (subject,),
    ).fetchone()


def cancel_intent(
    db: Any,
    command: TestCancelIntentRequest,
    identity: PlanningIdentity | None = None,
) -> Mapping[str, Any]:
    """HG039-ratified TEST recipe over the unchanged restricted T8 owner."""
    trusted = PlanningIdentity(IDENTITY.actor, SUBJECT) if identity is None else identity
    # Scope and trusted identity are checked before any historical replay. The existing
    # idle-connection registration guard is followed by a fresh binding under S01.
    bind(
        command,
        trusted,
        POLICY,
        ENVIRONMENT,
        IDENTITY.principal,
        ("TEST", POLICY, ENVIRONMENT, IDENTITY.principal),
    )
    service(db)._guard(trusted.subject_id)
    actor, key, request_hash = bind(
        command,
        trusted,
        POLICY,
        ENVIRONMENT,
        IDENTITY.principal,
        ("TEST", POLICY, ENVIRONMENT, IDENTITY.principal),
    )
    try:
        prior = replay_outcome(
            db,
            "CancelIntent",
            trusted.subject_id,
            actor_scope=actor,
            client_key=key,
            request_hash=request_hash,
        )
        return {**prior, "replayed": True, "executable": False}
    except ReplayNotFound:
        pass
    intent, reservation = UUID(command.intent_id), UUID(command.reservation_id)

    def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
        tx.lock_subject()
        bind(
            command,
            trusted,
            POLICY,
            ENVIRONMENT,
            IDENTITY.principal,
            cancellation_registration(db, trusted.subject_id),
        )
        # SELECT-only successful receipt lookup needs no receipt lock before S27/S31.
        # S01 serializes same-key contenders; history is checked before live-root guards.
        prior = db.execute(
            "SELECT request_hash,status,typed_payload FROM kineticloop.command_receipts "
            "WHERE subject_id=%s AND actor_scope=%s AND command_kind='CancelIntent' AND client_key=%s",
            (trusted.subject_id, actor, key),
        ).fetchone()
        previous = historical(command, prior)
        if previous is not None:
            return previous
        tx.lock_intents((intent,))
        tx.lock_reservations((reservation,))
        row = db.execute(
            "SELECT i.subject_id,i.id,i.current_attempt_id,c.id,c.ref_s27_id,c.ref_s29_id,"
            "i.status,r.request_revision,i.fence_token,c.status,i.typed_payload,"
            "i.result_bundle_revision_id,i.result_authorization_id,c.typed_payload "
            "FROM kineticloop.planning_intents i JOIN kineticloop.planning_request_revisions r "
            "ON r.id=i.current_request_revision_id AND r.subject_id=i.subject_id "
            "JOIN kineticloop.planning_attempts a ON a.id=i.current_attempt_id AND a.subject_id=i.subject_id "
            "AND a.ref_s27_id=i.id AND a.ref_s28_id=r.id "
            "JOIN kineticloop.call_reservations c ON c.subject_id=i.subject_id AND c.id=%s "
            "WHERE i.subject_id=%s AND i.id=%s",
            (reservation, trusted.subject_id, intent),
        ).fetchone()
        if row is None:
            raise GuardRequired("exact cancellation root/attempt/reservation required")
        basis = dict(
            zip(
                (
                    "subject_id",
                    "intent_id",
                    "attempt_id",
                    "reservation_id",
                    "reservation_root",
                    "reservation_attempt",
                    "status",
                    "request_revision",
                    "fence",
                    "reservation_status",
                ),
                row[:10],
                strict=True,
            )
        )
        if locked_basis(command, basis) == "COMPLETED_FACT":
            return {
                "intent_id": str(intent),
                "status": row[6],
                "completed_fact": row[10],
                "bundle_id": str(row[11]),
                "authorization_id": str(row[12]),
                "executable": False,
            }

        def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
            session.update(
                "S27", {"status": "CANCELLED"}, {"subject_id": trusted.subject_id, "id": intent}
            )
            return {"intent_id": str(intent), "status": "CANCELLED", "executable": False}

        outcome, replayed = tx.idempotent_outcome(
            receipt_id=uuid4(),
            actor_scope=actor,
            client_key=key,
            request_hash=request_hash,
            mutation=mutation,
            event=EventWrite(
                uuid4(),
                "PLANNING_COMMAND",
                digest([actor, "CancelIntent", key]),
                1,
                "INTENT_CANCELLED",
                "planning",
                uuid4(),
            ),
        )
        return {**outcome, "replayed": replayed, "executable": False}

    return execute_command(db, "CancelIntent", trusted.subject_id, operation)


def cancel_request(
    root: UUID, attempt: UUID, reservation: UUID, key: str = "root-cancel"
) -> TestCancelIntentRequest:
    return TestCancelIntentRequest.model_validate(
        {
            "command_kind": "CancelIntent",
            "boundary": "T8",
            "subject_id": str(SUBJECT),
            "policy_id": str(POLICY),
            "environment_id": str(ENVIRONMENT),
            "principal": IDENTITY.principal,
            "key": key,
            "intent_id": str(root),
            "attempt_id": str(attempt),
            "reservation_id": str(reservation),
            "expected_request_revision": 1,
            "expected_fence": 1,
        }
    )


def ledger(db: Any) -> CallLedgerService:
    return CallLedgerService(
        db, PlanningIdentity(IDENTITY.actor, SUBJECT), receipt_verifier=lambda _: True
    )


def cancellation_case(urls: dict[str, str]) -> Any:
    seed_inputs(urls)
    commit = upstream(urls, publish(urls))
    root, attempt = UUID(commit.intent_id), UUID(commit.attempt_id)
    reserve = ReserveCall(
        SUBJECT,
        "reserve",
        root,
        attempt,
        1,
        1,
        "one-physical-request",
        AccountingIdentity("test-provider", "test-model", "config-v1", "price-v1"),
        {"calls": 1, "tokens": 100, "tools": 1},
    )
    with connect(urls["admin"]) as db:
        reserved = ledger(db).reserve(reserve)
    reservation = UUID(reserved["reservation_id"])
    permit = PermitDispatch(SUBJECT, "permit", root, reservation, attempt, 1, 1)
    return commit, reserve, reservation, permit, cancel_request(root, attempt, reservation)


def test_cancel_vs_dispatch(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    for cancel_first in (True, False):
        commit, reserve, reservation, permit, cancellation = cancellation_case(urls)
        root, attempt = UUID(commit.intent_id), UUID(commit.attempt_id)
        # Every stale/cross-root and foreign-scope attempt runs the installed recipe,
        # with whole-relation no-effect assertions before any successful cancellation.
        payload = cancellation.model_dump(mode="python")
        negatives: list[tuple[str, Any]] = [("expected_request_revision", 2), ("expected_fence", 2)]
        negatives += [
            (field, str(uuid4()))
            for field in (
                "intent_id",
                "attempt_id",
                "reservation_id",
                "subject_id",
                "policy_id",
                "environment_id",
            )
        ]
        negatives.append(("principal", "kl_test_subject_2_login"))
        for field, value in negatives:
            bad = TestCancelIntentRequest.model_validate({**payload, field: value})
            bounded_denial(urls, lambda db: cancel_intent(db, bad))
        other_role = PlanningIdentity(RoleIdentity(str(uuid4()), ActorRole.SUBJECT), SUBJECT)
        bounded_denial(urls, lambda db: cancel_intent(db, cancellation, other_role))

        def root_cancel(db):
            return cancel_intent(db, cancellation)

        def dispatch(db):
            return ledger(db).permit(permit)

        before = snapshot(urls)
        a, b = race(
            urls,
            monkeypatch,
            "I03@DC",
            root_cancel if cancel_first else dispatch,
            dispatch if cancel_first else root_cancel,
            second_denies=cancel_first,
        )
        intermediate = snapshot(urls)
        root_row = intermediate["planning_intents"][0][0]
        assert root_row["status"] == "CANCELLED"
        assert {k: v for k, v in root_row.items() if k != "status"} == {
            k: v for k, v in before["planning_intents"][0][0].items() if k != "status"
        }
        reservation_row = intermediate["call_reservations"][0][0]
        assert reservation_row["status"] == ("RESERVED" if cancel_first else "DISPATCH_INTENT")
        assert root_row["typed_payload"]["reserved"] == {"calls": 1, "tokens": 100, "tools": 1}
        # Root termination itself immediately removes every new worker/dispatch/T6 authority.
        bounded_denial(
            urls,
            lambda db: ledger(db).reserve(
                ReserveCall(
                    SUBJECT,
                    "new-reserve",
                    root,
                    attempt,
                    1,
                    1,
                    "other-slot",
                    reserve.accounting,
                    reserve.bounds,
                )
            ),
        )
        bounded_denial(urls, lambda db: service(db).commit(commit))
        bounded_denial(
            urls,
            lambda db: ledger(db).permit(
                PermitDispatch(SUBJECT, "new-permit", root, reservation, attempt, 1, 1)
            ),
        )
        cleanup = CancelUndispatched(SUBJECT, "cleanup", root, reservation)
        if cancel_first:
            with connect(urls["admin"]) as db:
                assert ledger(db).cancel(cleanup)["status"] == "CANCELLED_BEFORE_DISPATCH"
            final = snapshot(urls)
            assert final["planning_intents"][0][0]["status"] == "CANCELLED"
            assert final["planning_intents"][0][0]["typed_payload"]["reserved"] == {
                "calls": 0,
                "tokens": 0,
                "tools": 0,
            }
            assert (
                final["call_reservations"][0][0]["settlement_revision"]
                == reservation_row["settlement_revision"] + 1
            )
            assert len(final["call_ledger_events"]) == len(intermediate["call_ledger_events"]) + 1
            with connect(urls["admin"]) as db:
                assert ledger(db).cancel(cleanup)["replayed"]
            assert snapshot(urls) == final
            assert_bookkeeping(urls, "CancelUndispatched")
            assert_bookkeeping(urls, "PermitDispatch", 0)
            assert_historical(urls, root_cancel, a)
        else:
            assert a.sendable and not a.replayed
            bounded_denial(urls, lambda db: ledger(db).cancel(cleanup))
            assert snapshot(urls)["call_reservations"] == intermediate["call_reservations"]
            with connect(urls["admin"]) as db:
                replay = ledger(db).permit(permit)
            assert replay.replayed and not replay.sendable and replay.reservation_id == reservation
            assert snapshot(urls) == intermediate
            assert_historical(urls, root_cancel, b)
            assert_bookkeeping(urls, "PermitDispatch")
            assert_bookkeeping(urls, "CancelUndispatched", 0)
        conflict = TestCancelIntentRequest.model_validate({**payload, "expected_fence": 2})
        bounded_denial(urls, lambda db: cancel_intent(db, conflict), match="request hash")
        assert_bookkeeping(urls, "CancelIntent")
        assert_bookkeeping(urls, "ReserveCall")
        # No sender/provider is instantiated or called by this DC suite.

    # Two existing roots and reservations prove cross-linkage rejection, beyond
    # nonexistent-ID denials. Both roots come from actual admission/acquire owners.
    commit, reserve, reservation, permit, cancellation = cancellation_case(urls)
    with connect(urls["admin"]) as db:
        with db.transaction():
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        planning = PlanningWorkflowService(db, PlanningIdentity(IDENTITY.actor, SUBJECT))
        other = planning.admit_or_revise(
            AdmitOrReviseIntent(
                SUBJECT,
                "other-root",
                now.date() + timedelta(days=1),
                "TRAINING",
                "test:UTC-v1",
                {"minutes": 30},
            )
        )
        other_root, other_attempt = UUID(other["intent_id"]), UUID(other["attempt_id"])
        lease = planning.acquire_lease(
            AcquireLease(
                SUBJECT,
                "other-lease",
                other_root,
                None,
                0,
                1,
                other_attempt,
                600,
            )
        )
        other_reserved = ledger(db).reserve(
            ReserveCall(
                SUBJECT,
                "other-reserve",
                other_root,
                other_attempt,
                1,
                lease["fence"],
                "other-physical-request",
                reserve.accounting,
                reserve.bounds,
            )
        )
    other_reservation = UUID(other_reserved["reservation_id"])
    mismatched = (
        cancel_request(
            UUID(commit.intent_id), UUID(commit.attempt_id), other_reservation, "cross-root"
        ),
        cancel_request(other_root, other_attempt, reservation, "cross-root-reverse"),
    )
    before = snapshot(urls)
    for request in mismatched:
        bounded_denial(
            urls, lambda db: cancel_intent(db, request), match="exact root/attempt/reservation"
        )
    assert_bookkeeping(urls, "CancelIntent", 0)
    emit_raw(
        "\nKL026_I03_CROSS_ROOT "
        + json.dumps(
            {
                "requirement": "I03@DC",
                "tested_commit": head_sha(),
                "layer": "DC",
                "existing_roots": [commit.intent_id, str(other_root)],
                "existing_reservations": [str(reservation), str(other_reservation)],
                "before_equals_after": snapshot(urls) == before,
                "persisted": snapshot(urls),
            },
            default=str,
        )
        + "\n"
    )

    # Two genuine preflight misses followed by one cancellation and an under-S01
    # successful historical receipt lookup. No fabricated replay or nested accessor.
    commit, reserve, reservation, permit, cancellation = cancellation_case(urls)
    root = UUID(commit.intent_id)
    original, duplicate = race(
        urls,
        monkeypatch,
        "I03@DC",
        lambda db: cancel_intent(db, cancellation),
        lambda db: cancel_intent(db, cancellation),
        duplicate_preflight=True,
    )
    assert not original["replayed"] and duplicate["replayed"]
    assert duplicate == {**original, "replayed": True, "executable": False}
    assert read(urls, "SELECT status FROM kineticloop.planning_intents WHERE id=%s", (root,)) == [
        ("CANCELLED",)
    ]
    assert_bookkeeping(urls, "CancelIntent", 1)
    assert_bookkeeping(urls, "ReserveCall", 1)
    before = snapshot(urls)
    with connect(urls["admin"]) as db:
        historical_result = cancel_intent(db, cancellation)
    assert historical_result == duplicate and snapshot(urls) == before

    # Actual successful T6 facts survive CancelIntent without cancellation bookkeeping.
    commit, reserve, reservation, permit, cancellation = cancellation_case(urls)
    root = UUID(commit.intent_id)
    with connect(urls["admin"]) as db:
        ledger(db).cancel(CancelUndispatched(SUBJECT, "precommit-cleanup", root, reservation))
        completed = service(db).commit(commit)
    before = snapshot(urls)
    with connect(urls["admin"]) as db:
        fact = cancel_intent(db, cancellation)
    assert fact["status"] == "FOUND_VALID_PLAN" and not fact["executable"]
    assert fact["bundle_id"] == completed["bundle_id"]
    assert fact["authorization_id"] == completed["authorization_id"]
    assert snapshot(urls) == before
    assert_bookkeeping(urls, "CancelIntent", 0)
    assert_bookkeeping(urls, "CommitBundle", 1)
    emit_raw(
        "\nKL026_I03_IDENTITY "
        + json.dumps(
            {
                "tested_commit": head_sha(),
                "layer": "DC",
                "stale_and_foreign_denials": 20,
                "same_key_conflict": True,
                "two_actual_preflight_misses": True,
                "one_cancellation_receipt": True,
                "terminal_success_preserved": True,
                "persisted": snapshot(urls),
            },
            default=str,
        )
        + "\n"
    )


EVIDENCE, CANDIDATE, UNDERLYING, ADMISSION = [UUID(int=26100 + n) for n in range(4)]


def seed_admitted_source(urls: dict[str, str]) -> None:
    with connect(urls["admin"]) as db:
        assert_database(db)
        db.execute(
            "INSERT INTO kineticloop.evidence_revisions(id,subject_id,source_connection_identity,source_object_type,source_object_identity,source_revision,trust_class,source_class,command_authority) VALUES (%s,%s,'test:kl026','observation','input','1','USER_REPORTED','USER','NONE')",
            (EVIDENCE, SUBJECT),
        )
        db.execute(
            "INSERT INTO kineticloop.candidate_assertions(id,subject_id,assertion_family_identity,ref_s09_id) VALUES (%s,%s,'test:kl026',%s)",
            (CANDIDATE, SUBJECT, EVIDENCE),
        )
        db.execute(
            "INSERT INTO kineticloop.underlying_events(id,subject_id,event_identity) VALUES (%s,%s,'test:kl026')",
            (UNDERLYING, SUBJECT),
        )
        db.execute(
            "INSERT INTO kineticloop.admission_decisions(id,subject_id,action_scope,decision,ref_s05_id,ref_s09_id,ref_s10_id) VALUES (%s,%s,'TEST_ONLY','ELIGIBLE',%s,%s,%s)",
            (ADMISSION, SUBJECT, POLICY, EVIDENCE, CANDIDATE),
        )


def input_revision(db: Any, key: str) -> Any:
    receipt, event, fact = uuid4(), uuid4(), uuid4()

    def operation(tx: RepositoryTransaction) -> Any:
        tx.lock_subject()
        epoch, frontier = db.execute(
            "SELECT authorization_epoch,input_frontier_hash FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone()

        def mutate(session: RestrictedSqlSession) -> Mapping[str, Any]:
            session.insert(
                "S14",
                {
                    "id": fact,
                    "subject_id": SUBJECT,
                    "stable_fact_identity": key,
                    "fact_kind": "HEALTH_OBSERVATION",
                    "fact_revision": 1,
                    "ref_s10_id": CANDIDATE,
                    "ref_s11_id": UNDERLYING,
                    "ref_s13_id": ADMISSION,
                },
            )
            session.insert(
                "S43",
                {
                    "id": uuid4(),
                    "subject_id": SUBJECT,
                    "event_kind": "EPOCH_INVALIDATED",
                    "invalidated_epoch": epoch + 1,
                    "scope": "TEST_ONLY",
                    "causation_key": key,
                    "ref_s02_id": receipt,
                },
            )
            session.update(
                "S01",
                {"input_frontier_hash": digest([frontier, key]), "authorization_epoch": epoch + 1},
                {"subject_id": SUBJECT},
            )
            return {"fact_id": str(fact), "epoch": epoch + 1}

        return tx.idempotent_outcome(
            receipt_id=receipt,
            actor_scope=IDENTITY.key,
            client_key=key,
            request_hash=digest(key),
            mutation=mutate,
            invalidation_scope="TEST_ONLY",
            event=EventWrite(event, "FACT", key, 1, "FACT_ACCEPTED", "canonical", uuid4()),
        )[0]

    return execute_command(db, "AcceptFactRevision", SUBJECT, operation)


def factset_service(db: Any) -> CanonicalViewService:
    return CanonicalViewService(db, BuilderIdentity(IDENTITY.actor, SUBJECT))


def completed_factset(urls: dict[str, str], key: str, fact: UUID) -> SealFactset:
    with connect(urls["admin"]) as db:
        with db.transaction():
            frontier, epoch = db.execute(
                "SELECT input_frontier_hash,authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
                (SUBJECT,),
            ).fetchone()
        basis = EvidenceBasis((), (ADMISSION,), (), "2026-09-30T00:00:00Z", "TEST_ONLY")
        builder = factset_service(db)
        build = UUID(
            builder.begin_build(BeginBuild(SUBJECT, key, frontier, epoch, PROGRAM, POLICY, basis))[
                "build_id"
            ]
        )
        builder.write_candidate(
            WriteCandidate(
                SUBJECT, key + "-member", build, 0, Member("FACT", key, "TEST_ONLY", fact)
            )
        )
        builder.write_candidate(
            WriteCandidate(
                SUBJECT,
                key + "-admission",
                build,
                1,
                Member("ADMISSION", "admitted-input", "TEST_ONLY", ADMISSION),
            )
        )
        completion = builder.complete_factset(CompleteFactset(SUBJECT, key + "-complete", build, 2))
    return SealFactset(SUBJECT, key + "-seal", build, completion)


def test_seal_vs_input_update(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    for input_first in (True, False):
        seed_inputs(urls)
        seed_admitted_source(urls)
        with connect(urls["admin"]) as db:
            initial = input_revision(db, "initial")
        command = completed_factset(urls, "old", UUID(initial["fact_id"]))

        def seal(db):
            return factset_service(db).seal_factset(command)

        def update(db):
            return input_revision(db, "new-input")

        a, b = race(
            urls,
            monkeypatch,
            "I08@DC",
            update if input_first else seal,
            seal if input_first else update,
            second_denies=input_first,
        )
        assert_bookkeeping(urls, "AcceptFactRevision", 2)
        assert read(urls, "SELECT authorization_epoch FROM kineticloop.user_decision_state") == [
            (2,)
        ]
        if input_first:
            assert read(urls, "SELECT current_factset_id FROM kineticloop.user_decision_state") == [
                (FACTSET,)
            ]
            assert read(
                urls,
                "SELECT status FROM kineticloop.factset_revisions WHERE id=%s",
                (command.build_id,),
            ) == [("READY",)]
            assert_bookkeeping(urls, "SealFactset", 0)
        else:
            historical = read(
                urls,
                "SELECT to_jsonb(f) FROM kineticloop.factset_revisions f WHERE id=%s",
                (command.build_id,),
            )
            members = read(
                urls,
                "SELECT to_jsonb(m) FROM kineticloop.factset_members m WHERE ref_s15_id=%s",
                (command.build_id,),
            )
            assert historical[0][0]["status"] == "SEALED" and len(members) == 2
            next_command = completed_factset(urls, "new", UUID(b["fact_id"]))
            with connect(urls["admin"]) as db:
                factset_service(db).seal_factset(next_command)
            before = snapshot(urls)
            with connect(urls["admin"]) as db:
                replay = seal(db)
            assert replay == a
            assert snapshot(urls) == before
            assert read(urls, "SELECT current_factset_id FROM kineticloop.user_decision_state") == [
                (next_command.build_id,)
            ]
            assert (
                read(
                    urls,
                    "SELECT to_jsonb(f) FROM kineticloop.factset_revisions f WHERE id=%s",
                    (command.build_id,),
                )
                == historical
            )
            assert (
                read(
                    urls,
                    "SELECT to_jsonb(m) FROM kineticloop.factset_members m WHERE ref_s15_id=%s",
                    (command.build_id,),
                )
                == members
            )
            assert_bookkeeping(urls, "SealFactset", 2)


def wait_server(urls: dict[str, str], target: datetime, *, before_seconds: float = 0) -> datetime:
    deadline = time.monotonic() + 5
    with connect(urls["admin"], autocommit=True) as observer:
        while time.monotonic() < deadline:
            now = observer.execute("SELECT clock_timestamp()").fetchone()[0]
            if now >= target - timedelta(seconds=before_seconds):
                return now
    raise AssertionError("trusted clock boundary deadline")


def blocked_expiry(
    urls: dict[str, str],
    operation: Callable[[Any], Any],
    end: datetime,
    requirement: str,
    *,
    registry: bool = False,
) -> None:
    # Reach the final 350 ms using real server time, without overwriting any timestamp.
    before_wait = wait_server(urls, end, before_seconds=0.35)
    assert before_wait < end
    before = snapshot(urls)
    ready = Event()
    pid: list[int] = []

    def contender() -> Any:
        with connect(urls["admin"], options="-c statement_timeout=15000") as db:
            pid.append(db.info.backend_pid)
            ready.set()
            try:
                return operation(db)
            except (RepositoryTransactionError, ValueError, psycopg.Error) as error:
                return error

    with connect(urls["admin"]) as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute(
            "SELECT 1 FROM kineticloop.safety_registry_state WHERE id=1 FOR UPDATE"
            if registry
            else "SELECT 1 FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
            () if registry else (SUBJECT,),
        )
        future = pool.submit(contender)
        try:
            assert ready.wait(3)
            with connect(urls["admin"], autocommit=True) as observer:
                witness = observe_block(observer, blocker.info.backend_pid, pid[0])
                assert witness["observed_at"] < end and witness["transaction_start"] < end
                after = wait_server(urls, end)
                assert after >= end
        finally:
            blocker.commit()
        result = future.result(timeout=8)
    assert isinstance(result, (RepositoryTransactionError, ValueError, psycopg.Error)), result
    # A timeout is not evidence that the fresh post-lock clock denied eligibility.
    assert "timeout" not in str(result).lower(), result
    assert snapshot(urls) == before
    emit_raw(
        "\nKL026_CLOCK_DC "
        + json.dumps(
            {
                "requirement": requirement,
                "tested_commit": head_sha(),
                "expiry": end,
                "before_wait": before_wait,
                "after_wait": after,
                "observed_wait": witness,
                "denial": str(result),
                "persisted_unchanged": before,
            },
            default=str,
        )
        + "\n"
    )


def test_takeover_vs_commit(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    for takeover_first in (False, True):
        seed_inputs(urls)
        commit = upstream(urls, publish(urls), lease_seconds=1 if takeover_first else 1200)
        root, attempt = UUID(commit.intent_id), UUID(commit.attempt_id)
        expiry = read(
            urls, "SELECT lease_expires_at FROM kineticloop.planning_intents WHERE id=%s", (root,)
        )[0][0]
        if takeover_first:
            wait_server(urls, expiry)
        replacement = PlanningIdentity(RoleIdentity(str(uuid4()), ActorRole.TEST), SUBJECT)
        acquire = AcquireLease(SUBJECT, "takeover", root, IDENTITY.key, 1, 1, attempt, 60)

        def takeover(db):
            return PlanningWorkflowService(db, replacement).acquire_lease(acquire)

        def commit_fn(db):
            return service(db).commit(commit)

        a, _ = race(
            urls,
            monkeypatch,
            "I04@DC",
            takeover if takeover_first else commit_fn,
            commit_fn if takeover_first else takeover,
            second_denies=True,
        )
        if takeover_first:
            assert a["fence"] == 2
            assert read(
                urls,
                "SELECT status,fence_token FROM kineticloop.planning_intents WHERE id=%s",
                (root,),
            ) == [("RUNNING", 2)]
            assert_bookkeeping(urls, "CommitBundle", 0)
            assert read(urls, "SELECT count(*) FROM kineticloop.authorization_issuances") == [(0,)]
        else:
            assert read(
                urls,
                "SELECT status,fence_token FROM kineticloop.planning_intents WHERE id=%s",
                (root,),
            ) == [("FOUND_VALID_PLAN", 1)]
            assert_bookkeeping(urls, "CommitBundle")
            assert_bookkeeping(urls, "AcquireLease")  # original acquisition only
            assert_historical(urls, commit_fn, a)
    # Lease and root-deadline boundaries independently cross during observed real locks.
    for boundary in ("lease", "deadline"):
        seed_inputs(urls, deadline_seconds=3 if boundary == "deadline" else 3600)
        commit = upstream(urls, publish(urls), lease_seconds=1 if boundary == "lease" else 1200)
        end = read(
            urls,
            f"SELECT {'lease_expires_at' if boundary == 'lease' else 'deadline'} FROM kineticloop.planning_intents WHERE id=%s",
            (UUID(commit.intent_id),),
        )[0][0]
        blocked_expiry(urls, lambda db: service(db).commit(commit), end, "I04@DC/" + boundary)
        bounded_denial(urls, lambda db: service(db).commit(commit))
        assert_bookkeeping(urls, "CommitBundle", 0)
    # Independent before-deadline owner success with a finite actual admission deadline.
    seed_inputs(urls, deadline_seconds=3)
    commit = upstream(urls, publish(urls))
    with connect(urls["admin"]) as db:
        issued = service(db).commit(commit)
    assert issued["authorization_id"]
    assert_bookkeeping(urls, "CommitBundle")


def test_expiry_vs_start(urls: dict[str, str]) -> None:
    for registry in (False, True):
        seed_inputs(urls)
        commit = upstream(urls, publish(urls), evidence_seconds=3)
        with connect(urls["admin"]) as db:
            issued = service(db).commit(commit)
        authorization = read(
            urls,
            "SELECT valid_until,validity_certificate FROM kineticloop.authorization_issuances WHERE id=%s",
            (UUID(issued["authorization_id"]),),
        )[0]
        end = authorization[0]
        # The minimum is the upstream admission freshness dependency, computed by T6.
        certificate = authorization[1]
        freshness = [
            item
            for item in certificate["dependencies"]
            if item["dependency_kind"] == "EVIDENCE_ADMISSION_FRESHNESS"
        ]
        assert (
            len(freshness) == 1
            and canonical_certificate_timestamp(end, "minimum validity end")
            == freshness[0]["valid_until"]
        )
        command = start_command(issued)
        with connect(urls["admin"]) as db:
            started = service(db).start(command)
        assert datetime.fromisoformat(started["accepted_at"]) < end
        assert_bookkeeping(urls, "StartSession")
        next_start = changed(start_command(issued), idempotency_key="queued-start")
        blocked_expiry(
            urls, lambda db: service(db).start(next_start), end, "I09@DC", registry=registry
        )
        assert_historical(urls, lambda db: service(db).start(command), started)
        assert_current_denied(urls, issued)
        assert_continue_denied(urls, issued, UUID(started["session_id"]))
        assert read(urls, "SELECT count(*) FROM kineticloop.execution_bindings") == [(1,)]
        assert_bookkeeping(urls, "StartSession")


def assert_race_snapshot(urls: dict[str, str], expected: dict[str, Any], *, registry: bool) -> None:
    actual = snapshot(urls)
    global_outputs = {
        "registry_management_receipts",
        "registry_audit_events",
        "registry_outbox",
        "artifact_revocation_events",
        "safety_registry_state",
    }
    assert {k: v for k, v in actual.items() if not registry or k not in global_outputs} == {
        k: v for k, v in expected.items() if not registry or k not in global_outputs
    }
    if registry:
        assert all(len(actual[table]) == 1 for table in global_outputs)
        rows = read(
            urls,
            "SELECT m.command_key,m.artifact_id,m.registry_revision,a.revocation_id,o.revocation_id,e.ref_s49_id,s.registry_revision FROM kineticloop.registry_management_receipts m JOIN kineticloop.registry_audit_events a ON a.revocation_id=m.revocation_id JOIN kineticloop.registry_outbox o ON o.delivery_id=m.outbox_delivery_id AND o.revocation_id=m.revocation_id JOIN kineticloop.artifact_revocation_events e ON e.id=m.revocation_id JOIN kineticloop.safety_registry_state s ON s.last_revocation_id=e.id",
        )
        assert len(rows) == 1 and rows[0][0:3] == ("transitive-revoke", POLICY_ARTIFACT, 1)
        assert rows[0][3] == rows[0][4] and rows[0][5:] == (POLICY_ARTIFACT, 1)


def emit_raw(value: str) -> None:
    # PYTEST_ADDOPTS=-s in the recorded task environment retains successful witnesses.
    print(value)


def assert_continue_denied(urls: dict[str, str], issued: Mapping[str, Any], session: UUID) -> None:
    before = snapshot(urls)
    with connect(urls["admin"]) as db:
        artifacts = service(db)._artifacts([str(ROOT_ARTIFACT), str(STATIC), str(POLICY_ARTIFACT)])
        with db.transaction():
            day = db.execute(
                "SELECT local_date FROM kineticloop.daily_plan_heads WHERE subject_id=%s",
                (SUBJECT,),
            ).fetchone()[0]
        decision = query_execution_eligibility(
            db,
            command_kind="ContinueSession",
            subject_id=SUBJECT,
            artifact_ids=[a.artifact_id for a in artifacts],
            artifact_identities=artifacts,
            local_date=day,
            session_id=session,
            prescription_id=UUID(issued["prescription_id"]),
            authorization_id=UUID(issued["authorization_id"]),
            execution_scope="TEST_ONLY",
        )
        assert not decision.is_executable and decision.denial_reasons == (
            "CURRENT_AUTHORITY_DENIED",
        )
    assert snapshot(urls) == before
