"""Versioned planning normalization and frozen single-flight/lease decisions."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

NORMALIZATION_VERSION = "kl024-v1"
ACTIVE = frozenset({"ADMITTED", "PENDING", "RUNNING"})  # PENDING is legacy ADMITTED.
TERMINAL = frozenset(
    {
        "FOUND_VALID_PLAN",
        "PROVEN_CONSTRAINT_CONFLICT",
        "SEARCH_BUDGET_EXHAUSTED",
        "MODEL_REFUSAL",
        "MODEL_OUTPUT_INVALID",
        "DEPENDENCY_UNAVAILABLE",
        "STALE_RETRY_EXHAUSTED",
        "DEADLINE_EXCEEDED",
        "CANCELLED",
    }
)
ATTEMPT_TERMINAL = frozenset({"COMMITTED", "STALE", "FAILED", "CANCELLED", "LEASE_LOST"})


class PlanningDenied(ValueError):
    """No planning authority was admitted."""


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def normalize(constraints: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize structured constraints; never infer semantics from free text.

    Equipment is a set. Strings use NFC and trim outer whitespace; ordered
    collections retain order. Unsupported/ambiguous types fail closed.
    """

    if not isinstance(constraints, Mapping):
        raise PlanningDenied("structured constraint mapping required")

    def visit(value: Any, depth: int = 0) -> Any:
        if depth > 16:
            raise PlanningDenied("constraint nesting limit exceeded")
        if value is None or type(value) in {bool, int}:
            return value
        if isinstance(value, str):
            return unicodedata.normalize("NFC", value).strip()
        if isinstance(value, Mapping):
            result: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str) or not key.strip():
                    raise PlanningDenied("constraint keys must be nonempty strings")
                canonical = visit(key)
                if canonical in result:
                    raise PlanningDenied("normalization key collision")
                result[canonical] = visit(item, depth + 1)
            return result
        if isinstance(value, (tuple, list)):
            return [visit(item, depth + 1) for item in value]
        raise PlanningDenied("unsupported constraint value")

    result: dict[str, Any] = visit(constraints)
    if "equipment" in result:
        items = result["equipment"]
        if not isinstance(items, list) or any(not isinstance(x, str) or not x for x in items):
            raise PlanningDenied("equipment must be a list of nonempty names")
        result["equipment"] = sorted(set(items))
    if len(json.dumps(result, ensure_ascii=False).encode()) > 32768:
        raise PlanningDenied("constraint size limit exceeded")
    return result


def fingerprint(constraints: Mapping[str, Any]) -> str:
    return digest({"version": NORMALIZATION_VERSION, "constraints": normalize(constraints)})


def admission_decision(
    *,
    status: str | None,
    same_scope: bool,
    same_fingerprint: bool,
    same_basis: bool,
    explicit: bool,
    trigger: str,
    purpose: str,
    policy: Mapping[str, Any],
    other_active: int,
    now: datetime,
    deadline: datetime | None,
) -> Literal["JOIN", "REVISE", "ADMIT"]:
    if policy.get("version") != NORMALIZATION_VERSION:
        raise PlanningDenied("unsupported planning admission policy")
    if purpose not in policy.get("purposes", []) or trigger not in policy.get("triggers", []):
        raise PlanningDenied("purpose or trigger is not policy-admitted")
    if status in ACTIVE and same_scope:
        if deadline is None or now >= deadline:
            raise PlanningDenied("active intent deadline expired")
        return "JOIN" if same_fingerprint and same_basis else "REVISE"
    if status is not None and status not in TERMINAL:
        raise PlanningDenied("unknown intent state")
    if status in TERMINAL and not explicit:
        raise PlanningDenied("terminal intent requires an explicit new request")
    if not explicit and trigger not in policy.get("auto_root_triggers", []):
        raise PlanningDenied("automatic root admission denied")
    if other_active >= policy.get("max_active_per_day", 0):
        raise PlanningDenied("same-day concurrency policy denied")
    if policy.get("capacity_available") is not True:
        raise PlanningDenied("system/model capacity unavailable")
    return "ADMIT"


def require_live(
    *,
    status: str,
    owner: str | None,
    fence: int,
    request: int,
    attempt: str,
    expected_owner: str,
    expected_fence: int,
    expected_request: int,
    expected_attempt: str,
    attempt_status: str,
    now: datetime,
    expiry: datetime | None,
    deadline: datetime,
) -> None:
    if (
        status != "RUNNING"
        or owner != expected_owner
        or fence != expected_fence
        or request != expected_request
        or attempt != expected_attempt
        or attempt_status in ATTEMPT_TERMINAL
        or expiry is None
        or now >= expiry
        or now >= deadline
    ):
        raise PlanningDenied("worker lost current planning authority")


def renewal_expiry(now: datetime, expiry: datetime, deadline: datetime, seconds: int) -> datetime:
    from datetime import timedelta

    if type(seconds) is not int or seconds <= 0 or now >= expiry or now >= deadline:
        raise PlanningDenied("renewal requires a live bounded lease")
    target = min(now + timedelta(seconds=seconds), deadline)
    if target <= expiry:
        raise PlanningDenied("renewal must extend the lease")
    return target
