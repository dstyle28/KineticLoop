"""Deterministic closed factset reconstruction; no admission/qualification decisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID


class FactsetError(ValueError):
    """The selected evidence basis or chain cannot be proved complete."""


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Member:
    kind: Literal["FACT", "ADMISSION", "ASSOCIATION", "MAPPING"]
    key: str
    scope: str
    revision_id: UUID | None
    operation: Literal["SET", "REMOVE"] = "SET"

    def __post_init__(self) -> None:
        if self.kind not in {"FACT", "ADMISSION", "ASSOCIATION", "MAPPING"}:
            raise FactsetError("unsupported member kind")
        if not self.key.strip() or not self.scope.strip():
            raise FactsetError("logical key and scope are required")
        if self.operation not in {"SET", "REMOVE"}:
            raise FactsetError("unsupported operation")
        if (self.operation == "SET") != isinstance(self.revision_id, UUID):
            raise FactsetError("SET requires a typed revision; REMOVE is a tombstone")

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.kind, self.key, self.scope

    def payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "scope": self.scope,
            "revision_id": str(self.revision_id) if self.revision_id else None,
            "operation": self.operation,
        }

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> Member:
        return cls(
            value["kind"],
            value["key"],
            value["scope"],
            UUID(value["revision_id"]) if value["revision_id"] else None,
            value["operation"],
        )


@dataclass(frozen=True)
class EvidenceBasis:
    """Explicit selected revision sets, including unresolved and contrary evidence."""

    associations: tuple[UUID, ...]
    admissions: tuple[UUID, ...]
    mappings: tuple[UUID, ...]
    knowledge_boundary: str
    effective_scope: str

    def __post_init__(self) -> None:
        if not self.knowledge_boundary.strip() or not self.effective_scope.strip():
            raise FactsetError("knowledge boundary and effective scope are required")
        for ids in (self.associations, self.admissions, self.mappings):
            if (
                type(ids) is not tuple
                or len(set(ids)) != len(ids)
                or any(not isinstance(x, UUID) for x in ids)
            ):
                raise FactsetError("basis revisions must be unique typed identities")

    def payload(self) -> dict[str, Any]:
        return {
            "associations": sorted(map(str, self.associations)),
            "admissions": sorted(map(str, self.admissions)),
            "mappings": sorted(map(str, self.mappings)),
            "knowledge_boundary": self.knowledge_boundary,
            "effective_scope": self.effective_scope,
        }

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> EvidenceBasis:
        return cls(
            tuple(UUID(x) for x in value["associations"]),
            tuple(UUID(x) for x in value["admissions"]),
            tuple(UUID(x) for x in value["mappings"]),
            value["knowledge_boundary"],
            value["effective_scope"],
        )


@dataclass(frozen=True)
class Factset:
    id: UUID
    subject_id: UUID
    status: str
    mode: str
    parent_id: UUID | None
    depth: int
    member_revision: int
    members: tuple[Member, ...]
    basis: EvidenceBasis
    checkpoint: tuple[Member, ...] = ()
    membership_digest: str | None = None
    member_count: int | None = None


@dataclass(frozen=True)
class Reconstruction:
    members: tuple[Member, ...]
    membership_digest: str
    member_count: int


def reconstruct(
    root: Factset, ancestors: Mapping[UUID, Factset], *, max_depth: int, canonical: bool = False
) -> Reconstruction:
    if type(max_depth) is not int or max_depth < 0:
        raise FactsetError("invalid depth bound")
    chain: list[Factset] = []
    seen: set[UUID] = set()
    node = root
    while True:
        if node.id in seen:
            raise FactsetError("cyclic chain")
        seen.add(node.id)
        if node.subject_id != root.subject_id:
            raise FactsetError("foreign parent")
        if (canonical or node is not root) and node.status != "SEALED":
            raise FactsetError("unsealed chain")
        if node.mode not in {"FULL", "DELTA"} or not 0 <= node.depth <= max_depth:
            raise FactsetError("invalid chain depth/mode")
        if len({m.identity for m in node.members}) != len(node.members):
            raise FactsetError("duplicate member")
        chain.append(node)
        if len(chain) > max_depth + 1:
            raise FactsetError("chain exceeds bound")
        if node.mode == "FULL":
            if node.parent_id is not None or node.depth != 0:
                raise FactsetError("FULL must close the chain")
            break
        if node.checkpoint or node.parent_id is None:
            raise FactsetError("DELTA requires parent and no checkpoint")
        parent = ancestors.get(node.parent_id)
        if parent is None:
            raise FactsetError("missing parent")
        if parent.depth + 1 != node.depth:
            raise FactsetError("invalid parent depth")
        node = parent
    selected: dict[tuple[str, str, str], Member] = {}
    for item in reversed(chain):
        if item.mode == "FULL":
            if any(m.operation != "SET" for m in item.checkpoint):
                raise FactsetError("invalid checkpoint")
            if len({m.identity for m in item.checkpoint}) != len(item.checkpoint):
                raise FactsetError("duplicate checkpoint member")
            selected = {m.identity: m for m in item.checkpoint}
        for member in item.members:
            if member.operation == "REMOVE":
                selected.pop(member.identity, None)
            else:
                selected[member.identity] = member
        # Each SEALED node is checked against its own complete selected basis.
        ordered = tuple(selected[k] for k in sorted(selected))
        _validate_basis(ordered, item.basis)
        closed_digest = digest(
            {
                "method": "kl023-members-v1",
                "basis": item.basis.payload(),
                "members": [m.payload() for m in ordered],
            }
        )
        if item.status in {"READY", "SEALED"} and (
            closed_digest != item.membership_digest or len(ordered) != item.member_count
        ):
            raise FactsetError("closed digest/count mismatch")
    return Reconstruction(ordered, closed_digest, len(ordered))


def _validate_basis(members: tuple[Member, ...], basis: EvidenceBasis) -> None:
    for kind, expected in (
        ("ASSOCIATION", basis.associations),
        ("ADMISSION", basis.admissions),
        ("MAPPING", basis.mappings),
    ):
        actual = {m.revision_id for m in members if m.kind == kind}
        if actual != set(expected):
            raise FactsetError(f"complete {kind} basis was not retained")


def storage_plan(parent: Factset | None, max_depth: int) -> tuple[str, UUID | None, int]:
    if type(max_depth) is not int or max_depth < 0:
        raise FactsetError("invalid depth bound")
    if parent is None:
        return "FULL", None, 0
    if parent.status != "SEALED":
        raise FactsetError("unsealed parent")
    if parent.depth >= max_depth:
        return "FULL", None, 0
    return "DELTA", parent.id, parent.depth + 1


def certificate_basis(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Additional immutable basis bound by owned-build completion certificates."""
    return {
        key: payload.get(key)
        for key in (
            "builder_identity",
            "program_revision_id",
            "policy_id",
            "mapping_revision_id",
            "parent_factset_id",
            "max_delta_depth",
        )
    } | {"domain_basis_digest": payload.get("domain_basis_digest")}


def completion_certificate(
    *,
    subject_id: UUID,
    build_id: UUID,
    member_revision: int,
    membership_digest: str,
    member_count: int,
    payload: Mapping[str, Any],
) -> str:
    return digest(
        {
            "method_version": "kl015-v1",
            "factset_id": str(build_id),
            "subject_id": str(subject_id),
            "captured_input_frontier": payload["captured_input_frontier"],
            "captured_epoch": payload["captured_epoch"],
            "completed_member_revision": member_revision,
            "membership_digest": membership_digest,
            "member_count": member_count,
        }
        | certificate_basis(payload)
    )
