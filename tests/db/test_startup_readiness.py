from __future__ import annotations

import ast
import hashlib
import subprocess
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

import pytest
import yaml

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError, DatabaseNamespace

ROOT = Path(__file__).parents[2]


def load(relative: str) -> Any:
    spec = spec_from_file_location(relative.replace('/', '_'), ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_compose_and_lifecycle_tcp_alignment() -> None:
    guard = load("tools/harness/validate_harness.py")
    source = (ROOT / "src/kineticloop/db/lifecycle.py").read_bytes()
    before = source.decode()
    for old, new in guard.READINESS_LIFECYCLE_REPLACEMENTS:
        assert before.count(new) == 1
        before = before.replace(new, old, 1)
    assert hashlib.sha256(before.encode()).hexdigest() == guard.READINESS_LIFECYCLE_BASE_SHA256
    assert source == guard.readiness_lifecycle_candidate(before.encode())
    tree = ast.parse(source)
    methods = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    for name in ("start", "reset"):
        calls = [node for node in ast.walk(methods[name]) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'compose_command'
                 and any(isinstance(arg, ast.Constant) and arg.value == 'pg_isready'
                         for arg in node.args)]
        assert len(calls) == 1
        constants = [arg.value for arg in calls[0].args if isinstance(arg, ast.Constant)]
        assert constants[:8] == ['exec', '--no-TTY', 'postgres', 'pg_isready',
                                 '--host', '127.0.0.1', '--port', '5432']
    psql_source = ast.get_source_segment(source.decode(), methods['_psql'])
    assert psql_source and '--host' not in psql_source and '--port' not in psql_source
    compose = (ROOT / "compose.yaml").read_bytes()
    baseline = compose.replace(b'pg_isready --host 127.0.0.1 --port 5432', b'pg_isready')
    assert guard.readiness_content_errors('compose.yaml', baseline, compose) == []
    assert guard.readiness_content_errors('compose.yaml', baseline, baseline) == ['readiness-compose-tcp-required']
    config = yaml.safe_load(compose)
    postgres = config['services']['postgres']
    assert postgres['image'] == 'postgres:16.10-alpine'
    assert postgres['ports'] == [{'target': 5432, 'host_ip': '127.0.0.1', 'published': '0', 'protocol': 'tcp'}]


def test_hosted_entrypoint_exact_positive_and_negative_contract() -> None:
    guard = load('tools/harness/validate_harness.py')
    actual = (ROOT / guard.READINESS_WORKFLOW_PATH).read_bytes()
    assert actual == (ROOT / 'docs/exec-plans/evidence/HG-037/kl074-readiness.workflow.proposal.yml').read_bytes()
    assert hashlib.sha256(actual).hexdigest() == guard.READINESS_WORKFLOW_SHA256
    assert guard.readiness_workflow_errors('', actual) == []
    assert guard.readiness_workflow_errors('existing-workflow', actual) == ['readiness-workflow-baseline-exists']
    for old, new in [(b'head.sha', b'base.sha'), (b'ubuntu-latest', b'self-hosted'),
                     (b'uv sync --locked', b'uv sync'), (b'if: always()', b'if: success()'),
                     (b'contents: read', b'contents: write'), (b'set -euo pipefail', b'set -eu')]:
        assert old in actual
        assert guard.readiness_workflow_errors('', actual.replace(old, new)) == ['readiness-workflow-content-scope']
    workflow = yaml.safe_load(actual)
    assert set(workflow['on']) == {'pull_request'}
    job = workflow['jobs']['kl074-readiness']
    assert job['runs-on'] == 'ubuntu-latest' and job['timeout-minutes'] == 20
    assert 'codex/kl074-' in job['if'] and 'head.repo.full_name == github.repository' in job['if']
    steps = job['steps']
    assert steps[0]['with']['ref'] == '${{ github.event.pull_request.head.sha }}'
    assert steps[0]['with']['persist-credentials'] is False
    assert steps[1]['with']['version'] == '0.12.17'
    assert all('continue-on-error' not in step for step in steps)
    assert steps[-1]['if'] == 'always()' and steps[-1]['with']['if-no-files-found'] == 'error'
    for path, expected in {
        '.github/workflows/ci.yml': 'c955d1de33682d253aeac020efb56bb660c92759b223bd6211fefccd859d4d8a',
        '.github/workflows/db.yml': 'efef56c3e5debb4c335fff41873889b209ce45979f950e85672165b0a1d06326',
    }.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected


def test_probe_exact_environment_and_owned_namespace_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = load('tools/db/verify_startup_readiness.py')
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    head = 'a' * 40
    evidence = tmp_path / f'docs/exec-plans/evidence/KL-074/hosted-{head}'
    env = {'KINETICLOOP_KL074_TESTED_COMMIT': head,
           'KINETICLOOP_KL074_EVIDENCE_DIR': str(evidence),
           'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'Linux'}
    assert probe.validate_environment(env, head) == evidence
    for key, value in [('KINETICLOOP_KL074_TESTED_COMMIT', 'b' * 40),
                       ('KINETICLOOP_KL074_EVIDENCE_DIR', str(tmp_path / 'foreign')),
                       ('RUNNER_ENVIRONMENT', 'self-hosted'), ('RUNNER_OS', 'macOS'),
                       ('DOCKER_HOST', 'tcp://foreign'), ('DOCKER_CONTEXT', 'foreign'),
                       ('COMPOSE_PROJECT_NAME', 'foreign'), ('KINETICLOOP_DB_NAME', 'postgres'),
                       ('COMPOSE_FILE', 'foreign.yaml'), ('KINETICLOOP_DB_PASSWORD', 'foreign')]:
        with pytest.raises(DatabaseLifecycleError):
            probe.validate_environment({**env, key: value}, head)
    root = tmp_path / 'owned'
    root.mkdir()
    compose = b'services: {}\n'
    (tmp_path / 'compose.yaml').write_bytes(compose)
    (root / 'compose.yaml').write_bytes(compose)
    lifecycle = DatabaseLifecycle(root, environ={})
    digest = hashlib.sha256(bytes(root.resolve())).hexdigest()[:12]
    expected = DatabaseNamespace(f'kineticloop-kl074-cold-aaaaaaa-{digest}',
                                 f'kineticloop_kl074_cold_aaaaaaa_{digest}')
    assert probe.owned_namespace(root, head) == expected
    with pytest.raises(DatabaseLifecycleError, match='namespace'):
        probe.validate_owned(lifecycle, head)
    lifecycle.namespace = expected
    probe.validate_owned(lifecycle, head)
    for foreign in (DatabaseNamespace('foreign', 'postgres'), DatabaseNamespace(expected.project_name, 'postgres')):
        lifecycle.namespace = foreign
        with pytest.raises(DatabaseLifecycleError, match='namespace'):
            probe.validate_owned(lifecycle, head)
    lifecycle.namespace = expected
    lifecycle._base_environ['KINETICLOOP_DB_NAME'] = expected.database_name
    with pytest.raises(DatabaseLifecycleError, match='ambient'):
        probe.validate_owned(lifecycle, head)


def test_probe_root_cause_oracle_rejects_success_without_ordering() -> None:
    probe = load('tools/db/verify_startup_readiness.py')
    logs = '\n'.join(f'2026-10-01T00:00:0{i}.000000000Z {line}' for i, line in enumerate([
        'listening on Unix socket', 'database system is ready to accept connections',
        'received fast shutdown request', 'database system is shut down',
        'listening on IPv4 address "0.0.0.0", port 5432',
        'database system is ready to accept connections',
    ]))
    events = [{'kind': 'socket_probe', 'returncode': 0}, {'kind': 'tcp_probe_begin'},
              {'kind': 'tcp_probe_end', 'returncode': 1},
              {'kind': 'tcp_probe_end', 'returncode': 0},
              {'kind': 'sql_begin', 'utc': '2026-10-01T00:00:06.000000+00:00'}]
    observer = '2026-10-01T00:00:01Z socket=0 tcp=2\n2026-10-01T00:00:05Z socket=0 tcp=0\n'
    assert probe.verify_ordering(logs, events, observer)['status'] == 'PASS'
    for bad_logs, bad_events in [(logs.replace('received fast shutdown request', 'missing'), events),
                                  (logs, [*events[:3], events[-1]]), (logs, [events[-1], *events[:-1]])]:
        with pytest.raises(DatabaseLifecycleError):
            probe.verify_ordering(bad_logs, bad_events, observer)
    with pytest.raises(DatabaseLifecycleError, match='measurement unavailable'):
        probe.verify_ordering(logs, events, '2026-10-01T00:00:05Z socket=0 tcp=0\n')


def test_probe_subprocesses_honor_remaining_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = load('tools/db/verify_startup_readiness.py')
    monkeypatch.setattr(probe.time, 'monotonic', lambda: 12.5)
    observed: list[float] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed.append(kwargs['timeout'])
        return subprocess.CompletedProcess(command, 0, stdout='')

    monkeypatch.setattr(probe.subprocess, 'run', runner)
    probe.bounded_run(['docker', 'version'], 15)
    probe.bounded_run(['docker', 'version'], 15, timeout=1)
    assert observed == [2.5, 1]
    with pytest.raises(DatabaseLifecycleError, match='deadline'):
        probe.bounded_run(['docker', 'version'], 12.5)
    assert observed == [2.5, 1]
