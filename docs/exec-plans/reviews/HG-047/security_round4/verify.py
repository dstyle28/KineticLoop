"""Independent round-four exact-Git security/evidence audit; no execution authority."""
import ast, collections, hashlib, importlib.util, json, re, subprocess, sys
import xml.etree.ElementTree as ET
from pathlib import Path
import yaml
R=Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
O=Path(__file__).resolve().parent
H='b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91'; B='d08927706a01a397dac2c78ca4aec7e9918a389c'; T='7b35dc5dd7c488b60651175574e37b5d9389d335'
def g(*args): return subprocess.check_output(['git',*args],cwd=R)
def blob(rev,path): return g('show',rev+':'+path)
def sha(data): return hashlib.sha256(data).hexdigest()
def mod(n):
 s=importlib.util.spec_from_file_location(n,R/'tools/harness'/(n+'.py')); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
ce=mod('compact_evidence'); v=mod('validate_harness'); gate=mod('local_gate')
assert g('rev-parse','HEAD').decode().strip()==H
assert not v.governance_suffix_errors(R,T,H,'HG-047','tested')
paths=g('diff','--name-only',B,H).decode().splitlines()
assert all(v.matches(p,v.governance_allowed_patterns('HG-047')) for p in paths)
source=[p for p in paths if not p.startswith('docs/exec-plans/')]
assert not g('diff','--name-only',T,H,'--',*source)
protected=['src','migrations','tests/db','.github','CURRENT_REQUIREMENT_SET.json','FROZEN_BASELINE.json','tools/harness/db_policy.py','tools/harness/db_ci.py','tools/harness/github_app.py','tools/harness/gate_pytest.py','tools/harness/gate_validate.py','tools/harness/db_ci_pytest.py','tools/harness/local_db']
protected += [e['path'] for e in json.loads(blob(B,'FROZEN_BASELINE.json'))['files']]
for i in ['HG-045','HG-046','HG-048']:
 protected += ['docs/exec-plans/governance/'+i+'.yaml','docs/exec-plans/evidence/'+i,'docs/exec-plans/reviews/'+i]
assert not g('diff','--name-only',B,H,'--',*protected)
old='d67ed45f2f634d39c2b9abd9a93d55da3b48ab50'; common='391c9198fa8ec647e377a0572700bc7568468c85'
shared={'CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','tools/harness/README.md','tools/harness/validate_harness.py'}
newpaths=set(g('diff','--name-only',common,B).decode().splitlines())-shared
for p in newpaths: assert blob(H,p)==blob(B,p),p
oldpaths=set(g('diff','--name-only',common,old).decode().splitlines())-(shared|{'docs/exec-plans/governance/HG-047.yaml','docs/exec-plans/evidence/HG-047/audit.py','docs/exec-plans/evidence/HG-047/SCOPE.md'})
for p in oldpaths: assert blob(H,p)==blob(old,p),p
p='tools/harness/validate_harness.py'; before=blob(old,p); base=blob(B,p); section=base[base.index(b"    if change_id == 'HG-048':"):base.index(b"    if change_id == 'HG-046':")]
assert blob(H,p)==before.replace(b"    if change_id == 'HG-046':",section+b"    if change_id == 'HG-046':",1)
p='tools/harness/README.md'; assert blob(H,p)==blob(old,p)+blob(B,p)[len(blob(common,p)):].lstrip(b'\n')
for fn,groups in [('CURRENT_DOCUMENT_INDEX.json',['documents','machine_readable']),('HARNESS_DOCUMENT_MANIFEST.json',['files'])]:
 data=json.loads(blob(H,fn))
 for group in groups:
  for e in data[group]:
   actual=blob(H,e['path']); assert sha(actual)==e['sha256'],e['path']
   if 'bytes' in e: assert len(actual)==e['bytes']
budget=ce.audit(R,B,H,'HG-047'); assert not budget['errors']
envs=[]
for p in paths:
 if p.startswith('docs/exec-plans/evidence/HG-047/') and p.endswith('.json'):
  manifest=ce.envelope(blob(H,p))
  if manifest is not None:
   raw=ce.read(R,p,H); assert sha(raw)==manifest['raw_sha256']; envs.append({'ref':p,'raw_sha256':sha(raw),'raw_bytes':len(raw)})
record=yaml.safe_load(blob(H,'docs/exec-plans/governance/HG-047.yaml')); assert (record['base_commit'],record['tested_commit'])==(B,T)
checks=[]
for c in record['checks_run']:
 raw=ce.read(R,c['evidence_ref'],H,tested=T,command=c['command'],exit_code=0); checks.append({'id':c['check_id'],'sha256':sha(raw),'bytes':len(raw)})
prefix='docs/exec-plans/evidence/HG-047/round4-7b35dc5/'
run=json.loads(blob(H,prefix+'execution.json'))
raws={k:ce.read(R,p,H,tested=T) for k,p in run['artifact_refs'].items()}
w=json.loads(raws['worker-receipt.json']); initial=json.loads(raws['development-initial-recovered.json']); final=json.loads(raws['development.json'])
assert initial['status']=='RUNNING' and final['status']=='PASS'
assert all(final[k]==val for k,val in initial.items() if k!='status')
assert set(final)-set(initial)=={'image_environment','counts','duration_seconds_monotonic','finished_at'}
assert final['mode']=='DEVELOPMENT_NO_PUBLICATION' and final['test_only'] and not final['full_db']
assert all(final[k] is False for k in ('publication','admission_read','signer_config_read','app_object_created'))
assert (w['base'],w['head'],w['status'])==(B,T,'PASS') and not w['full_database_required']
assert w['container_removed'] and w['volume_removed'] and w['volume']==w['container']+'-data'
assert w['mounts']==[{'Destination':'/var/lib/docker','Name':w['volume'],'Type':'volume'}]
assert final['image_environment']['Os']=='linux' and final['image_environment']['Architecture']=='arm64'
assert w['image']==final['image_environment']['Id'] and run['image_environment']==final['image_environment']
for name,h in w['artifacts'].items(): assert sha(raws['development-initial-recovered.json' if name=='development.json' else name])==h,name
assert set(final['controller_files'])==set(gate.ASSETS) and len(gate.ASSETS)==11
asset_differences=[]
for name,h in final['controller_files'].items():
 assert sha(blob(final['installed_reviewed_revision'],'tools/harness/'+name))==h
 if sha(blob(T,'tools/harness/'+name))!=h: asset_differences.append(name)
assert asset_differences==['validate_harness.py']
assert sha(json.dumps(final['controller_files'],sort_keys=True).encode())==final['controller']
assert final['command_plan']==[[n,a] for n,a in gate.gate_plan(B,T,False,True)]
for c in w['checks']:
 assert c['exit_code']==0 and not c['interrupted']; raw=raws[c['stdout']['path']]; assert len(raw)==c['stdout']['bytes'] and sha(raw)==c['stdout']['sha256']
for name,argv in final['command_plan']:
 c=next(c for c in w['checks'] if c['check_id']==name); assert c['argv'][-len(argv):]==argv
for c in record['checks_run']:
 name='merge_gate' if c['check_id']=='installed_authority' else c['check_id']
 if name in [x['check_id'] for x in w['checks']]: assert c['command']==' '.join(next(x['argv'] for x in w['checks'] if x['check_id']==name))
host=json.loads(raws['host/checks.json'])
for name,c in host['records'].items():
 raw=raws['host/'+name+'.log']; assert c['exit_code']==0 and len(raw)==c['bytes'] and sha(raw)==c['sha256']
counts={}; junit={}
for label,count in [('harness',1324),('unit',241)]:
 tree=ET.fromstring(raws['worker/'+label+'.xml']); cases=list(tree.iter('testcase')); ids=[(x.get('classname'),x.get('name')) for x in cases]
 assert len(ids)==len(set(ids))==count
 assert not any(list(c.iter(tag)) for c in cases for tag in ('error','failure','skipped'))
 assert sum(int(x.attrib['tests']) for x in tree.iter('testsuite'))==count
 assert all(int(x.attrib[k])==0 for x in tree.iter('testsuite') for k in ('errors','failures','skipped'))
 assert str(count)+' passed' in raws[label+'.log'].decode(); junit[label]=ids
 counts[label]={'tests':count,'failures':0,'errors':0,'skipped':0}; assert final['counts'][label]==counts[label]
observer=json.loads(raws['worker/run/execution.json']); nodes=observer['nodeids']; assert observer['exit_code']==0 and len(nodes)==len(set(nodes))==1324
collected=re.findall(r'^tests/[^\n]+::[^\n]+$',raws['host/collection.log'].decode(),re.M); assert collected==nodes
expected=[]
for n in nodes:
 stem,sep,params=n.partition('['); parts=stem.split('::'); expected.append((parts[0][:-3].replace('/','.')+('.'+'.'.join(parts[1:-1]) if len(parts)>2 else ''),parts[-1]+sep+params))
assert collections.Counter(expected)==collections.Counter(junit['harness'])
old_prefix='docs/exec-plans/evidence/HG-047/development-8a78241/'
failed=json.loads(ce.read(R,old_prefix+'worker-receipt-json.json',H)); app=json.loads(ce.read(R,old_prefix+'published-check-json.json',H)); cases=list(ET.fromstring(ce.read(R,old_prefix+'worker--harness-xml.json',H)).iter('testcase'))
assert failed['status']=='FAIL' and failed['container_removed'] and failed['volume_removed']
assert app['conclusion']=='failure' and app['head_sha']==failed['head'] and len(cases)==1306 and sum(bool(list(c.iter('error'))) for c in cases)==2
assert yaml.safe_load(blob(T,'docs/exec-plans/governance/HG-047.yaml'))['change_status']=='BLOCKED'
probes=[]
for enc in ['utf-8','utf-16','utf-16-le','utf-16-be','utf-32','utf-32-le','utf-32-be']:
 for text in [json.dumps([{ce.MARKER: ce.FORMAT}], separators=(',', ':')),
              json.dumps({'outer': dict(payload='missing', stored_sha256='a', raw_sha256='b')}, separators=(',', ':')),
              json.dumps({'outer': {ce.MARKER: ce.FORMAT}}, separators=(',', ':')).replace(ce.MARKER, chr(92) + 'u006b' + ce.MARKER[1:])]:
  try: ce.envelope(text.encode(enc)); raise AssertionError((enc,text))
  except ValueError as ex: probes.append({'encoding':enc,'kind':'wrapped_storage','rejected':str(ex)})
for text in ['{"event":"a","x":1,"x":2}','{"event":"\\u0061","x":1,"x":2}']:
 try: result=ce.envelope(text.encode()); outcome='plain' if result is None else 'envelope'
 except ValueError as ex: outcome=str(ex)
 probes.append({'sample':text,'observed':outcome,'classification':'NONBLOCKING ordinary JSON compatibility; failclosed'})
assert probes[-2]['observed']=='plain' and probes[-1]['observed']=='evidence-duplicate-key'
proof={'reviewed_head_sha':H,'base_commit':B,'tested_commit':T,'status':'PASS','changed_paths':paths,'source_matches_tested':True,'scope_valid':True,'protected_paths_unchanged':protected,'hg048_preserved_files':len(newpaths),'hg047_preserved_files':len(oldpaths),'full_shared_validator_and_readme_reconstruction':True,'all_index_manifest_hashes_valid':True,'budget':budget,'envelopes':envs,'selected_checks':checks,'linux_development':{'counts':counts,'receipt_artifacts_verified':len(w['artifacts']),'receipt_checks_verified':len(w['checks']),'host_records_verified':len(host['records']),'collection_observer_order_equal':True,'junit_identity_multiset_equal':True,'controller_assets_verified':len(gate.ASSETS),'installed_candidate_asset_differences':asset_differences,'initial_metadata_hash_verified':True,'final_metadata_preserved':True,'recorded_cleanup':True,'publication':False,'full_db':'NOT_RUN'},'failed_app_gate_preserved':{'head':failed['head'],'passed':1304,'errors':2,'conclusion':'failure'},'probes':probes}
(O/'verification.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:val for k,val in proof.items() if k not in ('changed_paths','protected_paths_unchanged','envelopes','probes')},indent=2))
