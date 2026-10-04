"""Independent read-only protocol evidence checks at immutable KL080 review revision."""
import collections, datetime, hashlib, json, pathlib, re, subprocess, sys, zlib
import xml.etree.ElementTree as ET
import yaml
ROOT=pathlib.Path('/Users/davetian/.codex/worktrees/59e4/KineticLoop')
HEAD='417b65ee68244dc86ab02add231b24dc662be790'
BASE='1d3075151246b2774640a3d7acec836f47ab2b8d'
TESTED='feb3236c175df171611fc5b7ddb4f6eeca3ce47c'
PREFIX='docs/exec-plans/evidence/KL-080/HG051-'+TESTED+'/'
OUT=pathlib.Path(__file__).parent
report={'reviewed_head_sha':HEAD,'base_commit':BASE,'tested_commit':TESTED,'probe_scope':'Read-only Git-bound evidence and protocol checks; no suites, DB lifecycle or controller execution.'}
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(p,rev=HEAD):
 entry=git('ls-tree',rev,'--',p).decode().strip().split()
 assert entry[0]=='100644' and entry[1]=='blob' and entry[3]==p, (rev,p)
 return git('show',rev+':'+p)
def sha(b): return hashlib.sha256(b).hexdigest()
def ancestor(a,b): subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=ROOT,check=True)
cache={}
def decode(p):
 if p in cache:return cache[p]
 e=json.loads(blob(p));assert e['kineticloop_evidence']=='gzip-v1'
 assert e['tested_commit']==TESTED
 payload=blob(e['payload']);assert len(payload)==e['stored_bytes'] and sha(payload)==e['stored_sha256']
 assert pathlib.PurePosixPath(p).parent==pathlib.PurePosixPath(e['payload']).parent
 d=zlib.decompressobj(31); raw=d.decompress(payload,64*1024*1024+1)+d.flush()
 assert d.eof and not d.unused_data and not d.unconsumed_tail
 assert len(raw)==e['raw_bytes'] and sha(raw)==e['raw_sha256']
 cache[p]=raw;return raw
ancestor(BASE,TESTED);ancestor(TESTED,HEAD)
packet=blob('docs/exec-plans/active/KL-080.md').decode()
contracts=json.loads(re.search(r'```json\n(.*?)\n```',packet,re.S).group(1))['check_contracts']
result=yaml.safe_load(blob('docs/exec-plans/completed/KL-080_RESULT.yaml'))
assert result['tested_commit']==TESTED and result['base_commit']==BASE
assert result['requirements_covered']==[] and result['integration_status']=='UNMERGED'
checks=json.loads(blob(PREFIX+'final-checks.json'))['executions']
assert len(checks)==len(contracts)==len(result['commands_run'])==17
report['commands']=[]
for c,e,r in zip(contracts,checks,result['commands_run']):
 assert c['check_id']==e['check_id']==r['check_id'] and c['command']==e['command']==r['command']
 assert e['tested_commit']==TESTED and e['exit_code']==0 and e['result']==r['result']=='PASS'
 raw=decode(e['stdout']['path']); env=json.loads(blob(e['stdout']['path']))
 assert env['command']==c['command'] and env['exit_code']==0
 assert sha(blob(e['stdout']['path']))==e['stdout']['sha256']
 for key,v in e.items():
  if isinstance(v,dict) and 'path' in v:
   assert sha(blob(v['path']))==v['sha256'];decode(v['path'])
 row={'check_id':c['check_id'],'command':c['command'],'raw_sha256':sha(raw)}
 if 'junit' in e:
  x=ET.fromstring(decode(e['junit']['path']));cases=x.findall('.//testcase');assert cases
  assert not x.findall('.//failure') and not x.findall('.//error') and not x.findall('.//skipped')
  assert len(cases)==e['counts']['executed'];row['executed']=len(cases)
  assert re.search(rb'\b'+str(len(cases)).encode()+rb' passed\b',raw)
  if 'collection.json' in e:
   col=json.loads(decode(e['collection.json']['path']));assert col['tested_commit']==TESTED and col['exit_code']==0
   nodes=col['nodeids'];assert len(nodes)==len(set(nodes))==len(cases)
   assert sorted(n.split('::',1)[1] for n in nodes)==sorted(c.attrib['name'] for c in cases)
 if c['check_id']=='harness_validation_passes':assert b'HARNESS_CHECK_PASS' in raw
 report['commands'].append(row)
# All current evidence envelopes in this execution directory must decode at review SHA.
paths=git('ls-tree','-r','--name-only',HEAD,'--',PREFIX).decode().splitlines()
for p in paths:
 if p.endswith('.capture.json'):decode(p)
report['verified_execution_envelopes']=len(cache)
# Frozen authorities and production/product/CI surfaces remain identical to protected base.
fixed=['CURRENT_DOCUMENT_INDEX.json','CURRENT_REQUIREMENT_SET.json','FROZEN_BASELINE.json','05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md']
for p in fixed:assert blob(p)==blob(p,BASE)
changed=git('diff','--name-only',BASE,HEAD).decode().splitlines()
impl=[p for p in changed if p.startswith(('src/','tests/','docs/contracts/'))]
assert len(impl)==19
assert not any(p.startswith(('.github/','migrations/')) for p in changed)
assert not git('diff','--name-only',TESTED,HEAD,'--','src','tests','docs/contracts')
report['implementation_paths']=impl;report['frozen_unchanged']=fixed
# Recursive prerequisite result/integration ancestry from existing entry record.
entry=json.loads(blob(PREFIX+'entry.json')); prereqs=[]
for p in entry['prerequisites']:
 task=p['task_identity'].split('/')[-1]
 integration=json.loads(blob('docs/exec-plans/integrations/'+task+'.json',BASE))
 assert integration['merge_commit']==p['merge_commit'];ancestor(p['merge_commit'],BASE)
 r=yaml.safe_load(blob('docs/exec-plans/completed/'+task+'_RESULT.yaml',BASE));assert r['task_status']=='PASS'
 assert sha(blob('docs/exec-plans/completed/'+task+'_RESULT.yaml',p['reviewed_head_sha']))==p['result_sha256']
 prereqs.append(task)
report['prerequisites_in_normal_base_ancestry']=prereqs
# Parse actual raw owner rows, rather than trusting the witness index.
raw=decode(PREFIX+'source_suite_dc.stdout.capture.json').decode()
w=[json.loads(l.split('SOURCE_EVIDENCE ',1)[1]) for l in raw.splitlines() if 'SOURCE_EVIDENCE ' in l]
by=collections.defaultdict(list)
for x in w:by[x['kind']].append(x)
report['witness_counts']={k:len(v) for k,v in by.items()}
assert len(by['kl080_namespace'])==len(by['kl080_cleanup'])==106
for x in by['kl080_namespace']:
 assert x['tested_commit']==TESTED and 'feb3236' in x['database'] and x['migration']=='e8c2f1a6b904'
for x in by['kl080_cleanup']:assert not any(x['remaining'].values())
def rows(s,t):return [x[0] for x in s[t]]
def canonical(s):
 assert all(x['decision']=='ELIGIBLE' for x in rows(s,'admission_decisions'))
 assert all(x['association_state']=='MATCHED' for x in rows(s,'event_association_decisions'))
 assert all(x['command_authority']=='NONE' for x in rows(s,'evidence_revisions'))
 assert all(x['typed_payload']['event_association_status']=='CONFIRMED' for x in rows(s,'evidence_resolutions'))
for x in by['kl080_preparation_owner']:
 s=x['persisted'];canonical(s)
 assert rows(s,'planning_attempts')[0]['status']=='COMMIT_READY'
 assert len(rows(s,'evidence_resolutions'))==(2 if x['full'] else 1)
 assert not rows(s,'authorization_issuances') and not rows(s,'execution_bindings')
x=by['kl080_canonical_full_t6_exact_freshness_reached'][0];s=x['persisted'];canonical(s)
a=rows(s,'admission_decisions')[0];assert x['reached'] and all(v[1]==a['id'] and v[3] for v in x['reached'])
assert len(rows(s,'authorization_issuances'))==2
for arow in rows(s,'authorization_issuances'):
 deps=arow['validity_certificate']['dependencies'];src=[d for d in deps if d['dependency_kind']=='EVIDENCE_ADMISSION_FRESHNESS']
 assert len(src)==1 and src[0]['identity']==a['id'] and src[0]['revision']==a['revision']
 assert datetime.datetime.fromisoformat(arow['valid_until'])==min(datetime.datetime.fromisoformat(d['valid_until']) for d in deps if d.get('valid_until'))
x=by['kl080_prior_deployment_earlier_denial'][0]
assert x['reached']==['_progress_sources -> _verify_full_progress'] and x['no_later_freshness_claim']
assert rows(x['immutable_rows'],'admission_decisions')[0]['decision']=='ADMITTED'
assert rows(x['immutable_rows'],'event_association_decisions')[0]['association_state']=='CONFIRMED'
assert rows(x['immutable_rows'],'planning_attempts')[0]['status']=='COMMIT_READY'
assert not rows(x['immutable_rows'],'authorization_issuances')
ancestor(x['protected_revision'],BASE)
for p,h in x['verified_blobs'].items():assert sha(blob(p,x['protected_revision']))==h
report['prior_deployment_verified_blobs']=len(x['verified_blobs'])
for x in by['kl080_exact_predicate_support_only']:
 assert x['end_to_end_claim'] is False and x['wrong_subject_policy_id_denied']
 assert bool(x['exact'])==(x['decision']=='ELIGIBLE')
x=by['kl080_mechanical_s37_legacy_consumer_denial'][0]
assert x['before']==x['after'] and x['first_use_head_observed_then_rolled_back']
assert x['no_construction_or_ingress_error'] and x['no_later_certificate_guard_claim']
assert x['actual_cause']=='policy, demand, and calendar authorization bounds must exist'
assert not rows(x['after'],'daily_plan_heads')
for g in ['require_test_execution_ingress','require_current_fence','lock_daily_head']:
 assert any(t['guard']==g and t['status']=='PASSED' and t['command']=='CommitBundle' for t in x['guard_trace'])
report['mechanical_reached_guard']=x['reached'][0]['guard'];report['mechanical_cause']=x['actual_cause']
x=by['kl080_owner_trajectory'][0];s=x['persisted'];canonical(s)
assert {m['action_type'] for m in x['result']['members']}=={'TRAINING','NUTRITION'}
bindings=rows(s,'execution_bindings');assert len(bindings)==4
assert collections.Counter(b['binding_kind'] for b in bindings)=={'START':2,'RESUME':2}
for m in x['result']['members']:
 b=[b for b in bindings if b['ref_s40_id']==m['prescription_id'] and b['ref_s42_id']==m['authorization_id']]
 assert len(b)==2 and all(v['execution_scope']=='TEST_ONLY' for v in b)
trace=x['guard_trace'];report['trajectory_guard_commands']=dict(collections.Counter(t['command'] for t in trace if t['guard']=='require_test_execution_ingress' and t['status']=='PASSED'))
assert by['F2_full_commit'][0]['immutable_prior'] and by['F2_full_commit'][0]['same_root_budget']
# Hosted fresh execution raw manifest and JUnit provenance.
manifest=json.loads(decode(PREFIX+'hosted.manifest.json.capture.json'))
report['hosted_manifest_keys']=list(manifest)
assert manifest['tested_commit']==TESTED and manifest['status']=='PASS'
assert manifest['provenance']['github_run_id']=='37161315464'
assert not manifest['remaining_containers'] and not manifest['remaining_volumes']
hosted_xml=ET.fromstring(decode(PREFIX+'hosted.database.xml.capture.json'))
assert len(hosted_xml.findall('.//testcase'))==780
assert not any(hosted_xml.findall('.//'+tag) for tag in ['failure','error','skipped'])
index_path='docs/exec-plans/evidence/KL-080/HG051-hosted-index-correction/hosted-db-verification.json'
index=json.loads(blob(index_path));assert index['tested_commit']==TESTED
for ref in index['raw_artifacts'].values():
 assert sha(blob(ref['path']))==ref['sha256'];raw=decode(ref['path']);assert sha(raw)==ref['raw_sha256'] and len(raw)==ref['raw_bytes']
for a in manifest['artifacts']:
 raw=decode(index['raw_artifacts'][a['path']]['path']);assert sha(raw)==a['sha256'] and len(raw)==a['bytes']
assert blob(PREFIX+'hosted-db-verification.json')==blob(PREFIX+'hosted-db-verification.json','5812ff2ca2c45bfe88c743e36656ea1921112ed6')
report['corrected_hosted_index']={'path':index_path,'verified_references':len(index['raw_artifacts']),'old_index_byte_identical':True}
for c in manifest['checks']:
 assert c['exit_code']==0
 if c.get('stdout'):
  raw=decode(PREFIX+'hosted.'+c['stdout']['path']+'.capture.json');assert sha(raw)==c['stdout']['sha256']
report['hosted_executed']=780
hcol=json.loads(decode(index['raw_artifacts']['collection.json']['path']));hexe=json.loads(decode(index['raw_artifacts']['execution.json']['path']))
assert hcol==hexe and hcol['exit_code']==0 and len(set(hcol['nodeids']))==780
assert sorted(n.split('::',1)[1] for n in hcol['nodeids'])==sorted(c.attrib['name'] for c in hosted_xml.findall('.//testcase'))
hcol=json.loads(decode(PREFIX+'harness.collection.json.capture.json'));hexe=json.loads(decode(PREFIX+'harness.execution.json.capture.json'))
nodes=next(iter(hcol['collections'].values()));assert len(set(nodes))==1492
assert set(hexe['started'])==set(nodes) and len(hexe['started'])==1492
assert all(set(v)==set(nodes) for v in hexe['collections'].values())
assert not hexe['errors'] and hexe['exit_code']==0
assert len(hexe['reports'])==1492*3 and all(r['outcome']=='passed' for r in hexe['reports'])
assert collections.Counter(r['nodeid'] for r in hexe['reports'] if r['phase']=='call')==collections.Counter(nodes)
report['harness_collection_execution_agree']=1492
# Lossless, pre-tested historical migration; archive status remains historical.
m=json.loads(blob('docs/exec-plans/evidence/KL-080/HISTORICAL_EVIDENCE_MAPPING.json'))
assert m['purpose']=='ARCHIVAL_RETRIEVAL_ONLY' and len(m['entries'])==4
assert m['historical_outcome']['task_checks_status']=='FAIL' and m['historical_outcome']['review_status']=='CHANGES_REQUIRED'
archive=[]
for e in m['entries']:
 o,t=e['original'],e['storage'];ancestor(o['revision'],t['revision']);ancestor(t['revision'],TESTED)
 original=blob(o['path'],o['revision']);assert sha(original)==o['raw_sha256'] and len(original)==o['raw_bytes']
 assert git('rev-parse',o['revision']+':'+o['path']).decode().strip()==o['blob_id']
 envelope=blob(t['envelope_path'],t['revision']);payload=blob(t['payload'],t['revision'])
 assert envelope==blob(t['envelope_path']) and payload==blob(t['payload'])
 assert sha(envelope)==t['envelope_sha256'] and sha(payload)==t['payload_sha256']
 d=zlib.decompressobj(31);raw=d.decompress(payload)+d.flush();assert d.eof and not d.unused_data and raw==original
 assert blob('docs/exec-plans/evidence/KL-080/HISTORICAL_EVIDENCE_MAPPING.json',TESTED)==blob('docs/exec-plans/evidence/KL-080/HISTORICAL_EVIDENCE_MAPPING.json')
 archive.append({'path':o['path'],'original_revision':o['revision'],'original_sha256':sha(original),'historical_result':o['execution']['result'],'storage_revision':t['revision']})
for r in m['preserved_records']:
 b=blob(r['path'],r['revision']);assert sha(b)==r['sha256'] and len(b)==r['bytes'];ancestor(r['revision'],TESTED)
report['verified_historical_representations']=archive
report['verified_execution_envelopes']=len(cache)
report['result']='PASS';report['repository_status']=git('status','--porcelain').decode()
assert not report['repository_status']
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'result':'PASS','commands':len(checks),'envelopes':len(cache),'witnesses':len(w),'hosted_cases':780,'output':str(OUT/'verification.json')}))
