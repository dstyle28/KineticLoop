from pathlib import Path
import importlib.util,json,subprocess,yaml,xml.etree.ElementTree as ET
ROOT=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
SOURCE='0557dbd8f2196df871af20c0982bdc2526f0ad6e';REVIEW='4073ca6ef64a625c398483fb5fbfe41b1ef3237c';BASE='b877db0edd2e4550d6ea81750656112fb7f2e223'
s=importlib.util.spec_from_file_location('final_db_ce',ROOT/'tools/harness/compact_evidence.py');ce=importlib.util.module_from_spec(s);s.loader.exec_module(ce)
prefix='docs/exec-plans/evidence/HG-051/final-0557dbd/'
def git(*args):return ce.git(ROOT,*args)
assert git('rev-parse','HEAD').decode().strip()==REVIEW
git('merge-base','--is-ancestor',SOURCE,REVIEW)
paths=git('diff','--name-only',SOURCE,REVIEW).decode().splitlines()
assert all(p.startswith(prefix) or p=='docs/exec-plans/governance/HG-051.yaml' for p in paths)
gov=yaml.safe_load(ce.blob(ROOT,'docs/exec-plans/governance/HG-051.yaml',REVIEW))
assert gov['tested_commit']==SOURCE and gov['change_status']=='PASS' and gov['frozen_impact']=='NONE'
execution=json.loads(ce.read(ROOT,prefix+'EXECUTION.json',REVIEW))
assert execution['tested_commit']==execution['source_end_sha']==SOURCE and execution['source_end_status']==''
executions={r['check_id']:r for r in execution['executions']}
assert len(executions)==len(gov['checks_run'])==10
summary=[]
for check in gov['checks_run']:
    actual=executions[check['check_id']]
    assert check['result']=='PASS' and actual['exit_code']==0 and actual['tested_commit']==SOURCE and actual['command']==check['command']
    raw=ce.read(ROOT,check['evidence_ref'],REVIEW,tested=SOURCE,command=check['command'],exit_code=0)
    summary.append({'check_id':check['check_id'],'exit_code':0,'raw_bytes':len(raw),'raw_sha256':ce.digest(raw)})
counts={}
for name,expected in [('focused-junit',190),('harness-junit-xml',1492),('unit-junit',241)]:
    raw=ce.read(ROOT,prefix+name+'.json',REVIEW,tested=SOURCE,exit_code=0)
    xml=ET.fromstring(raw);suites=[xml] if xml.tag=='testsuite' else list(xml.iter('testsuite'))
    value={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert value==dict(tests=expected,failures=0,errors=0,skipped=0),(name,value)
    counts[name]=value
aux={}
for name in ['harness-collection-json','harness-execution-json','harness-manifest-json']:
    value=json.loads(ce.read(ROOT,prefix+name+'.json',REVIEW,tested=SOURCE,exit_code=0))
    aux[name]={'keys':sorted(value),'type':type(value).__name__}
    Path('/private/tmp/hg051-r2-db-'+name+'.json').write_text(json.dumps(value,indent=2)+'\n')
inv=json.loads(ce.read(ROOT,prefix+'inventory_roundtrip.json',REVIEW,tested=SOURCE,exit_code=0))
assert inv['tested_commit']==SOURCE and inv['status']=='PASS' and inv['installed_layout'] and not inv['installed_schema_file']
assert len(inv['results'])==4 and all(r['exact'] for r in inv['results']) and not inv['storage_audit']['errors']
budget=ce.audit(ROOT,BASE,REVIEW,'HG-051');assert not budget['errors'],budget
report={'status':'PASS','reviewed_head_sha':REVIEW,'tested_commit':SOURCE,'governance_checks':summary,'junit_counts':counts,'auxiliary_inventory':aux,'installed_inventory_verified':True,'budget':budget,'tested_reviewed_delta':'Own governance and final clean-check evidence only; source unchanged','App_fullDB_completion':'NOT_RUN by reviewer; parent-owned mandatory final gate'}
print(json.dumps(report,indent=2))
