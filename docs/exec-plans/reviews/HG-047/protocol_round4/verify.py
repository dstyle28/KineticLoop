"""Independent exact-blob protocol audit; no candidate decoder used for raw proof."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
import yaml
from _pytest.junitxml import mangle_test_address, bin_xml_escape
ROOT=Path(sys.argv[1]).resolve()
HEAD='b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91'
BASE='d08927706a01a397dac2c78ca4aec7e9918a389c'
TESTED='7b35dc5dd7c488b60651175574e37b5d9389d335'
OLD='d67ed45f2f634d39c2b9abd9a93d55da3b48ab50'
COMMON='391c9198fa8ec647e377a0572700bc7568468c85'
PREFIX='docs/exec-plans/evidence/HG-047/round4-7b35dc5/'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def sha(data):return hashlib.sha256(data).hexdigest()
def blob(rev,path):
 rows=[x for x in git('ls-tree','-z',rev,'--',path).split(b'\0') if x]
 assert len(rows)==1,(rev,path)
 info,p=rows[0].split(b'\t'); mode,kind,oid=info.split()
 assert p.decode()==path and mode in (b'100644',b'100755') and kind==b'blob'
 return git('cat-file','blob',oid.decode())
def decode(path,tested=TESTED,command=None,exit_code=0):
 m=json.loads(blob(HEAD,path));assert m['kineticloop_evidence']=='gzip-v1'
 assert m['tested_commit']==tested and type(m['exit_code']) is int and m['exit_code']==exit_code
 if command is not None:assert m['command']==command,(path,m['command'],command)
 assert m['payload']==str(Path(path).parent/(m['raw_sha256']+'.gz'))
 git('merge-base','--is-ancestor',tested,HEAD)
 stored=blob(HEAD,m['payload']);assert len(stored)==m['stored_bytes']<=8*1024**2 and sha(stored)==m['stored_sha256']
 assert 0<=m['raw_bytes']<=64*1024**2
 d=zlib.decompressobj(31);raw=d.decompress(stored,m['raw_bytes']+1)
 assert d.eof and not d.unused_data and not d.unconsumed_tail
 assert len(raw)==m['raw_bytes'] and sha(raw)==m['raw_sha256']
 return raw
raws={}
for p in git('ls-tree','-r','--name-only',HEAD,'--',PREFIX).decode().splitlines():
 if p.endswith('.json') and p!=PREFIX+'execution.json':raws[p]=decode(p)
assert len(raws)==28
summary=json.loads(blob(HEAD,PREFIX+'execution.json'))
receipt=json.loads(raws[PREFIX+'worker-receipt-json.json'])
record=yaml.safe_load(blob(HEAD,'docs/exec-plans/governance/HG-047.yaml'))
assert record['tested_commit']==TESTED and record['base_commit']==BASE and record['change_status']=='PASS'
checks={}
for check in record['checks_run']:
 assert check['result']=='PASS'
 if check['check_id']=='committed_evidence_integrity':continue
 raw=decode(check['evidence_ref'],command=check['command']);checks[check['check_id']]=sha(raw)
assert receipt['head']==TESTED and receipt['base']==BASE and receipt['status']=='PASS'
assert receipt['container_removed'] and receipt['volume_removed'] and receipt['full_database_required'] is False
for c in receipt['checks']:
 assert c['exit_code']==0 and not c['interrupted']
 raw=decode(summary['artifact_refs'][c['stdout']['path']],command=' '.join(c['argv']))
 assert len(raw)==c['stdout']['bytes'] and sha(raw)==c['stdout']['sha256']
for name,digest in receipt['artifacts'].items():
 path=summary['artifact_refs'][name if name!='development.json' else 'development-initial-recovered.json']
 assert sha(raws[path])==digest,(name,path)
initial=raws[PREFIX+'development-initial-recovered-json.json'];final=raws[PREFIX+'development-json.json']
initial_obj=json.loads(initial);final_obj=json.loads(final)
reconstructed=dict(final_obj)
for key in ('image_environment','counts','duration_seconds_monotonic','finished_at'):reconstructed.pop(key)
reconstructed['status']='RUNNING'
assert (json.dumps(reconstructed,indent=2)+'\n').encode()==initial
assert final_obj['status']=='PASS' and final_obj['mode']=='DEVELOPMENT_NO_PUBLICATION'
assert final_obj['tested_commit']==TESTED and final_obj['base_commit']==BASE
assert final_obj['test_only'] is True and final_obj['full_db'] is False
for key in ['app_object_created','signer_config_read','admission_read','publication']:assert final_obj[key] is False
for name,digest in final_obj['controller_files'].items():
 assert sha(blob(final_obj['installed_reviewed_revision'],'tools/harness/'+name))==digest,name
assert final_obj['image_environment']['Os']=='linux' and final_obj['image_environment']['Architecture']=='arm64'
counts={}
for suite,n in [('harness',1324),('unit',241)]:
 log=raws[PREFIX+suite+'-log.json'].decode()
 assert re.findall(r'\b([1-9][0-9]*) passed\b',log)==[str(n)]
 assert not re.search(r'\b[1-9][0-9]* (failed|errors?|skipped|deselected|xfailed|xpassed)\b',log)
 cases=list(ET.fromstring(raws[PREFIX+'worker--'+suite+'-xml.json']).iter('testcase'))
 ids=[(c.attrib['classname'],c.attrib['name']) for c in cases]
 assert len(cases)==len(set(ids))==n
 assert all(not list(c.iter(tag)) for c in cases for tag in ('failure','error','skipped'))
 counts[suite]={'tests':n,'failures':0,'errors':0,'skipped':0}
 if suite=='harness':harness_ids=ids
worker=json.loads(raws[PREFIX+'worker--run--execution-json.json'])
collection=raws[PREFIX+'host--collection-log.json'].decode()
nodeids=[x for x in collection.splitlines() if x.startswith('tests/') and '::' in x]
assert worker['exit_code']==0 and worker['nodeids']==nodeids
assert len(nodeids)==len(set(nodeids))==1324
assert re.findall(r'(?m)^([0-9]+) tests collected in ',collection)==['1324']
expected=[]
for node in nodeids:
 parts=mangle_test_address(node);expected.append(('.'.join(parts[:-1]),bin_xml_escape(parts[-1])))
assert Counter(expected)==Counter(harness_ids)
assert sha(json.dumps(nodeids).encode())==summary['identity']['collection_identity_sha256']
# Complete parent preservation; compare actual Git blob bytes rather than local dirty reviews.
shared={'CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','tools/harness/README.md','tools/harness/validate_harness.py'}
newpaths=set(git('diff','--name-only',COMMON,BASE).decode().splitlines())-shared
for path in newpaths:assert blob(BASE,path)==blob(HEAD,path),path
oldpaths=set(git('diff','--name-only',COMMON,OLD).decode().splitlines())-(shared|{'docs/exec-plans/governance/HG-047.yaml','docs/exec-plans/evidence/HG-047/audit.py','docs/exec-plans/evidence/HG-047/SCOPE.md'})
for path in oldpaths:assert blob(OLD,path)==blob(HEAD,path),path
path='tools/harness/validate_harness.py';before=blob(OLD,path);base=blob(BASE,path)
added=b"    if change_id == 'HG-048':"+base.split(b"    if change_id == 'HG-048':",1)[1].split(b"    if change_id == 'HG-046':",1)[0]
assert blob(HEAD,path)==before.replace(b"    if change_id == 'HG-046':",added+b"    if change_id == 'HG-046':",1)
path='tools/harness/README.md'
assert blob(HEAD,path)==blob(OLD,path)+blob(BASE,path)[len(blob(COMMON,path)):].lstrip(b'\n')
changed=git('diff','--name-only',BASE,HEAD).decode().splitlines()
for p in changed:
 if p.startswith(('tools/','tests/')):assert (ROOT/p).read_bytes()==blob(HEAD,p),p
assert not any(p.startswith(('src/','migrations/','tests/db/','.github/','docs/exec-plans/active/','docs/exec-plans/completed/','docs/exec-plans/integrations/','docs/exec-plans/milestones/')) for p in changed)
frozen=json.loads(blob(HEAD,'FROZEN_BASELINE.json'))
protected=['FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Acceptance_Spec_v1.2.2.json','KineticLoop_Integration_Acceptance_v0.1.json','tools/harness/db_policy.py']+[x['path'] for x in frozen['files']]
for p in protected:assert blob(HEAD,p)==blob(BASE,p),p
for x in frozen['files']:assert sha(blob(HEAD,x['path']))==x['sha256']
trees=[ast.parse(blob(rev,'tools/harness/validate_harness.py')) for rev in (BASE,HEAD)]
def constants(t):return {n.id:ast.dump(x.value) for x in t.body if isinstance(x,ast.Assign) for n in x.targets if isinstance(n,ast.Name) and n.id.startswith('M3_')}
assert constants(trees[0])==constants(trees[1])
unchanged=['m3_pytest_count','m3_layer_errors','m3_dependency_order_errors','m3_frozen_authority_errors','m3_milestone_closure_errors']
for name in unchanged:
 fs=[next(x for x in t.body if isinstance(x,ast.FunctionDef) and x.name==name) for t in trees]
 for f in fs:f.decorator_list=[]
 assert ast.dump(fs[0])==ast.dump(fs[1]),name
for file,groups in [('CURRENT_DOCUMENT_INDEX.json',['documents','machine_readable']),('HARNESS_DOCUMENT_MANIFEST.json',['files'])]:
 doc=json.loads(blob(HEAD,file))
 for group in groups:
  for x in doc[group]:
   data=blob(HEAD,x['path']);assert sha(data)==x['sha256'],x['path']
   if 'bytes' in x:assert len(data)==x['bytes']
commits=git('rev-list','--reverse',TESTED+'..'+HEAD).decode().splitlines()
previous=TESTED
for commit in commits:
 parents=git('rev-list','--parents','-n','1',commit).decode().split()[1:]
 assert parents==[previous],(commit,parents)
 paths=git('diff','--name-only',previous,commit).decode().splitlines()
 assert all(p=='docs/exec-plans/governance/HG-047.yaml' or p.startswith('docs/exec-plans/evidence/HG-047/') for p in paths)
 previous=commit
suffix=git('diff','--name-only',TESTED,HEAD).decode().splitlines()
assert all(p=='docs/exec-plans/governance/HG-047.yaml' or p.startswith('docs/exec-plans/evidence/HG-047/') for p in suffix)
failed=decode('docs/exec-plans/evidence/HG-047/development-8a78241/harness-log.json',tested=git('rev-parse','8a78241^{commit}').decode().strip(),exit_code=1).decode()
assert '1304 passed, 2 errors' in failed and ('Argument list too long' in failed or 'E2BIG' in failed)
print(json.dumps({'status':'PASS','reviewed_head_sha':HEAD,'base_commit':BASE,'tested_commit':TESTED,'raw_envelopes':{p:{'sha256':sha(r),'bytes':len(r)} for p,r in raws.items()},'checks':checks,'raw_suite_counts':counts,'harness_collection_observer_junit_exact_identity':True,'observer_records_session_items_not_phase_events':True,'initial_metadata_reconstruction_receipt_sha256':sha(initial),'final_metadata_preserved_sha256':sha(final),'installed_assets_verified_at_reviewed_release':len(final_obj['controller_files']),'container_and_volume_removed_in_receipt':True,'hg048_unchanged_files':len(newpaths),'hg047_unchanged_files':len(oldpaths),'complete_validator_exact_parent_composition':True,'complete_README_exact_parent_composition':True,'M3_constants_unchanged':sorted(constants(trees[1])),'M3_raw_oracle_functions_unchanged':unchanged,'frozen_and_runtime_and_requirement_preservation':True,'source_unchanged_after_tested':True,'tested_suffix_linear_per_commit':True,'focused_working_sources_equal_reviewed_blobs':True,'all_index_and_manifest_entries_valid':True,'prior_failed_E2BIG_run_retained_as_failure':True,'fullDB_finalApp':'NOT_RUN','M3_release_requirement_closure':'NOT_CLAIMED'},indent=2))
