"""Read-only merged authority/fixture audit, before the first KL019 lifecycle call."""
import hashlib
import json
import subprocess
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[4]
def git(*args):
    return subprocess.check_output(['git', *args],cwd=ROOT,text=True).strip()
def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
def ancestor(revision):
    subprocess.run(['git','merge-base','--is-ancestor',revision,'HEAD'],cwd=ROOT,check=True)
index=json.loads((ROOT/'CURRENT_DOCUMENT_INDEX.json').read_text())
for row in index['documents']+index['machine_readable']:
    assert sha(row['path'])==row['sha256'],row['path']
rows=[]
for n in ('015','017','020','021','022','023','024','025'):
    task='KL-'+n
    result=yaml.safe_load((ROOT/f'docs/exec-plans/completed/{task}_RESULT.yaml').read_text())
    integration=json.loads((ROOT/f'docs/exec-plans/integrations/{task}.json').read_text())
    assert result['task_status']==result['task_checks_status']=='PASS'
    assert integration['integration_status']=='MERGED';ancestor(integration['merge_commit'])
    reviews=[]
    for path in (ROOT/f'docs/exec-plans/reviews/{task}').glob('*.json'):
        review=json.loads(path.read_text());assert review['status']=='PASS';ancestor(review['reviewed_head_sha'])
        reviews.append({'path':str(path.relative_to(ROOT)), 'sha256':sha(path.relative_to(ROOT)),
                        'reviewed_head_sha':review['reviewed_head_sha'],'type':review['review_type']})
    assert {'GENERAL','PROTOCOL','DB_CONCURRENCY'}<={r['type'] for r in reviews}
    rows.append({'task_identity':result['task_identity'],'result_sha256':sha(f'docs/exec-plans/completed/{task}_RESULT.yaml'),'integration':integration,'reviews':reviews})
m2=json.loads((ROOT/'docs/exec-plans/milestones/M2.json').read_text());assert m2['closure_status']=='PASS';ancestor(m2['evaluated_commit'])
paths=['tests/db/test_transaction_interfaces.py','tests/db/test_planning.py','tests/db/test_call_ledger.py','tests/db/test_migrations.py','tests/db/test_safety_registry.py','src/kineticloop/db/lifecycle.py','compose.yaml']
audit={'base_commit':git('rev-parse','HEAD'),'prerequisites':rows,'M2_evaluated_commit':m2['evaluated_commit'],
       'fixture_hashes':{p:sha(p) for p in paths},
       'nested_inventory':{
        'exec':'database_urls -> validated execution_namespace -> DatabaseLifecycle -> bootstrap_two_phase -> reset/provision_external_roles/ownership/baseline/DDL_guard/head; trusted upstream inputs only -> destroy selected exec',
        'tx':'unchanged module database_urls -> exact env overrides -> bootstrap_two_phase -> _SAFETY.seed -> _seed_transaction_rows; explicit _reset_kl022_fixture truncates/seed ONLY selected tx URL -> destroy selected tx',
        'plan':'database_urls -> _planning_namespace -> bootstrap_two_phase -> trusted synthetic prerequisite SQL/registration -> services -> destroy selected plan',
        'ledger':'database_urls -> _ledger_namespace -> bootstrap_two_phase -> trusted synthetic prerequisite SQL/registration -> services -> destroy selected ledger',
        'unit':'unit files have no real lifecycle calls; instrumented isolation proof is separate from required unchanged PG regressions'},
       'broader_db':'unchanged hosted ubuntu-latest CI only', 'requirements':'I01/I02/I04/I07/A03@DC NOT_RUN'}
(ROOT/'docs/exec-plans/evidence/KL-019/entry-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
print('ENTRY_AUDIT_PASS', len(rows), audit['fixture_hashes'])
