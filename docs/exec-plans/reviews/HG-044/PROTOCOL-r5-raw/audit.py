"""Independent exact-revision protocol audit; no application or database mutation."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
import jsonschema

ROOT = Path.cwd()
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/PROTOCOL-r5-raw'
BASE = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
REVIEW = '027bc2368e36e28aa9956489cb57af297882d671'
TESTED = '7206b60aa4f930caf1bac62db0f397978ea0ec34'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, rev=REVIEW):
    return git('show', rev + ':' + path)
def parsed(path, rev=REVIEW):
    return json.loads(blob(path, rev))
def ancestor(a, b):
    return subprocess.run(['git', 'merge-base', '--is-ancestor', a, b], cwd=ROOT).returncode == 0
def sha(data):
    return hashlib.sha256(data).hexdigest()

OUT.mkdir(parents=True, exist_ok=True)
diff = git('diff', '--binary', BASE, REVIEW)
(OUT / 'complete-diff.patch').write_bytes(diff)
paths = git('diff', '--name-only', BASE, REVIEW).decode().splitlines()
allowed = {'06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md', 'CURRENT_DOCUMENT_INDEX.json',
           'HARNESS_DOCUMENT_MANIFEST.json', 'MILESTONE_CLOSURE.schema.json',
           'docs/harness/M3_CLOSURE_CONTRACT.md', 'tests/harness/test_m3_milestone_closure.py',
           'tools/harness/validate_harness.py', 'docs/exec-plans/governance/HG-044.yaml'}
assert all(p in allowed or p.startswith('docs/exec-plans/evidence/HG-044/')
           or p.startswith('docs/exec-plans/reviews/HG-044/') for p in paths)
spec = importlib.util.spec_from_file_location('independent_m3', ROOT/'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert blob('tools/harness/validate_harness.py') == (ROOT/'tools/harness/validate_harness.py').read_bytes()
backlog = parsed(v.BACKLOG)
tasks = {t['id']: t for t in backlog['tasks']}
assert {t['id'] for t in tasks.values() if t['milestone']=='M3' and t['status']!='SUPERSEDED'} == v.M3_TASK_IDS
assert len(v.M3_TASK_IDS)==16 and tasks['KL-074']['milestone']=='M1'
assert 'KL-045' not in tasks['KL-029']['depends_on']
dependency_paths=[]
def walk(name, stack=()):
    assert name not in stack, ('cycle', stack, name)
    for dep in tasks[name]['depends_on']:
        if name in v.M3_TASK_IDS:
            assert tasks[dep]['milestone']!='M4', (name, dep)
        dependency_paths.append([name, dep])
        walk(dep, stack+(name,))
for name in v.M3_TASK_IDS:
    walk(name)
missing=[]; records={}; pending=list(v.M3_TASK_IDS|{'KL-074'})
while pending:
    name=pending.pop()
    if name in records or name in missing:
        continue
    path=f'docs/exec-plans/integrations/{name}.json'
    if not v.revision_regular_file(ROOT,path,REVIEW):
        missing.append(name)
        continue
    record=parsed(path); records[name]=record
    assert record['integration_status']=='MERGED'
    assert all(ancestor(record[key],REVIEW) for key in ('result_commit','reviewed_head_sha','review_record_commit','merge_commit'))
    pending.extend(tasks[name]['depends_on'])
assert set(missing)=={'KL-028','KL-029'},missing
integration_schemas=[jsonschema.Draft202012Validator(parsed(path)) for path in ('INTEGRATION_RECORD.schema.json','THREAD_RESULT.schema.json','THREAD_REVIEW.schema.json')]
integration_validation={}
for name,record in records.items():
    issues=v.integration_record_errors(ROOT,Path(f'docs/exec-plans/integrations/{name}.json'),record,*integration_schemas,tasks)
    integration_validation[name]=issues
    assert not issues,(name,issues)
edges=[]
for name,record in records.items():
    result_path=v.result_paths_at_revision(ROOT,name,record['reviewed_head_sha'])
    assert len(result_path)==1
    result=v.load_artifact_at_revision(ROOT,result_path[0],record['reviewed_head_sha'])
    for dep in tasks[name]['depends_on']:
        for key in ('base_commit','tested_commit'):
            assert ancestor(records[dep]['merge_commit'],result[key]),(name,dep,key)
            edges.append({'consumer':name,'dependency':dep,'before':key,'merge':records[dep]['merge_commit'],'consumer_sha':result[key]})
mapped=[]
for exit_id,mapping in v.M3_EXIT_TASK_CHECKS.items():
    for name,checks in mapping.items():
        contracts={c['check_id']:c for c in tasks[name]['check_contracts']}
        for check in checks:
            contract=contracts[check]
            assert v.canonical_value_sha(contract)==v.M3_CHECK_CONTRACT_DIGESTS[name+':'+check]
            assert contract['command'] in v.M3_REGRESSION_COMMANDS or contract['command'].startswith('uv run pytest -q ')
            for selector in contract['command'].removeprefix('uv run pytest -q ').split():
                assert any(selector in command.split() for command in v.M3_REGRESSION_COMMANDS)
            mapped.append({'exit':exit_id,'task':name,'contract':contract})
ledger=v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(),'Boundary layer ledger')
assert len(ledger)==31
assert sum(r['disposition']=='KL028_PLANNED_EXECUTABLE' for r in ledger)==19
assert all(r['status']=='NOT_RUN' for r in ledger)
assert not v.m3_boundary_layer_errors(ledger,parsed('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements'])
frozen=parsed('FROZEN_BASELINE.json')
assert blob('FROZEN_BASELINE.json')==blob('FROZEN_BASELINE.json',BASE)
for item in frozen['files']:
    assert sha(blob(item['path']))==item['sha256']
def functions(text):
    return {n.name:ast.get_source_segment(text,n) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
before=functions(blob('tools/harness/validate_harness.py',BASE).decode())
after=functions(blob('tools/harness/validate_harness.py').decode())
changed_functions=[n for n in before if before[n]!=after[n]]
assert changed_functions==['governance_allowed_patterns','validate'],changed_functions
schema_before=parsed('MILESTONE_CLOSURE.schema.json',BASE); schema_after=parsed('MILESTONE_CLOSURE.schema.json')
assert schema_before['oneOf']==schema_after['oneOf'][:2]
assert all(schema_before['$defs'][k]==schema_after['$defs'][k] for k in schema_before['$defs'])
assert not v.m3_closure_plan_errors(blob(v.PROJECT_PLAN).decode())
assert blob(v.PROJECT_PLAN).decode().split('## M3 exit-evidence mapping — HG044')[0]==blob(v.PROJECT_PLAN,BASE).decode()+'\n'
captures=[]
scope=parsed('docs/exec-plans/evidence/HG-044/scope-7206b60.json')
assert scope['tested_commit']==TESTED and scope['base_commit']==BASE and scope['status']=='PASS' and all(scope['checks'].values())
for name in ('focused','harness','unit','lint','typecheck','validation','source_diff'):
    path=f'docs/exec-plans/evidence/HG-044/{name}-7206b60.json'; data=parsed(path)
    raw=data['raw_utf8'].encode()
    assert data['tested_commit']==TESTED and data['base_commit']==BASE and type(data['exit_code']) is int and data['exit_code']==0 and data['result']=='PASS'
    assert sha(raw)==data['raw_sha256'] and len(raw)==data['raw_byte_count']
    captures.append({'path':path,'blob_sha256':sha(blob(path)),'raw_sha256':sha(raw),'raw_byte_count':len(raw),'summary':raw.decode()[-400:]})
assert ancestor(BASE,TESTED) and ancestor(TESTED,REVIEW)
assert not v.governance_suffix_errors(ROOT,TESTED,REVIEW,'HG-044','tested')
record=v.load_artifact_at_revision(ROOT,'docs/exec-plans/governance/HG-044.yaml',REVIEW)
assert record['base_commit']==BASE and record['tested_commit']==TESTED and record['change_status']=='PASS'
assert set(record['files_changed'])==set(paths)
assert all(c['result']=='PASS' for c in record['checks_run'])
for entry in parsed('CURRENT_DOCUMENT_INDEX.json')['documents']+parsed('CURRENT_DOCUMENT_INDEX.json')['machine_readable']:
    assert sha(blob(entry['path']))==entry['sha256'],entry['path']
for entry in parsed('HARNESS_DOCUMENT_MANIFEST.json')['files']:
    assert sha(blob(entry['path']))==entry['sha256'] and len(blob(entry['path']))==entry['bytes'],entry['path']
suffix=git('diff','--name-only',TESTED,REVIEW).decode().splitlines()
assert all(p=='docs/exec-plans/governance/HG-044.yaml' or p.startswith('docs/exec-plans/evidence/HG-044/') or p.startswith('docs/exec-plans/reviews/HG-044/') for p in suffix),suffix
check=subprocess.run(['git','diff','--check',BASE,REVIEW,'--','.',':(exclude)docs/exec-plans/reviews/HG-044/**'],cwd=ROOT,capture_output=True)
(OUT/'source-diff.log').write_bytes(check.stdout+check.stderr)
assert check.returncode==0
report={'reviewed_head_sha':REVIEW,'base':BASE,'tested':TESTED,'complete_diff_sha256':sha(diff),'paths':paths,'changed_existing_functions':changed_functions,'missing_prospective_integrations':missing,'integration_validation':integration_validation,'verified_dependency_edges':edges,'dependency_graph_edges':dependency_paths,'mapped_task_checks':mapped,'boundary_ledger':ledger,'selected_captures':captures,'tested_suffix':suffix,'source_diff_exit':check.returncode,'status':'PASS'}
(OUT/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('AUDIT_PASS',len(paths),'paths',len(edges),'ancestry edges',len(mapped),'mapped checks')
