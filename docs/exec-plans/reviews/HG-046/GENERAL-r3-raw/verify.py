from pathlib import Path
import gzip
import importlib.util
import json
import re
import yaml
from jsonschema import Draft202012Validator
ROOT = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
BASE = '26906bd7f4444914c228e98377f2b164fee0dd5d'
HEAD = 'fb720bc37c8e9ec436b0673de71c282f9778e6a8'
TESTED = 'fb7d62b73d80a56b8bce1d0f7cbd29f14aff77ab'
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
assert set(c['check_id'] for c in record['checks_run']) == {'focused', 'harness', 'unit', 'lint', 'typecheck', 'authority', 'source_diff'}
for c in record['checks_run']:
    ref = c['evidence_ref']
    envelope = json.loads(ce.blob(ROOT, ref, HEAD))
    raw = ce.read(ROOT, ref, HEAD, tested=TESTED, command=c['command'], exit_code=0)
    assert ce.blob(ROOT, envelope['payload'], HEAD) == gzip.compress(raw, compresslevel=9, mtime=0)
    text = raw.decode()
    if c['check_id'] in ('focused', 'harness', 'unit'):
        count = v.m3_pytest_count(text)
        assert count == {'focused': 114, 'harness': 1005, 'unit': 241}[c['check_id']]
        assert envelope['test_counts'] == {'passed': count}
    elif c['check_id'] == 'authority':
        assert re.fullmatch(r'HARNESS_CHECK_PASS tasks=[0-9]+ active=[0-9]+\n', text)
    elif c['check_id'] == 'source_diff':
        assert raw == b''
    elif c['check_id'] == 'lint':
        assert text == 'All checks passed!\n'
    elif c['check_id'] == 'typecheck':
        assert 'Success: no issues found' in text
    print(json.dumps({'check_id': c['check_id'], 'tested_commit': TESTED, 'raw_sha256': ce.digest(raw), 'raw_bytes': len(raw), 'test_counts': envelope['test_counts'], 'verification': 'PASS'}, sort_keys=True))
ref = 'docs/exec-plans/evidence/HG-046/selected-fb7d62b/base-drift.json'
assert ce.read(ROOT, ref, HEAD, tested=TESTED, command='git merge-base --is-ancestor fc8a044ffa4d15a74ce5dc59298ae411f1f4009b ' + TESTED, exit_code=1) == b''
for revision in ('r1', 'r2'):
    prior = json.loads(ce.blob(ROOT, f'docs/exec-plans/reviews/HG-046/GENERAL-{revision}-raw/review.json', HEAD))
    assert prior['status'] == 'CHANGES_REQUIRED' and any(f['classification'] == 'BLOCKER' for f in prior['findings'])
audit = ce.audit(ROOT, BASE, HEAD, 'HG-046')
assert not audit['errors'], audit
print(json.dumps({'scope_paths': len(changed), 'declared_files_exact': True, 'tested_suffix_source_unchanged': True, 'frozen_and_status_files_unchanged': True, 'prior_failed_reviews_retained': True, 'base_drift_exit_one_preserved': True, 'prospective_budget_stored_bytes': audit['stored_bytes'], 'prospective_budget_files': audit['files'], 'prospective_budget_errors': audit['errors']}, sort_keys=True))
