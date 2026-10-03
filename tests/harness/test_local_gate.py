"""Trusted-controller boundary tests; no real credentials/network/Docker needed."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    'local_gate', Path(__file__).parents[2] / 'tools/harness/local_gate.py')
assert spec is not None and spec.loader is not None
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
A, B = 'a' * 40, 'b' * 40
STATE = {'repository_id': 42, 'pr': 90, 'base': A, 'head': B}


def private_json(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


def app(pr=None, base=A):
    pr = pr or {'state': 'open', 'base': {'ref': 'master', 'sha': A, 'repo': {'id': 42}},
                'head': {'sha': B, 'repo': {'id': 42}}}
    return SimpleNamespace(config={'repository': 'owner/repo', 'repository_id': 42},
        request=lambda method, path: pr if '/pulls/' in path else {'object': {'sha': base}})


def test_live_snapshot_binds_repository_pr_and_master():
    assert gate.snapshot(app(), 90) == STATE
    # GitHub's PR base.sha can lag behind the actual branch ref. The live ref is
    # authoritative; git ancestry and the publication re-read enforce freshness.
    assert gate.snapshot(app(base='c' * 40), 90)['base'] == 'c' * 40


@pytest.mark.parametrize('mutation', ['closed', 'fork', 'base_repo', 'branch', 'short_sha'])
def test_snapshot_rejects_wrong_target_and_identity(mutation):
    pr = app().request('GET', '/pulls/90')
    if mutation == 'closed':
        pr['state'] = 'closed'
    elif mutation == 'fork':
        pr['head']['repo']['id'] = 43
    elif mutation == 'base_repo':
        pr['base']['repo']['id'] = 43
    elif mutation == 'branch':
        pr['base']['ref'] = 'other'
    else:
        pr['head']['sha'] = 'abc'
    with pytest.raises(ValueError):
        gate.snapshot(app(pr), 90)


def test_admission_is_exact_and_outside_candidate_records(tmp_path):
    value = {'format': 'kineticloop-local-admission-v1', 'snapshot': STATE,
             'controller': 'controller-hash', 'trusted_code_reviewed': True}
    path = private_json(tmp_path / 'admission.json', value)
    gate.admit(path, STATE, 'controller-hash')
    for key in ('base', 'head', 'repository_id', 'pr'):
        changed = dict(STATE, **{key: 'wrong'})
        with pytest.raises(ValueError):
            gate.admit(path, changed, 'controller-hash')
    with pytest.raises(ValueError):
        gate.admit(path, STATE, 'new-controller')
    path.chmod(0o644)
    with pytest.raises(ValueError):
        gate.admit(path, STATE, 'controller-hash')
    path.chmod(0o600)
    link = tmp_path / 'link'
    link.symlink_to(path)
    with pytest.raises(ValueError):
        gate.admit(link, STATE, 'controller-hash')


def test_pinned_installation_rejects_missing_changed_or_symlinked_code(tmp_path):
    for name in gate.ASSETS:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text('trusted')
    config = {'controller_files': {name: gate.digest(tmp_path / name) for name in gate.ASSETS}}
    identity = gate.installed(config, tmp_path)
    assert len(identity) == 64
    path = tmp_path / 'db_policy.py'
    path.write_text('changed')
    with pytest.raises(ValueError):
        gate.installed(config, tmp_path)
    path.unlink()
    path.symlink_to(tmp_path / 'db_ci.py')
    with pytest.raises(ValueError):
        gate.installed(config, tmp_path)


def test_installed_entrypoint_works_in_isolated_python():
    result = subprocess.run(['python3', '-I', str(gate.HERE / 'local_gate.py'), '--help'],
                             capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('full', [True, False])
def test_host_owns_plan_and_review_gate_cannot_be_skipped_for_publication(full):
    plan = dict(gate.gate_plan(A, B, full, False))
    assert {'lint', 'typecheck', 'unit', 'harness', 'merge_gate'} <= plan.keys()
    assert plan['merge_gate'][-4:] == ['--ci-pr-base', A, '--ci-pr-head', B]
    assert '-I' in plan['merge_gate']
    assert '/gate/tools/harness/gate_validate.py' in plan['merge_gate']
    assert ('full_database' in plan) == full
    assert not any('tools/harness/db_ci.py' in argv for argv in plan.values())
    if full:
        assert '/gate/tools/harness/gate_pytest.py' in plan['full_database']
        assert '-p' not in plan['full_database']
        assert plan['destroy'][-1] == 'destroy'
        assert plan['peer_remove'][-1] == '/evidence/run-peer'


def test_test_only_plan_does_not_claim_review_gate():
    assert '--ci-pr-base' not in dict(gate.gate_plan(A, B, True, True))['merge_gate']


@pytest.mark.parametrize('kind', ['file_link', 'dir_link', 'oversize', 'fifo'])
def test_worker_artifacts_cannot_escape_or_block_parser(tmp_path, kind):
    worker = tmp_path / 'worker'
    worker.mkdir()
    (tmp_path / 'private').write_text('do not read')
    if kind == 'file_link':
        (worker / 'database.xml').symlink_to(tmp_path / 'private')
    elif kind == 'dir_link':
        (worker / 'run').symlink_to(tmp_path, target_is_directory=True)
    elif kind == 'fifo':
        import os
        os.mkfifo(worker / 'database.xml')
    else:
        with (worker / 'database.xml').open('wb') as stream:
            stream.truncate(20_000_001)
    with pytest.raises(ValueError):
        gate.artifact_tree(worker)


def test_cleanup_errors_are_fail_closed_and_allow_other_cleanup(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('docker', 120)
    monkeypatch.setattr(gate.subprocess, 'run', timeout)
    assert gate.cleanup_resource(['docker', 'rm', 'owned']) is False


@pytest.mark.parametrize('passed,expected', [(True, 'success'), (False, 'failure')])
def test_neutral_or_skipped_can_never_be_published(passed, expected):
    body = gate.publish_body(STATE, 'unique-run', passed, 'summary')
    assert body['head_sha'] == B
    assert body['name'] == 'local-db-gate'
    assert body['conclusion'] == expected


def test_client_refuses_redirect_and_untrusted_paths():
    with pytest.raises(ValueError):
        gate.github_app.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test')
    for path in ('https://evil.test', '//evil.test', '/repos/owner/repo?token=secret'):
        with pytest.raises(ValueError):
            gate.github_app.api('GET', path, 'fake-token')


def test_installation_permission_expansion_prevents_token_mint(monkeypatch):
    config = {'app_id': 1, 'installation_id': 2, 'key_path': '/unused',
              'repository': 'owner/repo', 'repository_id': 42}
    monkeypatch.setattr(gate.github_app, 'jwt', lambda *_: 'fake-jwt')
    calls = []
    def request(method, path, token, body=None):
        calls.append(method)
        return {'app_id': 1, 'suspended_at': None, 'repository_selection': 'selected',
                'account': {'login': 'owner'},
                'permissions': dict(gate.github_app.PERMISSIONS, administration='write')}
    monkeypatch.setattr(gate.github_app, 'api', request)
    with pytest.raises(ValueError):
        gate.github_app.App(config).refresh()
    assert calls == ['GET']


def test_candidate_plugin_shadow_is_never_imported(tmp_path):
    (tmp_path / 'db_ci_pytest.py').write_text('raise RuntimeError("CANDIDATE PLUGIN RAN")')
    (tmp_path / 'test_probe.py').write_text('def test_probe():\n    assert True\n')
    result = subprocess.run([__import__('sys').executable, '-I', str(gate.HERE / 'gate_pytest.py'),
                             '-q', str(tmp_path / 'test_probe.py')], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert '1 passed' in result.stdout


@pytest.mark.parametrize('field', ['app', 'head_sha', 'name', 'id'])
def test_wrong_publication_identity_is_rejected(field):
    result = {'app': {'id': 12}, 'head_sha': B, 'name': 'local-db-gate', 'id': 21}
    gate.verify_check(result, 12, B, 21)
    result[field] = {'id': 13} if field == 'app' else 'wrong'
    with pytest.raises(ValueError):
        gate.verify_check(result, 12, B, 21)


@pytest.mark.parametrize('scenario', ['success', 'test_only', 'stale_head', 'stale_base',
                                     'worker_failure', 'cleanup_failure', 'bad_artifacts', 'final_stale'])
def test_publication_requires_fresh_completed_worker_and_patches_one_id(tmp_path, monkeypatch, scenario):
    config = private_json(tmp_path / 'config.json', {'repository': 'owner/repo', 'repository_id': 42,
                                                   'app_id': 12})
    admission = private_json(tmp_path / 'admission.json', {
        'format': 'kineticloop-local-admission-v1', 'snapshot': STATE,
        'controller': 'identity', 'trusted_code_reviewed': True})
    calls = []
    class FakeApp:
        def __init__(self, cfg):
            self.config = cfg
        def request(self, method, path, body=None):
            calls.append((method, path, body))
            return {'app': {'id': 12}, 'head_sha': B, 'name': 'local-db-gate', 'id': 21}
    monkeypatch.setattr(gate.github_app, 'App', FakeApp)
    snapshots = [dict(STATE), dict(STATE), dict(STATE)]
    if scenario == 'stale_head':
        snapshots[1]['head'] = 'c' * 40
    if scenario == 'stale_base':
        snapshots[1]['base'] = 'c' * 40
    if scenario == 'final_stale':
        snapshots[2]['base'] = 'c' * 40
    monkeypatch.setattr(gate, 'snapshot', lambda *_: snapshots.pop(0))
    monkeypatch.setattr(gate, 'installed', lambda *_: 'identity')
    monkeypatch.setattr(gate, 'checked', lambda *_: 'tree')
    monkeypatch.setattr(gate.db_policy, 'classify', lambda *_: {'full_database_required': True})
    def worker(*args, **kwargs):
        if scenario in ('worker_failure', 'cleanup_failure', 'bad_artifacts'):
            raise ValueError(scenario)
        return {'status': 'PASS', 'container_removed': True, 'volume_removed': True}
    monkeypatch.setattr(gate, 'run_worker', worker)
    # main deliberately sanitizes its process environment; don't modify pytest's.
    monkeypatch.setattr(gate.os, 'environ', dict(gate.os.environ))
    monkeypatch.setattr(gate.sys, 'argv', ['local_gate.py', '--config', str(config),
        '--admission', str(admission), '--pr', '90', '--evidence-dir', str(tmp_path / 'run'),
        *(['--test-only'] if scenario == 'test_only' else [])])
    if scenario in ('success', 'test_only'):
        assert gate.main() == 0
    elif scenario == 'final_stale':
        assert gate.main() == 1
        assert json.loads((tmp_path / 'run/receipt.json').read_text())['status'] == 'FAIL'
    else:
        with pytest.raises(ValueError):
            gate.main()
    if scenario == 'test_only':
        assert calls == []
    else:
        assert [c[0] for c in calls] == ['POST', 'PATCH']
        assert calls[0][2]['status'] == 'in_progress'
        assert calls[1][1].endswith('/check-runs/21')
        assert calls[1][2]['conclusion'] == ('success' if scenario == 'success' else 'failure')


def test_uncertain_resource_creation_is_cleaned_by_exact_owner(monkeypatch):
    exists = iter([True, False])
    monkeypatch.setattr(gate, 'resource_exists', lambda *_: next(exists))
    monkeypatch.setattr(gate.subprocess, 'check_output', lambda *a, **k:
                        json.dumps([{'Config': {'Labels': {'kineticloop.owner': 'owned'}}}]))
    commands = []
    def cleanup(argv):
        commands.append(argv)
        return True
    monkeypatch.setattr(gate, 'cleanup_resource', cleanup)
    assert gate.cleanup_owned('container', 'owned', 'owned')
    assert commands == [['docker', 'container', 'rm', '-f', '-v', 'owned']]


def test_cleanup_never_deletes_a_foreign_resource(monkeypatch):
    monkeypatch.setattr(gate, 'resource_exists', lambda *_: True)
    monkeypatch.setattr(gate.subprocess, 'check_output', lambda *a, **k:
                        json.dumps([{'Labels': {'kineticloop.owner': 'foreign'}}]))
    monkeypatch.setattr(gate, 'cleanup_resource', lambda *_: pytest.fail('foreign resource deleted'))
    assert gate.cleanup_owned('volume', 'candidate-name', 'owned') is False


def test_failed_start_still_attempts_both_owned_cleanups(tmp_path, monkeypatch):
    monkeypatch.setattr(gate.db_ci, 'local_client_preflight', lambda: None)
    monkeypatch.setattr(gate.db_ci, 'run_capture', lambda *a, **k: {'exit_code': 0})
    monkeypatch.setattr(gate, 'resource_exists', lambda *_: False)
    monkeypatch.delenv('DOCKER_HOST', raising=False)
    monkeypatch.delenv('DOCKER_CONTEXT', raising=False)
    def checked(argv, source):
        if argv[1:3] == ['context', 'show']:
            return 'default'
        if argv[1:3] == ['context', 'inspect']:
            return 'unix:///socket'
        if argv[1:3] == ['image', 'inspect']:
            return '[{"Id":"sha256:image"}]'
        if argv[1] == 'start':
            raise subprocess.CalledProcessError(126, argv)
        return ''
    monkeypatch.setattr(gate, 'checked', checked)
    monkeypatch.setattr(gate, 'cleanup_resource', lambda *_: True)
    cleaned = []
    def cleanup(kind, name, owner):
        cleaned.append(kind)
        return True
    monkeypatch.setattr(gate, 'cleanup_owned', cleanup)
    with pytest.raises(subprocess.CalledProcessError):
        gate.run_worker(tmp_path, B, A, True, tmp_path)
    assert cleaned == ['container', 'volume']
    record = json.loads((tmp_path / 'worker-receipt.json').read_text())
    assert record['status'] == 'FAIL'
    assert record['container_removed'] and record['volume_removed']
