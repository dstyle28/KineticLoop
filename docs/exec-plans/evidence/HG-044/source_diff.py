"""Check source whitespace while preserving literal independent review diff captures."""
import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
base = 'fa729ca4bcca0f2c2e7a2aa0601890d1356b8842'
tested = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
command = ['git', 'diff', '--check', base, tested, '--', '.',
           ':(exclude)docs/exec-plans/reviews/HG-044/**']
run = subprocess.run(command, capture_output=True)
raw = run.stdout + run.stderr
path = root / f'docs/exec-plans/evidence/HG-044/source_diff-{tested[:7]}.json'
assert not path.exists()
path.write_text(json.dumps(dict(check_id='source_diff', command=' '.join(command),
    tested_commit=tested, base_commit=base, exit_code=run.returncode,
    result='PASS' if run.returncode == 0 else 'FAIL', evidence_ref=str(path.relative_to(root)),
    raw_sha256=hashlib.sha256(raw).hexdigest(), raw_byte_count=len(raw), raw_utf8=raw.decode()),
    indent=2) + '\n')
print('SOURCE_DIFF', 'PASS' if run.returncode == 0 else 'FAIL', tested)
raise SystemExit(run.returncode)
