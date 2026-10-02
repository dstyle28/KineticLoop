import hashlib,json,subprocess
from pathlib import Path
import yaml
ROOT=Path.cwd();OUT=ROOT/'docs/exec-plans/reviews/HG-043/final-8245480-protocol-raw'
BASE='1099d85bd4aa76ec8221700e55b4e77a84479126'
SHA='8245480918251739339987de69bfe41fa0b39af5'
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def entry(sha,path):
 rows=git('ls-tree','-z',sha,'--',path).split(b'\0')
 for row in filter(None,rows):
  meta,name=row.split(b'\t',1)
  if name==path.encode(): return meta.decode().split()
 return None
def available_regular(sha,path):
 e=entry(sha,path)
 assert e is not None and e[0] in ('100644','100755') and e[1]=='blob',(sha,path,e)
 assert git('cat-file','-t',e[2]).strip()==b'blob'
 return e[2]
replay=json.loads(json.loads((OUT/'replay.json').read_text())['raw_utf8'])
tasks={t['id']:t for t in json.loads(git('show',BASE+':KineticLoop_Harness_Backlog_v0.2.json'))['tasks']}
report={'reviewed_head_sha':SHA,'purpose':'Independent raw-Git audit of replay sources; reviewer runs remain review evidence, not task acceptance','candidates':{}}
for task,x in replay['candidates'].items():
 r=x['record'];reviewed=r['reviewed_head_sha']; endpoint=r['review_record_commit']; merged=r['merge_commit']; prefix='docs/exec-plans/reviews/'+task+'/'
 assert subprocess.run(['git','merge-base','--is-ancestor',merged,BASE],cwd=ROOT).returncode==0
 parents=git('rev-list','--parents','-n','1',merged).decode().split()[1:]
 assert len(parents)==2 and endpoint in parents
 commits=git('rev-list','--reverse',reviewed+'..'+endpoint).decode().splitlines()
 suffix=[]
 for c in commits:
  p=git('rev-list','--parents','-n','1',c).decode().split()[1:];assert len(p)==1
  paths=git('diff','--name-only','-z',p[0],c).split(b'\0');paths=[q.decode() for q in paths if q]
  assert all(q.startswith(prefix) for q in paths)
  suffix.append({'commit':c,'paths':paths})
 ordinary=[];created=[]
 for ref in x['references']:
  path=ref['path'];e=entry(reviewed,path)
  if e is not None:
   ordinary.append({'path':path,'blob':available_regular(reviewed,path)})
  else:
   assert path.startswith(prefix)
   created.append({'path':path,'blob':available_regular(endpoint,path),'classification':'reviewer-created bookkeeping, not task acceptance'})
 resultpath='docs/exec-plans/completed/'+task+'_RESULT.yaml'
 try: resultbytes=git('show',r['result_commit']+':'+resultpath)
 except subprocess.CalledProcessError:
  resultpath=resultpath[:-4]+'json'; resultbytes=git('show',r['result_commit']+':'+resultpath)
 assert resultbytes==git('show',reviewed+':'+resultpath)
 result=yaml.safe_load(resultbytes)
 checkrefs=[]
 for command in result.get('commands_run',[]):
  if command.get('result')=='PASS':
   ref=command.get('evidence_ref')
   if ref: checkrefs.append({'check_id':command.get('check_id'),'path':ref,'blob_at_reviewed':available_regular(reviewed,ref)})
 report['candidates'][task]={'record':r,'normal_merge_parents':parents,'strict_suffix_commits':suffix,'ordinary_refs':ordinary,'review_created_refs':created,'task_check_refs_at_reviewed':checkrefs,'result_sha256':hashlib.sha256(resultbytes).hexdigest(),'old_errors':x['original_validator_errors'],'new_errors':x['repaired_validator_errors']}
(OUT/'replay-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print({k:{'ordinary_refs':len(v['ordinary_refs']),'review_created_refs':len(v['review_created_refs']),'task_check_refs_at_reviewed':len(v['task_check_refs_at_reviewed'])} for k,v in report['candidates'].items()})
