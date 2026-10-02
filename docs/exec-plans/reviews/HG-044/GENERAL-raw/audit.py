"""Independent committed-tree scope, hash, suffix and prerequisite audit."""
import ast, hashlib, importlib.util, json, subprocess
from pathlib import Path
import jsonschema
root=Path.cwd();head='351f0eda41ad492e66115f9ea1e41e3e0f9abf3d';base='9268fc8dd8c071c02dc5c698274dbf6fcd112776';tested='e748b37ec92e119190afad87478b7ecb951e5b5d'
def git(*a):return subprocess.check_output(['git',*a],cwd=root)
def blob(p,rev=head):return git('show',rev+':'+p)
def obj(p,rev=head):return json.loads(blob(p,rev))
def sha(b):return hashlib.sha256(b).hexdigest()
s=importlib.util.spec_from_file_location('v',root/'tools/harness/validate_harness.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
report={'reviewed_head_sha':head,'base_commit':base,'tested_commit':tested}
index=obj('CURRENT_DOCUMENT_INDEX.json');report['authority_hashes']=[dict(path=e['path'],valid=sha(blob(e['path']))==e['sha256']) for e in index['documents']+index['machine_readable']]
manifest=obj('HARNESS_DOCUMENT_MANIFEST.json');report['manifest_hashes']=[dict(path=e['path'],valid=sha(blob(e['path']))==e['sha256'] and len(blob(e['path']))==e['bytes']) for e in manifest['files']]
record=v.load_artifact_text(blob('docs/exec-plans/governance/HG-044.yaml').decode(),'.yaml')
changed=set(git('diff','--name-only',base,head).decode().splitlines());report['declared_exact']=changed==set(record['files_changed']);report['write_scope_exact']=all(v.matches(p,v.governance_allowed_patterns('HG-044')) for p in changed)
report['tested_suffix_errors']=v.governance_suffix_errors(root,tested,head,'HG-044','tested');report['head_exact']=git('rev-parse','HEAD').decode().strip()==head
report['selected_captures']=[]
for c in record['checks_run']:
 d=obj(c['evidence_ref']);row=dict(check_id=c['check_id'],path=c['evidence_ref'],sha256=sha(blob(c['evidence_ref'])),result=c['result'])
 if 'raw_utf8' in d:
  raw=d['raw_utf8'].encode();row.update(raw_sha256=sha(raw),raw_count=len(raw),valid_raw=sha(raw)==d['raw_sha256'] and len(raw)==d['raw_byte_count'],valid_binding=d['tested_commit']==tested and d['base_commit']==base and d['command']==c['command'] and d['check_id']==c['check_id'] and d['result']=='PASS' and type(d['exit_code']) is int and d['exit_code']==0,raw_summary=d['raw_utf8'][-500:])
 else:row.update(valid_raw=True,valid_binding=d['tested_commit']==tested and d['status']=='PASS' and all(d['checks'].values()))
 report['selected_captures'].append(row)
report['all_raw_captures']=[]
for p in sorted(changed):
 if p.startswith('docs/exec-plans/evidence/HG-044/') and p.endswith('.json'):
  d=obj(p)
  if 'raw_utf8' in d:report['all_raw_captures'].append(dict(path=p,valid=sha(d['raw_utf8'].encode())==d['raw_sha256'] and len(d['raw_utf8'].encode())==d['raw_byte_count']))
def funcs(b):
 text=b.decode();lines=text.splitlines(keepends=True);return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
f0,f1=funcs(blob('tools/harness/validate_harness.py',base)),funcs(blob('tools/harness/validate_harness.py'))
report['existing_functions_changed']=[n for n in f0 if f0[n]!=f1[n]]
old_schema=obj(v.MILESTONE_CLOSURE_SCHEMA,base);new_schema=obj(v.MILESTONE_CLOSURE_SCHEMA);report['m1_m2_schema_preserved']=old_schema['oneOf']==new_schema['oneOf'][:2] and all(new_schema['$defs'][k]==x for k,x in old_schema['$defs'].items())
report['m3_absent']=not v.revision_regular_file(root,'docs/exec-plans/milestones/M3.json',head) and not (root/'docs/exec-plans/milestones/M3.json').exists()
backlog=obj(v.BACKLOG);tasks={t['id']:t for t in backlog['tasks']};schemas=[jsonschema.Draft202012Validator(obj(n)) for n in (v.MILESTONE_CLOSURE_SCHEMA,v.INTEGRATION_SCHEMA,'THREAD_RESULT.schema.json','THREAD_REVIEW.schema.json')]
report['m1_errors']=v.milestone_closure_errors(root,obj('docs/exec-plans/milestones/M1.json'),*schemas,backlog,tasks)
report['m2_errors']=v.m2_milestone_closure_errors(root,obj('docs/exec-plans/milestones/M2.json'),*schemas,backlog,tasks)
report['named_check_digests']=[]
for key,digest in v.M3_CHECK_CONTRACT_DIGESTS.items():
 task,check=key.split(':');contracts=[c for c in tasks[task]['check_contracts'] if c['check_id']==check];report['named_check_digests'].append(dict(key=key,valid=len(contracts)==1 and v.canonical_value_sha(contracts[0])==digest))
records={};pending=list(v.M3_TASK_IDS-{'KL-028','KL-029'}|{'KL-074'})
while pending:
 name=pending.pop()
 if name in records:continue
 records[name]=obj(f'docs/exec-plans/integrations/{name}.json');pending.extend(tasks[name]['depends_on'])
report['integrations']=[]
for name,record in sorted(records.items()):
 reviewed=record['reviewed_head_sha'];p=v.result_paths_at_revision(root,name,reviewed)[0];r=v.load_artifact_at_revision(root,p,reviewed)
 row=dict(task=name,result_path=p,result_sha256=sha(blob(p,reviewed)),errors=v.integration_record_errors(root,Path(f'docs/exec-plans/integrations/{name}.json'),record,*schemas[1:],tasks),reachable={k:v.is_ancestor(root,record[k],head) for k in ('result_commit','reviewed_head_sha','review_record_commit','merge_commit')},dependencies=[dict(task=dep,merge_commit=records[dep]['merge_commit'],before_base=v.is_ancestor(root,records[dep]['merge_commit'],r['base_commit']),before_tested=v.is_ancestor(root,records[dep]['merge_commit'],r['tested_commit'])) for dep in tasks[name]['depends_on']]);report['integrations'].append(row)
report['missing_prospective']=[n for n in ('KL-028','KL-029') if not v.revision_regular_file(root,f'docs/exec-plans/integrations/{n}.json',head)]
(root/'docs/exec-plans/reviews/HG-044/GENERAL-raw/audit.json').write_text(json.dumps(report,indent=2)+'\n');print('audit retained',len(records),'integration chains')
