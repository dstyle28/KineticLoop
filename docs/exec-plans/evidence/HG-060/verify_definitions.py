"""Verify HG060 literal definitions against immutable Git objects, without source execution."""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[4]
BASE = '6d24db615b7c6e517478530d130feecd678bc123'
FROZEN = '3965cac382d333bd97f6c67fec8ecbe805b5932f'
EVIDENCE = 'docs/exec-plans/evidence/HG-060/'
DECLARATIONS = 'docs/harness/REVIEW_SOURCE_DECLARATIONS.json'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, timeout=60)


def raw(revision, path):
    meta, name = git('ls-tree', '-l', revision, '--', path).strip().split(b'\t')
    mode, kind, oid, size = meta.split()
    assert mode in (b'100644', b'100755') and kind == b'blob' and name.decode() == path
    assert int(size) <= 8 * 1024 * 1024
    data = git('cat-file', 'blob', oid.decode())
    assert len(data) == int(size)
    return mode.decode(), oid.decode(), data


def pinned(pin):
    mode, oid, data = raw(pin['revision'], pin['path'])
    assert (mode, oid, len(data), hashlib.sha256(data).hexdigest()) == (
        pin['mode'], pin['blob'], pin['bytes'], pin['sha256'])
    return data


def functions(data):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(data).body
            if isinstance(n, ast.FunctionDef)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default=BASE)
    parser.add_argument('--tested', default='HEAD')
    args = parser.parse_args()
    assert args.base == BASE
    tested = git('rev-parse', args.tested).decode().strip()
    git('merge-base', '--is-ancestor', BASE, tested)
    declaration_schema = json.loads(raw(BASE, 'REVIEW_SOURCE_DECLARATIONS.schema.json')[2])
    before = json.loads(raw(BASE, DECLARATIONS)[2])
    after = json.loads(raw(tested, DECLARATIONS)[2])
    Draft202012Validator(declaration_schema).validate(after)
    assert after['format'] == before['format'] and len(after['declarations']) == 8
    assert after['declarations'][:6] == before['declarations']
    # Original serialization is retained verbatim up to the former closing list.
    assert raw(tested, DECLARATIONS)[2].startswith(raw(BASE, DECLARATIONS)[2].rsplit(b'\n  ]', 1)[0])
    identities = json.loads(raw(tested, EVIDENCE + 'SOURCE_IDENTITIES.json')[2])
    assert after['declarations'][6:] == [r['declaration'] for r in identities]
    assert [r['declaration']['owner'] for r in identities] == [
        'harness-governance-v0.1/HG-042', 'harness-governance-v0.1/HG-043']
    for row in identities:
        item = row['declaration']
        record = json.loads(pinned(row['record']))
        Draft202012Validator(json.loads(raw(BASE, 'THREAD_REVIEW.schema.json')[2])).validate(record)
        assert (record['task_identity'], record['review_type'], record['reviewed_head_sha']) == (
            item['owner'], 'GENERAL', item['reviewed_head_sha'])
        assert item['reference'] in record['evidence_refs']
        assert item['reference'] == 'tests/harness/test_review_evidence_provenance.py'
        git('merge-base', '--is-ancestor', item['reviewed_head_sha'], item['original_review_record_commit'])
        git('merge-base', '--is-ancestor', item['original_review_record_commit'], BASE)
        assert raw(BASE, item['review_record_path']) == raw(tested, item['review_record_path'])
        source = pinned(row['source'])
        assert (row['source']['mode'], row['source']['blob'], len(source), hashlib.sha256(source).hexdigest()) == (
            '100644', 'e6e18454c7fef54e7d2bd704ab63be56bc685cfd', 14776,
            '0cac4692d4188b5bfb9cfa3f9d6436ba905ebe8d8c90640f2445eea69f28b8b7')
    disposition = json.loads(raw(tested, EVIDENCE + 'PRESERVATION_DISPOSITION.json')[2])
    expected_names = ['DIRECT_REVIEW_APPEND', 'GENERAL_COMMAND_INDEX', 'RAW_REVIEW_APPEND',
                      'RECOVERY_REVIEW_APPEND_INDEX', 'REVIEW_APPEND_INDEX', 'SECURITY_COMMAND_INDEX',
                      'SECURITY_narrow-results', 'SECURITY_preservation', 'WRAPPER_REVIEW_APPEND']
    assert disposition['source_revision'] == FROZEN and len(disposition['entries']) == 9
    references = []
    for row, name in zip(disposition['entries'], expected_names, strict=True):
        original = row['original']
        assert original['revision'] == FROZEN
        assert original['path'] == f'docs/exec-plans/reviews/HG-058/{name}.json'
        data = pinned(original)
        obj = json.loads(data)
        assert 'kineticloop_evidence' not in obj and 'compact_reencoding' not in obj
        assert row['destination'] == f'docs/exec-plans/reviews/HG-058/preserved-metadata/{name}.json'
        assert not git('ls-tree', tested, '--', row['destination']).strip()
        for revision in (FROZEN, BASE):
            run = subprocess.run(['git', 'grep', '-l', '-F', original['path'], revision, '--'],
                                 cwd=ROOT, capture_output=True, timeout=60)
            assert run.returncode in (0, 1)
            for line in run.stdout.decode().splitlines():
                path = line.split(':', 1)[1]
                _, oid, value = raw(revision, path)
                references.append(dict(revision=revision, reference_path=path,
                                       referenced_original=original['path'], reference_blob=oid,
                                       reference_sha256=hashlib.sha256(value).hexdigest()))
    assert references == disposition['literal_references']
    blocker = json.loads(raw(tested, EVIDENCE + 'BLOCKER_RECORD.json')[2])
    assert blocker['revision'] == FROZEN and blocker['change_status'] == 'SPEC_CHANGE_REQUIRED'
    assert any(c['result'] == 'FAIL' for c in blocker['checks'])
    assert any(c['result'] == 'NOT_RUN' for c in blocker['checks'])
    _, oid, value = raw(FROZEN, blocker['path'])
    assert oid == blocker['blob'] and hashlib.sha256(value).hexdigest() == blocker['sha256']
    regression = json.loads(raw(tested, EVIDENCE + 'REGRESSION_INPUTS.json')[2])
    assert len(regression) == 14
    for row in regression:
        envelope = json.loads(pinned(row['artifact_identity']))
        payload = pinned(row['payload_identity'])
        assert envelope['payload'] == row['payload_identity']['path']
        assert (len(payload), hashlib.sha256(payload).hexdigest()) == (
            envelope['stored_bytes'], envelope['stored_sha256'])
        assert row['producer'] == dict(tested_commit=envelope['tested_commit'], command=envelope['command'],
                                       observed_exit=envelope['exit_code'])
        assert row['recovered_identity'] == dict(bytes=envelope['raw_bytes'], sha256=envelope['raw_sha256'])
    # Read source identities only; no import/eval/exec of any historical input.
    validator = 'tools/harness/validate_harness.py'
    old, new = functions(raw(BASE, validator)[2]), functions(raw(tested, validator)[2])
    assert {n for n in old if old[n] != new.get(n)} == {'governance_allowed_patterns', 'validate'}
    assert set(new) - set(old) == {'bounded_recovery_projection_errors'}
    for path in ('REVIEW_SOURCE_DECLARATIONS.schema.json', 'HARNESS_CHANGE.schema.json',
                 'THREAD_REVIEW.schema.json', 'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json',
                 'tools/harness/compact_evidence.py', 'tools/harness/local_gate.py',
                 'docs/exec-plans/active/KL-081.md', 'KineticLoop_Harness_Backlog_v0.2.json'):
        assert raw(BASE, path) == raw(tested, path), path
    for name, phrases in {
        'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md': (
            'Global validation enumerates every', 'Selected ci-pr independently requires',
            'execution_state', 'INTERRUPTED', 'command_exit_code null', 'driver_exit_code',
            'fabricated-PASS', 'SKIPPED cannot be stored', 'first-parent3965',
            '256KiB candidate', '1024-work/1MiB', 'No identity exemption',
            'no retroactive collector/JUnit format migration', 'status-only diagnostic'),
        'docs/harness/EVIDENCE_STORAGE_POLICY.md': (
            'nine ordinary non-envelope', 'byte-for-byte', 'RECEIPT.json', 'PATH_INVENTORY.json',
            'No old report', 'not storage migration authority', 'firstcommit FAIL'),
        'docs/exec-plans/active/HG-058.md': (
            'normal HG060 merge', 'first-parent3965', 'no task-ID exemption',
            'all eight declared tuples', 'test_planning_fixture_scope.py', 'finite known-failure set'),
    }.items():
        text = raw(tested, name)[2].decode()
        assert all(phrase in text for phrase in phrases), name
    packet_before = raw(BASE, 'docs/exec-plans/active/HG-058.md')[2].decode()
    packet_after = raw(tested, 'docs/exec-plans/active/HG-058.md')[2].decode()
    checks = packet_before.split('## Required author checks')[1].split('## Reviews, installation')[0]
    assert checks in packet_after
    index = json.loads(raw(tested, 'CURRENT_DOCUMENT_INDEX.json')[2])
    old_index = json.loads(raw(BASE, 'CURRENT_DOCUMENT_INDEX.json')[2])
    for section in ('documents', 'machine_readable'):
        assert [{k:v for k,v in e.items() if k != 'sha256'} for e in index[section]] == [
            {k:v for k,v in e.items() if k != 'sha256'} for e in old_index[section]]
        for entry in index[section]:
            assert hashlib.sha256(raw(tested, entry['path'])[2]).hexdigest() == entry['sha256']
    manifest = json.loads(raw(tested, 'HARNESS_DOCUMENT_MANIFEST.json')[2])
    for entry in manifest['files']:
        value = raw(tested, entry['path'])[2]
        assert len(value) == entry['bytes'] and hashlib.sha256(value).hexdigest() == entry['sha256']
    allowed = {DECLARATIONS, validator, 'tests/harness/test_validator.py', 'CURRENT_DOCUMENT_INDEX.json',
               'HARNESS_DOCUMENT_MANIFEST.json', 'docs/harness/THREAD_REVIEW_CONTRACT.md',
               'docs/harness/EVIDENCE_STORAGE_POLICY.md', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
               'docs/exec-plans/active/HG-058.md', 'docs/exec-plans/governance/HG-060.yaml'}
    changed = git('diff', '--name-only', BASE, tested).decode().splitlines()
    assert all(p in allowed or p.startswith((EVIDENCE, 'docs/exec-plans/reviews/HG-060/')) for p in changed)
    for pin in (FROZEN, '7496d0d0696a6a870d164b15cf1bbe201e942d5e',
                'd1c1411eae72cbc3499e5fbdc8a266dfde19d003', '6af4b99f6895ac63686f3a560cae2d01a8a40a17'):
        git('cat-file', '-e', pin + '^{commit}')
        assert subprocess.run(['git', 'merge-base', '--is-ancestor', pin, tested], cwd=ROOT).returncode == 1
    print(json.dumps(dict(status='PASS', base=BASE, tested=tested, source_additions=2,
                          preserved_definitions=9, literal_references=len(references), regression_inputs=14,
                          changed_paths=changed, meaning='Definitions only; no HG058, execution or release PASS')))


if __name__ == '__main__':
    main()
