import json,os,shlex,subprocess,sys,time
from pathlib import Path
r=Path('/Users/davetian/.codex/worktrees/hg061-semantic-definitions/KineticLoop')
p='/Users/davetian/Personal_Projects/KineticLoop/.venv/bin/python';B='ebee712b591d14c165007cd3d56d89cb14ea1487';T='de3d4d3427b975798bd7428bfdb3d952acfa6c5d'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()==T
assert not subprocess.check_output(['git','status','--porcelain'],cwd=r)
s=Path('/private/tmp/hg061-author-'+T[:12]+'-dependency-retry');s.mkdir(exist_ok=False)
env=dict(os.environ,PYTHONPATH=str(r)+':'+str(r/'src')+':/Users/davetian/.cache/uv/archive-v0/nnPNXkWpFSNRe9Ad:/Users/davetian/.cache/uv/archive-v0/X_H5kIMi_L692EPn')
state_path=Path('/private/tmp/hg061-worker-state.json');state=json.loads(state_path.read_text());state.update(phase='same-T harness dependency retry then remaining checks',retry_scratch=str(s));state_path.write_text(json.dumps(state,indent=2)+'\n')
commands={'harness':[p,'-m','kineticloop.cli','test-harness','--workers','2','--evidence-dir',str(s/'harness-run'),'-q'],'lint':[p,'-m','kineticloop.cli','lint'],'typecheck':[p,'-m','kineticloop.cli','typecheck'],'authority':[p,'-m','kineticloop.cli','check-harness'],'diff':['git','diff','--check',B,T]}
for name,argv in commands.items():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()==T
 meta={'check_id':name,'base_commit':B,'tested_commit':T,'argv':argv,'command':shlex.join(argv),'environment':{'PYTHONPATH':env['PYTHONPATH']},'started_at_unix':time.time(),'execution_state':'STARTED','exit_code':None}
 (s/(name+'-command.json')).write_text(json.dumps(meta,indent=2)+'\n');print('START',name,T,flush=True)
 with (s/(name+'.log')).open('wb') as output:observed=subprocess.run(argv,cwd=r,env=env,stdout=output,stderr=subprocess.STDOUT)
 meta.update(exit_code=observed.returncode,elapsed_seconds=time.time()-meta['started_at_unix'],execution_state='COMPLETED');(s/(name+'-command.json')).write_text(json.dumps(meta,indent=2)+'\n')
 state['check_results'][name]={'exit_code':observed.returncode,'metadata':str(s/(name+'-command.json'))};state_path.write_text(json.dumps(state,indent=2)+'\n');print('FINISH',name,observed.returncode,round(meta['elapsed_seconds'],2),flush=True)
 if observed.returncode:
  state['phase']='same-T retry check failed';state['failures'].append({'T':T,'check':name,'exit_code':observed.returncode,'scratch':str(s)});state_path.write_text(json.dumps(state,indent=2)+'\n');print((s/(name+'.log')).read_text()[-5000:]);sys.exit(observed.returncode)
state['phase']='eight actual same-T checks completed; identity validation/capture pending';state_path.write_text(json.dumps(state,indent=2)+'\n')
