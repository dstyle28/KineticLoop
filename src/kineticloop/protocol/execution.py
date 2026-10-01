"""Typed isolated execution ingress; no database or command capabilities."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from kineticloop.contracts.commands import CommitBundle, StartSession, TestOnlyScope
from kineticloop.identity import ActorRole, RoleIdentity


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def command_digest(command: CommitBundle | StartSession) -> str:
    payload = command.model_dump(mode="json")
    payload.pop("request_hash")
    return digest(payload)


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    """Supplied by authenticated ingress, independently of all client request data."""

    actor: RoleIdentity
    subject_id: UUID
    policy_id: UUID
    environment_id: UUID
    principal: str

    def __post_init__(self) -> None:
        if type(self.actor) is not RoleIdentity or self.actor.role != ActorRole.TEST:
            raise ValueError("authenticated TEST identity required")
        if any(
            type(value) is not UUID
            for value in (self.subject_id, self.policy_id, self.environment_id)
        ):
            raise ValueError("exact TEST registration identities required")
        if self.principal not in {"kl_test_subject_1_login", "kl_test_subject_2_login"}:
            raise ValueError("canonical TEST database principal required")

    @property
    def key(self) -> str:
        return f"{self.actor.role}:{self.actor.identity_id}"

    def require_wire(self, command: CommitBundle | StartSession) -> None:
        scope = command.authorization_scope
        if (
            command.actor.role_identity != self.actor
            or command.subject_id != str(self.subject_id)
            or not isinstance(scope, TestOnlyScope)
            or scope.policy_id != str(self.policy_id)
            or scope.environment_id != str(self.environment_id)
            or (
                isinstance(command, CommitBundle)
                and command.expected_owner_id != self.actor.identity_id
            )
            or command_digest(command) != command.request_hash
        ):
            raise ValueError("authenticated TEST command binding mismatch")


@dataclass(frozen=True, slots=True)
class PublishReady:
    subject_id: UUID
    key: str
    build_id: UUID
    sealed_factset_id: UUID
    expected_input_frontier_hash: str
    expected_authorization_epoch: int
    program_revision_id: UUID
    policy_id: UUID
    dependency_basis_hash: str
    artifact_dependency_closure_hash: str

    def __post_init__(self) -> None:
        if any(
            type(value) is not UUID
            for value in (
                self.subject_id,
                self.build_id,
                self.sealed_factset_id,
                self.program_revision_id,
                self.policy_id,
            )
        ):
            raise ValueError("exact publication identities required")
        if any(
            type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in (
                self.expected_input_frontier_hash,
                self.dependency_basis_hash,
                self.artifact_dependency_closure_hash,
            )
        ):
            raise ValueError("exact publication basis hashes required")
        if type(self.key) is not str or not self.key or self.key != self.key.strip():
            raise ValueError("nonempty publication key required")
        if (
            type(self.expected_authorization_epoch) is not int
            or self.expected_authorization_epoch < 0
        ):
            raise ValueError("nonnegative epoch required")
