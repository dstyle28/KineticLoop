import subprocess,json,hashlib,os,importlib.util,copy
from pathlib import Path
import yaml,jsonschema
root=Path.cwd(); base='70dc4863ccdca95f7a44e79b68501a698262e323'; tested='35044fd3d94472b41b1bbe6c0313a2a7701c8063'; reviewed='5f41d88c5f8c3142b43b3101486c1fa149394543'
def git(*args):return subprocess.check_output(['git',*args],text=True)
def obj(rev,path):return json.loads(git('show',rev+':'+path))
assert git('rev-parse','HEAD').strip()==reviewed
record=yaml.safe_load((root/'docs/exec-plans/governance/HG-040.yaml').read_text()); jsonschema.validate(record,json.loads((root/'HARNESS_CHANGE.schema.json').read_text()))
changed=set(git('diff','--name-only',base,reviewed).splitlines()); assert changed==set(record['files_changed'])
assert record['base_commit']==base and record['tested_commit']==tested and len(record['checks_run'])==10
assert not any(p.startswith(('docs/history/','src/','migrations/','.github/','docs/exec-plans/completed/','docs/exec-plans/reviews/','docs/exec-plans/integrations/')) for p in changed)
old=obj(base,'KineticLoop_Harness_Backlog_v0.2.json');new=obj(reviewed,'KineticLoop_Harness_Backlog_v0.2.json');a={t['id']:t for t in old['tasks']};b={t['id']:t for t in new['tasks']};assert set(b)-set(a)=={'KL-078'}
assert [k for k in a if a[k]!=b[k]]==['KL-076']
assert set(k for k in a['KL-076'] if a['KL-076'][k]!=b['KL-076'][k])=={'depends_on','context_files','entry_conditions'}
assert b['KL-078']['status']=='NOT_STARTED' and b['KL-078']['requirements_covered']==[] and b['KL-078']['evidence_refs']==[]
for name in ('KL-076','KL-078'):
 assert not any('/'+name+'/' in p or '/'+name+'_RESULT.' in p or p.endswith('/'+name+'.json') for p in git('ls-tree','-r','--name-only',reviewed,'--','docs/exec-plans/completed','docs/exec-plans/reviews','docs/exec-plans/integrations').splitlines())
spec=importlib.util.spec_from_file_location('v',root/'tools/harness/validate_harness.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
assert v.governance_suffix_errors(root,tested,reviewed,'HG-040','tested')==[]
for name in ('KL-076','KL-078'):
 assert v.m3_next_wave_definition_errors(b[name])==[]
 assert v.packet_errors(b[name],(root/f'docs/exec-plans/active/{name}.md').read_text())==[]
for name in ('KL-026','KL-027','KL-075','KL-077'):
 assert b[name]==a[name]
 assert v.m3_next_wave_definition_errors(b[name])==[]
for p in ('05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md','FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','KineticLoop_Acceptance_Spec_v1.2.2.json','KineticLoop_Integration_Acceptance_v0.1.json','KineticLoop_Evidence_Manifest_v0.1.json'):
 assert git('rev-parse',base+':'+p)==git('rev-parse',reviewed+':'+p)
for ent in obj(reviewed,'CURRENT_DOCUMENT_INDEX.json')['documents']+obj(reviewed,'CURRENT_DOCUMENT_INDEX.json')['machine_readable']:
 assert hashlib.sha256((root/ent['path']).read_bytes()).hexdigest()==ent['sha256']
manifest=obj(reviewed,'HARNESS_DOCUMENT_MANIFEST.json')
for ent in manifest['files']:
 raw=(root/ent['path']).read_bytes();assert len(raw)==ent['bytes'] and hashlib.sha256(raw).hexdigest()==ent['sha256']
raw_summary=[]
for check in record['checks_run']:
 p=Path(check['evidence_ref']);raw=json.loads((root/p).read_text());side=json.loads((root/p.with_suffix('.json')).read_text());payload=raw['raw_utf8'].encode()
 assert check['result']==side['result']=='PASS' and raw['exit_code']==side['exit_code']==0
 assert raw['base_commit']==base and raw['tested_commit']==side['tested_commit']==tested
 assert raw['command']==side['command']==check['command']
 assert side['check_id']==check['check_id'] and side['evidence_ref']==check['evidence_ref']
 assert hashlib.sha256(payload).hexdigest()==raw['raw_sha256'] and len(payload)==raw['raw_byte_count']
 assert git('show',reviewed+':'+str(p))==(root/p).read_text()
 raw_summary.append({'check_id':check['check_id'],'raw_sha256':raw['raw_sha256'],'raw_byte_count':len(payload),'exit_code':0})
print(json.dumps({'status':'INDEPENDENT_GENERAL_AUDIT_PASS','base_commit':base,'tested_commit':tested,'reviewed_head_sha':reviewed,'changed_path_count':len(changed),'final_checks':raw_summary,'unchanged_old_tasks':len(a)-1,'changed_definitions':['KL-076','KL-078'],'tested_suffix':'one linear commit; own record update and twenty new evidence files only'},indent=2))
oldtrace=obj(base,'KineticLoop_Harness_Traceability_v0.3.json');newtrace=obj(reviewed,'KineticLoop_Harness_Traceability_v0.3.json')
x={t['task_identity']:t for t in oldtrace['tasks']};y={t['task_identity']:t for t in newtrace['tasks']}
assert set(y)-set(x)=={'harness-backlog-v0.2/KL-078'} and not set(x)-set(y)
assert {k for k in x if x[k]!=y[k]}=={'harness-backlog-v0.2/KL-076'}
for name in ('KL-076','KL-078'): assert v.traceability_projection(b[name])==y[b[name]['task_identity']]
for section in ('documents','machine_readable'):
 oi=obj(base,'CURRENT_DOCUMENT_INDEX.json')[section];ni=obj(reviewed,'CURRENT_DOCUMENT_INDEX.json')[section]
 assert len(oi)==len(ni)
 for o,n in zip(oi,ni):assert {k:val for k,val in o.items() if k!='sha256'}=={k:val for k,val in n.items() if k!='sha256'}
om={e['path']:e for e in obj(base,'HARNESS_DOCUMENT_MANIFEST.json')['files']};nm={e['path']:e for e in manifest['files']}
assert set(nm)-set(om)=={'docs/exec-plans/active/KL-078.md'} and not set(om)-set(nm)
for p in om:
 if om[p]!=nm[p]:assert p in changed
print('EXACT_TRACEABILITY_AND_DERIVED_ENTRY_GUARDS_PASS')
