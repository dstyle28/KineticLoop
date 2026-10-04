"""Execute immutable HG054 checks; preserve exact outputs, failures and positive cases."""
from __future__ import annotations

import concurrent.futures
import importlib.util
import importlib.metadata
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = 'af09be228fbc89d074b6e863c83e1fdda343d55b'
SPEC = importlib.util.spec_from_file_location('compact', ROOT / 'tools/harness/compact_evidence.py')
assert SPEC and SPEC.loader
ce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ce)


def main() -> int:
    revision = ce.git(ROOT, 'rev-parse', 'HEAD').decode().strip()
    assert not ce.git(ROOT, 'status', '--porcelain')
    temp = Path('/private/tmp') / ('hg054-checks-' + revision + '-' + uuid.uuid4().hex[:8])
    temp.mkdir()
    python = sys.executable
    dependencies = Path('/private/tmp/hg054-dependencies')
    assert dependencies.is_dir(), 'task-owned cached pytest-xdist dependencies required'
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / 'src'), str(dependencies)]))
    commands = [
        ('codec_security_and_budget', [python, '-m', 'pytest', 'tests/harness/test_compact_evidence.py', '-q']),
        ('bound_reader_regressions', [python, '-m', 'pytest', 'tests/harness/test_review_evidence_provenance.py', 'tests/harness/test_m3_milestone_closure.py', 'tests/harness/test_validator.py', '-q']),
        ('installed_decoder_isolation', [python, '-m', 'pytest', 'tests/harness/test_local_gate.py', '-q']),
        ('representative_roundtrip', [python, 'docs/exec-plans/evidence/HG-054/measure_codec.py']),
        ('scope', [python, 'docs/exec-plans/evidence/HG-054/verify_scope.py']),
        ('unit', [python, '-m', 'kineticloop.cli', 'test-unit', '-q', '--junitxml=' + str(temp / 'unit.xml')]),
        ('harness', [python, '-m', 'kineticloop.cli', 'test-harness', '--workers', '2', '--evidence-dir', str(temp / 'harness'), '-q']),
        ('lint', [python, '-m', 'kineticloop.cli', 'lint']),
        ('typecheck', [python, '-m', 'kineticloop.cli', 'typecheck']),
        ('authority', [python, '-m', 'kineticloop.cli', 'check-harness']),
        ('diff', ['git', 'diff', '--check', BASE, revision]),
    ]
    def run(entry):
        check_id, arguments = entry
        start = time.time()
        log = temp / (check_id + '.log')
        with log.open('wb') as stream:
            result = subprocess.run(arguments, cwd=ROOT, env=environment, stdout=stream,
                                    stderr=subprocess.STDOUT, check=False)
        print(f'{check_id}: exit={result.returncode} seconds={time.time() - start:.1f}', flush=True)
        return {'check_id': check_id, 'command': shlex.join(arguments),
                'result': 'PASS' if result.returncode == 0 else 'FAIL',
                'exit_code': result.returncode, 'seconds': round(time.time() - start, 3),
                'log': str(log)}
    # No source mutations until all revision-bound executions finish.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(run, commands))
    assert ce.git(ROOT, 'rev-parse', 'HEAD').decode().strip() == revision
    assert not ce.git(ROOT, 'status', '--porcelain')
    directory = ROOT / 'docs/exec-plans/evidence/HG-054' / ('checks-' + revision + '-' + temp.name[-8:])
    directory.mkdir()
    for record in records:
        target = directory / (record['check_id'] + '.json')
        ref = str(target.relative_to(ROOT))
        ce.capture(ROOT, ref, Path(record['log']).read_bytes(), revision,
                   record['command'], record['exit_code'], codec=ce.FORMAT)
        record['evidence_ref'] = ref
    # Collection identities, actual pytest phases/counts/JUnit and harness manifest
    # supplement stdout; these are captures from real executions, never a new run.
    harness = next(r for r in records if r['check_id'] == 'harness')
    for artifact in sorted((temp / 'harness').glob('*')):
        if artifact.is_file():
            ce.capture(ROOT, str((directory / ('harness-' + artifact.name + '.json')).relative_to(ROOT)),
                       artifact.read_bytes(), revision, harness['command'], harness['exit_code'])
    if (temp / 'unit.xml').exists():
        unit = next(r for r in records if r['check_id'] == 'unit')
        ce.capture(ROOT, str((directory / 'unit-junit.xml.json').relative_to(ROOT)),
                   (temp / 'unit.xml').read_bytes(), revision, unit['command'], unit['exit_code'])
    (directory / 'RUN.json').write_text(json.dumps({'tested_commit': revision, 'protected_base': BASE,
        'python': python, 'python_version': sys.version, 'PYTHONPATH': environment['PYTHONPATH'],
        'versions': {name: importlib.metadata.version(name) for name in ('pytest', 'pytest-xdist', 'execnet')},
        'checks': records, 'scratch': str(temp), 'scope': 'HG054 developer checks; App/fullDB NOT_RUN'}, indent=2) + '\n')
    print(str(directory / 'RUN.json'), flush=True)
    return int(any(record['exit_code'] != 0 for record in records))


if __name__ == '__main__':
    raise SystemExit(main())
