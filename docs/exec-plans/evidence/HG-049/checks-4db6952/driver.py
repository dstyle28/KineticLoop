from pathlib import Path
import concurrent.futures,subprocess,os,json,time
root=Path('/Users/davetian/.codex/worktrees/a9f7/KineticLoop')
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
out=Path('/private/tmp/hg049-checks-'+sha[:7]);out.mkdir(exist_ok=True)
env=dict(os.environ);env['PATH']='/private/tmp/hg048-tools/bin:'+str(root/'.venv/bin')+':'+env['PATH'];env['UV_CACHE_DIR']='/private/tmp/hg049-uv-cache'
commands={'harness':'uv run kl test-harness --workers 2 --evidence-dir '+str(out/'harness')+' -q','unit':'uv run kl test-unit -q --junitxml='+str(out/'unit.xml'),'authority':'uv run kl check-harness','lint':'uv run kl lint','typecheck':'uv run kl typecheck','scope':'uv run python docs/exec-plans/evidence/HG-049/scope_audit.py','diff':'git diff --check 95ddd75d3eb410b7dffa15a1017276c504adc9a6 '+sha}
def run(item):
 name,cmd=item;start=time.time()
 with (out/(name+'.log')).open('wb') as log:
  proc=subprocess.run(cmd.split(),cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
 rec={'check_id':name,'command':cmd,'exit_code':proc.returncode,'tested_commit':sha,'elapsed_seconds':time.time()-start,'log':str(out/(name+'.log'))}
 (out/(name+'.json')).write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec),flush=True);return rec
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 records=list(ex.map(run,commands.items()))
(out/'RUN.json').write_text(json.dumps(records,indent=2)+'\n')
raise SystemExit(any(r['exit_code'] for r in records))
