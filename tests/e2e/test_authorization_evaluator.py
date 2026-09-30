from __future__ import annotations

from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from kineticloop.contracts.safety_registry import revocation_payload_hash
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace
from kineticloop.persistence.transactions import ArtifactIdentity, query_execution_eligibility

ROOT = Path(__file__).parents[2]
_SCOPE_SPEC = spec_from_file_location(
    "kl022_e2e_subject_scope_seed", ROOT / "tests/db/test_subject_scope.py"
)
assert _SCOPE_SPEC is not None and _SCOPE_SPEC.loader is not None
_SCOPE: Any = module_from_spec(_SCOPE_SPEC)
_SCOPE_SPEC.loader.exec_module(_SCOPE)

TEST_ARTIFACT = UUID("00000000-0000-8000-8000-000000000261")
TEST_DEPENDENCY = UUID("00000000-0000-8000-8000-000000000262")
TEST_BUNDLE = UUID("00000000-0000-8000-8000-000000022401")
TEST_MEMBER = UUID("00000000-0000-8000-8000-000000022402")
TEST_SESSION = UUID("00000000-0000-8000-8000-000000022403")
TEST_REVOKE_INCIDENT = UUID("00000000-0000-8000-8000-000000022406")


def test_test_subject_eligibility_query_is_current_and_non_bearer() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    lifecycle.namespace = DatabaseNamespace(
        project_name="kineticloop-kl022-e2e-08e743c",
        database_name="kineticloop_kl022_e2e_08e743c",
    )
    try:
        urls = _SCOPE.bootstrap_two_phase(lifecycle)
        _SCOPE.seed(urls)
        subject_id = UUID(_SCOPE.TEST_SUBJECT)
        policy_id = UUID(_SCOPE.TEST_POLICY)
        environment_id = UUID(_SCOPE.TEST_ENVIRONMENT)
        authorization_id = UUID(_SCOPE.TEST_AUTHORIZATION)
        head_id = UUID(_SCOPE.TEST_PLAN)

        # Registration used the canonical trusted-admin routine before protected
        # S38/S42 state existed. Add only the P/A/session relation needed by the
        # read-only evaluator; the seeded authorization is already TEST_ONLY.
        with psycopg.connect(urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "INSERT INTO kineticloop.prescription_revisions("
                "id,subject_id,prescription_identity,prescription_kind,"
                "prescription_revision,content_hash,ref_s34_id,ref_s49_id) "
                "VALUES (%s,%s,'kl022-test-prescription','WORKOUT',1,"
                "'authorization-content',%s,%s)",
                (policy_id, subject_id, policy_id, TEST_ARTIFACT),
            )
            connection.execute(
                "INSERT INTO kineticloop.daily_bundle_revisions("
                "id,subject_id,local_date,generation_mode,revision_no,ref_s02_id,"
                "ref_s24_id,ref_s27_id,ref_s29_id,ref_s37_id,ref_s38_id) "
                "SELECT %s,%s,DATE '2026-09-26','TEST_FIXTURE',1,ref_s02_id,"
                "ref_s24_id,%s,%s,ref_s37_id,%s "
                "FROM kineticloop.authorization_issuances WHERE id=%s",
                (
                    TEST_BUNDLE,
                    subject_id,
                    policy_id,
                    policy_id,
                    head_id,
                    authorization_id,
                ),
            )
            connection.execute(
                "INSERT INTO kineticloop.bundle_prescription_members("
                "id,subject_id,member_kind,session_slot,member_order,ref_s39_id,ref_s40_id) "
                "VALUES (%s,%s,'PRESCRIPTION','e2e',1,%s,%s)",
                (TEST_MEMBER, subject_id, TEST_BUNDLE, policy_id),
            )
            connection.execute(
                "UPDATE kineticloop.daily_plan_heads SET head_revision=1,"
                "current_bundle_revision_id=%s WHERE id=%s AND subject_id=%s",
                (TEST_BUNDLE, head_id, subject_id),
            )
            connection.execute(
                "INSERT INTO kineticloop.workout_sessions("
                "id,subject_id,session_identity,origin,lifecycle,execution_revision) "
                "VALUES (%s,%s,'kl022-test-session','TEST','READY',0)",
                (TEST_SESSION, subject_id),
            )
            connection.execute("SET session_replication_role=origin")
            assert connection.execute(
                "SELECT namespace,policy_id,environment_id "
                "FROM kineticloop.subject_scopes WHERE subject_id=%s",
                (subject_id,),
            ).fetchone() == ("TEST", policy_id, environment_id)
            assert connection.execute(
                "SELECT scope,ref_s05_id FROM kineticloop.authorization_issuances WHERE id=%s",
                (authorization_id,),
            ).fetchone() == ("TEST_ONLY", policy_id)

        # A bound TEST principal sees exactly its own protected S42 through the
        # canonical lookup; no bypass-created scope or binding participates.
        with psycopg.connect(urls["test"]) as connection:
            scoped = connection.execute(
                "SELECT kineticloop.subject_scope_lookup('S42',%s)",
                (authorization_id,),
            ).fetchone()
            assert scoped is not None and scoped[0]["subject_id"] == str(subject_id)
            assert scoped[0]["namespace"] == "TEST"

        artifact_ids = (TEST_ARTIFACT, TEST_DEPENDENCY)
        artifact_identities = (
            ArtifactIdentity(
                TEST_ARTIFACT,
                "POLICY_BUNDLE",
                "artifact-test",
                "1",
                "a" * 64,
            ),
            ArtifactIdentity(
                TEST_DEPENDENCY,
                "EVALUATION_RELEASE",
                "dependency-test",
                "1",
                "b" * 64,
            ),
        )

        def current_query() -> Any:
            # This is the migrated service evaluator boundary. It returns only a
            # current observation and never performs a T7 mutation.
            with psycopg.connect(urls["admin"]) as connection:
                return query_execution_eligibility(
                    connection,
                    command_kind="StartSession",
                    subject_id=subject_id,
                    artifact_ids=artifact_ids,
                    artifact_identities=artifact_identities,
                    local_date=date(2026, 9, 26),
                    session_id=TEST_SESSION,
                    prescription_id=policy_id,
                    authorization_id=authorization_id,
                    execution_scope="TEST_ONLY",
                )

        first = current_query()
        assert first.is_executable and first.non_bearer
        assert not hasattr(first, "permission_token")
        with psycopg.connect(urls["admin"]) as connection:
            baseline = connection.execute(
                "SELECT (SELECT count(*) FROM kineticloop.execution_bindings),"
                "(SELECT count(*) FROM kineticloop.command_receipts),"
                "(SELECT count(*) FROM kineticloop.domain_events),"
                "(SELECT count(*) FROM kineticloop.outbox_deliveries)"
            ).fetchone()

        with psycopg.connect(urls["trusted_admin"]) as connection:
            effective_at_row = connection.execute("SELECT clock_timestamp()").fetchone()
            assert effective_at_row is not None
            effective_at = effective_at_row[0]
            revoked = connection.execute(
                "SELECT * FROM kineticloop.registry_revoke_artifact("
                "%s,%s,%s,%s,%s,%s,%s,%s,5000)",
                (
                    TEST_DEPENDENCY,
                    "b" * 64,
                    effective_at,
                    "KL022_E2E_REVOKE",
                    revocation_payload_hash(
                        effective_at=effective_at, reason_code="KL022_E2E_REVOKE"
                    ),
                    "kl022-e2e-revoke",
                    "e" * 64,
                    TEST_REVOKE_INCIDENT,
                ),
            ).fetchone()
            assert revoked is not None
            connection.commit()

        second = current_query()
        assert not second.is_executable and second.non_bearer
        with psycopg.connect(urls["admin"]) as connection:
            assert connection.execute(
                "SELECT (SELECT count(*) FROM kineticloop.execution_bindings),"
                "(SELECT count(*) FROM kineticloop.command_receipts),"
                "(SELECT count(*) FROM kineticloop.domain_events),"
                "(SELECT count(*) FROM kineticloop.outbox_deliveries)"
            ).fetchone() == baseline
    finally:
        lifecycle.destroy()
