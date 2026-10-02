"""Independent exact-SHA security/data-boundary audit; no lifecycle operations."""
import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
REVIEWED = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
BASE = 'fa729ca4bcca0f2c2e7a2aa0601890d1356b8842'
TESTED = '0af358014182c957eec07763aaaf9181d3e2d0c1'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def sha(data):
    return hashlib.sha256(data).hexdigest()
def blob(path, revision=REVIEWED):
    entry = git('ls-tree', '-z', revision, '--', path).split(b'\0')[0]
    metadata, name = entry.split(b'\t')
    mode, kind, oid = metadata.split()
    assert name.decode() == path and mode in (b'100644', b'100755') and kind == b'blob'
    assert git('cat-file', '-t', oid.decode()).strip() == b'blob'
    return git('show', revision + ':' + path)
spec = importlib.util.spec_from_file_location('security_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
def load(path, revision=REVIEWED):
    return v.load_artifact_text(blob(path, revision).decode(), Path(path).suffix)

assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
assert (ROOT / 'tools/harness/validate_harness.py').read_bytes() == blob('tools/harness/validate_harness.py')
assert (ROOT / 'tests/harness/test_m3_milestone_closure.py').read_bytes() == blob('tests/harness/test_m3_milestone_closure.py')
git('merge-base', '--is-ancestor', BASE, TESTED)
git('merge-base', '--is-ancestor', TESTED, REVIEWED)
assert not v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-044', 'tested')
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
assert all(v.matches(p, v.governance_allowed_patterns('HG-044')) for p in changed)
assert not git('ls-tree', REVIEWED, '--', 'docs/exec-plans/milestones/M3.json')
frozen = load('FROZEN_BASELINE.json')
assert blob('FROZEN_BASELINE.json') == blob('FROZEN_BASELINE.json', BASE)
for item in frozen['files']:
    assert sha(blob(item['path'])) == item['sha256']
    assert blob(item['path']) == blob(item['path'], BASE)
index = load('CURRENT_DOCUMENT_INDEX.json')
for entry in index['documents'] + index['machine_readable']:
    assert sha(blob(entry['path'])) == entry['sha256'], entry['path']
for path in ['docs/exec-plans/milestones/M1.json', 'docs/exec-plans/milestones/M2.json']:
    assert blob(path) == blob(path, BASE)
old = ast.parse(blob('tools/harness/validate_harness.py', BASE))
new = ast.parse(blob('tools/harness/validate_harness.py'))
old_funcs = {n.name: ast.dump(n) for n in old.body if isinstance(n, ast.FunctionDef)}
new_funcs = {n.name: ast.dump(n) for n in new.body if isinstance(n, ast.FunctionDef)}
preserved = ['integration_record_errors', 'review_evidence_exists', 'revision_git_entry',
             'revision_regular_file', 'suffix_errors', 'governance_suffix_errors',
             'milestone_closure_errors', 'm2_milestone_closure_errors', 'm2_execution_evidence_errors']
assert all(old_funcs[n] == new_funcs[n] for n in preserved)
schema = load('MILESTONE_CLOSURE.schema.json')
prior = load('MILESTONE_CLOSURE.schema.json', BASE)
assert schema['oneOf'][:2] == prior['oneOf']
assert all(schema['$defs'][k] == val for k, val in prior['$defs'].items())
result = load('docs/exec-plans/governance/HG-044.yaml')
assert result['base_commit'] == BASE and result['tested_commit'] == TESTED and result['change_status'] == 'PASS'
assert set(result['files_changed']) == set(changed)
captures = []
for check in result['checks_run']:
    raw = blob(check['evidence_ref'])
    payload = load(check['evidence_ref'])
    assert payload['tested_commit'] == TESTED and payload['base_commit'] == BASE
    if check['check_id'] == 'scope':
        assert payload['status'] == check['result'] == 'PASS'
        assert all(payload['checks'].values()) and set(payload['changed']) == set(git('diff', '--name-only', BASE, TESTED).decode().splitlines())
        captures.append({'path': check['evidence_ref'], 'sha256': sha(raw), 'check_id': 'scope', 'scope_payload': payload})
        continue
    assert payload['result'] == check['result'] == 'PASS'
    assert payload['command'] == check['command'] and payload['check_id'] == check['check_id']
    assert type(payload['exit_code']) is int and payload['exit_code'] == 0
    content = payload['raw_utf8'].encode()
    assert sha(content) == payload['raw_sha256'] and len(content) == payload['raw_byte_count']
    captures.append({'path': check['evidence_ref'], 'sha256': sha(raw), 'check_id': check['check_id'],
                     'raw_sha256': sha(content), 'raw_byte_count': len(content), 'raw_utf8': payload['raw_utf8']})
counts = {x['check_id']: v.m3_pytest_count(x['raw_utf8']) for x in captures if x['check_id'] in ('focused', 'harness', 'unit')}
assert counts == {'focused': 83, 'harness': 873, 'unit': 234}
integrity = load('docs/exec-plans/evidence/HG-044/capture-integrity-0af3580.json')
assert integrity['tested_commit'] == TESTED and integrity['status'] == 'PASS'
for row in integrity['records']:
    capture = next(x for x in captures if x['path'] == row['path'])
    for key in ('sha256', 'raw_sha256', 'raw_byte_count'):
        assert capture[key] == row[key]
backlog = load(v.BACKLOG)
tasks = {t['id']: t for t in backlog['tasks']}
assert {t['id'] for t in tasks.values() if t['milestone'] == 'M3' and t['status'] != 'SUPERSEDED'} == v.M3_TASK_IDS
assert len(v.M3_TASK_IDS) == 16 and tasks['KL-074']['milestone'] == 'M1'
contracts = []
for exit_id, mapping in v.M3_EXIT_TASK_CHECKS.items():
    for task_id, checks in mapping.items():
        for check_id in checks:
            contract = next(c for c in tasks[task_id]['check_contracts'] if c['check_id'] == check_id)
            assert v.canonical_value_sha(contract) == v.M3_CHECK_CONTRACT_DIGESTS[task_id + ':' + check_id]
            contracts.append({'exit': exit_id, 'task': task_id, 'check': check_id,
                              'command': contract['command'], 'oracle_sha256': v.canonical_value_sha(contract['pass_oracle'])})
assert len(contracts) == 52
ledger = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
assert len(ledger) == 31
assert sum(r['disposition'] == 'KL028_PLANNED_EXECUTABLE' for r in ledger) == 19
assert sum(r['status'] == 'NOT_RUN' and r['disposition'] != 'KL028_PLANNED_EXECUTABLE' for r in ledger) == 12
audit = {'reviewed_head_sha': REVIEWED, 'base_commit': BASE, 'tested_commit': TESTED,
         'status': 'PASS', 'changed_paths': changed, 'preserved_functions': preserved,
         'captures': captures, 'counts': counts, 'contracts': contracts,
         'boundary_ledger': ledger, 'no_actual_m3': True, 'test_execution_records': []}
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT / 'src'))
commands = [
    ['/private/tmp/hg044-venv/bin/python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
     '--basetemp=/private/tmp/hg044-security-r3-tests', '--junitxml=' + str(OUT / 'targeted.xml'),
     'tests/harness/test_m3_milestone_closure.py::test_each_multiselect_suite_requires_collected_and_executed_cases',
     'tests/harness/test_m3_milestone_closure.py::test_integrated_regression_fails_closed',
     'tests/harness/test_m3_milestone_closure.py::test_m3_symlink_is_rejected_before_target_parsing',
     'tests/harness/test_m3_milestone_closure.py::test_m3_reader_parses_checked_git_blob_not_second_ambient_read',
     'tests/harness/test_m3_milestone_closure.py::test_actual_closure_record_requires_unchanged_regular_head_blob',
     'tests/harness/test_m3_milestone_closure.py::test_schema_rejects_frozen_production_shadow_product_overclaims'],
    ['/private/tmp/hg044-venv/bin/python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
     '--basetemp=/private/tmp/hg044-security-r3-provenance', '--junitxml=' + str(OUT / 'provenance.xml'),
     'tests/harness/test_review_evidence_provenance.py'],
    ['git', 'diff', '--check', BASE, REVIEWED],
]
for i, command in enumerate(commands):
    started = time.time()
    run = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    name = ['targeted', 'provenance', 'diff'][i]
    (OUT / (name + '.log')).write_bytes(run.stdout)
    record = {'command': command, 'reviewed_head_sha': REVIEWED, 'exit_code': run.returncode,
              'raw_ref': str((OUT / (name + '.log')).relative_to(ROOT)), 'raw_sha256': sha(run.stdout),
              'elapsed_seconds': round(time.time() - started, 2)}
    audit['test_execution_records'].append(record)
    (OUT / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    assert type(run.returncode) is int and run.returncode == 0, run.stdout.decode()
    print(name, run.stdout.decode(), flush=True)
print('SECURITY_R3_AUDIT_PASS', flush=True)
