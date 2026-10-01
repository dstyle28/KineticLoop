"""Exact prospective namespace changes only; governance feasibility, not KL019 PASS."""
import ast
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path.cwd()
base = 'eab2b305351cf3c504f74ac74868edc58d0a3430'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
spec = importlib.util.spec_from_file_location('proof_validator', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
print('tested_commit=' + head, flush=True)
print('merged_prerequisite=' + base, flush=True)
print('classification=CANDIDATE_ISOLATION_PROOF_ONLY; KL019 checks/product obligations=NOT_RUN', flush=True)
originals = {path: (root / path).read_bytes() for path in v.EXECUTION_FIXTURE_BASE_HASHES}
with tempfile.TemporaryDirectory(prefix='hg035-candidate-') as folder:
    clone = Path(folder) / 'KineticLoop'
    subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(root), str(clone)], check=True)
    subprocess.run(['git', 'checkout', '--quiet', '--detach', head], cwd=clone, check=True)
    for path, before in originals.items():
        assert before == subprocess.check_output(['git', 'show', base + ':' + path])
        after = v.execution_fixture_candidate(path, before)
        (clone / path).write_bytes(after)
        tests = lambda b: {n.name: ast.dump(n) for n in ast.parse(b).body
                          if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')}
        assert tests(before) == tests(after)
        assert v.execution_fixture_content_errors(path, before, after) == []
        print('BYTE_EXACT_CANDIDATE', path, 'semantic_test_functions=' + str(len(tests(before))), flush=True)
    assert subprocess.check_output(['git', 'diff', '--name-only'], cwd=clone, text=True).splitlines() == sorted(originals)
    tx = 'tests/db/test_transaction_interfaces.py'
    assert (clone / tx).read_bytes() == (root / tx).read_bytes()
    assert subprocess.check_output(['git', 'diff', '--name-only', base, head, '--', 'src', 'migrations', 'tests/db', 'tests/unit'], cwd=clone) == b''
    env = os.environ.copy()
    env['PYTHONPATH'] = str(clone / 'src') + os.pathsep + str(root / 'docs/exec-plans/evidence/HG-035')
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    subprocess.run([sys.executable, '-c', 'from pathlib import Path; from namespace_probe import prove; prove(Path.cwd())'], cwd=clone, env=env, check=True)
    short = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=clone, text=True).strip()
    sys.path.insert(0, str(root / 'docs/exec-plans/evidence/HG-035'))
    from namespace_probe import derived, validate_tx_launch
    target = derived(clone, short, 'tx')
    env.update(KINETICLOOP_KL024_FIXTURE_OWNER='KL-019', KINETICLOOP_KL025_FIXTURE_OWNER='KL-019',
               KINETICLOOP_KL022_COMPOSE_PROJECT=target.project_name,
               KINETICLOOP_KL022_DATABASE=target.database_name)
    validate_tx_launch(clone, short, env)
    subprocess.run([sys.executable, '-m', 'pytest', '-q', '-s', '-p', 'no:cacheprovider', '-p', 'isolation_plugin',
                    'tests/unit/workflow/test_planning.py', 'tests/db/test_planning.py',
                    'tests/unit/workflow/test_call_ledger.py', 'tests/db/test_call_ledger.py',
                    'tests/unit/persistence/test_transactions.py', 'tests/db/test_transaction_interfaces.py'],
                   cwd=clone, env=env, check=True)
    subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                    'tests/harness/test_protocol_execution_scope.py', 'tests/harness/test_call_ledger_scope.py'],
                   cwd=clone, env=env, check=True)
for path, before in originals.items():
    assert (root / path).read_bytes() == before
print('PASS exact future two-file namespace candidates and all called real prerequisite regressions', flush=True)
print('PASS unchanged transaction fixture/product source; selected owned resources destroyed; KL019 checks NOT_RUN', flush=True)
