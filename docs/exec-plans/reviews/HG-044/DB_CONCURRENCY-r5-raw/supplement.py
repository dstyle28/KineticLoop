import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
import jsonschema
root=Path.cwd(); out=root/'docs/exec-plans/reviews/HG-044/DB_CONCURRENCY-r5-raw'
base='2c44f456a0daf8e6933f20fc3eadc7e1869d6fff'; rev='027bc2368e36e28aa9956489cb57af297882d671'
def blob(path, revision=rev):return subprocess.check_output(['git','show',revision+':'+path],cwd=root)
def load(path,revision=rev):return json.loads(blob(path,revision))
index=load('CURRENT_DOCUMENT_INDEX.json')
for section in ('documents','machine_readable'):
    for entry in index[section]:assert hashlib.sha256(blob(entry['path'])).hexdigest()==entry['sha256']
manifest=load('HARNESS_DOCUMENT_MANIFEST.json')
for entry in manifest['files']:
    raw=blob(entry['path'])
    assert len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256']
spec=importlib.util.spec_from_file_location('v',root/'tools/harness/validate_harness.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
tasks={t['id']:t for t in load(v.BACKLOG)['tasks']}
schemas=[jsonschema.Draft202012Validator(load(path)) for path in (v.MILESTONE_CLOSURE_SCHEMA,v.INTEGRATION_SCHEMA,'THREAD_RESULT.schema.json','THREAD_REVIEW.schema.json')]
selected=['KL-021','KL-022','KL-023','KL-026','KL-027','KL-074','KL-076','KL-077','KL-078','KL-079']
records=[]
for name in selected:
    path=f'docs/exec-plans/integrations/{name}.json';record=load(path)
    errors=v.integration_record_errors(root,Path(path),record,*schemas[1:],tasks)
    assert not errors,(name,errors)
    records.append({'task':name,'status':'PASS','reviewed':record['reviewed_head_sha'],'merge':record['merge_commit']})
b=load(v.BACKLOG)
legacy={'M1':v.milestone_closure_errors(root,load('docs/exec-plans/milestones/M1.json'),*schemas,b,tasks),
        'M2':v.m2_milestone_closure_errors(root,load('docs/exec-plans/milestones/M2.json'),*schemas,b,tasks)}
assert not any(legacy.values())
(out/'supplement.json').write_text(json.dumps({'status':'PASS','index':'all hash bindings verified',
 'manifest_entries':len(manifest['files']),'selected_integrations':records,'legacy':legacy},indent=2)+'\n')
print('SUPPLEMENT_PASS selected_integrations='+str(len(records)))
