"""Typed planning commands over the sole frozen repository transaction owner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.transactions import (
    EventWrite,
    FenceLost,
    GuardRequired,
    ReplayNotFound,
    RepositoryTransaction,
    RestrictedSqlSession,
    TransactionStateError,
    execute_command,
    replay_outcome,
)
from kineticloop.workflow.planning import (
    ACTIVE,
    ATTEMPT_ACTIVE,
    PlanningDenied,
    digest,
    normalize,
    renewal_expiry,
)


@dataclass(frozen=True)
class PlanningIdentity:
    actor: RoleIdentity
    subject_id: UUID

    def __post_init__(self) -> None:
        if type(self.actor) is not RoleIdentity or self.actor.role not in {
            ActorRole.SUBJECT,
            ActorRole.TEST,
        }:
            raise GuardRequired("trusted planning subject required")

    @property
    def key(self) -> str:
        return f"{self.actor.role}:{self.actor.identity_id}"


@dataclass(frozen=True)
class AdmitOrReviseIntent:
    subject_id: UUID
    key: str
    local_date: date
    purpose: str
    calendar_policy: str
    constraints: Mapping[str, Any]
    explicit: bool = True
    trigger: str = "USER_REQUEST"


@dataclass(frozen=True)
class AcquireLease:
    subject_id: UUID
    key: str
    intent_id: UUID
    expected_owner: str | None
    expected_fence: int
    request_revision: int
    attempt_id: UUID
    seconds: int


@dataclass(frozen=True)
class RenewLease:
    subject_id: UUID
    key: str
    intent_id: UUID
    fence: int
    request_revision: int
    attempt_id: UUID
    seconds: int


def _wire(value: Any) -> Any:
    if isinstance(value, (UUID, date)):
        return str(value)
    if isinstance(value, Mapping):
        return {k: _wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(v) for v in value]
    return value


class PlanningWorkflowService:
    def __init__(self, connection: Connection[Any], identity: PlanningIdentity) -> None:
        if type(identity) is not PlanningIdentity:
            raise GuardRequired("trusted planning identity required")
        self.connection = connection
        self.identity = identity

    def _guard(self, subject_id: UUID, key: str) -> None:
        if subject_id != self.identity.subject_id or not isinstance(key, str) or not key.strip():
            raise GuardRequired("subject/key binding invalid")
        if self.connection.info.transaction_status is not TransactionStatus.IDLE:
            raise TransactionStateError("planning requires idle connection")
        with self.connection.transaction():
            scope = self.connection.execute(
                "SELECT namespace FROM kineticloop.subject_scopes WHERE subject_id=%s",
                (subject_id,),
            ).fetchone()
        expected = "TEST" if self.identity.actor.role == ActorRole.TEST else "PRODUCTION"
        if scope is None or scope[0] != expected:
            raise GuardRequired("planning subject namespace mismatch")

    def _replay(self, command: Any, kind: str, request_hash: str) -> Mapping[str, Any] | None:
        try:
            # Historical identities are observations, never a current worker permit.
            return replay_outcome(
                self.connection,
                kind,
                command.subject_id,
                actor_scope=self.identity.key,
                client_key=command.key,
                request_hash=request_hash,
            )
        except ReplayNotFound:
            return None

    def admit_or_revise(self, command: AdmitOrReviseIntent) -> Mapping[str, Any]:
        self._guard(command.subject_id, command.key)
        if (
            type(command.explicit) is not bool
            or type(command.local_date) is not date
            or not command.purpose.strip()
            or not command.calendar_policy.strip()
        ):
            raise PlanningDenied("invalid planning partition/scope")
        normalized = normalize(command.constraints)
        payload = _wire(asdict(command))
        payload["constraints"] = normalized
        request_hash = digest(payload)
        prior = self._replay(command, "AdmitOrReviseIntent", request_hash)
        if prior is not None:
            return prior

        def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
            tx.lock_subject()
            historical = tx.planning_historical_outcome(
                actor_scope=self.identity.key,
                client_key=command.key,
                request_hash=request_hash,
            )
            if historical is not None:
                return historical
            basis = tx.prepare_planning_admission(
                local_date=command.local_date,
                purpose=command.purpose,
                calendar_policy=command.calendar_policy,
                constraints=normalized,
                explicit=command.explicit,
                trigger=command.trigger,
                new_intent_id=uuid4(),
            )
            mode, intent = basis["mode"], basis["intent_id"]
            request_id = basis["request_id"] if mode == "JOIN" else uuid4()
            attempt_id = basis["old_attempt_id"] if mode == "JOIN" else uuid4()
            receipt_id = uuid4()
            result = {
                "mode": mode,
                "intent_id": str(intent),
                "request_id": str(request_id),
                "attempt_id": str(attempt_id),
                "request_revision": basis["request_revision"],
            }

            def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                if mode == "JOIN":
                    return result
                if mode == "ADMIT":
                    session.insert(
                        "S27",
                        {
                            "id": intent,
                            "subject_id": command.subject_id,
                            "root_request_identity": f"{self.identity.key}:{command.key}",
                            "purpose": command.purpose,
                            "local_date": command.local_date,
                            "status": "ADMITTED",
                            "fence_token": 0,
                            "stale_restart_count": 0,
                            "deadline": basis["deadline"],
                            "typed_payload": Jsonb(basis["root_payload"]),
                        },
                    )
                    for quota in basis["quotas"]:
                        session.update(
                            "S30",
                            {"admitted_count": quota["count"] + 1},
                            {"subject_id": command.subject_id, "id": quota["id"]},
                        )
                else:
                    session.update(
                        "S29",
                        {"status": "STALE"},
                        {"subject_id": command.subject_id, "id": basis["old_attempt_id"]},
                    )
                session.insert(
                    "S28",
                    {
                        "id": request_id,
                        "subject_id": command.subject_id,
                        "ref_s27_id": intent,
                        "ref_s02_id": receipt_id,
                        "request_revision": basis["request_revision"],
                        "constraint_fingerprint": basis["fingerprint"],
                        "normalization_version": basis["normalization_version"],
                        "typed_payload": Jsonb(basis["request_payload"]),
                    },
                )
                session.insert(
                    "S29",
                    {
                        "id": attempt_id,
                        "subject_id": command.subject_id,
                        "ref_s27_id": intent,
                        "ref_s28_id": request_id,
                        "ref_s24_id": basis["manifest_id"],
                        "captured_epoch": basis["epoch"],
                        "fence_token": basis["fence"],
                        "attempt_no": basis["attempt_no"],
                        "status": "CREATED",
                    },
                )
                session.update(
                    "S27",
                    {"current_request_revision_id": request_id, "current_attempt_id": attempt_id},
                    {"subject_id": command.subject_id, "id": intent},
                )
                return result

            outcome, _ = tx.idempotent_outcome(
                receipt_id=receipt_id,
                actor_scope=self.identity.key,
                client_key=command.key,
                request_hash=request_hash,
                mutation=mutation,
                aggregate_locks={"planning_attempts": (basis["old_attempt_id"],)}
                if mode == "REVISE"
                else {},
                event=EventWrite(
                    event_id=uuid4(),
                    aggregate_type="PLANNING_COMMAND",
                    aggregate_identity=command.key,
                    event_type=mode,
                    aggregate_revision=1,
                    outbox_id=uuid4(),
                    destination="planning",
                ),
            )
            return outcome

        return execute_command(
            self.connection, "AdmitOrReviseIntent", command.subject_id, operation
        )

    def acquire_lease(self, command: AcquireLease) -> Mapping[str, Any]:
        return self._lease(command, "AcquireLease")

    def renew_lease(self, command: RenewLease) -> Mapping[str, Any]:
        return self._lease(command, "RenewLease")

    def _lease(self, command: AcquireLease | RenewLease, kind: str) -> Mapping[str, Any]:
        self._guard(command.subject_id, command.key)
        if type(command.seconds) is not int or command.seconds <= 0:
            raise PlanningDenied("positive lease duration required")
        expected_fence = (
            command.expected_fence if isinstance(command, AcquireLease) else command.fence
        )
        if (
            type(expected_fence) is not int
            or expected_fence < 0
            or type(command.request_revision) is not int
            or command.request_revision <= 0
            or not isinstance(command.intent_id, UUID)
            or not isinstance(command.attempt_id, UUID)
        ):
            raise PlanningDenied("invalid lease CAS identity")
        request_hash = digest(_wire(asdict(command)))
        prior = self._replay(command, kind, request_hash)
        if prior is not None:
            return prior

        def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
            tx.lock_subject()
            historical = tx.planning_historical_outcome(
                actor_scope=self.identity.key,
                client_key=command.key,
                request_hash=request_hash,
            )
            if historical is not None:
                return historical
            tx.lock_intents((command.intent_id,))
            state = tx.planning_lease_snapshot(command.intent_id)
            if (
                state["status"] not in ACTIVE
                or state["attempt_status"] not in ATTEMPT_ACTIVE
                or state["attempt"] != command.attempt_id
                or state["request"] != command.request_revision
                or state["now"] >= state["deadline"]
            ):
                raise FenceLost("obsolete or terminal planning chain")
            if isinstance(command, AcquireLease):
                target = min(state["now"] + timedelta(seconds=command.seconds), state["deadline"])
                fence = command.expected_fence + 1
                tx.require_lease_acquisition_basis(
                    command.intent_id,
                    expected_owner_id=command.expected_owner,
                    expected_fence=command.expected_fence,
                    new_owner_id=self.identity.key,
                    new_fence=fence,
                    new_lease_expires_at=target,
                    expected_request_revision=command.request_revision,
                )
                values = {
                    "status": "RUNNING",
                    "lease_owner": self.identity.key,
                    "fence_token": fence,
                    "lease_expires_at": target,
                }
            else:
                tx.require_current_fence(
                    command.intent_id,
                    owner_id=self.identity.key,
                    fence=command.fence,
                    expected_request_revision=command.request_revision,
                    expected_attempt_id=command.attempt_id,
                )
                target = renewal_expiry(
                    state["now"], state["expiry"], state["deadline"], command.seconds
                )
                fence = command.fence
                values = {"lease_expires_at": target}
            result = {
                "intent_id": str(command.intent_id),
                "attempt_id": str(command.attempt_id),
                "request_revision": command.request_revision,
                "owner": self.identity.key,
                "fence": fence,
                "lease_expires_at": target.isoformat(),
            }

            def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                session.update(
                    "S27", values, {"subject_id": command.subject_id, "id": command.intent_id}
                )
                return result

            outcome, _ = tx.idempotent_outcome(
                receipt_id=uuid4(),
                actor_scope=self.identity.key,
                client_key=command.key,
                request_hash=request_hash,
                mutation=mutation,
                event=EventWrite(
                    event_id=uuid4(),
                    aggregate_type="PLANNING_COMMAND",
                    aggregate_identity=command.key,
                    event_type=kind,
                    aggregate_revision=1,
                    outbox_id=uuid4(),
                    destination="planning",
                ),
            )
            return outcome

        return execute_command(self.connection, kind, command.subject_id, operation)
