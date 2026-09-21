from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from kineticloop.acceptance import RegistryValidationError, build_registry

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/fixtures/acceptance/requirement_registry.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_source(root: Path, relative_path: str, value: dict[str, Any]) -> str:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(rendered, encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_current_sources(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    requirement_set = copy.deepcopy(_load_json(ROOT / "CURRENT_REQUIREMENT_SET.json"))
    acceptance = copy.deepcopy(_load_json(ROOT / "KineticLoop_Acceptance_Spec_v1.2.2.json"))
    integration = copy.deepcopy(_load_json(ROOT / "KineticLoop_Integration_Acceptance_v0.1.json"))
    acceptance_path = "KineticLoop_Acceptance_Spec_v1.2.2.json"
    integration_path = "KineticLoop_Integration_Acceptance_v0.1.json"
    requirement_set["sources"] = [
        {
            "path": acceptance_path,
            "sha256": _write_source(tmp_path, acceptance_path, acceptance),
        },
        {
            "path": integration_path,
            "sha256": _write_source(tmp_path, integration_path, integration),
        },
    ]
    _write_source(tmp_path, "CURRENT_REQUIREMENT_SET.json", requirement_set)
    return requirement_set, acceptance, integration


def _rewrite_sources(
    root: Path,
    requirement_set: dict[str, Any],
    acceptance: dict[str, Any],
    integration: dict[str, Any],
) -> None:
    requirement_set["sources"][0]["sha256"] = _write_source(
        root, requirement_set["sources"][0]["path"], acceptance
    )
    requirement_set["sources"][1]["sha256"] = _write_source(
        root, requirement_set["sources"][1]["path"], integration
    )
    _write_source(root, "CURRENT_REQUIREMENT_SET.json", requirement_set)


def test_requirement_sources_parse() -> None:
    registry = build_registry(ROOT)
    fixture = _load_json(FIXTURE)

    assert registry.requirement_set_id == fixture["requirement_set_id"]
    assert registry.to_dict() == fixture
    assert {binding["kind"] for binding in registry.source_bindings} == {
        "acceptance",
        "integration",
    }


def test_obligation_ids_unique(tmp_path: Path) -> None:
    registry = build_registry(ROOT)
    ids = [obligation.obligation_id for obligation in registry.obligations]
    assert len(ids) == len(set(ids))

    requirement_set, acceptance, integration = _copy_current_sources(tmp_path)
    acceptance["original_layer_obligations"].append(
        copy.deepcopy(acceptance["original_layer_obligations"][0])
    )
    _rewrite_sources(tmp_path, requirement_set, acceptance, integration)
    with pytest.raises(RegistryValidationError, match="duplicate"):
        build_registry(tmp_path)


def test_all_expected_layers_registered(tmp_path: Path) -> None:
    registry = build_registry(ROOT)
    originals = [item for item in registry.obligations if item.kind == "ORIGINAL"]
    assert len(originals) == 67
    assert all(item.layer in item.required_layers for item in originals)
    assert len([item for item in registry.obligations if item.kind == "BOUNDARY"]) == 18
    assert len([item for item in registry.obligations if item.kind == "INTERLEAVING"]) == 9

    requirement_set, acceptance, integration = _copy_current_sources(tmp_path)
    acceptance["original_tests"][0]["layers"].pop()
    _rewrite_sources(tmp_path, requirement_set, acceptance, integration)
    with pytest.raises(RegistryValidationError, match="missing=.*E01@E2E"):
        build_registry(tmp_path)


def test_default_status_not_run() -> None:
    registry = build_registry(ROOT)
    fixture = registry.to_dict()

    assert fixture["status"] == "NOT_RUN"
    assert all(item.status == "NOT_RUN" for item in registry.obligations)
    assert {item["status"] for item in fixture["obligations"]} == {"NOT_RUN"}
    assert "PASS" not in {item["status"] for item in fixture["obligations"]}


def test_integration_obligations_registered(tmp_path: Path) -> None:
    registry = build_registry(ROOT)
    integrations = [
        item.obligation_id for item in registry.obligations if item.kind == "INTEGRATION"
    ]
    expected = _load_json(ROOT / "CURRENT_REQUIREMENT_SET.json")["obligations"][
        "integration_layer_obligations"
    ]
    assert integrations == expected
    assert len(integrations) == 20

    requirement_set, acceptance, integration = _copy_current_sources(tmp_path)
    integration["requirements"][0]["layers"].pop()
    _rewrite_sources(tmp_path, requirement_set, acceptance, integration)
    with pytest.raises(RegistryValidationError, match="missing=.*INT-A01@E2E"):
        build_registry(tmp_path)
