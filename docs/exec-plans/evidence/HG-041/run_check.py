"""Record raw governance checks at the exact tested revision; no overwriting."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
root=Path.cwd(); here=root/'docs/exec-plans/evidence/HG-041'
base=(here/'protected-base.txt').read_text().strip(); tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(); python=str(root/'.venv/bin/python')
checks={
 'scope_audit':[python,str(here/'audit.py')],
 'candidate_feasibility':[python,str(here/'candidate.py')],
 'action_scope_regressions':[python,'-m','pytest','-q','tests/harness/test_full_action_scope.py','tests/harness/test_m3_next_wave_scope.py','tests/harness/test_preparation_scope.py'],
 'legacy_unit_regression':[python,'-m','pytest','-q','tests/unit/workflow/test_deterministic_planning.py'],
 'harness_validation':[python,'-m','kineticloop.db.cli','check-harness'],
 'harness_tests':[python,'-m','kineticloop.db.cli','test-harness'],
 'unit_tests':[python,'-m','kineticloop.db.cli','test-unit'],
 'lint':[python,'-m','kineticloop.db.cli','lint'],
 'typecheck':[python,'-m','kineticloop.db.cli','typecheck'],
 'diff_clean':['git','diff','--check',base,tested],
}
key=sys.argv[1]; command=checks[key]; path=here/f'{key}-{tested[:7]}.log'; assert not path.exists()
env=os.environ.copy(); env['PATH']=str(root/'.venv/bin')+os.pathsep+env['PATH']; env['PYTHONDONTWRITEBYTECODE']='1'
run=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT); raw=run.stdout
path.write_text(json.dumps({'base_commit':base,'tested_commit':tested,'command':' '.join(command),'exit_code':run.returncode,'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_byte_count':len(raw),'raw_utf8':raw.decode()},indent=2)+'\n')
record={'check_id':key,'command':' '.join(command),'result':'PASS' if run.returncode==0 else 'FAIL','evidence_ref':str(path.relative_to(root)),'tested_commit':tested,'exit_code':run.returncode}
(here/f'{key}-{tested[:7]}.json').write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record)); print(raw.decode()[-3000:] if run.returncode else '')
raise SystemExit(run.returncode)
