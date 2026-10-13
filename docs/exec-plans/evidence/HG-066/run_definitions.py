"""ONE stable preparation cycle; actual exits/identities. No task/runtime PASS."""
from pathlib import Path
import os,json,hashlib,subprocess,sys,time,xml.etree.ElementTree as ET,gzip
from collections import Counter
from data_io import read_json
D=Path(__file__).resolve().parent;R=D.parents[3];E=R/'docs/exec-plans/evidence/HG-065';P='3768c1b4366677934cb952ef808343edcee4e438';O=Path(os.environ['HG066_OBSERVATIONS']);O.mkdir(parents=True,exist_ok=True);commands=[]
ENV=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONPATH=str(D),MULTI_PREPARATION_OUTPUT=str(O),EXECUTION_CONTRACT_CAPTURE_DIR=str(O))
def sha(b):return hashlib.sha256(b).hexdigest()
def sources_unchanged():
 from verify_delivery import verify
 verify()

def run(label,argv,env=ENV,cwd=D):
 t=time.monotonic_ns();p=subprocess.run(argv,cwd=cwd,env=env,capture_output=True,timeout=120)
 for k,b in [('stdout',p.stdout),('stderr',p.stderr)]:(O/(label+'.'+k)).write_bytes(b)
 row={'label':label,'argv':argv,'cwd':str(cwd),'exit_code':p.returncode,'elapsed_ns':time.monotonic_ns()-t,'environment':{k:env[k] for k in ['PYTHONDONTWRITEBYTECODE','PYTEST_DISABLE_PLUGIN_AUTOLOAD','PYTHONPATH']},'stdout_bytes':len(p.stdout),'stdout_sha256':sha(p.stdout),'stderr_bytes':len(p.stderr),'stderr_sha256':sha(p.stderr)}
 for key in ['MULTI_PREPARATION_OUTPUT','EXECUTION_CONTRACT_CAPTURE_DIR','EXECUTION_CONTRACT_OBSERVER','CUSTODY_STUDY_OBSERVER','HG065_OBSERVATIONS']:
  if key in env:row['environment'][key]=env[key]
 commands.append(row);(O/'COMMANDS.json').write_text(json.dumps(commands,indent=2)+'\n');print(label,p.returncode,p.stdout.decode(errors='replace')[-240:],flush=True)
 if p.returncode:raise SystemExit(p.returncode)

sources_unchanged()
for name in ['observe_group.py','observe_provenance.py','observe_delivery_reviews.py']:run(name,[sys.executable,str(D/name)])
newproof=json.loads((O/'CURRENT_ROOT_UNION_PROOF.json').read_bytes())
newgroup=json.loads((O/'CURRENT_GROUP_OBSERVATION.json').read_bytes())
expected=json.loads((D/'EXPECTED_FIXTURES.json').read_bytes())
canon=lambda x:sha(json.dumps(x,sort_keys=True,separators=(',',':')).encode())
assert canon(newproof)==expected['CURRENT_ROOT_UNION_PROOF.json']
assert canon({k:newgroup[k] for k in ['members','root_members','physical_paths','owners','coverage']})==expected['CURRENT_GROUP_OBSERVATION.json']
assert json.loads((O/'ORIGINAL_SOURCE_BINDINGS.json').read_bytes())==json.loads((D/'ORIGINAL_SOURCE_BINDINGS.json').read_bytes())
legacy=O/'preserved-hg065';legacy.mkdir();legacy_env=dict(ENV,PYTHONPATH=str(E)+':'+str(R)+':'+str(R/'src'),HG065_OBSERVATIONS=str(legacy))
for name in ['observe_immutable.py','observe_inherited_components.py']:run('preserved-'+name,[sys.executable,str(E/name)],legacy_env,E)
assert json.loads((legacy/'ACTUAL_CUSTODY_PROOF.json').read_bytes())==json.loads((E/'ACTUAL_CUSTODY_PROOF.json').read_bytes())
checks=[]
for test,root,baseenv,observer,var in [(t,D,ENV,'definition_observer','EXECUTION_CONTRACT_OBSERVER') for t in ['test_multi_owner.py','test_multi_limits.py','test_sequence_definition.py','test_boundaries.py','test_inventory_mix.py','test_native_inventory.py','test_preimport_pairing.py','test_preimport_exhaustion.py']]+[('test_custody_definition.py',E,legacy_env,'definition_observer','CUSTODY_STUDY_OBSERVER')]:
 label=test[:-3];out=O if root==D else legacy
 base=[sys.executable,'-m','pytest',test,'-q','--import-mode=importlib','--rootdir='+str(root),'--confcutdir='+str(root),'-c','/dev/null','-p',observer,'-p','no:cacheprovider','-o','xfail_strict=true']
 for phase,args in [('collection',['--collect-only','-q']),('execution',['--junitxml='+str(out/(label+'.junit.xml'))])]:
  env=dict(baseenv,**{var:str(out/(label+'.'+phase+'.json'))});run(label+'-'+phase,base+args,env,root)
 c=json.loads((out/(label+'.collection.json')).read_bytes());x=json.loads((out/(label+'.execution.json')).read_bytes());ids=c['collections'];assert ids==x['collections']==x['started'] and len(ids)==len(set(ids))>0
 assert c['exit_code']==x['exit_code']==0 and not c['errors'] and not x['errors'] and not c['reports'] and not c['started'];assert len(x['reports'])==3*len(ids)<=512
 for phase in ['setup','call','teardown']:
  reports=[a for a in x['reports'] if a['when']==phase];assert Counter(a['nodeid'] for a in reports)==Counter(ids) and all(a['outcome']=='passed' and a['wasxfail'] is None for a in reports)
 tree=ET.parse(out/(label+'.junit.xml')).getroot();cases=list(tree.iter('testcase'));assert len(cases)==len(ids) and not list(tree.iter('failure')) and not list(tree.iter('error')) and not list(tree.iter('skipped'));assert Counter((z.get('classname'),z.get('name')) for z in cases)==Counter((label,i.split('::')[-1]) for i in ids)
 expected_ids=next(s['identities'] for s in json.loads((D/'EXPECTED_IDENTITIES.json').read_bytes())['suites'] if s['file']==test)
 assert ids==expected_ids
 if root==E:assert ids==json.loads((E/'FIXTURE_IDENTITIES.json').read_bytes())['identities'] and len(ids)==156
 checks.append({'file':test,'purpose':'PROSPECTIVE_NEW_MODEL' if root==D else 'PRESERVED_HG065_V1_CONJUNCTION_NOT_V2_CREDIT','actual_cases':len(ids),'actual_phase_reports':len(x['reports']),'positive_collection_execution_phase_junit_identity_equal':True,'identities':ids})
sources_unchanged()
packed=[]
receipt={'status':'PASS_FRESH_HG066_DEFINITION_AND_COMPONENT_CHECKS_ONLY','checks':checks,'commands':commands,'actual_cases':sum(x['actual_cases'] for x in checks),'actual_phase_reports':sum(x['actual_phase_reports'] for x in checks),'complete_native_O_to_K_or_O_to_H':'NOT_RUN','full_private_installed_operation':'NOT_RUN','normal_import_or_runtime_gates':'NOT_RUN','current_group_observation':'7_OWNERS_17_ENVELOPES_7_PAYLOADS_24_PATHS_41682_BYTES_AT_FIXED_P_Q_ONLY','historical_execution':'UNVERIFIED','acceptance_eligible':False,'execution_reuse':False,'packing':packed}
(O/'FULL_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n');print('FULL_PREPARATION_CASES',receipt['actual_cases'],'NOT_TASK_OR_RUNTIME_PASS',flush=True)
