import gzip, hashlib, json, subprocess
from pathlib import Path
import yaml
ROOT=Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
BASE='391c9198fa8ec647e377a0572700bc7568468c85'
TESTED='536c9b7b7c5bfa9b36a0b38e513bce34ed6eb31d'
REVIEWED='b7370940c8b9165f471322baaeef7d9e250dfac6'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)
def sha(data):
    return hashlib.sha256(data).hexdigest()
def blob(path, rev=REVIEWED):
    entry=git('ls-tree','-z',rev,'--',path).rstrip(b'\0')
    metadata, listed=entry.split(b'\t')
    mode, kind, oid=metadata.split()
    assert listed.decode()==path and mode in (b'100644',b'100755') and kind==b'blob',path
    return git('cat-file','blob',oid.decode())
def decoded(path):
    record=json.loads(blob(path))
    payload=record['payload']
    assert payload==str(Path(path).parent/(record['raw_sha256']+'.gz'))
    data=blob(payload)
    assert len(data)==record['stored_bytes'] and sha(data)==record['stored_sha256']
    raw=gzip.decompress(data)
    assert len(raw)==record['raw_bytes'] and sha(raw)==record['raw_sha256']
    return record,raw
result=yaml.safe_load(blob('docs/exec-plans/governance/HG-047.yaml'))
assert result['base_commit']==BASE and result['tested_commit']==TESTED
execution=json.loads(blob('docs/exec-plans/evidence/HG-047/round2-536c9b7/execution.json'))
checks=[]
for check in result['checks_run']:
    r,raw=decoded(check['evidence_ref'])
    e=execution['checks'][check['check_id']]
    assert check['result']=='PASS' and r['exit_code']==e['exit_code']==0
    assert r['command']==check['command']==e['command']
    assert r['tested_commit']==e['tested']==TESTED
    assert r['test_counts']==e['test_counts']
    text=raw.decode()
    if check['check_id']=='harness': assert '1306 passed' in text and 'failed' not in text
    if check['check_id']=='unit': assert '241 passed' in text and 'failed' not in text
    if check['check_id']=='authority': assert 'HARNESS_CHECK_PASS' in text and 'HARNESS_CHECK_FAIL' not in text
    checks.append({'check':check['check_id'],'exit_code':r['exit_code'],'command':r['command'],'raw_sha256':sha(raw),'raw_bytes':len(raw),'counts':r['test_counts'],'tail':text[-1400:]})
protected=['FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','src','migrations','tests/db','.github/workflows','KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json','MILESTONE_CLOSURE.schema.json','docs/exec-plans/active/KL-080.md','tools/harness/db_policy.py','tools/harness/db_ci.py','tools/harness/github_app.py','tools/harness/gate_validate.py','tools/harness/gate_pytest.py','tools/harness/db_ci_pytest.py','tools/harness/local_db']
for identity in ('HG-045','HG-046'):
    protected += [f'docs/exec-plans/{kind}/{identity}' for kind in ('evidence','reviews')]
    protected += [f'docs/exec-plans/governance/{identity}.yaml']
protected += [e['path'] for e in json.loads(blob('FROZEN_BASELINE.json',BASE))['files']]
assert not git('diff','--name-only',BASE,REVIEWED,'--',*protected)
source=['tools/harness/compact_evidence.py','tools/harness/validate_harness.py','tools/harness/local_gate.py','tests/harness/test_compact_evidence.py','tests/harness/test_local_gate.py','tests/harness/test_m3_milestone_closure.py','tests/harness/test_validator.py','tests/harness/test_review_evidence_provenance.py']
assert not git('diff','--name-only',TESTED,REVIEWED,'--',*source)
assert all((ROOT/p).read_bytes()==blob(p) for p in source)
all_paths=git('ls-tree','-r','--name-only',REVIEWED,'--','docs/exec-plans/evidence/HG-047/').decode().splitlines()
all_envelopes=0
historical=[]
for path in all_paths:
    if not path.endswith('.json') or path.endswith('/execution.json'): continue
    r,raw=decoded(path)
    all_envelopes+=1
    if r['exit_code']:
        historical.append({'path':path,'exit_code':r['exit_code'],'tested_commit':r['tested_commit'],'raw_bytes':len(raw),'tail':raw.decode(errors='replace')[-1200:]})
assert any('/development-166bf3e/' in x['path'] and x['exit_code']!=0 for x in historical)
assert any('/development-b30a9c6/' in x['path'] and x['exit_code']!=0 for x in historical)
print(json.dumps({'status':'PASS','base':BASE,'tested':TESTED,'reviewed':REVIEWED,'decoder':'stdlib gzip and SHA256, no candidate decoder import','selected_checks':checks,'all_envelopes_verified':all_envelopes,'preserved_historical_failures':historical,'protected_paths_unchanged':sorted(set(protected)),'working_source_matches_reviewed':source,'tested_to_reviewed_source_unchanged':True},indent=2))
