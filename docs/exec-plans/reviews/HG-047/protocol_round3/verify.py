"""Independent HG047 protocol review: read exact Git blobs, never envelope counts as proof."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib
import yaml

ROOT = Path(sys.argv[1]).resolve()
BASE = '391c9198fa8ec647e377a0572700bc7568468c85'
TESTED = 'f29ffa97d9057eacc4bda7ad593b843c9c52c5a2'
HEAD = '589e538579f519bc10d178fa02dff12332931ba7'
PREFIX = 'docs/exec-plans/evidence/HG-047/round3-f29ffa9/'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def blob(revision, path):
    rows = [r for r in git('ls-tree', '-z', revision, '--', path).split(b'\0') if r]
    assert len(rows) == 1
    header, found = rows[0].split(b'\t')
    assert found.decode() == path and header.split()[:2] in ([b'100644', b'blob'], [b'100755', b'blob'])
    return git('cat-file', 'blob', header.split()[2].decode())

def decode(path, tested=TESTED, command=None, exit_code=0):
    envelope = json.loads(blob(HEAD, path))
    assert envelope['kineticloop_evidence'] == 'gzip-v1'
    assert envelope['tested_commit'] == tested and envelope['exit_code'] == exit_code
    if command is not None:
        assert envelope['command'] == command
    git('merge-base', '--is-ancestor', tested, HEAD)
    payload = envelope['payload']
    assert payload == str(Path(path).parent / (envelope['raw_sha256'] + '.gz'))
    stored = blob(HEAD, payload)
    assert len(stored) == envelope['stored_bytes'] <= 8 * 1024 * 1024
    assert sha(stored) == envelope['stored_sha256']
    assert envelope['raw_bytes'] <= 64 * 1024 * 1024
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    raw = decoder.decompress(stored, envelope['raw_bytes'] + 1)
    assert decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
    assert len(raw) == envelope['raw_bytes'] and sha(raw) == envelope['raw_sha256']
    return raw

record = yaml.safe_load(blob(HEAD, 'docs/exec-plans/governance/HG-047.yaml'))
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
checks = {}
for check in record['checks_run']:
    assert check['result'] == 'PASS'
    raw = decode(check['evidence_ref'], command=check['command'])
    checks[check['check_id']] = {'command': check['command'], 'raw_bytes': len(raw), 'raw_sha256': sha(raw)}

raw_evidence = {}
for path in git('ls-tree', '-r', '--name-only', HEAD, '--', PREFIX).decode().splitlines():
    if path.endswith('.json') and path != PREFIX + 'execution.json':
        raw = decode(path)
        raw_evidence[path] = {'raw_bytes': len(raw), 'raw_sha256': sha(raw)}

receipt = json.loads(decode(PREFIX + 'worker-receipt-json.json'))
summary = json.loads(blob(HEAD, PREFIX + 'execution.json'))
assert receipt['head'] == TESTED and receipt['base'] == BASE
assert receipt['status'] == 'PASS' and receipt['container_removed'] and receipt['volume_removed']
assert receipt['full_database_required'] is False
for check in receipt['checks']:
    assert check['exit_code'] == 0 and check['interrupted'] is False
    path = summary['artifact_refs'][check['stdout']['path']]
    raw = decode(path, command=' '.join(check['argv']))
    assert check['stdout']['sha256'] == sha(raw) and check['stdout']['bytes'] == len(raw)
for name, expected in receipt['artifacts'].items():
    assert sha(decode(summary['artifact_refs'][name])) == expected

counts = {}
for suite, expected in [('harness', 1306), ('unit', 241)]:
    output = decode(PREFIX + suite + '.json').decode()
    passed = re.findall(r'\b([1-9][0-9]*) passed\b', output)
    assert passed and int(passed[-1]) == expected
    assert not re.search(r'\b[1-9][0-9]* (?:failed|errors?|skipped|deselected|xfailed|xpassed)\b', output)
    xml = decode(PREFIX + 'worker--' + suite + '-xml.json')
    cases = list(ET.fromstring(xml).iter('testcase'))
    names = [(c.get('classname'), c.get('name')) for c in cases]
    assert len(cases) == len(set(names)) == expected
    assert all(not list(c.iter(tag)) for c in cases for tag in ('failure', 'error', 'skipped'))
    counts[suite] = {'tests': expected, 'failures': 0, 'errors': 0, 'skipped': 0, 'junit_raw_sha256': sha(xml)}
    if suite == 'harness':
        harness_cases = set(names)
worker = json.loads(decode(PREFIX + 'worker--run--execution-json.json'))
assert worker['exit_code'] == 0 and len(worker['nodeids']) == len(set(worker['nodeids'])) == 1306
expected_cases = set()
for node in worker['nodeids']:
    address, bracket, parameters = node.partition('[')
    parts = address.split('::')
    expected_cases.add(('.'.join([parts[0].removesuffix('.py').replace('/', '.'), *parts[1:-1]]), parts[-1] + bracket + parameters))
assert expected_cases == harness_cases
collection = decode(PREFIX + 'collection.json').decode()
raw_nodes = [line for line in collection.splitlines() if line.startswith('tests/') and '::' in line]
assert raw_nodes == worker['nodeids']
assert re.findall(r'(?m)^([0-9]+) tests collected in ', collection) == ['1306']
assert decode(PREFIX + 'merge_gate.json') == b'HARNESS_CHECK_PASS tasks=77 active=74\n'
development = json.loads(decode(PREFIX + 'development-final-json.json'))
assert development['tested_commit'] == TESTED and development['status'] == 'PASS'
assert development['mode'] == 'DEVELOPMENT_NO_PUBLICATION'
assert development['test_only'] is True and development['full_db'] is False
for key in ['app_object_created', 'signer_config_read', 'admission_read', 'publication']:
    assert development[key] is False
for name, digest in development['controller_files'].items():
    assert sha(blob(HEAD, 'tools/harness/' + name)) == digest
assert development['image_environment']['Os'] == 'linux'
assert development['image_environment']['Architecture'] == 'arm64'

failed_head = git('rev-parse', '8a78241^{commit}').decode().strip()
failed = decode('docs/exec-plans/evidence/HG-047/development-8a78241/harness-log.json', tested=failed_head, exit_code=1).decode()
assert '1304 passed, 2 errors' in failed and ('Argument list too long' in failed or 'E2BIG' in failed)

changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
protected_prefixes = ('src/', 'migrations/', 'tests/db/', '.github/', 'docs/exec-plans/active/', 'docs/exec-plans/completed/', 'docs/exec-plans/integrations/', 'docs/exec-plans/milestones/')
assert not any(path.startswith(protected_prefixes) for path in changed)
protected_files = ['FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Acceptance_Spec_v1.2.2.json', 'KineticLoop_Integration_Acceptance_v0.1.json', 'tools/harness/db_policy.py']
frozen = json.loads(blob(HEAD, 'FROZEN_BASELINE.json'))
protected_files += [entry['path'] for entry in frozen['files']]
protected_hashes = {}
for path in protected_files:
    current = blob(HEAD, path)
    assert current == blob(BASE, path)
    protected_hashes[path] = sha(current)
for entry in frozen['files']:
    assert protected_hashes[entry['path']] == entry['sha256']
assert not any('/HG-045/' in p or '/HG-046/' in p or p.endswith('/HG-045.yaml') or p.endswith('/HG-046.yaml') for p in changed)

source = 'tools/harness/validate_harness.py'
old_tree, new_tree = [ast.parse(blob(rev, source)) for rev in (BASE, HEAD)]
def m3_constants(tree):
    return {name.id: ast.dump(node.value) for node in tree.body if isinstance(node, ast.Assign) for name in node.targets if isinstance(name, ast.Name) and name.id.startswith('M3_')}
assert m3_constants(old_tree) == m3_constants(new_tree)
unchanged_functions = ['m3_pytest_count', 'm3_layer_errors', 'm3_dependency_order_errors', 'm3_frozen_authority_errors', 'm3_milestone_closure_errors']
for name in unchanged_functions:
    functions = [next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name) for tree in (old_tree, new_tree)]
    for function in functions:
        function.decorator_list = []
    assert ast.dump(functions[0]) == ast.dump(functions[1]), name
fix_path = 'tests/harness/test_compact_evidence.py'
trees = [ast.parse(blob(rev, fix_path)) for rev in (failed_head, TESTED)]
class RemoveIDs(ast.NodeTransformer):
    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'parametrize':
            node.keywords = [k for k in node.keywords if k.arg != 'ids']
        return self.generic_visit(node)
assert ast.dump(RemoveIDs().visit(trees[0])) == ast.dump(RemoveIDs().visit(trees[1]))
suffix = git('diff', '--name-only', TESTED, HEAD).decode().splitlines()
assert all(p == 'docs/exec-plans/governance/HG-047.yaml' or p.startswith('docs/exec-plans/evidence/HG-047/') for p in suffix)

spec = importlib.util.spec_from_file_location('review_validator', ROOT / source)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-047', 'tested') == []
audit = v.compact_evidence.audit(ROOT, BASE, HEAD, 'HG-047')
assert audit['errors'] == []
print(json.dumps({'reviewed_head_sha': HEAD, 'base_commit': BASE, 'tested_commit': TESTED,
 'status': 'PASS', 'raw_command_checks': checks, 'verified_envelopes': raw_evidence,
 'raw_test_counts': counts, 'harness_collection_execution_junit_equal': True,
 'prior_failure_preserved': {'head': failed_head, 'passed': 1304, 'errors': 2, 'cause': 'E2BIG'},
 'protected_hashes': protected_hashes, 'M3_constants_unchanged': sorted(m3_constants(new_tree)),
 'M3_oracle_functions_unchanged_excluding_session_decorator': unchanged_functions,
 'latest_test_fix_AST_equal_after_removing_ids': True, 'tested_suffix_source_unchanged': True,
 'development_execution_only': True, 'full_db_and_final_app_gate': 'NOT_RUN',
 'budget': audit}, indent=2))
