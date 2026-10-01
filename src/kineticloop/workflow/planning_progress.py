"""Internal preparation identities and frozen directed attempt transitions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.workflow.planning import ATTEMPT_ACTIVE, PlanningDenied, digest

FORWARD = dict(
    zip(
        (
            "CREATED",
            "LEASED",
            "BUILDING_CONTEXT",
            "FITNESS",
            "DEMAND_FEATURES",
            "NUTRITION",
            "VALIDATING",
        ),
        (
            "LEASED",
            "BUILDING_CONTEXT",
            "FITNESS",
            "DEMAND_FEATURES",
            "NUTRITION",
            "VALIDATING",
            "COMMIT_READY",
        ),
        strict=True,
    )
)
EXITS = frozenset({"STALE", "FAILED", "CANCELLED", "LEASE_LOST"})
MANDATORY_BLOCKS = frozenset(
    {
        "target_priorities",
        "program",
        "constraints",
        "restrictions_holds",
        "overrides",
        "sequence",
        "progression",
        "recent_execution",
        "data_quality_time",
    }
)
POLICY_BLOCKS = MANDATORY_BLOCKS - {"program", "constraints"}


def eligible_at(now: datetime, valid_from: datetime, valid_until: datetime) -> bool:
    return valid_from <= now < valid_until


def require_transition(source: str, target: str) -> None:
    if source not in ATTEMPT_ACTIVE or (FORWARD.get(source) != target and target not in EXITS):
        raise PlanningDenied("transition is outside Protocol 6.3; COMMITTED belongs to T6")


def hash_identity(value: str) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise PlanningDenied("canonical SHA256 required")


@dataclass(frozen=True, slots=True)
class ProgressIdentity:
    """Authenticated ingress identity, supplied separately from operation data."""

    actor: RoleIdentity
    subject_id: UUID
    policy_id: UUID
    environment_id: UUID
    principal: str

    def __post_init__(self) -> None:
        if type(self.actor) is not RoleIdentity or self.actor.role != ActorRole.TEST:
            raise PlanningDenied("authenticated TEST progress identity required")
        if any(type(v) is not UUID for v in (self.subject_id, self.policy_id, self.environment_id)):
            raise PlanningDenied("exact isolated registration required")
        if self.principal not in {"kl_test_subject_1_login", "kl_test_subject_2_login"}:
            raise PlanningDenied("canonical TEST principal required")

    @property
    def key(self) -> str:
        return f"{self.actor.role}:{self.actor.identity_id}"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProgressBasis:
    subject_id: UUID
    key: str
    intent_id: UUID
    request_id: UUID
    request_revision: int
    attempt_id: UUID
    expected_owner: str
    fence: int
    manifest_id: UUID
    epoch: int
    source_state: str

    def __post_init__(self) -> None:
        if any(
            type(v) is not UUID
            for v in (
                self.subject_id,
                self.intent_id,
                self.request_id,
                self.attempt_id,
                self.manifest_id,
            )
        ) or any(type(v) is not int for v in (self.request_revision, self.fence, self.epoch)):
            raise PlanningDenied("exact progress identities required")
        if self.request_revision <= 0 or self.fence <= 0 or self.epoch < 0:
            raise PlanningDenied("invalid revision/fence/epoch")
        if (
            not isinstance(self.key, str)
            or not self.key.strip()
            or len(self.key) > 512
            or not isinstance(self.expected_owner, str)
            or not self.expected_owner
        ):
            raise PlanningDenied("operation key and expected owner required")
        if self.source_state not in ATTEMPT_ACTIVE:
            raise PlanningDenied("terminal or unknown source attempt")


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordSnapshot(ProgressBasis):
    builder_id: UUID
    builder_hash: str
    source_cutoff: datetime
    context: Mapping[str, Any]
    context_hash: str
    accounting: Mapping[str, Any]

    def __post_init__(self) -> None:
        ProgressBasis.__post_init__(self)
        if self.source_state != "BUILDING_CONTEXT" or type(self.builder_id) is not UUID:
            raise PlanningDenied("snapshot requires BUILDING_CONTEXT and exact builder")
        hash_identity(self.builder_hash)
        hash_identity(self.context_hash)
        if (
            type(self.source_cutoff) is not datetime
            or self.source_cutoff.tzinfo is None
            or not isinstance(self.context, Mapping)
            or not isinstance(self.accounting, Mapping)
        ):
            raise PlanningDenied("canonical context/cutoff/accounting required")
        if self.context_hash != digest(dict(self.context)):
            raise PlanningDenied("context hash mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class AdvanceAttempt(ProgressBasis):
    target_state: str
    sources: Mapping[str, Mapping[str, str]]
    failure_code: str | None = None

    def __post_init__(self) -> None:
        ProgressBasis.__post_init__(self)
        require_transition(self.source_state, self.target_state)
        if not isinstance(self.sources, Mapping):
            raise PlanningDenied("explicit immutable source identities required")
        expected = {
            "FITNESS": {"snapshot"},
            "DEMAND_FEATURES": {"snapshot", "fitness"},
            "NUTRITION": {"snapshot", "fitness", "demand"},
            "VALIDATING": {"snapshot", "fitness", "demand", "nutrition"},
            "COMMIT_READY": {
                "snapshot",
                "fitness",
                "demand",
                "nutrition",
                "resolution",
                "validation",
            },
        }.get(self.target_state, set())
        if set(self.sources) != expected:
            raise PlanningDenied("stage requires exact source set")
        for source in self.sources.values():
            if set(source) != {"id", "hash"}:
                raise PlanningDenied("source identity/hash required")
            UUID(source["id"])
            hash_identity(source["hash"])
        if (self.target_state in EXITS) != (
            isinstance(self.failure_code, str) and bool(self.failure_code.strip())
        ):
            raise PlanningDenied("terminal exit requires an explicit failure reason")
