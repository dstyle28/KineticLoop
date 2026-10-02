"""Independent exact-revision PROTOCOL audit; no task or runtime mutations."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent
HEAD = '4bc0b0122245d54649e3f3d03a9acce7d4c6df2a'
BASE = 'fa729ca4bcca0f2c2e7a2aa0601890d1356b8842'
TESTED = '0ce071ace6e8290ae08b6926a5b87709b2c70b08'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, rev=HEAD):
    mode = git('ls-tree', rev, '--', path).decode().split()[0]
    assert mode in ('100644', '100755'), (path, rev, mode)
    return git('show', rev + ':' + path)
def load(path, rev=HEAD):
    raw = blob(path, rev)
    return yaml.safe_load(raw) if path.endswith('.yaml') else json.loads(raw)
def digest(raw):
    return hashlib.sha256(raw).hexdigest()
def module(path):
    spec = importlib.util.spec_from_file_location('protocol_r4_validator', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
v = module(ROOT / 'tools/harness/validate_harness.py')
assert git('rev-parse', 'HEAD').decode().strip() == HEAD
assert blob('tools/harness/validate_harness.py') == (ROOT / 'tools/harness/validate_harness.py').read_bytes()
schemas = [jsonschema.Draft202012Validator(load(p)) for p in (
    'MILESTONE_CLOSURE.schema.json', 'INTEGRATION_RECORD.schema.json',
    'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]
backlog = load(v.BACKLOG)
tasks = {t['id']: t for t in backlog['tasks']}
result = load('docs/exec-plans/governance/HG-044.yaml')
assert result['base_commit'] == BASE and result['tested_commit'] == TESTED
changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
assert len(changed) == 202 and set(changed) == set(result['files_changed'])
assert all(v.matches(p, v.governance_allowed_patterns('HG-044')) for p in changed)
assert not v.governance_suffix_errors(ROOT, TESTED, HEAD, 'HG-044', 'tested')
assert subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, TESTED], cwd=ROOT).returncode == 0
index = load('CURRENT_DOCUMENT_INDEX.json')
for entry in index['documents'] + index['machine_readable']:
    assert digest(blob(entry['path'])) == entry['sha256'], entry['path']
assert not v.m3_frozen_authority_errors(ROOT, HEAD)
assert git('ls-tree', HEAD, '--', 'docs/exec-plans/milestones/M3.json') == b''
inventory = [{'path':p, 'sha256':digest(blob(p)), 'bytes':len(blob(p))} for p in changed]
# Compare exact legacy function source and schema representations, not only behavior.
def functions(raw):
    src = raw.decode()
    lines = src.splitlines(keepends=True)
    return {n.name: ''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(src).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
before = functions(blob('tools/harness/validate_harness.py', BASE))
after = functions(blob('tools/harness/validate_harness.py'))
legacy = {}
for name in ('milestone_closure_errors','m2_milestone_closure_errors',
             'm2_execution_evidence_errors','integration_record_errors',
             'review_evidence_exists','semantic_result_errors'):
    assert before[name] == after[name], name
    legacy[name] = digest(after[name].encode())
old_schema = load('MILESTONE_CLOSURE.schema.json', BASE)
new_schema = load('MILESTONE_CLOSURE.schema.json')
assert old_schema['oneOf'] == new_schema['oneOf'][:2]
assert all(new_schema['$defs'][k] == val for k,val in old_schema['$defs'].items())
assert not v.milestone_closure_errors(ROOT, load('docs/exec-plans/milestones/M1.json'), *schemas, backlog, tasks)
assert not v.m2_milestone_closure_errors(ROOT, load('docs/exec-plans/milestones/M2.json'), *schemas, backlog, tasks)
# Recursive integration validation and both dependency ancestry boundaries.
pending = list(v.M3_TASK_IDS | {'KL-074'})
records, missing, ancestors = {}, [], []
while pending:
    name = pending.pop()
    if name in records or name in missing:
        continue
    path = f'docs/exec-plans/integrations/{name}.json'
    if not git('ls-tree', HEAD, '--', path):
        missing.append(name)
        continue
    record = load(path)
    records[name] = record
    errors = v.integration_record_errors(ROOT, Path(path), record, *schemas[1:], tasks)
    assert not errors, (name, errors)
    for key in ('result_commit','reviewed_head_sha','review_record_commit','merge_commit'):
        assert v.is_ancestor(ROOT, record[key], HEAD), (name,key)
    paths = v.result_paths_at_revision(ROOT, name, record['reviewed_head_sha'])
    assert len(paths) == 1
    r = load(paths[0], record['reviewed_head_sha'])
    ancestors.append({'task':name,'integration_sha256':digest(blob(path)),
                      'record':record,'base_commit':r['base_commit'],'tested_commit':r['tested_commit']})
    pending.extend(tasks[name]['depends_on'])
assert set(missing) == {'KL-028', 'KL-029'}
edges = []
for name, record in records.items():
    r = load(v.result_paths_at_revision(ROOT,name,record['reviewed_head_sha'])[0], record['reviewed_head_sha'])
    for dep in tasks[name]['depends_on']:
        for key in ('base_commit','tested_commit'):
            passed = v.is_ancestor(ROOT, records[dep]['merge_commit'], r[key])
            assert passed, (dep,name,key)
            edges.append({'dependency':dep,'consumer':name,'boundary':key,'passed':passed})
# Exact active mapping and every pinned full check contract/oracle.
expected = {f'KL-{n:03}' for n in range(19,30)} | {f'KL-{n:03}' for n in range(75,80)}
assert v.M3_TASK_IDS == expected
assert {n for n,t in tasks.items() if t['milestone']=='M3' and t['status']!='SUPERSEDED'} == expected
assert tasks['KL-074']['milestone'] == 'M1'
checks = []
for exit_id, mapping in v.M3_EXIT_TASK_CHECKS.items():
    for name, ids in mapping.items():
        assert len(ids)==len(set(ids))
        for check_id in ids:
            contracts=[c for c in tasks[name]['check_contracts'] if c['check_id']==check_id]
            assert len(contracts)==1
            contract=contracts[0]
            assert v.canonical_value_sha(contract)==v.M3_CHECK_CONTRACT_DIGESTS[name+':'+check_id]
            row={'exit':exit_id,'task':name,'check_id':check_id,'contract':contract,
                 'oracle_sha256':v.canonical_value_sha(contract['pass_oracle'])}
            if name in records:
                record=records[name]
                path=v.result_paths_at_revision(ROOT,name,record['reviewed_head_sha'])[0]
                r=load(path,record['reviewed_head_sha'])
                commands=[c for c in r['commands_run'] if c['check_id']==check_id]
                assert len(commands)==1 and commands[0]['command']==contract['command'] and commands[0]['result']=='PASS'
                raw=blob(commands[0]['evidence_ref'],record['reviewed_head_sha'])
                row['historical_raw_count']=v.m3_pytest_count(raw.decode())
                row['historical_raw_sha256']=digest(raw)
            checks.append(row)
assert len(checks)==52 and len(v.M3_CHECK_CONTRACT_DIGESTS)==52
rows=v.packet_json_section(blob('docs/exec-plans/active/KL-028.md').decode(),'Boundary layer ledger')
assert len(rows)==31 and len([r for r in rows if r['disposition']!='KL028_PLANNED_EXECUTABLE'])==12
assert not v.m3_boundary_layer_errors(rows, load('KineticLoop_Acceptance_Spec_v1.2.2.json')['supplemental_boundary_requirements'])
captures=[]
integrity=load('docs/exec-plans/evidence/HG-044/capture-integrity-0ce071a.json')
for check in result['checks_run']:
    p=check['evidence_ref']
    capture=load(p)
    if check['check_id']=='scope':
        assert capture['status']=='PASS' and all(capture['checks'].values())
    else:
        raw=capture['raw_utf8'].encode()
        assert capture['raw_sha256']==digest(raw) and capture['raw_byte_count']==len(raw)
        assert capture['tested_commit']==TESTED and capture['base_commit']==BASE
        assert type(capture['exit_code']) is int and capture['exit_code']==0 and capture['result']=='PASS'
        assert capture['command']==check['command']
        pin=next(x for x in integrity['records'] if x['check_id']==check['check_id'])
        assert pin['sha256']==digest(blob(p)) and pin['raw_sha256']==digest(raw)
        if check['check_id'] in ('focused','harness','unit'):
            assert v.m3_pytest_count(raw.decode())=={'focused':88,'harness':878,'unit':234}[check['check_id']]
    captures.append({'check_id':check['check_id'],'path':p,'sha256':digest(blob(p))})
assert load('docs/exec-plans/evidence/HG-044/diff-0ce071a.json')['result']=='FAIL'
suffix=git('rev-list','--reverse',TESTED+'..'+HEAD).decode().splitlines()
report={'reviewed_head_sha':HEAD,'protected_base':BASE,'tested_commit':TESTED,
        'status':'PASS','changed_path_inventory':inventory,'selected_captures':captures,
        'legacy_function_hashes':legacy,'legacy_schema_branches_preserved':True,
        'active_m3_ids':sorted(expected),'missing_integration_records':sorted(missing),
        'existing_integration_records':ancestors,'dependency_edges':edges,
        'pinned_checks':checks,'canonical_boundary_ledger':rows,'legal_tested_suffix':suffix,
        'prior_failed_reviews_retained':[
            load('docs/exec-plans/reviews/HG-044/rounds/'+r+'/PROTOCOL.json')['status']
            for r in ('351f0ed','19dc5a4')]}
assert report['prior_failed_reviews_retained']==['CHANGES_REQUIRED','CHANGES_REQUIRED']
(OUT/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':'PASS','reviewed_head_sha':HEAD,'paths':len(changed),
                  'pinned_checks':len(checks),'dependency_edges':len(edges),
                  'existing_integrations':len(records),'missing':missing}))
