"""Bound governance definitions to immutable Git; never execute historical source."""
import argparse
import ast
import copy
import hashlib
import json
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[4]
BASE = '9700a1b95d05c856897f74f125cfdf6fb3f6e646'
SCHEMA = 'REVIEW_SOURCE_DECLARATIONS.schema.json'
DECL = 'docs/harness/REVIEW_SOURCE_DECLARATIONS.json'
VALIDATOR = 'tools/harness/validate_harness.py'
FINAL = 'ada3b2f0e4f24f2b1fe857ad32c95e8ff6c6b983'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, timeout=30)


def raw(revision, path):
    entry = git('ls-tree', '-l', '-z', revision, '--', path).rstrip(b'\0')
    metadata, actual = entry.split(b'\t')
    mode, kind, oid, size = metadata.split()
    assert mode in (b'100644', b'100755') and kind == b'blob' and actual.decode() == path
    assert int(size) <= 1024 * 1024
    value = git('cat-file', 'blob', oid.decode())
    assert len(value) == int(size)
    return oid.decode(), value


def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate-key')
        obj[key] = value
    return obj


def declarations(data, schema):
    if len(data) > 256 * 1024:
        raise ValueError('document-budget')
    obj = json.loads(data, object_pairs_hook=unique)
    Draft202012Validator(schema).validate(obj)
    seen = set()
    for item in obj['declarations']:
        key = tuple(item[k] for k in ('owner', 'review_type', 'review_record_path', 'reference'))
        if key in seen:
            raise ValueError('duplicate-conflicting-tuple')
        seen.add(key)
        owner = item['owner'].split('/')[1]
        if item['review_record_path'] != f'docs/exec-plans/reviews/{owner}/{item["review_type"]}.json':
            raise ValueError('foreign-record-owner')
    return obj


def functions(data):
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(data).body if isinstance(node, ast.FunctionDef)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--tested', required=True)
    args = parser.parse_args()
    assert args.base == BASE
    tested = git('rev-parse', args.tested).decode().strip()
    git('merge-base', '--is-ancestor', BASE, tested)
    schema = json.loads(raw(tested, SCHEMA)[1])
    Draft202012Validator.check_schema(schema)
    obj = declarations(raw(tested, DECL)[1], schema)
    assert len(obj['declarations']) == 6
    review_schema = json.loads(raw(BASE, 'THREAD_REVIEW.schema.json')[1])
    identities = []
    expected = [
        ('9a34163c2b5e726d1a1d4a9af2dd6c00e7235b64', 35709),
        ('9a34163c2b5e726d1a1d4a9af2dd6c00e7235b64', 35709),
        ('9a34163c2b5e726d1a1d4a9af2dd6c00e7235b64', 35709),
        ('fb33e99c3a47c9c1b60fe27ad30ab5ea42e5e329', 6697),
        ('e565722e8f495008d00962304ecd2522c5100740', 6729),
        ('816e9ff76f8f85676d854627bd34a35b742f6fb7', 10728)]
    for item, source_identity in zip(obj['declarations'], expected, strict=True):
        commit = item['original_review_record_commit']
        git('merge-base', '--is-ancestor', commit, BASE)
        oid, value = raw(commit, item['review_record_path'])
        assert oid == item['original_review_record_blob']
        assert len(value) <= 256 * 1024
        review = json.loads(value, object_pairs_hook=unique)
        Draft202012Validator(review_schema).validate(review)
        assert (review['task_identity'], review['review_type'], review['reviewed_head_sha']) == (
            item['owner'], item['review_type'], item['reviewed_head_sha'])
        assert item['reference'] in review['evidence_refs']
        assert raw(BASE, item['review_record_path']) == raw(tested, item['review_record_path']) == (oid, value)
        revision = item['reviewed_head_sha']
        entry = git('ls-tree', revision, '--', item['reference'])
        if not entry.strip():
            prefix = 'docs/exec-plans/reviews/' + item['owner'].split('/')[1] + '/'
            assert item['reference'].startswith(prefix)
            git('merge-base', '--is-ancestor', revision, commit)
            edges = git('rev-list', '--reverse', revision + '..' + commit).decode().splitlines()
            for edge in edges:
                parents = git('rev-list', '--parents', '-n', '1', edge).decode().split()[1:]
                assert len(parents) == 1
                paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', parents[0], edge).decode().splitlines()
                assert all(path.startswith(prefix) for path in paths)
            revision = commit
        source_oid, source = raw(revision, item['reference'])
        assert (source_oid, len(source)) == source_identity
        # Only exact bytes/identity are inspected: no eval/import of original source.
        identities.append({'owner': item['owner'], 'type': item['review_type'],
                           'record_blob': oid, 'source_blob': source_oid,
                           'source_bytes': len(source), 'revision': revision,
                           'source_sha256': hashlib.sha256(source).hexdigest(),
                           'purpose': 'source citation; no output verdict'})
    negatives = []
    for name in ('unknown', 'duplicate', 'conflict', 'foreign', 'identity', 'traversal', 'sha', 'budget', 'purpose', 'count'):
        bad = copy.deepcopy(obj)
        if name == 'unknown': bad['extra'] = True
        if name == 'duplicate': bad['declarations'].append(copy.deepcopy(bad['declarations'][0]))
        if name == 'conflict':
            bad['declarations'].append(dict(bad['declarations'][0], original_review_record_commit='0' * 40))
        if name == 'foreign': bad['declarations'][0]['review_record_path'] = 'docs/exec-plans/reviews/HG-047/GENERAL.json'
        if name == 'identity': bad['declarations'][0]['owner'] = 'HG-045'
        if name == 'traversal': bad['declarations'][0]['reference'] = 'tests/../secret'
        if name == 'sha': bad['declarations'][0]['reviewed_head_sha'] = 'abc1234'
        if name == 'purpose': bad['declarations'][0]['purpose'] = 'EXECUTION'
        if name == 'count': bad['declarations'] *= 11
        data = json.dumps(bad).encode()
        if name == 'budget': data += b' ' * (256 * 1024)
        try: declarations(data, schema)
        except Exception: negatives.append(name)
        else: raise AssertionError(name)
    try: declarations(b'{"format":1,"format":2}', schema)
    except ValueError: negatives.append('duplicate-json-key')
    else: raise AssertionError('duplicate-json-key')
    before, after = functions(raw(BASE, VALIDATOR)[1]), functions(raw(tested, VALIDATOR)[1])
    assert {name for name in before if before[name] != after.get(name)} == {'governance_allowed_patterns', 'validate'}
    assert set(after) - set(before) == {'source_lineage_projection_errors'}
    # Frozen authorities, execution readers, KL081 and original attempts stay untouched.
    for path in ('THREAD_REVIEW.schema.json', 'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json',
                 'tools/harness/compact_evidence.py', 'tools/harness/local_gate.py',
                 'docs/exec-plans/active/KL-081.md', 'KineticLoop_Harness_Backlog_v0.2.json'):
        assert raw(BASE, path) == raw(tested, path), path
    for typ in ('GENERAL', 'SECURITY_DATA_BOUNDARY'):
        review = json.loads(raw(FINAL, f'docs/exec-plans/reviews/HG-058/{typ}.json')[1])
        assert review['status'] == 'CHANGES_REQUIRED'
        assert review['reviewed_head_sha'] == '6081301453f30496e6a06b12e20098c4a05a9fa4'
    for pin in (FINAL, '36b942f3087497d0c6609839df5e04398ec8bc4e',
                '6081301453f30496e6a06b12e20098c4a05a9fa4',
                'd1c1411eae72cbc3499e5fbdc8a266dfde19d003',
                '6af4b99f6895ac63686f3a560cae2d01a8a40a17'):
        git('cat-file', '-e', pin + '^{commit}')
        assert subprocess.run(['git', 'merge-base', '--is-ancestor', pin, tested], cwd=ROOT).returncode == 1
    mapping = 'docs/exec-plans/evidence/HG-058/recovery-conversion/COMPACT_REENCODING.json'
    map_oid, map_bytes = raw('d1c1411eae72cbc3499e5fbdc8a266dfde19d003', mapping)
    assert map_oid == 'fab5eda72851219c32694fe17414454d770d2099'
    assert hashlib.sha256(map_bytes).hexdigest() == 'fe500309a9b93702fa0d06f63c4fc1b0c28afa7965436a120a7a1cab8e6d47f2'
    contract = raw(tested, 'docs/harness/THREAD_REVIEW_CONTRACT.md')[1].decode()
    for phrase in ('REVIEW_SOURCE_LINEAGE', 'storage_bookkeeping_only', 'review_only_suffix',
                   'Selected task', 'Selected governance', 'Integration review', 'Global validate',
                   'same path used as output', 'evidence-envelope-json', 'including reverted',
                   'duplicate or conflicting', 'exact immutable validation revision'):
        assert phrase in contract, phrase
    packet = raw(tested, 'docs/exec-plans/active/HG-058.md')[1].decode()
    old_packet = raw(BASE, 'docs/exec-plans/active/HG-058.md')[1].decode()
    old_checks = old_packet.split('## Required author checks')[1].split('## Reviews, installation')[0]
    for line in old_checks.splitlines():
        if line.startswith('- ') and 'audit --base' not in line and '--ci-pr-base' not in line:
            assert line in packet, line
    for phrase in ('5da0e253', BASE, 'first-retirement', 'B-live', 'controller_files', 'fullDB',
                   'all 16', 'cleanup', 'normal merge', 'same-physical-path output decode failure'):
        assert phrase in packet, phrase
    index = json.loads(raw(tested, 'CURRENT_DOCUMENT_INDEX.json')[1])
    assert {SCHEMA, DECL} <= {e['path'] for e in index['machine_readable']}
    for entry in index['documents'] + index['machine_readable']:
        assert hashlib.sha256(raw(tested, entry['path'])[1]).hexdigest() == entry['sha256'], entry['path']
    for entry in json.loads(raw(tested, 'HARNESS_DOCUMENT_MANIFEST.json')[1])['files']:
        value = git('show', tested + ':' + entry['path'])
        assert len(value) == entry['bytes'] and hashlib.sha256(value).hexdigest() == entry['sha256']
    # Literal scope independently mirrors packet paths, without importing changed code.
    allowed = {SCHEMA, DECL, VALIDATOR, 'tests/harness/test_validator.py', 'CURRENT_DOCUMENT_INDEX.json',
               'HARNESS_DOCUMENT_MANIFEST.json', 'docs/harness/THREAD_REVIEW_CONTRACT.md',
               'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md', 'docs/harness/EVIDENCE_STORAGE_POLICY.md',
               'docs/exec-plans/active/HG-058.md', 'docs/exec-plans/governance/HG-059.yaml'}
    changed = git('diff', '--name-only', BASE, tested).decode().splitlines()
    assert all(p in allowed or p.startswith(('docs/exec-plans/evidence/HG-059/',
                                            'docs/exec-plans/reviews/HG-059/')) for p in changed)
    print(json.dumps({'status': 'PASS', 'base': BASE, 'tested': tested, 'tuples': identities,
                      'negative_definitions': negatives, 'changed_paths': changed,
                      'historical_failures': 'preserved; no task or requirement PASS'}))


if __name__ == '__main__':
    main()
