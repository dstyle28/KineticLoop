"""Fail-closed repository transaction interfaces for frozen T1--T8 boundaries.

The module deliberately owns no business decisions.  It supplies the small set of
mechanical primitives every command repository needs: one top-level transaction,
the frozen lock order, registry/subject guards, exact artifact and fence checks,
durable idempotent outcomes, atomic event/outbox writes, and isolated outbox claims.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Any, TypeVar
from uuid import UUID

from psycopg import Connection, Cursor, sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.persistence.schema_topology import LOGICAL_RELATIONS

_T = TypeVar("_T")

_LOGICAL_TABLES = {row.logical_id: row.table_name for row in LOGICAL_RELATIONS}


class RepositoryTransactionError(RuntimeError):
    """Base class for stable repository transaction failures."""


class TransactionStateError(RepositoryTransactionError):
    """A command owner was invoked without ownership of an idle connection."""


class LockOrderViolation(RepositoryTransactionError):
    """A caller attempted to acquire an earlier lock after a later lock."""


class GuardRequired(RepositoryTransactionError):
    """A protected operation is missing a required coordination guard."""


class ArtifactIdentityRequired(RepositoryTransactionError):
    """An exact registered immutable artifact identity was not proved."""


class FenceLost(RepositoryTransactionError):
    """The expected workflow lease owner/fence no longer has commit authority."""


class IdempotencyConflict(RepositoryTransactionError):
    """A durable command key was reused with a different request hash."""


class DispatchNotPermitted(RepositoryTransactionError):
    """The reservation did not win the one sendable transition."""


class StatementRejected(RepositoryTransactionError):
    """A callback attempted a lock or table outside its repository capability."""


class LockStage(IntEnum):
    REGISTRY = 10
    SUBJECT = 20
    QUOTA = 30
    INTENT = 40
    RESERVATION = 50
    DAILY_HEAD = 60
    EXECUTION = 70
    RECEIPT = 80
    AGGREGATE = 90


class Boundary(StrEnum):
    T1 = "T1"
    T2_IN = "T2-IN"
    T2_SEAL = "T2-SEAL"
    T2_GLOBAL = "T2-GLOBAL"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T6 = "T6"
    T7 = "T7"
    T8 = "T8"
    PREPARATION = "PREPARATION"
    BUILD = "BUILD"
    EXTERNAL = "OUTSIDE-T1-T8"


@dataclass(frozen=True, slots=True)
class OwnerSpec:
    owner: str
    boundary: Boundary
    mutation_surfaces: tuple[str, ...]
    registry_required: bool = False
    subject_guard_required: bool = True


# One and only one mutation owner for every public command surface.  Preparation
# writers remain explicit so they cannot be relabelled as part of T3/T5/T6.
TRANSACTION_OWNER_MATRIX: Mapping[str, OwnerSpec] = MappingProxyType(
    {
        "ReceiveEvidence": OwnerSpec("EvidenceService", Boundary.T1, ("S09", "S02", "S03", "S04"), subject_guard_required=False),
        "RecordCandidate": OwnerSpec("ExtractionService", Boundary.PREPARATION, ("S10",), subject_guard_required=False),
        "DecideAssociation": OwnerSpec("EvidenceAssociationService", Boundary.T2_IN, ("S12", "S01", "S02", "S03", "S04")),
        "DecideAdmission": OwnerSpec("AdmissionService", Boundary.T2_IN, ("S13", "S01", "S02", "S03", "S04")),
        "AcceptFactRevision": OwnerSpec("CanonicalFactService", Boundary.T2_IN, ("S14", "S01", "S02", "S03", "S04")),
        "ApplyControl": OwnerSpec("ControlService", Boundary.T2_IN, ("S17", "S18", "S01", "S02", "S03", "S04")),
        "ClearControl": OwnerSpec("ControlService", Boundary.T2_IN, ("S17", "S18", "S01", "S02", "S03", "S04")),
        "ApproveChange": OwnerSpec("ProgramReviewService", Boundary.T2_IN, ("S08", "S01", "S02", "S03", "S04")),
        "ActivateApprovedProgram": OwnerSpec("ProgramService", Boundary.T2_IN, ("S06", "S01", "S02", "S03", "S04")),
        "RecordActualExecution": OwnerSpec("CanonicalFactService", Boundary.T2_IN, ("S14", "S01", "S02", "S03", "S04")),
        "CompleteReportedWorkout": OwnerSpec("ExecutionService", Boundary.T2_IN, ("S44", "S14", "S01", "S02", "S03", "S04")),
        "BeginBuild": OwnerSpec("CanonicalViewService", Boundary.BUILD, ("S15",), subject_guard_required=False),
        "WriteCandidate": OwnerSpec("CanonicalViewService", Boundary.BUILD, ("S15", "S16"), subject_guard_required=False),
        "CompleteFactset": OwnerSpec("CanonicalViewService", Boundary.BUILD, ("S15",), subject_guard_required=False),
        "SealFactset": OwnerSpec("CanonicalViewService", Boundary.T2_SEAL, ("S01", "S15", "S02", "S03", "S04")),
        "RegisterArtifact": OwnerSpec("SafetyRegistry", Boundary.EXTERNAL, ("S49",), subject_guard_required=False),
        "RevokeArtifact": OwnerSpec("SafetyRegistry", Boundary.T2_GLOBAL, ("S50", "S51"), subject_guard_required=False),
        "RecordProjection": OwnerSpec("ProjectionService", Boundary.PREPARATION, ("S21", "S22"), subject_guard_required=False),
        "BuildManifest": OwnerSpec("DecisionPublicationService", Boundary.PREPARATION, ("S23",), subject_guard_required=False),
        "PublishManifest": OwnerSpec("DecisionPublicationService", Boundary.T3, ("S51", "S01", "S23", "S24", "S25", "S02", "S03", "S04"), registry_required=True),
        "AdmitOrReviseIntent": OwnerSpec("PlanningWorkflowService", Boundary.T4, ("S01", "S30", "S27", "S28", "S29", "S02", "S03", "S04")),
        "CancelIntent": OwnerSpec("PlanningWorkflowService", Boundary.T8, ("S01", "S27", "S31", "S02", "S03", "S04")),
        "AcquireLease": OwnerSpec("PlanningWorkflowService", Boundary.T5, ("S01", "S27", "S29", "S02", "S03", "S04")),
        "RenewLease": OwnerSpec("PlanningWorkflowService", Boundary.T5, ("S01", "S27", "S29", "S02", "S03", "S04")),
        "ReserveCall": OwnerSpec("CallLedgerService", Boundary.T5, ("S01", "S27", "S31", "S32", "S02", "S03", "S04")),
        "PermitDispatch": OwnerSpec("CallLedgerService", Boundary.T5, ("S01", "S27", "S31", "S32", "S02", "S03", "S04")),
        "RecordToolResult": OwnerSpec("ContextToolGateway", Boundary.PREPARATION, ("S33",), subject_guard_required=False),
        "RecordProposal": OwnerSpec("ProposalService", Boundary.PREPARATION, ("S34",), subject_guard_required=False),
        "RecordDemandFeatures": OwnerSpec("DemandFeatureService", Boundary.PREPARATION, ("S35",), subject_guard_required=False),
        "ResolveEvidence": OwnerSpec("EvidenceResolver", Boundary.PREPARATION, ("S36",), subject_guard_required=False),
        "RecordValidation": OwnerSpec("ValidationService", Boundary.PREPARATION, ("S37",), subject_guard_required=False),
        "CommitBundle": OwnerSpec("T6CommitCoordinator", Boundary.T6, ("S51", "S01", "S27", "S31", "S38", "S39", "S40", "S41", "S42", "S43", "S29", "S02", "S03", "S04"), registry_required=True),
        "Reauthorize": OwnerSpec("AuthorizationService", Boundary.T6, ("S51", "S01", "S27", "S31", "S38", "S42", "S29", "S02", "S03", "S04"), registry_required=True),
        "StartSession": OwnerSpec("ExecutionService", Boundary.T7, ("S51", "S01", "S38", "S44", "S45", "S02", "S03", "S04"), registry_required=True),
        "ResumeSession": OwnerSpec("ExecutionService", Boundary.T7, ("S51", "S01", "S38", "S44", "S45", "S02", "S03", "S04"), registry_required=True),
        "ContinueSession": OwnerSpec("ExecutionService", Boundary.T7, ("S51", "S01", "S38", "S44", "S45", "S02", "S03", "S04"), registry_required=True),
        "SettleCall": OwnerSpec("CallLedgerService", Boundary.T8, ("S01", "S27", "S31", "S32", "S02", "S03", "S04")),
        "MarkUnknown": OwnerSpec("CallLedgerService", Boundary.T8, ("S01", "S27", "S31", "S32", "S02", "S03", "S04")),
        "ReapIntent": OwnerSpec("PlanningWorkflowService", Boundary.T8, ("S01", "S27", "S29", "S31", "S02", "S03", "S04")),
    }
)


CATALOG_RELEASE_BOUNDARIES: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "ExerciseCatalogService.PublishRevision": MappingProxyType({"writes": ("S19",), "adoption_owner": "T2 classification/invalidation"}),
        "ExerciseMappingService.DecideMapping": MappingProxyType({"writes": ("S20",), "adoption_owner": "explicit factset selection"}),
        "ReleaseEvaluationService.RecordRelease": MappingProxyType({"writes": ("S48",), "boundary": Boundary.EXTERNAL, "activation_owner": "T2 user activation"}),
        "DecisionPublicationService.PublishManifest": MappingProxyType({"consumes_exact": ("S19", "S20", "S48"), "may_adopt_or_activate": False}),
    }
)


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    artifact_id: UUID
    artifact_kind: str
    artifact_identity: str
    artifact_version: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class DispatchPermit:
    reservation_id: UUID
    sendable: bool
    replayed: bool


@dataclass(frozen=True, slots=True)
class EventWrite:
    event_id: UUID
    aggregate_type: str
    aggregate_identity: str
    aggregate_revision: int
    event_type: str
    destination: str
    outbox_id: UUID


class RestrictedSqlSession:
    """Structured DML without arbitrary SQL, cursor, connection, or lock escape."""

    __slots__ = ("__allowed_logical_ids", "__cursor", "__subject_id")

    def __init__(
        self,
        cursor: Cursor[Any],
        allowed_logical_ids: Sequence[str],
        subject_id: UUID | None,
    ):
        self.__cursor = cursor
        self.__allowed_logical_ids = frozenset(allowed_logical_ids)
        self.__subject_id = subject_id

    def _table(self, logical_id: str) -> str:
        if logical_id not in self.__allowed_logical_ids or logical_id not in _LOGICAL_TABLES:
            raise StatementRejected(
                f"logical table {logical_id} exceeds capability "
                f"{sorted(self.__allowed_logical_ids)}"
            )
        return _LOGICAL_TABLES[logical_id]

    @staticmethod
    def _items(values: Mapping[str, Any], label: str) -> tuple[tuple[str, Any], ...]:
        if not values:
            raise ValueError(f"{label} cannot be empty")
        items = tuple(sorted(values.items()))
        if any(not name or not name.replace("_", "").isalnum() for name, _ in items):
            raise ValueError(f"{label} contains an invalid column")
        return items

    def insert(self, logical_id: str, values: Mapping[str, Any]) -> int:
        table = self._table(logical_id)
        items = self._items(values, "insert values")
        self._require_subject_predicate(logical_id, dict(items), "insert values")
        statement = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
            sql.Identifier("kineticloop"),
            sql.Identifier(table),
            sql.SQL(",").join(sql.Identifier(name) for name, _ in items),
            sql.SQL(",").join(sql.Placeholder() for _ in items),
        )
        self.__cursor.execute(statement, tuple(value for _, value in items))
        return self.__cursor.rowcount

    def update(
        self,
        logical_id: str,
        values: Mapping[str, Any],
        where: Mapping[str, Any],
    ) -> int:
        table = self._table(logical_id)
        assignments = self._items(values, "update values")
        predicates = self._items(where, "update predicates")
        self._require_subject_predicate(logical_id, dict(predicates), "update predicates")
        assignment_values = dict(assignments)
        if (
            "subject_id" in assignment_values
            and assignment_values["subject_id"] != self.__subject_id
        ):
            raise StatementRejected(
                "update values cannot change the authenticated transaction subject"
            )
        statement = sql.SQL("UPDATE {}.{} SET {} WHERE {}").format(
            sql.Identifier("kineticloop"),
            sql.Identifier(table),
            sql.SQL(",").join(
                sql.SQL("{}={}").format(sql.Identifier(name), sql.Placeholder())
                for name, _ in assignments
            ),
            sql.SQL(" AND ").join(
                sql.SQL("{}={}").format(sql.Identifier(name), sql.Placeholder())
                for name, _ in predicates
            ),
        )
        self.__cursor.execute(
            statement,
            tuple(value for _, value in assignments)
            + tuple(value for _, value in predicates),
        )
        return self.__cursor.rowcount

    def _require_subject_predicate(
        self, logical_id: str, values: Mapping[str, Any], label: str
    ) -> None:
        if logical_id in {"S49", "S50", "S51"}:
            return
        if self.__subject_id is None or values.get("subject_id") != self.__subject_id:
            raise StatementRejected(
                f"{label} must bind the authenticated transaction subject"
            )

    def relation_locks(self) -> frozenset[str]:
        self.__cursor.execute(
            "SELECT c.relname FROM pg_locks l JOIN pg_class c ON c.oid=l.relation "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE l.pid=pg_backend_pid() "
            "AND n.nspname='kineticloop' AND l.granted"
        )
        return frozenset(str(row[0]) for row in self.__cursor.fetchall())


class RepositoryTransaction:
    """One command-owned transaction with monotonic lock acquisition."""

    __slots__ = (
        "__cursor",
        "_last_aggregate_rank",
        "_last_stage",
        "_registry",
        "_subject",
        "_trace",
        "command_kind",
        "spec",
        "subject_id",
    )

    def __init__(self, cursor: Cursor[Any], command_kind: str, subject_id: UUID | None):
        try:
            self.spec = TRANSACTION_OWNER_MATRIX[command_kind]
        except KeyError as error:
            raise ValueError(f"unknown command owner surface: {command_kind}") from error
        self.__cursor = cursor
        self.command_kind = command_kind
        self.subject_id = subject_id
        self._last_stage = 0
        self._registry = False
        self._subject = False
        self._trace: list[tuple[LockStage, str]] = []
        self._last_aggregate_rank = -1

    @property
    def lock_trace(self) -> tuple[tuple[LockStage, str], ...]:
        """Observed canonical acquisition order, useful for operational evidence."""

        return tuple(self._trace)

    def _advance(self, stage: LockStage, *, allow_equal: bool = False) -> None:
        if stage < self._last_stage or (stage == self._last_stage and not allow_equal):
            raise LockOrderViolation(
                f"{stage.name} cannot follow {LockStage(self._last_stage).name}"
            )
        self._last_stage = stage

    def acquire_registry_lease(
        self,
        artifact_ids: Sequence[UUID],
        *,
        minimum_revision: int = 0,
        lock_timeout_ms: int = 1_000,
    ) -> int:
        if not self.spec.registry_required:
            raise GuardRequired(f"{self.command_kind} has no registry lease")
        if self.subject_id is None or not artifact_ids:
            raise GuardRequired("registry lease requires subject and exact artifact identities")
        self._advance(LockStage.REGISTRY)
        routine = {
            "PublishManifest": "registry_guard_publish_manifest",
            "CommitBundle": "registry_guard_commit_bundle",
            "Reauthorize": "registry_guard_reauthorize",
            "StartSession": "registry_guard_start_session",
            "ResumeSession": "registry_guard_resume_session",
            "ContinueSession": "registry_guard_continue_session",
        }[self.command_kind]
        self.__cursor.execute(
            f"SELECT kineticloop.{routine}(%s,%s,%s,%s)",
            (self.subject_id, list(artifact_ids), minimum_revision, lock_timeout_ms),
        )
        row = self.__cursor.fetchone()
        if row is None:
            raise GuardRequired("registry lease was not acquired")
        # The merged guard routine acquires S51 then S01 in the same transaction.
        self._registry = True
        self._subject = True
        self._last_stage = LockStage.SUBJECT
        self._trace.extend(
            ((LockStage.REGISTRY, "S51"), (LockStage.SUBJECT, "S01"))
        )
        return int(row[0])

    def lock_subject(self) -> None:
        if self.subject_id is None:
            raise GuardRequired("subject guard requires a subject")
        self._advance(LockStage.SUBJECT)
        self.__cursor.execute(
            "SELECT subject_id FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s FOR UPDATE",
            (self.subject_id,),
        )
        if self.__cursor.fetchone() is None:
            raise GuardRequired("subject coordination row does not exist")
        self._subject = True
        self._trace.append((LockStage.SUBJECT, "S01"))

    def _require_subject(self) -> None:
        if not self._subject:
            raise GuardRequired("S01 subject guard is required")

    def _require_receipt_guard(self) -> None:
        # Frozen T1 source receipt admission is the sole subject-command exception:
        # it owns source idempotency and must not later reverse into S01.
        if not self._subject and self.spec.boundary is not Boundary.T1:
            raise GuardRequired("S01 subject guard is required")

    def lock_quota_buckets(self, keys: Sequence[tuple[str, datetime, datetime]]) -> None:
        self._require_subject()
        self._advance(LockStage.QUOTA)
        for quota_kind, window_start, window_end in sorted(set(keys)):
            self.__cursor.execute(
                "SELECT id FROM kineticloop.planning_quota_buckets "
                "WHERE subject_id=%s AND quota_kind=%s AND window_start=%s "
                "AND window_end=%s ORDER BY id FOR UPDATE",
                (self.subject_id, quota_kind, window_start, window_end),
            )
            rows = self.__cursor.fetchall()
            if not rows:
                raise GuardRequired("quota bucket does not exist")
            self._trace.append(
                (LockStage.QUOTA, f"S30:{quota_kind}:{window_start}:{window_end}")
            )

    def lock_intents(self, intent_ids: Sequence[UUID]) -> None:
        self._require_subject()
        self._advance(LockStage.INTENT)
        self._lock_ids("planning_intents", intent_ids)

    def lock_reservations(self, reservation_ids: Sequence[UUID]) -> None:
        self._require_subject()
        self._advance(LockStage.RESERVATION)
        self._lock_ids("call_reservations", reservation_ids)

    def lock_daily_head(self, local_date: Any) -> None:
        self._require_subject()
        self._advance(LockStage.DAILY_HEAD)
        self.__cursor.execute(
            "SELECT id FROM kineticloop.daily_plan_heads "
            "WHERE subject_id=%s AND local_date=%s FOR UPDATE",
            (self.subject_id, local_date),
        )
        rows = self.__cursor.fetchall()
        if not rows:
            raise GuardRequired("daily head does not exist")
        self._trace.append((LockStage.DAILY_HEAD, f"S38:{local_date}"))

    def lock_execution(self, session_ids: Sequence[UUID]) -> None:
        self._require_subject()
        self._advance(LockStage.EXECUTION)
        self._lock_ids("workout_sessions", session_ids)

    def lock_receipt(self, command_kind: str, client_key: str, actor_scope: str) -> None:
        self._require_receipt_guard()
        self._advance(LockStage.RECEIPT)
        self.__cursor.execute(
            "SELECT id FROM kineticloop.command_receipts WHERE subject_id=%s "
            "AND command_kind=%s AND client_key=%s AND actor_scope=%s FOR UPDATE",
            (self.subject_id, command_kind, client_key, actor_scope),
        )
        self.__cursor.fetchall()
        self._trace.append(
            (LockStage.RECEIPT, f"S02:{actor_scope}:{command_kind}:{client_key}")
        )

    def lock_remaining(self, table: str, object_ids: Sequence[UUID]) -> None:
        self._require_subject()
        self._advance(LockStage.AGGREGATE, allow_equal=True)
        allowed = {
            "factset_revisions",
            "manifest_builds",
            "planning_attempts",
            "validation_results",
        }
        if table not in allowed:
            raise ValueError("remaining aggregate table is not allowlisted")
        rank = {
            "factset_revisions": 10,
            "manifest_builds": 20,
            "planning_attempts": 30,
            "validation_results": 40,
        }[table]
        if rank <= self._last_aggregate_rank:
            raise LockOrderViolation("remaining aggregate table order is not stable")
        self._last_aggregate_rank = rank
        self._lock_ids(table, object_ids)

    def _lock_ids(self, table: str, object_ids: Sequence[UUID]) -> None:
        for object_id in sorted(set(object_ids), key=str):
            self.__cursor.execute(
                f"SELECT id FROM kineticloop.{table} "
                "WHERE subject_id=%s AND id=%s FOR UPDATE",
                (self.subject_id, object_id),
            )
            if self.__cursor.fetchone() is None:
                raise GuardRequired(f"{table} row does not exist")
            stage = {
                "planning_intents": LockStage.INTENT,
                "call_reservations": LockStage.RESERVATION,
                "workout_sessions": LockStage.EXECUTION,
            }.get(table, LockStage.AGGREGATE)
            logical = {
                "planning_intents": "S27",
                "call_reservations": "S31",
                "workout_sessions": "S44",
                "factset_revisions": "S15",
                "manifest_builds": "S23",
                "planning_attempts": "S29",
                "validation_results": "S37",
            }[table]
            self._trace.append((stage, f"{logical}:{object_id}"))

    def require_artifact(self, identity: ArtifactIdentity) -> None:
        if not self._registry:
            raise GuardRequired("artifact consumption requires the shared registry lease")
        self.__cursor.execute(
            "SELECT 1 FROM kineticloop.safety_artifacts WHERE id=%s "
            "AND artifact_kind=%s AND artifact_identity=%s AND artifact_version=%s "
            "AND content_hash=%s",
            (
                identity.artifact_id,
                identity.artifact_kind,
                identity.artifact_identity,
                identity.artifact_version,
                identity.content_hash,
            ),
        )
        if self.__cursor.fetchone() is None:
            raise ArtifactIdentityRequired("exact registered artifact identity is required")

    def require_current_fence(
        self,
        intent_id: UUID,
        *,
        owner_id: str,
        fence: int,
        expected_status: str = "RUNNING",
    ) -> None:
        self._require_subject()
        if self._last_stage < LockStage.INTENT:
            raise GuardRequired("intent must be locked before checking fence")
        self.__cursor.execute(
            "SELECT 1 FROM kineticloop.planning_intents WHERE subject_id=%s AND id=%s "
            "AND lease_owner=%s AND fence_token=%s AND status=%s "
            "AND lease_expires_at > clock_timestamp()",
            (self.subject_id, intent_id, owner_id, fence, expected_status),
        )
        if self.__cursor.fetchone() is None:
            raise FenceLost("stale owner/fence cannot commit")

    def permit_dispatch(
        self,
        reservation_id: UUID,
        *,
        permit_key: str,
        request_hash: str,
        receipt_id: UUID,
        event: EventWrite,
        fence: int,
    ) -> DispatchPermit:
        self._require_subject()
        if self._last_stage < LockStage.RESERVATION:
            raise GuardRequired("reservation must be locked before dispatch transition")

        def transition(session: RestrictedSqlSession) -> Mapping[str, Any]:
            self.__cursor.execute(
                "SELECT status, dispatch_fence, typed_payload "
                "FROM kineticloop.call_reservations "
                "WHERE subject_id=%s AND id=%s",
                (self.subject_id, reservation_id),
            )
            row = self.__cursor.fetchone()
            if row is None or int(row[1] or 0) != fence:
                raise DispatchNotPermitted("reservation or fence mismatch")
            if row[0] != "RESERVED":
                raise DispatchNotPermitted("only RESERVED may become DISPATCH_INTENT")
            payload = dict(row[2] or {})
            payload["permit_key"] = permit_key
            if session.update(
                "S31",
                {"status": "DISPATCH_INTENT", "typed_payload": Jsonb(payload)},
                {"subject_id": self.subject_id, "id": reservation_id},
            ) != 1:
                raise DispatchNotPermitted("reservation transition was not durable")
            return {"reservation_id": str(reservation_id), "permit_key": permit_key}

        outcome, replayed = self.idempotent_outcome(
            receipt_id=receipt_id,
            actor_scope="subject",
            client_key=permit_key,
            request_hash=request_hash,
            mutation=transition,
            event=event,
        )
        if outcome.get("reservation_id") != str(reservation_id):
            raise DispatchNotPermitted("durable permit outcome is inconsistent")
        return DispatchPermit(reservation_id, sendable=not replayed, replayed=replayed)

    def idempotent_outcome(
        self,
        *,
        receipt_id: UUID,
        actor_scope: str,
        client_key: str,
        request_hash: str,
        mutation: Callable[[RestrictedSqlSession], Mapping[str, Any]],
        event: EventWrite,
        aggregate_locks: Mapping[str, Sequence[UUID]] | None = None,
    ) -> tuple[Mapping[str, Any], bool]:
        self._require_receipt_guard()
        self.lock_receipt(self.command_kind, client_key, actor_scope)
        self.__cursor.execute(
            "SELECT request_hash,status,typed_payload FROM kineticloop.command_receipts "
            "WHERE subject_id=%s AND actor_scope=%s AND command_kind=%s AND client_key=%s",
            (self.subject_id, actor_scope, self.command_kind, client_key),
        )
        prior = self.__cursor.fetchone()
        if prior is not None:
            if prior[0] != request_hash:
                raise IdempotencyConflict("command key request hash mismatch")
            if prior[1] != "SUCCEEDED" or "outcome" not in prior[2]:
                raise IdempotencyConflict("command key has no durable successful outcome")
            return dict(prior[2]["outcome"]), True
        for table in sorted(
            aggregate_locks or (),
            key={
                "factset_revisions": 10,
                "manifest_builds": 20,
                "planning_attempts": 30,
                "validation_results": 40,
            }.__getitem__,
        ):
            self.lock_remaining(table, (aggregate_locks or {})[table])
        self.__cursor.execute(
            "INSERT INTO kineticloop.command_receipts"
            "(id,subject_id,status,command_kind,client_key,actor_scope,request_hash) "
            "VALUES (%s,%s,'IN_PROGRESS',%s,%s,%s,%s)",
            (receipt_id, self.subject_id, self.command_kind, client_key, actor_scope, request_hash),
        )
        outcome = dict(
            mutation(
                RestrictedSqlSession(
                    self.__cursor, self.spec.mutation_surfaces, self.subject_id
                )
            )
        )
        self.__cursor.execute(
            "INSERT INTO kineticloop.domain_events"
            "(id,subject_id,aggregate_type,aggregate_identity,event_type,aggregate_revision,ref_s02_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (event.event_id, self.subject_id, event.aggregate_type, event.aggregate_identity, event.event_type, event.aggregate_revision, receipt_id),
        )
        self.__cursor.execute(
            "INSERT INTO kineticloop.outbox_deliveries"
            "(id,subject_id,destination,delivery_status,attempt_count,ref_s03_id) "
            "VALUES (%s,%s,%s,'PENDING',0,%s)",
            (event.outbox_id, self.subject_id, event.destination, event.event_id),
        )
        self.__cursor.execute(
            "UPDATE kineticloop.command_receipts SET status='SUCCEEDED',typed_payload=%s "
            "WHERE id=%s AND subject_id=%s",
            (Jsonb({"outcome": outcome}), receipt_id, self.subject_id),
        )
        return outcome, False

    def finish(self) -> None:
        if self.spec.registry_required and not self._registry:
            raise GuardRequired(f"{self.command_kind} requires a shared S51 registry lease")
        if self.spec.subject_guard_required and not self._subject:
            raise GuardRequired(f"{self.command_kind} requires the S01 subject guard")


def execute_command(
    connection: Connection[Any],
    command_kind: str,
    subject_id: UUID | None,
    operation: Callable[[RepositoryTransaction], _T],
) -> _T:
    """Own the outer transaction and commit only after all owner guards pass."""

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise TransactionStateError("repository command requires an idle connection")
    with connection.transaction():
        transaction = RepositoryTransaction(connection.cursor(), command_kind, subject_id)
        result = operation(transaction)
        transaction.finish()
        return result


def execute_preparation(
    connection: Connection[Any],
    command_kind: str,
    subject_id: UUID,
    operation: Callable[[RestrictedSqlSession], _T],
) -> _T:
    """Run external/model preparation in an independent transaction with no coordination API."""

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise TransactionStateError("preparation requires an idle connection")
    specification = TRANSACTION_OWNER_MATRIX.get(command_kind)
    if specification is None or specification.boundary is not Boundary.PREPARATION:
        raise GuardRequired("command is not a preparation owner")
    with connection.transaction():
        return operation(
            RestrictedSqlSession(
                connection.cursor(), specification.mutation_surfaces, subject_id
            )
        )


def execute_factset_build(
    connection: Connection[Any],
    command_kind: str,
    subject_id: UUID,
    build_id: UUID,
    operation: Callable[[RestrictedSqlSession], _T],
) -> _T:
    """Lock only the S15 build; factset construction never acquires S01."""

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise TransactionStateError("factset build requires an idle connection")
    specification = TRANSACTION_OWNER_MATRIX.get(command_kind)
    if specification is None or specification.boundary is not Boundary.BUILD:
        raise GuardRequired("command is not a factset-build owner")
    with connection.transaction():
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id FROM kineticloop.factset_revisions "
            "WHERE subject_id=%s AND id=%s FOR UPDATE",
            (subject_id, build_id),
        )
        if cursor.fetchone() is None:
            raise GuardRequired("factset build does not exist")
        return operation(
            RestrictedSqlSession(cursor, specification.mutation_surfaces, subject_id)
        )


def claim_outbox(
    connection: Connection[Any], *, destination: str, limit: int = 1
) -> tuple[UUID, ...]:
    """Claim S04 rows without exposing an S01/business-command callback."""

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise TransactionStateError("outbox claim requires an idle connection")
    if limit <= 0:
        raise ValueError("limit must be positive")
    with connection.transaction():
        rows = connection.execute(
            "SELECT id FROM kineticloop.outbox_deliveries "
            "WHERE destination=%s AND delivery_status='PENDING' ORDER BY recorded_at,id "
            "FOR UPDATE SKIP LOCKED LIMIT %s",
            (destination, limit),
        ).fetchall()
        ids = tuple(UUID(str(row[0])) for row in rows)
        if ids:
            connection.execute(
                "UPDATE kineticloop.outbox_deliveries SET delivery_status='CLAIMED' "
                "WHERE id=ANY(%s)",
                (list(ids),),
            )
        return ids
