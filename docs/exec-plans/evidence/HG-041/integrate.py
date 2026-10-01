"""Verified normal merge ancestry only, without historical artifact edits."""
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

root=Path.cwd(); here=root/'docs/exec-plans/evidence/HG-041'
base=(here/'protected-base.txt').read_text().strip()
def git(*args): return subprocess.check_output(['git',*args])
def ancestor(a,b): subprocess.run(['git','merge-base','--is-ancestor',a,b],check=True)
tasks={t['id']:t for t in json.loads((root/'KineticLoop_Harness_Backlog_v0.2.json').read_text())['tasks']}
facts=[]
for name in ['KL-026','KL-078','KL-076']:
 pr=json.loads((here/(name.replace('-','')+'-normal-merge.json')).read_text()); assert pr['state']=='MERGED'
 merge=pr['mergeCommit']['oid']; parents=git('rev-list','--parents','-n','1',merge).decode().split(); assert len(parents)==3; suffix=parents[2]; assert suffix==pr['headRefOid']; ancestor(merge,base)
 reviews=[json.loads(git('show',base+f':docs/exec-plans/reviews/{name}/{typ}.json')) for typ in tasks[name]['review_requirements']]
 assert all(r['status']=='PASS' and r['task_identity']==tasks[name]['task_identity'] for r in reviews)
 assert len({r['reviewed_head_sha'] for r in reviews})==1; reviewed=reviews[0]['reviewed_head_sha']
 path=f'docs/exec-plans/completed/{name}_RESULT.yaml'; result_commit=git('log','-1','--format=%H',reviewed,'--',path).decode().strip(); raw=git('show',result_commit+':'+path); result=yaml.safe_load(raw)
 assert result['task_status']==result['task_checks_status']=='PASS'; assert raw==git('show',reviewed+':'+path)==git('show',base+':'+path)
 for a,b in [(result['base_commit'],result['tested_commit']),(result['tested_commit'],result_commit),(result_commit,reviewed),(reviewed,suffix),(suffix,merge)]: ancestor(a,b)
 for c in git('rev-list',reviewed+'..'+suffix).decode().splitlines():
  assert len(git('rev-list','--parents','-n','1',c).decode().split())==2
  assert all(p.startswith(f'docs/exec-plans/reviews/{name}/') for p in git('diff-tree','--no-commit-id','--name-only','-r',c).decode().splitlines())
 assert git('rev-parse',suffix+'^{tree}')==git('rev-parse',merge+'^{tree}')
 missing=[]
 for r in reviews:
  for ref in r['evidence_refs']:
   if subprocess.run(['git','cat-file','-e',reviewed+':'+ref],capture_output=True).returncode: missing.append(ref)
 record={'task_identity':tasks[name]['task_identity'],'display_task_id':name,'result_commit':result_commit,'reviewed_head_sha':reviewed,'review_record_commit':suffix,'merge_commit':merge,'integration_status':'MERGED'}
 if not missing: (root/f'docs/exec-plans/integrations/{name}.json').write_text(json.dumps(record,indent=2)+'\n')
 facts.append({'id':name,'record':record,'result_sha256':hashlib.sha256(raw).hexdigest(),'disposition':'DEFERRED_MISSING_REVIEWED_EVIDENCE' if missing else 'APPENDED','missing_reviewed_refs':missing})
(here/'integration-provenance.json').write_text(json.dumps({'protected_base':base,'facts':facts},indent=2)+'\n')
print(json.dumps([{'id':f['id'],'disposition':f['disposition']} for f in facts]))
