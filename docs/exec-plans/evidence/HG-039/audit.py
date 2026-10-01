"""Exact HG039 scope and append-only protected-base audit; no DB lifecycle."""
import json
import subprocess
from pathlib import Path

root=Path.cwd()
base=(root/'docs/exec-plans/evidence/HG-039/protected-base.txt').read_text().strip()
def prior(path):
 return subprocess.check_output(['git','show',base+':'+path],text=True)
allowed={'CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json',
 'KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json',
 'docs/exec-plans/active/KL-026.md','tools/harness/validate_harness.py',
 'tests/harness/test_cancel_identity_scope.py','docs/exec-plans/governance/HG-039.yaml'}
changed=set(subprocess.check_output(['git','diff','--name-only',base],text=True).splitlines())
changed.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines())
assert all(p in allowed or p.startswith(('docs/exec-plans/evidence/HG-039/','docs/exec-plans/reviews/HG-039/')) for p in changed),changed
for name in ['KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json']:
 old=json.loads(prior(name));new=json.loads((root/name).read_text())
 assert {k:v for k,v in old.items() if k!='tasks'}=={k:v for k,v in new.items() if k!='tasks'}
 assert len(old['tasks'])==len(new['tasks'])
 for a,b in zip(old['tasks'],new['tasks']):
  if a['id']!='KL-026': assert a==b,a['id']
  else:
   assert {k for k in a if a[k]!=b[k]}=={'check_contracts','checks_required_for_this_task','context_files'}
   assert [c for c in b['check_contracts'] if c['check_id']!='cancellation_identity_pu']==a['check_contracts']
for p in ['src/kineticloop/contracts/commands.py','src/kineticloop/persistence/transactions.py',
          'FROZEN_BASELINE.json','05_KineticLoop_Protocol_v1.2_FROZEN.md',
          '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md','CURRENT_REQUIREMENT_SET.json']:
 assert subprocess.check_output(['git','show',base+':'+p])==(root/p).read_bytes(),p
for name in ['CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json']:
 old=json.loads(prior(name));new=json.loads((root/name).read_text())
 def strip(value):
  if isinstance(value,dict):return {k:strip(v) for k,v in value.items() if k not in {'sha256','bytes'}}
  if isinstance(value,list):return [strip(v) for v in value]
  return value
 assert strip(old)==strip(new)
assert not subprocess.run(['git','cat-file','-e',base+':docs/exec-plans/completed/KL-026_RESULT.yaml'],capture_output=True).returncode==0
print('HG039_SCOPE_PASS: only KL026 identity/check/context refined; existing DC oracles, public registry, production, frozen and requirements unchanged; no foreign lifecycle.')
