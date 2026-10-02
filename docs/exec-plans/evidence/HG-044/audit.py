"""Audit bounded HG044 diff and preserved canonical validator implementations."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

root=Path.cwd();base='2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
old=subprocess.check_output(['git','show',base+':tools/harness/validate_harness.py'],text=True)
new=(root/'tools/harness/validate_harness.py').read_text()
def functions(text):
 lines=text.splitlines(keepends=True)
 return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
before,after=functions(old),functions(new)
preserved=['milestone_closure_errors','m2_milestone_closure_errors','m2_execution_evidence_errors','integration_record_errors','review_evidence_exists','semantic_result_errors']
checks={name:before[name]==after[name] for name in preserved}
changed=subprocess.check_output(['git','diff','--name-only',base,head],text=True).splitlines()
allowed={'MILESTONE_CLOSURE.schema.json','tools/harness/validate_harness.py','tests/harness/test_m3_milestone_closure.py','docs/harness/M3_CLOSURE_CONTRACT.md','06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md','CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json'}
checks['scope']=all(p in allowed or p.startswith('docs/exec-plans/evidence/HG-044/') or p.startswith('docs/exec-plans/reviews/HG-044/') or p=='docs/exec-plans/governance/HG-044.yaml' for p in changed)
old_plan=subprocess.check_output(['git','show',base+':06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md'],text=True)
new_plan=(root/'06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md').read_text()
checks['plan_prefix']=new_plan.split('## M3 exit-evidence mapping — HG044',1)[0]==old_plan+'\n'
checks['no_instance']=not (root/'docs/exec-plans/milestones/M3.json').exists()
report=dict(base_commit=base,tested_commit=head,checks=checks,changed=changed,status='PASS' if all(checks.values()) else 'FAIL',preserved_function_sha256={n:hashlib.sha256(after[n].encode()).hexdigest() for n in preserved})
p=root/f'docs/exec-plans/evidence/HG-044/scope-{head[:7]}.json';assert not p.exists();p.write_text(json.dumps(report,indent=2)+'\n');print(report['status'])
raise SystemExit(0 if all(checks.values()) else 1)
