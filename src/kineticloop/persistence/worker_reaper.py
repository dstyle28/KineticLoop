"""Authenticated isolated TEST ReapIntent and lock-free bounded discovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.pq import TransactionStatus

from kineticloop.persistence.call_ledger import CallLedgerService, MarkUnknown
from kineticloop.persistence.planning import PlanningIdentity
from kineticloop.persistence.planning_progress import wire
from kineticloop.persistence.transactions import (
    EventWrite,
    FenceLost,
    GuardRequired,
    RepositoryTransaction,
    RestrictedSqlSession,
    TransactionStateError,
    _execute_guarded_reaper,
)
from kineticloop.workflow.planning import PlanningDenied, digest
from kineticloop.workflow.planning_progress import ProgressIdentity
from kineticloop.workflow.worker_reaper import ReapIntent


def _registration(connection: Connection[Any], identity: ProgressIdentity) -> None:
    if type(identity) is not ProgressIdentity:
        raise GuardRequired("separately authenticated TEST reaper identity required")
    identity.__post_init__()
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise TransactionStateError("reaper requires idle service connection")
    with connection.transaction():
        row = connection.execute(
            "SELECT s.namespace,s.policy_id,s.environment_id,b.principal_name,"
            "current_user,session_user FROM kineticloop.subject_scopes s "
            "JOIN kineticloop.subject_principal_bindings b ON b.subject_id=s.subject_id "
            "AND b.namespace=s.namespace WHERE s.subject_id=%s", (identity.subject_id,),
        ).fetchone()
    if (row is None or row[:4] != (
        "TEST", identity.policy_id, identity.environment_id, identity.principal
    ) or row[4] != row[5] or row[5] == identity.principal):
        raise GuardRequired("registered TEST client and separate internal service required")


class PlanningWorkflowService:
    def __init__(self, connection: Connection[Any], identity: ProgressIdentity) -> None:
        if type(identity) is not ProgressIdentity:
            raise GuardRequired("typed TEST reaper identity required")
        identity.__post_init__()
        self._connection, self._identity = connection, identity

    def scan(self, limit: int = 32) -> tuple[ReapIntent, ...]:
        if type(limit) is not int or not 1 <= limit <= 128:
            raise GuardRequired("bounded candidate scan required")
        _registration(self._connection, self._identity)
        with self._connection.transaction():
            rows = self._connection.execute(
                "SELECT i.id,r.id,r.request_revision,a.id,i.lease_owner,i.fence_token,"
                "i.deadline,i.lease_expires_at,i.status,a.status "
                "FROM kineticloop.planning_intents i "
                "JOIN kineticloop.planning_request_revisions r ON r.subject_id=i.subject_id "
                "AND r.id=i.current_request_revision_id AND r.ref_s27_id=i.id "
                "JOIN kineticloop.planning_attempts a ON a.subject_id=i.subject_id "
                "AND a.id=i.current_attempt_id AND a.ref_s27_id=i.id AND a.ref_s28_id=r.id "
                "WHERE i.subject_id=%s AND i.status IN ('ADMITTED','PENDING','RUNNING') "
                "AND a.status IN ('CREATED','LEASED','BUILDING_CONTEXT','FITNESS',"
                "'DEMAND_FEATURES','NUTRITION','VALIDATING','COMMIT_READY') "
                "AND (i.deadline<=clock_timestamp() OR i.lease_expires_at<=clock_timestamp()) "
                "ORDER BY i.id LIMIT %s", (self._identity.subject_id, limit),
            ).fetchall()
        # No row lock or read transaction survives discovery.
        return tuple(ReapIntent(
            subject_id=self._identity.subject_id, key="scan:" + digest(wire(row)),
            **dict(zip(("intent_id", "request_id", "request_revision", "attempt_id",
                        "expected_owner", "fence", "deadline", "lease_expires_at",
                        "intent_status", "attempt_status"), row, strict=True)),
        ) for row in rows)

    def reap_intent(self, request: ReapIntent) -> Mapping[str, Any]:
        if type(request) is not ReapIntent:
            raise GuardRequired("typed ReapIntent required")
        request = replace(request)
        request.__post_init__()
        if request.subject_id != self._identity.subject_id:
            raise GuardRequired("reaper subject mismatch")
        _registration(self._connection, self._identity)
        return _execute_guarded_reaper(self._connection, self._identity, request)

    def mark_outstanding_unknown(self, limit: int = 32) -> int:
        """Independent accounting owner transactions; failure safely retains occupation."""
        if type(limit) is not int or not 1 <= limit <= 128:
            raise GuardRequired("bounded accounting scan required")
        _registration(self._connection, self._identity)
        with self._connection.transaction():
            rows = self._connection.execute(
                "SELECT r.ref_s27_id,r.id,r.settlement_revision FROM kineticloop.call_reservations r "
                "JOIN kineticloop.planning_intents i ON i.subject_id=r.subject_id AND i.id=r.ref_s27_id "
                "WHERE r.subject_id=%s AND r.status='DISPATCH_INTENT' "
                "AND (i.status NOT IN ('ADMITTED','PENDING','RUNNING') "
                "OR i.deadline<=clock_timestamp() OR i.lease_expires_at<=clock_timestamp() "
                "OR r.dispatch_fence IS DISTINCT FROM i.fence_token OR r.ref_s29_id<>i.current_attempt_id) "
                "ORDER BY r.id LIMIT %s", (self._identity.subject_id, limit),
            ).fetchall()
        ledger = CallLedgerService(self._connection, PlanningIdentity(
            self._identity.actor, self._identity.subject_id
        ))
        completed = 0
        for intent, reservation, revision in rows:
            try:
                ledger.mark_unknown(MarkUnknown(
                    self._identity.subject_id, f"reaper-unknown:{reservation}:{revision}",
                    intent, reservation, expected_revision=revision,
                ))
            except GuardRequired as error:
                if str(error) not in {"ledger expected revision is stale", "reservation transition denied"}:
                    raise
                # The owner rolled back. Confirm stale discovery through its read
                # interface; registration/integrity/infrastructure errors still fail.
                current = ledger.read(reservation)
                if (current.intent_id != intent or
                    (current.status == "DISPATCH_INTENT" and current.revision == revision)):
                    raise
                continue
            completed += 1
        return completed

    def run(self, *, stop: Any, ready: Any, max_scans: int = 100,
            poll_seconds: float = 0.1) -> Mapping[str, Any]:
        """Independent bounded control process; scheduler supplies its own channel."""
        if (type(max_scans) is not int or not 1 <= max_scans <= 1000
            or type(poll_seconds) not in {int, float} or not 0 < poll_seconds <= 1):
            raise GuardRequired("bounded independent reaper schedule required")
        _registration(self._connection, self._identity)
        ready.set()
        reaped = unknown = 0
        for _ in range(max_scans):
            for candidate in self.scan():
                try:
                    result = self.reap_intent(candidate)
                    reaped += not result.get("replayed", False)
                except (FenceLost, PlanningDenied):
                    # Discovery confers no authority. A later scan supplies fresh facts.
                    continue
            unknown += self.mark_outstanding_unknown()
            if self._connection.info.transaction_status != TransactionStatus.IDLE:
                raise TransactionStateError("reaper wait requires committed idle connection")
            if stop.wait(poll_seconds):
                break
        return {"reaped": reaped, "unknown": unknown, "executable": False}


def _persist_reaper(tx: RepositoryTransaction, identity: ProgressIdentity,
                    request: ReapIntent) -> Mapping[str, Any]:
    tx.lock_subject()
    tx._require_reaper_ingress(identity)
    request_hash = digest(wire(asdict(request)))
    prior = tx._reaper_historical_outcome(identity.key, request.key, request_hash)
    if prior is not None:
        return prior
    tx.lock_intents((request.intent_id,))
    tx.require_reaper_basis(
        request.intent_id, owner_id=request.expected_owner, fence=request.fence,
        expected_deadline=request.deadline, expected_request_revision=request.request_revision,
        expected_attempt_id=request.attempt_id,
    )
    tx._lock_reaper_reservations(request.intent_id)

    def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
        prepared = tx._prepared_reaper()
        for logical, target in (("S27", request.intent_id), ("S29", request.attempt_id)):
            session.update(logical, prepared[logical], {"subject_id": request.subject_id,
                                                       "id": target})
        return {"intent_id": str(request.intent_id), "attempt_id": str(request.attempt_id),
                "intent_status": prepared["S27"]["status"],
                "attempt_status": prepared["S29"]["status"], "executable": False,
                "guard_accepted_at": prepared["S29"]["completed_at"].isoformat(),
                "lock_trace": [[int(stage), name] for stage, name in tx.lock_trace]}

    outcome, replayed = tx.idempotent_outcome(
        receipt_id=uuid4(), actor_scope=identity.key, client_key=request.key,
        request_hash=request_hash, mutation=mutation,
        aggregate_locks={"planning_attempts": (request.attempt_id,)},
        reaper_request=request,
        event=EventWrite(event_id=uuid4(), aggregate_type="PLANNING_REAPER",
                         aggregate_identity=digest([identity.key, request.key]),
                         event_type="ReapIntent", aggregate_revision=1,
                         outbox_id=uuid4(), destination="planning"),
    )
    return {**outcome, "replayed": True, "executable": False} if replayed else outcome
