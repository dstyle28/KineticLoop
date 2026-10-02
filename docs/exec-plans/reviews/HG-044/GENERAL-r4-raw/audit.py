from pathlib import Path
import ast, hashlib, importlib.util, json, subprocess, yaml, jsonschema
ROOT=Path('/Users/davetian/.codex/worktrees/8578/KineticLoop')
OUT=ROOT/'docs/exec-plans/reviews/HG-044/GENERAL-r4-raw'
HEAD='4bc0b0122245d54649e3f3d03a9acce7d4c6df2a'
BASE='fa729ca4bcca0f2c2e7a2aa0601890d1356b8842'
TESTED='0ce071ace6e8290ae08b6926a5b87709b2c70b08'
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(path,revision=HEAD): return git('show',revision+':'+path)
def digest(data): return hashlib.sha256(data).hexdigest()
def parsed(path,revision=HEAD): return json.loads(blob(path,revision))
report={'reviewed_head_sha':HEAD,'protected_base_sha':BASE,'tested_commit':TESTED,'checks':{}}
def check(name, value, detail=None):
    report['checks'][name]={'pass':bool(value),'detail':detail}
    assert value,name
spec=importlib.util.spec_from_file_location('general_r4_validator',ROOT/'tools/harness/validate_harness.py')
v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
check('exact_head',git('rev-parse','HEAD').decode().strip()==HEAD)
record=yaml.safe_load(blob('docs/exec-plans/governance/HG-044.yaml'))
check('governance_schema',not list(jsonschema.Draft202012Validator(parsed('HARNESS_CHANGE.schema.json')).iter_errors(record)))
check('record_identity_revision',record['base_commit']==BASE and record['tested_commit']==TESTED and record['change_status']=='PASS')
changed=git('diff','--name-only',BASE,HEAD).decode().splitlines()
check('exact_declared_paths',set(changed)==set(record['files_changed']) and len(changed)==202,{'count':len(changed),'paths':changed})
check('declared_write_scope',all(v.matches(p,v.governance_allowed_patterns('HG-044')) for p in changed))
check('tested_suffix',not v.governance_suffix_errors(ROOT,TESTED,HEAD,'HG-044','tested'))
check('no_actual_m3',not v.revision_regular_file(ROOT,'docs/exec-plans/milestones/M3.json',HEAD))
check('no_runtime_ci_or_foreign_artifacts',all(p in {'06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md','CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json','MILESTONE_CLOSURE.schema.json','tools/harness/validate_harness.py','tests/harness/test_m3_milestone_closure.py','docs/harness/M3_CLOSURE_CONTRACT.md','docs/exec-plans/governance/HG-044.yaml'} or p.startswith('docs/exec-plans/evidence/HG-044/') or p.startswith('docs/exec-plans/reviews/HG-044/') for p in changed))
old_schema=parsed('MILESTONE_CLOSURE.schema.json',BASE); new_schema=parsed('MILESTONE_CLOSURE.schema.json')
check('m1_m2_schema_unchanged',old_schema['oneOf']==new_schema['oneOf'][:2] and all(new_schema['$defs'][k]==value for k,value in old_schema['$defs'].items()))
def function_sources(revision):
    source=blob('tools/harness/validate_harness.py',revision).decode(); tree=ast.parse(source)
    return {node.name:ast.get_source_segment(source,node) for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
old_functions=function_sources(BASE); new_functions=function_sources(HEAD)
modified=[name for name,source in old_functions.items() if new_functions.get(name)!=source]
check('existing_functions_preserved',set(modified)=={'validate','governance_allowed_patterns'},{'count_preserved':len(old_functions)-len(modified),'modified':modified})
check('plan_append_only',blob(v.PROJECT_PLAN).decode().split('## M3 exit-evidence mapping — HG044')[0]==blob(v.PROJECT_PLAN,BASE).decode()+'\n')
index=parsed('CURRENT_DOCUMENT_INDEX.json')
entries=index['documents']+index['machine_readable']
for e in entries: assert digest(blob(e['path']))==e['sha256'],e['path']
check('index_hashes',True,len(entries))
manifest=parsed('HARNESS_DOCUMENT_MANIFEST.json')
for e in manifest['files']:
    data=blob(e['path']); assert len(data)==e['bytes'] and digest(data)==e['sha256'],e['path']
check('manifest_hashes_bytes',True,len(manifest['files']))
frozen=parsed('FROZEN_BASELINE.json')
check('frozen_baseline_unchanged',blob('FROZEN_BASELINE.json')==blob('FROZEN_BASELINE.json',BASE))
for e in frozen['files']: assert blob(e['path'])==blob(e['path'],BASE) and digest(blob(e['path']))==e['sha256']
check('frozen_authorities',not v.m3_frozen_authority_errors(ROOT,HEAD),len(frozen['files']))
captures=[]
for path in changed:
    if path.startswith('docs/exec-plans/evidence/HG-044/') and path.endswith('.json'):
        data=parsed(path)
        if 'raw_utf8' in data:
            raw=data['raw_utf8'].encode(); assert digest(raw)==data['raw_sha256'] and len(raw)==data['raw_byte_count'],path
            assert type(data['exit_code']) is int
            assert data['result']==('PASS' if data['exit_code']==0 else 'FAIL')
            captures.append({'path':path,'result':data['result'],'exit_code':data['exit_code'],'raw_sha256':digest(raw)})
check('retained_raw_capture_integrity',True,{'count':len(captures),'captures':captures})
selected=[]
for check_record in record['checks_run']:
    path=check_record['evidence_ref']; data=parsed(path)
    assert data['tested_commit']==TESTED and data['base_commit']==BASE and data.get('result',data.get('status'))=='PASS'
    if 'raw_utf8' in data:
        assert type(data['exit_code']) is int and data['exit_code']==0 and data['command']==check_record['command']
    selected.append({'check_id':check_record['check_id'],'path':path,'sha256':digest(blob(path)),'raw_sha256':data.get('raw_sha256'),'output':data.get('raw_utf8')})
check('selected_capture_bindings',True,selected)
integrity=parsed('docs/exec-plans/evidence/HG-044/capture-integrity-0ce071a.json')
for e in integrity['records']:
    raw=parsed(e['path']); assert e['sha256']==digest(blob(e['path'])) and e['raw_sha256']==raw['raw_sha256'] and e['raw_byte_count']==raw['raw_byte_count']
check('selected_integrity_report',integrity['status']=='PASS' and integrity['tested_commit']==TESTED,len(integrity['records']))
for key,count in [('focused',88),('harness',878),('unit',234)]:
    data=parsed(f'docs/exec-plans/evidence/HG-044/{key}-0ce071a.json'); assert f'{count} passed' in data['raw_utf8']
check('selected_executed_counts',True,{'focused':88,'harness':878,'unit':234})
broad=parsed('docs/exec-plans/evidence/HG-044/diff-0ce071a.json')
check('broad_failure_retained_unselected',broad['result']=='FAIL' and broad['exit_code']==2 and not any(e['check_id']=='diff' for e in selected))
proc=subprocess.run(['git','diff','--check',BASE,TESTED],cwd=ROOT,capture_output=True)
check('broad_failure_exact_raw',proc.returncode==2 and proc.stdout.decode()==broad['raw_utf8'])
patch=blob('docs/exec-plans/reviews/HG-044/PROTOCOL-r3-raw/complete-diff.patch').decode().splitlines()
for line in [7,10391,10392,10405,10406,10738]: assert patch[line-1]==' '
check('broad_failure_context_spaces_only',True)
proc=subprocess.run(['git','diff','--check',BASE,HEAD,'--','.',':(exclude)docs/exec-plans/reviews/HG-044/**'],cwd=ROOT,capture_output=True)
check('source_diff_excludes_only_own_review',proc.returncode==0,{'command':proc.args,'exit_code':proc.returncode,'stdout':proc.stdout.decode(),'stderr':proc.stderr.decode()})
backlog=parsed(v.BACKLOG); tasks={t['id']:t for t in backlog['tasks']}
check('exact16_and_separate_kl074',v.M3_TASK_IDS=={f'KL-{n:03}' for n in range(19,30)}|{f'KL-{n:03}' for n in range(75,80)} and tasks['KL-074']['milestone']=='M1')
contracts=[]
for mapping in v.M3_EXIT_TASK_CHECKS.values():
    for task,ids in mapping.items():
        for cid in ids:
            c=next(c for c in tasks[task]['check_contracts'] if c['check_id']==cid)
            assert v.canonical_value_sha(c)==v.M3_CHECK_CONTRACT_DIGESTS[task+':'+cid]
            assert c['command'] in v.M3_REGRESSION_COMMANDS
            contracts.append(task+':'+cid)
check('named_check_contracts_and_fresh_selectors',True,{'count':len(contracts),'contracts':contracts,'commands_count':len(v.M3_REGRESSION_COMMANDS)})
schemas=[jsonschema.Draft202012Validator(parsed(p)) for p in ['MILESTONE_CLOSURE.schema.json','INTEGRATION_RECORD.schema.json','THREAD_RESULT.schema.json','THREAD_REVIEW.schema.json']]
for name,fn in [('M1',v.milestone_closure_errors),('M2',v.m2_milestone_closure_errors)]:
    check(name+'_closure',not fn(ROOT,parsed(f'docs/exec-plans/milestones/{name}.json'),*schemas,backlog,tasks))
records={}; missing=[]; pending=list(v.M3_TASK_IDS|{'KL-074'})
while pending:
    name=pending.pop()
    if name in records or name in missing: continue
    p=f'docs/exec-plans/integrations/{name}.json'
    if not v.revision_regular_file(ROOT,p,HEAD): missing.append(name); continue
    r=parsed(p); records[name]=r
    errors=v.integration_record_errors(ROOT,Path(p),r,*schemas[1:],tasks); assert not errors,(name,errors)
    for key in ['result_commit','reviewed_head_sha','review_record_commit','merge_commit']: assert v.is_ancestor(ROOT,r[key],HEAD),(name,key)
    result=v.load_artifact_at_revision(ROOT,v.result_paths_at_revision(ROOT,name,r['reviewed_head_sha'])[0],r['reviewed_head_sha'])
    for dep in tasks[name]['depends_on']:
        dr=parsed(f'docs/exec-plans/integrations/{dep}.json')
        for key in ['base_commit','tested_commit']: assert v.is_ancestor(ROOT,dr['merge_commit'],result[key]),(name,dep,key)
    pending.extend(tasks[name]['depends_on'])
check('recursive_integrations_and_dependency_ancestry',set(missing)=={'KL-028','KL-029'},{'valid_count':len(records),'missing':sorted(missing),'valid':sorted(records)})
rows=v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(),'Boundary layer ledger')
check('exact31_boundary_ledger',len(rows)==31 and sum(r['disposition']=='KL028_PLANNED_EXECUTABLE' for r in rows)==19 and all(r['status']=='NOT_RUN' for r in rows) and not v.m3_boundary_layer_errors(rows,parsed('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements']),{'rows':rows})
check('m1_m2_hg043_paths_unchanged',all(blob(p)==blob(p,BASE) for p in ['docs/exec-plans/milestones/M1.json','docs/exec-plans/milestones/M2.json','docs/exec-plans/governance/HG-043.yaml']))
report['status']='PASS'; (OUT/'audit.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps({'status':'PASS','checks':len(report['checks']),'reviewed_head_sha':HEAD}))
