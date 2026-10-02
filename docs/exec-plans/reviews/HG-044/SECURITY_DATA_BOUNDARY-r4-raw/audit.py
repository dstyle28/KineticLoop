"""Independent exact-revision HG044 security evidence audit; no DB lifecycle."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent
HEAD = '4bc0b0122245d54649e3f3d03a9acce7d4c6df2a'
BASE = 'fa729ca4bcca0f2c2e7a2aa0601890d1356b8842'
TESTED = '0ce071ace6e8290ae08b6926a5b87709b2c70b08'
spec = importlib.util.spec_from_file_location('security_validator_r4', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, revision=HEAD):
    assert v.revision_regular_file(ROOT, path, revision), (path, revision)
    return git('show', revision + ':' + path)
def obj(path, revision=HEAD):
    return v.load_artifact_text(blob(path, revision).decode(), Path(path).suffix)
def digest(data):
    return hashlib.sha256(data).hexdigest()
assert git('rev-parse', 'HEAD').decode().strip() == HEAD
assert not git('diff', '--name-only', HEAD, '--', 'tools/harness/validate_harness.py', 'tests/harness/test_m3_milestone_closure.py')
changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
result = obj('docs/exec-plans/governance/HG-044.yaml')
assert result['base_commit'] == BASE and result['tested_commit'] == TESTED
assert len(changed) == 202 and set(changed) == set(result['files_changed'])
assert all(v.matches(path, v.governance_allowed_patterns('HG-044')) for path in changed)
for path in changed:
    blob(path)
assert not v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-044', 'tested')
suffix = []
for commit in git('rev-list', '--reverse', TESTED + '..' + HEAD).decode().splitlines():
    parent = git('rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
    assert len(parent) == 1
    paths = git('diff', '--name-only', parent[0], commit).decode().splitlines()
    suffix.append(dict(commit=commit, parent=parent[0], paths=paths))
    for path in paths:
        if path.startswith('docs/exec-plans/evidence/HG-044/'):
            assert subprocess.run(['git', 'cat-file', '-e', parent[0] + ':' + path], cwd=ROOT, capture_output=True).returncode != 0
index = obj('CURRENT_DOCUMENT_INDEX.json')
indexed = []
for item in index['documents'] + index['machine_readable']:
    actual = digest(blob(item['path']))
    assert actual == item['sha256'], item['path']
    indexed.append(dict(path=item['path'], sha256=actual))
assert not v.m3_frozen_authority_errors(ROOT, HEAD)
frozen = obj('FROZEN_BASELINE.json')
assert blob('FROZEN_BASELINE.json') == blob('FROZEN_BASELINE.json', BASE)
assert all(blob(entry['path']) == blob(entry['path'], BASE) for entry in frozen['files'])
captured = []
for check in result['checks_run']:
    capture = obj(check['evidence_ref'])
    assert capture.get('status', capture.get('result')) == 'PASS'
    assert capture['tested_commit'] == TESTED and capture['base_commit'] == BASE
    if 'raw_utf8' in capture:
        raw = capture['raw_utf8'].encode()
        assert capture['command'] == check['command']
        assert capture['check_id'] == check['check_id']
        assert type(capture['exit_code']) is int and capture['exit_code'] == 0
        assert digest(raw) == capture['raw_sha256'] and len(raw) == capture['raw_byte_count']
        if check['check_id'] in ('focused', 'harness', 'unit'):
            expected = {'focused':88, 'harness':878, 'unit':234}[check['check_id']]
            assert v.m3_pytest_count(raw.decode()) == expected
        captured.append(dict(check_id=check['check_id'], command=check['command'], sha256=digest(blob(check['evidence_ref'])), raw_sha256=digest(raw), exit_code=capture['exit_code']))
integrity = obj('docs/exec-plans/evidence/HG-044/capture-integrity-0ce071a.json')
assert integrity['status'] == 'PASS' and integrity['tested_commit'] == TESTED
for record in integrity['records']:
    assert digest(blob(record['path'])) == record['sha256']
    cap = obj(record['path'])
    assert cap['raw_sha256'] == record['raw_sha256'] and cap['raw_byte_count'] == record['raw_byte_count']
broad = obj('docs/exec-plans/evidence/HG-044/diff-0ce071a.json')
assert broad['result'] == 'FAIL' and broad['exit_code'] != 0
assert 'diff' not in {c['check_id'] for c in result['checks_run']}
patch = blob('docs/exec-plans/reviews/HG-044/PROTOCOL-r3-raw/complete-diff.patch')
assert any(line == b' ' for line in patch.splitlines())
selected_diff = subprocess.run(['git','diff','--check', BASE, HEAD, '--','.', ':(exclude)docs/exec-plans/reviews/HG-044/**'], cwd=ROOT, capture_output=True)
assert selected_diff.returncode == 0, selected_diff.stdout
source = blob('tools/harness/validate_harness.py').decode()
old_source = blob('tools/harness/validate_harness.py', BASE).decode()
def functions(text):
    return {n.name: ast.get_source_segment(text,n) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
now, old = functions(source), functions(old_source)
preserved = {}
for name in ('milestone_closure_errors','m2_milestone_closure_errors','m2_execution_evidence_errors','integration_record_errors','review_evidence_exists','semantic_result_errors'):
    assert now[name] == old[name], name
    preserved[name] = digest(now[name].encode())
schema = obj('MILESTONE_CLOSURE.schema.json')
old_schema = obj('MILESTONE_CLOSURE.schema.json', BASE)
assert schema['oneOf'][:2] == old_schema['oneOf']
for key,value in old_schema['$defs'].items():
    assert schema['$defs'][key] == value
for path in ('docs/exec-plans/milestones/M1.json','docs/exec-plans/milestones/M2.json'):
    assert blob(path) == blob(path, BASE)
assert not v.revision_regular_file(ROOT,'docs/exec-plans/milestones/M3.json',HEAD)
backlog = obj(v.BACKLOG)
tasks = {t['id']:t for t in backlog['tasks']}
assert {t['id'] for t in tasks.values() if t['milestone']=='M3' and t['status']!='SUPERSEDED'} == v.M3_TASK_IDS
assert len(v.M3_TASK_IDS) == 16 and tasks['KL-074']['milestone']=='M1'
contracts = []
for mapping in v.M3_EXIT_TASK_CHECKS.values():
    for name, checks in mapping.items():
        for check in checks:
            found = [c for c in tasks[name]['check_contracts'] if c['check_id']==check]
            assert len(found)==1 and v.canonical_value_sha(found[0]) == v.M3_CHECK_CONTRACT_DIGESTS[name+':'+check]
            contracts.append(dict(task_identity=tasks[name]['task_identity'],check_id=check,command=found[0]['command'],digest=v.canonical_value_sha(found[0])))
assert len(contracts)==52
ledger = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(),'Boundary layer ledger')
requirements = obj('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements']
assert not v.m3_boundary_layer_errors(ledger,requirements)
assert len(ledger)==31 and sum(r['disposition']=='KL028_PLANNED_EXECUTABLE' for r in ledger)==19
assert len([r for r in ledger if r['disposition']!='KL028_PLANNED_EXECUTABLE'])==12
assert all(r['status']=='NOT_RUN' for r in ledger)
schemas = [jsonschema.Draft202012Validator(obj(path)) for path in (v.MILESTONE_CLOSURE_SCHEMA,v.INTEGRATION_SCHEMA,'THREAD_RESULT.schema.json','THREAD_REVIEW.schema.json')]
assert v.milestone_closure_errors(ROOT,obj('docs/exec-plans/milestones/M1.json'),*schemas,backlog,tasks)==[]
assert v.m2_milestone_closure_errors(ROOT,obj('docs/exec-plans/milestones/M2.json'),*schemas,backlog,tasks)==[]
pending = list(v.M3_TASK_IDS|{'KL-074'})
records = {}
missing = []
integrations = []
while pending:
    name = pending.pop()
    if name in records or name in missing: continue
    pending.extend(tasks[name]['depends_on'])
    path = f'docs/exec-plans/integrations/{name}.json'
    if not v.revision_regular_file(ROOT,path,HEAD):
        missing.append(name); continue
    record = obj(path)
    records[name] = record
    errors = v.integration_record_errors(ROOT,Path(path),record,*schemas[1:],tasks)
    assert not errors, (name,errors)
    assert all(v.is_ancestor(ROOT,record[k],HEAD) for k in ('result_commit','reviewed_head_sha','review_record_commit','merge_commit'))
    result_path = v.result_paths_at_revision(ROOT,name,record['reviewed_head_sha'])
    assert len(result_path)==1
    task_result = obj(result_path[0],record['reviewed_head_sha'])
    dependencies = []
    for dep in tasks[name]['depends_on']:
        dep_record = obj(f'docs/exec-plans/integrations/{dep}.json')
        assert all(v.is_ancestor(ROOT,dep_record['merge_commit'],task_result[k]) for k in ('base_commit','tested_commit'))
        dependencies.append(dict(identity=tasks[dep]['task_identity'],merge_commit=dep_record['merge_commit']))
    integrations.append(dict(identity=tasks[name]['task_identity'],result_path=result_path[0],result_sha256=digest(blob(result_path[0],record['reviewed_head_sha'])),record=record,dependencies=dependencies))
assert set(missing)=={'KL-028','KL-029'} and len(records)==32
output = dict(reviewed_head_sha=HEAD,base_commit=BASE,tested_commit=TESTED,status='PASS',changed_count=len(changed),changed_paths=changed,tested_suffix=suffix,indexed_hashes=indexed,captures=captured,preserved_functions=preserved,task_checks=contracts,boundary_ledger=ledger,integrations=integrations,missing_integrations=sorted(missing),broad_diff_retained_unselected=True,source_diff_exit_code=selected_diff.returncode)
(OUT/'audit.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(dict(status='PASS',reviewed_head_sha=HEAD,changed_paths=len(changed),integrations=len(records),missing=sorted(missing),named_checks=len(contracts),selected_counts=[88,878,234])))
