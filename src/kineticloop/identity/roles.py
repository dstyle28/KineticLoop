"""Role categories and their non-escalating capability contract.

These capabilities classify identities; they do not replace authentication,
command-specific authorization, policy, scope, or transaction guards. Role
assignments must be bound by a trusted service before this contract is used at
an authorization boundary.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Self

from kineticloop.primitives import canonical_id, canonical_json

IDENTITY_WIRE_SCHEMA: Final = "kineticloop-role-identity-v1"


class ActorRole(StrEnum):
    """Closed identity-role vocabulary with stable wire values."""

    SUBJECT = "subject"
    TEST = "test"
    ADMIN = "admin"
    EVALUATION = "evaluation"


class Capability(StrEnum):
    """Coarse role capabilities; never a command authorization by itself."""

    ACT_AS_PRODUCTION_SUBJECT = "act_as_production_subject"
    RUN_TEST_SIMULATION = "run_test_simulation"
    ADMINISTER_PRODUCTION = "administer_production"
    RUN_ISOLATED_EVALUATION = "run_isolated_evaluation"


CAPABILITY_MATRIX: Final[Mapping[ActorRole, frozenset[Capability]]] = MappingProxyType(
    {
        ActorRole.SUBJECT: frozenset({Capability.ACT_AS_PRODUCTION_SUBJECT}),
        ActorRole.TEST: frozenset({Capability.RUN_TEST_SIMULATION}),
        ActorRole.ADMIN: frozenset({Capability.ADMINISTER_PRODUCTION}),
        ActorRole.EVALUATION: frozenset({Capability.RUN_ISOLATED_EVALUATION}),
    }
)

PRODUCTION_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {
        Capability.ACT_AS_PRODUCTION_SUBJECT,
        Capability.ADMINISTER_PRODUCTION,
    }
)


class IdentityContractError(ValueError):
    """Raised when an identity wire representation violates the contract."""


class CapabilityDenied(PermissionError):
    """Raised when an identity's bound role lacks a requested capability."""


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise IdentityContractError(f"duplicate identity field: {key}")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class RoleIdentity:
    """A service-bound identity whose capabilities are derived from its role."""

    identity_id: str
    role: ActorRole

    def __post_init__(self) -> None:
        if type(self.identity_id) is not str:
            raise TypeError("identity_id must be a canonical identifier string")
        if type(self.role) is not ActorRole:
            raise TypeError("role must be an ActorRole")
        canonical_id(self.identity_id)

    @property
    def capabilities(self) -> frozenset[Capability]:
        """Return the immutable capabilities assigned to the bound role."""

        return CAPABILITY_MATRIX[self.role]

    def to_payload(self) -> dict[str, str]:
        """Return the versioned wire payload without caller-asserted capabilities."""

        return {
            "schema": IDENTITY_WIRE_SCHEMA,
            "identity_id": self.identity_id,
            "role": self.role.value,
        }

    def to_json(self) -> str:
        """Serialize to deterministic canonical JSON."""

        return canonical_json(self.to_payload())

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        """Parse a strict versioned payload and derive its capabilities."""

        if type(payload) is not dict:
            raise IdentityContractError("identity payload must be an object")
        expected_fields = {"schema", "identity_id", "role"}
        if set(payload) != expected_fields:
            raise IdentityContractError("identity payload fields must be schema, identity_id, role")

        schema = payload["schema"]
        identity_id = payload["identity_id"]
        role_value = payload["role"]
        if type(schema) is not str or schema != IDENTITY_WIRE_SCHEMA:
            raise IdentityContractError("unsupported identity schema")
        if type(identity_id) is not str:
            raise IdentityContractError("identity_id must be a canonical identifier string")
        if type(role_value) is not str:
            raise IdentityContractError("role must be a string")

        try:
            role = ActorRole(role_value)
            return cls(identity_id=identity_id, role=role)
        except ValueError as error:
            raise IdentityContractError("identity payload contains an invalid value") from error

    @classmethod
    def from_json(cls, serialized: str) -> Self:
        """Parse strict JSON without accepting duplicate or extra fields."""

        if type(serialized) is not str:
            raise TypeError("serialized identity must be a string")
        try:
            payload = json.loads(serialized, object_pairs_hook=_strict_object)
        except IdentityContractError:
            raise
        except (json.JSONDecodeError, TypeError) as error:
            raise IdentityContractError("identity must be valid JSON") from error
        return cls.from_payload(payload)


def _require_identity(identity: RoleIdentity) -> None:
    if type(identity) is not RoleIdentity:
        raise TypeError("identity must be a RoleIdentity")


def has_capability(identity: RoleIdentity, capability: Capability) -> bool:
    """Return whether the immutable matrix grants *capability* to *identity*."""

    _require_identity(identity)
    if type(capability) is not Capability:
        raise TypeError("capability must be a Capability")
    return capability in identity.capabilities


def require_capability(identity: RoleIdentity, capability: Capability) -> RoleIdentity:
    """Return *identity* only when the role matrix grants *capability*."""

    if not has_capability(identity, capability):
        raise CapabilityDenied(f"role {identity.role.value} lacks capability {capability.value}")
    return identity


def is_production_actor(identity: RoleIdentity) -> bool:
    """Return whether the role is in a production actor category.

    This is a category check only. A caller must still enforce the exact
    subject/admin capability and every command-specific authorization guard.
    """

    _require_identity(identity)
    return not identity.capabilities.isdisjoint(PRODUCTION_CAPABILITIES)


def require_production_actor(
    identity: RoleIdentity, capability: Capability
) -> RoleIdentity:
    """Require one exact production capability at an actor boundary.

    Requiring the specific subject/admin capability prevents this coarse actor
    classification from becoming a convenience bypass between production roles.
    """

    if type(capability) is not Capability:
        raise TypeError("capability must be a Capability")
    if capability not in PRODUCTION_CAPABILITIES:
        raise ValueError("production actor boundaries require a production capability")
    return require_capability(identity, capability)
