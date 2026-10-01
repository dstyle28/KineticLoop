"""Append only missing integration facts, binding actual normally merged chains."""
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
HERE = ROOT / 'docs/exec-plans/evidence/HG-040'


def git(*args):
    return subprocess.check_output(['git', *args])


base = (HERE / 'protected-base.txt').read_text().strip()
backlog = {t['id']: t for t in json.loads((ROOT / 'KineticLoop_Harness_Backlog_v0.2.json').read_text())['tasks']}
facts = []
for name, number in [('KL-075', 74)]:
    path = ROOT / f'docs/exec-plans/integrations/{name}.json'
    if path.exists():
        facts.append({'id': name, 'disposition': 'EXISTING_UNCHANGED', 'record': json.loads(path.read_text())})
        continue
    pr = json.loads((HERE / 'KL075-normal-merge.json').read_text())
    assert pr['state'] == 'MERGED' and not pr['isDraft']
    merge = pr['mergeCommit']['oid']
    parents = git('rev-list', '--parents', '-n', '1', merge).decode().split()
    assert len(parents) == 3, 'normal two-parent merge required'
    suffix = parents[2]
    assert pr['headRefOid'] == suffix
    subprocess.run(['git', 'merge-base', '--is-ancestor', merge, base], check=True)
    reviews = [json.loads(git('show', base + f':docs/exec-plans/reviews/{name}/{typ}.json')) for typ in backlog[name]['review_requirements']]
    assert all(r['status'] == 'PASS' and r['task_identity'] == backlog[name]['task_identity'] for r in reviews)
    assert len({r['reviewed_head_sha'] for r in reviews}) == 1
    reviewed = reviews[0]['reviewed_head_sha']
    result_path = f'docs/exec-plans/completed/{name}_RESULT.yaml'
    result_commit = git('log', '-1', '--format=%H', reviewed, '--', result_path).decode().strip()
    result = yaml.safe_load(git('show', result_commit + ':' + result_path))
    assert result['task_status'] == result['task_checks_status'] == 'PASS'
    assert result['task_identity'] == backlog[name]['task_identity']
    raw = git('show', result_commit + ':' + result_path)
    assert raw == git('show', reviewed + ':' + result_path) == git('show', base + ':' + result_path)
    for earlier,later in [(result['base_commit'],result['tested_commit']),(result['tested_commit'],result_commit),(result_commit,reviewed),(reviewed,suffix)]:
        subprocess.run(['git', 'merge-base', '--is-ancestor', earlier, later], check=True)
    for commit in git('rev-list', reviewed + '..' + suffix).decode().splitlines():
        assert len(git('rev-list','--parents','-n','1',commit).decode().split()) == 2
        paths = git('diff-tree','--no-commit-id','--name-only','-r',commit).decode().splitlines()
        assert paths and all(p.startswith(f'docs/exec-plans/reviews/{name}/') for p in paths)
    assert git('rev-parse', suffix + '^{tree}') == git('rev-parse', merge + '^{tree}')
    record = {'task_identity': backlog[name]['task_identity'], 'display_task_id': name,
        'result_commit': result_commit, 'reviewed_head_sha': reviewed,
        'review_record_commit': suffix, 'merge_commit': merge, 'integration_status': 'MERGED'}
    # Prospective chain only: historical raw review logs are absent at reviewed SHA.
    # Do not append an invalid integration record or weaken the existing validator.
    facts.append({'id':name, 'disposition':'DEFERRED_REVIEW_EVIDENCE_NOT_AT_REVIEWED_SHA', 'record':record,
        'result_sha256':hashlib.sha256(raw).hexdigest(), 'tested_commit':result['tested_commit'],
        'merge_tree':git('rev-parse', merge+'^{tree}').decode().strip(),
        'review_types':[r['review_type'] for r in reviews]})
(HERE / 'integration-provenance.json').write_text(json.dumps({'protected_base':base,'facts':facts}, indent=2)+'\n')
print('HG040_ACTUAL_INTEGRATION_CHAINS_PASS', [f['id'] for f in facts])
