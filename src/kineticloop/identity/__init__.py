"""Closed role and capability vocabulary for KineticLoop identities."""

from kineticloop.identity.roles import (
    CAPABILITY_MATRIX,
    IDENTITY_WIRE_SCHEMA,
    PRODUCTION_CAPABILITIES,
    ActorRole,
    Capability,
    CapabilityDenied,
    IdentityContractError,
    RoleIdentity,
    has_capability,
    is_production_actor,
    require_capability,
    require_production_actor,
)

__all__ = [
    "CAPABILITY_MATRIX",
    "IDENTITY_WIRE_SCHEMA",
    "PRODUCTION_CAPABILITIES",
    "ActorRole",
    "Capability",
    "CapabilityDenied",
    "IdentityContractError",
    "RoleIdentity",
    "has_capability",
    "is_production_actor",
    "require_capability",
    "require_production_actor",
]
