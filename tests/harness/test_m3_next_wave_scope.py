"""HG038 exact next-wave ownership, oracle and independent evidence guards."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('m3_validator', ROOT / 'tools/harness/validate_harness.py')
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
TASKS = {t['id']: t for t in json.loads((ROOT / v.BACKLOG).read_text())['tasks']}


@pytest.mark.parametrize('name', sorted(v.M3_NEXT_WAVE_IDS))
def test_m3_next_wave_exact_projection(name: str) -> None:
    task = TASKS[name]
    assert v.m3_next_wave_definition_errors(task) == []
    assert v.packet_errors(task, (ROOT / f'docs/exec-plans/active/{name}.md').read_text()) == []
    trace = json.loads((ROOT / v.TRACEABILITY).read_text())['tasks']
    assert next(t for t in trace if t['id'] == name) == v.traceability_projection(task)
    assert task['status'] == 'NOT_STARTED' and task['evidence_refs'] == []
    assert task['checks_required_for_this_task'] == [c['check_id'] for c in task['check_contracts']]
    assert task['review_requirements'] == ['DB_CONCURRENCY', 'GENERAL', 'PROTOCOL']


@pytest.mark.parametrize('name', sorted(v.M3_NEXT_WAVE_IDS))
@pytest.mark.parametrize('field,value', [
    ('task_identity', 'historical-backlog/KL-026'),
    ('depends_on', []), ('conditional_depends_on', ['KL-052']),
    ('resource_keys', []), ('write_paths', ['src/kineticloop/**']),
    ('write_paths', ['tests/db/test_transaction_interfaces.py']),
    ('check_contracts', []), ('checks_required_for_this_task', ['I01-I09@DC']),
    ('requirements_covered', ['I04']), ('review_requirements', ['GENERAL']),
    ('entry_conditions', []), ('environment_requirements', []),
    ('definition_of_done', 'PASS'), ('packet_refinement', 'MUST_REFINE_BEFORE_READY'),
])
def test_m3_next_wave_drift_fails_closed(name: str, field: str, value: object) -> None:
    task = copy.deepcopy(TASKS[name])
    task[field] = value
    assert v.m3_next_wave_definition_errors(task) == ['m3-next-wave-definition:' + name]


@pytest.mark.parametrize('name', sorted(v.M3_NEXT_WAVE_IDS))
def test_m3_next_wave_oracle_and_boundary_drift(name: str) -> None:
    task = TASKS[name]
    packet = (ROOT / f'docs/exec-plans/active/{name}.md').read_text()
    for phrase in (task['check_contracts'][0]['pass_oracle'], 'No migrations', 'S01',
                   'first7 lowercase hex', 'No historical test/log reuse as new PASS'):
        assert phrase in packet
        changed = packet.replace(phrase, 'unsupported substitution', 1)
        assert 'm3-next-wave-packet:' + name in v.packet_errors(task, changed)


def test_m3_next_wave_tests_only_and_merged_interface_parallelism() -> None:
    left, demo = TASKS['KL-026'], TASKS['KL-027']
    for suite in (left, demo):
        assert all(p.startswith(('tests/', 'docs/contracts/')) for p in suite['write_paths'])
        assert suite['shared_hotspot'] is False
    for name in ('KL-075', 'KL-076', 'KL-077'):
        owner = TASKS[name]
        assert not set(left['resource_keys']) & set(owner['resource_keys'])
        assert not set(left['write_paths']) & set(owner['write_paths'])
        assert name in demo['depends_on']
        assert 'transaction_interfaces' in owner['resource_keys']
        assert 'src/kineticloop/persistence/transactions.py' in owner['write_paths']
        assert 'src/kineticloop/contracts/commands.py' not in owner['write_paths']
    assert TASKS['KL-076']['depends_on'][0] == 'KL-075'
    assert TASKS['KL-077']['depends_on'][0] == 'KL-076'
    assert not set(left['depends_on']) & {'KL-075', 'KL-076', 'KL-077'}
    assert left['requirements_covered'] == [f'I0{n}@DC' for n in range(1, 10)] + ['I04@WF']
    i04 = next(c for c in left['check_contracts'] if c['check_id'] == 'i04_dc')
    assert 'Actual CommitBundle T6' in i04['pass_oracle']
    assert 'does not satisfy I04@WF' in i04['pass_oracle']
    assert demo['requirements_covered'] == []


def test_m3_next_wave_global_validator_and_write_scope_guard() -> None:
    backlog = json.loads((ROOT / v.BACKLOG).read_text())
    assert v.task_definition_errors(ROOT, backlog)[0] == []
    for name in v.M3_NEXT_WAVE_IDS:
        altered = copy.deepcopy(backlog)
        task = next(t for t in altered['tasks'] if t['id'] == name)
        task['write_paths'].append('src/kineticloop/contracts/commands.py')
        assert 'm3-next-wave-definition:' + name in v.task_definition_errors(ROOT, altered)[0]
