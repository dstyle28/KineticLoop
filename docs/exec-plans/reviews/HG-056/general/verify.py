"""Bounded GENERAL review diagnostics; never execute inspected source or emit fixtures."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
BASE = '3ec7f7a38d974256a928c3687f63e4d90019e42b'
TESTED = 'a8ed5ba4985f982a1e050eebd10b9a8e2ed9df86'
REVIEWED = '76484185581647d1a5d038eaa2eaa2c26291b8c1'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ce = load_module('hg056_general_compact', 'tools/harness/compact_evidence.py')
validator = load_module('hg056_general_validator', 'tools/harness/validate_harness.py')
report = {'purpose': 'BOUNDED_INDEPENDENT_GENERAL_REVIEW_NOT_ACCEPTANCE_EXECUTION',
          'reviewed': REVIEWED, 'tested': TESTED, 'base': BASE}
assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
for revision in (TESTED, REVIEWED):
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, revision], cwd=ROOT, check=True)
core = ['tools/harness/compact_evidence.py', 'tools/harness/validate_harness.py',
        'tests/harness/test_compact_evidence.py', 'tests/harness/test_validator.py',
        'docs/harness/EVIDENCE_STORAGE_POLICY.md', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md']
assert all(git('show', TESTED + ':' + p) == git('show', REVIEWED + ':' + p) for p in core)
report['implementation_unchanged_since_tested'] = core
packet = git('show', REVIEWED + ':docs/exec-plans/evidence/HG-056/PACKET.md').decode()
scope_section = packet.split('**Exact write_paths**', 1)[1].split('Only needed classifier', 1)[0]
allowed = [line.split('`')[1] for line in scope_section.splitlines() if line.startswith('- `')]
changed = git('diff', '--no-renames', '--name-only', '-z', BASE, REVIEWED).decode().split('\0')[:-1]
assert all(any(p == a or (a.endswith('/**') and p.startswith(a[:-2])) for a in allowed) for p in changed)
assert all(git('ls-tree', REVIEWED, '--', p).startswith((b'100644 blob ', b'100755 blob ')) for p in changed)
frozen = json.loads(git('show', BASE + ':FROZEN_BASELINE.json'))
frozen_paths = ['FROZEN_BASELINE.json'] + [item['path'] for item in frozen['files']]
assert all(git('show', BASE + ':' + p) == git('show', REVIEWED + ':' + p) for p in frozen_paths)
report['scope'] = {'changed_paths': changed, 'within_packet': True,
                   'frozen_files_unchanged': len(frozen_paths),
                   'validator_mode': git('ls-tree', REVIEWED, '--', core[1]).decode().split()[0]}
run_path = 'docs/exec-plans/evidence/HG-056/checks-' + TESTED + '-beec415d/RUN.json'
run = json.loads(git('show', REVIEWED + ':' + run_path))
outputs = {}
records = []
for check in run['checks']:
    raw = ce.read(ROOT, check['evidence_ref'], REVIEWED, tested=TESTED,
                  command=check['command'], exit_code=check['exit_code'])
    outputs[check['check_id']] = raw
    manifest = json.loads(git('show', REVIEWED + ':' + check['evidence_ref']))
    observed = {kind: int(count) for count, kind in re.findall(
        r'\b([0-9]+) (passed|failed|skipped|errors?|deselected|xfailed|xpassed)\b', raw.decode(errors='replace'))}
    assert observed == manifest['test_counts']
    records.append({'check': check['check_id'], 'recorded_result': check['result'],
                    'recorded_exit': check['exit_code'], 'raw_length': len(raw),
                    'raw_digest': hashlib.sha256(raw).hexdigest(),
                    'counts': manifest['test_counts'], 'bound_read': 'PASS'})
assert len(records) == 11
report['actual_captured_checks'] = records
report['captured_failure_diagnostics'] = {
    'harness_missing_loose_object_unlink': b'FileNotFoundError' in outputs['harness'] and b'.unlink()' in outputs['harness'],
    'scope_regular_mode_assertion': b'missing/nonregular:tools/harness/validate_harness.py' in outputs['scope'],
    'authority_review_reference_failure': b'governance-review-evidence:' in outputs['authority'],
    'runner_capture_failure_recorded': run['runner_exit'] == 1,
    'machine_identity_capture': run['identity_capture_status']}
original_revision = 'f93364d90aaae9b0b62706fd4e4fe395a8cd8ec5'
original_path = 'docs/exec-plans/reviews/KL-036/SECURITY_DATA_BOUNDARY/audit.py'
original = ce.blob(ROOT, original_path, original_revision)
assert len(original) == 8063
assert hashlib.sha256(original).hexdigest() == 'a602ee684cdd7b4d8169388d2a2fe821fc6bc5beadf0d69a593c2ed260ffe382'
assert original == ce.blob(ROOT, 'docs/exec-plans/evidence/HG-056/original-reader.fixture', REVIEWED)
assert ce.envelope(original) is None and ce.reencoding_record(original) is None
assert ce.read(ROOT, original_path, original_revision) == original
report['original_helper'] = {'pins_match': True, 'classifier_plain': True,
                             'bound_read_identical': True, 'executed': False}
# Observe only metadata from already captured compatibility output.
compatibility_lines = [json.loads(line) for line in outputs['compatibility'].splitlines()
                       if line.startswith(b'{')]
compatibility = compatibility_lines[-1]
report['recorded_complete_compatibility'] = {
    'base': compatibility['base'], 'head': compatibility['head'],
    'candidate': compatibility['candidate'], 'expected_maps': compatibility['expected_maps'],
    'validated_maps': compatibility['validated_maps'],
    'history_errors': compatibility['history_errors'],
    'storage_errors': compatibility['storage_audit']['errors'],
    'rerun': False}
edge = 'e81cc2ccff69bf32a42f7c81b4671c99879b544b'
blocker = json.loads(git('show', REVIEWED + ':docs/exec-plans/evidence/HG-056/diagnostics/hg056-kl036-history-blocker.json'))
assert git('ls-tree', edge, '--', blocker['path']) == b''
assert git('ls-tree', edge + '^', '--', blocker['path']).startswith(b'100644 blob ')
report['external_history_deletion_confirmed'] = {'edge': edge, 'path': blocker['path']}
# Parse source for inspection only. Emit names/counts; never emit raw cases or IDs.
test_tree = ast.parse(git('show', REVIEWED + ':tests/harness/test_compact_evidence.py'))
new_tests = [node for node in test_tree.body if isinstance(node, ast.FunctionDef)
             and node.lineno >= 1998]
report['new_test_inspection'] = [{'name': node.name,
    'parameterizations': sum(isinstance(d, ast.Call) for d in node.decorator_list),
    'parameterizations_with_explicit_ids': sum(isinstance(d, ast.Call) and any(k.arg == 'ids' for k in d.keywords)
                                              for d in node.decorator_list)} for node in new_tests]
source_cases = []
for item in json.loads(git('show', REVIEWED + ':docs/exec-plans/evidence/HG-056/diagnostics/hg056-review-source-static-diagnostic.json'))['cases']:
    reference = item['reference']
    bound = item['reviewed_sha']
    entry = git('ls-tree', bound, '--', reference)
    if not entry:
        bound = '89b3d3f55de1c8e9882bfb7f5b109eb4c15da3c2'
        entry = git('ls-tree', bound, '--', reference)
    assert entry.startswith((b'100644 blob ', b'100755 blob '))
    source = git('show', bound + ':' + reference)
    ast.parse(source)
    try:
        ce.envelope(source)
        classification = 'PLAIN'
    except ValueError as error:
        classification = str(error)
    source_cases.append({'reference': reference, 'inspection_revision': bound,
                         'regular_blob': True, 'static_parse': 'VALID',
                         'strict_classification': classification,
                         'generic_availability': validator.review_reference_available(ROOT, reference, item['reviewed_sha']),
                         'executed': False})
report['source_reference_inspection'] = source_cases
suffix_start = 'b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91'
suffix_end = '89b3d3f55de1c8e9882bfb7f5b109eb4c15da3c2'
suffix = git('rev-list', '--reverse', suffix_start + '..' + suffix_end).decode().splitlines()
for commit in suffix:
    assert len(git('show', '-s', '--format=%P', commit).decode().split()) == 1
    paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', commit).decode().splitlines()
    assert all(path.startswith('docs/exec-plans/reviews/HG-047/') for path in paths)
report['hg047_historical_suffix'] = {'record': suffix_end, 'reviewed': suffix_start,
    'linear_own_paths_only': True, 'commits': len(suffix),
    'actual_guard_errors': validator.governance_suffix_errors(ROOT, suffix_start, suffix_end, 'HG-047', 'review'),
    'limitation': 'Path/linearity proof alone does not replace strict representation guards.'}
destination = Path(__file__).with_name('report.json')
destination.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'report': str(destination.relative_to(ROOT)), 'checks_decoded': len(records),
                  'scope': 'PASS', 'original_helper': 'PASS',
                  'acceptance': 'BLOCKED', 'source_programs_executed': False}))
