"""Read-only HG032 projection, protected-state and committed blocker audit."""
import importlib.util
import json
import subprocess
from pathlib import Path

import yaml

root = Path.cwd()
base = '7d24ee6dd0458e2971f26f9ac96d0465dae5ac22'
source = 'afc04894896de7ee2697dd1951ad4c3882b7d0c3'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
print('base_commit=' + base)
print('tested_commit=' + head)
print('KL024_source_commit=' + source)
for path in ['FROZEN_BASELINE.json', '05_KineticLoop_Protocol_v1.2_FROZEN.md',
             '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'src', 'migrations', 'tests/db',
             'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Acceptance_Spec_v1.2.2.json',
             'KineticLoop_Integration_Acceptance_v0.1.json', 'KineticLoop_Evidence_Manifest_v0.1.json',
             'docs/exec-plans/completed', 'docs/exec-plans/integrations',
             'docs/exec-plans/milestones']:
    subprocess.run(['git', 'diff', '--exit-code', base, head, '--', path], check=True)
print('PASS frozen/product/migration/database-test/completed/requirement/integration state unchanged')
for file in ['KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Harness_Traceability_v0.3.json']:
    old = json.loads(subprocess.check_output(['git', 'show', base + ':' + file]))
    new = json.loads((root / file).read_text())
    expected = json.loads(json.dumps(old))
    next(t for t in expected['tasks'] if t['id'] == 'KL-024')['write_paths'].append(
        'tests/db/test_transaction_interfaces.py')
    assert new == expected
print('PASS only KL024 exact write path added; all definitions/checks/statuses otherwise identical')
for ext in ['yaml', 'json']:
    for path in [f'docs/exec-plans/completed/KL-024_RESULT.{ext}',
                 f'docs/exec-plans/governance/HG-032.{ext}']:
        assert subprocess.run(['git', 'cat-file', '-e', base + ':' + path],
                              capture_output=True).returncode != 0
print('PASS protected base has no KL024 result; HG032 unused at protected base')
spec = importlib.util.spec_from_file_location('validator', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
task = next(t for t in json.loads((root / v.BACKLOG).read_text())['tasks'] if t['id'] == 'KL-024')
assert v.wave_definition_errors(task) == []
assert v.packet_errors(task, (root / 'docs/exec-plans/active/KL-024.md').read_text()) == []
trace = json.loads((root / v.TRACEABILITY).read_text())['tasks']
assert next(t for t in trace if t['id'] == 'KL-024') == v.traceability_projection(task)
folder = root / 'docs/exec-plans/evidence/HG-032'
for local, original in [
    ('KL024_RESULT.yaml', 'docs/exec-plans/completed/KL-024_RESULT.yaml'),
    ('KL024_failure.log', 'docs/exec-plans/evidence/KL-024/transaction_owner_regressions_pass-c414cd1.log'),
    ('KL024_proposal.patch', 'docs/exec-plans/evidence/KL-024/proposed-regression-fixture-rescope.patch'),
    ('KL024_migration.txt', 'migrations/versions/e8c2f1a6b904_planning_active_partition.py')]:
    assert (folder / local).read_bytes() == subprocess.check_output(['git', 'show', source + ':' + original])
result = yaml.safe_load((folder / 'KL024_RESULT.yaml').read_text())
assert result['task_status'] == 'BLOCKED'
assert result['tested_commit'] == 'c414cd12384a29e607e552c62e5e9199cdf401f9'
failed = [c for c in result['commands_run'] if c['result'] == 'FAIL']
assert len(failed) == 1 and failed[0]['check_id'] == 'transaction_owner_regressions_pass'
log = (folder / 'KL024_failure.log').read_text()
assert '1 failed, 57 passed' in log and 'uq_s27_active_partition' in log
assert 'test_reauthorize_requires_atomic_intent_success' in log
fixture = subprocess.check_output(['git', 'show', base + ':' + v.PLANNING_FIXTURE_PATH])
assert fixture == subprocess.check_output(['git', 'show', source + ':' + v.PLANNING_FIXTURE_PATH])
assert b"'PLAN','root-2',DATE '2026-09-27','RUNNING'" in fixture
assert b"DATE '2026-09-28'" not in fixture
proposal = (folder / 'KL024_proposal.patch').read_text().splitlines()
removed = [line[1:] for line in proposal if line.startswith('-') and not line.startswith('---')]
added = [line[1:] for line in proposal if line.startswith('+') and not line.startswith('+++')]
assert len(removed) == len(added) == 1
assert added[0] == removed[0].replace('2026-09-27', '2026-09-28')
assert v.planning_fixture_content_errors(fixture, fixture.replace(
    removed[0].encode(), added[0].encode())) == []
migration = (folder / 'KL024_migration.txt').read_text()
assert 'CREATE UNIQUE INDEX uq_s27_active_partition' in migration
assert "WHERE status IN ('ADMITTED','PENDING','RUNNING')" in migration
print('PASS exact committed BLOCKED result/1-failed-57-passed log/proposal verified against source SHA')
print('PASS unused 2026-09-28 preserves head-day mismatch from 2026-09-26 and S27 uniqueness')
print('PASS fixture is unchanged here; no database execution or KL024 PASS claimed in governance')
