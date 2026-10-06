"""Independent exact-revision GENERAL inspection; persist bounded metadata only."""
import ast
import collections
import hashlib
import importlib.util
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
B = '3ec7f7a38d974256a928c3687f63e4d90019e42b'
T = '61ab06ea8a8adfa6e1931db7e6ea80408dd58f49'
R = '0c3ad1ac6f0811f920002bfb8782e84cf0eb2460'
PREVIOUS = '3ec5fd2f'
D = 'docs/exec-plans/evidence/HG-056/checks-repair-' + T + '-cef31f82/'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path, revision=R):
    entry = git('ls-tree', '-z', revision, '--', path)
    assert entry.startswith((b'100644 blob ', b'100755 blob '))
    assert entry.split(b'\t')[1].rstrip(b'\0').decode() == path
    return git('show', revision + ':' + path)

def digest(data):
    return hashlib.sha256(data).hexdigest()

assert git('rev-parse', 'HEAD').decode().strip() == R
for a, b in ((B, T), (T, R)):
    git('merge-base', '--is-ancestor', a, b)
spec = importlib.util.spec_from_file_location('review_decoder', ROOT / 'tools/harness/compact_evidence.py')
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)
assert (ROOT / 'tools/harness/compact_evidence.py').read_bytes() == blob('tools/harness/compact_evidence.py')
run = json.loads(blob(D + 'RUN.json'))
assert run['tested_commit'] == T and run['base_commit'] == B and not run['capture_errors']
assert len(run['checks']) == 7
raw_checks = {}
check_records = []
for check in run['checks']:
    raw = ce.read(ROOT, check['evidence_ref'], R, tested=T, command=check['command'], exit_code=check['exit_code'])
    assert check['result'] == 'PASS' and check['exit_code'] == 0
    assert digest(raw) == check['raw_sha256'] and len(raw) == check['raw_bytes']
    raw_checks[check['check_id']] = raw
    check_records.append({'id': check['check_id'], 'command': check['command'], 'exit': check['exit_code'],
                          'result': check['result'], 'sha256': digest(raw), 'bytes': len(raw), 'bound_read': 'PASS'})

artifacts = {}
for group, command_id in ((run['harness_artifacts'], 'affected_harness'), (run['full_collection_artifacts'], 'full_collection')):
    command = next(c['command'] for c in run['checks'] if c['check_id'] == command_id)
    for item in group:
        artifacts[item['name']] = ce.read(ROOT, item['evidence_ref'], R, tested=T, command=command, exit_code=0)

phase_records = {}
identity_sets = {}
for prefix, count in (('harness', 830), ('full-collection', 2056)):
    manifest = json.loads(artifacts[prefix + '-manifest.json.json'])
    collection = json.loads(artifacts[prefix + '-collection.json.json'])
    execution = json.loads(artifacts[prefix + '-execution.json.json'])
    ids = collection['collections']['serial']
    assert len(ids) == len(set(ids)) == count
    identity_sets[prefix] = set(ids)
    assert not collection['started'] and not collection['reports'] and not collection['errors']
    assert manifest['tested_commit'] == T and not manifest['dirty_source']
    assert manifest['exit_code'] == manifest['pytest_exit_code'] == 0 and not manifest['errors']
    assert execution['exit_code'] == 0 and not execution['errors']
    for file in manifest['files']:
        raw = artifacts[prefix + '-' + file['path'] + '.json']
        assert len(raw) == file['bytes'] and digest(raw) == file['sha256']
    junit = ET.fromstring(artifacts[prefix + '-junit.xml.json'])
    cases = junit.findall('.//testcase')
    assert not junit.findall('.//failure') and not junit.findall('.//error') and not junit.findall('.//skipped')
    record = {'collected': count, 'identity_digest': digest(json.dumps(ids, separators=(',', ':')).encode()),
              'starts': len(execution['started']), 'reports': len(execution['reports']),
              'junit_cases': len(cases), 'workers': manifest['workers'], 'mode': manifest['mode'],
              'manifest_file_bindings': 'PASS'}
    if prefix == 'harness':
        assert len(execution['started']) == count and set(execution['started']) == set(ids)
        assert set(execution['collections']) == {'gw0', 'gw1'}
        assert all(worker_ids == ids for worker_ids in execution['collections'].values())
        phases = collections.defaultdict(list)
        for report in execution['reports']:
            phases[report['nodeid']].append(report)
        assert set(phases) == set(ids)
        for reports in phases.values():
            assert len(reports) == 3 and {p['phase'] for p in reports} == {'setup', 'call', 'teardown'}
            assert all(p['outcome'] == 'passed' and p['worker'] in execution['collections'] for p in reports)
            assert len({p['worker'] for p in reports}) == 1
        junit_ids = ['/'.join(c.attrib['classname'].split('.')[:3]) + '.py::' +
                     '::'.join(c.attrib['classname'].split('.')[3:] + [c.attrib['name']]) for c in cases]
        assert len(junit_ids) == len(set(junit_ids)) == count and set(junit_ids) == set(ids)
        compact = [i for i in ids if i.startswith('tests/harness/test_compact_evidence.py::')]
        assert len(compact) == 826
        assert manifest['mode'] == 'EXECUTION' and manifest['execution_complete']
        record.update(compact_cases=826, phase_counts=dict(collections.Counter(p['phase'] for p in execution['reports'])),
                      phase_worker_and_junit_identity_bindings='PASS')
    else:
        assert not execution['started'] and not execution['reports'] and not cases
        assert execution['collections']['serial'] == ids
        assert manifest['mode'] == 'COLLECTION_ONLY' and not manifest['execution_complete']
    phase_records[prefix] = record
assert identity_sets['harness'] <= identity_sets['full-collection']
assert {i for i in identity_sets['full-collection'] if i.startswith('tests/harness/test_compact_evidence.py::')} == {
    i for i in identity_sets['harness'] if i.startswith('tests/harness/test_compact_evidence.py::')}
assert re.search(rb'\b830 passed\b', raw_checks['affected_harness'])
assert re.search(rb'\b103 passed\b', raw_checks['installed_decoder_isolation'])

packet = blob('docs/exec-plans/evidence/HG-056/PACKET.md').decode()
section = packet.split('**Exact write_paths**', 1)[1].split('Only needed classifier', 1)[0]
allowlist = [line.split('`')[1] for line in section.splitlines() if line.startswith('- `')]
source = ast.parse(blob('tools/harness/validate_harness.py'))
scope_function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'governance_allowed_patterns')
literal_scope = [ast.literal_eval(v) if not isinstance(v, ast.Name) else {'INDEX': 'CURRENT_DOCUMENT_INDEX.json',
                 'MANIFEST': 'HARNESS_DOCUMENT_MANIFEST.json'}[v.id] for v in scope_function.body[0].body[0].value.elts]
assert literal_scope == allowlist
changed = git('diff', '--no-renames', '--name-only', '-z', B, R).decode().split('\0')[:-1]
assert all(any(p == a or (a.endswith('/**') and p.startswith(a[:-2])) for a in allowlist) for p in changed)
modes = collections.Counter()
for path in changed:
    blob(path)
    modes[git('ls-tree', R, '--', path).split()[0].decode()] += 1
frozen = json.loads(blob('FROZEN_BASELINE.json', B))
frozen_paths = ['FROZEN_BASELINE.json'] + [f['path'] for f in frozen['files']]
assert all(blob(p, B) == blob(p) for p in frozen_paths)
scope = json.loads(raw_checks['scope'])
assert scope['base'] == B and scope['head'] == T and scope['status'] == 'PASS'
assert scope['changed_paths'] == git('diff', '--no-renames', '--name-only', '-z', B, T).decode().split('\0')[:-1]

suffix = git('rev-list', '--reverse', T + '..' + R).decode().splitlines()
assert suffix == [R] and len(git('show', '-s', '--format=%P', R).split()) == 1
suffix_paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', R).decode().splitlines()
assert all(p.startswith(D) or p == 'docs/exec-plans/governance/HG-056.yaml' for p in suffix_paths)
assert all(blob(p, T) == blob(p) for p in changed if not p.startswith(('docs/exec-plans/evidence/', 'docs/exec-plans/reviews/', 'docs/exec-plans/governance/')))
prior_paths = git('ls-tree', '-r', '--name-only', PREVIOUS, '--', 'docs/exec-plans/evidence/HG-056').decode().splitlines()
preserved = [p for p in prior_paths if not p.endswith('/PREPARATION.json')]
prep_path = 'docs/exec-plans/evidence/HG-056/PREPARATION.json'
prep_old, prep_new = json.loads(blob(prep_path, PREVIOUS)), json.loads(blob(prep_path))
prep_key = next(k for k in prep_old if isinstance(prep_old[k], list) and prep_old[k] != prep_new[k])
assert prep_new[prep_key][:len(prep_old[prep_key])] == prep_old[prep_key]
assert {k:v for k,v in prep_old.items() if k != prep_key} == {k:v for k,v in prep_new.items() if k != prep_key}
assert all(blob(p, PREVIOUS) == blob(p) for p in preserved)
for round in ('round1', 'round2', 'round3', 'general', 'general_round2', 'general_round3', 'security', 'security_round2', 'security_round3', 'final-gates', 'final-round3'):
    paths = git('ls-tree', '-r', '--name-only', PREVIOUS, '--', 'docs/exec-plans/reviews/HG-056/' + round).decode().splitlines()
    assert paths and all(blob(p, PREVIOUS) == blob(p) for p in paths)

original_revision = 'f93364d90aaae9b0b62706fd4e4fe395a8cd8ec5'
original_path = 'docs/exec-plans/reviews/KL-036/SECURITY_DATA_BOUNDARY/audit.py'
original = blob(original_path, original_revision)
assert git('ls-tree', original_revision, '--', original_path).startswith(b'100644 blob cde206aee1eb240862863069104ad291ff98dedb\t')
assert len(original) == 8063 and digest(original) == 'a602ee684cdd7b4d8169388d2a2fe821fc6bc5beadf0d69a593c2ed260ffe382'
assert original == blob('docs/exec-plans/evidence/HG-056/original-reader.fixture')
assert ce.envelope(original) is None and ce.reencoding_record(original) is None
assert ce.read(ROOT, original_path, original_revision) == original
prior = json.loads(blob(D + 'PRIOR_REQUIRED_CHECKS.json'))
old_results = []
compatibility = None
for check in prior['checks_run']:
    raw = ce.read(ROOT, check['evidence_ref'], R, tested=prior['tested_commit'], command=check['command'],
                  exit_code=0 if check['result'] == 'PASS' else 1)
    old_results.append({'id': check['check_id'], 'result': check['result'], 'tested': prior['tested_commit'],
                        'sha256': digest(raw), 'bytes': len(raw)})
    if check['check_id'] == 'compatibility':
        objects = [json.loads(line) for line in raw.splitlines() if line.startswith(b'{')]
        compatibility = objects[-1]
        assert len(compatibility['expected_maps']) == 2 and len(compatibility['validated_maps']) == 1
        assert compatibility['history_errors'] and compatibility['storage_audit']['errors']
blocker = json.loads(blob('docs/exec-plans/evidence/HG-056/diagnostics/hg056-kl036-history-blocker.json'))
assert git('ls-tree', blocker['revision'], '--', blocker['path']) == b''
assert git('ls-tree', blocker['parent'], '--', blocker['path']).startswith(b'100644 blob ')

def functions(data):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(data).body if isinstance(n, ast.FunctionDef)}
base_decoder, current_decoder = functions(blob('tools/harness/compact_evidence.py', B)), functions(blob('tools/harness/compact_evidence.py'))
assert set(base_decoder) == set(current_decoder)
decoder_changes = sorted(n for n in base_decoder if base_decoder[n] != current_decoder[n])
assert decoder_changes == ['envelope', 'reserved_ascii']
base_validator, current_validator = functions(blob('tools/harness/validate_harness.py', B)), functions(blob('tools/harness/validate_harness.py'))
validator_changes = sorted(n for n in base_validator if base_validator[n] != current_validator[n])
assert validator_changes == ['governance_allowed_patterns', 'validate']
import jsonschema
import yaml
governance = yaml.safe_load(blob('docs/exec-plans/governance/HG-056.yaml'))
jsonschema.validate(governance, json.loads(blob('HARNESS_CHANGE.schema.json')))
assert governance['base_commit'] == B and governance['tested_commit'] == T and governance['change_status'] == 'BLOCKED'
assert governance['files_changed'] == changed
index_before, index_after = json.loads(blob('CURRENT_DOCUMENT_INDEX.json', B)), json.loads(blob('CURRENT_DOCUMENT_INDEX.json'))
for section in ('documents', 'machine_readable'):
    assert len(index_before[section]) == len(index_after[section])
    for old, new in zip(index_before[section], index_after[section]):
        assert {k: v for k, v in old.items() if k != 'sha256'} == {k: v for k, v in new.items() if k != 'sha256'}
        assert digest(blob(new['path'])) == new['sha256']
manifest_before, manifest_after = json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json', B)), json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json'))
assert {k: v for k, v in manifest_before.items() if k != 'files'} == {k: v for k, v in manifest_after.items() if k != 'files'}
old_rows = {row['path']: row for row in manifest_before['files']}
new_rows = {row['path']: row for row in manifest_after['files']}
assert old_rows.keys() <= new_rows.keys()
for path, row in new_rows.items():
    assert path in old_rows or path.startswith('docs/exec-plans/evidence/HG-056/')
    data = blob(path)
    assert len(data) == row['bytes'] and digest(data) == row['sha256']
report = {'purpose': 'INDEPENDENT_GENERAL_REVIEW_METADATA_ONLY', 'B': B, 'T': T, 'R': R,
          'checks': check_records, 'phases': phase_records, 'isolated_stdout_count': 103,
          'isolated_identity_artifact_claimed': False, 'scope': {'paths': len(changed), 'modes': dict(modes),
          'literal_scope_matches_packet': True, 'frozen_files_unchanged': len(frozen_paths)},
          'tested_to_result_suffix': suffix, 'suffix_only_result_and_new_capture': True,
          'preserved_prior_artifacts': len(preserved), 'prior_review_rounds_preserved': ['round1', 'round2', 'round3'],
          'original_helper': {'pins': 'PASS', 'classification_plain': True, 'bound_read_identical': True, 'executed': False},
          'decoder_functions_changed': decoder_changes, 'validator_functions_changed': validator_changes,
          'prior_actual_outcomes': old_results, 'compatibility': {'expected_maps': compatibility['expected_maps'],
          'validated_maps': compatibility['validated_maps'], 'history_errors': compatibility['history_errors'],
          'storage_errors': compatibility['storage_audit']['errors'], 'rerun': False},
          'external_deletion_tree_confirmed': True, 'source_inspection_authority': 'NOT_IMPLEMENTED/BLOCKED',
          'whole_cycles_rerun': False, 'new_source_defects_reproduced_by_general': 0,
          'previous_specialist_source_blocker': 'HG056-S9; new commented-write cases verified at T',
          'derived_authority_hashes_and_manifest_rows': 'PASS', 'governance_schema': 'PASS'}

# New source delta is one supplementary lexical view, not a storage/authority bypass.
prior_decoder = functions(blob('tools/harness/compact_evidence.py', PREVIOUS))
assert set(prior_decoder) == set(current_decoder)
assert [n for n in prior_decoder if prior_decoder[n] != current_decoder[n]] == ['reserved_ascii']
assert blob('tools/harness/validate_harness.py', PREVIOUS) == blob('tools/harness/validate_harness.py')
parsed_old = ast.parse(blob('tools/harness/compact_evidence.py', B))
parsed_new = ast.parse(blob('tools/harness/compact_evidence.py'))
non_functions = lambda tree: [ast.dump(n, include_attributes=False) for n in tree.body if not isinstance(n, ast.FunctionDef)]
assert non_functions(parsed_old) == non_functions(ast.Module(body=[n for n in parsed_new.body if not (isinstance(n, ast.Import) and [a.name for a in n.names] == ['unicodedata'])], type_ignores=[]))
assert blob(D + 'ROUND3_RESULT.yaml') == blob('docs/exec-plans/governance/HG-056.yaml', PREVIOUS)
assert blob('docs/exec-plans/reviews/HG-056/round3/GENERAL.json') == blob('docs/exec-plans/reviews/HG-056/GENERAL.json', PREVIOUS)
assert blob('docs/exec-plans/reviews/HG-056/round3/SECURITY_DATA_BOUNDARY.json') == blob('docs/exec-plans/reviews/HG-056/SECURITY_DATA_BOUNDARY.json', PREVIOUS)
prior_review_paths = git('ls-tree', '-r', '--name-only', PREVIOUS, '--', 'docs/exec-plans/reviews/HG-056').decode().splitlines()
assert all(blob(p, PREVIOUS) == blob(p) for p in prior_review_paths)
new_case_fragments = ['comment-subscript-write','comment-map-write','comment-augmented-write','comment-typed-write','comment-parenthesized-write','comment-subscript-read','comment-parenthesized-read','comment-reader-default','comment-adjacent-object']
new_case_counts = {fragment: sum(fragment in node for node in identity_sets['harness']) for fragment in new_case_fragments}
assert all(new_case_counts.values())
old_guard = json.loads(blob('docs/exec-plans/reviews/HG-056/final-round3/RUN.json'))
old_raw = ce.read(ROOT, old_guard['evidence_ref'], R, tested=old_guard['audited_head'], command=old_guard['command'], exit_code=0)
assert digest(old_raw) == old_guard['raw_sha256'] and len(old_raw) == old_guard['raw_bytes']
old_storage = json.loads(old_raw)
assert not old_storage['errors']
assembly = json.loads(blob(D + 'RESULT_ASSEMBLY.json'))
assert assembly['initial_result'] == 'FileNotFoundError'
assert not run['capture_errors']
report.update(prior_review_artifacts_preserved=len(prior_review_paths), round3_result_snapshot_exact=True,
              source_change_since_round3=['reserved_ascii'], decoder_constants_identical=True, added_import_since_base='unicodedata only',
              new_case_counts=new_case_counts, old_storage_guard={'R': old_guard['audited_head'], 'result': 'PASS', 'metadata': old_storage},
              ancillary_result_assembly_error_preserved=assembly, preparation_prior_entries_preserved=True,
              reviewer_preparation_error='Initial verifier included append-only PREPARATION.json in byte-equality check; assertion failed. Inspection confirmed exactly two appended preparation entries and preserved all earlier fields. Corrected check verifies append preservation; actual task artifacts unchanged. A second assertion over all non-function AST nodes failed because the prior repair adds unicodedata; corrected comparison permits that single inspected import and requires all other non-function nodes and constants identical.', independent_execution='This reviewer authored and executed this metadata verifier only; historical helper and captured inputs were not executed.')

(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
assert ce.envelope((OUT / 'report.json').read_bytes()) is None and ce.reencoding_record((OUT / 'report.json').read_bytes()) is None
assert ce.envelope(Path(__file__).read_bytes()) is None and ce.reencoding_record(Path(__file__).read_bytes()) is None
print(json.dumps({'checks_verified': len(check_records), 'phases': phase_records, 'scope': report['scope'],
                  'preserved_prior_artifacts': len(preserved), 'schema': 'PASS'}, indent=2))
