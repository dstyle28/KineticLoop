"""Independent HG-050 probes. Synthetic credentials; no network or controller run."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location('hg050_review_fixtures',
    ROOT / 'tests/harness/test_local_gate.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
gate = fixtures.gate
token_api = fixtures.token_api


@pytest.mark.parametrize('stage', ['jwt', 'validation'])
def test_age_includes_latency_before_mint(token_api, monkeypatch, stage):
    f = token_api
    if stage == 'jwt':
        def jwt(*args):
            f.clock.wall += 2999
            f.clock.mono += 2999
            return 'SENTINEL_JWT'
        monkeypatch.setattr(gate.github_app, 'jwt', jwt)
    else:
        def mutation(install):
            f.clock.wall += 2999
            f.clock.mono += 2999
        f.mutation = mutation
    f.app.refresh()
    assert f.app.deadline == 3100  # pre-JWT monotonic 100 + cap 3000
    f.clock.wall += 1
    f.clock.mono += 1
    f.app.request('GET', '/protected')
    assert f.minted == 2


@pytest.mark.parametrize('clock', ['wall', 'mono'])
def test_clock_rollback_during_mint_rejects_generation(token_api, monkeypatch, clock):
    f = token_api
    original = f.api
    def api(*args):
        result = original(*args)
        if args[1].endswith('/access_tokens'):
            setattr(f.clock, clock, getattr(f.clock, clock) - 1)
        return result
    monkeypatch.setattr(gate.github_app, 'api', api)
    with pytest.raises(ValueError, match='invalid or insufficient'):
        f.app.request('GET', '/protected')
    assert f.app.token == '' and len(f.calls) == 2


@pytest.mark.parametrize('scenario', ['admission', 'start_check', 'finish_check', 'final_snapshot401'])
def test_real_app_additional_fail_closed_controller_boundaries(tmp_path, monkeypatch,
                                                              token_api, scenario):
    f = token_api
    original = f.api
    writes, workers = [], []
    pulls = 0
    def api(method, path, token, body=None):
        nonlocal pulls
        if path.startswith('/app/'):
            return original(method, path, token, body)
        original(method, path, token, body)
        if method in ('POST', 'PATCH'):
            writes.append((method, path, body))
            wrong = scenario == ('start_check' if method == 'POST' else 'finish_check')
            return {'app': {'id': 13 if wrong else 12}, 'head_sha': fixtures.B,
                    'name': 'local-db-gate', 'id': 22 if wrong else 21}
        if '/pulls/' in path:
            pulls += 1
            if scenario == 'final_snapshot401' and pulls >= 3:
                raise gate.github_app.APIHTTPError('GET', 401)
            return {'state': 'open', 'base': {'ref': 'master', 'repo': {'id': 42}},
                    'head': {'sha': fixtures.B, 'repo': {'id': 42}}}
        return {'object': {'sha': fixtures.A}}
    monkeypatch.setattr(gate.github_app, 'api', api)
    config = fixtures.private_json(tmp_path / 'config.json', f.app.config)
    admission = fixtures.private_json(tmp_path / 'admission.json', {
        'format': 'kineticloop-local-admission-v1',
        'snapshot': dict(fixtures.STATE, head='c' * 40) if scenario == 'admission' else fixtures.STATE,
        'controller': 'identity', 'trusted_code_reviewed': True})
    monkeypatch.setattr(gate, 'installed', lambda *_: 'identity')
    monkeypatch.setattr(gate, 'checked', lambda *_: 'tree')
    monkeypatch.setattr(gate.db_policy, 'classify', lambda *_: {'full_database_required': True})
    def worker(*args, **kwargs):
        workers.append(True)
        f.clock.wall += 7200
        return {'status': 'PASS', 'container_removed': True, 'volume_removed': True}
    monkeypatch.setattr(gate, 'run_worker', worker)
    monkeypatch.setattr(gate.os, 'environ', dict(gate.os.environ))
    monkeypatch.setattr(gate.sys, 'argv', ['local_gate.py', '--config', str(config),
        '--admission', str(admission), '--pr', '90', '--evidence-dir', str(tmp_path / 'run')])
    with pytest.raises(ValueError) as error:
        gate.main()
    assert 'SENTINEL' not in str(error.value)
    assert not (tmp_path / 'run/published-check.json').exists()
    if scenario == 'admission':
        assert writes == [] and workers == []
    elif scenario == 'start_check':
        assert len(writes) == 1 and workers == []
    elif scenario == 'finish_check':
        assert len(writes) == 2 and writes[-1][1].endswith('/check-runs/21')
    else:
        assert len(writes) == 1 and len(workers) == 1
    for path in (tmp_path / 'run').glob('*.json'):
        assert 'SENTINEL' not in path.read_text()
