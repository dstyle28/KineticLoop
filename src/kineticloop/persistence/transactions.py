"""Fail-closed repository transaction interfaces for frozen T1--T8 boundaries.

The module deliberately owns no business decisions.  It supplies the small set of
mechanical primitives every command repository needs: one top-level transaction,
the frozen lock order, registry/subject guards, exact artifact and fence checks,
durable idempotent outcomes, atomic event/outbox writes, and isolated outbox claims.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Any, TypeVar
from uuid import UUID
from weakref import WeakKeyDictionary

from psycopg import Connection, Cursor, sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.persistence.metadata import REQUIRED_FIELDS
from kineticloop.persistence.schema_topology import LOGICAL_RELATIONS

_T = TypeVar("_T")

_LOGICAL_TABLES = {row.logical_id: row.table_name for row in LOGICAL_RELATIONS}
_CURSORS: WeakKeyDictionary[object, Cursor[Any]] = WeakKeyDictionary()


def evidence_source_identity_key(values: Mapping[str, Any]) -> str:
    """Canonical T1 identity matching the applicable PostgreSQL unique index."""

    revision = values.get("source_revision")
    observation = values.get("observation_key")
    if (revision is None) == (observation is None):
        raise GuardRequired("T1 requires exactly one reliable source revision identity")
    if revision is not None:
        revision_fields = (
            "subject_id",
            "source_connection_identity",
            "source_object_type",
            "source_object_identity",
        )
        return ":".join(str(values.get(field)) for field in revision_fields) + f":{revision}"
    observation_fields = ("subject_id", "source_connection_identity")
    return ":".join(str(values.get(field)) for field in observation_fields) + f":{observation}"


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
            "EvidenceAssociationService", Boundary.T2_IN, ("S12", "S43", "S01", "S02", "S03", "S04")
        ),
        "DecideAdmission": OwnerSpec(
            "AdmissionService", Boundary.T2_IN, ("S13", "S43", "S01", "S02", "S03", "S04")
        ),
        "AcceptFactRevision": OwnerSpec(
            "CanonicalFactService", Boundary.T2_IN, ("S14", "S43", "S01", "S02", "S03", "S04")
        ),
        "ApplyControl": OwnerSpec(
            "ControlService", Boundary.T2_IN, ("S17", "S18", "S43", "S01", "S02", "S03", "S04")
        ),
        "ClearControl": OwnerSpec(
            "ControlService", Boundary.T2_IN, ("S17", "S18", "S43", "S01", "S02", "S03", "S04")
        ),
        "ApproveChange": OwnerSpec(
            "ProgramReviewService", Boundary.T2_IN, ("S08", "S43", "S01", "S02", "S03", "S04")
        ),
        "ActivateApprovedProgram": OwnerSpec(
            "ProgramService", Boundary.T2_IN, ("S06", "S43", "S01", "S02", "S03", "S04")
        ),
        "RecordActualExecution": OwnerSpec(
            "CanonicalFactService", Boundary.T2_IN, ("S14", "S43", "S01", "S02", "S03", "S04")
        ),
        "CompleteReportedWorkout": OwnerSpec(
            "ExecutionService", Boundary.T2_IN, ("S44", "S14", "S43", "S01", "S02", "S03", "S04")
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
            ("S51", "S01", "S27", "S38", "S42", "S29", "S02", "S03", "S04"),
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
            ("S51", "S01", "S38", "S44", "S02", "S03", "S04"),
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
                    "observation_key",
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
        "PermitDispatch": {
            ("S31", "update"): frozenset({"status", "settlement_revision", "typed_payload"})
        },
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
                    "parent_revision_id",
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
                    "content_hash",
                    "typed_payload",
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
        "WriteCandidate": {
            ("S15", "update"): frozenset({"member_revision"}),
        },
        "CompleteFactset": {
            ("S15", "update"): frozenset(
                {
                    "status",
                    "member_revision",
                    "completed_member_revision",
                    "membership_digest",
                    "typed_payload",
                }
            )
        },
    }
)


def _fields(names: str) -> frozenset[str]:
    return frozenset(names.split())


# Explicit append capabilities.  These are intentionally literals: a future schema
# column must not silently become writable.  Database-generated known/recorded time
# and revision provenance are never callback supplied.
_INSERT_COLUMNS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "S08": _fields(
            "id subject_id approved_scope content_hash content_schema_version effective_at expires_at hash_scheme_version ref_s02_id ref_s05_id ref_s06_id ref_s07_id status typed_payload"
        ),
        "S09": _fields(
            "id subject_id source_connection_identity source_object_type source_object_identity source_revision observation_key trust_class source_class command_authority content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S10": _fields(
            "id subject_id assertion_family_identity predicate unit value_state ref_s09_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S12": _fields(
            "id subject_id association_family_identity association_state ref_s09_id ref_s11_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S13": _fields(
            "id subject_id action_scope decision ref_s05_id ref_s09_id ref_s10_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S14": _fields(
            "id subject_id stable_fact_identity fact_kind fact_revision ref_s10_id ref_s11_id ref_s13_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S15": _fields(
            "id subject_id factset_identity storage_mode membership_digest delta_depth member_revision completed_member_revision ref_s12_id ref_s13_id ref_s20_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S16": _fields(
            "id subject_id logical_member_key member_kind member_operation action_scope ref_s12_id ref_s13_id ref_s14_id ref_s15_id ref_s20_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S17": _fields(
            "id subject_id control_identity control_revision scope review_due_at ref_s02_id ref_s05_id ref_s09_id ref_s13_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S18": _fields(
            "id subject_id control_identity execution_scope head_revision ref_s17_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S21": _fields(
            "id subject_id projection_kind input_basis_hash computed_at valid_until content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S22": _fields(
            "id subject_id dependency_kind dependency_semantic_key collection_signature ref_s05_id ref_s06_id ref_s14_id ref_s15_id ref_s19_id ref_s20_id ref_s21_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S23": _fields(
            "id subject_id build_identity captured_epoch captured_input_frontier error_code ref_s05_id ref_s06_id ref_s15_id ref_s21_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S24": _fields(
            "id subject_id generation manifest_hash input_frontier_hash captured_epoch dependency_closure_hash valid_until registry_revision_at_publish registry_state_id ref_s05_id ref_s06_id ref_s15_id ref_s19_id ref_s20_id ref_s23_id ref_s49_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S25": _fields(
            "id subject_id projection_role unavailable_reason validated_basis_hash ref_s21_id ref_s24_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S27": _fields(
            "id subject_id root_request_identity purpose local_date deadline current_request_revision_id current_attempt_id lease_owner lease_expires_at fence_token stale_restart_count result_bundle_revision_id result_authorization_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S28": _fields(
            "id subject_id request_revision constraint_fingerprint normalization_version ref_s02_id ref_s27_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S29": _fields(
            "id subject_id attempt_no snapshot_id captured_epoch fence_token started_at completed_at failure_code ref_s24_id ref_s27_id ref_s28_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S31": _fields(
            "id subject_id operation_slot provider_request_identity config_fingerprint dispatch_owner dispatch_fence settlement_revision ref_s27_id ref_s29_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S32": _fields(
            "id subject_id event_type transition_revision receipt_identity occurred_at ref_s31_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S33": _fields(
            "id subject_id operation_slot tool_name tool_version arguments_hash result_hash trust_class ref_s26_id ref_s29_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S34": _fields(
            "id subject_id proposal_family_identity proposal_kind producer_artifact demand_feature_id ref_s26_id ref_s29_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S35": _fields(
            "id subject_id method_version feature_hash basis_hash ref_s34_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S36": _fields(
            "id subject_id action_type action_parameters_hash resolver_version query_basis_hash resolution_expires_at ref_s05_id ref_s09_id ref_s12_id ref_s14_id ref_s24_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S37": _fields(
            "id subject_id result validator_artifact valid_until ref_s03_id ref_s05_id ref_s24_id ref_s28_id ref_s29_id ref_s34_id ref_s35_id ref_s36_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S39": _fields(
            "id subject_id local_date revision_no generation_mode parent_revision_id ref_s02_id ref_s24_id ref_s27_id ref_s29_id ref_s37_id ref_s38_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S40": _fields(
            "id subject_id prescription_identity prescription_kind prescription_revision ref_s34_id ref_s49_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S41": _fields(
            "id subject_id member_kind session_slot member_order ref_s39_id ref_s40_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S42": _fields(
            "id subject_id bound_content_hash scope issuance_reason artifact_dependency_closure_hash registry_revision_at_issue valid_from valid_until validity_certificate ref_s02_id ref_s05_id ref_s24_id ref_s36_id ref_s37_id ref_s40_id ref_s49_id registry_state_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S43": _fields(
            "id subject_id event_kind scope causation_key invalidated_epoch ref_s02_id ref_s13_id ref_s17_id ref_s42_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S45": _fields(
            "id subject_id binding_kind binding_revision accepted_at execution_scope ref_s02_id ref_s40_id ref_s42_id ref_s44_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S49": _fields(
            "id artifact_kind artifact_identity artifact_version validity_kind valid_from valid_until timeless_approval_policy timeless_approval_reason ref_s05_id ref_s19_id ref_s48_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
        "S50": _fields(
            "id management_command_identity reason_code revocation_payload_hash registry_revision registry_state_id ref_s49_id content_hash content_schema_version effective_at hash_scheme_version status typed_payload"
        ),
    }
)


# Every public owner has an explicit logical-table/operation capability.  Existing
# entries above intentionally remain narrower where multiple commands share a table.
_COMMAND_OPERATIONS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "ReceiveEvidence": {"insert": ("S09",)},
    "RecordCandidate": {"insert": ("S10",)},
    "DecideAssociation": {"insert": ("S12", "S43"), "update": ("S01",)},
    "DecideAdmission": {"insert": ("S13", "S43"), "update": ("S01",)},
    "AcceptFactRevision": {"insert": ("S14", "S43"), "update": ("S01",)},
    "ApplyControl": {"insert": ("S17", "S18", "S43"), "update": ("S01", "S18")},
    "ClearControl": {"insert": ("S17", "S18", "S43"), "update": ("S01", "S18")},
    "ApproveChange": {"insert": ("S08", "S43"), "update": ("S01",)},
    "ActivateApprovedProgram": {"insert": ("S43",), "update": ("S01",)},
    "RecordActualExecution": {"insert": ("S14", "S43"), "update": ("S01",)},
    "CompleteReportedWorkout": {"insert": ("S14", "S43"), "update": ("S01", "S44")},
    "BeginBuild": {"insert": ("S15",)},
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
    "AcquireLease": {"update": ("S27",)},
    "RenewLease": {"update": ("S27",)},
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
    "ContinueSession": {"update": ("S44",)},
    "SettleCall": {"insert": ("S32",), "update": ("S27", "S31")},
    "MarkUnknown": {"insert": ("S32",), "update": ("S27", "S31")},
    "ReapIntent": {"update": ("S27", "S29", "S31")},
}

_mutation_columns = {command: dict(rules) for command, rules in _MUTATION_COLUMNS.items()}
for _command, _operations in _COMMAND_OPERATIONS.items():
    _rules = _mutation_columns.setdefault(_command, {})
    for _operation, _logical_ids in _operations.items():
        for _logical_id in _logical_ids:
            if _operation == "insert":
                try:
                    columns = _INSERT_COLUMNS[_logical_id]
                except KeyError as error:
                    raise RuntimeError(
                        f"missing explicit insert capability for {_logical_id}"
                    ) from error
                _rules.setdefault((_logical_id, _operation), columns)

_UPDATE_COLUMNS: Mapping[str, Mapping[str, frozenset[str]]] = {
    "ApplyControl": {"S18": frozenset({"status", "head_revision", "ref_s17_id", "typed_payload"})},
    "ClearControl": {"S18": frozenset({"status", "head_revision", "ref_s17_id", "typed_payload"})},
    "CompleteReportedWorkout": {
        "S44": frozenset(
            {"lifecycle", "execution_revision", "completed_at", "ref_s14_id", "typed_payload"}
        )
    },
    "SealFactset": {"S15": frozenset({"status", "sealed_at"})},
    "RevokeArtifact": {"S51": frozenset({"registry_revision", "last_revocation_id"})},
    "BuildManifest": {
        "S23": frozenset(
            {"status", "captured_epoch", "captured_input_frontier", "error_code", "typed_payload"}
        )
    },
    "AdmitOrReviseIntent": {
        "S27": frozenset(
            {"status", "current_request_revision_id", "current_attempt_id", "typed_payload"}
        ),
        "S30": frozenset({"admitted_count", "typed_payload"}),
    },
    "CancelIntent": {
        "S27": frozenset({"status", "lease_owner", "lease_expires_at", "typed_payload"}),
        "S31": frozenset({"status", "settlement_revision", "typed_payload"}),
    },
    "AcquireLease": {
        "S27": frozenset(
            {"status", "lease_owner", "fence_token", "lease_expires_at", "typed_payload"}
        )
    },
    "RenewLease": {"S27": frozenset({"lease_expires_at", "typed_payload"})},
    "ReserveCall": {"S27": frozenset({"typed_payload"})},
    "Reauthorize": {
        "S27": frozenset({"status", "result_authorization_id", "typed_payload"}),
        "S29": frozenset({"status", "completed_at", "typed_payload"}),
    },
    "ResumeSession": {
        "S44": frozenset({"lifecycle", "execution_revision", "started_at", "typed_payload"})
    },
    "ContinueSession": {"S44": frozenset({"lifecycle", "execution_revision", "typed_payload"})},
    "MarkUnknown": {
        "S27": frozenset({"typed_payload"}),
        "S31": frozenset({"status", "settlement_revision", "typed_payload"}),
    },
    "ReapIntent": {
        "S27": frozenset(
            {"status", "lease_owner", "lease_expires_at", "stale_restart_count", "typed_payload"}
        ),
        "S29": frozenset({"status", "failure_code", "completed_at", "typed_payload"}),
        "S31": frozenset({"status", "settlement_revision", "typed_payload"}),
    },
}
for _command, _tables in _UPDATE_COLUMNS.items():
    for _logical_id, _columns in _tables.items():
        _mutation_columns[_command][(_logical_id, "update")] = _columns

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
    "SealFactset": frozenset({"current_factset_id"}),
    "PublishManifest": frozenset({"decision_generation", "current_manifest_id"}),
    "CommitBundle": frozenset({"execution_basis_event_id"}),
    "Reauthorize": frozenset({"execution_basis_event_id"}),
    "StartSession": frozenset({"execution_basis_event_id"}),
    "ResumeSession": frozenset({"execution_basis_event_id"}),
    "ContinueSession": frozenset({"execution_basis_event_id"}),
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
        "__source_identity_key",
        "__subject_id",
        "__verified_artifacts",
        "__verified_fences",
        "__closure_authorizations",
        "__coordination_context",
        "__artifact_details",
        "__inserted_values",
        "__updated_values",
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
        source_identity_key: str | None = None,
        verified_fences: Mapping[UUID, tuple[int, str, object | None]] | None = None,
        artifact_details: Mapping[UUID, Mapping[str, Any]] | None = None,
        coordination_context: Mapping[str, Any] | None = None,
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
        self.__source_identity_key = source_identity_key
        self.__verified_fences = MappingProxyType(dict(verified_fences or {}))
        self.__artifact_details = MappingProxyType(
            {key: MappingProxyType(dict(value)) for key, value in (artifact_details or {}).items()}
        )
        self.__coordination_context = MappingProxyType(dict(coordination_context or {}))
        self.__inserted_ids: dict[str, set[UUID]] = {}
        self.__inserted_values: dict[str, dict[UUID, Mapping[str, Any]]] = {}
        self.__updated_values: dict[str, list[Mapping[str, Any]]] = {}
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
        capability_values = dict(values)
        database_values = dict(values)
        if logical_id == "S39" and "parent_revision_id" in database_values:
            parent = database_values.pop("parent_revision_id")
            database_values["typed_payload"] = Jsonb(
                {"parent_revision_id": str(parent) if parent is not None else None}
            )
        items = self._items(database_values, "insert values")
        self._require_subject_predicate(logical_id, capability_values, "insert values")
        self._require_columns(logical_id, "insert", capability_values)
        self._require_insert_bindings(logical_id, capability_values)
        if logical_id == "S09":
            natural_key = evidence_source_identity_key(capability_values)
            if natural_key != self.__source_identity_key:
                raise GuardRequired("S09 must bind the advisory-locked source identity")
            cursor = _cursor(self)
            if capability_values.get("source_revision") is not None:
                cursor.execute(
                    "SELECT 1 FROM kineticloop.evidence_revisions WHERE subject_id=%s "
                    "AND source_connection_identity=%s AND source_object_type=%s "
                    "AND source_object_identity=%s AND source_revision=%s",
                    (
                        capability_values["subject_id"],
                        capability_values["source_connection_identity"],
                        capability_values["source_object_type"],
                        capability_values["source_object_identity"],
                        capability_values["source_revision"],
                    ),
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM kineticloop.evidence_revisions WHERE subject_id=%s "
                    "AND source_connection_identity=%s AND observation_key=%s "
                    "AND source_revision IS NULL",
                    (
                        capability_values["subject_id"],
                        capability_values["source_connection_identity"],
                        capability_values["observation_key"],
                    ),
                )
            if cursor.fetchone() is not None:
                raise IdempotencyConflict("source evidence identity already exists")
        statement = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
            sql.Identifier("kineticloop"),
            sql.Identifier(table),
            sql.SQL(",").join(sql.Identifier(name) for name, _ in items),
            sql.SQL(",").join(sql.Placeholder() for _ in items),
        )
        cursor = _cursor(self)
        cursor.execute(statement, tuple(value for _, value in items))
        inserted_id = capability_values.get("id")
        if cursor.rowcount == 1 and isinstance(inserted_id, UUID):
            self.__inserted_ids.setdefault(logical_id, set()).add(inserted_id)
            self.__inserted_values.setdefault(logical_id, {})[inserted_id] = MappingProxyType(
                dict(capability_values)
            )
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
        if cursor.rowcount == 1:
            self.__updated_values.setdefault(logical_id, []).append(
                MappingProxyType({**dict(predicates), **assignment_values})
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

    def authorization_certificate_dependencies(self) -> tuple[Mapping[str, Any], ...]:
        dependencies = self.__coordination_context.get("authorization_dependencies")
        if not dependencies:
            raise GuardRequired("T6 authorization basis was not prepared under lock")
        return tuple(dict(item) for item in dependencies)

    def authorization_closure_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.authorization_certificate_dependencies(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def authorization_valid_until(self) -> datetime:
        value = self.__coordination_context.get("authorization_valid_until")
        if not isinstance(value, datetime):
            raise GuardRequired("T6 authorization validity was not prepared under lock")
        return value

    def authorization_valid_from(self) -> datetime:
        value = self.__coordination_context.get("authorization_valid_from")
        if not isinstance(value, datetime):
            raise GuardRequired("T6 authorization issuance time was not prepared under lock")
        return value

    def execution_binding_accepted_at(self) -> datetime:
        value = self.__coordination_context.get("execution_accepted_at")
        if not isinstance(value, datetime):
            raise GuardRequired("T7 execution eligibility time was not prepared under lock")
        return value

    def execution_binding_revision(self) -> int:
        value = self.__coordination_context.get("execution_binding_revision")
        if not isinstance(value, int):
            raise GuardRequired("T7 execution binding revision was not prepared under lock")
        return value

    def publication_dependency_digest(self) -> str:
        value = self.__coordination_context.get("publication_dependency_digest")
        if not isinstance(value, str) or not value:
            raise GuardRequired("T3 publication dependency basis was not prepared")
        return value

    def publication_valid_until(self) -> datetime:
        value = self.__coordination_context.get("publication_valid_until")
        if not isinstance(value, datetime):
            raise GuardRequired("T3 publication validity was not prepared")
        return value

    def factset_sealed_at(self) -> datetime:
        value = self.__coordination_context.get("seal_timestamp")
        if not isinstance(value, datetime):
            raise GuardRequired("T2 seal time was not prepared under lock")
        return value

    def factset_build_payload(self) -> Mapping[str, Any]:
        payload = self.__coordination_context.get("factset_begin", {}).get("typed_payload")
        if not isinstance(payload, dict):
            raise GuardRequired("BeginBuild basis was not prepared")
        return dict(payload)

    def factset_completion_payload(self) -> Mapping[str, Any]:
        payload = self.__coordination_context.get("factset_build", {}).get("completion_payload")
        if not isinstance(payload, dict):
            raise GuardRequired("CompleteFactset basis was not prepared")
        return dict(payload)

    def _require_insert_bindings(self, logical_id: str, values: Mapping[str, Any]) -> None:
        references = {
            "ref_s27_id": ("planning_intents",),
            "ref_s29_id": ("planning_attempts",),
            "ref_s37_id": ("validation_results",),
            "ref_s38_id": ("daily_plan_heads",),
            "ref_s31_id": ("call_reservations",),
            "ref_s44_id": ("workout_sessions",),
            "ref_s15_id": ("factset_revisions",),
        }
        for field, (lock_name,) in references.items():
            referenced = values.get(field)
            # Preparation rows may cite immutable workflow inputs without taking
            # coordination locks. Transactional/build owners must bind guarded FKs.
            requires_lock = self.__command_kind not in {
                "RecordCandidate",
                "RecordToolResult",
                "RecordProposal",
                "RecordDemandFeatures",
                "ResolveEvidence",
                "RecordValidation",
            }
            if field == "ref_s29_id" and self.__command_kind not in {
                "CommitBundle",
                "Reauthorize",
            }:
                requires_lock = False
            if field == "ref_s27_id" and referenced in self.__inserted_ids.get("S27", set()):
                requires_lock = False
            if field == "ref_s31_id" and referenced in self.__inserted_ids.get("S31", set()):
                requires_lock = False
            if field == "ref_s15_id" and self.__command_kind == "PublishManifest":
                requires_lock = False
            if (
                requires_lock
                and referenced is not None
                and referenced not in self.__locked_ids.get(lock_name, frozenset())
            ):
                raise GuardRequired(f"{logical_id}.{field} must bind an exact locked row")
        artifact_id = values.get("ref_s49_id")
        if (
            artifact_id is not None
            and self.__verified_artifacts
            and artifact_id not in self.__verified_artifacts
        ):
            raise ArtifactIdentityRequired(
                f"{logical_id}.ref_s49_id must bind a leased and verified artifact"
            )
        if "ref_s02_id" in values and values["ref_s02_id"] != self.__receipt_id:
            raise StatementRejected(f"{logical_id}.ref_s02_id must bind the current receipt")
        if logical_id == "S39":
            parent = values.get("parent_revision_id")
            head_id = values.get("ref_s38_id")
            expected = self.__head_bundles.get(head_id) if isinstance(head_id, UUID) else None
            head_basis = self.__coordination_context.get("daily_heads", {}).get(head_id, {})
            if head_id not in self.__head_bundles or parent != expected:
                raise GuardRequired("S39 must name the locked head revision as its parent")
            if (
                values.get("local_date") != head_basis.get("local_date")
                or values.get("local_date")
                != self.__coordination_context.get("verified_intent_local_date")
                or values.get("revision_no") != head_basis.get("head_revision", -1) + 1
            ):
                raise GuardRequired("S39 day and revision must advance the exact locked head")
        if logical_id == "S15" and self.__command_kind == "BeginBuild":
            expected = self.__coordination_context.get("factset_begin", {})
            payload = self._json_value(values.get("typed_payload", {}))
            if (
                values.get("id") != expected.get("build_id")
                or values.get("factset_identity") != expected.get("build_identity")
                or values.get("status") != "BUILDING"
                or values.get("storage_mode") != expected.get("storage_mode")
                or values.get("member_revision") != 0
                or values.get("completed_member_revision") is not None
                or values.get("membership_digest") is not None
                or values.get("ref_s20_id") != expected.get("mapping_revision_id")
                or payload != expected.get("typed_payload")
            ):
                raise GuardRequired("BeginBuild must create the exact captured BUILDING basis")
            if values.get("ref_s24_id") != self.__coordination_context.get("current_manifest_id"):
                raise GuardRequired("S39 must bind the current locked manifest")
            if values.get("ref_s29_id") != self.__coordination_context.get("verified_attempt_id"):
                raise GuardRequired("S39 must bind the current verified attempt")
            if values.get("ref_s27_id") != self.__coordination_context.get("verified_intent_id"):
                raise GuardRequired("S39 must bind the current verified intent")
            if values.get("ref_s37_id") != self.__coordination_context.get(
                "authorization_validation_id"
            ):
                raise GuardRequired("S39 must bind the prepared validation")
            if values.get("ref_s38_id") != self.__coordination_context.get("authorization_head_id"):
                raise GuardRequired("S39 must bind the prepared daily head")
        if logical_id == "S24":
            publication_expected: Mapping[str, Any] = {
                "generation": self.__coordination_context.get("publication_generation"),
                "captured_epoch": self.__coordination_context.get("authorization_epoch"),
                "input_frontier_hash": self.__coordination_context.get("input_frontier_hash"),
                "ref_s23_id": self.__coordination_context.get("publication_build_id"),
                "ref_s05_id": self.__coordination_context.get("active_policy_bundle_id"),
                "ref_s06_id": self.__coordination_context.get("active_program_id"),
                "ref_s15_id": self.__coordination_context.get("current_factset_id"),
                "ref_s19_id": self.__coordination_context.get("publication_catalog_id"),
                "ref_s20_id": self.__coordination_context.get("publication_mapping_id"),
                "dependency_closure_hash": self.__coordination_context.get(
                    "publication_dependency_digest"
                ),
                "manifest_hash": self.__coordination_context.get("publication_manifest_hash"),
                "ref_s49_id": self.__coordination_context.get("publication_primary_artifact_id"),
                "registry_revision_at_publish": self.__registry_revision,
                "registry_state_id": 1,
            }
            if any(values.get(field) != value for field, value in publication_expected.items()):
                raise GuardRequired("S24 must bind the exact guarded T3 publication basis")
            if not isinstance(values.get("valid_until"), datetime) or values[
                "valid_until"
            ] != self.__coordination_context.get("publication_valid_until"):
                raise GuardRequired("S24 validity must equal the guarded dependency minimum")
        if logical_id == "S25":
            expected_binding = self.__coordination_context.get("publication_projection")
            if (
                values.get("ref_s24_id") not in self.__inserted_ids.get("S24", set())
                or expected_binding is None
                or values.get("ref_s21_id") != expected_binding.get("id")
                or values.get("projection_role") != expected_binding.get("role")
                or values.get("validated_basis_hash") != expected_binding.get("basis_hash")
                or values.get("unavailable_reason") is not None
            ):
                raise GuardRequired("S25 must bind the exact guarded projection role and basis")
        if logical_id == "S18" and self.__command_kind in {"ApplyControl", "ClearControl"}:
            if values.get("ref_s17_id") not in self.__inserted_ids.get("S17", set()):
                raise GuardRequired("S18 must bind the control event inserted by this command")
        if logical_id == "S28" and self.__command_kind == "AdmitOrReviseIntent":
            intent_id = values.get("ref_s27_id")
            if intent_id not in self.__inserted_ids.get("S27", set()) and intent_id not in (
                self.__locked_ids.get("planning_intents", frozenset())
            ):
                raise GuardRequired("S28 must bind this command's new or locked intent")
        if logical_id == "S29" and self.__command_kind == "AdmitOrReviseIntent":
            intent_id = values.get("ref_s27_id")
            if (
                intent_id not in self.__inserted_ids.get("S27", set())
                and intent_id not in self.__locked_ids.get("planning_intents", frozenset())
            ) or values.get("ref_s28_id") not in self.__inserted_ids.get("S28", set()):
                raise GuardRequired("S29 must bind the exact admitted intent/request")
            if values.get("captured_epoch") != self.__coordination_context.get(
                "authorization_epoch"
            ) or values.get("ref_s24_id") != self.__coordination_context.get("current_manifest_id"):
                raise GuardRequired("S29 must capture the current epoch and manifest")
        if logical_id == "S31" and self.__command_kind == "ReserveCall":
            intent_id = values.get("ref_s27_id")
            verified = (
                self.__verified_fences.get(intent_id) if isinstance(intent_id, UUID) else None
            )
            if verified is None or verified[1] != "LIVE" or values.get("ref_s29_id") != verified[2]:
                raise GuardRequired("S31 must bind the verified live intent/attempt")
        if logical_id == "S32" and self.__command_kind == "ReserveCall":
            if values.get("ref_s31_id") not in self.__inserted_ids.get("S31", set()):
                raise GuardRequired("ReserveCall S32 must bind its same-command S31")
        if logical_id == "S32" and self.__command_kind in {"SettleCall", "MarkUnknown"}:
            basis = self.__coordination_context.get("settlement_basis", {})
            if (
                not basis.get("allowed")
                or values.get("ref_s31_id") != basis.get("reservation_id")
                or values.get("transition_revision") != basis.get("next_revision")
                or values.get("event_type") != basis.get("target_status")
                or values.get("receipt_identity")
                != self.__coordination_context.get("command_causation_key")
                or values.get("occurred_at") != basis.get("occurred_at")
            ):
                raise GuardRequired("S32 must equal the exact guarded settlement transition")
        if logical_id == "S41":
            if values.get("ref_s39_id") not in self.__inserted_ids.get("S39", set()):
                raise GuardRequired("S41 must bind the S39 inserted by this command")
            if values.get("ref_s40_id") not in self.__inserted_ids.get("S40", set()):
                raise GuardRequired("S41 must bind the S40 inserted by this command")
        if logical_id == "S42":
            permitted_reasons = {
                "CommitBundle": {"AI_PLAN", "REUSE", "FALLBACK"},
                "Reauthorize": {"REVALIDATION"},
            }
            if values.get("issuance_reason") not in permitted_reasons.get(
                self.__command_kind, set()
            ):
                raise GuardRequired("S42 issuance reason is missing or invalid for this command")
            prior_prescription: tuple[Any, ...] | None = None
            if self.__command_kind == "CommitBundle":
                if values.get("ref_s40_id") not in self.__inserted_ids.get("S40", set()):
                    raise GuardRequired("S42 must bind the S40 inserted by this command")
            else:
                _cursor(self).execute(
                    "SELECT prescription.content_hash,prescription.ref_s34_id "
                    "FROM kineticloop.bundle_prescription_members member "
                    "JOIN kineticloop.prescription_revisions prescription "
                    "ON prescription.subject_id=member.subject_id "
                    "AND prescription.id=member.ref_s40_id "
                    "JOIN kineticloop.daily_plan_heads head "
                    "ON head.subject_id=member.subject_id "
                    "AND head.current_bundle_revision_id=member.ref_s39_id "
                    "WHERE member.subject_id=%s AND member.ref_s40_id=%s "
                    "AND head.id=%s",
                    (
                        self.__subject_id,
                        values.get("ref_s40_id"),
                        self.__coordination_context.get("authorization_head_id"),
                    ),
                )
                prior_prescription = _cursor(self).fetchone()
                if prior_prescription is None:
                    raise GuardRequired(
                        "reauthorization must bind a prescription on the locked current head"
                    )
            if values.get("registry_revision_at_issue") != self.__registry_revision:
                raise GuardRequired("S42 must bind the acquired registry revision")
            if values.get("ref_s24_id") != self.__coordination_context.get("current_manifest_id"):
                raise GuardRequired("S42 must bind the current locked manifest")
            if values.get("ref_s05_id") != self.__coordination_context.get(
                "active_policy_bundle_id"
            ):
                raise GuardRequired("S42 must bind the active locked policy")
            if values.get("ref_s37_id") != self.__coordination_context.get(
                "authorization_validation_id"
            ) or values.get("ref_s36_id") != self.__coordination_context.get(
                "authorization_resolution_id"
            ):
                raise GuardRequired("S42 must bind the prepared validation/resolution basis")
            prescription_id = values.get("ref_s40_id")
            prescription = (
                self.__inserted_values.get("S40", {}).get(prescription_id)
                if isinstance(prescription_id, UUID)
                else None
            )
            if self.__command_kind == "Reauthorize" and prior_prescription is not None:
                prescription = MappingProxyType(
                    {"content_hash": prior_prescription[0], "ref_s34_id": prior_prescription[1]}
                )
            if (
                prescription is None
                or not prescription.get("content_hash")
                or values.get("bound_content_hash") != prescription.get("content_hash")
            ):
                raise GuardRequired("S42 bound content must equal the inserted S40 content hash")
            _cursor(self).execute(
                "SELECT ref_s05_id,ref_s24_id,ref_s28_id,ref_s29_id,ref_s34_id,ref_s36_id,"
                "result,valid_until,ref_s03_id "
                "FROM kineticloop.validation_results WHERE subject_id=%s AND id=%s",
                (self.__subject_id, values.get("ref_s37_id")),
            )
            validation = _cursor(self).fetchone()
            if (
                validation is None
                or (
                    values.get("ref_s05_id"),
                    values.get("ref_s24_id"),
                    self.__coordination_context.get("verified_request_id"),
                    self.__coordination_context.get("verified_attempt_id"),
                    prescription.get("ref_s34_id") if prescription else None,
                    values.get("ref_s36_id"),
                    "PASS",
                    self.__coordination_context.get("validation_valid_until"),
                    self.__coordination_context.get("execution_basis_event_id"),
                )
                != validation
            ):
                raise GuardRequired("S42 inputs must equal the locked validation basis")
            certificate = self._json_value(values.get("validity_certificate", {}))
            required = {"authorization_epoch", "method_version", "closure_digest", "dependencies"}
            if not isinstance(certificate, dict) or not required <= set(certificate):
                raise StatementRejected("S42 validity_certificate is incomplete")
            expected_dependencies = list(
                self.__coordination_context.get("authorization_dependencies", ())
            )
            if certificate["dependencies"] != expected_dependencies:
                raise ArtifactIdentityRequired(
                    "S42 certificate dependencies must equal exact verified artifact proofs"
                )
            expected_digest = hashlib.sha256(
                json.dumps(expected_dependencies, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if certificate["closure_digest"] != expected_digest:
                raise ArtifactIdentityRequired("S42 certificate closure digest mismatch")
            if values.get("artifact_dependency_closure_hash") != expected_digest:
                raise ArtifactIdentityRequired("S42 closure hash mismatch")
            if certificate["authorization_epoch"] != self.__coordination_context.get(
                "authorization_epoch"
            ):
                raise GuardRequired("S42 certificate epoch must equal locked S01")
            if certificate["method_version"] != "kl015-v1":
                raise GuardRequired("S42 certificate method version is server-owned")
            authorization_valid_until = values.get("valid_until")
            if (
                not expected_dependencies
                or not isinstance(authorization_valid_until, datetime)
                or authorization_valid_until
                != self.__coordination_context.get("authorization_valid_until")
            ):
                raise ArtifactIdentityRequired("S42 valid_until must equal closure minimum")
            if values.get("valid_from") != self.__coordination_context.get(
                "authorization_valid_from"
            ):
                raise GuardRequired("S42 valid_from must equal the authoritative issuance time")
        if logical_id == "S43" and self.__command_kind == "CommitBundle":
            prior_heads = [value for value in self.__head_bundles.values() if value is not None]
            inserted_issuances = self.__inserted_values.get("S42", {})
            replacement_scopes = {issuance.get("scope") for issuance in inserted_issuances.values()}
            _cursor(self).execute(
                "SELECT issuance.scope FROM kineticloop.bundle_prescription_members member "
                "JOIN kineticloop.authorization_issuances issuance "
                "ON issuance.subject_id=member.subject_id "
                "AND issuance.ref_s40_id=member.ref_s40_id "
                "WHERE member.subject_id=%s AND member.ref_s39_id=ANY(%s) "
                "AND issuance.id=%s",
                (self.__subject_id, prior_heads, values.get("ref_s42_id")),
            )
            prior_authorization = _cursor(self).fetchone()
            if prior_authorization is None:
                raise GuardRequired("S43 must supersede the authorization on the prior locked head")
            if (
                values.get("event_kind") != "SUPERSEDED"
                or values.get("scope") != prior_authorization[0]
                or replacement_scopes != {values.get("scope")}
                or values.get("ref_s02_id") != self.__receipt_id
                or not values.get("causation_key")
            ):
                raise GuardRequired("S43 must record the exact same-command supersession")
        if (
            logical_id == "S43"
            and TRANSACTION_OWNER_MATRIX[self.__command_kind].boundary is Boundary.T2_IN
        ):
            invalidated_epoch = values.get("invalidated_epoch")
            if (
                not isinstance(invalidated_epoch, int)
                or invalidated_epoch != int(self.__coordination_context["authorization_epoch"]) + 1
                or values.get("ref_s42_id") is not None
                or values.get("event_kind") != "EPOCH_INVALIDATED"
                or values.get("ref_s02_id") != self.__receipt_id
                or values.get("scope") != self.__coordination_context.get("invalidation_scope")
                or values.get("causation_key")
                != self.__coordination_context.get("command_causation_key")
            ):
                raise GuardRequired("T2 S43 must advance the locked authorization epoch barrier")
            inserted_causes = {
                "DecideAdmission": ("ref_s13_id", "S13"),
                "ApplyControl": ("ref_s17_id", "S17"),
                "ClearControl": ("ref_s17_id", "S17"),
            }
            cause = inserted_causes.get(self.__command_kind)
            if cause is not None and values.get(cause[0]) not in self.__inserted_ids.get(
                cause[1], set()
            ):
                raise GuardRequired("T2 S43 cause must bind the decision inserted by this command")
            scope_causes = {
                "DecideAdmission": ("S13", "action_scope"),
                "ApplyControl": ("S17", "scope"),
                "ClearControl": ("S17", "scope"),
                "ApproveChange": ("S08", "approved_scope"),
            }
            scope_cause = scope_causes.get(self.__command_kind)
            if scope_cause is not None:
                inserted = self.__inserted_values.get(scope_cause[0], {})
                if len(inserted) != 1 or next(iter(inserted.values())).get(
                    scope_cause[1]
                ) != values.get("scope"):
                    raise GuardRequired("T2 S43 scope must equal its same-command cause scope")
        if logical_id == "S45":
            exact_pair = self.__coordination_context.get("execution_authorization")
            if exact_pair != (values.get("ref_s40_id"), values.get("ref_s42_id")):
                raise GuardRequired(
                    "S45 must bind the exact revalidated prescription/authorization"
                )
            expected_kind = {"StartSession": "START", "ResumeSession": "RESUME"}.get(
                self.__command_kind
            )
            if values.get("binding_kind") != expected_kind:
                raise GuardRequired("S45 binding kind must match the T7 command")
            if values.get("ref_s44_id") != self.__coordination_context.get("execution_session_id"):
                raise GuardRequired("S45 must bind the exact guarded execution session")
            if (
                values.get("execution_scope") != self.__coordination_context.get("execution_scope")
                or values.get("accepted_at")
                != self.__coordination_context.get("execution_accepted_at")
                or values.get("binding_revision")
                != self.__coordination_context.get("execution_binding_revision")
            ):
                raise GuardRequired("S45 scope, time, and revision must equal guarded eligibility")

    def _require_update_bindings(
        self,
        logical_id: str,
        values: Mapping[str, Any],
        predicates: Mapping[str, Any],
    ) -> None:
        if logical_id == "S01" and self.__command_kind == "PublishManifest":
            if values.get("current_manifest_id") not in self.__inserted_ids.get(
                "S24", set()
            ) or values.get("decision_generation") != self.__coordination_context.get(
                "publication_generation"
            ):
                raise GuardRequired("S01 must publish the exact new manifest generation")
        if logical_id == "S01" and self.__command_kind == "SealFactset":
            if values.get("current_factset_id") != self.__coordination_context.get(
                "seal_factset_id"
            ):
                raise GuardRequired("S01 must point to the exact sealed factset")
        if logical_id == "S23" and self.__command_kind == "PublishManifest":
            if (
                predicates.get("id") != self.__coordination_context.get("publication_build_id")
                or values.get("status") != "PUBLISHED"
            ):
                raise GuardRequired("PublishManifest must finalize the exact READY build")
        if logical_id == "S44" and self.__command_kind in {
            "StartSession",
            "ResumeSession",
            "ContinueSession",
        }:
            if (
                predicates.get("id") != self.__coordination_context.get("execution_session_id")
                or values.get("lifecycle") != "IN_PROGRESS"
                or values.get("execution_revision")
                != self.__coordination_context.get("execution_revision", 0) + 1
            ):
                raise GuardRequired("T7 must advance the exact guarded execution session")
        if logical_id == "S15" and self.__command_kind == "SealFactset":
            if (
                predicates.get("id") != self.__coordination_context.get("seal_factset_id")
                or values.get("status") != "SEALED"
                or values.get("sealed_at") != self.__coordination_context.get("seal_timestamp")
            ):
                raise GuardRequired("SealFactset must seal the exact guarded READY factset")
        if logical_id == "S15" and self.__command_kind in {
            "WriteCandidate",
            "CompleteFactset",
        }:
            basis = self.__coordination_context.get("factset_build", {})
            if predicates.get("id") != basis.get("build_id") or basis.get("status") != "BUILDING":
                raise GuardRequired("factset build mutation requires the exact BUILDING gate")
            if self.__command_kind == "WriteCandidate":
                if values.get("member_revision") != basis.get("member_revision", -1) + 1:
                    raise GuardRequired(
                        "WriteCandidate must increment member revision exactly once"
                    )
            else:
                payload = self._json_value(values.get("typed_payload", {}))
                if (
                    values.get("status") != "READY"
                    or values.get("member_revision") != basis.get("member_revision")
                    or values.get("completed_member_revision") != basis.get("member_revision")
                    or values.get("membership_digest") != basis.get("membership_digest")
                    or payload != basis.get("completion_payload")
                ):
                    raise GuardRequired("CompleteFactset must freeze the exact completion basis")
        if logical_id == "S18" and self.__command_kind in {"ApplyControl", "ClearControl"}:
            if values.get("ref_s17_id") not in self.__inserted_ids.get("S17", set()):
                raise GuardRequired("S18 head must bind the same-command control event")
        if logical_id == "S27" and self.__command_kind == "AdmitOrReviseIntent":
            if "current_request_revision_id" in values or "current_attempt_id" in values:
                if values.get("current_request_revision_id") not in self.__inserted_ids.get(
                    "S28", set()
                ) or values.get("current_attempt_id") not in self.__inserted_ids.get("S29", set()):
                    raise GuardRequired("S27 must adopt this command's exact request and attempt")
        if logical_id == "S38" and "current_bundle_revision_id" in values:
            if values["current_bundle_revision_id"] not in self.__inserted_ids.get("S39", set()):
                raise GuardRequired("S38 head must point to this command's inserted S39")
            head_id = predicates.get("id")
            head_basis = self.__coordination_context.get("daily_heads", {}).get(head_id, {})
            manifest_values = self.__inserted_values.get("S39", {}).get(
                values["current_bundle_revision_id"], {}
            )
            if (
                head_id != self.__coordination_context.get("authorization_head_id")
                or values.get("head_revision") != head_basis.get("head_revision", -1) + 1
                or manifest_values.get("revision_no") != values.get("head_revision")
            ):
                raise GuardRequired("S38 must advance the exact locked head revision")
        if logical_id == "S31" and self.__command_kind in {"SettleCall", "MarkUnknown"}:
            basis = self.__coordination_context.get("settlement_basis", {})
            if (
                not basis.get("allowed")
                or predicates.get("id") != basis.get("reservation_id")
                or values.get("status") != basis.get("target_status")
                or values.get("settlement_revision") != basis.get("next_revision")
            ):
                raise GuardRequired("S31 must apply the exact guarded settlement transition")
        if logical_id == "S27":
            object_id = predicates.get("id")
            if self.__command_kind in {"SettleCall", "MarkUnknown"}:
                basis = self.__coordination_context.get("settlement_basis", {})
                if object_id != basis.get("intent_id"):
                    raise GuardRequired("settlement accounting must update the reservation intent")
            if self.__command_kind == "AcquireLease" and "fence_token" in values:
                verified = (
                    self.__verified_fences.get(object_id) if isinstance(object_id, UUID) else None
                )
                if verified is None or verified[:2] != (values["fence_token"], "CAS"):
                    raise FenceLost("AcquireLease mutation must use the verified new fence")
                if values.get("lease_owner") != verified[2]:
                    raise FenceLost("AcquireLease mutation must use the verified new owner")
                expected_lease = self.__coordination_context.get("lease_targets", {}).get(object_id)
                if (
                    values.get("lease_expires_at") != expected_lease
                    or values.get("status") != "RUNNING"
                ):
                    raise FenceLost(
                        "AcquireLease must persist RUNNING with the verified new lease expiry"
                    )
            if self.__command_kind == "RenewLease" and "lease_expires_at" in values:
                _cursor(self).execute(
                    "SELECT lease_expires_at,deadline,clock_timestamp() "
                    "FROM kineticloop.planning_intents WHERE subject_id=%s AND id=%s",
                    (self.__subject_id, object_id),
                )
                lease_basis = _cursor(self).fetchone()
                new_expiry = values["lease_expires_at"]
                if (
                    lease_basis is None
                    or not isinstance(new_expiry, datetime)
                    or new_expiry <= lease_basis[0]
                    or new_expiry <= lease_basis[2]
                    or new_expiry > lease_basis[1]
                ):
                    raise FenceLost("RenewLease expiry must extend the live lease within deadline")
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
            detail = self.__artifact_details[artifact_id]
            _cursor(self).execute(
                "INSERT INTO kineticloop.authorization_artifact_closure"
                "(subject_id,authorization_id,artifact_id,artifact_revision,valid_from,valid_until) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    self.__subject_id,
                    authorization_id,
                    artifact_id,
                    detail["artifact_revision"],
                    datetime.fromisoformat(str(detail["valid_from"])),
                    datetime.fromisoformat(str(detail["valid_until"]))
                    if detail["valid_until"] is not None
                    else None,
                ),
            )
            if _cursor(self).rowcount != 1:
                raise ArtifactIdentityRequired("closure artifact disappeared")
        self.__closure_authorizations.add(authorization_id)

    def validate_completion(self) -> None:
        if self.__command_kind == "BeginBuild":
            if len(self.__inserted_ids.get("S15", set())) != 1:
                raise GuardRequired("BeginBuild requires exactly one S15 creation")
        if self.__command_kind == "WriteCandidate":
            build_id = self.__coordination_context.get("factset_build", {}).get("build_id")
            if len(self.__inserted_ids.get("S16", set())) != 1 or not any(
                row.get("id") == build_id for row in self.__updated_values.get("S15", [])
            ):
                raise GuardRequired("WriteCandidate requires one member and one revision advance")
        if self.__command_kind == "CompleteFactset":
            build_id = self.__coordination_context.get("factset_build", {}).get("build_id")
            if len(self.__updated_values.get("S15", [])) != 1 or not any(
                row.get("id") == build_id and row.get("status") == "READY"
                for row in self.__updated_values.get("S15", [])
            ):
                raise GuardRequired("CompleteFactset requires one exact READY transition")
        if self.__command_kind in {"CommitBundle", "Reauthorize"}:
            inserted = self.__inserted_ids.get("S42", set())
            if inserted != self.__closure_authorizations:
                raise ArtifactIdentityRequired(
                    "every inserted authorization requires its exact materialized closure"
                )
        if self.__command_kind == "CommitBundle":
            for logical_id in ("S39", "S40", "S41", "S42"):
                if len(self.__inserted_ids.get(logical_id, set())) != 1:
                    raise GuardRequired(f"CommitBundle requires exactly one {logical_id} insert")
            prior_exists = any(value is not None for value in self.__head_bundles.values())
            required_s43 = 1 if prior_exists else 0
            if len(self.__inserted_ids.get("S43", set())) != required_s43:
                raise GuardRequired(
                    "CommitBundle supersession count must match the locked prior head"
                )
            commit_updates = {
                "S01": lambda row: row.get("execution_basis_event_id") == self.__event_id,
                "S38": lambda row: (
                    row.get("id") == self.__coordination_context.get("authorization_head_id")
                    and row.get("current_bundle_revision_id") in self.__inserted_ids["S39"]
                ),
                "S27": lambda row: (
                    row.get("id") == self.__coordination_context.get("verified_intent_id")
                    and row.get("status") == "FOUND_VALID_PLAN"
                    and row.get("result_bundle_revision_id") in self.__inserted_ids["S39"]
                    and row.get("result_authorization_id") in self.__inserted_ids["S42"]
                ),
                "S29": lambda row: (
                    row.get("id") == self.__coordination_context.get("verified_attempt_id")
                    and row.get("status") == "COMMITTED"
                ),
            }
            for logical_id, predicate in commit_updates.items():
                if not any(predicate(row) for row in self.__updated_values.get(logical_id, [])):
                    raise GuardRequired(f"CommitBundle requires its mandatory {logical_id} update")
        if self.__command_kind == "Reauthorize":
            if len(self.__inserted_ids.get("S42", set())) != 1:
                raise GuardRequired("Reauthorize requires exactly one new S42 issuance")
            reauthorization_updates = {
                "S01": lambda row: row.get("execution_basis_event_id") == self.__event_id,
                "S27": lambda row: (
                    row.get("id") == self.__coordination_context.get("verified_intent_id")
                    and row.get("result_authorization_id") in self.__inserted_ids["S42"]
                ),
                "S29": lambda row: (
                    row.get("id") == self.__coordination_context.get("verified_attempt_id")
                    and row.get("status") == "COMMITTED"
                ),
            }
            for logical_id, predicate in reauthorization_updates.items():
                if not any(predicate(row) for row in self.__updated_values.get(logical_id, [])):
                    raise GuardRequired(f"Reauthorize requires its mandatory {logical_id} update")
        if self.__command_kind == "PublishManifest":
            if (
                len(self.__inserted_ids.get("S24", set())) != 1
                or len(self.__inserted_ids.get("S25", set())) != 1
            ):
                raise GuardRequired("PublishManifest requires one exact guarded S24/S25 basis")
        if self.__command_kind in {
            "DecideAssociation",
            "DecideAdmission",
            "AcceptFactRevision",
        }:
            if not any(
                row.get("input_frontier_hash")
                and row.get("input_frontier_hash")
                != self.__coordination_context.get("input_frontier_hash")
                for row in self.__updated_values.get("S01", [])
            ):
                raise GuardRequired("T2 input admission must advance the input frontier")
        if self.__command_kind in {"ApplyControl", "ClearControl"}:
            if not (self.__inserted_ids.get("S18") or self.__updated_values.get("S18")):
                raise GuardRequired("control transition requires an atomic S18 head mutation")
        if self.__command_kind in {"RecordActualExecution", "CompleteReportedWorkout"}:
            if not any(
                row.get("execution_basis_event_id") == self.__event_id
                for row in self.__updated_values.get("S01", [])
            ):
                raise GuardRequired("actual execution must advance the exact S01 event basis")
        if self.__command_kind == "AdmitOrReviseIntent":
            requests = self.__inserted_values.get("S28", {})
            attempts = self.__inserted_values.get("S29", {})
            if len(requests) != 1 or len(attempts) != 1:
                raise GuardRequired("T4 requires exactly one request and one initial attempt")
            request_id, request = next(iter(requests.items()))
            attempt_id, attempt = next(iter(attempts.items()))
            if (
                request.get("ref_s27_id") != attempt.get("ref_s27_id")
                or attempt.get("ref_s28_id") != request_id
                or not any(
                    row.get("id") == request.get("ref_s27_id")
                    and row.get("current_request_revision_id") == request_id
                    and row.get("current_attempt_id") == attempt_id
                    for row in self.__updated_values.get("S27", [])
                )
            ):
                raise GuardRequired("T4 request/attempt/current-intent chain is not exact")
        if self.__command_kind == "ReserveCall":
            reservations = self.__inserted_values.get("S31", {})
            ledgers = self.__inserted_values.get("S32", {})
            if len(reservations) != 1 or len(ledgers) != 1:
                raise GuardRequired("ReserveCall requires one exact S31/S32 pair")
            reservation_id, reservation = next(iter(reservations.items()))
            ledger = next(iter(ledgers.values()))
            if ledger.get("ref_s31_id") != reservation_id or not any(
                row.get("id") == reservation.get("ref_s27_id")
                for row in self.__updated_values.get("S27", [])
            ):
                raise GuardRequired(
                    "ReserveCall must atomically bind its intent/reservation/ledger"
                )
        if self.__command_kind in {"StartSession", "ResumeSession", "ContinueSession"}:
            if not self.__coordination_context.get("execution_authorization"):
                raise GuardRequired(
                    f"{self.__command_kind} must revalidate its exact prescription/authorization"
                )
            if not any(
                row.get("execution_basis_event_id") == self.__event_id
                for row in self.__updated_values.get("S01", [])
            ):
                raise GuardRequired(f"{self.__command_kind} must advance S01 execution basis")
            if not any(
                row.get("id") == self.__coordination_context.get("execution_session_id")
                for row in self.__updated_values.get("S44", [])
            ):
                raise GuardRequired(f"{self.__command_kind} must update the locked S44")
            required_bindings = 0 if self.__command_kind == "ContinueSession" else 1
            if len(self.__inserted_ids.get("S45", set())) != required_bindings:
                raise GuardRequired(
                    f"{self.__command_kind} requires {required_bindings} new S45 binding(s)"
                )
        if self.__command_kind == "PermitDispatch" and not self.__coordination_context.get(
            "dispatch_guard"
        ):
            raise GuardRequired("PermitDispatch must use the guarded first-winner transition")
        if (
            self.__command_kind == "PermitDispatch"
            and len(self.__inserted_ids.get("S32", set())) != 1
        ):
            raise GuardRequired("PermitDispatch requires one atomic S32 ledger event")
        if self.__command_kind in {"SettleCall", "MarkUnknown"}:
            basis = self.__coordination_context.get("settlement_basis", {})
            reservation_id = basis.get("reservation_id")
            intent_id = basis.get("intent_id")
            settlement_ledgers = list(self.__inserted_values.get("S32", {}).values())
            reservation_updates = [
                row
                for row in self.__updated_values.get("S31", [])
                if row.get("id") == reservation_id
            ]
            intent_updates = [
                row for row in self.__updated_values.get("S27", []) if row.get("id") == intent_id
            ]
            if (
                len(settlement_ledgers) != 1
                or len(reservation_updates) != 1
                or len(intent_updates) != 1
            ):
                raise GuardRequired("settlement must atomically update one exact S27/S31/S32 chain")
        if self.__command_kind == "AcquireLease":
            if not any(
                isinstance(row.get("id"), UUID)
                and self.__verified_fences.get(row["id"])
                == (row.get("fence_token"), "CAS", row.get("lease_owner"))
                and row.get("status") == "RUNNING"
                and row.get("lease_expires_at")
                == self.__coordination_context.get("lease_targets", {}).get(row["id"])
                for row in self.__updated_values.get("S27", [])
            ):
                raise GuardRequired("AcquireLease must persist its verified owner and new fence")
        if self.__command_kind == "ReapIntent":
            terminal = {"FAILED", "CANCELLED", "SEARCH_BUDGET_EXHAUSTED"}
            reaper_attempts = self.__coordination_context.get("reaper_attempts", {})
            reaped = {
                row["id"]
                for row in self.__updated_values.get("S27", [])
                if isinstance(row.get("id"), UUID) and row.get("status") in terminal
            }
            reaped_attempt_ids = {
                row["id"]
                for row in self.__updated_values.get("S29", [])
                if isinstance(row.get("id"), UUID) and row.get("status") in terminal
            }
            if not reaper_attempts or any(
                intent_id not in reaped or attempt_id not in reaped_attempt_ids
                for intent_id, attempt_id in reaper_attempts.items()
            ):
                raise GuardRequired("ReapIntent must terminate every exact S27/S29 chain")

        required_inserts: Mapping[str, tuple[str, ...]] = {
            "ReceiveEvidence": ("S09",),
            "DecideAssociation": ("S12", "S43"),
            "DecideAdmission": ("S13", "S43"),
            "AcceptFactRevision": ("S14", "S43"),
            "ApplyControl": ("S17", "S43"),
            "ClearControl": ("S17", "S43"),
            "ApproveChange": ("S08", "S43"),
            "ActivateApprovedProgram": ("S43",),
            "RecordActualExecution": ("S14", "S43"),
            "CompleteReportedWorkout": ("S14", "S43"),
            "PublishManifest": ("S24", "S25"),
            "AdmitOrReviseIntent": ("S28", "S29"),
            "ReserveCall": ("S31", "S32"),
            "SettleCall": ("S32",),
            "MarkUnknown": ("S32",),
        }
        for logical_id in required_inserts.get(self.__command_kind, ()):
            if not self.__inserted_ids.get(logical_id):
                raise GuardRequired(
                    f"{self.__command_kind} requires a mandatory {logical_id} insert"
                )
        if TRANSACTION_OWNER_MATRIX[self.__command_kind].boundary is Boundary.T2_IN:
            barriers = list(self.__inserted_values.get("S43", {}).values())
            epoch_updates = [
                row.get("authorization_epoch")
                for row in self.__updated_values.get("S01", [])
                if "authorization_epoch" in row
            ]
            if len(barriers) != 1 or epoch_updates != [barriers[0].get("invalidated_epoch")]:
                raise GuardRequired("T2 S43 barrier must equal the atomic S01 epoch advance")
        mandatory_updates: Mapping[str, tuple[str, ...]] = {
            "DecideAssociation": ("S01",),
            "DecideAdmission": ("S01",),
            "AcceptFactRevision": ("S01",),
            "ApplyControl": ("S01",),
            "ClearControl": ("S01",),
            "ApproveChange": ("S01",),
            "ActivateApprovedProgram": ("S01",),
            "RecordActualExecution": ("S01",),
            "CompleteReportedWorkout": ("S01", "S44"),
            "SealFactset": ("S01", "S15"),
            "PublishManifest": ("S01", "S23"),
            "AdmitOrReviseIntent": ("S27", "S30"),
            "CancelIntent": ("S27",),
            "RenewLease": ("S27",),
            "ReserveCall": ("S27",),
            "SettleCall": ("S27", "S31"),
            "MarkUnknown": ("S27", "S31"),
        }
        for logical_id in mandatory_updates.get(self.__command_kind, ()):
            if not self.__updated_values.get(logical_id):
                raise GuardRequired(
                    f"{self.__command_kind} requires a mandatory {logical_id} update"
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
            "S30": "planning_quota_buckets",
        }.get(logical_id)
        if lock_name is None:
            return
        object_id = predicates.get("id")
        if logical_id == "S27" and object_id in self.__inserted_ids.get("S27", set()):
            return
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
        "_artifact_details",
        "_coordination_context",
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
        self._verified_fences: dict[UUID, tuple[int, str, object | None]] = {}
        self._registry_revision: int | None = None
        self._head_bundles: dict[UUID, UUID | None] = {}
        self._artifact_details: dict[UUID, Mapping[str, Any]] = {}
        self._coordination_context: dict[str, Any] = {}

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
        _cursor(self).execute(
            "SELECT current_manifest_id,active_policy_bundle_id,authorization_epoch,"
            "execution_basis_event_id,active_program_id,current_factset_id,"
            "input_frontier_hash,decision_generation "
            "FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s",
            (self.subject_id,),
        )
        context = _cursor(self).fetchone()
        if context is None:
            raise GuardRequired("subject coordination context disappeared")
        self._coordination_context = {
            "current_manifest_id": context[0],
            "active_policy_bundle_id": context[1],
            "authorization_epoch": int(context[2]),
            "execution_basis_event_id": context[3],
            "active_program_id": context[4],
            "current_factset_id": context[5],
            "input_frontier_hash": context[6],
            "decision_generation": int(context[7]),
        }
        return self._registry_revision

    def lock_subject(self) -> None:
        if not self.spec.subject_guard_required:
            raise GuardRequired(f"{self.command_kind} has no S01 coordination entry")
        if self.subject_id is None:
            raise GuardRequired("subject guard requires a subject")
        self._advance(LockStage.SUBJECT)
        _cursor(self).execute(
            "SELECT subject_id,authorization_epoch,current_factset_id,input_frontier_hash,"
            "active_policy_bundle_id,active_program_id,current_manifest_id "
            "FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s FOR UPDATE",
            (self.subject_id,),
        )
        subject = _cursor(self).fetchone()
        if subject is None:
            raise GuardRequired("subject coordination row does not exist")
        self._coordination_context["authorization_epoch"] = int(subject[1])
        self._coordination_context["current_factset_id"] = subject[2]
        self._coordination_context["input_frontier_hash"] = subject[3]
        self._coordination_context["active_policy_bundle_id"] = subject[4]
        self._coordination_context["active_program_id"] = subject[5]
        self._coordination_context["current_manifest_id"] = subject[6]
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
            "SELECT id,current_bundle_revision_id,local_date,head_revision "
            "FROM kineticloop.daily_plan_heads "
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
        daily_heads = self._coordination_context.setdefault("daily_heads", {})
        for row in rows:
            daily_heads[UUID(str(row[0]))] = {
                "current_bundle_revision_id": (UUID(str(row[1])) if row[1] is not None else None),
                "local_date": row[2],
                "head_revision": int(row[3] or 0),
            }

    def lock_execution(self, session_ids: Sequence[UUID]) -> None:
        self._require_subject()
        if len(session_ids) != 1:
            raise GuardRequired("T7 requires exactly one execution session")
        self._advance(LockStage.EXECUTION)
        self._lock_ids("workout_sessions", session_ids)
        session_id = session_ids[0]
        _cursor(self).execute(
            "SELECT lifecycle,execution_revision,EXISTS("
            "SELECT 1 FROM kineticloop.execution_bindings binding "
            "WHERE binding.subject_id=session.subject_id AND binding.ref_s44_id=session.id "
            "AND binding.binding_kind='START') FROM kineticloop.workout_sessions session "
            "WHERE session.subject_id=%s AND session.id=%s",
            (self.subject_id, session_id),
        )
        session = _cursor(self).fetchone()
        if session is None:
            raise GuardRequired("exact execution session disappeared")
        lifecycle, execution_revision, has_start = session
        eligible = {
            "StartSession": lifecycle in {"READY", "PLANNED"} and not has_start,
            "ResumeSession": lifecycle == "PAUSED" and has_start,
            "ContinueSession": lifecycle == "IN_PROGRESS" and has_start,
        }.get(self.command_kind, True)
        if not eligible:
            raise GuardRequired("session lifecycle or repeated START guard failed")
        self._coordination_context["execution_session_id"] = session_id
        self._coordination_context["execution_revision"] = int(execution_revision)

    def lock_receipt(
        self,
        command_kind: str,
        client_key: str,
        actor_scope: str,
        *,
        natural_identity_key: str | None = None,
    ) -> None:
        self._require_receipt_guard()
        if command_kind != self.command_kind:
            raise GuardRequired("receipt command kind must match its repository owner")
        self._advance(LockStage.RECEIPT)
        if self.spec.boundary is Boundary.T1:
            key = (
                natural_identity_key
                or f"{self.subject_id}:{actor_scope}:{command_kind}:{client_key}"
            )
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
            "SELECT artifact_kind,artifact_identity,artifact_version,content_hash,"
            "validity_kind,valid_from,valid_until,timeless_approval_policy,"
            "timeless_approval_reason,revision FROM kineticloop.safety_artifacts WHERE id=%s "
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
        row = _cursor(self).fetchone()
        if row is None:
            raise ArtifactIdentityRequired("exact registered artifact identity is required")
        if identity.artifact_id not in self._leased_artifacts:
            raise ArtifactIdentityRequired("artifact identity was not included in the lease")
        self._verified_artifacts.add(identity.artifact_id)
        artifact_revision = int(row[9])
        if artifact_revision <= 0:
            raise ArtifactIdentityRequired("artifact revision must be positive")
        self._artifact_details[identity.artifact_id] = MappingProxyType(
            {
                "artifact_id": str(identity.artifact_id),
                "artifact_kind": row[0],
                "artifact_identity": row[1],
                "artifact_version": row[2],
                "content_hash": row[3],
                "artifact_revision": artifact_revision,
                "validity_kind": row[4],
                "valid_from": row[5].isoformat(),
                "valid_until": row[6].isoformat() if row[6] is not None else None,
                "timeless_approval_policy": row[7],
                "timeless_approval_reason": row[8],
            }
        )

    def artifact_certificate_dependencies(self) -> tuple[Mapping[str, Any], ...]:
        if set(self._artifact_details) != set(self._verified_artifacts):
            raise ArtifactIdentityRequired("artifact proof set is incomplete")
        return tuple(
            dict(self._artifact_details[artifact_id])
            for artifact_id in sorted(self._verified_artifacts, key=str)
        )

    def artifact_closure_digest(self) -> str:
        dependencies = self.artifact_certificate_dependencies()
        return hashlib.sha256(
            json.dumps(dependencies, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def artifact_closure_valid_until(self) -> datetime:
        values = [
            datetime.fromisoformat(str(item["valid_until"]))
            for item in self.artifact_certificate_dependencies()
            if item["valid_until"] is not None
        ]
        if not values:
            raise ArtifactIdentityRequired("bounded authorization requires a bounded artifact")
        return min(values)

    @property
    def authorization_epoch(self) -> int:
        if not self._registry:
            raise GuardRequired("authorization epoch requires registry/subject guard")
        return int(self._coordination_context["authorization_epoch"])

    def require_current_fence(
        self,
        intent_id: UUID,
        *,
        owner_id: str,
        fence: int,
        expected_request_revision: int,
        expected_attempt_id: UUID,
    ) -> None:
        self._require_subject()
        if self.command_kind not in {
            "RenewLease",
            "ReserveCall",
            "PermitDispatch",
            "CommitBundle",
            "Reauthorize",
        }:
            raise GuardRequired("current live fence is not available to this command owner")
        if intent_id not in self._locked_ids.get("planning_intents", set()):
            raise GuardRequired("exact intent must be locked before checking fence")
        _cursor(self).execute(
            "SELECT request.id,intent.local_date FROM kineticloop.planning_intents intent "
            "JOIN kineticloop.planning_request_revisions request "
            "ON request.subject_id=intent.subject_id "
            "AND request.id=intent.current_request_revision_id "
            "WHERE intent.subject_id=%s AND intent.id=%s "
            "AND intent.lease_owner=%s AND intent.fence_token=%s "
            "AND intent.status='RUNNING' AND intent.lease_expires_at > clock_timestamp() "
            "AND intent.deadline > clock_timestamp() "
            "AND request.request_revision=%s AND intent.current_attempt_id=%s",
            (
                self.subject_id,
                intent_id,
                owner_id,
                fence,
                expected_request_revision,
                expected_attempt_id,
            ),
        )
        verified_request = _cursor(self).fetchone()
        if verified_request is None:
            raise FenceLost("stale owner/fence cannot commit")
        self._coordination_context["verified_request_id"] = verified_request[0]
        self._coordination_context["verified_intent_local_date"] = verified_request[1]
        self._coordination_context["verified_intent_id"] = intent_id
        self._coordination_context["verified_attempt_id"] = expected_attempt_id
        self._verified_fences[intent_id] = (fence, "LIVE", expected_attempt_id)

    def prepare_authorization_basis(
        self,
        *,
        validation_id: UUID,
        resolution_id: UUID,
        intent_id: UUID,
        head_id: UUID,
        requested_valid_until: datetime | None = None,
    ) -> tuple[tuple[Mapping[str, Any], ...], str, datetime]:
        """Server-compute the complete bounded T6 certificate basis under held locks."""

        if self.command_kind not in {"CommitBundle", "Reauthorize"}:
            raise GuardRequired("authorization basis is exclusive to T6 owners")
        if intent_id != self._coordination_context.get("verified_intent_id"):
            raise GuardRequired("authorization basis must use the verified current intent")
        if validation_id not in self._locked_ids.get("validation_results", set()):
            raise GuardRequired("authorization basis requires the exact validation lock")
        if head_id not in self._locked_ids.get("daily_plan_heads", set()):
            raise GuardRequired("authorization basis requires the exact daily head lock")
        _cursor(self).execute(
            "SELECT manifest.id,manifest.revision,manifest.valid_until,"
            "resolution.id,resolution.revision,resolution.resolution_expires_at,"
            "validation.id,validation.revision,validation.valid_until,validation.result,"
            "request.id,request.request_revision,intent.deadline,head.id,head.local_date,"
            "clock_timestamp() "
            "FROM kineticloop.planning_intents intent "
            "JOIN kineticloop.planning_request_revisions request "
            "ON request.subject_id=intent.subject_id AND request.id=intent.current_request_revision_id "
            "JOIN kineticloop.planning_attempts attempt "
            "ON attempt.subject_id=intent.subject_id AND attempt.id=intent.current_attempt_id "
            "JOIN kineticloop.validation_results validation "
            "ON validation.subject_id=intent.subject_id AND validation.id=%s "
            "JOIN kineticloop.evidence_resolutions resolution "
            "ON resolution.subject_id=intent.subject_id AND resolution.id=%s "
            "JOIN kineticloop.decision_manifests manifest "
            "ON manifest.subject_id=intent.subject_id AND manifest.id=%s "
            "JOIN kineticloop.daily_plan_heads head "
            "ON head.subject_id=intent.subject_id AND head.id=%s "
            "WHERE intent.subject_id=%s AND intent.id=%s "
            "AND attempt.id=%s AND attempt.status='COMMIT_READY' "
            "AND attempt.fence_token=intent.fence_token "
            "AND attempt.ref_s24_id=%s AND attempt.captured_epoch=%s "
            "AND manifest.captured_epoch=%s "
            "AND resolution.ref_s24_id=manifest.id "
            "AND validation.ref_s24_id=manifest.id "
            "AND validation.ref_s36_id=resolution.id "
            "AND validation.ref_s28_id=request.id "
            "AND validation.ref_s29_id=attempt.id",
            (
                validation_id,
                resolution_id,
                self._coordination_context.get("current_manifest_id"),
                head_id,
                self.subject_id,
                intent_id,
                self._coordination_context.get("verified_attempt_id"),
                self._coordination_context.get("current_manifest_id"),
                self._coordination_context.get("authorization_epoch"),
                self._coordination_context.get("authorization_epoch"),
            ),
        )
        row = _cursor(self).fetchone()
        if row is None or row[9] != "PASS":
            raise GuardRequired("authorization requires a current PASS validation basis")
        now = row[15]
        _cursor(self).execute(
            "SELECT revision,typed_payload FROM kineticloop.policy_bundles WHERE id=%s",
            (self._coordination_context.get("active_policy_bundle_id"),),
        )
        policy = _cursor(self).fetchone()
        _cursor(self).execute(
            "SELECT typed_payload FROM kineticloop.daily_plan_heads WHERE subject_id=%s AND id=%s",
            (self.subject_id, head_id),
        )
        calendar = _cursor(self).fetchone()
        if policy is None or calendar is None:
            raise GuardRequired("policy and calendar authorization bounds must exist")
        _cursor(self).execute(
            "SELECT projection.id,projection.revision,projection.valid_until,binding.projection_role "
            "FROM kineticloop.manifest_projection_bindings binding "
            "LEFT JOIN kineticloop.projection_versions projection "
            "ON projection.subject_id=binding.subject_id AND projection.id=binding.ref_s21_id "
            "WHERE binding.subject_id=%s AND binding.ref_s24_id=%s "
            "ORDER BY binding.projection_role,binding.id",
            (self.subject_id, row[0]),
        )
        projections = _cursor(self).fetchall()
        if not projections or any(
            projection[0] is None or not isinstance(projection[2], datetime) or projection[2] <= now
            for projection in projections
        ):
            raise GuardRequired("all manifest projections require live explicit validity")
        try:
            policy_ttl = int((policy[1] or {})["max_authorization_ttl_seconds"])
            calendar_end = datetime.fromisoformat(str((calendar[0] or {})["calendar_valid_until"]))
        except (KeyError, TypeError, ValueError) as error:
            raise GuardRequired("policy TTL and calendar validity must be explicit") from error
        policy_end = now + timedelta(seconds=policy_ttl)
        artifact_ends = tuple(
            datetime.fromisoformat(str(detail["valid_until"]))
            for detail in self._artifact_details.values()
            if detail["valid_until"] is not None
        )
        bounded = (
            row[2],
            row[5],
            row[8],
            row[12],
            policy_end,
            calendar_end,
            *(projection[2] for projection in projections),
            *artifact_ends,
        )
        if any(not isinstance(value, datetime) or value <= now for value in bounded):
            raise GuardRequired("authorization basis contains an expired or undefined dependency")
        valid_until = min(bounded)
        if requested_valid_until is not None:
            if requested_valid_until <= now:
                raise GuardRequired("requested authorization end is already expired")
            valid_until = min(valid_until, requested_valid_until)
        dependencies = [
            dict(self._artifact_details[artifact_id])
            for artifact_id in sorted(self._verified_artifacts, key=str)
        ]
        dependencies.extend(
            (
                {
                    "dependency_kind": "MANIFEST",
                    "identity": str(row[0]),
                    "revision": row[1],
                    "valid_until": row[2].isoformat(),
                },
                {
                    "dependency_kind": "EVIDENCE_RESOLUTION",
                    "identity": str(row[3]),
                    "revision": row[4],
                    "valid_until": row[5].isoformat(),
                },
                {
                    "dependency_kind": "VALIDATION",
                    "identity": str(row[6]),
                    "revision": row[7],
                    "valid_until": row[8].isoformat(),
                },
                {
                    "dependency_kind": "REQUEST",
                    "identity": str(row[10]),
                    "revision": row[11],
                    "valid_until": row[12].isoformat(),
                },
                {
                    "dependency_kind": "POLICY",
                    "identity": str(self._coordination_context.get("active_policy_bundle_id")),
                    "revision": policy[0],
                    "valid_until": policy_end.isoformat(),
                },
                {
                    "dependency_kind": "CALENDAR",
                    "identity": str(row[13]),
                    "revision": row[14].isoformat(),
                    "valid_until": calendar_end.isoformat(),
                },
            )
        )
        dependencies.extend(
            {
                "dependency_kind": "PROJECTION",
                "identity": str(projection[0]),
                "revision": projection[1],
                "role": projection[3],
                "valid_until": projection[2].isoformat(),
            }
            for projection in projections
        )
        digest = hashlib.sha256(
            json.dumps(dependencies, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self._coordination_context["authorization_dependencies"] = tuple(dependencies)
        self._coordination_context["authorization_valid_from"] = now
        self._coordination_context["authorization_valid_until"] = valid_until
        self._coordination_context["validation_valid_until"] = row[8]
        self._coordination_context["authorization_validation_id"] = validation_id
        self._coordination_context["authorization_resolution_id"] = resolution_id
        self._coordination_context["authorization_head_id"] = head_id
        return tuple(dependencies), digest, valid_until

    def _prepare_manifest_publication(self) -> None:
        """Bind T3 publication to the one locked READY build and current S01 basis."""

        if self.command_kind != "PublishManifest":
            raise GuardRequired("manifest publication basis is exclusive to T3")
        build_ids = self._locked_ids.get("manifest_builds", set())
        if len(build_ids) != 1:
            raise GuardRequired("PublishManifest requires exactly one locked build")
        build_id = next(iter(build_ids))
        _cursor(self).execute(
            "SELECT build.status,build.captured_epoch,build.captured_input_frontier,"
            "build.ref_s05_id,build.ref_s06_id,build.ref_s15_id,build.ref_s21_id,"
            "build.typed_payload,factset.status,factset.ref_s20_id,mapping.ref_s19_id,"
            "projection.projection_kind,projection.input_basis_hash,projection.valid_until,"
            "clock_timestamp() FROM kineticloop.manifest_builds build "
            "JOIN kineticloop.factset_revisions factset "
            "ON factset.subject_id=build.subject_id AND factset.id=build.ref_s15_id "
            "JOIN kineticloop.projection_versions projection "
            "ON projection.subject_id=build.subject_id AND projection.id=build.ref_s21_id "
            "LEFT JOIN kineticloop.exercise_mapping_decisions mapping "
            "ON mapping.subject_id=factset.subject_id AND mapping.id=factset.ref_s20_id "
            "WHERE build.subject_id=%s AND build.id=%s",
            (self.subject_id, build_id),
        )
        build = _cursor(self).fetchone()
        if build is None or (
            build[0] != "READY"
            or build[1] != self._coordination_context.get("authorization_epoch")
            or build[2] != self._coordination_context.get("input_frontier_hash")
            or build[3] != self._coordination_context.get("active_policy_bundle_id")
            or build[4] != self._coordination_context.get("active_program_id")
            or build[5] != self._coordination_context.get("current_factset_id")
            or build[6] is None
            or build[8] != "SEALED"
            or not build[11]
            or not build[12]
            or not isinstance(build[13], datetime)
            or build[13] <= build[14]
        ):
            raise GuardRequired("manifest build is stale or not bound to the current S01 basis")
        candidate = dict(build[7] or {})
        if not candidate.get("manifest_hash"):
            raise GuardRequired("READY manifest build is missing its frozen candidate hash")
        _cursor(self).execute(
            "SELECT dependency_kind,dependency_semantic_key,collection_signature,ref_s05_id,"
            "ref_s06_id,ref_s14_id,ref_s15_id,ref_s19_id,ref_s20_id "
            "FROM kineticloop.projection_dependencies WHERE subject_id=%s AND ref_s21_id=%s "
            "ORDER BY dependency_kind,dependency_semantic_key,id",
            (self.subject_id, build[6]),
        )
        dependency_rows = [
            {
                "kind": row[0],
                "key": row[1],
                "collection": row[2],
                "policy": str(row[3]) if row[3] else None,
                "program": str(row[4]) if row[4] else None,
                "fact": str(row[5]) if row[5] else None,
                "factset": str(row[6]) if row[6] else None,
                "catalog": str(row[7]) if row[7] else None,
                "mapping": str(row[8]) if row[8] else None,
            }
            for row in _cursor(self).fetchall()
        ]
        if any(
            (item["policy"] and item["policy"] != str(build[3]))
            or (item["program"] and item["program"] != str(build[4]))
            or (item["factset"] and item["factset"] != str(build[5]))
            or (item["catalog"] and item["catalog"] != str(build[10]))
            or (item["mapping"] and item["mapping"] != str(build[9]))
            for item in dependency_rows
        ):
            raise GuardRequired("projection dependency basis is stale or cross-wired")
        artifact_digest = self.artifact_closure_digest()
        dependency_basis = {
            "projection_id": str(build[6]),
            "projection_role": build[11],
            "validated_basis_hash": build[12],
            "dependencies": dependency_rows,
            "artifact_closure_hash": artifact_digest,
            "catalog_id": str(build[10]) if build[10] else None,
            "mapping_id": str(build[9]) if build[9] else None,
        }
        dependency_digest = hashlib.sha256(
            json.dumps(dependency_basis, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        valid_until = min(build[13], self.artifact_closure_valid_until())
        if valid_until <= build[14]:
            raise GuardRequired("manifest dependency closure is expired")
        self._coordination_context["publication_build_id"] = build_id
        self._coordination_context["publication_generation"] = (
            int(self._coordination_context["decision_generation"]) + 1
        )
        self._coordination_context["publication_catalog_id"] = build[10]
        self._coordination_context["publication_mapping_id"] = build[9]
        self._coordination_context["publication_dependency_digest"] = dependency_digest
        self._coordination_context["publication_valid_until"] = valid_until
        self._coordination_context["publication_manifest_hash"] = candidate["manifest_hash"]
        self._coordination_context["publication_primary_artifact_id"] = min(
            self._verified_artifacts, key=str
        )
        self._coordination_context["publication_projection"] = {
            "id": build[6],
            "role": build[11],
            "basis_hash": build[12],
        }

    def _prepare_factset_seal(self, basis: Mapping[str, Any] | None) -> None:
        if self.command_kind != "SealFactset":
            raise GuardRequired("factset seal basis is exclusive to T2-SEAL")
        factset_ids = self._locked_ids.get("factset_revisions", set())
        if len(factset_ids) != 1:
            raise GuardRequired("SealFactset requires exactly one locked factset")
        factset_id = next(iter(factset_ids))
        _cursor(self).execute(
            "SELECT status,member_revision,completed_member_revision,membership_digest,"
            "typed_payload,clock_timestamp() FROM kineticloop.factset_revisions "
            "WHERE subject_id=%s AND id=%s",
            (self.subject_id, factset_id),
        )
        row = _cursor(self).fetchone()
        if row is None or row[0] != "READY" or basis is None:
            raise GuardRequired("SealFactset requires the exact locked READY factset")
        payload = dict(row[4] or {})
        certificate_basis = {
            "method_version": "kl015-v1",
            "factset_id": str(factset_id),
            "subject_id": str(self.subject_id),
            "captured_input_frontier": payload.get("captured_input_frontier"),
            "captured_epoch": payload.get("captured_epoch"),
            "completed_member_revision": row[2],
            "membership_digest": row[3],
        }
        certificate = hashlib.sha256(
            json.dumps(certificate_basis, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        expected = {
            "factset_id": factset_id,
            "captured_input_frontier": self._coordination_context.get("input_frontier_hash"),
            "captured_epoch": self._coordination_context.get("authorization_epoch"),
            "completed_member_revision": row[2],
            "membership_digest": row[3],
            "completion_identity": payload.get("completion_identity"),
            "completion_certificate": certificate,
        }
        if (
            not row[3]
            or row[1] != row[2]
            or payload.get("completion_certificate") != certificate
            or any(basis.get(key) != value for key, value in expected.items())
        ):
            raise GuardRequired("factset completion basis is stale, incomplete, or mismatched")
        self._coordination_context["seal_factset_id"] = factset_id
        self._coordination_context["seal_timestamp"] = row[5]

    def _prepare_settlement_basis(self) -> None:
        if self.command_kind not in {"SettleCall", "MarkUnknown"}:
            return
        intent_ids = self._locked_ids.get("planning_intents", set())
        reservation_ids = self._locked_ids.get("call_reservations", set())
        if len(intent_ids) != 1 or len(reservation_ids) != 1:
            raise GuardRequired("settlement requires one exact locked intent/reservation chain")
        intent_id = next(iter(intent_ids))
        reservation_id = next(iter(reservation_ids))
        _cursor(self).execute(
            "SELECT reservation.ref_s27_id,reservation.ref_s29_id,reservation.status,"
            "reservation.settlement_revision,clock_timestamp(),attempt.ref_s27_id "
            "FROM kineticloop.call_reservations reservation "
            "JOIN kineticloop.planning_attempts attempt "
            "ON attempt.subject_id=reservation.subject_id AND attempt.id=reservation.ref_s29_id "
            "WHERE reservation.subject_id=%s AND reservation.id=%s",
            (self.subject_id, reservation_id),
        )
        row = _cursor(self).fetchone()
        if row is None or row[0] != intent_id or row[1] is None or row[5] != intent_id:
            raise GuardRequired("settlement reservation must bind the exact locked intent/attempt")
        target = "SETTLED" if self.command_kind == "SettleCall" else "OUTCOME_UNKNOWN"
        allowed_sources = (
            {"DISPATCH_INTENT", "DISPATCHED", "OUTCOME_UNKNOWN"}
            if self.command_kind == "SettleCall"
            else {"DISPATCH_INTENT", "DISPATCHED"}
        )
        self._coordination_context["settlement_basis"] = {
            "reservation_id": reservation_id,
            "intent_id": intent_id,
            "attempt_id": row[1],
            "source_status": row[2],
            "allowed": row[2] in allowed_sources,
            "target_status": target,
            "next_revision": int(row[3] or 0) + 1,
            "occurred_at": row[4],
        }

    def require_execution_authorization(
        self,
        *,
        prescription_id: UUID,
        authorization_id: UUID,
        execution_scope: str,
    ) -> None:
        """Revalidate the exact P/A pair consumed by a T7 START/RESUME/CONTINUE."""

        if self.command_kind not in {"StartSession", "ResumeSession", "ContinueSession"}:
            raise GuardRequired("execution authorization is exclusive to T7 owners")
        self._require_subject()
        if not self._registry:
            raise GuardRequired("T7 execution authorization requires the registry lease")
        _cursor(self).execute(
            "SELECT 1 FROM kineticloop.authorization_issuances issuance "
            "JOIN kineticloop.prescription_revisions prescription "
            "ON prescription.subject_id=issuance.subject_id "
            "AND prescription.id=issuance.ref_s40_id "
            "JOIN kineticloop.bundle_prescription_members member "
            "ON member.subject_id=prescription.subject_id "
            "AND member.ref_s40_id=prescription.id "
            "JOIN kineticloop.daily_plan_heads head "
            "ON head.subject_id=member.subject_id "
            "AND head.current_bundle_revision_id=member.ref_s39_id "
            "WHERE issuance.subject_id=%s AND issuance.id=%s "
            "AND prescription.id=%s "
            "AND issuance.bound_content_hash=prescription.content_hash "
            "AND issuance.scope=%s "
            "AND issuance.valid_from <= clock_timestamp() "
            "AND issuance.valid_until > clock_timestamp() "
            "AND issuance.registry_revision_at_issue <= %s "
            "AND issuance.registry_state_id=1 "
            "AND issuance.ref_s49_id=ANY(%s) "
            "AND (issuance.validity_certificate->>'authorization_epoch')::bigint=%s "
            "AND head.id=ANY(%s) "
            "AND NOT EXISTS ("
            "SELECT 1 FROM kineticloop.authorization_events event "
            "WHERE event.subject_id=issuance.subject_id "
            "AND event.ref_s42_id=issuance.id) "
            "AND (SELECT count(*) "
            "FROM kineticloop.authorization_artifact_closure closure "
            "WHERE closure.subject_id=issuance.subject_id "
            "AND closure.authorization_id=issuance.id "
            "AND closure.artifact_id=ANY(%s) "
            "AND closure.valid_from <= clock_timestamp() "
            "AND (closure.valid_until IS NULL "
            "OR closure.valid_until > clock_timestamp()))=%s "
            "AND (SELECT count(*) "
            "FROM kineticloop.authorization_artifact_closure closure "
            "WHERE closure.subject_id=issuance.subject_id "
            "AND closure.authorization_id=issuance.id)=%s",
            (
                self.subject_id,
                authorization_id,
                prescription_id,
                execution_scope,
                self._registry_revision,
                list(self._leased_artifacts),
                self._coordination_context.get("authorization_epoch"),
                list(self._locked_ids.get("daily_plan_heads", set())),
                list(self._leased_artifacts),
                len(self._leased_artifacts),
                len(self._leased_artifacts),
            ),
        )
        if _cursor(self).fetchone() is None:
            raise GuardRequired("exact T7 prescription/authorization is not executable")
        session_id = self._coordination_context.get("execution_session_id")
        _cursor(self).execute(
            "SELECT clock_timestamp(),COALESCE(MAX(binding_revision),0)+1 "
            "FROM kineticloop.execution_bindings WHERE subject_id=%s AND ref_s44_id=%s",
            (self.subject_id, session_id),
        )
        binding_basis = _cursor(self).fetchone()
        if binding_basis is None:
            raise GuardRequired("execution binding basis disappeared")
        self._coordination_context["execution_authorization"] = (
            prescription_id,
            authorization_id,
        )
        self._coordination_context["execution_scope"] = execution_scope
        self._coordination_context["execution_accepted_at"] = binding_basis[0]
        self._coordination_context["execution_binding_revision"] = int(binding_basis[1])

    def require_lease_acquisition_basis(
        self,
        intent_id: UUID,
        *,
        expected_owner_id: str | None,
        expected_fence: int,
        new_owner_id: str,
        new_fence: int,
        new_lease_expires_at: datetime,
        expected_request_revision: int,
    ) -> None:
        """Prove the exact prior lease state used by an AcquireLease CAS."""

        self._require_subject()
        if self.command_kind != "AcquireLease":
            raise GuardRequired("lease acquisition basis is exclusive to AcquireLease")
        if intent_id not in self._locked_ids.get("planning_intents", set()):
            raise GuardRequired("exact intent must be locked before lease acquisition")
        if new_fence <= expected_fence:
            raise FenceLost("new lease fence must be strictly monotonic")
        _cursor(self).execute(
            "SELECT 1 FROM kineticloop.planning_intents intent "
            "JOIN kineticloop.planning_request_revisions request "
            "ON request.subject_id=intent.subject_id "
            "AND request.id=intent.current_request_revision_id "
            "WHERE intent.subject_id=%s AND intent.id=%s "
            "AND intent.lease_owner IS NOT DISTINCT FROM %s AND intent.fence_token=%s "
            "AND intent.status IN ('PENDING','RUNNING') "
            "AND intent.deadline > clock_timestamp() "
            "AND (intent.lease_expires_at IS NULL OR intent.lease_expires_at <= clock_timestamp() "
            "OR intent.lease_owner IS NOT DISTINCT FROM %s) "
            "AND request.request_revision=%s "
            "AND %s > clock_timestamp() AND %s <= intent.deadline",
            (
                self.subject_id,
                intent_id,
                expected_owner_id,
                expected_fence,
                new_owner_id,
                expected_request_revision,
                new_lease_expires_at,
                new_lease_expires_at,
            ),
        )
        if _cursor(self).fetchone() is None:
            raise FenceLost("lease acquisition compare-and-swap basis was lost")
        self._verified_fences[intent_id] = (new_fence, "CAS", new_owner_id)
        self._coordination_context.setdefault("lease_targets", {})[intent_id] = new_lease_expires_at

    def require_reaper_basis(
        self,
        intent_id: UUID,
        *,
        owner_id: str,
        fence: int,
        expected_deadline: datetime,
        expected_request_revision: int,
        expected_attempt_id: UUID,
    ) -> None:
        """Prove the exact expired/deadline basis used by ReapIntent."""

        self._require_subject()
        if self.command_kind != "ReapIntent":
            raise GuardRequired("expired lease basis is exclusive to ReapIntent")
        if intent_id not in self._locked_ids.get("planning_intents", set()):
            raise GuardRequired("exact intent must be locked before reaping")
        _cursor(self).execute(
            "SELECT 1 FROM kineticloop.planning_intents intent "
            "JOIN kineticloop.planning_request_revisions request "
            "ON request.subject_id=intent.subject_id "
            "AND request.id=intent.current_request_revision_id "
            "WHERE intent.subject_id=%s AND intent.id=%s "
            "AND intent.lease_owner=%s AND intent.fence_token=%s "
            "AND intent.status IN ('PENDING','RUNNING') "
            "AND intent.deadline IS NOT DISTINCT FROM %s "
            "AND request.request_revision=%s "
            "AND intent.current_attempt_id=%s "
            "AND (intent.lease_expires_at <= clock_timestamp() "
            "OR intent.deadline <= clock_timestamp())",
            (
                self.subject_id,
                intent_id,
                owner_id,
                fence,
                expected_deadline,
                expected_request_revision,
                expected_attempt_id,
            ),
        )
        if _cursor(self).fetchone() is None:
            raise FenceLost("intent is not owned by the expected expired lease")
        self._coordination_context.setdefault("reaper_attempts", {})[intent_id] = (
            expected_attempt_id
        )
        self._verified_fences[intent_id] = (fence, "EXPIRED", expected_attempt_id)

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
        if self.command_kind != "PermitDispatch":
            raise GuardRequired("dispatch permit is exclusive to PermitDispatch")
        if reservation_id not in self._locked_ids.get("call_reservations", set()):
            raise GuardRequired("exact reservation must be locked before dispatch transition")

        def transition(session: RestrictedSqlSession) -> Mapping[str, Any]:
            _cursor(self).execute(
                "SELECT status,dispatch_fence,typed_payload,ref_s27_id,ref_s29_id,"
                "settlement_revision,clock_timestamp() "
                "FROM kineticloop.call_reservations "
                "WHERE subject_id=%s AND id=%s",
                (self.subject_id, reservation_id),
            )
            row = _cursor(self).fetchone()
            if (
                row is None
                or int(row[1] or 0) != fence
                or row[3] not in self._verified_fences
                or self._verified_fences[row[3]][:2] != (fence, "LIVE")
                or self._verified_fences[row[3]][2] != row[4]
            ):
                raise DispatchNotPermitted("reservation or fence mismatch")
            if row[0] != "RESERVED":
                raise DispatchNotPermitted("only RESERVED may become DISPATCH_INTENT")
            payload = dict(row[2] or {})
            payload["permit_key"] = permit_key
            transition_revision = int(row[5]) + 1
            if (
                session.update(
                    "S31",
                    {
                        "status": "DISPATCH_INTENT",
                        "settlement_revision": transition_revision,
                        "typed_payload": Jsonb(payload),
                    },
                    {"subject_id": self.subject_id, "id": reservation_id},
                )
                != 1
            ):
                raise DispatchNotPermitted("reservation transition was not durable")
            session.insert(
                "S32",
                {
                    "id": event.event_id,
                    "subject_id": self.subject_id,
                    "event_type": "DISPATCH_INTENT",
                    "transition_revision": transition_revision,
                    "receipt_identity": permit_key,
                    "occurred_at": row[6],
                    "ref_s31_id": reservation_id,
                },
            )
            return {"reservation_id": str(reservation_id), "permit_key": permit_key}

        self._coordination_context["dispatch_guard"] = reservation_id
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
        source_identity_key: str | None = None,
        authorization_basis: Mapping[str, Any] | None = None,
        invalidation_scope: str | None = None,
        factset_seal_basis: Mapping[str, Any] | None = None,
    ) -> tuple[Mapping[str, Any], bool]:
        self._require_receipt_guard()
        self._require_command_locks(aggregate_locks or {})
        self._coordination_context["command_causation_key"] = client_key
        if invalidation_scope is not None:
            self._coordination_context["invalidation_scope"] = invalidation_scope
        self._prepare_settlement_basis()
        if self.spec.boundary is Boundary.T1 and source_identity_key is None:
            raise GuardRequired("T1 first execution requires its source identity key")
        self.lock_receipt(
            self.command_kind,
            client_key,
            actor_scope,
            natural_identity_key=source_identity_key,
        )
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
        if self.command_kind == "PublishManifest":
            self._prepare_manifest_publication()
        if self.command_kind == "SealFactset":
            self._prepare_factset_seal(factset_seal_basis)
        if self.command_kind in {"CommitBundle", "Reauthorize"}:
            if authorization_basis is None:
                raise GuardRequired("T6 requires a complete authorization validity basis")
            self.prepare_authorization_basis(**authorization_basis)
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
            source_identity_key=source_identity_key,
            verified_fences=self._verified_fences,
            artifact_details=self._artifact_details,
            coordination_context=self._coordination_context,
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
            if self.command_kind == "AdmitOrReviseIntent" and logical_id == "S27":
                continue
            if self.command_kind == "ReserveCall" and logical_id == "S31":
                continue
            if self.command_kind == "ReapIntent" and logical_id == "S31":
                continue
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
                self._verified_fences.get(intent_id, (None, None, None))[1] != mode
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
        outcome = dict(prior[2]["outcome"])
        if command_kind == "PermitDispatch":
            outcome.update({"sendable": False, "replayed": True})
        if command_kind in {"StartSession", "ResumeSession", "ContinueSession"}:
            outcome.update({"executable": False, "replayed": True})
        return outcome


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
    *,
    factset_build_basis: Mapping[str, Any] | None = None,
) -> _T:
    """Lock only the S15 build; factset construction never acquires S01."""

    if connection.info.transaction_status is not TransactionStatus.IDLE:
        raise TransactionStateError("factset build requires an idle connection")
    specification = TRANSACTION_OWNER_MATRIX.get(command_kind)
    if specification is None or specification.boundary is not Boundary.BUILD:
        raise GuardRequired("command is not a factset-build owner")
    with connection.transaction():
        cursor = connection.cursor()
        basis = dict(factset_build_basis or {})
        context: dict[str, Any] = {}
        locked: Mapping[str, frozenset[UUID]] = {}
        if command_kind == "BeginBuild":
            cursor.execute(
                "SELECT 1 FROM kineticloop.factset_revisions WHERE subject_id=%s AND id=%s",
                (subject_id, build_id),
            )
            if (
                cursor.fetchone() is not None
                or not basis.get("captured_input_frontier")
                or not isinstance(basis.get("captured_epoch"), int)
                or not isinstance(basis.get("program_revision_id"), UUID)
                or not isinstance(basis.get("policy_id"), UUID)
                or not basis.get("build_identity")
                or basis.get("storage_mode") not in {"FULL", "DELTA"}
            ):
                raise GuardRequired("BeginBuild basis is stale, incomplete, or already exists")
            typed_payload = {
                "basis_version": "kl015-v1",
                "captured_input_frontier": basis["captured_input_frontier"],
                "captured_epoch": basis["captured_epoch"],
                "program_revision_id": str(basis["program_revision_id"]),
                "policy_id": str(basis["policy_id"]),
                "mapping_revision_id": (
                    str(basis["mapping_revision_id"])
                    if basis.get("mapping_revision_id") is not None
                    else None
                ),
            }
            context["factset_begin"] = {
                **basis,
                "build_id": build_id,
                "typed_payload": typed_payload,
            }
        else:
            cursor.execute(
                "SELECT status,member_revision,typed_payload FROM kineticloop.factset_revisions "
                "WHERE subject_id=%s AND id=%s FOR UPDATE",
                (subject_id, build_id),
            )
            row = cursor.fetchone()
            if (
                row is None
                or row[0] != "BUILDING"
                or basis.get("expected_member_revision") != int(row[1] or 0)
            ):
                raise GuardRequired("factset build is not at the expected BUILDING revision")
            build_context: dict[str, Any] = {
                "build_id": build_id,
                "status": row[0],
                "member_revision": int(row[1] or 0),
                "typed_payload": dict(row[2] or {}),
            }
            if command_kind == "CompleteFactset":
                if not basis.get("membership_digest") or not basis.get("completion_identity"):
                    raise GuardRequired("CompleteFactset requires digest and completion identity")
                certificate_basis = {
                    "method_version": "kl015-v1",
                    "factset_id": str(build_id),
                    "subject_id": str(subject_id),
                    "captured_input_frontier": build_context["typed_payload"].get(
                        "captured_input_frontier"
                    ),
                    "captured_epoch": build_context["typed_payload"].get("captured_epoch"),
                    "completed_member_revision": build_context["member_revision"],
                    "membership_digest": basis["membership_digest"],
                }
                certificate = hashlib.sha256(
                    json.dumps(certificate_basis, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                build_context["membership_digest"] = basis["membership_digest"]
                build_context["completion_payload"] = {
                    **build_context["typed_payload"],
                    "completion_identity": basis["completion_identity"],
                    "member_count": basis.get("member_count"),
                    "completion_certificate": certificate,
                }
            context["factset_build"] = build_context
            locked = {"factset_revisions": frozenset({build_id})}
        session = RestrictedSqlSession(
            cursor,
            specification.mutation_surfaces,
            subject_id,
            command_kind=command_kind,
            locked_ids=locked,
            coordination_context=context,
        )
        result = operation(session)
        session.validate_completion()
        return result


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
