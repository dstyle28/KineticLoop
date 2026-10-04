from pathlib import Path
import subprocess,json,hashlib,sys,xml.etree.ElementTree as ET,collections,os
import yaml,jsonschema
R=Path.cwd();sys.path.insert(0,str(R/'tools/harness'));import compact_evidence as ce
H='417b65ee68244dc86ab02add231b24dc662be790';B='1d3075151246b2774640a3d7acec836f47ab2b8d';T='feb3236c175df171611fc5b7ddb4f6eeca3ce47c'
E='docs/exec-plans/evidence/KL-080/HG051-'+T+'/'
def git(*a):return subprocess.check_output(['git',*a],cwd=R)
def blob(p,r=H):return git('show',r+':'+p)
def obj(p,r=H):return json.loads(blob(p,r))
def sha(b):return hashlib.sha256(b).hexdigest()
def anc(a,b):assert subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=R).returncode==0
S={'reviewed_head_sha':H,'base_commit':B,'tested_commit':T};anc(B,T);anc(T,H)
result=yaml.safe_load(blob('docs/exec-plans/completed/KL-080_RESULT.yaml'));jsonschema.validate(result,obj('THREAD_RESULT.schema.json'))
assert result['base_commit']==B and result['tested_commit']==T
assert result['task_status']==result['task_checks_status']=='PASS'
assert result['integration_status']=='UNMERGED' and result['merge_commit'] is None and result['requirements_covered']==[]
task=next(t for t in obj('KineticLoop_Harness_Backlog_v0.2.json')['tasks'] if t['id']=='KL-080')
checks=obj(E+'final-checks.json')['executions'];assert len(checks)==len(task['check_contracts'])==len(result['commands_run'])==17
byid={r['check_id']:r for r in checks};assert len(byid)==17
counts={};decoded={}
for c in task['check_contracts']:
 r=byid[c['check_id']];assert r['command']==c['command'] and r['tested_commit']==T and r['result']=='PASS' and r['exit_code']==0
 assert next(x for x in result['commands_run'] if x['check_id']==c['check_id'])['command']==c['command']
 for v in r.values():
  if isinstance(v,dict) and 'path' in v:
   assert sha(blob(v['path']))==v['sha256'];raw=ce.read(R,v['path'],H,tested=T,exit_code=0)
   assert sha(raw)==v['raw_sha256'] and len(raw)==v['raw_bytes'];decoded[v['path']]=raw
 raw=ce.read(R,r['stdout']['path'],H,tested=T,command=c['command'],exit_code=0)
 assert b'TESTED_COMMIT='+T.encode() in raw and b'COMMAND='+c['command'].encode() in raw and b'EXIT_CODE=0' in raw
 if 'junit' in r:
  xml=ET.fromstring(decoded[r['junit']['path']]);cases=xml.findall('.//testcase')
  a={'executed':len(cases),'failures':len(xml.findall('.//failure')),'errors':len(xml.findall('.//error')),'skipped':len(xml.findall('.//skipped'))}
  assert a==r['counts'] and a['executed']>0 and not any(a[k] for k in ['failures','errors','skipped']);counts[c['check_id']]=a
  if 'collection.json' in r:
   collect=json.loads(decoded[r['collection.json']['path']]);assert collect['tested_commit']==T and collect['exit_code']==0
   nodes=collect['nodeids'];assert len(nodes)==len(set(nodes))==len(cases)
   expect=[n.replace('.py::','::').replace('/','.').replace('::','.',1) for n in nodes]
   assert set(expect)=={x.attrib['classname']+'.'+x.attrib['name'] for x in cases}
S['named_execution_counts']=counts
for p in git('ls-tree','-r','--name-only',H,'--',E).decode().splitlines():
 if p.endswith('.capture.json'):decoded[p]=ce.read(R,p,H,tested=T,exit_code=0)
S['decoded_capture_count']=len(decoded)
suffix=git('diff','--name-only',T,H).decode().splitlines();assert all(p=='docs/exec-plans/completed/KL-080_RESULT.yaml' or p.startswith('docs/exec-plans/evidence/KL-080/') for p in suffix);S['tested_suffix_paths']=len(suffix)
m=obj('docs/exec-plans/evidence/KL-080/HISTORICAL_EVIDENCE_MAPPING.json');jsonschema.validate(m,obj('HISTORICAL_EVIDENCE_MAPPING.schema.json'))
assert m['historical_outcome']['task_status']=='BLOCKED' and m['historical_outcome']['task_checks_status']=='FAIL'
originals=[]
for e in m['entries']:
 o,s=e['original'],e['storage'];raw=blob(o['path'],o['revision']);anc(o['revision'],s['revision']);anc(s['revision'],T)
 assert git('rev-parse',o['revision']+':'+o['path']).decode().strip()==o['blob_id']
 assert sha(raw)==o['raw_sha256'] and len(raw)==o['raw_bytes'] and ce.read_archive(R,o['path'],T)==raw
 try:ce.read(R,o['path'],H)
 except ValueError:pass
 else:raise AssertionError('archive accepted as ordinary evidence')
 originals.append({'path':o['path'],'raw_bytes':len(raw),'raw_sha256':sha(raw),'exit_code':o['execution']['exit_code'],'result':o['execution']['result']})
S['verified_archival_originals']=originals
for rec in m['preserved_records']:
 raw=blob(rec['path'],rec['revision']);assert len(raw)==rec['bytes'] and sha(raw)==rec['sha256'];anc(rec['revision'],H)
audit=ce.audit(R,B,H,'KL-080');S['full_storage_audit']=audit;assert not audit['errors'],audit
before=git('rev-parse',m['entries'][0]['storage']['revision']+'^').decode().strip()
old=git('ls-tree','-r','--name-only',before,'--','docs/exec-plans/evidence/KL-080').decode().splitlines()
changed=[p for p in old if blob(p,before)!=blob(p)];assert set(changed)=={e['original']['path'] for e in m['entries']}
S['nonmigrated_historical_evidence_unchanged']=len(old)-len(changed)
protected=['CURRENT_DOCUMENT_INDEX.json','CURRENT_REQUIREMENT_SET.json','FROZEN_BASELINE.json','KineticLoop_Acceptance_Spec_v1.2.2.json','KineticLoop_Integration_Acceptance_v0.1.json']+[d['path'] for d in obj('CURRENT_DOCUMENT_INDEX.json')['documents']]
for p in protected:assert blob(p,B)==blob(p)
assert not git('diff',B,H,'--','.github','migrations','alembic');S['protected_authorities_unchanged']=len(set(protected))
v=obj('docs/exec-plans/evidence/KL-080/HG051-hosted-index-correction/hosted-db-verification.json')
S['unavailable_hosted_references']=[]
for key,i in v['raw_artifacts'].items():
 if not git('ls-tree',H,'--',i['path']).strip():
  S['unavailable_hosted_references'].append({'key':key,**i});continue
 assert sha(blob(i['path']))==i['sha256'];raw=ce.read(R,i['path'],H,tested=T,exit_code=0);assert sha(raw)==i['raw_sha256'] and len(raw)==i['raw_bytes']
x=ET.fromstring(decoded[E+'hosted.database.xml.capture.json']);assert len(x.findall('.//testcase'))==780 and not x.findall('.//failure') and not x.findall('.//error') and not x.findall('.//skipped')
S['hosted_manifest']=json.loads(decoded[E+'hosted.manifest.json.capture.json']);S['hosted_testcases']=780
w=[json.loads(l.split('SOURCE_EVIDENCE ',1)[1]) for l in decoded[E+'source_suite_dc.stdout.capture.json'].decode().splitlines() if 'SOURCE_EVIDENCE ' in l]
k=collections.Counter(x['kind'] for x in w);assert k['kl080_namespace']==k['kl080_cleanup']==106
for r in w:
 if r['kind']=='kl080_namespace':
  d=sha(os.fsencode(R.resolve()))[:12];assert r['tested_commit']==T and r['compose']=='kineticloop-kl080-source-'+T[:7]+'-'+d and r['database']=='kineticloop_kl080_source_'+T[:7]+'_'+d
 if r['kind']=='kl080_cleanup':assert not any(r['remaining'].values())
for name in ['kl080_canonical_full_t6_exact_freshness_reached','kl080_prior_deployment_earlier_denial','kl080_mechanical_s37_legacy_consumer_denial','kl080_owner_trajectory']:assert k[name]>=1
S['witness_counts']=dict(sorted(k.items()));S['status']='CHANGES_REQUIRED' if S['unavailable_hosted_references'] else 'PASS'
Path(__file__).with_name('verification.json').write_text(json.dumps(S,indent=2)+'\n')
print(json.dumps({k:v for k,v in S.items() if k!='hosted_manifest'},indent=2))
