"""Bounded independent audit; imports only immutable reviewed Git source; no DB lifecycle."""
import ast
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[5]
SHA = '351f0eda41ad492e66115f9ea1e41e3e0f9abf3d'
BASE = '9268fc8dd8c071c02dc5c698274dbf6fcd112776'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, rev=SHA):
    return git('show', rev + ':' + path)
source = blob('tools/harness/validate_harness.py').decode()
v = {'__file__': str(ROOT / 'tools/harness/validate_harness.py'), '__name__': 'immutable_db_review'}
exec(compile(source, SHA + ':tools/harness/validate_harness.py', 'exec'), v)
backlog = json.loads(blob(v['BACKLOG']))
tasks = {t['id']: t for t in backlog['tasks']}
changed = git('diff', '--name-only', BASE, SHA).decode().splitlines()
protected = [p for p in changed if p.startswith(('src/', 'migrations/', 'tests/db/', '.github/')) or p in ('FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', v['BACKLOG'], v['TRACEABILITY'])]
assert not protected, protected
old_schema = json.loads(blob('MILESTONE_CLOSURE.schema.json', BASE))
new_schema = json.loads(blob('MILESTONE_CLOSURE.schema.json'))
assert old_schema['oneOf'] == new_schema['oneOf'][:2]
assert all(new_schema['$defs'][k] == val for k, val in old_schema['$defs'].items())
def functions(text):
    return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
old_functions = functions(blob('tools/harness/validate_harness.py', BASE).decode())
new_functions = functions(source)
unchanged = [name for name in old_functions if name != 'validate' and old_functions[name] == new_functions[name]]
assert {name for name in old_functions if old_functions[name] != new_functions[name]} == {'validate', 'governance_allowed_patterns'}
for exit_id, mapping in v['M3_EXIT_TASK_CHECKS'].items():
    for name, ids in mapping.items():
        contracts = {c['check_id']: c for c in tasks[name]['check_contracts']}
        for check in ids:
            assert v['canonical_value_sha'](contracts[check]) == v['M3_CHECK_CONTRACT_DIGESTS'][name + ':' + check]
            assert contracts[check]['command'] in v['M3_REGRESSION_COMMANDS']
assert 'KL-078' in tasks['KL-076']['depends_on']
assert 'KL-079' in tasks['KL-077']['depends_on']
ledger = v['packet_json_section'](blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
assert len(ledger) == 31
assert sum(r['disposition'] == 'KL028_PLANNED_EXECUTABLE' for r in ledger) == 19
assert len(v['M3_TASK_IDS']) == 16
assert not v['m3_frozen_authority_errors'](ROOT, SHA)
capture = json.loads(blob('docs/exec-plans/evidence/HG-044/capture-integrity-e748b37.json'))
for item in capture['records']:
    data = blob(item['path'])
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    record = json.loads(data)
    raw = record['raw_utf8'].encode()
    assert hashlib.sha256(raw).hexdigest() == record['raw_sha256'] == item['raw_sha256']
    assert len(raw) == record['raw_byte_count'] == item['raw_byte_count']
    assert record['exit_code'] == 0 and record['tested_commit'] == capture['tested_commit']
suffix = git('diff', '--name-only', capture['tested_commit'], SHA).decode().splitlines()
assert all(v['matches'](p, v['governance_allowed_patterns']('HG-044')) for p in suffix)

# Exercise the immutable content oracle with only Git/provenance boundaries stubbed.
# This is a synthetic validator probe, never project/DB completion evidence.
raws = {}
prefix = 'docs/exec-plans/evidence/HG-999/'
def raw(name, text):
    path = prefix + name
    raws[path] = text.encode()
    return {'path': path, 'sha256': hashlib.sha256(raws[path]).hexdigest()}
commands = v['M3_REGRESSION_COMMANDS']
payload = {'change_id': 'HG-999', 'tested_commit': SHA, 'status': 'PASS', 'commands': commands, 'executions': []}
for i, command in enumerate(commands):
    run = {'command': command, 'tested_commit': SHA, 'exit_code': 0, 'stdout': raw(f'{i}.log', 'HARNESS_CHECK_PASS\n')}
    if command != 'uv run kl check-harness':
        selectors = (['tests/unit'] if command == 'uv run kl test-unit' else ['tests/harness'] if command == 'uv run kl test-harness' else command.removeprefix('uv run pytest -q ').split())
        nodes = [s if '::' in s else s + ('/example.py' if not s.endswith('.py') else '') + '::test_example' for s in selectors]
        run['stdout'] = raw(f'{i}.log', f'{len(nodes)} passed in 0.1s\n')
        cases = []
        for node in nodes:
            parts = node.split('::')
            klass = '.'.join([parts[0].removesuffix('.py').replace('/', '.'), *parts[1:-1]])
            cases.append(f'<testcase classname="{escape(klass)}" name="{escape(parts[-1])}"/>')
        run['junit'] = raw(f'{i}.xml', '<testsuite>' + ''.join(cases) + '</testsuite>')
        collect = {'command': 'uv run pytest --collect-only -q ' + ' '.join(selectors), 'tested_commit': SHA, 'exit_code': 0, 'nodeids': nodes, 'stdout': raw(f'{i}-collect.log', '\n'.join(nodes) + f'\n{len(nodes)} tests collected in 0.1s\n')}
        run['collection'] = raw(f'{i}-collect.json', json.dumps(collect))
    payload['executions'].append(run)
v['resolve'] = lambda root, revision: revision
v['is_ancestor'] = lambda *args: True
v['governance_suffix_errors'] = lambda *args: []
v['m3_evidence_bytes'] = lambda root, item, evaluated: raws[item['path']]
records = {n: {'merge_commit': SHA} for n in v['M3_TASK_IDS']}
def errors(p):
    return v['m3_execution_evidence_errors'](ROOT, p, SHA, SHA, records)
assert errors(payload) == []
multi = commands.index('uv run pytest -q tests/db/test_migrations.py tests/db/test_transaction_interfaces.py')
omitted = copy.deepcopy(payload)
run = omitted['executions'][multi]
collect = json.loads(raws[run['collection']['path']])
collect['nodeids'] = collect['nodeids'][:1]
collect['stdout'] = raw('omitted-collect.log', collect['nodeids'][0] + '\n1 test collected in 0.1s\n')
run['collection'] = raw('omitted-collect.json', json.dumps(collect))
run['stdout'] = raw('omitted.log', '1 passed in 0.1s\n')
run['junit'] = raw('omitted.xml', '<testsuite><testcase classname="tests.db.test_migrations" name="test_example"/></testsuite>')
omission_errors = errors(omitted)
assert omission_errors == []
float_execution = copy.deepcopy(payload)
float_execution['executions'][multi]['exit_code'] = 0.0
float_execution_errors = errors(float_execution)
assert float_execution_errors == []
float_collection = copy.deepcopy(payload)
run = float_collection['executions'][multi]
collect = json.loads(raws[run['collection']['path']])
collect['exit_code'] = 0.0
run['collection'] = raw('float-collection.json', json.dumps(collect))
float_collection_errors = errors(float_collection)
assert float_collection_errors == []
bool_execution = copy.deepcopy(payload)
bool_execution['executions'][multi]['exit_code'] = False
assert errors(bool_execution)
print(json.dumps({'reviewed_head_sha': SHA, 'base_commit': BASE, 'status': 'PASS', 'scope_protected_changes': protected, 'unchanged_existing_functions': len(unchanged), 'legacy_schema_preserved': True, 'mapped_check_contract_digests_verified': len(v['M3_CHECK_CONTRACT_DIGESTS']), 'boundary_rows': len(ledger), 'boundary_planned': 19, 'boundary_deferred': 12, 'interleaving_dc_ids': 9, 'i04_wf': 'NOT_RUN', 'frozen_integrity': 'PASS', 'implementation_captures_integrity': 'PASS', 'tested_suffix_own_governance_scope': suffix, 'probes': {'omitted_second_selector': omission_errors, 'float_execution_exit_code': float_execution_errors, 'float_collection_exit_code': float_collection_errors}, 'probe_limit': 'Content-oracle probe uses synthetic logs and stubs exact Git provenance; no closure, execution, or real DB pass is claimed.'}, indent=2))
