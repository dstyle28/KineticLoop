"""Verify the HG-055 five-path scope and frozen bytes at immutable revisions."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EXACT = {'.github/workflows/ci.yml', 'tests/harness/test_ci_execution_ownership.py',
         'docs/exec-plans/governance/HG-055.yaml'}
PREFIXES = ('docs/exec-plans/evidence/HG-055/', 'docs/exec-plans/reviews/HG-055/')


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    base, head = (git('rev-parse', value + '^{commit}').decode().strip()
                  for value in (args.base, args.head))
    assert git('rev-parse', 'HEAD').decode().strip() == head, 'wrong checked-out head'
    subprocess.run(['git', 'merge-base', '--is-ancestor', base, head], cwd=ROOT, check=True)
    changed = git('diff', '--no-renames', '--name-only', '-z', base, head).decode().split('\0')[:-1]
    assert changed, 'empty change'
    for path in changed:
        assert path in EXACT or path.startswith(PREFIXES), 'out-of-scope:' + path
        assert all(part not in ('', '.', '..') for part in path.split('/')), 'invalid path'
        entry = git('ls-tree', '-z', head, '--', path)
        assert entry.startswith(b'100644 blob '), 'missing/nonregular:' + path
        assert entry.split(b'\t', 1)[1].rstrip(b'\0').decode() == path, 'wrong tree entry'
    frozen = json.loads(git('show', base + ':FROZEN_BASELINE.json'))
    retained = ['FROZEN_BASELINE.json', *[entry['path'] for entry in frozen['files']]]
    for path in retained:
        assert git('show', base + ':' + path) == git('show', head + ':' + path), path
    print(json.dumps({'base': base, 'head': head, 'changed_paths': changed,
                      'frozen_paths_verified': len(retained), 'status': 'PASS'}, sort_keys=True))


if __name__ == '__main__':
    main()
