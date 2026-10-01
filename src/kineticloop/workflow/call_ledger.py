"""Versioned, finite call accounting; no planning or execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal
from uuid import UUID

ACCOUNTING_VERSION = "kl025-v1"
BOUND_VIOLATION_KEY = "call_bound_violation"
DIMENSIONS = frozenset({"calls", "tokens", "tools", "input_tokens", "output_tokens", "cost_micros"})
OCCUPIED = frozenset({"RESERVED", "DISPATCH_INTENT", "OUTCOME_UNKNOWN"})
ReceiptSource = Literal["PROVIDER_RECEIPT", "RECONCILIATION"]


class LedgerDenied(ValueError):
    """The requested accounting change cannot be established safely."""


def _name(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 512


@dataclass(frozen=True)
class AccountingIdentity:
    provider: str
    model: str
    config_fingerprint: str
    price_version: str
    strict_money: bool = False
    version: str = ACCOUNTING_VERSION

    def __post_init__(self) -> None:
        if (
            self.version != ACCOUNTING_VERSION
            or any(not _name(v) for v in (
                self.provider, self.model, self.config_fingerprint, self.price_version
            ))
            or type(self.strict_money) is not bool
            or self.strict_money
        ):
            raise LedgerDenied("versioned count/token accounting required; no strict money claim")


def validate_usage(
    usage: Any, dimensions: set[str] | frozenset[str] | None = None
) -> dict[str, int]:
    """Integer counters have exact units and reject floats, bools, NaN and infinity."""
    if (
        not isinstance(usage, Mapping)
        or not usage
        or any(not isinstance(k, str) or k not in DIMENSIONS for k in usage)
        or any(type(v) is not int or v < 0 for v in usage.values())
        or (dimensions is not None and set(usage) != dimensions)
    ):
        raise LedgerDenied("unknown, missing, negative or unbounded budget dimension")
    return dict(usage)


@dataclass(frozen=True)
class ReliableReceipt:
    """Evidence shape only; the settlement ingress must verify its provenance."""

    reservation_id: UUID
    accounting: AccountingIdentity
    actual: Mapping[str, int]
    source: ReceiptSource
    receipt_id: str
    provider_request_id: str
    provenance: str

    def __post_init__(self) -> None:
        if (
            type(self.reservation_id) is not UUID
            or type(self.accounting) is not AccountingIdentity
            or self.source not in {"PROVIDER_RECEIPT", "RECONCILIATION"}
            or any(not _name(v) for v in (
                self.receipt_id, self.provider_request_id, self.provenance
            ))
        ):
            raise LedgerDenied("receipt must bind exact reservation/accounting/source identities")
        self.accounting.__post_init__()
        object.__setattr__(self, "actual", MappingProxyType(validate_usage(self.actual)))


def _root(root: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    if not isinstance(root, Mapping):
        raise LedgerDenied("root budget mapping required")
    limits = validate_usage(root.get("limits"))
    if "calls" not in limits:
        raise LedgerDenied("physical call count must be bounded")
    dimensions = set(limits)
    return (
        limits,
        validate_usage(root.get("reserved"), dimensions),
        validate_usage(root.get("settled"), dimensions),
    )


def _bounds(bounds: Mapping[str, int], dimensions: set[str]) -> dict[str, int]:
    result = validate_usage(bounds, dimensions)
    if result["calls"] != 1:
        raise LedgerDenied("each physical request needs exactly one covered call slot")
    return result


def reserve_budget(
    root: Mapping[str, Any], bounds: Mapping[str, int], accounting: AccountingIdentity
) -> dict[str, Any]:
    if type(accounting) is not AccountingIdentity:
        raise LedgerDenied("versioned accounting identity required")
    # Revalidate at ingress even if a caller has circumvented frozen dataclass assignment.
    accounting.__post_init__()
    limits, reserved, settled = _root(root)
    upper = _bounds(bounds, set(limits))
    if root.get(BOUND_VIOLATION_KEY, False) is not False:
        raise LedgerDenied("root budget exhausted after reservation bound violation")
    if any(settled[k] + reserved[k] + upper[k] > limits[k] for k in limits):
        raise LedgerDenied("root budget exhausted")
    return {**root, "limits": limits, "settled": settled,
            "reserved": {k: reserved[k] + upper[k] for k in limits}}


def release_budget(root: Mapping[str, Any], bounds: Mapping[str, int]) -> dict[str, Any]:
    """Only the command owner's locked RESERVED winner may use this delta."""
    limits, reserved, settled = _root(root)
    upper = _bounds(bounds, set(limits))
    if any(reserved[k] < upper[k] for k in limits):
        raise LedgerDenied("release exceeds outstanding root occupation")
    return {**root, "limits": limits, "settled": settled,
            "reserved": {k: reserved[k] - upper[k] for k in limits}}


def settle_budget(
    root: Mapping[str, Any], bounds: Mapping[str, int], actual: Mapping[str, int]
) -> dict[str, Any]:
    """Record actuals and irreversibly close new reservations after a bound violation."""
    limits, _, settled = _root(root)
    verified = _bounds(actual, set(limits))
    upper = _bounds(bounds, set(limits))
    released = release_budget(root, bounds)
    if any(verified[k] > upper[k] for k in limits):
        released[BOUND_VIOLATION_KEY] = True
    return {**released, "settled": {k: settled[k] + verified[k] for k in limits}}


def next_state(source: str, command: str, expected_transition: str | None = None) -> str:
    """The merged owner API calls OUTCOME_UNKNOWN's expected transition UNKNOWN."""
    transitions = {
        ("RESERVED", "PermitDispatch"): "DISPATCH_INTENT",
        ("RESERVED", "CancelUndispatched"): "CANCELLED_BEFORE_DISPATCH",
        ("DISPATCH_INTENT", "MarkUnknown"): "OUTCOME_UNKNOWN",
        ("DISPATCH_INTENT", "SettleCall"): "SETTLED",
        ("OUTCOME_UNKNOWN", "SettleCall"): "SETTLED",
    }
    if command in {"MarkUnknown", "SettleCall"}:
        expected_source = {"DISPATCH_INTENT": "DISPATCH_INTENT", "UNKNOWN": "OUTCOME_UNKNOWN"}
        if expected_source.get(expected_transition or "") != source:
            raise LedgerDenied("stale or unsupported expected transition")
    target = transitions.get((source, command))
    if target is None:
        raise LedgerDenied("reservation transition denied")
    return target
