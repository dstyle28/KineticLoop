import importlib.util
import json
from pathlib import Path
root=Path.cwd();out=root/'docs/exec-plans/reviews/HG-044/DB_CONCURRENCY-r5-raw'
reviewed='027bc2368e36e28aa9956489cb57af297882d671'
spec=importlib.util.spec_from_file_location('v',root/'tools/harness/validate_harness.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
tasks={t['id']:t for t in v.load_artifact_at_revision(root,v.BACKLOG,reviewed)['tasks']}
rows=[]
for mapping in v.M3_EXIT_TASK_CHECKS.values():
    for name,ids in mapping.items():
        path=f'docs/exec-plans/integrations/{name}.json'
        if not v.revision_regular_file(root,path,reviewed):continue
        record=v.load_artifact_at_revision(root,path,reviewed);bound=record['reviewed_head_sha']
        result_path=v.result_paths_at_revision(root,name,bound)[0]
        result=v.load_artifact_at_revision(root,result_path,bound)
        contracts={c['check_id']:c for c in tasks[name]['check_contracts']}
        commands={c['check_id']:c for c in result['commands_run']}
        for cid in ids:
            check=commands[cid];contract=contracts[cid]
            raw=check['evidence_ref']
            witness={'task_identity':tasks[name]['task_identity'],'check_id':cid,
                     'tested_commit':result['tested_commit'],'command':check['command'],'result':'PASS',
                     'oracle_sha256':v.canonical_value_sha(contract['pass_oracle']),
                     'result_artifact':{'path':result_path,'revision':bound,'sha256':v.blob_sha_at_revision(root,result_path,bound)},
                     'raw':{'path':raw,'revision':bound,'sha256':v.blob_sha_at_revision(root,raw,bound)}}
            assert not v.m3_task_check_errors(root,witness,name,cid,tasks[name],record,reviewed)
            rows.append({'task':name,'check_id':cid,'raw':witness['raw'],
                         'executed_count':v.m3_pytest_count(v.git(root,'show',bound+':'+raw).decode())})
(out/'witnesses.json').write_text(json.dumps({'status':'PASS','historical_available_witnesses':rows},indent=2)+'\n')
print('WITNESS_PASS '+str(len(rows)))
