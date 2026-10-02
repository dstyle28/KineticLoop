"""Independent committed-tree GENERAL review audit; no implementation writes."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import jsonschema
import yaml

ROOT=Path.cwd();BASE='9268fc8dd8c071c02dc5c698274dbf6fcd112776';HEAD='080f25cf99eebc81701483bb801c5f2860dbd77f';TESTED='4302c0649c9255ac60be87d90853ee0620e9f019'
OUT=ROOT/'docs/exec-plans/reviews/HG-044/GENERAL-r2-raw/audit.json'
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(path,rev=HEAD):
 entry=git('ls-tree',rev,'--',path).decode().strip();assert entry.split()[0] in ('100644','100755'),(path,entry)
 return git('show',rev+':'+path)
def obj(path,rev=HEAD):return json.loads(blob(path,rev))
def digest(b):return hashlib.sha256(b).hexdigest()
def function_bytes(source):
 lines=source.splitlines(keepends=True)
 return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
spec=importlib.util.spec_from_file_location('general_r2_validator',ROOT/'tools/harness/validate_harness.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
assert git('rev-parse','HEAD').decode().strip()==HEAD
report={'base':BASE,'reviewed_head':HEAD,'tested_commit':TESTED}
changed=git('diff','--name-only',BASE,HEAD).decode().splitlines();report['diff_paths']=changed
assert all(v.matches(p,v.governance_allowed_patterns('HG-044')) for p in changed)
record=yaml.safe_load(blob('docs/exec-plans/governance/HG-044.yaml'));jsonschema.validate(record,obj('HARNESS_CHANGE.schema.json'))
assert sorted(changed)==record['files_changed'] and record['tested_commit']==TESTED and record['base_commit']==BASE
assert not v.governance_suffix_errors(ROOT,TESTED,HEAD,'HG-044','tested')
report['tested_suffix_paths']=git('diff','--name-only',TESTED,HEAD).decode().splitlines()
assert all(p=='docs/exec-plans/governance/HG-044.yaml' or p.startswith('docs/exec-plans/evidence/HG-044/') for p in report['tested_suffix_paths'])
assert all(git('diff','--diff-filter=A','--name-only',TESTED,HEAD).decode().splitlines().count(p)==1 for p in report['tested_suffix_paths'] if p!='docs/exec-plans/governance/HG-044.yaml')
old=function_bytes(blob('tools/harness/validate_harness.py',BASE).decode());new=function_bytes(blob('tools/harness/validate_harness.py').decode())
report['existing_function_changes']=[n for n in old if old[n]!=new[n]]
assert set(report['existing_function_changes'])=={'governance_allowed_patterns','validate'}
report['preserved_function_hashes']={n:digest(new[n].encode()) for n in ('milestone_closure_errors','m2_milestone_closure_errors','m2_execution_evidence_errors','integration_record_errors','review_evidence_exists','semantic_result_errors')}
oldschema=obj('MILESTONE_CLOSURE.schema.json',BASE);newschema=obj('MILESTONE_CLOSURE.schema.json');assert oldschema['oneOf']==newschema['oneOf'][:2]
assert all(newschema['$defs'][k]==val for k,val in oldschema['$defs'].items())
assert not git('ls-tree',HEAD,'--','docs/exec-plans/milestones/M3.json')
assert blob(v.PROJECT_PLAN).decode().split('## M3 exit-evidence mapping — HG044')[0]==blob(v.PROJECT_PLAN,BASE).decode()+'\n'
assert not v.m3_closure_plan_errors(blob(v.PROJECT_PLAN).decode())
for protected in ('FROZEN_BASELINE.json',v.BACKLOG,v.TRACEABILITY,'CURRENT_REQUIREMENT_SET.json','.github/workflows/ci.yml'):
 assert blob(protected)==blob(protected,BASE)
frozen=obj('FROZEN_BASELINE.json');assert all(digest(blob(e['path']))==e['sha256'] for e in frozen['files'])
index=obj('CURRENT_DOCUMENT_INDEX.json');rows=index['documents']+index['machine_readable']
assert all(digest(blob(e['path']))==e['sha256'] for e in rows)
manifest=obj('HARNESS_DOCUMENT_MANIFEST.json');assert all(digest(blob(e['path']))==e['sha256'] and ('bytes' not in e or len(blob(e['path']))==e['bytes']) for e in manifest['files'])
report['authority_counts']={'index':len(rows),'manifest':len(manifest['files'])}
captures=[]
for p in changed:
 if not p.startswith('docs/exec-plans/evidence/HG-044/') or not p.endswith('.json'):continue
 data=obj(p)
 if 'raw_utf8' not in data:continue
 raw=data['raw_utf8'].encode();assert digest(raw)==data['raw_sha256'] and len(raw)==data['raw_byte_count'];assert type(data['exit_code']) is int and data['exit_code']==0 and data['result']=='PASS'
 captures.append({'path':p,'sha256':digest(blob(p)),'raw_sha256':digest(raw),'tested_commit':data['tested_commit']})
report['raw_captures']=captures
integrity=obj('docs/exec-plans/evidence/HG-044/capture-integrity-4302c06.json');assert integrity['tested_commit']==TESTED
selected=[]
for c in record['checks_run']:
 data=obj(c['evidence_ref']);assert data['tested_commit']==TESTED and data['base_commit']==BASE and data.get('result',data.get('status'))=='PASS'
 assert c['result']=='PASS' and data.get('command',c['command'])==c['command']
 if c['check_id']!='scope':
  i=next(i for i in integrity['records'] if i['check_id']==c['check_id']);assert i['sha256']==digest(blob(c['evidence_ref'])) and i['raw_sha256']==data['raw_sha256'] and i['raw_byte_count']==data['raw_byte_count']
 selected.append({'check_id':c['check_id'],'path':c['evidence_ref'],'raw_utf8':data.get('raw_utf8'),'sha256':digest(blob(c['evidence_ref']))})
report['selected_checks']=selected
for name,count in [('focused',83),('harness',873),('unit',232)]:assert f'{count} passed' in next(c['raw_utf8'] for c in selected if c['check_id']==name)
backlog=obj(v.BACKLOG);tasks={t['id']:t for t in backlog['tasks']}
assert {t['id'] for t in tasks.values() if t['milestone']=='M3' and t['status']!='SUPERSEDED'}==v.M3_TASK_IDS and len(v.M3_TASK_IDS)==16
pairs={(name,c) for mapping in v.M3_EXIT_TASK_CHECKS.values() for name,checks in mapping.items() for c in checks}
assert len(pairs)==52
selectors=set()
for name,check in pairs:
 contracts=[c for c in tasks[name]['check_contracts'] if c['check_id']==check];assert len(contracts)==1
 assert v.canonical_value_sha(contracts[0])==v.M3_CHECK_CONTRACT_DIGESTS[name+':'+check]
 command=contracts[0]['command'];assert command.startswith('uv run pytest -q ')
 selectors.update(command.removeprefix('uv run pytest -q ').split())
commands=set(v.M3_REGRESSION_COMMANDS);assert {'uv run pytest -q '+s for s in selectors}<=commands or all(any(s in c.split() for c in commands) for s in selectors)
report['mapping']={'tasks':sorted(v.M3_TASK_IDS),'named_checks':len(pairs),'selectors':sorted(selectors),'regression_commands':len(commands)}
ledger=v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(),'Boundary layer ledger');assert len(ledger)==31
assert not v.m3_boundary_layer_errors(ledger,obj('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements'])
assert sum(r['disposition']=='KL028_PLANNED_EXECUTABLE' for r in ledger)==19
report['boundary_deferred']=[r for r in ledger if r['disposition']!='KL028_PLANNED_EXECUTABLE']
assert len(report['boundary_deferred'])==12
schema=[jsonschema.Draft202012Validator(obj(p)) for p in (v.MILESTONE_CLOSURE_SCHEMA,v.INTEGRATION_SCHEMA,'THREAD_RESULT.schema.json','THREAD_REVIEW.schema.json')]
assert not v.milestone_closure_errors(ROOT,obj('docs/exec-plans/milestones/M1.json'),*schema,backlog,tasks)
assert not v.m2_milestone_closure_errors(ROOT,obj('docs/exec-plans/milestones/M2.json'),*schema,backlog,tasks)
pending=list(v.M3_TASK_IDS|{'KL-074'});records={};missing=[]
while pending:
 name=pending.pop()
 if name in records or name in missing:continue
 p=f'docs/exec-plans/integrations/{name}.json'
 if not git('ls-tree',HEAD,'--',p):missing.append(name);continue
 item=obj(p);records[name]=item
 assert not v.integration_record_errors(ROOT,Path(p),item,*schema[1:],tasks),(name,'integration')
 assert all(v.is_ancestor(ROOT,item[k],HEAD) for k in ('result_commit','reviewed_head_sha','review_record_commit','merge_commit'))
 rp=v.result_paths_at_revision(ROOT,name,item['reviewed_head_sha']);assert len(rp)==1
 result=yaml.safe_load(blob(rp[0],item['reviewed_head_sha']));assert blob(rp[0],item['reviewed_head_sha'])==blob(rp[0],item['result_commit'])
 for kind in tasks[name]['review_requirements']:blob(f'docs/exec-plans/reviews/{name}/{kind}.json',item['review_record_commit'])
 pending.extend(tasks[name]['depends_on'])
for name,item in records.items():
 result=yaml.safe_load(blob(v.result_paths_at_revision(ROOT,name,item['reviewed_head_sha'])[0],item['reviewed_head_sha']))
 assert all(v.is_ancestor(ROOT,records[d]['merge_commit'],result[k]) for d in tasks[name]['depends_on'] for k in ('base_commit','tested_commit'))
assert set(missing)=={'KL-028','KL-029'}
report['available_transitive_integrations']=sorted(records);report['absent_prospective_integrations']=sorted(missing)
report['status']='PASS';OUT.write_text(json.dumps(report,indent=2)+'\n');print('GENERAL_R2_AUDIT_PASS',len(changed),len(captures),len(records))
