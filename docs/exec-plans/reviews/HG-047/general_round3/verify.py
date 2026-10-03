import ast, collections, gzip, hashlib, importlib.util, json, re, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path
import yaml
ROOT=Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
BASE='391c9198fa8ec647e377a0572700bc7568468c85'
HEAD='589e538579f519bc10d178fa02dff12332931ba7'
TESTED='f29ffa97d9057eacc4bda7ad593b843c9c52c5a2'
P='docs/exec-plans/evidence/HG-047/round3-f29ffa9/'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(path,sha=HEAD):return git('show',sha+':'+path)
def digest(b):return hashlib.sha256(b).hexdigest()
def load(path,sha=HEAD):return json.loads(blob(path,sha))
def module(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path); m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ce=module('ce','tools/harness/compact_evidence.py');v=module('validator','tools/harness/validate_harness.py')
report={'base':BASE,'reviewed':HEAD,'tested':TESTED,'independent_checks':{}}
checks=report['independent_checks']
assert git('rev-parse','HEAD').decode().strip()==HEAD
assert git('merge-base',BASE,HEAD).decode().strip()==BASE
assert not git('diff',TESTED,HEAD,'--','tools','tests','src','.github','migrations','CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','docs/harness')
checks['tested_implementation_equals_reviewed']=True
record=yaml.safe_load(blob('docs/exec-plans/governance/HG-047.yaml'))
changed=git('diff','--no-renames','--name-only',BASE,HEAD).decode().splitlines()
assert set(record['files_changed'])==set(changed)
assert all(v.matches(p,v.governance_allowed_patterns('HG-047')) for p in changed)
assert not v.governance_suffix_errors(ROOT,TESTED,HEAD,'HG-047','tested')
checks['exact_declared_scope_and_tested_suffix']=len(changed)
protected=['FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','src','migrations','tests/db','.github/workflows','KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json','tools/harness/db_policy.py','tools/harness/db_ci.py','tools/harness/github_app.py','tools/harness/gate_validate.py','tools/harness/gate_pytest.py','tools/harness/db_ci_pytest.py','tools/harness/local_db']
protected += [x['path'] for x in load('FROZEN_BASELINE.json',BASE)['files']]
for id in ['HG-045','HG-046']:
 protected += [f'docs/exec-plans/{kind}/{id}' for kind in ['evidence','reviews']]+[f'docs/exec-plans/governance/{id}.yaml']
assert not git('diff','--name-only',BASE,HEAD,'--',*protected)
checks['frozen_runtime_merged_prerequisite_policy_unchanged']=True
for name in ['CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json']:
 current=load(name);prior=load(name,BASE)
 def scrub(x):
  if isinstance(x,dict):return {k:scrub(v) for k,v in x.items() if k not in ['sha256','bytes']}
  if isinstance(x,list):return [scrub(v) for v in x]
  return x
 assert scrub(current)==scrub(prior)
 def inspect(x):
  if isinstance(x,dict):
   if 'path' in x and 'sha256' in x:
    assert digest(blob(x['path']))==x['sha256']
    if 'bytes' in x:assert len(blob(x['path']))==x['bytes']
   for val in x.values():inspect(val)
  elif isinstance(x,list):
   for val in x:inspect(val)
 inspect(current)
checks['authority_inventory_and_hashes']=True
all_env=[]; decoded={}
for path in changed:
 if not path.startswith('docs/exec-plans/evidence/HG-047/') or not path.endswith('.json'):continue
 try:m=load(path)
 except (ValueError,UnicodeError):continue
 if not isinstance(m,dict) or ('kineticloop_'+'evidence') not in m:continue
 stored=blob(m['payload']); raw=gzip.decompress(stored)
 assert len(stored)==m['stored_bytes'] and digest(stored)==m['stored_sha256']
 assert len(raw)==m['raw_bytes'] and digest(raw)==m['raw_sha256']
 assert Path(m['payload']).parent==Path(path).parent and Path(m['payload']).name==digest(raw)+'.gz'
 assert git('merge-base',m['tested_commit'],HEAD).decode().strip()==m['tested_commit']
 assert ce.read(ROOT,path,HEAD)==raw
 decoded[path]=raw
 all_env.append({'path':path,'raw_bytes':len(raw),'stored_bytes':len(stored),'tested':m['tested_commit'],'raw_digest':digest(raw)})
report['envelopes_verified']=all_env
checks['all_new_envelopes_independently_decoded']=len(all_env)
for check in record['checks_run']:
 ref=check['evidence_ref'];m=load(ref)
 assert check['result']=='PASS' and m['tested_commit']==TESTED and m['command']==check['command'] and m['exit_code']==0
 assert ce.read(ROOT,ref,HEAD,tested=TESTED,command=check['command'],exit_code=0)==decoded[ref]
checks['selected_checks_exact_bindings']=len(record['checks_run'])
execution=load(P+'execution.json');dev=json.loads(decoded[P+'development-final-json.json']);receipt=json.loads(decoded[P+'worker-receipt-json.json'])
assert execution['mode']==dev['mode']=='DEVELOPMENT_NO_PUBLICATION'
assert dev['full_db'] is False and dev['test_only'] is True
assert all(dev[x] is False for x in ['app_object_created','signer_config_read','admission_read','publication'])
assert receipt['head']==dev['tested_commit']==TESTED and receipt['base']==BASE
assert receipt['status']=='PASS' and receipt['full_database_required'] is False and receipt['container_removed'] and receipt['volume_removed']
for path,sha in receipt['artifacts'].items():
 ref=execution['artifact_refs'][path];assert digest(decoded[ref])==sha
for check in receipt['checks']:
 raw=decoded[execution['artifact_refs'][check['stdout']['path']]]
 assert digest(raw)==check['stdout']['sha256'] and len(raw)==check['stdout']['bytes']
 assert check['exit_code']==0 and check['interrupted'] is False
 if check['check_id'] in ['lint','typecheck','unit','harness','merge_gate']:
  assert load(execution['artifact_refs'][check['stdout']['path']])['command']==' '.join(check['argv'])
checks['linux_receipt_raw_digests_exits_cleanup_development_only']=True
for asset,sha in dev['controller_files'].items():
 assert digest(blob('tools/harness/'+asset,dev['installed_reviewed_revision']))==sha
 assert blob('tools/harness/'+asset,dev['installed_reviewed_revision'])==blob('tools/harness/'+asset)
checks['installed_release_assets_equal_reviewed_git_bytes']=len(dev['controller_files'])
observer=json.loads(decoded[P+'worker--run--execution-json.json'])
collected=[line for line in decoded[P+'collection.json'].decode().splitlines() if re.match(r'^tests/[^\s]+\.py::',line)]
assert len(collected)==len(set(collected))==1306
assert set(collected)==set(observer['nodeids']) and observer['exit_code']==0
for suite,total in [('harness',1306),('unit',241)]:
 tree=ET.fromstring(decoded[P+f'worker--{suite}-xml.json']); cases=list(tree.iter('testcase'))
 assert len(cases)==total
 assert not any(list(case.iter(tag)) for case in cases for tag in ['failure','error','skipped'])
 ids=[(case.get('classname'),case.get('name')) for case in cases];assert len(set(ids))==total
 assert re.search(r'\b'+str(total)+r' passed\b',decoded[P+suite+'.json'].decode())
 if suite=='harness':
  expected={tuple(node.split('::',1)) for node in collected}
  observed=set()
  for path,case in expected:
   before,bracket,parameters=case.partition('[')
   parts=before.split('::')
   classname=path.replace('/','.')[:-3]+('.'+'.'.join(parts[:-1]) if len(parts)>1 else '')
   observed.add((classname,parts[-1]+bracket+parameters))
  assert set(ids)==observed
 checks[suite+'_junit_log_and_collection_count']=total

def no_ids(data):
 tree=ast.parse(data)
 for node in ast.walk(tree):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='parametrize':node.keywords=[k for k in node.keywords if k.arg!='ids']
 return ast.dump(tree,include_attributes=False)
assert no_ids(blob('tests/harness/test_compact_evidence.py','8a78241e9b752247c3c4f4a43c4fe54bad72ef6c'))==no_ids(blob('tests/harness/test_compact_evidence.py',TESTED))
fixed=[n for n in collected if any(s in n for s in ['::test_bounded_single_member_decoder[','::test_budget_rejects_bulk_and_duplicate_metadata['])]
assert len(fixed)==10 and max(len(n.encode()) for n in fixed)==105
checks['linux_fix_ast_preserves_all_cases_assertions']=True
checks['fixed_case_count']=len(fixed);checks['fixed_case_id_max_bytes']=105
old='docs/exec-plans/evidence/HG-047/development-8a78241/'
old_log=decoded[old+'harness-log.json'].decode()
assert '1304 passed' in old_log and '2 errors' in old_log and 'Argument list too long' in old_log
old_xml=ET.fromstring(decoded[old+'worker--harness-xml.json']);assert len(list(old_xml.iter('error')))==2
old_receipt=json.loads(decoded[old+'worker-receipt-json.json']);assert old_receipt['status']=='FAIL'
checks['prior_failure_retained']=True
report['budget']=ce.audit(ROOT,BASE,HEAD,'HG-047');assert not report['budget']['errors']
assert not git('diff','--check',BASE,HEAD)
checks['diff_hygiene']=True
probe=[]
for label,raw in [('literal',b'{"event":"ok","event":"again"}'),('escaped',b'{"event":"\\u006f\\u006b","event":"again"}')]:
 try:r=ce.envelope(raw);probe.append({'case':label,'accepted_as_plain':r is None,'error':None})
 except ValueError as e:probe.append({'case':label,'accepted_as_plain':False,'error':str(e)})
report['ordinary_json_parity_probe']=probe
policy=module('policy','tools/harness/db_policy.py').classify(ROOT,BASE,HEAD)
assert policy['full_database_required'] is True
checks['final_full_database_policy_still_required']=True
refs=['docs/exec-plans/reviews/HG-047/general_round3/'+n for n in ['REPORT.md','verification.json','verify.py','focused.log']]
for ref in refs:
 assert not git('ls-tree',HEAD,'--',ref)
checks['new_review_references_absent_at_reviewed_sha']=refs
report['status']='PASS'
print(json.dumps(report,indent=2))
