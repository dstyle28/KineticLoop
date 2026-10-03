"""Independent read-only GENERAL R2 review proof for immutable HG047 objects."""
import gzip
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import zlib
from pathlib import Path
from jsonschema import Draft202012Validator

root = Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
base = '391c9198fa8ec647e377a0572700bc7568468c85'
tested = '536c9b7b7c5bfa9b36a0b38e513bce34ed6eb31d'
head = 'b7370940c8b9165f471322baaeef7d9e250dfac6'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=root)

def at(path, revision=head):
    return git('show', revision + ':' + path)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def module(name, path):
    assert (root / path).read_bytes() == at(path)
    spec = importlib.util.spec_from_file_location(name, root / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

assert git('rev-parse', 'HEAD').decode().strip() == head
v = module('v', 'tools/harness/validate_harness.py')
ce = v.compact_evidence
assert (root / 'tools/harness/compact_evidence.py').read_bytes() == at('tools/harness/compact_evidence.py')
policy = module('policy', 'tools/harness/db_policy.py')
record = v.load_artifact_text(at('docs/exec-plans/governance/HG-047.yaml').decode(), '.yaml')
Draft202012Validator(json.loads(at('HARNESS_CHANGE.schema.json'))).validate(record)
assert record['base_commit'] == base and record['tested_commit'] == tested
assert record['change_status'] == 'PASS' and record['frozen_impact'] == 'NONE'
changed = set(git('diff', '--name-only', '--no-renames', base, head).decode().splitlines())
assert changed == set(record['files_changed'])
assert all(v.matches(path, v.governance_allowed_patterns('HG-047')) for path in changed)
for a, b in [(base, tested), (tested, head)]:
    git('merge-base', '--is-ancestor', a, b)
suffix_errors = v.governance_suffix_errors(root, tested, head, 'HG-047', 'tested')
assert not suffix_errors, suffix_errors
suffix = git('diff', '--name-status', '--no-renames', tested, head).decode().splitlines()
assert all(line.startswith('A\tdocs/exec-plans/evidence/HG-047/') or
           line == 'M\tdocs/exec-plans/governance/HG-047.yaml' for line in suffix)
assert len(git('rev-list', tested + '..' + head).splitlines()) == 1
assert not git('rev-list', '--merges', tested + '..' + head)
frozen = json.loads(at('FROZEN_BASELINE.json', base))
protected = {entry['path'] for entry in frozen['files']} | {
    'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'src', 'migrations',
    'tests/db', '.github/workflows', 'KineticLoop_Harness_Backlog_v0.2.json',
    'KineticLoop_Harness_Traceability_v0.3.json', 'MILESTONE_CLOSURE.schema.json',
    'docs/exec-plans/active/KL-080.md', 'tools/harness/db_policy.py',
    'tools/harness/db_ci.py', 'tools/harness/github_app.py', 'tools/harness/gate_validate.py',
    'tools/harness/gate_pytest.py', 'tools/harness/db_ci_pytest.py', 'tools/harness/local_db',
}
for identity in ['HG-045', 'HG-046']:
    protected |= {f'docs/exec-plans/{kind}/{identity}' for kind in ['evidence', 'reviews']}
    protected.add(f'docs/exec-plans/governance/{identity}.yaml')
assert not git('diff', '--name-only', base, head, '--', *sorted(protected))
assert not v.governance_index_errors(root, base, record, changed, protected, head)
assert not v.governance_manifest_errors(root, base, changed, head)
git('diff', '--check', base, head)
budget = ce.audit(root, base, head, 'HG-047')
assert not budget['errors'], budget
classification = policy.classify(root, base, head)
assert classification['full_database_required']

# Verify raw bytes independently, before comparing the production reader result.
envelopes = {}
for path in sorted(changed):
    if not path.startswith('docs/exec-plans/evidence/HG-047/') or not path.endswith('.json'):
        continue
    item = json.loads(at(path))
    if 'kineticloop_evidence' not in item:
        continue
    stored = at(item['payload'])
    assert len(stored) == item['stored_bytes'] and sha(stored) == item['stored_sha256']
    dec = zlib.decompressobj(31)
    raw = dec.decompress(stored, item['raw_bytes'] + 1)
    assert dec.eof and not dec.unused_data and not dec.unconsumed_tail
    assert len(raw) == item['raw_bytes'] and sha(raw) == item['raw_sha256']
    assert stored == gzip.compress(raw, compresslevel=9, mtime=0)
    assert ce.read(root, path, head, tested=item['tested_commit'],
                   command=item['command'], exit_code=item['exit_code']) == raw
    envelopes[path] = (item, raw)
execution = json.loads(at('docs/exec-plans/evidence/HG-047/round2-536c9b7/execution.json'))
assert execution['base_commit'] == base and execution['tested_commit'] == tested
assert len(record['checks_run']) == len(execution['checks']) == 8
checks = {}
for check in record['checks_run']:
    name, ref = check['check_id'], check['evidence_ref']
    meta, raw = envelopes[ref]
    run = execution['checks'][name]
    assert check['result'] == 'PASS'
    assert meta['tested_commit'] == run['tested'] == tested
    assert meta['command'] == run['command'] == check['command']
    assert meta['exit_code'] == run['exit_code'] == 0
    assert meta['test_counts'] == run['test_counts']
    assert run['envelope'] == ref and run['seconds'] > 0
    assert meta['timestamp'] == run['timestamp']
    tail = raw.decode().splitlines()[-3:]
    if name in ['harness', 'unit']:
        expected = 1306 if name == 'harness' else 241
        assert re.search(r'\b' + str(expected) + r' passed in ', raw.decode())
        assert meta['test_counts'] == {'passed': expected}
    elif name == 'authority':
        assert b'HARNESS_CHECK_PASS' in raw and b'HARNESS_CHECK_FAIL' not in raw
    elif name == 'source_diff':
        assert not raw
    elif name in ['scope', 'performance']:
        data = json.loads(raw)
        assert data['status'] == 'PASS'
        assert data['tested'] == tested if name == 'scope' else data['current_source'] == tested
        if name == 'performance':
            for row in data['measurements']:
                assert row['repeats'] == 5 and row['after']['git_calls'] < row['before']['git_calls']
    checks[name] = {'command': meta['command'], 'exit_code': 0, 'ref': ref,
                    'envelope_digest': sha(at(ref)), 'raw_digest': sha(raw),
                    'raw_bytes': len(raw), 'stored_digest': sha(at(meta['payload'])),
                    'stored_bytes': meta['stored_bytes'], 'test_counts': meta['test_counts'],
                    'raw_tail': tail}
failed = {}
for folder, name, diagnostic in [
    ('development-166bf3e', 'unit', 'failed'),
    ('development-b30a9c6', 'authority', 'HARNESS_CHECK_FAIL')]:
    ref = f'docs/exec-plans/evidence/HG-047/{folder}/{name}.json'
    item, raw = envelopes[ref]
    assert item['exit_code'] != 0 and diagnostic in raw.decode()
    failed[ref] = {'exit_code': item['exit_code'], 'test_counts': item['test_counts'],
                   'raw_digest': sha(raw), 'raw_tail': raw.decode().splitlines()[-4:]}
report = {'reviewed_head': head, 'tested_commit': tested, 'base_commit': base,
          'status': 'PASS', 'changed_paths': sorted(changed), 'changed_file_count': len(changed),
          'record_digest': sha(at('docs/exec-plans/governance/HG-047.yaml')),
          'tested_to_result_changes': suffix, 'tested_suffix_errors': suffix_errors,
          'protected_paths_unchanged': sorted(protected), 'metadata_checks': 'PASS',
          'independently_verified_envelopes': len(envelopes), 'selected_checks': checks,
          'preserved_failed_evidence': failed, 'prospective_budget': budget,
          'full_database_required': classification['full_database_required'],
          'full_database_performed_by_this_review': False,
          'focused_tests_separate_review_evidence': True}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': report['status'], 'changed_files': len(changed),
                  'envelopes': len(envelopes), 'selected_checks': len(checks),
                  'budget': budget, 'raw_tails': {name: row['raw_tail'] for name, row in checks.items()}}, indent=2))
