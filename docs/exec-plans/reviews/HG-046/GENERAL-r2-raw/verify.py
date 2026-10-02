from pathlib import Path
import gzip
import importlib.util
import json
import re
import yaml
from jsonschema import Draft202012Validator

ROOT = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
BASE = '26906bd7f4444914c228e98377f2b164fee0dd5d'
HEAD = '5182feb0ad33319336efd913f63bf8c01c74b6a7'
TESTED = '58de0f7dfbf39947f2c2c1852cc927823e79b4c3'
spec = importlib.util.spec_from_file_location('validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
ce = v.compact_evidence
assert v.resolve(ROOT, 'HEAD') == HEAD
record = yaml.safe_load(ce.blob(ROOT, 'docs/exec-plans/governance/HG-046.yaml', HEAD))
Draft202012Validator(json.loads(ce.blob(ROOT, 'HARNESS_CHANGE.schema.json', HEAD))).validate(record)
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
assert record['change_status'] == 'PASS' and record['frozen_impact'] == 'NONE'
changed = set(v.changed_paths(ROOT, BASE, HEAD))
assert set(record['files_changed']) == changed
assert all(v.matches(p, v.governance_allowed_patterns('HG-046')) for p in changed)
assert not v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-046', 'tested')
for p in changed:
    if p != 'docs/exec-plans/governance/HG-046.yaml' and not p.startswith('docs/exec-plans/evidence/HG-046/'):
        assert ce.blob(ROOT, p, TESTED) == ce.blob(ROOT, p, HEAD), p
frozen = json.loads(ce.blob(ROOT, 'FROZEN_BASELINE.json', BASE))
for p in ['FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Harness_Backlog_v0.2.json', 'THREAD_REVIEW.schema.json', 'THREAD_RESULT.schema.json'] + [e['path'] for e in frozen['files']]:
    assert ce.blob(ROOT, p, BASE) == ce.blob(ROOT, p, HEAD), p
old_index = json.loads(ce.blob(ROOT, 'CURRENT_DOCUMENT_INDEX.json', BASE))
index = json.loads(ce.blob(ROOT, 'CURRENT_DOCUMENT_INDEX.json', HEAD))
assert [dict(e, sha256='') for k in ('documents', 'machine_readable') for e in old_index[k]] == [dict(e, sha256='') for k in ('documents', 'machine_readable') for e in index[k]]
for k in ('documents', 'machine_readable'):
    for e in index[k]:
        assert ce.digest(ce.blob(ROOT, e['path'], HEAD)) == e['sha256'], e['path']
manifest = json.loads(ce.blob(ROOT, 'HARNESS_DOCUMENT_MANIFEST.json', HEAD))
for e in manifest['files']:
    raw = ce.blob(ROOT, e['path'], HEAD)
    assert ce.digest(raw) == e['sha256'] and len(raw) == e['bytes'], e['path']
assert set(c['check_id'] for c in record['checks_run']) == {'focused', 'harness', 'unit', 'lint', 'typecheck', 'authority', 'source_diff'}
for c in record['checks_run']:
    ref = c['evidence_ref']
    envelope = json.loads(ce.blob(ROOT, ref, HEAD))
    raw = ce.read(ROOT, ref, HEAD, tested=TESTED, command=c['command'], exit_code=0)
    assert ce.blob(ROOT, envelope['payload'], HEAD) == gzip.compress(raw, compresslevel=9, mtime=0)
    text = raw.decode()
    if c['check_id'] in ('focused', 'harness', 'unit'):
        counts = {'focused': 59, 'harness': 950, 'unit': 241}
        count = v.m3_pytest_count(text)
        assert count == counts[c['check_id']] and envelope['test_counts'] == {'passed': count}
    elif c['check_id'] == 'authority':
        assert re.fullmatch(r'HARNESS_CHECK_PASS tasks=[0-9]+ active=[0-9]+\n', text)
    elif c['check_id'] == 'source_diff':
        assert raw == b''
    elif c['check_id'] == 'lint':
        assert text == 'All checks passed!\n'
    elif c['check_id'] == 'typecheck':
        assert 'Success: no issues found' in text
    print(json.dumps({'check_id': c['check_id'], 'revision': HEAD, 'tested_commit': TESTED, 'raw_sha256': ce.digest(raw), 'raw_bytes': len(raw), 'test_counts': envelope['test_counts'], 'verification': 'PASS'}, sort_keys=True))
audit = ce.audit(ROOT, BASE, HEAD, 'HG-046')
assert not audit['errors'], audit
print(json.dumps({'scope_paths': len(changed), 'source_equal_tested_to_reviewed': True, 'declared_files_exact': True, 'frozen_and_task_authority_unchanged': True, 'index_and_manifest_verified': True, 'prospective_budget': audit}, sort_keys=True))
