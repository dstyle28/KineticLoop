"""Read-only protected-state and projection audit for HG030."""
import importlib.util
import json
import subprocess
from pathlib import Path

root = Path.cwd()
base = '8df9d8851cdc8f68e1f6429149b420604d6aa1b5'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
print('base_commit=' + base)
print('tested_commit=' + head)
for path in ['FROZEN_BASELINE.json', '05_KineticLoop_Protocol_v1.2_FROZEN.md',
             '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'src', 'migrations',
             'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Acceptance_Spec_v1.2.2.json',
             'KineticLoop_Integration_Acceptance_v0.1.json', 'KineticLoop_Evidence_Manifest_v0.1.json',
             'docs/exec-plans/completed', 'docs/exec-plans/integrations',
             'docs/exec-plans/milestones']:
    subprocess.run(['git', 'diff', '--exit-code', base, head, '--', path], check=True)
print('PASS protected frozen/product/migration/completed/requirement state unchanged')
for file in ['KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Harness_Traceability_v0.3.json']:
    old = json.loads(subprocess.check_output(['git', 'show', base + ':' + file]))
    new = json.loads((root / file).read_text())
    assert {k: v for k, v in old.items() if k != 'tasks'} == {
        k: v for k, v in new.items() if k != 'tasks'}
    assert [t for t in old['tasks'] if t['id'] != 'KL-025'] == [
        t for t in new['tasks'] if t['id'] != 'KL-025']
print('PASS all unrelated task definitions byte-equivalent as parsed; task counts unchanged')
allowed = {'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
           'KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Harness_Traceability_v0.3.json',
           'docs/exec-plans/active/KL-025.md', 'tools/harness/validate_harness.py',
           'tests/harness/test_call_ledger_scope.py'}
changed = set(subprocess.check_output(['git', 'diff', '--name-only', base, head], text=True).splitlines())
content = {p for p in changed if not p.startswith(('docs/exec-plans/evidence/HG-030/',
                                                          'docs/exec-plans/governance/HG-030.'))}
assert content == allowed, changed
assert subprocess.run(['git', 'cat-file', '-e', base + ':docs/exec-plans/governance/HG-030.yaml'],
                      capture_output=True).returncode != 0
for name in ['KL-024', 'KL-025']:
    for ext in ['yaml', 'json']:
        assert not (root / f'docs/exec-plans/completed/{name}_RESULT.{ext}').exists()
print('PASS HG030 unused; KL024/KL025 have no result at tested base; no prerequisite PASS assumed')
spec = importlib.util.spec_from_file_location('validator', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
task = next(t for t in json.loads((root / v.BACKLOG).read_text())['tasks'] if t['id'] == 'KL-025')
assert task['status'] == 'NOT_STARTED'
assert task['depends_on'] == ['KL-024']
assert v.ledger_definition_errors(task) == []
assert v.packet_errors(task, (root / 'docs/exec-plans/active/KL-025.md').read_text()) == []
trace = json.loads((root / v.TRACEABILITY).read_text())['tasks']
assert next(t for t in trace if t['id'] == 'KL-025') == v.traceability_projection(task)
print('PASS exact KL025 packet/backlog/traceability; hard dependency and merged API verification preserved')
