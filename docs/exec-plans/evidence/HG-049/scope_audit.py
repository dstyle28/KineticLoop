"""Read-only HG049 scope, preservation and actual-source feasibility audit."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = '95ddd75d3eb410b7dffa15a1017276c504adc9a6'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def constants(source):
    names = {'M3_TASK_IDS', 'M3_EXIT_TASK_CHECKS', 'M3_CHECK_CONTRACT_DIGESTS',
             'M3_REGRESSION_COMMANDS', 'SOURCE_DECISION_PLAN_SHA256',
             'SOURCE_FIXTURE_REPLACEMENTS'}
    nodes = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in names for t in node.targets):
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                and t.value.id in names for t in node.targets):
            nodes.append(node)
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute)
              and isinstance(node.value.func.value, ast.Name)
              and node.value.func.value.id in names):
            nodes.append(node)
    values = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<base-constants>', 'exec'), values)
    return {key: values[key] for key in names}


def main():
    head = git('rev-parse', 'HEAD').decode().strip()
    git('merge-base', '--is-ancestor', BASE, head)
    spec = importlib.util.spec_from_file_location('audit_validator', ROOT / 'tools/harness/validate_harness.py')
    assert spec and spec.loader
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    changed = set(git('diff', '--name-only', BASE, head).decode().splitlines())
    allowed = v.governance_allowed_patterns('HG-049')
    assert all(v.matches(p, allowed) for p in changed), sorted(changed)
    before = json.loads(git('show', BASE + ':' + v.BACKLOG))
    after = json.loads((ROOT / v.BACKLOG).read_bytes())
    old = next(t for t in before['tasks'] if t['id'] == 'KL-080')
    new = next(t for t in after['tasks'] if t['id'] == 'KL-080')
    expected = copy.deepcopy(before)
    target = next(t for t in expected['tasks'] if t['id'] == 'KL-080')
    target['check_contracts'][7]['pass_oracle'] = new['check_contracts'][7]['pass_oracle']
    target['deliverables'][1] = new['deliverables'][1]
    assert expected == after
    assert len(new['write_paths']) == 19 and len(new['resource_keys']) == 8
    assert len(new['depends_on']) == 10 and len(new['check_contracts']) == 17
    assert new['status'] == 'NOT_STARTED' and new['requirements_covered'] == []
    assert new['evidence_refs'] == [] and len(new['review_requirements']) == 4
    assert not v.source_decision_definition_errors(new)
    assert not v.packet_errors(new, (ROOT / 'docs/exec-plans/active/KL-080.md').read_text())
    trace = json.loads((ROOT / v.TRACEABILITY).read_bytes())
    old_trace = json.loads(git('show', BASE + ':' + v.TRACEABILITY))
    expected_trace = copy.deepcopy(old_trace)
    i = next(i for i, t in enumerate(expected_trace['tasks']) if t['id'] == 'KL-080')
    expected_trace['tasks'][i] = v.traceability_projection(new)
    assert trace == expected_trace
    ratified = constants(git('show', BASE + ':tools/harness/validate_harness.py'))
    actual = constants((ROOT / 'tools/harness/validate_harness.py').read_bytes())
    key = 'KL-080:source_owner_trajectories_dc'
    assert ratified['M3_CHECK_CONTRACT_DIGESTS'][key] != actual['M3_CHECK_CONTRACT_DIGESTS'][key]
    ratified['M3_CHECK_CONTRACT_DIGESTS'][key] = v.canonical_value_sha(new['check_contracts'][7])
    assert ratified == actual and len(actual['M3_TASK_IDS']) == 17
    assert len([c for c in old['check_contracts'] if c['check_id'] != 'source_owner_trajectories_dc']) == 16
    protected = {entry['path'] for entry in
                 json.loads(git('show', BASE + ':FROZEN_BASELINE.json'))['files']}
    protected |= {'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', v.PROJECT_PLAN,
                  'MILESTONE_CLOSURE.schema.json', 'pyproject.toml', 'uv.lock'}
    history = {p for p in git('ls-tree', '-r', '--name-only', BASE).decode().splitlines()
               if p.startswith(('docs/history/', 'docs/exec-plans/completed/',
                                'docs/exec-plans/reviews/', 'docs/exec-plans/evidence/',
                                'docs/exec-plans/integrations/', 'docs/exec-plans/milestones/'))}
    assert not changed & (protected | history)
    assert not any(p.startswith(('src/', 'tests/db/', '.github/')) for p in changed)
    for path in ('docs/exec-plans/completed/KL-080_RESULT.yaml',
                 'docs/exec-plans/completed/KL-080_RESULT.json',
                 'docs/exec-plans/integrations/KL-080.json', 'docs/exec-plans/milestones/M3.json'):
        assert not (ROOT / path).exists()
    assert not (ROOT / 'docs/exec-plans/reviews/KL-080').exists()
    prerequisites = []
    for task in new['depends_on']:
        record = json.loads((ROOT / f'docs/exec-plans/integrations/{task}.json').read_bytes())
        assert record['integration_status'] == 'MERGED'
        assert record['task_identity'] == 'harness-backlog-v0.2/' + task
        git('merge-base', '--is-ancestor', record['merge_commit'], BASE)
        prerequisites.append({'task_identity': record['task_identity'], 'merge_commit': record['merge_commit']})
    assert json.loads((ROOT / 'docs/exec-plans/milestones/M2.json').read_bytes())['closure_status'] == 'PASS'
    source_paths = ['src/kineticloop/persistence/deterministic_planning.py',
                    'src/kineticloop/persistence/transactions.py',
                    'docs/contracts/deterministic_planning.md',
                    'docs/contracts/full_test_execution.md', 'docs/contracts/protocol_execution.md']
    hashes = {}
    for path in source_paths:
        data = git('show', BASE + ':' + path)
        assert (ROOT / path).read_bytes() == data
        hashes[path] = hashlib.sha256(data).hexdigest()
    producer = (ROOT / source_paths[0]).read_text()
    consumer = (ROOT / source_paths[1]).read_text()
    assert 'ref_s34_id=UUID(request.sources["nutrition"]["id"])' in producer
    assert '(demand_basis[2] != demand_basis[3] and not self._coordination_context.get("full_execution_members"))' in consumer
    assert 'demand_basis[1] != demand_basis[5]' in consumer
    assert 'policy, demand, and calendar authorization bounds must exist' in consumer
    assert 'certificate != expected_certificate' in consumer
    assert 'legacy downgrade denied' in consumer
    assert not v.source_decision_plan_errors((ROOT / v.PROJECT_PLAN).read_text())
    assert not v.governance_manifest_errors(ROOT, BASE, changed)
    index = json.loads((ROOT / v.INDEX).read_bytes())
    for entry in index['documents'] + index['machine_readable']:
        assert v.sha(ROOT / entry['path']) == entry['sha256']
    record_path = ROOT / 'docs/exec-plans/governance/HG-049.yaml'
    if record_path.exists():
        record = v.load_artifact(record_path)
        assert record['base_commit'] == BASE
        reviewed = head
        for review in (ROOT / 'docs/exec-plans/reviews/HG-049').glob('*.json'):
            reviewed = json.loads(review.read_bytes())['reviewed_head_sha']
        assert set(record['files_changed']) == set(v.changed_paths(ROOT, BASE, reviewed))
        assert not v.governance_suffix_errors(ROOT, record['tested_commit'], reviewed, 'HG-049', 'tested')
    print(json.dumps({'status': 'PASS', 'base_commit': BASE, 'head': head,
                      'changed_paths': sorted(changed), 'preserved_historical_paths': len(history),
                      'prerequisites': prerequisites, 'source_sha256': hashes,
                      'mechanical_negative_target': 'legacy dependency guard; later certificate not claimed',
                      'product_and_kl080_checks': 'NOT_RUN; this is source/governance evidence only'}, indent=2))


if __name__ == '__main__':
    main()
