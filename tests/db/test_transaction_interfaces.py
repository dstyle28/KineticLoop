from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from kineticloop.db.lifecycle import DatabaseLifecycle
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
    replay_outcome,
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
NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


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
            "valid_from": row[7].isoformat(),
            "valid_until": row[8].isoformat() if row[8] is not None else None,
            "timeless_approval_policy": row[9],
            "timeless_approval_reason": row[10],
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
    urls = _MIGRATIONS.bootstrap_two_phase(lifecycle)
    _SAFETY.seed(urls["admin"])
    _seed_transaction_rows(urls["admin"])
    yield urls


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
                NOW,
                NOW + timedelta(days=1),
                POLICY,
                SUBJECT,
                NOW,
                NOW + timedelta(days=30),
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
            "resolution_expires_at,ref_s05_id,ref_s24_id) "
            "VALUES (%s,%s,'PLAN','params','v1','basis',clock_timestamp()+interval '1 day',%s,%s)",
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
        original_payload = connection.execute(
            "SELECT typed_payload FROM kineticloop.factset_revisions WHERE id=%s",
            (FACTSET_BUILD_TEST,),
        ).fetchone()[0]
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
        tx.lock_quota_buckets((("DAILY", NOW, NOW + timedelta(days=1)),))
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
                tx.lock_quota_buckets((("DAILY", NOW, NOW + timedelta(days=1)),))


def test_multi_key_lock_order_is_stable(database_urls: dict[str, str]) -> None:
    traces: list[tuple[tuple[LockStage, str], ...]] = []
    quota_keys = (
        ("DAILY", NOW, NOW + timedelta(days=1)),
        ("MONTHLY", NOW, NOW + timedelta(days=30)),
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
                "quota": lambda: tx.lock_quota_buckets((("DAILY", NOW, NOW + timedelta(days=1)),)),
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
                tx.lock_quota_buckets((("DAILY", NOW, NOW + timedelta(days=1)),))
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

        def wrong_identity(tx: RepositoryTransaction) -> None:
            tx.lock_subject()
            tx.lock_intents((INTENT,))
            tx.require_lease_acquisition_basis(
                INTENT,
                expected_owner_id="worker-a",
                expected_fence=7,
                new_owner_id="worker-a",
                new_fence=8,
                new_lease_expires_at=NOW + timedelta(days=1),
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
        tx.lock_quota_buckets((("DAILY", NOW, NOW + timedelta(days=1)),))
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
                    "lease_expires_at": NOW + timedelta(days=1),
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
            tx.lock_quota_buckets((("DAILY", NOW, NOW + timedelta(days=1)),))
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
                    new_lease_expires_at=NOW + timedelta(days=1),
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
                        acquire_guards(tx),
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

                def acquire(tx: RepositoryTransaction) -> None:
                    tx.lock_subject()
                    tx.lock_intents((INTENT,))
                    tx.require_lease_acquisition_basis(
                        INTENT,
                        expected_owner_id="worker-a",
                        expected_fence=7,
                        new_owner_id="worker-b",
                        new_fence=8,
                        new_lease_expires_at=NOW + timedelta(days=1),
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
                                "lease_expires_at": NOW + timedelta(days=1),
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
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='FOUND_VALID_PLAN',"
            "lease_expires_at=%s,deadline=%s WHERE id=%s",
            (NOW - timedelta(minutes=1), NOW + timedelta(days=2), INTENT),
        )
        connection.execute("SET session_replication_role=origin")
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(FenceLost):
            execute_command(
                connection,
                "ReapIntent",
                SUBJECT,
                lambda tx: (
                    tx.lock_subject(),
                    tx.lock_intents((INTENT,)),
                    tx.require_reaper_basis(
                        INTENT,
                        owner_id="worker-b",
                        fence=8,
                        expected_deadline=NOW + timedelta(days=2),
                        expected_request_revision=1,
                        expected_attempt_id=ATTEMPT,
                    ),
                ),
            )
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',deadline=%s WHERE id=%s",
            (NOW - timedelta(minutes=1), INTENT),
        )
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(FenceLost):
            execute_command(
                connection,
                "ReapIntent",
                SUBJECT,
                lambda tx: (
                    tx.lock_subject(),
                    tx.lock_intents((INTENT,)),
                    tx.require_reaper_basis(
                        INTENT,
                        owner_id="worker-b",
                        fence=8,
                        expected_deadline=NOW - timedelta(minutes=2),
                        expected_request_revision=1,
                        expected_attempt_id=ATTEMPT,
                    ),
                ),
            )
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.planning_intents SET deadline=%s,lease_expires_at=%s WHERE id=%s",
            (NOW + timedelta(days=2), NOW + timedelta(days=1), INTENT),
        )

    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',"
            "deadline=%s,lease_expires_at=%s,current_attempt_id=%s WHERE id=%s",
            (NOW + timedelta(days=2), NOW - timedelta(minutes=1), ATTEMPT, INTENT),
        )

    def reap(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        tx.lock_subject()
        tx.lock_intents((INTENT,))
        tx.lock_reservations((RESERVATION_2,))
        tx.require_reaper_basis(
            INTENT,
            owner_id="worker-b",
            fence=8,
            expected_deadline=NOW + timedelta(days=2),
            expected_request_revision=1,
            expected_attempt_id=ATTEMPT,
        )

        def mutation(session: Any) -> Mapping[str, Any]:
            session.update(
                "S27",
                {"status": "FAILED", "lease_expires_at": NOW - timedelta(minutes=1)},
                {"id": INTENT, "subject_id": SUBJECT},
            )
            session.update(
                "S29",
                {"status": "FAILED", "failure_code": "LEASE_EXPIRED", "completed_at": NOW},
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
        connection.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',lease_owner='worker-a',"
            "fence_token=7,deadline=%s,lease_expires_at=%s WHERE id=%s",
            (NOW + timedelta(days=2), NOW + timedelta(days=1), INTENT),
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
                    tx.lock_subject(),
                    tx.lock_intents((INTENT,)),
                    tx.lock_reservations((RESERVATION,)),
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
        connection.execute(
            "UPDATE kineticloop.planning_intents "
            "SET status='RUNNING',lease_owner='worker-dispatch',fence_token=10,"
            "lease_expires_at=clock_timestamp()+interval '1 day' WHERE id=%s",
            (INTENT,),
        )
        connection.execute(
            "UPDATE kineticloop.planning_intents SET deadline=%s WHERE id=%s",
            (NOW - timedelta(minutes=1), INTENT),
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(FenceLost):
            execute_command(
                connection,
                "PermitDispatch",
                SUBJECT,
                lambda tx: (
                    tx.lock_subject(),
                    tx.lock_intents((INTENT,)),
                    tx.require_current_fence(
                        INTENT,
                        owner_id="worker-dispatch",
                        fence=10,
                        expected_request_revision=1,
                        expected_attempt_id=ATTEMPT,
                    ),
                ),
            )
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        connection.execute(
            "UPDATE kineticloop.planning_intents SET deadline=%s WHERE id=%s",
            (NOW + timedelta(days=2), INTENT),
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
                        tx.lock_subject(),
                        tx.lock_intents((INTENT,)),
                        tx.lock_reservations((RESERVATION_2,)),
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

    def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        tx.lock_subject()
        tx.lock_intents((INTENT,))
        tx.require_lease_acquisition_basis(
            INTENT,
            expected_owner_id="lease-test",
            expected_fence=20,
            new_owner_id="lease-test",
            new_fence=21,
            new_lease_expires_at=datetime.now(UTC) + timedelta(days=1),
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

    with psycopg.connect(database_urls["admin"]) as connection:
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
                    tx.lock_subject(),
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
                    tx.lock_intents((INTENT,)),
                    tx.lock_reservations((RESERVATION_2,)),
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
                    tx.lock_subject(),
                    tx.lock_intents((INTENT,)),
                    tx.lock_reservations((RESERVATION_2,)),
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
                        tx.lock_subject(),
                        tx.lock_intents((INTENT,)),
                        tx.lock_reservations((RESERVATION_2,)),
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

        def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
            tx.lock_subject()
            tx.lock_intents((INTENT_2,))
            tx.require_lease_acquisition_basis(
                INTENT_2,
                expected_owner_id="worker-a",
                expected_fence=7,
                new_owner_id="worker-ack",
                new_fence=8,
                new_lease_expires_at=NOW + timedelta(days=1),
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
                        "lease_expires_at": NOW + timedelta(days=1),
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

        with psycopg.connect(database_urls["admin"]) as connection:
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
                    "VALIDATION",
                    "REQUEST",
                    "POLICY",
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
                                "method_version": "kl015-v1",
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
                    {"status": "COMMITTED", "completed_at": NOW},
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
        manifest_payload = connection.execute(
            "SELECT typed_payload FROM kineticloop.decision_manifests WHERE id=%s",
            (MANIFEST,),
        ).fetchone()[0]
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
    with pytest.raises(GuardRequired, match="expired or undefined"):
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
        ).fetchone() == ("COMMITTED", NOW)
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
        execution_basis = connection.execute(
            "SELECT execution_basis_event_id FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone()[0]
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
                                "method_version": "kl015-v1",
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
                    {"status": "COMMITTED", "completed_at": NOW},
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
            "UPDATE kineticloop.planning_intents SET local_date=DATE '2026-09-27' WHERE id=%s",
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
            payload = connection.execute(
                "SELECT typed_payload FROM kineticloop.manifest_builds WHERE id=%s",
                (MANIFEST_BUILD,),
            ).fetchone()[0]
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
        with pytest.raises(GuardRequired, match="activated policy/release basis"):
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
        selected_policy_payload = connection.execute(
            "SELECT typed_payload FROM kineticloop.policy_bundles WHERE id=%s",
            (POLICY,),
        ).fetchone()[0]
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
        policy_payload = connection.execute(
            "SELECT typed_payload FROM kineticloop.policy_bundles WHERE id=%s",
            (POLICY,),
        ).fetchone()[0]
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
            "VALUES (%s,%s,'EXECUTION','ADMITTED',%s,%s,%s)",
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
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(GuardRequired, match="lifecycle or repeated START"):
            execute_command(
                connection,
                "StartSession",
                SUBJECT,
                lambda tx: (
                    _acquire_registry(tx),
                    tx.lock_daily_head(date(2026, 9, 26)),
                    tx.lock_execution((SESSION,)),
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
