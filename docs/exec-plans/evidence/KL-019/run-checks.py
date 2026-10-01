"""Run exact KL019 packet checks sequentially, preserving revision-bound raw logs."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'docs/exec-plans/evidence/KL-019'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
sha = git('rev-parse', 'HEAD')
short = git('rev-parse', '--short', 'HEAD')
assert re.fullmatch('[0-9a-f]{7,12}',short)
worktree_digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
packet = (ROOT / 'docs/exec-plans/active/KL-019.md').read_text()
contracts = json.loads(re.search(r'```json\n(.*?)\n```',packet,re.S).group(1))['check_contracts']
assert len(contracts) == 20
# Pure inventory/namespace proof MUST precede every real local lifecycle call.
contracts.sort(key=lambda c: c['check_id'] != 'execution_fixture_namespace_isolation_pu')
env = dict(os.environ, PYTHONPATH=str(ROOT/'src'))
registry = OUT / f'checks-{short}.json'
assert not registry.exists(), 'Never overwrite a prior check registry'
records=[]
for check in contracts:
    assert git('rev-parse','HEAD') == sha
    path=OUT/f"{check['check_id']}-{short}.log"
    assert not path.exists(), 'Never overwrite prior raw evidence'
    started=time.time()
    with path.open('w') as output:
        output.write(f'TASK_IDENTITY=harness-backlog-v0.2/KL-019\nTESTED_COMMIT={sha}\nWORKTREE={ROOT.resolve()}\nWORKTREE_DIGEST={worktree_digest}\nCOMMAND={check["command"]}\n')
        output.flush()
        process=subprocess.run(check['command'],shell=True,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT)
        output.write(f'\nEXIT_CODE={process.returncode}\n')
    raw=path.read_bytes()
    record={**check,'tested_commit':sha,'exit_code':process.returncode,'result':'PASS' if process.returncode==0 else 'FAIL',
            'evidence_ref':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(raw).hexdigest(),'elapsed_seconds':round(time.time()-started,3)}
    records.append(record)
    registry.write_text(json.dumps({'tested_commit':sha,'worktree':str(ROOT.resolve()),'worktree_digest':worktree_digest,
        'namespaces':{label:{'compose_project':f'kineticloop-kl019-{label}-{short}-{worktree_digest}',
        'database':f'kineticloop_kl019_{label}_{short}_{worktree_digest}'} for label in ('exec','tx','plan','ledger')},'checks':records},indent=2)+'\n')
    print(check['check_id'],record['result'],record['elapsed_seconds'],flush=True)
    if process.returncode:
        print(raw.decode()[-6000:],flush=True)
        raise SystemExit(process.returncode)
print('EXACT_20_CHECKS_PASS',sha,flush=True)
