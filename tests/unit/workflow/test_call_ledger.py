from collections.abc import Callable, Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from psycopg.pq import TransactionStatus

from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.planning import PlanningIdentity
from kineticloop.persistence.transactions import (
    DispatchNotPermitted,
    DispatchPermit,
    IdempotencyConflict,
    ReplayNotFound,
)
from kineticloop.workflow.call_ledger import (
    ACCOUNTING_VERSION,
    OCCUPIED,
    AccountingIdentity,
    LedgerDenied,
    ReliableReceipt,
    next_state,
    release_budget,
    reserve_budget,
    settle_budget,
    validate_usage,
)

ACCOUNTING = AccountingIdentity("fake-provider", "fake-model", "config-v1", "price-v1")
BOUNDS = {"calls": 1, "tokens": 20, "tools": 1, "input_tokens": 8,
          "output_tokens": 12, "cost_micros": 30}


def root_budget() -> dict[str, Any]:
    return {
        "limits": {k: v * 3 for k, v in BOUNDS.items()},
        "reserved": dict(BOUNDS),
        "settled": dict(BOUNDS),
        "admission_policy_id": "policy-v1",
        "version": "kl024-v1",
        "unrelated": {"deadline": "original", "request": 2},
    }


def test_root_budget_and_charge_bounds() -> None:
    root = root_budget()
    updated = reserve_budget(root, BOUNDS, ACCOUNTING)
    assert updated["reserved"] == {k: v * 2 for k, v in BOUNDS.items()}
    assert updated["settled"] == root["settled"]
    assert updated["version"] == "kl024-v1" and ACCOUNTING.version == ACCOUNTING_VERSION
    assert updated["unrelated"] == root["unrelated"]
    assert root == root_budget()  # pure calculation, not an unguarded root mutation
    for dimension in BOUNDS:
        saturated = root_budget()
        saturated["limits"][dimension] -= 1
        with pytest.raises(LedgerDenied, match="exhausted"):
            reserve_budget(saturated, BOUNDS, ACCOUNTING)
    with pytest.raises(LedgerDenied, match="exhausted"):
        reserve_budget(updated, BOUNDS, ACCOUNTING)

    for bad in (-1, 0.5, float("nan"), float("inf"), True, None):
        values: Any = {**BOUNDS, "tokens": bad}
        with pytest.raises(LedgerDenied):
            reserve_budget(root, values, ACCOUNTING)
    for values in ({**BOUNDS, "unknown": 1}, {k: v for k, v in BOUNDS.items() if k != "tokens"},
                   {**BOUNDS, "calls": 0}, {**BOUNDS, "calls": 2}):
        with pytest.raises(LedgerDenied):
            reserve_budget(root, values, ACCOUNTING)
    for change in ({"version": "unknown"}, {"price_version": ""}, {"strict_money": True},
                   {"config_fingerprint": ""}, {"provider": ""}, {"model": ""}):
        with pytest.raises(LedgerDenied):
            replace(ACCOUNTING, **change)
    with pytest.raises(LedgerDenied):
        validate_usage({"cost": 1})
    counts_only = {"limits": {"calls": 2, "tokens": 50},
                   "reserved": {"calls": 0, "tokens": 0},
                   "settled": {"calls": 0, "tokens": 0}}
    assert ACCOUNTING.strict_money is False
    assert reserve_budget(counts_only, {"calls": 1, "tokens": 50}, ACCOUNTING)["reserved"] == {
        "calls": 1, "tokens": 50
    }

    # Unknown and pending remain bounds, not invented provider-confirmed usage.
    assert {"RESERVED", "DISPATCH_INTENT", "OUTCOME_UNKNOWN"} <= OCCUPIED
    assert root["settled"] != updated["reserved"]
    actual = {**BOUNDS, "tokens": 999, "cost_micros": 9999}
    settled = settle_budget(root, BOUNDS, actual)
    assert settled["reserved"] == {k: 0 for k in BOUNDS}
    assert settled["settled"]["tokens"] == 1019
    assert settled["settled"]["cost_micros"] == 10029
    with pytest.raises(LedgerDenied, match="exhausted"):
        reserve_budget(settled, BOUNDS, ACCOUNTING)
    assert release_budget(root, BOUNDS)["reserved"] == {k: 0 for k in BOUNDS}
    with pytest.raises(LedgerDenied, match="occupation"):
        release_budget(release_budget(root, BOUNDS), BOUNDS)

    receipt = ReliableReceipt(uuid4(), ACCOUNTING, BOUNDS, "PROVIDER_RECEIPT",
                              "receipt-1", "request-1", "verified-adapter-v1")
    assert receipt.accounting == ACCOUNTING
    with pytest.raises(FrozenInstanceError):
        setattr(receipt, "provenance", "caller-mutated")
    with pytest.raises(TypeError):
        cast(MutableMapping[str, int], receipt.actual)["tokens"] = 0
    mutable_actual = dict(BOUNDS)
    captured = replace(receipt, actual=mutable_actual)
    mutable_actual["tokens"] = 0
    assert captured.actual["tokens"] == BOUNDS["tokens"]
    assert replace(receipt, source="RECONCILIATION").source == "RECONCILIATION"
    receipt_changes: tuple[dict[str, Any], ...] = (
        {"receipt_id": ""}, {"provider_request_id": ""}, {"provenance": ""},
        {"source": "UNTRUSTED"}, {"reservation_id": "wrong"},
    )
    for change in receipt_changes:
        with pytest.raises(LedgerDenied):
            replace(receipt, **change)


def test_state_machine_and_non_sendable_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    assert next_state("RESERVED", "CancelUndispatched") == "CANCELLED_BEFORE_DISPATCH"
    assert next_state("RESERVED", "PermitDispatch") == "DISPATCH_INTENT"
    assert next_state("DISPATCH_INTENT", "MarkUnknown", "DISPATCH_INTENT") == "OUTCOME_UNKNOWN"
    assert next_state("DISPATCH_INTENT", "SettleCall", "DISPATCH_INTENT") == "SETTLED"
    assert next_state("OUTCOME_UNKNOWN", "SettleCall", "UNKNOWN") == "SETTLED"
    for source in ("DISPATCH_INTENT", "OUTCOME_UNKNOWN", "SETTLED", "CANCELLED_BEFORE_DISPATCH"):
        for command in ("CancelUndispatched", "PermitDispatch", "ReserveCall"):
            with pytest.raises(LedgerDenied):
                next_state(source, command)
    for source, command, expectation in (
        ("OUTCOME_UNKNOWN", "MarkUnknown", "UNKNOWN"),
        ("OUTCOME_UNKNOWN", "SettleCall", "OUTCOME_UNKNOWN"),
        ("OUTCOME_UNKNOWN", "SettleCall", "DISPATCH_INTENT"),
        ("DISPATCH_INTENT", "SettleCall", "UNKNOWN"),
        ("DISPATCH_INTENT", "MarkUnknown", None),
        ("RESERVED", "SettleCall", "DISPATCH_INTENT"),
        ("SETTLED", "SettleCall", "UNKNOWN"),
    ):
        with pytest.raises(LedgerDenied):
            next_state(source, command, expectation)
    runtime, service, command = _permit_runtime(monkeypatch)
    first = service.permit(command)
    replay = service.permit(command)
    assert first == DispatchPermit(runtime.reservation_id, True, False)
    assert replay == DispatchPermit(runtime.reservation_id, False, True)
    assert not hasattr(first, "executable")  # dispatch grants no business/T6 authority
    with pytest.raises(IdempotencyConflict):
        service.permit(replace(command, fence=command.fence + 1))
    with pytest.raises(DispatchNotPermitted):
        service.permit(replace(command, key="another-permit-key"))
    assert runtime.transitions == 1 and runtime.root["reserved"] == BOUNDS


class _PermitConnection:
    def __init__(self) -> None:
        self.info = SimpleNamespace(transaction_status=TransactionStatus.IDLE)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        assert self.info.transaction_status is TransactionStatus.IDLE
        self.info.transaction_status = TransactionStatus.INTRANS
        try:
            yield
        finally:
            self.info.transaction_status = TransactionStatus.IDLE

    def execute(self, query: str, parameters: Any) -> Any:
        assert "subject_scopes" in query and parameters
        return SimpleNamespace(fetchone=lambda: ("TEST",))


class _PermitRuntime:
    """Instrument the real service's owner callback without SQL or a transport."""

    def __init__(self) -> None:
        self.connection = _PermitConnection()
        self.reservation_id = uuid4()
        self.intent_id = uuid4()
        self.attempt_id = uuid4()
        self.subject_id = uuid4()
        self.state = "RESERVED"
        self.root = {"limits": {k: v * 3 for k, v in BOUNDS.items()},
                     "reserved": dict(BOUNDS), "settled": {k: 0 for k in BOUNDS}}
        self.receipts: dict[str, tuple[str, dict[str, Any]]] = {}
        self.events: list[str] = []
        self.transitions = 0
        self.sent: list[UUID] = []
        self.failure: str | None = None
        self.staged: tuple[str, str] | None = None

    def replay(self, connection: Any, kind: str, subject: UUID, **values: Any) -> Mapping[str, Any]:
        assert connection is self.connection and kind == "PermitDispatch"
        assert subject == self.subject_id
        prior = self.receipts.get(values["client_key"])
        if prior is None:
            raise ReplayNotFound("no committed permit")
        if prior[0] != values["request_hash"]:
            raise IdempotencyConflict("changed permit payload")
        return {**prior[1], "sendable": False, "replayed": True}

    def execute(
        self, connection: Any, kind: str, subject: UUID, operation: Callable[[Any], Any]
    ) -> Any:
        assert connection is self.connection and kind == "PermitDispatch"
        assert subject == self.subject_id
        self.events.append("begin")
        self.staged = None
        try:
            with self.connection.transaction():
                result = operation(_PermitOwner(self))
                assert self.staged is not None
                if self.failure == "PRECOMMIT":
                    self.events.append("rollback")
                    raise RuntimeError("precommit rollback")
                key, request_hash = self.staged
                self.state = "DISPATCH_INTENT"
                self.receipts[key] = (request_hash, {"reservation_id": str(self.reservation_id)})
                self.transitions += 1
                self.events.append("commit")
        finally:
            self.events.append("release")
        if self.failure == "LOST_ACK":
            raise RuntimeError("lost permit ACK")
        return result

    def send(self, permit: DispatchPermit, *, sdk_max_retries: int) -> None:
        if not permit.sendable:
            return
        assert sdk_max_retries == 0
        assert self.connection.info.transaction_status is TransactionStatus.IDLE
        assert self.events[-2:] == ["commit", "release"]
        assert self.state == "DISPATCH_INTENT"
        assert permit.reservation_id == self.reservation_id and self.transitions == 1
        assert permit.reservation_id not in self.sent
        self.events.append("send")
        self.sent.append(permit.reservation_id)


class _PermitOwner:
    def __init__(self, runtime: _PermitRuntime) -> None:
        self.runtime = runtime

    def lock_subject(self) -> None:
        self.runtime.events.append("S01")

    def ledger_historical_outcome(self, **values: Any) -> Mapping[str, Any] | None:
        try:
            return self.runtime.replay(
                self.runtime.connection, "PermitDispatch", self.runtime.subject_id, **values
            )
        except ReplayNotFound:
            return None

    def lock_intents(self, ids: Any) -> None:
        assert list(ids) == [self.runtime.intent_id]
        self.runtime.events.append("S27")

    def lock_reservations(self, ids: Any) -> None:
        assert list(ids) == [self.runtime.reservation_id]
        self.runtime.events.append("S31")

    def require_current_fence(self, *args: Any, **values: Any) -> None:
        assert self.runtime.connection.info.transaction_status is TransactionStatus.INTRANS

    def permit_dispatch(self, reservation_id: UUID, **values: Any) -> DispatchPermit:
        assert reservation_id == self.runtime.reservation_id
        if self.runtime.state != "RESERVED":
            raise DispatchNotPermitted("possible send already committed")
        self.runtime.staged = (values["permit_key"], values["request_hash"])
        self.runtime.events.append("stage_DISPATCH_INTENT")
        return DispatchPermit(reservation_id, True, False)


def _permit_runtime(monkeypatch: pytest.MonkeyPatch) -> tuple[_PermitRuntime, Any, Any]:
    import kineticloop.persistence.call_ledger as ledger

    runtime = _PermitRuntime()
    monkeypatch.setattr(ledger, "execute_command", runtime.execute)
    monkeypatch.setattr(ledger, "replay_outcome", runtime.replay)
    identity = PlanningIdentity(RoleIdentity(str(runtime.subject_id), ActorRole.TEST),
                                runtime.subject_id)
    service = ledger.CallLedgerService(cast(Any, runtime.connection), identity)
    command = ledger.PermitDispatch(
        runtime.subject_id, "permit-key", runtime.intent_id, runtime.reservation_id,
        runtime.attempt_id, 1, 1,
    )
    return runtime, service, command


def test_dispatch_occurs_once_after_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    for failure in (None, "PRECOMMIT", "LOST_ACK", "BEFORE_SEND", "AFTER_SEND"):
        runtime, service, command = _permit_runtime(monkeypatch)
        runtime.failure = failure
        if failure in {"PRECOMMIT", "LOST_ACK"}:
            with pytest.raises(RuntimeError):
                service.permit(command)
            assert runtime.sent == []
            if failure == "PRECOMMIT":
                assert runtime.state == "RESERVED" and runtime.receipts == {}
                assert runtime.transitions == 0
        else:
            first = service.permit(command)
            assert runtime.events.index("stage_DISPATCH_INTENT") < runtime.events.index("commit")
            assert runtime.events.index("commit") < runtime.events.index("release")
            if failure != "BEFORE_SEND":
                runtime.send(first, sdk_max_retries=0)

        # Recovery after every boundary uses the durable service replay, not the old permit.
        runtime.failure = None
        recovered = service.permit(command)
        if failure == "PRECOMMIT":
            assert recovered.sendable
        else:
            assert recovered.replayed and not recovered.sendable
        runtime.send(recovered, sdk_max_retries=0)
        expected_calls = 0 if failure in {"LOST_ACK", "BEFORE_SEND"} else 1
        assert len(runtime.sent) == expected_calls
        assert runtime.transitions == 1
        assert runtime.state == "DISPATCH_INTENT"
        assert runtime.root["reserved"] == BOUNDS
        assert runtime.root["settled"] == {k: 0 for k in BOUNDS}
        assert runtime.connection.info.transaction_status is TransactionStatus.IDLE

    # A future explicit physical retry receives its own reservation and occupation.
    covered_requests: list[UUID] = []
    for _ in range(2):
        runtime, service, command = _permit_runtime(monkeypatch)
        runtime.send(service.permit(command), sdk_max_retries=0)
        covered_requests.extend(runtime.sent)
        assert runtime.root["reserved"]["calls"] == 1
    assert len(set(covered_requests)) == 2
