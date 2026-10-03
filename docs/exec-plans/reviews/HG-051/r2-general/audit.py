import hashlib, importlib.util,json,subprocess,yaml
from pathlib import Path
R=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop');B='b877db0edd2e4550d6ea81750656112fb7f2e223';H='0557dbd8f2196df871af20c0982bdc2526f0ad6e'
def g(*args):return subprocess.check_output(['git',*args],cwd=R)
def obj(rev,path):return g('show',rev+':'+path)
def j(rev,path):return json.loads(obj(rev,path))
def oid(rev,path):return g('rev-parse',rev+':'+path).decode().strip()
s=importlib.util.spec_from_file_location('audit_validator',R/'tools/harness/validate_harness.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
changed=g('diff','--no-renames','--name-only',B,H).decode().splitlines();assert all(v.matches(x,v.governance_allowed_patterns('HG-051')) for x in changed)
assert not any(x.startswith(('src/','migrations/','.github/')) or x in ('tools/harness/local_gate.py','tools/harness/github_app.py') for x in changed)
idx=j(H,'CURRENT_DOCUMENT_INDEX.json');authority=[]
for group in ('documents','machine_readable'):
 for x in idx[group]: assert hashlib.sha256(obj(H,x['path'])).hexdigest()==x['sha256'];authority.append(x['path'])
f=j(B,'FROZEN_BASELINE.json'); frozen=[x['path'] for x in f['files']]+['FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','KineticLoop_Acceptance_Spec_v1.2.2.json','KineticLoop_Integration_Acceptance_v0.1.json']
for p in frozen:assert oid(B,p)==oid(H,p)
prior=g('ls-tree','-r','--name-only',B,'--','docs/exec-plans/completed','docs/exec-plans/reviews','docs/exec-plans/evidence').decode().splitlines()
def tree(rev):
 return {line.split(b'\t',1)[1].decode():line.split(b'\t',1)[0] for line in g('ls-tree','-r',rev).splitlines()}
bt,ht=tree(B),tree(H)
for p in prior:assert bt[p]==ht[p]
old=j(B,v.BACKLOG);new=j(H,v.BACKLOG);oldtasks={t['id']:t for t in old['tasks']};newtasks={t['id']:t for t in new['tasks']};assert oldtasks.keys()==newtasks.keys()
for tid,t in oldtasks.items():
 expected=dict(t)
 if tid=='KL-080': expected['definition_of_done']=newtasks[tid]['definition_of_done'];assert expected['definition_of_done'].startswith(t['definition_of_done'])
 assert expected==newtasks[tid]
kl=newtasks['KL-080']; assert len(kl['exclusive_resources'])==8 if 'exclusive_resources' in kl else True
traceold=j(B,v.TRACEABILITY);tracenew=j(H,v.TRACEABILITY)
def scrub(x):
 if isinstance(x,dict):return {k:scrub(v) for k,v in x.items() if k!='definition_of_done'}
 if isinstance(x,list):return [scrub(v) for v in x]
 return x
assert scrub(traceold)==scrub(tracenew)
prereqs=[]
for tid in kl['depends_on']:
 path=next(p for p in v.result_paths(tid) if (R/p).exists());record=yaml.safe_load(obj(H,path));assert record['task_status']==record['task_checks_status']=='PASS';i=j(H,f'docs/exec-plans/integrations/{tid}.json');assert i['integration_status']=='MERGED';g('merge-base','--is-ancestor',i['merge_commit'],B)
 for typ in oldtasks[tid]['review_requirements']:
  rv=j(H,f'docs/exec-plans/reviews/{tid}/{typ}.json');assert rv['status']=='PASS' and rv['reviewed_head_sha']==i['reviewed_head_sha']
 prereqs.append(tid)
ce=v.compact_evidence;assert (ce.PLAIN_LIMIT,ce.STORED_LIMIT,ce.RAW_LIMIT,ce.TOTAL_LIMIT)==(262144,8388608,67108864,16777216)
basece=obj(B,'tools/harness/compact_evidence.py').decode();newce=obj(H,'tools/harness/compact_evidence.py').decode()
# Compare unchanged execution functions literally, avoiding insertion-boundary whitespace.
for start,end in [('def read(', 'def capture('),('def capture(', 'def embedded_raw(')]:
 a=basece[basece.index(start):basece.index(end)].strip(); stop=newce.index(end) if end!='def embedded_raw(' else newce.index('HISTORICAL_FORMAT ='); b=newce[newce.index(start):stop].strip();assert a==b
budget=ce.audit(R,B,H,'HG-051');assert not budget['errors'];g('diff','--check',B,H)
report=dict(source_commit=H,base_commit=B,status='PASS',changed_path_count=len(changed),indexed_authority_count=len(authority),frozen_and_requirement_files=frozen,historical_artifacts_preserved=len(prior),prerequisites=prereqs,execution_gzip_functions_unchanged=True,kl080_only_definition_of_done_appended=True,kl080_migration_applied=False,budget=budget)
Path('/private/tmp/hg051-r2-general-work/audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
