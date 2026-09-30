"""Regression checks for the HG-029 executable wave and preserved contention."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("wave_validator", ROOT / "tools/harness/validate_harness.py")
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
TASKS = {t["id"]: t for t in json.loads((ROOT / v.BACKLOG).read_text())["tasks"]}


@pytest.mark.parametrize("name", sorted(v.WAVE_REFINED_TASK_IDS))
def test_wave_identity_packet_and_traceability_projection(name: str) -> None:
    task = TASKS[name]
    assert v.wave_definition_errors(task) == []
    assert v.packet_errors(task, (ROOT / f"docs/exec-plans/active/{name}.md").read_text()) == []
    trace = json.loads((ROOT / v.TRACEABILITY).read_text())["tasks"]
    assert next(t for t in trace if t["id"] == name) == v.traceability_projection(task)


@pytest.mark.parametrize("name", sorted(v.WAVE_REFINED_TASK_IDS))
@pytest.mark.parametrize("field,value,error", [
    ("task_identity", "historical-backlog/KL-023", "wave-identity-or-dependency"),
    ("depends_on", [], "wave-identity-or-dependency"),
    ("conditional_depends_on", ["KL-052"], "wave-identity-or-dependency"),
    ("resource_keys", [], "wave-resource-contention"),
    ("write_paths", ["src/kineticloop/**"], "wave-write-ownership"),
    ("write_paths", ["src/kineticloop/integrations/__init__.py"], "wave-write-ownership"),
    ("write_paths", ["tests/db/test_transaction_interfaces.py"], "wave-write-ownership"),
    ("check_contracts", [], "wave-check-contract"),
    ("requirements_covered", ["W04@DC"], "wave-evidence-or-requirement-claim"),
    ("packet_refinement", "MUST_REFINE_BEFORE_READY", "wave-write-ownership"),
])
def test_wave_drift_fails_closed(name: str, field: str, value: object, error: str) -> None:
    task = copy.deepcopy(TASKS[name])
    task[field] = value
    assert error + ":" + name in v.wave_definition_errors(task)


@pytest.mark.parametrize("name", sorted(v.WAVE_REFINED_TASK_IDS))
def test_wave_machine_contract_packet_drift_rejected(name: str) -> None:
    task = TASKS[name]
    packet = (ROOT / f"docs/exec-plans/active/{name}.md").read_text()
    altered = packet.replace(task["check_contracts"][0]["pass_oracle"], "unsupported assertion")
    assert "packet-check-contract:" + name in v.packet_errors(task, altered)


def test_wave_parallelism_preserves_real_locks_and_adapter_dependencies() -> None:
    left, right, provider = (TASKS[name] for name in ("KL-023", "KL-024", "KL-050"))
    assert set(left["resource_keys"]) & set(right["resource_keys"]) == {
        "transaction_interfaces", "user_coordination"
    }
    assert set(left["write_paths"]) & set(right["write_paths"]) == {
        "src/kineticloop/persistence/transactions.py"
    }
    for core in (left, right):
        assert not set(core["resource_keys"]) & set(provider["resource_keys"])
        assert not set(core["write_paths"]) & set(provider["write_paths"])
    assert TASKS["KL-051"]["depends_on"] == ["KL-050", "KL-055", "KL-030", "KL-032"]
    assert TASKS["KL-052"]["depends_on"] == ["KL-050", "KL-055", "KL-030"]
    assert TASKS["KL-052"]["packet_refinement"] == "MUST_REFINE_BEFORE_READY"
