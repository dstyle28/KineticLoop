"""Preserve each HG038 governance check against its committed revision."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
HERE = ROOT / 'docs/exec-plans/evidence/HG-038'
BASE = (HERE / 'protected-base.txt').read_text().strip()
TESTED = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
PYTHON = '/private/tmp/kl017-venv/bin/python'
CHECKS = {
    'append_only_scope_audit':[PYTHON,str(HERE/'audit.py')],
    'next_wave_scope_regressions':[PYTHON,'-m','pytest','-q','tests/harness/test_m3_next_wave_scope.py'],
    'harness_validation':[PYTHON,'-m','kineticloop.db.cli','check-harness'],
    'harness_tests':[PYTHON,'-m','kineticloop.db.cli','test-harness'],
    'unit_tests':[PYTHON,'-m','kineticloop.db.cli','test-unit'],
    'lint':[PYTHON,'-m','kineticloop.db.cli','lint'],
    'typecheck':[PYTHON,'-m','kineticloop.db.cli','typecheck'],
    'diff_clean':['git','diff','--check',BASE,TESTED],
}
key = sys.argv[1]; command = CHECKS[key]
path = HERE / f'{key}-{TESTED[:7]}.log'
assert not path.exists()
env = os.environ.copy(); env['PYTHONPATH'] = str(ROOT/'src'); env['PYTHONDONTWRITEBYTECODE'] = '1'
with path.open('w') as out:
    out.write('base_commit='+BASE+'\ntested_commit='+TESTED+'\ncommand='+' '.join(command)+'\n'); out.flush()
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
    out.write('\nexit_code='+str(result.returncode)+'\n')
record = {'check_id':key,'command':' '.join(command),'result':'PASS' if result.returncode==0 else 'FAIL','evidence_ref':str(path.relative_to(ROOT)),'tested_commit':TESTED,'exit_code':result.returncode}
(HERE/f'{key}-{TESTED[:7]}.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record))
if result.returncode:
    print(path.read_text()[-5000:])
raise SystemExit(result.returncode)
