"""Read-only exact original and complete immutable KL036 storage/history audits."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = '3ec7f7a38d974256a928c3687f63e4d90019e42b'
HEAD = '1fee7a4ef9ecb484da24522962a6df4d4c2bd9b9'
ORIGINAL = 'f93364d90aaae9b0b62706fd4e4fe395a8cd8ec5'
PATH = 'docs/exec-plans/reviews/KL-036/SECURITY_DATA_BOUNDARY/audit.py'
SHA256 = 'a602ee684cdd7b4d8169388d2a2fe821fc6bc5beadf0d69a593c2ed260ffe382'
SPEC = importlib.util.spec_from_file_location('compact', ROOT / 'tools/harness/compact_evidence.py')
assert SPEC and SPEC.loader
ce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ce)


def main() -> None:
    raw = ce.blob(ROOT, PATH, ORIGINAL)
    tree = ce.git(ROOT, 'ls-tree', ORIGINAL, '--', PATH).decode().strip()
    assert tree.startswith('100644 blob cde206aee1eb240862863069104ad291ff98dedb\t')
    assert len(raw) == 8063 and ce.digest(raw) == SHA256
    assert raw == (Path(__file__).parent / 'original-reader.fixture').read_bytes()
    assert ce.envelope(raw) is None and ce.reencoding_record(raw) is None
    assert ce.read(ROOT, PATH, ORIGINAL) == raw
    expected = set()
    for revision, identity in ((BASE, 'HG-054'), (HEAD, 'KL-036')):
        for path in ce.git(ROOT, 'ls-tree', '-r', '--name-only', revision, '--',
                           'docs/exec-plans/evidence/' + identity,
                           'docs/exec-plans/reviews/' + identity).decode().splitlines():
            if Path(path).name == ce.REENCODING_NAME:
                expected.add(path)
    history_errors, reached = ce.reencoding_audit(ROOT, BASE, HEAD, 'KL-036')
    print(json.dumps({'history_errors': history_errors, 'validated_maps': sorted(reached)}), flush=True)
    storage = ce.audit(ROOT, BASE, HEAD, 'KL-036')
    report = {'purpose': 'READ_ONLY_COMPATIBILITY_NOT_TASK_APP_OR_ADMISSION_PASS',
              'candidate': ce.git(ROOT, 'rev-parse', 'HEAD').decode().strip(),
              'base': BASE, 'head': HEAD, 'original_revision': ORIGINAL,
              'original_blob': tree.split()[2], 'original_bytes': len(raw),
              'original_sha256': ce.digest(raw), 'expected_maps': sorted(expected),
              'validated_maps': sorted(reached), 'history_errors': history_errors,
              'storage_audit': storage}
    scratch = Path('/private/tmp/hg056-compatibility-' + report['candidate'] + '.json')
    scratch.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))
    assert expected and reached == expected, 'incomplete map inventory'
    assert not history_errors and not storage['errors'], 'actual audit errors'


if __name__ == '__main__':
    main()
