import sys, pathlib, json, subprocess, hashlib, re, xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
ROOT=pathlib.Path('/Users/davetian/.codex/worktrees/59e4/KineticLoop')
sys.path.insert(0,str(ROOT/'tools/harness'))
import compact_evidence as c
H='417b65ee68244dc86ab02add231b24dc662be790'; T='feb3236c175df171611fc5b7ddb4f6eeca3ce47c'; B='1d3075151246b2774640a3d7acec836f47ab2b8d'
P='docs/exec-plans/evidence/KL-080/HG051-'+T+'/'
def git(*a): return subprocess.check_output(['git',*a],cwd=ROOT)
def obj(path,rev=H): return json.loads(git('show',rev+':'+path))
def raw(path,command=None): return c.read(ROOT,path,H,tested=T,command=command,exit_code=0)
def check(v,msg):
 if not v: raise AssertionError(msg)
report={'reviewed_head_sha':H,'tested_commit':T,'protected_base':B,'reviewer_db_lifecycles':0}
for rev in [B,T]: git('merge-base','--is-ancestor',rev,H)
check(not git('diff','--name-only',T,H,'--','src','tests','docs/contracts'),'tested code differs')
packet=git('show',H+':docs/exec-plans/active/KL-080.md').decode()
contracts=json.loads(re.search(r'```json\n(.*?)\n```',packet,re.S)[1])['check_contracts']
checks=obj(P+'final-checks.json')['executions'];check(len(checks)==len(contracts)==17,'17 checks')
report['task_checks']=[]
for e,contract in zip(checks,contracts):
 check((e['check_id'],e['command'],e['result'],e['tested_commit'],e['exit_code'])==(contract['check_id'],contract['command'],'PASS',T,0),'check contract')
 out=raw(e['stdout']['path'],e['command']);check(hashlib.sha256(git('show',H+':'+e['stdout']['path'])).hexdigest()==e['stdout']['sha256'],'outer hash')
 info={'check_id':e['check_id'],'exit_code':0,'raw_sha256':hashlib.sha256(out).hexdigest()}
 if 'junit' in e:
  xml=ET.fromstring(raw(e['junit']['path']));cases=xml.findall('.//testcase');check(len(cases)==e['counts']['executed']>0,'JUnit count');check(not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped'),'dispositions');info['cases']=len(cases)
 if 'collection.json' in e:
  col=json.loads(raw(e['collection.json']['path']));check(len(col['nodeids'])==info['cases'],'collection count')
 report['task_checks'].append(info)
stdout=raw(P+'source_suite_dc.stdout.capture.json').decode();w=[json.loads(l.split('SOURCE_EVIDENCE ',1)[1]) for l in stdout.splitlines() if 'SOURCE_EVIDENCE ' in l]
counts=dict(Counter(x['kind'] for x in w));report['source_witness_counts']=counts
check(counts['kl080_namespace']==counts['kl080_cleanup']==106,'lifecycle count')
index=obj(P+'witness-index.json')
for k,v in index['witness_index'].items(): check(counts[k]==v['count'],'witness index count')
for x in w:
 if x['kind']=='kl080_namespace':check(x['tested_commit']==T and x['database']==index['namespace']['database'] and x['compose']==index['namespace']['compose'],'namespace')
 if x['kind']=='kl080_cleanup':check(not any(x['remaining'].values()),'cleanup')
 if x['kind']=='kl080_trusted_clock_crossing':check(datetime.fromisoformat(x['observed'])>datetime.fromisoformat(x['bound']) and not x['equality_claim'],'expiry')
 if x['kind']=='observed_duplicate':check(x['blocker'][1] and 'user_decision_state' in x['blocker'][2] and 'FOR UPDATE' in x['blocker'][2],'actual PG block');check(x['replay']=={**x['original'],'replayed':True,'executable':False},'duplicate replay')
 if x['kind']=='kl080_mechanical_s37_legacy_consumer_denial':
  check(x['before']==x['after'] and not x['after']['daily_plan_heads'],'mechanical rollback');check(x['reached'][0]['first_use_head']['head_revision']==0,'native first head');check(x['actual_cause']=='policy, demand, and calendar authorization bounds must exist','actual consumer');check(x['no_later_certificate_guard_claim'],'consumer label')
 if x['kind']=='kl080_prior_deployment_earlier_denial':
  check(x['reached']==['_progress_sources -> _verify_full_progress'] and x['no_later_freshness_claim'],'earlier label')
  for path,sha in x['verified_blobs'].items():check(hashlib.sha256(git('show',x['protected_revision']+':'+path)).hexdigest()==sha,'historical runtime blob')
 if x['kind']=='kl080_exact_predicate_support_only':check(x['end_to_end_claim'] is False and bool(x['exact'])==(x['decision']=='ELIGIBLE'),'query support')
 if x['kind']=='F2_full_commit':check(x['same_root_budget'] and x['immutable_prior'],'F2 history')
 if x['kind']=='kl080_owner_trajectory':
  p=x['persisted'];check(len(p['authorization_issuances'])==2 and len(p['execution_bindings'])==4 and len(p['workout_sessions'])==2,'both member trajectories')
  check(all(row[0]['execution_scope']=='TEST_ONLY' for row in p['execution_bindings']),'isolated bindings')
report['semantic_witness_assertions']='PASS: native head rollback, prior-deployment exact blobs/earlier guard, separate query support, two PG blockers, F2 immutable history, two T7 members, expiry and own cleanup'
manifest=json.loads(raw(P+'hosted.manifest.json.capture.json'));check(manifest['tested_commit']==T and manifest['status']=='PASS','hosted identity')
index_path='docs/exec-plans/evidence/KL-080/HG051-hosted-index-correction/hosted-db-verification.json'
verification=obj(index_path);refs=verification['raw_artifacts']
check(len(refs)==15 and not any(k.startswith('hosted.') for k in refs),'15 canonical artifact keys')
verified_refs=[]
for name,ref in refs.items():
 outer=c.blob(ROOT,ref['path'],H)
 check(hashlib.sha256(outer).hexdigest()==ref['sha256'],'hosted outer hash: '+name)
 decoded=raw(ref['path'])
 check(len(decoded)==ref['raw_bytes'] and hashlib.sha256(decoded).hexdigest()==ref['raw_sha256'],'hosted index raw hash: '+name)
 verified_refs.append({'name':name,**ref})
report['hosted_index']={'path':index_path,'verified_canonical_refs':verified_refs}
old=verification['supersedes']
check(hashlib.sha256(git('show',old['revision']+':'+old['path'])).hexdigest()==old['sha256'],'superseded hash')
check(git('show',H+':'+old['path'])==git('show',old['revision']+':'+old['path']),'superseded bytes altered')
changed=git('diff','--name-only',old['revision'],H).decode().splitlines()
check(set(changed)=={'docs/exec-plans/completed/KL-080_RESULT.yaml',index_path,index_path.replace('hosted-db-verification.json','correct-index.py'),index_path.replace('hosted-db-verification.json','correction-validation.json')},'correction scope')
check(index_path in git('show',H+':docs/exec-plans/completed/KL-080_RESULT.yaml').decode(),'result must name authoritative index')
for rec in manifest['checks']:
 check(rec['exit_code']==0 and not rec['interrupted'],'hosted check')
 rr=raw(refs[rec['stdout']['path']]['path']);check(len(rr)==rec['stdout']['bytes'] and hashlib.sha256(rr).hexdigest()==rec['stdout']['sha256'],'hosted raw hash')
for rec in manifest['artifacts']:
 rr=raw(refs[rec['path']]['path']);check(len(rr)==rec['bytes'] and hashlib.sha256(rr).hexdigest()==rec['sha256'],'hosted artifact hash')
xml=ET.fromstring(raw(refs['database.xml']['path']));check(len(xml.findall('.//testcase'))==780 and not any(xml.findall('.//'+k) for k in ['failure','error','skipped']),'hosted cases')
col=json.loads(raw(refs['collection.json']['path']));exe=json.loads(raw(refs['execution.json']['path']));check(col==exe,'hosted actual collection/execution')
check(not manifest['remaining_containers'] and not manifest['remaining_volumes'],'hosted cleanup')
report['hosted']={'run_id':manifest['provenance']['github_run_id'],'tested_commit':T,'cases':780,'failures':0,'errors':0,'skipped':0,'manifest_hashes_verified':True,'cleanup_empty':True}
mapping=obj('docs/exec-plans/evidence/KL-080/HISTORICAL_EVIDENCE_MAPPING.json'); recovered=c.validate_archive(ROOT,mapping,H,verify_originals=True)
check(len(recovered)==4,'archive exact 4'); git('merge-base','--is-ancestor',mapping['entries'][0]['storage']['revision'],T)
for path in recovered:
 try: c.read(ROOT,path,H)
 except ValueError: pass
 else: raise AssertionError('archival proof accepted as execution')
report['archive']={'exact_objects':4,'original_bytes_and_record_bindings_verified':True,'ordinary_decoder_rejects_archives':True,'historical_outcome':mapping['historical_outcome']}
audit=c.audit(ROOT,B,H,'KL-080');check(not audit['errors'],'storage gate errors: '+str(audit['errors']));report['storage_audit']=audit
scope=[p for p in git('diff','--name-only',B,H,'--','src','tests','docs/contracts').decode().splitlines()]
allowed=re.findall(r'^- ((?:src/|tests/|docs/contracts/)[^\n]+)$',packet.split('Expected write paths:')[1].split('Environment requirements:')[0],re.M);check(set(scope)==set(allowed),'19 path scope');report['source_test_contract_paths']=scope
check(not git('diff','--name-only',B,H,'--','FROZEN_BASELINE.json','CURRENT_DOCUMENT_INDEX.json','CURRENT_REQUIREMENT_SET.json','.github','migrations'),'frozen/harness boundaries')
report['status']='PASS'
pathlib.Path('/private/tmp/kl080-db-hg051-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['storage_audit','task_checks','source_test_contract_paths']},indent=2))
