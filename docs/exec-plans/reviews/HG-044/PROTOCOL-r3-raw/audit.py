"""Independent exact-revision protocol audit. Writes only its own review evidence."""
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent
BASE = 'fa729ca4bcca0f2c2e7a2aa0601890d1356b8842'
REVIEWED = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
TESTED = '0af358014182c957eec07763aaaf9181d3e2d0c1'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path, revision=REVIEWED):
    mode = git('ls-tree', revision, '--', path).decode().split()[0]
    assert mode in ('100644', '100755'), (path, mode)
    return git('show', revision + ':' + path)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def load(path, revision=REVIEWED):
    return json.loads(blob(path, revision))

source = blob('tools/harness/validate_harness.py').decode()
spec = importlib.util.spec_from_loader('independent_m3_validator', loader=None)
v = importlib.util.module_from_spec(spec)
v.__file__ = str(ROOT / 'tools/harness/validate_harness.py')
exec(compile(source, 'reviewed_validator.py', 'exec'), v.__dict__)
assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
assert subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, REVIEWED], cwd=ROOT).returncode == 0
changed = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
assert all(v.matches(p, v.governance_allowed_patterns('HG-044')) for p in changed)
diff = git('diff', '--no-ext-diff', BASE, REVIEWED)
(OUT / 'complete-diff.patch').write_bytes(diff)

old_source = blob('tools/harness/validate_harness.py', BASE).decode()
def functions(text):
    return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
old_functions, new_functions = functions(old_source), functions(source)
changed_functions = [n for n in old_functions if old_functions[n] != new_functions[n]]
assert set(changed_functions) == {'governance_allowed_patterns', 'validate'}
old_schema = load('MILESTONE_CLOSURE.schema.json', BASE)
schema = load('MILESTONE_CLOSURE.schema.json')
assert schema['oneOf'][:2] == old_schema['oneOf']
assert all(schema['$defs'][k] == val for k, val in old_schema['$defs'].items())
assert blob(v.PROJECT_PLAN).decode().split('## M3 exit-evidence mapping — HG044')[0] == blob(v.PROJECT_PLAN, BASE).decode() + '\n'
assert not v.m3_closure_plan_errors(blob(v.PROJECT_PLAN).decode())

index = load('CURRENT_DOCUMENT_INDEX.json')
index_checks = []
for group in ('documents', 'machine_readable'):
    for entry in index[group]:
        actual = sha(blob(entry['path']))
        assert actual == entry['sha256'], entry['path']
        index_checks.append({'path': entry['path'], 'sha256': actual})
frozen = load('FROZEN_BASELINE.json')
assert frozen == load('FROZEN_BASELINE.json', BASE)
for item in frozen['files']:
    assert sha(blob(item['path'])) == item['sha256']
    assert blob(item['path']) == blob(item['path'], BASE)
assert not git('ls-tree', REVIEWED, '--', 'docs/exec-plans/milestones/M3.json')

backlog = load(v.BACKLOG)
tasks = {task['id']: task for task in backlog['tasks']}
expected_ids = {f'KL-{i:03d}' for i in range(19, 30)} | {f'KL-{i:03d}' for i in range(75, 80)}
assert v.M3_TASK_IDS == expected_ids
assert {n for n,t in tasks.items() if t['milestone'] == 'M3' and t['status'] != 'SUPERSEDED'} == expected_ids
assert tasks['KL-074']['milestone'] == 'M1'
assert 'KL-078' in tasks['KL-076']['depends_on']
assert 'KL-079' in tasks['KL-077']['depends_on']
mapping = []
for exit_id, entries in v.M3_EXIT_TASK_CHECKS.items():
    for task_id, ids in entries.items():
        assert len(ids) == len(set(ids))
        contracts = {c['check_id']: c for c in tasks[task_id]['check_contracts']}
        for check_id in ids:
            contract = contracts[check_id]
            digest = v.canonical_value_sha(contract)
            assert digest == v.M3_CHECK_CONTRACT_DIGESTS[task_id + ':' + check_id]
            assert contract['command'] in v.M3_REGRESSION_COMMANDS
            mapping.append({'exit_id': exit_id, 'task_id': task_id, 'check_id': check_id,
                            'contract_sha256': digest, 'command': contract['command'],
                            'oracle': contract['pass_oracle']})
rows = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
assert len(rows) == 31
deferred = [r for r in rows if r['disposition'] != 'KL028_PLANNED_EXECUTABLE']
assert len(deferred) == 12 and all(r['status'] == 'NOT_RUN' for r in deferred)
assert sum(r['layer'] == 'E2E' for r in deferred) == 8
assert {(r['requirement_id'],r['layer']) for r in deferred if r['layer'] != 'E2E'} == {('B04','DC'), ('B11','PU'), ('B12','PU'), ('B14','WF')}

capture = load('docs/exec-plans/evidence/HG-044/capture-integrity-0af3580.json')
captures = []
for entry in capture['records']:
    data = blob(entry['path'])
    payload = json.loads(data)
    raw = payload['raw_utf8'].encode()
    assert sha(data) == entry['sha256']
    assert payload['tested_commit'] == TESTED and payload['base_commit'] == BASE
    assert type(payload['exit_code']) is int and payload['exit_code'] == 0
    assert sha(raw) == entry['raw_sha256'] == payload['raw_sha256']
    assert len(raw) == entry['raw_byte_count'] == payload['raw_byte_count']
    assert payload['result'] == 'PASS'
    captures.append({'check_id': payload['check_id'], 'command': payload['command'],
                     'exit_code': payload['exit_code'], 'raw_sha256': sha(raw), 'raw_utf8': payload['raw_utf8']})
for check_id, count in [('focused',83),('harness',873),('unit',234)]:
    assert re.search(r'\b' + str(count) + r' passed\b', next(c['raw_utf8'] for c in captures if c['check_id'] == check_id))
suffix = []
for commit in git('rev-list', '--reverse', TESTED + '..' + REVIEWED).decode().splitlines():
    parents = git('show', '-s', '--format=%P', commit).decode().split()
    paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', commit).decode().splitlines()
    assert len(parents) == 1
    assert all(p == 'docs/exec-plans/governance/HG-044.yaml'
               or p.startswith('docs/exec-plans/evidence/HG-044/') for p in paths)
    suffix.append({'commit': commit, 'paths': paths})
report = {'reviewed_head_sha': REVIEWED, 'base_commit': BASE, 'tested_commit': TESTED,
          'status': 'PASS', 'exit_code': 0, 'complete_diff_sha256': sha(diff),
          'changed_paths': changed, 'changed_legacy_functions': changed_functions,
          'index_hash_checks': index_checks, 'M3_task_ids': sorted(expected_ids),
          'named_check_contracts': mapping, 'regression_commands': v.M3_REGRESSION_COMMANDS,
          'boundary_ledger_count': len(rows), 'deferred_boundaries': deferred,
          'interleaving_ledger': 'nine DC PASS plus I04 WF NOT_RUN; exact constructor checked in diff',
          'selected_raw_captures': captures, 'legal_tested_suffix': suffix,
          'runtime_frozen_CI_and_actual_closure_unchanged': True}
(OUT / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print('PROTOCOL_R3_AUDIT_PASS: exact mapping, ledgers, raw hashes, frozen/runtime scope and tested suffix')
