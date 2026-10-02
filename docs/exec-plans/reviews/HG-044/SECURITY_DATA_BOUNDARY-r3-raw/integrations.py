"""Independent actual integration provenance checks at the reviewed SHA."""
import hashlib
import importlib.util
import json
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
SHA = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
spec = importlib.util.spec_from_file_location('integration_audit_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
def read(path, revision=SHA):
    assert v.revision_regular_file(ROOT, path, revision), (path, revision)
    return v.load_artifact_at_revision(ROOT, path, revision)
schemas = [jsonschema.Draft202012Validator(read(name)) for name in (
    v.INTEGRATION_SCHEMA, 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
tasks = {t['id']: t for t in read(v.BACKLOG)['tasks']}
pending = list(v.M3_TASK_IDS | {'KL-074'})
records = {}
rows = []
missing = []
while pending:
    name = pending.pop()
    if name in records:
        continue
    path = f'docs/exec-plans/integrations/{name}.json'
    if not v.revision_regular_file(ROOT, path, SHA):
        missing.append(name)
        continue
    record = read(path)
    records[name] = record
    errors = v.integration_record_errors(ROOT, Path(path), record, *schemas, tasks)
    assert not errors, (name, errors)
    for field in ('result_commit', 'reviewed_head_sha', 'review_record_commit', 'merge_commit'):
        assert v.resolve(ROOT, record[field]) == record[field]
        assert v.is_ancestor(ROOT, record[field], SHA)
    result_paths = v.result_paths_at_revision(ROOT, name, record['reviewed_head_sha'])
    assert len(result_paths) == 1
    result = read(result_paths[0], record['reviewed_head_sha'])
    for check in result['commands_run']:
        assert v.relative_path(check['evidence_ref'])
        assert v.revision_regular_file(ROOT, check['evidence_ref'], record['reviewed_head_sha'])
    for kind in tasks[name]['review_requirements']:
        review = read(f'docs/exec-plans/reviews/{name}/{kind}.json', record['review_record_commit'])
        assert review['status'] == 'PASS' and review['reviewed_head_sha'] == record['reviewed_head_sha']
    rows.append({'task': name, 'integration_sha256': v.blob_sha_at_revision(ROOT, path, SHA),
                 'integration': record, 'result_path': result_paths[0],
                 'result_sha256': v.blob_sha_at_revision(ROOT, result_paths[0], record['reviewed_head_sha']),
                 'errors': errors})
    pending.extend(tasks[name]['depends_on'])
errors = v.m3_dependency_order_errors(ROOT, records, tasks)
assert all(name in ('KL-028', 'KL-029') for name in missing), missing
assert not errors, errors
(OUT / 'integrations.json').write_text(json.dumps({'reviewed_head_sha': SHA, 'status': 'PASS',
    'records': sorted(rows, key=lambda r: r['task']), 'dependency_order_errors': errors,
    'missing_required_m3_integrations': sorted(set(missing)), 'actual_m3_closure_status': 'NOT_READY'}, indent=2) + '\n')
print('ACTUAL_INTEGRATION_PROVENANCE_PASS', len(rows), flush=True)
