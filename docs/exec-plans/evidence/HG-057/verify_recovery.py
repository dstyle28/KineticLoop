"""Revision-bound definition-only recovery assertions; never run source helpers."""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = '3ec7f7a38d974256a928c3687f63e4d90019e42b'
PINS = {
    'KL036_local': '1fee7a4ef9ecb484da24522962a6df4d4c2bd9b9',
    'HG056_final': '8bfb977f67f9e1fa8af8fb43fe98ad5bebd89aea',
    'HG056_tested': '1cb64a1baef54fc7801e4084a18db962c3528a70',
    'HG056_result': '0b089d7d3b0212a4e5458dc7891cbb4e831cd6f6',
}
BACKLOG = 'KineticLoop_Harness_Backlog_v0.2.json'
TRACE = 'KineticLoop_Harness_Traceability_v0.3.json'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def blob(revision, path):
    return git('show', revision + ':' + path)


def tasks(revision):
    return {task['id']: task for task in json.loads(blob(revision, BACKLOG))['tasks']}


def exists(revision, path):
    return bool(git('ls-tree', revision, '--', path).strip())


def functions(raw):
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(raw).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--tested', required=True)
    args = parser.parse_args()
    assert args.base == BASE
    tested = git('rev-parse', args.tested).decode().strip()
    git('merge-base', '--is-ancestor', BASE, tested)
    before, after = tasks(BASE), tasks(tested)
    assert before['KL-036']['status'] == 'NOT_STARTED'
    for revision, owner in ((BASE, 'KL-036'), (tested, 'KL-036'), (tested, 'KL-081')):
        for path in (f'docs/exec-plans/completed/{owner}_RESULT.yaml',
                     f'docs/exec-plans/completed/{owner}_RESULT.json',
                     f'docs/exec-plans/integrations/{owner}.json',
                     f'docs/exec-plans/reviews/{owner}'):
            assert not exists(revision, path), (revision, path)
    for owner in ('HG-058',):
        assert not exists(tested, f'docs/exec-plans/governance/{owner}.yaml')
        assert not exists(tested, f'docs/exec-plans/reviews/{owner}')
        assert not exists(tested, f'docs/exec-plans/evidence/{owner}')
    assert after['KL-036']['status'] == 'SUPERSEDED'
    assert after['KL-036']['superseded_by'] == ['KL-081']
    assert after['KL-036']['depends_on'] == ['KL-081']
    retirement_fields = {'status', 'title', 'depends_on', 'deliverables',
                         'definition_of_done', 'superseded_by', 'disposition_reason'}
    assert {field for field in set(before['KL-036']) | set(after['KL-036'])
            if before['KL-036'].get(field) != after['KL-036'].get(field)} <= retirement_fields
    retired_packet = blob(tested, 'docs/exec-plans/active/KL-036.md').decode()
    assert retired_packet.count('\nScheduling barrier: MUST NOT be scheduled.\n') == 1
    assert '\nReason: ' + after['KL-036']['disposition_reason'] + '\n' in retired_packet
    assert after['KL-036']['requirements_covered'] == before['KL-036']['requirements_covered'] == []
    successor = json.loads(json.dumps(before['KL-036']).replace('KL-036', 'KL-081'))
    entries = after['KL-081']['entry_conditions']
    assert entries[:len(successor['entry_conditions'])] == successor['entry_conditions']
    assert len(entries) == len(successor['entry_conditions']) + 4
    successor['entry_conditions'] = entries
    assert successor == after['KL-081']
    assert len(successor['write_paths']) == 6 and len(successor['check_contracts']) == 16
    assert set(successor['review_requirements']) == {
        'GENERAL', 'PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'}
    changed_ids = {id for id in set(before) | set(after) if before.get(id) != after.get(id)}
    assert changed_ids == {'KL-036', 'KL-081', 'KL-038', 'KL-039', 'KL-064'}
    for id in ('KL-038', 'KL-039', 'KL-064'):
        expected = dict(before[id])
        expected['depends_on'] = ['KL-081' if d == 'KL-036' else d for d in expected['depends_on']]
        assert after[id] == expected
        path = f'docs/exec-plans/active/{id}.md'
        old_packet = blob(BASE, path).decode()
        start = old_packet.index('## Dependencies\n')
        end = old_packet.index('\n### Conditional dependencies', start)
        expected_packet = old_packet[:start] + old_packet[start:end].replace('KL-036', 'KL-081') + old_packet[end:]
        assert blob(tested, path).decode() == expected_packet
    old_trace = json.loads(blob(BASE, TRACE))
    new_trace = json.loads(blob(tested, TRACE))
    assert {k: val for k, val in old_trace.items() if k != 'tasks'} == {k: val for k, val in new_trace.items() if k != 'tasks'}
    traces = {task['id']: task for task in json.loads(blob(tested, TRACE))['tasks']}
    for id in changed_ids:
        assert traces[id] == {field: after[id].get(field) for field in traces[id]}
    for id in ('KL-024', 'KL-026', 'KL-025', 'KL-075', 'KL-019'):
        record = json.loads(blob(BASE, f'docs/exec-plans/integrations/{id}.json'))
        assert record['integration_status'] == 'MERGED'
        git('merge-base', '--is-ancestor', record['merge_commit'], BASE)
    packet = blob(tested, 'docs/exec-plans/active/HG-058.md').decode()
    for pin in PINS.values():
        git('cat-file', '-e', pin + '^{commit}')
        assert pin in packet and pin in blob(tested, 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md').decode()
    # Old objects remain present and are not imported into the clean ancestry.
    for pin in (PINS['KL036_local'], PINS['HG056_final']):
        assert subprocess.run(['git', 'merge-base', '--is-ancestor', pin, tested], cwd=ROOT).returncode == 1
    import yaml
    kl_result = yaml.safe_load(blob(PINS['KL036_local'], 'docs/exec-plans/completed/KL-036_RESULT.yaml'))
    assert kl_result['task_status'] == 'BLOCKED' and kl_result['task_checks_status'] == 'NOT_RUN'
    for owner, pin in (('KL-036', PINS['KL036_local']), ('HG-056', PINS['HG056_final'])):
        for path in git('ls-tree', '-r', '--name-only', pin, '--', f'docs/exec-plans/reviews/{owner}').decode().splitlines():
            if path.count('/') == 4 and path.endswith('.json'):
                assert json.loads(blob(pin, path))['status'] == 'CHANGES_REQUIRED'
    old_result = blob(PINS['HG056_result'], 'docs/exec-plans/governance/HG-056.yaml')
    assert b'change_status: BLOCKED' in old_result
    original = blob('f93364d90aaae9b0b62706fd4e4fe395a8cd8ec5',
                    'docs/exec-plans/reviews/KL-036/SECURITY_DATA_BOUNDARY/audit.py')
    assert len(original) == 8063
    assert hashlib.sha256(original).hexdigest() == 'a602ee684cdd7b4d8169388d2a2fe821fc6bc5beadf0d69a593c2ed260ffe382'
    for phrase in ('NOT_STARTED', 'REVIEW_SOURCE_INSPECTION', 'absence', '256 KiB',
                   'FAIL/BLOCKED', 'GENERAL', 'SECURITY_DATA_BOUNDARY', 'controller_files',
                   'fullDB', 'verify_compatibility.py', 'verify_scope.py', 'git diff --check',
                   'no decoding', 'No schema expansion', 'concrete packet issue'):
        assert phrase in packet, phrase
    frozen = json.loads(blob(BASE, 'FROZEN_BASELINE.json'))
    unchanged = [entry['path'] for entry in frozen['files']] + [
        'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json',
        'tools/harness/compact_evidence.py', 'docs/harness/EVIDENCE_STORAGE_POLICY.md',
        'docs/harness/THREAD_REVIEW_CONTRACT.md', 'THREAD_REVIEW.schema.json',
        'tools/harness/local_gate.py', 'tools/harness/gate_validate.py']
    for path in unchanged:
        assert blob(BASE, path) == blob(tested, path), path
    old_functions = functions(blob(BASE, 'tools/harness/validate_harness.py'))
    new_functions = functions(blob(tested, 'tools/harness/validate_harness.py'))
    assert {name for name in old_functions if old_functions[name] != new_functions.get(name)} == {
        'packet_errors', 'governance_allowed_patterns', 'validate'}
    # Import only the committed governance validator, never an original helper.
    import importlib.util
    spec = importlib.util.spec_from_file_location('recovery_validator', ROOT / 'tools/harness/validate_harness.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not module.clean_recovery_projection_errors(before, after)
    assert hashlib.sha256(packet.encode()).hexdigest() == module.HG058_PACKET_SHA256
    paths = git('diff', '--name-only', BASE, tested).decode().splitlines()
    assert all(module.matches(path, module.HG057_ALLOWED_PATTERNS) for path in paths)
    for entry in json.loads(blob(tested, 'CURRENT_DOCUMENT_INDEX.json'))['documents'] + json.loads(blob(tested, 'CURRENT_DOCUMENT_INDEX.json'))['machine_readable']:
        assert hashlib.sha256(blob(tested, entry['path'])).hexdigest() == entry['sha256']
    for entry in json.loads(blob(tested, 'HARNESS_DOCUMENT_MANIFEST.json'))['files']:
        raw = blob(tested, entry['path'])
        assert len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['sha256']
    print(json.dumps({'status': 'PASS', 'base': BASE, 'tested': tested,
                      'changed_task_ids': sorted(changed_ids), 'source_pins': PINS,
                      'functional_paths': 6, 'functional_checks': 16,
                      'requirements': 'unchanged; no PASS', 'runtime_storage': 'unchanged'}))


if __name__ == '__main__':
    main()
