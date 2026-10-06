"""Independent GENERAL review of exact Git revisions, bounded metadata only."""
import ast
import collections
import hashlib
import importlib.util
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
B = '3ec7f7a38d974256a928c3687f63e4d90019e42b'
T = '9650c791e58aeb3aa79dcd20911863b33dc4d62f'
R = 'd8aaf7c897e5a7653daa30b8d3bd906ba859652d'
OLD = '0c3ad1ac6f0811f920002bfb8782e84cf0eb2460'
D = 'docs/exec-plans/evidence/HG-056/checks-repair-' + T + '-4e68e83c/'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blob(path, rev=R):
    entries = git('ls-tree', '-z', rev, '--', path).split(b'\0')
    entries = [x for x in entries if x and x.split(b'\t')[1].decode() == path]
    assert len(entries) == 1 and entries[0].startswith((b'100644 blob ', b'100755 blob '))
    return git('show', rev + ':' + path)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def parsed_functions(raw):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(raw).body
            if isinstance(n, ast.FunctionDef)}

assert git('rev-parse', 'HEAD').decode().strip() == R
for ancestor, descendant in ((B, T), (T, R), (OLD, T)):
    git('merge-base', '--is-ancestor', ancestor, descendant)
spec = importlib.util.spec_from_file_location('general_decoder', ROOT / 'tools/harness/compact_evidence.py')
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)
assert (ROOT / 'tools/harness/compact_evidence.py').read_bytes() == blob('tools/harness/compact_evidence.py')
run = json.loads(blob(D + 'RUN.json'))
assert run['tested_commit'] == T and run['base_commit'] == B and not run['capture_errors']
assert len(run['checks']) == 7
checks, raw_checks, artifacts = [], {}, {}
for item in run['checks']:
    assert item['exit_code'] == 0 and item['result'] == 'PASS'
    raw = ce.read(ROOT, item['evidence_ref'], R, tested=T, command=item['command'], exit_code=0)
    assert sha(raw) == item['raw_sha256'] and len(raw) == item['raw_bytes']
    raw_checks[item['check_id']] = raw
    checks.append({'id': item['check_id'], 'command': item['command'], 'exit': 0,
                   'sha256': sha(raw), 'bytes': len(raw), 'bound_read': 'PASS'})
for key, ident in (('harness_artifacts', 'affected_harness'), ('full_collection_artifacts', 'full_collection')):
    command = next(x['command'] for x in run['checks'] if x['check_id'] == ident)
    for item in run[key]:
        artifacts[item['name']] = ce.read(ROOT, item['evidence_ref'], R, tested=T, command=command, exit_code=0)
identities, phases = {}, {}
for prefix, count in (('harness', 892), ('full-collection', 2118)):
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
    for item in manifest['files']:
        raw = artifacts[prefix + '-' + item['path'] + '.json']
        assert len(raw) == item['bytes'] and sha(raw) == item['sha256']
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
        for items in reports.values():
            assert len(items) == 3 and {x['phase'] for x in items} == {'setup', 'call', 'teardown'}
            assert all(x['outcome'] == 'passed' and x['worker'] in execution['collections'] for x in items)
            assert len({x['worker'] for x in items}) == 1
        junit_ids = ['/'.join(c.attrib['classname'].split('.')[:3]) + '.py::' +
                     '::'.join(c.attrib['classname'].split('.')[3:] + [c.attrib['name']]) for c in cases]
        assert len(junit_ids) == len(set(junit_ids)) == count and set(junit_ids) == set(ids)
        compact_ids = {x for x in ids if x.startswith('tests/harness/test_compact_evidence.py::')}
        assert len(compact_ids) == 888 and manifest['mode'] == 'EXECUTION' and manifest['execution_complete']
        details.update(compact_cases=888, phase_counts=dict(collections.Counter(x['phase'] for x in execution['reports'])),
                       worker_phase_and_junit_binding='PASS')
    else:
        assert not execution['started'] and not execution['reports'] and not cases
        assert execution['collections']['serial'] == ids
        assert manifest['mode'] == 'COLLECTION_ONLY' and not manifest['execution_complete']
        assert {x for x in ids if x.startswith('tests/harness/test_compact_evidence.py::')} == compact_ids
    phases[prefix] = details
assert identities['harness'] <= identities['full-collection']
assert re.search(rb'\b892 passed\b', raw_checks['affected_harness'])
assert re.search(rb'\b103 passed\b', raw_checks['installed_decoder_isolation'])

packet = blob('docs/exec-plans/evidence/HG-056/PACKET.md').decode()
section = packet.split('**Exact write_paths**')[1].split('Only needed classifier')[0]
allowlist = [line.split('`')[1] for line in section.splitlines() if line.startswith('- `')]
validator = ast.parse(blob('tools/harness/validate_harness.py'))
function = next(n for n in validator.body if isinstance(n, ast.FunctionDef) and n.name == 'governance_allowed_patterns')
literal = [ast.literal_eval(n) if not isinstance(n, ast.Name) else {'INDEX': 'CURRENT_DOCUMENT_INDEX.json',
           'MANIFEST': 'HARNESS_DOCUMENT_MANIFEST.json'}[n.id] for n in function.body[0].body[0].value.elts]
assert literal == allowlist
changed = git('diff', '--no-renames', '--name-only', '-z', B, R).decode().split('\0')[:-1]
assert all(any(p == a or (a.endswith('/**') and p.startswith(a[:-2])) for a in allowlist) for p in changed)
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
assert all(p.startswith(D) or p == 'docs/exec-plans/governance/HG-056.yaml' for p in suffix_paths)
for path in changed:
    if not path.startswith(('docs/exec-plans/evidence/', 'docs/exec-plans/reviews/', 'docs/exec-plans/governance/')):
        assert blob(path, T) == blob(path)
scope = json.loads(raw_checks['scope'])
assert scope['base'] == B and scope['head'] == T and scope['status'] == 'PASS'
assert scope['changed_paths'] == git('diff', '--no-renames', '--name-only', '-z', B, T).decode().split('\0')[:-1]
try:
    result = yaml.safe_load(blob('docs/exec-plans/governance/HG-056.yaml'))
except yaml.YAMLError as error:
    result = None
    result_schema = {'status':'FAIL', 'exception':type(error).__name__, 'problem':error.problem,
                     'line':error.problem_mark.line + 1, 'context_line':error.context_mark.line + 1}
else:
    jsonschema.validate(result, json.loads(blob('HARNESS_CHANGE.schema.json')))
    assert result['tested_commit'] == T and result['base_commit'] == B and result['change_status'] == 'BLOCKED'
    assert result['files_changed'] == changed
    result_schema = {'status':'PASS'}
assert result_schema['status'] == 'FAIL' and result_schema['exception'] == 'ScannerError'
old_paths = git('ls-tree', '-r', '--name-only', OLD, '--', 'docs/exec-plans/evidence/HG-056', 'docs/exec-plans/reviews/HG-056').decode().splitlines()
preserved = [x for x in old_paths if not x.endswith(('/PREPARATION.json', '/GENERAL.json', '/SECURITY_DATA_BOUNDARY.json')) or '/round' in x or '/general_' in x]
assert all(blob(x, OLD) == blob(x) for x in preserved)
for kind in ('GENERAL', 'SECURITY_DATA_BOUNDARY'):
    assert blob('docs/exec-plans/reviews/HG-056/round4/' + kind + '.json') == blob('docs/exec-plans/reviews/HG-056/' + kind + '.json', OLD)
prep_old = json.loads(blob('docs/exec-plans/evidence/HG-056/PREPARATION.json', OLD))
prep_new = json.loads(blob('docs/exec-plans/evidence/HG-056/PREPARATION.json'))
assert prep_new['runs'][:len(prep_old['runs'])] == prep_old['runs']
assert {k:v for k,v in prep_new.items() if k != 'runs'} == {k:v for k,v in prep_old.items() if k != 'runs'}
old_result = 'docs/exec-plans/evidence/HG-056/checks-repair-cadb6ccb3e5493548ee8f02803994cd0266ee084-'
retained_cadb = [x for x in git('ls-tree', '-r', '--name-only', T).decode().splitlines() if x.startswith(old_result)]
assert retained_cadb and all(blob(x, T) == blob(x) for x in retained_cadb)

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
for item in prior['checks_run']:
    raw = ce.read(ROOT, item['evidence_ref'], R, tested=prior['tested_commit'], command=item['command'],
                  exit_code=0 if item['result'] == 'PASS' else 1)
    prior_checks.append({'id': item['check_id'], 'result': item['result'], 'tested': prior['tested_commit'],
                         'sha256': sha(raw), 'bytes': len(raw)})
    if item['check_id'] == 'compatibility':
        compatibility = [json.loads(line) for line in raw.splitlines() if line.startswith(b'{')][-1]
        assert len(compatibility['expected_maps']) == 2 and len(compatibility['validated_maps']) == 1
        assert compatibility['history_errors'] and compatibility['storage_audit']['errors']
blocker = json.loads(blob('docs/exec-plans/evidence/HG-056/diagnostics/hg056-kl036-history-blocker.json'))
assert not git('ls-tree', blocker['revision'], '--', blocker['path'])
assert git('ls-tree', blocker['parent'], '--', blocker['path']).startswith(b'100644 blob ')

index_old, index_new = json.loads(blob('CURRENT_DOCUMENT_INDEX.json', B)), json.loads(blob('CURRENT_DOCUMENT_INDEX.json'))
for section in ('documents', 'machine_readable'):
    assert len(index_old[section]) == len(index_new[section])
    for old, new in zip(index_old[section], index_new[section]):
        assert {k:v for k,v in old.items() if k != 'sha256'} == {k:v for k,v in new.items() if k != 'sha256'}
        assert sha(blob(new['path'])) == new['sha256']
manifest_old = json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json', B))
manifest_new = json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json'))
assert {k:v for k,v in manifest_old.items() if k != 'files'} == {k:v for k,v in manifest_new.items() if k != 'files'}
old_rows = {x['path']:x for x in manifest_old['files']}
new_rows = {x['path']:x for x in manifest_new['files']}
assert old_rows.keys() <= new_rows.keys()
for path, row in new_rows.items():
    assert path in old_rows or path.startswith('docs/exec-plans/evidence/HG-056/')
    raw = blob(path)
    assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
base_functions = parsed_functions(blob('tools/harness/compact_evidence.py', B))
new_functions = parsed_functions(blob('tools/harness/compact_evidence.py'))
assert sorted(set(new_functions) - set(base_functions)) == ['source_target_keys', 'source_write_keys']
assert sorted(n for n in base_functions if base_functions[n] != new_functions[n]) == ['envelope', 'reserved_ascii']
old_v = parsed_functions(blob('tools/harness/validate_harness.py', B))
new_v = parsed_functions(blob('tools/harness/validate_harness.py'))
assert old_v.keys() == new_v.keys()
assert sorted(n for n in old_v if old_v[n] != new_v[n]) == ['governance_allowed_patterns', 'validate']
report = {'purpose':'INDEPENDENT_GENERAL_METADATA_ONLY', 'B':B, 'T':T, 'R':R,
          'environment': {k:run[k] for k in ('python','python_version','PYTHONPATH','versions')},
          'checks': checks, 'execution': phases, 'isolated_stdout_count':103,
          'isolated_identity_artifact_claimed':False, 'paths_in_scope':len(changed),
          'literal_scope_and_regular_modes':'PASS', 'frozen_paths_identical':len(frozen_paths),
          'derived_index_and_manifest':'PASS', 'governance_schema':result_schema, 'tested_result_suffix':[R],
          'source_tree_identical_T_R':True, 'old_evidence_and_reviews_unchanged':len(preserved),
          'round4_canonical_copies_exact':True, 'superseded_cadb_files_unchanged':len(retained_cadb),
          'original_helper':{'pins':'PASS','plain':'PASS','bound_read_identical':True,'executed':False},
          'prior_actual_outcomes':prior_checks,
          'compatibility':{'expected_maps':compatibility['expected_maps'],'validated_maps':compatibility['validated_maps'],
                           'history_errors':compatibility['history_errors'],'storage_errors':compatibility['storage_audit']['errors'],'rerun':False},
          'external_deletion_tree_confirmed':True, 'source_inspection_authority':'NOT_IMPLEMENTED/BLOCKED',
          'new_functions':['source_target_keys','source_write_keys'], 'changed_decoder_functions':['envelope','reserved_ascii'],
          'changed_validator_functions':['governance_allowed_patterns','validate'],
          'whole_cycles_rerun':False,'new_general_source_defects':1,
          'reviewer_verifier_initial_failures':{'invocations':2,'stage':'governance safe_load','observed_failure':'ScannerError on retained invocation; first invocation yielded without retained output/session identifier'},
          'reviewer_execution':'Only this bounded verifier; no historical helper/input execution, private historical payload, DB/network or root gate.'}
(OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
for path in (Path(__file__), OUT / 'report.json'):
    assert ce.envelope(path.read_bytes()) is None and ce.reencoding_record(path.read_bytes()) is None
print(json.dumps({'bindings':'PASS','executed':892,'compact':888,'phase_reports':2676,'collection_only':2118,
                  'paths':len(changed),'prior_records':len(preserved),'governance_schema':result_schema,'new_general_source_defects':1}, indent=2))
