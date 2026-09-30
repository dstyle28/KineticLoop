"""Read-only protected-state, projection, source-evidence and migration-head audit."""
import ast
import importlib.util
import json
import subprocess
from pathlib import Path

import yaml

root = Path.cwd()
base = 'abc5af63bc580bb22e54baeb0af577448b57a75a'
source = '4543b563259f5170370a0624b4542d392e528c85'
folder = root / 'docs/exec-plans/evidence/HG-033'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
print('base_commit=' + base)
print('tested_commit=' + head)
print('KL024_source_commit=' + source)
for path in ['FROZEN_BASELINE.json', '05_KineticLoop_Protocol_v1.2_FROZEN.md',
             '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'src', 'migrations', 'tests/db',
             'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Acceptance_Spec_v1.2.2.json',
             'KineticLoop_Integration_Acceptance_v0.1.json', 'KineticLoop_Evidence_Manifest_v0.1.json',
             'docs/exec-plans/completed', 'docs/exec-plans/integrations',
             'docs/exec-plans/milestones', 'docs/exec-plans/governance/HG-032.yaml',
             'tests/harness/test_planning_fixture_scope.py', '.github']:
    subprocess.run(['git', 'diff', '--exit-code', base, head, '--', path], check=True)
for name in ['KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Harness_Traceability_v0.3.json']:
    old = json.loads(subprocess.check_output(['git', 'show', base + ':' + name]))
    new = json.loads((root / name).read_text())
    next(t for t in old['tasks'] if t['id'] == 'KL-024')['write_paths'].append(
        'tests/db/test_subject_scope.py')
    assert old == new
for path in ['docs/exec-plans/completed/KL-024_RESULT.yaml',
             'docs/exec-plans/completed/KL-024_RESULT.json',
             'docs/exec-plans/governance/HG-033.yaml']:
    assert subprocess.run(['git', 'cat-file', '-e', base + ':' + path],
                          capture_output=True).returncode != 0
print('PASS only KL024 exact write path added; checks/reviews/statuses/completed/Frozen/CI unchanged')
for local, original in {
    'KL024_RESULT.yaml': 'docs/exec-plans/completed/KL-024_RESULT.yaml',
    'KL024_failure.log': 'docs/exec-plans/evidence/KL-024/full_database_regressions-9282e12.log',
    'KL024_proposal.patch': 'docs/exec-plans/evidence/KL-024/proposed-subject-scope-head-rescope.patch',
    'KL024_candidate.py': 'docs/exec-plans/evidence/KL-024/candidate_subject_scope_head_probe.py',
    'KL024_candidate.log': 'docs/exec-plans/evidence/KL-024/candidate_subject_scope_head_probe-9282e12.log',
    'KL024_blocker.json': 'docs/exec-plans/evidence/KL-024/subject-scope-ci-blocker-9282e12.json',
}.items():
    assert (folder / local).read_bytes() == subprocess.check_output(['git', 'show', source + ':' + original])
result = yaml.safe_load((folder / 'KL024_RESULT.yaml').read_text())
assert result['task_status'] == 'BLOCKED' and result['task_checks_status'] == 'PASS'
assert result['tested_commit'] == '9282e124ad1ca30bf6b1a6149a17ac1c799500a1'
assert len(result['commands_run']) == 13 and all(c['result'] == 'PASS' for c in result['commands_run'])
for check in result['commands_run']:
    log = subprocess.check_output(['git', 'show', source + ':' + check['evidence_ref']]).decode()
    assert result['tested_commit'] in log and 'exit_code: 0' in log
failure = (folder / 'KL024_failure.log').read_text()
assert '1 failed, 237 passed' in failure
assert "assert ('e8c2f1a6b904',) == ('d4c1a9e7b203',)" in failure
candidate = (folder / 'KL024_candidate.log').read_text()
assert '1 passed' in candidate and 'CANDIDATE_PROOF_ONLY' in candidate
assert 'actual_CI_status: FAIL' in candidate
spec = importlib.util.spec_from_file_location('v', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
task = next(t for t in json.loads((root / v.BACKLOG).read_text())['tasks'] if t['id'] == 'KL-024')
assert v.wave_definition_errors(task) == []
assert v.packet_errors(task, (root / 'docs/exec-plans/active/KL-024.md').read_text()) == []
assert next(t for t in json.loads((root / v.TRACEABILITY).read_text())['tasks']
            if t['id'] == 'KL-024') == v.traceability_projection(task)
before = subprocess.check_output(['git', 'show', base + ':' + v.PLANNING_SUBJECT_SCOPE_PATH])
assert before == subprocess.check_output(['git', 'show', source + ':' + v.PLANNING_SUBJECT_SCOPE_PATH])
proposal = (folder / 'KL024_proposal.patch').read_text().splitlines()
removed = [line[1:] for line in proposal if line.startswith('-') and not line.startswith('---')]
added = [line[1:] for line in proposal if line.startswith('+') and not line.startswith('+++')]
assert len(removed) == len(added) == 2
assert all(new == old.replace('REVISION,', '_MIGRATIONS.HEAD_REVISION,')
           for old, new in zip(removed, added, strict=True))
after = before
for old, new in zip(removed, added, strict=True):
    after = after.replace(('\n' + old + '\n').encode(), ('\n' + new + '\n').encode())
assert v.planning_subject_scope_content_errors(before, after) == []
old_tree, new_tree = ast.parse(before), ast.parse(after)
changes = 0
class RestoreExpected(ast.NodeTransformer):
    def visit_Attribute(self, node):
        global changes
        if isinstance(node.value, ast.Name) and node.value.id == '_MIGRATIONS' and node.attr == 'HEAD_REVISION':
            changes += 1
            return ast.Name(id='REVISION', ctx=ast.Load())
        return self.generic_visit(node)
new_tree = RestoreExpected().visit(new_tree)
assert changes == 2 and ast.dump(old_tree) == ast.dump(new_tree)
print('PASS committed BLOCKED source, 13 exact PASS logs, failure and candidate verified by source SHA')
print('PASS proposal changes precisely two expressions; all other AST and bytes preserved')
# Read-only inventory: historical target expectations must stay historical; successful
# upgrades and failed transactional downgrades must expect current head.
paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', source, 'tests/db']).decode().splitlines()
for path in paths:
    if not path.endswith('.py'):
        continue
    text = subprocess.check_output(['git', 'show', source + ':' + path]).decode()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if 'version_num' in line:
            print(path + ':' + str(index + 1) + ': ' + ' '.join(lines[index:index + 4]).strip())
    if path != v.PLANNING_SUBJECT_SCOPE_PATH:
        assert '"d4c1a9e7b203"' not in text or path == 'tests/db/test_migrations.py'
print('PASS migration-head inventory: test_migrations current-head expectations already updated by KL024')
print('PASS no additional concrete same-cause omission; no scope expansion or database/task/product PASS')
