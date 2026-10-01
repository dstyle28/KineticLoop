"""HG036 exact offline evaluation task governance and isolation regressions."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'fitness_eval_validator', ROOT / 'tools/harness/validate_harness.py')
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
TASKS = {t['id']: t for t in json.loads((ROOT / v.BACKLOG).read_text())['tasks']}
TASK = TASKS['KL-047']
PACKET = (ROOT / 'docs/exec-plans/active/KL-047.md').read_text()


def test_exact_fitness_evaluation_definition_packet_and_projection() -> None:
    assert v.fitness_evaluation_definition_errors(TASK) == []
    assert v.fitness_evaluation_packet_errors(TASK, PACKET) == []
    assert v.packet_errors(TASK, PACKET) == []
    trace = json.loads((ROOT / v.TRACEABILITY).read_text())['tasks']
    assert next(t for t in trace if t['id'] == 'KL-047') == v.traceability_projection(TASK)


@pytest.mark.parametrize('field', sorted(v.FITNESS_EVAL_DEFINITION_DIGESTS))
def test_all_fitness_definition_authorities_are_bound(field: str) -> None:
    altered = copy.deepcopy(TASK)
    altered[field] = None
    assert 'fitness-eval-definition:KL-047:' + field in (
        v.fitness_evaluation_definition_errors(altered))


@pytest.mark.parametrize('field,value', [
    ('depends_on', ['KL-019']),
    ('conditional_depends_on', ['KL-048']),
    ('resource_keys', []),
    ('resource_keys', ['registry_coordination']),
    ('write_paths', ['src/kineticloop/agents/**']),
    ('write_paths', ['src/kineticloop/persistence/evaluation.py']),
    ('write_paths', ['src/kineticloop/integrations/fixtures.py']),
    ('write_paths', ['src/kineticloop/__init__.py']),
    ('write_paths', ['pyproject.toml']),
    ('write_paths', ['tests/evaluation/**']),
    ('requirements_covered', ['R02@PU']),
    ('review_requirements', ['GENERAL']),
    ('packet_refinement', 'MUST_REFINE_BEFORE_READY'),
    ('parallel_write_policy', 'SERIALIZE_WITH_OTHER_HOTSPOT_TASKS'),
    ('definition_of_done', 'Synthetic task PASS closes G-REMOTE-AI and Fitness quality.'),
    ('entry_conditions', ['G-REMOTE-AI closed']),
])
def test_drift_or_circular_gate_fails_closed(field: str, value: object) -> None:
    altered = copy.deepcopy(TASK)
    altered[field] = value
    assert 'fitness-eval-definition:KL-047:' + field in (
        v.fitness_evaluation_definition_errors(altered))


@pytest.mark.parametrize('member', ['command', 'pass_oracle', 'check_id'])
def test_keeping_check_ids_cannot_weaken_execution_or_oracles(member: str) -> None:
    altered = copy.deepcopy(TASK)
    altered['check_contracts'][0][member] = 'echo bypass'
    assert 'fitness-eval-definition:KL-047:check_contracts' in (
        v.fitness_evaluation_definition_errors(altered))


@pytest.mark.parametrize('clause', [
    'No typed production FitnessProposal contract exists yet',
    'S48 still requires measured evaluation results',
    'Hevy plus HealthKit remain mandatory launch scope',
    'the retired spreadsheet task remains retired',
    'tests/evaluation',
    'expert labels/reference judgments',
    'missing/duplicate/extra outputs',
    'postfreeze mutation',
    'no release PASSED',
])
def test_packet_obligations_cannot_be_removed(clause: str) -> None:
    assert clause in PACKET
    assert v.fitness_evaluation_packet_errors(TASK, PACKET.replace(clause, '')) == [
        'fitness-eval-packet:KL-047']


def test_real_task_definition_and_packet_validation_use_fitness_guards() -> None:
    backlog = json.loads((ROOT / v.BACKLOG).read_text())
    altered = copy.deepcopy(backlog)
    next(t for t in altered['tasks'] if t['id'] == 'KL-047')['resource_keys'] = []
    assert 'fitness-eval-definition:KL-047:resource_keys' in (
        v.task_definition_errors(ROOT, altered)[0])
    assert 'fitness-eval-packet:KL-047' in v.packet_errors(TASK, PACKET + '\nrelease PASSED\n')


def test_offline_task_remains_independent_of_protocol_execution() -> None:
    protocol = TASKS['KL-019']
    assert set(TASK['resource_keys']) == {'fitness_eval_contract'}
    assert not set(TASK['resource_keys']) & set(protocol['resource_keys'])
    assert TASK['depends_on'] == ['KL-005', 'KL-018']
    assert TASK['conditional_depends_on'] == []
    for left in TASK['write_paths']:
        for right in protocol['write_paths']:
            assert left != right
            assert not v.matches(left, [right]) and not v.matches(right, [left])
    assert TASK['write_paths'].count('src/kineticloop/evaluation/__init__.py') == 1
    assert all('*' not in p for p in TASK['write_paths'])
    assert 'uv run pytest -q tests/evaluation' in [c['command'] for c in TASK['check_contracts']]
    assert TASK['commands'] == TASK['transaction_boundaries'] == []


def test_historical_unrefined_base_and_unrelated_tasks_remain_compatible() -> None:
    historical = {**TASK, 'packet_refinement': 'MUST_REFINE_BEFORE_READY'}
    assert v.fitness_evaluation_packet_errors(historical, 'historical original packet') == []
    for task in TASKS.values():
        if task['id'] != 'KL-047':
            assert v.fitness_evaluation_definition_errors(task) == []
            assert v.fitness_evaluation_packet_errors(task, 'unrelated') == []
