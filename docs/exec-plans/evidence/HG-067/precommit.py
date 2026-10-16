"""Classify exact staged own bytes with unchanged native readers before each commit."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
R = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(R))
from tools.harness import compact_evidence as native
B = '276bcaebbf3b64b4ea128b175a0463b2f650ac7c'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=R)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    tree = git('write-tree').decode().strip()
    paths = git('diff', '--name-only', '--diff-filter=ACMRT', '-z', B, tree).decode().split('\0')[:-1]
    own = [p for p in paths if p.startswith(('docs/exec-plans/evidence/HG-067/', 'docs/exec-plans/reviews/HG-067/'))]
    rows, errors, payloads, bulk = [], [], set(), {}
    for path in own:
        raw = git('show', tree + ':' + path)
        row = {'path': path, 'bytes': len(raw), 'sha256': native.digest(raw)}
        try:
            assert (R / path).is_file() and not (R / path).is_symlink()
            assert (R / path).read_bytes() == raw
            assert len(raw) <= (native.STORED_LIMIT if path.endswith(('.gz', '.xz')) else native.PLAIN_LIMIT)
            meta = native.envelope(raw)
            assert native.reencoding_record(raw) is None
            if path.endswith(('.gz', '.xz')):
                assert meta is None
            else:
                data = native.read(R, path, None)
                if meta is not None:
                    payloads.add(meta['payload'])
                    assert git('show', tree + ':' + meta['payload']) == (R / meta['payload']).read_bytes()
                    git('merge-base', '--is-ancestor', meta['tested_commit'], 'HEAD')
                else:
                    try: value = json.loads(raw, object_pairs_hook=native.unique)
                    except (ValueError, UnicodeError): value = None
                    assert not native.embedded_raw(value)
                assert not data.lstrip().startswith(b'diff --git ')
                assert Path(path).name != 'complete-diff.patch'
                if len(data) >= 16384:
                    key = native.digest(data)
                    identity = meta['payload'] if meta else path
                    assert key not in bulk or bulk[key] == identity
                    bulk[key] = identity
            row['classification'] = 'NATIVE_VALIDATED'
        except Exception as error:
            errors.append({'path': path, 'error': str(error) or type(error).__name__})
        rows.append(row)
    for path in own:
        if path.endswith(('.gz', '.xz')) and path not in payloads:
            errors.append({'path': path, 'error': 'orphan-payload'})
    total = sum(row['bytes'] for row in rows)
    if total > 16777216: errors.append({'error': 'aggregate-byte-cap', 'bytes': total})
    assert git('write-tree').decode().strip() == tree
    report = {'base': B, 'staged_tree': tree, 'native_source_sha256': native.digest((R / 'tools/harness/compact_evidence.py').read_bytes()), 'files': rows, 'total_bytes': total, 'errors': errors}
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'tree': tree, 'files': len(rows), 'bytes': total, 'errors': errors}))
    return bool(errors)

if __name__ == '__main__':
    raise SystemExit(main())
