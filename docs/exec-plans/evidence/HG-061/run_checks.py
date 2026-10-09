"""Run HG061's own checks once at a clean stable commit; retain real observations."""
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PYTHON = '/Users/davetian/Personal_Projects/KineticLoop/.venv/bin/python'
BASE = 'ebee712b591d14c165007cd3d56d89cb14ea1487'
TESTED = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
SCRATCH = Path('/private/tmp/hg061-author-' + TESTED[:12])
SCRATCH.mkdir(exist_ok=False)
ENV = dict(os.environ, PYTHONPATH=str(ROOT) + ':' + str(ROOT / 'src')
           + ':/private/tmp/kl080-uv-cache/archive-v0/pMDaJUI6sj_futnY'
           + ':/private/tmp/kl080-uv-cache/archive-v0/_eUbZQqhbuQIXsBR')
CHECKS = {
    'definitions': [PYTHON, 'docs/exec-plans/evidence/HG-061/verify_definitions.py', '--base', BASE, '--tested', TESTED],
    'validator': [PYTHON, '-m', 'pytest', 'tests/harness/test_validator.py', '-q'],
    'unit': [PYTHON, '-m', 'kineticloop.cli', 'test-unit', '-q'],
    'harness': [PYTHON, '-m', 'kineticloop.cli', 'test-harness', '--workers', '2', '--evidence-dir', str(SCRATCH / 'harness-run'), '-q'],
    'lint': [PYTHON, '-m', 'kineticloop.cli', 'lint'],
    'typecheck': [PYTHON, '-m', 'kineticloop.cli', 'typecheck'],
    'authority': [PYTHON, '-m', 'kineticloop.cli', 'check-harness'],
    'diff': ['git', 'diff', '--check', BASE, TESTED],
}
state_path = Path('/private/tmp/hg061-worker-state.json')
state = json.loads(state_path.read_text())
state.update(T=TESTED, phase='eight checks running', scratch=str(SCRATCH), check_results={})
state_path.write_text(json.dumps(state, indent=2) + '\n')
for name, argv in CHECKS.items():
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == TESTED
    meta = {'check_id': name, 'base_commit': BASE, 'tested_commit': TESTED, 'argv': argv,
            'command': shlex.join(argv), 'environment': {'PYTHONPATH': ENV['PYTHONPATH']},
            'started_at_unix': time.time(), 'execution_state': 'STARTED', 'exit_code': None}
    env_run = ENV
    if name in ('validator', 'unit'):
        target = 'tests/harness/test_validator.py' if name == 'validator' else 'tests/unit'
        collection = [PYTHON, '-m', 'pytest', target, '--collect-only', '-q', '-p', 'tools.harness.parallel_observer']
        observer = {'KINETICLOOP_HARNESS_ROOT': str(ROOT), 'KINETICLOOP_HARNESS_WORKERS': '1'}
        collection_env = dict(observer, KINETICLOOP_HARNESS_OBSERVER=str(SCRATCH / (name + '-collection.json')))
        execution_env = dict(observer, KINETICLOOP_HARNESS_OBSERVER=str(SCRATCH / (name + '-execution.json')))
        meta.update(collection_argv=collection, collection_command=shlex.join(collection),
                    collection_environment=dict(meta['environment'], **collection_env))
        with (SCRATCH / (name + '-collection.log')).open('wb') as output:
            observed = subprocess.run(collection, cwd=ROOT, env=dict(ENV, **collection_env), stdout=output, stderr=subprocess.STDOUT)
        meta['collection_exit'] = observed.returncode
        argv = argv + ['-p', 'tools.harness.parallel_observer', '--junitxml=' + str(SCRATCH / (name + '-junit.xml'))]
        meta.update(argv=argv, command=shlex.join(argv), environment=dict(meta['environment'], **execution_env))
        env_run = dict(ENV, **execution_env)
        if observed.returncode:
            meta.update(execution_state='UNSTARTED', reason='collection failed')
            (SCRATCH / (name + '-command.json')).write_text(json.dumps(meta, indent=2) + '\n')
            state.update(phase='collection failed', failed_check=name)
            state_path.write_text(json.dumps(state, indent=2) + '\n')
            sys.exit(observed.returncode)
    (SCRATCH / (name + '-command.json')).write_text(json.dumps(meta, indent=2) + '\n')
    print('START', name, TESTED, flush=True)
    with (SCRATCH / (name + '.log')).open('wb') as output:
        result = subprocess.run(argv, cwd=ROOT, env=env_run, stdout=output, stderr=subprocess.STDOUT)
    meta.update(exit_code=result.returncode, elapsed_seconds=time.time() - meta['started_at_unix'], execution_state='COMPLETED')
    (SCRATCH / (name + '-command.json')).write_text(json.dumps(meta, indent=2) + '\n')
    state['check_results'][name] = {'exit_code': result.returncode, 'metadata': str(SCRATCH / (name + '-command.json'))}
    state_path.write_text(json.dumps(state, indent=2) + '\n')
    print('FINISH', name, result.returncode, round(meta['elapsed_seconds'], 2), flush=True)
    if result.returncode:
        state.update(phase='stable check cycle failed', failed_check=name)
        state['failures'].append({'T': TESTED, 'check': name, 'exit_code': result.returncode, 'scratch': str(SCRATCH)})
        state_path.write_text(json.dumps(state, indent=2) + '\n')
        print((SCRATCH / (name + '.log')).read_text()[-5000:], flush=True)
        sys.exit(result.returncode)
state['phase'] = 'eight actual checks completed; identity validation/capture pending'
state_path.write_text(json.dumps(state, indent=2) + '\n')
