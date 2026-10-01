"""Exercise the exact future fixture patch in a disposable merged-source clone.

This is governance candidate/isolation evidence, never KL025 task/product PASS.
"""
import ast
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path.cwd()
base = 'ff57a80feebd4e539f9af277e0dcb26d942bc3e0'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
path = 'tests/db/test_planning.py'
original = (root / path).read_bytes()
assert original == subprocess.check_output(['git', 'show', base + ':' + path])
print('tested_commit=' + head, flush=True)
print('merged_prerequisite=' + base, flush=True)
print('classification=CANDIDATE_ISOLATION_PROOF_ONLY; KL025 checks=NOT_RUN', flush=True)
with tempfile.TemporaryDirectory(prefix='hg034-candidate-') as folder:
    clone = Path(folder) / 'KineticLoop'
    subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(root), str(clone)], check=True)
    subprocess.run(['git', 'checkout', '--quiet', '--detach', head], cwd=clone, check=True)
    patch = root / 'docs/exec-plans/evidence/HG-034/planning_namespace.patch'
    subprocess.run(['git', 'apply', str(patch)], cwd=clone, check=True)
    assert subprocess.check_output(['git', 'diff', '--name-only'], cwd=clone, text=True).splitlines() == [path]
    before = ast.parse(original.decode())
    after = ast.parse((clone / path).read_text())
    tests = lambda tree: {n.name: ast.dump(n) for n in tree.body
                          if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')}
    assert tests(before) == tests(after) and len(tests(before)) == 6
    env = os.environ.copy()
    env['PYTHONPATH'] = str(clone / 'src') + os.pathsep + str(root / 'docs/exec-plans/evidence/HG-034')
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    # The probe imports the candidate from the clone and makes no lifecycle calls.
    subprocess.run([sys.executable, '-c', 'from pathlib import Path; from namespace_probe import prove; prove(Path.cwd())'],
                   cwd=clone, env=env, check=True)
    env['KINETICLOOP_KL024_FIXTURE_OWNER'] = 'KL-025'
    short = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=clone, text=True).strip()
    env['KINETICLOOP_KL022_COMPOSE_PROJECT'] = 'kineticloop-kl025-reg-' + short
    env['KINETICLOOP_KL022_DATABASE'] = 'kineticloop_kl025_reg_' + short
    subprocess.run([sys.executable, '-m', 'pytest', '-q', '-s', '-p', 'no:cacheprovider', '-p', 'isolation_plugin',
                    'tests/unit/workflow/test_planning.py', 'tests/db/test_planning.py',
                    'tests/db/test_transaction_interfaces.py', 'tests/unit/persistence/test_transactions.py'],
                   cwd=clone, env=env, check=True)
    # The complete-file guard remains valid after the future exact patch, using
    # immutable Git baseline bytes rather than the just-adapted current fixture.
    subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                    'tests/harness/test_call_ledger_scope.py'], cwd=clone, env=env, check=True)
assert (root / path).read_bytes() == original
print('PASS six planning oracles byte/AST unchanged; all called regressions and future scope checks passed', flush=True)
print('PASS disposable exact candidate only; own fixture/product unchanged; owned resources destroyed', flush=True)
