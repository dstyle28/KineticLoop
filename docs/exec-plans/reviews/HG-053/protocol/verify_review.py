"""Independent HG053 exact-revision evidence and scope verification; no runtime tests."""
import json
import subprocess
import hashlib
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import jsonschema
import yaml

B = 'c82e50aefad5c4d9e325d4928a8f96032b81192d'
C = 'a75a41edfb1b58828b81053b4ac3afa51457a279'
R = '2936848abed73320db56f71a649e86eca1497502'
ROOT = Path(__file__).resolve().parents[5]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def blob(path, revision=R):
    return git('show', revision + ':' + path)


def recover(path):
    return subprocess.check_output([str(ROOT / '.venv/bin/python'), 'tools/harness/compact_evidence.py', 'read', path, '--revision', R], cwd=ROOT)


def junit_identity(node):
    path, _, tail = node.partition('::')
    classname = path[:-3].replace('/', '.')
    before_parameters = tail.split('[', 1)[0]
    if '::' in before_parameters:
        cls, _, tail = tail.partition('::')
        classname += '.' + cls
    return classname, tail


def main():
    record = yaml.safe_load(blob('docs/exec-plans/governance/HG-053.yaml'))
    jsonschema.validate(record, json.loads(blob('HARNESS_CHANGE.schema.json')))
    assert record['base_commit'] == B and record['tested_commit'] == C
    assert record['change_status'] == 'PASS' and record['frozen_impact'] == 'NONE'
    changed = git('diff', '--name-only', B, R).decode().splitlines()
    assert sorted(changed) == sorted(record['files_changed'])
    commits = git('rev-list', '--reverse', C + '..' + R).decode().splitlines()
    assert commits
    suffix = []
    for commit in commits:
        assert len(git('show', '-s', '--format=%P', commit).decode().split()) == 1
        paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', commit).decode().splitlines()
        assert all(p.startswith('docs/exec-plans/evidence/HG-053/') or p == 'docs/exec-plans/governance/HG-053.yaml' for p in paths)
        assert all(not git('ls-tree', C, '--', p).strip() for p in paths)
        suffix.append({'commit': commit, 'new_evidence_or_record_files': len(paths)})
    assert not git('diff', '--name-only', B, R, 'src', 'tests', 'migrations', 'tools', '.github').strip()
    authorities = ['05_KineticLoop_Protocol_v1.2_FROZEN.md', '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'docs/exec-plans/milestones/M3.json']
    for path in authorities:
        assert blob(path, B) == blob(path)
    targets = ['KL-036', 'KL-037']
    for path in ['KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Harness_Traceability_v0.3.json']:
        old = json.loads(blob(path, B)); new = json.loads(blob(path))
        assert {k: v for k, v in old.items() if k != 'tasks'} == {k: v for k, v in new.items() if k != 'tasks'}
        assert [t['id'] for t in old['tasks']] == [t['id'] for t in new['tasks']]
        assert [a['id'] for a, b in zip(old['tasks'], new['tasks']) if a != b] == targets
    backlog = json.loads(blob('KineticLoop_Harness_Backlog_v0.2.json'))
    actual_deps = {}
    for task in backlog['tasks']:
        if task['id'] not in targets:
            continue
        assert task['status'] == 'NOT_STARTED' and task['requirements_covered'] == [] and task['evidence_refs'] == []
        assert task['review_requirements'] == ['DB_CONCURRENCY', 'GENERAL', 'PROTOCOL', 'SECURITY_DATA_BOUNDARY']
        assert task['shared_hotspot'] and task['parallel_write_policy'] == 'SERIALIZE_WITH_OTHER_HOTSPOT_TASKS'
        for dep in task['depends_on']:
            prior = yaml.safe_load(blob('docs/exec-plans/completed/' + dep + '_RESULT.yaml', B))
            integ = json.loads(blob('docs/exec-plans/integrations/' + dep + '.json', B))
            assert prior['task_identity'] == integ['task_identity'] == 'harness-backlog-v0.2/' + dep
            assert prior['task_status'] == prior['task_checks_status'] == 'PASS'
            subprocess.run(['git', 'merge-base', '--is-ancestor', integ['merge_commit'], B], cwd=ROOT, check=True)
            actual_deps[dep] = integ['merge_commit']
    index_path = 'docs/exec-plans/evidence/HG-053/checks-' + C + '/CHECK_INDEX.json'
    index = json.loads(blob(index_path))
    assert index['tested_commit'] == C and index['runtime_checks'] == 'NOT_RUN' and index['product_claims'] == []
    assert len(index['checks']) == len(record['checks_run']) == 7
    decoded = {}; observations = []
    for check in index['checks']:
        declared = next(x for x in record['checks_run'] if x['check_id'] == check['check_id'])
        assert all(declared[k] == check[k] for k in ['command', 'result', 'evidence_ref'])
        assert check['result'] == 'PASS' and check['exit_code'] == 0
        refs = [check['evidence_ref'], *check.get('ancillary_refs', [])]
        for path in refs:
            envelope = json.loads(blob(path))
            assert envelope['tested_commit'] == C and envelope['exit_code'] == 0
            assert envelope['command'] == check['command'] or (check['check_id'] == 'harness' and '--collect-only' in envelope['command'])
            raw = recover(path)
            assert hashlib.sha256(raw).hexdigest() == envelope['raw_sha256'] and len(raw) == envelope['raw_bytes']
            decoded[path] = raw
        observations.append({'check_id': check['check_id'], 'exit_code': 0, 'exact_R_recovered_refs': len(refs)})
    unit = next(x for x in index['checks'] if x['check_id'] == 'unit')
    unit_tree = ET.fromstring(decoded[unit['ancillary_refs'][0]])
    unit_cases = unit_tree.findall('.//testcase')
    assert len(unit_cases) == 247 and not unit_tree.findall('.//failure') and not unit_tree.findall('.//error') and not unit_tree.findall('.//skipped')
    assert b'247 passed' in decoded[unit['evidence_ref']]
    harness = next(x for x in index['checks'] if x['check_id'] == 'harness')
    def ancillary(suffix):
        return decoded[next(p for p in harness['ancillary_refs'] if p.endswith(suffix))]
    collection = json.loads(ancillary('harness-collection.json.json'))
    execution = json.loads(ancillary('harness-execution.json.json'))
    nodes = collection['collections']['serial']
    assert len(nodes) == len(set(nodes)) == 1492 and collection['exit_code'] == 0 and not collection['errors']
    assert all(worker_nodes == nodes for worker_nodes in execution['collections'].values())
    assert Counter(execution['started']) == Counter(nodes) and not execution['errors'] and execution['exit_code'] == 0
    assert Counter((r['nodeid'], r['phase']) for r in execution['reports']) == Counter((n, p) for n in nodes for p in ['setup', 'call', 'teardown'])
    assert all(r['outcome'] == 'passed' for r in execution['reports'])
    collection_stdout = ancillary('harness-collection.log.json').decode()
    assert all(n in collection_stdout for n in nodes)
    harness_tree = ET.fromstring(ancillary('harness-junit.xml.json'))
    harness_cases = harness_tree.findall('.//testcase')
    assert len(harness_cases) == 1492 and not harness_tree.findall('.//failure') and not harness_tree.findall('.//error') and not harness_tree.findall('.//skipped')
    assert Counter((case.attrib['classname'], case.attrib['name']) for case in harness_cases) == Counter(junit_identity(n) for n in nodes)
    manifest = json.loads(ancillary('harness-manifest.json.json'))
    assert manifest['tested_commit'] == C and not manifest['dirty_source'] and manifest['execution_complete']
    assert manifest['exit_code'] == manifest['pytest_exit_code'] == 0 and not manifest['errors']
    mapping = {'collection.json': 'harness-collection.json.json', 'collection.log': 'harness-collection.log.json', 'execution.json': 'harness-execution.json.json', 'junit.xml': 'harness-junit.xml.json', 'pytest.log': 'harness-pytest.log.json'}
    for entry in manifest['files']:
        raw = ancillary(mapping[entry['path']])
        assert len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['sha256']
    out = {'reviewed_head_sha': R, 'base_commit': B, 'tested_commit': C, 'verification': 'PASS', 'exact_files_changed': len(changed), 'tested_to_result_suffix': suffix, 'unchanged_frozen_and_state_authorities': authorities, 'actual_prerequisite_ancestors': actual_deps, 'recovered_checks': observations, 'unit_passed': len(unit_cases), 'harness_passed': len(harness_cases), 'harness_complete_node_and_phase_agreement': True, 'failed': 0, 'skipped': 0, 'runtime_implementation_checks': 'NOT_RUN', 'product_claims': []}
    path = ROOT / 'docs/exec-plans/reviews/HG-053/protocol/verification.json'
    path.write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
