"""Independent committed HG053 security evidence verification; no runtime execution."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,importlib.util,json,subprocess,xml.etree.ElementTree as ET
import jsonschema,yaml
ROOT=Path(__file__).resolve().parents[5]
B='c82e50aefad5c4d9e325d4928a8f96032b81192d'
C='a75a41edfb1b58828b81053b4ac3afa51457a279'
R='2936848abed73320db56f71a649e86eca1497502'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(path,revision=R):
 entry=git('ls-tree',revision,'--',path).decode().split()
 assert entry[:2]==['100644','blob'],(path,entry)
 return git('show',revision+':'+path)
spec=importlib.util.spec_from_file_location('compact',ROOT/'tools/harness/compact_evidence.py')
compact=importlib.util.module_from_spec(spec);spec.loader.exec_module(compact)
def recover(path,command=None):return compact.read(ROOT,path,R,tested=C,command=command,exit_code=0)
base='docs/exec-plans/evidence/HG-053/checks-'+C+'/'
index=json.loads(blob(base+'CHECK_INDEX.json'));assert index['tested_commit']==C
record=yaml.safe_load(blob('docs/exec-plans/governance/HG-053.yaml'))
jsonschema.validate(record,json.loads(blob('HARNESS_CHANGE.schema.json')))
assert record['base_commit']==B and record['tested_commit']==C and record['frozen_impact']=='NONE'
assert record['change_status']=='PASS' and len(index['checks'])==len(record['checks_run'])==7
checks=[]
raws={}
for check,declared in zip(index['checks'],record['checks_run'],strict=True):
 assert all(check[k]==declared[k] for k in ['check_id','command','result','evidence_ref'])
 assert check['result']=='PASS' and check['exit_code']==0
 raw=recover(check['evidence_ref'],check['command']);raws[check['check_id']]=raw
 checks.append({'id':check['check_id'],'raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),'command':check['command']})
 for ref in check.get('ancillary_refs',[]):recover(ref,check['command'])
assert b'247 passed' in raws['unit'] and b'1492 passed' in raws['harness']
h=index['checks'][-1]
anc={Path(ref).name:recover(ref,h['command']) for ref in h['ancillary_refs']}
collection=json.loads(next(v for k,v in anc.items() if 'collection.json.json' in k))
execution=json.loads(anc['harness-execution.json.json'])
manifest=json.loads(anc['harness-manifest.json.json'])
assert collection['exit_code']==execution['exit_code']==0 and not collection['errors'] and not execution['errors']
assert len(collection['collections'])==1
serial=next(iter(collection['collections'].values()))
assert len(serial)==len(set(serial))==1492
assert set(execution['collections'])=={'gw0','gw1'}
assert all(nodes==serial for nodes in execution['collections'].values())
assert Counter(execution['started'])==Counter(serial)
phases=defaultdict(Counter)
for report in execution['reports']:
 assert report['nodeid'] in serial and report['outcome']=='passed' and report['worker'] in {'gw0','gw1'}
 phases[report['nodeid']][report['phase']]+=1
assert len(execution['reports'])==4476 and len(phases)==1492
assert all(p==Counter({'setup':1,'call':1,'teardown':1}) for p in phases.values())
assert manifest['tested_commit']==C and manifest['dirty_source'] is False and manifest['workers']==2
assert manifest['mode']=='EXECUTION' and manifest['execution_complete'] is True
assert manifest['exit_code']==manifest['pytest_exit_code']==0 and manifest['errors']==[]
for file in manifest['files']:
 name=file['path']
 key=next(k for k in anc if ('harness-'+name+'.json' in k or k== 'harness-'+name+'.json.json'))
 raw=anc[key];assert file['bytes']==len(raw) and file['sha256']==hashlib.sha256(raw).hexdigest()
junit=ET.fromstring(anc['harness-junit.xml.json'])
cases=junit.findall('.//testcase');assert len(cases)==1492
assert not junit.findall('.//failure') and not junit.findall('.//error') and not junit.findall('.//skipped')
def junit_id(node):
 path,rest=node.split('::',1)
 main,sep,param=rest.partition('[')
 parts=main.split('::');return (path.removesuffix('.py').replace('/','.')+('.'+'.'.join(parts[:-1]) if len(parts)>1 else ''),parts[-1]+(sep+param if sep else ''))
actual_ids=Counter((x.attrib['classname'],x.attrib['name']) for x in cases)
expected_ids=Counter(map(junit_id,serial))
assert actual_ids==expected_ids
unit=ET.fromstring(recover(index['checks'][-2]['ancillary_refs'][0],index['checks'][-2]['command']))
assert len(unit.findall('.//testcase'))==247
assert not unit.findall('.//failure') and not unit.findall('.//error') and not unit.findall('.//skipped')
for rev in (B,C):subprocess.run(['git','merge-base','--is-ancestor',rev,R],cwd=ROOT,check=True)
suffix=git('diff','--name-only',C,R).decode().splitlines()
assert all(p.startswith('docs/exec-plans/evidence/HG-053/') or p=='docs/exec-plans/governance/HG-053.yaml' for p in suffix)
changed=git('diff','--name-only',B,R).decode().splitlines()
allowed={'CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json','docs/exec-plans/active/KL-036.md','docs/exec-plans/active/KL-037.md','docs/exec-plans/governance/HG-053.yaml'}
assert all(p in allowed or p.startswith('docs/exec-plans/evidence/HG-053/') for p in changed)
assert sorted(changed)==sorted(record['files_changed'])
before=json.loads(blob('KineticLoop_Harness_Backlog_v0.2.json',B));after=json.loads(blob('KineticLoop_Harness_Backlog_v0.2.json'))
assert [a['id'] for a,b in zip(before['tasks'],after['tasks'],strict=True) if a!=b]==['KL-036','KL-037']
for task in after['tasks']:
 if task['id'] not in {'KL-036','KL-037'}:continue
 assert task['status']=='NOT_STARTED' and task['requirements_covered']==[] and task['evidence_refs']==[]
 for dep in task['depends_on']:
  integration=json.loads(blob('docs/exec-plans/integrations/'+dep+'.json'))
  assert integration['task_identity']=='harness-backlog-v0.2/'+dep and integration['integration_status']=='MERGED'
  subprocess.run(['git','merge-base','--is-ancestor',integration['merge_commit'],B],cwd=ROOT,check=True)
 for phrase in ['Registered TEST logins remain nonwriters','Provider/event payloads are','Production auto-activation remains disabled','current_user =','no direct test-admin DML','never DSNs/secrets/data']:
  assert phrase in blob('docs/exec-plans/active/'+task['id']+'.md').decode(),phrase
storage=compact.audit(ROOT,B,R,'HG-053');assert not storage['errors'],storage
result={'status':'PASS','base_commit':B,'tested_commit':C,'reviewed_head_sha':R,'checks':checks,'harness':{'serial_collected':1492,'worker_collections':2,'started':1492,'reports':4476,'junit':1492,'failed':0,'skipped':0,'manifest_file_hashes_verified':5},'unit':{'junit':247,'failed':0,'skipped':0},'scope_and_C_to_R_bookkeeping':'PASS','prerequisite_ancestry':'PASS','storage_audit':storage,'runtime_implementation_checks':'NOT_RUN','product_claims':[]}
print(json.dumps(result,indent=2))
(ROOT/'docs/exec-plans/reviews/HG-053/security/VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n')
