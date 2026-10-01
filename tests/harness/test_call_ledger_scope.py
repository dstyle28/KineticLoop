"""Fail-closed governance coverage for conditional KL025 ledger implementation."""

from __future__ import annotations

import copy
import importlib.util
import json
from collections.abc import Callable
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


BASELINE = "ff57a80feebd4e539f9af277e0dcb26d942bc3e0"


def planning_baseline() -> bytes:
    return v.git(ROOT, "show", BASELINE + ":" + v.LEDGER_PLANNING_FIXTURE_PATH)


def test_planning_namespace_exact_candidate_is_allowed() -> None:
    before = planning_baseline()
    after = v.ledger_planning_fixture_candidate(before)
    assert v.ledger_planning_fixture_content_errors(before, after) == []
    assert before != after


@pytest.mark.parametrize("mutation", [
    lambda b: b + b"\n# unrelated edit\n",
    lambda b: b.replace(b"import os\n", b"import os, sys\n"),
    lambda b: b.replace(b'owner != "KL-025"', b'owner != "KL-024"'),
    lambda b: b.replace(b"7 <= len(short) <= 12", b"True"),
    lambda b: b.replace(b".project_name[-12:]", b'.project_name[:12]'),
    lambda b: b.replace(b"lifecycle.destroy()", b"pass"),
    lambda b: b.replace(b"assert ", b"# assert ", 1),
    lambda b: b.replace(b"@pytest.fixture()", b"@pytest.fixture(scope='session')"),
    lambda b: b.replace(b"POLICY_BODY = {", b"POLICY_BODY = {\n    'extra': 1,"),
    lambda b: b.replace(b"_MIGRATIONS.bootstrap_two_phase(lifecycle)", b"{}"),
])
def test_planning_namespace_other_bytes_fail_closed(mutation: Callable[[bytes], bytes]) -> None:
    before = planning_baseline()
    candidate = v.ledger_planning_fixture_candidate(before)
    changed = mutation(candidate)
    assert changed != candidate
    assert v.ledger_planning_fixture_content_errors(before, changed) == [
        "ledger-planning-fixture-content-scope:KL-025"
    ]


def test_planning_namespace_baseline_and_packet_drift_fail_closed() -> None:
    before = planning_baseline()
    after = v.ledger_planning_fixture_candidate(before)
    assert v.ledger_planning_fixture_content_errors(after, after) == [
        "ledger-planning-fixture-baseline-unexpected:KL-025"
    ]
    packet = (ROOT / "docs/exec-plans/active/KL-025.md").read_text()
    changed = packet.replace(v.LEDGER_PLANNING_FIXTURE_CONTRACT, "arbitrary reset target")
    assert "packet-ledger-planning-fixture-contract:KL-025" in v.packet_errors(TASK, changed)
