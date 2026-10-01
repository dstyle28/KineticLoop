"""Typed ContextService and PlanningWorkflowService internal guarded owners."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.persistence.transactions import (
    EventWrite,
    GuardRequired,
    RepositoryTransaction,
    RestrictedSqlSession,
    TransactionStateError,
    _execute_guarded_progress,
)
from kineticloop.workflow.planning import digest
from kineticloop.workflow.planning_progress import (
    POLICY_BLOCKS,
    AdvanceAttempt,
    ProgressBasis,
    ProgressIdentity,
    RecordSnapshot,
)


def wire(value: Any) -> Any:
    if isinstance(value, (UUID, datetime, date)):
        return str(value)
    if isinstance(value, Mapping):
        return {key: wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [wire(item) for item in value]
    return value


def capture_context(
    connection: Connection[Any], basis: ProgressBasis, builder_id: UUID
) -> dict[str, Any]:
    """Read immutable inputs and compute context outside any coordination lock.

    Explicit TEST policy summaries are input-only instrumentation. They make no
    F/D/N or clinical completeness claim. Missing blocks deny, never truncate.
    """
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise TransactionStateError("context capture requires idle connection")
    with connection.transaction():
        row = connection.execute(
            "SELECT m.ref_s05_id,m.ref_s06_id,m.manifest_hash,m.captured_epoch,"
            "p.typed_payload,g.typed_payload,r.typed_payload,r.request_revision,"
            "b.content_hash,b.artifact_version,clock_timestamp() "
            "FROM kineticloop.decision_manifests m JOIN kineticloop.policy_bundles p "
            "ON p.subject_id=m.subject_id AND p.id=m.ref_s05_id "
            "JOIN kineticloop.program_versions g ON g.subject_id=m.subject_id AND g.id=m.ref_s06_id "
            "JOIN kineticloop.planning_request_revisions r ON r.subject_id=m.subject_id AND r.id=%s "
            "JOIN kineticloop.safety_artifacts b ON b.id=%s "
            "WHERE m.subject_id=%s AND m.id=%s AND r.ref_s27_id=%s",
            (basis.request_id, builder_id, basis.subject_id, basis.manifest_id, basis.intent_id),
        ).fetchone()
    if row is None or row[3] != basis.epoch or row[7] != basis.request_revision:
        raise GuardRequired("immutable capture basis missing/mismatched")
    summaries = row[4].get("planning_context")
    if not isinstance(summaries, dict) or set(summaries) != POLICY_BLOCKS:
        raise GuardRequired("all mandatory policy context blocks required")
    context = {
        "mandatory_context": True,
        "manifest_id": str(basis.manifest_id),
        "manifest_hash": row[2],
        "request_id": str(basis.request_id),
        "request_revision": basis.request_revision,
        "attempt_id": str(basis.attempt_id),
        "epoch": basis.epoch,
        "policy_id": str(row[0]),
        "program_id": str(row[1]),
        "blocks": {**summaries, "program": row[5], "constraints": row[6]["constraints"]},
        "trust_class": "NON_COMMAND_CONTEXT",
        "builder_id": str(builder_id),
        "builder_hash": row[8],
        "context_builder_version": row[9],
        "source_cutoff": row[10].isoformat(),
    }
    raw = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    budget = row[4].get("planning_context_byte_budget")
    if type(budget) is not int or not 0 < len(raw) <= budget <= 131072:
        raise GuardRequired("mandatory context cannot fit declared budget")
    accounting = {
        "method": "UTF8_BYTE_UPPER_BOUND_V1",
        "input_units": len(raw),
        "budget_units": budget,
        "truncated": False,
    }
    context["accounting"] = accounting
    return {
        "context": context,
        "context_hash": digest(context),
        "builder_hash": row[8],
        "source_cutoff": row[10],
        "accounting": accounting,
    }


class _ProgressService:
    def __init__(self, connection: Connection[Any], identity: ProgressIdentity) -> None:
        if type(identity) is not ProgressIdentity:
            raise GuardRequired("separately authenticated progress identity required")
        identity.__post_init__()
        self._connection, self._identity = connection, identity

    def _run(self, request: RecordSnapshot | AdvanceAttempt) -> Mapping[str, Any]:
        # Freeze nested client data before hashing/checking; requests confer no SQL capability.
        request = replace(
            request,
            **copy.deepcopy(
                {
                    "context": dict(request.context),
                    "accounting": dict(request.accounting),
                }
                if isinstance(request, RecordSnapshot)
                else {"sources": dict(request.sources)}
            ),
        )
        request.__post_init__()
        if (
            request.subject_id != self._identity.subject_id
            or request.expected_owner != self._identity.key
        ):
            raise GuardRequired("authenticated subject/worker mismatch")
        if self._connection.info.transaction_status != TransactionStatus.IDLE:
            raise TransactionStateError("progress requires idle owner connection")
        with self._connection.transaction():
            registration = self._connection.execute(
                "SELECT s.namespace,s.policy_id,s.environment_id,b.principal_name "
                "FROM kineticloop.subject_scopes s JOIN kineticloop.subject_principal_bindings b "
                "ON b.subject_id=s.subject_id AND b.namespace=s.namespace WHERE s.subject_id=%s",
                (request.subject_id,),
            ).fetchone()
        if registration != (
            "TEST",
            self._identity.policy_id,
            self._identity.environment_id,
            self._identity.principal,
        ):
            raise GuardRequired("authenticated TEST registration mismatch")
        payload_hash = digest(wire(asdict(request)))
        return _execute_guarded_progress(self._connection, self._identity, request, payload_hash)


class ContextService(_ProgressService):
    def record_snapshot(self, request: RecordSnapshot) -> Mapping[str, Any]:
        if type(request) is not RecordSnapshot:
            raise GuardRequired("typed RecordSnapshot required")
        return self._run(request)


class PlanningWorkflowService(_ProgressService):
    def advance_attempt(self, request: AdvanceAttempt) -> Mapping[str, Any]:
        if type(request) is not AdvanceAttempt:
            raise GuardRequired("typed AdvanceAttempt required")
        return self._run(request)


def _persist_progress(
    tx: RepositoryTransaction,
    identity: ProgressIdentity,
    request: RecordSnapshot | AdvanceAttempt,
    payload_hash: str,
) -> Mapping[str, Any]:
    """Module-owned callback; callers never supply code or write grants."""
    tx.lock_subject()
    tx.require_progress_ingress(identity)
    prior = tx.progress_historical_outcome(
        actor_scope=identity.key, client_key=request.key, request_hash=payload_hash
    )
    if prior is not None:
        return prior
    tx.lock_intents((request.intent_id,))
    tx.require_current_fence(
        request.intent_id,
        owner_id=identity.key,
        fence=request.fence,
        expected_request_revision=request.request_revision,
        expected_attempt_id=request.attempt_id,
    )
    output_id = uuid4()

    def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
        prepared = tx.prepared_planning_progress()
        if type(request) is RecordSnapshot:
            session.insert("S26", {**prepared, "typed_payload": Jsonb(prepared["typed_payload"])})
        else:
            session.update(
                "S29",
                {**prepared, "typed_payload": Jsonb(prepared["typed_payload"])},
                {"subject_id": request.subject_id, "id": request.attempt_id},
            )
        return {
            "snapshot_id": str(output_id)
            if type(request) is RecordSnapshot
            else str(prepared["snapshot_id"])
            if prepared.get("snapshot_id")
            else None,
            "attempt_id": str(request.attempt_id),
            "state": request.source_state
            if isinstance(request, RecordSnapshot)
            else request.target_state,
            "executable": False,
            "lock_trace": [(int(stage), name) for stage, name in tx.lock_trace],
        }

    outcome, replayed = tx.idempotent_outcome(
        receipt_id=uuid4(),
        actor_scope=identity.key,
        client_key=request.key,
        request_hash=payload_hash,
        mutation=mutation,
        aggregate_locks={"planning_attempts": (request.attempt_id,)},
        progress_request=request,
        progress_identity=identity,
        progress_output_id=output_id,
        event=EventWrite(
            event_id=uuid4(),
            aggregate_type="PLANNING_PROGRESS",
            aggregate_identity=digest([identity.key, type(request).__name__, request.key]),
            event_type=type(request).__name__,
            aggregate_revision=1,
            outbox_id=uuid4(),
            destination="planning",
        ),
    )
    return {**outcome, "replayed": True} if replayed else outcome
