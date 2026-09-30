"""Reject authorization-test changes outside KL024's single fixture date literal."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "fixture_validator", ROOT / "tools/harness/validate_harness.py"
)
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
BEFORE = (ROOT / v.PLANNING_FIXTURE_PATH).read_bytes()
OLD = b"UPDATE kineticloop.planning_intents SET local_date=DATE '2026-09-27' WHERE id=%s"
AFTER = BEFORE.replace(OLD, OLD.replace(b"2026-09-27", b"2026-09-28"))


def test_only_proposed_literal_change_is_authorized() -> None:
    assert BEFORE.count(OLD) == 1
    assert v.planning_fixture_content_errors(BEFORE, AFTER) == []


@pytest.mark.parametrize("after", [
    BEFORE,
    AFTER.replace(b'match="head day"', b'match="anything"'),
    AFTER.replace(b"DATE '2026-09-26' WHERE id=%s", b"DATE '2026-09-28' WHERE id=%s"),
    AFTER.replace(b"def test_reauthorize_requires_atomic_intent_success(",
                  b"@pytest.mark.skip\ndef test_reauthorize_requires_atomic_intent_success("),
    AFTER + b"\n# unrelated test change\n",
    BEFORE.replace(OLD, OLD.replace(b"2026-09-27", b"2026-09-29")),
])
def test_fixture_or_oracle_drift_rejected(after: bytes) -> None:
    assert v.planning_fixture_content_errors(BEFORE, after) == [
        "planning-fixture-content-scope:KL-024"
    ]


def test_unexpected_protected_fixture_fails_closed() -> None:
    assert v.planning_fixture_content_errors(AFTER, AFTER) == [
        "planning-fixture-baseline-unexpected:KL-024"
    ]


def test_task_gate_reads_protected_and_head_committed_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def git(root: Path, *args: str) -> bytes:
        calls.append(args)
        return BEFORE if args[1].startswith("base:") else AFTER + b"# changed oracle"

    monkeypatch.setattr(v, "git", git)
    assert v.task_fixture_scope_errors(ROOT, "base", "head", "KL-024", {v.PLANNING_FIXTURE_PATH}) == [
        "planning-fixture-content-scope:KL-024"
    ]
    assert calls == [("show", "base:" + v.PLANNING_FIXTURE_PATH),
                     ("show", "head:" + v.PLANNING_FIXTURE_PATH)]
    calls.clear()
    assert v.task_fixture_scope_errors(ROOT, "base", "head", "KL-023", {v.PLANNING_FIXTURE_PATH}) == []
    assert v.task_fixture_scope_errors(ROOT, "base", "head", "KL-024", set()) == []
    assert calls == []


def test_packet_requires_restrictive_fixture_contract() -> None:
    import json

    task = next(t for t in json.loads((ROOT / v.BACKLOG).read_text())["tasks"] if t["id"] == "KL-024")
    packet = (ROOT / "docs/exec-plans/active/KL-024.md").read_text()
    assert v.packet_errors(task, packet) == []
    assert "packet-planning-fixture-contract:KL-024" in v.packet_errors(
        task, packet.replace(v.PLANNING_FIXTURE_CONTRACT, "General fixture repairs permitted.")
    )


@pytest.mark.parametrize("name", ["KL-023", "KL-050"])
def test_exception_cannot_authorize_other_wave_tasks(name: str) -> None:
    import json

    task = next(t for t in json.loads((ROOT / v.BACKLOG).read_text())["tasks"] if t["id"] == name)
    task["write_paths"].append(v.PLANNING_FIXTURE_PATH)
    assert "wave-write-ownership:" + name in v.wave_definition_errors(task)
