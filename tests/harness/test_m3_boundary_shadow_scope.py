"""HG042 exact tests-only scopes and truthful frozen boundary-layer ledger."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('boundary_shadow_validator', ROOT / 'tools/harness/validate_harness.py')
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
BACKLOG = json.loads((ROOT / v.BACKLOG).read_text())
TASKS = {t['id']: t for t in BACKLOG['tasks']}
PACKETS = {n: (ROOT / f'docs/exec-plans/active/{n}.md').read_text()
           for n in v.M3_BOUNDARY_SHADOW_IDS}
REQUIREMENTS = json.loads((ROOT / 'KineticLoop_Acceptance_Spec_v1.2.2.json').read_text())['supplemental_boundary_requirements']


@pytest.mark.parametrize('name', sorted(v.M3_BOUNDARY_SHADOW_IDS))
def test_exact_prospective_task_and_traceability(name: str) -> None:
    t = TASKS[name]
    assert v.m3_boundary_shadow_definition_errors(t) == []
    assert v.packet_errors(t, PACKETS[name]) == []
    trace = json.loads((ROOT / v.TRACEABILITY).read_text())['tasks']
    assert next(row for row in trace if row['id'] == name) == v.traceability_projection(t)
    assert t['status'] == 'NOT_STARTED' and t['evidence_refs'] == []
    assert v.packet_json_section(PACKETS[name], 'Prospective check status') == {
        check['check_id']: 'NOT_RUN' for check in t['check_contracts']}


@pytest.mark.parametrize('name', sorted(v.M3_BOUNDARY_SHADOW_IDS))
@pytest.mark.parametrize('field,value', [
    ('status', 'PASS'), ('task_identity', 'historical/KL-028'), ('depends_on', []),
    ('resource_keys', []), ('shared_hotspot', True),
    ('parallel_write_policy', 'SERIALIZE_WITH_OTHER_HOTSPOT_TASKS'),
    ('write_paths', ['src/kineticloop/**']),
    ('write_paths', ['tests/conftest.py']), ('write_paths', ['tests/db/helper.py']),
    ('write_paths', ['migrations/versions/new.py']),
    ('write_paths', ['tests/db/test_test_only_demo.py']),
    ('write_paths', ['compose.yaml']), ('write_paths', ['.github/workflows/ci.yml']),
    ('review_requirements', ['GENERAL']), ('environment_requirements', []),
    ('requirements_covered', ['R04@E2E']), ('check_contracts', []),
    ('checks_required_for_this_task', ['task_scope_e2e_checks']),
    ('packet_refinement', 'MUST_REFINE_BEFORE_READY'),
    ('entry_conditions', []), ('definition_of_done', 'All B product requirements PASS'),
])
def test_definition_scope_and_oracle_drift_fails_closed(name: str, field: str, value: object) -> None:
    changed = copy.deepcopy(TASKS[name])
    changed[field] = value
    assert v.m3_boundary_shadow_definition_errors(changed) == ['m3-boundary-shadow-definition:' + name]
    altered = copy.deepcopy(BACKLOG)
    next(t for t in altered['tasks'] if t['id'] == name)[field] = value
    assert 'm3-boundary-shadow-definition:' + name in v.task_definition_errors(ROOT, altered)[0]


def test_disjoint_tests_only_parallel_namespaces_and_review_union() -> None:
    boundary, shadow = TASKS['KL-028'], TASKS['KL-029']
    assert not set(boundary['write_paths']) & set(shadow['write_paths'])
    assert not set(boundary['resource_keys']) & set(shadow['resource_keys'])
    for task in (boundary, shadow):
        assert len(task['write_paths']) == 3
        assert all(p.startswith(('tests/', 'docs/contracts/')) and '*' not in p for p in task['write_paths'])
        assert task['shared_hotspot'] is False
        assert task['parallel_write_policy'] == 'PARALLEL_IF_DEPENDENCIES_MET'
        assert 'KL-027' in task['depends_on']
        environment = task['environment_requirements'][0]
        for phrase in ('first7 lowercase hex', 'first12 SHA256', 'Path(ROOT).resolve()', 'before lifecycle', 'nested', 'peer-root'):
            assert phrase in environment
    assert boundary['requirements_covered'] == [f'B{n:02}' for n in range(1, 19)]
    assert shadow['requirements_covered'] == []
    assert boundary['review_requirements'] == ['DB_CONCURRENCY', 'GENERAL', 'PROTOCOL']
    assert shadow['review_requirements'] == boundary['review_requirements'] + ['SECURITY_DATA_BOUNDARY']


def test_all_31_given_when_then_layers_and_truthful_dispositions() -> None:
    ledger = v.packet_json_section(PACKETS['KL-028'], 'Boundary layer ledger')
    assert len(ledger) == 31
    assert v.m3_boundary_layer_errors(ledger, REQUIREMENTS) == []
    assert {layer: sum(row['layer'] == layer for row in ledger)
            for layer in ('PU', 'DC', 'WF', 'E2E')} == {'PU': 8, 'DC': 14, 'WF': 1, 'E2E': 8}
    deferred = [row for row in ledger if row['disposition'] == 'DEFERRED_LAYER']
    assert len(deferred) == 11
    assert {row['requirement_id'] for row in deferred if row['layer'] == 'E2E'} == {
        'B04', 'B05', 'B07', 'B08', 'B10', 'B14', 'B16', 'B18'}
    checks = {c['check_id']: c for c in TASKS['KL-028']['check_contracts']}
    for row in ledger:
        assert row['status'] == 'NOT_RUN'
        if row['disposition'] != 'DEFERRED_LAYER':
            assert checks[row['check_id']]['command'] == row['selector']
            assert row['pass_oracle'] in checks[row['check_id']]['pass_oracle']
        else:
            assert row['reason'] and row['required_future_owner']
    b04 = next(row for row in ledger if (row['requirement_id'], row['layer']) == ('B04', 'DC'))
    assert 'guard support' in b04['qualification'] and 'NOT_RUN' in b04['qualification']
    assert b04['disposition'] == 'DEFERRED_FULL_ORACLE_WITH_GUARD_SUPPORT'
    assert 'explicitly rejects Reauthorize' in b04['qualification']
    assert len(deferred) + 1 == 12


@pytest.mark.parametrize('mutation', ['omit', 'duplicate', 'relabel', 'pass', 'skip', 'weaken', 'remove_owner', 'promote_deferred', 'remove_b04_qualification'])
def test_layer_negative_guards(mutation: str) -> None:
    ledger = v.packet_json_section(PACKETS['KL-028'], 'Boundary layer ledger')
    if mutation == 'omit':
        ledger.pop()
    elif mutation == 'duplicate':
        ledger.append(copy.deepcopy(ledger[0]))
    elif mutation == 'relabel':
        ledger[0]['layer'] = 'DC'
    elif mutation in ('pass', 'skip'):
        ledger[0]['status'] = mutation.upper()
    elif mutation == 'weaken':
        ledger[0]['then'] = 'BUILDING accepted'
    elif mutation == 'remove_owner':
        next(row for row in ledger if row['disposition'] == 'DEFERRED_LAYER').pop('required_future_owner')
    elif mutation == 'promote_deferred':
        next(row for row in ledger if row['layer'] == 'WF')['disposition'] = 'KL028_PLANNED_EXECUTABLE'
    else:
        next(row for row in ledger if (row['requirement_id'], row['layer']) == ('B04', 'DC')).pop('qualification')
    assert v.m3_boundary_layer_errors(ledger, REQUIREMENTS)


@pytest.mark.parametrize('name', sorted(v.M3_BOUNDARY_SHADOW_IDS))
@pytest.mark.parametrize('heading', ['Prospective check status', 'Merged owner and bootstrap boundary', 'Evidence and concurrency oracles', 'Isolated parallel test plan', 'Deferred layer boundary', 'Non-goals'])
def test_packet_boundary_drift(name: str, heading: str) -> None:
    text = PACKETS[name]
    block = v.section(text, heading)
    assert block is not None
    changed = text.replace(block, '\nUnsupported bypass.\n', 1)
    assert 'm3-boundary-shadow-packet:' + name in v.packet_errors(TASKS[name], changed)


def test_real_guard_and_missing_layer_distinctions() -> None:
    boundary, shadow = PACKETS['KL-028'], PACKETS['KL-029']
    for phrase in ('19 obligations', '12 layers are deferred', 'explicitly reject', 'API→workflow→DB→eligibility/rendering',
                   'B11/B12 PU', 'KL039', 'M3→M4 cycle', 'only M1/M2', 'not every B product requirement PASS'):
        assert phrase in boundary
        assert phrase in (ROOT / v.PROJECT_PLAN).read_text()
    for phrase in ('M2 G-SHADOW contract', 'KL045', 'external evaluation inputs',
                   'distinct reach labels', 'complete source/issuance/START', 'SECURITY_DATA_BOUNDARY'):
        assert phrase in shadow
    assert 'guard support' in boundary and 'pg_blocking_pids' in boundary
    assert 'No historical test/log reuse as new PASS' in boundary
    assert v.task_definition_errors(ROOT, BACKLOG)[0] == []


@pytest.mark.parametrize('phrase', ['19 obligations', '12 layers are deferred', 'API→workflow→DB→eligibility/rendering',
                                   'M3→M4 cycle', 'only M1/M2', 'read-only shared source'])
def test_parallel_and_deferred_plan_drift_fails_closed(phrase: str) -> None:
    text = (ROOT / v.PROJECT_PLAN).read_text()
    assert v.m3_boundary_shadow_plan_errors(text) == []
    assert phrase in text
    # Limit mutation to HG042's own plan section, not earlier plan text.
    before, block = text.split('## M3 boundary and shadow readiness — HG042', 1)
    altered = before + '## M3 boundary and shadow readiness — HG042' + block.replace(phrase, 'unsupported', 1)
    assert v.m3_boundary_shadow_plan_errors(altered) == ['m3-boundary-shadow-plan']


def test_plan_guard_allows_unrelated_governance_after_explicit_boundary() -> None:
    text = (ROOT / v.PROJECT_PLAN).read_text()
    assert v.m3_boundary_shadow_plan_errors(text + '\nGovernance fixture refinement.\n') == []
    assert v.m3_boundary_shadow_plan_errors(text.replace('<!-- HG042 plan end -->', '')) == ['m3-boundary-shadow-plan']
