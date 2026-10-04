import subprocess,json,hashlib,yaml
from pathlib import Path
B='1d3075151246b2774640a3d7acec836f47ab2b8d';H='5812ff2ca2c45bfe88c743e36656ea1921112ed6';T='feb3236c175df171611fc5b7ddb4f6eeca3ce47c'
def git(*a):return subprocess.check_output(['git',*a])
def read(p,r=B):return git('show',r+':'+p)
def obj(p,r=B):return json.loads(read(p,r))
entry=obj('docs/exec-plans/evidence/KL-080/HG051-'+T+'/entry.json',H)
rows=[]
for p in entry['prerequisites']:
 task=p['task_identity'].split('/')[-1];result=read('docs/exec-plans/completed/'+task+'_RESULT.yaml');r=yaml.safe_load(result)
 assert hashlib.sha256(result).hexdigest()==p['result_sha256'];assert r['task_status']==r['task_checks_status']=='PASS'
 i=obj('docs/exec-plans/integrations/'+task+'.json');assert i['integration_status']=='MERGED' and i['merge_commit']==p['merge_commit'] and i['reviewed_head_sha']==p['reviewed_head_sha']
 assert subprocess.run(['git','merge-base','--is-ancestor',i['merge_commit'],B]).returncode==0
 for kind in p['required_reviews']:
  v=obj('docs/exec-plans/reviews/'+task+'/'+kind+'.json',i['review_record_commit']);assert v['status']=='PASS' and v['reviewed_head_sha']==i['reviewed_head_sha'] and v['task_identity']==p['task_identity']
 rows.append({'task_identity':p['task_identity'],'merge_commit':i['merge_commit'],'required_reviews':p['required_reviews'],'status':'PASS'})
assert obj('docs/exec-plans/milestones/M2.json')['closure_status']=='PASS'
for p in ['docs/exec-plans/completed/KL-080_RESULT.yaml','docs/exec-plans/integrations/KL-080.json','docs/exec-plans/reviews/KL-080/GENERAL.json']:
 assert not git('ls-tree',B,'--',p).strip()
summary={'base_commit':B,'reviewed_head_sha':H,'transitive_prerequisites':rows,'M2':'PASS','KL080_absent_at_base':True,'status':'PASS'}
Path(__file__).with_name('prerequisites.json').write_text(json.dumps(summary,indent=2)+'\n')
print('PASS',len(rows),'prerequisite results, integrations and bound required reviews')
