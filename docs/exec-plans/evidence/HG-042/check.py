"""Capture raw final checks against a committed tested SHA; never overwrite."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
here = root / 'docs/exec-plans/evidence/HG-042'
base = '93b38f20a3f3d71206515fb0f4d852f5b0b6d344'
tested = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
python = str(root / '.venv/bin/python')
checks = {
    'boundary_shadow': [python, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests/harness/test_m3_boundary_shadow_scope.py'],
    'scope': [python, str(here / 'audit.py')],
    'integrations': [python, str(here / 'integrate.py')],
    'harness': [python, '-m', 'kineticloop.db.cli', 'test-harness'],
    'unit': [python, '-m', 'kineticloop.db.cli', 'test-unit'],
    'lint': [python, '-m', 'kineticloop.db.cli', 'lint'],
    'typecheck': [python, '-m', 'kineticloop.db.cli', 'typecheck'],
    'validation': [python, '-m', 'kineticloop.db.cli', 'check-harness'],
    'diff': ['git', 'diff', '--check', base, tested],
}
key = sys.argv[1]
path = here / f'{key}-{tested[:7]}.json'
assert not path.exists(), path
env = dict(os.environ, PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1')
run = subprocess.run(checks[key], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
raw = run.stdout
record = {'check_id': key, 'command': ' '.join(checks[key]), 'tested_commit': tested,
          'base_commit': base, 'exit_code': run.returncode,
          'result': 'PASS' if run.returncode == 0 else 'FAIL', 'evidence_ref': str(path.relative_to(root)),
          'raw_sha256': hashlib.sha256(raw).hexdigest(), 'raw_byte_count': len(raw), 'raw_utf8': raw.decode()}
path.write_text(json.dumps(record, indent=2) + '\n')
print(key, record['result'], tested, raw.decode()[-1600:] if run.returncode else '')
raise SystemExit(run.returncode)
