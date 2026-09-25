from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
    RegistryUnavailableError,
    fail_closed_registry_check,
)
from kineticloop.db.lifecycle import DatabaseLifecycle
from kineticloop.identity import ActorRole
from kineticloop.persistence.safety_registry import (
    RevocationResult,
    execute_shared_registry_command,
    execute_stop_without_registry,
    revoke_artifact,
)

ROOT = Path(__file__).parents[2]
SUBJECT_ID = "00000000-0000-8000-8000-000000000001"
ADMIN_ID = "00000000-0000-8000-8000-000000000002"
ARTIFACT_ID = "00000000-0000-8000-8000-000000000003"
DEPENDENCY_ID = "00000000-0000-8000-8000-000000000004"
INCIDENT_ID = "00000000-0000-8000-8000-000000000005"
CONTENT_HASH = "a" * 64
NOW = datetime(2026, 9, 24, 18, tzinfo=UTC)

SCHEMA_SQL = """
CREATE TABLE safety_registry_state (
    registry_scope text PRIMARY KEY,
    registry_revision bigint NOT NULL CHECK (registry_revision >= 0),
    last_revocation_id uuid
);
CREATE TABLE safety_artifacts (
    artifact_id uuid PRIMARY KEY,
    content_hash text NOT NULL,
    dependency_ids uuid[] NOT NULL,
    valid_from timestamptz,
    valid_until timestamptz
);
CREATE TABLE artifact_revocation_events (
    revocation_id uuid PRIMARY KEY,
    artifact_id uuid NOT NULL REFERENCES safety_artifacts(artifact_id),
    registry_revision bigint NOT NULL UNIQUE,
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    reason_code text NOT NULL,
    operator_identity uuid NOT NULL,
    command_key text NOT NULL UNIQUE,
    request_hash text NOT NULL,
    causation_incident_id uuid NOT NULL
);
CREATE TABLE registry_management_receipts (
    command_key text PRIMARY KEY,
    request_hash text NOT NULL,
    revocation_id uuid NOT NULL UNIQUE,
    registry_revision bigint NOT NULL,
    artifact_id uuid NOT NULL,
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL
);
CREATE TABLE registry_audit_events (
    event_id uuid PRIMARY KEY,
    revocation_id uuid NOT NULL UNIQUE,
    operator_identity uuid NOT NULL
);
CREATE TABLE registry_outbox (
    delivery_id uuid PRIMARY KEY,
    revocation_id uuid NOT NULL UNIQUE
);
CREATE TABLE subject_coordination (
    subject_id uuid PRIMARY KEY,
    t6_issuance_eligible boolean NOT NULL,
    t7_execution_eligible boolean NOT NULL,
    authorization_valid_until timestamptz
);
CREATE TABLE domain_mutations (
    mutation_id bigserial PRIMARY KEY,
    command_kind text NOT NULL,
    registry_revision bigint,
    subject_id uuid NOT NULL
);
CREATE TABLE authorization_history (
    authorization_id uuid PRIMARY KEY,
    authorized_at timestamptz NOT NULL,
    artifact_id uuid NOT NULL
);
"""


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    lifecycle = DatabaseLifecycle(ROOT)
    connection = lifecycle.reset(timeout_seconds=90)
    yield connection.url


@pytest.fixture
def db_url(database_url: str) -> str:
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")
        connection.execute(SCHEMA_SQL)
    seed(database_url)
    return database_url


def connect(database_url: str, *, name: str = "kl016-test") -> Connection[Any]:
    return psycopg.connect(database_url, application_name=name)


def seed(database_url: str) -> None:
    with connect(database_url) as connection:
        with connection.transaction():
            connection.execute(
                "INSERT INTO safety_registry_state VALUES ('system', 0, NULL)"
            )
            connection.execute(
                """
                INSERT INTO safety_artifacts
                    (artifact_id, content_hash, dependency_ids, valid_from, valid_until)
                VALUES (%s, %s, %s, %s, %s), (%s, %s, %s, %s, %s)
                """,
                (
                    UUID(DEPENDENCY_ID),
                    "b" * 64,
                    [],
                    NOW - timedelta(days=1),
                    NOW + timedelta(days=30),
                    UUID(ARTIFACT_ID),
                    CONTENT_HASH,
                    [UUID(DEPENDENCY_ID)],
                    NOW - timedelta(days=1),
                    NOW + timedelta(days=30),
                ),
            )
            connection.execute(
                "INSERT INTO subject_coordination VALUES (%s, true, true, %s)",
                (UUID(SUBJECT_ID), NOW + timedelta(days=1)),
            )
            connection.execute(
                "INSERT INTO authorization_history VALUES (%s, %s, %s)",
                (
                    UUID("00000000-0000-8000-8000-000000000006"),
                    NOW - timedelta(hours=1),
                    UUID(ARTIFACT_ID),
                ),
            )


def clear_state(database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("TRUNCATE registry_outbox, registry_audit_events")
        connection.execute(
            "TRUNCATE registry_management_receipts, artifact_revocation_events"
        )
        connection.execute("TRUNCATE domain_mutations RESTART IDENTITY")
        connection.execute(
            """
            UPDATE safety_registry_state
               SET registry_revision = 0, last_revocation_id = NULL
            """
        )
        connection.execute(
            """
            UPDATE safety_artifacts
               SET valid_from = %s, valid_until = %s
            """,
            (NOW - timedelta(days=1), NOW + timedelta(days=30)),
        )
        connection.execute(
            """
            UPDATE subject_coordination
               SET t6_issuance_eligible = true,
                   t7_execution_eligible = true,
                   authorization_valid_until = %s
            """,
            (NOW + timedelta(days=1),),
        )


def eligibility(
    command: RegistryCommand, *, minimum_registry_revision: int = 0
) -> RegistryEligibility:
    return RegistryEligibility(
        command=command,
        subject_id=SUBJECT_ID,
        artifact_ids=(ARTIFACT_ID, DEPENDENCY_ID),
        observed_at=NOW,
        minimum_registry_revision=minimum_registry_revision,
    )


def mutate(command: RegistryCommand) -> Any:
    def operation(cursor: Any, registry_revision: int) -> int:
        cursor.execute(
            """
            INSERT INTO domain_mutations (command_kind, registry_revision, subject_id)
            VALUES (%s, %s, %s)
            RETURNING mutation_id
            """,
            (command.value, registry_revision, UUID(SUBJECT_ID)),
        )
        return int(cursor.fetchone()[0])

    return operation


def mutation_count(database_url: str) -> int:
    with connect(database_url) as connection:
        row = connection.execute("SELECT count(*) FROM domain_mutations").fetchone()
        assert row is not None
        return int(row[0])


def wait_until_blocked(database_url: str, application_name: str) -> None:
    deadline = time.monotonic() + 5
    with connect(database_url) as observer:
        while time.monotonic() < deadline:
            row = observer.execute(
                """
                SELECT cardinality(pg_blocking_pids(pid))
                  FROM pg_stat_activity
                 WHERE application_name = %s AND state <> 'idle'
                """,
                (application_name,),
            ).fetchone()
            observer.rollback()
            if row is not None and row[0] > 0:
                return
            time.sleep(0.02)
    raise AssertionError(f"{application_name} did not block on the registry gate")


def direct_revoke(blocker: Connection[Any], command_key: str) -> None:
    blocker.execute(
        """
        INSERT INTO artifact_revocation_events (
            revocation_id, artifact_id, registry_revision, effective_at, reason_code,
            operator_identity, command_key, request_hash, causation_incident_id
        ) VALUES (%s, %s, 1, %s, 'TEST', %s, %s, %s, %s)
        """,
        (
            UUID("00000000-0000-8000-8000-000000000010"),
            UUID(ARTIFACT_ID),
            NOW,
            UUID(ADMIN_ID),
            command_key,
            "c" * 64,
            UUID(INCIDENT_ID),
        ),
    )
    blocker.execute(
        """
        UPDATE safety_registry_state
           SET registry_revision = 1,
               last_revocation_id = %s
         WHERE registry_scope = 'system'
        """,
        (UUID("00000000-0000-8000-8000-000000000010"),),
    )


def assert_subject_unlocked(database_url: str) -> None:
    with connect(database_url) as observer:
        observer.execute("SET LOCAL lock_timeout = '100ms'")
        observer.execute(
            "SELECT subject_id FROM subject_coordination WHERE subject_id = %s FOR UPDATE",
            (UUID(SUBJECT_ID),),
        )
        observer.rollback()


def run_waiting_shared_then_revoke(database_url: str, command: RegistryCommand) -> None:
    clear_state(database_url)
    blocker = connect(database_url, name=f"blocker-{command.value}")
    blocker.execute(
        "SELECT registry_revision FROM safety_registry_state WHERE registry_scope='system' FOR UPDATE"
    )
    outcome: dict[str, object] = {}
    app_name = f"shared-{command.value}"

    def worker() -> None:
        try:
            with connect(database_url, name=app_name) as connection:
                execute_shared_registry_command(
                    connection, eligibility(command), mutate(command), lock_timeout_ms=5_000
                )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    wait_until_blocked(database_url, app_name)
    assert_subject_unlocked(database_url)
    direct_revoke(blocker, f"direct-{command.value}")
    blocker.commit()
    blocker.close()
    thread.join(timeout=5)
    assert not thread.is_alive()
    error = outcome.get("error")
    assert isinstance(error, RegistryDenied)
    assert error.code is RegistryDenialCode.ARTIFACT_REVOKED
    assert mutation_count(database_url) == 0


def assert_denied_without_mutation(
    database_url: str,
    command: RegistryCommand,
    expected: RegistryDenialCode,
    *,
    minimum_registry_revision: int = 0,
) -> None:
    with connect(database_url) as connection:
        with pytest.raises(RegistryDenied) as denial:
            execute_shared_registry_command(
                connection,
                eligibility(command, minimum_registry_revision=minimum_registry_revision),
                mutate(command),
            )
    assert denial.value.code is expected
    assert mutation_count(database_url) == 0


def assert_timeout_before_subject(database_url: str, command: RegistryCommand) -> None:
    clear_state(database_url)
    blocker = connect(database_url)
    blocker.execute(
        "SELECT registry_revision FROM safety_registry_state WHERE registry_scope='system' FOR UPDATE"
    )
    with connect(database_url) as connection:
        with pytest.raises(RegistryDenied) as denial:
            execute_shared_registry_command(
                connection, eligibility(command), mutate(command), lock_timeout_ms=50
            )
    assert denial.value.code is RegistryDenialCode.REGISTRY_TIMEOUT
    assert_subject_unlocked(database_url)
    blocker.rollback()
    blocker.close()
    assert mutation_count(database_url) == 0


def test_shared_gate_command_matrix_fails_closed(db_url: str) -> None:
    for command in RegistryCommand:
        run_waiting_shared_then_revoke(db_url, command)

        clear_state(db_url)
        with connect(db_url) as connection:
            mutation_id = execute_shared_registry_command(
                connection, eligibility(command), mutate(command)
            )
        assert mutation_id == 1
        assert mutation_count(db_url) == 1

        clear_state(db_url)
        with psycopg.connect(db_url, autocommit=True) as connection:
            connection.execute(
                "UPDATE safety_artifacts SET valid_until = %s WHERE artifact_id = %s",
                (NOW, UUID(ARTIFACT_ID)),
            )
        assert_denied_without_mutation(
            db_url, command, RegistryDenialCode.ARTIFACT_EXPIRED
        )

        clear_state(db_url)
        assert_denied_without_mutation(
            db_url,
            command,
            RegistryDenialCode.REGISTRY_STALE,
            minimum_registry_revision=1,
        )

        assert_timeout_before_subject(db_url, command)

        clear_state(db_url)
        with pytest.raises(RegistryDenied) as unavailable:
            fail_closed_registry_check(
                lambda: (_ for _ in ()).throw(RegistryUnavailableError())
            )
        assert unavailable.value.code is RegistryDenialCode.REGISTRY_UNAVAILABLE
        assert mutation_count(db_url) == 0

        if command is not RegistryCommand.PUBLISH_MANIFEST:
            eligibility_column = (
                "t6_issuance_eligible"
                if command in {RegistryCommand.COMMIT_BUNDLE, RegistryCommand.REAUTHORIZE}
                else "t7_execution_eligible"
            )
            with psycopg.connect(db_url, autocommit=True) as connection:
                connection.execute(
                    f"UPDATE subject_coordination SET {eligibility_column} = false"
                )
            assert_denied_without_mutation(
                db_url, command, RegistryDenialCode.AUTHORIZATION_INELIGIBLE
            )


def test_reauthorize_shared_gate_precedes_s01_and_fails_closed(db_url: str) -> None:
    run_waiting_shared_then_revoke(db_url, RegistryCommand.REAUTHORIZE)
    clear_state(db_url)
    with psycopg.connect(db_url, autocommit=True) as connection:
        connection.execute(
            "UPDATE subject_coordination SET t6_issuance_eligible = false"
        )
    assert_denied_without_mutation(
        db_url, RegistryCommand.REAUTHORIZE, RegistryDenialCode.AUTHORIZATION_INELIGIBLE
    )
    assert_timeout_before_subject(db_url, RegistryCommand.REAUTHORIZE)
    clear_state(db_url)
    with psycopg.connect(db_url, autocommit=True) as connection:
        connection.execute(
            "UPDATE safety_artifacts SET valid_until = %s WHERE artifact_id = %s",
            (NOW, UUID(ARTIFACT_ID)),
        )
    assert_denied_without_mutation(
        db_url, RegistryCommand.REAUTHORIZE, RegistryDenialCode.ARTIFACT_EXPIRED
    )
    clear_state(db_url)
    assert_denied_without_mutation(
        db_url,
        RegistryCommand.REAUTHORIZE,
        RegistryDenialCode.REGISTRY_STALE,
        minimum_registry_revision=1,
    )
    with pytest.raises(RegistryDenied) as unavailable:
        fail_closed_registry_check(lambda: (_ for _ in ()).throw(RegistryUnavailableError()))
    assert unavailable.value.code is RegistryDenialCode.REGISTRY_UNAVAILABLE


def test_continue_session_rechecks_shared_gate_and_fails_closed(db_url: str) -> None:
    run_waiting_shared_then_revoke(db_url, RegistryCommand.CONTINUE_SESSION)
    clear_state(db_url)
    with psycopg.connect(db_url, autocommit=True) as connection:
        connection.execute(
            "UPDATE subject_coordination SET authorization_valid_until = %s",
            (NOW,),
        )
    assert_denied_without_mutation(
        db_url,
        RegistryCommand.CONTINUE_SESSION,
        RegistryDenialCode.AUTHORIZATION_INELIGIBLE,
    )
    assert_timeout_before_subject(db_url, RegistryCommand.CONTINUE_SESSION)
    clear_state(db_url)
    with psycopg.connect(db_url, autocommit=True) as connection:
        connection.execute(
            "UPDATE safety_artifacts SET valid_until = %s WHERE artifact_id = %s",
            (NOW, UUID(ARTIFACT_ID)),
        )
    assert_denied_without_mutation(
        db_url, RegistryCommand.CONTINUE_SESSION, RegistryDenialCode.ARTIFACT_EXPIRED
    )
    clear_state(db_url)
    assert_denied_without_mutation(
        db_url,
        RegistryCommand.CONTINUE_SESSION,
        RegistryDenialCode.REGISTRY_STALE,
        minimum_registry_revision=1,
    )
    with pytest.raises(RegistryDenied) as unavailable:
        fail_closed_registry_check(lambda: (_ for _ in ()).throw(RegistryUnavailableError()))
    assert unavailable.value.code is RegistryDenialCode.REGISTRY_UNAVAILABLE


def revoke_command(*, key: str = "revoke-1", request_hash: str = "d" * 64) -> RevokeArtifact:
    return RevokeArtifact(
        schema_version="kineticloop-command-v1",
        command_kind="RevokeArtifact",
        boundary=TransactionBoundary.T2_GLOBAL,
        command_id="00000000-0000-8000-8000-000000000007",
        actor=TrustedActor(
            schema="kineticloop-role-identity-v1",
            identity_id=ADMIN_ID,
            role=ActorRole.ADMIN,
        ),
        idempotency_key=key,
        request_hash=request_hash,
        subject_id=None,
        explicit_scope="global:safety-registry",
        artifact_id=ARTIFACT_ID,
        artifact_content_hash=CONTENT_HASH,
        revocation_payload_hash="e" * 64,
        causation_incident_id=INCIDENT_ID,
    )


def test_exclusive_global_gate_serializes(db_url: str) -> None:
    shared = connect(db_url)
    shared.execute(
        "SELECT registry_revision FROM safety_registry_state WHERE registry_scope='system' FOR SHARE"
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            with connect(db_url, name="exclusive-revoke") as connection:
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
    wait_until_blocked(db_url, "exclusive-revoke")
    assert "result" not in outcome
    shared.commit()
    shared.close()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert "error" not in outcome
    result = outcome["result"]
    assert isinstance(result, RevocationResult)
    assert result.registry_revision == 1


def table_counts(database_url: str) -> tuple[int, int, int, int, int]:
    with connect(database_url) as connection:
        counts: list[int] = []
        for table in (
            "artifact_revocation_events",
            "registry_management_receipts",
            "registry_audit_events",
            "registry_outbox",
            "authorization_history",
        ):
            row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
            assert row is not None
            counts.append(int(row[0]))
        assert len(counts) == 5
        return counts[0], counts[1], counts[2], counts[3], counts[4]


def test_revoke_artifact_atomic_linearization_and_idempotency(db_url: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as connection:
        connection.execute(
            """
            CREATE FUNCTION fail_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'injected outbox failure'; END $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER fail_outbox BEFORE INSERT ON registry_outbox
            FOR EACH ROW EXECUTE FUNCTION fail_outbox()
            """
        )
    with connect(db_url) as connection:
        with pytest.raises(psycopg.errors.RaiseException, match="injected outbox failure"):
            revoke_artifact(
                connection,
                revoke_command(),
                effective_at=NOW + timedelta(days=7),
                reason_code="EMERGENCY",
            )
    assert table_counts(db_url) == (0, 0, 0, 0, 1)
    with connect(db_url) as connection:
        revision_row = connection.execute(
            "SELECT registry_revision FROM safety_registry_state"
        ).fetchone()
        assert revision_row is not None
        revision = revision_row[0]
    assert revision == 0

    with psycopg.connect(db_url, autocommit=True) as connection:
        connection.execute("DROP TRIGGER fail_outbox ON registry_outbox")
        connection.execute("DROP FUNCTION fail_outbox()")

    future_effective = NOW + timedelta(days=7)
    with connect(db_url) as connection:
        first = revoke_artifact(
            connection,
            revoke_command(),
            effective_at=future_effective,
            reason_code="EMERGENCY",
        )
    assert first.registry_revision == 1
    assert first.effective_at == future_effective
    assert table_counts(db_url) == (1, 1, 1, 1, 1)

    with connect(db_url) as connection:
        replay = revoke_artifact(
            connection,
            revoke_command(),
            effective_at=NOW - timedelta(days=30),
            reason_code="DIFFERENT_METADATA_IGNORED_ON_REPLAY",
        )
    assert replay == first
    assert table_counts(db_url) == (1, 1, 1, 1, 1)

    with connect(db_url) as connection:
        with pytest.raises(RegistryDenied) as conflict:
            revoke_artifact(
                connection,
                revoke_command(request_hash="f" * 64),
                effective_at=NOW,
                reason_code="CONFLICT",
            )
    assert conflict.value.code is RegistryDenialCode.IDEMPOTENCY_CONFLICT
    assert table_counts(db_url) == (1, 1, 1, 1, 1)

    # A future effective_at never schedules permission: commit makes later admission deny now.
    assert_denied_without_mutation(
        db_url, RegistryCommand.START_SESSION, RegistryDenialCode.ARTIFACT_REVOKED
    )
    # The immutable authorization history predating commit is not rewritten.
    with connect(db_url) as connection:
        authorization_row = connection.execute(
            "SELECT authorized_at FROM authorization_history"
        ).fetchone()
        assert authorization_row is not None
        authorized_at = authorization_row[0]
    assert authorized_at == NOW - timedelta(hours=1)


def test_global_revoke_never_locks_s01(db_url: str) -> None:
    subject_holder = connect(db_url)
    subject_holder.execute(
        "SELECT subject_id FROM subject_coordination WHERE subject_id = %s FOR UPDATE",
        (UUID(SUBJECT_ID),),
    )
    outcome: dict[str, object] = {}

    def worker() -> None:
        try:
            with connect(db_url, name="revoke-no-s01") as connection:
                outcome["result"] = revoke_artifact(
                    connection,
                    revoke_command(),
                    effective_at=NOW,
                    reason_code="EMERGENCY",
                    lock_timeout_ms=250,
                )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive(), "global revoke waited on S01"
    assert "error" not in outcome
    subject_holder.rollback()
    subject_holder.close()


def test_stop_has_no_registry_dependency(db_url: str) -> None:
    registry_holder = connect(db_url)
    registry_holder.execute(
        "SELECT registry_revision FROM safety_registry_state WHERE registry_scope='system' FOR UPDATE"
    )
    outcome: dict[str, object] = {}

    def stop_mutation(cursor: Any) -> int:
        cursor.execute(
            """
            INSERT INTO domain_mutations (command_kind, subject_id)
            VALUES ('STOP', %s) RETURNING mutation_id
            """,
            (UUID(SUBJECT_ID),),
        )
        return int(cursor.fetchone()[0])

    def worker() -> None:
        try:
            with connect(db_url, name="stop-no-registry") as connection:
                outcome["result"] = execute_stop_without_registry(
                    connection, SUBJECT_ID, stop_mutation, lock_timeout_ms=250
                )
        except BaseException as error:
            outcome["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive(), "STOP waited on S51"
    assert "error" not in outcome
    registry_holder.rollback()
    registry_holder.close()
    assert mutation_count(db_url) == 1
