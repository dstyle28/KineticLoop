"""Fail closed on governance scope and historical prerequisite mutation."""
import importlib.util
import json
import subprocess
from pathlib import Path

root=Path.cwd(); here=root/'docs/exec-plans/evidence/HG-041'; base=(here/'protected-base.txt').read_text().strip()
def git(*args): return subprocess.check_output(['git',*args],text=True)
b=json.loads((root/'KineticLoop_Harness_Backlog_v0.2.json').read_text()); old=json.loads(git('show',base+':KineticLoop_Harness_Backlog_v0.2.json')); tasks={t['id']:t for t in b['tasks']}
for t in old['tasks']:
 if t['id']!='KL-077': assert t==tasks[t['id']], 'historical task definition changed: '+t['id']
old77=next(t for t in old['tasks'] if t['id']=='KL-077'); new77=tasks['KL-077']
assert {k for k in old77 if old77[k]!=new77[k]}=={'depends_on','entry_conditions','context_files'}
assert new77['depends_on']==old77['depends_on']+['KL-079']
new=tasks['KL-079']; assert new['status']=='NOT_STARTED' and new['requirements_covered']==new['evidence_refs']==[]
for kind in ['completed','reviews','integrations']: assert not list((root/f'docs/exec-plans/{kind}').glob('KL-079*'))
changed=git('diff','--name-only',base).splitlines()+git('ls-files','--others','--exclude-standard').splitlines()
assert all(not p.startswith(('src/','migrations/','.github/','docs/exec-plans/completed/')) for p in changed)
assert not any(p in {'FROZEN_BASELINE.json','05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md','CURRENT_REQUIREMENT_SET.json'} for p in changed)
for dep in new['depends_on']:
 result=f'docs/exec-plans/completed/{dep}_RESULT.yaml'; git('cat-file','-e',base+':'+result)
 for typ in tasks[dep]['review_requirements']:
  review=json.loads(git('show',base+f':docs/exec-plans/reviews/{dep}/{typ}.json'))
  assert review['status']=='PASS'
  subprocess.run(['git','merge-base','--is-ancestor',review['reviewed_head_sha'],base],check=True)
spec=importlib.util.spec_from_file_location('auditv',root/'tools/harness/validate_harness.py'); v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
for name in ['KL-077','KL-079']:
 assert v.m3_next_wave_definition_errors(tasks[name])==[]
 assert v.packet_errors(tasks[name],(root/f'docs/exec-plans/active/{name}.md').read_text())==[]
print('HG041_SCOPE_AND_PREREQUISITE_AUDIT_PASS; KL079 CHECKS NOT_RUN; NO PRODUCT OR DC PASS')
