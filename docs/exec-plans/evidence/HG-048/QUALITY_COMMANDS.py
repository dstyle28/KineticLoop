from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import datetime,hashlib,json,os,subprocess,sys,time
root=Path('/Users/davetian/.codex/worktrees/harness-concurrency/KineticLoop')
measure=Path('/private/tmp/hg048-final-measurements')
print('Quality capture waits for all benchmark runs to avoid timing contention.',flush=True)
while not (measure/'comparison.json').exists(): time.sleep(5)
tested=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
if tested!='0045808352507b7af67a3a2135408421d8bcc6bc': raise RuntimeError('Source changed')
out=Path('/private/tmp/hg048-final-quality')/tested
out.mkdir(parents=True,exist_ok=False)
python=str(root/'.venv/bin/python')
commands={
 'lint':[python,'-m','kineticloop.db.cli','lint'],
 'typecheck':[python,'-m','kineticloop.db.cli','typecheck','--no-incremental','--cache-dir','/private/tmp/hg048-final-mypy'],
 'unit':[python,'-m','kineticloop.db.cli','test-unit','-q','--junitxml='+str(out/'unit.xml')],
 'authority':[python,'-m','kineticloop.db.cli','check-harness'],
 'diff':['git','diff','--check','391c9198fa8ec647e377a0572700bc7568468c85',tested],
}
def capture(item):
 label,argv=item;start=time.monotonic()
 stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with (out/(label+'.log')).open('xb') as stream:
  result=subprocess.run(argv,cwd=root,stdout=stream,stderr=subprocess.STDOUT)
 raw=(out/(label+'.log')).read_bytes()
 record={'tested_commit':tested,'command':argv,'started_at_utc':stamp,'wall_seconds':time.monotonic()-start,'exit_code':result.returncode,'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)}
 (out/(label+'.json')).write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps({'check':label,'exit_code':result.returncode,'wall_seconds':record['wall_seconds']}),flush=True)
 print(raw.decode(errors='replace')[-1500:],flush=True)
 return record
start=time.monotonic()
with ThreadPoolExecutor(max_workers=3) as executor: records=list(executor.map(capture,commands.items()))
summary={'tested_commit':tested,'max_concurrent_commands':3,'wall_seconds':time.monotonic()-start,'checks':records}
(out/'quality.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
sys.exit(0 if all(r['exit_code']==0 for r in records) else 1)
