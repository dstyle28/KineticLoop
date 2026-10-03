"""Independent GENERAL audit; inspect exact Git blobs, never ambient evidence."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zlib
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]
BASE = '034d6301316d0dade784a61b159c027b83fbce3a'
TESTED = 'f302b22c0838ef2928913392e7c2a6af9e8f8698'
HEAD = '26482f7f7147fe33cf37d8028574196c97c82ec6'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def blob(path, revision=HEAD):
    entry = git('ls-tree', revision, '--', path).decode().split()
    assert entry[0] == '100644' or entry[0] == '100755', (path, entry)
    return git('show', revision + ':' + path)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


record = yaml.safe_load(blob('docs/exec-plans/governance/HG-050.yaml'))
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
assert record['change_identity'] == 'harness-governance-v0.1/HG-050'
assert record['change_status'] == 'PASS' and record['packets_refined'] == []
changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
assert sorted(changed) == sorted(record['files_changed'])
allowed = {'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
           'tools/harness/github_app.py', 'tools/harness/validate_harness.py',
           'tests/harness/test_local_gate.py', 'docs/harness/LOCAL_DB_CI.md',
           'docs/exec-plans/governance/HG-050.yaml'}
assert all(p in allowed or p.startswith('docs/exec-plans/evidence/HG-050/')
           or p.startswith('docs/exec-plans/reviews/HG-050/') for p in changed)
git('merge-base', '--is-ancestor', BASE, TESTED)
git('merge-base', '--is-ancestor', TESTED, HEAD)
suffix = []
for commit in git('rev-list', '--reverse', TESTED + '..' + HEAD).decode().splitlines():
    parents = git('rev-list', '--parents', '-n', '1', commit).decode().split()
    assert len(parents) == 2
    paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', commit).decode().splitlines()
    assert all(p == 'docs/exec-plans/governance/HG-050.yaml'
               or p.startswith('docs/exec-plans/evidence/HG-050/') for p in paths)
    for p in paths:
        if '/evidence/' in p:
            assert subprocess.run(['git', 'cat-file', '-e', parents[1] + ':' + p],
                                  cwd=ROOT, capture_output=True).returncode != 0
    suffix.append({'commit': commit, 'paths': paths})
for p in allowed - {'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
                    'docs/exec-plans/governance/HG-050.yaml'}:
    assert blob(p) == blob(p, TESTED), p
index = json.loads(blob('CURRENT_DOCUMENT_INDEX.json'))
for entry in index['documents'] + index['machine_readable']:
    assert sha(blob(entry['path'])) == entry['sha256'], entry['path']
manifest = json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json'))
entries = manifest['files']
for entry in entries:
    raw = blob(entry['path'])
    assert sha(raw) == entry['sha256'] and len(raw) == entry['bytes'], entry['path']
raws = {}
envelopes = []
for p in changed:
    if not p.startswith('docs/exec-plans/evidence/HG-050/runs/') or not p.endswith('.json'):
        continue
    envelope = json.loads(blob(p))
    assert envelope['kineticloop_evidence'] == 'gzip-v1'
    payload = envelope['payload']
    assert payload.startswith('docs/exec-plans/evidence/HG-050/runs/')
    stored = blob(payload)
    assert len(stored) == envelope['stored_bytes'] and sha(stored) == envelope['stored_sha256']
    assert stored[:4] == b'\x1f\x8b\x08\x00' and stored[4:8] == b'\x00' * 4
    decoder = zlib.decompressobj(31)
    raw = decoder.decompress(stored) + decoder.flush()
    assert decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
    assert len(raw) == envelope['raw_bytes'] and sha(raw) == envelope['raw_sha256']
    assert Path(payload).name == sha(raw) + '.gz'
    assert envelope['tested_commit'] == TESTED
    raws[Path(p).name] = raw
    envelopes.append({'path': p, 'raw_bytes': len(raw), 'sha256': sha(raw),
                      'exit_code': envelope['exit_code'], 'counts': envelope['test_counts']})
for check in record['checks_run']:
    envelope = json.loads(blob(check['evidence_ref']))
    assert envelope['exit_code'] == 0 and envelope['command'] == check['command']
    assert check['result'] == 'PASS'
runs = {}
for prefix, expected_tests, expected_failures, expected_wrapper in [
        ('initial-failed', 1405, 0, 1), ('retry-failed', 1405, 1, 1),
        ('isolated-pass', 1405, 0, 0)]:
    junit = ET.fromstring(raws[prefix + '-harness-junit-xml.json'])
    cases = list(junit.iter('testcase'))
    counts = {'tests': len(cases), 'failures': sum(c.find('failure') is not None for c in cases),
              'errors': sum(c.find('error') is not None for c in cases),
              'skipped': sum(c.find('skipped') is not None for c in cases)}
    assert counts == {'tests': expected_tests, 'failures': expected_failures, 'errors': 0, 'skipped': 0}
    collection = json.loads(raws[prefix + '-harness-collection-json.json'])
    execution = json.loads(raws[prefix + '-harness-execution-json.json'])
    run_manifest = json.loads(raws[prefix + '-harness-manifest-json.json'])
    for entry in run_manifest['files']:
        raw = raws[prefix + '-harness-' + entry['path'].replace('.', '-') + '.json']
        assert len(raw) == entry['bytes'] and sha(raw) == entry['sha256']
    wrapper = json.loads(blob('docs/exec-plans/evidence/HG-050/runs/' + prefix + '-harness.json'))
    assert wrapper['exit_code'] == expected_wrapper
    collected = collection['collections']['serial']
    assert len(collected) == expected_tests and len(set(collected)) == expected_tests
    assert len(execution['collections']) == 2
    assert all(v == collected for v in execution['collections'].values())
    assert Counter(execution['started']) == Counter(collected)
    phases = Counter((r['nodeid'], r['phase']) for r in execution['reports'])
    assert len(execution['reports']) == expected_tests * 3
    assert all(phases[(n, p)] == 1 for n in collected for p in ('setup', 'call', 'teardown'))
    outcomes = Counter((r['phase'], r['outcome']) for r in execution['reports'])
    assert outcomes[('call', 'passed')] == expected_tests - expected_failures
    assert outcomes[('call', 'failed')] == expected_failures
    assert not any(r['outcome'] == 'skipped' for r in execution['reports'])
    assert not execution['errors'] and not collection['errors']
    assert run_manifest['tested_commit'] == TESTED and run_manifest['dirty_source'] is False
    assert run_manifest['exit_code'] == expected_wrapper
    assert run_manifest['pytest_exit_code'] == (1 if expected_failures else 0)
    if prefix == 'isolated-pass':
        assert run_manifest['execution_complete'] is True and not run_manifest['errors']
    if prefix == 'initial-failed':
        assert 'source-changed-during-execution' in run_manifest['errors']
    if prefix == 'retry-failed':
        assert b'unable to create temporary file: Invalid argument' in raws[prefix + '-harness.json']
    runs[prefix] = {'junit': counts, 'manifest': run_manifest,
                    'collected': len(collected), 'started': len(execution['started']),
                    'reports': len(execution['reports']),
                    'outcomes': {str(k): v for k, v in outcomes.items()},
                    'wrapper_raw': raws[prefix + '-harness.json'].decode()}
unit = ET.fromstring(raws['unit-junit.json'])
unit_cases = list(unit.iter('testcase'))
assert len(unit_cases) == 241 and all(c.find('failure') is None and c.find('error') is None
                                      and c.find('skipped') is None for c in unit_cases)
artifact_total = sum(len(blob(p)) for p in changed if '/evidence/' in p or '/reviews/' in p)
report = {'reviewed_head_sha': HEAD, 'base_commit': BASE, 'tested_commit': TESTED,
          'declared_exact_paths': changed, 'tested_to_reviewed_suffix': suffix,
          'derived_hashes_verified': True, 'envelopes': envelopes,
          'runs': runs, 'unit_tests': len(unit_cases), 'artifact_bytes': artifact_total}
(Path(__file__).parent / 'AUDIT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'envelopes': len(envelopes), 'unit_tests': len(unit_cases),
                  'harness_runs': {p: r['junit'] for p, r in runs.items()},
                  'artifact_bytes': artifact_total, 'status': 'PASS'}))
