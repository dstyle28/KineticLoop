"""Fail-closed contracts separating shadow evaluation from test authorization.

These immutable values are inputs and artifacts only. They do not write storage,
issue authorization, bind execution, mark a live planning intent successful, or
replace the T6/T7 command-owner and transaction guards.
"""

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Self

from kineticloop.identity import (
    ActorRole,
    Capability,
    IdentityContractError,
    RoleIdentity,
    require_capability,
)
from kineticloop.primitives import canonical_id, canonical_json

SHADOW_ARTIFACT_WIRE_SCHEMA: Final = "kineticloop-shadow-evaluation-artifact-v1"
TEST_ONLY_SCOPE_WIRE_SCHEMA: Final = "kineticloop-test-only-authorization-scope-v1"


class ShadowMode(StrEnum):
    """Closed operating mode for artifacts created from real-data shadow runs."""

    SHADOW_ONLY = "shadow_only"


class ExecutionDisposition(StrEnum):
    """Closed execution disposition for real-data shadow artifacts."""

    NOT_EXECUTABLE = "not_executable"


class ShadowPersistenceBoundary(StrEnum):
    """The only persistence boundary exposed to real-data shadow."""

    ISOLATED_EVALUATION_ARTIFACT = "isolated_evaluation_artifact"


class AuthorizationScope(StrEnum):
    """Closed scope admitted by the test simulation contract."""

    TEST_ONLY = "test_only"


class IsolationBoundary(StrEnum):
    """Closed resource classification admitted by TEST_ONLY."""

    ISOLATED_NON_PRODUCTION = "isolated_non_production"


class ShadowContractError(ValueError):
    """Raised when serialized shadow/test input violates the contract."""


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ShadowContractError(f"duplicate shadow/test field: {key}")
        result[key] = value
    return result


def _parse_json(serialized: str, contract_name: str) -> object:
    if type(serialized) is not str:
        raise TypeError(f"serialized {contract_name} must be a string")
    try:
        return json.loads(serialized, object_pairs_hook=_strict_object)
    except ShadowContractError:
        raise
    except (json.JSONDecodeError, TypeError) as error:
        raise ShadowContractError(f"{contract_name} must be valid JSON") from error


def _require_payload(payload: object, expected_fields: set[str], contract_name: str) -> None:
    if type(payload) is not dict:
        raise ShadowContractError(f"{contract_name} payload must be an object")
    if set(payload) != expected_fields:
        raise ShadowContractError(f"{contract_name} payload fields do not match the schema")


def _require_canonical_identifier(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a canonical identifier string")
    return canonical_id(value)


def _require_wire_constant(
    payload: dict[str, object], field_name: str, expected: StrEnum
) -> None:
    if type(payload[field_name]) is not str or payload[field_name] != expected.value:
        raise ShadowContractError(f"{field_name} must be {expected.value}")


@dataclass(frozen=True, slots=True)
class ShadowEvaluationArtifact:
    """A real-data shadow artifact with no live-state write target."""

    artifact_id: str
    evaluation_run_id: str
    mode: ShadowMode = field(default=ShadowMode.SHADOW_ONLY, init=False)
    execution_disposition: ExecutionDisposition = field(
        default=ExecutionDisposition.NOT_EXECUTABLE, init=False
    )
    persistence_boundary: ShadowPersistenceBoundary = field(
        default=ShadowPersistenceBoundary.ISOLATED_EVALUATION_ARTIFACT, init=False
    )

    def __post_init__(self) -> None:
        _require_canonical_identifier(self.artifact_id, "artifact_id")
        _require_canonical_identifier(self.evaluation_run_id, "evaluation_run_id")

    @property
    def s38_live_head_target(self) -> None:
        return None

    @property
    def s42_production_issuance_target(self) -> None:
        return None

    @property
    def s45_execution_binding_target(self) -> None:
        return None

    @property
    def live_planning_intent_success_target(self) -> None:
        return None

    def to_payload(self) -> dict[str, object]:
        """Return the strict wire payload with explicit absent live targets."""

        return {
            "schema": SHADOW_ARTIFACT_WIRE_SCHEMA,
            "artifact_id": self.artifact_id,
            "evaluation_run_id": self.evaluation_run_id,
            "mode": self.mode.value,
            "execution_disposition": self.execution_disposition.value,
            "persistence_boundary": self.persistence_boundary.value,
            "s38_live_head_target": None,
            "s42_production_issuance_target": None,
            "s45_execution_binding_target": None,
            "live_planning_intent_success_target": None,
        }

    def to_json(self) -> str:
        """Serialize to deterministic canonical JSON."""

        return canonical_json(self.to_payload())

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        """Parse a strict artifact and reject every live-state target."""

        expected_fields = {
            "schema",
            "artifact_id",
            "evaluation_run_id",
            "mode",
            "execution_disposition",
            "persistence_boundary",
            "s38_live_head_target",
            "s42_production_issuance_target",
            "s45_execution_binding_target",
            "live_planning_intent_success_target",
        }
        _require_payload(payload, expected_fields, "shadow artifact")
        assert type(payload) is dict
        if payload["schema"] != SHADOW_ARTIFACT_WIRE_SCHEMA:
            raise ShadowContractError("unsupported shadow artifact schema")
        _require_wire_constant(payload, "mode", ShadowMode.SHADOW_ONLY)
        _require_wire_constant(
            payload, "execution_disposition", ExecutionDisposition.NOT_EXECUTABLE
        )
        _require_wire_constant(
            payload,
            "persistence_boundary",
            ShadowPersistenceBoundary.ISOLATED_EVALUATION_ARTIFACT,
        )
        for field_name in (
            "s38_live_head_target",
            "s42_production_issuance_target",
            "s45_execution_binding_target",
            "live_planning_intent_success_target",
        ):
            if payload[field_name] is not None:
                raise ShadowContractError(f"{field_name} is forbidden for real-data shadow")
        try:
            return cls(
                artifact_id=_require_canonical_identifier(payload["artifact_id"], "artifact_id"),
                evaluation_run_id=_require_canonical_identifier(
                    payload["evaluation_run_id"], "evaluation_run_id"
                ),
            )
        except (TypeError, ValueError) as error:
            raise ShadowContractError("shadow artifact contains an invalid identifier") from error

    @classmethod
    def from_json(cls, serialized: str) -> Self:
        return cls.from_payload(_parse_json(serialized, "shadow artifact"))


@dataclass(frozen=True, slots=True)
class TestOnlyAuthorizationScope:
    """Guarded T6/T7 input for an explicitly isolated test simulation.

    This value never grants a direct write. A later command owner must still
    authenticate the identity and enforce every normal T6 or T7 guard.
    """

    actor: RoleIdentity
    subject_id: str
    policy_id: str
    environment_id: str
    scope: AuthorizationScope = field(default=AuthorizationScope.TEST_ONLY, init=False)
    subject_boundary: IsolationBoundary = field(
        default=IsolationBoundary.ISOLATED_NON_PRODUCTION, init=False
    )
    policy_boundary: IsolationBoundary = field(
        default=IsolationBoundary.ISOLATED_NON_PRODUCTION, init=False
    )
    environment_boundary: IsolationBoundary = field(
        default=IsolationBoundary.ISOLATED_NON_PRODUCTION, init=False
    )

    def __post_init__(self) -> None:
        if type(self.actor) is not RoleIdentity:
            raise TypeError("actor must be an exact RoleIdentity")
        if self.actor.role is not ActorRole.TEST:
            raise ValueError("TEST_ONLY requires ActorRole.TEST")
        require_capability(self.actor, Capability.RUN_TEST_SIMULATION)
        _require_canonical_identifier(self.subject_id, "subject_id")
        _require_canonical_identifier(self.policy_id, "policy_id")
        _require_canonical_identifier(self.environment_id, "environment_id")

    @property
    def direct_write_allowed(self) -> bool:
        return False

    @property
    def t6_command_owner_guard_required(self) -> bool:
        return True

    @property
    def t7_command_owner_guard_required(self) -> bool:
        return True

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": TEST_ONLY_SCOPE_WIRE_SCHEMA,
            "actor": self.actor.to_payload(),
            "subject_id": self.subject_id,
            "policy_id": self.policy_id,
            "environment_id": self.environment_id,
            "scope": self.scope.value,
            "subject_boundary": self.subject_boundary.value,
            "policy_boundary": self.policy_boundary.value,
            "environment_boundary": self.environment_boundary.value,
            "required_capability": Capability.RUN_TEST_SIMULATION.value,
            "direct_write_allowed": False,
            "t6_command_owner_guard_required": True,
            "t7_command_owner_guard_required": True,
        }

    def to_json(self) -> str:
        return canonical_json(self.to_payload())

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        expected_fields = {
            "schema",
            "actor",
            "subject_id",
            "policy_id",
            "environment_id",
            "scope",
            "subject_boundary",
            "policy_boundary",
            "environment_boundary",
            "required_capability",
            "direct_write_allowed",
            "t6_command_owner_guard_required",
            "t7_command_owner_guard_required",
        }
        _require_payload(payload, expected_fields, "TEST_ONLY scope")
        assert type(payload) is dict
        if payload["schema"] != TEST_ONLY_SCOPE_WIRE_SCHEMA:
            raise ShadowContractError("unsupported TEST_ONLY scope schema")
        _require_wire_constant(payload, "scope", AuthorizationScope.TEST_ONLY)
        for field_name in (
            "subject_boundary",
            "policy_boundary",
            "environment_boundary",
        ):
            _require_wire_constant(
                payload, field_name, IsolationBoundary.ISOLATED_NON_PRODUCTION
            )
        if payload["required_capability"] != Capability.RUN_TEST_SIMULATION.value:
            raise ShadowContractError("TEST_ONLY requires RUN_TEST_SIMULATION")
        if payload["direct_write_allowed"] is not False:
            raise ShadowContractError("TEST_ONLY cannot grant direct-write permission")
        if payload["t6_command_owner_guard_required"] is not True:
            raise ShadowContractError("TEST_ONLY cannot omit the T6 command-owner guard")
        if payload["t7_command_owner_guard_required"] is not True:
            raise ShadowContractError("TEST_ONLY cannot omit the T7 command-owner guard")
        try:
            actor = RoleIdentity.from_payload(payload["actor"])
            return cls(
                actor=actor,
                subject_id=_require_canonical_identifier(payload["subject_id"], "subject_id"),
                policy_id=_require_canonical_identifier(payload["policy_id"], "policy_id"),
                environment_id=_require_canonical_identifier(
                    payload["environment_id"], "environment_id"
                ),
            )
        except (IdentityContractError, TypeError, ValueError) as error:
            raise ShadowContractError("TEST_ONLY scope contains an invalid binding") from error

    @classmethod
    def from_json(cls, serialized: str) -> Self:
        return cls.from_payload(_parse_json(serialized, "TEST_ONLY scope"))
