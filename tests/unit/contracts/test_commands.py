"""KL-014 command matrix and frozen-boundary regression tests."""

from __future__ import annotations

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

ID = "6ba7b810-9dad-41d1-80b4-00c04fd430c8"
OTHER_ID = "6ba7b811-9dad-41d1-80b4-00c04fd430c8"
HASH = "a" * 64


def _actor(role: ActorRole = ActorRole.SUBJECT) -> TrustedActor:
    capability = {
        ActorRole.SUBJECT: Capability.ACT_AS_PRODUCTION_SUBJECT,
        ActorRole.TEST: Capability.RUN_TEST_SIMULATION,
        ActorRole.ADMIN: Capability.ADMINISTER_PRODUCTION,
        ActorRole.EVALUATION: Capability.RUN_ISOLATED_EVALUATION,
    }[role]
    return TrustedActor(
        identity_id=ID,
        role=role,
        capability=capability,
        authenticated_by=OTHER_ID,
        authentication_event_id=ID,
        trusted=True,
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
        literal = _literal_value(field.annotation)
        if literal is not None:
            fields[name] = literal
        elif name == "source_revision":
            fields[name] = "source-revision"
        elif name == "adapter_observation_key":
            fields[name] = None
        elif name == "dependency_ids":
            fields[name] = (ID,)
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
    infrastructure_fields = {
        "schema_version",
        "command_kind",
        "boundary",
        "command_id",
        "actor",
        "idempotency_key",
        "request_hash",
        "subject_id",
        "explicit_scope",
        "authorization_scope",
    }
    for model in PUBLIC_COMMAND_MODELS:
        command = build_command(model)
        assert command.actor.trusted is True
        assert command.idempotency_key
        assert len(command.request_hash) == 64
        assert set(model.model_fields) - infrastructure_fields

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
