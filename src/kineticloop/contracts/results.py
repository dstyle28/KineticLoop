"""Typed success and rejection results for every public command contract."""

from __future__ import annotations

import json
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from typing_extensions import Annotated

from kineticloop.contracts.commands import PUBLIC_COMMAND_BY_KIND, CanonicalId, Sha256
from kineticloop.contracts.errors import ErrorCode
from kineticloop.primitives import canonical_json

NonEmpty = Annotated[str, StringConstraints(min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class StrictResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-command-result-v1"]
    result_kind: Literal["success"]
    command_kind: str
    receipt_id: CanonicalId
    result_id: CanonicalId
    entity_id: CanonicalId
    outcome_hash: Sha256
    completed_at: NonEmpty
    replayed: bool

    def to_canonical_json(self) -> str:
        return canonical_json(self.model_dump(mode="json"))


class ReceiveEvidenceSuccess(StrictResult):
    command_kind: Literal["ReceiveEvidence"]
    protective_action_applied: Literal[False]


class RecordCandidateSuccess(StrictResult):
    command_kind: Literal["RecordCandidate"]


class DecideAssociationSuccess(StrictResult):
    command_kind: Literal["DecideAssociation"]


class DecideAdmissionSuccess(StrictResult):
    command_kind: Literal["DecideAdmission"]


class AcceptFactRevisionSuccess(StrictResult):
    command_kind: Literal["AcceptFactRevision"]


class ApplyControlSuccess(StrictResult):
    command_kind: Literal["ApplyControl"]


class ClearControlSuccess(StrictResult):
    command_kind: Literal["ClearControl"]


class ApproveChangeSuccess(StrictResult):
    command_kind: Literal["ApproveChange"]


class ActivateApprovedProgramSuccess(StrictResult):
    command_kind: Literal["ActivateApprovedProgram"]


class RecordActualExecutionSuccess(StrictResult):
    command_kind: Literal["RecordActualExecution"]


class CompleteReportedWorkoutSuccess(StrictResult):
    command_kind: Literal["CompleteReportedWorkout"]


class BeginBuildSuccess(StrictResult):
    command_kind: Literal["BeginBuild"]
    acquired_subject_coordination_lock: Literal[False]


class WriteCandidateSuccess(StrictResult):
    command_kind: Literal["WriteCandidate"]
    acquired_subject_coordination_lock: Literal[False]


class CompleteFactsetSuccess(StrictResult):
    command_kind: Literal["CompleteFactset"]
    acquired_subject_coordination_lock: Literal[False]


class SealFactsetSuccess(StrictResult):
    command_kind: Literal["SealFactset"]


class RegisterArtifactSuccess(StrictResult):
    command_kind: Literal["RegisterArtifact"]
    acquired_registry_exclusive_gate: Literal[True]
    acquired_subject_coordination_lock: Literal[False]


class RevokeArtifactSuccess(StrictResult):
    command_kind: Literal["RevokeArtifact"]
    acquired_registry_exclusive_gate: Literal[True]
    acquired_subject_coordination_lock: Literal[False]


class RecordProjectionSuccess(StrictResult):
    command_kind: Literal["RecordProjection"]


class BuildManifestSuccess(StrictResult):
    command_kind: Literal["BuildManifest"]


class PublishManifestSuccess(StrictResult):
    command_kind: Literal["PublishManifest"]


class AdmitOrReviseIntentSuccess(StrictResult):
    command_kind: Literal["AdmitOrReviseIntent"]


class CancelIntentSuccess(StrictResult):
    command_kind: Literal["CancelIntent"]
    prior_success_revoked: Literal[False]


class AcquireLeaseSuccess(StrictResult):
    command_kind: Literal["AcquireLease"]
    owner_id: CanonicalId
    fence_token: NonNegativeInt
    lease_expires_at: NonEmpty


class RenewLeaseSuccess(StrictResult):
    command_kind: Literal["RenewLease"]
    owner_id: CanonicalId
    fence_token: NonNegativeInt
    lease_expires_at: NonEmpty


class ReserveCallSuccess(StrictResult):
    command_kind: Literal["ReserveCall"]


class PermitDispatchSuccess(StrictResult):
    command_kind: Literal["PermitDispatch"]
    provider_send_allowed: bool

    @model_validator(mode="after")
    def replay_cannot_grant_a_second_send(self) -> PermitDispatchSuccess:
        if self.replayed and self.provider_send_allowed:
            raise ValueError("a replayed dispatch permit cannot grant another provider send")
        return self


class RecordToolResultSuccess(StrictResult):
    command_kind: Literal["RecordToolResult"]


class RecordProposalSuccess(StrictResult):
    command_kind: Literal["RecordProposal"]


class RecordDemandFeaturesSuccess(StrictResult):
    command_kind: Literal["RecordDemandFeatures"]


class ResolveEvidenceSuccess(StrictResult):
    command_kind: Literal["ResolveEvidence"]


class RecordValidationSuccess(StrictResult):
    command_kind: Literal["RecordValidation"]


class CommitBundleSuccess(StrictResult):
    command_kind: Literal["CommitBundle"]
    currently_authorized: bool


class ReauthorizeSuccess(StrictResult):
    command_kind: Literal["Reauthorize"]
    currently_authorized: bool


class StartSessionSuccess(StrictResult):
    command_kind: Literal["StartSession"]
    currently_eligible: bool


class ResumeSessionSuccess(StrictResult):
    command_kind: Literal["ResumeSession"]
    currently_eligible: bool


class ContinueSessionSuccess(StrictResult):
    command_kind: Literal["ContinueSession"]
    currently_eligible: bool


class SettleCallSuccess(StrictResult):
    command_kind: Literal["SettleCall"]


class MarkUnknownSuccess(StrictResult):
    command_kind: Literal["MarkUnknown"]
    budget_restored: Literal[False]


class ReapIntentSuccess(StrictResult):
    command_kind: Literal["ReapIntent"]


PUBLIC_SUCCESS_RESULT_MODELS: tuple[type[StrictResult], ...] = (
    ReceiveEvidenceSuccess,
    RecordCandidateSuccess,
    DecideAssociationSuccess,
    DecideAdmissionSuccess,
    AcceptFactRevisionSuccess,
    ApplyControlSuccess,
    ClearControlSuccess,
    ApproveChangeSuccess,
    ActivateApprovedProgramSuccess,
    RecordActualExecutionSuccess,
    CompleteReportedWorkoutSuccess,
    BeginBuildSuccess,
    WriteCandidateSuccess,
    CompleteFactsetSuccess,
    SealFactsetSuccess,
    RegisterArtifactSuccess,
    RevokeArtifactSuccess,
    RecordProjectionSuccess,
    BuildManifestSuccess,
    PublishManifestSuccess,
    AdmitOrReviseIntentSuccess,
    CancelIntentSuccess,
    AcquireLeaseSuccess,
    RenewLeaseSuccess,
    ReserveCallSuccess,
    PermitDispatchSuccess,
    RecordToolResultSuccess,
    RecordProposalSuccess,
    RecordDemandFeaturesSuccess,
    ResolveEvidenceSuccess,
    RecordValidationSuccess,
    CommitBundleSuccess,
    ReauthorizeSuccess,
    StartSessionSuccess,
    ResumeSessionSuccess,
    ContinueSessionSuccess,
    SettleCallSuccess,
    MarkUnknownSuccess,
    ReapIntentSuccess,
)

PUBLIC_SUCCESS_RESULT_BY_KIND: dict[str, type[StrictResult]] = {
    get_args(model.model_fields["command_kind"].annotation)[0]: model
    for model in PUBLIC_SUCCESS_RESULT_MODELS
}


class CommandRejected(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["kineticloop-command-result-v1"]
    result_kind: Literal["rejected"]
    command_kind: str
    receipt_id: CanonicalId
    error_code: ErrorCode
    rejected_at: NonEmpty
    replayed: bool

    @model_validator(mode="after")
    def public_command_only(self) -> CommandRejected:
        if self.command_kind not in PUBLIC_COMMAND_BY_KIND:
            raise ValueError("rejections identify one public command")
        return self

    def to_canonical_json(self) -> str:
        return canonical_json(self.model_dump(mode="json"))


def parse_result(payload: str | dict[str, object]) -> StrictResult | CommandRejected:
    """Parse a strict typed result without accepting internal operation names."""

    if isinstance(payload, str):
        payload = json.loads(payload, object_pairs_hook=_reject_duplicate_fields)
    if type(payload) is not dict:
        raise TypeError("result payload must be an object")
    serialized = canonical_json(payload)
    result_kind = payload.get("result_kind")
    if result_kind == "rejected":
        return CommandRejected.model_validate_json(serialized)
    if result_kind != "success":
        raise ValueError("unknown result kind")
    command_kind = payload.get("command_kind")
    if type(command_kind) is not str or command_kind not in PUBLIC_SUCCESS_RESULT_BY_KIND:
        raise ValueError("unknown or internal-only command result kind")
    model = PUBLIC_SUCCESS_RESULT_BY_KIND[command_kind]
    return model.model_validate_json(serialized)


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate result field: {key}")
        result[key] = value
    return result
