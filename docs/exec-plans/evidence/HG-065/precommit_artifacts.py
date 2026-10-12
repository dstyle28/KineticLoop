"""Classify exact prospective HG065 artifacts with unchanged native functions.
The receipt remains external, contains hashes/diagnostics only and binds the staged tree.
No native classifier/codec/history authority is supplied by this helper.
"""
import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.harness import compact_evidence as native


def inspect():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    receipt = Path(args.receipt)
    assert not receipt.is_relative_to(ROOT)
    paths = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMRT', '-z'], cwd=ROOT).decode().split('\0')[:-1]
    rows, errors, payloads, bulk = [], [], set(), {}
    total = 0
    for path in sorted(paths):
        p = ROOT / path
        s = p.lstat()
        assert stat.S_ISREG(s.st_mode)
        raw = p.read_bytes()
        staged = subprocess.check_output(['git', 'show', ':' + path], cwd=ROOT)
        assert raw == staged, path
        row = {'path': path, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'mode': oct(stat.S_IMODE(s.st_mode))}
        rows.append(row)
        if not path.startswith(('docs/exec-plans/evidence/HG-065/', 'docs/exec-plans/reviews/HG-065/')):
            continue
        total += len(raw)
        try:
            manifest = native.envelope(raw)
            mapping = native.reencoding_record(raw)
            assert mapping is None, 'unexpected-reencoding-record'
            limit = native.STORED_LIMIT if path.endswith(('.gz', '.xz')) else native.PLAIN_LIMIT
            assert len(raw) <= limit, 'stored-byte-limit'
            data = native.blob(ROOT, path, None, limit)
            assert data == raw
            if manifest is not None:
                decoded = native.read(ROOT, path, None)
                payloads.add(manifest['payload'])
            elif path.endswith(('.gz', '.xz')):
                continue
            else:
                decoded = raw
                try:
                    value = json.loads(raw, object_pairs_hook=native.unique)
                except (UnicodeError, json.JSONDecodeError):
                    value = None
                assert not native.embedded_raw(value), 'embedded-raw-body'
            assert p.name != 'complete-diff.patch' and not decoded.lstrip().startswith(b'diff --git '), 'full-diff-copy'
            if len(decoded) >= 16384:
                key = native.digest(decoded)
                assert key not in bulk or (manifest is not None and bulk[key] == manifest['payload']), 'duplicate-bulk'
                bulk[key] = manifest['payload'] if manifest is not None else path
        except (ValueError, AssertionError, OSError, UnicodeError) as ex:
            errors.append({'path': path, 'error': str(ex)})
    assert total <= native.TOTAL_LIMIT, 'total-limit'
    for path in paths:
        if path.startswith(('docs/exec-plans/evidence/HG-065/', 'docs/exec-plans/reviews/HG-065/')) and path.endswith(('.gz', '.xz')) and path not in payloads:
            errors.append({'path': path, 'error': 'unreferenced-payload'})
    report = {'native_source_sha256': hashlib.sha256((ROOT / 'tools/harness/compact_evidence.py').read_bytes()).hexdigest(), 'staged_tree': subprocess.check_output(['git', 'write-tree'], cwd=ROOT, text=True).strip(), 'rows': rows, 'stored_bytes': total, 'errors': errors}
    if args.verify:
        assert json.loads(receipt.read_bytes()) == report, 'precommit-bytes-changed'
    else:
        assert not receipt.exists()
        receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'files': len(rows), 'stored_bytes': total, 'errors': errors, 'staged_tree': report['staged_tree']}))
    assert not errors


if __name__ == '__main__':
    inspect()
