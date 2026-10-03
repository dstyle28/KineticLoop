#!/usr/bin/env python3
"""Administrator-installed local CI gate for explicitly admitted reviewed code.

Run the installed copy with python -I. Never run candidate controller code with
signer credentials. Privileged Docker is not a hostile-code security boundary.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


def module(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / (name + '.py'))
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


db_ci, db_policy, github_app = (module(name) for name in ('db_ci', 'db_policy', 'github_app'))

CONTEXT = 'local-db-gate'
SHA = re.compile(r'[0-9a-f]{40}')
ASSETS = ('local_gate.py', 'github_app.py', 'db_ci.py', 'db_policy.py',
          'db_ci_pytest.py', 'validate_harness.py', 'gate_validate.py', 'gate_pytest.py', 'local_db/Dockerfile',
          'local_db/entrypoint.sh')
HERE = Path(__file__).resolve().parent
WORKSPACE = '/workspace/KineticLoop'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed(config: dict[str, Any], here: Path = HERE) -> str:
    expected = config['controller_files']
    if set(expected) != set(ASSETS):
        raise ValueError('incomplete trusted controller installation')
    for name in ASSETS:
        path = here / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected[name]:
            raise ValueError('controller installation changed: ' + name)
    return hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()


def snapshot(app: Any, number: int) -> dict[str, Any]:
    config = app.config
    prefix = '/repos/' + config['repository']
    pr = app.request('GET', prefix + '/pulls/' + str(number))
    base = app.request('GET', prefix + '/git/ref/heads/master')['object']['sha']
    if (pr['state'] != 'open' or pr['base']['ref'] != 'master'
            or pr['base']['repo']['id'] != config['repository_id']
            or pr['head']['repo']['id'] != config['repository_id']):
        raise ValueError('only open same-repository master PRs are admitted')
    head = pr['head']['sha']
    if not SHA.fullmatch(base) or not SHA.fullmatch(head):
        raise ValueError('invalid live commit identity')
    return {'repository_id': config['repository_id'], 'pr': number, 'base': base, 'head': head}


def admit(path: Path, state: dict[str, Any], identity: str) -> None:
    github_app.private_file(path)
    value = json.loads(path.read_text())
    if (value.get('format') != 'kineticloop-local-admission-v1'
            or value.get('snapshot') != state or value.get('controller') != identity
            or value.get('trusted_code_reviewed') is not True):
        raise ValueError('missing exact revision/controller administrator admission')


def checked(argv: list[str], cwd: Path) -> str:
    return subprocess.check_output(argv, cwd=cwd, text=True, timeout=120).strip()


def gate_plan(base: str, head: str, full_db: bool, test_only: bool) -> list[tuple[str, list[str]]]:
    python = ['uv', 'run', '--no-sync', 'python']
    commands = [
        ('lint', [*python, '-m', 'ruff', 'check', '.']),
        ('typecheck', [*python, '-m', 'mypy', '--no-incremental']),
        ('unit', [*python, '-I', '/gate/tools/harness/gate_pytest.py', '-q', 'tests/unit', '-o', 'xfail_strict=true',
                  '--junitxml=/evidence/unit.xml']),
        ('harness', [*python, '-I', '/gate/tools/harness/gate_pytest.py', '-q', 'tests/harness', '-o', 'xfail_strict=true',
                     '--junitxml=/evidence/harness.xml']),
        ('merge_gate', [*python, '-I', '/gate/tools/harness/gate_validate.py',
                       *([] if test_only else ['--ci-pr-base', base, '--ci-pr-head', head])]),
    ]
    if full_db:
        # The host owns each command and observes its process exit. The candidate
        # runner/manifest is never invoked or accepted as execution attestation.
        for name, argv in db_ci.command_plan(Path('/evidence/run'), head)[2:]:
            if '-m' in argv and 'pytest' in argv:
                idx = argv.index('-m')
                argv[idx:idx + 2] = ['-I', '/gate/tools/harness/gate_pytest.py']
                idx = argv.index('-p')
                del argv[idx:idx + 2]
            commands.append((name, argv))
        commands.extend([
            ('destroy', ['uv', 'run', 'python', 'tools/db/verify.py', 'destroy']),
            ('peer_remove', ['git', 'worktree', 'remove', '--force', '/evidence/run-peer']),
        ])
    return commands


def artifact_tree(directory: Path) -> None:
    """Reject copied links/devices/oversized data before any host-side parsing."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('worker evidence must be a regular directory')
    total = 0
    for path in directory.rglob('*'):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_size > 20_000_000:
            raise ValueError('worker artifact is not a bounded regular file')
        total += info.st_size
        if total > 500_000_000:
            raise ValueError('worker artifact budget exceeded')


def cleanup_resource(argv: list[str]) -> bool:
    try:
        return subprocess.run(argv, capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def resource_exists(kind: str, name: str) -> bool:
    argv = ['docker', kind, 'ls', *(['-a'] if kind == 'container' else []), '--format', '{{.Name}}' if kind == 'volume' else '{{.Names}}']
    return name in subprocess.check_output(argv, text=True, timeout=120).splitlines()


def cleanup_owned(kind: str, name: str, owner: str) -> bool:
    """Handle uncertain create/start outcomes; only remove our exact labelled resource."""
    try:
        if not resource_exists(kind, name):
            return True
        item = json.loads(subprocess.check_output(
            ['docker', kind, 'inspect', name], text=True, timeout=120))[0]
        labels = item['Config']['Labels'] if kind == 'container' else item['Labels']
        if labels.get('kineticloop.owner') != owner:
            return False
        if not cleanup_resource(['docker', kind, 'rm', *(['-f', '-v'] if kind == 'container' else []), name]):
            return False
        return not resource_exists(kind, name)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return False


def run_worker(source: Path, head: str, base: str, full_db: bool, destination: Path,
               *, test_only: bool = False, here: Path = HERE) -> dict[str, Any]:
    db_ci.local_client_preflight()
    if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        raise ValueError('ambient Docker override forbidden')
    context = checked(['docker', 'context', 'show'], source)
    endpoint = checked(['docker', 'context', 'inspect', context, '--format',
                        '{{.Endpoints.docker.Host}}'], source)
    if not endpoint.startswith('unix:///'):
        raise ValueError('a local Docker Unix socket is required')
    name = 'kl-gate-' + uuid.uuid4().hex
    volume = name + '-data'
    record: dict[str, Any] = {'status': 'FAIL', 'head': head, 'base': base,
        'container': name, 'volume': volume, 'checks': [], 'full_database_required': full_db}
    container_created = volume_created = False
    plan = gate_plan(base, head, full_db, test_only)
    try:
        build = db_ci.run_capture(['docker', 'build', '-t', name, str(here / 'local_db')],
                                  destination, 'image_build', cwd=source, timeout=1200)
        record['checks'].append(build)
        if build['exit_code']:
            raise ValueError('trusted image build failed')
        image = json.loads(checked(['docker', 'image', 'inspect', name], source))[0]['Id']
        record['image'] = image
        if resource_exists('container', name) or resource_exists('volume', volume):
            raise ValueError('refusing pre-existing executor resource names')
        volume_created = container_created = True  # Reserved, including uncertain creation outcomes.
        checked(['docker', 'volume', 'create', '--label', 'kineticloop.owner=' + name, volume], source)
        checked(['docker', 'create', '--privileged', '--name', name,
                 '--mount', 'type=volume,source=' + volume + ',target=/var/lib/docker',
                 '--label', 'kineticloop.owner=' + name, image], source)
        checked(['docker', 'start', name], source)
        inspect = json.loads(checked(['docker', 'inspect', name], source))[0]
        record['mounts'] = db_ci.owned_mounts(inspect, volume)
        for _ in range(60):
            if subprocess.run(['docker', 'exec', name, 'docker', 'info'],
                              capture_output=True, timeout=10).returncode == 0:
                break
            time.sleep(1)
        else:
            raise ValueError('owned Docker daemon failed to start')
        for argv in (['docker', 'ps', '-aq'], ['docker', 'volume', 'ls', '-q']):
            if checked(['docker', 'exec', name, *argv], source):
                raise ValueError('owned Docker daemon is not empty')
        bundle = destination / 'source.bundle'
        checked(['git', 'bundle', 'create', str(bundle), '--all'], source)
        checked(['docker', 'cp', str(bundle), name + ':/source.bundle'], source)
        checked(['docker', 'exec', name, 'git', 'clone', '/source.bundle', WORKSPACE], source)
        checked(['docker', 'exec', '-w', WORKSPACE, name, 'git', 'checkout', '--detach', head], source)
        checked(['docker', 'exec', name, 'mkdir', '-p', '/gate/tools/harness', '/evidence/run'], source)
        for asset in ('validate_harness.py', 'db_ci_pytest.py', 'db_ci.py', 'gate_validate.py', 'gate_pytest.py'):
            checked(['docker', 'cp', str(here / asset), name + ':/gate/tools/harness/' + asset], source)
        prefix = ['docker', 'exec', '-w', WORKSPACE,
                  '-e', 'PYTHONPATH=/gate/tools/harness:' + WORKSPACE + ':' + WORKSPACE + '/src']
        sync = db_ci.run_capture([*prefix, name, 'uv', 'sync', '--locked'], destination,
                                  'dependency_sync', cwd=source, timeout=1200)
        record['checks'].append(sync)
        if sync['exit_code']:
            raise ValueError('dependency sync failed')
        for label, argv in plan:
            nodeids = '/evidence/run/' + ('collection.json' if label == 'collection' else 'execution.json')
            check = db_ci.run_capture([*prefix, '-e', 'KINETICLOOP_DB_CI_NODEIDS=' + nodeids,
                                       name, *argv], destination, label, cwd=source)
            record['checks'].append(check)
            if check['exit_code'] or check['interrupted']:
                raise ValueError('worker check failed: ' + label)
        checked(['docker', 'cp', name + ':/evidence', str(destination / 'worker')], source)
        artifact_tree(destination / 'worker')
        for label in ('unit', 'harness'):
            counts = db_ci.junit_counts(destination / 'worker' / (label + '.xml'))
            if counts['tests'] <= 0 or any(counts[key] for key in ('failures', 'errors', 'skipped')):
                raise ValueError('incomplete quality test execution: ' + label)
        if full_db:
            data = destination / 'worker/run'
            record['database'] = db_ci.validate_execution(data)
        record['status'] = 'PASS'
    finally:
        if container_created:
            if not (destination / 'worker').exists():
                cleanup_resource(['docker', 'cp', name + ':/evidence', str(destination / 'worker')])
            record['container_removed'] = cleanup_owned('container', name, name)
        else:
            record['container_removed'] = True
        if volume_created:
            record['volume_removed'] = cleanup_owned('volume', volume, name)
        else:
            record['volume_removed'] = True
        if not record['container_removed'] or not record['volume_removed']:
            record['status'] = 'FAIL'
        if (destination / 'worker').exists():
            artifact_tree(destination / 'worker')
        record['artifacts'] = {str(p.relative_to(destination)): digest(p)
            for p in destination.rglob('*') if p.is_file() and not p.is_symlink()
            and p.name != 'source.bundle'}
        db_ci.write_json(destination / 'worker-receipt.json', record)
    if record['status'] != 'PASS':
        raise ValueError('worker cleanup failed')
    return record


def publish_body(state: dict[str, Any], run_id: str, passed: bool, summary: str) -> dict[str, Any]:
    return {'name': CONTEXT, 'head_sha': state['head'], 'status': 'completed',
            'conclusion': 'success' if passed else 'failure', 'external_id': run_id,
            'completed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'output': {'title': 'Local gate passed' if passed else 'Local gate failed',
                       'summary': summary}}


def verify_check(result: dict[str, Any], app_id: int, head: str, check_id: int | None = None) -> None:
    if (result['app']['id'] != app_id or result['head_sha'] != head
            or result['name'] != CONTEXT or type(result['id']) is not int
            or (check_id is not None and result['id'] != check_id)):
        raise ValueError('published check identity mismatch')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--admission', type=Path, required=True)
    parser.add_argument('--pr', type=int, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--test-only', action='store_true', help='No publication; omit PR review gate')
    args = parser.parse_args()
    os.environ.clear()
    os.environ.update(HOME=str(Path.home()), PATH='/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin', TMPDIR='/private/tmp')
    github_app.private_file(args.config)
    config = json.loads(args.config.read_text())
    identity = installed(config)
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', config['repository'])
            or args.pr <= 0):
        raise ValueError('invalid repository/PR')
    destination = args.evidence_dir.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    # Only one controller run may use this installation at a time.
    with (args.config.parent / 'executor.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        app = github_app.App(config)
        state = snapshot(app, args.pr)
        admit(args.admission, state, identity)
        run_id = uuid.uuid4().hex
        check_id = None
        if not args.test_only:
            started = app.request('POST', '/repos/' + config['repository'] + '/check-runs',
                        {'name': CONTEXT, 'head_sha': state['head'], 'status': 'in_progress',
                         'external_id': run_id})
            verify_check(started, config['app_id'], state['head'])
            check_id = started['id']
        receipt: dict[str, Any] = {'format': 'kineticloop-local-gate-v1', 'run_id': run_id,
            'snapshot': state, 'controller': identity, 'status': 'FAIL', 'test_only': args.test_only}
        try:
            with tempfile.TemporaryDirectory(prefix='kl-gate-source-') as temp:
                source = Path(temp)
                checked(['git', 'clone', '--no-checkout', 'https://github.com/'
                         + config['repository'] + '.git', str(source)], source)
                checked(['git', 'fetch', 'origin', 'refs/pull/' + str(args.pr) + '/head'], source)
                checked(['git', 'merge-base', '--is-ancestor', state['base'], state['head']], source)
                receipt['tree'] = checked(['git', 'rev-parse', state['head'] + '^{tree}'], source)
                policy = db_policy.classify(source, state['base'], state['head'])
                receipt['policy'] = policy
                receipt['worker'] = run_worker(source, state['head'], state['base'],
                    bool(policy['full_database_required']), destination, test_only=args.test_only)
            if snapshot(app, args.pr) != state:
                raise ValueError('live base/head changed during execution')
            receipt['status'] = 'PASS'
        except Exception as error:
            receipt['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            if not args.test_only and receipt['status'] == 'PASS':
                if snapshot(app, args.pr) != state:
                    receipt['status'] = 'FAIL'
                    receipt['error'] = 'Live base/head changed before publication'
            db_ci.write_json(destination / 'receipt.json', receipt)
            if not args.test_only:
                passed = receipt['status'] == 'PASS'
                body = publish_body(state, run_id, passed, json.dumps({
                    'snapshot': state, 'controller': identity, 'receipt_sha256': digest(destination / 'receipt.json'),
                    'full_database_required': receipt.get('policy', {}).get('full_database_required'),
                    'status': receipt['status']}, sort_keys=True))
                body.pop('head_sha')
                result = app.request('PATCH', '/repos/' + config['repository'] + '/check-runs/' + str(check_id), body)
                verify_check(result, config['app_id'], state['head'], check_id)
                db_ci.write_json(destination / 'published-check.json', result)
    return 0 if receipt['status'] == 'PASS' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        sys.exit('local-gate: ' + str(error))
