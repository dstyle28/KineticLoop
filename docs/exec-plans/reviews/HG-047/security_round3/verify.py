"""Independent security review of committed HG047 proof; no network or execution authority."""
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[5]
BASE = '391c9198fa8ec647e377a0572700bc7568468c85'
HEAD = '589e538579f519bc10d178fa02dff12332931ba7'
TESTED = 'f29ffa97d9057eacc4bda7ad593b843c9c52c5a2'
OUT = Path(__file__).resolve().parent

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/harness' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ce = load('compact_evidence')
v = load('validate_harness')
gate = load('local_gate')
assert git('rev-parse', 'HEAD').decode().strip() == HEAD
subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, TESTED], cwd=ROOT, check=True)
assert not v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-047', 'tested')
paths = git('diff', '--name-only', '--no-renames', BASE, HEAD).decode().splitlines()
assert all(v.matches(p, v.governance_allowed_patterns('HG-047')) for p in paths)
protected = ['FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'src', 'migrations',
             'tests/db', '.github/workflows', 'KineticLoop_Harness_Backlog_v0.2.json',
             'KineticLoop_Harness_Traceability_v0.3.json', 'MILESTONE_CLOSURE.schema.json',
             'docs/exec-plans/active/KL-080.md', 'tools/harness/db_policy.py',
             'tools/harness/db_ci.py', 'tools/harness/github_app.py', 'tools/harness/gate_validate.py',
             'tools/harness/gate_pytest.py', 'tools/harness/db_ci_pytest.py', 'tools/harness/local_db']
for identity in ('HG-045', 'HG-046'):
    protected += [f'docs/exec-plans/{kind}/{identity}' for kind in ('evidence', 'reviews')]
    protected.append(f'docs/exec-plans/governance/{identity}.yaml')
protected += [e['path'] for e in json.loads(git('show', BASE + ':FROZEN_BASELINE.json'))['files']]
assert not git('diff', '--name-only', BASE, HEAD, '--', *protected)
source_paths = [p for p in paths if not p.startswith('docs/exec-plans/')]
assert not git('diff', '--name-only', TESTED, HEAD, '--', *source_paths)
index = json.loads(git('show', HEAD + ':CURRENT_DOCUMENT_INDEX.json'))
for entry in index['documents'] + index['machine_readable']:
    assert digest(git('show', HEAD + ':' + entry['path'])) == entry['sha256']
record = yaml.safe_load(git('show', HEAD + ':docs/exec-plans/governance/HG-047.yaml'))
assert (record['base_commit'], record['tested_commit']) == (BASE, TESTED)
proof = {'reviewed': HEAD, 'base': BASE, 'tested': TESTED, 'status': 'PASS',
         'scope': {'changed_paths': paths, 'source_paths': source_paths,
                   'protected_paths_verified_unchanged': sorted(set(protected)),
                   'tested_result_suffix_valid': True, 'source_matches_tested': True}}
proof['budget'] = ce.audit(ROOT, BASE, HEAD, 'HG-047')
assert not proof['budget']['errors']
all_envelopes = []
for path in paths:
    if not path.startswith('docs/exec-plans/evidence/HG-047/') or not path.endswith('.json'):
        continue
    data = git('show', HEAD + ':' + path)
    envelope = ce.envelope(data)
    if envelope is None:
        continue
    raw = ce.read(ROOT, path, HEAD)
    assert len(raw) == envelope['raw_bytes'] and digest(raw) == envelope['raw_sha256']
    assert git('ls-tree', HEAD, '--', path).startswith(b'100644 blob ')
    assert git('ls-tree', HEAD, '--', envelope['payload']).startswith(b'100644 blob ')
    all_envelopes.append({'ref': path, 'raw_sha256': digest(raw), 'raw_bytes': len(raw)})
proof['all_committed_envelopes'] = all_envelopes
proof['selected_checks'] = []
for check in record['checks_run']:
    raw = ce.read(ROOT, check['evidence_ref'], HEAD, tested=TESTED,
                  command=check['command'], exit_code=0)
    proof['selected_checks'].append({'id': check['check_id'], 'sha256': digest(raw),
                                    'bytes': len(raw), 'command': check['command']})
prefix = 'docs/exec-plans/evidence/HG-047/round3-f29ffa9/'
execution = json.loads(git('show', HEAD + ':' + prefix + 'execution.json'))
raws = {name: ce.read(ROOT, ref, HEAD, tested=TESTED) for name, ref in execution['artifact_refs'].items()}
worker = json.loads(raws['worker-receipt.json'])
final = json.loads(raws['development-final.json'])
initial = json.loads(raws['development.json'])
assert initial['status'] == 'RUNNING' and final['status'] == 'PASS'
assert all(final[k] == value for k, value in initial.items() if k != 'status')
assert final['mode'] == 'DEVELOPMENT_NO_PUBLICATION'
assert final['test_only'] is True and final['full_db'] is False
for key in ('app_object_created', 'signer_config_read', 'admission_read', 'publication'):
    assert final[key] is False
assert (worker['base'], worker['head']) == (BASE, TESTED)
assert worker['status'] == 'PASS' and worker['full_database_required'] is False
assert worker['container_removed'] and worker['volume_removed']
assert worker['mounts'] == [{'Destination': '/var/lib/docker', 'Name': worker['volume'], 'Type': 'volume'}]
assert worker['volume'] == worker['container'] + '-data'
assert execution['full_database'].startswith('NOT_RUN')
assert final['image_environment']['Os'] == 'linux' and final['image_environment']['Architecture'] == 'arm64'
assert execution['image_environment'] == final['image_environment']
assert worker['image'] == final['image_environment']['Id']
for name, expected_hash in worker['artifacts'].items():
    assert digest(raws[name]) == expected_hash
assert set(final['controller_files']) == set(gate.ASSETS)
for name, expected_hash in final['controller_files'].items():
    assert digest(git('show', final['installed_reviewed_revision'] + ':tools/harness/' + name)) == expected_hash
    assert digest(git('show', TESTED + ':tools/harness/' + name)) == expected_hash
assert digest(json.dumps(final['controller_files'], sort_keys=True).encode()) == final['controller']
assert final['command_plan'] == [[name, argv] for name, argv in gate.gate_plan(BASE, TESTED, False, True)]
checks = {}
for check in worker['checks']:
    assert check['exit_code'] == 0 and check['interrupted'] is False
    raw = raws[check['stdout']['path']]
    assert len(raw) == check['stdout']['bytes'] and digest(raw) == check['stdout']['sha256']
    checks[check['check_id']] = check
for label, argv in final['command_plan']:
    assert checks[label]['argv'][-len(argv):] == argv
for check in record['checks_run']:
    label = 'merge_gate' if check['check_id'] == 'authority' else check['check_id']
    if label in checks:
        assert check['command'] == ' '.join(checks[label]['argv'])
counts = {}
for label, expected in [('unit', 241), ('harness', 1306)]:
    tree = ET.fromstring(raws['worker/' + label + '.xml'])
    cases = list(tree.iter('testcase'))
    identities = [(c.get('classname'), c.get('name')) for c in cases]
    assert len(cases) == len(set(identities)) == expected
    assert not any(list(c.iter(tag)) for c in cases for tag in ('failure', 'error', 'skipped'))
    suites = list(tree.iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == expected
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    assert re.search(r'\b' + str(expected) + r' passed\b', raws[label + '.log'].decode())
    assert final['counts'][label] == {'tests': expected, 'failures': 0, 'errors': 0, 'skipped': 0}
    counts[label] = final['counts'][label]
nodes = json.loads(raws['worker/run/execution.json'])
assert nodes['exit_code'] == 0 and len(nodes['nodeids']) == len(set(nodes['nodeids'])) == 1306
collected = re.findall(r'^tests/[^\n]+::[^\n]+$', raws['host/collection.log'].decode(), re.M)
assert len(collected) == 1306 and set(nodes['nodeids']) == set(collected)
fixed = [n for n in collected if 'test_bounded_single_member_decoder[' in n or 'test_budget_rejects_bulk_and_duplicate_metadata[' in n]
assert len(fixed) == 10 and max(len(n.encode()) for n in fixed) == 105
file = 'tests/harness/test_compact_evidence.py'
parent_tree = ast.parse(git('show', TESTED + '^:' + file))
current_tree = ast.parse(git('show', TESTED + ':' + file))
removed = 0
for node in ast.walk(current_tree):
    if isinstance(node, ast.FunctionDef) and node.name in ('test_bounded_single_member_decoder', 'test_budget_rejects_bulk_and_duplicate_metadata'):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                before = len(decorator.keywords)
                decorator.keywords = [kw for kw in decorator.keywords if kw.arg != 'ids']
                removed += before - len(decorator.keywords)
assert removed == 2 and ast.dump(parent_tree) == ast.dump(current_tree)
proof['development_execution'] = {'mode': final['mode'], 'status': final['status'],
    'architecture': final['image_environment']['Architecture'], 'counts': counts,
    'all_receipt_artifact_hashes_verified': len(worker['artifacts']),
    'all_host_observed_commands_verified': len(checks), 'controller_assets_verified': len(gate.ASSETS),
    'controller_assets_identical_to_tested_source': True,
    'collection_equals_observed_nodeids': True, 'id_only_ast_equivalence': True,
    'fixed_case_count': len(fixed), 'fixed_case_max_bytes': max(len(n.encode()) for n in fixed),
    'recorded_container_removed': True, 'recorded_volume_removed': True,
    'no_host_bind_or_socket_mount': True, 'publication': False, 'full_database': 'NOT_RUN',
    'initial_metadata_hash_verified': True, 'final_metadata_preserved_separately': True}
old = 'docs/exec-plans/evidence/HG-047/development-8a78241/'
old_receipt = json.loads(ce.read(ROOT, old + 'worker-receipt-json.json', HEAD))
old_check = json.loads(ce.read(ROOT, old + 'published-check-json.json', HEAD))
assert old_receipt['status'] == 'FAIL' and old_receipt['container_removed'] and old_receipt['volume_removed']
assert old_check['conclusion'] == 'failure' and old_check['head_sha'] == old_receipt['head']
old_junit = ET.fromstring(ce.read(ROOT, old + 'worker--harness-xml.json', HEAD))
old_cases = list(old_junit.iter('testcase'))
assert len(old_cases) == 1306 and sum(bool(list(c.iter('error'))) for c in old_cases) == 2
assert sum(not any(list(c.iter(t)) for t in ('error', 'failure', 'skipped')) for c in old_cases) == 1304
proof['preserved_failed_app_gate'] = {'head': old_check['head_sha'], 'conclusion': 'failure',
    'test_cases': len(old_cases), 'passed': 1304, 'errors': 2, 'cleanup_recorded': True,
    'selected_as_current_pass': False}
(OUT / 'verification.json').write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps({'status': 'PASS', 'reviewed': HEAD, 'committed_envelopes': len(all_envelopes),
                  'selected_checks': len(proof['selected_checks']), 'budget': proof['budget'],
                  'development_execution': proof['development_execution'],
                  'preserved_failed_app_gate': proof['preserved_failed_app_gate']}, indent=2))
