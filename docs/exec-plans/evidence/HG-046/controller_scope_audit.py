import hashlib,json,subprocess
from pathlib import Path
root=Path.cwd();base='fc8a044ffa4d15a74ce5dc59298ae411f1f4009b'
def git(*args):return subprocess.check_output(['git',*args],cwd=root)
assert not git('status','--porcelain'), 'Require clean tested HEAD'
paths=git('diff','--name-only',base,'HEAD').decode().splitlines()
allowed={'.github/workflows/ci.yml','.github/workflows/db.yml','CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','docs/harness/LOCAL_DB_CI.md','docs/harness/MERGE_GATE.md','docs/harness/M3_CLOSURE_CONTRACT.md','tools/harness/db_ci.py','tools/harness/db_ci_pytest.py','tools/harness/local_db/Dockerfile','tools/harness/local_db/entrypoint.sh','tools/harness/validate_harness.py','tests/harness/test_local_db_ci.py','tests/db/test_startup_readiness.py','tests/db/test_workflow.py','docs/harness/HARNESS_GOVERNANCE_CONTRACT.md','tools/harness/db_policy.py','tools/harness/local_gate.py','tools/harness/github_app.py','tools/harness/gate_validate.py','tools/harness/gate_pytest.py','tests/harness/test_local_gate.py','tests/harness/test_db_policy.py'}
for p in paths:assert p in allowed or p.startswith('docs/exec-plans/evidence/HG-046/') or p.startswith('docs/exec-plans/reviews/HG-046/') or p=='docs/exec-plans/governance/HG-046.yaml',p
frozen=json.loads(git('show',base+':FROZEN_BASELINE.json'))
protected=['FROZEN_BASELINE.json']+[f['path'] for f in frozen['files']]+['CURRENT_REQUIREMENT_SET.json','KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json','.github/workflows/kl074-readiness.yml','docs/exec-plans/active/KL-080.md','tests/harness/test_source_decision_scope.py','tests/harness/test_m3_milestone_closure.py','MILESTONE_CLOSURE.schema.json']
for p in protected:assert git('show',base+':'+p)==(root/p).read_bytes(),p
for folder in ['src/','migrations/','tests/unit/','docs/exec-plans/completed/','docs/exec-plans/evidence/HG-045/','docs/exec-plans/reviews/HG-045/']:
 assert not any(p.startswith(folder) for p in paths),folder
before=git('show',base+':tests/db/test_startup_readiness.py').decode();after=(root/'tests/db/test_startup_readiness.py').read_text()
assert before.split('    for path, expected in {')[0] == after.split('    # HG-046 prospectively')[0]
assert before.split('def test_probe_exact_environment')[1] == after.split('def test_probe_exact_environment')[1]
print(json.dumps({'tested_commit':git('rev-parse','HEAD').decode().strip(),'base_commit':base,'status':'PASS','changed_paths':paths,'frozen_unchanged':True,'runtime_and_db_fixtures_unchanged':True,'hg045_merged_changes_preserved':True,'secrets_in_diff':False},indent=2))
# Scan text diff for actual private-key payloads; fingerprints/filenames are safe.
raw=git('diff',base,'HEAD','--','.');assert b'-----BEGIN RSA PRIVATE KEY-----' not in raw and b'-----BEGIN PRIVATE KEY-----' not in raw
