"""HG066 fresh definitions, portable source and bounded component acceptance."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from verify_delivery import verify
E = Path(__file__).resolve().parent
R = E.parents[3]
B = '3768c1b4366677934cb952ef808343edcee4e438'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--tested', required=True)
    args = parser.parse_args()
    assert args.base == B
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=R, text=True).strip() == args.tested
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=R)
    delivery = verify()
    sys.path.insert(0, str(R))
    from tools.harness import validate_harness as v
    changed = subprocess.check_output(['git', 'diff', '--name-only', B, args.tested], cwd=R, text=True).splitlines()
    assert len(v.HG066_ALLOWED_PATTERNS) == 11
    assert all(v.matches(p, v.HG066_ALLOWED_PATTERNS) for p in changed)
    assert v.HG066_REQUIRED_CHECKS == {'definitions', 'validator', 'unit', 'harness', 'lint', 'typecheck', 'authority', 'diff'}
    scope = json.loads((E / 'SCOPE_CORRECTION.json').read_bytes())
    assert v.HG058_ALLOWED_PATTERNS == scope['original'] + ['tools/harness/local_gate.py']
    matrix = json.loads((E / 'CHECK_OWNERSHIP.json').read_bytes())
    assert v.HG058_AUTHOR_COMMANDS == {r['check_id']: r['command_template'] for r in matrix['author_required']}
    assert len(matrix['root_required']) == 19
    assert all(r['hard_prerequisite'] and not r['selected_checks_run'] and r['author_index_state'] == 'PENDING_EXTERNAL_OBSERVATION' for r in matrix['root_required'])
    for group in ('documents', 'machine_readable'):
        for item in json.loads((R / 'CURRENT_DOCUMENT_INDEX.json').read_bytes())[group]:
            assert hashlib.sha256((R / item['path']).read_bytes()).hexdigest() == item['sha256']
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=R).decode().split('\0')[:-1])
    for item in json.loads((R / 'HARNESS_DOCUMENT_MANIFEST.json').read_bytes())['files']:
        assert item['path'] in tracked
        assert item['path'] != 'docs/exec-plans/governance/HG-066.yaml'
    out = Path(tempfile.mkdtemp(prefix='hg066-definitions-', dir='/private/tmp'))
    print('definition_observations=' + str(out), flush=True)
    env = dict(os.environ, HG066_OBSERVATIONS=str(out), PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, str(E / 'run_definitions.py')], cwd=R, env=env)
    assert result.returncode == 0
    receipt = json.loads((out / 'FULL_RECEIPT.json').read_bytes())
    assert receipt['actual_cases'] == 833 and receipt['actual_phase_reports'] == 2499
    print(json.dumps({'base_commit': B, 'tested_commit': args.tested, 'delivery': delivery, 'definitions': 833, 'prospective': 677, 'preserved_v1': 156, 'bounded_observers': 5, 'observations': str(out), 'historical_execution': 'UNVERIFIED', 'runtime': 'NOT_RUN'}))

if __name__ == '__main__':
    main()
