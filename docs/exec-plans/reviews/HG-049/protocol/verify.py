"""Independent, read-only HG049 protocol review at the exact assigned revision."""
import ast
import copy
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'tools/harness'))
import compact_evidence as ce
import validate_harness as v

BASE = '95ddd75d3eb410b7dffa15a1017276c504adc9a6'
HEAD = 'ceed78db431a348aae0b599a5e1b09bb082fb968'
TESTED = '4db695230c2158f67394c8ac79a5f0fdf511849a'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def blob(path, revision=HEAD):
    return ce.blob(ROOT, path, revision)


def constants(revision):
    names = {'M3_TASK_IDS', 'M3_EXIT_TASK_CHECKS', 'M3_CHECK_CONTRACT_DIGESTS',
             'M3_REGRESSION_COMMANDS', 'SOURCE_DECISION_PLAN_SHA256',
             'SOURCE_FIXTURE_REPLACEMENTS'}
    nodes = []
    for node in ast.parse(blob('tools/harness/validate_harness.py', revision)).body:
        if isinstance(node, ast.Assign) and any(
            (isinstance(t, ast.Name) and t.id in names) or
            (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
             and t.value.id in names) for t in node.targets):
            nodes.append(node)
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute)
              and isinstance(node.value.func.value, ast.Name)
              and node.value.func.value.id in names):
            nodes.append(node)
    result = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<review-constants>', 'exec'), result)
    return {name: result[name] for name in names}


def main():
    assert git('rev-parse', 'HEAD').decode().strip() == HEAD
    git('merge-base', '--is-ancestor', BASE, HEAD)
    git('merge-base', '--is-ancestor', TESTED, HEAD)
    changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
    assert all(v.matches(p, v.governance_allowed_patterns('HG-049')) for p in changed)
    assert not any(p.startswith(('src/', 'tests/db/', '.github/')) for p in changed)
    prior = json.loads(blob(v.BACKLOG, BASE))
    current = json.loads(blob(v.BACKLOG))
    task = next(t for t in current['tasks'] if t['id'] == 'KL-080')
    old = next(t for t in prior['tasks'] if t['id'] == 'KL-080')
    expected = copy.deepcopy(prior)
    target = next(t for t in expected['tasks'] if t['id'] == 'KL-080')
    target['deliverables'][1] = task['deliverables'][1]
    target['check_contracts'][7]['pass_oracle'] = task['check_contracts'][7]['pass_oracle']
    assert current == expected
    assert len(task['check_contracts']) == 17
    assert len(task['write_paths']) == 19 and len(task['resource_keys']) == 8
    assert len(task['depends_on']) == 10 and len(task['review_requirements']) == 4
    assert task['requirements_covered'] == [] and task['status'] == 'NOT_STARTED'
    assert task['evidence_refs'] == []
    assert not v.source_decision_definition_errors(task)
    assert not v.source_decision_packet_errors(task, blob('docs/exec-plans/active/KL-080.md').decode())
    before_constants, after_constants = constants(BASE), constants(HEAD)
    key = 'KL-080:source_owner_trajectories_dc'
    before_constants['M3_CHECK_CONTRACT_DIGESTS'][key] = v.canonical_value_sha(task['check_contracts'][7])
    assert before_constants == after_constants
    assert len(after_constants['M3_TASK_IDS']) == 17
    history = [p for p in git('ls-tree', '-r', '--name-only', BASE).decode().splitlines()
               if p.startswith(('docs/history/', 'docs/exec-plans/completed/',
                                'docs/exec-plans/reviews/', 'docs/exec-plans/evidence/',
                                'docs/exec-plans/integrations/', 'docs/exec-plans/milestones/'))]
    assert not set(history).intersection(changed)
    protected = {p['path'] for p in json.loads(blob('FROZEN_BASELINE.json', BASE))['files']}
    protected.update({'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', v.PROJECT_PLAN,
                      'docs/harness/M3_CLOSURE_CONTRACT.md', 'MILESTONE_CLOSURE.schema.json'})
    assert not protected.intersection(changed)
    for path in protected:
        assert blob(path) == blob(path, BASE)
    absent = ['docs/exec-plans/completed/KL-080_RESULT.yaml',
              'docs/exec-plans/completed/KL-080_RESULT.json',
              'docs/exec-plans/integrations/KL-080.json', 'docs/exec-plans/milestones/M3.json']
    tree = set(git('ls-tree', '-r', '--name-only', HEAD).decode().splitlines())
    assert not tree.intersection(absent)
    assert not any(p.startswith('docs/exec-plans/reviews/KL-080/') for p in tree)
    sources = ['src/kineticloop/persistence/deterministic_planning.py',
               'src/kineticloop/persistence/transactions.py',
               'src/kineticloop/persistence/protocol_execution.py',
               'docs/contracts/deterministic_planning.md',
               'docs/contracts/full_action_preparation.md',
               'docs/contracts/full_test_execution.md',
               'docs/contracts/protocol_execution.md']
    source_hashes = {}
    for path in sources:
        raw = blob(path)
        assert raw == blob(path, BASE)
        source_hashes[path] = ce.digest(raw)
    producer = blob(sources[0]).decode()
    consumer = blob(sources[1]).decode()
    adapter = blob(sources[2]).decode()
    assert 'ref_s34_id=UUID(request.sources["nutrition"]["id"])' in producer
    assert 'ref_s34_id=UUID(payload["fitness_id"])' in producer
    guard = 'policy, demand, and calendar authorization bounds must exist'
    assert '(demand_basis[2] != demand_basis[3] and not self._coordination_context.get("full_execution_members"))' in consumer
    assert 'demand_basis[1] != demand_basis[5]' in consumer
    assert consumer.index(guard) < consumer.index('certificate != expected_certificate')
    assert 'legacy downgrade denied' in consumer
    body = consumer[consumer.index('if self.command_kind in {"CommitBundle", "Reauthorize"}:', consumer.index('def require_execution_request')):]
    assert body.index('self.prepare_authorization_basis(') < body.index('self.require_execution_request(')
    assert 'tx.lock_daily_head(inputs[0], create_first=True)' in adapter
    assert 'return execute_command(self._connection, "CommitBundle", subject, operation)' in adapter
    prerequisites = []
    for name in task['depends_on']:
        record = json.loads(blob(f'docs/exec-plans/integrations/{name}.json'))
        assert record['integration_status'] == 'MERGED'
        assert record['task_identity'] == 'harness-backlog-v0.2/' + name
        git('merge-base', '--is-ancestor', record['merge_commit'], BASE)
        result_path = f'docs/exec-plans/completed/{name}_RESULT.yaml'
        result = v.load_artifact(ROOT / result_path)
        assert blob(result_path) == blob(result_path, BASE)
        assert result['task_status'] == 'PASS'
        prerequisites.append({'task_identity': record['task_identity'], 'merge_commit': record['merge_commit']})
    evidence = 'docs/exec-plans/evidence/HG-049/'
    decoded = {}
    for path in tree:
        if path.startswith(evidence) and path.endswith('.json'):
            data = blob(path)
            envelope = ce.envelope(data)
            if envelope is not None:
                raw = ce.read(ROOT, path, HEAD)
                decoded[path] = {'decoded_sha256': ce.digest(raw), 'bytes': len(raw),
                                 'exit_code': envelope['exit_code'], 'tested_commit': envelope['tested_commit']}
    d = evidence + 'checks-4db6952/'
    execution = json.loads(ce.read(ROOT, d + 'harness-execution-json.json', HEAD))
    assert execution['exit_code'] == 0 and execution['errors'] == []
    calls = [r for r in execution['reports'] if r['phase'] == 'call']
    assert len(calls) == 1347 and all(r['outcome'] == 'passed' for r in execution['reports'])
    assert len({r['nodeid'] for r in calls}) == 1347
    for module in ['test_source_decision_scope.py', 'test_m3_milestone_closure.py']:
        assert any(module in r['nodeid'] for r in calls)
    junit = ET.fromstring(ce.read(ROOT, d + 'harness-junit-xml.json', HEAD))
    suites = list(junit.iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 1347
    assert all(int(s.attrib.get(k, 0)) == 0 for s in suites for k in ['failures', 'errors', 'skipped'])
    assert len(list(junit.iter('testcase'))) == 1347
    assert b'241 passed' in ce.read(ROOT, d + 'unit.json', HEAD)
    assert b'HARNESS_CHECK_PASS' in ce.read(ROOT, d + 'authority.json', HEAD)
    record = v.load_artifact(ROOT / 'docs/exec-plans/governance/HG-049.yaml')
    assert record['tested_commit'] == TESTED and record['base_commit'] == BASE
    assert set(record['files_changed']) == set(changed)
    assert not v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-049', 'tested')
    print(json.dumps({'reviewed_head_sha': HEAD, 'base_commit': BASE, 'status': 'PASS',
                      'source_hashes': source_hashes, 'preserved_history_paths': len(history),
                      'prerequisites': prerequisites, 'decoded_recorded_evidence': decoded,
                      'harness_passed': 1347, 'unit_passed': 241,
                      'scope': 'Prospective governance and static consumer audit; no database reach executed',
                      'pending': 'Exact-head hosted/App/full DB gates; KL080/M3/product/release remain separate'}, indent=2))


if __name__ == '__main__':
    main()
