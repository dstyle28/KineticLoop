from pathlib import Path
import fnmatch,hashlib,json,subprocess,sys
root=Path('/Users/davetian/.codex/worktrees/harness-concurrency/KineticLoop')
base='391c9198fa8ec647e377a0572700bc7568468c85'
tested='0045808352507b7af67a3a2135408421d8bcc6bc'
def git(*args):return subprocess.check_output(['git',*args],cwd=root)
changed=git('diff','--name-only',base,tested).decode().splitlines()
allowed={'CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','pyproject.toml','uv.lock','src/kineticloop/cli.py','tools/harness/run_harness_tests.py','tools/harness/parallel_observer.py','tools/harness/validate_harness.py','tests/harness/test_parallel_runner.py','tools/harness/README.md','docs/exec-plans/evidence/HG-048/SCOPE.md'}
errors=[]
if set(changed)!=allowed:errors.append('Implementation write scope differs: '+str(sorted(set(changed)^allowed)))
frozen=json.loads(git('show',base+':FROZEN_BASELINE.json'))
for path in ['FROZEN_BASELINE.json',*[e['path'] for e in frozen['files']]]:
 if git('show',base+':'+path)!=git('show',tested+':'+path):errors.append('Frozen change: '+path)
for path,groups,strip in [('CURRENT_DOCUMENT_INDEX.json',('documents','machine_readable'),('sha256',)),('HARNESS_DOCUMENT_MANIFEST.json',('files',),('sha256','bytes'))]:
 before=json.loads(git('show',base+':'+path));after=json.loads(git('show',tested+':'+path))
 if {k:v for k,v in before.items() if k not in groups}!={k:v for k,v in after.items() if k not in groups}:errors.append('Index/manifest metadata changed')
 for group in groups:
  if [{k:v for k,v in e.items() if k not in strip} for e in before[group]]!=[{k:v for k,v in e.items() if k not in strip} for e in after[group]]:errors.append('Index/manifest identities changed')
  for previous,current in zip(before[group],after[group]):
   raw=git('show',tested+':'+current['path'])
   if current['sha256']!=hashlib.sha256(raw).hexdigest():errors.append('Derived hash mismatch: '+current['path'])
   if 'bytes'in current and current['bytes']!=len(raw):errors.append('Derived byte mismatch: '+current['path'])
   if current!=previous and current['path'] not in changed:errors.append('Unrelated hash refresh: '+current['path'])
protected=['tools/harness/local_gate.py','tools/harness/db_ci_pytest.py','tools/harness/gate_pytest.py','tools/harness/db_ci.py','tools/harness/db_policy.py','.github/workflows/ci.yml','.github/workflows/db.yml','docs/harness/LOCAL_DB_CI.md']
for path in protected:
 if git('show',base+':'+path)!=git('show',tested+':'+path):errors.append('Controller/policy change: '+path)
record={'base_commit':base,'tested_commit':tested,'files_changed':changed,'frozen_and_execution_policy_unchanged':not errors,'pinned_controller_assets_changed':['validate_harness.py'],'compatibility_note':'Only the HG-048 governance allowlist changes in the pinned validator. Installed pins/settings are unchanged; reviewed installation remains required.','errors':errors,'requirements_status':'NOT_RUN: developer harness performance has no product/protocol PASS claim'}
print(json.dumps(record,indent=2));sys.exit(bool(errors))
