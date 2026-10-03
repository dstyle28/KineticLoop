"""Trusted-controller boundary tests; no real credentials/network/Docker needed."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
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


@pytest.mark.parametrize('mutation', ['missing_pin', 'missing_file', 'changed', 'symlink'])
def test_installed_compact_decoder_is_required_and_exact(tmp_path, mutation):
    for name in gate.ASSETS:
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text('trusted')
    config = {'controller_files': {name: gate.digest(tmp_path / name) for name in gate.ASSETS}}
    assert gate.installed(config, tmp_path)
    path = tmp_path / 'compact_evidence.py'
    if mutation == 'missing_pin':
        del config['controller_files']['compact_evidence.py']
    elif mutation == 'missing_file':
        path.unlink()
    elif mutation == 'changed':
        path.write_text('candidate decoder')
    else:
        path.unlink()
        path.symlink_to(tmp_path / 'db_policy.py')
    with pytest.raises(ValueError, match='installation'):
        gate.installed(config, tmp_path)


@pytest.mark.parametrize('missing', [False, True])
def test_isolated_validator_never_uses_candidate_compact_decoder(tmp_path, missing):
    installed = tmp_path / 'installed/tools/harness'
    installed.mkdir(parents=True)
    for name in ('validate_harness.py', 'compact_evidence.py'):
        shutil.copyfile(gate.HERE / name, installed / name)
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
    (candidate / 'compact_evidence.py').write_text('raise RuntimeError("CANDIDATE DECODER RAN")')
    if missing:
        (installed / 'compact_evidence.py').unlink()
    probe = (
        'import importlib.util, sys; '
        's = importlib.util.spec_from_file_location("trusted_validator", sys.argv[1]); '
        'v = importlib.util.module_from_spec(s); s.loader.exec_module(v); '
        'print(v.compact_evidence.__file__)'
    )
    result = subprocess.run([sys.executable, '-I', '-c', probe,
                             str(installed / 'validate_harness.py')], cwd=candidate,
                            capture_output=True, text=True)
    assert 'CANDIDATE DECODER RAN' not in result.stdout + result.stderr
    if missing:
        assert result.returncode != 0 and 'FileNotFoundError' in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(installed / 'compact_evidence.py')


def test_worker_copies_decoder_from_installed_release(tmp_path, monkeypatch):
    installed = tmp_path / 'installed'
    candidate = tmp_path / 'candidate'
    installed.mkdir()
    candidate.mkdir()
    (installed / 'compact_evidence.py').write_text('installed decoder')
    (candidate / 'compact_evidence.py').write_text('candidate decoder')
    monkeypatch.setattr(gate.db_ci, 'local_client_preflight', lambda: None)
    monkeypatch.setattr(gate.db_ci, 'owned_mounts', lambda *_: [])
    monkeypatch.setattr(gate, 'resource_exists', lambda *_: False)
    monkeypatch.setattr(gate, 'cleanup_resource', lambda *_: True)
    monkeypatch.setattr(gate, 'cleanup_owned', lambda *_: True)
    monkeypatch.setattr(gate.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.delenv('DOCKER_HOST', raising=False)
    monkeypatch.delenv('DOCKER_CONTEXT', raising=False)
    copies = []
    def checked(argv, source):
        assert source == candidate
        if argv[1:3] == ['context', 'show']:
            return 'default'
        if argv[1:3] == ['context', 'inspect']:
            return 'unix:///socket'
        if argv[1:3] == ['image', 'inspect']:
            return '[{"Id":"sha256:image"}]'
        if argv[1] == 'inspect':
            return '[{}]'
        if argv[1] == 'cp':
            copies.append(argv[2:])
        return ''
    monkeypatch.setattr(gate, 'checked', checked)
    monkeypatch.setattr(gate.db_ci, 'run_capture', lambda argv, dest, label, **kwargs:
                        {'exit_code': 1 if label == 'dependency_sync' else 0})
    with pytest.raises(ValueError, match='dependency sync failed'):
        gate.run_worker(candidate, B, A, False, tmp_path, here=installed)
    decoder = [pair for pair in copies if pair[1].endswith('/gate/tools/harness/compact_evidence.py')]
    assert len(decoder) == 1 and decoder[0][0] == str(installed / 'compact_evidence.py')


@pytest.fixture
def token_api(monkeypatch):
    from datetime import datetime, timezone
    client = gate.github_app
    clock = SimpleNamespace(wall=1800000000.0, mono=100.0)
    fake = SimpleNamespace(clock=clock, calls=[], minted=0, lifetime=3600, latency=0,
                           mutation=None, response=None, failures=[])
    monkeypatch.setattr(client.time, 'time', lambda: clock.wall)
    monkeypatch.setattr(client.time, 'monotonic', lambda: clock.mono)
    monkeypatch.setattr(client, 'jwt', lambda *_: 'SENTINEL_JWT')
    def api(method, path, token, body=None):
        fake.calls.append((method, path, token, body))
        if path == '/app/installations/2':
            install = {'app_id': 12, 'suspended_at': None, 'repository_selection': 'selected',
                       'account': {'login': 'owner'}, 'permissions': dict(client.PERMISSIONS)}
            if fake.mutation:
                fake.mutation(install)
            return install
        if path.endswith('/access_tokens'):
            assert token == 'SENTINEL_JWT'
            assert body == {'repository_ids': [42], 'permissions': client.PERMISSIONS}
            fake.minted += 1
            expiry = datetime.fromtimestamp(clock.wall + fake.lifetime, timezone.utc).isoformat()
            clock.wall += fake.latency
            clock.mono += fake.latency
            return fake.response if fake.response is not None else {
                'token': 'SENTINEL_TOKEN_' + str(fake.minted), 'expires_at': expiry}
        if fake.failures:
            error = fake.failures.pop(0)
            if error:
                raise error
        return {'ok': True}
    fake.api = api
    monkeypatch.setattr(client, 'api', api)
    fake.app = client.App({'app_id': 12, 'installation_id': 2, 'key_path': '/unused',
                          'repository': 'owner/repo', 'repository_id': 42})
    return fake


@pytest.mark.parametrize('jump,refresh', [((3539, 0), False), ((3540, 0), True),
    ((7200, 1613), True), ((0, 3000), True), ((-1, 1), True), ((-1, 3000), True)])
def test_token_two_clocks_and_exact_margin(token_api, jump, refresh):
    f = token_api
    f.app.request('GET', '/protected')
    f.clock.wall += jump[0]
    f.clock.mono += jump[1]
    f.app.request('GET', '/protected')
    assert f.minted == (2 if refresh else 1)
    assert f.calls[-1][2] == 'SENTINEL_TOKEN_' + str(f.minted)


def test_token_short_lifetime_latency_and_observed_rollback(token_api):
    f = token_api
    f.lifetime, f.latency = 120, 10
    f.app.refresh()
    assert f.app.deadline == 160  # anchored at 100, not mint completion at 110
    f.clock.wall += 30
    f.app.request('GET', '/protected')
    f.clock.wall -= 1  # still later than mint, but earlier than last observed request
    f.app.request('GET', '/protected')
    assert f.minted == 2


@pytest.mark.parametrize('response', [{}, {'token': 'SENTINEL_TOKEN'},
    {'token': '', 'expires_at': '2027-01-01T00:00:00Z'},
    {'token': None, 'expires_at': '2027-01-01T00:00:00Z'},
    {'token': 'bad token', 'expires_at': '2027-01-01T00:00:00Z'},
    *[{'token': 'SENTINEL_TOKEN', 'expires_at': value} for value in
      (None, 123, 'bad-SENTINEL_BODY', '2027-01-01T00:00:00',
       '2027-01-01T00:00:00+01:00', '99999-01-01T00:00:00Z',
       '2000-01-01T00:00:00Z')]])
def test_invalid_token_response_clears_stale_credentials(token_api, response):
    f = token_api
    f.app.refresh()
    f.response = response
    with pytest.raises(ValueError) as error:
        f.app.refresh()
    assert 'SENTINEL' not in str(error.value)
    assert f.app.token == '' and f.app.deadline == f.app.wall_deadline == 0
    assert all(c[1].startswith('/app/') for c in f.calls)
    with pytest.raises(ValueError):
        f.app.request('PATCH', '/protected')
    assert all(c[1].startswith('/app/') for c in f.calls)


@pytest.mark.parametrize('lifetime,latency', [(60, 0), (59, 0), (0, 0), (120, 60), (3600, 3000)])
def test_insufficient_lifetime_including_mint_latency(token_api, lifetime, latency):
    f = token_api
    f.lifetime, f.latency = lifetime, latency
    with pytest.raises(ValueError):
        f.app.request('GET', '/protected')
    assert len(f.calls) == 2 and f.app.token == ''


@pytest.mark.parametrize('mutation', [lambda i: i.update(app_id=13),
    lambda i: i.update(suspended_at='now'), lambda i: i.update(repository_selection='all'),
    lambda i: i.update(account={'login': 'other'}),
    lambda i: i.update(permissions=dict(gate.github_app.PERMISSIONS, contents='write'))])
def test_refresh_revalidates_installation_after_get401(token_api, mutation):
    f = token_api
    f.app.refresh()
    f.mutation = mutation
    f.failures = [gate.github_app.APIHTTPError('GET', 401)]
    with pytest.raises(ValueError):
        f.app.request('GET', '/protected')
    assert len(f.calls) == 4 and f.minted == 1 and f.app.token == ''


@pytest.mark.parametrize('second', [None, 401])
def test_get401_has_one_refresh_and_identical_retry(token_api, second):
    f = token_api
    f.failures = [gate.github_app.APIHTTPError('GET', 401),
                  gate.github_app.APIHTTPError('GET', second) if second else None]
    body = {'same': 'body'}
    if second:
        with pytest.raises(gate.github_app.APIHTTPError):
            f.app.request('GET', '/protected', body)
        assert f.app.token == ''
    else:
        assert f.app.request('GET', '/protected', body) == {'ok': True}
    assert f.minted == 2 and len(f.calls) == 6
    protected = [c for c in f.calls if c[1] == '/protected']
    assert [(c[0], c[1], c[3]) for c in protected] == [('GET', '/protected', body)] * 2
    assert [c[2] for c in protected] == ['SENTINEL_TOKEN_1', 'SENTINEL_TOKEN_2']


@pytest.mark.parametrize('stage', ['install', 'mint'])
def test_refresh401_never_recurses(token_api, monkeypatch, stage):
    f = token_api
    f.app.refresh()
    f.failures = [gate.github_app.APIHTTPError('GET', 401)]
    original = f.api
    def fail(method, path, token, body=None):
        if (stage == 'install' and path == '/app/installations/2'
                or stage == 'mint' and path.endswith('/access_tokens')):
            f.calls.append((method, path, token, body))
            raise gate.github_app.APIHTTPError(method, 401)
        return original(method, path, token, body)
    monkeypatch.setattr(gate.github_app, 'api', fail)
    with pytest.raises(gate.github_app.APIHTTPError):
        f.app.request('GET', '/protected')
    assert len(f.calls) == (4 if stage == 'install' else 5) and f.app.token == ''


@pytest.mark.parametrize('method,status', [('POST', 401), ('PATCH', 401),
    ('GET', 403), ('GET', 500), ('POST', 403), ('PATCH', 503)])
def test_client_never_replays_writes_or_other_status(token_api, method, status):
    f = token_api
    f.failures = [gate.github_app.APIHTTPError(method, status)]
    with pytest.raises(gate.github_app.APIHTTPError):
        f.app.request(method, '/protected', {'id': 21})
    assert f.minted == 1 and len(f.calls) == 3


@pytest.mark.parametrize('kind', ['401', '403', '500', 'redirect', 'timeout', 'transport'])
def test_real_api_sanitizes_errors_and_preserves_network_policy(monkeypatch, kind):
    import urllib.error
    from email.message import Message
    client = gate.github_app
    def opener(*handlers):
        assert handlers[0].proxies == {} and isinstance(handlers[1], client.NoRedirect)
        def opened(request, timeout):
            assert request.full_url == 'https://api.github.com/protected' and timeout == 60
            if kind.isdigit():
                headers = Message()
                headers['SENTINEL_HEADER'] = 'SENTINEL_TOKEN'
                raise urllib.error.HTTPError(request.full_url, int(kind), 'SENTINEL_BODY',
                                             headers, None)
            if kind == 'redirect':
                return handlers[1].redirect_request(None, None, 302, 'SENTINEL_BODY', {},
                                                      'https://evil.test/SENTINEL_TOKEN')
            if kind == 'timeout':
                raise TimeoutError('SENTINEL_TOKEN')
            raise urllib.error.URLError('SENTINEL_TOKEN')
        return SimpleNamespace(open=opened)
    monkeypatch.setattr(client.urllib.request, 'build_opener', opener)
    with pytest.raises(ValueError) as error:
        client.api('GET', '/protected', 'SENTINEL_TOKEN')
    assert 'SENTINEL' not in str(error.value)
    if kind.isdigit():
        assert isinstance(error.value, client.APIHTTPError) and error.value.status == int(kind)


@pytest.mark.parametrize('error', [TimeoutError('timeout'), ValueError('redirect'),
                                   OSError('ambiguous transport')])
def test_transport_or_redirect_never_triggers_authentication_retry(token_api, error):
    f = token_api
    f.failures = [error]
    with pytest.raises(type(error)):
        f.app.request('GET', '/protected')
    assert f.minted == 1 and len(f.calls) == 3


@pytest.mark.parametrize('scenario', ['success', 'test_only', 'refresh_failure', 'changed_head',
    'changed_base', 'cleanup_failure', 'repeated401', 'write401'])
def test_real_app_renewal_keeps_controller_publication_boundary(tmp_path, monkeypatch,
                                                              token_api, scenario):
    f = token_api
    config = private_json(tmp_path / 'config.json', f.app.config)
    admission = private_json(tmp_path / 'admission.json', {
        'format': 'kineticloop-local-admission-v1', 'snapshot': STATE,
        'controller': 'identity', 'trusted_code_reviewed': True})
    original = f.api
    writes = []
    def api(method, path, token, body=None):
        if path.startswith('/app/'):
            return original(method, path, token, body)
        original(method, path, token, body)
        if method in ('POST', 'PATCH'):
            writes.append((method, path, token, body))
            if scenario == 'write401' and method == 'PATCH':
                raise gate.github_app.APIHTTPError('PATCH', 401)
            return {'app': {'id': 12}, 'head_sha': B, 'name': 'local-db-gate', 'id': 21}
        if '/pulls/' in path:
            head = 'c' * 40 if scenario == 'changed_head' and f.minted > 1 else B
            return {'state': 'open', 'base': {'ref': 'master', 'sha': A, 'repo': {'id': 42}},
                    'head': {'sha': head, 'repo': {'id': 42}}}
        return {'object': {'sha': 'c' * 40 if scenario == 'changed_base' and f.minted > 1 else A}}
    monkeypatch.setattr(gate.github_app, 'api', api)
    monkeypatch.setattr(gate, 'installed', lambda *_: 'identity')
    monkeypatch.setattr(gate, 'checked', lambda *_: 'tree')
    monkeypatch.setattr(gate.db_policy, 'classify', lambda *_: {'full_database_required': True})
    def worker(*args, **kwargs):
        f.clock.wall += 7200  # monotonic stalls across the whole worker
        if scenario == 'refresh_failure':
            f.response = {'token': 'SENTINEL_TOKEN', 'expires_at': 'bad-SENTINEL_BODY'}
        if scenario == 'repeated401':
            f.failures = [gate.github_app.APIHTTPError('GET', 401)] * 2
        if scenario == 'cleanup_failure':
            raise ValueError('cleanup failed')
        return {'status': 'PASS', 'container_removed': True, 'volume_removed': True}
    monkeypatch.setattr(gate, 'run_worker', worker)
    monkeypatch.setattr(gate.os, 'environ', dict(gate.os.environ))
    monkeypatch.setattr(gate.sys, 'argv', ['local_gate.py', '--config', str(config),
        '--admission', str(admission), '--pr', '90', '--evidence-dir', str(tmp_path / 'run'),
        *(['--test-only'] if scenario == 'test_only' else [])])
    if scenario in ('success', 'test_only'):
        assert gate.main() == 0
    else:
        with pytest.raises(ValueError) as error:
            gate.main()
        assert 'SENTINEL' not in str(error.value)
    receipt = (tmp_path / 'run/receipt.json').read_text()
    assert 'SENTINEL' not in receipt
    if scenario != 'write401':
        assert json.loads(receipt)['status'] == ('PASS' if scenario in ('success', 'test_only') else 'FAIL')
    if scenario == 'test_only':
        assert writes == []
    else:
        assert writes[0][0] == 'POST'
        patches = [c for c in writes if c[0] == 'PATCH']
        assert len(patches) == (0 if scenario == 'refresh_failure' else 1)
        if patches:
            assert patches[0][1].endswith('/check-runs/21')
            assert patches[0][3]['conclusion'] == ('success' if scenario in ('success', 'write401') else 'failure')
            assert patches[0][2] != writes[0][2]
    # The controller's separate failure PATCH proactively renews after an unusable
    # credential; this is not a replay of the failed GET or a success publication.
    assert f.minted == {'repeated401': 4, 'refresh_failure': 3}.get(scenario, 2)


@pytest.mark.parametrize('missing_specialist', [False, True])
def test_hg050_real_governance_gate_requires_specialist_and_exact_scope(missing_specialist):
    spec = importlib.util.spec_from_file_location('expiry_validator_fixtures',
        Path(__file__).with_name('test_validator.py'))
    assert spec and spec.loader
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    fixture = fixtures.ValidatorTests()
    fixture.setUp()
    try:
        fixture.put('tools/harness/github_app.py', '# fixture correction\n')
        fixtures.refresh(fixture.root)
        tested = fixture.commit('prospective client correction')
        fixture.persist_governance_change('HG-050', tested, [],
            ['GENERAL'] if missing_specialist else ['GENERAL', 'SECURITY_DATA_BOUNDARY'])
        args = ('--ci-pr-base', fixture.base, '--ci-pr-head', 'HEAD')
        fixture.check(1 if missing_specialist else 0,
            'governance-required-reviews-not-pass:HG-050' if missing_specialist else '', *args)
        allowed = fixtures.v.governance_allowed_patterns('HG-050')
        for path in ('tools/harness/local_gate.py', '05_KineticLoop_Protocol_v1.2_FROZEN.md',
                     'docs/exec-plans/evidence/HG-050A/file', 'docs/history/old.md',
                     'tests/db/test_workflow.py'):
            assert not fixtures.v.matches(path, allowed)
        fixture.put('tools/harness/local_gate.py', '# outside exact scope\n')
        fixture.commit('unauthorized controller edit')
        fixture.check(1, 'governance-write-scope:HG-050:tools/harness/local_gate.py', *args)
    finally:
        fixture.doCleanups()
