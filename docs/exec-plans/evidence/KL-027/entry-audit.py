import hashlib
import json
import subprocess
from pathlib import Path
import yaml

root = Path.cwd().resolve()
base = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
def ancestor(sha):
    return subprocess.run(['git','merge-base','--is-ancestor',sha,base]).returncode == 0
records = []
for task in ['017','019','022','023','024','025','074','075','076','077','078','079']:
    name = 'KL-'+task
    result = yaml.safe_load((root/f'docs/exec-plans/completed/{name}_RESULT.yaml').read_text())
    assert result['task_identity'] == 'harness-backlog-v0.2/'+name
    assert result['task_status'] == result['task_checks_status'] == 'PASS'
    assert ancestor(result['tested_commit'])
    reviews = []
    for p in sorted((root/f'docs/exec-plans/reviews/{name}').glob('*.json')):
        r = json.loads(p.read_text())
        assert r['status'] == 'PASS', (p, r)
        assert ancestor(r['reviewed_head_sha'])
        reviews.append({'path':str(p.relative_to(root)), 'reviewed_head_sha':r['reviewed_head_sha'], 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    assert reviews
    log = subprocess.check_output(['git','log','--first-parent','--merges','--format=%H %s',base],text=True).splitlines()
    commits = subprocess.check_output(['git','log','--format=%H','--',f'docs/exec-plans/completed/{name}_RESULT.yaml'],text=True).splitlines()
    merge = next(line for line in reversed(log) if all(subprocess.run(['git','merge-base','--is-ancestor',c,line[:40]]).returncode == 0 for c in commits))
    parents = subprocess.check_output(['git','show','-s','--format=%P',merge[:40]],text=True).split()
    assert len(parents)==2 and 'Merge pull request #' in merge
    for r in reviews:
        paths = subprocess.check_output(['git','diff','--name-only',r['reviewed_head_sha'],parents[1]],text=True).splitlines()
        assert all(v.startswith('docs/exec-plans/reviews/'+name+'/') for v in paths)
        r['normal_merge_source_head'] = parents[1]
        r['verified_review_only_suffix_paths'] = paths
    integration = root/f'docs/exec-plans/integrations/{name}.json'
    records.append({'task':name,'tested_commit':result['tested_commit'],'normal_merge':merge,'reviews':reviews,'integration_record':json.loads(integration.read_text()) if integration.exists() else None,'result_sha256':hashlib.sha256((root/f'docs/exec-plans/completed/{name}_RESULT.yaml').read_bytes()).hexdigest()})
assert json.loads((root/'docs/exec-plans/milestones/M2.json').read_text())['closure_status']=='PASS'
for path in ['completed/KL-027_RESULT.yaml','integrations/KL-027.json','reviews/KL-027']:
    assert not (root/'docs/exec-plans'/path).exists()
print(json.dumps({'base_commit':base,'root':str(root),'exclusive_resource':'test_only_demo_suite','prerequisites':records,'m2':'PASS','own_result_review_integration':'ABSENT','initial_checks':'NOT_RUN'},indent=2))
