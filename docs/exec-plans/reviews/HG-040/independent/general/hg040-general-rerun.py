import os,subprocess,hashlib,json
from pathlib import Path
root=Path.cwd();python='/private/tmp/hg040-venv/bin/python';env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONDONTWRITEBYTECODE='1');summary=[]
commands=[('scope-negatives',[python,'-m','pytest','-p','no:cacheprovider','-q','tests/harness/test_preparation_scope.py','tests/harness/test_m3_next_wave_scope.py']),('harness-current',[python,'-m','kineticloop.db.cli','check-harness']),('original-gateway',[python,'docs/exec-plans/evidence/HG-040/original_gateway_probe.py']),('candidate-gateway',[python,'docs/exec-plans/evidence/HG-040/candidate_gateway_diagnostic.py'])]
for name,command in commands:
 r=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);path=Path('/private/tmp/hg040-general-'+name+'.log');path.write_bytes(r.stdout)
 summary.append({'command':command,'exit_code':r.returncode,'raw_path':str(path),'raw_sha256':hashlib.sha256(r.stdout).hexdigest(),'raw_byte_count':len(r.stdout),'last_output':r.stdout.decode().splitlines()[-1]})
 assert r.returncode==0,(name,r.stdout.decode())
print(json.dumps(summary,indent=2))
