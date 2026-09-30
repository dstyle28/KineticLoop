from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from kineticloop.protocol.authorization import (
    AuthorizationEvaluationError,
    ExecutabilityBasis,
    ValidityDependency,
    evaluate_executability,
    evaluate_validity_closure,
)

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
APPROVAL_ID = "00000000-0000-8000-8000-000000022001"
TIMELESS_ID = "00000000-0000-8000-8000-000000022002"


def _bound(kind: str, seconds: int, *, identity: str | None = None) -> ValidityDependency:
    return ValidityDependency(
        kind,
        identity or kind.lower(),
        1,
        NOW - timedelta(minutes=1),
        NOW + timedelta(seconds=seconds),
    )


def test_validity_closure_uses_every_bound_and_denies_missing_or_elapsed_basis() -> None:
    dependencies = [
        _bound("MANIFEST", 900),
        _bound("EVIDENCE_RESOLUTION", 800),
        _bound("EVIDENCE_ADMISSION_FRESHNESS", 700),
        _bound("VALIDATION", 600),
        _bound("PROJECTION", 500),
        _bound("ARTIFACT", 400),
        _bound("POLICY_TTL", 300),
        _bound("REQUEST_DEADLINE", 200),
        _bound("CALENDAR", 100),
    ]
    closure = evaluate_validity_closure(
        authoritative_now=NOW,
        dependencies=dependencies,
        requested_absolute_end=NOW + timedelta(seconds=50),
    )
    assert closure.valid_from == NOW
    assert closure.valid_until == NOW + timedelta(seconds=50)
    assert closure.valid_from < closure.valid_until
    assert len(closure.dependencies) == len(dependencies) + 1
    expected_digest = hashlib.sha256(
        json.dumps(
            [dict(item) for item in closure.dependencies],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert closure.closure_digest == expected_digest
    reversed_closure = evaluate_validity_closure(
        authoritative_now=NOW,
        dependencies=list(reversed(dependencies)),
        requested_absolute_end=NOW + timedelta(seconds=50),
    )
    assert reversed_closure.dependencies == closure.dependencies
    assert reversed_closure.closure_digest == closure.closure_digest

    offset = timezone(timedelta(hours=-7))
    offset_dependencies = [
        replace(
            dependency,
            valid_from=(
                dependency.valid_from.astimezone(offset)
                if dependency.valid_from is not None
                else None
            ),
            valid_until=(
                dependency.valid_until.astimezone(offset)
                if dependency.valid_until is not None
                else None
            ),
        )
        for dependency in dependencies
    ]
    offset_closure = evaluate_validity_closure(
        authoritative_now=NOW.astimezone(offset),
        dependencies=offset_dependencies,
        requested_absolute_end=(NOW + timedelta(seconds=50)).astimezone(offset),
    )
    assert offset_closure.dependencies == closure.dependencies
    assert offset_closure.closure_digest == closure.closure_digest
    assert all(
        not str(value).endswith("-07:00")
        for entry in offset_closure.dependencies
        for key, value in entry.items()
        if key in {"valid_from", "valid_until"}
    )

    assert evaluate_validity_closure(
        authoritative_now=NOW,
        dependencies=dependencies,
        requested_absolute_end=NOW + timedelta(seconds=150),
    ).valid_until == NOW + timedelta(seconds=100)
    for index, dependency in enumerate(dependencies):
        candidate = [replace(item, valid_until=NOW + timedelta(hours=2)) for item in dependencies]
        candidate[index] = replace(dependency, valid_until=NOW + timedelta(seconds=25 + index))
        assert evaluate_validity_closure(
            authoritative_now=NOW,
            dependencies=candidate,
        ).valid_until == NOW + timedelta(seconds=25 + index)

    invalid = (
        replace(dependencies[0], valid_from=None),
        replace(dependencies[0], valid_until=None),
        replace(dependencies[0], valid_from=NOW + timedelta(seconds=1)),
        replace(dependencies[0], valid_until=NOW),
        replace(dependencies[0], valid_until=NOW - timedelta(seconds=1)),
        replace(dependencies[0], valid_from=datetime(2026, 9, 29, 11, 0)),
    )
    for dependency in invalid:
        with pytest.raises(AuthorizationEvaluationError):
            evaluate_validity_closure(
                authoritative_now=NOW,
                dependencies=[dependency, *dependencies[1:]],
            )
    with pytest.raises(AuthorizationEvaluationError):
        evaluate_validity_closure(
            authoritative_now=NOW,
            dependencies=dependencies,
            requested_absolute_end=NOW,
        )


def test_timeless_dependency_requires_auditable_policy_in_same_transitive_closure() -> None:
    approval = ValidityDependency(
        "ARTIFACT",
        APPROVAL_ID,
        7,
        NOW - timedelta(days=1),
        NOW + timedelta(hours=2),
        artifact_kind="POLICY",
    )
    timeless = ValidityDependency(
        "ARTIFACT",
        TIMELESS_ID,
        3,
        NOW - timedelta(days=1),
        None,
        validity_kind="TIMELESS",
        artifact_kind="MODEL",
        timeless_approval_policy=APPROVAL_ID,
        timeless_approval_reason="static audited weights",
        dependency_ids=(APPROVAL_ID,),
    )
    bounded = _bound("MANIFEST", 600)
    closure = evaluate_validity_closure(
        authoritative_now=NOW,
        dependencies=[timeless, approval, bounded],
    )
    assert closure.valid_until == NOW + timedelta(seconds=600)
    timeless_entry = next(row for row in closure.dependencies if row["identity"] == TIMELESS_ID)
    assert timeless_entry["validity_kind"] == "TIMELESS"
    assert "valid_until" not in timeless_entry

    invalid = (
        replace(timeless, timeless_approval_reason=""),
        replace(timeless, timeless_approval_policy="missing"),
        replace(timeless, dependency_ids=()),
        replace(timeless, timeless_approval_policy="not-a-uuid"),
        replace(timeless, revoked=True),
        replace(timeless, admissible=None),
    )
    for dependency in invalid:
        with pytest.raises(AuthorizationEvaluationError):
            evaluate_validity_closure(
                authoritative_now=NOW,
                dependencies=[dependency, approval, bounded],
            )
    for bad_policy in (
        replace(approval, artifact_kind="MODEL"),
        replace(approval, valid_until=NOW),
        replace(approval, revoked=True),
    ):
        with pytest.raises(AuthorizationEvaluationError):
            evaluate_validity_closure(
                authoritative_now=NOW,
                dependencies=[timeless, bad_policy, bounded],
            )


def test_is_executable_requires_subject_content_scope_epoch_control_and_strict_time() -> None:
    basis = ExecutabilityBasis(
        authoritative_now=NOW,
        requested_subject_id="subject",
        authorization_subject_id="subject",
        prescription_content_hash="content",
        authorization_content_hash="content",
        requested_scope="EXECUTION",
        authorization_scope="EXECUTION",
        current_epoch=4,
        authorization_epoch=4,
        valid_from=NOW,
        valid_until=NOW + timedelta(minutes=5),
        target_state="ACTIVE",
        controls_proven=True,
        applicable_control_states=(),
        policy_admissible=True,
        session_relation_current=True,
        dependency_eligible=True,
    )
    allowed = evaluate_executability(basis)
    assert allowed.is_executable
    assert allowed.non_bearer
    assert not hasattr(allowed, "permission_token")

    mutations = (
        {"authorization_subject_id": "other"},
        {"authorization_subject_id": None},
        {"authorization_content_hash": "other"},
        {"authorization_scope": "OTHER"},
        {"authorization_scope": None},
        {"authorization_epoch": 3},
        {"applicable_control_states": ("HOLD",)},
        {"applicable_control_states": ("UNKNOWN",)},
        {"controls_proven": False},
        {"policy_admissible": None},
        {"policy_admissible": False},
        {"session_relation_current": False},
        {"session_relation_current": None},
        {"dependency_eligible": False},
        {"dependency_eligible": None},
        {"target_state": "REVOKED"},
        {"valid_from": NOW + timedelta(microseconds=1)},
        {"valid_until": NOW},
        {"valid_until": None},
    )
    for change in mutations:
        decision = evaluate_executability(replace(basis, **change))
        assert not decision.is_executable, change
