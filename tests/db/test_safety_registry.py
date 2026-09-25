from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg import Connection

from kineticloop.contracts.commands import RevokeArtifact, TransactionBoundary, TrustedActor
from kineticloop.contracts.safety_registry import (
    RegistryCommand,
    RegistryDenialCode,
    RegistryDenied,
    RegistryEligibility,
    revocation_payload_hash,
)
from kineticloop.db.lifecycle import DatabaseLifecycle
from kineticloop.identity import ActorRole
from kineticloop.persistence.safety_registry import (
    RegistryTransactionStateError,
    RevocationResult,
    execute_shared_registry_command,
    execute_stop_without_registry,
    revoke_artifact,
)
from kineticloop.primitives.times import canonical_utc

ROOT = Path(__file__).parents[2]
_MIGRATION_TEST_SPEC = spec_from_file_location(
    "kl072_test_migrations", ROOT / "tests/db/test_migrations.py"
)
assert _MIGRATION_TEST_SPEC is not None and _MIGRATION_TEST_SPEC.loader is not None
_MIGRATION_TESTS = module_from_spec(_MIGRATION_TEST_SPEC)
_MIGRATION_TEST_SPEC.loader.exec_module(_MIGRATION_TESTS)
bootstrap_two_phase: Any = _MIGRATION_TESTS.bootstrap_two_phase
SUBJECT_ID = "00000000-0000-8000-8000-000000000001"
CALLER_ADMIN_ID = "00000000-0000-8000-8000-000000000002"
ARTIFACT_ID = "00000000-0000-8000-8000-000000000003"
DEPENDENCY_ID = "00000000-0000-8000-8000-000000000004"
INCIDENT_ID = "00000000-0000-8000-8000-000000000005"
MISSING_ID = "00000000-0000-8000-8000-000000000007"
POLICY_ID = "00000000-0000-8000-8000-000000000008"
RELEASE_ID = "00000000-0000-8000-8000-000000000009"
MANIFEST_ID = "00000000-0000-8000-8000-00000000000a"
AUTHORIZATION_ID = "00000000-0000-8000-8000-00000000000b"
RECEIPT_ID = "00000000-0000-8000-8000-00000000000c"
EVENT_ID = "00000000-0000-8000-8000-00000000000d"
OUTBOX_ID = "00000000-0000-8000-8000-00000000000e"
CONTENT_HASH = "a" * 64
NOW = datetime(2026, 9, 24, 18, tzinfo=UTC)


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    lifecycle = DatabaseLifecycle(ROOT)
    yield bootstrap_two_phase(lifecycle)


@pytest.fixture
def db_urls(database_urls: dict[str, str]) -> dict[str, str]:
    seed(database_urls["admin"])
    return database_urls


def connect(url: str, *, name: str = "kl072-test") -> Connection[Any]:
    return psycopg.connect(url, application_name=name)


def seed(
    admin_url: str,
    *,
    expires_at: datetime | None = None,
    valid_from: datetime | None = None,
    authorization_expires_at: datetime | None = None,
) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        seed_now = datetime.now(UTC)
        connection.execute("SET session_replication_role = replica")
        connection.execute(
            "TRUNCATE kineticloop.registry_outbox, kineticloop.registry_audit_events, "
            "kineticloop.registry_management_receipts, kineticloop.artifact_revocation_events, "
            "kineticloop.authorization_artifact_closure, kineticloop.authorization_issuances, "
            "kineticloop.decision_manifests, "
            "kineticloop.outbox_deliveries, kineticloop.domain_events, "
            "kineticloop.command_receipts, "
            "kineticloop.safety_artifact_dependencies, kineticloop.safety_artifacts, "
            "kineticloop.user_decision_state, kineticloop.policy_bundles, "
            "kineticloop.evaluation_releases CASCADE"
        )
        connection.execute(
            "INSERT INTO kineticloop.safety_registry_state(id,registry_revision,last_revocation_id) "
            "VALUES (1,0,NULL) ON CONFLICT (id) DO UPDATE SET registry_revision=0, "
            "last_revocation_id=NULL"
        )
        connection.execute("DROP TABLE IF EXISTS public.domain_mutations")
        connection.execute(
            "CREATE TABLE public.domain_mutations ("
            "mutation_id bigserial PRIMARY KEY, command_kind text NOT NULL, "
            "registry_revision bigint, subject_id uuid NOT NULL, protected_at timestamptz)"
        )
        connection.execute("ALTER TABLE public.domain_mutations OWNER TO kl_application_login")
        connection.execute("GRANT INSERT ON public.domain_mutations TO kl_stop_login")
        connection.execute(
            "GRANT USAGE, SELECT ON SEQUENCE public.domain_mutations_mutation_id_seq "
            "TO kl_stop_login"
        )
        connection.execute(
            "INSERT INTO kineticloop.policy_bundles"
            "(id,subject_id,policy_namespace,policy_version,content_hash) "
            "VALUES (%s,%s,'registry-test','1','policy-hash')",
            (UUID(POLICY_ID), UUID(SUBJECT_ID)),
        )
        connection.execute(
            "INSERT INTO kineticloop.evaluation_releases"
            "(id,subject_id,release_namespace,release_version) "
            "VALUES (%s,%s,'registry-test','1')",
            (UUID(RELEASE_ID), UUID(SUBJECT_ID)),
        )
        connection.execute(
            """
            INSERT INTO kineticloop.safety_artifacts(
              id, artifact_kind, artifact_identity, artifact_version, content_hash,
              validity_kind, valid_from, valid_until, ref_s05_id, ref_s48_id
            ) VALUES
              (%s,'EVALUATION_RELEASE','dependency','1',%s,'BOUNDED',
               %s,%s,NULL,%s),
              (%s,'POLICY_BUNDLE','artifact','1',%s,'BOUNDED',
               %s,%s,%s,NULL)
            """,
            (
                UUID(DEPENDENCY_ID),
                "b" * 64,
                valid_from or seed_now - timedelta(days=1),
                expires_at or seed_now + timedelta(days=30),
                UUID(RELEASE_ID),
                UUID(ARTIFACT_ID),
                CONTENT_HASH,
                valid_from or seed_now - timedelta(days=1),
                expires_at or seed_now + timedelta(days=30),
                UUID(POLICY_ID),
            ),
        )
        connection.execute(
            "INSERT INTO kineticloop.safety_artifact_dependencies"
            "(artifact_id,dependency_artifact_id) VALUES (%s,%s)",
            (UUID(ARTIFACT_ID), UUID(DEPENDENCY_ID)),
        )
        connection.execute(
            "INSERT INTO kineticloop.command_receipts("
            "id,subject_id,status,command_kind,client_key,actor_scope,request_hash) "
            "VALUES (%s,%s,'SUCCEEDED','IssueAuthorization','seed-authorization',"
            "'subject','seed-request-hash')",
            (UUID(RECEIPT_ID), UUID(SUBJECT_ID)),
        )
        connection.execute(
            "INSERT INTO kineticloop.domain_events("
            "id,subject_id,aggregate_type,aggregate_identity,event_type,"
            "aggregate_revision,ref_s02_id) "
            "VALUES (%s,%s,'Authorization','seed-authorization','AuthorizationIssued',1,%s)",
            (UUID(EVENT_ID), UUID(SUBJECT_ID), UUID(RECEIPT_ID)),
        )
        connection.execute(
            "INSERT INTO kineticloop.outbox_deliveries("
            "id,subject_id,destination,delivery_status,attempt_count,ref_s03_id) "
            "VALUES (%s,%s,'authorization-events','PENDING',0,%s)",
            (UUID(OUTBOX_ID), UUID(SUBJECT_ID), UUID(EVENT_ID)),
        )
        connection.execute(
            """
            INSERT INTO kineticloop.decision_manifests(
              id, subject_id, manifest_hash, generation, captured_epoch,
              registry_revision_at_publish, valid_until, ref_s05_id, ref_s06_id,
              ref_s15_id, ref_s23_id, ref_s49_id, registry_state_id
            ) VALUES (%s,%s,'manifest-hash',1,0,0,%s,%s,%s,%s,%s,%s,1)
            """,
            (
                UUID(MANIFEST_ID), UUID(SUBJECT_ID),
                authorization_expires_at or seed_now + timedelta(days=1),
                UUID(POLICY_ID), UUID(POLICY_ID), UUID(POLICY_ID),
                UUID(POLICY_ID), UUID(ARTIFACT_ID),
            ),
        )
        connection.execute(
            """
            INSERT INTO kineticloop.authorization_issuances(
              id, subject_id, bound_content_hash, scope,
              artifact_dependency_closure_hash, registry_revision_at_issue,
              valid_from, valid_until, validity_certificate, ref_s02_id,
              ref_s05_id, ref_s24_id, ref_s36_id, ref_s37_id, ref_s40_id,
              ref_s49_id, registry_state_id
            ) VALUES (
              %s,%s,'authorization-content','EXECUTION','closure-hash',0,
              %s,%s,'{"authorization_epoch": 0}'::jsonb,%s,%s,%s,%s,%s,%s,%s,1
            )
            """,
            (
                UUID(AUTHORIZATION_ID), UUID(SUBJECT_ID),
                seed_now - timedelta(days=1),
                authorization_expires_at or seed_now + timedelta(days=1),
                UUID(RECEIPT_ID), UUID(POLICY_ID), UUID(MANIFEST_ID),
                UUID(POLICY_ID), UUID(POLICY_ID), UUID(POLICY_ID), UUID(ARTIFACT_ID),
            ),
        )
        for artifact_id in (ARTIFACT_ID, DEPENDENCY_ID):
            connection.execute(
                "INSERT INTO kineticloop.authorization_artifact_closure"
                "(subject_id,authorization_id,artifact_id,artifact_revision,valid_from,valid_until) "
                "VALUES (%s,%s,%s,1,%s,%s)",
                (
                    UUID(SUBJECT_ID), UUID(AUTHORIZATION_ID), UUID(artifact_id),
                    seed_now - timedelta(days=1),
                    authorization_expires_at or seed_now + timedelta(days=1),
                ),
            )
        connection.execute(
            "INSERT INTO kineticloop.user_decision_state"
            "(subject_id,authorization_epoch,current_manifest_id,active_policy_bundle_id) "
            "VALUES (%s,0,%s,%s)",
            (UUID(SUBJECT_ID), UUID(MANIFEST_ID), UUID(POLICY_ID)),
        )
        connection.execute("SET session_replication_role = origin")


def eligibility(
    command: RegistryCommand,
    *,
    minimum_revision: int = 0,
    artifact_ids: tuple[str, ...] = (ARTIFACT_ID, DEPENDENCY_ID),
) -> RegistryEligibility:
    return RegistryEligibility(
        command=command,
        subject_id=SUBJECT_ID,
        artifact_ids=artifact_ids,
        minimum_registry_revision=minimum_revision,
    )


def mutate(command: RegistryCommand) -> Any:
    def operation(cursor: Any, registry_revision: int) -> int:
        cursor.execute(
            "INSERT INTO public.domain_mutations(command_kind,registry_revision,subject_id) "
            "VALUES (%s,%s,%s) RETURNING mutation_id",
            (command.value, registry_revision, UUID(SUBJECT_ID)),
        )
        row = cursor.fetchone()
        assert row is not None
        return int(row[0])

    return operation


def mutation_count(admin_url: str) -> int:
    with connect(admin_url) as connection:
        row = connection.execute("SELECT count(*) FROM public.domain_mutations").fetchone()
        assert row is not None
        return int(row[0])


def assert_denied(
    urls: dict[str, str],
    command_kind: RegistryCommand,
    code: RegistryDenialCode,
    *,
    request: RegistryEligibility | None = None,
) -> None:
    with connect(urls["application"]) as connection:
        with pytest.raises(RegistryDenied) as denial:
            execute_shared_registry_command(
                connection, request or eligibility(command_kind), mutate(command_kind)
            )
    assert denial.value.code is code
    assert mutation_count(urls["admin"]) == 0


def wait_until_blocked(admin_url: str, application_name: str) -> None:
    deadline = time.monotonic() + 5
    with connect(admin_url) as observer:
        while time.monotonic() < deadline:
            row = observer.execute(
                "SELECT cardinality(pg_blocking_pids(pid)) FROM pg_stat_activity "
                "WHERE application_name=%s AND state<>'idle'",
                (application_name,),
            ).fetchone()
            observer.rollback()
            if row is not None and row[0] > 0:
                return
            time.sleep(0.02)
    raise AssertionError(f"{application_name} did not block")


def wait_until_database_time(admin_url: str, target: datetime) -> None:
    deadline = time.monotonic() + 5
    with psycopg.connect(admin_url, autocommit=True) as observer:
        while time.monotonic() < deadline:
            row = observer.execute("SELECT clock_timestamp() >= %s", (target,)).fetchone()
            if row is not None and row[0]:
                return
            time.sleep(0.02)
    raise AssertionError(f"database clock did not reach {target.isoformat()}")


def invoke_revoke_sql(
    connection: Connection[Any],
    *,
    key: str,
    request_hash: str = "d" * 64,
    effective_at: datetime = NOW,
    reason_code: str = "EMERGENCY",
    payload_hash: str | None = None,
) -> Any:
    return connection.execute(
        "SELECT * FROM kineticloop.registry_revoke_artifact(%s,%s,%s,%s,%s,%s,%s,%s,5000)",
        (
            UUID(ARTIFACT_ID), CONTENT_HASH, effective_at, reason_code,
            payload_hash or revocation_payload_hash(
                effective_at=effective_at, reason_code=reason_code
            ),
            key, request_hash, UUID(INCIDENT_ID),
        ),
    ).fetchone()


def run_revoke_first_then_shared_denies(
    urls: dict[str, str], command_kind: RegistryCommand
) -> None:
    seed(urls["admin"])
    blocker = connect(urls["trusted_admin"], name=f"revoke-first-{command_kind.value}")
    assert invoke_revoke_sql(blocker, key=f"revoke-first-{command_kind.value}") is not None
    outcome: dict[str, object] = {}
    app_name = f"shared-after-revoke-{command_kind.value}"

    def worker() -> None:
        try:
            with connect(urls["application"], name=app_name) as connection:
                execute_shared_registry_command(
                    connection, eligibility(command_kind), mutate(command_kind),
                    lock_timeout_ms=5_000,
                )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    wait_until_blocked(urls["admin"], app_name)
    with connect(urls["admin"]) as observer:
        observer.execute("SET LOCAL lock_timeout='100ms'")
        observer.execute(
            "SELECT subject_id FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s FOR UPDATE",
            (UUID(SUBJECT_ID),),
        )
    blocker.commit()
    blocker.close()
    thread.join(timeout=5)
    assert not thread.is_alive()
    error = outcome.get("error")
    assert isinstance(error, RegistryDenied)
    assert error.code is RegistryDenialCode.ARTIFACT_REVOKED
    assert mutation_count(urls["admin"]) == 0


def revoke_command(
    *,
    key: str = "revoke-1",
    request_hash: str = "d" * 64,
    effective_at: datetime = NOW,
    reason_code: str = "EMERGENCY",
) -> RevokeArtifact:
    return RevokeArtifact(
        schema_version="kineticloop-command-v1",
        command_kind="RevokeArtifact",
        boundary=TransactionBoundary.T2_GLOBAL,
        command_id="00000000-0000-8000-8000-000000000007",
        actor=TrustedActor(
            schema="kineticloop-role-identity-v1",
            identity_id=CALLER_ADMIN_ID,
            role=ActorRole.ADMIN,
        ),
        idempotency_key=key,
        request_hash=request_hash,
        subject_id=None,
        explicit_scope="global:safety-registry",
        artifact_id=ARTIFACT_ID,
        artifact_content_hash=CONTENT_HASH,
        revocation_payload_hash=revocation_payload_hash(
            effective_at=effective_at, reason_code=reason_code
        ),
        causation_incident_id=INCIDENT_ID,
    )


def test_shared_gate_command_matrix_fails_closed(db_urls: dict[str, str]) -> None:
    for command_kind in RegistryCommand:
        run_revoke_first_then_shared_denies(db_urls, command_kind)
        seed(db_urls["admin"])
        with connect(db_urls["application"]) as connection:
            assert (
                execute_shared_registry_command(
                    connection, eligibility(command_kind), mutate(command_kind)
                )
                == 1
            )
        assert mutation_count(db_urls["admin"]) == 1

        seed(db_urls["admin"])
        assert_denied(
            db_urls,
            command_kind,
            RegistryDenialCode.ARTIFACT_UNKNOWN,
            request=eligibility(
                command_kind, artifact_ids=(ARTIFACT_ID, DEPENDENCY_ID, MISSING_ID)
            ),
        )
        seed(db_urls["admin"])
        assert_denied(
            db_urls,
            command_kind,
            RegistryDenialCode.DEPENDENCY_INCOMPLETE,
            request=eligibility(command_kind, artifact_ids=(ARTIFACT_ID,)),
        )
        seed(db_urls["admin"], expires_at=datetime.now(UTC) - timedelta(seconds=1))
        assert_denied(db_urls, command_kind, RegistryDenialCode.ARTIFACT_EXPIRED)
        seed(db_urls["admin"], valid_from=datetime.now(UTC) + timedelta(days=1))
        assert_denied(db_urls, command_kind, RegistryDenialCode.ARTIFACT_EXPIRED)
        seed(db_urls["admin"])
        assert_denied(
            db_urls,
            command_kind,
            RegistryDenialCode.REGISTRY_STALE,
            request=eligibility(command_kind, minimum_revision=1),
        )
        seed(db_urls["admin"])
        with connect(db_urls["admin"]) as blocker:
            blocker.execute(
                "SELECT registry_revision FROM kineticloop.safety_registry_state "
                "WHERE id=1 FOR UPDATE"
            )
            with connect(db_urls["application"]) as connection:
                with pytest.raises(RegistryDenied) as denial:
                    execute_shared_registry_command(
                        connection,
                        eligibility(command_kind),
                        mutate(command_kind),
                        lock_timeout_ms=50,
                    )
            assert denial.value.code is RegistryDenialCode.REGISTRY_TIMEOUT
            blocker.rollback()
        seed(db_urls["admin"])
        with connect(db_urls["admin"]) as admin:
            admin.execute("SET LOCAL session_replication_role = replica")
            admin.execute("DELETE FROM kineticloop.safety_registry_state WHERE id=1")
            admin.commit()
        assert_denied(db_urls, command_kind, RegistryDenialCode.REGISTRY_UNAVAILABLE)
        with connect(db_urls["admin"]) as admin:
            admin.execute(
                "INSERT INTO kineticloop.safety_registry_state(id,registry_revision) VALUES (1,0)"
            )
            admin.commit()
        seed(db_urls["admin"])
        with connect(db_urls["admin"]) as admin:
            admin.execute(
                "DELETE FROM kineticloop.user_decision_state WHERE subject_id=%s",
                (UUID(SUBJECT_ID),),
            )
            admin.commit()
        assert_denied(db_urls, command_kind, RegistryDenialCode.AUTHORIZATION_INELIGIBLE)

        if command_kind is not RegistryCommand.PUBLISH_MANIFEST:
            seed(db_urls["admin"])
            with connect(db_urls["admin"]) as admin:
                admin.execute(
                    "UPDATE kineticloop.user_decision_state "
                    "SET authorization_epoch=authorization_epoch+1 WHERE subject_id=%s",
                    (UUID(SUBJECT_ID),),
                )
                admin.commit()
            assert_denied(
                db_urls, command_kind, RegistryDenialCode.AUTHORIZATION_INELIGIBLE
            )


def test_migrated_schema_rejects_undefined_artifact_validity(
    db_urls: dict[str, str],
) -> None:
    with connect(db_urls["admin"]) as admin:
        admin.execute("SET LOCAL session_replication_role=replica")
        with pytest.raises(psycopg.errors.NotNullViolation):
            admin.execute(
                "INSERT INTO kineticloop.safety_artifacts("
                "id,artifact_kind,artifact_identity,artifact_version,content_hash,"
                "validity_kind,valid_from) VALUES (%s,'POLICY_BUNDLE','undefined','1',%s,NULL,NULL)",
                (UUID(MISSING_ID), "f" * 64),
            )
        admin.rollback()
    assert mutation_count(db_urls["admin"]) == 0


def test_reauthorize_shared_gate_precedes_s01_and_fails_closed(
    db_urls: dict[str, str],
) -> None:
    blocker = connect(db_urls["admin"], name="exclusive-before-reauthorize")
    blocker.execute(
        "SELECT registry_revision FROM kineticloop.safety_registry_state WHERE id=1 FOR UPDATE"
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            with connect(db_urls["application"], name="waiting-reauthorize") as connection:
                outcome["result"] = execute_shared_registry_command(
                    connection,
                    eligibility(RegistryCommand.REAUTHORIZE),
                    mutate(RegistryCommand.REAUTHORIZE),
                    lock_timeout_ms=5_000,
                )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    wait_until_blocked(db_urls["admin"], "waiting-reauthorize")
    with connect(db_urls["admin"]) as observer:
        observer.execute("SET LOCAL lock_timeout='100ms'")
        observer.execute(
            "SELECT subject_id FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
            (UUID(SUBJECT_ID),),
        )
    blocker.rollback()
    blocker.close()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert outcome.get("result") == 1


def test_continue_session_rechecks_shared_gate_and_fails_closed(
    db_urls: dict[str, str],
) -> None:
    seed(db_urls["admin"], expires_at=datetime.now(UTC) + timedelta(milliseconds=400))
    subject_lock = connect(db_urls["admin"], name="subject-expiry-blocker")
    subject_lock.execute(
        "SELECT subject_id FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
        (UUID(SUBJECT_ID),),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            with connect(db_urls["application"], name="continue-after-expiry") as connection:
                execute_shared_registry_command(
                    connection,
                    eligibility(RegistryCommand.CONTINUE_SESSION),
                    mutate(RegistryCommand.CONTINUE_SESSION),
                    lock_timeout_ms=5_000,
                )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    wait_until_blocked(db_urls["admin"], "continue-after-expiry")
    time.sleep(0.5)
    subject_lock.commit()
    subject_lock.close()
    thread.join(timeout=5)
    error = outcome.get("error")
    assert isinstance(error, RegistryDenied)
    assert error.code is RegistryDenialCode.ARTIFACT_EXPIRED
    assert mutation_count(db_urls["admin"]) == 0

    authorization_expiry = datetime.now(UTC) + timedelta(milliseconds=400)
    seed(db_urls["admin"], authorization_expires_at=authorization_expiry)
    subject_lock = connect(db_urls["admin"], name="subject-authorization-expiry-blocker")
    subject_lock.execute(
        "SELECT subject_id FROM kineticloop.user_decision_state "
        "WHERE subject_id=%s FOR UPDATE",
        (UUID(SUBJECT_ID),),
    )
    outcome = {}

    def authorization_worker() -> None:
        try:
            with connect(db_urls["application"], name="continue-after-auth-expiry") as connection:
                execute_shared_registry_command(
                    connection,
                    eligibility(RegistryCommand.CONTINUE_SESSION),
                    mutate(RegistryCommand.CONTINUE_SESSION),
                    lock_timeout_ms=5_000,
                )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=authorization_worker)
    thread.start()
    wait_until_blocked(db_urls["admin"], "continue-after-auth-expiry")
    wait_until_database_time(db_urls["admin"], authorization_expiry)
    subject_lock.commit()
    subject_lock.close()
    thread.join(timeout=5)
    assert not thread.is_alive()
    error = outcome.get("error")
    assert isinstance(error, RegistryDenied)
    assert error.code is RegistryDenialCode.AUTHORIZATION_INELIGIBLE
    assert mutation_count(db_urls["admin"]) == 0


def test_exclusive_global_gate_serializes(db_urls: dict[str, str]) -> None:
    shared = connect(db_urls["application"], name="held-shared")
    shared.execute(
        "SELECT kineticloop.registry_guard_start_session(%s,%s,0,5000)",
        (UUID(SUBJECT_ID), [UUID(ARTIFACT_ID), UUID(DEPENDENCY_ID)]),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            with connect(db_urls["trusted_admin"], name="exclusive-revoke") as connection:
                outcome["result"] = revoke_artifact(
                    connection,
                    revoke_command(),
                    effective_at=NOW,
                    reason_code="EMERGENCY",
                    lock_timeout_ms=5_000,
                )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    time.sleep(0.1)
    assert "error" not in outcome, repr(outcome.get("error"))
    wait_until_blocked(db_urls["admin"], "exclusive-revoke")
    assert "result" not in outcome
    shared.commit()
    shared.close()
    thread.join(timeout=5)
    assert not thread.is_alive() and "error" not in outcome
    result = outcome["result"]
    assert isinstance(result, RevocationResult)
    assert result.registry_revision == 1

    seed(db_urls["admin"])
    mutation_entered = threading.Event()
    allow_commit = threading.Event()
    shared_outcome: dict[str, object] = {}
    revoke_outcome: dict[str, object] = {}

    def held_mutation(cursor: Any, registry_revision: int) -> int:
        result_id = mutate(RegistryCommand.START_SESSION)(cursor, registry_revision)
        mutation_entered.set()
        assert allow_commit.wait(timeout=5)
        cursor.execute(
            "UPDATE public.domain_mutations SET protected_at=clock_timestamp() "
            "WHERE mutation_id=%s",
            (result_id,),
        )
        return result_id

    def shared_worker() -> None:
        try:
            with connect(db_urls["application"], name="protected-mutation-first") as connection:
                shared_outcome["result"] = execute_shared_registry_command(
                    connection,
                    eligibility(RegistryCommand.START_SESSION),
                    held_mutation,
                    lock_timeout_ms=5_000,
                )
        except BaseException as error:
            shared_outcome["error"] = error

    def revoke_worker() -> None:
        try:
            with connect(db_urls["trusted_admin"], name="revoke-after-protected-mutation") as connection:
                revoke_outcome["result"] = revoke_artifact(
                    connection, revoke_command(), effective_at=NOW,
                    reason_code="EMERGENCY", lock_timeout_ms=5_000,
                )
        except BaseException as error:
            revoke_outcome["error"] = error

    shared_thread = threading.Thread(target=shared_worker)
    shared_thread.start()
    assert mutation_entered.wait(timeout=5)
    revoke_thread = threading.Thread(target=revoke_worker)
    revoke_thread.start()
    wait_until_blocked(db_urls["admin"], "revoke-after-protected-mutation")
    assert "result" not in revoke_outcome
    allow_commit.set()
    shared_thread.join(timeout=5)
    revoke_thread.join(timeout=5)
    assert not shared_thread.is_alive() and not revoke_thread.is_alive()
    assert "error" not in shared_outcome and "error" not in revoke_outcome
    assert shared_outcome["result"] == 1
    assert isinstance(revoke_outcome["result"], RevocationResult)
    assert mutation_count(db_urls["admin"]) == 1
    with connect(db_urls["admin"]) as observer:
        ordering = observer.execute(
            "SELECT mutation.protected_at, revocation.recorded_at "
            "FROM public.domain_mutations mutation "
            "CROSS JOIN kineticloop.artifact_revocation_events revocation"
        ).fetchone()
        assert ordering is not None
        assert ordering[0] is not None and ordering[0] <= ordering[1]


def registry_counts(admin_url: str) -> tuple[int, int, int, int]:
    with connect(admin_url) as connection:
        row = connection.execute(
            "SELECT (SELECT count(*) FROM kineticloop.artifact_revocation_events),"
            "(SELECT count(*) FROM kineticloop.registry_management_receipts),"
            "(SELECT count(*) FROM kineticloop.registry_audit_events),"
            "(SELECT count(*) FROM kineticloop.registry_outbox)"
        ).fetchone()
        assert row is not None
        return int(row[0]), int(row[1]), int(row[2]), int(row[3])


def test_revoke_artifact_atomic_linearization_and_idempotency(
    db_urls: dict[str, str],
) -> None:
    with connect(db_urls["admin"]) as admin:
        future_row = admin.execute(
            "SELECT clock_timestamp() + interval '7 days'"
        ).fetchone()
        assert future_row is not None
        future_effective = future_row[0]
        historical_authorization = admin.execute(
            "SELECT id,valid_from,valid_until FROM kineticloop.authorization_issuances "
            "WHERE id=%s", (UUID(AUTHORIZATION_ID),)
        ).fetchone()
        assert historical_authorization is not None
    with psycopg.connect(db_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "CREATE FUNCTION public.fail_registry_outbox() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected outbox failure'; END $$"
        )
        admin.execute(
            "CREATE TRIGGER fail_registry_outbox BEFORE INSERT ON kineticloop.registry_outbox "
            "FOR EACH ROW EXECUTE FUNCTION public.fail_registry_outbox()"
        )
    with connect(db_urls["trusted_admin"]) as connection:
        with pytest.raises(psycopg.errors.RaiseException, match="injected outbox failure"):
            revoke_artifact(
                connection, revoke_command(effective_at=future_effective),
                effective_at=future_effective, reason_code="EMERGENCY"
            )
    assert registry_counts(db_urls["admin"]) == (0, 0, 0, 0)
    with psycopg.connect(db_urls["admin"], autocommit=True) as admin:
        admin.execute("DROP TRIGGER fail_registry_outbox ON kineticloop.registry_outbox")
        admin.execute("DROP FUNCTION public.fail_registry_outbox()")
    with connect(db_urls["trusted_admin"]) as connection:
        first = revoke_artifact(
            connection, revoke_command(effective_at=future_effective),
            effective_at=future_effective, reason_code="EMERGENCY"
        )
    assert first.registry_revision == 1
    assert first.effective_at == future_effective
    assert first.effective_at > first.recorded_at
    assert registry_counts(db_urls["admin"]) == (1, 1, 1, 1)
    with connect(db_urls["trusted_admin"]) as connection:
        replay = revoke_artifact(
            connection, revoke_command(effective_at=future_effective),
            effective_at=future_effective, reason_code="EMERGENCY"
        )
    assert replay == first
    with connect(db_urls["trusted_admin"]) as connection:
        with pytest.raises(RegistryDenied) as denial:
            revoke_artifact(
                connection,
                revoke_command(request_hash="f" * 64, effective_at=future_effective),
                effective_at=future_effective,
                reason_code="EMERGENCY",
            )
    assert denial.value.code is RegistryDenialCode.IDEMPOTENCY_CONFLICT
    assert registry_counts(db_urls["admin"]) == (1, 1, 1, 1)
    assert_denied(db_urls, RegistryCommand.START_SESSION, RegistryDenialCode.ARTIFACT_REVOKED)
    with connect(db_urls["admin"]) as admin:
        assert admin.execute(
            "SELECT id,valid_from,valid_until FROM kineticloop.authorization_issuances "
            "WHERE id=%s", (UUID(AUTHORIZATION_ID),)
        ).fetchone() == historical_authorization

    def race(commands: tuple[RevokeArtifact, RevokeArtifact]) -> tuple[list[object], list[object]]:
        barrier = threading.Barrier(3)
        results: list[object] = []
        errors: list[object] = []

        def worker(command: RevokeArtifact) -> None:
            try:
                with connect(db_urls["trusted_admin"]) as connection:
                    barrier.wait(timeout=5)
                    results.append(
                        revoke_artifact(
                            connection, command, effective_at=NOW,
                            reason_code="EMERGENCY", lock_timeout_ms=5_000,
                        )
                    )
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=worker, args=(command,)) for command in commands]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)
            assert not thread.is_alive()
        return results, errors

    seed(db_urls["admin"])
    same = revoke_command(key="race-same")
    same_results, same_errors = race((same, same))
    assert same_errors == []
    assert len(same_results) == 2 and same_results[0] == same_results[1]
    assert registry_counts(db_urls["admin"]) == (1, 1, 1, 1)

    seed(db_urls["admin"])
    conflict_results, conflict_errors = race(
        (
            revoke_command(key="race-conflict", request_hash="1" * 64),
            revoke_command(key="race-conflict", request_hash="2" * 64),
        )
    )
    assert len(conflict_results) == 1 and len(conflict_errors) == 1
    assert isinstance(conflict_errors[0], RegistryDenied)
    assert conflict_errors[0].code is RegistryDenialCode.IDEMPOTENCY_CONFLICT
    assert registry_counts(db_urls["admin"]) == (1, 1, 1, 1)


class CommitUnknownTransaction:
    def __init__(
        self, transaction: Any, error_type: type[psycopg.Error]
    ) -> None:
        self.transaction = transaction
        self.error_type = error_type

    def __enter__(self) -> Any:
        return self.transaction.__enter__()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool:
        result = self.transaction.__exit__(exc_type, exc_value, traceback)
        if exc_type is None:
            raise self.error_type("injected unknown commit outcome")
        return bool(result)


class CommitUnknownConnection:
    def __init__(
        self,
        connection: Connection[Any],
        error_type: type[psycopg.Error] = psycopg.OperationalError,
    ) -> None:
        self.connection = connection
        self.error_type = error_type

    @property
    def info(self) -> Any:
        return self.connection.info

    def transaction(self) -> CommitUnknownTransaction:
        return CommitUnknownTransaction(self.connection.transaction(), self.error_type)

    def cursor(self) -> Any:
        return self.connection.cursor()


@pytest.mark.parametrize(
    "error_type",
    (psycopg.OperationalError, psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable),
)
def test_shared_command_ack_loss_propagates_unknown_outcome(
    db_urls: dict[str, str], error_type: type[psycopg.Error],
) -> None:
    with connect(db_urls["application"]) as raw:
        wrapped: Any = CommitUnknownConnection(raw, error_type)
        with pytest.raises(error_type, match="unknown commit outcome"):
            execute_shared_registry_command(
                wrapped,
                eligibility(RegistryCommand.START_SESSION),
                mutate(RegistryCommand.START_SESSION),
            )
    assert mutation_count(db_urls["admin"]) == 1


@pytest.mark.parametrize(
    "error_type",
    (psycopg.OperationalError, psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable),
)
def test_revoke_ack_loss_reconciles_by_command_key(
    db_urls: dict[str, str], error_type: type[psycopg.Error]
) -> None:
    with connect(db_urls["trusted_admin"]) as raw:
        wrapped: Any = CommitUnknownConnection(raw, error_type)
        with pytest.raises(error_type, match="unknown commit outcome"):
            revoke_artifact(wrapped, revoke_command(), effective_at=NOW, reason_code="EMERGENCY")
    assert registry_counts(db_urls["admin"]) == (1, 1, 1, 1)
    with connect(db_urls["trusted_admin"]) as connection:
        recovered = revoke_artifact(
            connection, revoke_command(), effective_at=NOW, reason_code="EMERGENCY"
        )
    assert recovered.registry_revision == 1


def test_direct_sql_revoke_rejects_unbound_payload_hash(
    db_urls: dict[str, str],
) -> None:
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_INVALID_ARGUMENT"):
            invoke_revoke_sql(
                trusted, key="forged-payload", payload_hash="f" * 64
            )
        trusted.rollback()
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_INVALID_ARGUMENT"):
            trusted.execute(
                "SELECT * FROM kineticloop.registry_revoke_artifact("
                "%s,%s,%s,%s,NULL,%s,%s,%s,5000)",
                (
                    UUID(ARTIFACT_ID), CONTENT_HASH, NOW, "EMERGENCY",
                    "null-payload", "d" * 64, UUID(INCIDENT_ID),
                ),
            )
        trusted.rollback()
    assert registry_counts(db_urls["admin"]) == (0, 0, 0, 0)
    with connect(db_urls["admin"]) as admin:
        assert admin.execute(
            "SELECT registry_revision,last_revocation_id "
            "FROM kineticloop.safety_registry_state WHERE id=1"
        ).fetchone() == (0, None)

    decomposed_reason = "Cafe\u0301"
    noncanonical_payload = json.dumps(
        {
            "effective_at": canonical_utc(NOW),
            "reason_code": decomposed_reason,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    noncanonical_hash = hashlib.sha256(noncanonical_payload).hexdigest()
    canonical_hash = revocation_payload_hash(
        effective_at=NOW, reason_code=decomposed_reason
    )
    assert noncanonical_hash != canonical_hash
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_INVALID_ARGUMENT"):
            invoke_revoke_sql(
                trusted, key="unicode-revoke", reason_code=decomposed_reason,
                payload_hash=noncanonical_hash,
            )
        trusted.rollback()
        row = invoke_revoke_sql(
            trusted, key="unicode-revoke", reason_code=decomposed_reason,
            payload_hash=canonical_hash,
        )
        assert row is not None
        trusted.commit()
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_INVALID_ARGUMENT"):
            trusted.execute(
                "SELECT * FROM kineticloop.registry_revoke_artifact("
                "%s,%s,%s,%s,%s,%s,NULL,%s,5000)",
                (
                    UUID(ARTIFACT_ID), CONTENT_HASH, NOW, decomposed_reason,
                    canonical_hash, "unicode-revoke", UUID(INCIDENT_ID),
                ),
            )
        trusted.rollback()
    assert registry_counts(db_urls["admin"]) == (1, 1, 1, 1)
    with connect(db_urls["admin"]) as admin:
        assert admin.execute(
            "SELECT reason_code FROM kineticloop.artifact_revocation_events"
        ).fetchone() == ("Caf\u00e9",)


def test_global_revoke_never_locks_s01(db_urls: dict[str, str]) -> None:
    blocker = connect(db_urls["admin"], name="held-s01")
    blocker.execute(
        "SELECT subject_id FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
        (UUID(SUBJECT_ID),),
    )
    with connect(db_urls["trusted_admin"]) as connection:
        result = revoke_artifact(
            connection,
            revoke_command(),
            effective_at=NOW,
            reason_code="EMERGENCY",
            lock_timeout_ms=200,
        )
    blocker.rollback()
    blocker.close()
    assert result.registry_revision == 1


def test_stop_has_no_registry_dependency(db_urls: dict[str, str]) -> None:
    blocker = connect(db_urls["admin"])
    blocker.execute(
        "SELECT registry_revision FROM kineticloop.safety_registry_state WHERE id=1 FOR UPDATE"
    )
    def stop_mutation(cursor: Any) -> int:
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        assert row is not None
        return int(row[0])

    with connect(db_urls["stop"]) as connection:
        result = execute_stop_without_registry(
            connection,
            SUBJECT_ID,
            stop_mutation,
            lock_timeout_ms=100,
        )
    blocker.rollback()
    blocker.close()
    assert result == 1


def test_command_owners_reject_nested_transactions(db_urls: dict[str, str]) -> None:
    with connect(db_urls["application"]) as connection:
        connection.execute("SELECT 1")
        with pytest.raises(RegistryTransactionStateError):
            execute_shared_registry_command(
                connection,
                eligibility(RegistryCommand.START_SESSION),
                mutate(RegistryCommand.START_SESSION),
            )
        connection.rollback()
    with connect(db_urls["trusted_admin"]) as connection:
        connection.execute("SELECT 1")
        with pytest.raises(RegistryTransactionStateError):
            revoke_artifact(connection, revoke_command(), effective_at=NOW, reason_code="EMERGENCY")


def test_migrated_registry_command_routine_privileges(db_urls: dict[str, str]) -> None:
    with connect(db_urls["admin"]) as connection:
        rows = connection.execute(
            "SELECT p.proname, p.oid::regprocedure::text, "
            "pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig, "
            "NOT EXISTS (SELECT 1 FROM aclexplode(coalesce(p.proacl, "
            "acldefault('f',p.proowner))) acl WHERE acl.grantee=0 "
            "AND acl.privilege_type='EXECUTE') "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='kineticloop' AND p.prosecdef ORDER BY p.proname"
        ).fetchall()
        assert [row[0] for row in rows] == [
            "registry_guard_commit_bundle",
            "registry_guard_continue_session",
            "registry_guard_publish_manifest",
            "registry_guard_reauthorize",
            "registry_guard_resume_session",
            "registry_guard_start_session",
            "registry_revoke_artifact",
        ]
        assert all(row[2] == "kl_writer_safety_registry" for row in rows)
        assert all(row[3] is True and row[4] == ["search_path=pg_catalog"] for row in rows)
        assert all(row[5] is True for row in rows)
        for name, signature, _owner, _security, _config, _acl in rows:
            expected_role = (
                "kl_trusted_admin" if name == "registry_revoke_artifact" else "kl_application"
            )
            denied_role = (
                "kl_application" if name == "registry_revoke_artifact" else "kl_trusted_admin"
            )
            assert connection.execute(
                "SELECT has_function_privilege(%s,%s,'EXECUTE')",
                (expected_role, signature),
            ).fetchone() == (True,)
            for role in (denied_role, "kl_auditor"):
                assert connection.execute(
                    "SELECT has_function_privilege(%s,%s,'EXECUTE')",
                    (role, signature),
                ).fetchone() == (False,)


def test_migrated_registry_role_owner_boundary(db_urls: dict[str, str]) -> None:
    with connect(db_urls["application"]) as application:
        for sql_text in (
            "SET ROLE kl_migration_owner",
            "SET ROLE kl_writer_safety_registry",
            "UPDATE kineticloop.safety_registry_state SET registry_revision=99 WHERE id=1",
        ):
            with pytest.raises(psycopg.Error):
                application.execute(sql_text)
            application.rollback()
        with pytest.raises(psycopg.Error):
            application.execute(
                "SELECT * FROM kineticloop.registry_revoke_artifact(%s,%s,%s,%s,%s,%s,%s,%s,1000)",
                (
                    UUID(ARTIFACT_ID),
                    CONTENT_HASH,
                    NOW,
                    "EMERGENCY",
                    revocation_payload_hash(effective_at=NOW, reason_code="EMERGENCY"),
                    "caller-asserted-admin",
                    "e" * 64,
                    UUID(INCIDENT_ID),
                ),
            )
        application.rollback()
    assert registry_counts(db_urls["admin"]) == (0, 0, 0, 0)

    revoke_signature = (
        "kineticloop.registry_revoke_artifact("
        "uuid,text,timestamp with time zone,text,text,text,text,uuid,integer)"
    )
    with psycopg.connect(db_urls["admin"], autocommit=True) as admin:
        admin.execute(f"GRANT EXECUTE ON FUNCTION {revoke_signature} TO kl_stop_login")
    try:
        with connect(db_urls["stop"]) as stop:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_REGISTRY_COMMAND_NOT_AUTHORIZED",
            ):
                invoke_revoke_sql(stop, key="unauthorized-direct-execute")
            stop.rollback()
    finally:
        with psycopg.connect(db_urls["admin"], autocommit=True) as admin:
            admin.execute(f"REVOKE EXECUTE ON FUNCTION {revoke_signature} FROM kl_stop_login")
    assert registry_counts(db_urls["admin"]) == (0, 0, 0, 0)

    denied_writes = (
        "UPDATE kineticloop.safety_registry_state SET registry_revision=99 WHERE id=1",
        "INSERT INTO kineticloop.safety_artifacts("
        "id,artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from) "
        "VALUES ('00000000-0000-8000-8000-0000000000ff','POLICY_BUNDLE','forged','1',"
        "'forged','TIMELESS',clock_timestamp())",
        "INSERT INTO kineticloop.artifact_revocation_events("
        "id,effective_at,management_command_identity,reason_code,revocation_payload_hash,"
        "registry_revision,ref_s49_id,registry_state_id) VALUES ("
        "'00000000-0000-8000-8000-0000000000fe',clock_timestamp(),'forged','forged',"
        "'forged',99,'00000000-0000-8000-8000-000000000003',1)",
    )
    for role_url in (db_urls["application"], db_urls["trusted_admin"], db_urls["stop"]):
        with connect(role_url) as runtime:
            for statement in denied_writes:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    runtime.execute(statement)
                runtime.rollback()
    assert registry_counts(db_urls["admin"]) == (0, 0, 0, 0)

    with connect(db_urls["trusted_admin"]) as trusted:
        result = revoke_artifact(
            trusted, revoke_command(), effective_at=NOW, reason_code="EMERGENCY"
        )
    assert result.registry_revision == 1
    with connect(db_urls["admin"]) as admin:
        row = admin.execute(
            "SELECT operator_identity,command_key,request_hash,causation_incident_id,"
            "outbox_delivery_id FROM kineticloop.artifact_revocation_events"
        ).fetchone()
        assert row is not None
        assert row[0] == "kl_trusted_admin_login"
        assert row[1] == "revoke-1"
        assert row[2] == "d" * 64
        assert row[3] == UUID(INCIDENT_ID)
        assert row[4] is not None
