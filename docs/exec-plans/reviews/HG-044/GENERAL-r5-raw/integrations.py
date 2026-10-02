"""Independently replay available M3/support integration chains at reviewed revision."""
import importlib.util
import json
from pathlib import Path
import jsonschema
ROOT = Path.cwd()
REV = '027bc2368e36e28aa9956489cb57af297882d671'
OUT = ROOT / 'docs/exec-plans/reviews/HG-044/GENERAL-r5-raw'
spec = importlib.util.spec_from_file_location('g_integrations', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
def load(p): return v.load_artifact_at_revision(ROOT, p, REV)
tasks = {t['id']: t for t in load(v.BACKLOG)['tasks']}
schemas = [jsonschema.Draft202012Validator(load(p)) for p in (v.INTEGRATION_SCHEMA, 'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
records = {}; absent = []; pending = list(v.M3_TASK_IDS | {'KL-074'}); reports = []
while pending:
    name = pending.pop()
    if name in records or name in absent: continue
    path = f'docs/exec-plans/integrations/{name}.json'
    if not v.revision_regular_file(ROOT, path, REV):
        absent.append(name); continue
    record = load(path); records[name] = record
    errors = v.integration_record_errors(ROOT, Path(path), record, *schemas, tasks)
    for key in ('result_commit', 'reviewed_head_sha', 'review_record_commit', 'merge_commit'):
        if not v.is_ancestor(ROOT, record[key], REV): errors.append('not-reachable:' + key)
    reports.append({'task': name, 'errors': errors})
    pending.extend(tasks[name]['depends_on'])
order_errors = v.m3_dependency_order_errors(ROOT, records, tasks)
witnesses = []
for exit_id, mapping in v.M3_EXIT_TASK_CHECKS.items():
    for name, names in mapping.items():
        if name in absent: continue
        rec = records[name]; reviewed = rec['reviewed_head_sha']
        result_path = v.result_paths_at_revision(ROOT, name, reviewed)[0]
        result = v.load_artifact_at_revision(ROOT, result_path, reviewed)
        for check in names:
            contract = next(c for c in tasks[name]['check_contracts'] if c['check_id'] == check)
            command = next(c for c in result['commands_run'] if c['check_id'] == check)
            def ref(p): return {'path': p, 'revision': reviewed, 'sha256': v.blob_sha_at_revision(ROOT, p, reviewed)}
            witness = {'task_identity': tasks[name]['task_identity'], 'check_id': check, 'tested_commit': result['tested_commit'], 'result': 'PASS', 'command': command['command'], 'oracle_sha256': v.canonical_value_sha(contract['pass_oracle']), 'result_artifact': ref(result_path), 'raw': ref(command['evidence_ref'])}
            errors = v.m3_task_check_errors(ROOT, witness, name, check, tasks[name], rec, REV)
            witnesses.append({'exit': exit_id, 'task': name, 'check': check, 'errors': errors})
report = {'reviewed': REV, 'absent_prospective_integrations': sorted(absent), 'integrations': reports, 'dependency_order_errors': order_errors, 'available_exit_witnesses': witnesses}
(OUT / 'integrations.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'integrations_checked': len(reports), 'witnesses_checked': len(witnesses), 'absent': sorted(absent), 'dependency_order_errors': order_errors}))
assert not any(r['errors'] for r in reports + witnesses)
assert not order_errors
