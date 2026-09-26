"""PostgreSQL command owner for trusted artifact registration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.pq import TransactionStatus

from kineticloop.contracts.artifacts import ArtifactRegistration
from kineticloop.contracts.safety_registry import RegistryDenialCode, RegistryDenied


@dataclass(frozen=True, slots=True)
class ArtifactRegistrationResult:
    artifact_id: str
    registered_at: datetime
    operator_identity: str
    replayed: bool


class ArtifactRegistryTransactionStateError(RuntimeError):
    """RegisterArtifact must own its top-level transaction through commit."""


class ArtifactRegistryDenialCode(StrEnum):
    """RegisterArtifact-specific frozen public denials."""

    IMMUTABLE_ARTIFACT = "IMMUTABLE_ARTIFACT"


_DATABASE_DENIALS = {
    "KL_REGISTRY_COMMAND_NOT_AUTHORIZED": RegistryDenialCode.COMMAND_NOT_AUTHORIZED,
    "KL_REGISTRY_ARTIFACT_UNKNOWN": RegistryDenialCode.ARTIFACT_UNKNOWN,
    "KL_REGISTRY_DEPENDENCY_INCOMPLETE": RegistryDenialCode.DEPENDENCY_INCOMPLETE,
    "KL_REGISTRY_VALIDITY_UNDEFINED": RegistryDenialCode.VALIDITY_UNDEFINED,
    "KL_REGISTRY_UNAVAILABLE": RegistryDenialCode.REGISTRY_UNAVAILABLE,
    "KL_REGISTRY_TIMEOUT": RegistryDenialCode.REGISTRY_TIMEOUT,
    "KL_REGISTRY_IMMUTABLE_ARTIFACT": ArtifactRegistryDenialCode.IMMUTABLE_ARTIFACT,
}


def register_artifact(
    connection: Connection[Any],
    registration: ArtifactRegistration,
    *,
    lock_timeout_ms: int = 1_000,
) -> ArtifactRegistrationResult:
    """Register immutable S49 identity through the session-bound admin routine."""

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise ArtifactRegistryTransactionStateError(
            "RegisterArtifact requires an idle connection"
        )
    if lock_timeout_ms <= 0:
        raise ValueError("lock_timeout_ms must be positive")
    completed = False
    try:
        with connection.transaction():
            row = connection.execute(
                """
                SELECT artifact_id, registered_at, operator_identity, replayed
                FROM kineticloop.registry_register_artifact(
                  %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    UUID(registration.command.artifact_id),
                    registration.command.artifact_kind,
                    registration.command.content_hash,
                    [UUID(value) for value in registration.command.dependency_ids],
                    registration.artifact_identity,
                    registration.artifact_version,
                    registration.validity.to_canonical_json(),
                    lock_timeout_ms,
                ),
            ).fetchone()
            if row is None:
                raise RegistryDenied(RegistryDenialCode.REGISTRY_UNAVAILABLE)
            completed = True
            return ArtifactRegistrationResult(
                artifact_id=str(row[0]),
                registered_at=row[1],
                operator_identity=str(row[2]),
                replayed=bool(row[3]),
            )
    except psycopg.Error as error:
        if completed:
            raise
        message = str(error)
        for marker, denial in _DATABASE_DENIALS.items():
            if marker in message:
                raise RegistryDenied(cast(RegistryDenialCode, denial)) from error
        raise
