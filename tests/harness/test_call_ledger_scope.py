"""Fail-closed governance coverage for conditional KL025 ledger implementation."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "ledger_validator", ROOT / "tools/harness/validate_harness.py"
)
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
TASK = next(t for t in json.loads((ROOT / v.BACKLOG).read_text())["tasks"] if t["id"] == "KL-025")


def test_ledger_conditional_projection_and_packet() -> None:
    assert v.ledger_definition_errors(TASK) == []
    assert v.packet_errors(TASK, (ROOT / "docs/exec-plans/active/KL-025.md").read_text()) == []
    trace = json.loads((ROOT / v.TRACEABILITY).read_text())["tasks"]
    assert next(t for t in trace if t["id"] == "KL-025") == v.traceability_projection(TASK)


@pytest.mark.parametrize(
    "field,value",
    [
        ("depends_on", ["KL-015"]),
        ("entry_conditions", ["KL-024 packet is merged"]),
        ("write_paths", ["src/kineticloop/**"]),
        ("write_paths", ["tests/db/test_transaction_interfaces.py"]),
        ("resource_keys", ["planning_ledger"]),
        ("checks_required_for_this_task", ["task_scope_dc_checks"]),
        ("check_contracts", []),
        ("requirements_covered", ["W02@DC"]),
        ("review_requirements", ["GENERAL"]),
        ("environment_requirements", []),
    ],
)
def test_ledger_definition_drift_fails_closed(field: str, value: object) -> None:
    task = copy.deepcopy(TASK)
    task[field] = value
    assert "ledger-definition-drift:" + field in v.ledger_definition_errors(task)


def test_ledger_oracle_drift_fails_closed() -> None:
    task = copy.deepcopy(TASK)
    task["check_contracts"][0]["pass_oracle"] = "UNKNOWN refunds budget"
    assert "ledger-definition-drift:check_contracts" in v.ledger_definition_errors(task)
    packet = (ROOT / "docs/exec-plans/active/KL-025.md").read_text()
    changed = packet.replace(TASK["check_contracts"][0]["pass_oracle"], "UNKNOWN refunds budget")
    assert "packet-check-contract:KL-025" in v.packet_errors(TASK, changed)
