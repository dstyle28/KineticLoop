"""Independent immutable-object/provenance audit; never imports historical source."""
import collections
import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from _pytest.junitxml import mangle_test_address
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
B = '9700a1b95d05c856897f74f125cfdf6fb3f6e646'
T = '74c93c06e83cd5087ecd3b4cc11320b88b246616'
R = '337146e1927ba0f57995d4af26f4108cfc95d7a5'
PYTHON = '/Users/davetian/Personal_Projects/KineticLoop/.venv/bin/python'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, timeout=30)


def read(rev, path):
    tree = git('ls-tree', '-z', '-l', rev, '--', path).rstrip(b'\0')
    meta, actual = tree.split(b'\t')
    mode, kind, oid, size = meta.split()
    assert actual.decode() == path and mode in (b'100644', b'100755') and kind == b'blob'
    assert int(size) <= 32 * 1024 * 1024
    data = git('cat-file', 'blob', oid.decode())
    assert len(data) == int(size)
    return data


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(read(R, path))


cache = {}


def payload(ref):
    if ref in cache:
        return cache[ref]
    env = load(ref)
    stored = read(R, env['payload'])
    assert len(stored) == env['stored_bytes'] and digest(stored) == env['stored_sha256']
    assert env['kineticloop_evidence'] == 'gzip-v1'
    raw = gzip.decompress(stored)
    assert len(raw) == env['raw_bytes'] and digest(raw) == env['raw_sha256']
    cache[ref] = (env, raw)
    return env, raw


git('merge-base', '--is-ancestor', B, T)
git('merge-base', '--is-ancestor', T, R)
assert git('rev-parse', R + '^').decode().strip() == T
record = yaml.safe_load(read(R, 'docs/exec-plans/governance/HG-059.yaml'))
Draft202012Validator(load('HARNESS_CHANGE.schema.json')).validate(record)
assert record['base_commit'] == B and record['tested_commit'] == T
assert record['change_status'] == 'PASS' and record['packets_refined'] == []
changed = git('diff', '--name-only', B, R).decode().splitlines()
assert set(changed) == set(record['files_changed'])
allowed = {'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
           'REVIEW_SOURCE_DECLARATIONS.schema.json', 'docs/harness/REVIEW_SOURCE_DECLARATIONS.json',
           'docs/harness/THREAD_REVIEW_CONTRACT.md', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
           'docs/harness/EVIDENCE_STORAGE_POLICY.md', 'docs/exec-plans/active/HG-058.md',
           'tools/harness/validate_harness.py', 'tests/harness/test_validator.py',
           'docs/exec-plans/governance/HG-059.yaml'}
assert all(p in allowed or p.startswith(('docs/exec-plans/evidence/HG-059/',
                                        'docs/exec-plans/reviews/HG-059/')) for p in changed)
for path in git('diff', '--name-only', T, R).decode().splitlines():
    assert path in {'HARNESS_DOCUMENT_MANIFEST.json', 'docs/exec-plans/governance/HG-059.yaml'} or path.startswith('docs/exec-plans/evidence/HG-059/')
index = load('CURRENT_DOCUMENT_INDEX.json')
for entry in index['documents'] + index['machine_readable']:
    assert digest(read(R, entry['path'])) == entry['sha256']
manifest = load('HARNESS_DOCUMENT_MANIFEST.json')
for entry in manifest['files']:
    data = read(R, entry['path'])
    assert len(data) == entry['bytes'] and digest(data) == entry['sha256']

checks = load('docs/exec-plans/evidence/HG-059/checks-74c93c06e83c/CHECK_INDEX.json')
declarations = load('docs/harness/REVIEW_SOURCE_DECLARATIONS.json')
Draft202012Validator(load('REVIEW_SOURCE_DECLARATIONS.schema.json')).validate(declarations)
source_identities = []
for declaration in declarations['declarations']:
    original = declaration['original_review_record_commit']
    path = declaration['review_record_path']
    git('merge-base', '--is-ancestor', original, B)
    record_bytes = read(original, path)
    assert record_bytes == read(B, path) == read(R, path)
    assert git('rev-parse', original + ':' + path).decode().strip() == declaration['original_review_record_blob']
    review = json.loads(record_bytes)
    Draft202012Validator(load('THREAD_REVIEW.schema.json')).validate(review)
    assert (review['task_identity'], review['review_type'], review['reviewed_head_sha']) == (
        declaration['owner'], declaration['review_type'], declaration['reviewed_head_sha'])
    assert declaration['reference'] in review['evidence_refs']
    revision = declaration['reviewed_head_sha']
    edges = []
    if not git('ls-tree', revision, '--', declaration['reference']).strip():
        prefix = 'docs/exec-plans/reviews/' + declaration['owner'].split('/')[1] + '/'
        assert declaration['reference'].startswith(prefix)
        git('merge-base', '--is-ancestor', revision, original)
        for commit in git('rev-list', '--reverse', revision + '..' + original).decode().splitlines():
            parents = git('rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
            assert len(parents) == 1
            paths = git('diff-tree', '-z', '--no-commit-id', '--name-only', '-r', parents[0], commit).decode().rstrip('\0').split('\0')
            assert all(p.startswith(prefix) for p in paths)
            edges.append({'commit': commit, 'changed_path_count': len(paths)})
        revision = original
    source = read(revision, declaration['reference'])
    assert len(source) <= 256 * 1024
    owner_record = yaml.safe_load(read(original, 'docs/exec-plans/governance/' + declaration['owner'].split('/')[1] + '.yaml'))
    assert declaration['reference'] not in {check['evidence_ref'] for check in owner_record['checks_run']}
    source_identities.append({'owner': declaration['owner'], 'type': declaration['review_type'],
                              'reference': declaration['reference'], 'selected_revision': revision,
                              'source_bytes': len(source), 'source_sha256': digest(source),
                              'source_blob': git('rev-parse', revision + ':' + declaration['reference']).decode().strip(),
                              'fallback_edges': edges, 'original_review_bytes_preserved': True})
assert checks['tested_commit'] == T
assert {c['check_id'] for c in checks['checks']} == {'definitions', 'validator', 'unit', 'harness', 'lint', 'typecheck', 'authority', 'diff'}
summary = []
by_check = {c['check_id']: c for c in record['checks_run']}
for c in checks['checks']:
    assert c['tested_commit'] == T and c['exit_code'] == 0
    expected = by_check[c['check_id']]
    assert expected['command'] == c['command'] and expected['result'] == 'PASS'
    assert expected['evidence_ref'] == c['output_ref']
    env, raw = payload(c['output_ref'])
    assert env['tested_commit'] == T and env['command'] == c['command'] and env['exit_code'] == 0
    row = {'check_id': c['check_id'], 'exit_code': 0, 'output_sha256': digest(raw)}
    refs = c.get('evidence_refs', [])
    for ref in refs:
        assert payload(ref)[0]['tested_commit'] == T
    if c['check_id'] in {'validator', 'unit', 'harness'}:
        collection = json.loads(payload(next(r for r in refs if 'collection.json' in r))[1])
        execution = json.loads(payload(next(r for r in refs if 'execution.json' in r))[1])
        xml = ET.fromstring(payload(next(r for r in refs if 'junit' in r))[1])
        ids = collection['collections']['serial']
        assert len(ids) == len(set(ids)) == c['cases']
        assert collection['errors'] == [] and collection['exit_code'] == 0
        assert execution['errors'] == [] and execution['exit_code'] == 0
        assert all(v == ids for v in execution['collections'].values())
        assert collections.Counter(execution['started']) == collections.Counter(ids)
        phases = collections.Counter((r['nodeid'], r['phase'], r['outcome']) for r in execution['reports'])
        assert phases == collections.Counter((n, p, 'passed') for n in ids for p in ('setup', 'call', 'teardown'))
        cases = list(xml.iter('testcase'))
        assert len(cases) == len(ids)
        assert not any(list(case) for case in cases)
        expected_xml = collections.Counter(('.'.join(mangle_test_address(n)[:-1]), mangle_test_address(n)[-1]) for n in ids)
        assert expected_xml == collections.Counter((case.attrib['classname'], case.attrib['name']) for case in cases)
        for suite in xml.iter('testsuite'):
            assert all(suite.attrib[k] == '0' for k in ('errors', 'failures', 'skipped'))
        row.update(cases=len(ids), phase_reports=len(execution['reports']), junit_identity_match=True,
                   collection_sha256=digest(payload(next(r for r in refs if 'collection.json' in r))[1]))
        if c['check_id'] == 'harness':
            manifest_data = json.loads(payload(next(r for r in refs if 'manifest' in r))[1])
            assert manifest_data['tested_commit'] == T and not manifest_data['dirty_source']
            assert manifest_data['workers'] == 2 and manifest_data['execution_complete']
            assert manifest_data['errors'] == [] and manifest_data['pytest_exit_code'] == 0
            artifacts = {Path(r).name.replace('.json.json', '.json'): payload(r)[1] for r in refs}
            for item in manifest_data['files']:
                matching = [raw for raw in artifacts.values() if digest(raw) == item['sha256']]
                if matching:
                    assert len(matching[0]) == item['bytes']
            row['clean_source_workers'] = 2
    summary.append(row)
# Every compact author artifact, including superseded failures, retains stored/raw integrity.
envelope_count = 0
for path in changed:
    if path.startswith('docs/exec-plans/evidence/HG-059/') and path.endswith('.json'):
        obj = json.loads(read(R, path))
        if isinstance(obj, dict) and obj.get('kineticloop_evidence') == 'gzip-v1':
            payload(path)
            envelope_count += 1
# Repeat the bounded definition oracle, retaining only its actual result identity and compact facts.
cmd = [PYTHON, str(ROOT / 'docs/exec-plans/evidence/HG-059/verify_definitions.py'), '--base', B, '--tested', T]
run = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=60)
assert run.returncode == 0, run.stderr.decode()
verified = json.loads(run.stdout)
assert verified['status'] == 'PASS' and len(verified['tuples']) == 6
result = {'reviewed_head_sha': R, 'base_commit': B, 'tested_commit': T, 'status': 'PASS',
          'changed_files': len(changed), 'scope_and_governance_projection': 'exact',
          'index_entries_verified': len(index['documents']) + len(index['machine_readable']),
          'manifest_entries_verified': len(manifest['files']), 'compact_envelopes_verified': envelope_count,
          'independently_verified_source_identities': source_identities,
          'author_checks': summary,
          'definition_oracle': {'argv': cmd, 'exit_code': run.returncode, 'stdout_sha256': digest(run.stdout),
                                'tuples': 6, 'negative_cases': len(verified['negative_definitions'])},
          'historical_source_executed': False, 'full_suites_rerun': False,
          'root_installation_admission_app_full_db_hosted_merge': 'NOT_RUN by this review'}
(OUT / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
