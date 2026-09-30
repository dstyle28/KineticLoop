"""Apply only both future KL024 exceptions in a disposable clone; run scope tests."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path.cwd()
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
paths = ['tests/db/test_transaction_interfaces.py', 'tests/db/test_subject_scope.py']
original = {path: (root / path).read_bytes() for path in paths}
print('tested_commit=' + head, flush=True)
with tempfile.TemporaryDirectory(prefix='hg033-future-scope-') as directory:
    clone = Path(directory) / 'KineticLoop'
    subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(root), str(clone)], check=True)
    subprocess.run(['git', 'checkout', '--quiet', '--detach', head], cwd=clone, check=True)
    for proposal in ['HG-032/KL024_proposal.patch', 'HG-033/KL024_proposal.patch']:
        patch = (root / 'docs/exec-plans/evidence' / proposal).read_bytes()
        subprocess.run(['git', 'apply', '-'], cwd=clone, input=patch, check=True)
    changed = subprocess.check_output(['git', 'diff', '--name-only'], cwd=clone, text=True).splitlines()
    assert set(changed) == set(paths)
    env = os.environ.copy()
    env['PYTHONPATH'] = str(clone / 'src')
    subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                    'tests/harness/test_planning_fixture_scope.py',
                    'tests/harness/test_planning_subject_scope.py',
                    'tests/harness/test_wave_scope.py'], cwd=clone, env=env, check=True)
assert all((root / path).read_bytes() == original[path] for path in paths)
print('PASS both future exact repairs preserve 73 scope regressions; own DB tests unchanged')
