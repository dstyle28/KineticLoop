import hashlib
import json
from pathlib import Path
import jsonschema
root=Path.cwd();out=root/'docs/exec-plans/reviews/HG-044/DB_CONCURRENCY-r5-raw'
prefix='docs/exec-plans/reviews/HG-044/DB_CONCURRENCY-r5-raw/'
review={'task_identity':'harness-governance-v0.1/HG-044',
        'reviewed_head_sha':'027bc2368e36e28aa9956489cb57af297882d671',
        'review_type':'DB_CONCURRENCY','status':'PASS','review_contract_version':'v0.2','findings':[],
        'evidence_refs':['docs/exec-plans/governance/HG-044.yaml','docs/harness/M3_CLOSURE_CONTRACT.md',
                         'docs/exec-plans/evidence/HG-044/focused-7206b60.json',
                         'docs/exec-plans/evidence/HG-044/capture-integrity-7206b60.json']+
        [prefix+n for n in ('assessment.md','audit.py','audit.json','complete-diff.patch','commands.json',
         'bounded-pytest.stdout','bounded.xml','supplement.py','supplement.json','witnesses.py','witnesses.json',
         'broad-diff.stdout','source-diff.stdout')]}
jsonschema.Draft202012Validator(json.loads((root/'THREAD_REVIEW.schema.json').read_text())).validate(review)
assert all((root/ref).is_file() and not (root/ref).is_symlink() for ref in review['evidence_refs'])
commands=json.loads((out/'commands.json').read_text())
assert all(type(c['exit_code']) is int and c['exit_code']==0 for c in commands)
assert '43 passed, 45 deselected' in (out/'bounded-pytest.stdout').read_text()
(root/'docs/exec-plans/reviews/HG-044/DB_CONCURRENCY.json').write_text(json.dumps(review,indent=2)+'\n')
rows=[]
for path in sorted(out.iterdir()):
    if path.is_file() and path.name!='inventory.json':
        raw=path.read_bytes();rows.append({'path':str(path.relative_to(root)),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
(out/'inventory.json').write_text(json.dumps({'status':'PASS','reviewed':review['reviewed_head_sha'],'files':rows},indent=2)+'\n')
print('DB_CONCURRENCY_REVIEW_SCHEMA_PASS files='+str(len(rows)))
