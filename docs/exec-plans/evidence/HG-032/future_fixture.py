"""Prove harness regressions survive the exact future KL024 fixture-only repair."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path.cwd()
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
fixture = root / 'tests/db/test_transaction_interfaces.py'
original = fixture.read_bytes()
print('tested_commit=' + head, flush=True)
with tempfile.TemporaryDirectory(prefix='hg032-future-fixture-') as directory:
    clone = Path(directory) / 'KineticLoop'
    subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(root), str(clone)],
                   check=True)
    subprocess.run(['git', 'checkout', '--quiet', '--detach', head], cwd=clone, check=True)
    patch = (root / 'docs/exec-plans/evidence/HG-032/KL024_proposal.patch').read_bytes()
    subprocess.run(['git', 'apply', '-'], cwd=clone, input=patch, check=True)
    changed = subprocess.check_output(['git', 'diff', '--name-only'], cwd=clone, text=True)
    assert changed.strip() == 'tests/db/test_transaction_interfaces.py'
    env = os.environ.copy()
    env['PYTHONPATH'] = str(clone / 'src')
    subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                    'tests/harness/test_planning_fixture_scope.py',
                    'tests/harness/test_wave_scope.py'], cwd=clone, env=env, check=True)
assert fixture.read_bytes() == original
print('PASS future authorized fixture passes all 49 harness scope regressions in disposable clone')
print('PASS governance database-test fixture remains byte-identical; temporary clone removed')
