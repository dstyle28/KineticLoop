"""Run governance-only checks on one committed tested revision; no KL047 code."""
import argparse
import json
import os
import subprocess
from pathlib import Path

root = Path.cwd()
parser = argparse.ArgumentParser()
parser.add_argument('base_commit')
base = parser.parse_args().base_commit
sha = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
folder = root/'docs/exec-plans/evidence/HG-036'
python = '/private/tmp/kl017-venv/bin/python'
env = dict(os.environ, PYTHONPATH=str(root/'src'), PYTHONUNBUFFERED='1')
checks = [
 ('merged_preflight_and_protected_scope', [python,'docs/exec-plans/evidence/HG-036/audit.py',base]),
 ('fitness_governance_regressions', [python,'-m','pytest','-q','tests/harness/test_fitness_evaluation_scope.py']),
 ('harness_validation', [python,'-m','kineticloop.db.cli','check-harness']),
 ('harness_tests', [python,'-m','kineticloop.db.cli','test-harness']),
 ('unit_tests', [python,'-m','kineticloop.db.cli','test-unit']),
 ('lint', [python,'-m','kineticloop.db.cli','lint']),
 ('typecheck', [python,'-m','kineticloop.db.cli','typecheck']),
 ('diff_clean', ['git','diff','--check',base,sha]),
]
results = []
for name,command in checks:
    ref = f'docs/exec-plans/evidence/HG-036/{name}-{sha[:8]}.log'
    path = root/ref
    assert not path.exists(), 'Evidence is append-only: ' + ref
    result = subprocess.run(command,cwd=root,env=env,capture_output=True,text=True)
    path.write_text('protected_base_commit='+base+'\ntested_commit='+sha+'\ncommand='+ ' '.join(command)+'\n'+result.stdout+result.stderr+'\nexit_code='+str(result.returncode)+'\n')
    status = 'PASS' if result.returncode == 0 else 'FAIL'
    results.append(dict(check_id=name,command='PYTHONPATH=src '+' '.join(command) if command[0] == python else ' '.join(command),result=status,evidence_ref=ref))
    print(name+' '+status,flush=True)
summary = dict(base_commit=base,tested_commit=sha,tested_tree=subprocess.check_output(['git','rev-parse',sha+'^{tree}'],text=True).strip(),checks_run=results,prospective_kl047_checks='NOT_RUN',product_gate_release_quality_status='NOT_RUN')
(folder/f'checks-{sha[:8]}.json').write_text(json.dumps(summary,indent=2)+'\n')
raise SystemExit(0 if all(r['result']=='PASS' for r in results) else 1)
