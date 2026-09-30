from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from kineticloop.workflow.planning import (
    ACTIVE,
    TERMINAL,
    PlanningDenied,
    admission_decision,
    fingerprint,
    normalize,
    renewal_expiry,
    require_live,
)

POLICY = {
    "version": "kl024-v1",
    "purposes": ["TRAINING", "NUTRITION"],
    "triggers": ["USER_REQUEST", "INPUT_EVENT"],
    "auto_root_triggers": [],
    "max_active_per_day": 1,
    "capacity_available": True,
}
NOW = datetime(2026, 9, 30, tzinfo=UTC)


def test_normalized_single_flight_and_revision_decisions() -> None:
    a = {"equipment": [" band ", "mat", "band"], "minutes": 30, "note": "e\u0301"}
    b = {"note": "é", "minutes": 30, "equipment": ["mat", "band"]}
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) != fingerprint({**b, "minutes": 31})
    assert normalize({"ordered": [2, 1]}) != normalize({"ordered": [1, 2]})
    for bad in ({"x": 1.0}, {"x": float("nan")}, {"a": 1, " a ": 2}):
        with pytest.raises(PlanningDenied):
            normalize(bad)
    basis: dict[str, Any] = dict(
        status="ADMITTED",
        same_scope=True,
        same_fingerprint=True,
        same_basis=True,
        explicit=True,
        trigger="USER_REQUEST",
        purpose="TRAINING",
        policy=POLICY,
        other_active=1,
        now=NOW,
        deadline=NOW + timedelta(hours=1),
    )
    assert admission_decision(**basis) == "JOIN"
    assert admission_decision(**{**basis, "same_fingerprint": False}) == "REVISE"
    assert admission_decision(**{**basis, "same_basis": False}) == "REVISE"
    new = {**basis, "status": None, "same_scope": False, "other_active": 0}
    assert admission_decision(**new) == "ADMIT"
    assert admission_decision(**{**new, "status": "CANCELLED"}) == "ADMIT"
    for change in (
        {"purpose": "OTHER"},
        {"other_active": 1},
        {"status": "CANCELLED", "explicit": False},
        {"explicit": False, "trigger": "INPUT_EVENT"},
        {"policy": {**POLICY, "capacity_available": False}},
        {"status": "FAILED"},
    ):
        with pytest.raises(PlanningDenied):
            admission_decision(**{**new, **dict(change)})
    assert (
        admission_decision(
            **{
                **new,
                "explicit": False,
                "trigger": "INPUT_EVENT",
                "policy": {**POLICY, "auto_root_triggers": ["INPUT_EVENT"]},
            }
        )
        == "ADMIT"
    )
    assert "ADMITTED" in ACTIVE and "FAILED" not in TERMINAL


def test_fence_deadline_and_terminal_guards() -> None:
    live: dict[str, Any] = dict(
        status="RUNNING",
        owner="a",
        fence=2,
        request=3,
        attempt="b",
        expected_owner="a",
        expected_fence=2,
        expected_request=3,
        expected_attempt="b",
        attempt_status="CREATED",
        now=NOW,
        expiry=NOW + timedelta(seconds=10),
        deadline=NOW + timedelta(seconds=20),
    )
    require_live(**live)
    changes: tuple[dict[str, Any], ...] = (
        {"owner": "old"},
        {"fence": 1},
        {"request": 2},
        {"attempt": "old"},
        {"expiry": NOW},
        {"deadline": NOW},
        {"attempt_status": "STALE"},
        *({"status": terminal} for terminal in TERMINAL),
    )
    for change in changes:
        with pytest.raises(PlanningDenied):
            require_live(**{**live, **dict(change)})
    assert renewal_expiry(NOW, live["expiry"], live["deadline"], 100) == live["deadline"]
    for expiry, deadline, seconds in (
        (NOW, live["deadline"], 30),
        (live["expiry"], NOW, 30),
        (live["expiry"], live["deadline"], 10),
        (live["expiry"], live["deadline"], 0),
    ):
        with pytest.raises(PlanningDenied):
            renewal_expiry(NOW, expiry, deadline, seconds)
