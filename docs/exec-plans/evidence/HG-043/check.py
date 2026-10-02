"""Capture raw checks bound to one committed implementation revision, without overwriting."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
here = root / 'docs/exec-plans/evidence/HG-043'
base = '1099d85bd4aa76ec8221700e55b4e77a84479126'
tested = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
python = str(root / '.venv/bin/python')
checks = {
    'provenance': [python, '-m', 'pytest', '-q', 'tests/harness/test_review_evidence_provenance.py'],
    'harness': [python, '-m', 'kineticloop.db.cli', 'test-harness'],
    'unit': [python, '-m', 'kineticloop.db.cli', 'test-unit'],
    'lint': [python, '-m', 'kineticloop.db.cli', 'lint'],
    'typecheck': [python, '-m', 'kineticloop.db.cli', 'typecheck'],
    'validation': [python, '-m', 'kineticloop.db.cli', 'check-harness'],
    'replay': [python, str(here / 'replay.py')],
    'diff': ['git', 'diff', '--check', base, tested],
}
key = sys.argv[1]
path = here / f'{key}-{tested[:7]}.json'
assert not path.exists(), path
env = dict(os.environ, PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1')
run = subprocess.run(checks[key], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
raw = run.stdout
record = {'check_id': key, 'command': ' '.join(checks[key]),
          'tested_commit': tested, 'base_commit': base,
          'exit_code': run.returncode, 'result': 'PASS' if run.returncode == 0 else 'FAIL',
          'evidence_ref': str(path.relative_to(root)), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
          'raw_byte_count': len(raw), 'raw_utf8': raw.decode()}
path.write_text(json.dumps(record, indent=2) + '\n')
print(key, record['result'], tested, raw.decode()[-1200:] if run.returncode else '')
raise SystemExit(run.returncode)
