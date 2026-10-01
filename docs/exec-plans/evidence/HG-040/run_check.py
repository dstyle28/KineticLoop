"""Preserve HG040 check raw output at exact own tested revision."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

root=Path.cwd(); here=root/'docs/exec-plans/evidence/HG-040'
base=(here/'protected-base.txt').read_text().strip()
tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
python='/private/tmp/hg040-venv/bin/python'
checks={
 'original_gateway_reproduction':[python,str(here/'original_gateway_probe.py')],
 'candidate_gateway_feasibility':[python,str(here/'candidate_gateway_diagnostic.py')],
 'scope_audit':[python,str(here/'audit.py')],
 'upstream_scope_regressions':[python,'-m','pytest','-q','tests/harness/test_preparation_scope.py','tests/harness/test_m3_next_wave_scope.py'],
 'harness_validation':[python,'-m','kineticloop.db.cli','check-harness'],
 'harness_tests':[python,'-m','kineticloop.db.cli','test-harness'],
 'unit_tests':[python,'-m','kineticloop.db.cli','test-unit'],
 'lint':[python,'-m','kineticloop.db.cli','lint'],
 'typecheck':[python,'-m','kineticloop.db.cli','typecheck'],
 'diff_clean':['git','diff','--check',base,tested],
}
key=sys.argv[1];command=checks[key];path=here/f'{key}-{tested[:7]}.log'
assert not path.exists()
env=os.environ.copy();env['PYTHONPATH']=str(root/'src');env['PYTHONDONTWRITEBYTECODE']='1';env['PATH']=str(Path(python).parent)+os.pathsep+env['PATH']
result=subprocess.run(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
raw=result.stdout
path.write_text(json.dumps({'base_commit':base,'tested_commit':tested,'command':' '.join(command),
 'exit_code':result.returncode,'raw_sha256':hashlib.sha256(raw).hexdigest(),
 'raw_byte_count':len(raw),'raw_utf8':raw.decode()},indent=2)+'\n')
record={'check_id':key,'command':' '.join(command),'result':'PASS' if result.returncode==0 else 'FAIL',
 'evidence_ref':str(path.relative_to(root)),'tested_commit':tested,'exit_code':result.returncode}
(here/f'{key}-{tested[:7]}.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
if result.returncode:print(raw.decode()[-5000:])
raise SystemExit(result.returncode)
