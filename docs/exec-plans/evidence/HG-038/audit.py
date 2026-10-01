"""HG038 append-only scope, new identity and immutable-authority audit."""
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path.cwd()
HERE = ROOT / 'docs/exec-plans/evidence/HG-038'
BASE = (HERE / 'protected-base.txt').read_text().strip()
HEAD = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()


def git(*args):
    return subprocess.check_output(['git', *args])


print('base_commit='+BASE+'\ntested_commit='+HEAD)
protected = ['src','tests/db','tests/unit','migrations','.github','compose.yaml','FROZEN_BASELINE.json',
 '05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
 'CURRENT_REQUIREMENT_SET.json','KineticLoop_Acceptance_Spec_v1.2.2.json','KineticLoop_Integration_Acceptance_v0.1.json',
 'KineticLoop_Evidence_Manifest_v0.1.json','docs/exec-plans/completed','docs/exec-plans/milestones','docs/exec-plans/reviews','docs/contracts']
for path in protected:
    assert git('diff','--name-only',BASE,HEAD,'--',path) == b'', path
for path in git('diff','--name-only',BASE,HEAD,'--','docs/exec-plans/evidence').decode().splitlines():
    assert path.startswith('docs/exec-plans/evidence/HG-038/'), path
names = {'KL-026','KL-027','KL-075','KL-076','KL-077'}
for p in ['KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json']:
    old = json.loads(git('show',BASE+':'+p)); new = json.loads((ROOT/p).read_text())
    old_tasks = {t['id']:t for t in old['tasks']}
    new_tasks = {t['id']:t for t in new['tasks']}
    assert set(new_tasks)-set(old_tasks) == {'KL-075','KL-076','KL-077'}
    assert set(old_tasks)-set(new_tasks) == set()
    for name,t in old_tasks.items():
        if name not in names:
            assert new_tasks[name] == t, (p,name)
    assert {k:v for k,v in old.items() if k not in ['tasks','task_count','active_task_count']} == {k:v for k,v in new.items() if k not in ['tasks','task_count','active_task_count']}
spec=importlib.util.spec_from_file_location('hg038_audit_validator',ROOT/'tools/harness/validate_harness.py')
v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
tasks={t['id']:t for t in json.loads((ROOT/v.BACKLOG).read_text())['tasks']}
for name in names:
    t=tasks[name]
    assert t['status']=='NOT_STARTED' and t['evidence_refs']==[]
    assert v.m3_next_wave_definition_errors(t)==[]
    assert v.packet_errors(t,(ROOT/f'docs/exec-plans/active/{name}.md').read_text())==[]
    for p in v.result_paths(name)+[f'docs/exec-plans/integrations/{name}.json',f'docs/exec-plans/reviews/{name}',f'docs/exec-plans/evidence/{name}']:
        assert not (ROOT/p).exists(), p
integration_paths=git('diff','--name-only',BASE,HEAD,'--','docs/exec-plans/integrations').decode().splitlines()
assert set(integration_paths) <= {f'docs/exec-plans/integrations/{n}.json' for n in ['KL-019','KL-047','KL-074']}
for path in integration_paths:
    assert subprocess.run(['git','cat-file','-e',BASE+':'+path],capture_output=True).returncode != 0
    record=json.loads((ROOT/path).read_text())
    subprocess.run(['git','merge-base','--is-ancestor',record['merge_commit'],BASE],check=True)
    print('ACTUAL_MERGE_CHAIN',record)
assert len(names)==5
print('PASS exact tests-only 026/027; three unused NOT_STARTED owner prerequisites; independent DB isolation; completed definitions/results/evidence/frozen/product unchanged')
print('PASS I04 DC != WF; no product/release/M3 PASS or public command extension')
print('HG038_AUDIT_PASS')
