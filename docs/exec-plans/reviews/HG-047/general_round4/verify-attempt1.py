import ast, collections, gzip, hashlib, importlib.util, json, re, subprocess, xml.etree.ElementTree as ET
from pathlib import Path
import yaml
R=Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop'); O=Path('/private/tmp/hg047-general-r4'); H='b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91'; B='d08927706a01a397dac2c78ca4aec7e9918a389c'; S='7b35dc5dd7c488b60651175574e37b5d9389d335'
def git(*args): return subprocess.check_output(['git',*args],cwd=R)
def blob(rev,p): return git('show',rev+':'+p)
def sha(x): return hashlib.sha256(x).hexdigest()
assert git('rev-parse','HEAD').decode().strip()==H
spec=importlib.util.spec_from_file_location('ce',R/'tools/harness/compact_evidence.py'); ce=importlib.util.module_from_spec(spec);spec.loader.exec_module(ce)
paths=git('ls-tree','-r','--name-only',H).decode().splitlines(); prefix='docs/exec-plans/evidence/HG-047/round4-7b35dc5/'
raw={}; manifests={}; summaries=[]; historical=[]
for p in paths:
 if not p.startswith('docs/exec-plans/evidence/HG-047/') or not p.endswith('.json'): continue
 m=json.loads(blob(H,p))
 if m.get('kineticloop_evidence')!='gzip-v1': continue
 stored=blob(H,m['payload']); decoded=gzip.decompress(stored)
 assert len(stored)==m['stored_bytes'] and sha(stored)==m['stored_sha256']
 assert len(decoded)==m['raw_bytes'] and sha(decoded)==m['raw_sha256']
 assert ce.read(R,p,H)==decoded
 if p.startswith(prefix):
  raw[Path(p).name]=decoded; manifests[Path(p).name]=m
  assert m['tested_commit']==S
  summaries.append({'path':p,'bytes':len(decoded),'sha256':sha(decoded),'exit_code':m['exit_code'],'command':m['command'],'test_counts':m['test_counts']})
  (O/('decoded-'+Path(p).name)).write_bytes(decoded)
 elif m['exit_code'] or m['test_counts'].get('errors') or m['test_counts'].get('failed'):
  historical.append({'path':p,'exit_code':m['exit_code'],'test_counts':m['test_counts']})
# Integrity at every indexed byte, rather than accepting the author audit.
metadata={}
for p,arr in [('CURRENT_DOCUMENT_INDEX.json',None),('HARNESS_DOCUMENT_MANIFEST.json','files')]:
 obj=json.loads(blob(H,p)); entries=obj[arr] if arr else obj['documents']+obj['machine_readable']
 for e in entries:
  b=blob(H,e['path']); assert sha(b)==e['sha256'],e['path']
  if 'bytes' in e: assert len(b)==e['bytes']
 metadata[p]=len(entries)
# Complete shared-validator reconstruction: old HG047 file plus only exact HG048 branch.
vp='tools/harness/validate_harness.py'; current=blob(H,vp).decode(); old=blob('d67ed45',vp).decode(); base=blob(B,vp).decode()
branch=base.split("    if change_id == 'HG-048':",1)[1].split("    if change_id == ",1)[0]
addition="    if change_id == 'HG-048':"+branch
assert current==old.replace('def governance_allowed_patterns(change_id):\n','def governance_allowed_patterns(change_id):\n'+addition,1)
readme='tools/harness/README.md'; extra='For lossless capture, validated retrieval and the prospective protected-base PR\nbudget, see [Evidence Storage Policy](../../docs/harness/EVIDENCE_STORAGE_POLICY.md).\n'
assert blob(H,readme).decode().replace(extra,'',1)==blob(B,readme).decode()
# Every nonshared HG048 introduced blob and every retained HG047 nonshared blob.
shared={'CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json',vp,readme}
hg48=git('diff','--name-only',B+'^1',B).decode().splitlines(); kept48=[]
for p in hg48:
 if p not in shared: assert blob(B,p)==blob(H,p),p; kept48.append(p)
changed=git('diff','--name-only',B,H).decode().splitlines()
protected=['FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','src','migrations','tests/db','.github/workflows','tools/harness/db_policy.py','tools/harness/db_ci.py','tools/harness/github_app.py']+[e['path'] for e in json.loads(blob(B,'FROZEN_BASELINE.json'))['files']]
assert not git('diff','--name-only',B,H,'--',*protected)
retained47=[]
for p in git('ls-tree','-r','--name-only','d67ed45').decode().splitlines():
 if p.startswith(('docs/exec-plans/evidence/HG-047/','docs/exec-plans/reviews/HG-047/')) and p not in {'docs/exec-plans/evidence/HG-047/SCOPE.md','docs/exec-plans/evidence/HG-047/audit.py'}:
  assert blob('d67ed45',p)==blob(H,p),p; retained47.append(p)
# All selected task check metadata exactly matches raw wrappers when applicable.
result=yaml.safe_load(blob(H,'docs/exec-plans/governance/HG-047.yaml'))
assert result['tested_commit']==S and result['base_commit']==B
for c in result['checks_run']:
 p=c['evidence_ref']; m=json.loads(blob(H,p))
 if m.get('kineticloop_evidence'):
  assert m['tested_commit']==S and m['command']==c['command'] and m['exit_code']==0
# Inspect JUnit identity/counters independently of author identity-verifier.
counts={}; identities={}
for kind,total in [('harness',1324),('unit',241)]:
 tree=ET.fromstring(raw['worker--'+kind+'-xml.json']); cases=list(tree.iter('testcase')); ids=[(c.get('classname'),c.get('name')) for c in cases]
 assert len(cases)==total and len(set(ids))==total
 assert all(not list(c.iter(t)) for c in cases for t in ['failure','error','skipped'])
 suite=list(tree.iter('testsuite')); assert sum(int(s.attrib['tests']) for s in suite)==total
 assert re.search(r'\b'+str(total)+r' passed\b',raw[kind+'-log.json'].decode())
 counts[kind]=total;identities[kind]=ids
collection=[line for line in raw['host--collection-log.json'].decode().splitlines() if re.match(r'^tests/[^\s]+\.py::',line)]
observer=json.loads(raw['worker--run--execution-json.json'])
(O/'observer-shape.json').write_text(json.dumps({k:(len(v) if isinstance(v,(list,dict)) else v) for k,v in observer.items()},indent=2))
# Fail-closed ordinary JSON parity probe, independent of old review conclusion.
probe={}
for label,data in [('literal',b'{"x":"a","x":"b"}'),('unicode',b'{"x":"\\u0061","x":"b"}')]:
 try: probe[label]={'classification':ce.envelope(data),'returned':'plain'}
 except ValueError as e: probe[label]={'error':str(e)}
report={'reviewed_head':H,'source':S,'base':B,'metadata_counts':metadata,'hg048_nonshared_preserved':kept48,'retained_hg047_reports_evidence':retained47,'shared_validator_exact_reconstruction':True,'readme_exact_reconstruction':True,'selected_artifacts':summaries,'historical_nonzero_evidence':historical,'counts':counts,'collection_count':len(collection),'collection_unique':len(set(collection)),'ordinary_json_probe':probe,'budget':ce.audit(R,B,H,'HG-047'),'source_to_result_paths':git('diff','--name-only',S,H).decode().splitlines(),'intermediate_validator_lines':len(blob('a878a70',vp).splitlines()),'repaired_validator_lines':len(blob(S,vp).splitlines())}
(O/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in {'selected_artifacts','retained_hg047_reports_evidence','hg048_nonshared_preserved','source_to_result_paths'}},indent=2))
