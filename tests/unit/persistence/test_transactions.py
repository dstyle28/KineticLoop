from __future__ import annotations

from typing import get_args

from kineticloop.contracts.commands import PUBLIC_COMMAND_MODELS
from kineticloop.persistence.transactions import (
    CATALOG_RELEASE_BOUNDARIES,
    MUTATION_CAPABILITY_MATRIX,
    TRANSACTION_OWNER_MATRIX,
    Boundary,
)


def test_transaction_owner_matrix_complete() -> None:
    public_commands = {
        get_args(model.model_fields["command_kind"].annotation)[0]
        for model in PUBLIC_COMMAND_MODELS
    }
    assert set(TRANSACTION_OWNER_MATRIX) == public_commands
    for command_kind, specification in TRANSACTION_OWNER_MATRIX.items():
        assert command_kind
        assert specification.owner
        assert "+" not in specification.owner
        assert specification.mutation_surfaces
        assert len(set(specification.mutation_surfaces)) == len(specification.mutation_surfaces)
    assert {
        command
        for command, specification in TRANSACTION_OWNER_MATRIX.items()
        if specification.registry_required
    } == {
        "PublishManifest",
        "CommitBundle",
        "Reauthorize",
        "StartSession",
        "ResumeSession",
        "ContinueSession",
    }


def test_every_public_owner_has_explicit_non_infrastructure_dml_capabilities() -> None:
    assert set(MUTATION_CAPABILITY_MATRIX) == set(TRANSACTION_OWNER_MATRIX)
    for command_kind, specification in TRANSACTION_OWNER_MATRIX.items():
        rules = MUTATION_CAPABILITY_MATRIX[command_kind]
        assert rules, command_kind
        for (logical_id, operation), columns in rules.items():
            assert logical_id in specification.mutation_surfaces
            assert logical_id not in {"S02", "S03", "S04"}
            assert operation in {"insert", "update"}
            assert columns
    assert MUTATION_CAPABILITY_MATRIX["RenewLease"][("S27", "update")] == {
        "lease_expires_at",
        "typed_payload",
    }
    assert ("S29", "update") not in MUTATION_CAPABILITY_MATRIX["AcquireLease"]
    assert ("S29", "update") not in MUTATION_CAPABILITY_MATRIX["RenewLease"]
    assert "S29" not in TRANSACTION_OWNER_MATRIX["AcquireLease"].mutation_surfaces
    assert "S29" not in TRANSACTION_OWNER_MATRIX["RenewLease"].mutation_surfaces
    assert "S31" not in TRANSACTION_OWNER_MATRIX["CommitBundle"].mutation_surfaces
    assert MUTATION_CAPABILITY_MATRIX["PermitDispatch"][("S31", "update")] == {
        "status",
        "settlement_revision",
        "typed_payload",
    }
    assert "session_identity" not in MUTATION_CAPABILITY_MATRIX["StartSession"][("S44", "update")]
    for command in ("StartSession", "ResumeSession", "ContinueSession"):
        assert MUTATION_CAPABILITY_MATRIX[command][("S01", "update")] == {
            "execution_basis_event_id"
        }
    assert ("S45", "insert") not in MUTATION_CAPABILITY_MATRIX["ContinueSession"]
    for rules in MUTATION_CAPABILITY_MATRIX.values():
        for (logical_id, operation), columns in rules.items():
            if operation == "insert":
                assert "recorded_at" not in columns, logical_id
                assert "known_at" not in columns, logical_id


def test_catalog_mapping_and_release_owner_boundaries_complete() -> None:
    assert CATALOG_RELEASE_BOUNDARIES == {
        "ExerciseCatalogService.PublishRevision": {
            "writes": ("S19",),
            "adoption_owner": "T2 classification/invalidation",
        },
        "ExerciseMappingService.DecideMapping": {
            "writes": ("S20",),
            "adoption_owner": "explicit factset selection",
        },
        "ReleaseEvaluationService.RecordRelease": {
            "writes": ("S48",),
            "boundary": Boundary.EXTERNAL,
            "activation_owner": "T2 user activation",
        },
        "DecisionPublicationService.PublishManifest": {
            "consumes_exact": ("S19", "S20", "S48"),
            "may_adopt_or_activate": False,
        },
    }
    publish = TRANSACTION_OWNER_MATRIX["PublishManifest"]
    assert publish.boundary is Boundary.T3
    assert "S19" not in publish.mutation_surfaces
    assert "S20" not in publish.mutation_surfaces
    assert "S48" not in publish.mutation_surfaces
