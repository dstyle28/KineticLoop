import ast,hashlib,json,os,subprocess,sys,time
from pathlib import Path
P='/Users/davetian/Personal_Projects/KineticLoop/.venv/bin/python';R=Path('/Users/davetian/.codex/worktrees/hg065-custody-delivery/KineticLoop');E=R/'docs/exec-plans/evidence/HG-065';O=Path('/private/tmp/hg065-general-r1');S=O/'scratch';S.mkdir(exist_ok=False)
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONPATH=f'{E}:{R}:{R}/src',HG065_OBSERVATIONS=str(S));runs=[]
for name,argv,cwd in [('original',[P,str(E/'observe_immutable.py')],E),('inherited',[P,str(E/'observe_inherited_components.py')],E),('definitions',[P,'-m','pytest','test_custody_definition.py','-q','-q','--import-mode=importlib','--rootdir='+str(E),'--confcutdir='+str(E),'-c','/dev/null','-p','no:cacheprovider','-o','xfail_strict=true','--junitxml='+str(S/'probe-junit.xml')],E),('scope',[P,'-m','pytest','tests/harness/test_validator.py','-q','-k','hg065','-p','no:cacheprovider','--basetemp='+str(S/'pytest')],R)]:
 start=time.monotonic();p=subprocess.run(argv,cwd=cwd,env=env,capture_output=True);log=p.stdout+p.stderr;(O/(name+'.log')).write_bytes(log);runs.append(dict(name=name,argv=argv,cwd=str(cwd),exit_code=p.returncode,elapsed_seconds=time.monotonic()-start,output_bytes=len(log),output_sha256=hashlib.sha256(log).hexdigest()));(O/'probe_commands.json').write_text(json.dumps(runs,indent=2)+'\n');print(name,p.returncode,flush=True);assert p.returncode==0,log[-2000:]
# Compact evidence only. Preserve hashes of transient fresh component observations, not bulky fixtures.
rows=[]
for f in sorted(S.iterdir()):
 if f.is_file():rows.append(dict(name=f.name,bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
(O/'fresh_observation_identities.json').write_text(json.dumps(rows,indent=2)+'\n')
