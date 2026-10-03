import sys,subprocess,json,hashlib,os,time
from pathlib import Path
name=sys.argv[1];command=sys.argv[2:];root=Path.cwd()
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
d=Path('/private/tmp/hg046-checks')/sha[:7];d.mkdir(parents=True,exist_ok=True)
log=d/(name+'.log');record=d/(name+'.json')
assert not log.exists() and not record.exists()
start=time.monotonic()
with log.open('wb') as f:
 result=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONPATH':'.:src'})
raw=log.read_bytes()
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==sha
record.write_text(json.dumps({'check_id':name,'tested_commit':sha,'argv':command,'exit_code':result.returncode,'result':'PASS' if result.returncode==0 else 'FAIL','duration_seconds':round(time.monotonic()-start,3),'raw_log':log.name,'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)},indent=2)+'\n')
print(record.read_text());print(raw.decode(errors='replace')[-2500:])
sys.exit(result.returncode)
