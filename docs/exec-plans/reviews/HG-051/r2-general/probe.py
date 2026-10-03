import copy, gzip, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
OUT=Path('/private/tmp/hg051-r2-general-work')
SOURCE='0557dbd8f2196df871af20c0982bdc2526f0ad6e'
BASE='b877db0edd2e4550d6ea81750656112fb7f2e223'
def git(root,*args):
 p=subprocess.run(['git',*args],cwd=root,capture_output=True)
 if p.returncode: raise ValueError(p.stderr.decode())
 return p.stdout

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
checks=[]
def check(name,fn):
 fn(); checks.append(name); print('PASS '+name,flush=True)
def reject(fn):
 try: fn()
 except (ValueError,OSError): return
 raise AssertionError('unexpected acceptance')
with tempfile.TemporaryDirectory(prefix='hg051-r2-general-fixture-',dir='/private/tmp') as work:
 root=Path(work); git(root,'init','-q'); git(root,'config','user.name','Independent reviewer'); git(root,'config','user.email','review@example.invalid')
 objects=git(ROOT,'rev-parse','--git-path','objects').decode().strip(); objects=str((ROOT/objects).resolve())
 (root/'.git/objects/info/alternates').write_text(objects+'\n')
 original_head='477b213f67429f571b60d5701f02892ab9c1cbbf'
 git(root,'update-ref','HEAD',original_head); git(root,'read-tree',original_head)
 installed=root/'gate/tools/harness'; installed.mkdir(parents=True)
 for asset in ('validate_harness.py','compact_evidence.py','db_ci_pytest.py','db_ci.py','gate_validate.py','gate_pytest.py'):
  (installed/asset).write_bytes(git(ROOT,'show',SOURCE+':tools/harness/'+asset))
 ce=load('independent_installed_ce',installed/'compact_evidence.py'); v=load('independent_installed_v',installed/'validate_harness.py')
 assert not (root/'gate'/ce.MAPPING_SCHEMA).exists()
 authority=git(ROOT,'show',SOURCE+':'+ce.MAPPING_SCHEMA)
 check('installed_decoder_embeds_exact_schema_without_adjacent_schema',lambda: None if ce.HISTORICAL_SCHEMA_BYTES==authority else (_ for _ in ()).throw(AssertionError()))
 originals=ce.historical_originals(); template=ce.historical_template(); inv=json.loads(git(ROOT,'show',SOURCE+':docs/exec-plans/evidence/HG-051/INVENTORY.json'))
 assert len(originals)==len(inv['overlimit'])==4
 assert template['historical_outcome']['task_status']=='BLOCKED' and template['historical_outcome']['review_status']=='CHANGES_REQUIRED'
 assert [o['execution']['exit_code'] for o in originals]==[0,1,0,1]
 assert all(o['execution']['timestamp'] is None for o in originals)
 check('exact_four_failed_outcomes_and_unknown_timestamps_preserved',lambda: None)
 measured=[]
 for o,inventory in zip(originals,inv['overlimit'],strict=True):
  raw=ce.archive_original(ROOT,o); assert ce.digest(raw)==inventory['raw_sha256'] and len(raw)==inventory['raw_bytes'] and o['blob_id']==inventory['git_blob']
  ref=o['execution_record']; data=ce.blob(ROOT,ref['path'],ref['revision']); assert ce.digest(data)==ref['sha256'] and len(data)==ref['bytes']
  known=json.loads(data)
  if 'executions' in known: known=next(x for x in known['executions'] if x['check_id']=='source_suite_dc')
  assert known['command']==o['execution']['command'] and known['exit_code']==o['execution']['exit_code'] and known['tested_commit']==o['execution']['tested_commit']
  manifest,stored=ce.archive_envelope(o,raw); assert len(stored)==inventory['gzip9_bytes']
  target=root/o['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(manifest,indent=2)+'\n'); (root/manifest['payload']).write_bytes(stored)
  git(root,'add','--',o['path'],manifest['payload']);measured.append(dict(path=o['path'],bytes=len(raw),sha256=ce.digest(raw),stored_bytes=len(stored),blob_id=o['blob_id']))
 for ref in template['preserved_records']:
  data=ce.blob(ROOT,ref['path'],ref['revision']);assert ce.digest(data)==ref['sha256'] and len(data)==ref['bytes']
 check('all_original_regular_git_identities_metadata_and_preserved_records_match',lambda: None)
 git(root,'commit','-qm','temporary forward storage');storage=git(root,'rev-parse','HEAD').decode().strip();mapping=ce.archive_mapping(root,storage)
 (root/ce.MAPPING_PATH).write_text(json.dumps(mapping,indent=2)+'\n');git(root,'add','--',ce.MAPPING_PATH);git(root,'commit','-qm','temporary mapping');head=git(root,'rev-parse','HEAD').decode().strip()
 for o in originals:
  raw=ce.read_archive(root,o['path'],head);assert raw==ce.archive_original(root,o)==ce.read(root,o['path'],o['revision']); reject(lambda: ce.read(root,o['path'],head)); assert not v.evidence_exists(root,o['path'],head)
  reject(lambda: v.m3_evidence_bytes(root,dict(path=o['path'],revision=head,sha256=ce.digest(ce.blob(root,o['path'],head))),head))
 check('real_installed_four_blob_roundtrip_never_supplies_execution_or_m3_proof',lambda: None)
 budget=ce.audit(root,original_head,head,'KL-080');assert not budget['errors']; assert ce.audit(root,original_head,head,'HG-051')['errors']
 check('forward_ancestry_and_budget_exact_owner_only',lambda: None)
 for field,value in [('raw_bytes',1),('blob_id','0'*40),('revision','0'*40),('path','../borrow')]:
  bad=copy.deepcopy(mapping);bad['entries'][0]['original'][field]=value;reject(lambda: ce.validate_archive(root,bad,head))
 for field,value in [('result','PASS'),('exit_code',0),('timestamp','invented')]:
  bad=copy.deepcopy(mapping);bad['entries'][1]['original']['execution'][field]=value;reject(lambda: ce.validate_archive(root,bad,head))
 for field,value in [('revision','HEAD'),('payload','../borrow.gz'),('envelope_bytes',ce.PLAIN_LIMIT+1),('payload_bytes',ce.STORED_LIMIT+1)]:
  bad=copy.deepcopy(mapping);bad['entries'][0]['storage'][field]=value;reject(lambda: ce.validate_archive(root,bad,head))
 check('original_failure_timestamp_and_storage_rebinding_rejected',lambda: None)
 candidate=root/'candidate';candidate.mkdir();(candidate/ce.MAPPING_SCHEMA).write_bytes(authority);assert v.historical_schema_authority_errors(candidate)==[]
 for data in (b'{}', authority+b' ', b' '*(ce.PLAIN_LIMIT+1)):
  (candidate/ce.MAPPING_SCHEMA).write_bytes(data); assert all(x.startswith('historical-schema-authority:') for x in v.validate(candidate,None))
 (candidate/ce.MAPPING_SCHEMA).unlink(); assert v.validate(candidate,None)
 (candidate/ce.MAPPING_SCHEMA).symlink_to(ROOT/ce.MAPPING_SCHEMA); assert v.validate(candidate,None)
 check('installed_validator_rejects_missing_tampered_whitespace_oversize_and_symlink_schema_before_index',lambda: None)
 real_git=ce.git
 def unavailable(r,*args):
  if any(o['revision']+'^{commit}' in args for o in originals):raise ValueError('unavailable original')
  return real_git(r,*args)
 ce.git=unavailable
 for o in originals: assert ce.read_archive(root,o['path'],head);reject(lambda: ce.archive_original(root,o))
 assert ce.archive_audit(root,head)[0];ce.git=real_git
 check('unavailable_original_cannot_fallback_but_archive_retrieval_remains_distinct',lambda: None)
 unrelated=git(root,'commit-tree',storage+'^{tree}','-m','unrelated tree').decode().strip(); bad=copy.deepcopy(mapping)
 for e in bad['entries']:e['storage']['revision']=unrelated
 assert ce.validate_archive(root,bad,unrelated);reject(lambda:ce.validate_archive(root,bad,unrelated,verify_originals=True))
 check('disconnected_original_ancestry_cannot_certify_proof',lambda: None)
 for encoding in ('utf-8','utf-16','utf-32'):
  for value in (mapping,[mapping],{'wrapped':mapping}):
   path='docs/exec-plans/evidence/KL-080/renamed.log';(root/path).write_bytes(json.dumps(value).encode(encoding));reject(lambda:ce.read(root,path,None))
 check('encoded_wrapped_archival_metadata_rejected_as_plain_output',lambda: None)
 for o in originals: (root/o['path']).write_bytes(b'1 passed\n');(root/mapping['entries'][originals.index(o)]['storage']['payload']).unlink()
 (root/ce.MAPPING_PATH).unlink();git(root,'add','-u');git(root,'commit','-qm','temporary deletion');badhead=git(root,'rev-parse','HEAD').decode().strip();assert ce.audit(root,head,badhead,'HG-051')['errors']
 check('complete_archival_deletion_and_plain_pass_substitution_rejected',lambda: None)
 report=dict(source_commit=SOURCE,base_commit=BASE,checks=checks,measurements=measured,temporary_storage_sha=storage,temporary_mapping_sha=head,budget=budget,status='PASS',scope='No repo edits or installer/credential/DB action')
 (OUT/'probe.json').write_text(json.dumps(report,indent=2)+'\n')
