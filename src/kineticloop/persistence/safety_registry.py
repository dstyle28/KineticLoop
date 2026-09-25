"""PostgreSQL implementation of the frozen S51 shared/exclusive registry gate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

import psycopg
from psycopg import Connection, Cursor
from psycopg.pq import TransactionStatus

from kineticloop.contracts.commands import RevokeArtifact
from kineticloop.contracts.safety_registry import (
    RegistryDenialCode,
    RegistryDenied,
    RegistryEligibility,
    revocation_payload_hash,
)

_T = TypeVar("_T")
Mutation = Callable[[Cursor[Any], int], _T]
StopMutation = Callable[[Cursor[Any]], _T]

_SHARED_ROUTINES = {
    "PublishManifest": "registry_guard_publish_manifest",
    "CommitBundle": "registry_guard_commit_bundle",
    "Reauthorize": "registry_guard_reauthorize",
    "StartSession": "registry_guard_start_session",
    "ResumeSession": "registry_guard_resume_session",
    "ContinueSession": "registry_guard_continue_session",
}

_DATABASE_DENIALS = {
    "KL_REGISTRY_UNAVAILABLE": RegistryDenialCode.REGISTRY_UNAVAILABLE,
    "KL_REGISTRY_TIMEOUT": RegistryDenialCode.REGISTRY_TIMEOUT,
    "KL_REGISTRY_STALE": RegistryDenialCode.REGISTRY_STALE,
    "KL_REGISTRY_ARTIFACT_UNKNOWN": RegistryDenialCode.ARTIFACT_UNKNOWN,
    "KL_REGISTRY_ARTIFACT_REVOKED": RegistryDenialCode.ARTIFACT_REVOKED,
    "KL_REGISTRY_ARTIFACT_EXPIRED": RegistryDenialCode.ARTIFACT_EXPIRED,
    "KL_REGISTRY_VALIDITY_UNDEFINED": RegistryDenialCode.VALIDITY_UNDEFINED,
    "KL_REGISTRY_DEPENDENCY_INCOMPLETE": RegistryDenialCode.DEPENDENCY_INCOMPLETE,
    "KL_REGISTRY_AUTHORIZATION_INELIGIBLE": RegistryDenialCode.AUTHORIZATION_INELIGIBLE,
    "KL_REGISTRY_IDEMPOTENCY_CONFLICT": RegistryDenialCode.IDEMPOTENCY_CONFLICT,
    "KL_REGISTRY_COMMAND_NOT_AUTHORIZED": RegistryDenialCode.COMMAND_NOT_AUTHORIZED,
}


@dataclass(frozen=True, slots=True)
class RevocationResult:
    revocation_id: str
    registry_revision: int
    artifact_id: str
    effective_at: datetime
    recorded_at: datetime


class RegistryTransactionStateError(RuntimeError):
    """The command owner requires an idle connection and owns the top-level commit."""


def _require_idle_connection(connection: Connection[Any]) -> None:
    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise RegistryTransactionStateError(
            "SafetyRegistry command owners require an idle connection"
        )


def _set_lock_timeout(cursor: Cursor[Any], lock_timeout_ms: int) -> None:
    if lock_timeout_ms <= 0:
        raise ValueError("lock_timeout_ms must be positive")
    cursor.execute("SELECT set_config('lock_timeout', %s, true)", (f"{lock_timeout_ms}ms",))


def _database_denial(error: psycopg.Error) -> RegistryDenied | None:
    message = str(error)
    for marker, code in _DATABASE_DENIALS.items():
        if marker in message:
            return RegistryDenied(code)
    return None


def execute_shared_registry_command(
    connection: Connection[Any],
    eligibility: RegistryEligibility,
    mutation: Mutation[_T],
    *,
    lock_timeout_ms: int = 1_000,
) -> _T:
    """Run T3/T6/T7 as S51 shared -> S01 -> fresh bounded guards -> mutation."""

    _require_idle_connection(connection)
    mutation_started = False
    try:
        with connection.transaction():
            cursor = connection.cursor()
            routine = _SHARED_ROUTINES[eligibility.command.value]
            cursor.execute(
                f"SELECT kineticloop.{routine}(%s, %s, %s, %s)",
                (
                    UUID(eligibility.subject_id),
                    [UUID(value) for value in eligibility.artifact_ids],
                    eligibility.minimum_registry_revision,
                    lock_timeout_ms,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RegistryDenied(RegistryDenialCode.REGISTRY_UNAVAILABLE)
            revision = int(row[0])
            mutation_started = True
            return mutation(cursor, revision)
    except psycopg.Error as error:
        denial = _database_denial(error)
        if denial is not None and not mutation_started:
            raise denial from error
        if isinstance(error, (psycopg.errors.LockNotAvailable, psycopg.errors.QueryCanceled)):
            raise RegistryDenied(RegistryDenialCode.REGISTRY_TIMEOUT) from error
        if mutation_started:
            raise
        raise RegistryDenied(RegistryDenialCode.REGISTRY_UNAVAILABLE) from error
def revoke_artifact(
    connection: Connection[Any],
    command: RevokeArtifact,
    *,
    effective_at: datetime,
    reason_code: str,
    lock_timeout_ms: int = 1_000,
) -> RevocationResult:
    """Execute T2-GLOBAL; the successful transaction commit is linearization."""

    if effective_at.tzinfo is None or effective_at.utcoffset() is None:
        raise ValueError("effective_at must be timezone-aware")
    if not reason_code:
        raise ValueError("reason_code must be non-empty")
    if command.revocation_payload_hash != revocation_payload_hash(
        effective_at=effective_at, reason_code=reason_code
    ):
        raise RegistryDenied(RegistryDenialCode.IDEMPOTENCY_CONFLICT)

    _require_idle_connection(connection)
    try:
        with connection.transaction():
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT revocation_id, registry_revision, artifact_id,
                       effective_at, recorded_at
                FROM kineticloop.registry_revoke_artifact(
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    UUID(command.artifact_id),
                    command.artifact_content_hash,
                    effective_at,
                    reason_code,
                    command.revocation_payload_hash,
                    command.idempotency_key,
                    command.request_hash,
                    UUID(command.causation_incident_id),
                    lock_timeout_ms,
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise RegistryDenied(RegistryDenialCode.REGISTRY_UNAVAILABLE)
            return RevocationResult(
                revocation_id=str(row[0]),
                registry_revision=int(row[1]),
                artifact_id=str(row[2]),
                effective_at=row[3],
                recorded_at=row[4],
            )
    except psycopg.Error as error:
        denial = _database_denial(error)
        if denial is not None:
            raise denial from error
        if isinstance(error, (psycopg.errors.LockNotAvailable, psycopg.errors.QueryCanceled)):
            raise RegistryDenied(RegistryDenialCode.REGISTRY_TIMEOUT) from error
        raise


def execute_stop_without_registry(
    connection: Connection[Any],
    subject_id: str,
    mutation: StopMutation[_T],
    *,
    lock_timeout_ms: int = 1_000,
) -> _T:
    """Run STOP from S01 directly; this function never reads or locks S51."""

    _require_idle_connection(connection)
    with connection.transaction():
        cursor = connection.cursor()
        _set_lock_timeout(cursor, lock_timeout_ms)
        cursor.execute(
            "SELECT subject_id FROM kineticloop.user_decision_state "
            "WHERE subject_id = %s FOR UPDATE",
            (UUID(subject_id),),
        )
        if cursor.fetchone() is None:
            raise RegistryDenied(RegistryDenialCode.AUTHORIZATION_INELIGIBLE)
        return mutation(cursor)
