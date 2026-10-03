import json,subprocess,os,time
from pathlib import Path
root=Path('/Users/davetian/.codex/worktrees/cd73/KineticLoop')
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert sha=='f302b22c0838ef2928913392e7c2a6af9e8f8698'
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root)
out=Path('/private/tmp/hg050-harness-rerun-f302b22');out.mkdir(exist_ok=False)
command='uv run kl test-harness --workers 2 --evidence-dir '+str(out/'harness')+' -q'
env=dict(os.environ);env['PATH']='/private/tmp/hg048-tools/bin:'+str(root/'.venv/bin')+':'+env['PATH'];env['UV_CACHE_DIR']='/private/tmp/hg050-uv-cache'
start=time.time()
with (out/'harness.log').open('wb') as log:
 result=subprocess.run(command.split(),cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
record={'check_id':'harness','command':command,'exit_code':result.returncode,'tested_commit':sha,'elapsed_seconds':time.time()-start,'log':str(out/'harness.log'),'source_start_status':'clean','source_end_status':subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True),'source_end_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()}
(out/'EXECUTION.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
raise SystemExit(result.returncode)
