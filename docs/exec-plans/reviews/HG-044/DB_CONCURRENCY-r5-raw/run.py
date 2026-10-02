import json
import os
import subprocess
from pathlib import Path
root=Path.cwd()
out=root/'docs/exec-plans/reviews/HG-044/DB_CONCURRENCY-r5-raw'
env=dict(os.environ,PYTHONPATH='src',PYTHONDONTWRITEBYTECODE='1',TMPDIR='/private/tmp')
commands=[
 ['audit',['/private/tmp/hg044-venv/bin/python',str(out/'audit.py')]],
 ['bounded-pytest',['/private/tmp/hg044-venv/bin/python','-m','pytest','-q','-p','no:cacheprovider',
 '--basetemp=/private/tmp/hg044d5','--junitxml='+str(out/'bounded.xml'),
 'tests/harness/test_m3_milestone_closure.py','-k',
 'prerequisite_merge_must_precede or each_multiselect_suite or genuine_pytest_parameter or zero_skip_xfail or governance_scope or existing_schema or m3_reader or m3_symlink or actual_closure_record or ratified_plan or integrated_regression_fails_closed']]
]
rows=[]
for label,cmd in commands:
    run=subprocess.run(cmd,env=env,cwd=root,capture_output=True)
    (out/(label+'.stdout')).write_bytes(run.stdout)
    (out/(label+'.stderr')).write_bytes(run.stderr)
    rows.append({'label':label,'command':cmd,'exit_code':run.returncode})
    (out/'commands.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(label,run.returncode,run.stdout.decode()[-400:],run.stderr.decode()[-500:],flush=True)
    if run.returncode: raise SystemExit(run.returncode)
