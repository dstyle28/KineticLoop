"""Check every available transitive result via the M3 dependency helper."""
import importlib.util
import json
from pathlib import Path

root = Path.cwd()
out = root / 'docs/exec-plans/reviews/HG-044/SECURITY_DATA_BOUNDARY-r5-raw'
revision = '027bc2368e36e28aa9956489cb57af297882d671'
spec = importlib.util.spec_from_file_location('v', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
audit = json.loads((out / 'audit.json').read_text())
records = {name: v.load_artifact_at_revision(root, f'docs/exec-plans/integrations/{name}.json', revision)
           for name in audit['integration_closure']['valid_existing']}
tasks = {t['id']: t for t in v.load_artifact_at_revision(root, v.BACKLOG, revision)['tasks']}
errors = v.m3_dependency_order_errors(root, records, tasks)
assert not errors
assert 'm3_dependency_order_errors(root, records, evaluated_tasks)' in (root / 'tools/harness/validate_harness.py').read_text()
report = dict(reviewed_head_sha=revision, status='PASS', errors=errors, checked_tasks=sorted(records),
              assessment='The complete recursive records set is checked for exactly one regular reviewed result before result parsing; this includes tasks without mapped witnesses and M1 support/dependencies.')
(out / 'reviewed-result-guard.json').write_text(json.dumps(report, indent=2) + '\n')
print('REVIEWED_RESULT_GUARD_PASS', len(records))
