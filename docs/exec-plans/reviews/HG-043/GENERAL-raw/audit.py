"""Independent GENERAL review source and check-evidence audit, HG043."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import jsonschema
import yaml

ROOT = Path.cwd()
HEAD = '2896d2422999fdf8a2cbca75eb316798c015ad17'
BASE = '1099d85bd4aa76ec8221700e55b4e77a84479126'
TESTED = 'bd3811fb283d9cbcca9bbb1dbd8d52bb0035f3ae'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path, revision=HEAD):
    return git('show', revision + ':' + path)

assert git('rev-parse', 'HEAD').decode().strip() == HEAD
changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
for path in changed:
    assert (ROOT / path).read_bytes() == blob(path), path
record_path = 'docs/exec-plans/governance/HG-043.yaml'
record = yaml.safe_load(blob(record_path))
jsonschema.validate(record, json.loads(blob('HARNESS_CHANGE.schema.json')))
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
assert record['change_status'] == 'PASS'
assert record['files_changed'] == changed
assert record['packets_refined'] == []
spec = importlib.util.spec_from_file_location('general_validator', ROOT / 'tools/harness/validate_harness.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
assert validator.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-043', 'tested') == []
for path in ('tools/harness/validate_harness.py', 'tests/harness/test_review_evidence_provenance.py',
             'docs/harness/THREAD_REVIEW_CONTRACT.md', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
             'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json'):
    assert blob(path, TESTED) == blob(path), path
checks = []
for entry in record['checks_run']:
    path = entry['evidence_ref']
    data = json.loads(blob(path))
    raw = data['raw_utf8'].encode()
    assert data['tested_commit'] == TESTED and data['base_commit'] == BASE
    assert data['evidence_ref'] == path
    assert data['result'] == entry['result'] == 'PASS' and data['exit_code'] == 0
    assert data['command'] == entry['command'] and data['check_id'] == entry['check_id']
    assert hashlib.sha256(raw).hexdigest() == data['raw_sha256']
    assert len(raw) == data['raw_byte_count']
    checks.append({'check_id': data['check_id'], 'source_blob': git('rev-parse', HEAD + ':' + path).decode().strip(),
                   'raw_sha256': data['raw_sha256'], 'raw_bytes': len(raw)})
assert {c['check_id'] for c in checks} == {'provenance', 'harness', 'unit', 'lint', 'typecheck', 'validation', 'replay', 'diff'}
index = json.loads(blob('CURRENT_DOCUMENT_INDEX.json'))
for group in ('documents', 'machine_readable'):
    for entry in index[group]:
        assert hashlib.sha256(blob(entry['path'])).hexdigest() == entry['sha256'], entry['path']
manifest = json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json'))
for entry in manifest['files']:
    data = blob(entry['path'])
    assert hashlib.sha256(data).hexdigest() == entry['sha256'], entry['path']
    if 'bytes' in entry:
        assert len(data) == entry['bytes'], entry['path']
assert git('diff', '--check', BASE, HEAD) == b''
report = {'reviewed_head_sha': HEAD, 'protected_base': BASE, 'tested_commit': TESTED,
          'status': 'PASS', 'checked_files': len(changed), 'declared_files_exact': True,
          'implementation_identical_to_tested_revision': True, 'checks_verified': checks,
          'indexed_authority_hashes_verified': True, 'manifest_hashes_and_sizes_verified': True,
          'tested_to_reviewed_suffix': 'linear governance/evidence only; evidence additions only',
          'task_packets_refined': [], 'scope': 'validator, provenance tests, two harness contracts, derived metadata, own HG043 evidence/governance'}
print(json.dumps(report, indent=2))
