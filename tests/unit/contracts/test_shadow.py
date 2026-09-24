"""Executable checks for the KL-008 shadow/test semantic split."""

import json
from dataclasses import FrozenInstanceError

import pytest

from kineticloop.contracts import (
    SHADOW_ARTIFACT_WIRE_SCHEMA,
    TEST_ONLY_SCOPE_WIRE_SCHEMA,
    AuthorizationScope,
    ExecutionDisposition,
    IsolationBoundary,
    ShadowContractError,
    ShadowEvaluationArtifact,
    ShadowMode,
    ShadowPersistenceBoundary,
)
from kineticloop.contracts import (
    TestOnlyAuthorizationScope as AuthorizationTestScope,
)
from kineticloop.identity import ActorRole, RoleIdentity

ARTIFACT_ID = "6ba7b810-9dad-41d1-80b4-00c04fd430c8"
RUN_ID = "6ba7b811-9dad-41d1-80b4-00c04fd430c8"
IDENTITY_ID = "6ba7b812-9dad-41d1-80b4-00c04fd430c8"
SUBJECT_ID = "6ba7b813-9dad-41d1-80b4-00c04fd430c8"
POLICY_ID = "6ba7b814-9dad-41d1-80b4-00c04fd430c8"
ENVIRONMENT_ID = "6ba7b815-9dad-41d1-80b4-00c04fd430c8"


def _artifact() -> ShadowEvaluationArtifact:
    return ShadowEvaluationArtifact(artifact_id=ARTIFACT_ID, evaluation_run_id=RUN_ID)


def _scope(role: ActorRole = ActorRole.TEST) -> AuthorizationTestScope:
    return AuthorizationTestScope(
        actor=RoleIdentity(identity_id=IDENTITY_ID, role=role),
        subject_id=SUBJECT_ID,
        policy_id=POLICY_ID,
        environment_id=ENVIRONMENT_ID,
    )


def test_shadow_contract_schema_valid() -> None:
    artifact = _artifact()
    scope = _scope()

    assert ShadowEvaluationArtifact.from_json(artifact.to_json()) == artifact
    assert AuthorizationTestScope.from_json(scope.to_json()) == scope
    assert artifact.to_json() == artifact.to_json()
    assert scope.to_json() == scope.to_json()
    assert json.loads(artifact.to_json())["schema"] == SHADOW_ARTIFACT_WIRE_SCHEMA
    assert json.loads(scope.to_json())["schema"] == TEST_ONLY_SCOPE_WIRE_SCHEMA
    with pytest.raises(FrozenInstanceError):
        artifact.artifact_id = RUN_ID  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        scope.subject_id = RUN_ID  # type: ignore[misc]

    invalid_json = (
        '{"schema":"kineticloop-shadow-evaluation-artifact-v1",'
        f'"artifact_id":"{ARTIFACT_ID}","artifact_id":"{RUN_ID}",'
        f'"evaluation_run_id":"{RUN_ID}","mode":"shadow_only",'
        '"execution_disposition":"not_executable",'
        '"persistence_boundary":"isolated_evaluation_artifact",'
        '"s38_live_head_target":null,"s42_production_issuance_target":null,'
        '"s45_execution_binding_target":null,'
        '"live_planning_intent_success_target":null}'
    )
    with pytest.raises(ShadowContractError, match="duplicate"):
        ShadowEvaluationArtifact.from_json(invalid_json)

    for original, field_name, invalid_value in (
        (artifact.to_payload(), "schema", "kineticloop-shadow-evaluation-artifact-v2"),
        (artifact.to_payload(), "mode", "live"),
        (scope.to_payload(), "schema", "kineticloop-test-only-authorization-scope-v2"),
        (scope.to_payload(), "scope", "production"),
    ):
        original[field_name] = invalid_value
        with pytest.raises(ShadowContractError):
            if "artifact_id" in original:
                ShadowEvaluationArtifact.from_payload(original)
            else:
                AuthorizationTestScope.from_payload(original)

    for original, parser in (
        (artifact.to_payload(), ShadowEvaluationArtifact.from_payload),
        (scope.to_payload(), AuthorizationTestScope.from_payload),
    ):
        original["extra"] = True
        with pytest.raises(ShadowContractError):
            parser(original)

    with pytest.raises(ValueError):
        ShadowEvaluationArtifact(artifact_id=ARTIFACT_ID.upper(), evaluation_run_id=RUN_ID)
    invalid_scope = scope.to_payload()
    invalid_scope["environment_id"] = ENVIRONMENT_ID.upper()
    with pytest.raises(ShadowContractError):
        AuthorizationTestScope.from_payload(invalid_scope)


def test_real_data_shadow_forbids_live_head_issuance_binding() -> None:
    artifact = _artifact()

    assert artifact.mode is ShadowMode.SHADOW_ONLY
    assert artifact.execution_disposition is ExecutionDisposition.NOT_EXECUTABLE
    assert (
        artifact.persistence_boundary
        is ShadowPersistenceBoundary.ISOLATED_EVALUATION_ARTIFACT
    )
    assert artifact.s38_live_head_target is None
    assert artifact.s42_production_issuance_target is None
    assert artifact.s45_execution_binding_target is None
    assert artifact.live_planning_intent_success_target is None

    forbidden_targets = (
        "s38_live_head_target",
        "s42_production_issuance_target",
        "s45_execution_binding_target",
        "live_planning_intent_success_target",
    )
    for field_name in forbidden_targets:
        payload = artifact.to_payload()
        payload[field_name] = RUN_ID
        with pytest.raises(ShadowContractError, match="forbidden"):
            ShadowEvaluationArtifact.from_payload(payload)

    for field_name, invalid_value in (
        ("execution_disposition", "executable"),
        ("persistence_boundary", "daily_plan_heads"),
    ):
        payload = artifact.to_payload()
        payload[field_name] = invalid_value
        with pytest.raises(ShadowContractError):
            ShadowEvaluationArtifact.from_payload(payload)

    with pytest.raises(TypeError):
        ShadowEvaluationArtifact(  # type: ignore[call-arg]
            artifact_id=ARTIFACT_ID,
            evaluation_run_id=RUN_ID,
            s42_production_issuance_target=RUN_ID,
        )


def test_test_only_scope_requires_isolation() -> None:
    scope = _scope()

    assert scope.scope is AuthorizationScope.TEST_ONLY
    assert scope.actor.role is ActorRole.TEST
    assert scope.subject_boundary is IsolationBoundary.ISOLATED_NON_PRODUCTION
    assert scope.policy_boundary is IsolationBoundary.ISOLATED_NON_PRODUCTION
    assert scope.environment_boundary is IsolationBoundary.ISOLATED_NON_PRODUCTION
    assert scope.direct_write_allowed is False
    assert scope.t6_command_owner_guard_required is True
    assert scope.t7_command_owner_guard_required is True

    for role in (ActorRole.SUBJECT, ActorRole.ADMIN, ActorRole.EVALUATION):
        with pytest.raises(ValueError, match="ActorRole.TEST"):
            _scope(role)

    invalid_payloads: list[tuple[str, object]] = [
        ("subject_boundary", "production"),
        ("policy_boundary", "production"),
        ("environment_boundary", "production"),
        ("environment_boundary", "evaluation"),
        ("required_capability", "administer_production"),
        ("direct_write_allowed", True),
        ("t6_command_owner_guard_required", False),
        ("t7_command_owner_guard_required", False),
    ]
    for field_name, invalid_value in invalid_payloads:
        payload = scope.to_payload()
        payload[field_name] = invalid_value
        with pytest.raises(ShadowContractError):
            AuthorizationTestScope.from_payload(payload)

    for field_name in ("subject_id", "policy_id", "environment_id"):
        kwargs = {
            "actor": scope.actor,
            "subject_id": SUBJECT_ID,
            "policy_id": POLICY_ID,
            "environment_id": ENVIRONMENT_ID,
        }
        kwargs[field_name] = str(kwargs[field_name]).upper()
        with pytest.raises(ValueError):
            AuthorizationTestScope(
                actor=kwargs["actor"],  # type: ignore[arg-type]
                subject_id=kwargs["subject_id"],  # type: ignore[arg-type]
                policy_id=kwargs["policy_id"],  # type: ignore[arg-type]
                environment_id=kwargs["environment_id"],  # type: ignore[arg-type]
            )
