"""Lossless task-owned evidence. No archive extraction or ambient Git fallback."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLAIN_LIMIT = 256 * 1024
STORED_LIMIT = 8 * 1024 * 1024
RAW_LIMIT = 64 * 1024 * 1024
TOTAL_LIMIT = 16 * 1024 * 1024
MARKER = 'kineticloop_evidence'
FORMAT = 'gzip-v1'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized(path: str) -> bool:
    return (isinstance(path, str) and bool(path) and '\\' not in path and '\0' not in path
            and all(p not in ('', '.', '..') for p in path.split('/')))


def owner(path: str) -> str:
    if not normalized(path):
        raise ValueError('evidence-path')
    match = re.match(r'^docs/exec-plans/(?:evidence|reviews)/((?:HG|KL)-[0-9]{3}[A-Z]?)/', path)
    if not match:
        raise ValueError('evidence-owner')
    return '/'.join(path.split('/')[:4])


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if result.returncode:
        raise ValueError('evidence-git:' + result.stderr.decode(errors='replace').strip())
    return result.stdout


def blob(root: Path, path: str, revision: str | None, limit: int | None = None) -> bytes:
    if not normalized(path):
        raise ValueError('evidence-path')
    if revision is None:
        target = root / path
        if any(p.is_symlink() for p in [target, *target.parents]) or not target.is_file():
            raise ValueError('evidence-regular-file')
        if root.resolve() not in target.resolve().parents:
            raise ValueError('evidence-path')
        size = target.stat().st_size
        if limit is not None and size > limit:
            raise ValueError(f'evidence-size:{size}>{limit}')
        return target.read_bytes()
    commit = git(root, 'rev-parse', '--verify', '--end-of-options', revision + '^{commit}')
    revision = commit.decode().strip()
    entry = [e for e in git(root, 'ls-tree', '-z', revision, '--', path).split(b'\0')
             if e and e.split(b'\t', 1)[1] == path.encode()]
    if len(entry) != 1:
        raise ValueError('evidence-missing')
    mode, kind, oid = entry[0].split(b'\t', 1)[0].split()
    if mode not in (b'100644', b'100755') or kind != b'blob':
        raise ValueError('evidence-regular-blob')
    size = int(git(root, 'cat-file', '-s', oid.decode()))
    if limit is not None and size > limit:
        raise ValueError(f'evidence-size:{size}>{limit}')
    return git(root, 'cat-file', 'blob', oid.decode())


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('evidence-duplicate-key')
        result[key] = value
    return result


def envelope(data: bytes) -> dict[str, Any] | None:
    # Historical logs/JSON remain byte-preserving plain references.
    if b'"kineticloop_evidence"' not in data:
        return None
    if len(data) > PLAIN_LIMIT:
        raise ValueError('evidence-envelope-size')
    try:
        value = json.loads(data, object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) and MARKER in value else None


def read(root: Path, path: str, revision: str | None, *, tested: str | None = None,
         command: str | None = None, exit_code: int | None = None) -> bytes:
    data = blob(root, path, revision)
    manifest = envelope(data) if path.endswith('.json') else None
    if manifest is None:
        return data
    fields = {MARKER, 'payload', 'stored_sha256', 'stored_bytes', 'raw_sha256', 'raw_bytes',
              'tested_commit', 'command', 'exit_code', 'timestamp', 'test_counts'}
    if (len(data) > PLAIN_LIMIT or set(manifest) != fields or manifest[MARKER] != FORMAT
            or not re.fullmatch(r'[0-9a-f]{40}', str(manifest['tested_commit']))
            or not isinstance(manifest['command'], str) or not manifest['command']
            or type(manifest['exit_code']) is not int
            or not isinstance(manifest['timestamp'], (str, type(None)))
            or not isinstance(manifest['test_counts'], dict)
            or any(not isinstance(k, str) or type(v) is not int or v < 0
                   for k, v in manifest['test_counts'].items())):
        raise ValueError('evidence-envelope')
    for field, maximum in [('stored_bytes', STORED_LIMIT), ('raw_bytes', RAW_LIMIT)]:
        if type(manifest[field]) is not int or not 0 <= manifest[field] <= maximum:
            raise ValueError('evidence-size')
    for field in ('stored_sha256', 'raw_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}', str(manifest[field])):
            raise ValueError('evidence-hash')
    expected = str(Path(path).parent / (manifest['raw_sha256'] + '.gz'))
    if manifest['payload'] != expected or owner(path) != owner(expected):
        raise ValueError('evidence-payload-owner-or-name')
    if tested is not None and manifest['tested_commit'] != tested:
        raise ValueError('evidence-tested-revision')
    if command is not None and manifest['command'] != command:
        raise ValueError('evidence-command')
    if exit_code is not None and manifest['exit_code'] != exit_code:
        raise ValueError('evidence-exit-code')
    resolved_tested = git(root, 'rev-parse', '--verify', '--end-of-options',
                         manifest['tested_commit'] + '^{commit}').decode().strip()
    if resolved_tested != manifest['tested_commit']:
        raise ValueError('evidence-tested-revision')
    if revision is not None:
        git(root, 'merge-base', '--is-ancestor', resolved_tested, revision)
    stored = blob(root, expected, revision, STORED_LIMIT)
    if len(stored) != manifest['stored_bytes'] or digest(stored) != manifest['stored_sha256']:
        raise ValueError('evidence-stored-integrity')
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = decoder.decompress(stored, manifest['raw_bytes'] + 1)
    except zlib.error as ex:
        raise ValueError('evidence-gzip') from ex
    if (len(raw) != manifest['raw_bytes'] or not decoder.eof or decoder.unused_data
            or decoder.unconsumed_tail or digest(raw) != manifest['raw_sha256']):
        raise ValueError('evidence-raw-integrity-or-bound')
    return raw


def capture(root: Path, path: str, raw: bytes, tested: str, command: str, exit_code: int,
            timestamp: str | None = None) -> dict:
    owner(path)
    if (not isinstance(command, str) or not command or type(exit_code) is not int
            or not re.fullmatch(r'[0-9a-f]{40}', tested)
            or git(root, 'rev-parse', '--verify', '--end-of-options',
                   tested + '^{commit}').decode().strip() != tested):
        raise ValueError('capture-command-or-tested-revision')
    if not path.endswith('.json') or len(raw) > RAW_LIMIT:
        raise ValueError('capture-json-path-or-raw-limit')
    stored = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(stored) > STORED_LIMIT:
        raise ValueError('capture-stored-limit: split real executions, never truncate')
    target = root / path
    payload = target.parent / (digest(raw) + '.gz')
    # Check every component before writing; never follow task-directory symlinks.
    if any(p.is_symlink() for p in [target, payload, *target.parents]):
        raise ValueError('capture-symlink')
    if target.exists():
        raise ValueError('capture-existing-envelope')
    target.parent.mkdir(parents=True, exist_ok=True)
    if payload.exists() and payload.read_bytes() != stored:
        raise ValueError('capture-existing-payload')
    counts = {kind: int(count) for count, kind in re.findall(
        r'\b([0-9]+) (passed|failed|skipped|errors?|deselected|xfailed|xpassed)\b',
        raw.decode(errors='replace'))}
    record = {MARKER: FORMAT, 'payload': str(payload.relative_to(root)),
              'stored_sha256': digest(stored), 'stored_bytes': len(stored),
              'raw_sha256': digest(raw), 'raw_bytes': len(raw), 'tested_commit': tested,
              'command': command, 'exit_code': exit_code, 'timestamp': timestamp,
              'test_counts': counts}
    new_payload = not payload.exists()
    payload.write_bytes(stored)
    target.write_text(json.dumps(record, indent=2) + '\n')
    try:
        read(root, path, None, tested=tested, command=command)
    except (ValueError, OSError):
        target.unlink()
        if new_payload:
            payload.unlink()
        raise
    return record


def embedded_raw(value: Any) -> bool:
    if isinstance(value, dict):
        return 'raw_utf8' in value or any(embedded_raw(v) for v in value.values())
    return isinstance(value, list) and any(embedded_raw(v) for v in value)


def audit(root: Path, base: str, head: str, identity: str) -> dict:
    if not re.fullmatch(r'(?:HG|KL)-[0-9]{3}[A-Z]?', identity):
        raise ValueError('budget-identity')
    base, head = [git(root, 'rev-parse', '--verify', '--end-of-options',
                      rev + '^{commit}').decode().strip() for rev in (base, head)]
    paths = git(root, 'diff', '--no-renames', '--name-only', '--diff-filter=ACMRT', '-z',
                base, head, '--').decode().split('\0')[:-1]
    prefixes = [f'docs/exec-plans/{kind}/{identity}/' for kind in ('evidence', 'reviews')]
    paths = sorted(p for p in paths if any(p.startswith(prefix) for prefix in prefixes))
    errors: list[str] = []
    total = 0
    payloads: set[str] = set()
    bulk: dict[str, str] = {}
    for path in paths:
        try:
            total += int(git(root, 'cat-file', '-s', head + ':' + path))
            data = blob(root, path, head, STORED_LIMIT if path.endswith('.gz') else PLAIN_LIMIT)
            if path.endswith('.gz'):
                continue
            if Path(path).name == 'complete-diff.patch':
                raise ValueError('full-diff-copy: record base/head instead')
            manifest = envelope(data) if path.endswith('.json') else None
            if manifest is not None:
                raw = read(root, path, head)
                payloads.add(manifest['payload'])
            else:
                raw = data
                if path.endswith('.json') and embedded_raw(json.loads(data, object_pairs_hook=unique)):
                    raise ValueError('embedded-raw_utf8: capture raw once')
            if len(raw) >= 16 * 1024:
                key = digest(raw)
                if key in bulk and (manifest is None or bulk[key] != manifest['payload']):
                    raise ValueError('duplicate-bulk:' + bulk[key])
                bulk[key] = manifest['payload'] if manifest is not None else path
        except (ValueError, OSError, UnicodeError) as ex:
            errors.append(path + ':' + str(ex))
    for path in paths:
        if path.endswith('.gz') and path not in payloads:
            errors.append(path + ':unreferenced-payload')
    if total > TOTAL_LIMIT:
        errors.append(f'PR-evidence-total:{total}>{TOTAL_LIMIT}')
    return {'identity': identity, 'base': base, 'head': head, 'stored_bytes': total,
            'files': len(paths), 'errors': sorted(set(errors)),
            'remedy': 'python tools/harness/compact_evidence.py capture --help'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    commands = parser.add_subparsers(dest='action', required=True)
    cap = commands.add_parser('capture', help='Capture exact existing command output once')
    cap.add_argument('--input', type=Path, required=True)
    cap.add_argument('--output', required=True)
    cap.add_argument('--tested', required=True)
    cap.add_argument('--command', required=True)
    cap.add_argument('--exit-code', required=True, type=int)
    cap.add_argument('--timestamp', default=datetime.now(timezone.utc).isoformat())
    retrieve = commands.add_parser('read', help='Write validated exact raw bytes to stdout')
    retrieve.add_argument('path')
    retrieve.add_argument('--revision', required=True)
    budget = commands.add_parser('audit')
    budget.add_argument('--base', required=True)
    budget.add_argument('--head', required=True)
    budget.add_argument('--identity', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'capture':
            if args.input.stat().st_size > RAW_LIMIT:
                raise ValueError('capture-raw-limit')
            result = capture(args.root, args.output, args.input.read_bytes(), args.tested,
                             args.command, args.exit_code, args.timestamp)
            print(json.dumps(result, indent=2))
        elif args.action == 'read':
            sys.stdout.buffer.write(read(args.root, args.path, args.revision))
        else:
            result = audit(args.root, args.base, args.head, args.identity)
            print(json.dumps(result, indent=2))
            return int(bool(result['errors']))
    except (ValueError, OSError) as ex:
        print(str(ex), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
