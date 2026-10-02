import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
OUT=Path(__file__).parent
HEAD='4bc0b0122245d54649e3f3d03a9acce7d4c6df2a'
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT/'src'),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
commands=[
    [sys.executable,str(OUT/'probe.py')],
    [sys.executable,'-m','pytest','-q','-p','no:cacheprovider','--basetemp','/private/tmp/hg044-protocol-r4-pytest',
     'tests/harness/test_m3_milestone_closure.py','-k',
     'each_multiselect or genuine_pytest_parameter or integrated_regression_fails_closed or legacy_m1_m2 or deferred_layers or schema_rejects_frozen or prerequisite_merge or existing_schema_branches'],
    ['git','diff','--check','fa729ca4bcca0f2c2e7a2aa0601890d1356b8842',HEAD,'--','.',':(exclude)docs/exec-plans/reviews/HG-044/**'],
]
records=[]
for i,command in enumerate(commands):
    start=time.time()
    p=subprocess.run(command,cwd=ROOT,env=env,capture_output=True)
    raw=p.stdout+p.stderr
    path=OUT/f'command-{i}.log'
    path.write_bytes(raw)
    records.append({'command':command,'reviewed_head_sha':HEAD,'observed_head_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
                    'exit_code':p.returncode,'stdout_stderr_ref':str(path.relative_to(ROOT)),
                    'sha256':hashlib.sha256(raw).hexdigest(),'duration_seconds':round(time.time()-start,3)})
    (OUT/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps(records[-1]),flush=True)
    if p.returncode:
        print(raw.decode(),flush=True)
        raise SystemExit(p.returncode)
