import json
import os
import subprocess
import sys
import hashlib
from pathlib import Path
OUT=Path(__file__).parent
ROOT=OUT.parents[4]
name=sys.argv[1]
command=sys.argv[2:]
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT/'src')+':'+str(ROOT),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
env.pop('PYTEST_ADDOPTS',None)
completed=subprocess.run(command,cwd=ROOT,env=env,capture_output=True)
raw=completed.stdout+completed.stderr
(OUT/(name+'.log')).write_bytes(raw)
record=dict(command=command,reviewed_head_sha='4bc0b0122245d54649e3f3d03a9acce7d4c6df2a',exit_code=completed.returncode,raw_path=str((OUT/(name+'.log')).relative_to(ROOT)),raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw))
(OUT/(name+'-execution.json')).write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
sys.exit(completed.returncode)
