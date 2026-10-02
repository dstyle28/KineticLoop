import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
import yaml
import jsonschema
ROOT = Path('/Users/davetian/.codex/worktrees/8578/KineticLoop')
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/GENERAL-r3-raw/audit.json'
BASE = 'fa729ca4bcca0f2c2e7a2aa0601890d1356b8842'
HEAD = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
commands = []
def git(*args):
    p = subprocess.run(['git', *args], cwd=ROOT, capture_output=True)
    commands.append({'command': ['git', *args], 'exit_code': p.returncode, 'stdout_sha256': hashlib.sha256(p.stdout).hexdigest(), 'stderr': p.stderr.decode()})
    assert p.returncode == 0, (args, p.stderr.decode())
    return p.stdout
def blob(path, rev=HEAD):
    line = git('ls-tree', rev, '--', path).decode().strip()
    assert line.split()[0] in ('100644', '100755'), (path, line)
    return git('show', rev + ':' + path)
def load(path, rev=HEAD):
    raw = blob(path, rev)
    return yaml.safe_load(raw) if path.endswith('.yaml') else json.loads(raw)
def digest(raw): return hashlib.sha256(raw).hexdigest()
assert git('rev-parse', 'HEAD').decode().strip() == HEAD
assert git('merge-base', BASE, HEAD).decode().strip() == BASE
record = load('docs/exec-plans/governance/HG-044.yaml')
assert record['base_commit'] == BASE and record['change_status'] == 'PASS'
tested = record['tested_commit']
assert tested == '0af358014182c957eec07763aaaf9181d3e2d0c1'
changes = set(git('diff', '--name-only', BASE, HEAD).decode().splitlines())
assert changes == set(record['files_changed'])
assert not any(p.startswith(('src/', 'migrations/', '.github/')) for p in changes)
spec = importlib.util.spec_from_file_location('general_r3_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert (ROOT / 'tools/harness/validate_harness.py').read_bytes() == blob('tools/harness/validate_harness.py')
assert all(v.matches(p, v.governance_allowed_patterns('HG-044')) for p in changes)
assert v.governance_suffix_errors(ROOT, tested, HEAD, 'HG-044', 'tested') == []
index = load('CURRENT_DOCUMENT_INDEX.json')
index_entries = index['documents'] + index['machine_readable']
for item in index_entries:
    assert digest(blob(item['path'])) == item['sha256'], item['path']
manifest = load('HARNESS_DOCUMENT_MANIFEST.json')
for item in manifest['files']:
    raw = blob(item['path'])
    assert digest(raw) == item['sha256'] and len(raw) == item['bytes'], item['path']
captures = []
for path in git('ls-tree', '-r', '--name-only', HEAD, 'docs/exec-plans/evidence/HG-044').decode().splitlines():
    if not path.endswith('.json'): continue
    payload = load(path)
    if isinstance(payload, dict) and 'raw_utf8' in payload:
        raw = payload['raw_utf8'].encode()
        assert len(raw) == payload['raw_byte_count'] and digest(raw) == payload['raw_sha256'], path
        captures.append({'path': path, 'sha256': digest(blob(path)), 'exit_code': payload['exit_code'], 'tested_commit': payload['tested_commit']})
selected = []
for check in record['checks_run']:
    payload = load(check['evidence_ref'])
    assert payload['base_commit'] == BASE and payload['tested_commit'] == tested
    if check['check_id'] == 'scope':
        assert payload['status'] == check['result'] == 'PASS' and all(payload['checks'].values())
        selected.append({'path': check['evidence_ref'], 'status': payload['status'], 'checks': payload['checks']})
        continue
    assert payload['command'] == check['command'] and payload['check_id'] == check['check_id']
    assert payload['result'] == check['result'] == 'PASS'
    assert type(payload['exit_code']) is int and payload['exit_code'] == 0
    selected.append({'path': check['evidence_ref'], 'raw_utf8': payload['raw_utf8']})
for item in load('docs/exec-plans/evidence/HG-044/capture-integrity-0af3580.json')['records']:
    payload = load(item['path'])
    assert digest(blob(item['path'])) == item['sha256']
    assert payload['raw_sha256'] == item['raw_sha256'] and payload['raw_byte_count'] == item['raw_byte_count']
forbidden = ['FROZEN_BASELINE.json', 'docs/exec-plans/milestones/M3.json', 'CURRENT_REQUIREMENT_SET.json', v.BACKLOG, v.TRACEABILITY]
assert not changes.intersection(forbidden)
frozen = load('FROZEN_BASELINE.json')
for item in frozen['files']:
    assert blob(item['path']) == blob(item['path'], BASE)
    assert digest(blob(item['path'])) == item['sha256']
old_schema, schema = load(v.MILESTONE_CLOSURE_SCHEMA, BASE), load(v.MILESTONE_CLOSURE_SCHEMA)
assert schema['oneOf'][:2] == old_schema['oneOf']
assert all(schema['$defs'][k] == val for k, val in old_schema['$defs'].items())
before_source, after_source = blob('tools/harness/validate_harness.py', BASE).decode(), blob('tools/harness/validate_harness.py').decode()
def functions(source):
    return {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
old, new = functions(before_source), functions(after_source)
changed_functions = sorted(k for k in old if old[k] != new[k])
assert changed_functions == ['governance_allowed_patterns', 'validate'], changed_functions
backlog = load(v.BACKLOG)
tasks = {t['id']: t for t in backlog['tasks']}
assert v.M3_TASK_IDS == {f'KL-{n:03}' for n in range(19, 30)} | {f'KL-{n:03}' for n in range(75, 80)}
checks = []
required_commands = set()
for mapping in v.M3_EXIT_TASK_CHECKS.values():
    for name, check_ids in mapping.items():
        for cid in check_ids:
            found = [c for c in tasks[name]['check_contracts'] if c['check_id'] == cid]
            assert len(found) == 1 and v.canonical_value_sha(found[0]) == v.M3_CHECK_CONTRACT_DIGESTS[name + ':' + cid]
            required_commands.add(found[0]['command'])
            checks.append(name + ':' + cid)
assert required_commands <= set(v.M3_REGRESSION_COMMANDS), required_commands - set(v.M3_REGRESSION_COMMANDS)
ledger = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
assert len(ledger) == 31 and sum(r['disposition'] == 'KL028_PLANNED_EXECUTABLE' for r in ledger) == 19
assert not v.m3_boundary_layer_errors(ledger, load('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements'])
assert blob(v.PROJECT_PLAN).decode().split('## M3 exit-evidence mapping — HG044', 1)[0] == blob(v.PROJECT_PLAN, BASE).decode() + '\n'
assert not v.m3_closure_plan_errors(blob(v.PROJECT_PLAN).decode())
schemas = [jsonschema.Draft202012Validator(load(p)) for p in (v.MILESTONE_CLOSURE_SCHEMA, v.INTEGRATION_SCHEMA, 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
assert not v.milestone_closure_errors(ROOT, load('docs/exec-plans/milestones/M1.json'), *schemas, backlog, tasks)
assert not v.m2_milestone_closure_errors(ROOT, load('docs/exec-plans/milestones/M2.json'), *schemas, backlog, tasks)
records, absent = {}, []
pending = list(v.M3_TASK_IDS | {'KL-074'})
while pending:
    name = pending.pop()
    if name in records or name in absent: continue
    path = f'docs/exec-plans/integrations/{name}.json'
    if not git('ls-tree', HEAD, '--', path):
        absent.append(name)
        continue
    integrated = load(path)
    assert not v.integration_record_errors(ROOT, Path(path), integrated, *schemas[1:], tasks), name
    for key in ('result_commit', 'reviewed_head_sha', 'review_record_commit', 'merge_commit'):
        assert v.is_ancestor(ROOT, integrated[key], HEAD), (name, key)
    records[name] = integrated
    pending.extend(tasks[name]['depends_on'])
assert set(absent) == {'KL-028', 'KL-029'}, absent
assert not v.m3_dependency_order_errors(ROOT, records, tasks)
OUT.write_text(json.dumps({'reviewed_head_sha': HEAD, 'protected_base_sha': BASE, 'tested_commit': tested, 'status': 'PASS', 'changed_paths': sorted(changes), 'index_count': len(index_entries), 'manifest_count': len(manifest['files']), 'retained_raw_captures': captures, 'selected_checks': selected, 'unchanged_existing_functions': len(old) - len(changed_functions), 'changed_existing_functions': changed_functions, 'mapped_check_count': len(checks), 'regression_command_count': len(v.M3_REGRESSION_COMMANDS), 'boundary_rows': len(ledger), 'boundary_executable_rows': 19, 'boundary_deferred_rows': 12, 'validated_recursive_integrations': sorted(records), 'absent_prospective_integrations': absent, 'commands': commands}, indent=2) + '\n')
print(json.dumps({'status': 'PASS', 'changed_paths': len(changes), 'captures': len(captures), 'selected_checks': len(selected), 'recursive_integrations': len(records), 'absent': absent, 'mapped_checks': len(checks)}))
