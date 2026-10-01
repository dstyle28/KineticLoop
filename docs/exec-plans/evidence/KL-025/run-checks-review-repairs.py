"""Sequential exact KL025 checks; no full foreign-fixture local database suite."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import time
ROOT = Path(__file__).resolve().parents[4]
HEAD = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
assert len(HEAD) == 40
EV = ROOT / 'docs/exec-plans/evidence/KL-025'
packet = (ROOT / 'docs/exec-plans/active/KL-025.md').read_text()
contracts = json.loads(re.search(r'```json\n(.*?)\n```', packet, re.S).group(1))['check_contracts']
contracts.sort(key=lambda c: c['check_id'] != 'planning_fixture_namespace_isolation_pu')
env = dict(os.environ)
env.update(PATH='/private/tmp/kl001-bootstrap/bin:/opt/homebrew/bin:/usr/local/bin:'+env.get('PATH',''),
           UV_PROJECT_ENVIRONMENT='/private/tmp/kl017-venv',UV_NO_SYNC='1',
           UV_CACHE_DIR='/private/tmp/kl025-uv-cache',PYTHONPATH=str(ROOT / 'src'))
checks=[]
for c in contracts + [{'check_id':'full_unit_regressions','command':'uv run kl test-unit'},
                      {'check_id':'full_harness_regressions','command':'uv run kl test-harness'}]:
    identifier, command = c['check_id'], c['command']
    log = EV / f'{identifier}-{HEAD[:7]}.log'
    start=time.monotonic()
    with log.open('w') as f:
        f.write(f'tested_commit: {HEAD}\ncommand: {command}\nworktree: {ROOT}\n')
        f.flush()
        result=subprocess.run(command, cwd=ROOT, env=env, shell=True, executable='/bin/bash',
                              stdout=f, stderr=subprocess.STDOUT)
        f.write(f'\nexit_code: {result.returncode}\n')
    row={'check_id':identifier,'command':command,'result':'PASS' if result.returncode==0 else 'FAIL',
         'exit_code':result.returncode,'evidence_ref':str(log.relative_to(ROOT)),
         'elapsed_seconds':round(time.monotonic()-start,2),'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    checks.append(row)
    (EV / f'checks-{HEAD[:7]}.json').write_text(json.dumps({'tested_commit':HEAD,'checks':checks},indent=2)+'\n')
    print(identifier,row['result'],row['elapsed_seconds'],flush=True)
    if result.returncode:
        print(log.read_text()[-7000:],flush=True)
        raise SystemExit(result.returncode)
# Record actual task namespaces and exact protected adaptation, not merely labels.
import sys
sys.path.insert(0, str(ROOT / "src"))
from kineticloop.db.lifecycle import DatabaseNamespace
from kineticloop.persistence import transactions
suffix=DatabaseNamespace.for_worktree(ROOT).project_name[-12:]
assert Path(transactions.__file__).resolve().is_relative_to(ROOT)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==HEAD
(EV / f'namespaces-and-source-{HEAD[:7]}.json').write_text(json.dumps({
 'tested_commit':HEAD,'runtime_source':transactions.__file__,
 'ledger_database':'kineticloop_kl025_'+HEAD[:7],'ledger_compose':'kineticloop-kl025-'+HEAD[:7],
 'planning_database':f'kineticloop_kl025_plan_{HEAD[:7]}_{suffix}',
 'planning_compose':f'kineticloop-kl025-plan-{HEAD[:7]}-{suffix}',
 'owner_regression_database':'kineticloop_kl025_reg_'+HEAD[:7],
 'owner_regression_compose':'kineticloop-kl025-reg-'+HEAD[:7],
 'planning_fixture_sha256':hashlib.sha256((ROOT/'tests/db/test_planning.py').read_bytes()).hexdigest(),
 'full_db_suite':'UNCHANGED_HOSTED_CI_ONLY_NOT_RUN_LOCALLY',
 'runtime_env':{'UV_PROJECT_ENVIRONMENT':env['UV_PROJECT_ENVIRONMENT'],'UV_NO_SYNC':'1','PYTHONPATH':env['PYTHONPATH']}
},indent=2)+'\n')
