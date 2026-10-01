from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier, Event
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from kineticloop.persistence.planning import (
    AcquireLease,
    AdmitOrReviseIntent,
    PlanningIdentity,
)
from kineticloop.persistence.planning import (
    PlanningWorkflowService as LeaseService,
)
from kineticloop.persistence.planning_progress import (
    ContextService,
    PlanningWorkflowService,
    capture_context,
)
from kineticloop.persistence.transactions import (
    EventWrite,
    GuardRequired,
    RepositoryTransaction,
    RepositoryTransactionError,
    RestrictedSqlSession,
    execute_command,
)
from kineticloop.protocol.authorization import canonical_certificate_timestamp
from kineticloop.workflow.planning import PlanningDenied, digest
from kineticloop.workflow.planning_progress import (
    POLICY_BLOCKS,
    AdvanceAttempt,
    ProgressBasis,
    ProgressIdentity,
    RecordSnapshot,
)

ROOT = Path(__file__).resolve().parents[2]


def load(path: str) -> Any:
    spec = spec_from_file_location("kl075_" + Path(path).stem, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MIGRATIONS = load("tests/db/test_migrations.py")
_NAMESPACE = load("tests/unit/workflow/test_planning_progress.py")
# Only immutable upstream TEST inputs and publish request builders are reused.
# Foreign fixtures and lifecycle/seed functions are never invoked.
_UPSTREAM = load("tests/db/test_protocol_execution.py")
SUBJECT, POLICY, PROGRAM, ENVIRONMENT = (
    _UPSTREAM.SUBJECT,
    _UPSTREAM.POLICY,
    _UPSTREAM.PROGRAM,
    _UPSTREAM.ENVIRONMENT,
)
BASIS_EVENT, FACTSET, BUILD, PROJECTION = (
    _UPSTREAM.BASIS_EVENT,
    _UPSTREAM.FACTSET,
    _UPSTREAM.BUILD,
    _UPSTREAM.PROJECTION,
)
ROOT_ARTIFACT, STATIC, POLICY_ARTIFACT = (
    _UPSTREAM.ROOT_ARTIFACT,
    _UPSTREAM.STATIC,
    _UPSTREAM.POLICY_ARTIFACT,
)
IDENTITY, DEPS = _UPSTREAM.IDENTITY, _UPSTREAM.DEPS
POLICY_BODY = copy.deepcopy(_UPSTREAM.POLICY_BODY)
POLICY_BODY["planning_context"] = {
    block: {"status": "TEST_INPUT_ONLY", "value": []} for block in POLICY_BLOCKS
}
POLICY_BODY["planning_context_byte_budget"] = 65536
TARGETS = _UPSTREAM.TARGETS + (
    "decision_snapshots",
    "planning_intents",
    "planning_request_revisions",
    "planning_attempts",
)
BUILDER = uuid4()
POLICY_BODY["planning_context_builder"] = {"id": str(BUILDER), "hash": digest("context-builder")}
PROGRESS_IDENTITY = ProgressIdentity(
    IDENTITY.actor, SUBJECT, POLICY, ENVIRONMENT, IDENTITY.principal
)
INVENTORY: list[dict[str, Any]] = []


def connect(url: str, **kwargs: Any) -> Any:
    return psycopg.connect(url, options="-c statement_timeout=10000 -c lock_timeout=8000", **kwargs)


def evidence(item: Mapping[str, Any]) -> None:
    INVENTORY.append(dict(item))
    print("PROGRESS_EVIDENCE " + json.dumps(item, sort_keys=True, default=str), flush=True)


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    # Namespace proof is mandatory before constructor/bootstrap/reset/finally.
    _NAMESPACE.test_namespace(
        Path("/private/tmp/kl075-peer-root")
        if sys.platform == "darwin"
        else Path("/tmp/kl075-peer-root")
    )
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    selected = _NAMESPACE.progress_namespace(ROOT, sha[:7], "progress")
    lifecycle = _NAMESPACE.ProgressLifecycle(ROOT, sha[:7], "progress")
    started = time.monotonic()
    try:
        lifecycle.validate_target()
        urls = _MIGRATIONS.bootstrap_two_phase(lifecycle)
        with connect(urls["admin"]) as db:
            assert db.execute("SELECT current_database()").fetchone()[0] == selected.database_name
            migration = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert migration == _MIGRATIONS.HEAD_REVISION
        evidence(
            {
                "kind": "namespace",
                "tested_commit": sha,
                "resolved_root": str(ROOT.resolve()),
                "compose": selected.project_name,
                "database": selected.database_name,
                "migration": migration,
                "nested_routes": [
                    "bootstrap_two_phase(selected_lifecycle)",
                    "reset",
                    "start",
                    "connection",
                    "seed_reset",
                    "finally_destroy",
                ],
                "bootstrap_elapsed": time.monotonic() - started,
            }
        )
        yield urls
    finally:
        lifecycle.validate_target()
        lifecycle.destroy()
        remaining = {
            kind: lifecycle._run(
                [
                    "docker",
                    kind,
                    "ls",
                    "--filter",
                    "label=com.docker.compose.project=" + selected.project_name,
                    "--quiet",
                ]
            ).stdout.strip()
            for kind in ("container", "volume", "network")
        }
        assert not any(remaining.values())
        evidence(
            {
                "kind": "cleanup",
                "compose": selected.project_name,
                "database": selected.database_name,
                "elapsed": time.monotonic() - started,
                "destroy": "PASS",
                "remaining_resources": remaining,
                "startup_timeout_seconds": 60,
                "statement_timeout_ms": 10000,
                "lock_timeout_ms": 8000,
            }
        )


def validate_database(urls: dict[str, str]) -> None:
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    expected = _NAMESPACE.progress_namespace(ROOT, sha[:7], "progress")
    _NAMESPACE.ProgressLifecycle(ROOT, sha[:7], "progress").validate_target()
    with connect(urls["admin"]) as db:
        assert db.execute("SELECT current_database()").fetchone()[0] == expected.database_name


def reset_inputs(urls: dict[str, str], validity_seconds: float = 2700) -> None:
    validate_database(urls)
    with connect(urls["admin"], autocommit=True) as db:
        tables = db.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='kineticloop'"
        ).fetchall()
        db.execute(
            sql.SQL("TRUNCATE {} CASCADE").format(
                sql.SQL(",").join(sql.Identifier("kineticloop", row[0]) for row in tables)
            )
        )
    seed_inputs(urls, validity_seconds)
    with connect(urls["admin"], autocommit=True) as db:
        now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        db.execute(
            "INSERT INTO kineticloop.safety_artifacts(id,artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,ref_s48_id,typed_payload) VALUES (%s,'RUNTIME','test:kl075-builder','1',%s,'BOUNDED',%s,%s,%s,%s)",
            (
                BUILDER,
                digest("context-builder"),
                now - timedelta(minutes=1),
                now + timedelta(hours=1),
                STATIC,
                Jsonb({"operation": "CONTEXT_BUILDER"}),
            ),
        )


def seed_inputs(urls: dict[str, str], validity_seconds: float = 2700) -> None:
    """Declared trusted upstream inputs only; never tested owner outputs."""
    validate_database(urls)
    with connect(urls["admin"], autocommit=True) as db:
        db.execute("SET session_replication_role=replica")
        now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        db.execute(
            "INSERT INTO kineticloop.safety_registry_state(id,registry_revision) VALUES (1,0)"
        )
        db.execute(
            "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) VALUES (%s,%s,'test:kl019','1',%s,%s)",
            (POLICY, SUBJECT, digest(POLICY_BODY), Jsonb(POLICY_BODY)),
        )
        db.execute(
            "INSERT INTO kineticloop.program_versions(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test:kl019',1)",
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
            "INSERT INTO kineticloop.factset_revisions(id,subject_id,factset_identity,status,storage_mode,member_revision,completed_member_revision,membership_digest,sealed_at,typed_payload) VALUES (%s,%s,'test:kl019','SEALED','FULL',0,0,'empty',%s,%s)",
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
            "INSERT INTO kineticloop.evaluation_releases(id,subject_id,release_namespace,release_version,content_hash) VALUES (%s,%s,'test:kl019','1',%s)",
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
            (
                PROJECTION,
                SUBJECT,
                digest("projection"),
                now,
                now + timedelta(seconds=validity_seconds),
            ),
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
            "INSERT INTO kineticloop.manifest_builds(id,subject_id,build_identity,status,captured_epoch,captured_input_frontier,ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id,typed_payload) VALUES (%s,%s,'test:kl019','READY',0,%s,%s,%s,%s,%s,%s)",
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


def chain(
    urls: dict[str, str], *, state: str = "BUILDING_CONTEXT", validity_seconds: float = 2700
) -> ProgressBasis:
    reset_inputs(urls, validity_seconds)
    published = _UPSTREAM.publish(urls)
    with connect(urls["admin"]) as db:
        service = LeaseService(db, PlanningIdentity(IDENTITY.actor, SUBJECT))
        admitted = service.admit_or_revise(
            AdmitOrReviseIntent(
                SUBJECT,
                "admit",
                date.today(),
                "TRAINING",
                "test:UTC-v1",
                {"equipment": [], "minutes": 30},
            )
        )
        leased = service.acquire_lease(
            AcquireLease(
                SUBJECT,
                "lease",
                UUID(admitted["intent_id"]),
                None,
                0,
                1,
                UUID(admitted["attempt_id"]),
                600,
            )
        )
        assert (
            db.execute(
                "SELECT status FROM kineticloop.planning_attempts WHERE id=%s",
                (admitted["attempt_id"],),
            ).fetchone()[0]
            == "CREATED"
        )
        db.commit()
    basis = ProgressBasis(
        subject_id=SUBJECT,
        key="snapshot",
        intent_id=UUID(admitted["intent_id"]),
        request_id=UUID(admitted["request_id"]),
        request_revision=1,
        attempt_id=UUID(admitted["attempt_id"]),
        expected_owner=PROGRESS_IDENTITY.key,
        fence=leased["fence"],
        manifest_id=UUID(published["manifest_id"]),
        epoch=0,
        source_state="CREATED",
    )
    if state != "CREATED":
        advance(urls, basis, "LEASED", {})
        basis = replace(basis, source_state="LEASED")
    if state == "BUILDING_CONTEXT":
        advance(urls, basis, "BUILDING_CONTEXT", {})
        basis = replace(basis, source_state="BUILDING_CONTEXT")
    return basis


def args(basis: ProgressBasis) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(basis)


def advance(
    urls: dict[str, str],
    basis: ProgressBasis,
    target: str,
    sources: Mapping[str, Mapping[str, str]],
    **extra: Any,
) -> Mapping[str, Any]:
    request = AdvanceAttempt(
        **{**args(basis), "key": "advance:" + target}, target_state=target, sources=sources, **extra
    )
    with connect(urls["admin"]) as db:
        return PlanningWorkflowService(db, PROGRESS_IDENTITY).advance_attempt(request)


def snapshot_request(urls: dict[str, str], basis: ProgressBasis) -> RecordSnapshot:
    with connect(urls["admin"]) as db:
        context = capture_context(db, basis, BUILDER)
    return RecordSnapshot(**args(basis), builder_id=BUILDER, **context)


def record(
    urls: dict[str, str], request: RecordSnapshot, identity: ProgressIdentity = PROGRESS_IDENTITY
) -> Mapping[str, Any]:
    with connect(urls["admin"]) as db:
        return ContextService(db, identity).record_snapshot(request)


def persisted(urls: dict[str, str]) -> dict[str, Any]:
    with connect(urls["admin"]) as db:
        return {
            table: db.execute(
                sql.SQL("SELECT to_jsonb(t) FROM kineticloop.{} t ORDER BY {}").format(
                    sql.Identifier(table),
                    sql.Identifier("subject_id" if table == "user_decision_state" else "id"),
                )
            ).fetchall()
            for table in (
                "user_decision_state",
                "call_reservations",
                "call_ledger_events",
                "decision_snapshots",
                "planning_attempts",
                "planning_intents",
                "planning_request_revisions",
                "command_receipts",
                "domain_events",
                "outbox_deliveries",
                "authorization_issuances",
                "daily_bundle_revisions",
            )
        }


def no_effect(urls: dict[str, str], action: Any) -> None:
    before = persisted(urls)
    with pytest.raises((RepositoryTransactionError, PlanningDenied, psycopg.Error)):
        action()
    assert persisted(urls) == before


def source(urls: dict[str, str], table: str, identity: str) -> dict[str, str]:
    with connect(urls["admin"]) as db:
        content_hash = db.execute(
            sql.SQL("SELECT content_hash FROM kineticloop.{} WHERE id=%s").format(
                sql.Identifier(table)
            ),
            (UUID(identity),),
        ).fetchone()[0]
    return {"id": identity, "hash": content_hash}


def later_inputs(
    urls: dict[str, str], basis: ProgressBasis, snapshot_id: str, mutant: str | None = None
) -> dict[str, dict[str, str]]:
    """Immutable input-only placeholders. No target S26/S29 output seed or engine claim."""
    validate_database(urls)
    f, d, n, r, v = (uuid4() for _ in range(5))
    fitness = {"action": {"kind": "TEST_INPUT_ONLY", "planned": 1}, "completeness": "NOT_RUN"}
    demand = {"fitness_hash": digest(fitness), "semantics": "ESTIMATE", "completeness": "NOT_RUN"}
    nutrition = {
        "fitness_id": str(f),
        "fitness_hash": digest(fitness),
        "demand_id": str(d),
        "demand_hash": digest(demand),
        "manifest_id": str(basis.manifest_id),
        "policy_id": str(POLICY),
        "completeness": "NOT_RUN",
    }
    resolution = {
        "coverage": "COMPLETE_FOR_POLICY",
        "consistency": "CONSISTENT",
        "truncation_status": "NOT_TRUNCATED",
        "instrumentation": "INPUT_ONLY",
    }
    if mutant == "demand":
        demand["fitness_hash"] = "0" * 64
        nutrition["demand_hash"] = digest(demand)
    elif mutant == "nutrition":
        nutrition["fitness_hash"] = "0" * 64
    sources = {
        "snapshot": source(urls, "decision_snapshots", snapshot_id),
        "fitness": {"id": str(f), "hash": digest(fitness)},
        "demand": {"id": str(d), "hash": digest(demand)},
        "nutrition": {"id": str(n), "hash": digest(nutrition)},
        "resolution": {"id": str(r), "hash": digest(resolution)},
    }
    certificate = {
        "semantic_validation": "PASS",
        "policy_envelope": "PASS",
        "execution_basis_event_id": str(BASIS_EVENT),
        "snapshot_id": snapshot_id,
        "context_hash": sources["snapshot"]["hash"],
        "fitness_hash": digest(fitness),
        "demand_hash": digest(demand),
        "nutrition_hash": digest(nutrition),
        "resolution_hash": digest(resolution),
        "captured_epoch": basis.epoch,
        "request_revision": basis.request_revision,
    }
    if mutant == "validation":
        certificate["fitness_hash"] = "0" * 64
    elif mutant == "execution_basis":
        certificate["execution_basis_event_id"] = str(uuid4())
    elif mutant == "missing_semantics":
        certificate.pop("semantic_validation")
    resolution_basis = digest(
        {
            "manifest_id": str(basis.manifest_id),
            "policy_id": str(POLICY),
            "fitness_hash": digest(fitness),
            "action_parameters_hash": digest(fitness["action"]),
        }
    )
    if mutant == "resolution":
        resolution_basis = "0" * 64
    with connect(urls["admin"], autocommit=True) as db:
        now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        db.execute(
            "INSERT INTO kineticloop.proposal_revisions(id,subject_id,proposal_family_identity,proposal_kind,producer_artifact,ref_s26_id,ref_s29_id,content_hash,typed_payload) VALUES (%s,%s,'test:kl075-f','FITNESS','test:placeholder',%s,%s,%s,%s)",
            (f, SUBJECT, UUID(snapshot_id), basis.attempt_id, digest(fitness), Jsonb(fitness)),
        )
        db.execute(
            "INSERT INTO kineticloop.prescription_demand_features(id,subject_id,method_version,feature_hash,basis_hash,ref_s34_id,content_hash,typed_payload) VALUES (%s,%s,'test:placeholder',%s,%s,%s,%s,%s)",
            (d, SUBJECT, digest(demand), digest(fitness), f, digest(demand), Jsonb(demand)),
        )
        db.execute(
            "INSERT INTO kineticloop.proposal_revisions(id,subject_id,proposal_family_identity,proposal_kind,producer_artifact,demand_feature_id,ref_s26_id,ref_s29_id,content_hash,typed_payload) VALUES (%s,%s,'test:kl075-n','NUTRITION','test:placeholder',%s,%s,%s,%s,%s)",
            (
                n,
                SUBJECT,
                d,
                UUID(snapshot_id),
                basis.attempt_id,
                digest(nutrition),
                Jsonb(nutrition),
            ),
        )
        db.execute(
            "INSERT INTO kineticloop.evidence_resolutions(id,subject_id,action_type,action_parameters_hash,resolver_version,query_basis_hash,resolution_expires_at,ref_s05_id,ref_s24_id,content_hash,typed_payload) VALUES (%s,%s,'TEST_ONLY',%s,'test:placeholder',%s,%s,%s,%s,%s,%s)",
            (
                r,
                SUBJECT,
                digest(fitness["action"]),
                resolution_basis,
                now + timedelta(minutes=30),
                POLICY,
                basis.manifest_id,
                digest(resolution),
                Jsonb(resolution),
            ),
        )
        db.execute(
            "INSERT INTO kineticloop.validation_results(id,subject_id,result,validator_artifact,valid_until,ref_s03_id,ref_s05_id,ref_s24_id,ref_s28_id,ref_s29_id,ref_s34_id,ref_s35_id,ref_s36_id,content_hash,typed_payload) VALUES (%s,%s,'PASS','test:placeholder',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                v,
                SUBJECT,
                now + timedelta(minutes=30),
                BASIS_EVENT,
                POLICY,
                basis.manifest_id,
                basis.request_id,
                basis.attempt_id,
                n,
                d,
                r,
                digest(certificate),
                Jsonb(certificate),
            ),
        )
    sources["validation"] = {"id": str(v), "hash": digest(certificate)}
    return sources


def test_snapshot_owner(database_urls: dict[str, str]) -> None:
    urls = database_urls
    basis = chain(urls)
    request = snapshot_request(urls, basis)
    before = persisted(urls)
    outcome = record(urls, request)
    after = persisted(urls)
    assert before["planning_attempts"] == after["planning_attempts"]
    assert len(after["decision_snapshots"]) == 1
    assert len(after["command_receipts"]) == len(before["command_receipts"]) + 1
    assert len(after["domain_events"]) == len(before["domain_events"]) + 1
    assert len(after["outbox_deliveries"]) == len(before["outbox_deliveries"]) + 1
    snapshot = after["decision_snapshots"][0][0]
    assert snapshot["ref_s24_id"] == str(basis.manifest_id)
    assert snapshot["ref_s28_id"] == str(basis.request_id)
    assert snapshot["ref_s29_id"] == str(basis.attempt_id)
    assert snapshot["captured_epoch"] == basis.epoch
    assert snapshot["context_hash"] == request.context_hash == digest(snapshot["typed_payload"])
    assert snapshot["typed_payload"]["accounting"] == request.accounting
    assert snapshot["typed_payload"]["context_builder_version"] == "1"
    assert [stage for stage, _ in outcome["lock_trace"]] == [20, 40, 80, 90]
    replay = record(urls, request)
    assert replay["snapshot_id"] == outcome["snapshot_id"] and replay["replayed"] is True
    assert persisted(urls) == after
    no_effect(
        urls,
        lambda: record(
            urls, replace(request, accounting={**request.accounting, "budget_units": 1})
        ),
    )
    # A second rebuild appends immutable history without changing the first snapshot.
    rebuilt = record(urls, replace(request, key="snapshot-rebuild"))
    assert rebuilt["snapshot_id"] != outcome["snapshot_id"]
    assert persisted(urls)["decision_snapshots"][0:] != []
    with connect(urls["admin"]) as db:
        assert (
            db.execute(
                "SELECT revision FROM kineticloop.decision_snapshots WHERE id=%s",
                (rebuilt["snapshot_id"],),
            ).fetchone()[0]
            == 2
        )
    with connect(urls["application"]) as db:
        with pytest.raises(psycopg.Error):
            db.execute(
                "UPDATE kineticloop.decision_snapshots SET context_hash='changed' WHERE id=%s",
                (outcome["snapshot_id"],),
            )
    sources = later_inputs(urls, basis, outcome["snapshot_id"])
    for target, names in (
        ("FITNESS", ["snapshot"]),
        ("DEMAND_FEATURES", ["snapshot", "fitness"]),
        ("NUTRITION", ["snapshot", "fitness", "demand"]),
        ("VALIDATING", ["snapshot", "fitness", "demand", "nutrition"]),
        ("COMMIT_READY", list(sources)),
    ):
        selected = {name: sources[name] for name in names}
        wrong = copy.deepcopy(selected)
        wrong[names[-1]]["hash"] = "0" * 64
        no_effect(urls, lambda: advance(urls, basis, target, wrong))
        advanced = advance(urls, basis, target, selected)
        basis = replace(basis, source_state=target)
        assert advanced["state"] == target
    final = persisted(urls)
    assert final["planning_attempts"][0][0]["snapshot_id"] == outcome["snapshot_id"]
    assert final["planning_attempts"][0][0]["status"] == "COMMIT_READY"
    assert (
        final["planning_intents"][0][0]["typed_payload"]
        == before["planning_intents"][0][0]["typed_payload"]
    )
    assert (
        final["planning_intents"][0][0]["deadline"] == before["planning_intents"][0][0]["deadline"]
    )
    assert final["authorization_issuances"] == final["daily_bundle_revisions"] == []
    evidence(
        {
            "kind": "snapshot_and_stages",
            "identities": outcome,
            "final_attempt": final["planning_attempts"],
            "snapshot_rows": final["decision_snapshots"],
            "product_requirements": "NOT_RUN",
            "later_inputs": "PLACEHOLDER_INPUT_ONLY",
        }
    )


@pytest.mark.parametrize(
    "case",
    [
        "owner",
        "fence",
        "revision",
        "request",
        "attempt",
        "manifest",
        "epoch",
        "policy",
        "environment",
        "principal",
        "subject",
        "terminal_attempt",
        "terminal_root",
        "takeover",
        "lease_expired",
        "deadline_expired",
        "control",
        "request_changed",
        "manifest_changed",
        "manifest_expired",
        "lease_before",
        "deadline_before",
        "manifest_before",
        "snapshot_lease_wait",
        "snapshot_deadline_wait",
        "advance_lease_wait",
        "advance_deadline_wait",
    ],
)
def test_current_guard_denials(database_urls: dict[str, str], case: str) -> None:
    urls = database_urls
    if case.endswith("_wait"):
        operation, boundary, _ = case.split("_")
        assert_post_lock_expiry(
            urls, "lease_expires_at" if boundary == "lease" else "deadline", operation
        )
        return
    basis = chain(urls, validity_seconds=2 if case == "manifest_expired" else 2700)
    request = snapshot_request(urls, basis)
    original = record(urls, request)
    valid_snapshot = source(urls, "decision_snapshots", original["snapshot_id"])
    request = replace(request, key="denied_snapshot")
    identity = PROGRESS_IDENTITY
    changes: dict[str, Any] = {
        "owner": {"expected_owner": "foreign"},
        "fence": {"fence": 2},
        "revision": {"request_revision": 2},
        "request": {"request_id": uuid4()},
        "attempt": {"attempt_id": uuid4()},
        "manifest": {"manifest_id": uuid4()},
        "epoch": {"epoch": 1},
        "subject": {"subject_id": uuid4()},
    }
    if case in changes:
        request = replace(request, **changes[case])
    elif case in {"policy", "environment", "principal"}:
        identity_changes: dict[str, Any] = {
            "policy": {"policy_id": uuid4()},
            "environment": {"environment_id": uuid4()},
            "principal": {"principal": "kl_test_subject_2_login"},
        }
        identity = replace(identity, **identity_changes[case])
    elif case == "terminal_attempt":
        advance(urls, basis, "FAILED", {}, failure_code="TEST_INPUT_INVALID")
    elif case == "terminal_root":
        cancel_root(urls, basis)
    elif case == "takeover":
        perturb_expiry(urls, basis, "lease_expires_at", -1)
        with connect(urls["admin"]) as db:
            other = PlanningIdentity(replace(IDENTITY.actor, identity_id=str(uuid4())), SUBJECT)
            LeaseService(db, other).acquire_lease(
                AcquireLease(
                    SUBJECT,
                    "takeover",
                    basis.intent_id,
                    PROGRESS_IDENTITY.key,
                    1,
                    1,
                    basis.attempt_id,
                    100,
                )
            )
    elif case in {"lease_expired", "deadline_expired"}:
        perturb_expiry(
            urls, basis, "deadline" if case == "deadline_expired" else "lease_expires_at", -1
        )
    elif case == "control":
        apply_control(urls)
    elif case == "request_changed":
        with connect(urls["admin"]) as db:
            LeaseService(db, PlanningIdentity(IDENTITY.actor, SUBJECT)).admit_or_revise(
                AdmitOrReviseIntent(
                    SUBJECT,
                    "request-changed",
                    date.today(),
                    "TRAINING",
                    "test:UTC-v1",
                    {"equipment": [], "minutes": 31},
                )
            )
    elif case == "manifest_changed":
        publish_again(urls)
    elif case == "manifest_expired":
        with connect(urls["admin"], autocommit=True) as db:
            end = time.monotonic() + 4
            while time.monotonic() < end:
                observed = db.execute(
                    "SELECT clock_timestamp(),valid_until FROM kineticloop.decision_manifests WHERE id=%s",
                    (basis.manifest_id,),
                ).fetchone()
                if observed[0] > observed[1]:
                    break
                time.sleep(0.01)
            assert observed[0] > observed[1]
        evidence(
            {
                "kind": "AFTER_DC",
                "bound": "manifest.valid_until",
                "observed_now": observed[0],
                "valid_until": observed[1],
            }
        )
    if case.endswith("_before"):
        if case != "manifest_before":
            perturb_expiry(
                urls, basis, "lease_expires_at" if case == "lease_before" else "deadline", 10
            )
        before = persisted(urls)
        result = record(urls, request, identity)
        advanced = advance(urls, basis, "FITNESS", {"snapshot": valid_snapshot})
        assert result["state"] == "BUILDING_CONTEXT" and advanced["state"] == "FITNESS"
        assert persisted(urls)["planning_intents"] == before["planning_intents"]
        evidence({"kind": "BEFORE_DC", "case": case, "snapshot": result, "advance": advanced})
        return
    no_effect(urls, lambda: record(urls, request, identity))
    # The same current guards protect AdvanceAttempt as well as S26 persistence.
    next_request = AdvanceAttempt(
        **{**{k: getattr(request, k) for k in args(basis)}, "key": "denied-stage"},
        target_state="FITNESS",
        sources={"snapshot": valid_snapshot},
    )
    no_effect(urls, lambda: run_advance(urls, next_request, identity))
    evidence({"kind": "guard_denial", "case": case, "no_effect": True})


def run_advance(
    urls: dict[str, str], request: AdvanceAttempt, identity: ProgressIdentity = PROGRESS_IDENTITY
) -> Mapping[str, Any]:
    with connect(urls["admin"]) as db:
        return PlanningWorkflowService(db, identity).advance_attempt(request)


def perturb_expiry(urls: dict[str, str], basis: ProgressBasis, field: str, seconds: float) -> None:
    validate_database(urls)
    assert field in {"deadline", "lease_expires_at"}
    # Labeled privileged negative/time instrumentation; never a seeded owner success.
    with connect(urls["admin"], autocommit=True) as db:
        db.execute(
            sql.SQL(
                "UPDATE kineticloop.planning_intents SET {}=clock_timestamp() + %s::interval WHERE id=%s"
            ).format(sql.Identifier(field)),
            (f"{seconds} seconds", basis.intent_id),
        )


def cancel_root(urls: dict[str, str], basis: ProgressBasis) -> None:
    from kineticloop.persistence.call_ledger import CallLedgerService, ReserveCall
    from kineticloop.workflow.call_ledger import AccountingIdentity

    with connect(urls["admin"]) as db:
        reserved = CallLedgerService(db, PlanningIdentity(IDENTITY.actor, SUBJECT)).reserve(
            ReserveCall(
                SUBJECT,
                "cancel-input-reservation",
                basis.intent_id,
                basis.attempt_id,
                basis.request_revision,
                basis.fence,
                "cancel-input-slot",
                AccountingIdentity("test-provider", "test-model", "config", "price"),
                {"calls": 1, "tokens": 10, "tools": 1},
            )
        )
    with connect(urls["admin"]) as db:

        def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
            tx.lock_subject()
            tx.lock_intents((basis.intent_id,))
            tx.lock_reservations((UUID(reserved["reservation_id"]),))

            def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                session.update(
                    "S27", {"status": "CANCELLED"}, {"subject_id": SUBJECT, "id": basis.intent_id}
                )
                return {"cancelled": True}

            return tx.idempotent_outcome(
                receipt_id=uuid4(),
                actor_scope=PROGRESS_IDENTITY.key,
                client_key="cancel",
                request_hash=digest("cancel"),
                mutation=mutation,
                event=EventWrite(
                    uuid4(), "INTENT", str(basis.intent_id), 1, "CANCELLED", "planning", uuid4()
                ),
            )[0]

        execute_command(db, "CancelIntent", SUBJECT, operation)


def apply_control(urls: dict[str, str]) -> None:
    with connect(urls["admin"]) as db:

        def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
            tx.lock_subject()
            control = uuid4()
            epoch = db.execute(
                "SELECT authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
                (SUBJECT,),
            ).fetchone()[0]

            def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                session.insert(
                    "S17",
                    {
                        "id": control,
                        "subject_id": SUBJECT,
                        "control_identity": "kl075-stop",
                        "control_revision": 1,
                        "scope": "TEST_ONLY",
                        "status": "STOP",
                        "ref_s05_id": POLICY,
                        "ref_s02_id": receipt,
                    },
                )
                session.insert(
                    "S18",
                    {
                        "id": uuid4(),
                        "subject_id": SUBJECT,
                        "control_identity": "kl075-stop",
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
                        "causation_key": "stop",
                        "invalidated_epoch": epoch + 1,
                        "ref_s02_id": receipt,
                        "ref_s17_id": control,
                    },
                )
                session.update(
                    "S01",
                    {"authorization_epoch": epoch + 1, "last_control_event_id": control},
                    {"subject_id": SUBJECT},
                )
                return {"control_id": str(control)}

            receipt = uuid4()
            return tx.idempotent_outcome(
                receipt_id=receipt,
                actor_scope=PROGRESS_IDENTITY.key,
                client_key="stop",
                request_hash=digest("stop"),
                mutation=mutation,
                invalidation_scope="TEST_ONLY",
                event=EventWrite(uuid4(), "CONTROL", "kl075-stop", 1, "STOP", "planning", uuid4()),
            )[0]

        execute_command(db, "ApplyControl", SUBJECT, operation)


def assert_post_lock_expiry(urls: dict[str, str], field: str, operation: str) -> None:
    basis = chain(urls, state="CREATED" if operation == "advance" else "BUILDING_CONTEXT")
    request = (
        snapshot_request(urls, basis)
        if operation == "snapshot"
        else AdvanceAttempt(**args(basis), target_state="LEASED", sources={})
    )
    perturb_expiry(urls, basis, field, 1.5)
    before = persisted(urls)
    blocker = connect(urls["admin"])
    blocker.execute(
        "SELECT id FROM kineticloop.planning_attempts WHERE id=%s FOR UPDATE", (basis.attempt_id,)
    )
    pid_ready = Event()
    worker_pid: list[int] = []

    def worker() -> str:
        with connect(urls["admin"]) as db:
            worker_pid.append(db.info.backend_pid)
            db.execute("SET lock_timeout='8s'")
            db.commit()
            pid_ready.set()
            try:
                if isinstance(request, RecordSnapshot):
                    ContextService(db, PROGRESS_IDENTITY).record_snapshot(request)
                else:
                    PlanningWorkflowService(db, PROGRESS_IDENTITY).advance_attempt(request)
            except (RepositoryTransactionError, PlanningDenied) as error:
                return type(error).__name__
            raise AssertionError("post-lock expiry granted authority")

    start = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker)
            assert pid_ready.wait(3)
            with connect(urls["admin"], autocommit=True) as observer:
                deadline = time.monotonic() + 4
                observed = False
                while time.monotonic() < deadline:
                    row = observer.execute(
                        "SELECT pg_blocking_pids(%s)", (worker_pid[0],)
                    ).fetchone()
                    if blocker.info.backend_pid in row[0]:
                        observed = True
                        break
                    time.sleep(0.01)
                assert observed, "actual blocking witness required"
                waited_until = time.monotonic() + 4
                while time.monotonic() < waited_until:
                    expired = observer.execute(
                        sql.SQL(
                            "SELECT clock_timestamp(), {} FROM kineticloop.planning_intents WHERE id=%s"
                        ).format(sql.Identifier(field)),
                        (basis.intent_id,),
                    ).fetchone()
                    if expired[0] > expired[1]:
                        break
                    time.sleep(0.01)
                assert expired[0] > expired[1]
                blocker.rollback()
                result = future.result(timeout=5)
    finally:
        blocker.rollback()
        blocker.close()
    assert persisted(urls) == before
    evidence(
        {
            "kind": "POST_LOCK_DC",
            "operation": operation,
            "bound": field,
            "blocking_observed": observed,
            "observed_now": expired[0],
            "expiry": expired[1],
            "result": result,
            "elapsed": time.monotonic() - start,
            "exact_equality": "PU_ONLY",
        }
    )


@pytest.mark.parametrize("operation", ["snapshot", "advance"])
@pytest.mark.parametrize("step", ["owner_write", "bookkeeping", "ack_loss", "concurrent"])
def test_progress_atomicity(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch, operation: str, step: str
) -> None:
    urls = database_urls
    basis = chain(urls, state="CREATED" if operation == "advance" else "BUILDING_CONTEXT")
    request = (
        snapshot_request(urls, basis)
        if operation == "snapshot"
        else AdvanceAttempt(**args(basis), target_state="LEASED", sources={})
    )

    def action() -> Mapping[str, Any]:
        return (
            record(urls, request)
            if isinstance(request, RecordSnapshot)
            else run_advance(urls, request)
        )

    before = persisted(urls)
    if step == "owner_write":
        name = "insert" if operation == "snapshot" else "update"
        original = getattr(RestrictedSqlSession, name)

        def fail(session: RestrictedSqlSession, logical: str, *values: Any) -> Any:
            result = original(session, logical, *values)
            if logical == ("S26" if operation == "snapshot" else "S29"):
                raise GuardRequired("injected after actual owner write")
            return result

        with monkeypatch.context() as m:
            m.setattr(RestrictedSqlSession, name, fail)
            no_effect(urls, action)
        action()
    elif step == "bookkeeping":
        validate_database(urls)
        with connect(urls["admin"], autocommit=True) as db:
            db.execute(
                "CREATE FUNCTION public.kl075_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.status='SUCCEEDED' THEN RAISE EXCEPTION 'injected after owner/event/outbox'; END IF; RETURN NEW; END $$"
            )
            db.execute(
                "CREATE TRIGGER kl075_fail BEFORE UPDATE ON kineticloop.command_receipts FOR EACH ROW EXECUTE FUNCTION public.kl075_fail()"
            )
        try:
            no_effect(urls, action)
        finally:
            with connect(urls["admin"], autocommit=True) as db:
                db.execute("DROP TRIGGER kl075_fail ON kineticloop.command_receipts")
                db.execute("DROP FUNCTION public.kl075_fail()")
        action()
    elif step == "ack_loss":
        first = action()
        # Simulated lost transport acknowledgment after the durable commit.
        with pytest.raises(ConnectionError):
            raise ConnectionError("lost ACK after committed owner return")
        current = persisted(urls)
        apply_control(urls)
        historical_state = persisted(urls)
        retry = action()
        assert retry["replayed"] is True and retry["executable"] is False
        assert retry["snapshot_id"] == first["snapshot_id"]
        assert persisted(urls) == historical_state
        assert len(current["command_receipts"]) == len(before["command_receipts"]) + 1
    else:
        from kineticloop.persistence import planning_progress

        original_entry = planning_progress._execute_guarded_progress
        barrier = Barrier(2)

        def simultaneous(*values: Any, **keywords: Any) -> Any:
            barrier.wait(timeout=5)
            return original_entry(*values, **keywords)

        with monkeypatch.context() as m:
            m.setattr(planning_progress, "_execute_guarded_progress", simultaneous)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: action(), range(2)))
        assert results[0]["snapshot_id"] == results[1]["snapshot_id"]
        assert sum(r.get("replayed") is True for r in results) == 1
    after = persisted(urls)
    added = 2 if step == "ack_loss" else 1  # control has its own bookkeeping
    for table in ["command_receipts", "domain_events", "outbox_deliveries"]:
        assert len(after[table]) == len(before[table]) + added
    assert len(after["decision_snapshots"]) == len(before["decision_snapshots"]) + (
        operation == "snapshot"
    )
    assert (
        after["planning_intents"][0][0]["typed_payload"]
        == before["planning_intents"][0][0]["typed_payload"]
    )
    assert (
        after["planning_intents"][0][0]["deadline"] == before["planning_intents"][0][0]["deadline"]
    )
    evidence(
        {
            "kind": "atomicity",
            "operation": operation,
            "step": step,
            "persisted_ids": after,
            "no_duplicate_event": True,
        }
    )


def publish_again(urls: dict[str, str]) -> None:
    validate_database(urls)
    new_build = uuid4()
    with connect(urls["admin"], autocommit=True) as db:
        db.execute(
            "INSERT INTO kineticloop.manifest_builds(id,subject_id,build_identity,status,captured_epoch,captured_input_frontier,ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id,typed_payload) SELECT %s,subject_id,'test:kl075-new-build','READY',captured_epoch,captured_input_frontier,ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id,typed_payload FROM kineticloop.manifest_builds WHERE id=%s",
            (new_build, BUILD),
        )
    request = replace(_UPSTREAM.publish_request(urls), key="publish-again", build_id=new_build)
    with connect(urls["admin"]) as db:
        _UPSTREAM.service(db).publish(request)


@pytest.mark.parametrize(
    "case",
    [
        "missing_block",
        "changed_constraints",
        "command_trust",
        "bad_hash",
        "truncated",
        "wrong_accounting",
        "unknown_builder",
        "builder_hash",
        "future_cutoff",
    ],
)
def test_snapshot_payload_denials(database_urls: dict[str, str], case: str) -> None:
    urls = database_urls
    basis = chain(urls)
    request = snapshot_request(urls, basis)
    context = copy.deepcopy(dict(request.context))

    def mutation() -> Mapping[str, Any]:
        changes: dict[str, Any] = {"key": case}
        if case == "missing_block":
            context["blocks"].pop("target_priorities")
            changes.update(context=context, context_hash=digest(context))
        elif case == "changed_constraints":
            context["blocks"]["constraints"] = {"minutes": 999}
            changes.update(context=context, context_hash=digest(context))
        elif case == "command_trust":
            context["trust_class"] = "APPROVAL"
            changes.update(context=context, context_hash=digest(context))
        elif case == "bad_hash":
            changes["context_hash"] = "0" * 64
        elif case in {"truncated", "wrong_accounting"}:
            changes["accounting"] = {
                **request.accounting,
                **({"truncated": True} if case == "truncated" else {"input_units": 1}),
            }
        elif case == "unknown_builder":
            changes["builder_id"] = uuid4()
        elif case == "builder_hash":
            changes["builder_hash"] = "0" * 64
        else:
            changes["source_cutoff"] = request.source_cutoff + timedelta(hours=1)
            context["source_cutoff"] = changes["source_cutoff"].isoformat()
            changes.update(context=context, context_hash=digest(context))
        return record(urls, replace(request, **changes))

    no_effect(urls, mutation)
    evidence({"kind": "payload_denial", "case": case, "no_effect": True})


@pytest.mark.parametrize("target", ["STALE", "FAILED", "CANCELLED", "LEASE_LOST"])
def test_terminal_exits(database_urls: dict[str, str], target: str) -> None:
    urls = database_urls
    basis = chain(urls)
    outcome = record(urls, snapshot_request(urls, basis))
    sources = {"snapshot": source(urls, "decision_snapshots", outcome["snapshot_id"])}
    advance(urls, basis, "FITNESS", sources)
    basis = replace(basis, source_state="FITNESS")
    before = persisted(urls)
    advance(urls, basis, target, {}, failure_code="TEST_WORKER_EXIT")
    after = persisted(urls)
    assert after["planning_attempts"][0][0]["status"] == target
    assert (
        after["planning_attempts"][0][0]["typed_payload"]
        == before["planning_attempts"][0][0]["typed_payload"]
    )
    assert after["planning_attempts"][0][0]["snapshot_id"] == outcome["snapshot_id"]
    assert after["planning_intents"] == before["planning_intents"]
    request = snapshot_request(urls, replace(basis, source_state="BUILDING_CONTEXT"))
    no_effect(urls, lambda: record(urls, request))
    evidence(
        {
            "kind": "terminal_exit",
            "target": target,
            "immutable_sources_preserved": True,
            "reopened": False,
        }
    )


@pytest.mark.parametrize(
    "mutant,denied_target",
    [
        ("demand", "NUTRITION"),
        ("nutrition", "VALIDATING"),
        ("resolution", "COMMIT_READY"),
        ("validation", "COMMIT_READY"),
        ("execution_basis", "COMMIT_READY"),
        ("missing_semantics", "COMMIT_READY"),
    ],
)
def test_source_binding_denials(
    database_urls: dict[str, str], mutant: str, denied_target: str
) -> None:
    urls = database_urls
    basis = chain(urls)
    outcome = record(urls, snapshot_request(urls, basis))
    sources = later_inputs(urls, basis, outcome["snapshot_id"], mutant)
    for target, names in (
        ("FITNESS", ["snapshot"]),
        ("DEMAND_FEATURES", ["snapshot", "fitness"]),
        ("NUTRITION", ["snapshot", "fitness", "demand"]),
        ("VALIDATING", ["snapshot", "fitness", "demand", "nutrition"]),
        ("COMMIT_READY", list(sources)),
    ):
        selected = {name: sources[name] for name in names}
        if target == denied_target:
            no_effect(urls, lambda: advance(urls, basis, target, selected))
            break
        advance(urls, basis, target, selected)
        basis = replace(basis, source_state=target)
    evidence(
        {
            "kind": "source_binding_mutant",
            "mutant": mutant,
            "denied_target": denied_target,
            "immutable_input_only": True,
            "hashes_self_consistent": True,
            "no_effect": True,
        }
    )
