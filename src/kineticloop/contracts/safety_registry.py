"""Fail-closed contract for the frozen SafetyRegistry command surface."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from kineticloop.primitives import canonical_id


class RegistryCommand(StrEnum):
    PUBLISH_MANIFEST = "PublishManifest"
    COMMIT_BUNDLE = "CommitBundle"
    REAUTHORIZE = "Reauthorize"
    START_SESSION = "StartSession"
    RESUME_SESSION = "ResumeSession"
    CONTINUE_SESSION = "ContinueSession"


class RegistryDenialCode(StrEnum):
    REGISTRY_UNAVAILABLE = "REGISTRY_UNAVAILABLE"
    REGISTRY_TIMEOUT = "REGISTRY_TIMEOUT"
    REGISTRY_STALE = "REGISTRY_STALE"
    ARTIFACT_UNKNOWN = "ARTIFACT_UNKNOWN"
    ARTIFACT_REVOKED = "ARTIFACT_REVOKED"
    ARTIFACT_EXPIRED = "ARTIFACT_EXPIRED"
    VALIDITY_UNDEFINED = "VALIDITY_UNDEFINED"
    DEPENDENCY_INCOMPLETE = "DEPENDENCY_INCOMPLETE"
    AUTHORIZATION_INELIGIBLE = "AUTHORIZATION_INELIGIBLE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    COMMAND_NOT_AUTHORIZED = "COMMAND_NOT_AUTHORIZED"


class RegistryUnavailableError(RuntimeError):
    """The authoritative registry cannot be read."""


class RegistryGateTimeoutError(TimeoutError):
    """The authoritative gate could not be acquired within its bounded wait."""


class RegistryDenied(PermissionError):
    """A stable fail-closed command rejection."""

    def __init__(self, code: RegistryDenialCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class RegistryEligibility:
    """Bounded eligibility inputs that must be checked after acquiring S51."""

    command: RegistryCommand
    subject_id: str
    artifact_ids: tuple[str, ...]
    observed_at: datetime
    minimum_registry_revision: int = 0

    def __post_init__(self) -> None:
        canonical_id(self.subject_id)
        if not self.artifact_ids:
            raise ValueError("artifact_ids must contain the complete dependency closure")
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("artifact_ids must be unique")
        for artifact_id in self.artifact_ids:
            canonical_id(artifact_id)
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.minimum_registry_revision < 0:
            raise ValueError("minimum_registry_revision cannot be negative")


GATED_COMMANDS = frozenset(RegistryCommand)
T6_COMMANDS = frozenset({RegistryCommand.COMMIT_BUNDLE, RegistryCommand.REAUTHORIZE})
T7_COMMANDS = frozenset(
    {
        RegistryCommand.START_SESSION,
        RegistryCommand.RESUME_SESSION,
        RegistryCommand.CONTINUE_SESSION,
    }
)


def command_requires_registry(command_kind: str) -> bool:
    """Return the closed frozen surface; STOP deliberately remains outside it."""

    return command_kind in {command.value for command in GATED_COMMANDS}


_T = TypeVar("_T")


def fail_closed_registry_check(check: Callable[[], _T]) -> _T:
    """Translate authority availability failures into stable deny results."""

    try:
        return check()
    except RegistryGateTimeoutError as error:
        raise RegistryDenied(RegistryDenialCode.REGISTRY_TIMEOUT) from error
    except RegistryUnavailableError as error:
        raise RegistryDenied(RegistryDenialCode.REGISTRY_UNAVAILABLE) from error
