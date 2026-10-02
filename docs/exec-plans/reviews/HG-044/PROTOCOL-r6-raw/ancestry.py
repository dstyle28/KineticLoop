"""Bind available actual integrated records; absent prospective records stay absent."""
import importlib.util
import json
from pathlib import Path
import jsonschema

root = Path.cwd()
out = root / 'docs/exec-plans/reviews/HG-044/PROTOCOL-r6-raw'
head = 'cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54'
spec = importlib.util.spec_from_file_location('ancestry_validator', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
backlog = v.load_artifact_at_revision(root, v.BACKLOG, head)
tasks = {t['id']: t for t in backlog['tasks']}
schemas = [jsonschema.Draft202012Validator(v.load_artifact_at_revision(root, p, head)) for p in
           (v.MILESTONE_CLOSURE_SCHEMA, v.INTEGRATION_SCHEMA, 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
pending = sorted(v.M3_TASK_IDS | {'KL-074'})
records = {}
missing = []
checks = []
while pending:
    name = pending.pop()
    if name in records or name in missing:
        continue
    path = f'docs/exec-plans/integrations/{name}.json'
    if not v.revision_regular_file(root, path, head):
        missing.append(name)
        continue
    record = v.load_artifact_at_revision(root, path, head)
    records[name] = record
    errors = v.integration_record_errors(root, Path(path), record, *schemas[1:], tasks)
    assert not errors, (name, errors)
    result_paths = v.result_paths_at_revision(root, name, record['reviewed_head_sha'])
    assert len(result_paths) == 1
    result = v.load_artifact_at_revision(root, result_paths[0], record['reviewed_head_sha'])
    dependencies = []
    for dep in tasks[name]['depends_on']:
        dependency = v.load_artifact_at_revision(root, f'docs/exec-plans/integrations/{dep}.json', head)
        for key in ('base_commit', 'tested_commit'):
            assert v.is_ancestor(root, dependency['merge_commit'], result[key]), (name, dep, key)
        dependencies.append(dict(task_id=dep, merge_commit=dependency['merge_commit'],
                                  before_consumer_base=True, before_consumer_tested=True))
    checks.append(dict(task_identity=tasks[name]['task_identity'], record=record,
                       result_path=result_paths[0], result_sha256=v.blob_sha_at_revision(root, result_paths[0], record['reviewed_head_sha']),
                       dependencies=dependencies))
    pending.extend(tasks[name]['depends_on'])
assert set(missing) == {'KL-028', 'KL-029'}, missing
assert not v.m3_dependency_order_errors(root, records, tasks)
closures = []
for name, fn in [('M1', v.milestone_closure_errors), ('M2', v.m2_milestone_closure_errors)]:
    path = f'docs/exec-plans/milestones/{name}.json'
    closure = v.load_artifact_at_revision(root, path, head)
    errors = fn(root, closure, *schemas, backlog, tasks)
    assert not errors, errors
    closures.append(dict(milestone=name, sha256=v.blob_sha_at_revision(root, path, head), errors=errors))
(out / 'ancestry.json').write_text(json.dumps(dict(reviewed_head_sha=head, integrations=checks,
    absent_m3_integrations=missing, prerequisites=closures,
    statement='Absent KL-028/KL-029 integrations prevent actual M3 closure; synthetic inputs are not project evidence.'), indent=2) + '\n')
print('Available exact integration chains and transitive merge-before-base/tested checks: PASS; KL-028/KL-029 absent')
