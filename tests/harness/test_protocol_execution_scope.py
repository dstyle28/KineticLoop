"""Bound KL019 governance to one minimal owner-driven execution slice."""
from __future__ import annotations

import copy
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "execution_validator", ROOT / "tools/harness/validate_harness.py"
)
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
BASE = "eab2b305351cf3c504f74ac74868edc58d0a3430"
TASK = next(t for t in json.loads((ROOT / v.BACKLOG).read_text())["tasks"] if t["id"] == "KL-019")
PACKET = (ROOT / "docs/exec-plans/active/KL-019.md").read_text()


def test_execution_definition_packet_and_traceability() -> None:
    assert v.execution_definition_errors(TASK) == []
    assert v.packet_errors(TASK, PACKET) == []
    trace = json.loads((ROOT / v.TRACEABILITY).read_text())["tasks"]
    assert next(t for t in trace if t["id"] == "KL-019") == v.traceability_projection(TASK)
    assert len(TASK["check_contracts"]) == len(TASK["checks_required_for_this_task"]) == 20
    assert [c["check_id"] for c in TASK["check_contracts"]] == TASK["checks_required_for_this_task"]
    assert "tests/db/test_transaction_interfaces.py" not in TASK["write_paths"]
    assert TASK["status"] == "NOT_STARTED"


@pytest.mark.parametrize("field,value", [
    ("task_identity", "historical/KL-019"),
    ("status", "PASS"),
    ("packet_refinement", "READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED"),
    ("depends_on", ["KL-015"]),
    ("commands", ["PublishManifest", "CommitBundle", "StartSession", "AdvanceAttempt"]),
    ("write_paths", ["src/kineticloop/**", "tests/db/**"]),
    ("write_paths", ["tests/db/test_transaction_interfaces.py"]),
    ("resource_keys", ["user_coordination"]),
    ("environment_requirements", []),
    ("checks_required_for_this_task", ["minimal_publish_commit_start_api_tests"]),
    ("check_contracts", []),
    ("requirements_covered", ["I01@PASS"]),
    ("review_requirements", ["GENERAL"]),
    ("entry_conditions", ["KL025 reviews passed"]),
    ("definition_of_done", "seed S24, S42 and S45"),
])
def test_execution_definition_drift_fails_closed(field: str, value: object) -> None:
    task = copy.deepcopy(TASK)
    task[field] = value
    assert "execution-definition-drift:" + field in v.execution_definition_errors(task)


def test_command_oracle_and_machine_packet_drift_fail_closed() -> None:
    for field in ("command", "pass_oracle"):
        task = copy.deepcopy(TASK)
        task["check_contracts"][2][field] = "fixture SQL publication is sufficient"
        assert "execution-definition-drift:check_contracts" in v.execution_definition_errors(task)
        old = TASK["check_contracts"][2][field]
        assert "packet-check-contract:KL-019" in v.packet_errors(
            TASK, PACKET.replace(old, "fixture SQL publication is sufficient")
        )


@pytest.mark.parametrize("before,after,heading", [
    ("separately authenticated TEST RoleIdentity", "caller asserted TEST RoleIdentity",
     "Identity and service contract"),
    ("No SQL precreation of S38 or S44", "SQL precreation of S38 or S44",
     "Existing owner reuse and bounded missing capabilities"),
    ("The fixture may therefore explicitly bootstrap S26", "The service may expose arbitrary S26 SQL",
     "Trusted upstream bootstrap boundary"),
    ("not run on shared developer Docker", "run on shared developer Docker",
     "Local and hosted lifecycle boundary"),
    ("No duplicate T3/T6/T7 owner", "A duplicate T3/T6/T7 owner",
     "Non-goals"),
])
def test_authority_bootstrap_and_lifecycle_boundary_drift_fails_closed(
    before: str, after: str, heading: str
) -> None:
    assert before in PACKET
    changed = PACKET.replace(before, after)
    assert "execution-packet-boundary:" + heading in v.packet_errors(TASK, changed)


def baseline(path: str) -> bytes:
    return v.git(ROOT, "show", BASE + ":" + path)


@pytest.mark.parametrize("path", list(v.EXECUTION_FIXTURE_BASE_HASHES))
def test_only_exact_merged_fixture_candidate_is_authorized(path: str) -> None:
    before = baseline(path)
    after = v.execution_fixture_candidate(path, before)
    assert after != before
    assert v.execution_fixture_content_errors(path, before, after) == []
    compile(after, path, "exec")


@pytest.mark.parametrize("path", list(v.EXECUTION_FIXTURE_BASE_HASHES))
@pytest.mark.parametrize("mutate", [
    lambda b: b + b"\n# unrelated edit\n",
    lambda b: b.replace(b"assert ", b"# assert ", 1),
    lambda b: b.replace(b"lifecycle.destroy()", b"pass"),
    lambda b: b.replace(b"_MIGRATIONS.bootstrap_two_phase(lifecycle)", b"{}"),
    lambda b: b.replace(b"@pytest.fixture()", b"@pytest.fixture(scope='session')"),
    lambda b: b.replace(b"POLICY_BODY = {", b"POLICY_BODY = {'extra': 1,"),
    lambda b: b.replace(b".project_name[-12:]", b".project_name[:12]"),
    lambda b: b.replace(b'"KL-019"', b'"arbitrary"'),
    lambda b: b.replace(b"import os\n", b"import os, sys\n"),
])
def test_any_fixture_semantic_or_namespace_mutation_fails_closed(
    path: str, mutate: Callable[[bytes], bytes]
) -> None:
    before = baseline(path)
    after = v.execution_fixture_candidate(path, before)
    changed = mutate(after)
    assert changed != after
    assert v.execution_fixture_content_errors(path, before, changed) == [
        "execution-fixture-content-scope:KL-019:" + path
    ]


@pytest.mark.parametrize("path", list(v.EXECUTION_FIXTURE_BASE_HASHES))
def test_fixture_baseline_unknown_path_and_packet_drift_fail_closed(path: str) -> None:
    before = baseline(path)
    after = v.execution_fixture_candidate(path, before)
    assert v.execution_fixture_content_errors(path, after, after) == [
        "execution-fixture-baseline-unexpected:KL-019:" + path
    ]
    with pytest.raises(ValueError, match="baseline"):
        v.execution_fixture_candidate("tests/db/test_transaction_interfaces.py", before)
    assert "packet-execution-fixture-contract:KL-019" in v.packet_errors(
        TASK, PACKET.replace(v.EXECUTION_FIXTURE_CONTRACT, "Any fixture edit is allowed.")
    )


def test_execution_gate_reads_only_declared_committed_fixtures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = list(v.EXECUTION_FIXTURE_BASE_HASHES)
    blobs = {path: baseline(path) for path in paths}
    calls = []

    def git(root: Path, *args: str) -> bytes:
        calls.append(args)
        revision, path = args[1].split(":", 1)
        before = blobs[path]
        return before if revision == "base" else v.execution_fixture_candidate(path, before)

    monkeypatch.setattr(v, "git", git)
    assert v.task_fixture_scope_errors(ROOT, "base", "head", "KL-019", set(paths)) == []
    assert calls == [args for path in paths for args in (
        ("show", "base:" + path), ("show", "head:" + path)
    )]
    calls.clear()
    assert v.task_fixture_scope_errors(ROOT, "base", "head", "KL-019", set()) == []
    assert calls == []


def test_historical_unrefined_definition_stays_unchanged() -> None:
    old = json.loads(v.git(ROOT, "show", BASE + ":" + v.BACKLOG))
    task = next(t for t in old["tasks"] if t["id"] == "KL-019")
    packet = v.git(ROOT, "show", BASE + ":docs/exec-plans/active/KL-019.md").decode()
    assert v.execution_definition_errors(task) == []
    assert v.packet_errors(task, packet) == []
