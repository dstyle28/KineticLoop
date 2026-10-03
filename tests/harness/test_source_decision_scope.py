"""Prospective KL080 governance feasibility and fail-closed scope, never runtime PASS."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('source_validator', ROOT / 'tools/harness/validate_harness.py')
assert SPEC and SPEC.loader
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
TASK = next(t for t in json.loads((ROOT / v.BACKLOG).read_text())['tasks'] if t['id'] == 'KL-080')
PACKET = (ROOT / 'docs/exec-plans/active/KL-080.md').read_text()
BASE = '26906bd7f4444914c228e98377f2b164fee0dd5d'
PROFILE_BASE = '95ddd75d3eb410b7dffa15a1017276c504adc9a6'


def test_exact_prospective_definition_packet_and_projection():
    assert TASK['status'] == 'NOT_STARTED'
    assert TASK['evidence_refs'] == [] and TASK['requirements_covered'] == []
    assert v.source_decision_definition_errors(TASK) == []
    assert v.packet_errors(TASK, PACKET) == []
    trace = json.loads((ROOT / v.TRACEABILITY).read_text())['tasks']
    assert v.traceability_projection(TASK) == next(t for t in trace if t['id'] == 'KL-080')
    assert 'KL-080' in v.M3_TASK_IDS and len(v.M3_TASK_IDS) == 17
    assert v.source_decision_plan_errors((ROOT / v.PROJECT_PLAN).read_text()) == []
    assert v.m3_closure_plan_errors((ROOT / v.PROJECT_PLAN).read_text()) == []


@pytest.mark.parametrize('field,value', [
    ('depends_on', ['KL-076']), ('conditional_depends_on', ['KL-080']),
    ('write_paths', ['src/kineticloop/**']), ('resource_keys', ['transaction_interfaces']),
    ('review_requirements', ['GENERAL']), ('status', 'PASS'),
    ('entry_conditions', ['M3 closure PASS']), ('requirements_covered', ['B01']),
    ('environment_requirements', ['Default database allowed']),
    ('packet_refinement', 'DRAFT'), ('write_paths_status', 'UNREFINED'),
    ('table_ids', ['S27']), ('transaction_boundaries', ['T6']),
])
def test_definition_cannot_weaken_scope_prerequisites_or_reviews(field, value):
    task = copy.deepcopy(TASK)
    task[field] = value
    assert v.source_decision_definition_errors(task)


@pytest.mark.parametrize('mutation', ['omitted', 'oracle', 'command', 'selector', 'extra'])
def test_check_matrix_cannot_be_weakened(mutation):
    task = copy.deepcopy(TASK)
    if mutation == 'omitted':
        task['check_contracts'].pop(6)
    elif mutation == 'extra':
        task['write_paths'].append('tests/fixtures/**')
    else:
        task['check_contracts'][6]['pass_oracle' if mutation == 'oracle' else 'command'] = (
            'Any rejection counts as freshness proof' if mutation == 'oracle' else
            'uv run pytest -q tests/unit/workflow/test_source_decision_conformance.py')
    assert v.source_decision_definition_errors(task)


@pytest.mark.parametrize('literal', ['earlier', 'S27 PlanningIntent ADMITTED', 'Hevy and HealthKit',
                                     'AMBIGUOUS', 'current_database', 'NOT_RUN',
                                     'kl079-full-actions-v1', 'immutable'])
def test_packet_semantics_are_pinned(literal):
    assert literal in PACKET
    assert v.source_decision_packet_errors(TASK, PACKET.replace(literal, 'weakened'))


@pytest.mark.parametrize('path', list(v.SOURCE_FIXTURE_REPLACEMENTS))
def test_only_identified_old_fixture_literals_can_change(path):
    before = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)
    after = before
    for old, new in v.SOURCE_FIXTURE_REPLACEMENTS[path]:
        assert after.count(old.encode()) == 1
        after = after.replace(old.encode(), new.encode(), 1)
    assert v.source_fixture_content_errors(path, before, after) == []
    assert v.source_fixture_content_errors(path, before, before)
    assert v.source_fixture_content_errors(path, before, after + b'\n')
    assert v.source_fixture_content_errors(path, before, after.replace(b'assert ', b'#assert ', 1))
    if 'AMBIGUOUS' in str(v.SOURCE_FIXTURE_REPLACEMENTS[path]):
        assert v.source_fixture_content_errors(path, before, after.replace(b'AMBIGUOUS', b'MATCHED'))


def test_governance_exact_scope_excludes_runtime_history_and_closure():
    allowed = v.governance_allowed_patterns('HG-045')
    for path in ['src/kineticloop/persistence/transactions.py', 'tests/db/test_factsets.py',
                 'docs/exec-plans/active/KL-079.md', 'docs/exec-plans/milestones/M3.json',
                 'docs/exec-plans/reviews/KL-076/GENERAL.json', 'FROZEN_BASELINE.json',
                 '.github/workflows/ci.yml']:
        assert not v.matches(path, allowed)
    for path in ['docs/exec-plans/active/KL-080.md', 'tests/harness/test_source_decision_scope.py',
                 'docs/exec-plans/integrations/KL-028.json', 'docs/exec-plans/evidence/HG-045/a.json']:
        assert v.matches(path, allowed)


def test_all_prior_m3_exits_and_commands_are_preserved():
    namespace: dict[str, Any] = {}
    source = subprocess.check_output(['git', 'show', BASE + ':' + 'tools/harness/validate_harness.py'],
                                     cwd=ROOT).decode()
    # Read only the protected-base ratified constants, no import of historical validator.
    lines = '\n'.join(line for line in source.splitlines() if line.startswith((
        'M3_EXIT_TASK_CHECKS = ', 'M3_CHECK_CONTRACT_DIGESTS = ', 'M3_REGRESSION_COMMANDS = ')))
    exec(lines, namespace)
    for key, value in namespace['M3_EXIT_TASK_CHECKS'].items():
        assert v.M3_EXIT_TASK_CHECKS[key] == value
    for key, value in namespace['M3_CHECK_CONTRACT_DIGESTS'].items():
        assert v.M3_CHECK_CONTRACT_DIGESTS[key] == value
    old = namespace['M3_REGRESSION_COMMANDS']
    assert v.M3_REGRESSION_COMMANDS[:len(old)] == old
    assert len(v.M3_REGRESSION_COMMANDS) == len(set(v.M3_REGRESSION_COMMANDS))
    source_checks = [c for c in TASK['check_contracts'] if c['check_id'].startswith('source_')]
    assert v.M3_EXIT_TASK_CHECKS['source_decision_conformance'] == {
        'KL-080': [c['check_id'] for c in source_checks]}
    for contract in source_checks:
        assert contract['command'] in v.M3_REGRESSION_COMMANDS
        assert v.M3_CHECK_CONTRACT_DIGESTS['KL-080:' + contract['check_id']] == v.canonical_value_sha(contract)


def test_current_harness_cannot_omit_corrective_task():
    backlog = json.loads((ROOT / v.BACKLOG).read_text())
    backlog['tasks'] = [t for t in backlog['tasks'] if t['id'] != 'KL-080']
    backlog['task_count'] -= 1
    backlog['active_task_count'] -= 1
    errors, _ = v.task_definition_errors(ROOT, backlog)
    assert 'source-decision-task-missing:KL-080' in errors


def test_corrective_task_cannot_omit_any_required_fixture_file():
    paths = set(v.SOURCE_FIXTURE_REPLACEMENTS)
    errors = v.task_fixture_scope_errors(ROOT, BASE, 'HEAD', 'KL-080', set())
    assert set(errors) == {'source-fixture-correction-missing:KL-080:' + path for path in paths}
    assert v.task_fixture_scope_errors(ROOT, BASE, 'HEAD', 'HG-045', set()) == []


def test_new_packet_is_in_the_hashed_delivery_manifest():
    manifest = json.loads((ROOT / v.MANIFEST).read_text())
    entries = [e for e in manifest['files'] if e['path'] == 'docs/exec-plans/active/KL-080.md']
    assert len(entries) == 1
    path = ROOT / entries[0]['path']
    assert entries[0]['sha256'] == v.sha(path)
    assert entries[0]['bytes'] == path.stat().st_size


@pytest.mark.parametrize('literal', [
    'actual kl079-full-actions-v1 F/D/N owners', 'full T6',
    'START -> ordinary PAUSE -> RESUME -> CONTINUE', 'for both action members',
    'exact current member bindings', 'complete immutable source history',
    'positive through COMMIT_READY', 'untouched owner-produced mechanical S37',
    'well-formed legacy CommitBundle', 'authenticated current ingress',
    'correct policy, closure, owner, request, attempt, fence, lease, epoch',
    'execution basis, key and fingerprint', 'actual legacy dependency/certificate consumer',
    'complete zero effects, including first-use head rollback', 'exact reached guard',
    'request construction, registration, unrelated ingress/lifecycle/hash errors',
    'full-policy downgrade are insufficient substitutes',
    'Existing synthetic legacy execution regressions remain mandatory support coverage',
    'cannot substitute for canonical source-to-execution evidence',
    'No target seeding, caller PASS, certificate rewriting, policy downgrade',
    'production or real-data-shadow output',
])
def test_profile_boundary_oracle_cannot_be_weakened(literal):
    task = copy.deepcopy(TASK)
    contract = next(c for c in task['check_contracts']
                    if c['check_id'] == 'source_owner_trajectories_dc')
    assert literal in contract['pass_oracle']
    contract['pass_oracle'] = contract['pass_oracle'].replace(literal, 'omitted')
    assert v.source_decision_definition_errors(task)
    assert v.canonical_value_sha(contract) != v.M3_CHECK_CONTRACT_DIGESTS[
        'KL-080:source_owner_trajectories_dc']
    assert v.source_decision_packet_errors(TASK, PACKET.replace(literal, 'omitted'))


def test_profile_refinement_preserves_all_other_definitions_and_m3_contracts():
    before = json.loads(subprocess.check_output(
        ['git', 'show', PROFILE_BASE + ':' + v.BACKLOG], cwd=ROOT))
    old = next(t for t in before['tasks'] if t['id'] == 'KL-080')
    expected = copy.deepcopy(old)
    expected['deliverables'][1] = TASK['deliverables'][1]
    expected['check_contracts'][7]['pass_oracle'] = TASK['check_contracts'][7]['pass_oracle']
    assert TASK == expected
    assert len(TASK['write_paths']) == 19 and len(TASK['resource_keys']) == 8
    assert len(TASK['depends_on']) == 10 and len(TASK['check_contracts']) == 17
    source = subprocess.check_output(
        ['git', 'show', PROFILE_BASE + ':tools/harness/validate_harness.py'], cwd=ROOT).decode()
    namespace: dict[str, Any] = {}
    constants = '\n'.join(line for line in source.splitlines() if line.startswith((
        'M3_TASK_IDS = ', 'M3_EXIT_TASK_CHECKS', 'M3_CHECK_CONTRACT_DIGESTS',
        'M3_REGRESSION_COMMANDS', 'SOURCE_DECISION_PLAN_SHA256 = ')))
    exec(constants, namespace)
    assert v.M3_TASK_IDS == namespace['M3_TASK_IDS']
    assert v.M3_EXIT_TASK_CHECKS == namespace['M3_EXIT_TASK_CHECKS']
    assert v.M3_REGRESSION_COMMANDS == namespace['M3_REGRESSION_COMMANDS']
    assert v.SOURCE_DECISION_PLAN_SHA256 == namespace['SOURCE_DECISION_PLAN_SHA256']
    digests = dict(namespace['M3_CHECK_CONTRACT_DIGESTS'])
    key = 'KL-080:source_owner_trajectories_dc'
    assert digests[key] != v.M3_CHECK_CONTRACT_DIGESTS[key]
    digests[key] = v.M3_CHECK_CONTRACT_DIGESTS[key]
    assert v.M3_CHECK_CONTRACT_DIGESTS == digests


def test_hg049_exact_scope_excludes_every_other_owner_and_artifact():
    allowed = v.governance_allowed_patterns('HG-049')
    assert len(allowed) == 10
    for path in [v.BACKLOG, v.TRACEABILITY, v.INDEX, v.MANIFEST,
                 'docs/exec-plans/active/KL-080.md', 'tools/harness/validate_harness.py',
                 'tests/harness/test_source_decision_scope.py',
                 'docs/exec-plans/governance/HG-049.yaml',
                 'docs/exec-plans/evidence/HG-049/scope_audit.py',
                 'docs/exec-plans/reviews/HG-049/GENERAL.json']:
        assert v.matches(path, allowed)
    for path in ['src/kineticloop/persistence/transactions.py', v.PROJECT_PLAN,
                 'tests/db/test_source_decision_conformance.py', 'uv.lock',
                 'CURRENT_REQUIREMENT_SET.json', 'FROZEN_BASELINE.json',
                 'docs/exec-plans/evidence/HG-045/FEASIBILITY.md',
                 'docs/exec-plans/completed/KL-080_RESULT.yaml',
                 'docs/exec-plans/integrations/KL-080.json',
                 'docs/exec-plans/reviews/KL-080/GENERAL.json',
                 'docs/exec-plans/milestones/M3.json',
                 'docs/exec-plans/evidence/HG-049A/probe.json',
                 '.github/workflows/db.yml', 'tools/harness/local_gate.py']:
        assert not v.matches(path, allowed)
