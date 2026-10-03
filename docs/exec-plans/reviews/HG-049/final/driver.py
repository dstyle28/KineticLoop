from pathlib import Path
import json,subprocess,os,time
root=Path('/Users/davetian/.codex/worktrees/a9f7/KineticLoop');head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
cmd=['uv','run','kl','check-harness','--ci-pr-base','95ddd75d3eb410b7dffa15a1017276c504adc9a6','--ci-pr-head',head]
env=dict(os.environ);env['PATH']='/private/tmp/hg048-tools/bin:'+str(root/'.venv/bin')+':'+env['PATH'];env['UV_CACHE_DIR']='/private/tmp/hg049-uv-cache'
start=time.time()
with open('/private/tmp/hg049-final-gate.log','wb') as log:
 r=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
record={'tested_commit':head,'command':' '.join(cmd),'exit_code':r.returncode,'elapsed_seconds':time.time()-start}
Path('/private/tmp/hg049-final-gate.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
raise SystemExit(r.returncode)
