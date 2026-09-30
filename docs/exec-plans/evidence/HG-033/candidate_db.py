"""Independent disposable source-clone proof of the exact two-expression candidate.

Not KL024 CI/task PASS. No repository DB test or production file is edited here.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path.cwd()
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
source = '4543b563259f5170370a0624b4542d392e528c85'
path = 'tests/db/test_subject_scope.py'
original = (root / path).read_bytes()
print('tested_commit=' + head, flush=True)
print('KL024_source_commit=' + source, flush=True)
print('classification=CANDIDATE_PROOF_ONLY; actual_KL024_CI=FAIL', flush=True)
with tempfile.TemporaryDirectory(prefix='hg033-candidate-db-') as directory:
    clone = Path(directory) / 'KineticLoop'
    subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(root), str(clone)], check=True)
    subprocess.run(['git', 'checkout', '--quiet', '--detach', source], cwd=clone, check=True)
    patch = (root / 'docs/exec-plans/evidence/HG-033/KL024_proposal.patch').read_bytes()
    subprocess.run(['git', 'apply', '-'], cwd=clone, input=patch, check=True)
    changed = subprocess.check_output(['git', 'diff', '--name-only'], cwd=clone, text=True).splitlines()
    assert changed == [path]
    env = os.environ.copy()
    env['PYTHONPATH'] = str(clone / 'src')
    # Lifecycle uses the disposable clone's unique path hash; no 88b8/kl055 DB reuse.
    cleanup = "from pathlib import Path; from kineticloop.db.lifecycle import DatabaseLifecycle; "
    cleanup += "life=DatabaseLifecycle(Path.cwd()); print(life.namespace); life.destroy()"
    try:
        subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                        path + '::test_populated_downgrade_fails_before_guard_or_acl_changes'],
                       cwd=clone, env=env, check=True)
    finally:
        subprocess.run([sys.executable, '-c', cleanup], cwd=clone, env=env, check=True)
assert (root / path).read_bytes() == original
print('PASS exact candidate exercised all named rollback/guard/ACL/namespace/binding oracles')
print('PASS only disposable clone/database changed and cleaned; actual KL024 CI remains FAIL')
