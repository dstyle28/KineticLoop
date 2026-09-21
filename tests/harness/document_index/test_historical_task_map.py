"""Namespaced historical task mapping checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import write_json

from kineticloop.harness.documents import HistoricalTaskMap, ValidationError


def test_historical_task_map_resolves_both_namespaces(historical_root: Path) -> None:
    assert HistoricalTaskMap.validate(historical_root) == 10


def test_unqualified_historical_identity_is_rejected(historical_root: Path) -> None:
    path = historical_root / "HISTORICAL_TASK_ID_MAP.json"
    mapping = json.loads(path.read_text())
    mapping["reused_display_ids"][0]["legacy_identity"] = "KL-062"
    write_json(path, mapping)

    with pytest.raises(ValidationError, match="historical-legacy-identity:KL-062"):
        HistoricalTaskMap.validate(historical_root)


def test_reused_display_id_must_match_across_namespaces(historical_root: Path) -> None:
    path = historical_root / "HISTORICAL_TASK_ID_MAP.json"
    mapping = json.loads(path.read_text())
    mapping["reused_display_ids"][0]["current_identity"] = "harness-backlog-v0.2/KL-052"
    mapping["reused_display_ids"][0]["current_title"] = (
        "Apple HealthKit iOS bridge: anchored sync, deletions, provenance"
    )
    write_json(path, mapping)

    with pytest.raises(ValidationError, match="historical-reused-display-id"):
        HistoricalTaskMap.validate(historical_root)


def test_mapping_titles_are_bound_to_source_backlogs(historical_root: Path) -> None:
    path = historical_root / "HISTORICAL_TASK_ID_MAP.json"
    mapping = json.loads(path.read_text())
    mapping["semantic_migrations"][0]["legacy_title"] = "Invented historical meaning"
    write_json(path, mapping)

    with pytest.raises(ValidationError, match="historical-legacy-title"):
        HistoricalTaskMap.validate(historical_root)


def test_current_namespace_is_anchored_to_declared_backlog(historical_root: Path) -> None:
    path = historical_root / "HISTORICAL_TASK_ID_MAP.json"
    mapping = json.loads(path.read_text())
    mapping["current_namespace"] = "forged-backlog-v9"
    current_source = next(
        source
        for source in mapping["namespace_sources"]
        if source["path"] == "KineticLoop_Harness_Backlog_v0.2.json"
    )
    current_source["namespace"] = "forged-backlog-v9"
    for group in ("reused_display_ids", "semantic_migrations"):
        for entry in mapping[group]:
            entry["current_identity"] = entry["current_identity"].replace(
                "harness-backlog-v0.2/", "forged-backlog-v9/"
            )
    write_json(path, mapping)

    with pytest.raises(ValidationError, match="historical-current-namespace"):
        HistoricalTaskMap.validate(historical_root)


def test_legacy_namespace_source_cannot_be_fabricated(historical_root: Path) -> None:
    path = historical_root / "HISTORICAL_TASK_ID_MAP.json"
    mapping = json.loads(path.read_text())
    legacy_source = next(
        source
        for source in mapping["namespace_sources"]
        if source["namespace"] == "project-backlog-v0.3"
    )
    legacy_source["namespace"] = "forged-legacy-v9"
    mapping["legacy_namespaces"] = ["forged-legacy-v9"]
    for group in ("reused_display_ids", "semantic_migrations"):
        for entry in mapping[group]:
            entry["legacy_identity"] = entry["legacy_identity"].replace(
                "project-backlog-v0.3/", "forged-legacy-v9/"
            )
    write_json(path, mapping)

    with pytest.raises(ValidationError, match="historical-authority-sources"):
        HistoricalTaskMap.validate(historical_root)
