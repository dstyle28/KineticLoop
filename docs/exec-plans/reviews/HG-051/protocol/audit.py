from pathlib import Path
import subprocess, json, importlib.util, hashlib, xml.etree.ElementTree as ET
import yaml
R=Path.cwd(); B='b877db0edd2e4550d6ea81750656112fb7f2e223'; H='7141b1dfe48df8f0e25429cf9ff646af6de4b5ce'; T='5debfe1b41a26c0b3f985917b80995a9eb38b92e'
def git(*a): return subprocess.check_output(['git',*a],cwd=R)
def obj(path,rev=H): return git('show',rev+':'+path)
def js(path,rev=H): return json.loads(obj(path,rev))
s=importlib.util.spec_from_file_location('protocol_compact',R/'tools/harness/compact_evidence.py'); ce=importlib.util.module_from_spec(s); s.loader.exec_module(ce)
changed=git('diff','--no-renames','--name-only',B,H).decode().splitlines()
assert not [p for p in changed if p.startswith(('src/','migrations/','protocol_model/','.github/'))]
frozen=js('FROZEN_BASELINE.json',B)
for p in ['FROZEN_BASELINE.json']+[x['path'] for x in frozen['files']]: assert obj(p,B)==obj(p,H)
for p in ['CURRENT_REQUIREMENT_SET.json','KineticLoop_Acceptance_Spec_v1.2.2.json','KineticLoop_Integration_Acceptance_v0.1.json']: assert obj(p,B)==obj(p,H)
old=js('KineticLoop_Harness_Backlog_v0.2.json',B); new=js('KineticLoop_Harness_Backlog_v0.2.json')
for a,b in zip(old['tasks'],new['tasks'],strict=True):
 if a['id']=='KL-080':
  x=dict(b); x['definition_of_done']=a['definition_of_done']; assert x==a
 else: assert a==b
prior=git('ls-tree','-r','--name-only',B,'--','docs/exec-plans/evidence','docs/exec-plans/completed','docs/exec-plans/reviews').decode().splitlines()
for p in prior: assert git('rev-parse',B+':'+p)==git('rev-parse',H+':'+p)
for rev in git('rev-list','--reverse',T+'..'+H).decode().splitlines():
 assert len(git('rev-list','--parents','-n','1',rev).split())==2
 for p in git('diff-tree','--no-commit-id','--name-only','-r',rev).decode().splitlines(): assert p=='docs/exec-plans/governance/HG-051.yaml' or p.startswith('docs/exec-plans/evidence/HG-051/')
idx=js('CURRENT_DOCUMENT_INDEX.json'); checked=0
for x in idx['documents']+idx['machine_readable']:
 assert hashlib.sha256(obj(x['path'])).hexdigest()==x['sha256']; checked+=1
schema=js('HISTORICAL_EVIDENCE_MAPPING.schema.json'); originals=ce.historical_originals(); assert len(originals)==4
hist=[]
for o in originals:
 raw=ce.archive_original(R,o)
 ref=o['execution_record']; d=ce.blob(R,ref['path'],ref['revision']); assert hashlib.sha256(d).hexdigest()==ref['sha256'] and len(d)==ref['bytes']
 assert o['execution']['timestamp'] is None
 if 'source_suite' in o['path']: assert o['execution']['exit_code']==1 and o['execution']['result']=='FAIL'
 else: assert o['execution']['exit_code']==0 and o['execution']['result']=='PASS'
 hist.append({'path':o['path'],'length':len(raw),'original_verified':True,'recorded_result':o['execution']['result']})
for ref in schema['properties']['preserved_records']['const']:
 data=ce.blob(R,ref['path'],ref['revision']); assert hashlib.sha256(data).hexdigest()==ref['sha256'] and len(data)==ref['bytes']
 if ref['path'].endswith('_RESULT.yaml'):
  r=yaml.safe_load(data); assert (r['task_status'],r['task_checks_status'],r['integration_status'])==('BLOCKED','FAIL','UNMERGED')
 else: assert json.loads(data)['status']=='CHANGES_REQUIRED'
g=yaml.safe_load(obj('docs/exec-plans/governance/HG-051.yaml')); assert g['tested_commit']==T and g['base_commit']==B
counts={}
for check in g['checks_run']:
 ref=check['evidence_ref']; m=js(ref); assert m['tested_commit']==T and m['command']==check['command'] and m['exit_code']==0 and check['result']=='PASS'
 raw=ce.read(R,ref,H,tested=T,command=check['command'],exit_code=0)
 if check['check_id'] in ('harness','unit','focused'):
  text=raw.decode(); assert 'passed' in text and not __import__('re').search(r'\b[1-9][0-9]* (failed|skipped|errors?|xfailed|xpassed)\b',text)
  counts[check['check_id']]=text.strip().splitlines()[-1]
for name in ('focused-junit.json','unit-junit.json','harness-junit-xml.json'):
 raw=ce.read(R,'docs/exec-plans/evidence/HG-051/final-5debfe1/'+name,H)
 tree=ET.fromstring(raw); cases=tree.findall('.//testcase'); assert cases and not tree.findall('.//failure') and not tree.findall('.//error') and not tree.findall('.//skipped')
 counts[name]=len(cases)
execs=js('docs/exec-plans/evidence/HG-051/final-5debfe1/EXECUTION.json'); assert execs['source_end_sha']==T and execs['source_end_status']==''
for x in execs['executions']: assert x['exit_code']==0 and x['tested_commit']==T
budget=ce.audit(R,B,H,'HG-051'); assert not budget['errors'],budget
assert ce.PLAIN_LIMIT==262144 and ce.STORED_LIMIT==8388608 and ce.RAW_LIMIT==67108864 and ce.TOTAL_LIMIT==16777216
print(json.dumps({'reviewed_sha':H,'tested_sha':T,'base_sha':B,'audit_status':'PASS','changed_files':len(changed),'untouched_historical_files':len(prior),'indexed_hashes_checked':checked,'runtime_or_frozen_changes':False,'kl080_check_oracle_dependency_resource_changes':False,'historical_objects_verified':hist,'test_counts':counts,'reviewed_budget_bytes':budget['stored_bytes'],'actual_kl080_migration':False,'closure_or_product_release_credit':False},indent=2))
