import hashlib,importlib.util,json,subprocess,xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import yaml
root=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop');tested='0557dbd8f2196df871af20c0982bdc2526f0ad6e';reviewed='4073ca6ef64a625c398483fb5fbfe41b1ef3237c';base='b877db0edd2e4550d6ea81750656112fb7f2e223'
def git(*a):return subprocess.check_output(['git',*a],cwd=root)
spec=importlib.util.spec_from_file_location('ce_final_protocol',root/'tools/harness/compact_evidence.py');ce=importlib.util.module_from_spec(spec);spec.loader.exec_module(ce)
prefix='docs/exec-plans/evidence/HG-051/final-0557dbd/'
gov=yaml.safe_load(ce.blob(root,'docs/exec-plans/governance/HG-051.yaml',reviewed))
assert gov['tested_commit']==tested and gov['base_commit']==base and gov['change_status']=='PASS'
subprocess.run(['git','merge-base','--is-ancestor',tested,reviewed],cwd=root,check=True)
changed=git('diff','--name-only',tested,reviewed).decode().splitlines()
assert all(p.startswith(prefix) or p=='docs/exec-plans/governance/HG-051.yaml' for p in changed)
execution=json.loads(ce.blob(root,prefix+'EXECUTION.json',reviewed))
assert execution['tested_commit']==execution['source_end_sha']==tested and execution['source_end_status']==''
assert len(execution['executions'])==len(gov['checks_run'])==10
checks=[]
for check in gov['checks_run']:
 run=next(x for x in execution['executions'] if x['check_id']==check['check_id'])
 assert run['tested_commit']==tested and run['exit_code']==0 and check['result']=='PASS' and check['command']==run['command']
 raw=ce.read(root,check['evidence_ref'],reviewed,tested=tested,command=run['command'],exit_code=0)
 checks.append({'check_id':check['check_id'],'exit_code':0,'raw_bytes':len(raw),'raw_sha256':ce.digest(raw)})
counts={}
for name,want in [('focused-junit.json',190),('harness-junit-xml.json',1492),('unit-junit.json',241)]:
 raw=ce.read(root,prefix+name,reviewed,tested=tested,exit_code=0)
 xml=ET.fromstring(raw);cases=list(xml.iter('testcase'))
 assert len(cases)==want and not list(xml.iter('failure')) and not list(xml.iter('error')) and not list(xml.iter('skipped'))
 counts[name]={'cases':len(cases),'failures':0,'errors':0,'skipped':0}
manifest=json.loads(ce.read(root,prefix+'harness-manifest-json.json',reviewed))
collected=json.loads(ce.read(root,prefix+'harness-collection-json.json',reviewed))
executed=json.loads(ce.read(root,prefix+'harness-execution-json.json',reviewed))
assert manifest['tested_commit']==tested and manifest['dirty_source'] is False and manifest['execution_complete'] is True and manifest['exit_code']==manifest['pytest_exit_code']==0 and not manifest['errors']
assert collected['exit_code']==executed['exit_code']==0 and not collected['errors'] and not executed['errors']
assert len(collected['collections']['serial'])==1492 and len(set(executed['started']))==1492 and len(executed['started'])==1492
assert set(executed['started'])==set(collected['collections']['serial'])
print(json.dumps({'reviewed_head_sha':reviewed,'tested_commit':tested,'base_commit':base,'status':'PASS','tested_to_reviewed_only_governance_and_final_evidence':True,'clean_source_end':True,'checks':checks,'junit':counts,'collection_count':1492,'started_unique_count':1492,'execution_report_count':len(executed['reports']),'manifest_execution_complete':True,'manifest_evidence_scope':manifest['evidence_scope'],'execution_scope_not_release_or_App_gate':True},indent=2))
