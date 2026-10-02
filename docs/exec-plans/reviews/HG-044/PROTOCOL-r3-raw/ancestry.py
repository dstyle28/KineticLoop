"""Independently check available real prerequisite chains at the reviewed revision."""
import json
import subprocess
from pathlib import Path

import yaml

root = Path(__file__).resolve().parents[5]
revision = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
out = Path(__file__).parent

def git(*args):
    return subprocess.check_output(['git', *args], cwd=root)

def regular(path, rev):
    value = git('ls-tree', rev, '--', path).decode().split()
    return bool(value) and value[0] in ('100644', '100755')

def load(path, rev):
    assert regular(path, rev), (path, rev)
    return yaml.safe_load(git('show', rev + ':' + path))

tasks = {t['id']: t for t in load('KineticLoop_Harness_Backlog_v0.2.json', revision)['tasks']}
pending = [f'KL-{i:03d}' for i in list(range(19,30)) + list(range(75,80))] + ['KL-074']
records, missing, checks = {}, [], []
while pending:
    task = pending.pop()
    if task in records or task in missing:
        continue
    path = f'docs/exec-plans/integrations/{task}.json'
    if not regular(path, revision):
        missing.append(task)
        continue
    record = load(path, revision)
    assert record['integration_status'] == 'MERGED'
    assert record['task_identity'] == 'harness-backlog-v0.2/' + task
    records[task] = record
    pending.extend(tasks[task]['depends_on'])
for task, record in sorted(records.items()):
    reviewed = record['reviewed_head_sha']
    candidates = [f'docs/exec-plans/completed/{task}_RESULT.{ext}' for ext in ('json','yaml')]
    candidates = [p for p in candidates if regular(p, reviewed)]
    assert len(candidates) == 1
    result = load(candidates[0], reviewed)
    for dep in tasks[task]['depends_on']:
        assert dep in records, (dep, task)
        for key in ('base_commit', 'tested_commit'):
            status = subprocess.run(['git', 'merge-base', '--is-ancestor',
                                     records[dep]['merge_commit'], result[key]], cwd=root).returncode
            assert status == 0, (dep, task, key)
            checks.append({'dependency': dep, 'consumer': task, 'consumer_field': key,
                           'dependency_merge': records[dep]['merge_commit'],
                           'consumer_commit': result[key], 'exit_code': status})
assert set(missing) == {'KL-028', 'KL-029'}, missing
report = {'reviewed_head_sha': revision, 'status': 'PASS', 'exit_code': 0,
          'missing_real_integrations': missing, 'closure_available': False,
          'available_recursive_records': sorted(records), 'ancestry_checks': checks}
(out / 'ancestry.json').write_text(json.dumps(report, indent=2) + '\n')
print('PROTOCOL_R3_ANCESTRY_PASS: ' + str(len(checks)) + ' real ancestry checks; KL028/KL029 integration records missing prevents closure')
