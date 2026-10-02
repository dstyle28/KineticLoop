"""Independent exact-SHA HG044 DB review inventory; no source mutations."""
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import jsonschema

ROOT = Path.cwd()
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/DB_CONCURRENCY-r6-raw'
BASE = '2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'
REVIEWED = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
TESTED = '06dab6dbb38221e7111c18811cb20b42b8cc2397'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, rev=REVIEWED):
    return git('show', rev + ':' + path)
def obj(path, rev=REVIEWED):
    return json.loads(blob(path, rev))
def digest(raw):
    return hashlib.sha256(raw).hexdigest()
def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')
spec = importlib.util.spec_from_file_location('db_review_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
changed = git('diff', '--name-only', '-z', BASE, REVIEWED).decode().strip('\0').split('\0')
inventory = []
for path in changed:
    entries = git('ls-tree', REVIEWED, '--', path).decode().strip().split('\t')
    mode, kind, oid = entries[0].split()
    raw = blob(path)
    assert mode in ('100644', '100755') and kind == 'blob', path
    assert v.matches(path, v.governance_allowed_patterns('HG-044')), path
    inventory.append(dict(path=path, mode=mode, kind=kind, git_oid=oid,
                          bytes=len(raw), sha256=digest(raw)))
save('inventory.json', inventory)
source_paths = [p for p in changed if not p.startswith('docs/exec-plans/reviews/HG-044/')
                and not p.startswith('docs/exec-plans/evidence/HG-044/')]
(OUT / 'bounded-source-diff.patch').write_bytes(git('diff', BASE, REVIEWED, '--', *source_paths))
whitespace = {}
for name, paths in [('source', ['.', ':(exclude)docs/exec-plans/reviews/HG-044/**']), ('broad', ['.'])]:
    run = subprocess.run(['git', 'diff', '--check', BASE, REVIEWED, '--', *paths], cwd=ROOT, capture_output=True)
    (OUT / (name + '-whitespace.stdout')).write_bytes(run.stdout)
    (OUT / (name + '-whitespace.stderr')).write_bytes(run.stderr)
    whitespace[name] = dict(exit_code=run.returncode, stdout_sha256=digest(run.stdout), stderr_sha256=digest(run.stderr))
assert whitespace['source']['exit_code'] == 0
save('whitespace.json', whitespace)
record = v.load_artifact_text(blob('docs/exec-plans/governance/HG-044.yaml').decode(), '.yaml')
jsonschema.Draft202012Validator(obj('HARNESS_CHANGE.schema.json')).validate(record)
assert set(record['files_changed']) == set(changed)
assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
assert not v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-044', 'tested')
selected = []
for check in record['checks_run']:
    raw = blob(check['evidence_ref'])
    capture = json.loads(raw)
    if check['check_id'] == 'scope':
        assert check['result'] == capture['status'] == 'PASS' and all(capture['checks'].values())
        assert capture['tested_commit'] == TESTED and capture['base_commit'] == BASE
        selected.append(dict(check_id='scope', path=check['evidence_ref'], sha256=digest(raw), checks=capture['checks']))
        continue
    assert check['result'] == capture['result'] == 'PASS'
    assert capture['tested_commit'] == TESTED and capture['base_commit'] == BASE
    assert type(capture['exit_code']) is int and capture['exit_code'] == 0
    assert capture['command'] == check['command']
    output = capture['raw_utf8'].encode()
    assert digest(output) == capture['raw_sha256'] and len(output) == capture['raw_byte_count']
    selected.append(dict(check_id=check['check_id'], path=check['evidence_ref'], sha256=digest(raw),
                         raw_sha256=digest(output), raw_bytes=len(output), output=capture['raw_utf8']))
save('selected-captures.json', selected)
backlog = obj(v.BACKLOG)
tasks = {t['id']: t for t in backlog['tasks']}
records = {}
pending = sorted(v.M3_TASK_IDS | {'KL-074'})
missing = []
while pending:
    name = pending.pop()
    if name in records or name in missing:
        continue
    path = f'docs/exec-plans/integrations/{name}.json'
    if not v.revision_regular_file(ROOT, path, REVIEWED):
        missing.append(name)
    else:
        records[name] = obj(path)
    pending.extend(tasks[name]['depends_on'])
assert sorted(missing) == ['KL-028', 'KL-029']
schemas = [jsonschema.Draft202012Validator(obj(p)) for p in (
    v.INTEGRATION_SCHEMA, 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
ancestry = []
for name, integration in sorted(records.items()):
    issues = v.integration_record_errors(ROOT, Path(f'docs/exec-plans/integrations/{name}.json'),
                                         integration, *schemas, tasks)
    assert not issues, (name, issues)
    reviewed = integration['reviewed_head_sha']
    paths = v.result_paths_at_revision(ROOT, name, reviewed)
    result = v.load_artifact_at_revision(ROOT, paths[0], reviewed)
    row = dict(task=name, integration_sha256=digest(blob(f'docs/exec-plans/integrations/{name}.json')),
               result_path=paths[0], result_sha256=digest(blob(paths[0], reviewed)),
               revisions=integration, validated_integration_errors=issues, dependencies=[])
    for key in ('result_commit', 'reviewed_head_sha', 'review_record_commit', 'merge_commit'):
        assert v.is_ancestor(ROOT, integration[key], REVIEWED), (name,key)
    for dependency in tasks[name]['depends_on']:
        merge = records[dependency]['merge_commit']
        edges = {key: v.is_ancestor(ROOT, merge, result[key]) for key in ('base_commit', 'tested_commit')}
        assert all(edges.values()), (name, dependency, edges)
        row['dependencies'].append(dict(task=dependency, merge=merge, consumer_base=result['base_commit'],
                                        consumer_tested=result['tested_commit'], edges=edges))
    ancestry.append(row)
save('ancestry.json', dict(missing_integrations=sorted(missing), validated=ancestry))
mapping = []
for exit_id, required in v.M3_EXIT_TASK_CHECKS.items():
    for name, ids in required.items():
        for check_id in ids:
            contract = next(c for c in tasks[name]['check_contracts'] if c['check_id'] == check_id)
            assert v.canonical_value_sha(contract) == v.M3_CHECK_CONTRACT_DIGESTS[name + ':' + check_id]
            mapping.append(dict(exit_id=exit_id, task=name, check_id=check_id, contract=contract,
                                oracle_sha256=v.canonical_value_sha(contract['pass_oracle'])))
save('mapped-checks.json', mapping)
ledger = v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
assert len(ledger) == 31 and not v.m3_boundary_layer_errors(ledger, obj('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements'])
assert sum(r['disposition'] == 'KL028_PLANNED_EXECUTABLE' for r in ledger) == 19
save('boundary-ledger.json', ledger)
def funcs(raw):
    text = raw.decode()
    return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
before = funcs(blob('tools/harness/validate_harness.py', BASE))
after = funcs(blob('tools/harness/validate_harness.py'))
edited = sorted(name for name in before if before[name] != after.get(name))
assert edited == ['governance_allowed_patterns', 'validate'], edited
schema_before = obj(v.MILESTONE_CLOSURE_SCHEMA, BASE)
schema_after = obj(v.MILESTONE_CLOSURE_SCHEMA)
assert schema_after['oneOf'][:2] == schema_before['oneOf']
assert all(schema_after['$defs'][k] == val for k,val in schema_before['$defs'].items())
assert not v.m3_frozen_authority_errors(ROOT, REVIEWED)
assert not v.m3_governance_plan_prefix_errors(ROOT, BASE, REVIEWED)
assert not v.m3_closure_plan_errors(blob(v.PROJECT_PLAN).decode())
assert not v.revision_regular_file(ROOT, 'docs/exec-plans/milestones/M3.json', REVIEWED)
repair_diff = git('diff', 'ec0713f614359b502045d09edea59e7c85f3994b', TESTED, '--',
                  'tools/harness/validate_harness.py', 'tests/harness/test_m3_milestone_closure.py')
(OUT / 'gate-repair-diff.patch').write_bytes(repair_diff)
diagnostic = obj('docs/exec-plans/evidence/HG-044/gate-diagnostic-06dab6d.json')
assert diagnostic['head'] == TESTED and diagnostic['exit_code'] == 1
assert digest(diagnostic['raw_utf8'].encode()) == diagnostic['raw_sha256']
assert 'Traceback' not in diagnostic['raw_utf8']
assert all(line == 'HARNESS_CHECK_FAIL' or line == 'git-worktree-not-clean' or
           line.startswith('governance-review-stale-change:') for line in diagnostic['raw_utf8'].splitlines())
save('audit.json', dict(reviewed_sha=REVIEWED, base_sha=BASE, tested_sha=TESTED,
     changed_paths=len(changed), source_paths=source_paths, edited_prior_functions=edited,
     preserved_prior_function_count=len(before)-len(edited), selected_checks=len(selected),
     integrations_validated=len(records), missing_integrations=sorted(missing),
     mapping_count=len(mapping), boundary_rows=len(ledger), planned_boundary_rows=19,
     deferred_boundary_rows=12, interleaving_rows=10, no_actual_m3=True,
     schema_and_frozen_preserved=True, legal_tested_suffix=True, plan_prefix=True,
     repaired_gate_diagnostic_errors_expected=True))
print('DB_CONCURRENCY independent audit PASS')
