"""Capture real checks once at a clean committed HG050 revision."""
import concurrent.futures
import json
import os
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parents[4]
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)
out = Path('/private/tmp/hg050-checks-' + sha[:7])
out.mkdir(exist_ok=False)
env = dict(os.environ)
env['PATH'] = '/private/tmp/hg048-tools/bin:' + str(root / '.venv/bin') + ':' + env['PATH']
env['UV_CACHE_DIR'] = '/private/tmp/hg050-uv-cache'
commands = {
    'focused': 'uv run pytest tests/harness/test_local_gate.py -q',
    'harness': 'uv run kl test-harness --workers 2 --evidence-dir ' + str(out / 'harness') + ' -q',
    'unit': 'uv run kl test-unit -q --junitxml=' + str(out / 'unit.xml'),
    'authority': 'uv run kl check-harness', 'lint': 'uv run kl lint',
    'typecheck': 'uv run kl typecheck',
    'scope': 'uv run python docs/exec-plans/evidence/HG-050/scope_audit.py',
    'diff': 'git diff --check 034d6301316d0dade784a61b159c027b83fbce3a ' + sha,
}


def run(item):
    name, command = item
    start = time.time()
    with (out / (name + '.log')).open('wb') as log:
        result = subprocess.run(command.split(), cwd=root, env=env, stdout=log,
                                stderr=subprocess.STDOUT)
    record = {'check_id': name, 'command': command, 'exit_code': result.returncode,
              'tested_commit': sha, 'elapsed_seconds': time.time() - start,
              'log': str(out / (name + '.log'))}
    print(json.dumps(record), flush=True)
    return record


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    records = list(pool.map(run, commands.items()))
(out / 'RUN.json').write_text(json.dumps(records, indent=2) + '\n')
raise SystemExit(any(r['exit_code'] for r in records))
