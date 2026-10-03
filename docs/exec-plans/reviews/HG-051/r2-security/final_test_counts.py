from pathlib import Path
import importlib.util,json,xml.etree.ElementTree as ET,yaml
ROOT=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop');W=Path('/private/tmp/hg051-r2-security-20261003')
FINAL='4073ca6ef64a625c398483fb5fbfe41b1ef3237c';SOURCE='0557dbd8f2196df871af20c0982bdc2526f0ad6e';D='docs/exec-plans/evidence/HG-051/final-0557dbd/'
spec=importlib.util.spec_from_file_location('security_counts',W/'gate/tools/harness/compact_evidence.py');ce=importlib.util.module_from_spec(spec);spec.loader.exec_module(ce)
gov=yaml.safe_load(ce.blob(ROOT,'docs/exec-plans/governance/HG-051.yaml',FINAL)); commands={x['check_id']:x['command'] for x in gov['checks_run']}
counts=[]
for label,file,expected,command in [('focused','focused-junit.json',190,commands['focused']),('harness','harness-junit-xml.json',1492,commands['harness']),('unit','unit-junit.json',241,commands['unit'])]:
 raw=ce.read(ROOT,D+file,FINAL,tested=SOURCE,command=command,exit_code=0); doc=ET.fromstring(raw); cases=list(doc.iter('testcase'))
 assert len(cases)==expected,(label,len(cases)); assert not list(doc.iter('failure')) and not list(doc.iter('error')) and not list(doc.iter('skipped'))
 counts.append(dict(suite=label,tests=len(cases),failures=0,errors=0,skipped=0,sha256=ce.digest(raw)))
print(json.dumps(dict(status='PASS',reviewed_sha=FINAL,source_sha=SOURCE,junit=counts),indent=2))
for label in ('harness-collection-json','harness-execution-json'):
 raw=ce.read(ROOT,D+label+'.json',FINAL,tested=SOURCE,command=commands['harness'],exit_code=0); data=json.loads(raw)
 print(json.dumps(dict(label=label,keys=list(data),sha256=ce.digest(raw),summary={k:v for k,v in data.items() if not isinstance(v,(dict,list))}),indent=2))
 print(json.dumps({k:list(v)[:12] if isinstance(v,dict) else {'length':len(v),'first':v[:1]} for k,v in data.items() if isinstance(v,(dict,list))},indent=2))
collection=json.loads(ce.read(ROOT,D+'harness-collection-json.json',FINAL,tested=SOURCE,command=commands['harness'],exit_code=0))
execution=json.loads(ce.read(ROOT,D+'harness-execution-json.json',FINAL,tested=SOURCE,command=commands['harness'],exit_code=0))
expected_nodes=collection['collections']['serial']
assert collection['exit_code']==execution['exit_code']==0 and not collection['errors'] and not execution['errors']
assert len(expected_nodes)==len(set(expected_nodes))==1492
assert len(execution['started'])==len(set(execution['started']))==1492
assert set(expected_nodes)==set(execution['started'])
assert all(set(nodes)==set(expected_nodes) and len(nodes)==1492 for nodes in execution['collections'].values())
assert len(execution['reports'])==3*1492 and all(r['outcome']=='passed' for r in execution['reports'])
for phase in ('setup','call','teardown'):
 reports=[r['nodeid'] for r in execution['reports'] if r['phase']==phase]
 assert len(reports)==len(set(reports))==1492 and set(reports)==set(expected_nodes)
print(json.dumps(dict(status='PASS',harness_collected=1492,harness_started=1492,phases_per_test=3,all_phase_outcomes='passed',collection_execution_exact=True)))
