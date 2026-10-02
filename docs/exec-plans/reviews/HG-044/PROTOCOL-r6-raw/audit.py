"""Independent exact-revision protocol audit; inventories retain hashes, not blob copies."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/PROTOCOL-r6-raw'
BASE = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
HEAD = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
TESTED = '06dab6dbb38221e7111c18811cb20b42b8cc2397'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(rev, path):
    return git('show', rev + ':' + path)
def sha(data):
    return hashlib.sha256(data).hexdigest()
def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + '\n')
spec = importlib.util.spec_from_file_location('review_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert git('rev-parse', 'HEAD').decode().strip() == HEAD
assert (ROOT / 'tools/harness/validate_harness.py').read_bytes() == blob(HEAD, 'tools/harness/validate_harness.py')
changed = git('diff', '--name-only', '-z', BASE, HEAD).decode().split('\0')[:-1]
tree = {}
for entry in git('ls-tree', '-r', '-z', HEAD).decode().split('\0')[:-1]:
    meta, path = entry.split('\t', 1)
    tree[path] = meta.split()
inventory = []
for path in changed:
    mode, kind, oid = tree[path]
    data = git('cat-file', 'blob', oid)
    inventory.append(dict(path=path, mode=mode, type=kind, git_blob=oid,
                          bytes=len(data), sha256=sha(data),
                          allowed=v.matches(path, v.governance_allowed_patterns('HG-044'))))
write('path-inventory.json', inventory)
assert all(i['mode'] in ('100644', '100755') and i['type'] == 'blob' and i['allowed'] for i in inventory)
assert git('ls-tree', BASE, 'tools/harness/validate_harness.py').decode().startswith('100755 ')
record = v.load_artifact_at_revision(ROOT, 'docs/exec-plans/governance/HG-044.yaml', HEAD)
assert set(changed) == set(record['files_changed'])
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
assert v.is_ancestor(ROOT, BASE, TESTED) and v.is_ancestor(ROOT, TESTED, HEAD)
suffix = v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-044', 'tested')
assert not suffix, suffix
frozen = json.loads(blob(HEAD, 'FROZEN_BASELINE.json'))
frozen_records = []
for item in frozen['files']:
    path = item['path']
    data = blob(HEAD, path)
    assert blob(BASE, path) == data and sha(data) == item['sha256']
    frozen_records.append(dict(path=path, sha256=sha(data), unchanged=True))
assert blob(BASE, 'FROZEN_BASELINE.json') == blob(HEAD, 'FROZEN_BASELINE.json')
assert not v.m3_frozen_authority_errors(ROOT, HEAD)
assert not v.m3_governance_plan_prefix_errors(ROOT, BASE, HEAD)
schema_before = json.loads(blob(BASE, 'MILESTONE_CLOSURE.schema.json'))
schema_after = json.loads(blob(HEAD, 'MILESTONE_CLOSURE.schema.json'))
assert schema_after['oneOf'][:2] == schema_before['oneOf']
assert all(schema_after['$defs'][k] == val for k, val in schema_before['$defs'].items())
source_before = blob(BASE, 'tools/harness/validate_harness.py').decode()
source_after = blob(HEAD, 'tools/harness/validate_harness.py').decode()
def functions(source):
    lines = source.splitlines(keepends=True)
    return {n.name: ''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
old_funcs, new_funcs = functions(source_before), functions(source_after)
modified = [name for name in old_funcs if old_funcs[name] != new_funcs.get(name)]
assert set(modified) == {'governance_allowed_patterns', 'validate'}
assert not any(p.startswith(('src/', 'tests/db/', '.github/', 'migrations/')) for p in changed)
assert 'docs/exec-plans/milestones/M3.json' not in tree
backlog = json.loads(blob(HEAD, v.BACKLOG))
tasks = {t['id']: t for t in backlog['tasks']}
assert {t['id'] for t in tasks.values() if t['milestone'] == 'M3' and t['status'] != 'SUPERSEDED'} == v.M3_TASK_IDS
contracts = []
for exit_id, mapping in v.M3_EXIT_TASK_CHECKS.items():
    for task, ids in mapping.items():
        for check_id in ids:
            contract = next(c for c in tasks[task]['check_contracts'] if c['check_id'] == check_id)
            digest = v.canonical_value_sha(contract)
            assert digest == v.M3_CHECK_CONTRACT_DIGESTS[task + ':' + check_id]
            contracts.append(dict(exit_id=exit_id, task_identity=tasks[task]['task_identity'],
                                  digest=digest, **contract))
assert len(contracts) == 52
assert len(v.M3_CHECK_CONTRACT_DIGESTS) == 52
write('check-contracts.json', contracts)
rows = v.packet_json_section(blob(HEAD, 'docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
assert not v.m3_boundary_layer_errors(rows, json.loads(blob(HEAD, 'KineticLoop_Acceptance_Spec_v1.2.2.json'))['supplemental_boundary_requirements'])
assert len(rows) == 31
deferred = [r for r in rows if r['disposition'] != 'KL028_PLANNED_EXECUTABLE']
assert len(deferred) == 12 and all(r['status'] == 'NOT_RUN' for r in deferred)
write('boundary-ledger.json', rows)
selected = []
for check in record['checks_run']:
    payload = json.loads(blob(HEAD, check['evidence_ref']))
    assert payload['tested_commit'] == TESTED and payload['base_commit'] == BASE
    if check['check_id'] == 'scope':
        assert check['result'] == 'PASS' and all(payload['checks'].values())
        selected.append(dict(check_id='scope', ref=check['evidence_ref'],
                             sha256=sha(blob(HEAD, check['evidence_ref'])), checks=payload['checks']))
        continue
    assert payload['result'] == check['result'] == 'PASS' and payload['exit_code'] == 0
    assert payload['command'] == check['command']
    raw = payload['raw_utf8'].encode()
    assert sha(raw) == payload['raw_sha256'] and len(raw) == payload['raw_byte_count']
    selected.append(dict(check_id=check['check_id'], ref=check['evidence_ref'],
                         sha256=sha(blob(HEAD, check['evidence_ref'])), raw_sha256=sha(raw),
                         raw_bytes=len(raw), raw_utf8=payload['raw_utf8']))
write('selected-evidence.json', selected)
compact_paths = [p for p in changed if not p.startswith(('docs/exec-plans/reviews/', 'docs/exec-plans/evidence/'))]
(OUT / 'bounded-source-diff.patch').write_bytes(git('diff', BASE, HEAD, '--', *compact_paths))
write('audit.json', dict(base_commit=BASE, tested_commit=TESTED, reviewed_head_sha=HEAD,
    changed_paths=len(changed), exact_declared_paths=True, all_regular_allowed=True,
    frozen=frozen_records, no_actual_m3=True, no_runtime_ci_peer_changes=True,
    tested_suffix_errors=suffix, schema_m1_m2_preserved=True,
    modified_existing_functions=modified, unchanged_existing_functions=len(old_funcs)-len(modified),
    active_m3=sorted(v.M3_TASK_IDS), supporting_kl074_milestone=tasks['KL-074']['milestone'],
    check_contract_count=len(contracts), boundary_rows=len(rows), deferred_rows=len(deferred),
    deferred=[dict(requirement_id=r['requirement_id'], layer=r['layer'], status=r['status']) for r in deferred]))
print('Independent protocol inventory, contract hashes, frozen and selected evidence: PASS')
