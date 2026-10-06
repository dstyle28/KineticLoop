"""Independent exact-Git GENERAL review; no input/helper execution or root audit."""
import ast
import collections
import hashlib
import importlib.util
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
B = '3ec7f7a38d974256a928c3687f63e4d90019e42b'
T = '1cb64a1baef54fc7801e4084a18db962c3528a70'
R = '0b089d7d3b0212a4e5458dc7891cbb4e831cd6f6'
OLD = 'd8aaf7c897e5a7653daa30b8d3bd906ba859652d'
D = 'docs/exec-plans/evidence/HG-056/checks-repair-' + T + '-9bc7f4cc/'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def blob(path, revision=R):
    entries = [x for x in git('ls-tree', '-z', revision, '--', path).split(b'\0')
               if x and x.split(b'\t')[1].decode() == path]
    assert len(entries) == 1 and entries[0].startswith((b'100644 blob ', b'100755 blob ')), path
    return git('show', revision + ':' + path)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def functions(raw):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(raw).body
            if isinstance(n, ast.FunctionDef)}


assert git('rev-parse', 'HEAD').decode().strip() == R
for parent, child in ((B, T), (T, R), (OLD, T)):
    git('merge-base', '--is-ancestor', parent, child)
spec = importlib.util.spec_from_file_location('general_review_decoder', ROOT / 'tools/harness/compact_evidence.py')
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)
assert (ROOT / 'tools/harness/compact_evidence.py').read_bytes() == blob('tools/harness/compact_evidence.py')
run = json.loads(blob(D + 'RUN.json'))
assert run['tested_commit'] == T and run['base_commit'] == B and not run['capture_errors']
assert len(run['checks']) == 7
checks, outputs, artifacts = [], {}, {}
for row in run['checks']:
    assert row['exit_code'] == 0 and row['result'] == 'PASS'
    raw = ce.read(ROOT, row['evidence_ref'], R, tested=T, command=row['command'], exit_code=0)
    assert sha(raw) == row['raw_sha256'] and len(raw) == row['raw_bytes']
    outputs[row['check_id']] = raw
    checks.append({'id': row['check_id'], 'command': row['command'], 'sha256': sha(raw),
                   'bytes': len(raw), 'exit_code': 0, 'bound_read': 'PASS'})
for key, check in (('harness_artifacts', 'affected_harness'), ('full_collection_artifacts', 'full_collection')):
    command = next(x['command'] for x in run['checks'] if x['check_id'] == check)
    for row in run[key]:
        artifacts[row['name']] = ce.read(ROOT, row['evidence_ref'], R, tested=T, command=command, exit_code=0)

identities, execution_details = {}, {}
for prefix, count in (('harness', 951), ('full-collection', 2177)):
    collection = json.loads(artifacts[prefix + '-collection.json.json'])
    execution = json.loads(artifacts[prefix + '-execution.json.json'])
    manifest = json.loads(artifacts[prefix + '-manifest.json.json'])
    ids = collection['collections']['serial']
    assert len(ids) == len(set(ids)) == count
    identities[prefix] = set(ids)
    assert not collection['started'] and not collection['reports'] and not collection['errors']
    assert manifest['tested_commit'] == T and not manifest['dirty_source']
    assert manifest['exit_code'] == manifest['pytest_exit_code'] == execution['exit_code'] == 0
    assert not manifest['errors'] and not execution['errors']
    for row in manifest['files']:
        raw = artifacts[prefix + '-' + row['path'] + '.json']
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    junit = ET.fromstring(artifacts[prefix + '-junit.xml.json'])
    cases = junit.findall('.//testcase')
    assert not any(junit.findall('.//' + tag) for tag in ('failure', 'error', 'skipped'))
    details = {'collected': count, 'identity_sha256': sha(json.dumps(ids, separators=(',', ':')).encode()),
               'starts': len(execution['started']), 'reports': len(execution['reports']), 'junit_cases': len(cases),
               'mode': manifest['mode'], 'artifact_hashes': 'PASS'}
    if prefix == 'harness':
        assert len(execution['started']) == count and set(execution['started']) == set(ids)
        assert set(execution['collections']) == {'gw0', 'gw1'}
        assert all(values == ids for values in execution['collections'].values())
        reports = collections.defaultdict(list)
        for report in execution['reports']:
            reports[report['nodeid']].append(report)
        assert set(reports) == set(ids)
        for rows in reports.values():
            assert len(rows) == 3 and {x['phase'] for x in rows} == {'setup', 'call', 'teardown'}
            assert all(x['outcome'] == 'passed' and x['worker'] in execution['collections'] for x in rows)
            assert len({x['worker'] for x in rows}) == 1
        expected_pairs = [('.'.join(node.split('::')[0][:-3].split('/') + node.split('::')[1:-1]),
                           node.split('::')[-1]) for node in ids]
        actual_pairs = [(case.attrib['classname'], case.attrib['name']) for case in cases]
        assert len(actual_pairs) == len(set(actual_pairs)) == count
        assert set(actual_pairs) == set(expected_pairs)
        compact_ids = {node for node in ids if node.startswith('tests/harness/test_compact_evidence.py::')}
        assert len(compact_ids) == 947 and manifest['mode'] == 'EXECUTION' and manifest['execution_complete']
        details.update(compact_cases=947, worker_phase_junit_binding='PASS',
                       phase_counts=dict(collections.Counter(row['phase'] for row in execution['reports'])))
    else:
        assert not execution['started'] and not execution['reports'] and not cases
        assert execution['collections']['serial'] == ids
        assert manifest['mode'] == 'COLLECTION_ONLY' and not manifest['execution_complete']
        assert {node for node in ids if node.startswith('tests/harness/test_compact_evidence.py::')} == compact_ids
    execution_details[prefix] = details
assert identities['harness'] <= identities['full-collection']
assert re.search(rb'\b951 passed\b', outputs['affected_harness'])
assert re.search(rb'\b103 passed\b', outputs['installed_decoder_isolation'])

packet = blob('docs/exec-plans/evidence/HG-056/PACKET.md').decode()
scope_section = packet.split('**Exact write_paths**')[1].split('Only needed classifier')[0]
allowed = [line.split('`')[1] for line in scope_section.splitlines() if line.startswith('- `')]
validator = ast.parse(blob('tools/harness/validate_harness.py'))
scope_function = next(n for n in validator.body if isinstance(n, ast.FunctionDef) and n.name == 'governance_allowed_patterns')
literal = [ast.literal_eval(n) if not isinstance(n, ast.Name) else {'INDEX': 'CURRENT_DOCUMENT_INDEX.json',
           'MANIFEST': 'HARNESS_DOCUMENT_MANIFEST.json'}[n.id] for n in scope_function.body[0].body[0].value.elts]
assert literal == allowed
changed = git('diff', '--no-renames', '--name-only', '-z', B, R).decode().split('\0')[:-1]
assert all(any(path == item or (item.endswith('/**') and path.startswith(item[:-2])) for item in allowed) for path in changed)
for path in changed:
    blob(path)
frozen = json.loads(blob('FROZEN_BASELINE.json', B))
frozen_paths = ['FROZEN_BASELINE.json'] + [row['path'] for row in frozen['files']]
assert all(blob(path, B) == blob(path) for path in frozen_paths)
for path in ('CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Harness_Backlog_v0.2.json', 'HISTORICAL_TASK_ID_MAP.json'):
    assert blob(path, B) == blob(path)
assert git('rev-list', '--reverse', T + '..' + R).decode().splitlines() == [R]
assert git('show', '-s', '--format=%P', R).decode().strip() == T
suffix_paths = git('diff-tree', '--no-commit-id', '--name-only', '-r', R).decode().splitlines()
assert all(path.startswith(D) or path == 'docs/exec-plans/governance/HG-056.yaml' for path in suffix_paths)
for path in changed:
    if not path.startswith(('docs/exec-plans/evidence/', 'docs/exec-plans/reviews/', 'docs/exec-plans/governance/')):
        assert blob(path, T) == blob(path)
scope = json.loads(outputs['scope'])
assert scope['base'] == B and scope['head'] == T and scope['status'] == 'PASS'
assert scope['changed_paths'] == git('diff', '--no-renames', '--name-only', '-z', B, T).decode().split('\0')[:-1]
result = yaml.safe_load(blob('docs/exec-plans/governance/HG-056.yaml'))
jsonschema.validate(result, json.loads(blob('HARNESS_CHANGE.schema.json')))
assert result['base_commit'] == B and result['tested_commit'] == T and result['change_status'] == 'BLOCKED'
assert result['files_changed'] == changed
assert [(x['check_id'], x['command'], x['evidence_ref'], x['result']) for x in result['checks_run']] == [
    (x['check_id'], x['command'], x['evidence_ref'], x['result']) for x in run['checks']]
try:
    yaml.safe_load(blob('docs/exec-plans/governance/HG-056.yaml', OLD))
except yaml.scanner.ScannerError:
    old_result_invalid = True
else:
    old_result_invalid = False
assert old_result_invalid
assert blob(D + 'ROUND5_RESULT.yaml') == blob('docs/exec-plans/governance/HG-056.yaml', OLD)

old_paths = git('ls-tree', '-r', '--name-only', OLD, '--', 'docs/exec-plans/evidence/HG-056', 'docs/exec-plans/reviews/HG-056').decode().splitlines()
preserved = [path for path in old_paths if path not in ('docs/exec-plans/evidence/HG-056/PREPARATION.json',
             'docs/exec-plans/reviews/HG-056/GENERAL.json', 'docs/exec-plans/reviews/HG-056/SECURITY_DATA_BOUNDARY.json')]
assert all(blob(path, OLD) == blob(path) for path in preserved)
for kind in ('GENERAL', 'SECURITY_DATA_BOUNDARY'):
    assert blob('docs/exec-plans/reviews/HG-056/round5/' + kind + '.json') == blob('docs/exec-plans/reviews/HG-056/' + kind + '.json')
old_prep = json.loads(blob('docs/exec-plans/evidence/HG-056/PREPARATION.json', OLD))
new_prep = json.loads(blob('docs/exec-plans/evidence/HG-056/PREPARATION.json'))
assert new_prep['runs'][:len(old_prep['runs'])] == old_prep['runs']
assert {k: v for k, v in old_prep.items() if k != 'runs'} == {k: v for k, v in new_prep.items() if k != 'runs'}

original_rev = 'f93364d90aaae9b0b62706fd4e4fe395a8cd8ec5'
original_path = 'docs/exec-plans/reviews/KL-036/SECURITY_DATA_BOUNDARY/audit.py'
original = blob(original_path, original_rev)
assert git('ls-tree', original_rev, '--', original_path).startswith(b'100644 blob cde206aee1eb240862863069104ad291ff98dedb\t')
assert len(original) == 8063 and sha(original) == 'a602ee684cdd7b4d8169388d2a2fe821fc6bc5beadf0d69a593c2ed260ffe382'
assert original == blob('docs/exec-plans/evidence/HG-056/original-reader.fixture')
assert ce.envelope(original) is None and ce.reencoding_record(original) is None
assert ce.read(ROOT, original_path, original_rev) == original
prior = json.loads(blob(D + 'PRIOR_REQUIRED_CHECKS.json'))
prior_checks = []
for row in prior['checks_run']:
    raw = ce.read(ROOT, row['evidence_ref'], R, tested=prior['tested_commit'], command=row['command'],
                  exit_code=0 if row['result'] == 'PASS' else 1)
    prior_checks.append({'id': row['check_id'], 'result': row['result'], 'tested': prior['tested_commit'],
                         'sha256': sha(raw), 'bytes': len(raw)})
    if row['check_id'] == 'compatibility':
        compatibility = [json.loads(line) for line in raw.splitlines() if line.startswith(b'{')][-1]
        assert len(compatibility['expected_maps']) == 2 and len(compatibility['validated_maps']) == 1
        assert compatibility['history_errors'] and compatibility['storage_audit']['errors']
blocker = json.loads(blob('docs/exec-plans/evidence/HG-056/diagnostics/hg056-kl036-history-blocker.json'))
assert not git('ls-tree', blocker['revision'], '--', blocker['path'])
assert git('ls-tree', blocker['parent'], '--', blocker['path']).startswith(b'100644 blob ')

old_index, new_index = json.loads(blob('CURRENT_DOCUMENT_INDEX.json', B)), json.loads(blob('CURRENT_DOCUMENT_INDEX.json'))
for section in ('documents', 'machine_readable'):
    assert len(old_index[section]) == len(new_index[section])
    for old, new in zip(old_index[section], new_index[section]):
        assert {k: v for k, v in old.items() if k != 'sha256'} == {k: v for k, v in new.items() if k != 'sha256'}
        assert sha(blob(new['path'])) == new['sha256']
old_manifest, new_manifest = json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json', B)), json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json'))
assert {k: v for k, v in old_manifest.items() if k != 'files'} == {k: v for k, v in new_manifest.items() if k != 'files'}
old_rows, new_rows = ({x['path']: x for x in doc['files']} for doc in (old_manifest, new_manifest))
assert old_rows.keys() <= new_rows.keys()
for path, row in new_rows.items():
    assert path in old_rows or path.startswith('docs/exec-plans/evidence/HG-056/')
    raw = blob(path)
    assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
base_funcs, new_funcs = functions(blob('tools/harness/compact_evidence.py', B)), functions(blob('tools/harness/compact_evidence.py'))
assert sorted(set(new_funcs) - set(base_funcs)) == ['classification_views', 'source_fields_present', 'source_statements', 'source_target_keys', 'source_tree', 'source_write_keys']
assert sorted(n for n in base_funcs if base_funcs[n] != new_funcs[n]) == ['envelope', 'reserved_ascii']
base_v, new_v = functions(blob('tools/harness/validate_harness.py', B)), functions(blob('tools/harness/validate_harness.py'))
assert base_v.keys() == new_v.keys()
assert sorted(n for n in base_v if base_v[n] != new_v[n]) == ['governance_allowed_patterns', 'validate']

# Use the exact recovered actual current collector stdout; count work without
# timing assumptions or a production budget. No historical input is executed.
scale = []
parse = ce.ast.parse
for copies in (1, 2):
    calls = [0]
    def observed_parse(*args, **kwargs):
        calls[0] += 1
        return parse(*args, **kwargs)
    ce.ast.parse = observed_parse
    started = time.monotonic()
    try:
        raw = outputs['full_collection'] * copies
        assert ce.reserved_ascii(raw) is False
    finally:
        ce.ast.parse = parse
    scale.append({'copies': copies, 'bytes': len(raw), 'parse_calls': calls[0],
                  'seconds': round(time.monotonic() - started, 3), 'reserved': False})
assert scale[1]['parse_calls'] < 2 * scale[0]['parse_calls']
test_tree = ast.parse(blob('tests/harness/test_compact_evidence.py'))
static_params = {}
for node in ast.walk(test_tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'param':
        label = next((kw.value.value for kw in node.keywords if kw.arg == 'id' and isinstance(kw.value, ast.Constant)), None)
        if label and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, bytes):
            static_params[label] = ast.literal_eval(node.args[0])
probes = []
probe_inputs = [(name, static_params[name], hostile) for name, hostile in (
    ('byte-string-write', True), ('byte-string-read', False),
    ('multiline-comment-target', True), ('multiline-prose-target', True), ('field-get', False))]
probe_inputs.append(('deep-native-read', b'(' * 256 + static_params['field-get'] + b')' * 256, True))
for name, raw, hostile in probe_inputs:
    outcomes = []
    for classify in (ce.envelope, ce.reencoding_record):
        try:
            assert classify(raw) is None
            outcomes.append('plain')
        except ValueError as error:
            outcomes.append(str(error))
    assert all(value != 'plain' for value in outcomes) if hostile else outcomes == ['plain', 'plain']
    probes.append({'name': name, 'sha256': sha(raw), 'bytes': len(raw), 'outcomes': outcomes})

report = {'purpose': 'INDEPENDENT_GENERAL_EXACT_GIT_METADATA_ONLY', 'B': B, 'T': T, 'R': R,
          'environment': {k: run[k] for k in ('python', 'python_version', 'PYTHONPATH', 'versions')},
          'checks': checks, 'execution': execution_details, 'isolated_stdout_count': 103,
          'isolated_identity_artifact_claimed': False, 'paths_in_scope': len(changed),
          'governance_schema_and_bindings': 'PASS', 'old_invalid_result_preserved': True,
          'G5_closed_at_new_revision': True, 'source_tree_identical_T_R': True,
          'frozen_paths_identical': len(frozen_paths), 'derived_index_and_manifest': 'PASS',
          'literal_scope_and_regular_modes': 'PASS', 'old_artifacts_preserved': len(preserved),
          'round5_canonical_copies_exact': True, 'original_helper': {'pins': 'PASS', 'plain': 'PASS', 'bound_read': 'PASS', 'executed': False},
          'prior_actual_outcomes': prior_checks,
          'compatibility': {'expected_maps': compatibility['expected_maps'], 'validated_maps': compatibility['validated_maps'],
                            'history_errors': compatibility['history_errors'], 'storage_errors': compatibility['storage_audit']['errors'], 'rerun': False},
          'external_deletion_tree_confirmed': True, 'source_inspection_authority': 'NOT_IMPLEMENTED/BLOCKED',
          'collection_scaling': scale, 'bounded_original_scope_probes': probes,
          'new_general_implementation_defects': 0, 'whole_cycles_rerun': False, 'root_audit_duplicated': False,
          'reviewer_verifier_initial_failures': ['First invocation passed current capture/result checks, then expected old ScannerError hit incorrect yaml.ScannerError exception path (AttributeError); reviewer script corrected to yaml.scanner.ScannerError.', 'Second invocation passed captures/current schema/prior invalid-result preservation, then assumed round5 canonical copies existed at the earlier reviewed R instead of the later review-record R; corrected to compare exact current R copies. No implementation or evidence was changed.'],
          'reviewer_execution': 'Only this metadata verifier, classification of inert bytes, and bound recovery; no helper/private logs/DB/network/config/credentials.'}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'bindings': 'PASS', 'executed': 951, 'compact': 947, 'reports': 2853,
                  'collect_only': 2177, 'result_schema': 'PASS', 'scaling': scale, 'new_defects': 0}))
