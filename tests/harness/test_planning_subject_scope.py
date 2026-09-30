"""Enforce KL024's two-expression current-head repair without changing DB oracles."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "subject_scope_validator", ROOT / "tools/harness/validate_harness.py"
)
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
# This historical input remains stable after KL024 applies the repair.
BEFORE = v.git(
    ROOT, "show", "abc5af63bc580bb22e54baeb0af577448b57a75a:" + v.PLANNING_SUBJECT_SCOPE_PATH
)
AFTER = BEFORE.replace(b"\n                REVISION,\n",
                       b"\n                _MIGRATIONS.HEAD_REVISION,\n").replace(
    b"\n            REVISION,\n", b"\n            _MIGRATIONS.HEAD_REVISION,\n"
)


def test_exact_two_head_expectations_are_authorized() -> None:
    assert BEFORE.count(b"REVISION,\n") == 2
    assert v.planning_subject_scope_content_errors(BEFORE, AFTER) == []


@pytest.mark.parametrize("after", [
    BEFORE,
    AFTER.replace(b"                _MIGRATIONS.HEAD_REVISION,", b"                REVISION,"),
    AFTER.replace(b"            _MIGRATIONS.HEAD_REVISION,", b"            REVISION,"),
    AFTER.replace(b"_MIGRATIONS.HEAD_REVISION,", b'"e8c2f1a6b904",'),
    AFTER.replace(b"KL_SUBJECT_SCOPE_DOWNGRADE_SCOPED_STATE", b"anything"),
    AFTER.replace(b"AND NOT trigger.tgisinternal", b"OR trigger.tgisinternal"),
    AFTER.replace(b"fetchone() == (5,)", b"fetchone() == (0,)"),
    AFTER.replace(b"fetchone() == (True,)", b"fetchone() == (False,)"),
    AFTER.replace(b"fetchone() == (False,)", b"fetchone() == (True,)"),
    AFTER.replace(b"fetchone() == (4,)", b"fetchone() == (0,)"),
    AFTER.replace(b"fetchone() == (production_only_subject,)", b"fetchone() == (None,)"),
    AFTER.replace(b"def test_populated_downgrade_fails_before_guard_or_acl_changes(",
                  b"@pytest.mark.skip\ndef test_populated_downgrade_fails_before_guard_or_acl_changes("),
    AFTER.replace(b"REVISION: str = _MIGRATIONS.REVISION",
                  b"REVISION: str = _MIGRATIONS.HEAD_REVISION"),
    AFTER + b"\n# unrelated\n",
])
def test_any_other_oracle_or_file_change_fails_closed(after: bytes) -> None:
    assert v.planning_subject_scope_content_errors(BEFORE, after) == [
        "planning-subject-scope-content-scope:KL-024"
    ]


@pytest.mark.parametrize("before", [
    AFTER,
    BEFORE.replace(b"test_populated_downgrade_fails_before_guard_or_acl_changes", b"other_test"),
    BEFORE.replace(b"\n                REVISION,\n", b"\n                OTHER,\n"),
    BEFORE.replace(b"\n            REVISION,\n", b"\n            OTHER,\n"),
    BEFORE.replace(b"    # Non-production", b"    REVISION,\n    # Non-production"),
])
def test_unexpected_protected_baseline_fails_closed(before: bytes) -> None:
    assert v.planning_subject_scope_content_errors(before, AFTER) == [
        "planning-subject-scope-baseline-unexpected:KL-024"
    ]


def test_task_gate_checks_committed_both_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    fixture_before = v.git(ROOT, "show", "abc5af6:" + v.PLANNING_FIXTURE_PATH)
    fixture_after = fixture_before.replace(
        b"UPDATE kineticloop.planning_intents SET local_date=DATE '2026-09-27' WHERE id=%s",
        b"UPDATE kineticloop.planning_intents SET local_date=DATE '2026-09-28' WHERE id=%s",
    )

    def git(root: Path, *args: str) -> bytes:
        calls.append(args)
        if args[1].endswith(v.PLANNING_FIXTURE_PATH):
            return fixture_before if args[1].startswith("base:") else fixture_after
        return BEFORE if args[1].startswith("base:") else AFTER

    monkeypatch.setattr(v, "git", git)
    changed = {v.PLANNING_SUBJECT_SCOPE_PATH, v.PLANNING_FIXTURE_PATH}
    assert v.task_fixture_scope_errors(ROOT, "base", "head", "KL-024", changed) == []
    assert calls == [("show", revision + ":" + path)
                     for path in [v.PLANNING_FIXTURE_PATH, v.PLANNING_SUBJECT_SCOPE_PATH]
                     for revision in ["base", "head"]]
    calls.clear()
    assert v.task_fixture_scope_errors(ROOT, "base", "head", "KL-023", changed) == []
    assert v.task_fixture_scope_errors(ROOT, "base", "head", "KL-024", set()) == []
    assert calls == []


def test_packet_requires_exact_subject_scope_contract() -> None:
    task = next(t for t in json.loads((ROOT / v.BACKLOG).read_text())["tasks"] if t["id"] == "KL-024")
    packet = (ROOT / "docs/exec-plans/active/KL-024.md").read_text()
    assert v.packet_errors(task, packet) == []
    assert "packet-planning-subject-scope-contract:KL-024" in v.packet_errors(
        task, packet.replace(v.PLANNING_SUBJECT_SCOPE_CONTRACT, "Any repairs allowed.")
    )


@pytest.mark.parametrize("name", ["KL-023", "KL-050"])
def test_other_wave_tasks_cannot_gain_subject_scope_write(name: str) -> None:
    task = next(t for t in json.loads((ROOT / v.BACKLOG).read_text())["tasks"] if t["id"] == name)
    task["write_paths"].append(v.PLANNING_SUBJECT_SCOPE_PATH)
    assert "wave-write-ownership:" + name in v.wave_definition_errors(task)
