import subprocess,json,hashlib
from pathlib import Path
r=Path.cwd();base='26906bd7f4444914c228e98377f2b164fee0dd5d'
def git(*a):return subprocess.check_output(['git',*a])
paths=git('diff','--name-only',base,'HEAD').decode().splitlines()
allowed={'.github/workflows/ci.yml','.github/workflows/db.yml','CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','docs/harness/LOCAL_DB_CI.md','docs/harness/MERGE_GATE.md','docs/harness/M3_CLOSURE_CONTRACT.md','tools/harness/db_ci.py','tools/harness/db_ci_pytest.py','tools/harness/local_db/Dockerfile','tools/harness/local_db/entrypoint.sh','tools/harness/validate_harness.py','tests/harness/test_local_db_ci.py','tests/db/test_startup_readiness.py','tests/db/test_workflow.py','docs/harness/HARNESS_GOVERNANCE_CONTRACT.md'}
for p in paths:assert p in allowed or p.startswith('docs/exec-plans/evidence/HG-046/') or p.startswith('docs/exec-plans/reviews/HG-046/') or p=='docs/exec-plans/governance/HG-046.yaml',p
frozen=json.loads(git('show',base+':FROZEN_BASELINE.json'))
for p in ['FROZEN_BASELINE.json']+[f['path'] for f in frozen['files']]:assert git('show',base+':'+p)==(r/p).read_bytes(),p
for p in ['CURRENT_REQUIREMENT_SET.json','KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json','.github/workflows/kl074-readiness.yml']:
 assert git('show',base+':'+p)==(r/p).read_bytes(),p
assert not any(p.startswith(('src/','tests/db/','tests/unit/','docs/exec-plans/completed/','migrations/')) for p in paths if p not in ('tests/db/test_startup_readiness.py','tests/db/test_workflow.py'))
before=git('show',base+':tests/db/test_startup_readiness.py').decode();after=(r/'tests/db/test_startup_readiness.py').read_text()
assert before.split('    for path, expected in {')[0] == after.split('    # HG-046 prospectively')[0]
assert before.split('def test_probe_exact_environment')[1] == after.split('def test_probe_exact_environment')[1]
print(json.dumps({'tested_commit':git('rev-parse','HEAD').decode().strip(),'base_commit':base,'status':'PASS','changed_paths':paths,'frozen_unchanged':True,'runtime_and_db_fixtures_unchanged':True,'task_requirement_status_unchanged':True,'kl074_workflow_unchanged':True},indent=2))
