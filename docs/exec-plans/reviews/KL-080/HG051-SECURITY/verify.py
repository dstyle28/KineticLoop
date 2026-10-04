"""Independent read-only SHA-bound KL080 security/evidence probes; no DB lifecycle."""
import sys, json, hashlib, collections, subprocess, xml.etree.ElementTree as ET
from pathlib import Path
import yaml
ROOT=Path('/Users/davetian/.codex/worktrees/59e4/KineticLoop')
HEAD='417b65ee68244dc86ab02add231b24dc662be790'
BASE='1d3075151246b2774640a3d7acec836f47ab2b8d'
TESTED='feb3236c175df171611fc5b7ddb4f6eeca3ce47c'
D='docs/exec-plans/evidence/KL-080/HG051-'+TESTED+'/'
sys.path.insert(0,str(ROOT/'tools/harness'))
import compact_evidence as ce
out={'reviewed_head_sha':HEAD,'base_commit':BASE,'tested_commit':TESTED}
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(p,rev=HEAD): return ce.blob(ROOT,p,rev)
def js(p,rev=HEAD): return json.loads(blob(p,rev))
def sha(b): return hashlib.sha256(b).hexdigest()
def ancestor(a,b): git('merge-base','--is-ancestor',a,b)
def raw(ref,command=None):
 p=ref['path']; b=blob(p); assert sha(b)==ref['sha256'],p
 data=ce.read(ROOT,p,HEAD,tested=TESTED,command=command,exit_code=0)
 assert sha(data)==ref['raw_sha256'] and len(data)==ref['raw_bytes'],p
 return data
ancestor(BASE,TESTED);ancestor(TESTED,HEAD)
assert not git('diff',TESTED,HEAD,'--','src','tests','tools','.github','docs/contracts','FROZEN_BASELINE.json','CURRENT_DOCUMENT_INDEX.json')
idx=js('CURRENT_DOCUMENT_INDEX.json')
for row in idx['documents']+idx['machine_readable']:
 assert sha(blob(row['path']))==row['sha256'],row['path']
 assert blob(row['path'])==blob(row['path'],BASE),row['path']
out['current_authority_hashes_and_base_bytes']=len(idx['documents']+idx['machine_readable'])
prereqs=[]
for n in [76,79,77,27,78,26,23,22,28,29]:
 task=f'KL-{n:03d}';p=f'docs/exec-plans/completed/{task}_RESULT.yaml'
 result=yaml.safe_load(blob(p,BASE));assert result['task_status']=='PASS'
 integ=js(f'docs/exec-plans/integrations/{task}.json',BASE)
 assert integ['integration_status']=='MERGED';ancestor(integ['merge_commit'],BASE)
 prereqs.append(task)
out['prerequisite_pass_and_merged_at_base']=prereqs
packet=blob('docs/exec-plans/active/KL-080.md').decode(); contracts=json.loads(packet.split('```json\n',1)[1].split('```',1)[0])['check_contracts']
expected={x['check_id']:x['command'] for x in contracts}
checks=js(D+'final-checks.json')['executions'];assert len(checks)==len(expected)==17
summary={}
for x in checks:
 cid=x['check_id'];assert x['command']==expected[cid] and x['tested_commit']==TESTED and x['exit_code']==0 and x['result']=='PASS'
 stdout=raw(x['stdout'],x['command'])
 record=json.loads(raw(x['execution_record'],x['command']))
 assert record['command']==x['command'] and record['tested_commit']==TESTED and record['exit_code']==0
 assert record['sha256']==sha(stdout)
 counts=None
 if 'junit' in x:
  xml=ET.fromstring(raw(x['junit'],x['command']));cases=xml.findall('.//testcase')
  assert cases and not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
  assert len(cases)==x['counts']['executed'];counts=len(cases)
 if 'collection.json' in x:
  collection=json.loads(raw(x['collection.json']))
  assert collection['tested_commit']==TESTED and collection['exit_code']==0
  assert len(collection['nodeids'])==counts
  raw(x['collection.log'])
 summary[cid]={'command':x['command'],'exit_code':0,'testcases':counts}
out['packet_executions']=summary
host=js('docs/exec-plans/evidence/KL-080/HG051-hosted-index-correction/hosted-db-verification.json')
assert len(host['raw_artifacts'])==15
hostraw={k:raw(v) for k,v in host['raw_artifacts'].items()}
manifest=json.loads(hostraw['manifest.json']);assert manifest['tested_commit']==TESTED
assert manifest['provenance']['github_run_id']==str(host['run_id'])=='37161315464'
for x in manifest['artifacts']+[c['stdout'] for c in manifest['checks']]:
 assert sha(hostraw[x['path']])==x['sha256'] and len(hostraw[x['path']])==x['bytes']
assert all(c['exit_code']==0 and not c['interrupted'] for c in manifest['checks'])
assert manifest['remaining_containers']==manifest['remaining_volumes']==''
xml=ET.fromstring(hostraw['database.xml']);cases=xml.findall('.//testcase')
assert len(cases)==780 and not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
col=json.loads(hostraw['collection.json']);exe=json.loads(hostraw['execution.json'])
assert col==exe
sup=host['supersedes'];assert sha(blob(sup['path'],sup['revision']))==sup['sha256'];assert blob(sup['path'])==blob(sup['path'],sup['revision'])
out['hosted']={'keys':sorted(hostraw),'testcases':780,'run_id':host['run_id'],'manifest_artifact_checks':'PASS','old_index_preserved':True,'collection_equals_execution':True,'collection_shape':list(col) if isinstance(col,dict) else 'array'}
map_path='docs/exec-plans/evidence/KL-080/HISTORICAL_EVIDENCE_MAPPING.json';mapping=js(map_path)
archives=ce.validate_archive(ROOT,mapping,HEAD,verify_originals=True);assert len(archives)==4
archive_errors,_=ce.archive_audit(ROOT,HEAD);assert not archive_errors,archive_errors
mapping_commit=git('log','--format=%H','--diff-filter=A',HEAD,'--',map_path).decode().splitlines()[0]
ancestor(mapping_commit,TESTED)
for x in mapping['entries']:
 ancestor(x['original']['revision'],x['storage']['revision']);ancestor(x['storage']['revision'],mapping_commit)
 try: ce.read(ROOT,x['original']['path'],HEAD)
 except ValueError: pass
 else: raise AssertionError('archival representation accepted by ordinary reader')
assert [x['original']['execution']['exit_code'] for x in mapping['entries']]==[0,1,0,1]
preserve='78dfa7ff6d28eaca515d83b29f8a16453eba5832'
changed=git('diff','--name-only','--diff-filter=MDT',preserve,HEAD,'--','docs/exec-plans/evidence/KL-080').decode().splitlines()
assert set(changed)==set(archives),changed
out['archive']={'roundtrips':4,'ordinary_reads_rejected':4,'mapping_commit':mapping_commit,'historical_exit_codes':[0,1,0,1],'nonmigrated_history_unchanged':True,'historical_outcome':mapping['historical_outcome']}
w=[]
for line in ce.read(ROOT,D+'source_suite_dc.stdout.capture.json',HEAD,tested=TESTED).decode().splitlines():
 if 'SOURCE_EVIDENCE ' in line: w.append(json.loads(line.split('SOURCE_EVIDENCE ',1)[1]))
by=collections.defaultdict(list)
for x in w: by[x['kind']].append(x)
assert len(by['kl080_namespace'])==len(by['kl080_cleanup'])==106
for x in by['kl080_namespace']:
 assert x['tested_commit']==TESTED
 token=sha(str(Path(x['root']).resolve()).encode())[:12]
 assert x['database']==f'kineticloop_kl080_source_{TESTED[:7]}_{token}'
 assert x['compose']==f'kineticloop-kl080-source-{TESTED[:7]}-{token}'
for x in by['kl080_cleanup']: assert not any(x['remaining'].values())
prior=by['kl080_prior_deployment_earlier_denial'][0]
ancestor(prior['protected_revision'],BASE)
for p,h in prior['verified_blobs'].items(): assert sha(blob(p,prior['protected_revision']))==h and blob(p,prior['protected_revision'])==blob(p,BASE)
assert prior['reached']==['_progress_sources -> _verify_full_progress'] and prior['no_later_freshness_claim']
assert set(prior['child_connection_databases'])=={by['kl080_namespace'][0]['database']}
legacy=by['kl080_mechanical_s37_legacy_consumer_denial'][0]
assert legacy['before']==legacy['after'] and legacy['first_use_head_observed_then_rolled_back']
assert legacy['actual_cause']=='policy, demand, and calendar authorization bounds must exist'
trajectory=by['kl080_owner_trajectory'][0];assert trajectory['full']
for table,field in [('authorization_issuances','scope'),('execution_bindings','execution_scope')]:
 rows=trajectory['persisted'][table]
 # Inspect execution scope directly where represented; issuances use action_scope.
 if table=='execution_bindings': assert rows and all(r[0][field]=='TEST_ONLY' for r in rows)
for table in ['admission_decisions','event_association_decisions']:
 assert trajectory['persisted'][table]
out['witnesses']={'counts':dict(collections.Counter(x['kind'] for x in w)),'prior_runtime_helper_blob_count':len(prior['verified_blobs']),'prior_revision':prior['protected_revision'],'prior_blobs_identical_at_protected_base':True,'prior_guard':prior['reached'],'mechanical_guard':legacy['actual_cause'],'mechanical_zero_effects':True,'test_binding_count':len(trajectory['persisted']['execution_bindings'])}
budget=ce.audit(ROOT,BASE,HEAD,'KL-080');out['budget']=budget;assert not budget['errors'],budget
out['status']='PASS'
Path(__file__).with_name('verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
