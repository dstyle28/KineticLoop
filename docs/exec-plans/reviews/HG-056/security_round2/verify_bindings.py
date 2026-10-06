"""Read exact committed HG056 machine artifacts; emit metadata only."""
import collections
import hashlib
import json
import re
import subprocess
import types
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
R = '388557f1e404de0835d3f643ab43217b0b88665f'
T = '272784e9966206c7ed35acccf9dcb2cb67f33d9d'
B = '3ec7f7a38d974256a928c3687f63e4d90019e42b'
D = 'docs/exec-plans/evidence/HG-056/checks-repair-' + T + '-1cdb6604/'
def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path): return git('show', R + ':' + path)
def pin(path):
    tree = git('ls-tree', '-l', R, '--', path).decode().strip()
    assert tree.startswith(('100644 blob ', '100755 blob ')) and tree.split('\t')[1] == path
    raw = blob(path)
    return {'path': path, 'revision': R, 'mode': tree.split()[0], 'git_blob': tree.split()[2], 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
ce = types.ModuleType('pinned_ce'); ce.__file__ = str(ROOT/'tools/harness/compact_evidence.py')
exec(compile(blob('tools/harness/compact_evidence.py'), 'pinned_decoder', 'exec'), ce.__dict__)
run = json.loads(blob(D+'RUN.json'))
assert run['tested_commit'] == T and run['base_commit'] == B
for ancestor, descendant in ((B,T),(T,R)):
    git('merge-base','--is-ancestor',ancestor,descendant)
checks = []; raw_by_name = {}; pins = [pin(D+'RUN.json')]
for check in run['checks']:
    path = check['evidence_ref']; envelope = json.loads(blob(path))
    assert envelope['tested_commit'] == T and envelope['command'] == check['command'] and envelope['exit_code'] == check['exit_code']
    raw = ce.read(ROOT,path,R,tested=T,command=check['command'],exit_code=check['exit_code'])
    assert ce.digest(raw) == check['raw_sha256'] and len(raw) == check['raw_bytes']
    raw_by_name[check['check_id']] = raw
    counts = {kind:int(count) for count,kind in re.findall(rb'\b(\d+) (passed|failed|skipped|errors?|deselected|xfailed|xpassed)\b',raw)}
    checks.append({'check_id':check['check_id'],'command':check['command'],'exit_code':check['exit_code'],'reported_result':check['result'],'read_binding':'PASS','raw_sha256':ce.digest(raw),'raw_bytes':len(raw),'observed_summary_counts':{k.decode():v for k,v in counts.items()}})
    pins.extend((pin(path),pin(envelope['payload'])))
commands = {check['check_id']:check['command'] for check in run['checks']}
artifacts = {}
for prefix, group, command in (('harness',run['harness_artifacts'],commands['affected_harness']),('full-collection',run['full_collection_artifacts'],commands['full_collection'])):
    for item in group:
        path = item['evidence_ref']; env = json.loads(blob(path))
        raw = ce.read(ROOT,path,R,tested=T,command=command,exit_code=0)
        artifacts[item['name']] = raw
        pins.extend((pin(path),pin(env['payload'])))

def phase_evidence(prefix, expected):
    manifest = json.loads(artifacts[prefix+'-manifest.json.json'])
    collected = json.loads(artifacts[prefix+'-collection.json.json'])
    executed = json.loads(artifacts[prefix+'-execution.json.json'])
    assert manifest['tested_commit'] == T and not manifest['dirty_source'] and manifest['exit_code'] == 0 and manifest['pytest_exit_code'] == 0
    assert not manifest['errors'] and not collected['errors'] and not executed['errors']
    ids = collected['collections']['serial']; assert len(ids) == len(set(ids)) == expected
    for entry in manifest['files']:
        data = artifacts[prefix+'-'+entry['path']+'.json']
        assert len(data) == entry['bytes'] and ce.digest(data) == entry['sha256']
    junit = ET.fromstring(artifacts[prefix+'-junit.xml.json'])
    cases = junit.findall('.//testcase')
    summary = {'mode':manifest['mode'],'tested_commit':manifest['tested_commit'],'dirty_source':manifest['dirty_source'],'command':manifest['command'],'collection_command':manifest['collection_command'],'collected_identities':len(ids),'ordered_collection_sha256':ce.digest(json.dumps(ids,separators=(',',':')).encode()),'workers':manifest['workers'],'started_count':len(executed['started']),'reports_count':len(executed['reports']),'worker_collection_counts':{k:len(v) for k,v in executed['collections'].items()},'junit_cases':len(cases),'junit_failures':len(junit.findall('.//failure')),'junit_errors':len(junit.findall('.//error')),'junit_skips':len(junit.findall('.//skipped')),'all_manifest_files_match_raw':True,'execution_complete':manifest['execution_complete']}
    if prefix == 'harness':
        started = executed['started']; assert len(started) == len(set(started)) == expected and set(started) == set(ids)
        for worker_ids in executed['collections'].values(): assert worker_ids == ids
        reports = collections.defaultdict(list)
        for record in executed['reports']: reports[record['nodeid']].append(record)
        assert set(reports) == set(ids)
        assert all(len(items) == 3 and {item['phase'] for item in items} == {'setup','call','teardown'} and all(item['outcome'] == 'passed' for item in items) for items in reports.values())
        compact = [item for item in ids if item.startswith('tests/harness/test_compact_evidence.py::')]
        assert len(compact) == 733
        assert len(cases) == expected and summary['junit_failures'] == summary['junit_errors'] == summary['junit_skips'] == 0
        junit_ids = ['/'.join(item.attrib['classname'].split('.')[:3])+'.py::'+'::'.join(item.attrib['classname'].split('.')[3:]+[item.attrib['name']]) for item in cases]
        assert set(junit_ids) == set(ids)
        summary.update(compact_case_identities=len(compact),all_three_phases_passed=True,junit_identity_set_matches=True,execution_identity_set_matches=True)
    else:
        assert not executed['started'] and not executed['reports'] and len(cases) == 0
        assert executed['collections']['serial'] == ids and manifest['mode'] == 'COLLECTION_ONLY' and not manifest['execution_complete']
        summary['executed_identities'] = 0
    return summary

phases = {'affected_harness':phase_evidence('harness',737),'full_collection':phase_evidence('full-collection',1963)}
assert re.search(rb'\b103 passed\b',raw_by_name['installed_decoder_isolation'])
assert re.search(rb'\b737 passed\b',raw_by_name['affected_harness'])
scope = json.loads(raw_by_name['scope']); assert scope['base'] == B and scope['head'] == T and scope['status'] == 'PASS'
actual_paths = git('diff','--no-renames','--name-only','-z',B,T).decode().split('\0')[:-1]
assert actual_paths == scope['changed_paths']
path_modes = collections.Counter()
for path in actual_paths:
    entry = git('ls-tree','-z',T,'--',path)
    assert entry.startswith((b'100644 blob ',b'100755 blob ')) and entry.split(b'\t')[1].rstrip(b'\0').decode() == path
    path_modes[entry.split()[0].decode()] += 1
critical = ['tools/harness/compact_evidence.py','tools/harness/validate_harness.py','tests/harness/test_compact_evidence.py','tests/harness/test_validator.py','docs/harness/EVIDENCE_STORAGE_POLICY.md','docs/harness/HARNESS_GOVERNANCE_CONTRACT.md','docs/exec-plans/evidence/HG-056/verify_scope.py']
assert all(git('show',T+':'+path) == blob(path) for path in critical)
pins.extend(pin(path) for path in critical)
prior_ref = D+'PRIOR_REQUIRED_CHECKS.json'; prior=json.loads(blob(prior_ref)); assert prior['tested_commit'] != T
prior_meta=[]
for check in prior['checks_run']:
    env=json.loads(blob(check['evidence_ref']))
    raw=ce.read(ROOT,check['evidence_ref'],R,tested=prior['tested_commit'],command=check['command'],exit_code=0 if check['result']=='PASS' else 1)
    item={'check_id':check['check_id'],'source_tested_commit':prior['tested_commit'],'result':check['result'],'exit_code':env['exit_code'],'bound_read':'PASS','raw_sha256':ce.digest(raw),'raw_bytes':len(raw)}
    if check['check_id']=='compatibility':
        objects=[]; decoder=json.JSONDecoder(); text=raw.decode(); cursor=0
        while cursor<len(text):
            start=text.find('{',cursor)
            if start<0: break
            try: value,length=decoder.raw_decode(text[start:])
            except json.JSONDecodeError: cursor=start+1;continue
            if isinstance(value,dict): objects.append(value)
            cursor=start+length
        item['compatibility_objects']=objects
        assert any(len(obj.get('expected_maps',[]))==2 and len(obj.get('validated_maps',[]))==1 for obj in objects)
    prior_meta.append(item)
pins.extend((pin(prior_ref),pin(D+'SOURCE_INSPECTION_ADJUDICATION.md'),pin('docs/exec-plans/governance/HG-056.yaml')))
result={'R':R,'T':T,'B':B,'checks':checks,'phases':phases,'isolated_count_source':'Actual captured stdout: 103 passed; no separate ordered isolated identity artifact is claimed','scope':{'head':T,'changed_path_count':len(actual_paths),'tree_modes':dict(path_modes),'exact_changed_paths_match':True,'frozen_paths_verified':scope['frozen_paths_verified']},'critical_source_tested_to_result_identical':True,'tested_to_result_changed_paths':git('diff','--name-only',T,R).decode().splitlines(),'prior_actual_outcomes':prior_meta,'source_inspection':'Root deferred authority clarification, NOT_IMPLEMENTED; strict original HG047 suffix unchanged','pins':list({p['path']:p for p in pins}.values()),'raw_logs_emitted':False,'complete_cycles_rerun':False}
(OUT/'evidence-bindings.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'R':R,'T':T,'B':B,'phases':phases,'checks_verified':len(checks),'scope':result['scope'],'prior_outcomes_verified':len(prior_meta)},indent=2))
