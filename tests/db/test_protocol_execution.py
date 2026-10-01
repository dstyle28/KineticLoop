from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Event
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from kineticloop.contracts.commands import CommitBundle, StartSession
from kineticloop.db.lifecycle import DatabaseLifecycle
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.planning import (
    AcquireLease,
    AdmitOrReviseIntent,
    PlanningIdentity,
    PlanningWorkflowService,
)
from kineticloop.persistence.protocol_execution import ProtocolExecutionService
from kineticloop.persistence.transactions import (
    GuardRequired,
    IdempotencyConflict,
    RepositoryTransaction,
    RepositoryTransactionError,
)
from kineticloop.protocol.authorization import canonical_certificate_timestamp
from kineticloop.protocol.execution import ExecutionIdentity, PublishReady, command_digest, digest

ROOT = Path(__file__).resolve().parents[2]


def load(path: str) -> Any:
    spec = spec_from_file_location("kl019_" + Path(path).stem, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MIGRATIONS = load("tests/db/test_migrations.py")
_NAMESPACE = load("tests/unit/protocol/test_execution.py")
execution_namespace = _NAMESPACE.execution_namespace
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
) = [UUID(f"00000000-0000-8000-8000-{19000 + n:012x}") for n in range(10)]
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


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    short = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
    ).strip()
    selected = execution_namespace(
        ROOT, short, "exec"
    )  # Validation precedes constructor/reset/finally.
    lifecycle = DatabaseLifecycle(ROOT)
    lifecycle.namespace = selected
    try:
        yield _MIGRATIONS.bootstrap_two_phase(lifecycle)
    finally:
        lifecycle.destroy()


def connect(url: str, **kwargs: Any) -> Any:
    return psycopg.connect(url, **kwargs)


def seed_inputs(urls: dict[str, str]) -> None:
    """Declared trusted upstream inputs only; never tested owner outputs."""
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


@pytest.fixture()
def urls(database_urls: dict[str, str]) -> dict[str, str]:
    seed_inputs(database_urls)
    return database_urls


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


def upstream(urls: dict[str, str], published: Mapping[str, Any]) -> CommitBundle:
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
                1200,
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


def test_publish_ready_build(urls: dict[str, str]) -> None:
    result = publish(urls)
    with connect(urls["admin"]) as db:
        assert db.execute(
            "SELECT current_manifest_id,decision_generation FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone() == (UUID(result["manifest_id"]), 1)
        assert db.execute(
            "SELECT status FROM kineticloop.manifest_builds WHERE id=%s", (BUILD,)
        ).fetchone() == ("PUBLISHED",)
        assert db.execute(
            "SELECT projection_role,ref_s21_id FROM kineticloop.manifest_projection_bindings"
        ).fetchall() == [("EXPOSURE", PROJECTION)]
        manifest = db.execute(
            "SELECT typed_payload,registry_revision_at_publish FROM kineticloop.decision_manifests"
        ).fetchone()
        assert (
            manifest[0]["artifact_root_ids"] == [str(ROOT_ARTIFACT)]
            and len(manifest[0]["artifact_closure_ids"]) == 3
            and manifest[1] == 0
        )
        assert db.execute("SELECT count(*) FROM kineticloop.outbox_deliveries").fetchone() == (1,)


def test_commit_test_only_bundle(urls: dict[str, str]) -> None:
    command, result = committed(urls)
    with connect(urls["admin"]) as db:
        assert db.execute(
            "SELECT head_revision,current_bundle_revision_id,calendar_policy FROM kineticloop.daily_plan_heads"
        ).fetchone() == (1, UUID(result["bundle_id"]), "test:UTC-v1")
        assert db.execute(
            "SELECT typed_payload->'parent_revision_id' FROM kineticloop.daily_bundle_revisions"
        ).fetchone() == (None,)
        assert db.execute(
            "SELECT status,result_bundle_revision_id,result_authorization_id FROM kineticloop.planning_intents"
        ).fetchone() == (
            "FOUND_VALID_PLAN",
            UUID(result["bundle_id"]),
            UUID(result["authorization_id"]),
        )
        assert db.execute("SELECT status FROM kineticloop.planning_attempts").fetchone() == (
            "COMMITTED",
        )
        scope, until, cert = db.execute(
            "SELECT scope,valid_until,validity_certificate FROM kineticloop.authorization_issuances"
        ).fetchone()
        assert scope == "TEST_ONLY"
        finite = [
            datetime.fromisoformat(d["valid_until"])
            for d in cert["dependencies"]
            if d.get("valid_until")
        ]
        assert until == min(finite)
        # Independently compare every certificate identity/bound to persisted upstream inputs.
        actual = {(d["dependency_kind"], d["identity"]): d for d in cert["dependencies"]}
        expected: dict[tuple[str, str], datetime | None] = {}
        for kind, table, column in (
            ("ARTIFACT", "safety_artifacts", "valid_until"),
            ("MANIFEST", "decision_manifests", "valid_until"),
            ("EVIDENCE_RESOLUTION", "evidence_resolutions", "resolution_expires_at"),
            ("VALIDATION_ADMISSION_FRESHNESS", "validation_results", "valid_until"),
            ("PROJECTION", "projection_versions", "valid_until"),
            ("DEMAND_FEATURE", "prescription_demand_features", "NULL"),
        ):
            for identity, bound in db.execute(
                f"SELECT id,{column} FROM kineticloop.{table}"
            ).fetchall():
                expected[(kind, str(identity))] = bound
        request_id, deadline = db.execute(
            "SELECT current_request_revision_id,deadline FROM kineticloop.planning_intents"
        ).fetchone()
        expected[("REQUEST_DEADLINE", str(request_id))] = deadline
        head_id, calendar = db.execute(
            "SELECT id,typed_payload FROM kineticloop.daily_plan_heads"
        ).fetchone()
        expected[("CALENDAR", str(head_id))] = datetime.fromisoformat(
            calendar["calendar_valid_until"]
        )
        policy_entry = actual[("POLICY_TTL", str(POLICY))]
        ttl = db.execute(
            "SELECT (typed_payload->>'max_authorization_ttl_seconds')::int FROM kineticloop.policy_bundles WHERE id=%s",
            (POLICY,),
        ).fetchone()[0]
        expected[("POLICY_TTL", str(POLICY))] = datetime.fromisoformat(
            policy_entry["valid_from"]
        ) + timedelta(seconds=ttl)
        freshness = db.execute(
            "SELECT typed_payload->'admission_freshness' FROM kineticloop.evidence_resolutions"
        ).fetchone()[0]
        for entry in freshness:
            expected[("EVIDENCE_ADMISSION_FRESHNESS", entry["identity"])] = datetime.fromisoformat(
                entry["valid_until"]
            )
        assert set(actual) == set(expected)
        for key, bound in expected.items():
            assert (
                datetime.fromisoformat(actual[key]["valid_until"])
                if actual[key].get("valid_until")
                else None
            ) == bound, key
        assert until == min(bound for bound in expected.values() if bound is not None)
        assert cert["closure_digest"] == digest(cert["dependencies"])
        assert any(
            d.get("validity_kind") == "TIMELESS"
            and d["timeless_approval_policy"] == str(POLICY_ARTIFACT)
            for d in cert["dependencies"]
        )
        assert db.execute(
            "SELECT count(*) FROM kineticloop.authorization_artifact_closure"
        ).fetchone() == (3,)
        assert db.execute(
            "SELECT execution_basis_event_id FROM kineticloop.user_decision_state"
        ).fetchone() == (UUID(result["event_id"]),)
    # Request can shorten only; absence of a request cannot lengthen any dependency.
    seed_inputs(urls)
    cmd = upstream(urls, publish(urls))
    with connect(urls["admin"], autocommit=True) as db:
        end = db.execute("SELECT clock_timestamp()+interval '60 seconds'").fetchone()[0]
    with connect(urls["admin"]) as db:
        issued = service(db).commit(cmd, requested_valid_until=end)
    assert datetime.fromisoformat(issued["valid_until"]) == end


def test_start_new_session(urls: dict[str, str]) -> None:
    _, result = committed(urls)
    command = start_command(result)
    with connect(urls["admin"]) as db:
        started = service(db).start(command)
    with connect(urls["admin"]) as db:
        assert db.execute(
            "SELECT origin,lifecycle,execution_revision FROM kineticloop.workout_sessions"
        ).fetchone() == ("APP_STARTED", "IN_PROGRESS", 1)
        assert db.execute(
            "SELECT binding_kind,ref_s40_id,ref_s42_id,execution_scope,ref_s02_id FROM kineticloop.execution_bindings"
        ).fetchone() == (
            "START",
            UUID(result["prescription_id"]),
            UUID(result["authorization_id"]),
            "TEST_ONLY",
            UUID(started["receipt_id"]),
        )
        assert db.execute(
            "SELECT execution_basis_event_id FROM kineticloop.user_decision_state"
        ).fetchone() == (UUID(started["event_id"]),)
    before = snapshot(urls)
    with connect(urls["admin"]) as db:
        with pytest.raises(GuardRequired):
            service(db).start(
                changed(command, idempotency_key="another-start", command_id=str(uuid4()))
            )
    assert snapshot(urls) == before


def perturb(urls: dict[str, str], sql: str, parameters: Any = ()) -> None:
    """Explicit trusted negative input perturbation; never claimed as an upstream owner."""
    with connect(urls["admin"], autocommit=True) as db:
        db.execute("SET session_replication_role=replica")
        db.execute(sql, parameters)
        db.execute("SET session_replication_role=origin")


def test_stale_commit_basis_denies(urls: dict[str, str]) -> None:
    cases = (
        "epoch",
        "manifest",
        "generation",
        "request",
        "attempt",
        "owner",
        "fence",
        "lease_equal",
        "deadline_equal",
        "execution_basis",
        "validation",
        "proposal",
        "demand",
        "resolution",
        "closure",
        "snapshot",
        "context",
        "certificate",
        "budget",
        "production_policy_scope",
        "shadow_policy_scope",
        "evaluation_policy_scope",
    )
    for case in cases:
        seed_inputs(urls)
        command = upstream(urls, publish(urls))
        fields: dict[str, dict[str, Any]] = {
            "epoch": {"expected_authorization_epoch": 1},
            "manifest": {"manifest_id": str(uuid4())},
            "generation": {"expected_generation": 2},
            "request": {"expected_request_revision": 2},
            "attempt": {"attempt_id": str(uuid4())},
            "owner": {"expected_owner_id": str(uuid4())},
            "fence": {"expected_fence": command.expected_fence + 1},
            "execution_basis": {"execution_basis_event_id": str(uuid4())},
            "validation": {"validation_id": str(uuid4())},
            "closure": {"artifact_dependency_closure_hash": "a" * 64},
        }
        if case in fields:
            command = changed(command, **fields[case])
        elif case in {"lease_equal", "deadline_equal"}:
            column = "lease_expires_at" if case == "lease_equal" else "deadline"
            perturb(urls, f"UPDATE kineticloop.planning_intents SET {column}=clock_timestamp()")
        elif case == "proposal":
            perturb(urls, "UPDATE kineticloop.proposal_revisions SET content_hash=%s", ("a" * 64,))
        elif case == "demand":
            perturb(
                urls, "UPDATE kineticloop.proposal_revisions SET demand_feature_id=%s", (uuid4(),)
            )
        elif case == "resolution":
            perturb(urls, "UPDATE kineticloop.evidence_resolutions SET ref_s05_id=%s", (uuid4(),))
        elif case == "snapshot":
            perturb(urls, "UPDATE kineticloop.decision_snapshots SET ref_s28_id=%s", (uuid4(),))
        elif case == "context":
            perturb(urls, "UPDATE kineticloop.decision_snapshots SET context_hash=%s", ("a" * 64,))
        elif case == "certificate":
            perturb(
                urls,
                "UPDATE kineticloop.validation_results SET typed_payload=jsonb_set(typed_payload,'{policy_envelope}','\"FAIL\"')",
            )
        elif case == "budget":
            perturb(
                urls,
                "UPDATE kineticloop.planning_intents SET typed_payload=jsonb_set(typed_payload,'{settled,calls}','4')",
            )
        elif case.endswith("_policy_scope"):
            # Explicit negative immutable-policy input, never a legitimate policy mutation.
            scope = {
                "production_policy_scope": "EXECUTION",
                "shadow_policy_scope": "SHADOW",
                "evaluation_policy_scope": "EVALUATION",
            }[case]
            perturb(
                urls,
                "UPDATE kineticloop.policy_bundles SET typed_payload=jsonb_set(typed_payload,'{authorization_action_scopes,TRAINING}',%s)",
                (Jsonb(scope),),
            )
        before = snapshot(urls)
        with connect(urls["admin"]) as db:
            with pytest.raises(
                (RepositoryTransactionError, ValueError, psycopg.Error),
                match="TEST_ONLY policy scope" if case.endswith("_policy_scope") else None,
            ):
                service(db).commit(command)
        assert snapshot(urls) == before, case


def revoke_input(urls: dict[str, str], artifact: UUID, key: str) -> None:
    # Actual merged T2-GLOBAL revoke owner; no user fanout or synthetic event success.
    from kineticloop.contracts.safety_registry import revocation_payload_hash
    from kineticloop.persistence.safety_registry import revoke_artifact

    with connect(urls["admin"]) as db:
        row = db.execute(
            "SELECT content_hash FROM kineticloop.safety_artifacts WHERE id=%s", (artifact,)
        ).fetchone()
    from kineticloop.contracts.commands import RevokeArtifact

    with connect(urls["admin"]) as db:
        effective = db.execute("SELECT clock_timestamp()").fetchone()[0]
    command_payload = {
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
        "artifact_id": str(artifact),
        "artifact_content_hash": row[0],
        "revocation_payload_hash": revocation_payload_hash(
            effective_at=effective, reason_code="TEST"
        ),
        "causation_incident_id": str(uuid4()),
    }
    with connect(urls["trusted_admin"]) as db:
        revoke_artifact(
            db,
            RevokeArtifact.model_validate_json(json.dumps(command_payload)),
            effective_at=effective,
            reason_code="TEST",
        )


def test_current_start_denial(urls: dict[str, str]) -> None:
    cases = (
        "actor",
        "subject",
        "policy",
        "environment",
        "principal",
        "prescription",
        "authorization",
        "hash",
        "scope",
        "bundle",
        "epoch",
        "hold",
        "stop",
        "root_revoke",
        "transitive_revoke",
        "missing",
        "future",
        "expired",
        "undefined",
        "authorization_equal",
        "closure",
        "binding",
    )
    for case in cases:
        seed_inputs(urls)
        _, result = committed(urls)
        command = start_command(result)
        identity = IDENTITY
        if case == "actor":
            command = changed(
                command,
                actor={
                    "schema": "kineticloop-role-identity-v1",
                    "identity_id": str(uuid4()),
                    "role": "test",
                },
            )
        elif case == "subject":
            body = command.model_dump(mode="json")
            subject = str(uuid4())
            body["subject_id"] = subject
            body["authorization_scope"]["subject_id"] = subject
            command = signed(StartSession, body)
        elif case in {"policy", "environment"}:
            body = command.model_dump(mode="json")
            body["authorization_scope"][case + "_id"] = str(uuid4())
            command = signed(StartSession, body)
        elif case == "principal":
            identity = replace(IDENTITY, principal="kl_test_subject_2_login")
        elif case in {"prescription", "authorization"}:
            command = changed(command, **{case + "_id": str(uuid4())})
        elif case == "hash":
            command = changed(command, content_hash="a" * 64)
        elif case == "closure":
            command = changed(command, artifact_dependency_closure_hash="a" * 64)
        elif case == "binding":
            command = changed(command, binding_revision=2)
        elif case == "epoch":
            perturb(urls, "UPDATE kineticloop.user_decision_state SET authorization_epoch=1")
        elif case == "bundle":
            perturb(urls, "UPDATE kineticloop.daily_plan_heads SET current_bundle_revision_id=NULL")
        elif case == "scope":
            perturb(urls, "UPDATE kineticloop.authorization_issuances SET scope='EXECUTION'")
        elif case in {"hold", "stop"}:
            # A true read-only current observation does not authorize a later action.
            from kineticloop.persistence.transactions import query_execution_eligibility

            first_start = start_command(result)
            with connect(urls["admin"]) as db:
                service(db).start(first_start)
                artifacts = service(db)._artifacts(
                    [str(ROOT_ARTIFACT), str(STATIC), str(POLICY_ARTIFACT)]
                )
                with db.transaction():
                    local_date = db.execute(
                        "SELECT local_date FROM kineticloop.daily_plan_heads"
                    ).fetchone()[0]
                observed = query_execution_eligibility(
                    db,
                    command_kind="ContinueSession",
                    subject_id=SUBJECT,
                    artifact_ids=[a.artifact_id for a in artifacts],
                    artifact_identities=artifacts,
                    local_date=local_date,
                    session_id=UUID(first_start.session_id),
                    prescription_id=UUID(result["prescription_id"]),
                    authorization_id=UUID(result["authorization_id"]),
                    execution_scope="TEST_ONLY",
                )
                assert observed.is_executable
            # Reuse the actual merged control owner with exact T2 classification and bookkeeping.
            from kineticloop.persistence.transactions import (
                EventWrite,
                RestrictedSqlSession,
                execute_command,
            )

            control, receipt, event_id = uuid4(), uuid4(), uuid4()

            def apply(tx: RepositoryTransaction) -> Any:
                tx.lock_subject()

                def mutation(session: RestrictedSqlSession) -> dict[str, Any]:
                    session.insert(
                        "S17",
                        {
                            "id": control,
                            "subject_id": SUBJECT,
                            "control_identity": str(control),
                            "control_revision": 1,
                            "scope": "TEST_ONLY",
                            "status": "HOLD" if case == "hold" else "STOP",
                            "ref_s02_id": receipt,
                            "ref_s05_id": POLICY,
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
                            "causation_key": case,
                            "invalidated_epoch": 1,
                            "ref_s17_id": control,
                            "ref_s02_id": receipt,
                        },
                    )
                    session.update(
                        "S01",
                        {"authorization_epoch": 1, "last_control_event_id": control},
                        {"subject_id": SUBJECT},
                    )
                    return {"control_id": str(control)}

                return tx.idempotent_outcome(
                    receipt_id=receipt,
                    actor_scope="trusted-test-control",
                    client_key=case,
                    request_hash=digest(case),
                    mutation=mutation,
                    event=EventWrite(
                        event_id,
                        "CONTROL",
                        str(control),
                        1,
                        "CONTROL_APPLIED",
                        "execution",
                        uuid4(),
                    ),
                    invalidation_scope="TEST_ONLY",
                )

            with connect(urls["admin"]) as db:
                execute_command(db, "ApplyControl", SUBJECT, apply)
            with connect(urls["admin"]) as db:
                from kineticloop.protocol.authorization import controls_are_eligible

                with db.transaction():
                    tx = RepositoryTransaction(db.cursor(), "ApplyControl", SUBJECT)
                    tx.lock_subject()
                    proven, states = tx._current_control_states("TEST_ONLY")
                    assert proven and states == (("HOLD" if case == "hold" else "STOP"),)
                    assert not controls_are_eligible(proven=proven, states=states)
                    projected = db.execute(
                        "SELECT head.status,event.status FROM kineticloop.control_heads head JOIN kineticloop.control_events event ON event.id=head.ref_s17_id AND event.subject_id=head.subject_id WHERE head.subject_id=%s",
                        (SUBJECT,),
                    ).fetchone()
                    assert projected == ("ACTIVE", "HOLD" if case == "hold" else "STOP")
                denied = query_execution_eligibility(
                    db,
                    command_kind="ContinueSession",
                    subject_id=SUBJECT,
                    artifact_ids=[a.artifact_id for a in artifacts],
                    artifact_identities=artifacts,
                    local_date=local_date,
                    session_id=UUID(first_start.session_id),
                    prescription_id=UUID(result["prescription_id"]),
                    authorization_id=UUID(result["authorization_id"]),
                    execution_scope="TEST_ONLY",
                )
                assert not denied.is_executable and denied.denial_reasons == (
                    "CURRENT_AUTHORITY_DENIED",
                )
        elif case in {"root_revoke", "transitive_revoke"}:
            revoke_input(urls, ROOT_ARTIFACT if case == "root_revoke" else STATIC, case)
        elif case == "missing":
            perturb(urls, "DELETE FROM kineticloop.safety_artifacts WHERE id=%s", (STATIC,))
        elif case == "future":
            perturb(
                urls,
                "UPDATE kineticloop.safety_artifacts SET valid_from=clock_timestamp()+interval '1 minute' WHERE id=%s",
                (STATIC,),
            )
        elif case == "expired":
            perturb(
                urls,
                "UPDATE kineticloop.safety_artifacts SET valid_until=clock_timestamp() WHERE id=%s",
                (ROOT_ARTIFACT,),
            )
        elif case == "undefined":
            perturb(
                urls,
                "UPDATE kineticloop.authorization_artifact_closure SET valid_until=NULL WHERE artifact_id=%s",
                (ROOT_ARTIFACT,),
            )
        elif case == "authorization_equal":
            perturb(
                urls, "UPDATE kineticloop.authorization_issuances SET valid_until=clock_timestamp()"
            )
        before = snapshot(urls)
        with connect(urls["admin"]) as db:
            with pytest.raises((RepositoryTransactionError, ValueError, psycopg.Error)):
                service(db, identity).start(command)
        assert snapshot(urls) == before, case


def test_ack_loss_replay_is_historical(
    urls: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    request = publish_request(urls)
    with connect(urls["admin"]) as db:
        published = service(db).publish(request)
    before = snapshot(urls)
    with connect(urls["admin"]) as db:
        replay = service(db).publish(request)
        assert replay == {**published, "replayed": True, "executable": False}
        with pytest.raises(IdempotencyConflict):
            service(db).publish(replace(request, expected_authorization_epoch=1))
        with pytest.raises(GuardRequired):
            service(db).publish(replace(request, key="natural-build-retry"))
    assert snapshot(urls) == before
    command = upstream(urls, published)
    with connect(urls["admin"]) as db:
        result = service(db).commit(command)
    before = snapshot(urls)
    with connect(urls["admin"]) as db:
        assert service(db).commit(command) == {**result, "replayed": True, "executable": False}
        with pytest.raises(IdempotencyConflict):
            service(db).commit(changed(command, result_fingerprint="a" * 64))
    assert snapshot(urls) == before
    start = start_command(result)
    with connect(urls["admin"]) as db:
        accepted = service(db).start(start)
    perturb(
        urls, "UPDATE kineticloop.user_decision_state SET authorization_epoch=authorization_epoch+1"
    )
    before = snapshot(urls)
    with connect(urls["admin"]) as db:
        assert service(db).start(start) == {**accepted, "replayed": True, "executable": False}
        with pytest.raises(IdempotencyConflict):
            service(db).start(changed(start, action_key="changed"))
    assert snapshot(urls) == before

    for loss in ("expiry", "revocation"):
        seed_inputs(urls)
        _, issued = committed(urls)
        first = start_command(issued)
        with connect(urls["admin"]) as db:
            original = service(db).start(first)
        # Expiry is explicit negative certificate input; revocation uses the real owner.
        if loss == "expiry":
            perturb(
                urls, "UPDATE kineticloop.authorization_issuances SET valid_until=clock_timestamp()"
            )
        else:
            revoke_input(urls, ROOT_ARTIFACT, "replay-revocation")
        baseline = snapshot(urls)
        with connect(urls["admin"]) as db:
            assert service(db).start(first) == {**original, "replayed": True, "executable": False}
            with pytest.raises((RepositoryTransactionError, ValueError, psycopg.Error)):
                service(db).start(changed(first, session_id=str(uuid4()), idempotency_key=loss))
        assert snapshot(urls) == baseline, loss

    # A real preflight miss releases S01 before a concurrent original and authority loss.
    for kind, loss in (
        ("PublishManifest", "unchanged"),
        ("CommitBundle", "unchanged"),
        ("StartSession", "unchanged"),
        ("PublishManifest", "revocation"),
        ("CommitBundle", "revocation"),
        ("StartSession", "revocation"),
        ("StartSession", "expiry"),
        ("StartSession", "membership"),
    ):
        seed_inputs(urls)
        race_value: Any = (
            publish_request(urls)
            if kind == "PublishManifest"
            else upstream(urls, publish(urls))
            if kind == "CommitBundle"
            else start_command(committed(urls)[1])
        )
        missed, resume = Event(), Event()
        real_replay = ProtocolExecutionService._replay
        real_history = RepositoryTransaction.execution_historical_outcome
        observations: list[Any] = []
        locked_history: list[Any] = []

        def replay_probe(adapter: ProtocolExecutionService, *args: Any, **kw: Any) -> Any:
            result = real_replay(adapter, *args, **kw)
            if (
                adapter._connection.info.parameter_status("application_name")
                == "kl019-preflight-miss"
            ):
                observations.append(result)
                if result is None and not missed.is_set():
                    missed.set()
                    assert (
                        adapter._connection.info.transaction_status
                        == psycopg.pq.TransactionStatus.IDLE
                    )
                    assert resume.wait(10)
            return result

        def history(tx: RepositoryTransaction, **kw: Any) -> Any:
            result = real_history(tx, **kw)
            if missed.is_set() and resume.is_set():
                locked_history.append(result)
            return result

        def call(name: str) -> Any:
            with connect(urls["admin"], application_name=name) as db:
                adapter = service(db)
                return (
                    adapter.publish(race_value)
                    if kind == "PublishManifest"
                    else adapter.commit(race_value)
                    if kind == "CommitBundle"
                    else adapter.start(race_value)
                )

        with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=1) as pool:
            patch.setattr(ProtocolExecutionService, "_replay", replay_probe)
            patch.setattr(RepositoryTransaction, "execution_historical_outcome", history)
            contender = pool.submit(call, "kl019-preflight-miss")
            assert missed.wait(10)
            try:
                original = call("kl019-original")
                if loss == "revocation":
                    revoke_input(urls, ROOT_ARTIFACT, "miss-then-revoke")
                elif loss == "expiry":
                    perturb(
                        urls,
                        "UPDATE kineticloop.authorization_issuances SET valid_until=clock_timestamp()",
                    )
                elif loss == "membership":
                    perturb(
                        urls,
                        "UPDATE kineticloop.daily_plan_heads SET current_bundle_revision_id=NULL",
                    )
                baseline = snapshot(urls)
            finally:
                resume.set()
            retried = contender.result(timeout=10)
        assert retried == {**original, "replayed": True, "executable": False}, (kind, loss)
        assert observations[0] is None
        if loss == "unchanged":
            assert len(observations) == 1 and locked_history == [retried]
        else:
            assert len(observations) == 2 and observations[1] == retried and not locked_history
        assert snapshot(urls) == baseline


def test_failures_roll_back_each_boundary(
    urls: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from kineticloop.persistence import transactions

    real = transactions._cursor

    class Injected(RuntimeError):
        pass

    for kind in ("PublishManifest", "CommitBundle", "StartSession"):
        # Run a real owner once to discover every executed write, then inject after each.
        boundaries: list[str] = []

        def setup() -> Any:
            seed_inputs(urls)
            if kind == "PublishManifest":
                return publish_request(urls)
            if kind == "CommitBundle":
                return upstream(urls, publish(urls))
            return start_command(committed(urls)[1])

        def call(command: Any) -> Any:
            with connect(urls["admin"]) as db:
                if kind == "PublishManifest":
                    return service(db).publish(command)
                if kind == "CommitBundle":
                    return service(db).commit(command)
                return service(db).start(command)

        command = setup()

        class Cursor:
            def __init__(self, cursor: Any, fail: int | None) -> None:
                self.cursor, self.fail = cursor, fail

            def __getattr__(self, key: str) -> Any:
                return getattr(self.cursor, key)

            def execute(self, query: Any, parameters: Any = None) -> Any:
                result = self.cursor.execute(query, parameters)
                text = query.as_string(self.cursor) if hasattr(query, "as_string") else str(query)
                if text.startswith(("INSERT INTO", "UPDATE kineticloop", 'UPDATE "kineticloop"')):
                    boundaries.append(text.split("VALUES")[0].split("SET")[0])
                    if self.fail == len(boundaries):
                        raise Injected(text)
                return result

        with monkeypatch.context() as patch:
            patch.setattr(
                transactions,
                "_cursor",
                lambda owner: Cursor(getattr(real(owner), "cursor", real(owner)), None),
            )
            call(command)
        count = len(boundaries)
        assert count > 0
        expected = {"PublishManifest": 7, "CommitBundle": 15, "StartSession": 7}
        assert count >= expected[kind], boundaries
        for fail in range(1, count + 1):
            command = setup()
            before = snapshot(urls)
            boundaries.clear()
            with monkeypatch.context() as patch:
                patch.setattr(
                    transactions,
                    "_cursor",
                    lambda owner: Cursor(getattr(real(owner), "cursor", real(owner)), fail),
                )
                with pytest.raises(Injected):
                    call(command)
            assert snapshot(urls) == before, (kind, fail)
            call(command)  # Real retry succeeds exactly once after complete rollback.
        print("ALL_WRITE_BOUNDARIES_ROLLBACK", kind, count)


def wait_blocked(url: str, name: str) -> list[int]:
    deadline = time.monotonic() + 10
    with connect(url, autocommit=True) as db:
        while time.monotonic() < deadline:
            row = db.execute(
                "SELECT pg_blocking_pids(pid) FROM pg_stat_activity WHERE application_name=%s",
                (name,),
            ).fetchone()
            if row and row[0]:
                return row[0]
    raise AssertionError("PostgreSQL did not observe blocked contender")


def test_first_use_contention(urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    for kind in ("CommitBundle", "StartSession"):
        for same_key in (False, True):
            seed_inputs(urls)
            command = (
                upstream(urls, publish(urls))
                if kind == "CommitBundle"
                else start_command(committed(urls)[1])
            )
            competitor = (
                command
                if same_key
                else changed(command, idempotency_key="competitor", command_id=str(uuid4()))
            )
            acquired, release = Event(), Event()
            traces = []
            real = RepositoryTransaction.require_test_execution_ingress

            def held(tx: RepositoryTransaction, **kw: Any) -> None:
                real(tx, **kw)
                if tx.command_kind == kind and not acquired.is_set():
                    traces.append(tx.lock_trace)
                    acquired.set()
                    assert release.wait(10)

            def run(value: Any, name: str) -> Any:
                try:
                    with connect(urls["admin"], application_name=name) as db:
                        return (
                            service(db).commit(value)
                            if kind == "CommitBundle"
                            else service(db).start(value)
                        )
                except (RepositoryTransactionError, ValueError, psycopg.Error) as error:
                    return error

            with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
                patch.setattr(RepositoryTransaction, "require_test_execution_ingress", held)
                winner = pool.submit(run, command, "kl019-winner")
                assert acquired.wait(10)
                loser = pool.submit(run, competitor, "kl019-loser")
                try:
                    assert wait_blocked(urls["admin"], "kl019-loser")
                finally:
                    release.set()
                first, second = winner.result(timeout=10), loser.result(timeout=10)
            assert isinstance(first, Mapping), first
            if same_key:
                assert (
                    isinstance(second, Mapping) and second["replayed"] and not second["executable"]
                )
                assert all(
                    second[k] == v for k, v in first.items() if k not in {"replayed", "executable"}
                )
            else:
                assert isinstance(second, Exception), second
            assert [str(stage.name) for stage, _ in traces[0]] == ["REGISTRY", "SUBJECT"]
            with connect(urls["admin"]) as db:
                for table in (
                    ("daily_plan_heads", "daily_bundle_revisions", "authorization_issuances")
                    if kind == "CommitBundle"
                    else ("workout_sessions", "execution_bindings")
                ):
                    assert db.execute(f"SELECT count(*) FROM kineticloop.{table}").fetchone() == (
                        1,
                    )

    # First-use support adds no generic insert/extra-column/lifecycle/calendar grants.
    from kineticloop.persistence.transactions import RestrictedSqlSession

    cmd: Any
    for target in ("S38", "S44", "calendar", "lifecycle", "extra_column", "day", "session"):
        seed_inputs(urls)
        if target in {"S38", "calendar", "day"}:
            cmd = upstream(urls, publish(urls))
        else:
            cmd = start_command(committed(urls)[1])
        before = snapshot(urls)
        original_insert = RestrictedSqlSession.insert
        original_update = RestrictedSqlSession.update

        def insert(session: RestrictedSqlSession, logical: str, values: Mapping[str, Any]) -> int:
            if (target == "S38" and logical == "S39") or (target == "S44" and logical == "S45"):
                original_insert(session, target, {"id": uuid4(), "subject_id": SUBJECT})
            return original_insert(session, logical, values)

        def update(
            session: RestrictedSqlSession,
            logical: str,
            values: Mapping[str, Any],
            where: Mapping[str, Any],
        ) -> int:
            if logical == "S38" and target == "calendar":
                values = {
                    **values,
                    "typed_payload": Jsonb({"calendar_valid_until": "2099-01-01T00:00:00Z"}),
                }
            if logical == "S44" and target == "lifecycle":
                values = {**values, "lifecycle": "COMPLETED"}
            if logical == "S44" and target == "extra_column":
                values = {**values, "origin": "EXTERNAL_REPORTED"}
            return original_update(session, logical, values, where)

        original_day = RepositoryTransaction.lock_daily_head
        original_session = RepositoryTransaction.lock_execution

        def day_lock(tx: RepositoryTransaction, local_date: Any, **kw: Any) -> None:
            if target == "day" and kw.get("create_first"):
                local_date += timedelta(days=1)
            original_day(tx, local_date, **kw)

        def session_lock(tx: RepositoryTransaction, ids: Any, **kw: Any) -> None:
            original_session(tx, (uuid4(),) if target == "session" else ids, **kw)

        with monkeypatch.context() as patch:
            patch.setattr(RestrictedSqlSession, "insert", insert)
            patch.setattr(RepositoryTransaction, "lock_daily_head", day_lock)
            patch.setattr(RepositoryTransaction, "lock_execution", session_lock)
            patch.setattr(RestrictedSqlSession, "update", update)
            with connect(urls["admin"]) as db:
                with pytest.raises(RepositoryTransactionError):
                    if target in {"S38", "calendar", "day"}:
                        service(db).commit(cmd)
                    else:
                        service(db).start(cmd)
        assert snapshot(urls) == before, target

    from kineticloop.persistence.transactions import execute_command

    for kind in ("CommitBundle", "StartSession"):
        seed_inputs(urls)
        bare_command: Any = (
            upstream(urls, publish(urls))
            if kind == "CommitBundle"
            else start_command(committed(urls)[1])
        )
        before = snapshot(urls)
        with connect(urls["admin"]) as db:
            adapter = service(db)
            artifacts = adapter._artifacts([str(ROOT_ARTIFACT), str(STATIC), str(POLICY_ARTIFACT)])

            def bare(tx: RepositoryTransaction) -> str:
                adapter._registry(tx, artifacts)
                if kind == "CommitBundle":
                    tx.lock_intents((UUID(bare_command.intent_id),))
                    tx.require_current_fence(
                        UUID(bare_command.intent_id),
                        owner_id=IDENTITY.key,
                        fence=bare_command.expected_fence,
                        expected_request_revision=bare_command.expected_request_revision,
                        expected_attempt_id=UUID(bare_command.attempt_id),
                    )
                    day = db.execute(
                        "SELECT local_date FROM kineticloop.planning_intents WHERE id=%s",
                        (UUID(bare_command.intent_id),),
                    ).fetchone()[0]
                    tx.lock_daily_head(day, create_first=True)
                else:
                    tx.lock_execution((UUID(bare_command.session_id),), create_first=True)
                return "early return without owner outcome"

            with pytest.raises(
                GuardRequired, match="first-use row requires complete owner outcome"
            ):
                execute_command(db, kind, SUBJECT, bare)
        assert snapshot(urls) == before, kind
