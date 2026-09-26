from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from kineticloop.contracts.artifacts import (
    ArtifactBindingKind,
    ArtifactDependencyError,
    ArtifactRegistration,
    ArtifactValiditySpec,
    require_artifact_references,
    validate_complete_dependency_closure,
)
from kineticloop.contracts.commands import RegisterArtifact, TransactionBoundary
from kineticloop.identity import ActorRole, Capability

ADMIN_ID = "00000000-0000-8000-8000-000000000001"
ARTIFACT_ID = "00000000-0000-8000-8000-000000000002"
DEPENDENCY_ID = "00000000-0000-8000-8000-000000000003"
TRANSITIVE_ID = "00000000-0000-8000-8000-000000000004"
RELEASE_ID = "00000000-0000-8000-8000-000000000005"


def validity() -> ArtifactValiditySpec:
    now = datetime(2026, 9, 26, tzinfo=UTC)
    return ArtifactValiditySpec(
        validity_kind="BOUNDED",
        valid_from=now,
        valid_until=now + timedelta(days=30),
        binding_kind=ArtifactBindingKind.EVALUATION_RELEASE,
        binding_id=RELEASE_ID,
    )


def registration_payload(*, role: ActorRole = ActorRole.ADMIN) -> dict[str, object]:
    spec = validity()
    return {
        "schema_version": "kineticloop-command-v1",
        "command_kind": "RegisterArtifact",
        "boundary": TransactionBoundary.REGISTRY_MANAGEMENT,
        "command_id": "00000000-0000-8000-8000-000000000006",
        "actor": {
            "schema": "kineticloop-role-identity-v1",
            "identity_id": ADMIN_ID,
            "role": role,
        },
        "idempotency_key": "register-model-1",
        "request_hash": "a" * 64,
        "subject_id": None,
        "explicit_scope": "global:safety-registry",
        "artifact_id": ARTIFACT_ID,
        "artifact_kind": "MODEL",
        "content_hash": "b" * 64,
        "dependency_ids": (DEPENDENCY_ID, TRANSITIVE_ID),
        "validity_spec_hash": spec.sha256(),
    }


def test_artifact_registration_requires_management_capability() -> None:
    command = RegisterArtifact.model_validate(registration_payload())
    assert command.actor.capability is Capability.ADMINISTER_PRODUCTION
    ArtifactRegistration(
        command=command,
        artifact_identity="planner-model",
        artifact_version="1",
        validity=validity(),
    )

    for role in (ActorRole.SUBJECT, ActorRole.TEST):
        with pytest.raises(ValidationError, match="authenticated admin actor"):
            RegisterArtifact.model_validate(registration_payload(role=role))

    asserted = registration_payload()
    asserted_actor = dict(asserted["actor"])  # type: ignore[arg-type]
    asserted_actor["capability"] = "ADMINISTER_PRODUCTION"
    asserted["actor"] = asserted_actor
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RegisterArtifact.model_validate(asserted)


def test_artifact_dependency_closure_required() -> None:
    graph = {
        DEPENDENCY_ID: (TRANSITIVE_ID,),
        TRANSITIVE_ID: (),
    }
    assert validate_complete_dependency_closure(
        (DEPENDENCY_ID, TRANSITIVE_ID), graph
    ) == tuple(sorted((DEPENDENCY_ID, TRANSITIVE_ID)))
    with pytest.raises(ArtifactDependencyError, match="incomplete"):
        validate_complete_dependency_closure((DEPENDENCY_ID,), graph)


def test_t3_t6_t7_require_artifact_refs() -> None:
    for boundary in (
        TransactionBoundary.T3,
        TransactionBoundary.T6,
        TransactionBoundary.T7,
    ):
        assert require_artifact_references(
            boundary, (ARTIFACT_ID, DEPENDENCY_ID)
        ) == (ARTIFACT_ID, DEPENDENCY_ID)
        with pytest.raises(ValueError, match="exact unique"):
            require_artifact_references(boundary, ())
        with pytest.raises(ValueError, match="exact unique"):
            require_artifact_references(boundary, (ARTIFACT_ID, ARTIFACT_ID))
