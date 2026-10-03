"""Committed HG051 exact scope, frozen, authority, inventory and prerequisite audit."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
BASE = 'b877db0edd2e4550d6ea81750656112fb7f2e223'
SPEC = importlib.util.spec_from_file_location('hg051_scope_validator', ROOT / 'tools/harness/validate_harness.py')
assert SPEC and SPEC.loader
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def main():
    head = git('rev-parse', 'HEAD')
    changed = git('diff', '--no-renames', '--name-only', BASE, head).splitlines()
    assert all(v.matches(p, v.governance_allowed_patterns('HG-051')) for p in changed)
    frozen = json.loads(git('show', BASE + ':FROZEN_BASELINE.json'))
    protected = {x['path'] for x in frozen['files']} | {'FROZEN_BASELINE.json'}
    assert not set(changed) & protected
    for path in protected:
        assert git('rev-parse', BASE + ':' + path) == git('rev-parse', head + ':' + path)
    old = json.loads(git('show', BASE + ':' + v.BACKLOG))
    new = json.loads((ROOT / v.BACKLOG).read_bytes())
    before, after = {t['id']: t for t in old['tasks']}, {t['id']: t for t in new['tasks']}
    assert before.keys() == after.keys()
    for identity in before:
        if identity != 'KL-080':
            assert before[identity] == after[identity]
    expected = dict(before['KL-080'])
    expected['definition_of_done'] = after['KL-080']['definition_of_done']
    assert after['KL-080'] == expected
    assert after['KL-080']['definition_of_done'].startswith(before['KL-080']['definition_of_done'])
    assert not v.source_decision_definition_errors(after['KL-080'])
    assert not v.packet_errors(after['KL-080'], (ROOT / 'docs/exec-plans/active/KL-080.md').read_text())
    prior_artifacts = git('ls-tree', '-r', '--name-only', BASE, '--',
                          'docs/exec-plans/completed', 'docs/exec-plans/reviews',
                          'docs/exec-plans/evidence').splitlines()
    for path in prior_artifacts:
        assert git('rev-parse', BASE + ':' + path) == git('rev-parse', head + ':' + path)
    prerequisites = []
    for task_id in after['KL-080']['depends_on']:
        result_path = next(p for p in v.result_paths(task_id) if (ROOT / p).exists())
        result = yaml.safe_load((ROOT / result_path).read_bytes())
        assert result['task_identity'] == 'harness-backlog-v0.2/' + task_id
        assert result['task_status'] == result['task_checks_status'] == 'PASS'
        record = json.loads((ROOT / f'docs/exec-plans/integrations/{task_id}.json').read_bytes())
        assert record['integration_status'] == 'MERGED'
        git('merge-base', '--is-ancestor', record['merge_commit'], BASE)
        for review_type in before[task_id]['review_requirements']:
            review = json.loads((ROOT / f'docs/exec-plans/reviews/{task_id}/{review_type}.json').read_bytes())
            assert review['status'] == 'PASS' and review['reviewed_head_sha'] == record['reviewed_head_sha']
        prerequisites.append(dict(task_identity=result['task_identity'], merge_commit=record['merge_commit']))
    assert (v.compact_evidence.PLAIN_LIMIT, v.compact_evidence.STORED_LIMIT,
            v.compact_evidence.RAW_LIMIT, v.compact_evidence.TOTAL_LIMIT) == (
                262144, 8388608, 67108864, 16777216)
    print(json.dumps(dict(base_commit=BASE, tested_commit=head, status='PASS',
                         changed_paths=changed, preserved_historical_artifacts=len(prior_artifacts),
                         prerequisites=prerequisites, kl080_migration_applied=False,
                         frozen_impact='NONE', product_m3_release='NOT_RUN'), indent=2))


if __name__ == '__main__':
    main()
