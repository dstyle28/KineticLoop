import importlib.util,json,subprocess,yaml,xml.etree.ElementTree as ET
from pathlib import Path
R=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop');T='0557dbd8f2196df871af20c0982bdc2526f0ad6e';H='4073ca6ef64a625c398483fb5fbfe41b1ef3237c';B='b877db0edd2e4550d6ea81750656112fb7f2e223';D='docs/exec-plans/evidence/HG-051/final-0557dbd/'
def g(*a):return subprocess.check_output(['git',*a],cwd=R)
s=importlib.util.spec_from_file_location('final_ce',R/'tools/harness/compact_evidence.py');ce=importlib.util.module_from_spec(s);s.loader.exec_module(ce)
g('merge-base','--is-ancestor',T,H); suffix=g('rev-list','--reverse',T+'..'+H).decode().splitlines()
for sha in suffix:
 assert len(g('rev-list','--parents','-n','1',sha).decode().split())==2
 paths=g('diff-tree','--no-commit-id','--name-only','-r',sha).decode().splitlines(); assert all(p.startswith('docs/exec-plans/evidence/HG-051/') or p=='docs/exec-plans/governance/HG-051.yaml' for p in paths)
record=yaml.safe_load(ce.blob(R,'docs/exec-plans/governance/HG-051.yaml',H));assert record['change_status']=='PASS' and record['tested_commit']==T and record['base_commit']==B
execution=json.loads(ce.blob(R,D+'EXECUTION.json',H));assert execution['tested_commit']==execution['source_end_sha']==T and execution['source_end_status']==''
byid={x['check_id']:x for x in execution['executions']};assert len(byid)==10;decoded={};checks=[]
for c in record['checks_run']:
 r=byid[c['check_id']];assert c['result']=='PASS' and c['command']==r['command'] and r['exit_code']==0 and r['tested_commit']==T
 raw=ce.read(R,c['evidence_ref'],H,tested=T,command=c['command'],exit_code=0);checks.append(dict(check_id=c['check_id'],raw_bytes=len(raw)))
for p in g('ls-tree','-r','--name-only',H,'--',D).decode().splitlines():
 if p.endswith('.json'):
  m=ce.envelope(ce.blob(R,p,H))
  if m is not None:assert m[ce.MARKER]==ce.FORMAT and m['tested_commit']==T and m['exit_code']==0;decoded[Path(p).name]=ce.read(R,p,H,tested=T,exit_code=0)
counts={}
for name,expected in [('focused-junit.json',190),('harness-junit-xml.json',1492),('unit-junit.json',241)]:
 tree=ET.fromstring(decoded[name]);suites=list(tree.iter('testsuite'));totals={k:sum(int(x.attrib.get(k,0)) for x in suites) for k in ('tests','failures','errors','skipped')};assert totals['tests']==expected and not any(totals[k] for k in ('failures','errors','skipped'));counts[name]=totals
collection=json.loads(decoded['harness-collection-json.json']);run=json.loads(decoded['harness-execution-json.json']);manifest=json.loads(decoded['harness-manifest-json.json'])
serial=collection['collections']['serial'];assert len(serial)==len(set(serial))==1492 and collection['exit_code']==0 and not collection['errors']
assert all(nodes==serial for nodes in run['collections'].values()) and run['exit_code']==0 and not run['errors']
assert len(run['started'])==1492 and len(run['reports'])==1492*3 and all(report['outcome']=='passed' for report in run['reports'])
assert sorted(report['nodeid'] for report in run['reports'] if report['phase']=='call')==sorted(serial)
assert manifest['tested_commit']==T and manifest['dirty_source'] is False and manifest['execution_complete'] is True and manifest['exit_code']==0

roundtrip=json.loads(decoded['inventory_roundtrip.json']);assert roundtrip['status']=='PASS' and roundtrip['tested_commit']==T and roundtrip['installed_layout'] and not roundtrip['installed_schema_file'];assert len(roundtrip['results'])==4
budget=ce.audit(R,B,H,'HG-051');assert not budget['errors'];g('diff','--check',B,H)
report=dict(reviewed_sha=H,tested_sha=T,clean_source_end=True,governance_status='PASS',suffix=suffix,checks=checks,decoded_envelopes=len(decoded),junit_counts=counts,collection_nodes=1492,execution_call_reports=1492,all_execution_phases_passed=True,real_inventory_installed_roundtrip=True,budget=budget,status='PASS')
Path('/private/tmp/hg051-r2-general-work/final_evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
