"""Record affected HG056 repair executions without repeating the blocked full cycle."""
from __future__ import annotations

import concurrent.futures
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = '3ec7f7a38d974256a928c3687f63e4d90019e42b'
SPEC = importlib.util.spec_from_file_location('compact', ROOT / 'tools/harness/compact_evidence.py')
assert SPEC and SPEC.loader
ce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ce)


def main() -> int:
    revision = ce.git(ROOT, 'rev-parse', 'HEAD').decode().strip()
    assert not ce.git(ROOT, 'status', '--porcelain')
    scratch = Path('/private/tmp') / ('hg056-repair-' + revision + '-' + uuid.uuid4().hex[:8])
    scratch.mkdir()
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([
        str(ROOT / 'src'), '/private/tmp/hg054-dependencies']))
    versions = json.loads(subprocess.check_output([sys.executable, '-c',
        "import importlib.metadata,json; print(json.dumps({name: importlib.metadata.version(name) "
        "for name in ('pytest','pytest-xdist','execnet')}))"], cwd=ROOT, env=env))
    commands = [
        ('affected_harness', [sys.executable, '-m', 'kineticloop.cli', 'test-harness',
            '--workers', '2', '--evidence-dir', str(scratch / 'harness'), '-q', '-k',
            'test_compact_evidence or test_missing_blob_is_not_available_evidence_or_an_absent_path or hg056']),
        ('installed_decoder_isolation', [sys.executable, '-m', 'pytest',
            'tests/harness/test_local_gate.py', '-q']),
        ('scope', [sys.executable, 'docs/exec-plans/evidence/HG-056/verify_scope.py', '--base', BASE]),
        ('lint', [sys.executable, '-m', 'kineticloop.cli', 'lint']),
        ('typecheck', [sys.executable, '-m', 'kineticloop.cli', 'typecheck']),
        ('diff', ['git', 'diff', '--check', BASE, revision]),
    ]
    def run(item):
        check, args = item
        start = time.time()
        path = scratch / (check + '.log')
        with path.open('wb') as stream:
            result = subprocess.run(args, cwd=ROOT, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, check=False)
        raw = path.read_bytes()
        record = {'check_id': check, 'command': shlex.join(args), 'exit_code': result.returncode,
            'result': 'PASS' if result.returncode == 0 else 'FAIL',
            'seconds': round(time.time() - start, 3), 'stdout_path': str(path),
            'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest()}
        (scratch / (check + '.metadata.json')).write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record), flush=True)
        return record
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(run, commands))
    assert ce.git(ROOT, 'rev-parse', 'HEAD').decode().strip() == revision
    assert not ce.git(ROOT, 'status', '--porcelain')
    target = ROOT / 'docs/exec-plans/evidence/HG-056' / ('checks-repair-' + revision + '-' + scratch.name[-8:])
    target.mkdir()
    capture_errors = []
    def capture(path, name, command, exit_code):
        ref = str((target / name).relative_to(ROOT))
        try:
            ce.capture(ROOT, ref, path.read_bytes(), revision, command, exit_code, codec=ce.XZ_FORMAT)
            return {'name': name, 'evidence_ref': ref}
        except ValueError as error:
            raw = path.read_bytes()
            item = {'name': name, 'error': str(error), 'scratch': str(path),
                    'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest()}
            capture_errors.append(item)
            return item
    for record in records:
        captured = capture(Path(record['stdout_path']), record['check_id'] + '.json',
                           record['command'], record['exit_code'])
        record.update(captured)
    harness = next(record for record in records if record['check_id'] == 'affected_harness')
    artifacts = [capture(path, 'harness-' + path.name + '.json', harness['command'], harness['exit_code'])
                 for path in sorted((scratch / 'harness').iterdir()) if path.is_file()]
    payload = {'tested_commit': revision, 'base_commit': BASE, 'python': sys.executable,
        'python_version': sys.version, 'PYTHONPATH': env['PYTHONPATH'], 'versions': versions,
        'checks': records, 'harness_artifacts': artifacts, 'capture_errors': capture_errors,
        'scratch': str(scratch), 'scope': 'Affected repair checks, not a full-cycle or acceptance PASS',
        'not_rerun': ['known failing immutable KL036 compatibility', 'whole unit/harness/authority cycle'],
        'remaining': 'External oracle and proposed source-inspection integration remain BLOCKED; old failures unchanged'}
    (target / 'RUN.json').write_text(json.dumps(payload, indent=2) + '\n')
    print(str(target / 'RUN.json'), flush=True)
    return int(bool(capture_errors) or any(record['exit_code'] for record in records))


if __name__ == '__main__':
    raise SystemExit(main())
