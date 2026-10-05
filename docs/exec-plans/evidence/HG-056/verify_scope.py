"""Verify the HG-056 literal scope and frozen bytes at immutable revisions."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EXACT = {'tools/harness/compact_evidence.py', 'tools/harness/validate_harness.py',
         'tests/harness/test_compact_evidence.py', 'tests/harness/test_review_evidence_provenance.py',
         'tests/harness/test_m3_milestone_closure.py', 'tests/harness/test_validator.py',
         'tests/harness/test_local_gate.py', 'docs/harness/EVIDENCE_STORAGE_POLICY.md',
         'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md', 'CURRENT_DOCUMENT_INDEX.json',
         'HARNESS_DOCUMENT_MANIFEST.json', 'docs/exec-plans/governance/HG-056.yaml'}
PREFIXES = ('docs/exec-plans/evidence/HG-056/', 'docs/exec-plans/reviews/HG-056/')


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', default='HEAD')
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
