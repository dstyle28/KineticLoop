"""PostgreSQL implementation of the frozen S51 shared/exclusive registry gate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID, uuid4

import psycopg
from psycopg import Connection, Cursor

from kineticloop.contracts.commands import RevokeArtifact
from kineticloop.contracts.safety_registry import (
    T6_COMMANDS,
    T7_COMMANDS,
    RegistryDenialCode,
    RegistryDenied,
    RegistryEligibility,
    RegistryGateTimeoutError,
)
from kineticloop.identity import ActorRole

SYSTEM_SCOPE = "system"
_T = TypeVar("_T")
Mutation = Callable[[Cursor[Any], int], _T]
StopMutation = Callable[[Cursor[Any]], _T]


@dataclass(frozen=True, slots=True)
class RevocationResult:
    revocation_id: str
    registry_revision: int
    artifact_id: str
    effective_at: datetime
    recorded_at: datetime


def _set_lock_timeout(cursor: Cursor[Any], lock_timeout_ms: int) -> None:
    if lock_timeout_ms <= 0:
        raise ValueError("lock_timeout_ms must be positive")
    cursor.execute("SELECT set_config('lock_timeout', %s, true)", (f"{lock_timeout_ms}ms",))


def _gate_timeout(error: psycopg.Error) -> RegistryGateTimeoutError:
    return RegistryGateTimeoutError("SafetyRegistry gate acquisition timed out")


def _acquire_shared_gate(cursor: Cursor[Any], lock_timeout_ms: int) -> int:
    _set_lock_timeout(cursor, lock_timeout_ms)
    try:
        cursor.execute(
            """
            SELECT registry_revision
              FROM safety_registry_state
             WHERE registry_scope = %s
             FOR SHARE
            """,
            (SYSTEM_SCOPE,),
        )
    except (psycopg.errors.LockNotAvailable, psycopg.errors.QueryCanceled) as error:
        raise _gate_timeout(error) from error
    row = cursor.fetchone()
    if row is None:
        raise RegistryDenied(RegistryDenialCode.REGISTRY_UNAVAILABLE)
    return int(row[0])


def _acquire_exclusive_gate(cursor: Cursor[Any], lock_timeout_ms: int) -> int:
    _set_lock_timeout(cursor, lock_timeout_ms)
    try:
        cursor.execute(
            """
            SELECT registry_revision
              FROM safety_registry_state
             WHERE registry_scope = %s
             FOR UPDATE
            """,
            (SYSTEM_SCOPE,),
        )
    except (psycopg.errors.LockNotAvailable, psycopg.errors.QueryCanceled) as error:
        raise _gate_timeout(error) from error
    row = cursor.fetchone()
    if row is None:
        raise RegistryDenied(RegistryDenialCode.REGISTRY_UNAVAILABLE)
    return int(row[0])


def _lock_subject_and_check_authorization(
    cursor: Cursor[Any], eligibility: RegistryEligibility
) -> None:
    cursor.execute(
        """
        SELECT t6_issuance_eligible, t7_execution_eligible, authorization_valid_until
          FROM subject_coordination
         WHERE subject_id = %s
         FOR UPDATE
        """,
        (UUID(eligibility.subject_id),),
    )
    row = cursor.fetchone()
    if row is None:
        raise RegistryDenied(RegistryDenialCode.AUTHORIZATION_INELIGIBLE)
    t6_eligible, t7_eligible, authorization_valid_until = row
    if eligibility.command in T6_COMMANDS and not t6_eligible:
        raise RegistryDenied(RegistryDenialCode.AUTHORIZATION_INELIGIBLE)
    if eligibility.command in T7_COMMANDS and (
        not t7_eligible
        or authorization_valid_until is None
        or authorization_valid_until <= eligibility.observed_at
    ):
        raise RegistryDenied(RegistryDenialCode.AUTHORIZATION_INELIGIBLE)


def _check_artifact_closure(cursor: Cursor[Any], eligibility: RegistryEligibility) -> None:
    artifact_ids = tuple(UUID(value) for value in eligibility.artifact_ids)
    cursor.execute(
        """
        SELECT artifact_id, dependency_ids, valid_from, valid_until
          FROM safety_artifacts
         WHERE artifact_id = ANY(%s)
        """,
        (list(artifact_ids),),
    )
    artifacts = {row[0]: row for row in cursor.fetchall()}
    if set(artifacts) != set(artifact_ids):
        raise RegistryDenied(RegistryDenialCode.ARTIFACT_UNKNOWN)

    closure = set(artifact_ids)
    for _, dependency_ids, valid_from, valid_until in artifacts.values():
        if dependency_ids is None or not set(dependency_ids).issubset(closure):
            raise RegistryDenied(RegistryDenialCode.DEPENDENCY_INCOMPLETE)
        if valid_from is None or valid_until is None:
            raise RegistryDenied(RegistryDenialCode.VALIDITY_UNDEFINED)
        if eligibility.observed_at < valid_from or eligibility.observed_at >= valid_until:
            raise RegistryDenied(RegistryDenialCode.ARTIFACT_EXPIRED)

    cursor.execute(
        """
        SELECT artifact_id
          FROM artifact_revocation_events
         WHERE artifact_id = ANY(%s)
         LIMIT 1
        """,
        (list(artifact_ids),),
    )
    if cursor.fetchone() is not None:
        raise RegistryDenied(RegistryDenialCode.ARTIFACT_REVOKED)


def execute_shared_registry_command(
    connection: Connection[Any],
    eligibility: RegistryEligibility,
    mutation: Mutation[_T],
    *,
    lock_timeout_ms: int = 1_000,
) -> _T:
    """Run T3/T6/T7 as S51 shared -> S01 -> fresh bounded guards -> mutation."""

    try:
        with connection.transaction():
            cursor = connection.cursor()
            revision = _acquire_shared_gate(cursor, lock_timeout_ms)
            if revision < eligibility.minimum_registry_revision:
                raise RegistryDenied(RegistryDenialCode.REGISTRY_STALE)
            _lock_subject_and_check_authorization(cursor, eligibility)
            _check_artifact_closure(cursor, eligibility)
            return mutation(cursor, revision)
    except RegistryGateTimeoutError as error:
        raise RegistryDenied(RegistryDenialCode.REGISTRY_TIMEOUT) from error
    except psycopg.OperationalError as error:
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

    if command.actor.role is not ActorRole.ADMIN:
        raise RegistryDenied(RegistryDenialCode.COMMAND_NOT_AUTHORIZED)
    if effective_at.tzinfo is None or effective_at.utcoffset() is None:
        raise ValueError("effective_at must be timezone-aware")
    if not reason_code:
        raise ValueError("reason_code must be non-empty")

    with connection.transaction():
        cursor = connection.cursor()
        current_revision = _acquire_exclusive_gate(cursor, lock_timeout_ms)

        cursor.execute(
            """
            SELECT request_hash, revocation_id, registry_revision, artifact_id,
                   effective_at, recorded_at
              FROM registry_management_receipts
             WHERE command_key = %s
            """,
            (command.idempotency_key,),
        )
        receipt = cursor.fetchone()
        if receipt is not None:
            if receipt[0] != command.request_hash:
                raise RegistryDenied(RegistryDenialCode.IDEMPOTENCY_CONFLICT)
            return RevocationResult(
                revocation_id=str(receipt[1]),
                registry_revision=int(receipt[2]),
                artifact_id=str(receipt[3]),
                effective_at=receipt[4],
                recorded_at=receipt[5],
            )

        artifact_id = UUID(command.artifact_id)
        cursor.execute(
            "SELECT content_hash FROM safety_artifacts WHERE artifact_id = %s",
            (artifact_id,),
        )
        artifact = cursor.fetchone()
        if artifact is None or artifact[0] != command.artifact_content_hash:
            raise RegistryDenied(RegistryDenialCode.ARTIFACT_UNKNOWN)
        cursor.execute(
            "SELECT 1 FROM artifact_revocation_events WHERE artifact_id = %s LIMIT 1",
            (artifact_id,),
        )
        if cursor.fetchone() is not None:
            raise RegistryDenied(RegistryDenialCode.ARTIFACT_REVOKED)

        revocation_id = uuid4()
        registry_revision = current_revision + 1
        cursor.execute(
            """
            INSERT INTO artifact_revocation_events (
                revocation_id, artifact_id, registry_revision, effective_at, reason_code,
                operator_identity, command_key, request_hash, causation_incident_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING recorded_at
            """,
            (
                revocation_id,
                artifact_id,
                registry_revision,
                effective_at,
                reason_code,
                UUID(command.actor.identity_id),
                command.idempotency_key,
                command.request_hash,
                UUID(command.causation_incident_id),
            ),
        )
        recorded_row = cursor.fetchone()
        assert recorded_row is not None
        recorded_at = recorded_row[0]
        cursor.execute(
            """
            UPDATE safety_registry_state
               SET registry_revision = %s, last_revocation_id = %s
             WHERE registry_scope = %s
            """,
            (registry_revision, revocation_id, SYSTEM_SCOPE),
        )
        cursor.execute(
            """
            INSERT INTO registry_management_receipts (
                command_key, request_hash, revocation_id, registry_revision,
                artifact_id, effective_at, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                command.idempotency_key,
                command.request_hash,
                revocation_id,
                registry_revision,
                artifact_id,
                effective_at,
                recorded_at,
            ),
        )
        cursor.execute(
            """
            INSERT INTO registry_audit_events (event_id, revocation_id, operator_identity)
            VALUES (%s, %s, %s)
            """,
            (uuid4(), revocation_id, UUID(command.actor.identity_id)),
        )
        cursor.execute(
            """
            INSERT INTO registry_outbox (delivery_id, revocation_id)
            VALUES (%s, %s)
            """,
            (uuid4(), revocation_id),
        )
        return RevocationResult(
            revocation_id=str(revocation_id),
            registry_revision=registry_revision,
            artifact_id=command.artifact_id,
            effective_at=effective_at,
            recorded_at=recorded_at,
        )


def execute_stop_without_registry(
    connection: Connection[Any],
    subject_id: str,
    mutation: StopMutation[_T],
    *,
    lock_timeout_ms: int = 1_000,
) -> _T:
    """Run STOP from S01 directly; this function never reads or locks S51."""

    with connection.transaction():
        cursor = connection.cursor()
        _set_lock_timeout(cursor, lock_timeout_ms)
        cursor.execute(
            "SELECT subject_id FROM subject_coordination WHERE subject_id = %s FOR UPDATE",
            (UUID(subject_id),),
        )
        if cursor.fetchone() is None:
            raise RegistryDenied(RegistryDenialCode.AUTHORIZATION_INELIGIBLE)
        return mutation(cursor)
