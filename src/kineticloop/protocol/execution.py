"""Typed isolated execution ingress; no database or command capabilities."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from kineticloop.contracts.commands import (
    CommitBundle,
    ContinueSession,
    ResumeSession,
    StartSession,
    TestOnlyScope,
)
from kineticloop.identity import ActorRole, RoleIdentity


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def command_digest(command: CommitBundle | StartSession | ContinueSession | ResumeSession) -> str:
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

    def require_wire(
        self, command: CommitBundle | StartSession | ContinueSession | ResumeSession
    ) -> None:
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


@dataclass(frozen=True, slots=True)
class FullCommitRequest:
    """Closed internal full TEST input; public CommitBundle stays unchanged."""

    command: CommitBundle
    sources: Mapping[str, Mapping[str, str]]

    def __post_init__(self) -> None:
        names = {
            "snapshot",
            "fitness",
            "demand",
            "nutrition",
            "resolution",
            "nutrition_resolution",
            "validation",
        }
        if (
            type(self.command) is not CommitBundle
            or not isinstance(self.sources, Mapping)
            or set(self.sources) != names
        ):
            raise ValueError("exact full F/D/N/two-resolution/validation closure required")
        for source in self.sources.values():
            if not isinstance(source, Mapping) or set(source) != {"id", "hash"}:
                raise ValueError("exact immutable source descriptor required")
            if (
                type(source["id"]) is not str
                or str(UUID(source["id"])) != source["id"]
                or type(source["hash"]) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", source["hash"])
            ):
                raise ValueError("canonical source identity/hash required")
        if self.sources["validation"][
            "id"
        ] != self.command.validation_id or self.command.result_fingerprint != digest(
            {"contract": "kl079-full-actions-v1", "sources": dict(self.sources)}
        ):
            raise ValueError("full result fingerprint/validation binding mismatch")


@dataclass(frozen=True, slots=True)
class OrdinaryPause:
    """Non-granting internal TEST lifecycle request, distinct from protective T2."""

    identity: ExecutionIdentity
    key: str
    session_id: UUID
    binding_id: UUID
    binding_hash: str
    expected_execution_revision: int
    reason: str

    def __post_init__(self) -> None:
        if type(self.identity) is not ExecutionIdentity:
            raise ValueError("exact pause TEST identity required")
        self.identity.__post_init__()
        if any(type(v) is not UUID for v in (self.session_id, self.binding_id)):
            raise ValueError("exact pause session/binding identities required")
        if (
            type(self.expected_execution_revision) is not int
            or self.expected_execution_revision < 1
        ):
            raise ValueError("positive expected execution revision required")
        for value, bound in ((self.key, 200), (self.reason, 500)):
            if (
                type(value) is not str
                or not value.strip()
                or value != value.strip()
                or len(value) > bound
            ):
                raise ValueError("bounded nonempty ordinary pause key/reason required")
        if type(self.binding_hash) is not str or not re.fullmatch(
            r"[0-9a-f]{64}", self.binding_hash
        ):
            raise ValueError("exact immutable pause binding hash required")


def binding_digest(row: Mapping[str, Any]) -> str:
    """Hash the closed immutable START/RESUME identity, independent of display data."""
    fields = (
        "id",
        "subject_id",
        "binding_kind",
        "binding_revision",
        "accepted_at",
        "execution_scope",
        "ref_s02_id",
        "ref_s40_id",
        "ref_s42_id",
        "ref_s44_id",
    )
    return digest({key: str(row[key]) if key != "binding_revision" else row[key] for key in fields})
