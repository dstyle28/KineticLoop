"""Fail-closed repository transaction interfaces for frozen T1--T8 boundaries.

The module deliberately owns no business decisions.  It supplies the small set of
mechanical primitives every command repository needs: one top-level transaction,
the frozen lock order, registry/subject guards, exact artifact and fence checks,
durable idempotent outcomes, atomic event/outbox writes, and isolated outbox claims.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Any, TypeVar
from uuid import UUID
from weakref import WeakKeyDictionary

from psycopg import Connection, Cursor, sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.persistence.metadata import REQUIRED_FIELDS, metadata
from kineticloop.persistence.schema_topology import LOGICAL_RELATIONS

_T = TypeVar("_T")

_LOGICAL_TABLES = {row.logical_id: row.table_name for row in LOGICAL_RELATIONS}
_CURSORS: WeakKeyDictionary[object, Cursor[Any]] = WeakKeyDictionary()


def _cursor(owner: object) -> Cursor[Any]:
    """Return internal DB state without placing a cursor on callback capabilities."""

    try:
        return _CURSORS[owner]
    except KeyError as error:  # pragma: no cover - defensive lifetime invariant
        raise TransactionStateError("repository capability is no longer active") from error


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


class ReplayNotFound(RepositoryTransactionError):
    """No durable successful outcome exists for the supplied idempotency key."""


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
        "ReceiveEvidence": OwnerSpec(
            "EvidenceService",
            Boundary.T1,
            ("S09", "S02", "S03", "S04"),
            subject_guard_required=False,
        ),
        "RecordCandidate": OwnerSpec(
            "ExtractionService", Boundary.PREPARATION, ("S10",), subject_guard_required=False
        ),
        "DecideAssociation": OwnerSpec(
            "EvidenceAssociationService", Boundary.T2_IN, ("S12", "S01", "S02", "S03", "S04")
        ),
        "DecideAdmission": OwnerSpec(
            "AdmissionService", Boundary.T2_IN, ("S13", "S01", "S02", "S03", "S04")
        ),
        "AcceptFactRevision": OwnerSpec(
            "CanonicalFactService", Boundary.T2_IN, ("S14", "S01", "S02", "S03", "S04")
        ),
        "ApplyControl": OwnerSpec(
            "ControlService", Boundary.T2_IN, ("S17", "S18", "S01", "S02", "S03", "S04")
        ),
        "ClearControl": OwnerSpec(
            "ControlService", Boundary.T2_IN, ("S17", "S18", "S01", "S02", "S03", "S04")
        ),
        "ApproveChange": OwnerSpec(
            "ProgramReviewService", Boundary.T2_IN, ("S08", "S01", "S02", "S03", "S04")
        ),
        "ActivateApprovedProgram": OwnerSpec(
            "ProgramService", Boundary.T2_IN, ("S06", "S01", "S02", "S03", "S04")
        ),
        "RecordActualExecution": OwnerSpec(
            "CanonicalFactService", Boundary.T2_IN, ("S14", "S01", "S02", "S03", "S04")
        ),
        "CompleteReportedWorkout": OwnerSpec(
            "ExecutionService", Boundary.T2_IN, ("S44", "S14", "S01", "S02", "S03", "S04")
        ),
        "BeginBuild": OwnerSpec(
            "CanonicalViewService", Boundary.BUILD, ("S15",), subject_guard_required=False
        ),
        "WriteCandidate": OwnerSpec(
            "CanonicalViewService", Boundary.BUILD, ("S15", "S16"), subject_guard_required=False
        ),
        "CompleteFactset": OwnerSpec(
            "CanonicalViewService", Boundary.BUILD, ("S15",), subject_guard_required=False
        ),
        "SealFactset": OwnerSpec(
            "CanonicalViewService", Boundary.T2_SEAL, ("S01", "S15", "S02", "S03", "S04")
        ),
        "RegisterArtifact": OwnerSpec(
            "SafetyRegistry", Boundary.EXTERNAL, ("S49",), subject_guard_required=False
        ),
        "RevokeArtifact": OwnerSpec(
            "SafetyRegistry", Boundary.T2_GLOBAL, ("S50", "S51"), subject_guard_required=False
        ),
        "RecordProjection": OwnerSpec(
            "ProjectionService", Boundary.PREPARATION, ("S21", "S22"), subject_guard_required=False
        ),
        "BuildManifest": OwnerSpec(
            "DecisionPublicationService",
            Boundary.PREPARATION,
            ("S23",),
            subject_guard_required=False,
        ),
        "PublishManifest": OwnerSpec(
            "DecisionPublicationService",
            Boundary.T3,
            ("S51", "S01", "S23", "S24", "S25", "S02", "S03", "S04"),
            registry_required=True,
        ),
        "AdmitOrReviseIntent": OwnerSpec(
            "PlanningWorkflowService",
            Boundary.T4,
            ("S01", "S30", "S27", "S28", "S29", "S02", "S03", "S04"),
        ),
        "CancelIntent": OwnerSpec(
            "PlanningWorkflowService", Boundary.T8, ("S01", "S27", "S31", "S02", "S03", "S04")
        ),
        "AcquireLease": OwnerSpec(
            "PlanningWorkflowService", Boundary.T5, ("S01", "S27", "S29", "S02", "S03", "S04")
        ),
        "RenewLease": OwnerSpec(
            "PlanningWorkflowService", Boundary.T5, ("S01", "S27", "S29", "S02", "S03", "S04")
        ),
        "ReserveCall": OwnerSpec(
            "CallLedgerService", Boundary.T5, ("S01", "S27", "S31", "S32", "S02", "S03", "S04")
        ),
        "PermitDispatch": OwnerSpec(
            "CallLedgerService", Boundary.T5, ("S01", "S27", "S31", "S32", "S02", "S03", "S04")
        ),
        "RecordToolResult": OwnerSpec(
            "ContextToolGateway", Boundary.PREPARATION, ("S33",), subject_guard_required=False
        ),
        "RecordProposal": OwnerSpec(
            "ProposalService", Boundary.PREPARATION, ("S34",), subject_guard_required=False
        ),
        "RecordDemandFeatures": OwnerSpec(
            "DemandFeatureService", Boundary.PREPARATION, ("S35",), subject_guard_required=False
        ),
        "ResolveEvidence": OwnerSpec(
            "EvidenceResolver", Boundary.PREPARATION, ("S36",), subject_guard_required=False
        ),
        "RecordValidation": OwnerSpec(
            "ValidationService", Boundary.PREPARATION, ("S37",), subject_guard_required=False
        ),
        "CommitBundle": OwnerSpec(
            "T6CommitCoordinator",
            Boundary.T6,
            (
                "S51",
                "S01",
                "S27",
                "S31",
                "S38",
                "S39",
                "S40",
                "S41",
                "S42",
                "S43",
                "S29",
                "S02",
                "S03",
                "S04",
            ),
            registry_required=True,
        ),
        "Reauthorize": OwnerSpec(
            "AuthorizationService",
            Boundary.T6,
            ("S51", "S01", "S27", "S31", "S38", "S42", "S29", "S02", "S03", "S04"),
            registry_required=True,
        ),
        "StartSession": OwnerSpec(
            "ExecutionService",
            Boundary.T7,
            ("S51", "S01", "S38", "S44", "S45", "S02", "S03", "S04"),
            registry_required=True,
        ),
        "ResumeSession": OwnerSpec(
            "ExecutionService",
            Boundary.T7,
            ("S51", "S01", "S38", "S44", "S45", "S02", "S03", "S04"),
            registry_required=True,
        ),
        "ContinueSession": OwnerSpec(
            "ExecutionService",
            Boundary.T7,
            ("S51", "S01", "S38", "S44", "S45", "S02", "S03", "S04"),
            registry_required=True,
        ),
        "SettleCall": OwnerSpec(
            "CallLedgerService", Boundary.T8, ("S01", "S27", "S31", "S32", "S02", "S03", "S04")
        ),
        "MarkUnknown": OwnerSpec(
            "CallLedgerService", Boundary.T8, ("S01", "S27", "S31", "S32", "S02", "S03", "S04")
        ),
        "ReapIntent": OwnerSpec(
            "PlanningWorkflowService",
            Boundary.T8,
            ("S01", "S27", "S29", "S31", "S02", "S03", "S04"),
        ),
    }
)


CATALOG_RELEASE_BOUNDARIES: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "ExerciseCatalogService.PublishRevision": MappingProxyType(
            {"writes": ("S19",), "adoption_owner": "T2 classification/invalidation"}
        ),
        "ExerciseMappingService.DecideMapping": MappingProxyType(
            {"writes": ("S20",), "adoption_owner": "explicit factset selection"}
        ),
        "ReleaseEvaluationService.RecordRelease": MappingProxyType(
            {
                "writes": ("S48",),
                "boundary": Boundary.EXTERNAL,
                "activation_owner": "T2 user activation",
            }
        ),
        "DecisionPublicationService.PublishManifest": MappingProxyType(
            {"consumes_exact": ("S19", "S20", "S48"), "may_adopt_or_activate": False}
        ),
    }
)


# Column authority is command-specific and fail-closed.  Adding a logical table to
# OwnerSpec does not by itself grant arbitrary column writes on that table.
_MUTATION_COLUMNS: Mapping[str, Mapping[tuple[str, str], frozenset[str]]] = MappingProxyType(
    {
        "ReceiveEvidence": {
            ("S09", "insert"): frozenset(
                {
                    "id",
                    "subject_id",
                    "source_connection_identity",
                    "source_object_type",
                    "source_object_identity",
                    "source_revision",
                    "trust_class",
                    "source_class",
                    "command_authority",
                }
            )
        },
        "DecideAdmission": {
            ("S01", "update"): frozenset({"authorization_epoch", "input_frontier_hash"})
        },
        "PublishManifest": {
            ("S01", "update"): frozenset({"decision_generation", "current_manifest_id"}),
            ("S23", "update"): frozenset({"status", "captured_epoch"}),
        },
        "AdmitOrReviseIntent": {("S27", "update"): frozenset({"status", "typed_payload"})},
        "AcquireLease": {
            ("S27", "update"): frozenset(
                {"status", "typed_payload", "lease_owner", "fence_token", "lease_expires_at"}
            )
        },
        "SettleCall": {
            ("S27", "update"): frozenset({"status", "typed_payload"}),
            ("S31", "update"): frozenset({"status", "settlement_revision", "typed_payload"}),
        },
        "PermitDispatch": {("S31", "update"): frozenset({"status", "typed_payload"})},
        "StartSession": {
            ("S44", "update"): frozenset({"lifecycle", "execution_revision", "typed_payload"})
        },
        "CommitBundle": {
            ("S27", "update"): frozenset(
                {"status", "result_bundle_revision_id", "result_authorization_id"}
            ),
            ("S29", "update"): frozenset({"status", "completed_at"}),
            ("S38", "update"): frozenset({"head_revision", "current_bundle_revision_id"}),
            ("S39", "insert"): frozenset(
                {
                    "id",
                    "subject_id",
                    "local_date",
                    "revision_no",
                    "generation_mode",
                    "typed_payload",
                    "ref_s02_id",
                    "ref_s24_id",
                    "ref_s27_id",
                    "ref_s29_id",
                    "ref_s37_id",
                    "ref_s38_id",
                }
            ),
            ("S40", "insert"): frozenset(
                {
                    "id",
                    "subject_id",
                    "prescription_identity",
                    "prescription_kind",
                    "prescription_revision",
                    "ref_s34_id",
                    "ref_s49_id",
                }
            ),
            ("S41", "insert"): frozenset(
                {
                    "id",
                    "subject_id",
                    "member_kind",
                    "session_slot",
                    "member_order",
                    "ref_s39_id",
                    "ref_s40_id",
                }
            ),
            ("S42", "insert"): frozenset(
                {
                    "id",
                    "subject_id",
                    "bound_content_hash",
                    "scope",
                    "issuance_reason",
                    "artifact_dependency_closure_hash",
                    "registry_revision_at_issue",
                    "valid_from",
                    "valid_until",
                    "validity_certificate",
                    "ref_s02_id",
                    "ref_s05_id",
                    "ref_s24_id",
                    "ref_s36_id",
                    "ref_s37_id",
                    "ref_s40_id",
                    "ref_s49_id",
                    "registry_state_id",
                }
            ),
            ("S43", "insert"): frozenset(
                {
                    "id",
                    "subject_id",
                    "event_kind",
                    "scope",
                    "causation_key",
                    "ref_s42_id",
                    "ref_s02_id",
                }
            ),
        },
        "RecordProjection": {
            ("S21", "update"): frozenset({"projection_revision", "typed_payload"})
        },
        "BeginBuild": {("S15", "update"): frozenset({"status", "member_revision"})},
        "WriteCandidate": {
            ("S15", "update"): frozenset({"member_revision"}),
        },
        "CompleteFactset": {("S15", "update"): frozenset({"status", "member_revision"})},
    }
)


def _all_columns(logical_id: str) -> frozenset[str]:
    table = _LOGICAL_TABLES[logical_id]
    return frozenset(metadata.tables[f"kineticloop.{table}"].columns.keys())


# Every public owner has an explicit logical-table/operation capability.  Existing
# entries above intentionally remain narrower where multiple commands share a table.
_COMMAND_OPERATIONS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "ReceiveEvidence": {"insert": ("S09",)},
    "RecordCandidate": {"insert": ("S10",)},
    "DecideAssociation": {"insert": ("S12",), "update": ("S01",)},
    "DecideAdmission": {"insert": ("S13",), "update": ("S01",)},
    "AcceptFactRevision": {"insert": ("S14",), "update": ("S01",)},
    "ApplyControl": {"insert": ("S17", "S18"), "update": ("S01", "S18")},
    "ClearControl": {"insert": ("S17", "S18"), "update": ("S01", "S18")},
    "ApproveChange": {"insert": ("S08",), "update": ("S01",)},
    "ActivateApprovedProgram": {"update": ("S01",)},
    "RecordActualExecution": {"insert": ("S14",), "update": ("S01",)},
    "CompleteReportedWorkout": {"insert": ("S14",), "update": ("S01", "S44")},
    "BeginBuild": {"update": ("S15",)},
    "WriteCandidate": {"insert": ("S16",), "update": ("S15",)},
    "CompleteFactset": {"update": ("S15",)},
    "SealFactset": {"update": ("S01", "S15")},
    "RegisterArtifact": {"insert": ("S49",)},
    "RevokeArtifact": {"insert": ("S50",), "update": ("S51",)},
    "RecordProjection": {"insert": ("S21", "S22"), "update": ("S21",)},
    "BuildManifest": {"insert": ("S23",), "update": ("S23",)},
    "PublishManifest": {"insert": ("S24", "S25"), "update": ("S01", "S23")},
    "AdmitOrReviseIntent": {"insert": ("S27", "S28", "S29"), "update": ("S27", "S30")},
    "CancelIntent": {"update": ("S27", "S31")},
    "AcquireLease": {"update": ("S27", "S29")},
    "RenewLease": {"update": ("S27", "S29")},
    "ReserveCall": {"insert": ("S31", "S32"), "update": ("S27",)},
    "PermitDispatch": {"insert": ("S32",), "update": ("S31",)},
    "RecordToolResult": {"insert": ("S33",)},
    "RecordProposal": {"insert": ("S34",)},
    "RecordDemandFeatures": {"insert": ("S35",)},
    "ResolveEvidence": {"insert": ("S36",)},
    "RecordValidation": {"insert": ("S37",)},
    "CommitBundle": {
        "insert": ("S39", "S40", "S41", "S42", "S43"),
        "update": ("S01", "S27", "S29", "S38"),
    },
    "Reauthorize": {"insert": ("S42",), "update": ("S01", "S27", "S29", "S38")},
    "StartSession": {"insert": ("S45",), "update": ("S44",)},
    "ResumeSession": {"insert": ("S45",), "update": ("S44",)},
    "ContinueSession": {"insert": ("S45",), "update": ("S44",)},
    "SettleCall": {"insert": ("S32",), "update": ("S27", "S31")},
    "MarkUnknown": {"insert": ("S32",), "update": ("S27", "S31")},
    "ReapIntent": {"update": ("S27", "S29", "S31")},
}

_mutation_columns = {command: dict(rules) for command, rules in _MUTATION_COLUMNS.items()}
for _command, _operations in _COMMAND_OPERATIONS.items():
    _rules = _mutation_columns.setdefault(_command, {})
    for _operation, _logical_ids in _operations.items():
        for _logical_id in _logical_ids:
            _rules.setdefault((_logical_id, _operation), _all_columns(_logical_id))

# S01 field ownership is narrower than table ownership and must never inherit the
# generic table column set above.
_S01_UPDATE_COLUMNS: Mapping[str, frozenset[str]] = {
    "DecideAssociation": frozenset({"input_frontier_hash", "authorization_epoch"}),
    "DecideAdmission": frozenset({"input_frontier_hash", "authorization_epoch"}),
    "AcceptFactRevision": frozenset({"input_frontier_hash", "authorization_epoch"}),
    "ApplyControl": frozenset({"authorization_epoch", "last_control_event_id"}),
    "ClearControl": frozenset({"authorization_epoch", "last_control_event_id"}),
    "ApproveChange": frozenset({"authorization_epoch"}),
    "ActivateApprovedProgram": frozenset(
        {"active_program_id", "active_policy_bundle_id", "authorization_epoch"}
    ),
    "RecordActualExecution": frozenset({"execution_basis_event_id", "authorization_epoch"}),
    "CompleteReportedWorkout": frozenset({"execution_basis_event_id", "authorization_epoch"}),
    "SealFactset": frozenset({"current_factset_id", "input_frontier_hash"}),
    "PublishManifest": frozenset({"decision_generation", "current_manifest_id"}),
    "CommitBundle": frozenset({"execution_basis_event_id"}),
    "Reauthorize": frozenset({"execution_basis_event_id"}),
}
for _command, _columns in _S01_UPDATE_COLUMNS.items():
    _mutation_columns[_command][("S01", "update")] = _columns
_MUTATION_COLUMNS = MappingProxyType(
    {command: MappingProxyType(rules) for command, rules in _mutation_columns.items()}
)
MUTATION_CAPABILITY_MATRIX = _MUTATION_COLUMNS


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

    __slots__ = (
        "__allowed_logical_ids",
        "__command_kind",
        "__event_id",
        "__head_bundles",
        "__inserted_ids",
        "__locked_ids",
        "__receipt_id",
        "__registry_revision",
        "__subject_id",
        "__verified_artifacts",
        "__closure_authorizations",
        "__weakref__",
    )

    def __init__(
        self,
        cursor: Cursor[Any],
        allowed_logical_ids: Sequence[str],
        subject_id: UUID | None,
        *,
        command_kind: str,
        locked_ids: Mapping[str, frozenset[UUID]] | None = None,
        verified_artifacts: frozenset[UUID] = frozenset(),
        receipt_id: UUID | None = None,
        event_id: UUID | None = None,
        registry_revision: int | None = None,
        head_bundles: Mapping[UUID, UUID | None] | None = None,
    ):
        _CURSORS[self] = cursor
        self.__allowed_logical_ids = frozenset(allowed_logical_ids)
        self.__subject_id = subject_id
        self.__command_kind = command_kind
        self.__locked_ids = MappingProxyType(dict(locked_ids or {}))
        self.__verified_artifacts = verified_artifacts
        self.__receipt_id = receipt_id
        self.__event_id = event_id
        self.__registry_revision = registry_revision
        self.__head_bundles = MappingProxyType(dict(head_bundles or {}))
        self.__inserted_ids: dict[str, set[UUID]] = {}
        self.__closure_authorizations: set[UUID] = set()

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
        item_values = dict(items)
        self._require_columns(logical_id, "insert", item_values)
        self._require_insert_bindings(logical_id, item_values)
        statement = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
            sql.Identifier("kineticloop"),
            sql.Identifier(table),
            sql.SQL(",").join(sql.Identifier(name) for name, _ in items),
            sql.SQL(",").join(sql.Placeholder() for _ in items),
        )
        cursor = _cursor(self)
        cursor.execute(statement, tuple(value for _, value in items))
        inserted_id = item_values.get("id")
        if cursor.rowcount == 1 and isinstance(inserted_id, UUID):
            self.__inserted_ids.setdefault(logical_id, set()).add(inserted_id)
        return cursor.rowcount

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
        self._require_columns(logical_id, "update", assignment_values)
        self._require_locked_identity(logical_id, dict(predicates))
        self._require_update_bindings(logical_id, assignment_values, dict(predicates))
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
        cursor = _cursor(self)
        cursor.execute(
            statement,
            tuple(value for _, value in assignments) + tuple(value for _, value in predicates),
        )
        return cursor.rowcount

    def _require_columns(self, logical_id: str, operation: str, values: Mapping[str, Any]) -> None:
        allowed = _MUTATION_COLUMNS.get(self.__command_kind, {}).get(
            (logical_id, operation), frozenset()
        )
        requested = frozenset(values)
        if not requested or not requested <= allowed:
            raise StatementRejected(
                f"{self.__command_kind} cannot {operation} columns "
                f"{sorted(requested - allowed)} on {logical_id}"
            )
        if operation == "insert":
            required = REQUIRED_FIELDS.get(logical_id, frozenset())
            if not required <= requested:
                raise StatementRejected(
                    f"{logical_id} insert omits required fields {sorted(required - requested)}"
                )

    @staticmethod
    def _json_value(value: Any) -> Any:
        return getattr(value, "obj", value)

    def _require_insert_bindings(self, logical_id: str, values: Mapping[str, Any]) -> None:
        references = {
            "ref_s27_id": ("planning_intents",),
            "ref_s29_id": ("planning_attempts",),
            "ref_s37_id": ("validation_results",),
            "ref_s38_id": ("daily_plan_heads",),
        }
        for field, (lock_name,) in references.items():
            referenced = values.get(field)
            if referenced is not None and referenced not in self.__locked_ids.get(
                lock_name, frozenset()
            ):
                raise GuardRequired(f"{logical_id}.{field} must bind an exact locked row")
        artifact_id = values.get("ref_s49_id")
        if artifact_id is not None and artifact_id not in self.__verified_artifacts:
            raise ArtifactIdentityRequired(
                f"{logical_id}.ref_s49_id must bind a leased and verified artifact"
            )
        if "ref_s02_id" in values and values["ref_s02_id"] != self.__receipt_id:
            raise StatementRejected(f"{logical_id}.ref_s02_id must bind the current receipt")
        if logical_id == "S39":
            parent = self._json_value(values.get("typed_payload", {})).get("parent_revision_id")
            head_id = values.get("ref_s38_id")
            expected = self.__head_bundles.get(head_id) if isinstance(head_id, UUID) else None
            if expected is None or parent != str(expected):
                raise GuardRequired("S39 must name the locked head revision as its parent")
        if logical_id == "S41":
            if values.get("ref_s39_id") not in self.__inserted_ids.get("S39", set()):
                raise GuardRequired("S41 must bind the S39 inserted by this command")
            if values.get("ref_s40_id") not in self.__inserted_ids.get("S40", set()):
                raise GuardRequired("S41 must bind the S40 inserted by this command")
        if logical_id == "S42":
            if self.__command_kind == "CommitBundle":
                if values.get("ref_s40_id") not in self.__inserted_ids.get("S40", set()):
                    raise GuardRequired("S42 must bind the S40 inserted by this command")
            else:
                _cursor(self).execute(
                    "SELECT 1 FROM kineticloop.bundle_prescription_members member "
                    "JOIN kineticloop.daily_plan_heads head "
                    "ON head.subject_id=member.subject_id "
                    "AND head.current_bundle_revision_id=member.ref_s39_id "
                    "WHERE member.subject_id=%s AND member.ref_s40_id=%s "
                    "AND head.id=ANY(%s)",
                    (
                        self.__subject_id,
                        values.get("ref_s40_id"),
                        list(self.__locked_ids.get("daily_plan_heads", frozenset())),
                    ),
                )
                if _cursor(self).fetchone() is None:
                    raise GuardRequired(
                        "reauthorization must bind a prescription on the locked current head"
                    )
            if values.get("registry_revision_at_issue") != self.__registry_revision:
                raise GuardRequired("S42 must bind the acquired registry revision")
            certificate = self._json_value(values.get("validity_certificate", {}))
            required = {"authorization_epoch", "method_version", "closure_digest", "dependencies"}
            if not isinstance(certificate, dict) or not required <= set(certificate):
                raise StatementRejected("S42 validity_certificate is incomplete")
            dependencies = {UUID(item) for item in certificate["dependencies"]}
            if dependencies != set(self.__verified_artifacts):
                raise ArtifactIdentityRequired(
                    "S42 certificate dependencies must equal the verified lease closure"
                )
            expected_digest = hashlib.sha256(
                ",".join(sorted(map(str, dependencies))).encode()
            ).hexdigest()
            if certificate["closure_digest"] != expected_digest:
                raise ArtifactIdentityRequired("S42 certificate closure digest mismatch")
            if values.get("artifact_dependency_closure_hash") != expected_digest:
                raise ArtifactIdentityRequired("S42 closure hash mismatch")

    def _require_update_bindings(
        self,
        logical_id: str,
        values: Mapping[str, Any],
        predicates: Mapping[str, Any],
    ) -> None:
        if logical_id == "S38" and "current_bundle_revision_id" in values:
            if values["current_bundle_revision_id"] not in self.__inserted_ids.get("S39", set()):
                raise GuardRequired("S38 head must point to this command's inserted S39")
        if logical_id == "S27":
            if "result_bundle_revision_id" in values and values[
                "result_bundle_revision_id"
            ] not in self.__inserted_ids.get("S39", set()):
                raise GuardRequired("S27 result bundle must bind this command's inserted S39")
            if "result_authorization_id" in values and values[
                "result_authorization_id"
            ] not in self.__inserted_ids.get("S42", set()):
                raise GuardRequired(
                    "S27 result authorization must bind this command's inserted S42"
                )
        if logical_id == "S01" and "execution_basis_event_id" in values:
            if values["execution_basis_event_id"] != self.__event_id:
                raise GuardRequired("S01 execution basis must bind the current S03 event")

    def insert_authorization_artifact_closure(
        self, authorization_id: UUID, artifact_ids: Sequence[UUID]
    ) -> None:
        ids = frozenset(artifact_ids)
        if self.__command_kind not in {"CommitBundle", "Reauthorize"}:
            raise StatementRejected("authorization closure is not available to this owner")
        if authorization_id not in self.__inserted_ids.get("S42", set()):
            raise GuardRequired("closure must bind an S42 inserted by this command")
        if ids != self.__verified_artifacts:
            raise ArtifactIdentityRequired("materialized closure must equal verified artifacts")
        for artifact_id in sorted(ids, key=str):
            _cursor(self).execute(
                "INSERT INTO kineticloop.authorization_artifact_closure"
                "(subject_id,authorization_id,artifact_id,artifact_revision,valid_from,valid_until) "
                "SELECT %s,%s,id,GREATEST(%s,1),valid_from,valid_until "
                "FROM kineticloop.safety_artifacts "
                "WHERE id=%s",
                (
                    self.__subject_id,
                    authorization_id,
                    self.__registry_revision,
                    artifact_id,
                ),
            )
            if _cursor(self).rowcount != 1:
                raise ArtifactIdentityRequired("closure artifact disappeared")
        self.__closure_authorizations.add(authorization_id)

    def validate_completion(self) -> None:
        if self.__command_kind in {"CommitBundle", "Reauthorize"}:
            inserted = self.__inserted_ids.get("S42", set())
            if inserted != self.__closure_authorizations:
                raise ArtifactIdentityRequired(
                    "every inserted authorization requires its exact materialized closure"
                )

    def _require_locked_identity(self, logical_id: str, predicates: Mapping[str, Any]) -> None:
        lock_name = {
            "S27": "planning_intents",
            "S31": "call_reservations",
            "S38": "daily_plan_heads",
            "S44": "workout_sessions",
            "S15": "factset_revisions",
            "S23": "manifest_builds",
            "S29": "planning_attempts",
            "S37": "validation_results",
        }.get(logical_id)
        if lock_name is None:
            return
        object_id = predicates.get("id")
        if object_id is None or object_id not in self.__locked_ids.get(lock_name, frozenset()):
            raise GuardRequired(f"{logical_id} mutation requires its exact row lock before S02")

    def _require_subject_predicate(
        self, logical_id: str, values: Mapping[str, Any], label: str
    ) -> None:
        if logical_id in {"S49", "S50", "S51"}:
            return
        if self.__subject_id is None or values.get("subject_id") != self.__subject_id:
            raise StatementRejected(f"{label} must bind the authenticated transaction subject")

    def relation_locks(self) -> frozenset[str]:
        cursor = _cursor(self)
        cursor.execute(
            "SELECT c.relname FROM pg_locks l JOIN pg_class c ON c.oid=l.relation "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE l.pid=pg_backend_pid() "
            "AND n.nspname='kineticloop' AND l.granted"
        )
        return frozenset(str(row[0]) for row in cursor.fetchall())


class RepositoryTransaction:
    """One command-owned transaction with monotonic lock acquisition."""

    __slots__ = (
        "__weakref__",
        "_last_aggregate_rank",
        "_last_stage",
        "_leased_artifacts",
        "_head_bundles",
        "_locked_ids",
        "_registry",
        "_registry_revision",
        "_subject",
        "_trace",
        "_verified_artifacts",
        "_verified_fences",
        "command_kind",
        "spec",
        "subject_id",
    )

    def __init__(self, cursor: Cursor[Any], command_kind: str, subject_id: UUID | None):
        try:
            self.spec = TRANSACTION_OWNER_MATRIX[command_kind]
        except KeyError as error:
            raise ValueError(f"unknown command owner surface: {command_kind}") from error
        _CURSORS[self] = cursor
        self.command_kind = command_kind
        self.subject_id = subject_id
        self._last_stage = 0
        self._registry = False
        self._subject = False
        self._trace: list[tuple[LockStage, str]] = []
        self._last_aggregate_rank = -1
        self._locked_ids: dict[str, set[UUID]] = {}
        self._leased_artifacts: frozenset[UUID] = frozenset()
        self._verified_artifacts: set[UUID] = set()
        self._verified_fences: dict[UUID, tuple[int, str]] = {}
        self._registry_revision: int | None = None
        self._head_bundles: dict[UUID, UUID | None] = {}

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
        _cursor(self).execute(
            f"SELECT kineticloop.{routine}(%s,%s,%s,%s)",
            (self.subject_id, list(artifact_ids), minimum_revision, lock_timeout_ms),
        )
        row = _cursor(self).fetchone()
        if row is None:
            raise GuardRequired("registry lease was not acquired")
        # The merged guard routine acquires S51 then S01 in the same transaction.
        self._registry = True
        self._registry_revision = int(row[0])
        self._leased_artifacts = frozenset(artifact_ids)
        self._subject = True
        self._last_stage = LockStage.SUBJECT
        self._trace.extend(((LockStage.REGISTRY, "S51"), (LockStage.SUBJECT, "S01")))
        return self._registry_revision

    def lock_subject(self) -> None:
        if not self.spec.subject_guard_required:
            raise GuardRequired(f"{self.command_kind} has no S01 coordination entry")
        if self.subject_id is None:
            raise GuardRequired("subject guard requires a subject")
        self._advance(LockStage.SUBJECT)
        _cursor(self).execute(
            "SELECT subject_id FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
            (self.subject_id,),
        )
        if _cursor(self).fetchone() is None:
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
        if "S30" not in self.spec.mutation_surfaces:
            raise GuardRequired(f"{self.command_kind} cannot lock inapplicable S30")
        self._advance(LockStage.QUOTA)
        if not keys:
            raise GuardRequired("quota lock requires at least one exact key")
        for quota_kind, window_start, window_end in sorted(set(keys)):
            _cursor(self).execute(
                "SELECT id FROM kineticloop.planning_quota_buckets "
                "WHERE subject_id=%s AND quota_kind=%s AND window_start=%s "
                "AND window_end=%s ORDER BY id FOR UPDATE",
                (self.subject_id, quota_kind, window_start, window_end),
            )
            rows = _cursor(self).fetchall()
            if not rows:
                raise GuardRequired("quota bucket does not exist")
            self._trace.append((LockStage.QUOTA, f"S30:{quota_kind}:{window_start}:{window_end}"))
            self._locked_ids.setdefault("planning_quota_buckets", set()).update(
                UUID(str(row[0])) for row in rows
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
        if "S38" not in self.spec.mutation_surfaces:
            raise GuardRequired(f"{self.command_kind} cannot lock inapplicable S38")
        self._advance(LockStage.DAILY_HEAD)
        _cursor(self).execute(
            "SELECT id,current_bundle_revision_id FROM kineticloop.daily_plan_heads "
            "WHERE subject_id=%s AND local_date=%s FOR UPDATE",
            (self.subject_id, local_date),
        )
        rows = _cursor(self).fetchall()
        if not rows:
            raise GuardRequired("daily head does not exist")
        self._trace.append((LockStage.DAILY_HEAD, f"S38:{local_date}"))
        self._locked_ids.setdefault("daily_plan_heads", set()).update(
            UUID(str(row[0])) for row in rows
        )
        self._head_bundles.update(
            {UUID(str(row[0])): UUID(str(row[1])) if row[1] is not None else None for row in rows}
        )

    def lock_execution(self, session_ids: Sequence[UUID]) -> None:
        self._require_subject()
        self._advance(LockStage.EXECUTION)
        self._lock_ids("workout_sessions", session_ids)

    def lock_receipt(self, command_kind: str, client_key: str, actor_scope: str) -> None:
        self._require_receipt_guard()
        if command_kind != self.command_kind:
            raise GuardRequired("receipt command kind must match its repository owner")
        self._advance(LockStage.RECEIPT)
        if self.spec.boundary is Boundary.T1:
            key = f"{self.subject_id}:{actor_scope}:{command_kind}:{client_key}"
            _cursor(self).execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))
        _cursor(self).execute(
            "SELECT id FROM kineticloop.command_receipts WHERE subject_id=%s "
            "AND command_kind=%s AND client_key=%s AND actor_scope=%s FOR UPDATE",
            (self.subject_id, command_kind, client_key, actor_scope),
        )
        _cursor(self).fetchall()
        self._trace.append((LockStage.RECEIPT, f"S02:{actor_scope}:{command_kind}:{client_key}"))

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
        ids = tuple(sorted(set(object_ids), key=str))
        if not ids:
            raise GuardRequired(f"{table} lock requires at least one exact row")
        logical = {
            "planning_intents": "S27",
            "call_reservations": "S31",
            "workout_sessions": "S44",
            "factset_revisions": "S15",
            "manifest_builds": "S23",
            "planning_attempts": "S29",
            "validation_results": "S37",
        }[table]
        if logical not in self.spec.mutation_surfaces and not (
            self.command_kind in {"CommitBundle", "Reauthorize"} and logical == "S37"
        ):
            raise GuardRequired(f"{self.command_kind} cannot lock inapplicable {logical}")
        for object_id in ids:
            _cursor(self).execute(
                f"SELECT id FROM kineticloop.{table} WHERE subject_id=%s AND id=%s FOR UPDATE",
                (self.subject_id, object_id),
            )
            if _cursor(self).fetchone() is None:
                raise GuardRequired(f"{table} row does not exist")
            stage = {
                "planning_intents": LockStage.INTENT,
                "call_reservations": LockStage.RESERVATION,
                "workout_sessions": LockStage.EXECUTION,
            }.get(table, LockStage.AGGREGATE)
            self._trace.append((stage, f"{logical}:{object_id}"))
            self._locked_ids.setdefault(table, set()).add(object_id)

    def require_artifact(self, identity: ArtifactIdentity) -> None:
        if not self._registry:
            raise GuardRequired("artifact consumption requires the shared registry lease")
        _cursor(self).execute(
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
        if _cursor(self).fetchone() is None:
            raise ArtifactIdentityRequired("exact registered artifact identity is required")
        if identity.artifact_id not in self._leased_artifacts:
            raise ArtifactIdentityRequired("artifact identity was not included in the lease")
        self._verified_artifacts.add(identity.artifact_id)

    def require_current_fence(
        self,
        intent_id: UUID,
        *,
        owner_id: str,
        fence: int,
        expected_status: str = "RUNNING",
    ) -> None:
        self._require_subject()
        if intent_id not in self._locked_ids.get("planning_intents", set()):
            raise GuardRequired("exact intent must be locked before checking fence")
        _cursor(self).execute(
            "SELECT 1 FROM kineticloop.planning_intents WHERE subject_id=%s AND id=%s "
            "AND lease_owner=%s AND fence_token=%s AND status=%s "
            "AND lease_expires_at > clock_timestamp()",
            (self.subject_id, intent_id, owner_id, fence, expected_status),
        )
        if _cursor(self).fetchone() is None:
            raise FenceLost("stale owner/fence cannot commit")
        self._verified_fences[intent_id] = (fence, "LIVE")

    def require_lease_acquisition_basis(
        self, intent_id: UUID, *, expected_owner_id: str, expected_fence: int
    ) -> None:
        """Prove the exact prior lease state used by an AcquireLease CAS."""

        self._require_subject()
        if self.command_kind != "AcquireLease":
            raise GuardRequired("lease acquisition basis is exclusive to AcquireLease")
        if intent_id not in self._locked_ids.get("planning_intents", set()):
            raise GuardRequired("exact intent must be locked before lease acquisition")
        _cursor(self).execute(
            "SELECT 1 FROM kineticloop.planning_intents WHERE subject_id=%s AND id=%s "
            "AND lease_owner=%s AND fence_token=%s",
            (self.subject_id, intent_id, expected_owner_id, expected_fence),
        )
        if _cursor(self).fetchone() is None:
            raise FenceLost("lease acquisition compare-and-swap basis was lost")
        self._verified_fences[intent_id] = (expected_fence, "CAS")

    def require_reaper_basis(self, intent_id: UUID, *, owner_id: str, fence: int) -> None:
        """Prove the exact expired/deadline basis used by ReapIntent."""

        self._require_subject()
        if self.command_kind != "ReapIntent":
            raise GuardRequired("expired lease basis is exclusive to ReapIntent")
        if intent_id not in self._locked_ids.get("planning_intents", set()):
            raise GuardRequired("exact intent must be locked before reaping")
        _cursor(self).execute(
            "SELECT 1 FROM kineticloop.planning_intents WHERE subject_id=%s AND id=%s "
            "AND lease_owner=%s AND fence_token=%s "
            "AND (lease_expires_at <= clock_timestamp() OR deadline <= clock_timestamp())",
            (self.subject_id, intent_id, owner_id, fence),
        )
        if _cursor(self).fetchone() is None:
            raise FenceLost("intent is not owned by the expected expired lease")
        self._verified_fences[intent_id] = (fence, "EXPIRED")

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
        if reservation_id not in self._locked_ids.get("call_reservations", set()):
            raise GuardRequired("exact reservation must be locked before dispatch transition")

        def transition(session: RestrictedSqlSession) -> Mapping[str, Any]:
            _cursor(self).execute(
                "SELECT status, dispatch_fence, typed_payload, ref_s27_id "
                "FROM kineticloop.call_reservations "
                "WHERE subject_id=%s AND id=%s",
                (self.subject_id, reservation_id),
            )
            row = _cursor(self).fetchone()
            if (
                row is None
                or int(row[1] or 0) != fence
                or row[3] not in self._verified_fences
                or self._verified_fences[row[3]] != (fence, "LIVE")
            ):
                raise DispatchNotPermitted("reservation or fence mismatch")
            if row[0] != "RESERVED":
                raise DispatchNotPermitted("only RESERVED may become DISPATCH_INTENT")
            payload = dict(row[2] or {})
            payload["permit_key"] = permit_key
            if (
                session.update(
                    "S31",
                    {"status": "DISPATCH_INTENT", "typed_payload": Jsonb(payload)},
                    {"subject_id": self.subject_id, "id": reservation_id},
                )
                != 1
            ):
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
        self._require_command_locks(aggregate_locks or {})
        self.lock_receipt(self.command_kind, client_key, actor_scope)
        _cursor(self).execute(
            "SELECT request_hash,status,typed_payload FROM kineticloop.command_receipts "
            "WHERE subject_id=%s AND actor_scope=%s AND command_kind=%s AND client_key=%s",
            (self.subject_id, actor_scope, self.command_kind, client_key),
        )
        prior = _cursor(self).fetchone()
        if prior is not None:
            if prior[0] != request_hash:
                raise IdempotencyConflict("command key request hash mismatch")
            if prior[1] != "SUCCEEDED" or "outcome" not in prior[2]:
                raise IdempotencyConflict("command key has no durable successful outcome")
            return dict(prior[2]["outcome"]), True
        self._require_fence_guard()
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
        _cursor(self).execute(
            "INSERT INTO kineticloop.command_receipts"
            "(id,subject_id,status,command_kind,client_key,actor_scope,request_hash) "
            "VALUES (%s,%s,'IN_PROGRESS',%s,%s,%s,%s)",
            (receipt_id, self.subject_id, self.command_kind, client_key, actor_scope, request_hash),
        )
        _cursor(self).execute(
            "INSERT INTO kineticloop.domain_events"
            "(id,subject_id,aggregate_type,aggregate_identity,event_type,aggregate_revision,ref_s02_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                event.event_id,
                self.subject_id,
                event.aggregate_type,
                event.aggregate_identity,
                event.event_type,
                event.aggregate_revision,
                receipt_id,
            ),
        )
        _cursor(self).execute(
            "INSERT INTO kineticloop.outbox_deliveries"
            "(id,subject_id,destination,delivery_status,attempt_count,ref_s03_id) "
            "VALUES (%s,%s,%s,'PENDING',0,%s)",
            (event.outbox_id, self.subject_id, event.destination, event.event_id),
        )
        session = RestrictedSqlSession(
            _cursor(self),
            self.spec.mutation_surfaces,
            self.subject_id,
            command_kind=self.command_kind,
            locked_ids={table: frozenset(ids) for table, ids in self._locked_ids.items()},
            verified_artifacts=frozenset(self._verified_artifacts),
            receipt_id=receipt_id,
            event_id=event.event_id,
            registry_revision=self._registry_revision,
            head_bundles=self._head_bundles,
        )
        outcome = dict(mutation(session))
        session.validate_completion()
        _cursor(self).execute(
            "UPDATE kineticloop.command_receipts SET status='SUCCEEDED',typed_payload=%s "
            "WHERE id=%s AND subject_id=%s",
            (Jsonb({"outcome": outcome}), receipt_id, self.subject_id),
        )
        return outcome, False

    def _require_command_locks(self, aggregate_locks: Mapping[str, Sequence[UUID]]) -> None:
        required = {
            "S30": "planning_quota_buckets",
            "S27": "planning_intents",
            "S31": "call_reservations",
            "S38": "daily_plan_heads",
            "S44": "workout_sessions",
        }
        for logical_id, table in required.items():
            if logical_id in self.spec.mutation_surfaces and not self._locked_ids.get(table):
                raise GuardRequired(
                    f"{self.command_kind} requires an applicable {logical_id} row lock"
                )
        required_aggregates = {
            "PublishManifest": {"manifest_builds"},
            "SealFactset": {"factset_revisions"},
            "CommitBundle": {"planning_attempts", "validation_results"},
            "Reauthorize": {"planning_attempts", "validation_results"},
        }.get(self.command_kind, set())
        if not required_aggregates <= set(aggregate_locks):
            raise GuardRequired(
                f"{self.command_kind} requires aggregate locks {sorted(required_aggregates)}"
            )

    def _require_fence_guard(self) -> None:
        mode = {
            "AcquireLease": "CAS",
            "RenewLease": "LIVE",
            "ReserveCall": "LIVE",
            "PermitDispatch": "LIVE",
            "CommitBundle": "LIVE",
            "Reauthorize": "LIVE",
            "ReapIntent": "EXPIRED",
        }.get(self.command_kind)
        if mode is not None:
            locked_intents = self._locked_ids.get("planning_intents", set())
            if not locked_intents or any(
                self._verified_fences.get(intent_id, (None, None))[1] != mode
                for intent_id in locked_intents
            ):
                raise GuardRequired(
                    f"{self.command_kind} requires {mode} fence validation for every intent"
                )

    def locked_identity(self, table: str, object_id: UUID) -> bool:
        """Report whether the exact applicable row guard is held."""

        return object_id in self._locked_ids.get(table, set())

    def finish(self) -> None:
        if self.spec.registry_required and not self._registry:
            raise GuardRequired(f"{self.command_kind} requires a shared S51 registry lease")
        if self.spec.subject_guard_required and not self._subject:
            raise GuardRequired(f"{self.command_kind} requires the S01 subject guard")
        if self._registry and self._verified_artifacts != set(self._leased_artifacts):
            raise ArtifactIdentityRequired(
                "every leased artifact requires exact kind/identity/version/hash validation"
            )


def execute_command(
    connection: Connection[Any],
    command_kind: str,
    subject_id: UUID | None,
    operation: Callable[[RepositoryTransaction], _T],
) -> _T:
    """Own the outer transaction and commit only after all owner guards pass."""

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise TransactionStateError("repository command requires an idle connection")
    specification = TRANSACTION_OWNER_MATRIX.get(command_kind)
    if specification is None:
        raise ValueError(f"unknown command owner surface: {command_kind}")
    if specification.boundary in {Boundary.PREPARATION, Boundary.BUILD, Boundary.EXTERNAL}:
        raise GuardRequired(f"{command_kind} must use its isolated non-coordination entrypoint")
    with connection.transaction():
        transaction = RepositoryTransaction(connection.cursor(), command_kind, subject_id)
        result = operation(transaction)
        transaction.finish()
        return result


def replay_outcome(
    connection: Connection[Any],
    command_kind: str,
    subject_id: UUID | None,
    *,
    actor_scope: str,
    client_key: str,
    request_hash: str,
) -> Mapping[str, Any]:
    """Return a durable historical result without re-running current eligibility guards."""

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise TransactionStateError("repository replay requires an idle connection")
    specification = TRANSACTION_OWNER_MATRIX.get(command_kind)
    if specification is None or specification.boundary in {
        Boundary.PREPARATION,
        Boundary.BUILD,
        Boundary.EXTERNAL,
    }:
        raise GuardRequired("command has no durable coordination receipt")
    with connection.transaction():
        transaction = RepositoryTransaction(connection.cursor(), command_kind, subject_id)
        if specification.subject_guard_required:
            transaction.lock_subject()
        transaction.lock_receipt(command_kind, client_key, actor_scope)
        _cursor(transaction).execute(
            "SELECT request_hash,status,typed_payload FROM kineticloop.command_receipts "
            "WHERE subject_id=%s AND actor_scope=%s AND command_kind=%s AND client_key=%s",
            (subject_id, actor_scope, command_kind, client_key),
        )
        prior = _cursor(transaction).fetchone()
        if prior is None:
            raise ReplayNotFound("durable command outcome does not exist")
        if prior[0] != request_hash:
            raise IdempotencyConflict("command key request hash mismatch")
        if prior[1] != "SUCCEEDED" or "outcome" not in prior[2]:
            raise ReplayNotFound("durable successful outcome does not exist")
        return dict(prior[2]["outcome"])


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
                connection.cursor(),
                specification.mutation_surfaces,
                subject_id,
                command_kind=command_kind,
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
            "SELECT id FROM kineticloop.factset_revisions WHERE subject_id=%s AND id=%s FOR UPDATE",
            (subject_id, build_id),
        )
        if cursor.fetchone() is None:
            raise GuardRequired("factset build does not exist")
        return operation(
            RestrictedSqlSession(
                cursor,
                specification.mutation_surfaces,
                subject_id,
                command_kind=command_kind,
                locked_ids={"factset_revisions": frozenset({build_id})},
            )
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
