"""Capture distinct real executions after successful clean completion; no result import."""
import json
import shutil
import subprocess
from pathlib import Path

import yaml

root=Path('/Users/davetian/.codex/worktrees/cd73/KineticLoop')
sha='f302b22c0838ef2928913392e7c2a6af9e8f8698'
initial=Path('/private/tmp/hg050-checks-f302b22')
retry=Path('/private/tmp/hg050-harness-rerun-f302b22')
final=Path('/private/tmp/hg050-harness-isolated-f302b22')
records=json.loads((initial/'RUN.json').read_text())
recovery=json.loads((retry/'EXECUTION.json').read_text())
success=json.loads((final/'EXECUTION.json').read_text())
assert recovery['exit_code']==1 and recovery['source_end_status']==''
assert success['exit_code']==0 and success['source_end_status']=='' and success['source_end_sha']==sha
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root)
owner=root/'docs/exec-plans/evidence/HG-050'
shutil.copytree('/private/tmp/hg050-pending-artifacts/precommit',owner/'precommit')
shutil.copyfile('/private/tmp/hg050-pending-artifacts/OPERATOR_OBSERVATIONS.json',owner/'OPERATOR_OBSERVATIONS.json')
raw=owner/'runs';raw.mkdir()
metadata=owner/'checks-f302b22';metadata.mkdir()
# All envelopes share one directory: identical raw outputs from distinct real
# executions share content-addressed gzip bytes, while metadata stays distinct.
def capture(source,name,record):
 target=raw/(name+'.json')
 subprocess.run([str(root/'.venv/bin/python'),'tools/harness/compact_evidence.py','capture',
  '--input',str(source),'--output',str(target.relative_to(root)),'--tested',sha,
  '--command',record['command'],'--exit-code',str(record['exit_code'])],cwd=root,check=True,stdout=subprocess.DEVNULL)
 return str(target.relative_to(root))

def harness(source,prefix,record):
 ref=capture(Path(record['log']),prefix+'-harness',record)
 for path in sorted((source/'harness').iterdir()):
  if path.is_file():capture(path,prefix+'-harness-'+path.name.replace('.','-'),record)
 return ref

checks=[]
for record in records:
 if record['check_id']=='harness':
  assert record['exit_code']==1
  harness(initial,'initial-failed',record)
  continue
 assert record['exit_code']==0
 ref=capture(Path(record['log']),record['check_id'],record)
 checks.append({'check_id':record['check_id'],'command':record['command'],'result':'PASS','evidence_ref':ref})
unit=next(r for r in records if r['check_id']=='unit')
capture(initial/'unit.xml','unit-junit',unit)
harness(retry,'retry-failed',recovery)
ref=harness(final,'isolated-pass',success)
checks.append({'check_id':'harness','command':success['command'],'result':'PASS','evidence_ref':ref})
probe={'command':"uv run pytest 'tests/harness/test_m3_milestone_closure.py::test_compact_nested_storage_cannot_supply_m3_execution_stdout[missing]' -q --basetemp=/private/tmp/hg050-m3-probe-temp",'exit_code':0}
ref=capture(Path('/private/tmp/hg050-m3-probe.log'),'git-temp-probe',probe)
checks.append({'check_id':'git_temp_recovery','command':probe['command'],'result':'PASS','evidence_ref':ref})
shutil.copyfile(initial/'RUN.json',metadata/'INITIAL_EXECUTION.json')
shutil.copyfile('/private/tmp/hg050-driver.log',metadata/'initial-driver.log')
shutil.copyfile(retry/'EXECUTION.json',metadata/'RETRY_EXECUTION.json')
shutil.copyfile(final/'EXECUTION.json',metadata/'ISOLATED_EXECUTION.json')
shutil.copyfile('/private/tmp/hg050-rerun.py',metadata/'rerun_driver.py')
shutil.copyfile('/private/tmp/hg050-isolated-run.py',metadata/'isolated_driver.py')
shutil.copyfile(__file__,metadata/'capture_driver.py')
(metadata/'EXECUTION.json').write_text(json.dumps({'tested_commit':sha,'passing_checks':[r for r in records if r['check_id']!='harness']+[success],'failed_attempts':['INITIAL_EXECUTION.json','RETRY_EXECUTION.json']},indent=2)+'\n')
(metadata/'DIAGNOSIS.json').write_text(json.dumps({
 'tested_commit':sha,
 'initial_attempt':{'wrapper_exit_code':1,'pytest_exit_code':0,'pytest_passed':1405,
  'error':'source-changed-during-execution','initial_source_status':'clean; manifest dirty_source=false',
  'observed_end_head':sha,'observed_end_status':'?? docs/exec-plans/evidence/HG-050/OPERATOR_OBSERVATIONS.json\n?? docs/exec-plans/evidence/HG-050/precommit/\n',
  'tracked_changes':'none; observed status showed only the two own untracked paths; git diff --exit-code HEAD succeeded',
  'cause':'Implementer appended prospective untracked evidence during the clean-start harness execution.',
  'correction':'Move pending artifacts outside checkout; no source/Git writes during later executions.'},
 'retry_attempt':{'wrapper_exit_code':1,'pytest_exit_code':1,'pytest_passed':1404,'pytest_failed':1,
  'source_start_status':'clean','source_end_status':'clean','source_end_sha':sha,
  'error':'Git add in synthetic M3 fixture: unable to create temporary file: Invalid argument',
  'phase':'fixture setup before the test assertions; no GitHub client path involved',
  'diagnosis':'Temporary Git filesystem failure; exact underlying OS cause unproven. Disk inspection showed 1.4 TiB available. Isolated same-test probe passed in task-owned basetemp; no fixture/runtime edits.',
  'correction':'Full harness under task-owned --basetemp with normal two workers.'},
 'final_attempt':{'reference':'ISOLATED_EXECUTION.json','source_start_status':'clean','source_end_status':'clean','source_end_sha':sha},
 'claims':'Both failures remain FAIL. Only the final complete clean wrapper execution supplies harness PASS. No stitched PASS, historical mutation, import or manual publication.'},indent=2)+'\n')
record={'change_identity':'harness-governance-v0.1/HG-050','display_change_id':'HG-050',
 'base_commit':'034d6301316d0dade784a61b159c027b83fbce3a','tested_commit':sha,'change_status':'PASS',
 'summary':'Prospectively validate server UTC expiry with a 60-second margin and conservative pre-mint monotonic age; invalidate on observed wall rollback or failed renewal. Typed 401 permits one installation-token GET refresh/retry, never write replay. Preserve controller admission, snapshots, check identity and publication semantics.',
 'packets_refined':[],'files_changed':[],'checks_run':checks,'frozen_impact':'NONE',
 'authority_entries_added':[],'known_limitations':[
 'Product, M3, release and full database/controller checks remain NOT_RUN here. Root owns separately reviewed installation, exact pins/admission and final stable-head App full DB window.',
 'GENERAL and SECURITY_DATA_BOUNDARY independent reviews bind the implementation/governance/evidence revision. Only own REVIEW_RECORD_ONLY suffix may follow.',
 'Historical HG049 failure and separate unchanged-controller caffeinate rerun remain untouched and supply no corrective PASS. No configuration/signing/admission edit, manual publication or one-time exception.',
 'Clock rollback detection is conservative at observations, not proof against arbitrary unobserved clock corruption. Installation tokens remain memory-only.',
 'POST/PATCH errors terminate without replay; a success body rejected with 401 is not published. A separate controller failure PATCH may proactively renew after a failed GET; it never turns that run into success.',
 'Failed precommit probes and both failed full-harness executions are preserved losslessly. Initial wrapper rejected implementer-created untracked evidence despite 1405 pytest passes. Clean retry failed a temporary Git fixture setup with 1404 passes; isolated probe passed. Only final complete clean run supplies PASS. Other checks remain valid at unchanged tested SHA.']}
changed=subprocess.check_output(['git','diff','--name-only',record['base_commit'],'HEAD'],cwd=root,text=True).splitlines()
added=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()
record['files_changed']=sorted(set(changed+added+['docs/exec-plans/governance/HG-050.yaml']))
(root/'docs/exec-plans/governance/HG-050.yaml').write_text(yaml.safe_dump(record,sort_keys=False,width=110))
