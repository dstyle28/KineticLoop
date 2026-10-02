"""Independent SHA-bound security/data review; read-only Git and pure checks."""
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import jsonschema
import yaml

ROOT = Path.cwd()
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/SECURITY_DATA_BOUNDARY-r5-raw'
BASE = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
REVIEWED = '027bc2368e36e28aa9956489cb57af297882d671'
TESTED = '7206b60aa4f930caf1bac62db0f397978ea0ec34'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path, revision=REVIEWED):
    return git('show', revision + ':' + path)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def regular(path, revision=REVIEWED):
    entries = git('ls-tree', '-z', revision, '--', path).split(b'\0')
    for entry in filter(None, entries):
        metadata, actual = entry.split(b'\t', 1)
        mode, kind, oid = metadata.split()
        if actual == path.encode():
            return mode in (b'100644', b'100755') and kind == b'blob' and git('cat-file', '-t', oid.decode()).strip() == b'blob'
    return False

spec = importlib.util.spec_from_file_location('review_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert digest((ROOT / 'tools/harness/validate_harness.py').read_bytes()) == digest(blob('tools/harness/validate_harness.py'))
report = {'reviewed_head_sha': REVIEWED, 'base_commit': BASE, 'tested_commit': TESTED}
patch = git('diff', '--binary', BASE, REVIEWED)
(OUT / 'complete-diff.patch').write_bytes(patch)
report['complete_diff'] = {'sha256': digest(patch), 'bytes': len(patch)}
paths = git('diff', '--name-only', BASE, REVIEWED).decode().splitlines()
record = yaml.safe_load(blob('docs/exec-plans/governance/HG-044.yaml'))
assert set(paths) == set(record['files_changed'])
assert all(v.matches(path, v.governance_allowed_patterns('HG-044')) for path in paths)
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
assert not v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-044', 'tested')
assert v.is_ancestor(ROOT, BASE, TESTED)
assert not regular('docs/exec-plans/milestones/M3.json')
report['changed_paths'] = [{'path': p, 'sha256': digest(blob(p)), 'regular': regular(p)} for p in paths]
assert all(p['regular'] for p in report['changed_paths'])
report['selected_captures'] = []
integrity = json.loads(blob('docs/exec-plans/evidence/HG-044/capture-integrity-7206b60.json'))
assert integrity['tested_commit'] == TESTED and integrity['status'] == 'PASS'
for check in record['checks_run']:
    data = blob(check['evidence_ref'])
    item = json.loads(data)
    assert regular(check['evidence_ref'])
    if check['check_id'] == 'scope':
        assert item['tested_commit'] == TESTED and item['base_commit'] == BASE and item['status'] == 'PASS'
        assert all(item['checks'].values())
        report['selected_captures'].append({'check_id': 'scope', 'path': check['evidence_ref'], 'sha256': digest(data)})
        continue
    assert item['check_id'] == check['check_id'] and item['command'] == check['command']
    assert item['tested_commit'] == TESTED and item['base_commit'] == BASE
    assert type(item['exit_code']) is int and item['exit_code'] == 0
    assert item['result'] == check['result'] == 'PASS'
    raw = item['raw_utf8'].encode()
    assert digest(raw) == item['raw_sha256'] and len(raw) == item['raw_byte_count']
    matches = [i for i in integrity['records'] if i['check_id'] == check['check_id']]
    if check['check_id'] != 'scope':
        assert len(matches) == 1 and matches[0]['sha256'] == digest(data)
        assert matches[0]['raw_sha256'] == digest(raw) and matches[0]['raw_byte_count'] == len(raw)
    if check['check_id'] in ('focused', 'harness', 'unit'):
        assert re.search(r'\b[1-9][0-9]* passed\b', item['raw_utf8'])
        assert not re.search(r'\b[1-9][0-9]* (failed|skipped|errors?|deselected|xfailed|xpassed)\b', item['raw_utf8'], re.I)
    report['selected_captures'].append({'check_id': check['check_id'], 'path': check['evidence_ref'], 'sha256': digest(data), 'raw_sha256': digest(raw), 'raw_bytes': len(raw)})
report['indexed_hashes'] = []
index = json.loads(blob('CURRENT_DOCUMENT_INDEX.json'))
for group in ('documents', 'machine_readable'):
    for item in index[group]:
        assert regular(item['path']) and digest(blob(item['path'])) == item['sha256']
        report['indexed_hashes'].append(item['path'])
manifest = json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json'))
for item in manifest['files']:
    data = blob(item['path'])
    assert regular(item['path']) and digest(data) == item['sha256'] and len(data) == item['bytes']
report['manifest_verified_files'] = len(manifest['files'])
frozen = json.loads(blob('FROZEN_BASELINE.json'))
assert blob('FROZEN_BASELINE.json') == blob('FROZEN_BASELINE.json', BASE)
for item in frozen['files']:
    assert blob(item['path']) == blob(item['path'], BASE)
    assert digest(blob(item['path'])) == item['sha256']
before_schema = json.loads(blob('MILESTONE_CLOSURE.schema.json', BASE))
after_schema = json.loads(blob('MILESTONE_CLOSURE.schema.json'))
assert after_schema['oneOf'][:2] == before_schema['oneOf']
assert all(after_schema['$defs'][key] == val for key, val in before_schema['$defs'].items())
before_ast = ast.parse(blob('tools/harness/validate_harness.py', BASE))
after_ast = ast.parse(blob('tools/harness/validate_harness.py'))
before_functions = {n.name: ast.get_source_segment(blob('tools/harness/validate_harness.py', BASE).decode(), n) for n in before_ast.body if isinstance(n, ast.FunctionDef)}
after_functions = {n.name: ast.get_source_segment(blob('tools/harness/validate_harness.py').decode(), n) for n in after_ast.body if isinstance(n, ast.FunctionDef)}
report['changed_existing_functions'] = [name for name, val in before_functions.items() if after_functions.get(name) != val]
assert set(report['changed_existing_functions']) == {'governance_allowed_patterns', 'validate'}
plan = blob(v.PROJECT_PLAN).decode()
assert plan.split('## M3 exit-evidence mapping — HG044', 1)[0] == blob(v.PROJECT_PLAN, BASE).decode() + '\n'
assert not v.m3_closure_plan_errors(plan)
assert not v.m3_frozen_authority_errors(ROOT, REVIEWED)
backlog = json.loads(blob(v.BACKLOG))
errors, tasks = v.task_definition_errors(ROOT, backlog, REVIEWED)
assert not errors
integration_schema, result_schema, review_schema = [jsonschema.Draft202012Validator(json.loads(blob(path))) for path in (v.INTEGRATION_SCHEMA, 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
pending = list(v.M3_TASK_IDS | {'KL-074'})
records = {}
while pending:
    task_id = pending.pop()
    if task_id in records:
        continue
    path = f'docs/exec-plans/integrations/{task_id}.json'
    if not regular(path):
        assert task_id in ('KL-028', 'KL-029')
        records[task_id] = None
        continue
    integration = json.loads(blob(path))
    assert not v.integration_record_errors(ROOT, Path(path), integration, integration_schema, result_schema, review_schema, tasks)
    records[task_id] = integration
    for key in ('result_commit', 'reviewed_head_sha', 'review_record_commit', 'merge_commit'):
        assert v.is_ancestor(ROOT, integration[key], REVIEWED)
    for revision in (integration['result_commit'], integration['reviewed_head_sha']):
        for rp in v.result_paths_at_revision(ROOT, task_id, revision):
            assert regular(rp, revision)
    for kind in tasks[task_id]['review_requirements']:
        rp = f'docs/exec-plans/reviews/{task_id}/{kind}.json'
        assert regular(rp, integration['review_record_commit'])
    result = v.load_artifact_at_revision(ROOT, v.result_paths_at_revision(ROOT, task_id, integration['reviewed_head_sha'])[0], integration['reviewed_head_sha'])
    for check in result['commands_run']:
        assert regular(check['evidence_ref'], integration['reviewed_head_sha'])
    pending.extend(tasks[task_id]['depends_on'])
for task_id, integration in records.items():
    if integration is None:
        continue
    result = v.load_artifact_at_revision(ROOT, v.result_paths_at_revision(ROOT, task_id, integration['reviewed_head_sha'])[0], integration['reviewed_head_sha'])
    for dep in tasks[task_id]['depends_on']:
        assert records[dep] is not None
        assert all(v.is_ancestor(ROOT, records[dep]['merge_commit'], result[key]) for key in ('base_commit', 'tested_commit'))
report['integration_closure'] = {'valid_existing': sorted(k for k, val in records.items() if val), 'absent_prospective': sorted(k for k, val in records.items() if val is None)}
for name, checks in [(n, checks) for mapping in v.M3_EXIT_TASK_CHECKS.values() for n, checks in mapping.items()]:
    for check_id in checks:
        contract = next(c for c in tasks[name]['check_contracts'] if c['check_id'] == check_id)
        assert v.canonical_value_sha(contract) == v.M3_CHECK_CONTRACT_DIGESTS[name + ':' + check_id]
report['pinned_check_contracts_verified'] = len(v.M3_CHECK_CONTRACT_DIGESTS)
rows = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
report['boundary_layers'] = {'total': len(rows), 'planned_executable': sum(r['disposition'] == 'KL028_PLANNED_EXECUTABLE' for r in rows), 'deferred': sum(r['disposition'] != 'KL028_PLANNED_EXECUTABLE' for r in rows)}
assert report['boundary_layers'] == {'total': 31, 'planned_executable': 19, 'deferred': 12}
source_diff = subprocess.run(['git', 'diff', '--check', BASE, REVIEWED, '--', '.', ':(exclude)docs/exec-plans/reviews/HG-044/**'], capture_output=True)
(OUT / 'source-diff.stdout').write_bytes(source_diff.stdout)
(OUT / 'source-diff.stderr').write_bytes(source_diff.stderr)
assert source_diff.returncode == 0
report['sensitive_material_scan'] = []
for path in paths:
    data = blob(path).decode(errors='replace')
    for label, pattern in [('private_key', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'), ('aws_access_key', r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'), ('openai_key', r'\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b')]:
        if re.search(pattern, data):
            report['sensitive_material_scan'].append({'path': path, 'kind': label})
assert not report['sensitive_material_scan']
report['status'] = 'PASS'
(OUT / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': 'PASS', 'changed_files': len(paths), 'selected_captures': len(record['checks_run']), 'integrations': report['integration_closure'], 'boundary_layers': report['boundary_layers']}))
