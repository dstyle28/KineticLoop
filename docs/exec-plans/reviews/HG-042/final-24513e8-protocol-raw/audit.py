"""Independent SHA-bound HG042 protocol and raw-evidence audit. No DB lifecycle."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from collections import Counter
from pathlib import Path

import jsonschema
import yaml

ROOT = Path.cwd()
BASE = '93b38f20a3f3d71206515fb0f4d852f5b0b6d344'
HEAD = '24513e86d90799edb951fa2bdf52ba433c59318a'
TESTED = 'e4134f963450db1522fd6c3339e4cb036fcf5ffe'
OUT = ROOT / 'docs/exec-plans/reviews/HG-042/final-24513e8-protocol-raw'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path, revision=HEAD):
    entry = git('ls-tree', revision, '--', path).decode().split()
    assert len(entry) >= 4 and entry[0] in {'100644', '100755'} and entry[1] == 'blob', path
    return git('show', revision + ':' + path)

def doc(path, revision=HEAD):
    return json.loads(blob(path, revision))

assert git('rev-parse', 'HEAD').decode().strip() == HEAD
for earlier, later in ((BASE, TESTED), (TESTED, HEAD)):
    assert subprocess.run(['git', 'merge-base', '--is-ancestor', earlier, later]).returncode == 0
record = yaml.safe_load(blob('docs/exec-plans/governance/HG-042.yaml'))
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
assert record['frozen_impact'] == 'NONE' and record['change_status'] == 'PASS'
changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
assert sorted(changed) == sorted(record['files_changed'])
assert not any(p.startswith(('src/', 'migrations/', '.github/', 'docs/exec-plans/completed/')) for p in changed)
for path in ('05_KineticLoop_Protocol_v1.2_FROZEN.md', '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
             'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Acceptance_Spec_v1.2.2.json',
             'MILESTONE_CLOSURE.schema.json', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
             'docs/harness/THREAD_REVIEW_CONTRACT.md'):
    assert blob(path, BASE) == blob(path), path
commits = git('rev-list', '--reverse', TESTED + '..' + HEAD).decode().splitlines()
for commit in commits:
    assert len(git('rev-list', '--parents', '-n', '1', commit).decode().split()) == 2
    for path in git('diff-tree', '--no-commit-id', '--name-only', '-r', commit).decode().splitlines():
        assert path == 'docs/exec-plans/governance/HG-042.yaml' or path.startswith('docs/exec-plans/evidence/HG-042/'), path
        if path.startswith('docs/exec-plans/evidence/HG-042/'):
            assert not git('ls-tree', TESTED, '--', path), path

spec = importlib.util.spec_from_file_location('review_protocol_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
before = {t['id']: t for t in doc(v.BACKLOG, BASE)['tasks']}
tasks = {t['id']: t for t in doc(v.BACKLOG)['tasks']}
assert [n for n in tasks if tasks[n] != before[n]] == ['KL-028', 'KL-029']
for name in ('KL-028', 'KL-029'):
    task = tasks[name]
    packet = blob('docs/exec-plans/active/' + name + '.md').decode()
    assert task['status'] == 'NOT_STARTED' and task['evidence_refs'] == []
    assert task['requirements_covered'] == before[name]['requirements_covered']
    assert set(before[name]['review_requirements']) <= set(task['review_requirements'])
    assert v.m3_boundary_shadow_definition_errors(task) == []
    assert v.packet_errors(task, packet) == []
    assert set(v.packet_json_section(packet, 'Prospective check status').values()) == {'NOT_RUN'}
    assert len(task['write_paths']) == 3
    for prefix in ('docs/exec-plans/completed/' + name + '_RESULT.',
                   'docs/exec-plans/reviews/' + name + '/', 'docs/exec-plans/integrations/' + name + '.'):
        assert not any(p.startswith(prefix) for p in git('ls-tree', '-r', '--name-only', HEAD).decode().splitlines())
assert not set(tasks['KL-028']['write_paths']) & set(tasks['KL-029']['write_paths'])
assert not set(tasks['KL-028']['resource_keys']) & set(tasks['KL-029']['resource_keys'])
ledger = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
assert v.m3_boundary_layer_errors(ledger, doc('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements']) == []
capacity = Counter(r['layer'] for r in ledger if r['disposition'] == 'KL028_PLANNED_EXECUTABLE')
assert capacity == {'PU': 6, 'DC': 13}
assert len(ledger) == 31 and sum(r['disposition'] != 'KL028_PLANNED_EXECUTABLE' for r in ledger) == 12
assert set(r['status'] for r in ledger) == {'NOT_RUN'}

raw_checks = []
assert len(record['checks_run']) == 9
for check in record['checks_run']:
    evidence = doc(check['evidence_ref'])
    raw = evidence['raw_utf8'].encode()
    assert evidence['check_id'] == check['check_id'] and evidence['command'] == check['command']
    assert evidence['tested_commit'] == TESTED and evidence['base_commit'] == BASE
    assert evidence['exit_code'] == 0 and evidence['result'] == check['result'] == 'PASS'
    assert hashlib.sha256(raw).hexdigest() == evidence['raw_sha256'] and len(raw) == evidence['raw_byte_count']
    raw_checks.append({'check_id': check['check_id'], 'raw_sha256': evidence['raw_sha256'],
                       'raw_byte_count': len(raw), 'terminal_output': raw.decode().splitlines()[-1:]})
old = blob('tools/harness/validate_harness.py', BASE).decode()
new = blob('tools/harness/validate_harness.py').decode()
functions = lambda source: {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
for name in ('integration_record_errors', 'review_evidence_exists', 'revision_regular_file', 'suffix_errors'):
    assert functions(old)[name] == functions(new)[name]
schemas = [jsonschema.Draft202012Validator(doc(p)) for p in ('INTEGRATION_RECORD.schema.json', 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
integrations = []
for name in ('KL-027', 'KL-075', 'KL-076', 'KL-077', 'KL-079'):
    path = 'docs/exec-plans/integrations/' + name + '.json'
    integration = doc(path)
    errors = v.integration_record_errors(ROOT, Path(path), integration, *schemas, tasks)
    assert not errors, (name, errors)
    parents = git('rev-list', '--parents', '-n', '1', integration['merge_commit']).decode().split()[1:]
    assert len(parents) == 2 and parents[1] == integration['review_record_commit']
    assert subprocess.run(['git', 'merge-base', '--is-ancestor', integration['merge_commit'], BASE]).returncode == 0
    result_paths = v.result_paths_at_revision(ROOT, name, integration['result_commit'])
    assert len(result_paths) == 1
    assert yaml.safe_load(blob(result_paths[0], integration['result_commit']))['integration_status'] == 'UNMERGED'
    assert blob(result_paths[0], BASE) == blob(result_paths[0])
    integrations.append({'task': name, 'errors': errors, 'normal_merge': integration['merge_commit'], 'historical_result_status': 'UNMERGED'})
report = {'reviewed_head_sha': HEAD, 'protected_base': BASE, 'tested_commit': TESTED,
          'frozen_and_production_unchanged': True, 'changed_task_definitions': ['KL-028', 'KL-029'],
          'layer_count': len(ledger), 'prospective_executable_layers': dict(capacity), 'deferred_layers': 12,
          'requirement_statuses': ['NOT_RUN'], 'raw_final_checks': raw_checks,
          'hg043_provenance_functions_unchanged': True, 'actual_normal_integrations': integrations,
          'tested_to_reviewed_bookkeeping_commits': commits}
(OUT / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
