"""HG040 exact upstream capability prerequisite boundaries fail closed."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "upstream_validator", ROOT / "tools/harness/validate_harness.py"
)
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
TASKS = {t["id"]: t for t in json.loads((ROOT / v.BACKLOG).read_text())["tasks"]}


def test_exact_upstream_scope_and_dependency() -> None:
    t = TASKS["KL-078"]
    assert t["status"] == "NOT_STARTED" and not t["evidence_refs"]
    assert t["write_paths"] == [
        "src/kineticloop/persistence/transactions.py",
        "src/kineticloop/persistence/preparation.py",
        "tests/unit/persistence/test_preparation.py",
        "tests/db/test_preparation.py",
        "docs/contracts/preparation.md",
    ]
    assert t["resource_keys"] == ["transaction_interfaces"]
    assert t["requirements_covered"] == []
    assert "KL-078" in TASKS["KL-076"]["depends_on"]
    assert v.m3_next_wave_definition_errors(t) == []
    assert v.packet_errors(t, (ROOT / "docs/exec-plans/active/KL-078.md").read_text()) == []
    for name in ("KL-075", "KL-076", "KL-077"):
        assert set(t["resource_keys"]) & set(TASKS[name]["resource_keys"])
    assert not set(t["write_paths"]) & set(TASKS["KL-026"]["write_paths"])


@pytest.mark.parametrize(
    "paths",
    [
        ["src/kineticloop/persistence/**"],
        ["migrations/versions/new.py"],
        [".github/workflows/new.yml"],
        ["src/kineticloop/contracts/commands.py"],
        ["src/kineticloop/persistence/metadata.py"],
        ["tests/db/helpers.py"],
        ["src/kineticloop/persistence/factsets.py"],
        ["src/kineticloop/persistence/protocol_execution.py"],
    ],
)
def test_undeclared_helper_or_permission_expansion_denied(paths: list[str]) -> None:
    task = copy.deepcopy(TASKS["KL-078"])
    task["write_paths"] += paths
    assert v.m3_next_wave_definition_errors(task) == ["m3-next-wave-definition:KL-078"]


@pytest.mark.parametrize(
    "phrase",
    [
        "server-owned revision",
        "same-subject SEALED S15",
        "S22 complete dependency closure",
        "READY/PUBLISHED candidate mutation",
        "no S01/registry coordination",
        "No output SQL seeds",
        "actual CanonicalViewService",
        "first7 lowercase hex",
        "before every destructive entrypoint",
        "No historical test/log reuse as new PASS",
        "existing unchanged hosted CI",
    ],
)
def test_upstream_oracle_boundary_weakening_denied(phrase: str) -> None:
    text = (ROOT / "docs/exec-plans/active/KL-078.md").read_text()
    assert phrase in text
    assert "m3-next-wave-packet:KL-078" in v.packet_errors(
        TASKS["KL-078"], text.replace(phrase, "bypass", 1)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("depends_on", []),
        ("status", "DONE"),
        ("requirements_covered", ["I01@DC"]),
        ("resource_keys", []),
        ("review_requirements", ["GENERAL"]),
        ("check_contracts", []),
        ("entry_conditions", []),
        ("environment_requirements", []),
    ],
)
def test_prerequisite_or_evidence_weakening_denied(field: str, value: object) -> None:
    task = copy.deepcopy(TASKS["KL-078"])
    task[field] = value
    assert v.m3_next_wave_definition_errors(task) == ["m3-next-wave-definition:KL-078"]
