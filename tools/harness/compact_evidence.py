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
    root = root.resolve()
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
    return _blob_at_commit(root, path, revision, limit)


def _blob_at_commit(root: Path, path: str, revision: str, limit: int | None) -> bytes:
    # Only internal callers that have already resolved the exact commit use this.
    if not normalized(path):
        raise ValueError('evidence-path')
    entry = [e for e in git(root, 'ls-tree', '-l', '-z', revision, '--', path).split(b'\0')
             if e and e.split(b'\t', 1)[1] == path.encode()]
    if len(entry) != 1:
        raise ValueError('evidence-missing')
    mode, kind, oid, size_text = entry[0].split(b'\t', 1)[0].split()
    if mode not in (b'100644', b'100755') or kind != b'blob':
        raise ValueError('evidence-regular-blob')
    size = int(size_text)
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


def reserved_ascii(data: bytes) -> bool:
    # Classification only: neither escape nor NUL normalization accepts bytes.
    data = re.sub(rb'\\u([0-9a-fA-F]{4})',
                  lambda m: bytes([int(m[1], 16)]) if int(m[1], 16) < 128
                  else m[0], data)
    return (b'"kineticloop_evidence"' in data or
            all(k in data for k in (b'"payload"', b'"stored_sha256"', b'"raw_sha256"')) or
            all(k in data for k in (b'"authorization"', b'"preserved_records"', b'"entries"')))


def envelope(data: bytes) -> dict[str, Any] | None:
    original = data
    original_bytes = len(data)
    encoding = json.detect_encoding(data)
    if encoding != 'utf-8':
        try:
            data = data.decode(encoding).encode('utf-8')
        except UnicodeError as ex:
            if reserved_ascii(original.replace(b'\0', b'')):
                raise ValueError('evidence-envelope-encoding') from ex
            # Replacement is only for classification, never accepted decoding.
            if envelope(data.decode(encoding, errors='replace').encode('utf-8')) is not None:
                raise ValueError('evidence-envelope-encoding') from ex
            return None
    # Storage fields identify damaged envelopes even if their marker is removed.
    if not reserved_ascii(data) and b'\\u' not in data:
        # A conflicting BOM/body can decode without error into NUL-interleaved
        # or wrong-endian text. Recognizable reserved bytes cannot fall back to
        # opaque evidence merely because that decoding hid their keys.
        if ((encoding != 'utf-8' or b'\0' in original)
                and reserved_ascii(original.replace(b'\0', b''))):
            raise ValueError('evidence-envelope-encoding')
        return None
    reserved = False
    def storage_pairs(pairs):
        nonlocal reserved
        value = unique(pairs)
        reserved = reserved or MARKER in value or {'payload', 'stored_sha256', 'raw_sha256'} <= set(value) or {'authorization', 'preserved_records', 'entries'} <= set(value)
        return value
    try:
        value = json.loads(data, object_pairs_hook=storage_pairs)
    except (UnicodeError, json.JSONDecodeError) as ex:
        # Decode ASCII key escapes only to classify a malformed storage record.
        # Opaque historical bytes containing unrelated \u text stay plain.
        if (reserved_ascii(data) or
                reserved_ascii(original.replace(b'\0', b''))):
            raise ValueError('evidence-envelope-json') from ex
        return None
    if isinstance(value, dict) and (MARKER in value or
                                   {'payload', 'stored_sha256', 'raw_sha256'} <= set(value) or
                                   {'authorization', 'preserved_records', 'entries'} <= set(value)):
        if original_bytes > PLAIN_LIMIT:
            raise ValueError('evidence-envelope-size')
        return value
    if reserved:
        raise ValueError('evidence-envelope-shape')
    return None


def read(root: Path, path: str, revision: str | None, *, tested: str | None = None,
         command: str | None = None, exit_code: int | None = None) -> bytes:
    if revision is not None:
        revision = git(root, 'rev-parse', '--verify', '--end-of-options',
                       revision + '^{commit}').decode().strip()
    data = (blob(root, path, None) if revision is None else
            _blob_at_commit(root, path, revision, None))
    manifest = envelope(data)
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
    stored = (blob(root, expected, None, STORED_LIMIT) if revision is None else
              _blob_at_commit(root, expected, revision, STORED_LIMIT))
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
    # Storage metadata is never command output, even inside a valid payload.
    # Classify once; nested/wrapped envelopes cannot supply a raw PASS oracle.
    if envelope(raw) is not None:
        raise ValueError('evidence-nested-envelope')
    return raw


def capture(root: Path, path: str, raw: bytes, tested: str, command: str, exit_code: int,
            timestamp: str | None = None) -> dict:
    root = root.resolve()
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



HISTORICAL_FORMAT = 'historical-gzip-v1'
MAPPING_FORMAT = 'historical-mapping-v1'
MAPPING_PATH = 'docs/exec-plans/evidence/KL-080/HISTORICAL_EVIDENCE_MAPPING.json'
MAPPING_SCHEMA = 'HISTORICAL_EVIDENCE_MAPPING.schema.json'


def historical_schema() -> dict:
    # This schema is indexed governance authority, not caller-supplied metadata.
    return json.loads((Path(__file__).resolve().parents[2] / MAPPING_SCHEMA).read_bytes(),
                      object_pairs_hook=unique)


def historical_originals() -> list[dict]:
    return [item['properties']['original']['const'] for item in
            historical_schema()['properties']['entries']['prefixItems']]


def historical_template() -> dict:
    schema = historical_schema()
    return {key: value['const'] for key, value in schema['properties'].items()
            if 'const' in value}


def archive_envelope(original: dict, raw: bytes) -> tuple[dict, bytes]:
    if original not in historical_originals() or len(raw) > RAW_LIMIT:
        raise ValueError('archive-authorization')
    if len(raw) != original['raw_bytes'] or digest(raw) != original['raw_sha256']:
        raise ValueError('archive-original-integrity')
    if envelope(raw) is not None:
        raise ValueError('archive-nested-storage')
    stored = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(stored) > STORED_LIMIT:
        raise ValueError('archive-stored-limit')
    record = {MARKER: HISTORICAL_FORMAT, 'original': original,
              'payload': str(Path(original['path']).parent / (digest(raw) + '.gz')),
              'raw_sha256': digest(raw), 'raw_bytes': len(raw),
              'stored_sha256': digest(stored), 'stored_bytes': len(stored)}
    return record, stored


def archive_mapping(root: Path, storage_revision: str) -> dict:
    """Build metadata only, after a normal committed forward storage change."""
    exact_commit(root, storage_revision)
    record = historical_template()
    record['entries'] = []
    for original in historical_originals():
        path = original['path']
        data = blob(root, path, storage_revision, PLAIN_LIMIT)
        manifest = envelope(data)
        if not manifest or manifest.get(MARKER) != HISTORICAL_FORMAT:
            raise ValueError('archive-envelope')
        storage = dict(revision=storage_revision, envelope_path=path,
                       envelope_sha256=digest(data), envelope_bytes=len(data),
                       payload=manifest['payload'], payload_sha256=manifest['stored_sha256'],
                       payload_bytes=manifest['stored_bytes'])
        record['entries'].append(dict(original=original, storage=storage))
    validate_archive(root, record, storage_revision, verify_originals=True)
    return record


def exact_commit(root: Path, revision: str) -> None:
    if (not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision)
            or git(root, 'rev-parse', '--verify', '--end-of-options',
                   revision + '^{commit}').decode().strip() != revision):
        raise ValueError('archive-revision')


def archive_original(root: Path, original: dict) -> bytes:
    """Original proof always reads the exact original regular Git blob."""
    if original not in historical_originals():
        raise ValueError('archive-original-authorization')
    exact_commit(root, original['revision'])
    path = original['path']
    raw = blob(root, path, original['revision'], RAW_LIMIT)
    oid = git(root, 'rev-parse', original['revision'] + ':' + path).decode().strip()
    if (oid != original['blob_id'] or digest(raw) != original['raw_sha256']
            or len(raw) != original['raw_bytes'] or envelope(raw) is not None):
        raise ValueError('archive-original-integrity')
    return raw


def validate_archive(root: Path, mapping: dict, revision: str, *,
                     verify_originals: bool = False) -> dict[str, bytes]:
    """Storage retrieval is separate from original-revision verification."""
    from jsonschema import Draft202012Validator
    issues = list(Draft202012Validator(historical_schema()).iter_errors(mapping))
    if issues:
        raise ValueError('archive-mapping-schema:' + issues[0].message)
    exact_commit(root, revision)
    if len({entry['storage']['revision'] for entry in mapping['entries']}) != 1:
        raise ValueError('archive-single-storage-revision')
    result = {}
    for entry in mapping['entries']:
        original, storage = entry['original'], entry['storage']
        path, stored_revision = original['path'], storage['revision']
        exact_commit(root, stored_revision)
        git(root, 'merge-base', '--is-ancestor', stored_revision, revision)
        expected = str(Path(path).parent / (original['raw_sha256'] + '.gz'))
        if storage['envelope_path'] != path or storage['payload'] != expected:
            raise ValueError('archive-storage-owner-or-path')
        data = blob(root, path, stored_revision, PLAIN_LIMIT)
        if (len(data) != storage['envelope_bytes']
                or digest(data) != storage['envelope_sha256']
                or blob(root, path, revision, PLAIN_LIMIT) != data):
            raise ValueError('archive-envelope-integrity')
        manifest = envelope(data)
        fields = {MARKER, 'original', 'payload', 'raw_sha256', 'raw_bytes',
                  'stored_sha256', 'stored_bytes'}
        if (manifest is None or set(manifest) != fields
                or manifest[MARKER] != HISTORICAL_FORMAT or manifest['original'] != original
                or manifest['payload'] != expected
                or manifest['raw_sha256'] != original['raw_sha256']
                or type(manifest['raw_bytes']) is not int
                or manifest['raw_bytes'] != original['raw_bytes']
                or type(manifest['stored_bytes']) is not int
                or manifest['stored_bytes'] != storage['payload_bytes']
                or manifest['stored_sha256'] != storage['payload_sha256']):
            raise ValueError('archive-envelope')
        stored = blob(root, expected, stored_revision, STORED_LIMIT)
        if (len(stored) != storage['payload_bytes']
                or digest(stored) != storage['payload_sha256']
                or blob(root, expected, revision, STORED_LIMIT) != stored):
            raise ValueError('archive-stored-integrity')
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            raw = decoder.decompress(stored, min(original['raw_bytes'], RAW_LIMIT) + 1)
        except zlib.error as ex:
            raise ValueError('archive-gzip') from ex
        if (original['raw_bytes'] > RAW_LIMIT or len(raw) != original['raw_bytes']
                or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
                or digest(raw) != original['raw_sha256']):
            raise ValueError('archive-raw-integrity-or-bound')
        if envelope(raw) is not None:
            raise ValueError('archive-nested-storage')
        if verify_originals:
            if archive_original(root, original) != raw:
                raise ValueError('archive-original-integrity')
            git(root, 'merge-base', '--is-ancestor', original['revision'], stored_revision)
            ref = original['execution_record']
            verify_historical_ref(root, ref, stored_revision)
        result[path] = raw
    if verify_originals:
        for ref in mapping['preserved_records']:
            verify_historical_ref(root, ref, revision)
    return result


def verify_historical_ref(root: Path, ref: dict, revision: str) -> None:
    exact_commit(root, ref['revision'])
    git(root, 'merge-base', '--is-ancestor', ref['revision'], revision)
    data = blob(root, ref['path'], ref['revision'], PLAIN_LIMIT)
    if len(data) != ref['bytes'] or digest(data) != ref['sha256']:
        raise ValueError('archive-preserved-record')


def read_archive(root: Path, path: str, revision: str) -> bytes:
    # May recover archive bytes when originals are unavailable; this is NEVER
    # evidence_exists, original proof, review certification or execution PASS.
    if path not in {item['path'] for item in historical_originals()}:
        raise ValueError('archive-unauthorized-path')
    exact_commit(root, revision)
    mapping = envelope(blob(root, MAPPING_PATH, revision, PLAIN_LIMIT))
    if mapping is None:
        raise ValueError('archive-mapping-missing')
    return validate_archive(root, mapping, revision)[path]


def archive_audit(root: Path, revision: str) -> tuple[list[str], set[str]]:
    """Fail closed on global orphan/duplicate/out-of-scope archival metadata."""
    paths = git(root, 'ls-tree', '-r', '--name-only', revision, '--',
                'docs/exec-plans/evidence/KL-080', 'docs/exec-plans/reviews/KL-080').decode().splitlines()
    errors, archives, mappings = [], set(), set()
    for path in paths:
        # Plain historical bulk can be large. Classification does not recover it.
        if path.endswith('.gz'):
            continue
        data = b''
        try:
            data = blob(root, path, revision)
            manifest = envelope(data)
            if manifest and manifest.get(MARKER) == HISTORICAL_FORMAT:
                archives.add(path)
            elif manifest and manifest.get(MARKER) == MAPPING_FORMAT:
                mappings.add(path)
        except ValueError as ex:
            # Existing invalid historical output is handled by its own bound
            # validator. Reserved archival content must never evade this audit.
            if b'historical-' in data:
                errors.append(path + ':' + str(ex))
    if not archives and not mappings:
        return errors, set()
    if mappings != {MAPPING_PATH} or archives != {x['path'] for x in historical_originals()}:
        errors.append('archive-exact-inventory-or-mapping')
        return errors, set()
    try:
        mapping = envelope(blob(root, MAPPING_PATH, revision, PLAIN_LIMIT))
        if mapping is None:
            raise ValueError('archive-mapping')
        validate_archive(root, mapping, revision, verify_originals=True)
        # Existing non-migrated evidence remains byte-identical. New captures
        # may be added, but never replace or delete historical inputs.
        preservation_revision = mapping['preserved_records'][1]['revision']
        preserved = git(root, 'diff', '--no-renames', '--name-only', '--diff-filter=MDT',
                        preservation_revision, revision, '--',
                        'docs/exec-plans/evidence/KL-080').decode().splitlines()
        if set(preserved) - archives:
            raise ValueError('archive-nonmigrated-history-changed')
        return errors, {entry['storage']['payload'] for entry in mapping['entries']}
    except (ValueError, OSError) as ex:
        errors.append('archive-invalid:' + str(ex))
        return errors, set()


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
    # The selected PR's scope gate proves ownership separately. Include every
    # changed owned artifact (also exact-pair/remediation reviews), so moving bulk
    # output to another identity cannot evade the PR-wide budget.
    paths = sorted(p for p in paths if re.match(
        r'^docs/exec-plans/(?:evidence|reviews)/(?:HG|KL)-[0-9]{3}[A-Z]?/', p))
    errors: list[str] = []
    total = 0
    payloads: set[str] = set()
    archive_errors, archive_payloads = archive_audit(root, head)
    errors.extend(archive_errors)
    payloads.update(archive_payloads)
    bulk: dict[str, str] = {}
    for path in paths:
        try:
            total += int(git(root, 'cat-file', '-s', head + ':' + path))
            data = blob(root, path, head, STORED_LIMIT if path.endswith('.gz') else PLAIN_LIMIT)
            if path.endswith('.gz'):
                continue
            if Path(path).name == 'complete-diff.patch':
                raise ValueError('full-diff-copy: record base/head instead')
            manifest = envelope(data)
            if manifest is not None and manifest.get(MARKER) in (HISTORICAL_FORMAT, MAPPING_FORMAT):
                if (archive_errors or identity != 'KL-080'
                        or path not in {MAPPING_PATH, *[x['path'] for x in historical_originals()]}
                        or not archive_payloads):
                    raise ValueError('archive-invalid-or-owner')
                if path == MAPPING_PATH and git(root, 'ls-tree', base, '--', path).strip():
                    raise ValueError('archive-mapping-not-forward-addition')
                continue
            if manifest is not None:
                raw = read(root, path, head)
                payloads.add(manifest['payload'])
            else:
                raw = data
                # JSON content remains JSON evidence even under a .log/.txt name.
                try:
                    value = json.loads(data, object_pairs_hook=unique)
                except (UnicodeError, json.JSONDecodeError):
                    value = None
                if embedded_raw(value):
                    raise ValueError('embedded-raw_utf8: capture raw once')
            if raw.lstrip().startswith(b'diff --git '):
                raise ValueError('full-diff-copy: record base/head instead')
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
    archival = commands.add_parser('archive-read', help='Recover archival bytes; never execution proof')
    archival.add_argument('path')
    archival.add_argument('--revision', required=True)
    mapping = commands.add_parser('archive-map', help='Build the exact authorized mapping after storage commit')
    mapping.add_argument('--storage-revision', required=True)
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
        elif args.action == 'archive-read':
            sys.stdout.buffer.write(read_archive(args.root, args.path, args.revision))
        elif args.action == 'archive-map':
            print(json.dumps(archive_mapping(args.root, args.storage_revision), indent=2))
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
