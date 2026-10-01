"""Typed bounded call accounting over the sole T5/T8 transaction owners."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.identity import ActorRole
from kineticloop.persistence.planning import PlanningIdentity
from kineticloop.persistence.transactions import (
    DispatchPermit,
    EventWrite,
    GuardRequired,
    ReplayNotFound,
    RepositoryTransaction,
    RestrictedSqlSession,
    TransactionStateError,
    execute_command,
    replay_outcome,
)
from kineticloop.workflow.call_ledger import AccountingIdentity, LedgerDenied, ReliableReceipt
from kineticloop.workflow.planning import digest


@dataclass(frozen=True)
class ReserveCall:
    subject_id: UUID
    key: str
    intent_id: UUID
    attempt_id: UUID
    request_revision: int
    fence: int
    operation_slot: str
    accounting: AccountingIdentity
    bounds: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bounds", MappingProxyType(dict(self.bounds)))


@dataclass(frozen=True)
class PermitDispatch:
    subject_id: UUID
    key: str
    intent_id: UUID
    reservation_id: UUID
    attempt_id: UUID
    request_revision: int
    fence: int


@dataclass(frozen=True)
class CancelUndispatched:
    subject_id: UUID
    key: str
    intent_id: UUID
    reservation_id: UUID


@dataclass(frozen=True)
class MarkUnknown:
    subject_id: UUID
    key: str
    intent_id: UUID
    reservation_id: UUID
    expected_transition: str = "DISPATCH_INTENT"
    expected_revision: int = 1


@dataclass(frozen=True)
class SettleCall:
    subject_id: UUID
    key: str
    intent_id: UUID
    reservation_id: UUID
    receipt: ReliableReceipt
    expected_transition: str = "UNKNOWN"
    expected_revision: int = 2


@dataclass(frozen=True)
class ReservationView:
    """Immutable accounting observation; no current business-write authority."""

    reservation_id: UUID
    intent_id: UUID
    attempt_id: UUID
    status: str
    revision: int
    accounting: AccountingIdentity
    bounds: Mapping[str, int]
    actual: Mapping[str, int] | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bounds", MappingProxyType(dict(self.bounds)))
        if self.actual is not None:
            object.__setattr__(self, "actual", MappingProxyType(dict(self.actual)))


def _wire(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _wire(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: _wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(v) for v in value]
    return value


class CallLedgerService:
    def __init__(
        self,
        connection: Connection[Any],
        identity: PlanningIdentity,
        *,
        receipt_verifier: Callable[[ReliableReceipt], bool] | None = None,
    ) -> None:
        if type(identity) is not PlanningIdentity:
            raise GuardRequired("trusted planning identity required")
        self.connection, self.identity = connection, identity
        self.receipt_verifier = receipt_verifier

    def _guard(self, subject_id: UUID, key: str) -> None:
        if (
            subject_id != self.identity.subject_id
            or not isinstance(key, str)
            or not key.strip()
            or len(key) > 512
        ):
            raise GuardRequired("subject/key binding invalid")
        if self.connection.info.transaction_status is not TransactionStatus.IDLE:
            raise TransactionStateError("call ledger requires idle connection")
        with self.connection.transaction():
            row = self.connection.execute(
                "SELECT namespace FROM kineticloop.subject_scopes WHERE subject_id=%s",
                (subject_id,),
            ).fetchone()
        expected = "TEST" if self.identity.actor.role == ActorRole.TEST else "PRODUCTION"
        if row is None or row[0] != expected:
            raise GuardRequired("call ledger subject namespace mismatch")

    def _validate(self, command: Any) -> None:
        self._guard(command.subject_id, command.key)
        for name in ("intent_id", "reservation_id", "attempt_id"):
            if hasattr(command, name) and type(getattr(command, name)) is not UUID:
                raise LedgerDenied("exact ledger UUID chain required")
        for name in ("fence", "request_revision", "expected_revision"):
            if hasattr(command, name):
                value = getattr(command, name)
                if type(value) is not int or value < (1 if name == "request_revision" else 0):
                    raise LedgerDenied("invalid ledger revision/fence")

    def _replay(self, command: Any, kind: str, request_hash: str) -> Mapping[str, Any] | None:
        try:
            outcome = replay_outcome(
                self.connection,
                kind,
                command.subject_id,
                actor_scope="subject",
                client_key=command.key,
                request_hash=request_hash,
            )
            return {**outcome, "replayed": True}
        except ReplayNotFound:
            return None

    @staticmethod
    def _event(kind: str, key: str) -> EventWrite:
        return EventWrite(
            event_id=uuid4(),
            aggregate_type="CALL_COMMAND",
            aggregate_identity=digest([kind, key]),
            event_type=kind,
            aggregate_revision=1,
            outbox_id=uuid4(),
            destination="call-ledger",
        )

    def read(self, reservation_id: UUID) -> ReservationView:
        self._guard(self.identity.subject_id, "ledger-read")
        if type(reservation_id) is not UUID:
            raise LedgerDenied("exact reservation identity required")
        with self.connection.transaction():
            row = self.connection.execute(
                "SELECT ref_s27_id,ref_s29_id,status,settlement_revision,typed_payload "
                "FROM kineticloop.call_reservations WHERE subject_id=%s AND id=%s",
                (self.identity.subject_id, reservation_id),
            ).fetchone()
        if row is None:
            raise LedgerDenied("reservation not found")
        payload = row[4]
        return ReservationView(
            reservation_id,
            row[0],
            row[1],
            row[2],
            row[3],
            AccountingIdentity(**payload["accounting"]),
            payload["bounds"],
            payload["actual"],
        )

    def reserve(self, command: ReserveCall) -> Mapping[str, Any]:
        if type(command) is not ReserveCall:
            raise LedgerDenied("typed reservation command required")
        self._validate(command)
        if (
            not isinstance(command.operation_slot, str)
            or not command.operation_slot.strip()
            or len(command.operation_slot) > 512
        ):
            raise LedgerDenied("bounded operation slot required")
        request_hash = digest(_wire(command))
        prior = self._replay(command, "ReserveCall", request_hash)
        if prior is not None:
            return prior

        def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
            tx.lock_subject()
            prior = tx.ledger_historical_outcome(
                actor_scope="subject", client_key=command.key, request_hash=request_hash
            )
            if prior is not None:
                return prior
            tx.lock_intents((command.intent_id,))
            tx.require_current_fence(
                command.intent_id,
                owner_id=self.identity.key,
                fence=command.fence,
                expected_request_revision=command.request_revision,
                expected_attempt_id=command.attempt_id,
            )
            reservation_id, event = uuid4(), self._event("ReserveCall", command.key)
            basis = tx.prepare_ledger_reservation(
                intent_id=command.intent_id,
                reservation_id=reservation_id,
                attempt_id=command.attempt_id,
                operation_slot=command.operation_slot,
                accounting=command.accounting,
                bounds=command.bounds,
            )

            def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                session.update(
                    "S27",
                    {"typed_payload": Jsonb(basis["root_payload"])},
                    {"subject_id": command.subject_id, "id": command.intent_id},
                )
                session.insert(
                    "S31",
                    {
                        "id": reservation_id,
                        "subject_id": command.subject_id,
                        "ref_s27_id": command.intent_id,
                        "ref_s29_id": command.attempt_id,
                        "operation_slot": command.operation_slot,
                        "config_fingerprint": command.accounting.config_fingerprint,
                        "dispatch_owner": self.identity.key,
                        "dispatch_fence": command.fence,
                        "status": "RESERVED",
                        "settlement_revision": 0,
                        "typed_payload": Jsonb(basis["payload"]),
                    },
                )
                self._ledger_event(session, command.subject_id, command.key, event, basis)
                return {
                    "reservation_id": str(reservation_id),
                    "status": "RESERVED",
                    "replayed": False,
                }

            outcome, replayed = tx.idempotent_outcome(
                receipt_id=uuid4(),
                actor_scope="subject",
                client_key=command.key,
                request_hash=request_hash,
                mutation=mutation,
                event=event,
            )
            return {**outcome, "replayed": replayed}

        return execute_command(self.connection, "ReserveCall", command.subject_id, operation)

    def permit(self, command: PermitDispatch) -> DispatchPermit:
        if type(command) is not PermitDispatch:
            raise LedgerDenied("typed permit command required")
        self._validate(command)
        request_hash = digest(_wire(command))
        prior = self._replay(command, "PermitDispatch", request_hash)
        if prior is not None:
            return DispatchPermit(UUID(prior["reservation_id"]), sendable=False, replayed=True)

        def operation(tx: RepositoryTransaction) -> DispatchPermit:
            tx.lock_subject()
            prior = tx.ledger_historical_outcome(
                actor_scope="subject", client_key=command.key, request_hash=request_hash
            )
            if prior is not None:
                return DispatchPermit(UUID(prior["reservation_id"]), sendable=False, replayed=True)
            tx.lock_intents((command.intent_id,))
            tx.lock_reservations((command.reservation_id,))
            tx.require_current_fence(
                command.intent_id,
                owner_id=self.identity.key,
                fence=command.fence,
                expected_request_revision=command.request_revision,
                expected_attempt_id=command.attempt_id,
            )
            return tx.permit_dispatch(
                command.reservation_id,
                permit_key=command.key,
                request_hash=request_hash,
                receipt_id=uuid4(),
                event=self._event("PermitDispatch", command.key),
                fence=command.fence,
            )

        # execute_command owns commit; a permission cannot escape a failed commit.
        return execute_command(self.connection, "PermitDispatch", command.subject_id, operation)

    def cancel(self, command: CancelUndispatched) -> Mapping[str, Any]:
        return self._change(command, "CancelUndispatched")

    def mark_unknown(self, command: MarkUnknown) -> Mapping[str, Any]:
        return self._change(command, "MarkUnknown")

    def settle(self, command: SettleCall) -> Mapping[str, Any]:
        # Evidence verification may involve external work; always outside coordination.
        if type(command) is not SettleCall or type(command.receipt) is not ReliableReceipt:
            raise LedgerDenied("typed reliable receipt required")
        self._validate(command)
        if self.receipt_verifier is None or self.receipt_verifier(command.receipt) is not True:
            raise LedgerDenied("untrusted settlement receipt")
        return self._change(command, "SettleCall")

    @staticmethod
    def _ledger_event(
        session: RestrictedSqlSession,
        subject: UUID,
        key: str,
        event: EventWrite,
        basis: Mapping[str, Any],
    ) -> None:
        session.insert(
            "S32",
            {
                "id": event.event_id,
                "subject_id": subject,
                "ref_s31_id": basis["reservation_id"],
                "event_type": basis["target_status"],
                "transition_revision": basis["next_revision"],
                "receipt_identity": key,
                "occurred_at": basis["occurred_at"],
                "typed_payload": Jsonb(
                    {
                        "accounting_version": "kl025-v1",
                        "accounting": basis["payload"],
                        "reserved_delta": basis["reserved_delta"],
                        "settled_delta": basis["settled_delta"],
                    }
                ),
            },
        )

    def _change(
        self, command: CancelUndispatched | MarkUnknown | SettleCall, kind: str
    ) -> Mapping[str, Any]:
        expected_type = {
            "CancelUndispatched": CancelUndispatched,
            "MarkUnknown": MarkUnknown,
            "SettleCall": SettleCall,
        }[kind]
        if type(command) is not expected_type:
            raise LedgerDenied("typed ledger change required")
        self._validate(command)
        request_hash = digest(_wire(command))
        prior = self._replay(command, kind, request_hash)
        if prior is not None:
            return prior

        def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
            tx.lock_subject()
            prior = tx.ledger_historical_outcome(
                actor_scope="subject", client_key=command.key, request_hash=request_hash
            )
            if prior is not None:
                return prior
            tx.lock_intents((command.intent_id,))
            tx.lock_reservations((command.reservation_id,))
            snapshot = tx.ledger_snapshot(command.intent_id, command.reservation_id)
            expected = (
                "RESERVED"
                if isinstance(command, CancelUndispatched)
                else command.expected_transition
            )
            revision = (
                snapshot["revision"]
                if isinstance(command, CancelUndispatched)
                else command.expected_revision
            )
            basis = tx.prepare_ledger_change(
                intent_id=command.intent_id,
                reservation_id=command.reservation_id,
                expected_transition=expected,
                expected_revision=revision,
                receipt=command.receipt if isinstance(command, SettleCall) else None,
            )
            event = self._event(kind, command.key)

            def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                session.update(
                    "S27",
                    {"typed_payload": Jsonb(basis["root_payload"])},
                    {"subject_id": command.subject_id, "id": command.intent_id},
                )
                session.update(
                    "S31",
                    {
                        "status": basis["target_status"],
                        "settlement_revision": basis["next_revision"],
                        "typed_payload": Jsonb(basis["payload"]),
                    },
                    {"subject_id": command.subject_id, "id": command.reservation_id},
                )
                self._ledger_event(session, command.subject_id, command.key, event, basis)
                return {
                    "reservation_id": str(command.reservation_id),
                    "status": basis["target_status"],
                    "replayed": False,
                }

            outcome, replayed = tx.idempotent_outcome(
                receipt_id=uuid4(),
                actor_scope="subject",
                client_key=command.key,
                request_hash=request_hash,
                mutation=mutation,
                event=event,
                expected_transition=expected,
            )
            return {**outcome, "replayed": replayed}

        return execute_command(self.connection, kind, command.subject_id, operation)
