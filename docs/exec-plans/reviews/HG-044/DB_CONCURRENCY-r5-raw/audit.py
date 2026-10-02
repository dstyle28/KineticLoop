"""Independent exact-revision DB closure review; no database lifecycle."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
import jsonschema
import yaml

ROOT = Path.cwd()
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/DB_CONCURRENCY-r5-raw'
BASE = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
REVIEWED = '027bc2368e36e28aa9956489cb57af297882d671'
TESTED = '7206b60aa4f930caf1bac62db0f397978ea0ec34'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, rev=REVIEWED):
    return git('show', rev + ':' + path)
def load(path, rev=REVIEWED):
    raw = blob(path, rev)
    return yaml.safe_load(raw) if path.endswith('.yaml') else json.loads(raw)
def digest(raw):
    return hashlib.sha256(raw).hexdigest()
def ancestor(a,b):
    return subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=ROOT).returncode == 0

spec = importlib.util.spec_from_file_location('review_validator', ROOT/'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert blob('tools/harness/validate_harness.py') == (ROOT/'tools/harness/validate_harness.py').read_bytes()
patch = git('diff','--binary',BASE,REVIEWED)
(OUT/'complete-diff.patch').write_bytes(patch)
changed = git('diff','--name-only',BASE,REVIEWED).decode().splitlines()
record = load('docs/exec-plans/governance/HG-044.yaml')
assert set(changed) == set(record['files_changed'])
assert all(v.matches(path,v.governance_allowed_patterns('HG-044')) for path in changed)
assert ancestor(BASE,TESTED) and ancestor(TESTED,REVIEWED)
assert v.governance_suffix_errors(ROOT,TESTED,REVIEWED,'HG-044','tested') == []
assert not any(path.startswith(('src/','migrations/','.github/')) for path in changed)
assert not any('milestones/M3.json' in p for p in changed)
jsonschema.Draft202012Validator(load('HARNESS_CHANGE.schema.json')).validate(record)

captures=[]
for check in record['checks_run']:
    obj=load(check['evidence_ref'])
    if check['check_id']=='scope':
        assert obj['tested_commit']==TESTED and obj['base_commit']==BASE
        assert all(obj['checks'].values())
        continue
    raw=obj['raw_utf8'].encode()
    assert obj['tested_commit']==TESTED and obj['base_commit']==BASE
    assert obj['result']=='PASS' and type(obj['exit_code']) is int and obj['exit_code']==0
    assert obj['command']==check['command'] and obj['check_id']==check['check_id']
    assert obj['raw_sha256']==digest(raw) and obj['raw_byte_count']==len(raw)
    captures.append({'check_id':check['check_id'],'file_sha256':digest(blob(check['evidence_ref'])),
                     'raw_sha256':digest(raw),'raw_bytes':len(raw),'raw_summary':obj['raw_utf8'][-350:]})
for check in load('docs/exec-plans/evidence/HG-044/capture-integrity-7206b60.json')['records']:
    obj=load(check['path'])
    assert check['sha256']==digest(blob(check['path']))
    assert check['raw_sha256']==obj['raw_sha256'] and check['raw_byte_count']==obj['raw_byte_count']

old=blob('tools/harness/validate_harness.py',BASE).decode(); new=blob('tools/harness/validate_harness.py').decode()
def functions(source):
    lines=source.splitlines(keepends=True)
    return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
before=functions(old); after=functions(new)
preserved=[n for n in before if n.startswith(('m2_','milestone_','integration_','review_evidence_','revision_regular_','suffix_'))]
assert all(before[n]==after[n] for n in preserved)
old_schema=load('MILESTONE_CLOSURE.schema.json',BASE); new_schema=load('MILESTONE_CLOSURE.schema.json')
assert old_schema['oneOf']==new_schema['oneOf'][:2]
assert all(new_schema['$defs'][k]==val for k,val in old_schema['$defs'].items())
assert blob('FROZEN_BASELINE.json',BASE)==blob('FROZEN_BASELINE.json')
frozen=load('FROZEN_BASELINE.json')
for entry in frozen['files']:
    assert blob(entry['path'],BASE)==blob(entry['path']) and digest(blob(entry['path']))==entry['sha256']

tasks={t['id']:t for t in load(v.BACKLOG)['tasks']}
records={}; missing=[]; pending=list(v.M3_TASK_IDS|{'KL-074'})
while pending:
    name=pending.pop()
    if name in records or name in missing: continue
    path=f'docs/exec-plans/integrations/{name}.json'
    if not v.revision_regular_file(ROOT,path,REVIEWED):
        missing.append(name); continue
    records[name]=load(path)
    pending.extend(tasks[name]['depends_on'])
edges=[]
for name, item in records.items():
    for key in ('result_commit','reviewed_head_sha','review_record_commit','merge_commit'):
        assert ancestor(item[key],REVIEWED)
    path=v.result_paths_at_revision(ROOT,name,item['reviewed_head_sha'])[0]
    result=load(path,item['reviewed_head_sha'])
    for dep in tasks[name]['depends_on']:
        assert dep in records
        for key in ('base_commit','tested_commit'):
            assert ancestor(records[dep]['merge_commit'],result[key])
            edges.append({'dependency':dep,'consumer':name,'consumer_revision_type':key,
                          'merge':records[dep]['merge_commit'],'revision':result[key]})

contracts=[]
for mapping in v.M3_EXIT_TASK_CHECKS.values():
    for name, ids in mapping.items():
        for cid in ids:
            check=next(c for c in tasks[name]['check_contracts'] if c['check_id']==cid)
            assert v.canonical_value_sha(check)==v.M3_CHECK_CONTRACT_DIGESTS[name+':'+cid]
            contracts.append({'task':name,'check_id':cid,'command':check['command'],'pass_oracle':check['pass_oracle']})
ledger=v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(),'Boundary layer ledger')
assert len(ledger)==31 and v.m3_boundary_layer_errors(ledger,load('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements'])==[]
assert sum(r['disposition']=='KL028_PLANNED_EXECUTABLE' for r in ledger)==19
for command in v.M3_REGRESSION_COMMANDS:
    if command.startswith('uv run pytest -q '):
        for selector in command.removeprefix('uv run pytest -q ').split():
            pieces=selector.split('::'); source=blob(pieces[0]).decode()
            if len(pieces)>1: assert 'def '+pieces[-1]+'(' in source

source_diff=subprocess.run(['git','diff','--check',BASE,REVIEWED,'--','.',':(exclude)docs/exec-plans/reviews/HG-044/**'],cwd=ROOT,capture_output=True)
(OUT/'source-diff.stdout').write_bytes(source_diff.stdout)
(OUT/'source-diff.stderr').write_bytes(source_diff.stderr)
assert source_diff.returncode==0
broad=subprocess.run(['git','diff','--check',BASE,REVIEWED],cwd=ROOT,capture_output=True)
(OUT/'broad-diff.stdout').write_bytes(broad.stdout)
(OUT/'broad-diff.stderr').write_bytes(broad.stderr)
for line in broad.stdout.decode().splitlines():
    if ': trailing whitespace.' in line:
        assert line.startswith('docs/exec-plans/reviews/HG-044/')
result={'status':'PASS','base':BASE,'tested':TESTED,'reviewed':REVIEWED,'diff_sha256':digest(patch),
        'changed_paths':changed,'captures':captures,'preserved_functions':preserved,
        'integrations':sorted(records),'missing_prospective_integrations':sorted(missing),
        'dependency_edges':edges,'contracts':contracts,'boundary_ledger':ledger,
        'broad_diff_exit':broad.returncode,'source_diff_exit':source_diff.returncode,
        'limitations':['No real M3 closure or DB lifecycle; validator evidence only.',
                       'KL028/KL029 source merged; missing integration records still prevent closure.']}
(OUT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':'PASS','changed_paths':len(changed),'selected_captures':len(captures),
                  'recursive_integrations':len(records),'dependency_checks':len(edges),
                  'missing':missing,'contract_checks':len(contracts),'broad_diff_exit':broad.returncode}))
