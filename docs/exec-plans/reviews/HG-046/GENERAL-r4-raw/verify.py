from pathlib import Path
import gzip
import importlib.util
import json
import subprocess
import yaml
from jsonschema import Draft202012Validator
ROOT = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
BASE = '26906bd7f4444914c228e98377f2b164fee0dd5d'
HEAD = '02d95c1d86ade83128671190e1e1bf916cfe2b88'
TESTED = '9f2f38fe69f772d1564f0fa5eee2441da038aef1'
spec = importlib.util.spec_from_file_location('validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
ce = v.compact_evidence
assert v.resolve(ROOT, 'HEAD') == HEAD
record = yaml.safe_load(ce.blob(ROOT, 'docs/exec-plans/governance/HG-046.yaml', HEAD))
Draft202012Validator(json.loads(ce.blob(ROOT, 'HARNESS_CHANGE.schema.json', HEAD))).validate(record)
assert (record['base_commit'], record['tested_commit'], record['change_status'], record['frozen_impact']) == (BASE, TESTED, 'PASS', 'NONE')
changed = set(v.changed_paths(ROOT, BASE, HEAD))
assert changed == set(record['files_changed'])
assert len(record['files_changed']) == len(changed)
assert all(v.matches(p, v.governance_allowed_patterns('HG-046')) for p in changed)
assert not v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-046', 'tested')
for p in changed:
    if p != 'docs/exec-plans/governance/HG-046.yaml' and not p.startswith('docs/exec-plans/evidence/HG-046/'):
        assert ce.blob(ROOT, p, TESTED) == ce.blob(ROOT, p, HEAD), p
frozen = json.loads(ce.blob(ROOT, 'FROZEN_BASELINE.json', BASE))
unchanged = ['FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Harness_Backlog_v0.2.json', 'THREAD_REVIEW.schema.json', 'THREAD_RESULT.schema.json', 'HARNESS_CHANGE.schema.json', 'MILESTONE_CLOSURE.schema.json'] + [e['path'] for e in frozen['files']]
for p in unchanged:
    assert ce.blob(ROOT, p, BASE) == ce.blob(ROOT, p, HEAD), p
assert not any(p.startswith(('src/', 'migrations/', 'tests/db/', 'docs/exec-plans/active/', 'docs/exec-plans/completed/')) for p in changed)
expected_ids = {'focused', 'harness', 'unit', 'lint', 'typecheck', 'authority', 'source_diff'}
assert set(c['check_id'] for c in record['checks_run']) == expected_ids and len(record['checks_run']) == len(expected_ids)
prefix = 'PYTHONPATH=/Users/davetian/.codex/worktrees/ffff/KineticLoop/src /private/tmp/hg044-venv/bin/python -m '
for c in record['checks_run']:
    check_id = c['check_id']
    expected_command = (prefix + 'pytest -q tests/harness/test_compact_evidence.py' if check_id == 'focused' else 'git diff --check ' + BASE + ' HEAD' if check_id == 'source_diff' else prefix + 'kineticloop.db.cli ' + ('check-harness' if check_id == 'authority' else 'test-' + check_id if check_id in ('harness', 'unit') else check_id))
    assert c['command'] == expected_command and c['result'] == 'PASS'
    ref = c['evidence_ref']
    assert ref.startswith('docs/exec-plans/evidence/HG-046/selected-9f2f38f/')
    envelope = json.loads(ce.blob(ROOT, ref, HEAD))
    raw = ce.read(ROOT, ref, HEAD, tested=TESTED, command=expected_command, exit_code=0)
    stored = ce.blob(ROOT, envelope['payload'], HEAD)
    assert stored == gzip.compress(raw, compresslevel=9, mtime=0)
    assert gzip.decompress(stored) == raw and envelope['timestamp']
    text = raw.decode()
    if check_id in ('focused', 'harness', 'unit'):
        count = v.m3_pytest_count(text)
        assert count == {'focused': 194, 'harness': 1085, 'unit': 241}[check_id]
        assert envelope['test_counts'] == {'passed': count}
    elif check_id == 'authority':
        assert text.startswith('HARNESS_CHECK_PASS tasks=') and 'HARNESS_CHECK_FAIL' not in text
    elif check_id == 'source_diff':
        assert raw == b''
    elif check_id == 'lint':
        assert text == 'All checks passed!\n'
    elif check_id == 'typecheck':
        assert 'Success: no issues found' in text
    print(json.dumps({'check_id': check_id, 'command': expected_command, 'exit_code': envelope['exit_code'], 'tested_commit': envelope['tested_commit'], 'raw_sha256': ce.digest(raw), 'raw_bytes': len(raw), 'raw_test_counts': envelope['test_counts'], 'verification': 'PASS'}, sort_keys=True))
drift_command = 'git merge-base --is-ancestor fc8a044ffa4d15a74ce5dc59298ae411f1f4009b ' + TESTED
assert ce.read(ROOT, 'docs/exec-plans/evidence/HG-046/selected-9f2f38f/base-drift.json', HEAD, tested=TESTED, command=drift_command, exit_code=1) == b''
assert subprocess.run(drift_command.split(), cwd=ROOT, capture_output=True).returncode == 1
for round_id in ('r1', 'r2', 'r3'):
    child = f'docs/exec-plans/reviews/HG-046/GENERAL-{round_id}-raw/'
    prior = json.loads(ce.blob(ROOT, child + 'review.json', HEAD))
    assert prior['status'] == 'CHANGES_REQUIRED' and any(f['classification'] == 'BLOCKER' for f in prior['findings'])
    for ref in prior['evidence_refs']:
        ce.read(ROOT, ref, HEAD)
    print(json.dumps({'preserved_round': round_id, 'reviewed_head_sha': prior['reviewed_head_sha'], 'status': prior['status'], 'evidence_integrity': 'PASS'}, sort_keys=True))
audit = ce.audit(ROOT, BASE, HEAD, 'HG-046')
assert not audit['errors'], audit
print(json.dumps({'scope_paths': len(changed), 'exact_declaration': True, 'source_unchanged_after_tested': True, 'frozen_runtime_task_requirement_schema_changes': False, 'base_drift_actual_exit_code': 1, 'prospective_budget': audit}, sort_keys=True))
