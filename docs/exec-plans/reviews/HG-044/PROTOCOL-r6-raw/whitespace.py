"""Preserve broad failure bytes; check all source outside own raw review records."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

out = Path('docs/exec-plans/reviews/HG-044/PROTOCOL-r6-raw')
base = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
head = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
records = []
for name, args in [('broad-whitespace', ['git', 'diff', '--check', base, head]),
                   ('source-whitespace', ['git', 'diff', '--check', base, head, '--', '.',
                                           ':(exclude)docs/exec-plans/reviews/HG-044/**'])]:
    run = subprocess.run(args, capture_output=True)
    (out / (name + '.stdout')).write_bytes(run.stdout)
    (out / (name + '.stderr')).write_bytes(run.stderr)
    locations = re.findall(r'^(.+):[0-9]+: trailing whitespace\.$', run.stdout.decode(), re.M)
    records.append(dict(name=name, argv=args, exit_code=run.returncode,
        stdout_sha256=hashlib.sha256(run.stdout).hexdigest(),
        stderr_sha256=hashlib.sha256(run.stderr).hexdigest(),
        warning_count=len(locations), affected_paths=sorted(set(locations))))
    if name == 'source-whitespace':
        assert run.returncode == 0
    else:
        assert run.returncode == 2 and locations
        assert all(p.startswith('docs/exec-plans/reviews/HG-044/') for p in locations)
        assert all(p.endswith(('.patch', '.log', '.stdout')) for p in locations)
(out / 'whitespace.json').write_text(json.dumps(records, indent=2) + '\n')
print('Source whitespace PASS; broad raw-review capture whitespace FAIL preserved')
