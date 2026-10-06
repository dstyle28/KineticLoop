"""Lossless task-owned evidence. No archive extraction or ambient Git fallback."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import lzma
import re
import subprocess
import sys
import unicodedata
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
XZ_FORMAT = 'xz-v1'
CODECS = {FORMAT: '.gz', XZ_FORMAT: '.xz'}
XZ_MEMLIMIT = 64 * 1024 * 1024


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
    def ascii_escape(match):
        digits = next(value for value in match.groups() if value)
        value = int(digits, 8 if match.group(4) else 16)
        return bytes([value]) if value < 128 else match[0]
    data = re.sub(rb'\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})|U([0-9a-fA-F]{8})|([0-7]{1,3}))',
                  ascii_escape, data)
    def named_ascii_escape(match):
        try:
            value = unicodedata.lookup(match[1].decode('ascii'))
        except (KeyError, UnicodeError):
            return match[0]
        return value.encode('ascii') if value.isascii() else match[0]
    data = re.sub(rb'\\N\{([^{}\r\n]+)\}', named_ascii_escape, data)
    # A field reference/string value is ordinary content. Recognize key/value
    # syntax even in broken JSON, source dictionaries, comments and string
    # wrappers; classification never parses or executes source as authority.
    data = data.replace(b'\\"', b'"').replace(b"\\'", b"'")
    # Keep the unjoined view too: malformed JSON must not hide a complete
    # reserved key by appending an adjacent token. Both views only classify.
    continued = re.sub(rb'\\\r?\n', b'', data)
    # Prefixes and comments do not prevent Python's implicit literal joining.
    # This additional view only identifies keys; it never accepts source bytes.
    joined = re.sub(rb"[\"'](?:\s|\#[^\r\n]*(?:\r?\n|$))*[rRuUbBfF]{0,2}[\"']", b"", continued)
    keys = set()
    assignment = rb'(?:\*\*|//|<<|>>|[+\-*/%@&|^:])?=(?!=)'
    for view in (data, continued, joined):
        keys.update(re.findall(rb"[\"']([a-z_][a-z_0-9]*)[\"']\s*\)*\s*:", view))
        keys.update(re.findall(rb"\b([a-z_][a-z_0-9]*)\s*" + assignment, view))
        keys.update(re.findall(
            rb"[\"']([a-z_][a-z_0-9]*)[\"']\s*\)*\s*\]\s*\)*\s*(?:" + assignment + rb"|:)", view))
        keys.update(re.findall(rb"\{\s*[\"']([a-z_][a-z_0-9]*)[\"']", view))
        # An unfinished object key after a comma still identifies damaged
        # metadata. Commas in lists/calls and quoted values do not identify keys.
        # This small lexical walk supplies only delimiter context, never trust
        # in a source program or permission to execute it.
        stack = []
        object_commas = set()
        statement_start = 0
        statements = []
        for token in re.finditer(rb'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\#[^\r\n]*|[{}\[\](),;\r\n]''', view):
            text = token[0]
            if text in (b'{', b'[', b'('):
                stack.append(text)
            elif text in (b'}', b']', b')'):
                opening = {b'}': b'{', b']': b'[', b')': b'('}[text]
                # Damaged inner containers must not mask a later partial object
                # key. Only a closing brace can discard the enclosing object.
                while stack and stack[-1] not in (opening, b'{'):
                    stack.pop()
                if stack and stack[-1] == opening:
                    stack.pop()
            elif text == b',' and stack and stack[-1] == b'{':
                object_commas.add(token.start())
            elif text == b';' or (text in (b'\r', b'\n') and not stack):
                statements.append(view[statement_start:token.start()])
                statement_start = token.end()
        statements.append(view[statement_start:])
        # Newlines inside annotations belong to the same logical statement.
        # Scan each statement once without unbounded annotation backtracking.
        for statement in statements:
            if re.search(rb'(?<![=<>!])' + assignment, statement):
                keys.update(re.findall(rb"\b([a-z_][a-z_0-9]*)\s*:", statement))
        keys.update(match[1] for match in re.finditer(
            rb",\s*[\"']([a-z_][a-z_0-9]*)[\"']", view)
                    if match.start() in object_commas)
    return (b'kineticloop_evidence' in keys or b'compact_reencoding' in keys or
            {b'payload', b'stored_sha256', b'raw_sha256'} <= keys or
            {b'authorization', b'preserved_records', b'entries'} <= keys or
            {b'protected_base', b'source_revision', b'entries'} <= keys)


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
        reserved = reserved or MARKER in value or 'compact_reencoding' in value or {'payload', 'stored_sha256', 'raw_sha256'} <= set(value) or {'authorization', 'preserved_records', 'entries'} <= set(value) or {'protected_base', 'source_revision', 'entries'} <= set(value)
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
    if isinstance(value, dict) and (MARKER in value or 'compact_reencoding' in value or
                                   {'payload', 'stored_sha256', 'raw_sha256'} <= set(value) or
                                   {'authorization', 'preserved_records', 'entries'} <= set(value) or {'protected_base', 'source_revision', 'entries'} <= set(value)):
        if original_bytes > PLAIN_LIMIT:
            raise ValueError('evidence-envelope-size')
        return value
    if reserved or reserved_ascii(data):
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
    if (len(data) > PLAIN_LIMIT or set(manifest) != fields or manifest[MARKER] not in CODECS
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
    expected = str(Path(path).parent / (manifest['raw_sha256'] + CODECS[manifest[MARKER]]))
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
    raw = decode(stored, manifest[MARKER], manifest['raw_bytes'])
    if digest(raw) != manifest['raw_sha256']:
        raise ValueError('evidence-raw-integrity-or-bound')
    # Storage metadata is never command output, even inside a valid payload.
    # Classify once; nested/wrapped envelopes cannot supply a raw PASS oracle.
    if envelope(raw) is not None:
        raise ValueError('evidence-nested-envelope')
    return raw


def encode(raw: bytes, codec: str) -> bytes:
    if codec == FORMAT:
        return gzip.compress(raw, compresslevel=9, mtime=0)
    if codec == XZ_FORMAT:
        return lzma.compress(raw, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=6)
    raise ValueError('evidence-codec')


def decode(stored: bytes, codec: str, raw_bytes: int) -> bytes:
    try:
        if codec == FORMAT:
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            raw = decoder.decompress(stored, raw_bytes + 1)
            extra = bool(decoder.unconsumed_tail)
        elif codec == XZ_FORMAT:
            xz_decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=XZ_MEMLIMIT)
            raw = xz_decoder.decompress(stored, max_length=raw_bytes + 1)
            if len(raw) != raw_bytes or not xz_decoder.eof or xz_decoder.unused_data or xz_decoder.check != lzma.CHECK_CRC64:
                raise ValueError('evidence-raw-integrity-or-bound')
            return raw
        else:
            raise ValueError('evidence-codec')
        if len(raw) != raw_bytes or not decoder.eof or decoder.unused_data or extra:
            raise ValueError('evidence-raw-integrity-or-bound')
        return raw
    except (zlib.error, lzma.LZMAError) as ex:
        raise ValueError('evidence-' + codec) from ex


def capture(root: Path, path: str, raw: bytes, tested: str, command: str, exit_code: int,
            timestamp: str | None = None, codec: str = FORMAT) -> dict:
    root = root.resolve()
    owner(path)
    if (not isinstance(command, str) or not command or type(exit_code) is not int
            or not re.fullmatch(r'[0-9a-f]{40}', tested)
            or git(root, 'rev-parse', '--verify', '--end-of-options',
                   tested + '^{commit}').decode().strip() != tested):
        raise ValueError('capture-command-or-tested-revision')
    if not path.endswith('.json') or len(raw) > RAW_LIMIT:
        raise ValueError('capture-json-path-or-raw-limit')
    stored = encode(raw, codec)
    if len(stored) > STORED_LIMIT:
        raise ValueError('capture-stored-limit: split real executions, never truncate')
    target = root / path
    payload = target.parent / (digest(raw) + CODECS[codec])
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
    record = {MARKER: codec, 'payload': str(payload.relative_to(root)),
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


# Exact indexed HG051 authority travels with the reviewed/pinned decoder. The
# installed worker has only Python assets and must never trust candidate schema
# contents or an ambient filesystem fallback to authorize historical bytes.
HISTORICAL_SCHEMA_BYTES = r'''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "kineticloop/historical-evidence-mapping-v1",
  "title": "HG051 exact four-blob KL080 archival storage authorization",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "kineticloop_evidence",
    "authorization",
    "task_identity",
    "purpose",
    "historical_outcome",
    "preserved_records",
    "entries"
  ],
  "properties": {
    "kineticloop_evidence": {
      "const": "historical-mapping-v1"
    },
    "authorization": {
      "const": "harness-governance-v0.1/HG-051"
    },
    "task_identity": {
      "const": "harness-backlog-v0.2/KL-080"
    },
    "purpose": {
      "const": "ARCHIVAL_RETRIEVAL_ONLY"
    },
    "historical_outcome": {
      "const": {
        "task_status": "BLOCKED",
        "task_checks_status": "FAIL",
        "integration_status": "UNMERGED",
        "tested_commit": "15a7167e44b8044c94688cf7e367e2d02a962e31",
        "reviewed_head_sha": "7e19587458d611155051d0c89d36e0b89f98b8a1",
        "review_status": "CHANGES_REQUIRED"
      }
    },
    "preserved_records": {
      "const": [
        {
          "path": "docs/exec-plans/completed/KL-080_RESULT.yaml",
          "revision": "7e19587458d611155051d0c89d36e0b89f98b8a1",
          "sha256": "d2a4c09325746eed188804df75a177eb87090bed111ebd8c740efe3177ec58ba",
          "bytes": 26928
        },
        {
          "path": "docs/exec-plans/reviews/KL-080/GENERAL.json",
          "revision": "477b213f67429f571b60d5701f02892ab9c1cbbf",
          "sha256": "075f182f8ec7a917eb310dd8830bd81ddc6c361410b164a57184268f0ed82584",
          "bytes": 25548
        },
        {
          "path": "docs/exec-plans/reviews/KL-080/PROTOCOL.json",
          "revision": "477b213f67429f571b60d5701f02892ab9c1cbbf",
          "sha256": "6182dcfcd122457e7763282b8084a52d1fb5009c27a2fd368d8cbf20a4d77375",
          "bytes": 5173
        },
        {
          "path": "docs/exec-plans/reviews/KL-080/DB_CONCURRENCY.json",
          "revision": "477b213f67429f571b60d5701f02892ab9c1cbbf",
          "sha256": "0682ea1f9f70a8edbe72a9b3ea8f52523f9f46fed5f8da795a381138b693c37f",
          "bytes": 7157
        }
      ]
    },
    "entries": {
      "type": "array",
      "minItems": 4,
      "maxItems": 4,
      "prefixItems": [
        {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "original",
            "storage"
          ],
          "properties": {
            "original": {
              "const": {
                "task_identity": "harness-backlog-v0.2/KL-080",
                "path": "docs/exec-plans/evidence/KL-080/15a7167e44b8044c94688cf7e367e2d02a962e31/harness_regressions_pass.xml",
                "revision": "7e19587458d611155051d0c89d36e0b89f98b8a1",
                "blob_id": "4c14842b283158b38b2b6771afa631a83fa1942b",
                "raw_sha256": "62bdbc352d2f80bc4f254e85b91a7101fecaef40ea72f27448aa04017f19f436",
                "raw_bytes": 3456356,
                "execution": {
                  "tested_commit": "15a7167e44b8044c94688cf7e367e2d02a962e31",
                  "command": "uv run kl test-harness",
                  "exit_code": 0,
                  "result": "PASS",
                  "timestamp": null
                },
                "execution_record": {
                  "path": "docs/exec-plans/evidence/KL-080/15a7167e44b8044c94688cf7e367e2d02a962e31/harness_regressions_pass.execution.json",
                  "revision": "7e19587458d611155051d0c89d36e0b89f98b8a1",
                  "sha256": "00255738b0a2220a5980d0fb39c999d7f449dc4c9ef1fbd7eafe299c64b90ef4",
                  "bytes": 697
                }
              }
            },
            "storage": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "revision",
                "envelope_path",
                "envelope_sha256",
                "envelope_bytes",
                "payload",
                "payload_sha256",
                "payload_bytes"
              ],
              "properties": {
                "revision": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{40}$"
                },
                "envelope_path": {
                  "type": "string"
                },
                "envelope_sha256": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{64}$"
                },
                "envelope_bytes": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 262144
                },
                "payload": {
                  "type": "string"
                },
                "payload_sha256": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{64}$"
                },
                "payload_bytes": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 8388608
                }
              }
            }
          }
        },
        {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "original",
            "storage"
          ],
          "properties": {
            "original": {
              "const": {
                "task_identity": "harness-backlog-v0.2/KL-080",
                "path": "docs/exec-plans/evidence/KL-080/15a7167e44b8044c94688cf7e367e2d02a962e31/source_suite_dc.log",
                "revision": "7e19587458d611155051d0c89d36e0b89f98b8a1",
                "blob_id": "74b505e3882c8857e7d4434f200fa2ecf454d7b8",
                "raw_sha256": "2b9d584a65063ef0e00040c69fcdc925e7e512b5f49c281ab880962e7490d92d",
                "raw_bytes": 12503732,
                "execution": {
                  "tested_commit": "15a7167e44b8044c94688cf7e367e2d02a962e31",
                  "command": "uv run pytest -q tests/db/test_source_decision_conformance.py",
                  "exit_code": 1,
                  "result": "FAIL",
                  "timestamp": null
                },
                "execution_record": {
                  "path": "docs/exec-plans/evidence/KL-080/15a7167e44b8044c94688cf7e367e2d02a962e31/source_suite_dc.execution.json",
                  "revision": "7e19587458d611155051d0c89d36e0b89f98b8a1",
                  "sha256": "633c49b0b8e943aaaf7cea496c4c1e6a25a133f9ad5630033704b13720602fb8",
                  "bytes": 709
                }
              }
            },
            "storage": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "revision",
                "envelope_path",
                "envelope_sha256",
                "envelope_bytes",
                "payload",
                "payload_sha256",
                "payload_bytes"
              ],
              "properties": {
                "revision": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{40}$"
                },
                "envelope_path": {
                  "type": "string"
                },
                "envelope_sha256": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{64}$"
                },
                "envelope_bytes": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 262144
                },
                "payload": {
                  "type": "string"
                },
                "payload_sha256": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{64}$"
                },
                "payload_bytes": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 8388608
                }
              }
            }
          }
        },
        {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "original",
            "storage"
          ],
          "properties": {
            "original": {
              "const": {
                "task_identity": "harness-backlog-v0.2/KL-080",
                "path": "docs/exec-plans/evidence/KL-080/d6bfb285087456a1a43d6c6b856a07eee4e1746d/harness_regressions_pass.parallel.xml",
                "revision": "79fa887dc20f5865902b0b5d90ce0e4b68e0118e",
                "blob_id": "f73c446fe5a49036e39e87121ad3a6029ebdffd1",
                "raw_sha256": "089e1aba60ca60a64c6b513a966d66732f3519e21c51b6d7af3e9dd0fabb93d7",
                "raw_bytes": 3456356,
                "execution": {
                  "tested_commit": "d6bfb285087456a1a43d6c6b856a07eee4e1746d",
                  "command": "uv run kl test-harness",
                  "exit_code": 0,
                  "result": "PASS",
                  "timestamp": null
                },
                "execution_record": {
                  "path": "docs/exec-plans/evidence/KL-080/d6bfb285087456a1a43d6c6b856a07eee4e1746d/harness_regressions_pass.parallel.json",
                  "revision": "79fa887dc20f5865902b0b5d90ce0e4b68e0118e",
                  "sha256": "b1c83e48564bd206eada7e1b879009741f2301423c15873d617e16eab243d190",
                  "bytes": 715
                }
              }
            },
            "storage": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "revision",
                "envelope_path",
                "envelope_sha256",
                "envelope_bytes",
                "payload",
                "payload_sha256",
                "payload_bytes"
              ],
              "properties": {
                "revision": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{40}$"
                },
                "envelope_path": {
                  "type": "string"
                },
                "envelope_sha256": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{64}$"
                },
                "envelope_bytes": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 262144
                },
                "payload": {
                  "type": "string"
                },
                "payload_sha256": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{64}$"
                },
                "payload_bytes": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 8388608
                }
              }
            }
          }
        },
        {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "original",
            "storage"
          ],
          "properties": {
            "original": {
              "const": {
                "task_identity": "harness-backlog-v0.2/KL-080",
                "path": "docs/exec-plans/evidence/KL-080/d6bfb285087456a1a43d6c6b856a07eee4e1746d/source_suite_dc.log",
                "revision": "79fa887dc20f5865902b0b5d90ce0e4b68e0118e",
                "blob_id": "2da980979a754eaf2e081b7181aa11a839020c05",
                "raw_sha256": "5c94998447a516b39433e028b6ca98c64b0f8a00521db6096835210fb1209a1c",
                "raw_bytes": 12480477,
                "execution": {
                  "tested_commit": "d6bfb285087456a1a43d6c6b856a07eee4e1746d",
                  "command": "uv run pytest -q tests/db/test_source_decision_conformance.py",
                  "exit_code": 1,
                  "result": "FAIL",
                  "timestamp": null
                },
                "execution_record": {
                  "path": "docs/exec-plans/evidence/KL-080/d6bfb285087456a1a43d6c6b856a07eee4e1746d/checks.json",
                  "revision": "79fa887dc20f5865902b0b5d90ce0e4b68e0118e",
                  "sha256": "9b00d9cfed7a74d5e1c4923643ad5629ab484ca8542ed4f73b77fe80ae9ceb91",
                  "bytes": 11318
                }
              }
            },
            "storage": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "revision",
                "envelope_path",
                "envelope_sha256",
                "envelope_bytes",
                "payload",
                "payload_sha256",
                "payload_bytes"
              ],
              "properties": {
                "revision": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{40}$"
                },
                "envelope_path": {
                  "type": "string"
                },
                "envelope_sha256": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{64}$"
                },
                "envelope_bytes": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 262144
                },
                "payload": {
                  "type": "string"
                },
                "payload_sha256": {
                  "type": "string",
                  "pattern": "^[0-9a-f]{64}$"
                },
                "payload_bytes": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 8388608
                }
              }
            }
          }
        }
      ],
      "items": false
    }
  }
}
'''.encode('ascii')


def historical_schema() -> dict:
    return json.loads(HISTORICAL_SCHEMA_BYTES, object_pairs_hook=unique)


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
        if path.endswith(('.gz', '.xz')):
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


REENCODING_KEY = 'compact_reencoding'
REENCODING_NAME = 'COMPACT_REENCODING.json'
EXECUTION_FIELDS = ('raw_sha256', 'raw_bytes', 'tested_commit', 'command', 'exit_code',
                    'timestamp', 'test_counts')


def snapshot(root: Path, path: str, revision: str | None, limit: int) -> dict:
    return snapshot_bytes(path, blob(root, path, revision, limit))


def snapshot_bytes(path: str, data: bytes) -> dict:
    return {'path': path, 'sha256': digest(data), 'bytes': len(data),
            'blob_id': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}


def verify_snapshot(root: Path, value: dict, revision: str | None, limit: int) -> bytes:
    if not isinstance(value, dict) or set(value) != {'path', 'sha256', 'bytes', 'blob_id'}:
        raise ValueError('reencoding-snapshot-shape')
    if snapshot(root, value['path'], revision, limit) != value:
        raise ValueError('reencoding-snapshot-integrity')
    return blob(root, value['path'], revision, limit)


def reencoding_record(data: bytes) -> dict | None:
    value = envelope(data)
    if value is None:
        return None
    if {'protected_base', 'source_revision', 'entries'} <= set(value) and REENCODING_KEY not in value:
        raise ValueError('reencoding-marker-missing')
    return value if REENCODING_KEY in value else None


def retained_reencoding_base(root: Path, path: str, record: dict, base: str,
                             head: str) -> tuple[str, str]:
    """Prove an unchanged own map on the task lineage before importing a new base."""
    original_base = record['protected_base']
    source = record['source_revision']
    exact_commit(root, base)
    exact_commit(root, head)
    exact_commit(root, original_base)
    exact_commit(root, source)
    git(root, 'merge-base', '--is-ancestor', original_base, base)
    git(root, 'merge-base', '--is-ancestor', base, head)
    if (git(root, 'merge-base', source, base).decode().strip() == source
            or git(root, 'ls-tree', original_base, '--', path).strip()):
        raise ValueError('reencoding-retained-source-already-protected')
    # Walk the task's first-parent lineage, never a late side branch. Locate the
    # first import boundary by comparing each first parent to the actual base.
    predecessor = None
    for revision in git(root, 'rev-list', '--first-parent', head).decode().splitlines():
        if git(root, 'merge-base', base, revision).decode().strip() != base:
            break
        parents = git(root, 'rev-list', '--parents', '-n', '1', revision).decode().split()[1:]
        if not parents:
            break
        if git(root, 'merge-base', base, parents[0]).decode().strip() != base:
            predecessor = parents[0]
            break
    if predecessor is None:
        raise ValueError('reencoding-retained-import-boundary')
    data = blob(root, path, head, PLAIN_LIMIT)
    if reencoding_record(data) != record or blob(root, path, predecessor, PLAIN_LIMIT) != data:
        raise ValueError('reencoding-retained-map-not-before-import')
    admission = None
    for revision in git(root, 'rev-list', '--first-parent', '--reverse',
                        original_base + '..' + predecessor).decode().splitlines():
        if git(root, 'ls-tree', revision, '--', path).strip():
            admission = revision
            if blob(root, path, admission, PLAIN_LIMIT) != data:
                raise ValueError('reencoding-retained-admission-bytes')
            break
    if (admission is None
            or git(root, 'merge-base', '--all', admission, base).decode().splitlines() != [original_base]):
        raise ValueError('reencoding-retained-admission-base')
    git(root, 'merge-base', '--is-ancestor', source, admission)
    for revision in git(root, 'rev-list', base + '..' + head).decode().splitlines():
        if (git(root, 'merge-base', base, revision).decode().strip() == base
                and git(root, 'merge-base', source, revision).decode().strip() == source
                and git(root, 'merge-base', admission, revision).decode().strip() != admission):
            raise ValueError('reencoding-retained-source-import-before-admission')
    protected_paths = [path]
    for entry in record['entries']:
        for side in ('original', 'replacement'):
            for item in ('envelope', 'payload'):
                protected_paths.append(entry[side][item]['path'])
    if git(root, '--literal-pathspecs', 'log', '--full-history', '--format=%H', original_base + '..' + base,
           '--', *protected_paths).strip():
        raise ValueError('reencoding-retained-protected-path-history')
    # This is a strictly older task prefix. Its original admission, every edge,
    # source/snapshot proofs and transient mutations must pass the existing audit.
    issues, _ = reencoding_audit(root, original_base, predecessor, record['identity'])
    if issues:
        raise ValueError('reencoding-retained-history:' + ';'.join(issues))
    return original_base, admission


def validate_reencoding(root: Path, path: str, record: dict, base: str,
                        head: str | None, identity: str) -> set[str]:
    if (set(record) != {REENCODING_KEY, 'identity', 'protected_base', 'source_revision', 'entries'}
            or record[REENCODING_KEY] != 'v1' or record['identity'] != identity
            or owner(path).split('/')[-1] != identity or Path(path).name != REENCODING_NAME
            or len(path.split('/')) < 6
            or not isinstance(record['entries'], list) or not record['entries']):
        raise ValueError('reencoding-record')
    source = record['source_revision']
    exact_commit(root, source)
    exact_commit(root, record['protected_base'])
    git(root, 'merge-base', '--is-ancestor', record['protected_base'], source)
    if git(root, 'merge-base', base, source).decode().strip() != base:
        if head is None:
            raise ValueError('reencoding-retained-working-record')
        retained_reencoding_base(root, path, record, base, head)
    git(root, 'merge-base', '--is-ancestor', source, head or 'HEAD')
    paths: set[str] = set()
    for entry in record['entries']:
        if not isinstance(entry, dict) or set(entry) != {'original', 'replacement', 'execution'}:
            raise ValueError('reencoding-entry')
        original, replacement = entry['original'], entry['replacement']
        for binding in (original, replacement):
            if not isinstance(binding, dict) or set(binding) != {'envelope', 'payload'}:
                raise ValueError('reencoding-binding')
        ref = original['envelope']['path']
        destination = replacement['envelope']['path']
        if (ref in paths or destination in paths
                or owner(ref).split('/')[-1] != identity
                or owner(destination) != owner(ref)):
            raise ValueError('reencoding-owner-or-path')
        paths.update((ref, destination))
        if destination != ref:
            if (Path(destination).name != original['envelope']['sha256'] + '.json'
                    or len(Path(destination).parent.parts) < 5):
                raise ValueError('reencoding-relocation-destination-shape')
            retained = ((root / ref).exists() or (root / ref).is_symlink()) if head is None else bool(
                git(root, 'ls-tree', head, '--', ref).strip())
            if git(root, 'ls-tree', source, '--', destination).strip() or retained:
                raise ValueError('reencoding-relocation-collision-or-retained-source')
            # A destination introduced after source is still an independent
            # artifact. Prove addition on every edge admitting this map, not
            # merely absence at the older source/protected base.
            bound_head = head or git(root, 'rev-parse', 'HEAD').decode().strip()
            admission_parents = git(root, 'rev-list', '--parents', '-n', '1', bound_head).decode().split()[1:]
            for parent in ([bound_head] if head is None else admission_parents):
                parent_record = (reencoding_record(blob(root, path, parent, PLAIN_LIMIT))
                                 if git(root, 'ls-tree', parent, '--', path).strip() else None)
                if parent_record != record and git(root, 'ls-tree', parent, '--', destination).strip():
                    raise ValueError('reencoding-relocation-destination-preexists')
        for binding in (original, replacement):
            for key in ('envelope', 'payload'):
                bound_path = binding[key]['path']
                if owner(bound_path) != owner(ref):
                    raise ValueError('reencoding-owner')
                for protected in (base, record['protected_base']):
                    if git(root, 'ls-tree', protected, '--', bound_path).strip():
                        raise ValueError('reencoding-protected-base')
        before = envelope(verify_snapshot(root, original['envelope'], source, PLAIN_LIMIT))
        after = envelope(verify_snapshot(root, replacement['envelope'], head, PLAIN_LIMIT))
        if (before is None or after is None or before.get(MARKER) not in CODECS
                or after.get(MARKER) not in CODECS or before[MARKER] == after[MARKER]):
            raise ValueError('reencoding-compact-codec')
        execution = {key: before[key] for key in EXECUTION_FIELDS}
        if (json.dumps(entry['execution'], sort_keys=True) != json.dumps(execution, sort_keys=True)
                or any(after[key] != execution[key] for key in execution)):
            raise ValueError('reencoding-execution-changed')
        for manifest, binding, revision in ((before, original, source), (after, replacement, head)):
            if manifest['payload'] != binding['payload']['path']:
                raise ValueError('reencoding-payload-binding')
            verify_snapshot(root, binding['payload'], revision, STORED_LIMIT)
        if read(root, ref, source) != read(root, destination, head):
            raise ValueError('reencoding-raw-changed')
    return paths


def reencode(root: Path, base: str, source: str, identity: str, paths: list[str],
             record_path: str, codec: str, destination_directory: str | None = None) -> dict:
    """Explicit forward mutation; source and prior record bytes stay in ancestry.

    One envelope can be reencoded only once per unmerged branch. Maps are immutable;
    a second conversion of that envelope would invalidate its first map.
    """
    exact_commit(root, base)
    exact_commit(root, source)
    git(root, 'merge-base', '--is-ancestor', base, source)
    git(root, 'merge-base', '--is-ancestor', source, 'HEAD')
    if not paths or len(paths) != len(set(paths)) or codec not in CODECS:
        raise ValueError('reencoding-selection')
    # Validate all inputs and existing maps before any writes.
    if (owner(record_path).split('/')[-1] != identity or Path(record_path).name != REENCODING_NAME
            or len(record_path.split('/')) < 6):
        raise ValueError('reencoding-record-path')
    target = root / record_path
    if target.exists() or any(p.is_symlink() for p in [target, *target.parents]):
        raise ValueError('reencoding-existing-record-or-symlink')
    # Existing immutable maps cannot be superseded by another representation.
    referenced = set()
    for subtree in ('evidence', 'reviews'):
        for candidate in (root / 'docs/exec-plans' / subtree / identity).rglob('*'):
            if candidate.is_file() and not candidate.name.endswith(('.gz', '.xz')):
                candidate_path = str(candidate.relative_to(root))
                data = blob(root, candidate_path, None)
                prior = reencoding_record(data)
                if prior is not None:
                    if git(root, 'merge-base', base, prior['source_revision']).decode().strip() != base:
                        # Retained maps must already be committed byte-exact; a
                        # working-only backdated record cannot borrow admission.
                        if blob(root, candidate_path, 'HEAD', PLAIN_LIMIT) != data:
                            raise ValueError('reencoding-retained-working-record')
                        validate_reencoding(root, candidate_path, prior, base,
                                            git(root, 'rev-parse', 'HEAD').decode().strip(), identity)
                        validate_reencoding(root, candidate_path, prior, prior['protected_base'], None, identity)
                    else:
                        validate_reencoding(root, candidate_path, prior, base, None, identity)
                    if set(paths) & {e[side]['envelope']['path'] for e in prior['entries']
                                     for side in ('original', 'replacement')}:
                        raise ValueError('reencoding-already-mapped')
                else:
                    manifest = envelope(data)
                    if manifest and manifest.get(MARKER) in CODECS and candidate_path not in paths:
                        referenced.add(manifest['payload'])
    plans: list[tuple[str, str, dict, dict, bytes]] = []
    for ref in paths:
        before_data = blob(root, ref, source, PLAIN_LIMIT)
        before = envelope(before_data)
        if before is None or before.get(MARKER) not in CODECS or before[MARKER] == codec:
            raise ValueError('reencoding-compact-codec')
        if owner(ref).split('/')[-1] != identity:
            raise ValueError('reencoding-owner')
        old_payload = before['payload']
        if (blob(root, ref, None) != before_data
                or blob(root, ref, 'HEAD') != before_data
                or blob(root, old_payload, None) != blob(root, old_payload, source)
                or blob(root, old_payload, 'HEAD') != blob(root, old_payload, source)):
            raise ValueError('reencoding-working-source-mismatch')
        raw = read(root, ref, source)
        stored = encode(raw, codec)
        if len(stored) > STORED_LIMIT:
            raise ValueError('reencoding-stored-limit')
        new_ref = ref
        if destination_directory is not None:
            if (not normalized(destination_directory)
                    or owner(destination_directory + '/probe.json') != owner(ref)
                    or len(destination_directory.split('/')) < 5):
                raise ValueError('reencoding-destination-owner-or-path')
            new_ref = destination_directory + '/' + digest(before_data) + '.json'
            if (new_ref == ref or (root / new_ref).exists()
                    or git(root, 'ls-tree', source, '--', new_ref).strip()
                    or git(root, 'ls-tree', 'HEAD', '--', new_ref).strip()
                    or any(plan[1] == new_ref for plan in plans)):
                raise ValueError('reencoding-destination-collision')
        new_payload = str(Path(new_ref).parent / (before['raw_sha256'] + CODECS[codec]))
        for p in (ref, new_ref, old_payload, new_payload):
            if git(root, 'ls-tree', base, '--', p).strip():
                raise ValueError('reencoding-protected-base')
            dest = root / p
            if any(part.is_symlink() for part in [dest, *dest.parents]):
                raise ValueError('reencoding-symlink')
            if any(part.exists() and not part.is_dir() for part in dest.parents):
                raise ValueError('reencoding-parent-not-directory')
        if (root / new_payload).exists() and blob(root, new_payload, None) != stored:
            raise ValueError('reencoding-conflicting-payload')
        if (git(root, 'ls-tree', 'HEAD', '--', new_payload).strip()
                and blob(root, new_payload, 'HEAD', STORED_LIMIT) != stored):
            raise ValueError('reencoding-conflicting-committed-payload')
        after = dict(before, **{MARKER: codec, 'payload': new_payload,
                               'stored_sha256': digest(stored), 'stored_bytes': len(stored)})
        plans.append((ref, new_ref, before, after, stored))
    entries = []
    replacements = {}
    for ref, new_ref, before, after, stored in plans:
        original = {'envelope': snapshot(root, ref, source, PLAIN_LIMIT),
                    'payload': snapshot(root, before['payload'], source, STORED_LIMIT)}
        after_bytes = (json.dumps(after, indent=2) + '\n').encode()
        replacements[new_ref] = after_bytes
        replacements[after['payload']] = stored
        entries.append({'original': original,
                        'replacement': {'envelope': snapshot_bytes(new_ref, after_bytes),
                                        'payload': snapshot_bytes(after['payload'], stored)},
                        'execution': {key: before[key] for key in EXECUTION_FIELDS}})
    record = {REENCODING_KEY: 'v1', 'identity': identity, 'protected_base': base,
              'source_revision': source, 'entries': entries}
    record_bytes = (json.dumps(record, indent=2) + '\n').encode()
    if len(record_bytes) > PLAIN_LIMIT:
        raise ValueError('reencoding-record-limit')
    # Roll back local effects on any write/validation failure; never commit here.
    originals = {p: blob(root, p, None) if (root / p).exists() else None for p in replacements}
    removed = {}
    try:
        for path, data in replacements.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_bytes(data)
        for ref, new_ref, _, _, _ in plans:
            if ref != new_ref:
                removed[ref] = blob(root, ref, None)
                (root / ref).unlink()
        validate_reencoding(root, record_path, record, base, None, identity)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(record_bytes)
        for _, _, before, _, _ in plans:
            old = before['payload']
            if old not in referenced and (root / old).exists():
                removed[old] = blob(root, old, None)
                (root / old).unlink()
    except (ValueError, OSError, KeyError, TypeError):
        for restore_path, restore_data in {**originals, **removed}.items():
            if restore_data is None:
                (root / restore_path).unlink(missing_ok=True)
            else:
                (root / restore_path).write_bytes(restore_data)
        target.unlink(missing_ok=True)
        raise
    return record


def reencoding_audit(root: Path, base: str, head: str, identity: str) -> tuple[list[str], set[str]]:
    """Inspect every forward commit so deletion/reversion cannot hide conversions."""
    errors: list[str] = []
    records: set[str] = set()
    verified_archival_payloads: dict[str, set[str]] = {}
    prefixes = [f'docs/exec-plans/{kind}/{identity}/' for kind in ('evidence', 'reviews')]
    storage_roots = ['docs/exec-plans/evidence', 'docs/exec-plans/reviews']

    def archival_payloads(revision: str) -> set[str]:
        if revision not in verified_archival_payloads:
            if git(root, 'ls-tree', revision, '--', MAPPING_PATH).strip():
                archival_errors, payloads = archive_audit(root, revision)
                if archival_errors:
                    raise ValueError('reencoding-archival-binding:' + ';'.join(archival_errors))
            else:
                # The frozen workflow commits all four storage objects before
                # building its mapping. The existing builder verifies this stage.
                mapping = archive_mapping(root, revision)
                payloads = {entry['storage']['payload'] for entry in mapping['entries']}
            verified_archival_payloads[revision] = payloads
        return verified_archival_payloads[revision]

    def bound_payload(path: str, revision: str) -> bool:
        # A valid unchanged sibling envelope can also bind a restored payload.
        # Decoder selection comes from that envelope, never the file extension.
        parent = Path(path).parent
        for ref in git(root, 'ls-tree', '-r', '--name-only', revision, '--',
                       str(parent) + '/').decode().splitlines():
            if ref == path or Path(ref).parent != parent:
                continue
            try:
                manifest = envelope(blob(root, ref, revision, PLAIN_LIMIT))
                if manifest is None or manifest.get('payload') != path:
                    continue
                if manifest.get(MARKER) in CODECS:
                    read(root, ref, revision)
                    return True
                if (manifest.get(MARKER) == HISTORICAL_FORMAT
                        and ref in {x['path'] for x in historical_originals()}
                        and path in archival_payloads(revision)):
                    return True
            except (ValueError, OSError, KeyError, TypeError):
                # An invalid or unrelated candidate cannot supply a proof.
                continue
        return False

    try:
        git(root, 'merge-base', '--is-ancestor', base, head)
        inherited = {}
        retained = {}
        retained_admissions = {}
        admitted = {}
        # Already admitted mappings at the protected base are immutable history.
        # Reverify originals even with no changed blobs; do not authorize any new
        # migration using their older protected-base claim.
        # Every admitted owner's originals remain required on unrelated PRs too.
        # Canonical filenames were validated at admission; avoid reading arbitrary
        # historical bulk merely to discover these small ordinary audit records.
        for path in git(root, 'ls-tree', '-r', '--name-only', base, '--',
                        'docs/exec-plans/evidence', 'docs/exec-plans/reviews').decode().splitlines():
            if Path(path).name != REENCODING_NAME:
                continue
            data = blob(root, path, base, PLAIN_LIMIT)
            record = reencoding_record(data)
            if record is not None:
                if blob(root, path, head, PLAIN_LIMIT) != data:
                    raise ValueError('reencoding-merged-record-mutated-or-deleted')
                admitted_owner = owner(path).split('/')[-1]
                validate_reencoding(root, path, record, record['protected_base'], head, admitted_owner)
                inherited[path] = record['protected_base']
                admitted[path] = (data, record, admitted_owner)
                records.add(path)
        for path in git(root, 'ls-tree', '-r', '--name-only', head, '--', *prefixes).decode().splitlines():
            if Path(path).name != REENCODING_NAME or path in inherited:
                continue
            data = blob(root, path, head, PLAIN_LIMIT)
            record = reencoding_record(data)
            if (record is not None
                    and git(root, 'merge-base', base, record['source_revision']).decode().strip() != base):
                retained[path], retained_admissions[path] = retained_reencoding_base(root, path, record, base, head)
                validate_reencoding(root, path, record, retained[path], head, identity)
                for entry in record['entries']:
                    for side in ('original', 'replacement'):
                        for item in ('envelope', 'payload'):
                            if git(root, 'ls-tree', base, '--', entry[side][item]['path']).strip():
                                raise ValueError('reencoding-protected-base')
                admitted[path] = (data, record, identity)
        commits = git(root, 'rev-list', '--reverse', base + '..' + head).decode().splitlines()
        for revision in commits:
            parents = git(root, 'rev-list', '--parents', '-n', '1', revision).decode().split()[1:]
            if not parents:
                continue
            # A later restoration cannot hide a mutation after admission, even
            # when this PR belongs to another owner. Side branches predating
            # this protected base have not inherited its admitted records yet.
            for bound_revision in [revision, *parents]:
                if admitted and git(root, 'merge-base', base, bound_revision).decode().strip() == base:
                    for path, (data, record, admitted_owner) in admitted.items():
                        if (path in retained_admissions
                                and git(root, 'merge-base', retained_admissions[path],
                                        bound_revision).decode().strip() != retained_admissions[path]):
                            if git(root, 'merge-base', record['source_revision'],
                                   bound_revision).decode().strip() == record['source_revision']:
                                raise ValueError('reencoding-retained-source-import-before-admission')
                            # Only a protected parent without this task's source
                            # can precede its admission across a base import.
                            continue
                        if blob(root, path, bound_revision, PLAIN_LIMIT) != data:
                            raise ValueError('reencoding-merged-record-mutated-or-deleted')
                        validate_reencoding(root, path, record, record['protected_base'],
                                            bound_revision, admitted_owner)
            # Classify every changed metadata blob globally, including aliases
            # on pre-admission branches. Later deletion cannot hide a new map.
            changed_metadata_paths = set()
            for parent in parents:
                changed_metadata_paths.update(git(root, 'diff', '--no-renames', '--name-only',
                                      '--diff-filter=ACMT', parent, revision, '--',
                                      *storage_roots).decode().splitlines())
            proven_payloads: set[str] = set()
            deferred_metadata_errors: list[tuple[str, ValueError]] = []
            for path in sorted(changed_metadata_paths):
                data = blob(root, path, revision,
                            STORED_LIMIT if path.endswith(('.gz', '.xz')) else PLAIN_LIMIT)
                try:
                    record = reencoding_record(data)
                except ValueError as ex:
                    if (not path.endswith(('.gz', '.xz'))
                            or str(ex) not in {'evidence-envelope-json', 'evidence-envelope-encoding'}):
                        raise
                    # Small XZ streams may contain literal ordinary JSON bytes.
                    # Defer classification until exact envelope proofs are known.
                    deferred_metadata_errors.append((path, ex))
                    continue
                if record is None:
                    manifest = envelope(data)
                    if manifest is not None:
                        if manifest.get(MARKER) in (HISTORICAL_FORMAT, MAPPING_FORMAT):
                            if path not in {MAPPING_PATH, *(x['path'] for x in historical_originals())}:
                                raise ValueError('archive-unauthorized-path')
                            proven_payloads.update(archival_payloads(revision))
                        else:
                            read(root, path, revision)
                            proven_payloads.add(manifest['payload'])
                elif path not in inherited and not any(path.startswith(prefix) for prefix in prefixes):
                    raise ValueError('reencoding-foreign-owner:' + path)
                else:
                    admitted_owner = admitted[path][2] if path in inherited else identity
                    validate_reencoding(root, path, record, inherited.get(path, retained.get(path, base)),
                                        revision, admitted_owner)
            for path, error in deferred_metadata_errors:
                if path not in proven_payloads and not bound_payload(path, revision):
                    raise error
            mapped = {}
            for path in git(root, 'ls-tree', '-r', '--name-only', revision, '--', *prefixes).decode().splitlines():
                if path.endswith(('.gz', '.xz')):
                    continue
                data = blob(root, path, revision)
                record = reencoding_record(data)
                if record is not None:
                    if len(data) > PLAIN_LIMIT:
                        raise ValueError('reencoding-record-limit')
                    validate_reencoding(root, path, record, inherited.get(path, retained.get(path, base)), revision, identity)
                    records.add(path)
                    for entry in record['entries']:
                        ref = entry['original']['envelope']['path']
                        if ref in mapped:
                            raise ValueError('reencoding-duplicate-mapping')
                        mapped[ref] = entry
            for parent in parents:
                changed = git(root, 'diff', '--no-renames', '--name-only', '--diff-filter=MDT',
                              parent, revision, '--', *storage_roots).decode().splitlines()
                for path in changed:
                    old = blob(root, path, parent)
                    selected_owner = any(path.startswith(prefix) for prefix in prefixes)
                    try:
                        old_record = reencoding_record(old)
                    except ValueError as ex:
                        if (not path.endswith(('.gz', '.xz'))
                                or str(ex) not in {'evidence-envelope-json', 'evidence-envelope-encoding'}
                                or not bound_payload(path, parent)):
                            raise
                        old_record = None
                    if old_record is not None:
                        raise ValueError('reencoding-record-mutated-or-deleted')
                    # Pre-admission side branches do not inherit protected state.
                    # Selected-owner history retains its existing strict checks.
                    if not selected_owner:
                        if (git(root, 'merge-base', base, revision).decode().strip() != base or
                                git(root, 'merge-base', base, parent).decode().strip() != base):
                            continue
                    if path.endswith(('.gz', '.xz')):
                        if not selected_owner:
                            raise ValueError('reencoding-foreign-payload-mutation:' + path)
                        accounted = [e for e in mapped.values()
                                     if e['original']['payload'] == snapshot(root, path, parent, STORED_LIMIT)]
                        if not accounted:
                            raise ValueError('reencoding-unmapped-payload-mutation:' + path)
                        if git(root, 'ls-tree', revision, '--', path).strip():
                            raise ValueError('reencoding-old-payload-mutated:' + path)
                        # No current refs may still require the removed payload.
                        for current in git(root, 'ls-tree', '-r', '--name-only', revision, '--', *prefixes).decode().splitlines():
                            if current.endswith(('.gz', '.xz')):
                                continue
                            value = envelope(blob(root, current, revision))
                            if value and value.get('payload') == path:
                                raise ValueError('reencoding-live-payload-deleted')
                    else:
                        manifest = envelope(old)
                        if manifest and manifest.get(MARKER) in CODECS:
                            if not selected_owner:
                                raise ValueError('reencoding-foreign-envelope-mutation:' + path)
                            # Existing extension/JSON encoding compatibility is not
                            # a codec conversion. All metadata and payload identity
                            # must remain exactly equal, under the same owner.
                            unchanged = False
                            current_exists = bool(git(root, 'ls-tree', revision, '--', path).strip())
                            candidates = ([path] if current_exists else
                                          git(root, 'ls-tree', '-r', '--name-only', revision,
                                              '--', owner(path) + '/').decode().splitlines())
                            for current in candidates:
                                if not current.endswith(('.gz', '.xz')):
                                    try:
                                        if envelope(blob(root, current, revision)) == manifest:
                                            unchanged = True
                                            break
                                    except ValueError:
                                        continue
                            if not unchanged:
                                entry = mapped.get(path)
                                if entry is None or entry['original']['envelope'] != snapshot(root, path, parent, PLAIN_LIMIT):
                                    raise ValueError('reencoding-unmapped-envelope-mutation:' + path)
        return errors, records
    except (ValueError, OSError, KeyError, TypeError) as ex:
        return ['reencoding-invalid:' + str(ex)], records


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
    # Deleting the complete archival representation must not disappear from an
    # ACMRT-only budget diff. Once merged, these storage bindings are immutable.
    if git(root, 'ls-tree', base, '--', MAPPING_PATH).strip():
        historical_paths = {MAPPING_PATH}
        for original in historical_originals():
            historical_paths.add(original['path'])
            historical_paths.add(str(Path(original['path']).parent / (original['raw_sha256'] + '.gz')))
        for historical_path in sorted(historical_paths):
            try:
                if blob(root, historical_path, base) != blob(root, historical_path, head):
                    raise ValueError('archive-history-rebound')
            except ValueError as ex:
                errors.append(historical_path + ':archive-history-deleted-or-rebound:' + str(ex))
    elif identity == 'KL-080':
        # Before the first merge, original artifacts may be PR additions. Their
        # introduction commits still prove that deleting/truncating all copies
        # cannot evade the narrowly authorized representation migration.
        for original in historical_originals():
            try:
                git(root, 'merge-base', '--is-ancestor', original['revision'], head)
            except ValueError:
                continue
            try:
                data = blob(root, original['path'], head, RAW_LIMIT)
                manifest = envelope(data)
                if manifest is None and (digest(data) != original['raw_sha256']
                                         or len(data) != original['raw_bytes']):
                    raise ValueError('archive-original-current-integrity')
                if manifest is not None and manifest.get(MARKER) != HISTORICAL_FORMAT:
                    raise ValueError('archive-original-current-format')
            except ValueError as ex:
                errors.append(original['path'] + ':archive-original-current-missing-or-changed:' + str(ex))
    reencoding_errors, reencoding_paths = reencoding_audit(root, base, head, identity)
    errors.extend(reencoding_errors)
    bulk: dict[str, str] = {}
    for path in paths:
        try:
            total += int(git(root, 'cat-file', '-s', head + ':' + path))
            data = blob(root, path, head, STORED_LIMIT if path.endswith(('.gz', '.xz')) else PLAIN_LIMIT)
            if path.endswith(('.gz', '.xz')):
                continue
            if Path(path).name == 'complete-diff.patch':
                raise ValueError('full-diff-copy: record base/head instead')
            if path in reencoding_paths:
                continue
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
        if path.endswith(('.gz', '.xz')) and path not in payloads:
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
    cap.add_argument('--codec', choices=('gzip', 'xz'), default='gzip')
    cap.add_argument('--timestamp', default=datetime.now(timezone.utc).isoformat())
    retrieve = commands.add_parser('read', help='Write validated exact raw bytes to stdout')
    retrieve.add_argument('path')
    retrieve.add_argument('--revision', required=True)
    archival = commands.add_parser('archive-read', help='Recover archival bytes; never execution proof')
    archival.add_argument('path')
    archival.add_argument('--revision', required=True)
    mapping = commands.add_parser('archive-map', help='Build the exact authorized mapping after storage commit')
    mapping.add_argument('--storage-revision', required=True)
    recode = commands.add_parser('reencode', help='Explicit own unmerged compact conversion')
    recode.add_argument('--base', required=True)
    recode.add_argument('--source', required=True)
    recode.add_argument('--identity', required=True)
    recode.add_argument('--path', action='append', required=True)
    recode.add_argument('--record', required=True)
    recode.add_argument('--codec', choices=('gzip', 'xz'), required=True)
    recode.add_argument('--destination-dir', help='Explicit same-owner relocation during codec conversion')
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
                             args.command, args.exit_code, args.timestamp, args.codec + '-v1')
            print(json.dumps(result, indent=2))
        elif args.action == 'reencode':
            print(json.dumps(reencode(args.root, args.base, args.source, args.identity,
                                     args.path, args.record, args.codec + '-v1',
                                     args.destination_dir), indent=2))
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
