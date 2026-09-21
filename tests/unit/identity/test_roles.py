"""Executable checks for the role/capability contract."""

import json

import pytest

from kineticloop.identity import (
    CAPABILITY_MATRIX,
    IDENTITY_WIRE_SCHEMA,
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

IDENTITY_ID = "8c7d83ee-49db-4b2c-9df2-0b0f158c328f"


def identity(role: ActorRole) -> RoleIdentity:
    return RoleIdentity(identity_id=IDENTITY_ID, role=role)


def test_role_vocabulary_valid() -> None:
    assert tuple((role.name, role.value) for role in ActorRole) == (
        ("SUBJECT", "subject"),
        ("TEST", "test"),
        ("ADMIN", "admin"),
        ("EVALUATION", "evaluation"),
    )
    assert tuple((capability.name, capability.value) for capability in Capability) == (
        ("ACT_AS_PRODUCTION_SUBJECT", "act_as_production_subject"),
        ("RUN_TEST_SIMULATION", "run_test_simulation"),
        ("ADMINISTER_PRODUCTION", "administer_production"),
        ("RUN_ISOLATED_EVALUATION", "run_isolated_evaluation"),
    )


def test_capability_matrix_enforced() -> None:
    expected = {
        ActorRole.SUBJECT: frozenset({Capability.ACT_AS_PRODUCTION_SUBJECT}),
        ActorRole.TEST: frozenset({Capability.RUN_TEST_SIMULATION}),
        ActorRole.ADMIN: frozenset({Capability.ADMINISTER_PRODUCTION}),
        ActorRole.EVALUATION: frozenset({Capability.RUN_ISOLATED_EVALUATION}),
    }
    assert dict(CAPABILITY_MATRIX) == expected

    for role, capabilities in expected.items():
        actor = identity(role)
        assert actor.capabilities == capabilities
        for capability in Capability:
            assert has_capability(actor, capability) is (capability in capabilities)
            if capability in capabilities:
                assert require_capability(actor, capability) is actor
            else:
                with pytest.raises(CapabilityDenied):
                    require_capability(actor, capability)


@pytest.mark.parametrize("role", [ActorRole.TEST, ActorRole.EVALUATION])
def test_nonproduction_actor_rejected(role: ActorRole) -> None:
    actor = identity(role)

    assert not is_production_actor(actor)
    for production_capability in (
        Capability.ACT_AS_PRODUCTION_SUBJECT,
        Capability.ADMINISTER_PRODUCTION,
    ):
        with pytest.raises(CapabilityDenied):
            require_production_actor(actor, production_capability)


@pytest.mark.parametrize("role", [ActorRole.SUBJECT, ActorRole.ADMIN])
def test_production_actor_categories_still_require_exact_capability(role: ActorRole) -> None:
    actor = identity(role)
    exact_capability = (
        Capability.ACT_AS_PRODUCTION_SUBJECT
        if role is ActorRole.SUBJECT
        else Capability.ADMINISTER_PRODUCTION
    )
    other_capability = (
        Capability.ADMINISTER_PRODUCTION
        if role is ActorRole.SUBJECT
        else Capability.ACT_AS_PRODUCTION_SUBJECT
    )

    assert is_production_actor(actor)
    assert require_production_actor(actor, exact_capability) is actor
    with pytest.raises(CapabilityDenied):
        require_production_actor(actor, other_capability)
    assert has_capability(actor, Capability.ACT_AS_PRODUCTION_SUBJECT) is (
        role is ActorRole.SUBJECT
    )
    assert has_capability(actor, Capability.ADMINISTER_PRODUCTION) is (role is ActorRole.ADMIN)


def test_nonproduction_capability_rejected_at_production_boundary() -> None:
    with pytest.raises(ValueError, match="require a production capability"):
        require_production_actor(identity(ActorRole.TEST), Capability.RUN_TEST_SIMULATION)


def test_serialization_round_trip() -> None:
    for role in ActorRole:
        original = identity(role)
        serialized = original.to_json()
        restored = RoleIdentity.from_json(serialized)

        assert restored == original
        assert restored.capabilities == CAPABILITY_MATRIX[role]
        assert json.loads(serialized) == {
            "schema": IDENTITY_WIRE_SCHEMA,
            "identity_id": IDENTITY_ID,
            "role": role.value,
        }
        assert "capabilities" not in original.to_payload()


@pytest.mark.parametrize(
    "serialized",
    [
        '{"schema":"kineticloop-role-identity-v1","identity_id":"8c7d83ee-49db-4b2c-9df2-0b0f158c328f","role":"subject","capabilities":["administer_production"]}',
        '{"schema":"kineticloop-role-identity-v1","identity_id":"8c7d83ee-49db-4b2c-9df2-0b0f158c328f","role":"production"}',
        '{"schema":"kineticloop-role-identity-v1","identity_id":"8C7D83EE-49DB-4B2C-9DF2-0B0F158C328F","role":"subject"}',
        '{"schema":"kineticloop-role-identity-v1","identity_id":"8c7d83ee-49db-4b2c-9df2-0b0f158c328f","role":"test","role":"subject"}',
    ],
)
def test_serialization_rejects_escalating_or_ambiguous_input(serialized: str) -> None:
    with pytest.raises(IdentityContractError):
        RoleIdentity.from_json(serialized)


def test_identity_constructor_rejects_untyped_role() -> None:
    with pytest.raises(TypeError, match="role must be an ActorRole"):
        RoleIdentity(identity_id=IDENTITY_ID, role="subject")  # type: ignore[arg-type]
