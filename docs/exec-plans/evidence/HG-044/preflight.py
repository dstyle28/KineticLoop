"""Read-only revision-bound HG044 prerequisites and dependency-chain audit."""
import importlib.util
import json
from pathlib import Path

import jsonschema

r=Path.cwd();s=importlib.util.spec_from_file_location('v',r/'tools/harness/validate_harness.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
b=json.loads((r/v.BACKLOG).read_text());tasks={t['id']:t for t in b['tasks']}
schemas=[jsonschema.Draft202012Validator(json.loads((r/n).read_text())) for n in (v.MILESTONE_CLOSURE_SCHEMA,v.INTEGRATION_SCHEMA,'THREAD_RESULT.schema.json','THREAD_REVIEW.schema.json')]
report={'head':v.resolve(r,'HEAD'),'origin_master':v.resolve(r,'origin/master'),'m2_errors':v.m2_milestone_closure_errors(r,json.loads((r/'docs/exec-plans/milestones/M2.json').read_text()),*schemas,b,tasks),'records':[],'missing_prospective':['KL-028','KL-029']}
for n in sorted(v.M3_TASK_IDS-{'KL-028','KL-029'}|{'KL-074'}):
 p=r/f'docs/exec-plans/integrations/{n}.json';record=json.loads(p.read_text());reviewed=record['reviewed_head_sha'];result_path=v.result_paths_at_revision(r,n,reviewed)[0];result=v.load_artifact_at_revision(r,result_path,reviewed)
 row={'task':n,'integration':record,'result_path':result_path,'result_sha256':v.blob_sha_at_revision(r,result_path,reviewed),'errors':v.integration_record_errors(r,p,record,*schemas[1:],tasks),'dependencies':[]}
 for dep in tasks[n]['depends_on']:
  d=json.loads((r/f'docs/exec-plans/integrations/{dep}.json').read_text());row['dependencies'].append({'task':dep,'merge_commit':d['merge_commit'],'before_base':v.is_ancestor(r,d['merge_commit'],result['base_commit']),'before_tested':v.is_ancestor(r,d['merge_commit'],result['tested_commit'])})
 report['records'].append(row)
report['status']='PASS' if not report['m2_errors'] and all(not row['errors'] and all(d['before_base'] and d['before_tested'] for d in row['dependencies']) for row in report['records']) else 'FAIL'
(r/'docs/exec-plans/evidence/HG-044/preflight.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'])
