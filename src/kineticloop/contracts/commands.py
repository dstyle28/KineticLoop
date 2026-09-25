"""Strict Pydantic command contracts for the frozen T1--T8 surface.

The models in this module are data contracts, not command authorization.  They
make the authenticated identity, idempotency identity, immutable basis, and
atomic boundary explicit so a command owner cannot accidentally treat
preparation data as a member of a frozen transaction.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, TypeAlias, get_args

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from kineticloop.identity import ActorRole, Capability, RoleIdentity
from kineticloop.primitives import canonical_json, canonical_utc

CanonicalId = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    ),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]


def _require_canonical_utc(value: str) -> str:
    if canonical_utc(value) != value:
        raise ValueError("instant must already use canonical UTC wire form")
    return value


CanonicalUtc = Annotated[
    str,
    StringConstraints(min_length=1),
    AfterValidator(_require_canonical_utc),
]


class TransactionBoundary(StrEnum):
    T1 = "T1"
    T1_PREPARATION = "T1-PREPARATION"
    T2_IN = "T2-IN"
    BUILD_PREPARATION = "BUILD-PREPARATION"
    T2_SEAL = "T2-SEAL"
    REGISTRY_MANAGEMENT = "REGISTRY-MANAGEMENT"
    T2_GLOBAL = "T2-GLOBAL"
    T3_PREPARATION = "T3-PREPARATION"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T5_PREPARATION = "T5-PREPARATION"
    T6_PREPARATION = "T6-PREPARATION"
    T6 = "T6"
    T7 = "T7"
    T8 = "T8"


class TrustedActor(BaseModel):
    """The merged role-identity wire shape, with no caller-asserted authority."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, serialize_by_alias=True
    )

    wire_schema: Literal["kineticloop-role-identity-v1"] = Field(alias="schema")
    identity_id: CanonicalId
    role: ActorRole

    @property
    def capability(self) -> Capability:
        """Derive the coarse capability from the merged immutable role matrix."""

        return {
            ActorRole.SUBJECT: Capability.ACT_AS_PRODUCTION_SUBJECT,
            ActorRole.TEST: Capability.RUN_TEST_SIMULATION,
            ActorRole.ADMIN: Capability.ADMINISTER_PRODUCTION,
            ActorRole.EVALUATION: Capability.RUN_ISOLATED_EVALUATION,
        }[self.role]

    @property
    def role_identity(self) -> RoleIdentity:
        return RoleIdentity(identity_id=self.identity_id, role=self.role)


class ProductionScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    scope: Literal["production"]
    subject_id: CanonicalId


class TestOnlyScope(BaseModel):
    """Fail-closed isolated scope accepted only by the real T6/T7 owners."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    scope: Literal["test_only"]
    subject_id: CanonicalId
    policy_id: CanonicalId
    environment_id: CanonicalId
    subject_boundary: Literal["isolated_non_production"]
    policy_boundary: Literal["isolated_non_production"]
    environment_boundary: Literal["isolated_non_production"]
    direct_write_allowed: Literal[False]
    command_owner_guard_required: Literal[True]


CommandScope: TypeAlias = Annotated[
    ProductionScope | TestOnlyScope, Field(discriminator="scope")
]


class StrictCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-command-v1"]
    command_kind: str
    boundary: TransactionBoundary
    command_id: CanonicalId
    actor: TrustedActor
    idempotency_key: NonEmpty
    request_hash: Sha256

    allowed_test_boundaries: ClassVar[frozenset[TransactionBoundary]] = frozenset(
        {TransactionBoundary.T6, TransactionBoundary.T7}
    )

    def to_canonical_json(self) -> str:
        return canonical_json(self.model_dump(mode="json"))


class SubjectCommand(StrictCommand):
    subject_id: CanonicalId
    explicit_scope: Literal[None]
    authorization_scope: CommandScope

    @model_validator(mode="after")
    def scope_and_actor_must_match(self) -> SubjectCommand:
        if self.authorization_scope.subject_id != self.subject_id:
            raise ValueError("authorization scope must bind the command subject")
        if isinstance(self.authorization_scope, ProductionScope):
            if self.actor.capability is not Capability.ACT_AS_PRODUCTION_SUBJECT:
                raise ValueError("production subject commands require a subject actor")
            if self.actor.identity_id != self.subject_id:
                raise ValueError(
                    "production subject commands require the authenticated actor "
                    "identity to match the command subject"
                )
        else:
            if self.actor.capability is not Capability.RUN_TEST_SIMULATION:
                raise ValueError("TEST_ONLY commands require a TEST actor")
            if self.boundary not in self.allowed_test_boundaries:
                raise ValueError("TEST_ONLY is admitted only at T6/T7 command owners")
        return self


class GlobalCommand(StrictCommand):
    subject_id: Literal[None]
    explicit_scope: Literal["global:safety-registry"]

    @model_validator(mode="after")
    def management_actor_required(self) -> GlobalCommand:
        if self.actor.capability is not Capability.ADMINISTER_PRODUCTION:
            raise ValueError("registry management requires an authenticated admin actor")
        return self


class ReceiveEvidence(SubjectCommand):
    command_kind: Literal["ReceiveEvidence"]
    boundary: Literal[TransactionBoundary.T1]
    source_object_id: CanonicalId
    source_revision: NonEmpty | None
    adapter_observation_key: NonEmpty | None
    content_hash: Sha256

    @model_validator(mode="after")
    def reliable_source_identity_required(self) -> ReceiveEvidence:
        if (self.source_revision is None) == (self.adapter_observation_key is None):
            raise ValueError("exactly one reliable source identity is required")
        return self


class RecordCandidate(SubjectCommand):
    command_kind: Literal["RecordCandidate"]
    boundary: Literal[TransactionBoundary.T1_PREPARATION]
    evidence_revision_id: CanonicalId
    extractor_version: NonEmpty
    extraction_operation_id: CanonicalId
    provenance_hash: Sha256


class DecideAssociation(SubjectCommand):
    command_kind: Literal["DecideAssociation"]
    boundary: Literal[TransactionBoundary.T2_IN]
    evidence_revision_id: CanonicalId
    expected_input_frontier_hash: Sha256
    association_basis_hash: Sha256


class DecideAdmission(SubjectCommand):
    command_kind: Literal["DecideAdmission"]
    boundary: Literal[TransactionBoundary.T2_IN]
    candidate_id: CanonicalId
    expected_input_frontier_hash: Sha256
    admission_basis_hash: Sha256


class AcceptFactRevision(SubjectCommand):
    command_kind: Literal["AcceptFactRevision"]
    boundary: Literal[TransactionBoundary.T2_IN]
    fact_revision_id: CanonicalId
    expected_input_frontier_hash: Sha256
    fact_basis_hash: Sha256


class ApplyControl(SubjectCommand):
    command_kind: Literal["ApplyControl"]
    boundary: Literal[TransactionBoundary.T2_IN]
    control_id: CanonicalId
    risk_evidence_id: CanonicalId
    policy_id: CanonicalId
    control_scope_hash: Sha256


class ClearControl(SubjectCommand):
    command_kind: Literal["ClearControl"]
    boundary: Literal[TransactionBoundary.T2_IN]
    control_id: CanonicalId
    clearance_evidence_id: CanonicalId
    policy_id: CanonicalId
    clearance_basis_hash: Sha256


class ApproveChange(SubjectCommand):
    command_kind: Literal["ApproveChange"]
    boundary: Literal[TransactionBoundary.T2_IN]
    proposal_revision_id: CanonicalId
    approval_content_hash: Sha256
    policy_id: CanonicalId


class ActivateApprovedProgram(SubjectCommand):
    command_kind: Literal["ActivateApprovedProgram"]
    boundary: Literal[TransactionBoundary.T2_IN]
    approval_id: CanonicalId
    proposal_revision_id: CanonicalId
    proposal_content_hash: Sha256
    expected_program_revision_id: CanonicalId


class RecordActualExecution(SubjectCommand):
    command_kind: Literal["RecordActualExecution"]
    boundary: Literal[TransactionBoundary.T2_IN]
    source_observation_id: CanonicalId
    session_id: CanonicalId
    actual_execution_hash: Sha256


class CompleteReportedWorkout(SubjectCommand):
    command_kind: Literal["CompleteReportedWorkout"]
    boundary: Literal[TransactionBoundary.T2_IN]
    actual_report_id: CanonicalId
    session_id: CanonicalId
    report_hash: Sha256


class BeginBuild(SubjectCommand):
    command_kind: Literal["BeginBuild"]
    boundary: Literal[TransactionBoundary.BUILD_PREPARATION]
    build_id: CanonicalId
    captured_input_frontier_hash: Sha256
    captured_authorization_epoch: NonNegativeInt
    program_revision_id: CanonicalId
    policy_id: CanonicalId
    mapping_revision_id: CanonicalId


class WriteCandidate(SubjectCommand):
    command_kind: Literal["WriteCandidate"]
    boundary: Literal[TransactionBoundary.BUILD_PREPARATION]
    build_id: CanonicalId
    member_operation_key: NonEmpty
    expected_member_revision: NonNegativeInt
    candidate_id: CanonicalId
    candidate_hash: Sha256


class CompleteFactset(SubjectCommand):
    command_kind: Literal["CompleteFactset"]
    boundary: Literal[TransactionBoundary.BUILD_PREPARATION]
    build_id: CanonicalId
    closed_member_revision: NonNegativeInt
    member_count: NonNegativeInt
    completion_digest: Sha256


class SealFactset(SubjectCommand):
    command_kind: Literal["SealFactset"]
    boundary: Literal[TransactionBoundary.T2_SEAL]
    build_id: CanonicalId
    completion_identity: CanonicalId
    captured_input_frontier_hash: Sha256
    captured_authorization_epoch: NonNegativeInt
    closed_member_revision: NonNegativeInt
    completion_digest: Sha256


class RegisterArtifact(GlobalCommand):
    command_kind: Literal["RegisterArtifact"]
    boundary: Literal[TransactionBoundary.REGISTRY_MANAGEMENT]
    artifact_id: CanonicalId
    artifact_kind: NonEmpty
    content_hash: Sha256
    dependency_ids: tuple[CanonicalId, ...]
    validity_spec_hash: Sha256


class RevokeArtifact(GlobalCommand):
    command_kind: Literal["RevokeArtifact"]
    boundary: Literal[TransactionBoundary.T2_GLOBAL]
    artifact_id: CanonicalId
    artifact_content_hash: Sha256
    revocation_payload_hash: Sha256
    causation_incident_id: CanonicalId


class RecordProjection(SubjectCommand):
    command_kind: Literal["RecordProjection"]
    boundary: Literal[TransactionBoundary.T3_PREPARATION]
    projection_id: CanonicalId
    projection_type: NonEmpty
    engine_version: NonEmpty
    exact_basis_hash: Sha256


class BuildManifest(SubjectCommand):
    command_kind: Literal["BuildManifest"]
    boundary: Literal[TransactionBoundary.T3_PREPARATION]
    build_id: CanonicalId
    sealed_factset_id: CanonicalId
    dependency_basis_hash: Sha256
    artifact_dependency_closure_hash: Sha256


class PublishManifest(SubjectCommand):
    command_kind: Literal["PublishManifest"]
    boundary: Literal[TransactionBoundary.T3]
    build_id: CanonicalId
    sealed_factset_id: CanonicalId
    expected_input_frontier_hash: Sha256
    expected_authorization_epoch: NonNegativeInt
    program_revision_id: CanonicalId
    policy_id: CanonicalId
    dependency_basis_hash: Sha256
    artifact_dependency_closure_hash: Sha256


class AdmitOrReviseIntent(SubjectCommand):
    command_kind: Literal["AdmitOrReviseIntent"]
    boundary: Literal[TransactionBoundary.T4]
    intent_id: CanonicalId
    request_revision: PositiveInt
    request_fingerprint: Sha256
    single_flight_partition: NonEmpty
    quota_policy_id: CanonicalId


class CancelIntent(SubjectCommand):
    command_kind: Literal["CancelIntent"]
    boundary: Literal[TransactionBoundary.T4, TransactionBoundary.T8]
    intent_id: CanonicalId
    expected_request_revision: PositiveInt
    expected_fence: NonNegativeInt


class AcquireLease(SubjectCommand):
    command_kind: Literal["AcquireLease"]
    boundary: Literal[TransactionBoundary.T5]
    intent_id: CanonicalId
    attempt_id: CanonicalId
    lease_operation_key: NonEmpty
    expected_owner_id: CanonicalId | None
    expected_fence: NonNegativeInt


class RenewLease(SubjectCommand):
    command_kind: Literal["RenewLease"]
    boundary: Literal[TransactionBoundary.T5]
    intent_id: CanonicalId
    attempt_id: CanonicalId
    lease_operation_key: NonEmpty
    expected_owner_id: CanonicalId
    expected_fence: NonNegativeInt


class ReserveCall(SubjectCommand):
    command_kind: Literal["ReserveCall"]
    boundary: Literal[TransactionBoundary.T5]
    intent_id: CanonicalId
    attempt_id: CanonicalId
    operation_slot: NonEmpty
    expected_fence: NonNegativeInt
    budget_policy_id: CanonicalId


class PermitDispatch(SubjectCommand):
    command_kind: Literal["PermitDispatch"]
    boundary: Literal[TransactionBoundary.T5]
    reservation_id: CanonicalId
    permit_key: NonEmpty
    expected_transition: Literal["RESERVED"]
    expected_fence: NonNegativeInt


class WorkerPreparationCommand(SubjectCommand):
    """Stale-worker basis required for every shared workflow preparation write."""

    intent_id: CanonicalId
    attempt_id: CanonicalId
    expected_request_revision: PositiveInt
    expected_owner_id: CanonicalId
    expected_fence: NonNegativeInt
    expected_lease_expires_at: CanonicalUtc
    expected_intent_status: Literal["RUNNING"]


class RecordToolResult(WorkerPreparationCommand):
    command_kind: Literal["RecordToolResult"]
    boundary: Literal[TransactionBoundary.T5_PREPARATION]
    operation_slot: NonEmpty
    tool_result_id: CanonicalId
    snapshot_id: CanonicalId
    tool_name: NonEmpty
    tool_version: NonEmpty
    artifact_version: NonEmpty
    arguments_hash: Sha256
    query_scope_window_hash: Sha256
    input_revision_refs_hash: Sha256
    result_hash: Sha256
    coverage: Literal["COMPLETE_FOR_POLICY", "PARTIAL", "UNKNOWN"]
    truncation_status: Literal["NOT_TRUNCATED", "TRUNCATED"]
    trust_class: Literal["MODEL_DERIVED"]
    command_authority: Literal["NONE"]


class RecordProposal(WorkerPreparationCommand):
    command_kind: Literal["RecordProposal"]
    boundary: Literal[TransactionBoundary.T5_PREPARATION]
    operation_slot: NonEmpty
    proposal_id: CanonicalId
    proposal_family_id: CanonicalId
    proposal_revision: PositiveInt
    snapshot_id: CanonicalId
    proposal_kind: Literal["FITNESS", "NUTRITION", "BLUEPRINT"]
    artifact_version: NonEmpty
    producer_artifact_id: CanonicalId
    proposal_hash: Sha256
    citations_hash: Sha256
    parent_proposal_id: CanonicalId | None = None
    fitness_proposal_id: CanonicalId | None = None
    fitness_proposal_hash: Sha256 | None = None
    demand_feature_id: CanonicalId | None = None
    demand_feature_hash: Sha256 | None = None
    manifest_id: CanonicalId | None = None
    policy_id: CanonicalId | None = None

    @model_validator(mode="after")
    def nutrition_dependencies_are_typed(self) -> RecordProposal:
        dependencies = (
            self.fitness_proposal_id,
            self.fitness_proposal_hash,
            self.demand_feature_id,
            self.demand_feature_hash,
            self.manifest_id,
            self.policy_id,
        )
        if self.proposal_kind == "NUTRITION" and any(value is None for value in dependencies):
            raise ValueError("NUTRITION proposals require Fitness, Demand, Manifest, and policy")
        if self.proposal_kind != "NUTRITION" and any(value is not None for value in dependencies):
            raise ValueError("cross-domain proposal dependencies belong only to NUTRITION")
        return self


class RecordDemandFeatures(WorkerPreparationCommand):
    command_kind: Literal["RecordDemandFeatures"]
    boundary: Literal[TransactionBoundary.T5_PREPARATION]
    operation_slot: NonEmpty
    demand_feature_id: CanonicalId
    fitness_proposal_id: CanonicalId
    fitness_proposal_hash: Sha256
    method_version: NonEmpty
    artifact_version: NonEmpty
    feature_payload_hash: Sha256
    demand_features_hash: Sha256
    semantic_classes_hash: Sha256
    estimate_intervals_hash: Sha256
    window_basis_hash: Sha256


class ResolveEvidence(WorkerPreparationCommand):
    command_kind: Literal["ResolveEvidence"]
    boundary: Literal[TransactionBoundary.T6_PREPARATION]
    resolution_id: CanonicalId
    action_id: CanonicalId
    action_type: NonEmpty
    action_parameters_hash: Sha256
    exercise_identity_id: CanonicalId
    manifest_id: CanonicalId
    policy_id: CanonicalId
    resolver_version: NonEmpty
    supporting_events_hash: Sha256
    contradicting_events_hash: Sha256
    superseded_or_retracted_items_hash: Sha256
    event_association_status: NonEmpty
    coverage: Literal["COMPLETE_FOR_POLICY", "PARTIAL", "UNKNOWN"]
    consistency: Literal["CONSISTENT", "CONFLICTED", "UNRESOLVED"]
    query_scope_window_hash: Sha256
    source_watermarks_hash: Sha256
    truncation_status: Literal["NOT_TRUNCATED", "TRUNCATED"]
    execution_basis_event_id: CanonicalId
    basis_fingerprint: Sha256
    resolution_expires_at: CanonicalUtc


class RecordValidation(WorkerPreparationCommand):
    command_kind: Literal["RecordValidation"]
    boundary: Literal[TransactionBoundary.T6_PREPARATION]
    validation_id: CanonicalId
    action_id: CanonicalId
    manifest_id: CanonicalId
    expected_authorization_epoch: NonNegativeInt
    proposal_hashes: tuple[Sha256, ...]
    demand_features_hash: Sha256
    resolver_results_hash: Sha256
    policy_bundle_id: CanonicalId
    execution_basis_event_id: CanonicalId
    execution_head_revisions_hash: Sha256
    validation_status: Literal["PASS", "FAIL", "REVIEW"]
    validation_codes: tuple[NonEmpty, ...]
    valid_until: CanonicalUtc
    validator_artifact_id: CanonicalId
    validator_artifact_version: NonEmpty
    validation_basis_fingerprint: Sha256


class T6Command(SubjectCommand):
    intent_id: CanonicalId
    attempt_id: CanonicalId
    manifest_id: CanonicalId
    expected_generation: PositiveInt
    expected_authorization_epoch: NonNegativeInt
    expected_request_revision: PositiveInt
    expected_owner_id: CanonicalId
    expected_fence: NonNegativeInt
    validation_id: CanonicalId
    execution_basis_event_id: CanonicalId
    policy_id: CanonicalId
    artifact_dependency_closure_hash: Sha256

    @model_validator(mode="after")
    def test_scope_policy_must_match(self) -> T6Command:
        if (
            isinstance(self.authorization_scope, TestOnlyScope)
            and self.authorization_scope.policy_id != self.policy_id
        ):
            raise ValueError("TEST_ONLY scope must bind the T6 command policy")
        return self


class CommitBundle(T6Command):
    command_kind: Literal["CommitBundle"]
    boundary: Literal[TransactionBoundary.T6]
    commit_identity: CanonicalId
    result_fingerprint: Sha256


class Reauthorize(T6Command):
    command_kind: Literal["Reauthorize"]
    boundary: Literal[TransactionBoundary.T6]
    prior_authorization_id: CanonicalId
    revalidation_intent_id: CanonicalId
    result_fingerprint: Sha256


class T7Command(SubjectCommand):
    session_id: CanonicalId
    action_key: NonEmpty
    prescription_id: CanonicalId
    authorization_id: CanonicalId
    binding_revision: PositiveInt
    expected_authorization_epoch: NonNegativeInt
    content_hash: Sha256
    artifact_dependency_closure_hash: Sha256


class StartSession(T7Command):
    command_kind: Literal["StartSession"]
    boundary: Literal[TransactionBoundary.T7]


class ResumeSession(T7Command):
    command_kind: Literal["ResumeSession"]
    boundary: Literal[TransactionBoundary.T7]
    prior_binding_id: CanonicalId


class ContinueSession(T7Command):
    command_kind: Literal["ContinueSession"]
    boundary: Literal[TransactionBoundary.T7]
    current_binding_id: CanonicalId


class SettleCall(SubjectCommand):
    command_kind: Literal["SettleCall"]
    boundary: Literal[TransactionBoundary.T8]
    reservation_id: CanonicalId
    provider_receipt_id: NonEmpty
    provider_receipt_hash: Sha256
    expected_transition: Literal["DISPATCH_INTENT", "UNKNOWN"]


class MarkUnknown(SubjectCommand):
    command_kind: Literal["MarkUnknown"]
    boundary: Literal[TransactionBoundary.T8]
    reservation_id: CanonicalId
    expected_transition: Literal["DISPATCH_INTENT"]
    reconciliation_basis_hash: Sha256


class ReapIntent(SubjectCommand):
    command_kind: Literal["ReapIntent"]
    boundary: Literal[TransactionBoundary.T8]
    intent_id: CanonicalId
    expected_owner_id: CanonicalId
    expected_fence: NonNegativeInt
    expected_deadline: CanonicalUtc


PUBLIC_COMMAND_MODELS: tuple[type[StrictCommand], ...] = (
    ReceiveEvidence,
    RecordCandidate,
    DecideAssociation,
    DecideAdmission,
    AcceptFactRevision,
    ApplyControl,
    ClearControl,
    ApproveChange,
    ActivateApprovedProgram,
    RecordActualExecution,
    CompleteReportedWorkout,
    BeginBuild,
    WriteCandidate,
    CompleteFactset,
    SealFactset,
    RegisterArtifact,
    RevokeArtifact,
    RecordProjection,
    BuildManifest,
    PublishManifest,
    AdmitOrReviseIntent,
    CancelIntent,
    AcquireLease,
    RenewLease,
    ReserveCall,
    PermitDispatch,
    RecordToolResult,
    RecordProposal,
    RecordDemandFeatures,
    ResolveEvidence,
    RecordValidation,
    CommitBundle,
    Reauthorize,
    StartSession,
    ResumeSession,
    ContinueSession,
    SettleCall,
    MarkUnknown,
    ReapIntent,
)

PUBLIC_COMMAND_BY_KIND: dict[str, type[StrictCommand]] = {
    get_args(model.model_fields["command_kind"].annotation)[0]: model
    for model in PUBLIC_COMMAND_MODELS
}

# These are deliberately absent from PUBLIC_COMMAND_MODELS.  Owners may use
# internal helpers, but they are not independently invocable command contracts.
INTERNAL_ONLY_OPERATIONS = frozenset(
    {
        "IssueAuthorization",
        "InvalidateAuthorization",
        "RecordSnapshot",
        "AdvanceAttempt",
        "CancelUndispatched",
    }
)


def parse_command(payload: str | dict[str, object]) -> StrictCommand:
    """Parse exactly one public command using its closed command discriminator."""

    if isinstance(payload, str):
        payload = json.loads(payload, object_pairs_hook=_reject_duplicate_fields)
    if type(payload) is not dict:
        raise TypeError("command payload must be an object")
    kind = payload.get("command_kind")
    if type(kind) is not str or kind not in PUBLIC_COMMAND_BY_KIND:
        raise ValueError("unknown or internal-only command kind")
    adapter = TypeAdapter(PUBLIC_COMMAND_BY_KIND[kind])
    return adapter.validate_json(canonical_json(payload))


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate command field: {key}")
        result[key] = value
    return result
