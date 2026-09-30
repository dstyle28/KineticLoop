"""Deterministic Authorization validity and executability evaluation.

The functions in this module are deliberately pure. Repository transaction owners
remain responsible for locking S51 then S01 and for reading authoritative current
state. The values returned here are observations and certificate material, never a
bearer permission for a later mutation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Mapping, Sequence
from uuid import UUID

AUTHORIZATION_METHOD_VERSION = "kl022-v1"
_CLEAR_CONTROL_STATES = frozenset({"CLEAR", "CLEARED", "INACTIVE"})
_ARTIFACT_POLICY_KINDS = frozenset({"POLICY", "POLICY_BUNDLE"})


class AuthorizationEvaluationError(ValueError):
    """A required Authorization basis cannot be proved and must deny."""


def _aware(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AuthorizationEvaluationError(f"{label} must be an aware datetime")
    return value


def canonical_certificate_timestamp(value: object, label: str) -> str:
    """Serialize one instant in the certificate's canonical UTC RFC3339 form."""

    return _aware(value, label).astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ValidityDependency:
    """One immutable identity in an authorization certificate closure."""

    dependency_kind: str
    identity: str
    revision: str | int
    valid_from: datetime | None
    valid_until: datetime | None
    validity_kind: str = "BOUNDED"
    requires_validity: bool = True
    artifact_kind: str | None = None
    timeless_approval_policy: str | None = None
    timeless_approval_reason: str | None = None
    admissible: bool | None = True
    revoked: bool | None = False
    dependency_ids: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def certificate_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "dependency_kind": self.dependency_kind,
            "identity": self.identity,
            "revision": self.revision,
        }
        if self.validity_kind != "BOUNDED" or self.dependency_kind == "ARTIFACT":
            entry["validity_kind"] = self.validity_kind
        if self.valid_from is not None:
            entry["valid_from"] = canonical_certificate_timestamp(
                self.valid_from, "dependency valid_from"
            )
        if self.valid_until is not None:
            entry["valid_until"] = canonical_certificate_timestamp(
                self.valid_until, "dependency valid_until"
            )
        if self.artifact_kind is not None:
            entry["artifact_kind"] = self.artifact_kind
        if self.timeless_approval_policy is not None:
            entry["timeless_approval_policy"] = self.timeless_approval_policy
        if self.timeless_approval_reason is not None:
            entry["timeless_approval_reason"] = self.timeless_approval_reason
        if self.dependency_ids:
            entry["dependency_ids"] = list(self.dependency_ids)
        entry.update(dict(self.attributes))
        return entry


@dataclass(frozen=True)
class ValidityClosure:
    """Finite immutable interval and deterministic certificate closure."""

    valid_from: datetime
    valid_until: datetime
    dependencies: tuple[Mapping[str, Any], ...]
    closure_digest: str
    method_version: str = AUTHORIZATION_METHOD_VERSION


def evaluate_validity_closure(
    *,
    authoritative_now: datetime,
    dependencies: Sequence[ValidityDependency],
    requested_absolute_end: datetime | None = None,
) -> ValidityClosure:
    """Return the exact finite minimum of all required live dependency bounds."""

    now = _aware(authoritative_now, "authoritative_now")
    if not dependencies:
        raise AuthorizationEvaluationError("authorization dependency closure is empty")

    identities: dict[str, ValidityDependency] = {}
    exact_keys: set[tuple[str, str, str]] = set()
    for dependency in dependencies:
        if not dependency.dependency_kind.strip() or not dependency.identity.strip():
            raise AuthorizationEvaluationError("dependency identity is missing")
        if dependency.revision is None or str(dependency.revision).strip() == "":
            raise AuthorizationEvaluationError("dependency revision is missing")
        key = (
            dependency.dependency_kind,
            dependency.identity,
            str(dependency.revision),
        )
        if key in exact_keys:
            raise AuthorizationEvaluationError("dependency closure contains a duplicate identity")
        if dependency.identity in identities:
            raise AuthorizationEvaluationError("dependency identity is ambiguous")
        exact_keys.add(key)
        identities[dependency.identity] = dependency

    finite_ends: list[datetime] = []
    for dependency in dependencies:
        if dependency.admissible is not True or dependency.revoked is not False:
            raise AuthorizationEvaluationError("dependency current admission is unprovable")
        if not dependency.requires_validity:
            continue
        valid_from = _aware(dependency.valid_from, "dependency valid_from")
        if valid_from > now:
            raise AuthorizationEvaluationError("dependency is not yet effective")
        if dependency.validity_kind == "TIMELESS":
            if dependency.dependency_kind != "ARTIFACT":
                raise AuthorizationEvaluationError("only an artifact may be TIMELESS")
            if dependency.valid_until is not None:
                raise AuthorizationEvaluationError("TIMELESS cannot carry an artificial end")
            if not (dependency.timeless_approval_reason or "").strip():
                raise AuthorizationEvaluationError("TIMELESS approval reason is missing")
            approval_identity = dependency.timeless_approval_policy or ""
            try:
                UUID(approval_identity)
            except ValueError as error:
                raise AuthorizationEvaluationError(
                    "TIMELESS approval policy identity is malformed"
                ) from error
            policy = identities.get(approval_identity)
            if (
                policy is None
                or policy.dependency_kind != "ARTIFACT"
                or policy.artifact_kind not in _ARTIFACT_POLICY_KINDS
                or policy.admissible is not True
                or policy.revoked is not False
                or approval_identity not in dependency.dependency_ids
            ):
                raise AuthorizationEvaluationError(
                    "TIMELESS approval policy is absent from the exact closure"
                )
            continue
        if dependency.validity_kind != "BOUNDED":
            raise AuthorizationEvaluationError("dependency validity kind is unknown")
        valid_until = _aware(dependency.valid_until, "dependency valid_until")
        if valid_until <= now or valid_from >= valid_until:
            raise AuthorizationEvaluationError("dependency validity is expired or non-increasing")
        finite_ends.append(valid_until)

    if requested_absolute_end is not None:
        requested = _aware(requested_absolute_end, "requested_absolute_end")
        if requested <= now:
            raise AuthorizationEvaluationError("requested authorization end is not future")
        finite_ends.append(requested)
    if not finite_ends:
        raise AuthorizationEvaluationError("authorization closure has no finite bound")

    valid_until = min(finite_ends)
    if valid_until <= now:
        raise AuthorizationEvaluationError("authorization interval is not strictly increasing")
    certificate_entries = [
        dependency.certificate_entry()
        for dependency in sorted(
            dependencies,
            key=lambda item: (
                item.dependency_kind,
                item.identity,
                str(item.revision),
            ),
        )
    ]
    if requested_absolute_end is not None:
        certificate_entries.append(
            {
                "dependency_kind": "REQUESTED_ABSOLUTE_END",
                "identity": "client-shortening-request",
                "revision": 1,
                "valid_from": canonical_certificate_timestamp(now, "authoritative_now"),
                "valid_until": canonical_certificate_timestamp(
                    requested_absolute_end, "requested_absolute_end"
                ),
            }
        )
        certificate_entries.sort(
            key=lambda item: (
                str(item["dependency_kind"]),
                str(item["identity"]),
                str(item["revision"]),
            )
        )
    entries = tuple(MappingProxyType(entry) for entry in certificate_entries)
    serializable_entries = [dict(entry) for entry in entries]
    digest = hashlib.sha256(
        json.dumps(serializable_entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ValidityClosure(now, valid_until, entries, digest)


@dataclass(frozen=True)
class ExecutabilityBasis:
    """Current authoritative facts for one exact P/A/scope/session observation."""

    authoritative_now: datetime
    requested_subject_id: str
    authorization_subject_id: str | None
    prescription_content_hash: str | None
    authorization_content_hash: str | None
    requested_scope: str
    authorization_scope: str | None
    current_epoch: int
    authorization_epoch: int | None
    valid_from: datetime | None
    valid_until: datetime | None
    target_state: str | None
    controls_proven: bool
    applicable_control_states: tuple[str, ...]
    policy_admissible: bool | None
    session_relation_current: bool | None
    dependency_eligible: bool | None


@dataclass(frozen=True)
class ExecutabilityDecision:
    """A non-bearer observation that cannot authorize a later T7 mutation."""

    is_executable: bool
    observed_at: datetime
    denial_reasons: tuple[str, ...]
    non_bearer: bool = True


def controls_are_eligible(*, proven: bool, states: Sequence[str]) -> bool:
    """Return true only for a fully proved set of explicitly cleared controls."""

    return proven and all(state in _CLEAR_CONTROL_STATES for state in states)


def evaluate_executability(basis: ExecutabilityBasis) -> ExecutabilityDecision:
    """Evaluate every frozen current eligibility dimension using a half-open interval."""

    now = _aware(basis.authoritative_now, "authoritative_now")
    reasons: list[str] = []
    if not basis.authorization_subject_id or (
        basis.requested_subject_id != basis.authorization_subject_id
    ):
        reasons.append("SUBJECT_MISMATCH")
    if not basis.prescription_content_hash or (
        basis.prescription_content_hash != basis.authorization_content_hash
    ):
        reasons.append("CONTENT_MISMATCH")
    if not basis.authorization_scope or basis.requested_scope != basis.authorization_scope:
        reasons.append("SCOPE_MISMATCH")
    if basis.authorization_epoch is None or basis.current_epoch != basis.authorization_epoch:
        reasons.append("EPOCH_MISMATCH")
    try:
        valid_from = _aware(basis.valid_from, "authorization valid_from")
        valid_until = _aware(basis.valid_until, "authorization valid_until")
        if not valid_from <= now < valid_until:
            reasons.append("TIME_INELIGIBLE")
    except AuthorizationEvaluationError:
        reasons.append("TIME_UNPROVABLE")
    if basis.target_state != "ACTIVE":
        reasons.append("TARGET_INACTIVE")
    if not controls_are_eligible(
        proven=basis.controls_proven,
        states=basis.applicable_control_states,
    ):
        reasons.append("CONTROL_INELIGIBLE")
    if basis.policy_admissible is not True:
        reasons.append("POLICY_INELIGIBLE")
    if basis.session_relation_current is not True:
        reasons.append("SESSION_RELATION_INELIGIBLE")
    if basis.dependency_eligible is not True:
        reasons.append("DEPENDENCY_INELIGIBLE")
    return ExecutabilityDecision(not reasons, now, tuple(reasons))
