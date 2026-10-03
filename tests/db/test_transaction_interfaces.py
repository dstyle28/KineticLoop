from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from kineticloop.contracts.safety_registry import revocation_payload_hash
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace
from kineticloop.persistence.transactions import (
    ArtifactIdentity,
    ArtifactIdentityRequired,
    DispatchNotPermitted,
    EventWrite,
    FenceLost,
    GuardRequired,
    IdempotencyConflict,
    LockOrderViolation,
    LockStage,
    ReplayNotFound,
    RepositoryTransaction,
    StatementRejected,
    claim_outbox,
    execute_command,
    execute_factset_build,
    execute_preparation,
    query_execution_eligibility,
    replay_outcome,
)
from kineticloop.protocol.authorization import (
    AUTHORIZATION_METHOD_VERSION,
    canonical_certificate_timestamp,
)

ROOT = Path(__file__).parents[2]
_MIGRATION_SPEC = spec_from_file_location(
    "kl015_test_migrations", ROOT / "tests/db/test_migrations.py"
)
assert _MIGRATION_SPEC is not None and _MIGRATION_SPEC.loader is not None
_MIGRATIONS: Any = module_from_spec(_MIGRATION_SPEC)
_MIGRATION_SPEC.loader.exec_module(_MIGRATIONS)

_SAFETY_SPEC = spec_from_file_location(
    "kl015_safety_seed", ROOT / "tests/db/test_safety_registry.py"
)
assert _SAFETY_SPEC is not None and _SAFETY_SPEC.loader is not None
_SAFETY: Any = module_from_spec(_SAFETY_SPEC)
_SAFETY_SPEC.loader.exec_module(_SAFETY)

SUBJECT = UUID(_SAFETY.SUBJECT_ID)
ARTIFACT = UUID(_SAFETY.ARTIFACT_ID)
DEPENDENCY = UUID(_SAFETY.DEPENDENCY_ID)
POLICY = UUID(_SAFETY.POLICY_ID)
MANIFEST = UUID(_SAFETY.MANIFEST_ID)
INTENT = UUID("00000000-0000-8000-8000-000000015027")
INTENT_2 = UUID("00000000-0000-8000-8000-000000015127")
REQUEST_RECEIPT = UUID("00000000-0000-8000-8000-000000015002")
REQUEST = UUID("00000000-0000-8000-8000-000000015028")
REQUEST_2 = UUID("00000000-0000-8000-8000-000000015128")
ATTEMPT = UUID("00000000-0000-8000-8000-000000015029")
ATTEMPT_2 = UUID("00000000-0000-8000-8000-000000015129")
QUOTA = UUID("00000000-0000-8000-8000-000000015030")
RESERVATION = UUID("00000000-0000-8000-8000-000000015031")
RESERVATION_2 = UUID("00000000-0000-8000-8000-000000015131")
DAILY_HEAD = UUID("00000000-0000-8000-8000-000000015038")
BUNDLE = UUID("00000000-0000-8000-8000-000000015039")
OLD_BUNDLE = UUID("00000000-0000-8000-8000-000000015139")
PRESCRIPTION = UUID("00000000-0000-8000-8000-000000015040")
BUNDLE_MEMBER = UUID("00000000-0000-8000-8000-000000015041")
OLD_BUNDLE_MEMBER = UUID("00000000-0000-8000-8000-000000015141")
ISSUANCE = UUID("00000000-0000-8000-8000-000000015042")
SUPERSESSION = UUID("00000000-0000-8000-8000-000000015043")
SESSION = UUID("00000000-0000-8000-8000-000000015044")
PROPOSAL = UUID("00000000-0000-8000-8000-000000015034")
DEMAND = UUID("00000000-0000-8000-8000-000000015035")
DEMAND_2 = UUID("00000000-0000-8000-8000-000000015135")
RESOLUTION = UUID("00000000-0000-8000-8000-000000015036")
VALIDATION = UUID("00000000-0000-8000-8000-000000015037")
FACTSET = UUID("00000000-0000-8000-8000-000000015015")
FACTSET_BUILD_TEST = UUID("00000000-0000-8000-8000-000000015115")
FACTSET_MEMBER_TEST = UUID("00000000-0000-8000-8000-000000015116")
MANIFEST_BUILD = UUID("00000000-0000-8000-8000-000000015023")
PROJECTION = UUID("00000000-0000-8000-8000-000000015021")
PROJECTION_BINDING = UUID("00000000-0000-8000-8000-000000015025")
PROJECTION_DEPENDENCY = UUID("00000000-0000-8000-8000-000000015022")
PROJECTION_COLLECTION_DEPENDENCY = UUID("00000000-0000-8000-8000-000000015122")
PROJECTION_POLICY_DEPENDENCY = UUID("00000000-0000-8000-8000-000000015222")
PROJECTION_PROGRAM_DEPENDENCY = UUID("00000000-0000-8000-8000-000000015322")
PROJECTION_ENGINE_DEPENDENCY = UUID("00000000-0000-8000-8000-000000015422")
PROJECTION_OUTSIDE_FACT_DEPENDENCY = UUID("00000000-0000-8000-8000-000000015522")
OUTSIDE_FACT = UUID("00000000-0000-8000-8000-000000015514")
OUTSIDE_EVIDENCE = UUID("00000000-0000-8000-8000-000000015509")
OUTSIDE_CANDIDATE = UUID("00000000-0000-8000-8000-000000015510")
OUTSIDE_EVENT = UUID("00000000-0000-8000-8000-000000015511")
OUTSIDE_ADMISSION = UUID("00000000-0000-8000-8000-000000015513")
QUOTA_WINDOW_START = datetime(2026, 9, 26, 12, tzinfo=UTC)
COMPLETION_RECORDED_AT = datetime(2026, 9, 26, 12, tzinfo=UTC)


def _database_timestamp(connection: Any, *, offset: timedelta = timedelta()) -> datetime:
    with connection.transaction():
        row = connection.execute(
            "SELECT clock_timestamp() + %s::interval",
            (offset,),
        ).fetchone()
    assert row is not None
    return row[0]


def _completion_certificate(
    factset_id: UUID,
    member_revision: int,
    membership_digest: str,
    member_count: int,
    *,
    captured_input_frontier: str = "frontier-1",
    captured_epoch: int = 0,
) -> str:
    basis = {
        "method_version": "kl015-v1",
        "factset_id": str(factset_id),
        "subject_id": str(SUBJECT),
        "captured_input_frontier": captured_input_frontier,
        "captured_epoch": captured_epoch,
        "completed_member_revision": member_revision,
        "membership_digest": membership_digest,
        "member_count": member_count,
    }
    return hashlib.sha256(
        json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _manifest_candidate_payload(connection: Any) -> dict[str, Any]:
    artifact_rows = connection.execute(
        "SELECT id,artifact_kind,artifact_identity,artifact_version,content_hash,revision,"
        "validity_kind,valid_from,valid_until,timeless_approval_policy,"
        "timeless_approval_reason FROM kineticloop.safety_artifacts WHERE id=ANY(%s) ORDER BY id",
        ([ARTIFACT, DEPENDENCY],),
    ).fetchall()
    artifact_details = [
        {
            "artifact_id": str(row[0]),
            "artifact_kind": row[1],
            "artifact_identity": row[2],
            "artifact_version": row[3],
            "content_hash": row[4],
            "artifact_revision": row[5],
            "validity_kind": row[6],
            "valid_from": canonical_certificate_timestamp(row[7], "artifact valid_from"),
            "valid_until": (
                canonical_certificate_timestamp(row[8], "artifact valid_until")
                if row[8] is not None
                else None
            ),
            "timeless_approval_policy": row[9],
            "timeless_approval_reason": row[10],
            "dependency_ids": [
                str(dependency[0])
                for dependency in connection.execute(
                    "SELECT dependency_artifact_id "
                    "FROM kineticloop.safety_artifact_dependencies WHERE artifact_id=%s "
                    "ORDER BY dependency_artifact_id",
                    (row[0],),
                ).fetchall()
            ],
        }
        for row in artifact_rows
    ]
    artifact_digest = hashlib.sha256(
        json.dumps(artifact_details, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    dependencies = [
        {
            "projection_id": str(PROJECTION),
            "kind": "COLLECTION",
            "key": "admitted-facts",
            "collection": "all-admitted-v1",
            "policy": None,
            "program": None,
            "fact": None,
            "factset": str(FACTSET),
            "catalog": None,
            "mapping": None,
        },
        {
            "projection_id": str(PROJECTION),
            "kind": "FACTSET",
            "key": "current-factset",
            "collection": None,
            "policy": None,
            "program": None,
            "fact": None,
            "factset": str(FACTSET),
            "catalog": None,
            "mapping": None,
        },
        {
            "projection_id": str(PROJECTION),
            "kind": "ENGINE",
            "key": "exposure-engine:v1",
            "collection": None,
            "policy": None,
            "program": None,
            "fact": None,
            "factset": None,
            "catalog": None,
            "mapping": None,
        },
        {
            "projection_id": str(PROJECTION),
            "kind": "POLICY",
            "key": "active-policy",
            "collection": None,
            "policy": str(POLICY),
            "program": None,
            "fact": None,
            "factset": None,
            "catalog": None,
            "mapping": None,
        },
        {
            "projection_id": str(PROJECTION),
            "kind": "PROGRAM",
            "key": "active-program",
            "collection": None,
            "policy": None,
            "program": str(POLICY),
            "fact": None,
            "factset": None,
            "catalog": None,
            "mapping": None,
        },
    ]
    dependencies = sorted(dependencies, key=lambda item: (item["kind"], item["key"]))
    dependency_basis = {
        "projections": [
            {
                "id": str(PROJECTION),
                "role": "EXPOSURE",
                "projection_kind": "EXPOSURE",
                "validated_basis_hash": "projection-basis",
                "dependencies": dependencies,
            }
        ],
        "catalog_id": None,
        "mapping_id": None,
    }
    dependency_basis_hash = hashlib.sha256(
        json.dumps(dependency_basis, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "manifest_hash": "manifest-hash-2",
        "dependency_basis_hash": dependency_basis_hash,
        "artifact_dependency_closure_hash": artifact_digest,
        "artifact_closure_ids": sorted((str(ARTIFACT), str(DEPENDENCY))),
        "artifact_root_ids": [str(ARTIFACT)],
        "projection_bindings": [
            {"id": str(PROJECTION), "role": "EXPOSURE", "basis_hash": "projection-basis"}
        ],
    }


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    lifecycle = DatabaseLifecycle(ROOT)
    kl022_project = os.environ.get(
        "KINETICLOOP_KL022_COMPOSE_PROJECT", "kineticloop-kl022-08e743c"
    )
    kl022_database = os.environ.get(
        "KINETICLOOP_KL022_DATABASE", "kineticloop_kl022_08e743c"
    )
    lifecycle.namespace = DatabaseNamespace(
        project_name=kl022_project,
        database_name=kl022_database,
    )
    try:
        urls = _MIGRATIONS.bootstrap_two_phase(lifecycle)
        _SAFETY.seed(urls["admin"])
        _seed_transaction_rows(urls["admin"])
        yield urls
    finally:
        lifecycle.destroy()


def _seed_transaction_rows(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        manifest_artifact_basis = _manifest_candidate_payload(connection)
        connection.execute(
            "UPDATE kineticloop.decision_manifests SET typed_payload=%s WHERE id=%s",
            (
                psycopg.types.json.Jsonb(
                    {
                        "artifact_closure_ids": manifest_artifact_basis[
                            "artifact_closure_ids"
                        ],
                        "artifact_root_ids": manifest_artifact_basis["artifact_root_ids"],
                        "artifact_dependency_closure_hash": manifest_artifact_basis[
                            "artifact_dependency_closure_hash"
                        ],
                    }
                ),
                MANIFEST,
            ),
        )
        connection.execute(
            "INSERT INTO kineticloop.command_receipts"
            "(id,subject_id,status,command_kind,client_key,actor_scope,request_hash) "
            "VALUES (%s,%s,'SUCCEEDED','AdmitOrReviseIntent','seed-request','subject','seed')",
            (REQUEST_RECEIPT, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_intents"
            "(id,subject_id,purpose,root_request_identity,local_date,status,fence_token,"
            "lease_owner,lease_expires_at,deadline) VALUES "
            "(%s,%s,'PLAN','root-1',DATE '2026-09-26','RUNNING',7,'worker-a',"
            "clock_timestamp()+interval '1 day',clock_timestamp()+interval '2 days'),"
            "(%s,%s,'PLAN','root-2',DATE '2026-09-27','RUNNING',7,'worker-a',"
            "clock_timestamp()+interval '1 day',clock_timestamp()+interval '2 days')",
            (INTENT, SUBJECT, INTENT_2, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_request_revisions"
            "(id,subject_id,request_revision,constraint_fingerprint,normalization_version,"
            "ref_s02_id,ref_s27_id) VALUES (%s,%s,1,'constraint','v1',%s,%s)",
            (REQUEST, SUBJECT, REQUEST_RECEIPT, INTENT),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_request_revisions"
            "(id,subject_id,request_revision,constraint_fingerprint,normalization_version,"
            "ref_s02_id,ref_s27_id) VALUES (%s,%s,1,'constraint-2','v1',%s,%s)",
            (REQUEST_2, SUBJECT, REQUEST_RECEIPT, INTENT_2),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_attempts"
            "(id,subject_id,attempt_no,status,captured_epoch,fence_token,ref_s24_id,"
            "ref_s27_id,ref_s28_id) VALUES (%s,%s,1,'COMMIT_READY',0,7,%s,%s,%s)",
            (ATTEMPT, SUBJECT, MANIFEST, INTENT, REQUEST),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_attempts"
            "(id,subject_id,attempt_no,status,captured_epoch,fence_token,ref_s24_id,"
            "ref_s27_id,ref_s28_id) VALUES (%s,%s,1,'COMMIT_READY',0,7,%s,%s,%s)",
            (ATTEMPT_2, SUBJECT, MANIFEST, INTENT_2, REQUEST_2),
        )
        connection.execute(
            "UPDATE kineticloop.planning_intents SET "
            "current_request_revision_id=%s,current_attempt_id=%s WHERE id=%s",
            (REQUEST, ATTEMPT, INTENT),
        )
        connection.execute(
            "UPDATE kineticloop.planning_intents SET "
            "current_request_revision_id=%s,current_attempt_id=%s WHERE id=%s",
            (REQUEST_2, ATTEMPT_2, INTENT_2),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_quota_buckets"
            "(id,subject_id,quota_kind,window_start,window_end,admitted_count,quota_limit,ref_s05_id) "
            "VALUES (%s,%s,'DAILY',%s,%s,1,10,%s),"
            "(gen_random_uuid(),%s,'MONTHLY',%s,%s,1,100,%s)",
            (
                QUOTA,
                SUBJECT,
                QUOTA_WINDOW_START,
                QUOTA_WINDOW_START + timedelta(days=1),
                POLICY,
                SUBJECT,
                QUOTA_WINDOW_START,
                QUOTA_WINDOW_START + timedelta(days=30),
                POLICY,
            ),
        )
        connection.execute(
            "INSERT INTO kineticloop.call_reservations"
            "(id,subject_id,operation_slot,status,settlement_revision,dispatch_fence,"
            "ref_s27_id,ref_s29_id) VALUES "
            "(%s,%s,'slot-1','RESERVED',0,10,%s,%s),"
            "(%s,%s,'slot-2','RESERVED',0,10,%s,%s)",
            (RESERVATION, SUBJECT, INTENT, ATTEMPT, RESERVATION_2, SUBJECT, INTENT, ATTEMPT),
        )
        connection.execute(
            "INSERT INTO kineticloop.daily_plan_heads"
            "(id,subject_id,local_date,calendar_policy,day_lifecycle,head_revision,typed_payload) "
            "VALUES (%s,%s,DATE '2026-09-26','UTC','ACTIVE',0,"
            "jsonb_build_object('calendar_valid_until',(clock_timestamp()+interval '2 days')::text))",
            (DAILY_HEAD, SUBJECT),
        )
        connection.execute(
            "UPDATE kineticloop.policy_bundles SET typed_payload=%s WHERE id=%s",
            (
                psycopg.types.json.Jsonb(
                    {
                        "max_authorization_ttl_seconds": 86400,
                        "authorization_action_scopes": {"PLAN": "EXECUTION"},
                        "t2_invalidation_scopes": {
                            command: "EXECUTION"
                            for command in (
                                "DecideAssociation",
                                "DecideAdmission",
                                "AcceptFactRevision",
                                "ApplyControl",
                                "ClearControl",
                                "ApproveChange",
                                "ActivateApprovedProgram",
                                "RecordActualExecution",
                                "CompleteReportedWorkout",
                            )
                        },
                        "manifest_projection_requirements": {
                            "EXPOSURE": {
                                "projection_kind": "EXPOSURE",
                                "dependencies": [
                                    {
                                        "kind": "COLLECTION",
                                        "key": "admitted-facts",
                                        "collection": "all-admitted-v1",
                                    },
                                    {
                                        "kind": "FACTSET",
                                        "key": "current-factset",
                                        "collection": None,
                                    },
                                    {
                                        "kind": "ENGINE",
                                        "key": "exposure-engine:v1",
                                        "collection": None,
                                    },
                                    {
                                        "kind": "POLICY",
                                        "key": "active-policy",
                                        "collection": None,
                                    },
                                    {
                                        "kind": "PROGRAM",
                                        "key": "active-program",
                                        "collection": None,
                                    },
                                ],
                            }
                        },
                    }
                ),
                POLICY,
            ),
        )
        connection.execute(
            "INSERT INTO kineticloop.workout_sessions"
            "(id,subject_id,session_identity,origin,lifecycle,execution_revision) "
            "VALUES (%s,%s,'session-1','PLANNED','READY',0)",
            (SESSION, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.proposal_revisions"
            "(id,subject_id,proposal_family_identity,proposal_kind,producer_artifact,revision,"
            "demand_feature_id) VALUES (%s,%s,'proposal-family','FITNESS','test',1,%s)",
            (PROPOSAL, SUBJECT, DEMAND),
        )
        connection.execute(
            "INSERT INTO kineticloop.prescription_demand_features"
            "(id,subject_id,method_version,feature_hash,basis_hash,ref_s34_id) "
            "VALUES (%s,%s,'v1','feature','basis',%s)",
            (DEMAND, SUBJECT, PROPOSAL),
        )
        connection.execute(
            "INSERT INTO kineticloop.evidence_resolutions"
            "(id,subject_id,action_type,action_parameters_hash,resolver_version,query_basis_hash,"
            "resolution_expires_at,ref_s05_id,ref_s24_id,typed_payload) "
            "VALUES (%s,%s,'PLAN','params','v1','basis',clock_timestamp()+interval '1 day',%s,%s,"
            "jsonb_build_object('admission_freshness',jsonb_build_array(jsonb_build_object("
            "'identity','admission:fitness','revision',1,"
            "'valid_from',(clock_timestamp()-interval '1 minute')::text,"
            "'valid_until',(clock_timestamp()+interval '20 hours')::text))))",
            (RESOLUTION, SUBJECT, POLICY, MANIFEST),
        )
        connection.execute(
            "INSERT INTO kineticloop.validation_results"
            "(id,subject_id,result,validator_artifact,valid_until,revision,ref_s05_id,"
            "ref_s24_id,ref_s28_id,ref_s29_id,ref_s34_id,ref_s35_id,ref_s36_id) "
            "VALUES (%s,%s,'PASS','validator',clock_timestamp()+interval '1 day',1,"
            "%s,%s,%s,%s,%s,%s,%s)",
            (VALIDATION, SUBJECT, POLICY, MANIFEST, REQUEST, ATTEMPT, PROPOSAL, DEMAND, RESOLUTION),
        )
        connection.execute(
            "INSERT INTO kineticloop.factset_revisions"
            "(id,subject_id,factset_identity,status,storage_mode,member_revision,"
            "completed_member_revision,membership_digest,sealed_at,typed_payload) "
            "VALUES (%s,%s,'build-1','SEALED','FULL',0,0,'factset-digest',"
            "clock_timestamp(),%s)",
            (
                FACTSET,
                SUBJECT,
                psycopg.types.json.Jsonb(
                    {
                        "basis_version": "kl015-v1",
                        "captured_input_frontier": "frontier-1",
                        "captured_epoch": 0,
                        "program_revision_id": str(POLICY),
                        "policy_id": str(POLICY),
                        "mapping_revision_id": None,
                        "completion_identity": "seed-completion",
                        "member_count": 0,
                        "completion_certificate": _completion_certificate(
                            FACTSET, 0, "factset-digest", 0
                        ),
                    }
                ),
            ),
        )
        connection.execute(
            "INSERT INTO kineticloop.program_versions"
            "(id,subject_id,program_identity,program_revision) "
            "VALUES (%s,%s,'program-1',1) ON CONFLICT (id) DO NOTHING",
            (POLICY, SUBJECT),
        )
        connection.execute(
            "UPDATE kineticloop.user_decision_state SET current_factset_id=%s,"
            "active_program_id=%s,decision_generation=1,"
            "input_frontier_hash='frontier-1' WHERE subject_id=%s",
            (FACTSET, POLICY, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.projection_versions"
            "(id,subject_id,projection_kind,input_basis_hash,computed_at,valid_until,revision) "
            "VALUES (%s,%s,'EXPOSURE','projection-basis',clock_timestamp(),"
            "clock_timestamp()+interval '18 hours',1)",
            (PROJECTION, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.manifest_projection_bindings"
            "(id,subject_id,projection_role,validated_basis_hash,ref_s21_id,ref_s24_id) "
            "VALUES (%s,%s,'EXPOSURE','projection-basis',%s,%s)",
            (PROJECTION_BINDING, SUBJECT, PROJECTION, MANIFEST),
        )
        connection.execute(
            "INSERT INTO kineticloop.projection_dependencies"
            "(id,subject_id,dependency_kind,dependency_semantic_key,collection_signature,"
            "ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id) VALUES "
            "(%s,%s,'FACTSET','current-factset',NULL,NULL,NULL,%s,%s),"
            "(%s,%s,'COLLECTION','admitted-facts','all-admitted-v1',NULL,NULL,%s,%s),"
            "(%s,%s,'POLICY','active-policy',NULL,%s,NULL,NULL,%s),"
            "(%s,%s,'PROGRAM','active-program',NULL,NULL,%s,NULL,%s),"
            "(%s,%s,'ENGINE','exposure-engine:v1',NULL,NULL,NULL,NULL,%s)",
            (
                PROJECTION_DEPENDENCY,
                SUBJECT,
                FACTSET,
                PROJECTION,
                PROJECTION_COLLECTION_DEPENDENCY,
                SUBJECT,
                FACTSET,
                PROJECTION,
                PROJECTION_POLICY_DEPENDENCY,
                SUBJECT,
                POLICY,
                PROJECTION,
                PROJECTION_PROGRAM_DEPENDENCY,
                SUBJECT,
                POLICY,
                PROJECTION,
                PROJECTION_ENGINE_DEPENDENCY,
                SUBJECT,
                PROJECTION,
            ),
        )
        connection.execute(
            "INSERT INTO kineticloop.manifest_builds"
            "(id,subject_id,build_identity,status,captured_epoch,captured_input_frontier,"
            "ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id,typed_payload) "
            "VALUES (%s,%s,'manifest-build','READY',0,'frontier-1',%s,%s,%s,%s,%s)",
            (
                MANIFEST_BUILD,
                SUBJECT,
                POLICY,
                POLICY,
                FACTSET,
                PROJECTION,
                psycopg.types.json.Jsonb(_manifest_candidate_payload(connection)),
            ),
        )
        connection.execute("SET session_replication_role=origin")


def _registry_ids() -> tuple[UUID, UUID]:
    return ARTIFACT, DEPENDENCY


def _registry_identities() -> tuple[ArtifactIdentity, ArtifactIdentity]:
    return (
        ArtifactIdentity(ARTIFACT, "POLICY_BUNDLE", "artifact", "1", _SAFETY.CONTENT_HASH),
        ArtifactIdentity(DEPENDENCY, "EVALUATION_RELEASE", "dependency", "1", "b" * 64),
    )


def _acquire_registry(tx: RepositoryTransaction) -> int:
    revision = tx.acquire_registry_lease(_registry_ids())
    for identity in _registry_identities():
        tx.require_artifact(identity)
    return revision


def _event(tag: int) -> EventWrite:
    return EventWrite(
        UUID(f"00000000-0000-8000-8000-{tag:012x}"),
        "PlanningIntent",
        f"kl015-{tag}",
        1,
        "KL015Mutation",
        "kl015-events",
        UUID(f"00000000-0000-8000-8000-{tag + 1:012x}"),
    )


def _reset_kl022_fixture(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='kineticloop' ORDER BY tablename"
        ).fetchall()
        connection.execute(
            psycopg.sql.SQL("TRUNCATE {} CASCADE").format(
                psycopg.sql.SQL(",").join(
                    psycopg.sql.Identifier("kineticloop", str(row[0])) for row in tables
                )
            )
        )
    _SAFETY.seed(database_urls["admin"])
    _seed_transaction_rows(database_urls["admin"])


def _seed_current_t7_pair(admin_url: str) -> tuple[UUID, UUID]:
    prescription_id = UUID(_SAFETY.POLICY_ID)
    authorization_id = UUID(_SAFETY.AUTHORIZATION_ID)
    bundle_id = UUID("00000000-0000-8000-8000-000000022039")
    member_id = UUID("00000000-0000-8000-8000-000000022041")
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.prescription_revisions"
            "(id,subject_id,prescription_identity,prescription_kind,prescription_revision,"
            "content_hash,ref_s34_id,ref_s49_id) "
            "VALUES (%s,%s,'kl022-current','WORKOUT',1,'authorization-content',%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (prescription_id, SUBJECT, PROPOSAL, ARTIFACT),
        )
        connection.execute(
            "INSERT INTO kineticloop.daily_bundle_revisions"
            "(id,subject_id,local_date,revision_no,generation_mode,ref_s02_id,ref_s24_id,"
            "ref_s27_id,ref_s29_id,ref_s37_id,ref_s38_id) "
            "VALUES (%s,%s,DATE '2026-09-26',22,'KL022_TEST',%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (
                bundle_id,
                SUBJECT,
                UUID(_SAFETY.RECEIPT_ID),
                MANIFEST,
                INTENT,
                ATTEMPT,
                VALIDATION,
                DAILY_HEAD,
            ),
        )
        connection.execute(
            "INSERT INTO kineticloop.bundle_prescription_members"
            "(id,subject_id,member_kind,session_slot,member_order,ref_s39_id,ref_s40_id) "
            "VALUES (%s,%s,'PRESCRIPTION','kl022',1,%s,%s) ON CONFLICT (id) DO NOTHING",
            (member_id, SUBJECT, bundle_id, prescription_id),
        )
        connection.execute(
            "UPDATE kineticloop.daily_plan_heads SET current_bundle_revision_id=%s WHERE id=%s",
            (bundle_id, DAILY_HEAD),
        )
        connection.execute("SET session_replication_role=origin")
    return prescription_id, authorization_id


def _wait_until_database_blocked(
    admin_url: str,
    application_name: str,
    *,
    timeout_seconds: float = 5,
) -> tuple[int, ...]:
    deadline = time.monotonic() + timeout_seconds
    with psycopg.connect(admin_url, autocommit=True) as observer:
        while time.monotonic() < deadline:
            row = observer.execute(
                "SELECT pg_blocking_pids(pid) FROM pg_stat_activity "
                "WHERE application_name=%s AND state<>'idle'",
                (application_name,),
            ).fetchone()
            if row is not None and row[0]:
                return tuple(int(pid) for pid in row[0])
            threading.Event().wait(0.02)
    raise AssertionError(f"{application_name} did not become database-blocked")


def _cancel_idempotent_outcome(
    tx: RepositoryTransaction,
    *,
    client_key: str,
    request_hash: str,
    receipt_id: UUID,
    event: EventWrite,
    result_identity: str,
    mutation_runs: list[str],
    hold_after_subject: tuple[threading.Event, threading.Event] | None = None,
) -> tuple[Mapping[str, Any], bool]:
    tx.lock_subject()
    if hold_after_subject is not None:
        locked, release = hold_after_subject
        locked.set()
        assert release.wait(timeout=5)
    tx.lock_intents((INTENT,))
    tx.lock_reservations((RESERVATION,))

    def mutation(session: Any) -> Mapping[str, Any]:
        mutation_runs.append(request_hash)
        session.update(
            "S27",
            {"typed_payload": psycopg.types.json.Jsonb({"kl020": result_identity})},
            {"id": INTENT, "subject_id": SUBJECT},
        )
        return {
            "intent_id": str(INTENT),
            "result_identity": result_identity,
        }

    return tx.idempotent_outcome(
        receipt_id=receipt_id,
        actor_scope="subject",
        client_key=client_key,
        request_hash=request_hash,
        mutation=mutation,
        event=event,
    )


def test_registry_lease_required_for_publish_commit_and_session_entry(
    database_urls: dict[str, str],
) -> None:
    for command in (
        "PublishManifest",
        "CommitBundle",
        "Reauthorize",
        "StartSession",
        "ResumeSession",
        "ContinueSession",
    ):
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(GuardRequired, match="shared S51"):
                execute_command(connection, command, SUBJECT, lambda tx: tx.lock_subject())
        with psycopg.connect(database_urls["admin"]) as connection:
            revision = execute_command(
                connection,
                command,
                SUBJECT,
                lambda tx: _acquire_registry(tx),
            )
            assert revision >= 0


def test_preparation_work_stays_outside_coordination_locks(
    database_urls: dict[str, str],
) -> None:
    for command in ("RecordProjection", "BuildManifest", "ResolveEvidence", "RecordValidation"):
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(GuardRequired, match="isolated"):
                execute_command(connection, command, SUBJECT, lambda tx: tx.lock_subject())
        with psycopg.connect(database_urls["admin"]) as connection:
            observed = execute_preparation(
                connection, command, SUBJECT, lambda session: session.relation_locks()
            )
        assert "safety_registry_state" not in observed, command
        assert "user_decision_state" not in observed, command
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(StatementRejected):
                execute_preparation(
                    connection,
                    command,
                    SUBJECT,
                    lambda session: session.update(
                        "S01",
                        {"decision_generation": 1},
                        {"subject_id": SUBJECT},
                    ),
                )


def test_factset_build_stays_outside_subject_coordination(
    database_urls: dict[str, str],
) -> None:
    for command in ("BeginBuild", "WriteCandidate", "CompleteFactset"):
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(GuardRequired, match="isolated"):
                execute_command(connection, command, SUBJECT, lambda tx: tx.lock_subject())
    begin_basis = {
        "build_identity": "build-interface-test",
        "captured_input_frontier": "frontier-1",
        "captured_epoch": 0,
        "program_revision_id": POLICY,
        "policy_id": POLICY,
        "mapping_revision_id": None,
        "storage_mode": "FULL",
    }

    def begin(session: Any) -> tuple[str, ...]:
        session.insert(
            "S15",
            {
                "id": FACTSET_BUILD_TEST,
                "subject_id": SUBJECT,
                "factset_identity": "build-interface-test",
                "status": "BUILDING",
                "storage_mode": "FULL",
                "member_revision": 0,
                "completed_member_revision": None,
                "membership_digest": None,
                "ref_s20_id": None,
                "typed_payload": psycopg.types.json.Jsonb(session.factset_build_payload()),
            },
        )
        return session.relation_locks()

    with psycopg.connect(database_urls["admin"]) as connection:
        observed = execute_factset_build(
            connection,
            "BeginBuild",
            SUBJECT,
            FACTSET_BUILD_TEST,
            begin,
            factset_build_basis=begin_basis,
        )
    assert "factset_revisions" in observed
    assert "user_decision_state" not in observed

    def write(session: Any) -> tuple[str, ...]:
        session.insert(
            "S16",
            {
                "id": FACTSET_MEMBER_TEST,
                "subject_id": SUBJECT,
                "logical_member_key": "member-1",
                "member_kind": "FACT",
                "member_operation": "SET",
                "action_scope": "CURRENT",
                "ref_s15_id": FACTSET_BUILD_TEST,
            },
        )
        session.update(
            "S15",
            {"member_revision": 1},
            {"id": FACTSET_BUILD_TEST, "subject_id": SUBJECT},
        )
        return session.relation_locks()

    with psycopg.connect(database_urls["admin"]) as connection:
        observed = execute_factset_build(
            connection,
            "WriteCandidate",
            SUBJECT,
            FACTSET_BUILD_TEST,
            write,
            factset_build_basis={"expected_member_revision": 0},
        )
    assert "factset_revisions" in observed and "user_decision_state" not in observed

    def stale_seal(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        tx.lock_subject()
        return tx.idempotent_outcome(
            receipt_id=UUID("00000000-0000-8000-8000-000000015117"),
            actor_scope="subject",
            client_key="stale-factset-seal",
            request_hash="stale-factset-seal-hash",
            mutation=lambda session: {"unexpected": True},
            event=_event(0x15118),
            aggregate_locks={"factset_revisions": (FACTSET_BUILD_TEST,)},
            factset_seal_basis={
                "factset_id": FACTSET_BUILD_TEST,
                "captured_input_frontier": "wrong-frontier",
                "captured_epoch": 0,
                "completed_member_revision": 1,
                "membership_digest": "build-test-digest",
                "completion_identity": "build-test-completion",
                "completion_certificate": _completion_certificate(
                    FACTSET_BUILD_TEST, 1, "build-test-digest", 1
                ),
                "member_count": 1,
            },
        )

    def complete(session: Any) -> tuple[str, ...]:
        session.update(
            "S15",
            {
                "status": "READY",
                "member_revision": 1,
                "completed_member_revision": 1,
                "membership_digest": "build-test-digest",
                "typed_payload": psycopg.types.json.Jsonb(session.factset_completion_payload()),
            },
            {"id": FACTSET_BUILD_TEST, "subject_id": SUBJECT},
        )
        return session.relation_locks()

    with psycopg.connect(database_urls["admin"]) as connection:
        observed = execute_factset_build(
            connection,
            "CompleteFactset",
            SUBJECT,
            FACTSET_BUILD_TEST,
            complete,
            factset_build_basis={
                "expected_member_revision": 1,
                "membership_digest": "build-test-digest",
                "completion_identity": "build-test-completion",
                "member_count": 1,
            },
        )
    assert "factset_revisions" in observed and "user_decision_state" not in observed
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="completion basis"):
            execute_command(connection, "SealFactset", SUBJECT, stale_seal)
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        original_payload_row = connection.execute(
            "SELECT typed_payload FROM kineticloop.factset_revisions WHERE id=%s",
            (FACTSET_BUILD_TEST,),
        ).fetchone()
        assert original_payload_row is not None
        original_payload = original_payload_row[0]
        stale_payload = dict(original_payload)
        stale_payload["captured_input_frontier"] = "frontier-stale"
        stale_payload["completion_certificate"] = _completion_certificate(
            FACTSET_BUILD_TEST,
            1,
            "build-test-digest",
            1,
            captured_input_frontier="frontier-stale",
        )
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.factset_revisions SET typed_payload=%s WHERE id=%s",
            (psycopg.types.json.Jsonb(stale_payload), FACTSET_BUILD_TEST),
        )
        connection.execute("SET session_replication_role=origin")

    def stale_stored_basis(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        tx.lock_subject()
        return tx.idempotent_outcome(
            receipt_id=UUID("00000000-0000-8000-8000-000000015119"),
            actor_scope="subject",
            client_key="stale-stored-factset-basis",
            request_hash="stale-stored-factset-basis-hash",
            mutation=lambda session: {"unexpected": True},
            event=_event(0x15120),
            aggregate_locks={"factset_revisions": (FACTSET_BUILD_TEST,)},
            factset_seal_basis={
                "factset_id": FACTSET_BUILD_TEST,
                "captured_input_frontier": "frontier-1",
                "captured_epoch": 0,
                "completed_member_revision": 1,
                "membership_digest": "build-test-digest",
                "completion_identity": "build-test-completion",
                "completion_certificate": stale_payload["completion_certificate"],
                "member_count": 1,
            },
        )

    try:
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(GuardRequired, match="completion basis"):
                execute_command(connection, "SealFactset", SUBJECT, stale_stored_basis)
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.factset_revisions SET typed_payload=%s WHERE id=%s",
                (psycopg.types.json.Jsonb(original_payload), FACTSET_BUILD_TEST),
            )
            connection.execute("SET session_replication_role=origin")


    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises((GuardRequired, StatementRejected)):
            execute_factset_build(
                connection,
                "CompleteFactset",
                SUBJECT,
                FACTSET_BUILD_TEST,
                lambda session: session.update(
                    "S16",
                    {"member_operation": "SET"},
                    {"subject_id": SUBJECT},
                ),
            )
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired):
            execute_factset_build(
                connection,
                "WriteCandidate",
                SUBJECT,
                FACTSET_BUILD_TEST,
                lambda session: session.insert(
                    "S16",
                    {
                        "id": UUID("00000000-0000-8000-8000-000000015916"),
                        "subject_id": SUBJECT,
                        "ref_s15_id": UUID("00000000-0000-8000-8000-000000015915"),
                        "member_operation": "SET",
                        "logical_member_key": "wrong-build",
                        "member_kind": "FACT",
                        "action_scope": "CURRENT",
                    },
                ),
            )


def test_subject_guard_required(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            capability = RepositoryTransaction(connection.cursor(), "AdmitOrReviseIntent", SUBJECT)
            assert not [name for name in dir(capability) if "cursor" in name.lower()]
        exposed = execute_preparation(
            connection,
            "RecordProjection",
            SUBJECT,
            lambda session: [name for name in dir(session) if "cursor" in name.lower()],
        )
        assert exposed == []
        with pytest.raises(GuardRequired, match="S01"):
            execute_command(
                connection,
                "AdmitOrReviseIntent",
                SUBJECT,
                lambda tx: tx.lock_intents((INTENT,)),
            )
        with pytest.raises(StatementRejected, match="authenticated transaction subject"):
            execute_preparation(
                connection,
                "RecordProjection",
                SUBJECT,
                lambda session: session.update(
                    "S21",
                    {"projection_revision": 2},
                    {
                        "id": UUID("00000000-0000-8000-8000-000000015021"),
                        "subject_id": UUID("00000000-0000-8000-8000-000000015999"),
                    },
                ),
            )
        with pytest.raises(StatementRejected, match="cannot change"):
            execute_preparation(
                connection,
                "RecordProjection",
                SUBJECT,
                lambda session: session.update(
                    "S21",
                    {"subject_id": UUID("00000000-0000-8000-8000-000000015999")},
                    {
                        "id": UUID("00000000-0000-8000-8000-000000015021"),
                        "subject_id": SUBJECT,
                    },
                ),
            )


def test_complete_frozen_lock_order_enforced(database_urls: dict[str, str]) -> None:
    traces: list[tuple[tuple[LockStage, str], ...]] = []

    def t4(tx: RepositoryTransaction) -> None:
        tx.lock_subject()
        tx.lock_quota_buckets(
            (("DAILY", QUOTA_WINDOW_START, QUOTA_WINDOW_START + timedelta(days=1)),)
        )
        tx.lock_intents((INTENT,))
        tx.lock_receipt("AdmitOrReviseIntent", "lock-order-t4", "subject")
        traces.append(tx.lock_trace)

    def t6(tx: RepositoryTransaction) -> None:
        _acquire_registry(tx)
        tx.lock_intents((INTENT,))
        tx.lock_daily_head(date(2026, 9, 26))
        tx.lock_receipt("CommitBundle", "lock-order-t6", "subject")
        tx.lock_remaining("planning_attempts", (ATTEMPT,))
        tx.lock_remaining("validation_results", (VALIDATION,))
        traces.append(tx.lock_trace)

    def t7(tx: RepositoryTransaction) -> None:
        _acquire_registry(tx)
        tx.lock_daily_head(date(2026, 9, 26))
        tx.lock_execution((SESSION,))
        tx.lock_receipt("StartSession", "lock-order-t7", "subject")
        traces.append(tx.lock_trace)

    with psycopg.connect(database_urls["admin"]) as connection:
        execute_command(connection, "AdmitOrReviseIntent", SUBJECT, t4)
        execute_command(connection, "CommitBundle", SUBJECT, t6)
        execute_command(connection, "StartSession", SUBJECT, t7)
    assert all(
        [stage for stage, _ in trace] == sorted(stage for stage, _ in trace) for trace in traces
    )
    observed = {label.split(":", 1)[0] for trace in traces for _, label in trace}
    assert observed == {"S51", "S01", "S30", "S27", "S38", "S44", "S02", "S29", "S37"}
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "CommitBundle", SUBJECT)
            tx.lock_subject()
            with pytest.raises(GuardRequired, match="inapplicable S30"):
                tx.lock_quota_buckets(
                    (("DAILY", QUOTA_WINDOW_START, QUOTA_WINDOW_START + timedelta(days=1)),)
                )


def test_multi_key_lock_order_is_stable(database_urls: dict[str, str]) -> None:
    traces: list[tuple[tuple[LockStage, str], ...]] = []
    quota_keys = (
        ("DAILY", QUOTA_WINDOW_START, QUOTA_WINDOW_START + timedelta(days=1)),
        ("MONTHLY", QUOTA_WINDOW_START, QUOTA_WINDOW_START + timedelta(days=30)),
    )
    for quotas, intents, reservations in (
        (quota_keys, (INTENT, INTENT_2), (RESERVATION, RESERVATION_2)),
        (quota_keys[::-1], (INTENT_2, INTENT), (RESERVATION_2, RESERVATION)),
    ):
        with psycopg.connect(database_urls["admin"]) as connection:

            def t4(tx: RepositoryTransaction) -> None:
                tx.lock_subject()
                tx.lock_quota_buckets(quotas)
                tx.lock_intents(intents)
                traces.append(tx.lock_trace)

            def t5(tx: RepositoryTransaction) -> None:
                tx.lock_subject()
                tx.lock_intents(intents)
                tx.lock_reservations(reservations)
                traces.append(tx.lock_trace)

            # T4 owns S30/S27 ordering; T5 owns S27/S31 ordering.
            execute_command(connection, "AdmitOrReviseIntent", SUBJECT, t4)
            execute_command(connection, "ReserveCall", SUBJECT, t5)
    assert traces[0] == traces[2]
    assert traces[1] == traces[3]


@pytest.mark.parametrize(
    ("later", "earlier"),
    [
        ("quota", "subject"),
        ("intent", "quota"),
        ("reservation", "intent"),
        ("daily", "reservation"),
        ("execution", "daily"),
        ("receipt", "execution"),
        ("aggregate", "receipt"),
    ],
)
def test_reverse_lock_order_is_rejected(
    database_urls: dict[str, str], later: str, earlier: str
) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            command = {
                "quota": "AdmitOrReviseIntent",
                "intent": "AdmitOrReviseIntent",
                "reservation": "ReserveCall",
                "daily": "CommitBundle",
                "execution": "StartSession",
                "receipt": "StartSession",
                "aggregate": "CommitBundle",
            }[later]
            tx = RepositoryTransaction(connection.cursor(), command, SUBJECT)
            tx.lock_subject()
            actions = {
                "subject": tx.lock_subject,
                "quota": lambda: tx.lock_quota_buckets(
                    (("DAILY", QUOTA_WINDOW_START, QUOTA_WINDOW_START + timedelta(days=1)),)
                ),
                "intent": lambda: tx.lock_intents((INTENT,)),
                "reservation": lambda: tx.lock_reservations((RESERVATION,)),
                "daily": lambda: tx.lock_daily_head(date(2026, 9, 26)),
                "execution": lambda: tx.lock_execution((SESSION,)),
                "receipt": lambda: tx.lock_receipt(tx.command_kind, "reverse", "subject"),
                "aggregate": lambda: tx.lock_remaining("validation_results", (VALIDATION,)),
            }
            actions[later]()
            with pytest.raises(LockOrderViolation):
                actions[earlier]()
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "CommitBundle", SUBJECT)
            tx.lock_subject()
            with pytest.raises(LockOrderViolation):
                _acquire_registry(tx)
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "CommitBundle", SUBJECT)
            tx.lock_subject()
            tx.lock_intents((INTENT_2,))
            with pytest.raises(LockOrderViolation):
                tx.lock_intents((INTENT,))
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "CommitBundle", SUBJECT)
            tx.lock_subject()
            tx.lock_remaining("validation_results", (VALIDATION,))
            with pytest.raises(LockOrderViolation):
                tx.lock_remaining("factset_revisions", (FACTSET,))
        with psycopg.connect(database_urls["admin"]) as connection:

            def incomplete_new_root(tx: RepositoryTransaction) -> None:
                tx.lock_subject()
                tx.lock_quota_buckets(
                    (("DAILY", QUOTA_WINDOW_START, QUOTA_WINDOW_START + timedelta(days=1)),)
                )
                tx.idempotent_outcome(
                    receipt_id=UUID("00000000-0000-8000-8000-000000015702"),
                    actor_scope="subject",
                    client_key="incomplete-new-root",
                    request_hash="incomplete-new-root",
                    mutation=lambda session: {"unexpected": True},
                    event=_event(0x15703),
                )

            with pytest.raises(GuardRequired, match="T4 requires"):
                execute_command(connection, "AdmitOrReviseIntent", SUBJECT, incomplete_new_root)
    with psycopg.connect(database_urls["admin"]) as connection:
        lease_expires_at = _database_timestamp(connection, offset=timedelta(days=1))

        def wrong_identity(tx: RepositoryTransaction) -> None:
            tx.lock_subject()
            tx.lock_intents((INTENT,))
            tx.require_lease_acquisition_basis(
                INTENT,
                expected_owner_id="worker-a",
                expected_fence=7,
                new_owner_id="worker-a",
                new_fence=8,
                new_lease_expires_at=lease_expires_at,
                expected_request_revision=1,
            )

            def mutate_wrong_identity(session: Any) -> Mapping[str, Any]:
                session.update(
                    "S27",
                    {"typed_payload": psycopg.types.json.Jsonb({"bad": True})},
                    {"id": INTENT_2, "subject_id": SUBJECT},
                )
                return {"unexpected": True}

            tx.idempotent_outcome(
                receipt_id=UUID("00000000-0000-8000-8000-000000015712"),
                actor_scope="subject",
                client_key="wrong-identity-lock",
                request_hash="wrong-identity-lock",
                mutation=mutate_wrong_identity,
                event=_event(0x15713),
            )

        with pytest.raises(GuardRequired, match="exact row lock"):
            execute_command(connection, "AcquireLease", SUBJECT, wrong_identity)


def test_receipt_before_s01_is_rejected(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "ReserveCall", SUBJECT)
            with pytest.raises(GuardRequired, match="S01"):
                tx.lock_receipt("ReserveCall", "too-early", "subject")


def test_artifact_identity_required(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(ArtifactIdentityRequired, match="every leased artifact"):
            execute_command(
                connection,
                "CommitBundle",
                SUBJECT,
                lambda tx: tx.acquire_registry_lease(_registry_ids()),
            )

    def operation(tx: RepositoryTransaction) -> None:
        _acquire_registry(tx)
        with pytest.raises(ArtifactIdentityRequired):
            tx.require_artifact(
                ArtifactIdentity(ARTIFACT, "POLICY_BUNDLE", "wrong", "1", _SAFETY.CONTENT_HASH)
            )
        tx.require_artifact(
            ArtifactIdentity(
                ARTIFACT,
                "POLICY_BUNDLE",
                "artifact",
                "1",
                _SAFETY.CONTENT_HASH,
            )
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        execute_command(connection, "CommitBundle", SUBJECT, operation)


def test_direct_write_bypass_rejected(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["application"]) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "UPDATE kineticloop.planning_intents SET status='FAILED' WHERE id=%s",
                (INTENT,),
            )

    def wrong_quota(tx: RepositoryTransaction) -> None:
        tx.lock_subject()
        tx.lock_quota_buckets(
            (("DAILY", QUOTA_WINDOW_START, QUOTA_WINDOW_START + timedelta(days=1)),)
        )
        tx.lock_intents((INTENT,))
        tx.idempotent_outcome(
            receipt_id=UUID("00000000-0000-8000-8000-000000015962"),
            actor_scope="subject",
            client_key="wrong-quota",
            request_hash="wrong-quota-hash",
            mutation=lambda session: (
                session.update(
                    "S30",
                    {"admitted_count": 2},
                    {
                        "subject_id": SUBJECT,
                        "id": UUID("00000000-0000-8000-8000-000000015930"),
                    },
                ),
                {"unexpected": True},
            )[1],
            event=_event(0x15963),
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="exact row lock"):
            execute_command(connection, "AdmitOrReviseIntent", SUBJECT, wrong_quota)


@pytest.mark.parametrize(
    ("command", "tag"),
    [
        ("ReceiveEvidence", 0x15210),
        ("DecideAdmission", 0x15220),
        ("PublishManifest", 0x15230),
        ("AdmitOrReviseIntent", 0x15240),
        ("AcquireLease", 0x15250),
        ("CommitBundle", 0x15260),
        ("StartSession", 0x15270),
        ("SettleCall", 0x15280),
    ],
)
def test_event_outbox_atomicity_enforced(
    database_urls: dict[str, str], command: str, tag: int
) -> None:
    if command == "SettleCall":
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute(
                "UPDATE kineticloop.call_reservations SET status='DISPATCH_INTENT' WHERE id=%s",
                (RESERVATION_2,),
            )
    receipt = UUID(f"00000000-0000-8000-8000-{tag:012x}")
    event = _event(tag + 1)
    lease_expires_at: datetime | None = None

    def acquired_lease_expiry() -> datetime:
        assert lease_expires_at is not None
        return lease_expires_at

    def mutate(session: Any) -> Mapping[str, Any]:
        if command == "ReceiveEvidence":
            session.insert(
                "S09",
                {
                    "id": UUID(f"00000000-0000-8000-8000-{tag + 9:012x}"),
                    "subject_id": SUBJECT,
                    "source_connection_identity": command,
                    "source_object_type": "TEST",
                    "source_object_identity": "object",
                    "source_revision": "1",
                    "trust_class": "SOURCE_REPORTED",
                    "source_class": "TEST",
                    "command_authority": "NONE",
                },
            )
        elif command == "DecideAdmission":
            session.update(
                "S01",
                {"authorization_epoch": 1},
                {"subject_id": SUBJECT},
            )
        elif command == "PublishManifest":
            session.update(
                "S23",
                {"status": "PUBLISHED"},
                {"id": MANIFEST_BUILD, "subject_id": SUBJECT},
            )
        elif command == "AcquireLease":
            session.update(
                "S27",
                {
                    "status": "RUNNING",
                    "lease_owner": "worker-a",
                    "fence_token": 8,
                    "lease_expires_at": acquired_lease_expiry(),
                    "typed_payload": psycopg.types.json.Jsonb({"atomic": command}),
                },
                {"id": INTENT, "subject_id": SUBJECT},
            )
        elif command in {"AdmitOrReviseIntent", "SettleCall"}:
            session.update(
                "S27",
                {"typed_payload": psycopg.types.json.Jsonb({"atomic": command})},
                {"id": INTENT, "subject_id": SUBJECT},
            )
        elif command == "CommitBundle":
            session.update(
                "S38",
                {"head_revision": 1},
                {"id": DAILY_HEAD, "subject_id": SUBJECT},
            )
        else:
            session.update(
                "S44",
                {"lifecycle": "IN_PROGRESS", "execution_revision": 1},
                {"id": SESSION, "subject_id": SUBJECT},
            )
        return {"command": command}

    def acquire_guards(tx: RepositoryTransaction) -> None:
        if tx.spec.registry_required:
            _acquire_registry(tx)
        elif tx.spec.subject_guard_required:
            tx.lock_subject()
        if command == "AdmitOrReviseIntent":
            tx.lock_quota_buckets(
                (("DAILY", QUOTA_WINDOW_START, QUOTA_WINDOW_START + timedelta(days=1)),)
            )
            tx.lock_intents((INTENT,))
        elif command in {"AcquireLease", "SettleCall"}:
            tx.lock_intents((INTENT,))
            if command == "AcquireLease":
                tx.require_lease_acquisition_basis(
                    INTENT,
                    expected_owner_id="worker-a",
                    expected_fence=7,
                    new_owner_id="worker-a",
                    new_fence=8,
                    new_lease_expires_at=acquired_lease_expiry(),
                    expected_request_revision=1,
                )
            else:
                tx.lock_reservations((RESERVATION_2,))
        elif command == "CommitBundle":
            tx.lock_intents((INTENT,))
            tx.lock_daily_head(date(2026, 9, 26))
            tx.require_current_fence(
                INTENT,
                owner_id="worker-a",
                fence=7,
                expected_request_revision=1,
                expected_attempt_id=ATTEMPT,
            )
        elif command == "StartSession":
            tx.lock_daily_head(date(2026, 9, 26))
            tx.lock_execution((SESSION,))

    def aggregate_locks() -> Mapping[str, tuple[UUID, ...]] | None:
        if command == "PublishManifest":
            return {"manifest_builds": (MANIFEST_BUILD,)}
        if command == "CommitBundle":
            return {
                "planning_attempts": (ATTEMPT,),
                "validation_results": (VALIDATION,),
            }
        return None

    def operation(tx: RepositoryTransaction) -> None:
        acquire_guards(tx)

        def fail(session: Any) -> Mapping[str, Any]:
            mutate(session)
            raise RuntimeError("failure injection")

        tx.idempotent_outcome(
            receipt_id=receipt,
            actor_scope="subject",
            client_key="atomic-fail",
            request_hash="atomic-hash",
            mutation=fail,
            event=event,
            aggregate_locks=aggregate_locks(),
            source_identity_key=(
                f"{SUBJECT}:ReceiveEvidence:TEST:object:1" if command == "ReceiveEvidence" else None
            ),
            authorization_basis=(
                {
                    "validation_id": VALIDATION,
                    "resolution_id": RESOLUTION,
                    "intent_id": INTENT,
                    "head_id": DAILY_HEAD,
                }
                if command == "CommitBundle"
                else None
            ),
            invalidation_scope="EXECUTION" if command == "DecideAdmission" else None,
            expected_transition="DISPATCH_INTENT" if command == "SettleCall" else None,
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        if command == "AcquireLease":
            lease_expires_at = _database_timestamp(connection, offset=timedelta(days=1))
        with pytest.raises(RuntimeError, match="failure injection"):
            execute_command(connection, command, SUBJECT, operation)
    with psycopg.connect(database_urls["admin"]) as connection:
        if command == "ReceiveEvidence":
            assert connection.execute(
                "SELECT count(*) FROM kineticloop.evidence_revisions "
                "WHERE source_connection_identity=%s",
                (command,),
            ).fetchone() == (0,)
        elif command == "DecideAdmission":
            assert connection.execute(
                "SELECT authorization_epoch FROM kineticloop.user_decision_state "
                "WHERE subject_id=%s",
                (SUBJECT,),
            ).fetchone() == (0,)
        elif command == "PublishManifest":
            assert connection.execute(
                "SELECT captured_epoch FROM kineticloop.manifest_builds WHERE id=%s",
                (MANIFEST_BUILD,),
            ).fetchone() == (0,)
        elif command in {"AdmitOrReviseIntent", "AcquireLease", "SettleCall"}:
            assert connection.execute(
                "SELECT typed_payload FROM kineticloop.planning_intents WHERE id=%s",
                (INTENT,),
            ).fetchone() == ({},)
        elif command == "CommitBundle":
            assert connection.execute(
                "SELECT head_revision FROM kineticloop.daily_plan_heads WHERE id=%s",
                (DAILY_HEAD,),
            ).fetchone() == (0,)
        else:
            assert connection.execute(
                "SELECT execution_revision FROM kineticloop.workout_sessions WHERE id=%s",
                (SESSION,),
            ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.command_receipts WHERE id=%s", (receipt,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.domain_events WHERE id=%s", (event.event_id,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.outbox_deliveries WHERE id=%s", (event.outbox_id,)
        ).fetchone() == (0,)

    if command in {"AcquireLease", "CommitBundle", "StartSession"}:
        return
    if command != "ReceiveEvidence":
        partial_receipt = UUID(f"00000000-0000-8000-8000-{tag + 0x1000:012x}")
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(GuardRequired):
                execute_command(
                    connection,
                    command,
                    SUBJECT,
                    lambda tx: (
                        acquire_guards(tx),  # type: ignore[func-returns-value]
                        tx.idempotent_outcome(
                            receipt_id=partial_receipt,
                            actor_scope="subject",
                            client_key="atomic-partial",
                            request_hash="atomic-partial-hash",
                            mutation=mutate,
                            event=_event(tag + 0x1001),
                            aggregate_locks=aggregate_locks(),
                            authorization_basis=(
                                {
                                    "validation_id": VALIDATION,
                                    "resolution_id": RESOLUTION,
                                    "intent_id": INTENT,
                                    "head_id": DAILY_HEAD,
                                }
                                if command == "CommitBundle"
                                else None
                            ),
                        ),
                    ),
                )
        with psycopg.connect(database_urls["admin"]) as connection:
            assert connection.execute(
                "SELECT count(*) FROM kineticloop.command_receipts WHERE id=%s",
                (partial_receipt,),
            ).fetchone() == (0,)
        return

    success_receipt = UUID(f"00000000-0000-8000-8000-{tag + 0x1000:012x}")
    success_event = _event(tag + 0x1001)

    def success(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        acquire_guards(tx)
        return tx.idempotent_outcome(
            receipt_id=success_receipt,
            actor_scope="subject",
            client_key="atomic-success",
            request_hash="atomic-success-hash",
            mutation=mutate,
            event=success_event,
            aggregate_locks=aggregate_locks(),
            source_identity_key=(
                f"{SUBJECT}:ReceiveEvidence:TEST:object:1" if command == "ReceiveEvidence" else None
            ),
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        outcome, replayed = execute_command(connection, command, SUBJECT, success)
    assert outcome == {"command": command}
    assert not replayed
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.command_receipts WHERE id=%s",
            (success_receipt,),
        ).fetchone() == (1,)

        assert connection.execute(
            "SELECT count(*) FROM kineticloop.domain_events WHERE id=%s",
            (success_event.event_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.outbox_deliveries WHERE id=%s",
            (success_event.outbox_id,),
        ).fetchone() == (1,)
        if command == "DecideAdmission":
            connection.execute(
                "UPDATE kineticloop.user_decision_state SET authorization_epoch=0 "
                "WHERE subject_id=%s",
                (SUBJECT,),
            )
        elif command == "PublishManifest":
            connection.execute(
                "UPDATE kineticloop.manifest_builds SET captured_epoch=0 WHERE id=%s",
                (MANIFEST_BUILD,),
            )
        elif command in {"AdmitOrReviseIntent", "SettleCall"}:
            connection.execute(
                "UPDATE kineticloop.planning_intents SET typed_payload='{}' WHERE id=%s",
                (INTENT,),
            )
        elif command == "AcquireLease":
            connection.execute(
                "UPDATE kineticloop.planning_intents SET typed_payload='{}',"
                "lease_owner='worker-a',fence_token=7,"
                "lease_expires_at=clock_timestamp()+interval '1 day' WHERE id=%s",
                (INTENT,),
            )
        elif command == "CommitBundle":
            connection.execute(
                "UPDATE kineticloop.daily_plan_heads SET head_revision=0 WHERE id=%s",
                (DAILY_HEAD,),
            )
        elif command == "StartSession":
            connection.execute(
                "UPDATE kineticloop.workout_sessions SET execution_revision=0 WHERE id=%s",
                (SESSION,),
            )


def test_t1_observation_key_identity_is_supported(database_urls: dict[str, str]) -> None:
    observation_evidence = UUID("00000000-0000-8000-8000-000000015819")

    def receive_observation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        def mutation(session: Any) -> Mapping[str, Any]:
            session.insert(
                "S09",
                {
                    "id": observation_evidence,
                    "subject_id": SUBJECT,
                    "source_connection_identity": "t1-observation",
                    "source_object_type": "TEST",
                    "source_object_identity": "observation-object",
                    "observation_key": "observed-at-1",
                    "trust_class": "TEST_ONLY",
                    "source_class": "TEST",
                    "command_authority": "NONE",
                },
            )
            return {"evidence_id": str(observation_evidence)}

        return tx.idempotent_outcome(
            receipt_id=UUID("00000000-0000-8000-8000-000000015820"),
            actor_scope="subject",
            client_key="observation-key-path",
            request_hash="observation-key-hash",
            mutation=mutation,
            event=_event(0x15821),
            source_identity_key=f"{SUBJECT}:t1-observation:observed-at-1",
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        observation_outcome, observation_replayed = execute_command(
            connection, "ReceiveEvidence", SUBJECT, receive_observation
        )
    assert not observation_replayed
    assert observation_outcome["evidence_id"] == str(observation_evidence)

    barrier = threading.Barrier(2)
    outcomes: list[Mapping[str, Any]] = []
    errors: list[BaseException] = []

    def contender(tag: int, object_identity: str) -> None:
        evidence_id = UUID(f"00000000-0000-8000-8000-{tag:012x}")

        def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
            def mutation(session: Any) -> Mapping[str, Any]:
                session.insert(
                    "S09",
                    {
                        "id": evidence_id,
                        "subject_id": SUBJECT,
                        "source_connection_identity": "t1-observation-race",
                        "source_object_type": "TEST",
                        "source_object_identity": object_identity,
                        "observation_key": "same-database-observation-key",
                        "trust_class": "TEST_ONLY",
                        "source_class": "TEST",
                        "command_authority": "NONE",
                    },
                )
                return {"evidence_id": str(evidence_id)}

            return tx.idempotent_outcome(
                receipt_id=UUID(f"00000000-0000-8000-8000-{tag + 10:012x}"),
                actor_scope="subject",
                client_key=f"observation-race-{tag}",
                request_hash=f"observation-race-hash-{tag}",
                mutation=mutation,
                event=_event(tag + 20),
                source_identity_key=(
                    f"{SUBJECT}:t1-observation-race:same-database-observation-key"
                ),
            )

        try:
            barrier.wait(timeout=5)
            with psycopg.connect(database_urls["admin"]) as connection:
                outcome, _ = execute_command(connection, "ReceiveEvidence", SUBJECT, operation)
                outcomes.append(outcome)
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=contender, args=(0x15830, "object-a")),
        threading.Thread(target=contender, args=(0x15840, "object-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert all(not thread.is_alive() for thread in threads)
    assert len(outcomes) == 1
    assert len(errors) == 1 and isinstance(errors[0], IdempotencyConflict)
    assert not isinstance(errors[0], psycopg.errors.UniqueViolation)
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.evidence_revisions "
            "WHERE source_connection_identity='t1-observation-race' "
            "AND observation_key='same-database-observation-key'"
        ).fetchone() == (1,)


def test_outbox_dispatcher_does_not_lock_subject_guard(
    database_urls: dict[str, str],
) -> None:
    blocker = psycopg.connect(database_urls["admin"])
    blocker.execute(
        "SELECT subject_id FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
        (SUBJECT,),
    )
    outcome: dict[str, Any] = {}

    def worker() -> None:
        with psycopg.connect(
            database_urls["admin"], application_name="kl015-outbox-observer"
        ) as connection:
            outcome["ids"] = claim_outbox(connection, destination="authorization-events")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive(), "S01 contention must not block OutboxDispatcher"
    assert outcome["ids"]
    blocker.rollback()
    blocker.close()


def test_stale_fence_commit_is_rejected(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.planning_intents SET lease_owner='worker-a',fence_token=7,"
            "lease_expires_at=clock_timestamp()-interval '1 minute' WHERE id=%s",
            (INTENT,),
        )

    takeover_ready = threading.Event()
    old_started = threading.Event()
    release_takeover = threading.Event()
    errors: list[BaseException] = []

    def takeover() -> None:
        try:
            with psycopg.connect(database_urls["admin"]) as connection:
                lease_expires_at = _database_timestamp(connection, offset=timedelta(days=1))

                def acquire(tx: RepositoryTransaction) -> None:
                    tx.lock_subject()
                    tx.lock_intents((INTENT,))
                    tx.require_lease_acquisition_basis(
                        INTENT,
                        expected_owner_id="worker-a",
                        expected_fence=7,
                        new_owner_id="worker-b",
                        new_fence=8,
                        new_lease_expires_at=lease_expires_at,
                        expected_request_revision=1,
                    )
                    takeover_ready.set()
                    assert release_takeover.wait(timeout=5)

                    def mutation(session: Any) -> Mapping[str, Any]:
                        session.update(
                            "S27",
                            {
                                "status": "RUNNING",
                                "lease_owner": "worker-b",
                                "fence_token": 8,
                                "lease_expires_at": lease_expires_at,
                            },
                            {"subject_id": SUBJECT, "id": INTENT},
                        )
                        return {"intent_id": str(INTENT), "fence": 8}

                    tx.idempotent_outcome(
                        receipt_id=UUID("00000000-0000-8000-8000-000000015702"),
                        actor_scope="subject",
                        client_key="takeover-api",
                        request_hash="takeover-api-hash",
                        mutation=mutation,
                        event=_event(0x15703),
                    )

                execute_command(connection, "AcquireLease", SUBJECT, acquire)
        except BaseException as error:
            errors.append(error)

    def stale_commit() -> None:
        try:
            assert takeover_ready.wait(timeout=5)
            old_started.set()
            with psycopg.connect(database_urls["admin"]) as connection:

                def operation(tx: RepositoryTransaction) -> None:
                    tx.lock_subject()
                    tx.lock_intents((INTENT,))
                    tx.require_current_fence(
                        INTENT,
                        owner_id="worker-a",
                        fence=7,
                        expected_request_revision=1,
                        expected_attempt_id=ATTEMPT,
                    )

                with pytest.raises(FenceLost):
                    execute_command(connection, "ReserveCall", SUBJECT, operation)
        except BaseException as error:
            errors.append(error)

    takeover_thread = threading.Thread(target=takeover)
    stale_thread = threading.Thread(target=stale_commit)
    takeover_thread.start()
    stale_thread.start()
    assert old_started.wait(timeout=5)
    release_takeover.set()
    takeover_thread.join(timeout=5)
    stale_thread.join(timeout=5)
    assert not takeover_thread.is_alive() and not stale_thread.is_alive()
    assert not errors

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        stale_lease = _database_timestamp(connection, offset=-timedelta(minutes=1))
        future_deadline = _database_timestamp(connection, offset=timedelta(days=2))
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='FOUND_VALID_PLAN',"
            "lease_expires_at=%s,deadline=%s WHERE id=%s",
            (stale_lease, future_deadline, INTENT),
        )
        connection.execute("SET session_replication_role=origin")
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(FenceLost):
            execute_command(
                connection,
                "ReapIntent",
                SUBJECT,
                lambda tx: (
                    tx.lock_subject(),  # type: ignore[func-returns-value]
                    tx.lock_intents((INTENT,)),  # type: ignore[func-returns-value]
                    tx.require_reaper_basis(  # type: ignore[func-returns-value]
                        INTENT,
                        owner_id="worker-b",
                        fence=8,
                        expected_deadline=future_deadline,
                        expected_request_revision=1,
                        expected_attempt_id=ATTEMPT,
                    ),
                ),
            )
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        expired_deadline = _database_timestamp(connection, offset=-timedelta(minutes=1))
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',deadline=%s WHERE id=%s",
            (expired_deadline, INTENT),
        )
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(FenceLost):
            execute_command(
                connection,
                "ReapIntent",
                SUBJECT,
                lambda tx: (
                    tx.lock_subject(),  # type: ignore[func-returns-value]
                    tx.lock_intents((INTENT,)),  # type: ignore[func-returns-value]
                    tx.require_reaper_basis(  # type: ignore[func-returns-value]
                        INTENT,
                        owner_id="worker-b",
                        fence=8,
                        expected_deadline=expired_deadline - timedelta(minutes=1),
                        expected_request_revision=1,
                        expected_attempt_id=ATTEMPT,
                    ),
                ),
            )
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        future_deadline = _database_timestamp(connection, offset=timedelta(days=2))
        live_lease = _database_timestamp(connection, offset=timedelta(days=1))
        connection.execute(
            "UPDATE kineticloop.planning_intents SET deadline=%s,lease_expires_at=%s WHERE id=%s",
            (future_deadline, live_lease, INTENT),
        )

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        reap_deadline = _database_timestamp(connection, offset=timedelta(days=2))
        expired_lease = _database_timestamp(connection, offset=-timedelta(minutes=1))
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',"
            "deadline=%s,lease_expires_at=%s,current_attempt_id=%s WHERE id=%s",
            (reap_deadline, expired_lease, ATTEMPT, INTENT),
        )

    def reap(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        tx.lock_subject()
        tx.lock_intents((INTENT,))
        tx.lock_reservations((RESERVATION_2,))
        tx.require_reaper_basis(
            INTENT,
            owner_id="worker-b",
            fence=8,
            expected_deadline=reap_deadline,
            expected_request_revision=1,
            expected_attempt_id=ATTEMPT,
        )

        def mutation(session: Any) -> Mapping[str, Any]:
            session.update(
                "S27",
                {"status": "FAILED", "lease_expires_at": expired_lease},
                {"id": INTENT, "subject_id": SUBJECT},
            )
            session.update(
                "S29",
                {
                    "status": "FAILED",
                    "failure_code": "LEASE_EXPIRED",
                    "completed_at": COMPLETION_RECORDED_AT,
                },
                {"id": ATTEMPT, "subject_id": SUBJECT},
            )
            return {"intent_id": str(INTENT), "status": "FAILED"}

        return tx.idempotent_outcome(
            receipt_id=UUID("00000000-0000-8000-8000-000000015490"),
            actor_scope="subject",
            client_key="reaper-success",
            request_hash="reaper-success-hash",
            mutation=mutation,
            event=_event(0x15491),
            aggregate_locks={"planning_attempts": (ATTEMPT,)},
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        reaped, replayed = execute_command(connection, "ReapIntent", SUBJECT, reap)
    assert not replayed and reaped["status"] == "FAILED"

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        reset_deadline = _database_timestamp(connection, offset=timedelta(days=2))
        reset_lease = _database_timestamp(connection, offset=timedelta(days=1))
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',lease_owner='worker-a',"
            "fence_token=7,deadline=%s,lease_expires_at=%s WHERE id=%s",
            (reset_deadline, reset_lease, INTENT),
        )
        connection.execute(
            "UPDATE kineticloop.planning_attempts SET status='RUNNING',failure_code=NULL,"
            "completed_at=NULL WHERE id=%s",
            (ATTEMPT,),
        )


def test_dispatch_first_winner_and_replay_non_resend(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="exclusive to PermitDispatch"):
            execute_command(
                connection,
                "SettleCall",
                SUBJECT,
                lambda tx: (
                    tx.lock_subject(),  # type: ignore[func-returns-value]
                    tx.lock_intents((INTENT,)),  # type: ignore[func-returns-value]
                    tx.lock_reservations((RESERVATION,)),  # type: ignore[func-returns-value]
                    tx.permit_dispatch(
                        RESERVATION,
                        permit_key="wrong-owner",
                        request_hash="wrong-owner-hash",
                        receipt_id=UUID("00000000-0000-8000-8000-000000015501"),
                        event=_event(0x15502),
                        fence=10,
                    ),
                ),
            )

    permit_receipt = UUID("00000000-0000-8000-8000-000000015502")
    permit_event = _event(0x15503)
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        expired_deadline = _database_timestamp(connection, offset=-timedelta(minutes=1))
        connection.execute(
            "UPDATE kineticloop.planning_intents "
            "SET status='RUNNING',lease_owner='worker-dispatch',fence_token=10,"
            "lease_expires_at=clock_timestamp()+interval '1 day' WHERE id=%s",
            (INTENT,),
        )
        connection.execute(
            "UPDATE kineticloop.planning_intents SET deadline=%s WHERE id=%s",
            (expired_deadline, INTENT),
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(FenceLost):
            execute_command(
                connection,
                "PermitDispatch",
                SUBJECT,
                lambda tx: (
                    tx.lock_subject(),  # type: ignore[func-returns-value]
                    tx.lock_intents((INTENT,)),  # type: ignore[func-returns-value]
                    tx.require_current_fence(  # type: ignore[func-returns-value]
                        INTENT,
                        owner_id="worker-dispatch",
                        fence=10,
                        expected_request_revision=1,
                        expected_attempt_id=ATTEMPT,
                    ),
                ),
            )
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        future_deadline = _database_timestamp(connection, offset=timedelta(days=2))
        connection.execute(
            "UPDATE kineticloop.planning_intents SET deadline=%s WHERE id=%s",
            (future_deadline, INTENT),
        )
        connection.execute(
            "UPDATE kineticloop.call_reservations SET ref_s29_id=%s WHERE id=%s",
            (ATTEMPT_2, RESERVATION),
        )

    def stale_attempt(tx: RepositoryTransaction) -> Any:
        tx.lock_subject()
        tx.lock_intents((INTENT,))
        tx.lock_reservations((RESERVATION,))
        tx.require_current_fence(
            INTENT,
            owner_id="worker-dispatch",
            fence=10,
            expected_request_revision=1,
            expected_attempt_id=ATTEMPT,
        )
        return tx.permit_dispatch(
            RESERVATION,
            permit_key="stale-attempt",
            request_hash="stale-attempt-hash",
            receipt_id=UUID("00000000-0000-8000-8000-000000015522"),
            event=_event(0x15523),
            fence=10,
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(DispatchNotPermitted):
            execute_command(connection, "PermitDispatch", SUBJECT, stale_attempt)
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.call_reservations SET ref_s29_id=%s WHERE id=%s",
            (ATTEMPT, RESERVATION),
        )

    def permit(tx: RepositoryTransaction, permit_key: str) -> Any:
        tx.lock_subject()
        tx.lock_intents((INTENT,))
        tx.lock_reservations((RESERVATION,))
        tx.require_current_fence(
            INTENT,
            owner_id="worker-dispatch",
            fence=10,
            expected_request_revision=1,
            expected_attempt_id=ATTEMPT,
        )
        return tx.permit_dispatch(
            RESERVATION,
            permit_key=permit_key,
            request_hash=f"hash-{permit_key}",
            receipt_id=permit_receipt,
            event=permit_event,
            fence=10,
        )

    barrier = threading.Barrier(2)
    outcomes: list[Any] = []
    errors: list[BaseException] = []

    def contender() -> None:
        try:
            barrier.wait(timeout=5)
            with psycopg.connect(database_urls["admin"]) as connection:
                outcomes.append(
                    execute_command(
                        connection,
                        "PermitDispatch",
                        SUBJECT,
                        lambda tx: permit(tx, "permit-1"),
                    )
                )
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=contender) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert sum(result.sendable for result in outcomes) == 1
    assert sum(result.replayed for result in outcomes) == 1
    with psycopg.connect(database_urls["admin"]) as connection:
        replay = execute_command(
            connection,
            "PermitDispatch",
            SUBJECT,
            lambda tx: permit(tx, "permit-1"),
        )
    assert not replay.sendable and replay.replayed
    with psycopg.connect(database_urls["admin"]) as connection:
        historical_permit = replay_outcome(
            connection,
            "PermitDispatch",
            SUBJECT,
            actor_scope="subject",
            client_key="permit-1",
            request_hash="hash-permit-1",
        )
    assert historical_permit["sendable"] is False
    assert historical_permit["replayed"] is True
    with psycopg.connect(database_urls["admin"]) as connection:
        for table, object_id in (
            ("command_receipts", permit_receipt),
            ("domain_events", permit_event.event_id),
            ("outbox_deliveries", permit_event.outbox_id),
        ):
            assert connection.execute(
                f"SELECT count(*) FROM kineticloop.{table} WHERE id=%s", (object_id,)
            ).fetchone() == (1,)
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(DispatchNotPermitted):
            second_receipt = UUID("00000000-0000-8000-8000-000000015512")
            second_event = _event(0x15513)

            def conflicting(tx: RepositoryTransaction) -> Any:
                tx.lock_subject()
                tx.lock_intents((INTENT,))
                tx.lock_reservations((RESERVATION,))
                tx.require_current_fence(
                    INTENT,
                    owner_id="worker-dispatch",
                    fence=10,
                    expected_request_revision=1,
                    expected_attempt_id=ATTEMPT,
                )
                return tx.permit_dispatch(
                    RESERVATION,
                    permit_key="permit-2",
                    request_hash="hash-permit-2",
                    receipt_id=second_receipt,
                    event=second_event,
                    fence=10,
                )

            execute_command(
                connection,
                "PermitDispatch",
                SUBJECT,
                conflicting,
            )
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.command_receipts WHERE id=%s",
            (second_receipt,),
        ).fetchone() == (0,)


def test_t8_settlement_rejects_crosswired_intent_reservation(
    database_urls: dict[str, str],
) -> None:
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.call_reservations SET ref_s27_id=%s,ref_s29_id=%s WHERE id=%s",
            (INTENT_2, ATTEMPT_2, RESERVATION_2),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(GuardRequired, match="exact locked intent/attempt"):
                execute_command(
                    connection,
                    "SettleCall",
                    SUBJECT,
                    lambda tx: (
                        tx.lock_subject(),  # type: ignore[func-returns-value]
                        tx.lock_intents((INTENT,)),  # type: ignore[func-returns-value]
                        tx.lock_reservations(  # type: ignore[func-returns-value]
                            (RESERVATION_2,)
                        ),
                        tx.idempotent_outcome(
                            receipt_id=UUID("00000000-0000-8000-8000-000000015562"),
                            actor_scope="subject",
                            client_key="crosswired-settlement",
                            request_hash="crosswired-settlement-hash",
                            mutation=lambda session: {"unexpected": True},
                            event=_event(0x15563),
                            expected_transition="DISPATCH_INTENT",
                        ),
                    ),
                )
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.call_reservations SET ref_s27_id=%s,ref_s29_id=%s WHERE id=%s",
                (INTENT, ATTEMPT, RESERVATION_2),
            )
            connection.execute("SET session_replication_role=origin")


@pytest.mark.parametrize(
    "command",
    (
        "DecideAssociation",
        "DecideAdmission",
        "AcceptFactRevision",
        "ApplyControl",
        "ClearControl",
        "ApproveChange",
        "ActivateApprovedProgram",
        "RecordActualExecution",
        "CompleteReportedWorkout",
    ),
)
def test_t2_invalidation_scope_is_mandatory(
    database_urls: dict[str, str], command: str
) -> None:
    def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        tx.lock_subject()
        if command == "CompleteReportedWorkout":
            tx.lock_execution((SESSION,))
        return tx.idempotent_outcome(
            receipt_id=UUID("00000000-0000-8000-8000-000000015570"),
            actor_scope="subject",
            client_key=f"missing-scope-{command}",
            request_hash=f"missing-scope-{command}-hash",
            mutation=lambda session: {"unexpected": True},
            event=_event(0x15571),
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="nonempty canonical scope"):
            execute_command(connection, command, SUBJECT, operation)


def test_lease_commands_reject_arbitrary_attempt_locks(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',lease_owner='lease-test',"
            "fence_token=20,lease_expires_at=clock_timestamp()+interval '1 hour',"
            "deadline=clock_timestamp()+interval '2 days' WHERE id=%s",
            (INTENT,),
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        lease_expires_at = _database_timestamp(connection, offset=timedelta(days=1))

        def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
            tx.lock_subject()
            tx.lock_intents((INTENT,))
            tx.require_lease_acquisition_basis(
                INTENT,
                expected_owner_id="lease-test",
                expected_fence=20,
                new_owner_id="lease-test",
                new_fence=21,
                new_lease_expires_at=lease_expires_at,
                expected_request_revision=1,
            )
            return tx.idempotent_outcome(
                receipt_id=UUID("00000000-0000-8000-8000-000000015572"),
                actor_scope="subject",
                client_key="lease-arbitrary-attempt-lock",
                request_hash="lease-arbitrary-attempt-lock-hash",
                mutation=lambda session: {"unexpected": True},
                event=_event(0x15573),
                aggregate_locks={"planning_attempts": (ATTEMPT,)},
            )

        with pytest.raises(GuardRequired, match="inapplicable S29"):
            execute_command(connection, "AcquireLease", SUBJECT, operation)


def test_t2_invalidation_scope_must_match_active_policy(
    database_urls: dict[str, str],
) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="active-policy classification"):
            execute_command(
                connection,
                "DecideAssociation",
                SUBJECT,
                lambda tx: (
                    tx.lock_subject(),  # type: ignore[func-returns-value]
                    tx.idempotent_outcome(
                        receipt_id=UUID("00000000-0000-8000-8000-000000015573"),
                        actor_scope="subject",
                        client_key="wrong-policy-invalidation-scope",
                        request_hash="wrong-policy-invalidation-scope-hash",
                        mutation=lambda session: {"unexpected": True},
                        event=_event(0x15574),
                        invalidation_scope="ARBITRARY",
                    ),
                ),
            )


def test_commit_bundle_rejects_inapplicable_reservation_lock(
    database_urls: dict[str, str],
) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="inapplicable S31"):
            execute_command(
                connection,
                "CommitBundle",
                SUBJECT,
                lambda tx: (
                    _acquire_registry(tx),
                    tx.lock_intents((INTENT,)),  # type: ignore[func-returns-value]
                    tx.lock_reservations(  # type: ignore[func-returns-value]
                        (RESERVATION_2,)
                    ),
                ),
            )


def test_t8_expected_transition_is_exact(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.call_reservations SET status='DISPATCH_INTENT' WHERE id=%s",
            (RESERVATION_2,),
        )
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="expected transition"):
            execute_command(
                connection,
                "SettleCall",
                SUBJECT,
                lambda tx: (
                    tx.lock_subject(),  # type: ignore[func-returns-value]
                    tx.lock_intents((INTENT,)),  # type: ignore[func-returns-value]
                    tx.lock_reservations(  # type: ignore[func-returns-value]
                        (RESERVATION_2,)
                    ),
                    tx.idempotent_outcome(
                        receipt_id=UUID("00000000-0000-8000-8000-000000015574"),
                        actor_scope="subject",
                        client_key="stale-settlement-transition",
                        request_hash="stale-settlement-transition-hash",
                        mutation=lambda session: {"unexpected": True},
                        event=_event(0x15575),
                        expected_transition="UNKNOWN",
                    ),
                ),
            )


def test_t8_stale_contender_rechecks_after_locked_transition(
    database_urls: dict[str, str],
) -> None:
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.call_reservations SET status='DISPATCH_INTENT',"
            "settlement_revision=0 WHERE id=%s",
            (RESERVATION_2,),
        )
    first_has_subject = threading.Event()
    release_first = threading.Event()
    errors: list[BaseException] = []

    def mark_unknown() -> None:
        try:
            def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
                tx.lock_subject()
                first_has_subject.set()
                assert release_first.wait(timeout=5)
                tx.lock_intents((INTENT,))
                tx.lock_reservations((RESERVATION_2,))

                def mutation(session: Any) -> Mapping[str, Any]:
                    transition = session.settlement_transition()
                    session.insert(
                        "S32",
                        {
                            "id": UUID("00000000-0000-8000-8000-000000015576"),
                            "subject_id": SUBJECT,
                            "event_type": transition["target_status"],
                            "transition_revision": transition["next_revision"],
                            "receipt_identity": "mark-unknown-first",
                            "occurred_at": transition["occurred_at"],
                            "ref_s31_id": RESERVATION_2,
                        },
                    )
                    session.update(
                        "S31",
                        {
                            "status": transition["target_status"],
                            "settlement_revision": transition["next_revision"],
                        },
                        {"id": RESERVATION_2, "subject_id": SUBJECT},
                    )
                    session.update(
                        "S27",
                        {"typed_payload": psycopg.types.json.Jsonb({"unknown": True})},
                        {"id": INTENT, "subject_id": SUBJECT},
                    )
                    return {"status": transition["target_status"]}

                return tx.idempotent_outcome(
                    receipt_id=UUID("00000000-0000-8000-8000-000000015577"),
                    actor_scope="subject",
                    client_key="mark-unknown-first",
                    request_hash="mark-unknown-first-hash",
                    mutation=mutation,
                    event=_event(0x15578),
                    expected_transition="DISPATCH_INTENT",
                )

            with psycopg.connect(database_urls["admin"]) as connection:
                execute_command(connection, "MarkUnknown", SUBJECT, operation)
        except BaseException as error:
            errors.append(error)

    stale_errors: list[BaseException] = []

    def stale_settle() -> None:
        try:
            with psycopg.connect(database_urls["admin"]) as connection:
                execute_command(
                    connection,
                    "SettleCall",
                    SUBJECT,
                    lambda tx: (
                        tx.lock_subject(),  # type: ignore[func-returns-value]
                        tx.lock_intents((INTENT,)),  # type: ignore[func-returns-value]
                        tx.lock_reservations(  # type: ignore[func-returns-value]
                            (RESERVATION_2,)
                        ),
                        tx.idempotent_outcome(
                            receipt_id=UUID("00000000-0000-8000-8000-000000015579"),
                            actor_scope="subject",
                            client_key="stale-after-unknown",
                            request_hash="stale-after-unknown-hash",
                            mutation=lambda session: {"unexpected": True},
                            event=_event(0x15580),
                            expected_transition="DISPATCH_INTENT",
                        ),
                    ),
                )
        except BaseException as error:
            stale_errors.append(error)

    first = threading.Thread(target=mark_unknown)
    first.start()
    assert first_has_subject.wait(timeout=5)
    stale = threading.Thread(target=stale_settle)
    stale.start()
    release_first.set()
    first.join(timeout=5)
    stale.join(timeout=5)
    assert not first.is_alive() and not stale.is_alive()
    assert not errors
    assert len(stale_errors) == 1
    assert isinstance(stale_errors[0], GuardRequired)
    assert "expected transition" in str(stale_errors[0])
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT status,settlement_revision FROM kineticloop.call_reservations WHERE id=%s",
            (RESERVATION_2,),
        ).fetchone() == ("OUTCOME_UNKNOWN", 1)


def test_ack_loss_replay_preserves_natural_uniqueness(database_urls: dict[str, str]) -> None:
    receipt = UUID("00000000-0000-8000-8000-000000015302")
    event = _event(0x15303)
    runs = 0
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.planning_intents SET lease_expires_at=clock_timestamp()-interval '1 minute' "
            "WHERE id=%s",
            (INTENT_2,),
        )

    def invoke() -> tuple[Mapping[str, Any], bool]:
        nonlocal runs
        with psycopg.connect(database_urls["admin"]) as connection:
            lease_expires_at = _database_timestamp(connection, offset=timedelta(days=1))

            def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
                tx.lock_subject()
                tx.lock_intents((INTENT_2,))
                tx.require_lease_acquisition_basis(
                    INTENT_2,
                    expected_owner_id="worker-a",
                    expected_fence=7,
                    new_owner_id="worker-ack",
                    new_fence=8,
                    new_lease_expires_at=lease_expires_at,
                    expected_request_revision=1,
                )

                def mutation(session: Any) -> Mapping[str, Any]:
                    nonlocal runs
                    runs += 1
                    session.update(
                        "S27",
                        {
                            "status": "RUNNING",
                            "typed_payload": psycopg.types.json.Jsonb({"committed": True}),
                            "lease_owner": "worker-ack",
                            "fence_token": 8,
                            "lease_expires_at": lease_expires_at,
                        },
                        {"id": INTENT_2, "subject_id": SUBJECT},
                    )
                    return {"intent_id": str(INTENT_2), "status": "COMMITTED"}

                return tx.idempotent_outcome(
                    receipt_id=receipt,
                    actor_scope="subject",
                    client_key="ack-loss",
                    request_hash="ack-loss-hash",
                    mutation=mutation,
                    event=event,
                )

            return execute_command(connection, "AcquireLease", SUBJECT, operation)

    class CommitAcknowledgementLost(ConnectionError):
        pass

    first: Mapping[str, Any]
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(ReplayNotFound):
            replay_outcome(
                connection,
                "AcquireLease",
                SUBJECT,
                actor_scope="subject",
                client_key="ack-loss",
                request_hash="ack-loss-hash",
            )
    with pytest.raises(CommitAcknowledgementLost):
        committed, replayed = invoke()
        assert not replayed
        first = committed
        # The database transaction has committed; only the caller's acknowledgement is lost.
        raise CommitAcknowledgementLost
    with psycopg.connect(database_urls["admin"]) as connection:
        second = replay_outcome(
            connection,
            "AcquireLease",
            SUBJECT,
            actor_scope="subject",
            client_key="ack-loss",
            request_hash="ack-loss-hash",
        )
    assert second == first and runs == 1
    with psycopg.connect(database_urls["admin"]) as connection:
        for table, object_id in (
            ("command_receipts", receipt),
            ("domain_events", event.event_id),
            ("outbox_deliveries", event.outbox_id),
        ):
            assert connection.execute(
                f"SELECT count(*) FROM kineticloop.{table} WHERE id=%s", (object_id,)
            ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.call_reservations WHERE ref_s27_id IN (%s,%s)",
            (INTENT, INTENT_2),
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.planning_intents WHERE id IN (%s,%s)",
            (INTENT, INTENT_2),
        ).fetchone() == (2,)

    # Missing S02 rows are serialized by the T1 natural idempotency key before
    # either contender may admit evidence or publish S03/S04.
    evidence_id = UUID("00000000-0000-8000-8000-000000015809")
    barrier = threading.Barrier(2)
    t1_outcomes: list[tuple[Mapping[str, Any], bool]] = []
    t1_errors: list[BaseException] = []

    def receive(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            with psycopg.connect(database_urls["admin"]) as connection:

                def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
                    def mutation(session: Any) -> Mapping[str, Any]:
                        session.insert(
                            "S09",
                            {
                                "id": evidence_id,
                                "subject_id": SUBJECT,
                                "source_connection_identity": "t1-race",
                                "source_object_type": "TEST",
                                "source_object_identity": "same-object",
                                "source_revision": "1",
                                "trust_class": "TEST_ONLY",
                                "source_class": "TEST",
                                "command_authority": "NONE",
                            },
                        )
                        return {"evidence_id": str(evidence_id)}

                    return tx.idempotent_outcome(
                        receipt_id=UUID(f"00000000-0000-8000-8000-{0x15802 + index:012x}"),
                        actor_scope="subject",
                        client_key=f"different-client-key-{index}",
                        request_hash="same-t1-hash",
                        mutation=mutation,
                        event=_event(0x15803 + index * 2),
                        source_identity_key=f"{SUBJECT}:t1-race:TEST:same-object:1",
                    )

                t1_outcomes.append(
                    execute_command(connection, "ReceiveEvidence", SUBJECT, operation)
                )
        except BaseException as error:
            t1_errors.append(error)

    contenders = [threading.Thread(target=receive, args=(index,)) for index in range(2)]
    for contender in contenders:
        contender.start()
    for contender in contenders:
        contender.join(timeout=5)
    assert len(t1_outcomes) == 1 and not t1_outcomes[0][1]
    assert len(t1_errors) == 1 and isinstance(t1_errors[0], IdempotencyConflict)
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.evidence_revisions WHERE id=%s",
            (evidence_id,),
        ).fetchone() == (1,)


def test_t6_ack_loss_replay_returns_same_issuance(database_urls: dict[str, str]) -> None:
    receipt = UUID("00000000-0000-8000-8000-000000015402")
    event = _event(0x15403)
    runs = 0
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.daily_bundle_revisions"
            "(id,subject_id,local_date,revision_no,generation_mode,ref_s02_id,"
            "ref_s24_id,ref_s27_id,ref_s29_id,ref_s37_id,ref_s38_id) "
            "VALUES (%s,%s,DATE '2026-09-26',1,'AI_GENERATED_CURRENT',%s,%s,%s,%s,%s,%s)",
            (
                OLD_BUNDLE,
                SUBJECT,
                REQUEST_RECEIPT,
                MANIFEST,
                INTENT,
                ATTEMPT,
                VALIDATION,
                DAILY_HEAD,
            ),
        )
        old_prescription_row = connection.execute(
            "SELECT ref_s40_id FROM kineticloop.authorization_issuances WHERE id=%s",
            (UUID(_SAFETY.AUTHORIZATION_ID),),
        ).fetchone()
        assert old_prescription_row is not None
        old_prescription = old_prescription_row[0]
        connection.execute(
            "INSERT INTO kineticloop.bundle_prescription_members"
            "(id,subject_id,member_kind,session_slot,member_order,ref_s39_id,ref_s40_id) "
            "VALUES (%s,%s,'PRESCRIPTION','old-primary',1,%s,%s)",
            (OLD_BUNDLE_MEMBER, SUBJECT, OLD_BUNDLE, old_prescription),
        )
        connection.execute(
            "UPDATE kineticloop.daily_plan_heads "
            "SET head_revision=1,current_bundle_revision_id=%s WHERE id=%s",
            (OLD_BUNDLE, DAILY_HEAD),
        )
        connection.execute(
            "UPDATE kineticloop.planning_intents "
            "SET status='RUNNING',lease_owner='worker-t6',fence_token=9,"
            "lease_expires_at=clock_timestamp()+interval '1 day',"
            "result_bundle_revision_id=NULL,result_authorization_id=NULL WHERE id=%s",
            (INTENT,),
        )
        connection.execute(
            "UPDATE kineticloop.planning_attempts SET status='COMMIT_READY',fence_token=9,"
            "ref_s24_id=%s,captured_epoch=(SELECT authorization_epoch "
            "FROM kineticloop.user_decision_state WHERE subject_id=%s) WHERE id=%s",
            (MANIFEST, SUBJECT, ATTEMPT),
        )
        connection.execute("SET session_replication_role=origin")

    def invoke(
        superseded_authorization: UUID = UUID(_SAFETY.AUTHORIZATION_ID),
        *,
        parent_revision: UUID | None = OLD_BUNDLE,
        include_supersession: bool = True,
        revision_override: int | None = None,
        manifest_override: UUID = MANIFEST,
        authorization_scope: str = "EXECUTION",
    ) -> tuple[Mapping[str, Any], bool]:
        def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
            registry_revision = _acquire_registry(tx)
            tx.lock_intents((INTENT,))
            tx.lock_daily_head(date(2026, 9, 26))
            tx.require_current_fence(
                INTENT,
                owner_id="worker-t6",
                fence=9,
                expected_request_revision=1,
                expected_attempt_id=ATTEMPT,
            )

            def mutation(session: Any) -> Mapping[str, Any]:
                nonlocal runs
                new_revision = revision_override or (1 if parent_revision is None else 2)
                artifact_dependencies = session.authorization_certificate_dependencies()
                closure_digest = session.authorization_closure_digest()
                authorization_valid_from = session.authorization_valid_from()
                closure_valid_until = session.authorization_valid_until()
                dependency_kinds = {item.get("dependency_kind") for item in artifact_dependencies}
                assert {
                    "MANIFEST",
                    "EVIDENCE_RESOLUTION",
                    "VALIDATION_ADMISSION_FRESHNESS",
                    "EVIDENCE_ADMISSION_FRESHNESS",
                    "REQUEST_DEADLINE",
                    "POLICY_TTL",
                    "CALENDAR",
                    "PROJECTION",
                } <= dependency_kinds
                session.insert(
                    "S39",
                    {
                        "id": BUNDLE,
                        "subject_id": SUBJECT,
                        "local_date": date(2026, 9, 26),
                        "revision_no": new_revision,
                        "generation_mode": "AI_GENERATED_CURRENT",
                        "parent_revision_id": parent_revision,
                        "ref_s02_id": receipt,
                        "ref_s24_id": manifest_override,
                        "ref_s27_id": INTENT,
                        "ref_s29_id": ATTEMPT,
                        "ref_s37_id": VALIDATION,
                        "ref_s38_id": DAILY_HEAD,
                    },
                )
                session.insert(
                    "S40",
                    {
                        "id": PRESCRIPTION,
                        "subject_id": SUBJECT,
                        "prescription_identity": "prescription-1",
                        "prescription_kind": "WORKOUT",
                        "prescription_revision": 1,
                        "content_hash": "content",
                        "ref_s34_id": PROPOSAL,
                        "ref_s49_id": ARTIFACT,
                    },
                )
                session.insert(
                    "S41",
                    {
                        "id": BUNDLE_MEMBER,
                        "subject_id": SUBJECT,
                        "member_kind": "PRESCRIPTION",
                        "session_slot": "primary",
                        "member_order": 1,
                        "ref_s39_id": BUNDLE,
                        "ref_s40_id": PRESCRIPTION,
                    },
                )
                session.insert(
                    "S42",
                    {
                        "id": ISSUANCE,
                        "subject_id": SUBJECT,
                        "bound_content_hash": "content",
                        "scope": authorization_scope,
                        "issuance_reason": "AI_PLAN",
                        "artifact_dependency_closure_hash": closure_digest,
                        "registry_revision_at_issue": registry_revision,
                        "valid_from": authorization_valid_from,
                        "valid_until": closure_valid_until,
                        "validity_certificate": psycopg.types.json.Jsonb(
                            {
                                "authorization_epoch": tx.authorization_epoch,
                                "method_version": AUTHORIZATION_METHOD_VERSION,
                                "closure_digest": closure_digest,
                                "dependencies": list(artifact_dependencies),
                            }
                        ),
                        "ref_s02_id": receipt,
                        "ref_s05_id": POLICY,
                        "ref_s24_id": MANIFEST,
                        "ref_s36_id": RESOLUTION,
                        "ref_s37_id": VALIDATION,
                        "ref_s40_id": PRESCRIPTION,
                        "ref_s49_id": ARTIFACT,
                        "registry_state_id": 1,
                    },
                )
                session.insert_authorization_artifact_closure(ISSUANCE, _registry_ids())
                if include_supersession:
                    session.insert(
                        "S43",
                        {
                            "id": SUPERSESSION,
                            "subject_id": SUBJECT,
                            "event_kind": "SUPERSEDED",
                            "scope": "EXECUTION",
                            "causation_key": "t6-ack-loss",
                            "ref_s42_id": superseded_authorization,
                            "ref_s02_id": receipt,
                        },
                    )
                session.update(
                    "S01",
                    {"execution_basis_event_id": event.event_id},
                    {"subject_id": SUBJECT},
                )
                session.update(
                    "S38",
                    {
                        "head_revision": new_revision,
                        "current_bundle_revision_id": BUNDLE,
                    },
                    {"id": DAILY_HEAD, "subject_id": SUBJECT},
                )
                session.update(
                    "S27",
                    {
                        "status": "FOUND_VALID_PLAN",
                        "result_bundle_revision_id": BUNDLE,
                        "result_authorization_id": ISSUANCE,
                    },
                    {"id": INTENT, "subject_id": SUBJECT},
                )
                session.update(
                    "S29",
                    {"status": "COMMITTED", "completed_at": COMPLETION_RECORDED_AT},
                    {"id": ATTEMPT, "subject_id": SUBJECT},
                )
                runs += 1
                return {
                    "receipt_id": str(receipt),
                    "bundle_revision_id": str(BUNDLE),
                    "prescription_id": str(PRESCRIPTION),
                    "bundle_member_id": str(BUNDLE_MEMBER),
                    "authorization_issuance_id": str(ISSUANCE),
                    "supersession_id": str(SUPERSESSION) if include_supersession else None,
                }

            return tx.idempotent_outcome(
                receipt_id=receipt,
                actor_scope="subject",
                client_key="t6-ack-loss",
                request_hash="t6-ack-loss-hash",
                mutation=mutation,
                event=event,
                aggregate_locks={
                    "planning_attempts": (ATTEMPT,),
                    "validation_results": (VALIDATION,),
                },
                authorization_basis={
                    "validation_id": VALIDATION,
                    "resolution_id": RESOLUTION,
                    "intent_id": INTENT,
                    "head_id": DAILY_HEAD,
                },
            )

        with psycopg.connect(database_urls["admin"]) as connection:
            return execute_command(connection, "CommitBundle", SUBJECT, operation)

    class CommitAcknowledgementLost(ConnectionError):
        pass

    first: Mapping[str, Any]
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        manifest_payload_row = connection.execute(
            "SELECT typed_payload FROM kineticloop.decision_manifests WHERE id=%s",
            (MANIFEST,),
        ).fetchone()
        assert manifest_payload_row is not None
        manifest_payload = manifest_payload_row[0]
        incomplete_manifest_payload = dict(manifest_payload)
        incomplete_manifest_payload["artifact_closure_ids"] = [str(ARTIFACT)]
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.decision_manifests SET typed_payload=%s WHERE id=%s",
            (psycopg.types.json.Jsonb(incomplete_manifest_payload), MANIFEST),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(ArtifactIdentityRequired, match="current manifest artifact closure"):
            invoke()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.decision_manifests SET typed_payload=%s WHERE id=%s",
                (psycopg.types.json.Jsonb(manifest_payload), MANIFEST),
            )
            connection.execute("SET session_replication_role=origin")

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.validation_results SET valid_until=clock_timestamp()-interval '1 minute' "
            "WHERE id=%s",
            (VALIDATION,),
        )
        connection.execute("SET session_replication_role=origin")
    with pytest.raises(GuardRequired, match="expired or non-increasing"):
        invoke()
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.validation_results SET valid_until=clock_timestamp()+interval '1 day',"
            "result='FAIL' WHERE id=%s",
            (VALIDATION,),
        )
        connection.execute("SET session_replication_role=origin")
    with pytest.raises(GuardRequired, match="current PASS"):
        invoke()
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.validation_results SET result='PASS' WHERE id=%s",
            (VALIDATION,),
        )
        connection.execute("SET session_replication_role=origin")
    with pytest.raises(GuardRequired, match="prior locked head"):
        invoke(UUID("00000000-0000-8000-8000-000000015942"))
    with pytest.raises(GuardRequired, match="day and revision"):
        invoke(revision_override=99)
    with pytest.raises(GuardRequired, match="current locked manifest"):
        invoke(manifest_override=UUID("00000000-0000-8000-8000-000000015999"))
    with pytest.raises(GuardRequired, match="policy-derived resolution scope"):
        invoke(authorization_scope="CROSSWIRED")
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.prescription_demand_features"
            "(id,subject_id,method_version,feature_hash,basis_hash,ref_s34_id) "
            "VALUES (%s,%s,'v1','feature-crosswire','basis-crosswire',%s)",
            (DEMAND_2, SUBJECT, PROPOSAL),
        )
        connection.execute(
            "UPDATE kineticloop.proposal_revisions SET demand_feature_id=%s WHERE id=%s",
            (DEMAND_2, PROPOSAL),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="policy, demand, and calendar"):
            invoke()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.proposal_revisions SET demand_feature_id=%s WHERE id=%s",
                (DEMAND, PROPOSAL),
            )
            connection.execute(
                "DELETE FROM kineticloop.prescription_demand_features WHERE id=%s",
                (DEMAND_2,),
            )
            connection.execute("SET session_replication_role=origin")

    def partial_commit(tx: RepositoryTransaction) -> None:
        _acquire_registry(tx)
        tx.lock_intents((INTENT,))
        tx.lock_daily_head(date(2026, 9, 26))
        tx.require_current_fence(
            INTENT,
            owner_id="worker-t6",
            fence=9,
            expected_request_revision=1,
            expected_attempt_id=ATTEMPT,
        )
        tx.idempotent_outcome(
            receipt_id=UUID("00000000-0000-8000-8000-000000015952"),
            actor_scope="subject",
            client_key="partial-t6",
            request_hash="partial-t6-hash",
            mutation=lambda session: {"partial": True},
            event=_event(0x15953),
            aggregate_locks={
                "planning_attempts": (ATTEMPT,),
                "validation_results": (VALIDATION,),
            },
            authorization_basis={
                "validation_id": VALIDATION,
                "resolution_id": RESOLUTION,
                "intent_id": INTENT,
                "head_id": DAILY_HEAD,
            },
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="exactly one S39"):
            execute_command(connection, "CommitBundle", SUBJECT, partial_commit)

    with pytest.raises(CommitAcknowledgementLost):
        committed, replayed = invoke()
        assert not replayed
        first = committed
        raise CommitAcknowledgementLost
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        prior_valid_until_row = connection.execute(
            "SELECT valid_until FROM kineticloop.safety_artifacts WHERE id=%s",
            (ARTIFACT,),
        ).fetchone()
        assert prior_valid_until_row is not None
        prior_valid_until = prior_valid_until_row[0]
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.safety_artifacts SET valid_until=clock_timestamp()-interval '1 minute' "
            "WHERE id=%s",
            (ARTIFACT,),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with psycopg.connect(database_urls["admin"]) as connection:
            second = replay_outcome(
                connection,
                "CommitBundle",
                SUBJECT,
                actor_scope="subject",
                client_key="t6-ack-loss",
                request_hash="t6-ack-loss-hash",
            )
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.safety_artifacts SET valid_until=%s WHERE id=%s",
                (prior_valid_until, ARTIFACT),
            )
            connection.execute("SET session_replication_role=origin")
    assert second == first and runs == 1
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.daily_bundle_revisions WHERE id=%s", (BUNDLE,)
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.authorization_issuances WHERE id=%s", (ISSUANCE,)
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.prescription_revisions WHERE id=%s",
            (PRESCRIPTION,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.bundle_prescription_members WHERE id=%s",
            (BUNDLE_MEMBER,),
        ).fetchone() == (1,)
        for table, object_id in (
            ("command_receipts", receipt),
            ("domain_events", event.event_id),
            ("outbox_deliveries", event.outbox_id),
        ):
            assert connection.execute(
                f"SELECT count(*) FROM kineticloop.{table} WHERE id=%s", (object_id,)
            ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.authorization_events WHERE id=%s",
            (SUPERSESSION,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT execution_basis_event_id FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone() == (event.event_id,)
        assert connection.execute(
            "SELECT typed_payload->>'parent_revision_id' FROM kineticloop.daily_bundle_revisions "
            "WHERE id=%s",
            (BUNDLE,),
        ).fetchone() == (str(OLD_BUNDLE),)
        assert {
            row[0]
            for row in connection.execute(
                "SELECT artifact_id FROM kineticloop.authorization_artifact_closure "
                "WHERE authorization_id=%s",
                (ISSUANCE,),
            ).fetchall()
        } == set(_registry_ids())
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.bundle_prescription_members old_member "
            "JOIN kineticloop.authorization_issuances old_auth "
            "ON old_auth.subject_id=old_member.subject_id "
            "AND old_auth.ref_s40_id=old_member.ref_s40_id "
            "JOIN kineticloop.authorization_events supersession "
            "ON supersession.subject_id=old_auth.subject_id "
            "AND supersession.ref_s42_id=old_auth.id "
            "WHERE old_member.ref_s39_id=%s AND supersession.id=%s",
            (OLD_BUNDLE, SUPERSESSION),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT head_revision,current_bundle_revision_id "
            "FROM kineticloop.daily_plan_heads WHERE id=%s",
            (DAILY_HEAD,),
        ).fetchone() == (2, BUNDLE)
        assert connection.execute(
            "SELECT status,result_bundle_revision_id,result_authorization_id "
            "FROM kineticloop.planning_intents WHERE id=%s",
            (INTENT,),
        ).fetchone() == ("FOUND_VALID_PLAN", BUNDLE, ISSUANCE)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.call_reservations WHERE id IN (%s,%s)",
            (RESERVATION, RESERVATION_2),
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT status,completed_at FROM kineticloop.planning_attempts WHERE id=%s",
            (ATTEMPT,),
        ).fetchone() == ("COMMITTED", COMPLETION_RECORDED_AT)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.daily_bundle_revisions WHERE id IN (%s,%s)",
            (OLD_BUNDLE, BUNDLE),
        ).fetchone() == (2,)

    # The same complete T6 path must also install the first-ever head without
    # fabricating a parent or supersession event.
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "DELETE FROM kineticloop.authorization_artifact_closure WHERE authorization_id=%s",
            (ISSUANCE,),
        )
        for table, object_id in (
            ("authorization_events", SUPERSESSION),
            ("authorization_issuances", ISSUANCE),
            ("bundle_prescription_members", BUNDLE_MEMBER),
            ("prescription_revisions", PRESCRIPTION),
            ("daily_bundle_revisions", BUNDLE),
            ("outbox_deliveries", event.outbox_id),
            ("domain_events", event.event_id),
            ("command_receipts", receipt),
            ("bundle_prescription_members", OLD_BUNDLE_MEMBER),
            ("daily_bundle_revisions", OLD_BUNDLE),
        ):
            connection.execute(f"DELETE FROM kineticloop.{table} WHERE id=%s", (object_id,))
        connection.execute(
            "UPDATE kineticloop.daily_plan_heads SET head_revision=0,"
            "current_bundle_revision_id=NULL WHERE id=%s",
            (DAILY_HEAD,),
        )
        connection.execute(
            "UPDATE kineticloop.user_decision_state SET execution_basis_event_id=NULL "
            "WHERE subject_id=%s",
            (SUBJECT,),
        )
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',lease_owner='worker-t6',"
            "fence_token=9,lease_expires_at=clock_timestamp()+interval '1 day',"
            "result_bundle_revision_id=NULL,result_authorization_id=NULL WHERE id=%s",
            (INTENT,),
        )
        connection.execute(
            "UPDATE kineticloop.planning_attempts SET status='COMMIT_READY',completed_at=NULL "
            "WHERE id=%s",
            (ATTEMPT,),
        )
        connection.execute("SET session_replication_role=origin")

    initial, initial_replayed = invoke(parent_revision=None, include_supersession=False)
    assert not initial_replayed and initial["supersession_id"] is None and runs == 2
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT typed_payload->'parent_revision_id' FROM kineticloop.daily_bundle_revisions "
            "WHERE id=%s",
            (BUNDLE,),
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.authorization_events WHERE id=%s",
            (SUPERSESSION,),
        ).fetchone() == (0,)


def test_reauthorize_requires_atomic_intent_success(database_urls: dict[str, str]) -> None:
    issuance = UUID("00000000-0000-8000-8000-000000015742")
    receipt = UUID("00000000-0000-8000-8000-000000015743")
    foreign_policy = UUID("00000000-0000-8000-8000-000000015749")
    event = _event(0x15744)
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        execution_basis_row = connection.execute(
            "SELECT execution_basis_event_id FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone()
        assert execution_basis_row is not None
        execution_basis = execution_basis_row[0]
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',"
            "lease_owner='worker-reauth',fence_token=11,"
            "lease_expires_at=clock_timestamp()+interval '1 day',"
            "result_authorization_id=NULL WHERE id=%s",
            (INTENT,),
        )
        connection.execute(
            "UPDATE kineticloop.planning_attempts SET status='COMMIT_READY',fence_token=11,"
            "completed_at=NULL,captured_epoch=(SELECT authorization_epoch "
            "FROM kineticloop.user_decision_state WHERE subject_id=%s) WHERE id=%s",
            (SUBJECT, ATTEMPT),
        )
        connection.execute(
            "UPDATE kineticloop.validation_results SET result='PASS',"
            "valid_until=clock_timestamp()+interval '1 day',ref_s03_id=%s WHERE id=%s",
            (execution_basis, VALIDATION),
        )
        connection.execute("SET session_replication_role=origin")

    def invoke(status: str) -> tuple[Mapping[str, Any], bool]:
        def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
            registry_revision = _acquire_registry(tx)
            tx.lock_intents((INTENT,))
            tx.lock_daily_head(date(2026, 9, 26))
            tx.require_current_fence(
                INTENT,
                owner_id="worker-reauth",
                fence=11,
                expected_request_revision=1,
                expected_attempt_id=ATTEMPT,
            )

            def mutation(session: Any) -> Mapping[str, Any]:
                dependencies = session.authorization_certificate_dependencies()
                closure_digest = session.authorization_closure_digest()
                session.insert(
                    "S42",
                    {
                        "id": issuance,
                        "subject_id": SUBJECT,
                        "bound_content_hash": "content",
                        "scope": "EXECUTION",
                        "issuance_reason": "REVALIDATION",
                        "artifact_dependency_closure_hash": closure_digest,
                        "registry_revision_at_issue": registry_revision,
                        "valid_from": session.authorization_valid_from(),
                        "valid_until": session.authorization_valid_until(),
                        "validity_certificate": psycopg.types.json.Jsonb(
                            {
                                "authorization_epoch": tx.authorization_epoch,
                                "method_version": AUTHORIZATION_METHOD_VERSION,
                                "closure_digest": closure_digest,
                                "dependencies": list(dependencies),
                            }
                        ),
                        "ref_s02_id": receipt,
                        "ref_s05_id": POLICY,
                        "ref_s24_id": MANIFEST,
                        "ref_s36_id": RESOLUTION,
                        "ref_s37_id": VALIDATION,
                        "ref_s40_id": PRESCRIPTION,
                        "ref_s49_id": ARTIFACT,
                        "registry_state_id": 1,
                    },
                )
                session.insert_authorization_artifact_closure(issuance, _registry_ids())
                session.update(
                    "S01",
                    {"execution_basis_event_id": event.event_id},
                    {"subject_id": SUBJECT},
                )
                session.update(
                    "S27",
                    {"status": status, "result_authorization_id": issuance},
                    {"id": INTENT, "subject_id": SUBJECT},
                )
                session.update(
                    "S29",
                    {"status": "COMMITTED", "completed_at": COMPLETION_RECORDED_AT},
                    {"id": ATTEMPT, "subject_id": SUBJECT},
                )
                return {"authorization_id": str(issuance)}

            return tx.idempotent_outcome(
                receipt_id=receipt,
                actor_scope="subject",
                client_key="reauthorize-intent-success",
                request_hash="reauthorize-intent-success-hash",
                mutation=mutation,
                event=event,
                aggregate_locks={
                    "planning_attempts": (ATTEMPT,),
                    "validation_results": (VALIDATION,),
                },
                authorization_basis={
                    "validation_id": VALIDATION,
                    "resolution_id": RESOLUTION,
                    "intent_id": INTENT,
                    "head_id": DAILY_HEAD,
                },
            )

        with psycopg.connect(database_urls["admin"]) as connection:
            return execute_command(connection, "Reauthorize", SUBJECT, operation)

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.policy_bundles"
            "(id,subject_id,policy_namespace,policy_version,content_hash) "
            "VALUES (%s,%s,'kl015-cross-policy','1','cross-policy') "
            "ON CONFLICT (id) DO NOTHING",
            (foreign_policy, SUBJECT),
        )
        connection.execute(
            "UPDATE kineticloop.evidence_resolutions SET ref_s05_id=%s WHERE id=%s",
            (foreign_policy, RESOLUTION),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="current PASS validation basis"):
            invoke("FOUND_VALID_PLAN")
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.evidence_resolutions SET ref_s05_id=%s WHERE id=%s",
                (POLICY, RESOLUTION),
            )
            connection.execute("SET session_replication_role=origin")

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.planning_intents SET local_date=DATE '2026-09-28' WHERE id=%s",
            (INTENT,),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="head day"):
            invoke("FOUND_VALID_PLAN")
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.planning_intents SET local_date=DATE '2026-09-26' WHERE id=%s",
                (INTENT,),
            )
            connection.execute("SET session_replication_role=origin")

    with pytest.raises(GuardRequired, match="mandatory S27 update"):
        invoke("RUNNING")
    outcome, replayed = invoke("FOUND_VALID_PLAN")
    assert not replayed and outcome["authorization_id"] == str(issuance)
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT status,result_authorization_id FROM kineticloop.planning_intents WHERE id=%s",
            (INTENT,),
        ).fetchone() == ("FOUND_VALID_PLAN", issuance)


def test_t3_rejects_incomplete_or_crosswired_ready_candidate(
    database_urls: dict[str, str],
) -> None:
    def attempt() -> None:
        def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
            _acquire_registry(tx)
            return tx.idempotent_outcome(
                receipt_id=UUID("00000000-0000-8000-8000-000000015810"),
                actor_scope="subject",
                client_key="invalid-ready-candidate",
                request_hash="invalid-ready-candidate-hash",
                mutation=lambda session: {"unexpected": True},
                event=_event(0x15811),
                aggregate_locks={"manifest_builds": (MANIFEST_BUILD,)},
            )

        with psycopg.connect(database_urls["admin"]) as connection:
            execute_command(connection, "PublishManifest", SUBJECT, operation)

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "DELETE FROM kineticloop.projection_dependencies WHERE ref_s21_id=%s",
            (PROJECTION,),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="dependency basis is incomplete"):
            attempt()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "INSERT INTO kineticloop.projection_dependencies"
                "(id,subject_id,dependency_kind,dependency_semantic_key,collection_signature,"
                "ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id) VALUES "
                "(%s,%s,'FACTSET','current-factset',NULL,NULL,NULL,%s,%s),"
                "(%s,%s,'COLLECTION','admitted-facts','all-admitted-v1',NULL,NULL,%s,%s),"
                "(%s,%s,'POLICY','active-policy',NULL,%s,NULL,NULL,%s),"
                "(%s,%s,'PROGRAM','active-program',NULL,NULL,%s,NULL,%s),"
                "(%s,%s,'ENGINE','exposure-engine:v1',NULL,NULL,NULL,NULL,%s)",
                (
                    PROJECTION_DEPENDENCY,
                    SUBJECT,
                    FACTSET,
                    PROJECTION,
                    PROJECTION_COLLECTION_DEPENDENCY,
                    SUBJECT,
                    FACTSET,
                    PROJECTION,
                    PROJECTION_POLICY_DEPENDENCY,
                    SUBJECT,
                    POLICY,
                    PROJECTION,
                    PROJECTION_PROGRAM_DEPENDENCY,
                    SUBJECT,
                    POLICY,
                    PROJECTION,
                    PROJECTION_ENGINE_DEPENDENCY,
                    SUBJECT,
                    PROJECTION,
                ),
            )
            payload_row = connection.execute(
                "SELECT typed_payload FROM kineticloop.manifest_builds WHERE id=%s",
                (MANIFEST_BUILD,),
            ).fetchone()
            assert payload_row is not None
            payload = payload_row[0]
            wrong_payload = dict(payload)
            wrong_payload["artifact_closure_ids"] = [str(ARTIFACT)]
            connection.execute(
                "UPDATE kineticloop.manifest_builds SET typed_payload=%s WHERE id=%s",
                (psycopg.types.json.Jsonb(wrong_payload), MANIFEST_BUILD),
            )
            connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="verified full closure"):
            attempt()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.manifest_builds SET typed_payload=%s WHERE id=%s",
                (psycopg.types.json.Jsonb(payload), MANIFEST_BUILD),
            )
            connection.execute("SET session_replication_role=origin")

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.projection_dependencies SET ref_s05_id=NULL "
            "WHERE id=%s",
            (PROJECTION_POLICY_DEPENDENCY,),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="dependency basis is incomplete"):
            attempt()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.projection_dependencies SET ref_s05_id=%s "
                "WHERE id=%s",
                (POLICY, PROJECTION_POLICY_DEPENDENCY),
            )
            connection.execute("SET session_replication_role=origin")

    # A registered S48 artifact is not activated merely because the caller adds
    # it to the candidate closure. It must remain reachable from the artifact
    # bound to the active S05 policy.
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "DELETE FROM kineticloop.safety_artifact_dependencies "
            "WHERE artifact_id=%s AND dependency_artifact_id=%s",
            (ARTIFACT, DEPENDENCY),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(
            GuardRequired, match="verified full closure|activated policy/release basis"
        ):
            attempt()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "INSERT INTO kineticloop.safety_artifact_dependencies"
                "(artifact_id,dependency_artifact_id) VALUES (%s,%s) "
                "ON CONFLICT DO NOTHING",
                (ARTIFACT, DEPENDENCY),
            )
            connection.execute("SET session_replication_role=origin")

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        extra_root_payload = dict(payload)
        extra_root_payload["artifact_root_ids"] = [str(ARTIFACT), str(DEPENDENCY)]
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.manifest_builds SET typed_payload=%s WHERE id=%s",
            (psycopg.types.json.Jsonb(extra_root_payload), MANIFEST_BUILD),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="activated policy/release basis"):
            attempt()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.manifest_builds SET typed_payload=%s WHERE id=%s",
                (psycopg.types.json.Jsonb(payload), MANIFEST_BUILD),
            )
            connection.execute("SET session_replication_role=origin")

    catalog = UUID("00000000-0000-8000-8000-000000015819")
    mapping = UUID("00000000-0000-8000-8000-000000015820")
    catalog_dependency = UUID("00000000-0000-8000-8000-000000015821")
    mapping_dependency = UUID("00000000-0000-8000-8000-000000015822")
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        selected_policy_payload_row = connection.execute(
            "SELECT typed_payload FROM kineticloop.policy_bundles WHERE id=%s",
            (POLICY,),
        ).fetchone()
        assert selected_policy_payload_row is not None
        selected_policy_payload = selected_policy_payload_row[0]
        catalog_policy_payload = dict(selected_policy_payload)
        exposure = dict(
            selected_policy_payload["manifest_projection_requirements"]["EXPOSURE"]
        )
        exposure["dependencies"] = [
            *exposure["dependencies"],
            {"kind": "CATALOG", "key": "selected-catalog", "collection": None},
            {"kind": "MAPPING", "key": "selected-mapping", "collection": None},
        ]
        catalog_policy_payload["manifest_projection_requirements"] = {"EXPOSURE": exposure}
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.exercise_catalog_revisions"
            "(id,subject_id,catalog_namespace,exercise_identity,catalog_revision) "
            "VALUES (%s,%s,'kl015','exercise',1)",
            (catalog, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.exercise_mapping_decisions"
            "(id,subject_id,mapping_family_identity,source_exercise_identity,mapping_scope,"
            "ref_s19_id) VALUES (%s,%s,'kl015-map','exercise','SUBJECT',%s)",
            (mapping, SUBJECT, catalog),
        )
        connection.execute(
            "UPDATE kineticloop.factset_revisions SET ref_s20_id=%s WHERE id=%s",
            (mapping, FACTSET),
        )
        connection.execute(
            "INSERT INTO kineticloop.projection_dependencies"
            "(id,subject_id,dependency_kind,dependency_semantic_key,ref_s19_id,ref_s21_id) "
            "VALUES (%s,%s,'CATALOG','selected-catalog',%s,%s)",
            (catalog_dependency, SUBJECT, catalog, PROJECTION),
        )
        connection.execute(
            "INSERT INTO kineticloop.projection_dependencies"
            "(id,subject_id,dependency_kind,dependency_semantic_key,ref_s20_id,ref_s21_id) "
            "VALUES (%s,%s,'MAPPING','selected-mapping',%s,%s)",
            (mapping_dependency, SUBJECT, mapping, PROJECTION),
        )
        connection.execute(
            "UPDATE kineticloop.policy_bundles SET typed_payload=%s WHERE id=%s",
            (psycopg.types.json.Jsonb(catalog_policy_payload), POLICY),
        )
        rows = connection.execute(
            "SELECT dependency_kind,dependency_semantic_key,collection_signature,"
            "ref_s05_id,ref_s06_id,ref_s14_id,ref_s15_id,ref_s19_id,ref_s20_id "
            "FROM kineticloop.projection_dependencies WHERE ref_s21_id=%s "
            "ORDER BY dependency_kind,dependency_semantic_key,id",
            (PROJECTION,),
        ).fetchall()
        catalog_dependencies = [
            {
                "projection_id": str(PROJECTION),
                "kind": row[0],
                "key": row[1],
                "collection": row[2],
                "policy": str(row[3]) if row[3] else None,
                "program": str(row[4]) if row[4] else None,
                "fact": str(row[5]) if row[5] else None,
                "factset": str(row[6]) if row[6] else None,
                "catalog": str(row[7]) if row[7] else None,
                "mapping": str(row[8]) if row[8] else None,
            }
            for row in rows
        ]
        catalog_basis = {
            "projections": [
                {
                    "id": str(PROJECTION),
                    "role": "EXPOSURE",
                    "projection_kind": "EXPOSURE",
                    "validated_basis_hash": "projection-basis",
                    "dependencies": catalog_dependencies,
                }
            ],
            "catalog_id": str(catalog),
            "mapping_id": str(mapping),
        }
        catalog_candidate = dict(payload)
        catalog_candidate["dependency_basis_hash"] = hashlib.sha256(
            json.dumps(catalog_basis, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        connection.execute(
            "UPDATE kineticloop.manifest_builds SET typed_payload=%s WHERE id=%s",
            (psycopg.types.json.Jsonb(catalog_candidate), MANIFEST_BUILD),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="activated policy/release basis"):
            attempt()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.manifest_builds SET typed_payload=%s WHERE id=%s",
                (psycopg.types.json.Jsonb(payload), MANIFEST_BUILD),
            )
            connection.execute(
                "UPDATE kineticloop.policy_bundles SET typed_payload=%s WHERE id=%s",
                (psycopg.types.json.Jsonb(selected_policy_payload), POLICY),
            )
            connection.execute(
                "UPDATE kineticloop.factset_revisions SET ref_s20_id=NULL WHERE id=%s",
                (FACTSET,),
            )
            connection.execute(
                "DELETE FROM kineticloop.projection_dependencies WHERE id=ANY(%s)",
                ([catalog_dependency, mapping_dependency],),
            )
            connection.execute(
                "DELETE FROM kineticloop.exercise_mapping_decisions WHERE id=%s",
                (mapping,),
            )
            connection.execute(
                "DELETE FROM kineticloop.exercise_catalog_revisions WHERE id=%s",
                (catalog,),
            )
            connection.execute("SET session_replication_role=origin")

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        policy_payload_row = connection.execute(
            "SELECT typed_payload FROM kineticloop.policy_bundles WHERE id=%s",
            (POLICY,),
        ).fetchone()
        assert policy_payload_row is not None
        policy_payload = policy_payload_row[0]
        extra_role_policy = dict(policy_payload)
        extra_role_policy["manifest_projection_requirements"] = {
            **policy_payload["manifest_projection_requirements"],
            "RECOVERY": {
                "projection_kind": "RECOVERY",
                "dependencies": policy_payload["manifest_projection_requirements"]["EXPOSURE"][
                    "dependencies"
                ],
            },
        }
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.policy_bundles SET typed_payload=%s WHERE id=%s",
            (psycopg.types.json.Jsonb(extra_role_policy), POLICY),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="active-policy requirements"):
            attempt()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.policy_bundles SET typed_payload=%s WHERE id=%s",
                (psycopg.types.json.Jsonb(policy_payload), POLICY),
            )
            connection.execute("SET session_replication_role=origin")

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        fact_policy = dict(policy_payload)
        exposure_requirement = dict(
            policy_payload["manifest_projection_requirements"]["EXPOSURE"]
        )
        exposure_requirement["dependencies"] = [
            *exposure_requirement["dependencies"],
            {"kind": "FACT", "key": "outside-fact", "collection": None},
        ]
        fact_policy["manifest_projection_requirements"] = {
            "EXPOSURE": exposure_requirement
        }
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.evidence_revisions"
            "(id,subject_id,source_connection_identity,source_object_type,"
            "source_object_identity,source_revision,trust_class,source_class,command_authority) "
            "VALUES (%s,%s,'outside','TEST','outside','1','SOURCE_REPORTED','TEST','NONE')",
            (OUTSIDE_EVIDENCE, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.candidate_assertions"
            "(id,subject_id,assertion_family_identity,predicate,value_state,ref_s09_id) "
            "VALUES (%s,%s,'outside','outside','KNOWN',%s)",
            (OUTSIDE_CANDIDATE, SUBJECT, OUTSIDE_EVIDENCE),
        )
        connection.execute(
            "INSERT INTO kineticloop.underlying_events"
            "(id,subject_id,event_identity,event_kind) VALUES (%s,%s,'outside','ACTUAL')",
            (OUTSIDE_EVENT, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.admission_decisions"
            "(id,subject_id,action_scope,decision,ref_s05_id,ref_s09_id,ref_s10_id) "
            "VALUES (%s,%s,'EXECUTION','ELIGIBLE',%s,%s,%s)",
            (OUTSIDE_ADMISSION, SUBJECT, POLICY, OUTSIDE_EVIDENCE, OUTSIDE_CANDIDATE),
        )
        connection.execute(
            "INSERT INTO kineticloop.canonical_fact_revisions"
            "(id,subject_id,stable_fact_identity,fact_kind,fact_revision,ref_s10_id,"
            "ref_s11_id,ref_s13_id) VALUES (%s,%s,'outside-fact','ACTUAL',1,%s,%s,%s)",
            (OUTSIDE_FACT, SUBJECT, OUTSIDE_CANDIDATE, OUTSIDE_EVENT, OUTSIDE_ADMISSION),
        )
        connection.execute(
            "INSERT INTO kineticloop.projection_dependencies"
            "(id,subject_id,dependency_kind,dependency_semantic_key,ref_s14_id,ref_s21_id) "
            "VALUES (%s,%s,'FACT','outside-fact',%s,%s)",
            (PROJECTION_OUTSIDE_FACT_DEPENDENCY, SUBJECT, OUTSIDE_FACT, PROJECTION),
        )
        connection.execute(
            "UPDATE kineticloop.policy_bundles SET typed_payload=%s WHERE id=%s",
            (psycopg.types.json.Jsonb(fact_policy), POLICY),
        )
        connection.execute("SET session_replication_role=origin")
    try:
        with pytest.raises(GuardRequired, match="dependency basis is incomplete"):
            attempt()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "DELETE FROM kineticloop.projection_dependencies WHERE id=%s",
                (PROJECTION_OUTSIDE_FACT_DEPENDENCY,),
            )
            connection.execute(
                "DELETE FROM kineticloop.canonical_fact_revisions WHERE id=%s",
                (OUTSIDE_FACT,),
            )
            connection.execute(
                "DELETE FROM kineticloop.admission_decisions WHERE id=%s",
                (OUTSIDE_ADMISSION,),
            )
            connection.execute(
                "DELETE FROM kineticloop.candidate_assertions WHERE id=%s",
                (OUTSIDE_CANDIDATE,),
            )
            connection.execute(
                "DELETE FROM kineticloop.underlying_events WHERE id=%s",
                (OUTSIDE_EVENT,),
            )
            connection.execute(
                "DELETE FROM kineticloop.evidence_revisions WHERE id=%s",
                (OUTSIDE_EVIDENCE,),
            )
            connection.execute(
                "UPDATE kineticloop.policy_bundles SET typed_payload=%s WHERE id=%s",
                (psycopg.types.json.Jsonb(policy_payload), POLICY),
            )
            connection.execute("SET session_replication_role=origin")


def test_t7_exact_session_and_t3_publication_guards(database_urls: dict[str, str]) -> None:
    authorization_id = UUID(_SAFETY.AUTHORIZATION_ID)
    alternate_prescription = UUID("00000000-0000-8000-8000-000000015901")
    alternate_authorization = UUID("00000000-0000-8000-8000-000000015902")
    alternate_member = UUID("00000000-0000-8000-8000-000000015903")
    t7_bundle = UUID("00000000-0000-8000-8000-000000015839")
    t7_member = UUID("00000000-0000-8000-8000-000000015841")
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        authorization = connection.execute(
            "SELECT ref_s40_id,bound_content_hash FROM kineticloop.authorization_issuances "
            "WHERE id=%s",
            (authorization_id,),
        ).fetchone()
        assert authorization is not None
        prescription_id, content_hash = authorization
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.prescription_revisions"
            "(id,subject_id,prescription_identity,prescription_kind,prescription_revision,"
            "content_hash,ref_s34_id,ref_s49_id) "
            "VALUES (%s,%s,'t7-seed','WORKOUT',1,%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (prescription_id, SUBJECT, content_hash, PROPOSAL, ARTIFACT),
        )
        connection.execute(
            "INSERT INTO kineticloop.daily_bundle_revisions"
            "(id,subject_id,local_date,revision_no,generation_mode,ref_s02_id,ref_s24_id,"
            "ref_s27_id,ref_s29_id,ref_s37_id,ref_s38_id) "
            "VALUES (%s,%s,DATE '2026-09-26',99,'T7_SEED',%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (id) DO NOTHING",
            (
                t7_bundle,
                SUBJECT,
                UUID("00000000-0000-8000-8000-000000015838"),
                MANIFEST,
                INTENT,
                ATTEMPT,
                VALIDATION,
                DAILY_HEAD,
            ),
        )
        connection.execute(
            "INSERT INTO kineticloop.bundle_prescription_members"
            "(id,subject_id,member_kind,session_slot,member_order,ref_s39_id,ref_s40_id) "
            "VALUES (%s,%s,'PRESCRIPTION','t7',1,%s,%s) ON CONFLICT (id) DO NOTHING",
            (t7_member, SUBJECT, t7_bundle, prescription_id),
        )
        connection.execute(
            "INSERT INTO kineticloop.prescription_revisions"
            "(id,subject_id,prescription_identity,prescription_kind,prescription_revision,"
            "content_hash,ref_s34_id,ref_s49_id) "
            "VALUES (%s,%s,'t7-alternate','WORKOUT',1,%s,%s,%s)",
            (alternate_prescription, SUBJECT, content_hash, PROPOSAL, ARTIFACT),
        )
        connection.execute(
            "INSERT INTO kineticloop.bundle_prescription_members"
            "(id,subject_id,member_kind,session_slot,member_order,ref_s39_id,ref_s40_id) "
            "VALUES (%s,%s,'PRESCRIPTION','t7-alternate',2,%s,%s)",
            (alternate_member, SUBJECT, t7_bundle, alternate_prescription),
        )
        connection.execute(
            "INSERT INTO kineticloop.authorization_issuances("
            "id,subject_id,bound_content_hash,scope,artifact_dependency_closure_hash,"
            "registry_revision_at_issue,valid_from,valid_until,validity_certificate,"
            "ref_s02_id,ref_s05_id,ref_s24_id,ref_s36_id,ref_s37_id,ref_s40_id,"
            "ref_s49_id,registry_state_id) "
            "SELECT %s,subject_id,bound_content_hash,scope,artifact_dependency_closure_hash,"
            "registry_revision_at_issue,valid_from,valid_until,validity_certificate,"
            "ref_s02_id,ref_s05_id,ref_s24_id,ref_s36_id,ref_s37_id,%s,"
            "ref_s49_id,registry_state_id FROM kineticloop.authorization_issuances WHERE id=%s",
            (alternate_authorization, alternate_prescription, authorization_id),
        )
        connection.execute(
            "INSERT INTO kineticloop.authorization_artifact_closure"
            "(subject_id,authorization_id,artifact_id,artifact_revision,valid_from,valid_until) "
            "SELECT subject_id,%s,artifact_id,artifact_revision,valid_from,valid_until "
            "FROM kineticloop.authorization_artifact_closure WHERE authorization_id=%s",
            (alternate_authorization, authorization_id),
        )
        connection.execute(
            "UPDATE kineticloop.daily_plan_heads SET current_bundle_revision_id=%s WHERE id=%s",
            (t7_bundle, DAILY_HEAD),
        )
        connection.execute("SET session_replication_role=origin")
    binding = UUID("00000000-0000-8000-8000-000000015845")
    start_receipt = UUID("00000000-0000-8000-8000-000000015846")
    start_event = _event(0x15847)

    def start(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        _acquire_registry(tx)
        tx.lock_daily_head(date(2026, 9, 26))
        tx.lock_execution((SESSION,))
        tx.require_execution_authorization(
            prescription_id=prescription_id,
            authorization_id=authorization_id,
            execution_scope="EXECUTION",
        )

        def mutation(session: Any) -> Mapping[str, Any]:
            session.insert(
                "S45",
                {
                    "id": binding,
                    "subject_id": SUBJECT,
                    "binding_kind": "START",
                    "binding_revision": session.execution_binding_revision(),
                    "accepted_at": session.execution_binding_accepted_at(),
                    "execution_scope": "EXECUTION",
                    "ref_s02_id": start_receipt,
                    "ref_s40_id": prescription_id,
                    "ref_s42_id": authorization_id,
                    "ref_s44_id": SESSION,
                },
            )
            session.update(
                "S44",
                {"lifecycle": "IN_PROGRESS", "execution_revision": 1},
                {"id": SESSION, "subject_id": SUBJECT},
            )
            session.update(
                "S01",
                {"execution_basis_event_id": start_event.event_id},
                {"subject_id": SUBJECT},
            )
            return {"binding_id": str(binding)}

        return tx.idempotent_outcome(
            receipt_id=start_receipt,
            actor_scope="subject",
            client_key="exact-t7-start",
            request_hash="exact-t7-start-hash",
            mutation=mutation,
            event=start_event,
        )

    def crosswired_start(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        _acquire_registry(tx)
        tx.lock_daily_head(date(2026, 9, 26))
        tx.lock_execution((SESSION,))
        tx.require_execution_authorization(
            prescription_id=prescription_id,
            authorization_id=authorization_id,
            execution_scope="EXECUTION",
        )

        def mutation(session: Any) -> Mapping[str, Any]:
            session.insert(
                "S45",
                {
                    "id": UUID("00000000-0000-8000-8000-000000015855"),
                    "subject_id": SUBJECT,
                    "binding_kind": "START",
                    "binding_revision": session.execution_binding_revision(),
                    "accepted_at": session.execution_binding_accepted_at(),
                    "execution_scope": "WRONG_SCOPE",
                    "ref_s02_id": UUID("00000000-0000-8000-8000-000000015856"),
                    "ref_s40_id": prescription_id,
                    "ref_s42_id": authorization_id,
                    "ref_s44_id": SESSION,
                },
            )
            return {"unexpected": True}

        return tx.idempotent_outcome(
            receipt_id=UUID("00000000-0000-8000-8000-000000015856"),
            actor_scope="subject",
            client_key="crosswired-t7-scope",
            request_hash="crosswired-t7-scope-hash",
            mutation=mutation,
            event=_event(0x15857),
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="scope, time, and revision"):
            execute_command(connection, "StartSession", SUBJECT, crosswired_start)

    with psycopg.connect(database_urls["admin"]) as connection:
        outcome, replayed = execute_command(connection, "StartSession", SUBJECT, start)
    assert not replayed and outcome["binding_id"] == str(binding)

    def substituted_continue(tx: RepositoryTransaction) -> None:
        _acquire_registry(tx)
        tx.lock_daily_head(date(2026, 9, 26))
        tx.lock_execution((SESSION,))
        tx.require_execution_authorization(
            prescription_id=alternate_prescription,
            authorization_id=alternate_authorization,
            execution_scope="EXECUTION",
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="SESSION_RELATION_INELIGIBLE"):
            execute_command(
                connection,
                "ContinueSession",
                SUBJECT,
                substituted_continue,
            )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="lifecycle or repeated START"):
            execute_command(
                connection,
                "StartSession",
                SUBJECT,
                lambda tx: (
                    _acquire_registry(tx),
                    tx.lock_daily_head(  # type: ignore[func-returns-value]
                        date(2026, 9, 26)
                    ),
                    tx.lock_execution((SESSION,)),  # type: ignore[func-returns-value]
                ),
            )

    manifest = UUID("00000000-0000-8000-8000-000000015824")
    manifest_binding = UUID("00000000-0000-8000-8000-000000015825")
    publish_receipt = UUID("00000000-0000-8000-8000-000000015826")
    publish_event = _event(0x15827)

    def publish(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        registry_revision = _acquire_registry(tx)

        def mutation(session: Any) -> Mapping[str, Any]:
            session.insert(
                "S24",
                {
                    "id": manifest,
                    "subject_id": SUBJECT,
                    "generation": 2,
                    "manifest_hash": "manifest-hash-2",
                    "input_frontier_hash": "frontier-1",
                    "captured_epoch": 0,
                    "dependency_closure_hash": session.publication_dependency_digest(),
                    "valid_until": session.publication_valid_until(),
                    "registry_revision_at_publish": registry_revision,
                    "registry_state_id": 1,
                    "ref_s05_id": POLICY,
                    "ref_s06_id": POLICY,
                    "ref_s15_id": FACTSET,
                    "ref_s23_id": MANIFEST_BUILD,
                    "ref_s49_id": ARTIFACT,
                },
            )
            session.insert(
                "S25",
                {
                    "id": manifest_binding,
                    "subject_id": SUBJECT,
                    "projection_role": "EXPOSURE",
                    "unavailable_reason": None,
                    "validated_basis_hash": "projection-basis",
                    "ref_s21_id": PROJECTION,
                    "ref_s24_id": manifest,
                },
            )
            session.update(
                "S01",
                {"decision_generation": 2, "current_manifest_id": manifest},
                {"subject_id": SUBJECT},
            )
            session.update(
                "S23",
                {"status": "PUBLISHED"},
                {"id": MANIFEST_BUILD, "subject_id": SUBJECT},
            )
            return {"manifest_id": str(manifest)}

        return tx.idempotent_outcome(
            receipt_id=publish_receipt,
            actor_scope="subject",
            client_key="exact-t3-publish",
            request_hash="exact-t3-publish-hash",
            mutation=mutation,
            event=publish_event,
            aggregate_locks={"manifest_builds": (MANIFEST_BUILD,)},
        )

    def crosswired_publish(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        registry_revision = _acquire_registry(tx)

        def mutation(session: Any) -> Mapping[str, Any]:
            session.insert(
                "S24",
                {
                    "id": UUID("00000000-0000-8000-8000-000000015834"),
                    "subject_id": SUBJECT,
                    "generation": 2,
                    "manifest_hash": "manifest-hash-2",
                    "input_frontier_hash": "wrong-frontier",
                    "captured_epoch": 0,
                    "dependency_closure_hash": session.publication_dependency_digest(),
                    "valid_until": session.publication_valid_until(),
                    "registry_revision_at_publish": registry_revision,
                    "registry_state_id": 1,
                    "ref_s05_id": POLICY,
                    "ref_s06_id": POLICY,
                    "ref_s15_id": FACTSET,
                    "ref_s23_id": MANIFEST_BUILD,
                    "ref_s49_id": ARTIFACT,
                },
            )
            return {"unexpected": True}

        return tx.idempotent_outcome(
            receipt_id=UUID("00000000-0000-8000-8000-000000015836"),
            actor_scope="subject",
            client_key="crosswired-t3-frontier",
            request_hash="crosswired-t3-frontier-hash",
            mutation=mutation,
            event=_event(0x15837),
            aggregate_locks={"manifest_builds": (MANIFEST_BUILD,)},
        )

    # T3 authenticates the READY candidate closure under S51 -> S01. It must not
    # require an outgoing current Manifest during bootstrap publication.
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.user_decision_state SET current_manifest_id=NULL "
            "WHERE subject_id=%s",
            (SUBJECT,),
        )
        connection.execute("SET session_replication_role=origin")

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="exact guarded T3"):
            execute_command(connection, "PublishManifest", SUBJECT, crosswired_publish)

    with psycopg.connect(database_urls["admin"]) as connection:
        outcome, replayed = execute_command(connection, "PublishManifest", SUBJECT, publish)
    assert not replayed and outcome["manifest_id"] == str(manifest)
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT typed_payload->'artifact_root_ids',"
            "typed_payload->'artifact_closure_ids' FROM kineticloop.decision_manifests "
            "WHERE id=%s",
            (manifest,),
        ).fetchone() == ([str(ARTIFACT)], sorted((str(ARTIFACT), str(DEPENDENCY))))

    next_build = UUID("00000000-0000-8000-8000-000000015864")
    next_manifest = UUID("00000000-0000-8000-8000-000000015865")
    next_binding = UUID("00000000-0000-8000-8000-000000015866")
    next_receipt = UUID("00000000-0000-8000-8000-000000015867")
    next_event = _event(0x15868)
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        next_candidate = _manifest_candidate_payload(connection)
        next_candidate["manifest_hash"] = "manifest-hash-3"
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.manifest_builds"
            "(id,subject_id,build_identity,status,captured_epoch,captured_input_frontier,"
            "ref_s05_id,ref_s06_id,ref_s15_id,ref_s21_id,typed_payload) "
            "VALUES (%s,%s,'manifest-build-3','READY',0,'frontier-1',%s,%s,%s,%s,%s)",
            (
                next_build,
                SUBJECT,
                POLICY,
                POLICY,
                FACTSET,
                PROJECTION,
                psycopg.types.json.Jsonb(next_candidate),
            ),
        )
        connection.execute("SET session_replication_role=origin")

    def publish_next(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        registry_revision = _acquire_registry(tx)

        def mutation(session: Any) -> Mapping[str, Any]:
            session.insert(
                "S24",
                {
                    "id": next_manifest,
                    "subject_id": SUBJECT,
                    "generation": 3,
                    "manifest_hash": "manifest-hash-3",
                    "input_frontier_hash": "frontier-1",
                    "captured_epoch": 0,
                    "dependency_closure_hash": session.publication_dependency_digest(),
                    "valid_until": session.publication_valid_until(),
                    "registry_revision_at_publish": registry_revision,
                    "registry_state_id": 1,
                    "ref_s05_id": POLICY,
                    "ref_s06_id": POLICY,
                    "ref_s15_id": FACTSET,
                    "ref_s23_id": next_build,
                    "ref_s49_id": ARTIFACT,
                },
            )
            session.insert(
                "S25",
                {
                    "id": next_binding,
                    "subject_id": SUBJECT,
                    "projection_role": "EXPOSURE",
                    "unavailable_reason": None,
                    "validated_basis_hash": "projection-basis",
                    "ref_s21_id": PROJECTION,
                    "ref_s24_id": next_manifest,
                },
            )
            session.update(
                "S01",
                {"decision_generation": 3, "current_manifest_id": next_manifest},
                {"subject_id": SUBJECT},
            )
            session.update(
                "S23",
                {"status": "PUBLISHED"},
                {"id": next_build, "subject_id": SUBJECT},
            )
            return {"manifest_id": str(next_manifest)}

        return tx.idempotent_outcome(
            receipt_id=next_receipt,
            actor_scope="subject",
            client_key="exact-t3-consecutive-publish",
            request_hash="exact-t3-consecutive-publish-hash",
            mutation=mutation,
            event=next_event,
            aggregate_locks={"manifest_builds": (next_build,)},
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        outcome, replayed = execute_command(
            connection, "PublishManifest", SUBJECT, publish_next
        )
    assert not replayed and outcome["manifest_id"] == str(next_manifest)


def test_t2_t7_subject_commands_share_s01_linearization(
    database_urls: dict[str, str],
) -> None:
    independent_subject = UUID("00000000-0000-8000-8000-000000020001")
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        original_epoch_row = connection.execute(
            "SELECT authorization_epoch FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone()
        assert original_epoch_row is not None
        original_epoch = int(original_epoch_row[0])
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.user_decision_state"
            "(subject_id,authorization_epoch,input_frontier_hash) VALUES (%s,0,'independent')",
            (independent_subject,),
        )
        connection.execute("SET session_replication_role=origin")

    commands = (
        "ApplyControl",
        "PublishManifest",
        "AdmitOrReviseIntent",
        "AcquireLease",
        "CommitBundle",
        "StartSession",
    )
    observations: dict[str, tuple[int, tuple[tuple[LockStage, str], ...]]] = {}
    fail_closed: dict[str, BaseException] = {}
    errors: list[BaseException] = []
    attempted_outcomes = {
        command: (
            UUID(f"00000000-0000-8000-8000-{0x20020 + index * 0x10:012x}"),
            _event(0x20021 + index * 0x10),
        )
        for index, command in enumerate(commands)
    }
    with psycopg.connect(database_urls["admin"]) as connection:
        lease_target = _database_timestamp(connection, offset=timedelta(hours=1))
    try:
        for index, command in enumerate(commands, start=1):
            blocker = psycopg.connect(
                database_urls["admin"],
                application_name=f"kl020-s01-holder-{command}",
            )
            try:
                blocker.execute(
                    "SELECT authorization_epoch FROM kineticloop.user_decision_state "
                    "WHERE subject_id=%s FOR UPDATE",
                    (SUBJECT,),
                )
                next_epoch = original_epoch + index
                blocker.execute(
                    "UPDATE kineticloop.user_decision_state SET authorization_epoch=%s "
                    "WHERE subject_id=%s",
                    (next_epoch, SUBJECT),
                )
                application_name = f"kl020-s01-waiter-{command}"

                def contender(command_kind: str = command) -> None:
                    try:
                        with psycopg.connect(
                            database_urls["admin"],
                            application_name=application_name,
                            options="-c statement_timeout=5000",
                        ) as connection:

                            def operation(tx: RepositoryTransaction) -> None:
                                if command_kind in {
                                    "PublishManifest",
                                    "CommitBundle",
                                    "StartSession",
                                }:
                                    _acquire_registry(tx)
                                else:
                                    tx.lock_subject()
                                context = getattr(tx, "_coordination_context")
                                observations[command_kind] = (
                                    int(context["authorization_epoch"]),
                                    tx.lock_trace,
                                )
                                receipt_id, event = attempted_outcomes[command_kind]
                                if command_kind == "ApplyControl":
                                    tx.idempotent_outcome(
                                        receipt_id=receipt_id,
                                        actor_scope="subject",
                                        client_key="kl020-t2-stale-guard",
                                        request_hash="kl020-t2-stale-guard-hash",
                                        mutation=lambda session: {},
                                        event=event,
                                        invalidation_scope="NOT_THE_POLICY_SCOPE",
                                    )
                                elif command_kind == "PublishManifest":
                                    tx.idempotent_outcome(
                                        receipt_id=receipt_id,
                                        actor_scope="subject",
                                        client_key="kl020-t3-stale-guard",
                                        request_hash="kl020-t3-stale-guard-hash",
                                        mutation=lambda session: {},
                                        event=event,
                                        aggregate_locks={
                                            "manifest_builds": (MANIFEST_BUILD,)
                                        },
                                    )
                                elif command_kind == "AdmitOrReviseIntent":
                                    tx.idempotent_outcome(
                                        receipt_id=receipt_id,
                                        actor_scope="subject",
                                        client_key="kl020-t4-missing-guard",
                                        request_hash="kl020-t4-missing-guard-hash",
                                        mutation=lambda session: {},
                                        event=event,
                                    )
                                elif command_kind == "AcquireLease":
                                    tx.lock_intents((INTENT,))
                                    tx.require_lease_acquisition_basis(
                                        INTENT,
                                        expected_owner_id="pre-lock-owner",
                                        expected_fence=999,
                                        new_owner_id="kl020-worker",
                                        new_fence=1000,
                                        new_lease_expires_at=lease_target,
                                        expected_request_revision=1,
                                    )

                            execute_command(connection, command_kind, SUBJECT, operation)
                    except BaseException as error:
                        expected_fragments = {
                            "ApplyControl": "invalidation scope",
                            "PublishManifest": "manifest build is stale",
                            "AdmitOrReviseIntent": "S30 row lock",
                            "AcquireLease": "compare-and-swap basis",
                            "CommitBundle": "KL_REGISTRY_AUTHORIZATION_INELIGIBLE",
                            "StartSession": "KL_REGISTRY_AUTHORIZATION_INELIGIBLE",
                        }
                        if expected_fragments[command_kind] in str(error):
                            fail_closed[command_kind] = error
                        else:
                            errors.append(error)

                thread = threading.Thread(target=contender)
                thread.start()
                blockers = _wait_until_database_blocked(
                    database_urls["admin"], application_name
                )
                assert blocker.info.backend_pid in blockers

                if index == 1:
                    independent_done = threading.Event()

                    def independent() -> None:
                        try:
                            with psycopg.connect(
                                database_urls["admin"],
                                application_name="kl020-independent-subject",
                                options="-c statement_timeout=5000",
                            ) as connection:
                                execute_command(
                                    connection,
                                    "AdmitOrReviseIntent",
                                    independent_subject,
                                    lambda tx: tx.lock_subject(),
                                )
                            independent_done.set()
                        except BaseException as error:
                            errors.append(error)

                    independent_thread = threading.Thread(target=independent)
                    independent_thread.start()
                    independent_thread.join(timeout=5)
                    assert not independent_thread.is_alive()
                    assert independent_done.is_set()
                    assert thread.is_alive()

                blocker.commit()
                thread.join(timeout=5)
                assert not thread.is_alive()
            finally:
                if not blocker.closed:
                    blocker.rollback()
                    blocker.close()

        assert not errors
        assert set(observations) | set(fail_closed) == set(commands)
        assert set(fail_closed) == set(commands)
        for index, command in enumerate(commands, start=1):
            if command in {"CommitBundle", "StartSession"}:
                continue
            observed_epoch, trace = observations[command]
            assert observed_epoch == original_epoch + index
            expected_prefix = (
                ((LockStage.REGISTRY, "S51"), (LockStage.SUBJECT, "S01"))
                if command in {"PublishManifest", "CommitBundle", "StartSession"}
                else ((LockStage.SUBJECT, "S01"),)
            )
            assert trace[: len(expected_prefix)] == expected_prefix
        with psycopg.connect(database_urls["admin"]) as connection:
            assert connection.execute(
                "SELECT authorization_epoch FROM kineticloop.user_decision_state "
                "WHERE subject_id=%s",
                (SUBJECT,),
            ).fetchone() == (original_epoch + len(commands),)
            for receipt_id, event in attempted_outcomes.values():
                for table, object_id in (
                    ("command_receipts", receipt_id),
                    ("domain_events", event.event_id),
                    ("outbox_deliveries", event.outbox_id),
                ):
                    assert connection.execute(
                        f"SELECT count(*) FROM kineticloop.{table} WHERE id=%s",
                        (object_id,),
                    ).fetchone() == (0,)
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute(
                "UPDATE kineticloop.user_decision_state SET authorization_epoch=%s "
                "WHERE subject_id=%s",
                (original_epoch, SUBJECT),
            )
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "DELETE FROM kineticloop.user_decision_state WHERE subject_id=%s",
                (independent_subject,),
            )
            connection.execute("SET session_replication_role=origin")


def test_concurrent_same_key_same_hash_replays_one_outcome(
    database_urls: dict[str, str],
) -> None:
    client_key = "kl020-same-hash"
    request_hash = "kl020-same-hash-request"
    receipt = UUID("00000000-0000-8000-8000-000000020102")
    event = _event(0x20103)
    first_locked = threading.Event()
    release_first = threading.Event()
    mutation_runs: list[str] = []
    outcomes: list[tuple[Mapping[str, Any], bool]] = []
    errors: list[BaseException] = []

    def invoke(index: int) -> None:
        try:
            with psycopg.connect(
                database_urls["admin"],
                application_name=f"kl020-same-hash-{index}",
                options="-c statement_timeout=5000",
            ) as connection:
                outcomes.append(
                    execute_command(
                        connection,
                        "CancelIntent",
                        SUBJECT,
                        lambda tx: _cancel_idempotent_outcome(
                            tx,
                            client_key=client_key,
                            request_hash=request_hash,
                            receipt_id=receipt,
                            event=event,
                            result_identity="kl020-same-result",
                            mutation_runs=mutation_runs,
                            hold_after_subject=(first_locked, release_first)
                            if index == 0
                            else None,
                        ),
                    )
                )
        except BaseException as error:
            errors.append(error)

    first = threading.Thread(target=invoke, args=(0,))
    first.start()
    assert first_locked.wait(timeout=5)
    second = threading.Thread(target=invoke, args=(1,))
    second.start()
    blockers = _wait_until_database_blocked(
        database_urls["admin"], "kl020-same-hash-1"
    )
    assert blockers
    release_first.set()
    first.join(timeout=5)
    second.join(timeout=5)
    assert not first.is_alive() and not second.is_alive()
    assert not errors
    assert len(outcomes) == 2
    assert sum(replayed for _, replayed in outcomes) == 1
    serialized = [
        json.dumps(outcome, sort_keys=True, separators=(",", ":")).encode()
        for outcome, _ in outcomes
    ]
    assert serialized[0] == serialized[1]
    assert mutation_runs == [request_hash]
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.command_receipts "
            "WHERE subject_id=%s AND command_kind='CancelIntent' AND client_key=%s",
            (SUBJECT, client_key),
        ).fetchone() == (1,)
        for table, object_id in (
            ("domain_events", event.event_id),
            ("outbox_deliveries", event.outbox_id),
        ):
            assert connection.execute(
                f"SELECT count(*) FROM kineticloop.{table} WHERE id=%s",
                (object_id,),
            ).fetchone() == (1,)


def test_concurrent_same_key_different_hash_rejects_conflict(
    database_urls: dict[str, str],
) -> None:
    client_key = "kl020-different-hash"
    first_locked = threading.Event()
    release_first = threading.Event()
    mutation_runs: list[str] = []
    outcomes: list[tuple[Mapping[str, Any], bool]] = []
    errors: list[tuple[BaseException, tuple[str, str] | None]] = []

    def invoke(index: int) -> None:
        request_hash = f"kl020-different-hash-{index}"
        receipt = UUID(f"00000000-0000-8000-8000-{0x20202 + index * 0x10:012x}")
        event = _event(0x20203 + index * 0x10)
        try:
            with psycopg.connect(
                database_urls["admin"],
                application_name=f"kl020-different-hash-{index}",
                options="-c statement_timeout=5000",
            ) as connection:
                outcomes.append(
                    execute_command(
                        connection,
                        "CancelIntent",
                        SUBJECT,
                        lambda tx: _cancel_idempotent_outcome(
                            tx,
                            client_key=client_key,
                            request_hash=request_hash,
                            receipt_id=receipt,
                            event=event,
                            result_identity=f"kl020-result-{index}",
                            mutation_runs=mutation_runs,
                            hold_after_subject=(first_locked, release_first)
                            if index == 0
                            else None,
                        ),
                    )
                )
        except BaseException as error:
            with psycopg.connect(database_urls["admin"]) as observer:
                committed = observer.execute(
                    "SELECT status,request_hash FROM kineticloop.command_receipts "
                    "WHERE subject_id=%s AND command_kind='CancelIntent' AND client_key=%s",
                    (SUBJECT, client_key),
                ).fetchone()
            errors.append((error, committed))

    first = threading.Thread(target=invoke, args=(0,))
    first.start()
    assert first_locked.wait(timeout=5)
    second = threading.Thread(target=invoke, args=(1,))
    second.start()
    blockers = _wait_until_database_blocked(
        database_urls["admin"], "kl020-different-hash-1"
    )
    assert blockers
    release_first.set()
    first.join(timeout=5)
    second.join(timeout=5)
    assert not first.is_alive() and not second.is_alive()
    assert len(outcomes) == 1 and outcomes[0][1] is False
    assert len(errors) == 1 and isinstance(errors[0][0], IdempotencyConflict)
    assert errors[0][1] == ("SUCCEEDED", "kl020-different-hash-0")
    assert mutation_runs == ["kl020-different-hash-0"]
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.command_receipts "
            "WHERE subject_id=%s AND command_kind='CancelIntent' AND client_key=%s",
            (SUBJECT, client_key),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.domain_events WHERE id IN (%s,%s)",
            (
                UUID("00000000-0000-8000-8000-000000020203"),
                UUID("00000000-0000-8000-8000-000000020213"),
            ),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.outbox_deliveries WHERE id IN (%s,%s)",
            (
                UUID("00000000-0000-8000-8000-000000020204"),
                UUID("00000000-0000-8000-8000-000000020214"),
            ),
        ).fetchone() == (1,)


def test_historical_replay_preserves_guard_boundary(
    database_urls: dict[str, str],
) -> None:
    mutation_runs: list[str] = []
    cancel_receipt = UUID("00000000-0000-8000-8000-000000020302")
    cancel_event = _event(0x20303)
    with psycopg.connect(database_urls["admin"]) as connection:
        first, replayed = execute_command(
            connection,
            "CancelIntent",
            SUBJECT,
            lambda tx: _cancel_idempotent_outcome(
                tx,
                client_key="kl020-historical-cancel",
                request_hash="kl020-historical-cancel-hash",
                receipt_id=cancel_receipt,
                event=cancel_event,
                result_identity="kl020-historical-result",
                mutation_runs=mutation_runs,
            ),
        )
    assert not replayed

    seeded_receipts = (
        (
            UUID("00000000-0000-8000-8000-000000020312"),
            "CommitBundle",
            "kl020-historical-t6",
            "kl020-historical-t6-hash",
            {"bundle_id": "old-bundle", "authorization_id": "old-authorization"},
        ),
        (
            UUID("00000000-0000-8000-8000-000000020322"),
            "AcquireLease",
            "kl020-historical-lease",
            "kl020-historical-lease-hash",
            {"intent_id": str(INTENT), "fence": 7},
        ),
        (
            UUID("00000000-0000-8000-8000-000000020332"),
            "PermitDispatch",
            "kl020-historical-permit",
            "kl020-historical-permit-hash",
            {"reservation_id": str(RESERVATION), "sendable": True},
        ),
        (
            UUID("00000000-0000-8000-8000-000000020342"),
            "StartSession",
            "kl020-historical-start",
            "kl020-historical-start-hash",
            {"session_id": str(SESSION), "executable": True},
        ),
    )
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        artifact_row = connection.execute(
            "SELECT valid_until FROM kineticloop.safety_artifacts WHERE id=%s",
            (ARTIFACT,),
        ).fetchone()
        intent_row = connection.execute(
            "SELECT status,lease_owner,fence_token,lease_expires_at "
            "FROM kineticloop.planning_intents WHERE id=%s",
            (INTENT,),
        ).fetchone()
        assert artifact_row is not None and intent_row is not None
        for receipt_id, command, key, request_hash, outcome in seeded_receipts:
            connection.execute(
                "INSERT INTO kineticloop.command_receipts"
                "(id,subject_id,status,command_kind,client_key,actor_scope,request_hash,typed_payload) "
                "VALUES (%s,%s,'SUCCEEDED',%s,%s,'subject',%s,%s)",
                (
                    receipt_id,
                    SUBJECT,
                    command,
                    key,
                    request_hash,
                    psycopg.types.json.Jsonb({"outcome": outcome}),
                ),
            )
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.safety_artifacts "
            "SET valid_until=clock_timestamp()-interval '1 minute' WHERE id=%s",
            (ARTIFACT,),
        )
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='FAILED',lease_owner='obsolete',"
            "fence_token=fence_token+1,lease_expires_at=clock_timestamp()-interval '1 minute' "
            "WHERE id=%s",
            (INTENT,),
        )
        connection.execute("SET session_replication_role=origin")

    try:
        aggregate_blocker = psycopg.connect(
            database_urls["admin"],
            application_name="kl020-historical-aggregate-holder",
            options="-c statement_timeout=5000",
        )
        aggregate_replay: dict[str, Mapping[str, Any]] = {}
        aggregate_errors: list[BaseException] = []
        try:
            for table, object_id in (
                ("planning_intents", INTENT),
                ("call_reservations", RESERVATION),
                ("daily_plan_heads", DAILY_HEAD),
                ("workout_sessions", SESSION),
            ):
                assert aggregate_blocker.execute(
                    f"SELECT id FROM kineticloop.{table} WHERE id=%s FOR UPDATE",
                    (object_id,),
                ).fetchone() == (object_id,)

            def replay_while_aggregates_are_locked() -> None:
                try:
                    with psycopg.connect(
                        database_urls["admin"],
                        application_name="kl020-historical-replay",
                        options="-c statement_timeout=5000",
                    ) as connection:
                        aggregate_replay["outcome"] = replay_outcome(
                            connection,
                            "CommitBundle",
                            SUBJECT,
                            actor_scope="subject",
                            client_key="kl020-historical-t6",
                            request_hash="kl020-historical-t6-hash",
                        )
                except BaseException as error:
                    aggregate_errors.append(error)

            replay_thread = threading.Thread(target=replay_while_aggregates_are_locked)
            replay_thread.start()
            replay_thread.join(timeout=5)
            assert not replay_thread.is_alive()
            assert not aggregate_errors
            assert aggregate_replay["outcome"] == {
                "bundle_id": "old-bundle",
                "authorization_id": "old-authorization",
            }
        finally:
            if not aggregate_blocker.closed:
                aggregate_blocker.rollback()
                aggregate_blocker.close()

        with psycopg.connect(database_urls["admin"]) as connection:
            historical_cancel = replay_outcome(
                connection,
                "CancelIntent",
                SUBJECT,
                actor_scope="subject",
                client_key="kl020-historical-cancel",
                request_hash="kl020-historical-cancel-hash",
            )
            historical_t6 = replay_outcome(
                connection,
                "CommitBundle",
                SUBJECT,
                actor_scope="subject",
                client_key="kl020-historical-t6",
                request_hash="kl020-historical-t6-hash",
            )
            historical_lease = replay_outcome(
                connection,
                "AcquireLease",
                SUBJECT,
                actor_scope="subject",
                client_key="kl020-historical-lease",
                request_hash="kl020-historical-lease-hash",
            )
            historical_permit = replay_outcome(
                connection,
                "PermitDispatch",
                SUBJECT,
                actor_scope="subject",
                client_key="kl020-historical-permit",
                request_hash="kl020-historical-permit-hash",
            )
            historical_start = replay_outcome(
                connection,
                "StartSession",
                SUBJECT,
                actor_scope="subject",
                client_key="kl020-historical-start",
                request_hash="kl020-historical-start-hash",
            )
        assert historical_cancel == first and mutation_runs == [
            "kl020-historical-cancel-hash"
        ]
        assert historical_t6 == {
            "bundle_id": "old-bundle",
            "authorization_id": "old-authorization",
        }
        assert historical_lease == {"intent_id": str(INTENT), "fence": 7}
        assert historical_permit["sendable"] is False
        assert historical_permit["replayed"] is True
        assert historical_start["executable"] is False
        assert historical_start["replayed"] is True

        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(IdempotencyConflict):
                replay_outcome(
                    connection,
                    "CancelIntent",
                    SUBJECT,
                    actor_scope="subject",
                    client_key="kl020-historical-cancel",
                    request_hash="kl020-wrong-hash",
                )
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_REGISTRY_ARTIFACT_EXPIRED",
            ):
                execute_command(
                    connection,
                    "CommitBundle",
                    SUBJECT,
                    lambda tx: _acquire_registry(tx),
                )
        with psycopg.connect(database_urls["admin"]) as connection:
            new_expiry = _database_timestamp(connection, offset=timedelta(hours=1))

            def stale_lease_guard(tx: RepositoryTransaction) -> None:
                tx.lock_subject()
                tx.lock_intents((INTENT,))
                tx.require_lease_acquisition_basis(
                    INTENT,
                    expected_owner_id="worker-a",
                    expected_fence=7,
                    new_owner_id="worker-kl020",
                    new_fence=8,
                    new_lease_expires_at=new_expiry,
                    expected_request_revision=1,
                )

            with pytest.raises(FenceLost):
                execute_command(
                    connection,
                    "AcquireLease",
                    SUBJECT,
                    stale_lease_guard,
                )
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.safety_artifacts SET valid_until=%s WHERE id=%s",
                (artifact_row[0], ARTIFACT),
            )
            connection.execute(
                "UPDATE kineticloop.planning_intents SET status=%s,lease_owner=%s,"
                "fence_token=%s,lease_expires_at=%s WHERE id=%s",
                (*intent_row, INTENT),
            )
            connection.execute("SET session_replication_role=origin")


def _set_kl022_t6_ready(admin_url: str) -> tuple[UUID, UUID]:
    prescription_id, prior_authorization_id = _seed_current_t7_pair(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        execution_basis = connection.execute(
            "SELECT execution_basis_event_id FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone()
        assert execution_basis is not None
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',"
            "lease_owner='worker-kl022',fence_token=22,"
            "lease_expires_at=clock_timestamp()+interval '2 days',"
            "deadline=clock_timestamp()+interval '2 days',result_authorization_id=NULL "
            "WHERE id=%s",
            (INTENT,),
        )
        connection.execute(
            "UPDATE kineticloop.planning_attempts SET status='COMMIT_READY',fence_token=22,"
            "completed_at=NULL,captured_epoch=(SELECT authorization_epoch "
            "FROM kineticloop.user_decision_state WHERE subject_id=%s) WHERE id=%s",
            (SUBJECT, ATTEMPT),
        )
        connection.execute(
            "UPDATE kineticloop.validation_results SET result='PASS',"
            "valid_until=clock_timestamp()+interval '2 days',ref_s03_id=%s WHERE id=%s",
            (execution_basis[0], VALIDATION),
        )
        connection.execute("SET session_replication_role=origin")
    return prescription_id, prior_authorization_id


def _prepare_kl022_t6_basis(
    admin_url: str,
    command_kind: str,
    requested_valid_until: datetime | None = None,
    *,
    session_timezone: str | None = None,
) -> tuple[tuple[Mapping[str, Any], ...], str, datetime, tuple[tuple[LockStage, str], ...]]:
    def operation(
        tx: RepositoryTransaction,
    ) -> tuple[
        tuple[Mapping[str, Any], ...],
        str,
        datetime,
        tuple[tuple[LockStage, str], ...],
    ]:
        _acquire_registry(tx)
        tx.lock_intents((INTENT,))
        tx.lock_daily_head(date(2026, 9, 26))
        tx.require_current_fence(
            INTENT,
            owner_id="worker-kl022",
            fence=22,
            expected_request_revision=1,
            expected_attempt_id=ATTEMPT,
        )
        tx.lock_remaining("planning_attempts", (ATTEMPT,))
        tx.lock_remaining("validation_results", (VALIDATION,))
        dependencies, digest, valid_until = tx.prepare_authorization_basis(
            validation_id=VALIDATION,
            resolution_id=RESOLUTION,
            intent_id=INTENT,
            head_id=DAILY_HEAD,
            requested_valid_until=requested_valid_until,
        )
        return dependencies, digest, valid_until, tx.lock_trace

    with psycopg.connect(admin_url) as connection:
        if session_timezone is not None:
            connection.execute(
                "SELECT set_config('TimeZone',%s,false)", (session_timezone,)
            )
            connection.commit()
        return execute_command(connection, command_kind, SUBJECT, operation)


def test_t6_authorization_evaluator_persists_exact_minimum_certificate(
    database_urls: dict[str, str],
) -> None:
    _reset_kl022_fixture(database_urls)
    prescription_id, _ = _set_kl022_t6_ready(database_urls["admin"])

    def configure_long_bounds() -> None:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.decision_manifests SET valid_until="
                "clock_timestamp()+interval '2 days' WHERE id=%s",
                (MANIFEST,),
            )
            connection.execute(
                "UPDATE kineticloop.evidence_resolutions SET resolution_expires_at="
                "clock_timestamp()+interval '2 days',typed_payload=jsonb_build_object("
                "'admission_freshness',jsonb_build_array(jsonb_build_object("
                "'identity','admission:fitness','revision',1,"
                "'valid_from',(clock_timestamp()-interval '1 minute')::text,"
                "'valid_until',(clock_timestamp()+interval '2 days')::text))) WHERE id=%s",
                (RESOLUTION,),
            )
            connection.execute(
                "UPDATE kineticloop.projection_versions SET valid_until="
                "clock_timestamp()+interval '2 days' WHERE id=%s",
                (PROJECTION,),
            )
            connection.execute(
                "UPDATE kineticloop.safety_artifacts SET valid_until="
                "clock_timestamp()+interval '2 days' WHERE id=ANY(%s)",
                (list(_registry_ids()),),
            )
            connection.execute(
                "UPDATE kineticloop.policy_bundles SET typed_payload=jsonb_set(typed_payload,"
                "'{max_authorization_ttl_seconds}','172800'::jsonb) WHERE id=%s",
                (POLICY,),
            )
            connection.execute(
                "UPDATE kineticloop.daily_plan_heads SET typed_payload=jsonb_set(typed_payload,"
                "'{calendar_valid_until}',to_jsonb((clock_timestamp()+interval '2 days')::text)) "
                "WHERE id=%s",
                (DAILY_HEAD,),
            )
            connection.execute("SET session_replication_role=origin")
            manifest_basis = _manifest_candidate_payload(connection)
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.decision_manifests SET typed_payload=%s WHERE id=%s",
                (
                    psycopg.types.json.Jsonb(
                        {
                            "artifact_closure_ids": manifest_basis["artifact_closure_ids"],
                            "artifact_root_ids": manifest_basis["artifact_root_ids"],
                            "artifact_dependency_closure_hash": manifest_basis[
                                "artifact_dependency_closure_hash"
                            ],
                        }
                    ),
                    MANIFEST,
                ),
            )
            connection.execute("SET session_replication_role=origin")

    configure_long_bounds()

    requested_end: datetime | None
    with psycopg.connect(database_urls["admin"]) as connection:
        requested_end = _database_timestamp(connection, offset=timedelta(minutes=10))
    commit_basis = _prepare_kl022_t6_basis(
        database_urls["admin"], "CommitBundle", requested_end
    )
    reauthorize_basis = _prepare_kl022_t6_basis(
        database_urls["admin"], "Reauthorize", requested_end
    )
    los_angeles_basis = _prepare_kl022_t6_basis(
        database_urls["admin"],
        "Reauthorize",
        requested_end,
        session_timezone="America/Los_Angeles",
    )
    for dependencies, digest, valid_until, trace in (commit_basis, reauthorize_basis):
        assert valid_until == requested_end
        assert trace[:2] == ((LockStage.REGISTRY, "S51"), (LockStage.SUBJECT, "S01"))
        assert digest == hashlib.sha256(
            json.dumps(
                list(dependencies), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        kinds = {item["dependency_kind"] for item in dependencies}
        assert {
            "ARTIFACT",
            "MANIFEST",
            "EVIDENCE_RESOLUTION",
            "VALIDATION_ADMISSION_FRESHNESS",
            "EVIDENCE_ADMISSION_FRESHNESS",
            "REQUEST_DEADLINE",
            "POLICY_TTL",
            "CALENDAR",
            "PROJECTION",
            "REQUESTED_ABSOLUTE_END",
        } <= kinds
    assert los_angeles_basis[2] == requested_end
    assert los_angeles_basis[1] == hashlib.sha256(
        json.dumps(
            list(los_angeles_basis[0]), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    assert all(
        str(value).endswith("Z")
        for dependency in los_angeles_basis[0]
        for key, value in dependency.items()
        if key in {"valid_from", "valid_until"}
    )

    def vary_bound(kind: str, *, restore: bool = False) -> None:
        interval = "2 days" if restore else "20 minutes"
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            if kind == "MANIFEST":
                connection.execute(
                    "UPDATE kineticloop.decision_manifests SET valid_until="
                    "clock_timestamp()+%s::interval WHERE id=%s",
                    (interval, MANIFEST),
                )
            elif kind == "EVIDENCE_RESOLUTION":
                connection.execute(
                    "UPDATE kineticloop.evidence_resolutions SET resolution_expires_at="
                    "clock_timestamp()+%s::interval WHERE id=%s",
                    (interval, RESOLUTION),
                )
            elif kind == "VALIDATION_ADMISSION_FRESHNESS":
                connection.execute(
                    "UPDATE kineticloop.validation_results SET valid_until="
                    "clock_timestamp()+%s::interval WHERE id=%s",
                    (interval, VALIDATION),
                )
            elif kind == "EVIDENCE_ADMISSION_FRESHNESS":
                connection.execute(
                    "UPDATE kineticloop.evidence_resolutions SET typed_payload="
                    "jsonb_build_object('admission_freshness',jsonb_build_array("
                    "jsonb_build_object('identity','admission:fitness','revision',1,"
                    "'valid_from',(clock_timestamp()-interval '1 minute')::text,"
                    "'valid_until',(clock_timestamp()+%s::interval)::text))) WHERE id=%s",
                    (interval, RESOLUTION),
                )
            elif kind == "PROJECTION":
                connection.execute(
                    "UPDATE kineticloop.projection_versions SET valid_until="
                    "clock_timestamp()+%s::interval WHERE id=%s",
                    (interval, PROJECTION),
                )
            elif kind == "ARTIFACT":
                connection.execute(
                    "UPDATE kineticloop.safety_artifacts SET valid_until="
                    "clock_timestamp()+%s::interval WHERE id=%s",
                    (interval, DEPENDENCY),
                )
            elif kind == "POLICY_TTL":
                seconds = 172800 if restore else 1200
                connection.execute(
                    "UPDATE kineticloop.policy_bundles SET typed_payload=jsonb_set("
                    "typed_payload,'{max_authorization_ttl_seconds}',to_jsonb(%s::integer)) "
                    "WHERE id=%s",
                    (seconds, POLICY),
                )
            elif kind == "REQUEST_DEADLINE":
                connection.execute(
                    "UPDATE kineticloop.planning_intents SET deadline="
                    "clock_timestamp()+%s::interval WHERE id=%s",
                    (interval, INTENT),
                )
            elif kind == "CALENDAR":
                connection.execute(
                    "UPDATE kineticloop.daily_plan_heads SET typed_payload=jsonb_set("
                    "typed_payload,'{calendar_valid_until}',"
                    "to_jsonb((clock_timestamp()+%s::interval)::text)) WHERE id=%s",
                    (interval, DAILY_HEAD),
                )
            else:  # pragma: no cover - local exhaustive test helper
                raise AssertionError(kind)
            connection.execute("SET session_replication_role=origin")
            if kind == "ARTIFACT":
                manifest_basis = _manifest_candidate_payload(connection)
                connection.execute("SET session_replication_role=replica")
                connection.execute(
                    "UPDATE kineticloop.decision_manifests SET typed_payload=%s WHERE id=%s",
                    (
                        psycopg.types.json.Jsonb(
                            {
                                "artifact_closure_ids": manifest_basis["artifact_closure_ids"],
                                "artifact_root_ids": manifest_basis["artifact_root_ids"],
                                "artifact_dependency_closure_hash": manifest_basis[
                                    "artifact_dependency_closure_hash"
                                ],
                            }
                        ),
                        MANIFEST,
                    ),
                )
                connection.execute("SET session_replication_role=origin")

    varied_kinds = (
        "MANIFEST",
        "EVIDENCE_RESOLUTION",
        "VALIDATION_ADMISSION_FRESHNESS",
        "EVIDENCE_ADMISSION_FRESHNESS",
        "PROJECTION",
        "ARTIFACT",
        "POLICY_TTL",
        "REQUEST_DEADLINE",
        "CALENDAR",
    )
    for kind in varied_kinds:
        vary_bound(kind)
        varied_dependencies, _, varied_until, _ = _prepare_kl022_t6_basis(
            database_urls["admin"], "CommitBundle"
        )
        matching_ends = [
            datetime.fromisoformat(str(item["valid_until"]))
            for item in varied_dependencies
            if item["dependency_kind"] == kind
            and item.get("valid_until") is not None
            and (kind != "ARTIFACT" or item["identity"] == str(DEPENDENCY))
        ]
        assert matching_ends == [varied_until], kind
        vary_bound(kind, restore=True)

    future_effective_rows = (
        ("MANIFEST", "decision_manifests", MANIFEST),
        ("EVIDENCE_RESOLUTION", "evidence_resolutions", RESOLUTION),
        ("VALIDATION_ADMISSION_FRESHNESS", "validation_results", VALIDATION),
        ("PROJECTION", "projection_versions", PROJECTION),
    )
    for kind, table, object_id in future_effective_rows:
        with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                psycopg.sql.SQL(
                    "UPDATE kineticloop.{} SET effective_at=clock_timestamp()+interval '1 hour' "
                    "WHERE id=%s"
                ).format(psycopg.sql.Identifier(table)),
                (object_id,),
            )
            connection.execute("SET session_replication_role=origin")
        try:
            with pytest.raises(GuardRequired, match="not yet effective"):
                _prepare_kl022_t6_basis(database_urls["admin"], "CommitBundle")
        finally:
            with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
                connection.execute("SET session_replication_role=replica")
                connection.execute(
                    psycopg.sql.SQL("UPDATE kineticloop.{} SET effective_at=NULL WHERE id=%s").format(
                        psycopg.sql.Identifier(table)
                    ),
                    (object_id,),
                )
                connection.execute("SET session_replication_role=origin")

    issuance = UUID("00000000-0000-8000-8000-000000022142")
    receipt = UUID("00000000-0000-8000-8000-000000022143")
    event = _event(0x22144)

    def persist(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        registry_revision = _acquire_registry(tx)
        tx.lock_intents((INTENT,))
        tx.lock_daily_head(date(2026, 9, 26))
        tx.require_current_fence(
            INTENT,
            owner_id="worker-kl022",
            fence=22,
            expected_request_revision=1,
            expected_attempt_id=ATTEMPT,
        )

        def mutation(session: Any) -> Mapping[str, Any]:
            dependencies = session.authorization_certificate_dependencies()
            digest = session.authorization_closure_digest()
            session.insert(
                "S42",
                {
                    "id": issuance,
                    "subject_id": SUBJECT,
                    "bound_content_hash": "authorization-content",
                    "scope": "EXECUTION",
                    "issuance_reason": "REVALIDATION",
                    "artifact_dependency_closure_hash": digest,
                    "registry_revision_at_issue": registry_revision,
                    "valid_from": session.authorization_valid_from(),
                    "valid_until": session.authorization_valid_until(),
                    "validity_certificate": psycopg.types.json.Jsonb(
                        {
                            "authorization_epoch": tx.authorization_epoch,
                            "method_version": AUTHORIZATION_METHOD_VERSION,
                            "closure_digest": digest,
                            "dependencies": list(dependencies),
                        }
                    ),
                    "ref_s02_id": receipt,
                    "ref_s05_id": POLICY,
                    "ref_s24_id": MANIFEST,
                    "ref_s36_id": RESOLUTION,
                    "ref_s37_id": VALIDATION,
                    "ref_s40_id": prescription_id,
                    "ref_s49_id": ARTIFACT,
                    "registry_state_id": 1,
                },
            )
            session.insert_authorization_artifact_closure(issuance, _registry_ids())
            session.update(
                "S01", {"execution_basis_event_id": event.event_id}, {"subject_id": SUBJECT}
            )
            session.update(
                "S27",
                {"status": "FOUND_VALID_PLAN", "result_authorization_id": issuance},
                {"id": INTENT, "subject_id": SUBJECT},
            )
            session.update(
                "S29",
                {"status": "COMMITTED", "completed_at": COMPLETION_RECORDED_AT},
                {"id": ATTEMPT, "subject_id": SUBJECT},
            )
            return {"authorization_id": str(issuance)}

        return tx.idempotent_outcome(
            receipt_id=receipt,
            actor_scope="subject",
            client_key="kl022-exact-certificate",
            request_hash="kl022-exact-certificate-hash",
            mutation=mutation,
            event=event,
            aggregate_locks={
                "planning_attempts": (ATTEMPT,),
                "validation_results": (VALIDATION,),
            },
            authorization_basis={
                "validation_id": VALIDATION,
                "resolution_id": RESOLUTION,
                "intent_id": INTENT,
                "head_id": DAILY_HEAD,
                "requested_valid_until": requested_end,
            },
        )

    dynamic_start_kinds = {
        "CALENDAR",
        "POLICY_TTL",
        "REQUEST_DEADLINE",
        "REQUESTED_ABSOLUTE_END",
    }

    def assert_exact_certificate(
        actual: list[Mapping[str, Any]],
        expected: tuple[Mapping[str, Any], ...],
        authorization_valid_from: datetime,
    ) -> None:
        actual_normalized = []
        expected_normalized = []
        for actual_entry, expected_entry in zip(actual, expected, strict=True):
            assert set(actual_entry) == set(expected_entry)
            actual_copy = dict(actual_entry)
            expected_copy = dict(expected_entry)
            if actual_entry["dependency_kind"] in dynamic_start_kinds:
                assert datetime.fromisoformat(str(actual_copy.pop("valid_from"))) == (
                    authorization_valid_from
                )
                expected_copy.pop("valid_from")
            if actual_entry["dependency_kind"] == "POLICY_TTL":
                policy_end = datetime.fromisoformat(str(actual_copy.pop("valid_until")))
                assert policy_end - authorization_valid_from in {
                    timedelta(seconds=1200),
                    timedelta(seconds=172800),
                }
                expected_copy.pop("valid_until")
            actual_normalized.append(actual_copy)
            expected_normalized.append(expected_copy)
        assert actual_normalized == expected_normalized

    reauthorize_basis = _prepare_kl022_t6_basis(
        database_urls["admin"], "Reauthorize", requested_end
    )
    with psycopg.connect(database_urls["admin"]) as connection:
        outcome, replayed = execute_command(connection, "Reauthorize", SUBJECT, persist)
    assert not replayed and outcome == {"authorization_id": str(issuance)}
    with psycopg.connect(database_urls["admin"]) as connection:
        persisted = connection.execute(
            "SELECT valid_from,valid_until,validity_certificate,"
            "artifact_dependency_closure_hash FROM kineticloop.authorization_issuances "
            "WHERE id=%s",
            (issuance,),
        ).fetchone()
        assert persisted is not None and persisted[0] < persisted[1] == requested_end
        assert persisted[2]["method_version"] == AUTHORIZATION_METHOD_VERSION
        assert persisted[2]["closure_digest"] == persisted[3]
        assert persisted[2]["closure_digest"] == hashlib.sha256(
            json.dumps(
                persisted[2]["dependencies"], sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        assert_exact_certificate(
            persisted[2]["dependencies"], reauthorize_basis[0], persisted[0]
        )

    # Exercise the full existing Reauthorize owner for every independently varied
    # finite bound, and compare the immutable S42 certificate (including both
    # validity endpoints) with the exact server-computed basis.
    for kind in varied_kinds:
        _reset_kl022_fixture(database_urls)
        prescription_id, _ = _set_kl022_t6_ready(database_urls["admin"])
        configure_long_bounds()
        vary_bound(kind)
        varied_basis = _prepare_kl022_t6_basis(database_urls["admin"], "Reauthorize")
        requested_end = None
        with psycopg.connect(database_urls["admin"]) as connection:
            varied_outcome, varied_replayed = execute_command(
                connection, "Reauthorize", SUBJECT, persist
            )
        assert not varied_replayed and varied_outcome == {
            "authorization_id": str(issuance)
        }
        with psycopg.connect(database_urls["admin"]) as connection:
            varied_persisted = connection.execute(
                "SELECT valid_from,valid_until,validity_certificate,"
                "artifact_dependency_closure_hash "
                "FROM kineticloop.authorization_issuances WHERE id=%s",
                (issuance,),
            ).fetchone()
        assert varied_persisted is not None
        if kind == "POLICY_TTL":
            assert varied_persisted[1] == varied_persisted[0] + timedelta(seconds=1200)
        else:
            assert varied_persisted[1] == varied_basis[2], kind
        assert_exact_certificate(
            varied_persisted[2]["dependencies"], varied_basis[0], varied_persisted[0]
        )
        assert varied_persisted[2]["closure_digest"] == varied_persisted[3]
        assert varied_persisted[2]["closure_digest"] == hashlib.sha256(
            json.dumps(
                varied_persisted[2]["dependencies"],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    _reset_kl022_fixture(database_urls)
    _set_kl022_t6_ready(database_urls["admin"])
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        before = connection.execute(
            "SELECT (SELECT count(*) FROM kineticloop.daily_bundle_revisions),"
            "(SELECT count(*) FROM kineticloop.prescription_revisions),"
            "(SELECT count(*) FROM kineticloop.bundle_prescription_members),"
            "(SELECT count(*) FROM kineticloop.authorization_issuances),"
            "(SELECT count(*) FROM kineticloop.authorization_events),"
            "(SELECT count(*) FROM kineticloop.command_receipts),"
            "(SELECT count(*) FROM kineticloop.domain_events),"
            "(SELECT count(*) FROM kineticloop.outbox_deliveries),"
            "(SELECT status FROM kineticloop.planning_intents WHERE id=%s),"
            "(SELECT status FROM kineticloop.planning_attempts WHERE id=%s),"
            "(SELECT head_revision FROM kineticloop.daily_plan_heads WHERE id=%s)",
            (INTENT, ATTEMPT, DAILY_HEAD),
        ).fetchone()
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.evidence_resolutions SET typed_payload='{}'::jsonb WHERE id=%s",
            (RESOLUTION,),
        )
        connection.execute("SET session_replication_role=origin")
    with pytest.raises(GuardRequired, match="admission freshness"):
        _prepare_kl022_t6_basis(database_urls["admin"], "CommitBundle")
    with psycopg.connect(database_urls["admin"]) as connection:
        after = connection.execute(
            "SELECT (SELECT count(*) FROM kineticloop.daily_bundle_revisions),"
            "(SELECT count(*) FROM kineticloop.prescription_revisions),"
            "(SELECT count(*) FROM kineticloop.bundle_prescription_members),"
            "(SELECT count(*) FROM kineticloop.authorization_issuances),"
            "(SELECT count(*) FROM kineticloop.authorization_events),"
            "(SELECT count(*) FROM kineticloop.command_receipts),"
            "(SELECT count(*) FROM kineticloop.domain_events),"
            "(SELECT count(*) FROM kineticloop.outbox_deliveries),"
            "(SELECT status FROM kineticloop.planning_intents WHERE id=%s),"
            "(SELECT status FROM kineticloop.planning_attempts WHERE id=%s),"
            "(SELECT head_revision FROM kineticloop.daily_plan_heads WHERE id=%s)",
            (INTENT, ATTEMPT, DAILY_HEAD),
        ).fetchone()
    assert after == before

    _reset_kl022_fixture(database_urls)
    _set_kl022_t6_ready(database_urls["admin"])
    rollback_bundle = UUID("00000000-0000-8000-8000-000000022239")
    rollback_prescription = UUID("00000000-0000-8000-8000-000000022240")
    rollback_member = UUID("00000000-0000-8000-8000-000000022241")
    rollback_authorization = UUID("00000000-0000-8000-8000-000000022242")
    rollback_receipt = UUID("00000000-0000-8000-8000-000000022247")
    rollback_event = _event(0x22248)
    with psycopg.connect(database_urls["admin"]) as connection:
        rollback_parent_row = connection.execute(
            "SELECT current_bundle_revision_id FROM kineticloop.daily_plan_heads WHERE id=%s",
            (DAILY_HEAD,),
        ).fetchone()
        assert rollback_parent_row is not None
        rollback_parent = rollback_parent_row[0]
        rollback_before = connection.execute(
            "SELECT (SELECT count(*) FROM kineticloop.daily_bundle_revisions),"
            "(SELECT count(*) FROM kineticloop.prescription_revisions),"
            "(SELECT count(*) FROM kineticloop.bundle_prescription_members),"
            "(SELECT count(*) FROM kineticloop.authorization_issuances),"
            "(SELECT count(*) FROM kineticloop.authorization_events),"
            "(SELECT count(*) FROM kineticloop.command_receipts),"
            "(SELECT count(*) FROM kineticloop.domain_events),"
            "(SELECT count(*) FROM kineticloop.outbox_deliveries),"
            "(SELECT ARRAY[authorization_epoch::text,execution_basis_event_id::text] "
            "FROM kineticloop.user_decision_state WHERE subject_id=%s),"
            "(SELECT ARRAY[status,result_bundle_revision_id::text,result_authorization_id::text] "
            "FROM kineticloop.planning_intents WHERE id=%s),"
            "(SELECT ARRAY[status,completed_at::text] "
            "FROM kineticloop.planning_attempts WHERE id=%s),"
            "(SELECT ARRAY[head_revision::text,current_bundle_revision_id::text] "
            "FROM kineticloop.daily_plan_heads WHERE id=%s)",
            (SUBJECT, INTENT, ATTEMPT, DAILY_HEAD),
        ).fetchone()

    def partial_then_bad_certificate(tx: RepositoryTransaction) -> Any:
        registry_revision = _acquire_registry(tx)
        tx.lock_intents((INTENT,))
        tx.lock_daily_head(date(2026, 9, 26))
        tx.require_current_fence(
            INTENT,
            owner_id="worker-kl022",
            fence=22,
            expected_request_revision=1,
            expected_attempt_id=ATTEMPT,
        )

        def mutation(session: Any) -> Mapping[str, Any]:
            dependencies = list(session.authorization_certificate_dependencies())
            omitted_dependencies = dependencies[:-1]
            omitted_digest = hashlib.sha256(
                json.dumps(
                    omitted_dependencies, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
            session.insert(
                "S39",
                {
                    "id": rollback_bundle,
                    "subject_id": SUBJECT,
                    "local_date": date(2026, 9, 26),
                    "revision_no": 1,
                    "generation_mode": "AI_GENERATED_CURRENT",
                    "parent_revision_id": rollback_parent,
                    "ref_s02_id": rollback_receipt,
                    "ref_s24_id": MANIFEST,
                    "ref_s27_id": INTENT,
                    "ref_s29_id": ATTEMPT,
                    "ref_s37_id": VALIDATION,
                    "ref_s38_id": DAILY_HEAD,
                },
            )
            session.insert(
                "S40",
                {
                    "id": rollback_prescription,
                    "subject_id": SUBJECT,
                    "prescription_identity": "kl022-rollback-prescription",
                    "prescription_kind": "WORKOUT",
                    "prescription_revision": 1,
                    "content_hash": "kl022-rollback-content",
                    "ref_s34_id": PROPOSAL,
                    "ref_s49_id": ARTIFACT,
                },
            )
            session.insert(
                "S41",
                {
                    "id": rollback_member,
                    "subject_id": SUBJECT,
                    "member_kind": "PRESCRIPTION",
                    "session_slot": "rollback",
                    "member_order": 1,
                    "ref_s39_id": rollback_bundle,
                    "ref_s40_id": rollback_prescription,
                },
            )
            session.update(
                "S01",
                {"execution_basis_event_id": rollback_event.event_id},
                {"subject_id": SUBJECT},
            )
            session.update(
                "S38",
                {"head_revision": 1, "current_bundle_revision_id": rollback_bundle},
                {"id": DAILY_HEAD, "subject_id": SUBJECT},
            )
            session.update(
                "S27",
                {"status": "FOUND_VALID_PLAN", "result_bundle_revision_id": rollback_bundle},
                {"id": INTENT, "subject_id": SUBJECT},
            )
            session.update(
                "S29",
                {"status": "COMMITTED", "completed_at": COMPLETION_RECORDED_AT},
                {"id": ATTEMPT, "subject_id": SUBJECT},
            )
            session.insert(
                "S42",
                {
                    "id": rollback_authorization,
                    "subject_id": SUBJECT,
                    "bound_content_hash": "kl022-rollback-content",
                    "scope": "EXECUTION",
                    "issuance_reason": "AI_PLAN",
                    "artifact_dependency_closure_hash": omitted_digest,
                    "registry_revision_at_issue": registry_revision,
                    "valid_from": session.authorization_valid_from(),
                    "valid_until": session.authorization_valid_until(),
                    "validity_certificate": psycopg.types.json.Jsonb(
                        {
                            "authorization_epoch": tx.authorization_epoch,
                            "method_version": AUTHORIZATION_METHOD_VERSION,
                            "closure_digest": omitted_digest,
                            "dependencies": omitted_dependencies,
                        }
                    ),
                    "ref_s02_id": rollback_receipt,
                    "ref_s05_id": POLICY,
                    "ref_s24_id": MANIFEST,
                    "ref_s36_id": RESOLUTION,
                    "ref_s37_id": VALIDATION,
                    "ref_s40_id": rollback_prescription,
                    "ref_s49_id": ARTIFACT,
                    "registry_state_id": 1,
                },
            )
            raise AssertionError("incomplete certificate unexpectedly admitted")

        return tx.idempotent_outcome(
            receipt_id=rollback_receipt,
            actor_scope="subject",
            client_key="kl022-partial-rollback",
            request_hash="kl022-partial-rollback-hash",
            mutation=mutation,
            event=rollback_event,
            aggregate_locks={
                "planning_attempts": (ATTEMPT,),
                "validation_results": (VALIDATION,),
            },
            authorization_basis={
                "validation_id": VALIDATION,
                "resolution_id": RESOLUTION,
                "intent_id": INTENT,
                "head_id": DAILY_HEAD,
            },
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(ArtifactIdentityRequired, match="exact verified artifact proofs"):
            execute_command(
                connection, "CommitBundle", SUBJECT, partial_then_bad_certificate
            )
    with psycopg.connect(database_urls["admin"]) as connection:
        rollback_after = connection.execute(
            "SELECT (SELECT count(*) FROM kineticloop.daily_bundle_revisions),"
            "(SELECT count(*) FROM kineticloop.prescription_revisions),"
            "(SELECT count(*) FROM kineticloop.bundle_prescription_members),"
            "(SELECT count(*) FROM kineticloop.authorization_issuances),"
            "(SELECT count(*) FROM kineticloop.authorization_events),"
            "(SELECT count(*) FROM kineticloop.command_receipts),"
            "(SELECT count(*) FROM kineticloop.domain_events),"
            "(SELECT count(*) FROM kineticloop.outbox_deliveries),"
            "(SELECT ARRAY[authorization_epoch::text,execution_basis_event_id::text] "
            "FROM kineticloop.user_decision_state WHERE subject_id=%s),"
            "(SELECT ARRAY[status,result_bundle_revision_id::text,result_authorization_id::text] "
            "FROM kineticloop.planning_intents WHERE id=%s),"
            "(SELECT ARRAY[status,completed_at::text] "
            "FROM kineticloop.planning_attempts WHERE id=%s),"
            "(SELECT ARRAY[head_revision::text,current_bundle_revision_id::text] "
            "FROM kineticloop.daily_plan_heads WHERE id=%s)",
            (SUBJECT, INTENT, ATTEMPT, DAILY_HEAD),
        ).fetchone()
    assert rollback_after == rollback_before


def test_t7_executability_rereads_epoch_scope_control_and_time(
    database_urls: dict[str, str],
) -> None:
    _reset_kl022_fixture(database_urls)
    prescription_id, old_authorization_id = _seed_current_t7_pair(database_urls["admin"])
    current_authorization_id = old_authorization_id

    def query(command_kind: str = "StartSession") -> Any:
        with psycopg.connect(database_urls["admin"]) as connection:
            return query_execution_eligibility(
                connection,
                command_kind=command_kind,
                subject_id=SUBJECT,
                artifact_ids=_registry_ids(),
                artifact_identities=_registry_identities(),
                local_date=date(2026, 9, 26),
                session_id=SESSION,
                prescription_id=prescription_id,
                authorization_id=current_authorization_id,
                execution_scope="EXECUTION",
            )

    first = query()
    assert first.is_executable and first.non_bearer
    assert not hasattr(first, "permission_token")

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.authorization_issuances SET "
            "validity_certificate=jsonb_set(validity_certificate,'{authorization_epoch}','1') "
            "WHERE id=%s",
            (old_authorization_id,),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.authorization_issuances SET "
            "validity_certificate=jsonb_set(validity_certificate,'{authorization_epoch}','0') "
            "WHERE id=%s",
            (old_authorization_id,),
        )
        connection.execute(
            "UPDATE kineticloop.authorization_issuances SET scope='OTHER' WHERE id=%s",
            (old_authorization_id,),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.authorization_issuances SET scope='EXECUTION',"
            "bound_content_hash='other-content' WHERE id=%s",
            (old_authorization_id,),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.authorization_issuances SET "
            "bound_content_hash='authorization-content' WHERE id=%s",
            (old_authorization_id,),
        )
        connection.execute(
            "UPDATE kineticloop.daily_plan_heads SET current_bundle_revision_id=NULL WHERE id=%s",
            (DAILY_HEAD,),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable
    _seed_current_t7_pair(database_urls["admin"])

    invalidation_id = UUID("00000000-0000-8000-8000-000000022243")
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.authorization_events"
            "(id,subject_id,event_kind,scope,causation_key,ref_s42_id,ref_s02_id) "
            "VALUES (%s,%s,'EPOCH_INVALIDATED','EXECUTION','kl022-targeted',%s,%s)",
            (invalidation_id, SUBJECT, old_authorization_id, UUID(_SAFETY.RECEIPT_ID)),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "DELETE FROM kineticloop.authorization_events WHERE id=%s", (invalidation_id,)
        )
        connection.execute("SET session_replication_role=origin")

    control_event = UUID("00000000-0000-8000-8000-000000022217")
    control_head = UUID("00000000-0000-8000-8000-000000022218")
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.control_events"
            "(id,subject_id,control_identity,control_revision,scope,status) "
            "VALUES (%s,%s,'kl022-hold',1,'EXECUTION','HOLD')",
            (control_event, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.control_heads"
            "(id,subject_id,control_identity,execution_scope,head_revision,status,ref_s17_id) "
            "VALUES (%s,%s,'kl022-hold','EXECUTION',1,'ACTIVE',%s)",
            (control_head, SUBJECT, control_event),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        for control_state in ("STOP", "RESTRICTION"):
            connection.execute(
                "UPDATE kineticloop.control_events SET status=%s WHERE id=%s",
                (control_state, control_event),
            )
            assert not query().is_executable
        connection.execute(
            "UPDATE kineticloop.control_heads SET status='UNKNOWN' WHERE id=%s", (control_head,)
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable

    clear_event = UUID("00000000-0000-8000-8000-000000022219")
    new_authorization_id = UUID("00000000-0000-8000-8000-000000022242")
    new_authorization_receipt = UUID("00000000-0000-8000-8000-000000022244")
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.command_receipts"
            "(id,subject_id,status,command_kind,client_key,actor_scope,request_hash) "
            "VALUES (%s,%s,'SUCCEEDED','Reauthorize','kl022-new-authorization',"
            "'subject','kl022-new-authorization-hash')",
            (new_authorization_receipt, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.control_events"
            "(id,subject_id,control_identity,control_revision,scope,status) "
            "VALUES (%s,%s,'kl022-hold',2,'EXECUTION','CLEAR')",
            (clear_event, SUBJECT),
        )
        connection.execute(
            "UPDATE kineticloop.control_heads SET head_revision=2,status='CLEARED',ref_s17_id=%s "
            "WHERE id=%s",
            (clear_event, control_head),
        )
        connection.execute(
            "UPDATE kineticloop.user_decision_state SET authorization_epoch=1 WHERE subject_id=%s",
            (SUBJECT,),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.authorization_issuances("
            "id,subject_id,bound_content_hash,scope,issuance_reason,"
            "artifact_dependency_closure_hash,registry_revision_at_issue,valid_from,valid_until,"
            "validity_certificate,ref_s02_id,ref_s05_id,ref_s24_id,ref_s36_id,ref_s37_id,"
            "ref_s40_id,ref_s49_id,registry_state_id) "
            "SELECT %s,subject_id,bound_content_hash,scope,'REVALIDATION',"
            "artifact_dependency_closure_hash,registry_revision_at_issue,valid_from,valid_until,"
            "jsonb_set(validity_certificate,'{authorization_epoch}','1'),%s,ref_s05_id,"
            "ref_s24_id,ref_s36_id,ref_s37_id,ref_s40_id,ref_s49_id,registry_state_id "
            "FROM kineticloop.authorization_issuances WHERE id=%s",
            (new_authorization_id, new_authorization_receipt, old_authorization_id),
        )
        connection.execute(
            "INSERT INTO kineticloop.authorization_artifact_closure"
            "(subject_id,authorization_id,artifact_id,artifact_revision,valid_from,valid_until) "
            "SELECT subject_id,%s,artifact_id,artifact_revision,valid_from,valid_until "
            "FROM kineticloop.authorization_artifact_closure WHERE authorization_id=%s",
            (new_authorization_id, old_authorization_id),
        )
        connection.execute("SET session_replication_role=origin")
    current_authorization_id = new_authorization_id
    assert query().is_executable

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.authorization_artifact_closure "
            "SET valid_from=clock_timestamp()+interval '1 hour' "
            "WHERE authorization_id=%s AND artifact_id=%s",
            (new_authorization_id, DEPENDENCY),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.authorization_artifact_closure "
            "SET valid_from=clock_timestamp()-interval '1 day' "
            "WHERE authorization_id=%s AND artifact_id=%s",
            (new_authorization_id, DEPENDENCY),
        )
        connection.execute(
            "UPDATE kineticloop.authorization_issuances SET valid_until=clock_timestamp() "
            "WHERE id=%s",
            (new_authorization_id,),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query().is_executable
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.authorization_issuances SET valid_until=clock_timestamp()+interval '1 day' "
            "WHERE id=%s",
            (new_authorization_id,),
        )
        start_binding = UUID("00000000-0000-8000-8000-000000022245")
        connection.execute(
            "INSERT INTO kineticloop.execution_bindings"
            "(id,subject_id,binding_kind,execution_scope,binding_revision,accepted_at,"
            "ref_s02_id,ref_s40_id,ref_s42_id,ref_s44_id) "
            "VALUES (%s,%s,'START','EXECUTION',1,clock_timestamp(),%s,%s,%s,%s)",
            (
                start_binding,
                SUBJECT,
                new_authorization_receipt,
                prescription_id,
                new_authorization_id,
                SESSION,
            ),
        )
        connection.execute(
            "UPDATE kineticloop.workout_sessions SET lifecycle='PAUSED' WHERE id=%s", (SESSION,)
        )
        connection.execute("SET session_replication_role=origin")
    assert query("ResumeSession").is_executable

    resume_binding = UUID("00000000-0000-8000-8000-000000022246")
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.execution_bindings"
            "(id,subject_id,binding_kind,execution_scope,binding_revision,accepted_at,"
            "ref_s02_id,ref_s40_id,ref_s42_id,ref_s44_id) "
            "VALUES (%s,%s,'RESUME','EXECUTION',2,clock_timestamp(),%s,%s,%s,%s)",
            (
                resume_binding,
                SUBJECT,
                new_authorization_receipt,
                prescription_id,
                new_authorization_id,
                SESSION,
            ),
        )
        connection.execute(
            "UPDATE kineticloop.workout_sessions SET lifecycle='IN_PROGRESS' WHERE id=%s",
            (SESSION,),
        )
        connection.execute("SET session_replication_role=origin")
        baseline = connection.execute(
            "SELECT (SELECT count(*) FROM kineticloop.execution_bindings),"
            "(SELECT count(*) FROM kineticloop.command_receipts),"
            "(SELECT count(*) FROM kineticloop.domain_events),"
            "(SELECT count(*) FROM kineticloop.outbox_deliveries),"
            "(SELECT execution_revision FROM kineticloop.workout_sessions WHERE id=%s)",
            (SESSION,),
        ).fetchone()
    assert query("ContinueSession").is_executable
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.execution_bindings SET ref_s42_id=%s WHERE id=%s",
            (old_authorization_id, resume_binding),
        )
        connection.execute("SET session_replication_role=origin")
    assert not query("ContinueSession").is_executable
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT (SELECT count(*) FROM kineticloop.execution_bindings),"
            "(SELECT count(*) FROM kineticloop.command_receipts),"
            "(SELECT count(*) FROM kineticloop.domain_events),"
            "(SELECT count(*) FROM kineticloop.outbox_deliveries),"
            "(SELECT execution_revision FROM kineticloop.workout_sessions WHERE id=%s)",
            (SESSION,),
        ).fetchone() == baseline


def test_t6_t7_deny_revoked_transitive_dependency_after_current_registry_read(
    database_urls: dict[str, str],
) -> None:
    _reset_kl022_fixture(database_urls)
    prescription_id, authorization_id = _seed_current_t7_pair(database_urls["admin"])
    unrelated = UUID("00000000-0000-8000-8000-000000022303")
    unrelated_hash = "c" * 64
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.safety_artifacts("
            "id,artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,"
            "valid_from,valid_until,ref_s48_id) VALUES "
            "(%s,'EVALUATION_RELEASE','unrelated-kl022','1',%s,'BOUNDED',"
            "clock_timestamp()-interval '1 day',clock_timestamp()+interval '1 day',%s)",
            (unrelated, unrelated_hash, UUID(_SAFETY.RELEASE_ID)),
        )
        connection.execute("SET session_replication_role=origin")

    def revoke_sql(
        connection: Any,
        artifact_id: UUID,
        content_hash: str,
        key: str,
        incident: UUID,
    ) -> Any:
        effective_at = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        return connection.execute(
            "SELECT * FROM kineticloop.registry_revoke_artifact(%s,%s,%s,%s,%s,%s,%s,%s,5000)",
            (
                artifact_id,
                content_hash,
                effective_at,
                "KL022_TEST_REVOKE",
                revocation_payload_hash(
                    effective_at=effective_at, reason_code="KL022_TEST_REVOKE"
                ),
                key,
                "d" * 64,
                incident,
            ),
        ).fetchone()

    with psycopg.connect(database_urls["trusted_admin"]) as connection:
        assert revoke_sql(
            connection,
            unrelated,
            unrelated_hash,
            "kl022-unrelated-revoke",
            UUID("00000000-0000-8000-8000-000000022304"),
        ) is not None
        connection.commit()
    with psycopg.connect(database_urls["admin"]) as connection:
        assert execute_command(
            connection, "CommitBundle", SUBJECT, lambda tx: _acquire_registry(tx)
        ) >= 1
        assert query_execution_eligibility(
            connection,
            command_kind="StartSession",
            subject_id=SUBJECT,
            artifact_ids=_registry_ids(),
            artifact_identities=_registry_identities(),
            local_date=date(2026, 9, 26),
            session_id=SESSION,
            prescription_id=prescription_id,
            authorization_id=authorization_id,
            execution_scope="EXECUTION",
        ).is_executable

    history_tables = (
        "authorization_issuances",
        "authorization_events",
        "execution_bindings",
        "command_receipts",
        "domain_events",
        "outbox_deliveries",
    )

    def snapshot() -> dict[str, tuple[tuple[Any, ...], ...]]:
        with psycopg.connect(database_urls["admin"]) as connection:
            return {
                table: tuple(
                    connection.execute(
                        psycopg.sql.SQL("SELECT * FROM kineticloop.{} ORDER BY id").format(
                            psycopg.sql.Identifier(table)
                        )
                    ).fetchall()
                )
                for table in history_tables
            }

    before = snapshot()
    blocker = psycopg.connect(
        database_urls["trusted_admin"], application_name="kl022-transitive-revoke"
    )
    assert revoke_sql(
        blocker,
        DEPENDENCY,
        "b" * 64,
        "kl022-transitive-revoke",
        UUID("00000000-0000-8000-8000-000000022305"),
    ) is not None
    outcome: dict[str, object] = {}
    application_name = "kl022-post-wait-registry-reader"

    def waiter() -> None:
        try:
            with psycopg.connect(
                database_urls["admin"], application_name=application_name
            ) as connection:
                execute_command(
                    connection, "CommitBundle", SUBJECT, lambda tx: _acquire_registry(tx)
                )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=waiter)
    thread.start()
    assert _wait_until_database_blocked(database_urls["admin"], application_name)
    blocker.commit()
    blocker.close()
    thread.join(timeout=5)
    assert not thread.is_alive()
    blocked_error = outcome.get("error")
    assert isinstance(blocked_error, psycopg.Error)
    assert "KL_REGISTRY_ARTIFACT_REVOKED" in str(blocked_error)

    for command_kind in ("CommitBundle", "Reauthorize"):
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(psycopg.Error, match="KL_REGISTRY_ARTIFACT_REVOKED"):
                execute_command(
                    connection, command_kind, SUBJECT, lambda tx: _acquire_registry(tx)
                )
    with psycopg.connect(database_urls["admin"]) as connection:
        decision = query_execution_eligibility(
            connection,
            command_kind="StartSession",
            subject_id=SUBJECT,
            artifact_ids=_registry_ids(),
            artifact_identities=_registry_identities(),
            local_date=date(2026, 9, 26),
            session_id=SESSION,
            prescription_id=prescription_id,
            authorization_id=authorization_id,
            execution_scope="EXECUTION",
        )
    assert not decision.is_executable and decision.non_bearer
    assert snapshot() == before
