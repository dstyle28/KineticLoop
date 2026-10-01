"""Ratified KL074 scope and readiness boundaries fail closed."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = "0c11a89f4c624290bf8f2a911bc81e5740240e45"
SPEC = importlib.util.spec_from_file_location('readiness_validator', ROOT / 'tools/harness/validate_harness.py')
assert SPEC and SPEC.loader
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
TASK = next(t for t in json.loads((ROOT / v.BACKLOG).read_text())['tasks'] if t['id'] == 'KL-074')
PACKET = (ROOT / 'docs/exec-plans/active/KL-074.md').read_text()


def test_exact_readiness_packet_definition_traceability() -> None:
    assert v.readiness_definition_errors(TASK) == []
    assert v.packet_errors(TASK, PACKET) == []
    assert next(t for t in json.loads((ROOT / v.TRACEABILITY).read_text())['tasks'] if t['id'] == 'KL-074') == v.traceability_projection(TASK)
    assert TASK['status'] == 'NOT_STARTED' and TASK['requirements_covered'] == []
    assert len(TASK['check_contracts']) == 9


@pytest.mark.parametrize('field,value', [
    ('task_identity', 'historical/KL-074'), ('status', 'PASS'),
    ('depends_on', ['KL-002']), ('resource_keys', ['transaction_interfaces']),
    ('write_paths', ['src/kineticloop/**', 'tests/db/**']),
    ('review_requirements', ['GENERAL']), ('environment_requirements', []),
    ('check_contracts', []), ('requirements_covered', ['I01@PASS']),
    ('definition_of_done', 'CI rerun eventually succeeds'),
])
def test_readiness_definition_drift_fails_closed(field: str, value: object) -> None:
    changed = copy.deepcopy(TASK)
    changed[field] = value
    assert 'readiness-definition-drift:' + field in v.readiness_definition_errors(changed)


@pytest.mark.parametrize('heading', ['Repair boundary', 'Isolation and evidence boundary', 'Non-goals'])
def test_readiness_packet_boundary_drift_fails_closed(heading: str) -> None:
    assert v.readiness_packet_errors(TASK, PACKET) == []
    changed = PACKET.replace(v.READINESS_PACKET_BOUNDARIES[heading], 'Retry DROP on shared default database.')
    assert 'readiness-packet-boundary:' + heading in v.packet_errors(TASK, changed)


def candidate(path: str, before: bytes) -> bytes:
    if path == 'compose.yaml':
        return before.replace(b'pg_isready --username', b'pg_isready --host 127.0.0.1 --port 5432 --username')
    return before.replace(b'"pg_isready",\n', b'"pg_isready",\n                "--host",\n                "127.0.0.1",\n                "--port",\n                "5432",\n')


@pytest.mark.parametrize('path', ['compose.yaml', 'src/kineticloop/db/lifecycle.py'])
def test_minimal_readiness_content_is_accepted(path: str) -> None:
    before = v.git(ROOT, 'show', BASE + ':' + path)
    assert v.readiness_content_errors(path, before, candidate(path, before)) == []
    assert v.readiness_content_errors(path, before, before)


@pytest.mark.parametrize('old,new', [
    (b'DROP DATABASE IF EXISTS', b'DROP DATABASE'),
    (b'WITH (FORCE)', b''),
    (b'ON_ERROR_STOP=1', b'ON_ERROR_STOP=0'),
    (b'resolved.parent.name.lower()', b'"shared"'),
    (b'check: bool = True', b'check: bool = False'),
    (b'check=check,', b'check=False,'),
])
def test_sql_auth_namespace_changes_rejected(old: bytes, new: bytes) -> None:
    path = 'src/kineticloop/db/lifecycle.py'
    before = v.git(ROOT, 'show', BASE + ':' + path)
    after = candidate(path, before).replace(old, new)
    assert after != candidate(path, before)
    # _run is permitted bounded timeout plumbing; its default failure policy must remain.
    assert v.readiness_content_errors(path, before, after)


@pytest.mark.parametrize('old,new', [
    (b'postgres:16.10-alpine', b'postgres:latest'),
    (b'kineticloop-local-only', b'changed'),
    (b'interval: 1s', b'interval: 30s'),
    (b'--host 127.0.0.1', b'--host shared'),
    (b'--port 5432', b'--port 49152'),
])
def test_compose_non_readiness_and_wrong_endpoint_rejected(old: bytes, new: bytes) -> None:
    path = 'compose.yaml'
    before = v.git(ROOT, 'show', BASE + ':' + path)
    after = candidate(path, before).replace(old, new)
    assert v.readiness_content_errors(path, before, after)


def test_gate_reads_changed_committed_readiness_blobs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    paths = ['compose.yaml', 'src/kineticloop/db/lifecycle.py']
    def git(root: Path, *args: str) -> bytes:
        calls.append(args)
        rev, path = args[1].split(':', 1)
        raw = v.git_original(ROOT, 'show', BASE + ':' + path)
        return raw if rev == 'base' else candidate(path, raw)
    monkeypatch.setattr(v, 'git_original', v.git, raising=False)
    monkeypatch.setattr(v, 'git', git)
    assert v.task_fixture_scope_errors(ROOT, 'base', 'head', 'KL-074', set(paths)) == []
    assert len(calls) == 4
    calls.clear()
    assert v.task_fixture_scope_errors(ROOT, 'base', 'head', 'KL-074', set()) == []
    assert calls == []


def test_timeout_handler_cannot_replay_sql() -> None:
    path = 'src/kineticloop/db/lifecycle.py'
    before = v.git(ROOT, 'show', BASE + ':' + path)
    after = candidate(path, before).replace(
        b'        except FileNotFoundError as error:',
        b'        except subprocess.TimeoutExpired:\n            self._runner(command)\n        except FileNotFoundError as error:',
    )
    assert v.readiness_content_errors(path, before, after)
