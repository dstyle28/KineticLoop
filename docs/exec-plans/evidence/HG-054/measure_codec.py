"""Read-only codec verification; prints hashes/sizes, never recovered logs."""
from __future__ import annotations

import importlib.util
import json
import random
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location('compact', ROOT / 'tools/harness/compact_evidence.py')
assert SPEC and SPEC.loader
ce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ce)
SOURCE = 'e71e599885de45da5bcc0a1a9f817939a3fdbcf2'
BASE = 'af09be228fbc89d074b6e863c83e1fdda343d55b'


def measure(raw: bytes, label: str, gzip_bytes: bytes | None = None) -> dict:
    old = gzip_bytes if gzip_bytes is not None else ce.encode(raw, ce.FORMAT)
    new = ce.encode(raw, ce.XZ_FORMAT)
    assert ce.encode(raw, ce.XZ_FORMAT) == new
    assert ce.decode(old, ce.FORMAT, len(raw)) == raw
    assert ce.decode(new, ce.XZ_FORMAT, len(raw)) == raw
    assert ce.digest(ce.decode(new, ce.XZ_FORMAT, len(raw))) == ce.digest(raw)
    return {'label': label, 'raw_bytes': len(raw), 'raw_sha256': ce.digest(raw),
            'gzip_bytes': len(old), 'gzip_sha256': ce.digest(old),
            'xz_bytes': len(new), 'xz_sha256': ce.digest(new)}


def main() -> None:
    rng = random.Random(54)
    block = rng.randbytes(32768)
    representative = measure(block * 640 + b'100 passed\n', 'deterministic repeated binary output')
    report = {'representative': representative, 'limits': {
        'plain': ce.PLAIN_LIMIT, 'stored': ce.STORED_LIMIT, 'raw': ce.RAW_LIMIT,
        'aggregate': ce.TOTAL_LIMIT, 'xz_memory': ce.XZ_MEMLIMIT}}
    # Immutable Git inputs only; no owner worktree, DB, controller or credentials.
    exists = subprocess.run(['git', 'cat-file', '-e', SOURCE + '^{commit}'], cwd=ROOT,
                            capture_output=True).returncode == 0
    if exists:
        paths = ce.git(ROOT, 'diff', '--no-renames', '--name-only', '--diff-filter=ACMRT',
                       BASE, SOURCE).decode().splitlines()
        paths = [p for p in paths if p.startswith(('docs/exec-plans/evidence/KL-036/',
                                                 'docs/exec-plans/reviews/KL-036/'))]
        payloads = []
        total = 0
        for path in paths:
            data = ce.blob(ROOT, path, SOURCE)
            total += len(data)
            if path.endswith('.gz'):
                payloads.append((len(data), path, data))
        selected = sorted(payloads, reverse=True)[:4]
        rows = []
        for _, path, data in selected:
            # Obtain declared raw bound from its exact committed envelope.
            parent = str(Path(path).parent)
            refs = ce.git(ROOT, 'ls-tree', '-r', '--name-only', SOURCE, '--', parent).decode().splitlines()
            for ref in refs:
                if ref.endswith('.gz'):
                    continue
                manifest = ce.envelope(ce.blob(ROOT, ref, SOURCE))
                if manifest is not None and manifest.get('payload') == path:
                    raw = ce.read(ROOT, ref, SOURCE)
                    rows.append(measure(raw, path, data))
                    break
            else:
                raise AssertionError('unreferenced measured payload')
        savings = sum(row['gzip_bytes'] - row['xz_bytes'] for row in rows)
        report['pinned_read_only_proposal'] = {
            'source': SOURCE, 'base': BASE, 'changed_files': len(paths),
            'payloads': len(payloads), 'current_bytes': total, 'four_largest': rows,
            'savings_bytes': savings, 'projected_bytes_before_envelope_and_record_changes': total - savings,
            'within_unchanged_total_budget': total - savings <= ce.TOTAL_LIMIT}
        assert total == 18194008
        assert total - savings == 9026903
        assert len(rows) == 4
    else:
        report['pinned_read_only_proposal'] = {'status': 'UNAVAILABLE', 'source': SOURCE}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
