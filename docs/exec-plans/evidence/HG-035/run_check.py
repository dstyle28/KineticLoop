"""Record one exact HG035 check against current committed governance candidate."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
TESTED = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
BASE = 'eab2b305351cf3c504f74ac74868edc58d0a3430'
PYTHON = '/private/tmp/kl017-venv/bin/python'
CHECKS = {
    'merged_scope_api_fixture_audit': [PYTHON, 'docs/exec-plans/evidence/HG-035/audit.py'],
    'execution_scope_regressions': [PYTHON, '-m', 'pytest', '-q', 'tests/harness/test_protocol_execution_scope.py', 'tests/harness/test_call_ledger_scope.py', 'tests/harness/test_planning_fixture_scope.py', 'tests/harness/test_planning_subject_scope.py', 'tests/harness/test_wave_scope.py'],
    'harness_validation': [PYTHON, '-m', 'kineticloop.db.cli', 'check-harness'],
    'harness_tests': [PYTHON, '-m', 'kineticloop.db.cli', 'test-harness'],
    'unit_tests': [PYTHON, '-m', 'kineticloop.db.cli', 'test-unit'],
    'lint': [PYTHON, '-m', 'kineticloop.db.cli', 'lint'],
    'typecheck': [PYTHON, '-m', 'kineticloop.db.cli', 'typecheck'],
    'diff_clean': ['git', 'diff', '--check', BASE, TESTED],
    'candidate_isolation_and_regressions': [PYTHON, 'docs/exec-plans/evidence/HG-035/candidate_proof.py'],
}
key = sys.argv[1]
command = CHECKS[key]
ref = f'docs/exec-plans/evidence/HG-035/{key}-{TESTED[:7]}.log'
path = ROOT / ref
assert not path.exists(), 'never overwrite recorded check evidence'
env = os.environ.copy()
env['PYTHONPATH'] = str(ROOT / 'src')
env['PYTHONDONTWRITEBYTECODE'] = '1'
with path.open('w') as output:
    output.write('base_commit=' + BASE + '\ntested_commit=' + TESTED + '\ncommand=' + ' '.join(command) + '\n')
    output.flush()
    proc = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
    output.write('\nexit_code=' + str(proc.returncode) + '\n')
record = dict(check_id=key, command=' '.join(command), result='PASS' if proc.returncode == 0 else 'FAIL',
              evidence_ref=ref, tested_commit=TESTED, exit_code=proc.returncode)
(ROOT / f'docs/exec-plans/evidence/HG-035/{key}-{TESTED[:7]}.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps(record))
if proc.returncode:
    print(path.read_text()[-5000:])
raise SystemExit(proc.returncode)
