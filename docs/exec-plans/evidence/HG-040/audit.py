"""Exact bounded HG040 governance scope, source and prospective-state audit."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

root=Path.cwd(); here=root/'docs/exec-plans/evidence/HG-040'
base=(here/'protected-base.txt').read_text().strip(); sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
def raw(path):return subprocess.check_output(['git','show',base+':'+path])
allowed={'06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md','CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json','docs/exec-plans/active/KL-076.md','docs/exec-plans/active/KL-078.md','docs/exec-plans/governance/HG-040.yaml','tools/harness/validate_harness.py','tests/harness/test_preparation_scope.py','docs/exec-plans/integrations/KL-075.json'}
paths=subprocess.check_output(['git','diff','--name-only',base,sha],text=True).splitlines()
assert all(p in allowed or p.startswith('docs/exec-plans/evidence/HG-040/') for p in paths),paths
bpath='KineticLoop_Harness_Backlog_v0.2.json'; prior=json.loads(raw(bpath)); current=json.loads((root/bpath).read_text())
assert current['task_count']==prior['task_count']+1 and current['active_task_count']==prior['active_task_count']+1
old={t['id']:t for t in prior['tasks']}; new={t['id']:t for t in current['tasks']}
assert set(new)-set(old)=={'KL-078'} and not set(old)-set(new)
assert {k:v for k,v in prior.items() if k not in {'tasks','task_count','active_task_count'}}=={k:v for k,v in current.items() if k not in {'tasks','task_count','active_task_count'}}
for name in old:
 if name!='KL-076':assert old[name]==new[name],name
for field in old['KL-076']:
 if field not in {'depends_on','context_files','entry_conditions'}:assert old['KL-076'][field]==new['KL-076'][field],field
assert new['KL-076']['depends_on']==old['KL-076']['depends_on']+['KL-078']
assert new['KL-076']['context_files']==old['KL-076']['context_files']+['docs/exec-plans/completed/KL-078_RESULT.yaml']
assert new['KL-076']['entry_conditions'][:-1]==old['KL-076']['entry_conditions']
assert new['KL-078']==json.loads((here/'KL-078.definition.draft.json').read_text())
assert (root/'docs/exec-plans/active/KL-078.md').read_bytes()==(here/'KL-078.packet.draft.md').read_bytes()
for name in ['KL-076','KL-078']:
 for directory in ['completed','reviews','integrations']:
  prefix=f'docs/exec-plans/{directory}/{name}'
  assert not subprocess.check_output(['git','ls-tree','-r','--name-only',base,'--',prefix],text=True).strip()
  assert not subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'--',prefix],text=True).strip()
for path in ['05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md','FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','KineticLoop_Acceptance_Spec_v1.2.2.json','KineticLoop_Integration_Acceptance_v0.1.json']:
 assert raw(path)==(root/path).read_bytes(),path
assert not any(p.startswith(('src/','migrations/','.github/','tools/db/','tests/db/','tests/unit/','docs/exec-plans/completed/','docs/exec-plans/evidence/KL-076/')) for p in paths)
assert new['KL-078']['status']=='NOT_STARTED' and new['KL-078']['requirements_covered']==[] and new['KL-078']['evidence_refs']==[]
print(json.dumps({'status':'HG040_SCOPE_AUDIT_PASS','base_commit':base,'tested_commit':sha,'paths':paths,'application_edits':False,'prospective_checks':'NOT_RUN','requirements_promoted':False},indent=2))
