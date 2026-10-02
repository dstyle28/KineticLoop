"""Capture independent review runs, without altering implementation artifacts."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
head = '2896d2422999fdf8a2cbca75eb316798c015ad17'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == head
dest = root / 'docs/exec-plans/reviews/HG-043/GENERAL-raw'
python = str(root / '.venv/bin/python')
commands = {
    'audit': [python, str(dest / 'audit.py')],
    'focused': [python, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                'tests/harness/test_review_evidence_provenance.py', 'tests/harness/test_validator.py',
                '-k', 'provenance or integration or delayed_review or exact_tree_exception'],
    'replay': [python, str(root / 'docs/exec-plans/evidence/HG-043/replay.py')],
    'harness': [python, '-m', 'kineticloop.db.cli', 'check-harness'],
}
name = sys.argv[1]
output = dest / (name + '.json')
assert not output.exists()
env = dict(os.environ, PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1')
run = subprocess.run(commands[name], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
raw = run.stdout
result = {'reviewed_head_sha': head, 'review_type': 'GENERAL', 'command': commands[name],
          'exit_code': run.returncode, 'status': 'PASS' if run.returncode == 0 else 'FAIL',
          'raw_sha256': hashlib.sha256(raw).hexdigest(), 'raw_bytes': len(raw), 'raw_utf8': raw.decode()}
output.write_text(json.dumps(result, indent=2) + '\n')
print(name, result['status'], raw.decode()[-1800:] if name != 'replay' else str(len(raw)) + ' raw replay bytes')
raise SystemExit(run.returncode)
