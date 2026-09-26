"""Strict artifact identity and dependency-admission contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kineticloop.contracts.commands import RegisterArtifact, TransactionBoundary
from kineticloop.primitives import canonical_id, canonical_json, canonical_sha256, canonical_utc

MAX_ARTIFACT_DEPENDENCY_NODES = 128
MAX_ARTIFACT_DEPENDENCY_DEPTH = 16


class ArtifactKind(StrEnum):
    MODEL = "MODEL"
    PROMPT = "PROMPT"
    TOOL = "TOOL"
    RUNTIME = "RUNTIME"
    POLICY = "POLICY"


class ArtifactBindingKind(StrEnum):
    POLICY_BUNDLE = "POLICY_BUNDLE"
    EXERCISE_CATALOG = "EXERCISE_CATALOG"
    EVALUATION_RELEASE = "EVALUATION_RELEASE"


class ArtifactDependencyError(ValueError):
    """The submitted dependency closure is not safe to register."""


@dataclass(frozen=True, slots=True)
class ArtifactValiditySpec:
    validity_kind: str
    valid_from: datetime
    binding_kind: ArtifactBindingKind
    binding_id: str
    valid_until: datetime | None = None
    timeless_approval_policy: str | None = None
    timeless_approval_reason: str | None = None
    closure_complete: bool = True

    def __post_init__(self) -> None:
        canonical_id(self.binding_id)
        if self.valid_from.tzinfo is None or self.valid_from.utcoffset() is None:
            raise ValueError("valid_from must be timezone-aware")
        if self.validity_kind == "BOUNDED":
            if (
                self.valid_until is None
                or self.valid_until.tzinfo is None
                or self.valid_until.utcoffset() is None
                or self.valid_until <= self.valid_from
            ):
                raise ValueError("BOUNDED validity requires valid_until after valid_from")
            if self.timeless_approval_policy is not None or self.timeless_approval_reason is not None:
                raise ValueError("BOUNDED validity cannot carry TIMELESS approval")
        elif self.validity_kind == "TIMELESS":
            if self.valid_until is not None:
                raise ValueError("TIMELESS validity cannot carry valid_until")
            if not self.timeless_approval_policy or not self.timeless_approval_reason:
                raise ValueError("TIMELESS validity requires approval policy and reason")
        else:
            raise ValueError("validity_kind must be BOUNDED or TIMELESS")
        if not self.closure_complete:
            raise ValueError("artifact dependency closure must be explicitly complete")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "binding_id": self.binding_id,
            "binding_kind": self.binding_kind.value,
            "closure_complete": self.closure_complete,
            "timeless_approval_policy": self.timeless_approval_policy,
            "timeless_approval_reason": self.timeless_approval_reason,
            "valid_from": canonical_utc(self.valid_from),
            "valid_until": (
                canonical_utc(self.valid_until) if self.valid_until is not None else None
            ),
            "validity_kind": self.validity_kind,
        }

    def to_canonical_json(self) -> str:
        return canonical_json(self.canonical_payload())

    def sha256(self) -> str:
        return canonical_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class ArtifactRegistration:
    command: RegisterArtifact
    artifact_identity: str
    artifact_version: str
    validity: ArtifactValiditySpec

    def __post_init__(self) -> None:
        if not self.artifact_identity.strip() or not self.artifact_version.strip():
            raise ValueError("artifact identity and version must be non-empty")
        if self.command.artifact_kind not in set(ArtifactKind):
            raise ValueError("unsupported artifact kind")
        if len(set(self.command.dependency_ids)) != len(self.command.dependency_ids):
            raise ArtifactDependencyError("dependency identities must be unique")
        if self.command.artifact_id in self.command.dependency_ids:
            raise ArtifactDependencyError("artifact cannot depend on itself")
        expected_binding = {
            ArtifactKind.MODEL: ArtifactBindingKind.EVALUATION_RELEASE,
            ArtifactKind.PROMPT: ArtifactBindingKind.EVALUATION_RELEASE,
            ArtifactKind.RUNTIME: ArtifactBindingKind.EVALUATION_RELEASE,
            ArtifactKind.TOOL: ArtifactBindingKind.EXERCISE_CATALOG,
            ArtifactKind.POLICY: ArtifactBindingKind.POLICY_BUNDLE,
        }[ArtifactKind(self.command.artifact_kind)]
        if self.validity.binding_kind is not expected_binding:
            raise ValueError("artifact kind and validity binding kind do not match")
        if self.command.validity_spec_hash != self.validity.sha256():
            raise ValueError("validity_spec_hash does not bind the supplied validity spec")
        if self.validity.validity_kind == "TIMELESS":
            policy_id = self.validity.timeless_approval_policy
            if policy_id is None:
                raise ValueError("TIMELESS validity requires approval policy")
            canonical_id(policy_id)
            if policy_id not in self.command.dependency_ids:
                raise ArtifactDependencyError(
                    "TIMELESS approval policy must be an explicit dependency"
                )


def validate_complete_dependency_closure(
    dependency_ids: tuple[str, ...],
    registered_dependencies: Mapping[str, tuple[str, ...]],
    *,
    maximum_nodes: int = MAX_ARTIFACT_DEPENDENCY_NODES,
    maximum_depth: int = MAX_ARTIFACT_DEPENDENCY_DEPTH,
) -> tuple[str, ...]:
    """Require a unique, pre-registered, acyclic and bounded transitive closure."""

    if len(set(dependency_ids)) != len(dependency_ids):
        raise ArtifactDependencyError("dependency identities must be unique")
    if len(dependency_ids) > maximum_nodes:
        raise ArtifactDependencyError("artifact dependency node bound exceeded")
    declared = set(dependency_ids)
    for artifact_id in dependency_ids:
        canonical_id(artifact_id)
        if artifact_id not in registered_dependencies:
            raise ArtifactDependencyError("artifact dependency is not pre-registered")

    visited: set[str] = set()

    def visit(node: str, path: tuple[str, ...]) -> None:
        if len(path) > maximum_depth:
            raise ArtifactDependencyError("artifact dependency depth bound exceeded")
        if node in path:
            raise ArtifactDependencyError("artifact dependency graph is cyclic")
        if node in visited:
            return
        dependencies = registered_dependencies.get(node)
        if dependencies is None:
            raise ArtifactDependencyError("artifact dependency is not pre-registered")
        for dependency in dependencies:
            if dependency not in declared:
                raise ArtifactDependencyError("artifact dependency closure is incomplete")
            visit(dependency, (*path, node))
        visited.add(node)

    for artifact_id in dependency_ids:
        visit(artifact_id, ())
    return tuple(sorted(declared))


def require_artifact_references(
    boundary: TransactionBoundary, artifact_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """T3/T6/T7 commands must bind an exact non-empty artifact closure."""

    if boundary not in {
        TransactionBoundary.T3,
        TransactionBoundary.T6,
        TransactionBoundary.T7,
    }:
        raise ValueError("artifact references are required only at T3/T6/T7")
    if not artifact_ids or len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError("an exact unique artifact dependency closure is required")
    for artifact_id in artifact_ids:
        canonical_id(artifact_id)
    return artifact_ids
