"""KL-014 command matrix and frozen-boundary regression tests."""

from __future__ import annotations

import json
from typing import Any, Literal, get_args, get_origin

import pytest
from pydantic import ValidationError

from kineticloop.contracts import (
    INTERNAL_ONLY_OPERATIONS,
    PUBLIC_COMMAND_BY_KIND,
    PUBLIC_COMMAND_MODELS,
    BeginBuild,
    BuildManifest,
    CommitBundle,
    CompleteFactset,
    ProductionScope,
    RecordCandidate,
    RecordDemandFeatures,
    RecordProjection,
    RecordProposal,
    RecordToolResult,
    RecordValidation,
    RegisterArtifact,
    ResolveEvidence,
    RevokeArtifact,
    TransactionBoundary,
    TrustedActor,
    WriteCandidate,
    parse_command,
)
from kineticloop.contracts import (
    TestOnlyScope as CommandTestOnlyScope,
)
from kineticloop.identity import ActorRole, Capability
from kineticloop.primitives import canonical_json

ID = "6ba7b810-9dad-41d1-80b4-00c04fd430c8"
OTHER_ID = "6ba7b811-9dad-41d1-80b4-00c04fd430c8"
HASH = "a" * 64


def _actor(role: ActorRole = ActorRole.SUBJECT) -> TrustedActor:
    return TrustedActor(
        schema="kineticloop-role-identity-v1",
        identity_id=ID,
        role=role,
    )


def _literal_value(annotation: object) -> object | None:
    if get_origin(annotation) is Literal:
        return get_args(annotation)[0]
    return None


def command_payload(model: Any, *, test_only: bool = False) -> dict[str, object]:
    fields: dict[str, object] = {
        "schema_version": "kineticloop-command-v1",
        "command_id": ID,
        "idempotency_key": "idempotency-key",
        "request_hash": HASH,
    }
    global_command = issubclass(model, RegisterArtifact.__bases__[0])
    if global_command:
        fields.update(
            actor=_actor(ActorRole.ADMIN),
            subject_id=None,
            explicit_scope="global:safety-registry",
        )
    else:
        fields.update(
            actor=_actor(ActorRole.TEST if test_only else ActorRole.SUBJECT),
            subject_id=ID,
            explicit_scope=None,
            authorization_scope=(
                CommandTestOnlyScope(
                    scope="test_only",
                    subject_id=ID,
                    policy_id=ID,
                    environment_id=ID,
                    subject_boundary="isolated_non_production",
                    policy_boundary="isolated_non_production",
                    environment_boundary="isolated_non_production",
                    direct_write_allowed=False,
                    command_owner_guard_required=True,
                )
                if test_only
                else ProductionScope(scope="production", subject_id=ID)
            ),
        )

    for name, field in model.model_fields.items():
        if name in fields:
            continue
        if not field.is_required():
            continue
        literal = _literal_value(field.annotation)
        if literal is not None:
            fields[name] = literal
        elif name == "source_revision":
            fields[name] = "source-revision"
        elif name == "adapter_observation_key":
            fields[name] = None
        elif name == "dependency_ids":
            fields[name] = (ID,)
        elif name == "proposal_hashes":
            fields[name] = (HASH,)
        elif name == "validation_codes":
            fields[name] = ("VALID",)
        elif name.endswith("_at") or name in {"valid_until", "expected_deadline"}:
            fields[name] = "2026-09-24T16:05:00.000000Z"
        elif name == "expected_owner_id" and field.annotation is not str:
            fields[name] = ID
        elif name.endswith("_id") or name.endswith("_identity"):
            fields[name] = ID
        elif any(
            token in name
            for token in ("hash", "fingerprint", "digest")
        ):
            fields[name] = HASH
        elif any(
            token in name
            for token in ("frontier", "epoch", "revision", "fence", "count", "generation")
        ):
            fields[name] = 1
        else:
            fields[name] = "value"
    return fields


def build_command(model: Any, *, test_only: bool = False) -> Any:
    return model.model_validate(command_payload(model, test_only=test_only))


EXPECTED_BOUNDARIES = {
    "ReceiveEvidence": TransactionBoundary.T1,
    "RecordCandidate": TransactionBoundary.T1_PREPARATION,
    "DecideAssociation": TransactionBoundary.T2_IN,
    "DecideAdmission": TransactionBoundary.T2_IN,
    "AcceptFactRevision": TransactionBoundary.T2_IN,
    "ApplyControl": TransactionBoundary.T2_IN,
    "ClearControl": TransactionBoundary.T2_IN,
    "ApproveChange": TransactionBoundary.T2_IN,
    "ActivateApprovedProgram": TransactionBoundary.T2_IN,
    "RecordActualExecution": TransactionBoundary.T2_IN,
    "CompleteReportedWorkout": TransactionBoundary.T2_IN,
    "BeginBuild": TransactionBoundary.BUILD_PREPARATION,
    "WriteCandidate": TransactionBoundary.BUILD_PREPARATION,
    "CompleteFactset": TransactionBoundary.BUILD_PREPARATION,
    "SealFactset": TransactionBoundary.T2_SEAL,
    "RegisterArtifact": TransactionBoundary.REGISTRY_MANAGEMENT,
    "RevokeArtifact": TransactionBoundary.T2_GLOBAL,
    "RecordProjection": TransactionBoundary.T3_PREPARATION,
    "BuildManifest": TransactionBoundary.T3_PREPARATION,
    "PublishManifest": TransactionBoundary.T3,
    "AdmitOrReviseIntent": TransactionBoundary.T4,
    "CancelIntent": TransactionBoundary.T4,
    "AcquireLease": TransactionBoundary.T5,
    "RenewLease": TransactionBoundary.T5,
    "ReserveCall": TransactionBoundary.T5,
    "PermitDispatch": TransactionBoundary.T5,
    "RecordToolResult": TransactionBoundary.T5_PREPARATION,
    "RecordProposal": TransactionBoundary.T5_PREPARATION,
    "RecordDemandFeatures": TransactionBoundary.T5_PREPARATION,
    "ResolveEvidence": TransactionBoundary.T6_PREPARATION,
    "RecordValidation": TransactionBoundary.T6_PREPARATION,
    "CommitBundle": TransactionBoundary.T6,
    "Reauthorize": TransactionBoundary.T6,
    "StartSession": TransactionBoundary.T7,
    "ResumeSession": TransactionBoundary.T7,
    "ContinueSession": TransactionBoundary.T7,
    "SettleCall": TransactionBoundary.T8,
    "MarkUnknown": TransactionBoundary.T8,
    "ReapIntent": TransactionBoundary.T8,
}

REQUIRED_BASIS_FIELDS = {
    "ReceiveEvidence": {"source_object_id", "source_revision", "content_hash"},
    "RecordCandidate": {"evidence_revision_id", "extractor_version", "extraction_operation_id", "provenance_hash"},
    "DecideAssociation": {"evidence_revision_id", "expected_input_frontier_hash", "association_basis_hash"},
    "DecideAdmission": {"candidate_id", "expected_input_frontier_hash", "admission_basis_hash"},
    "AcceptFactRevision": {"fact_revision_id", "expected_input_frontier_hash", "fact_basis_hash"},
    "ApplyControl": {"control_id", "risk_evidence_id", "policy_id", "control_scope_hash"},
    "ClearControl": {"control_id", "clearance_evidence_id", "policy_id", "clearance_basis_hash"},
    "ApproveChange": {"proposal_revision_id", "approval_content_hash", "policy_id"},
    "ActivateApprovedProgram": {"approval_id", "proposal_revision_id", "proposal_content_hash", "expected_program_revision_id"},
    "RecordActualExecution": {"source_observation_id", "session_id", "actual_execution_hash"},
    "CompleteReportedWorkout": {"actual_report_id", "session_id", "report_hash"},
    "BeginBuild": {"build_id", "captured_input_frontier_hash", "captured_authorization_epoch", "program_revision_id", "policy_id", "mapping_revision_id"},
    "WriteCandidate": {"build_id", "member_operation_key", "expected_member_revision", "candidate_id", "candidate_hash"},
    "CompleteFactset": {"build_id", "closed_member_revision", "member_count", "completion_digest"},
    "SealFactset": {"build_id", "completion_identity", "captured_input_frontier_hash", "captured_authorization_epoch", "closed_member_revision", "completion_digest"},
    "RegisterArtifact": {"artifact_id", "artifact_kind", "content_hash", "dependency_ids", "validity_spec_hash"},
    "RevokeArtifact": {"artifact_id", "artifact_content_hash", "revocation_payload_hash", "causation_incident_id"},
    "RecordProjection": {"projection_id", "projection_type", "engine_version", "exact_basis_hash"},
    "BuildManifest": {"build_id", "sealed_factset_id", "dependency_basis_hash", "artifact_dependency_closure_hash"},
    "PublishManifest": {"build_id", "sealed_factset_id", "expected_input_frontier_hash", "expected_authorization_epoch", "program_revision_id", "policy_id", "dependency_basis_hash", "artifact_dependency_closure_hash"},
    "AdmitOrReviseIntent": {"intent_id", "request_revision", "request_fingerprint", "single_flight_partition", "quota_policy_id"},
    "CancelIntent": {"intent_id", "expected_request_revision", "expected_fence"},
    "AcquireLease": {"intent_id", "attempt_id", "lease_operation_key", "expected_owner_id", "expected_fence"},
    "RenewLease": {"intent_id", "attempt_id", "lease_operation_key", "expected_owner_id", "expected_fence"},
    "ReserveCall": {"intent_id", "attempt_id", "operation_slot", "expected_fence", "budget_policy_id"},
    "PermitDispatch": {"reservation_id", "permit_key", "expected_transition", "expected_fence"},
    "RecordToolResult": {"intent_id", "attempt_id", "expected_request_revision", "expected_owner_id", "expected_fence", "expected_lease_expires_at", "snapshot_id", "tool_result_id", "arguments_hash", "input_revision_refs_hash", "result_hash", "coverage", "truncation_status"},
    "RecordProposal": {"intent_id", "attempt_id", "expected_request_revision", "expected_owner_id", "expected_fence", "expected_lease_expires_at", "proposal_id", "proposal_family_id", "proposal_revision", "snapshot_id", "proposal_kind", "proposal_hash", "producer_artifact_id", "citations_hash"},
    "RecordDemandFeatures": {"intent_id", "attempt_id", "expected_request_revision", "expected_owner_id", "expected_fence", "expected_lease_expires_at", "demand_feature_id", "fitness_proposal_id", "fitness_proposal_hash", "method_version", "feature_payload_hash", "demand_features_hash", "semantic_classes_hash", "window_basis_hash"},
    "ResolveEvidence": {"intent_id", "attempt_id", "expected_request_revision", "expected_owner_id", "expected_fence", "expected_lease_expires_at", "resolution_id", "action_id", "manifest_id", "policy_id", "supporting_events_hash", "contradicting_events_hash", "coverage", "consistency", "source_watermarks_hash", "basis_fingerprint"},
    "RecordValidation": {"intent_id", "attempt_id", "expected_request_revision", "expected_owner_id", "expected_fence", "expected_lease_expires_at", "validation_id", "manifest_id", "expected_authorization_epoch", "proposal_hashes", "demand_features_hash", "resolver_results_hash", "policy_bundle_id", "execution_basis_event_id", "execution_head_revisions_hash", "validation_status", "validation_codes", "valid_until", "validator_artifact_id"},
    "CommitBundle": {"intent_id", "attempt_id", "manifest_id", "expected_generation", "expected_authorization_epoch", "expected_request_revision", "expected_owner_id", "expected_fence", "validation_id", "execution_basis_event_id", "policy_id", "artifact_dependency_closure_hash", "commit_identity", "result_fingerprint"},
    "Reauthorize": {"intent_id", "attempt_id", "manifest_id", "expected_generation", "expected_authorization_epoch", "expected_request_revision", "expected_owner_id", "expected_fence", "validation_id", "execution_basis_event_id", "policy_id", "artifact_dependency_closure_hash", "prior_authorization_id", "revalidation_intent_id", "result_fingerprint"},
    "StartSession": {"session_id", "action_key", "prescription_id", "authorization_id", "binding_revision", "expected_authorization_epoch", "content_hash", "artifact_dependency_closure_hash"},
    "ResumeSession": {"session_id", "action_key", "prescription_id", "authorization_id", "binding_revision", "expected_authorization_epoch", "content_hash", "artifact_dependency_closure_hash", "prior_binding_id"},
    "ContinueSession": {"session_id", "action_key", "prescription_id", "authorization_id", "binding_revision", "expected_authorization_epoch", "content_hash", "artifact_dependency_closure_hash", "current_binding_id"},
    "SettleCall": {"reservation_id", "provider_receipt_id", "provider_receipt_hash", "expected_transition"},
    "MarkUnknown": {"reservation_id", "expected_transition", "reconciliation_basis_hash"},
    "ReapIntent": {"intent_id", "expected_owner_id", "expected_fence", "expected_deadline"},
}


def test_strict_t1_t8_contract_matrix() -> None:
    assert set(PUBLIC_COMMAND_BY_KIND) == set(EXPECTED_BOUNDARIES)
    assert len(PUBLIC_COMMAND_MODELS) == len(EXPECTED_BOUNDARIES) == 39
    assert INTERNAL_ONLY_OPERATIONS.isdisjoint(PUBLIC_COMMAND_BY_KIND)

    for kind, model in PUBLIC_COMMAND_BY_KIND.items():
        command = build_command(model)
        assert command.command_kind == kind
        assert command.boundary == EXPECTED_BOUNDARIES[kind]
        assert command.model_config["extra"] == "forbid"
        assert command.model_config["frozen"] is True
        assert type(parse_command(command.to_canonical_json())) is model
        assert type(parse_command(json.loads(command.to_canonical_json()))) is model

        extra = command.model_dump(mode="python") | {"unexpected": True}
        with pytest.raises(ValidationError):
            model.model_validate(extra)


def test_build_preparation_stays_outside_t2() -> None:
    for model in (BeginBuild, WriteCandidate, CompleteFactset):
        command = build_command(model)
        assert command.boundary is TransactionBoundary.BUILD_PREPARATION
        assert "subject_coordination" not in type(command).model_fields
        mutated = command.model_dump(mode="python") | {"boundary": TransactionBoundary.T2_IN}
        with pytest.raises(ValidationError):
            model.model_validate(mutated)


def test_preparation_and_registry_management_stay_outside_atomic_boundaries() -> None:
    expected: dict[Any, TransactionBoundary] = {
        RecordCandidate: TransactionBoundary.T1_PREPARATION,
        RegisterArtifact: TransactionBoundary.REGISTRY_MANAGEMENT,
        RecordProjection: TransactionBoundary.T3_PREPARATION,
        BuildManifest: TransactionBoundary.T3_PREPARATION,
        RecordToolResult: TransactionBoundary.T5_PREPARATION,
        RecordProposal: TransactionBoundary.T5_PREPARATION,
        RecordDemandFeatures: TransactionBoundary.T5_PREPARATION,
        ResolveEvidence: TransactionBoundary.T6_PREPARATION,
        RecordValidation: TransactionBoundary.T6_PREPARATION,
    }
    forbidden = {
        TransactionBoundary.T1_PREPARATION: TransactionBoundary.T1,
        TransactionBoundary.REGISTRY_MANAGEMENT: TransactionBoundary.T2_GLOBAL,
        TransactionBoundary.T3_PREPARATION: TransactionBoundary.T3,
        TransactionBoundary.T5_PREPARATION: TransactionBoundary.T5,
        TransactionBoundary.T6_PREPARATION: TransactionBoundary.T6,
    }
    for model, boundary in expected.items():
        command = build_command(model)
        assert command.boundary is boundary
        mutated = command.model_dump(mode="python") | {"boundary": forbidden[boundary]}
        with pytest.raises(ValidationError):
            model.model_validate(mutated)


def test_identity_idempotency_and_basis_fields() -> None:
    assert set(REQUIRED_BASIS_FIELDS) == set(PUBLIC_COMMAND_BY_KIND)
    for model in PUBLIC_COMMAND_MODELS:
        command = build_command(model)
        assert command.actor.capability in {
            Capability.ACT_AS_PRODUCTION_SUBJECT,
            Capability.ADMINISTER_PRODUCTION,
        }
        assert set(command.actor.model_dump()) == {"schema", "identity_id", "role"}
        assert command.idempotency_key
        assert len(command.request_hash) == 64
        required = REQUIRED_BASIS_FIELDS[command.command_kind]
        assert required <= set(model.model_fields)
        assert all(model.model_fields[name].is_required() for name in required)

        payload = command_payload(model)
        for name in required:
            missing = payload.copy()
            missing.pop(name)
            with pytest.raises(ValidationError):
                model.model_validate(missing)

        if model is RevokeArtifact or model is RegisterArtifact:
            assert command.subject_id is None
            assert command.explicit_scope == "global:safety-registry"
        else:
            assert command.subject_id == ID
            assert command.explicit_scope is None

    payload = command_payload(CommitBundle)
    actor = payload["actor"]
    assert isinstance(actor, TrustedActor)
    payload["actor"] = actor.model_copy(update={"identity_id": OTHER_ID})
    with pytest.raises(ValidationError, match="authenticated actor identity"):
        CommitBundle.model_validate(payload)

    actor_payload = _actor().model_dump(mode="json") | {
        "capability": Capability.ADMINISTER_PRODUCTION.value
    }
    with pytest.raises(ValidationError):
        TrustedActor.model_validate(actor_payload)


def test_cancel_intent_supports_only_t4_and_t8() -> None:
    model = PUBLIC_COMMAND_BY_KIND["CancelIntent"]
    for boundary in (TransactionBoundary.T4, TransactionBoundary.T8):
        payload = command_payload(model)
        payload["boundary"] = boundary
        command = model.model_validate(payload)
        assert command.boundary is boundary
        assert parse_command(command.to_canonical_json()).boundary is boundary

    payload = command_payload(model)
    payload["boundary"] = TransactionBoundary.T5
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_nutrition_proposal_requires_cross_domain_basis() -> None:
    model: Any = PUBLIC_COMMAND_BY_KIND["RecordProposal"]
    payload = command_payload(model)
    payload["proposal_kind"] = "NUTRITION"
    with pytest.raises(ValidationError, match="Fitness, Demand, Manifest, and policy"):
        model.model_validate(payload)

    payload.update(
        fitness_proposal_id=ID,
        fitness_proposal_hash=HASH,
        demand_feature_id=ID,
        demand_feature_hash=HASH,
        manifest_id=ID,
        policy_id=ID,
    )
    assert model.model_validate(payload).proposal_kind == "NUTRITION"


def test_tool_results_are_non_command_and_times_are_canonical_utc() -> None:
    model: Any = PUBLIC_COMMAND_BY_KIND["RecordToolResult"]
    payload = command_payload(model)
    assert payload["trust_class"] == "MODEL_DERIVED"
    assert payload["command_authority"] == "NONE"
    wire_payload = model.model_validate(payload).model_dump(mode="json")

    for serialized in (wire_payload, canonical_json(wire_payload)):
        invalid = dict(serialized) if isinstance(serialized, dict) else json.loads(serialized)
        invalid["trust_class"] = "ADMIN_COMMAND_AUTHORITY"
        with pytest.raises(ValidationError):
            parse_command(invalid)
        with pytest.raises(ValidationError):
            parse_command(canonical_json(invalid))

    for command_kind, field_name in (
        ("RecordToolResult", "expected_lease_expires_at"),
        ("ResolveEvidence", "resolution_expires_at"),
        ("RecordValidation", "valid_until"),
        ("ReapIntent", "expected_deadline"),
    ):
        command_model = PUBLIC_COMMAND_BY_KIND[command_kind]
        invalid = command_model.model_validate(command_payload(command_model)).model_dump(
            mode="json"
        )
        invalid[field_name] = "not-an-instant"
        with pytest.raises(ValidationError):
            parse_command(invalid)
        with pytest.raises(ValidationError):
            parse_command(canonical_json(invalid))


@pytest.mark.parametrize(
    ("command_kind", "field_name"),
    (
        ("DecideAssociation", "expected_input_frontier_hash"),
        ("DecideAdmission", "expected_input_frontier_hash"),
        ("AcceptFactRevision", "expected_input_frontier_hash"),
        ("BeginBuild", "captured_input_frontier_hash"),
        ("SealFactset", "captured_input_frontier_hash"),
        ("PublishManifest", "expected_input_frontier_hash"),
    ),
)
def test_input_frontier_is_an_immutable_hash(
    command_kind: str, field_name: str
) -> None:
    model = PUBLIC_COMMAND_BY_KIND[command_kind]
    payload = command_payload(model)
    assert payload[field_name] == HASH
    command = model.model_validate(payload)
    assert getattr(command, field_name) == HASH

    payload[field_name] = 1
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_shadow_and_test_scope_fail_closed() -> None:
    for model in (CommitBundle, PUBLIC_COMMAND_BY_KIND["Reauthorize"], PUBLIC_COMMAND_BY_KIND["StartSession"], PUBLIC_COMMAND_BY_KIND["ResumeSession"], PUBLIC_COMMAND_BY_KIND["ContinueSession"]):
        command = build_command(model, test_only=True)
        assert command.authorization_scope.scope == "test_only"
        assert command.authorization_scope.direct_write_allowed is False
        assert command.authorization_scope.command_owner_guard_required is True

    invalid_model = PUBLIC_COMMAND_BY_KIND["PublishManifest"]
    with pytest.raises(ValidationError, match="T6/T7"):
        build_command(invalid_model, test_only=True)

    payload = command_payload(CommitBundle, test_only=True)
    payload["actor"] = _actor(ActorRole.SUBJECT)
    with pytest.raises(ValidationError, match="TEST_ONLY"):
        CommitBundle.model_validate(payload)

    payload = command_payload(CommitBundle, test_only=True)
    scope = payload["authorization_scope"]
    assert isinstance(scope, CommandTestOnlyScope)
    scope = scope.model_dump(mode="python")
    scope["direct_write_allowed"] = True
    payload["authorization_scope"] = scope
    with pytest.raises(ValidationError):
        CommitBundle.model_validate(payload)

    for model in (CommitBundle, PUBLIC_COMMAND_BY_KIND["Reauthorize"]):
        payload = command_payload(model, test_only=True)
        payload["policy_id"] = OTHER_ID
        with pytest.raises(ValidationError, match="scope must bind the T6 command policy"):
            model.model_validate(payload)
