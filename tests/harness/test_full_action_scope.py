"""HG041 bounded upstream task, immutable prerequisites and representation audit."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("full_action_validator", ROOT / "tools/harness/validate_harness.py")
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
TASKS = {t["id"]: t for t in json.loads((ROOT / v.BACKLOG).read_text())["tasks"]}


def test_exact_producer_consumer_scope() -> None:
    task = TASKS["KL-079"]
    assert task["status"] == "NOT_STARTED" and task["evidence_refs"] == []
    assert task["requirements_covered"] == []
    assert task["write_paths"] == [
        "src/kineticloop/workflow/deterministic_planning.py",
        "src/kineticloop/persistence/deterministic_planning.py",
        "src/kineticloop/persistence/transactions.py",
        "tests/unit/workflow/test_full_action_preparation.py",
        "tests/db/test_full_action_preparation.py",
        "tests/fixtures/full_action_preparation.json",
        "docs/contracts/full_action_preparation.md",
    ]
    assert task["resource_keys"] == ["transaction_interfaces", "user_coordination"]
    assert "KL-079" in TASKS["KL-077"]["depends_on"]
    assert "KL-077" in TASKS["KL-027"]["depends_on"]
    assert "KL-077" not in task["depends_on"] and "KL-027" not in task["depends_on"]
    for name in ("KL-077", "KL-079"):
        assert v.m3_next_wave_definition_errors(TASKS[name]) == []
        assert v.packet_errors(TASKS[name], (ROOT / f"docs/exec-plans/active/{name}.md").read_text()) == []


@pytest.mark.parametrize("path", [
    "src/kineticloop/persistence/**", "migrations/versions/new.py", ".github/workflows/new.yml",
    "src/kineticloop/contracts/commands.py", "src/kineticloop/persistence/planning_progress.py",
    "src/kineticloop/workflow/planning_progress.py", "src/kineticloop/persistence/metadata.py",
    "tests/db/test_deterministic_planning.py", "tests/fixtures/deterministic_planning.json",
    "tests/db/helper.py", "src/kineticloop/persistence/protocol_execution.py",
])
def test_undeclared_scope_rejected(path: str) -> None:
    changed = copy.deepcopy(TASKS["KL-079"])
    changed["write_paths"].append(path)
    assert v.m3_next_wave_definition_errors(changed) == ["m3-next-wave-definition:KL-079"]


@pytest.mark.parametrize("field,value", [
    ("depends_on", []), ("depends_on", ["KL-077"]), ("status", "DONE"),
    ("requirements_covered", ["W07@DC"]), ("resource_keys", []),
    ("review_requirements", ["GENERAL"]), ("check_contracts", []),
    ("entry_conditions", []), ("environment_requirements", []),
])
def test_prerequisite_or_claim_weakening_rejected(field: str, value: object) -> None:
    changed = copy.deepcopy(TASKS["KL-079"])
    changed[field] = value
    assert v.m3_next_wave_definition_errors(changed) == ["m3-next-wave-definition:KL-079"]


@pytest.mark.parametrize("phrase", [
    "singular ref_s36_id anchored to its TRAINING S36", "additional NUTRITION resolution",
    "JSON references", "mechanically reconstructed", "legacy resolution_hash",
    "policy required_members alone cannot establish coverage", "preserving legacy",
    "No historical test/log reuse as new PASS", "before every destructive entrypoint",
    "No new stage", "not caller completeness", "Full semantic validation",
])
def test_per_member_contract_weakening_rejected(phrase: str) -> None:
    packet = (ROOT / "docs/exec-plans/active/KL-079.md").read_text()
    assert phrase in packet
    assert "m3-next-wave-packet:KL-079" in v.packet_errors(
        TASKS["KL-079"], packet.replace(phrase, "bypass", 1)
    )


def test_actual_schema_and_mechanical_candidate_feasibility() -> None:
    candidate_spec = importlib.util.spec_from_file_location(
        "hg041_candidate", ROOT / "docs/exec-plans/evidence/HG-041/candidate.py"
    )
    assert candidate_spec is not None and candidate_spec.loader is not None
    candidate = importlib.util.module_from_spec(candidate_spec)
    candidate_spec.loader.exec_module(candidate)
    report = candidate.run()
    assert report["diagnostic_only"] and not report["real_pg"]
    assert report["task_checks"] == "NOT_RUN"
    assert report["original_gap"] == "ACTUAL_LEGACY_MODEL_REJECTS_NUTRITION"
    assert len(report["negative_controls"]) == 8
    bindings = report["candidate"]["action_bindings"]
    assert [b["action_type"] for b in bindings] == ["TRAINING", "NUTRITION"]
    assert bindings[0]["resolution_id"] != bindings[1]["resolution_id"]
    assert bindings[0]["action_parameters_hash"] != bindings[1]["action_parameters_hash"]
