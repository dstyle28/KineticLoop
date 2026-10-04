"""Bounded isolated TEST worker orchestration and non-authoritative scan facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.pq import TransactionStatus

from kineticloop.persistence.planning import (
    AcquireLease,
    PlanningIdentity,
    RenewLease,
)
from kineticloop.persistence.planning import PlanningWorkflowService as LeaseService
from kineticloop.persistence.planning_progress import PlanningWorkflowService as ProgressService
from kineticloop.persistence.transactions import GuardRequired, TransactionStateError
from kineticloop.workflow.planning import ACTIVE, ATTEMPT_ACTIVE, PlanningDenied
from kineticloop.workflow.planning_progress import AdvanceAttempt, ProgressIdentity


@dataclass(frozen=True, slots=True, kw_only=True)
class ReapIntent:
    """Exact scan expectations. No chosen terminal, time, budget, SQL or callback."""

    subject_id: UUID
    key: str
    intent_id: UUID
    request_id: UUID
    request_revision: int
    attempt_id: UUID
    expected_owner: str | None
    fence: int
    deadline: datetime
    lease_expires_at: datetime | None
    intent_status: str
    attempt_status: str

    def __post_init__(self) -> None:
        if any(type(v) is not UUID for v in (
            self.subject_id, self.intent_id, self.request_id, self.attempt_id
        )) or type(self.request_revision) is not int or self.request_revision <= 0:
            raise PlanningDenied("exact reaper identities required")
        if type(self.fence) is not int or self.fence < 0:
            raise PlanningDenied("exact nonnegative fence required")
        if type(self.key) is not str or not self.key.strip() or len(self.key) > 512:
            raise PlanningDenied("bounded operation key required")
        if self.intent_status not in ACTIVE or self.attempt_status not in ATTEMPT_ACTIVE:
            raise PlanningDenied("active reaper chain required")
        if type(self.deadline) is not datetime or self.deadline.tzinfo is None:
            raise PlanningDenied("recorded aware deadline required")
        if self.expected_owner is None:
            if (self.intent_status not in {"ADMITTED", "PENDING"} or self.fence != 0
                or self.attempt_status != "CREATED" or self.lease_expires_at is not None):
                raise PlanningDenied("null owner is exclusive to the unacquired basis")
        elif (type(self.expected_owner) is not str or not self.expected_owner.startswith("test:")
              or self.fence <= 0 or type(self.lease_expires_at) is not datetime
              or self.lease_expires_at.tzinfo is None):
            raise PlanningDenied("exact TEST leased basis required")


def terminal_targets(
    request: ReapIntent, now: datetime, *, cancel_expired_lease: bool
) -> tuple[str, str]:
    """Pure boundary oracle. Persistence supplies post-lock time and policy."""
    request.__post_init__()
    if now >= request.deadline:
        return "DEADLINE_EXCEEDED", "LEASE_LOST"
    if (request.expected_owner is not None and request.lease_expires_at is not None
        and now >= request.lease_expires_at and cancel_expired_lease):
        return "CANCELLED", "CANCELLED"
    raise PlanningDenied("live/stale candidate or absent recovery cancellation policy")


@dataclass(frozen=True, slots=True)
class WorkerSchedule:
    lease_seconds: int = 5
    heartbeat_seconds: float = 1.0
    max_heartbeats: int = 3

    def __post_init__(self) -> None:
        if (type(self.lease_seconds) is not int or not 1 <= self.lease_seconds <= 60
            or type(self.heartbeat_seconds) not in {int, float}
            or not 0 < self.heartbeat_seconds < self.lease_seconds / 2
            or type(self.max_heartbeats) is not int or not 0 <= self.max_heartbeats <= 100):
            raise PlanningDenied("bounded heartbeat/stop schedule required")


class TestWorker:
    """Acquire/heartbeat/stop only; a replay never establishes work authority."""

    __test__ = False

    def __init__(self, connection: Connection[Any], identity: ProgressIdentity,
                 schedule: WorkerSchedule = WorkerSchedule()) -> None:
        if type(identity) is not ProgressIdentity or type(schedule) is not WorkerSchedule:
            raise GuardRequired("typed TEST worker identity/schedule required")
        identity.__post_init__()
        schedule.__post_init__()
        self.connection, self.identity, self.schedule = connection, identity, schedule

    def run(self, candidate: ReapIntent, *, manifest_id: UUID, epoch: int,
            stop: Any, ready: Any) -> dict[str, Any]:
        from kineticloop.persistence.worker_reaper import _registration

        if type(candidate) is not ReapIntent:
            raise GuardRequired("typed worker candidate required")
        candidate.__post_init__()
        if candidate.subject_id != self.identity.subject_id or type(manifest_id) is not UUID:
            raise GuardRequired("worker target/identity mismatch")
        _registration(self.connection, self.identity)
        lease = LeaseService(self.connection, PlanningIdentity(self.identity.actor,
                                                               self.identity.subject_id))
        operation = str(uuid4())
        result = lease.acquire_lease(AcquireLease(
            candidate.subject_id, "worker-acquire:" + operation, candidate.intent_id,
            candidate.expected_owner, candidate.fence, candidate.request_revision,
            candidate.attempt_id, self.schedule.lease_seconds,
        ))
        if result.get("replayed"):
            raise GuardRequired("historical lease cannot start a worker")
        if candidate.attempt_status == "CREATED":
            ProgressService(self.connection, self.identity).advance_attempt(AdvanceAttempt(
                subject_id=candidate.subject_id, key="worker-leased:" + operation,
                intent_id=candidate.intent_id, request_id=candidate.request_id,
                request_revision=candidate.request_revision, attempt_id=candidate.attempt_id,
                expected_owner=self.identity.key, fence=result["fence"], manifest_id=manifest_id,
                epoch=epoch, source_state="CREATED", target_state="LEASED", sources={},
            ))
        ready.set()
        beats = 0
        for n in range(self.schedule.max_heartbeats):
            if self.connection.info.transaction_status != TransactionStatus.IDLE:
                raise TransactionStateError("worker wait requires committed idle connection")
            if stop.wait(self.schedule.heartbeat_seconds):
                break
            result = lease.renew_lease(RenewLease(
                candidate.subject_id, f"worker-renew:{operation}:{n}", candidate.intent_id,
                result["fence"], candidate.request_revision, candidate.attempt_id,
                self.schedule.lease_seconds,
            ))
            if result.get("replayed"):
                raise GuardRequired("historical heartbeat cannot sustain a worker")
            beats += 1
        return {"fence": result["fence"], "heartbeats": beats, "executable": False}
