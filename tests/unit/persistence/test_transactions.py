from __future__ import annotations

from typing import get_args

from kineticloop.contracts.commands import PUBLIC_COMMAND_MODELS
from kineticloop.persistence.transactions import (
    CATALOG_RELEASE_BOUNDARIES,
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
        assert len(set(specification.mutation_surfaces)) == len(
            specification.mutation_surfaces
        )
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
