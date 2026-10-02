"""Capture final checks at a committed SHA, retaining raw output without overwrite."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

root=Path.cwd();here=root/'docs/exec-plans/evidence/HG-044'
base='9268fc8dd8c071c02dc5c698274dbf6fcd112776'
tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
python='/private/tmp/hg044-venv/bin/python'
checks={
 'focused':[python,'-m','pytest','-q','-p','no:cacheprovider','tests/harness/test_m3_milestone_closure.py'],
 'harness':[python,'-m','kineticloop.db.cli','test-harness','-p','no:cacheprovider'],
 'unit':[python,'-m','kineticloop.db.cli','test-unit','-p','no:cacheprovider'],
 'lint':[python,'-m','kineticloop.db.cli','lint'],
 'typecheck':[python,'-m','kineticloop.db.cli','typecheck'],
 'validation':[python,'-m','kineticloop.db.cli','check-harness'],
 'diff':['git','diff','--check',base,tested],
}
key=sys.argv[1];path=here/f'{key}-{tested[:7]}.json';assert not path.exists(),path
env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONDONTWRITEBYTECODE='1',MYPY_CACHE_DIR='/private/tmp/hg044-mypy-cache',RUFF_CACHE_DIR='/private/tmp/hg044-ruff-cache')
run=subprocess.run(checks[key],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
raw=run.stdout
record=dict(check_id=key,command=' '.join(checks[key]),tested_commit=tested,base_commit=base,
            exit_code=run.returncode,result='PASS' if run.returncode==0 else 'FAIL',
            evidence_ref=str(path.relative_to(root)),raw_sha256=hashlib.sha256(raw).hexdigest(),
            raw_byte_count=len(raw),raw_utf8=raw.decode())
path.write_text(json.dumps(record,indent=2)+'\n');print(key,record['result'],tested,raw.decode()[-2000:] if run.returncode else '')
raise SystemExit(run.returncode)
