from pathlib import Path
import json,hashlib,subprocess,collections,importlib.util,sys,xml.etree.ElementTree as ET
from datetime import datetime,timezone
root=Path.cwd();head='feb3236c175df171611fc5b7ddb4f6eeca3ce47c';base='1d3075151246b2774640a3d7acec836f47ab2b8d'
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==head
raw=Path('/private/tmp/kl080-hg051-final')/head; out=root/'docs/exec-plans/evidence/KL-080'/('HG051-'+head)
out.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('compact',root/'tools/harness/compact_evidence.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def save(name,data):
 p=out/name;p.write_text(json.dumps(data,indent=2)+'\n');return str(p.relative_to(root))
def cap(p,name,command,exit_code=0):
 ref=str((out/(name+'.capture.json')).relative_to(root));rec=m.capture(root,ref,p.read_bytes(),head,command,exit_code,datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat());assert m.read(root,ref,None,tested=head,command=command)==p.read_bytes();return {'path':ref,'sha256':hashlib.sha256((root/ref).read_bytes()).hexdigest(),'raw_sha256':rec['raw_sha256'],'raw_bytes':rec['raw_bytes']}
rows=json.loads((raw/'final-checks.json').read_text())['executions']; assert len(rows)==17 and all(r['result']=='PASS' and r['exit_code']==0 and r['tested_commit']==head for r in rows)
contracts=next(t for t in json.loads((root/'KineticLoop_Harness_Backlog_v0.2.json').read_text())['tasks'] if t['id']=='KL-080')
byid={r['check_id']:r for r in rows};assert set(byid)==set(contracts['checks_required_for_this_task'])
records=[]
for c in contracts['check_contracts']:
 r=byid[c['check_id']];assert r['command']==c['command'];check=r['check_id'];record={k:r[k] for k in ['check_id','command','result','exit_code','tested_commit']};record['stdout']=cap(Path(r['stdout']),check+'.stdout',r['command']);record['evidence_ref']=record['stdout']['path']
 if 'counts' in r:
  assert r['counts']['executed']>0 and not any(r['counts'][k] for k in ('failures','errors','skipped'));record['counts']=r['counts'];record['junit']=cap(Path(r['junit']['path']),check+'.junit',r['command'])
 for suffix in ('collection.log','collection.json'):
  p=raw/(check+'.'+suffix)
  if p.exists():
   cc=json.loads((raw/(check+'.collection.json')).read_text());assert cc['tested_commit']==head and cc['exit_code']==0 and len(cc['nodeids'])==r['counts']['executed'];record[suffix]=cap(p,check+'.'+suffix,cc['command'])
 record['execution_record']=cap(raw/(check+'.execution.json'),check+'.execution',r['command']);records.append(record)
save('final-checks.json',{'tested_commit':head,'executions':records})
for suffix in ('collection.log','collection.json','execution.json','pytest.log'):
 p=raw/('harness.'+suffix); assert p.exists();cap(p,'harness.'+suffix,'uv run kl test-harness')
# Runner's ephemeral manifest was removed before the hardlink watcher caught it.
# Actual collection, execution and JUnit were retained losslessly, without altering the command.
save('execution-layout.json',{'tested_commit':head,'commands_unmodified':True,'source_lifecycles':'serial, namespace preflight first; read-only harness/unit checks parallel','harness_workers':2,'harness_capture':'Exact temporary collection/execution/JUnit/pytest inodes retained through hardlinks under controlled external TMPDIR. Ephemeral manifest was not retained; no reconstructed raw manifest is claimed.','driver_sha256':hashlib.sha256(Path('/private/tmp/kl080-hg051-final.py').read_bytes()).hexdigest()})
idx=collections.defaultdict(list); ns=[];cleanup=[]
for i,line in enumerate((raw/'source_suite_dc.log').read_text().splitlines(),1):
 if 'SOURCE_EVIDENCE ' not in line:continue
 v=json.loads(line.partition('SOURCE_EVIDENCE ')[2]);idx[v['kind']].append(i)
 if v['kind']=='kl080_namespace':ns.append(v)
 if v['kind']=='kl080_cleanup':cleanup.append(v)
assert len(ns)==len(cleanup)==106;assert len(idx['kl080_mechanical_s37_legacy_consumer_denial'])==1
assert all(v['tested_commit']==head and v['migration']=='e8c2f1a6b904' and v['calendar_timezone']=='UTC' for v in ns)
assert all(not any(v['remaining'].values()) for v in cleanup)
assert len({(v['compose'],v['database']) for v in ns})==1
save('witness-index.json',{'tested_commit':head,'raw_stdout':next(r['stdout'] for r in records if r['check_id']=='source_suite_dc'),'executed_cases':106,'namespaces':106,'cleanups':106,'all_owned_resources_empty':True,'namespace':{'compose':ns[0]['compose'],'database':ns[0]['database']},'migration':'e8c2f1a6b904','witness_index':{k:{'count':len(v),'raw_line_numbers':v} for k,v in idx.items()},'mechanical_oracle':'Untouched owner S37 and correct authenticated CommitBundle reach native prepare_authorization_basis denial; first-use head observed inside actual T6 and fully rolled back. No later certificate reach claimed.','equality_timing_layer':'PU equality only; PostgreSQL boundary observes time strictly beyond expiry.'})
host=Path('/private/tmp/kl080-hg051-hosted-37161315464')/('db-evidence-'+head+'-37161315464-1');h=json.loads((host/'manifest.json').read_text());assert h['tested_commit']==head and h['status']=='PASS' and h['provenance']['environment']=='github-hosted' and h['provenance']['github_run_id']=='37161315464';assert h['junit']=={'errors':0,'failures':0,'skipped':0,'tests':780};assert not h['remaining_containers'] and not h['remaining_volumes']
assert len(ET.parse(host/'database.xml').findall('.//testcase'))==780
hostrefs={}
parent='uv run python tools/harness/db_ci.py run --revision '+head+' --environment github-hosted --evidence-dir "$RUNNER_TEMP/db-evidence"'
for a in h['artifacts']+[c['stdout'] for c in h['checks']]:
 p=host/a['path'];assert len(p.read_bytes())==a['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==a['sha256']
assert all(c['exit_code']==0 and not c['interrupted'] for c in h['checks'])
for p in sorted(host.iterdir()):
 command=next((' '.join(c['argv']) for c in h['checks'] if c['stdout']['path']==p.name),parent)
 hostrefs[p.name]=cap(p,'hosted.'+p.name,command)
save('hosted-db-verification.json',{'tested_commit':head,'workflow_ref_sha':base,'run_id':37161315464,'run_url':'https://github.com/dstyle28/KineticLoop/actions/runs/37161315464','actual_checkout_verified':True,'status':'PASS','counts':h['junit'],'all_artifact_hashes_match':True,'cleanup_empty':True,'raw_artifacts':hostrefs})
# Verify scope, original failed evidence retention, and unchanged base authorities.
vs=importlib.util.spec_from_file_location('validator',root/'tools/harness/validate_harness.py');v=importlib.util.module_from_spec(vs);vs.loader.exec_module(v)
def git(*args):return subprocess.check_output(['git',*args])
changed=git('diff','--name-only',base,head).decode().splitlines();assert not v.task_fixture_scope_errors(root,base,head,'KL-080',changed)
allowed=contracts['write_paths']+['docs/exec-plans/evidence/KL-080/**','docs/exec-plans/completed/KL-080_RESULT.yaml','docs/exec-plans/reviews/KL-080/**'];assert all(v.matches(p,allowed) for p in changed)
protected=[]
for p in git('ls-tree','-r','--name-only',base).decode().splitlines():
 if p.startswith(('docs/exec-plans/','docs/history/','.github/','tools/harness/','tests/harness/')) or p.endswith('_FROZEN.md') or p in {'FROZEN_BASELINE.json','CURRENT_DOCUMENT_INDEX.json','CURRENT_REQUIREMENT_SET.json','KineticLoop_Harness_Backlog_v0.2.json'}:
  before=git('rev-parse',base+':'+p);assert before==git('rev-parse',head+':'+p),p;protected.append((p,before.decode().strip()))
old='78dfa7ff6d28eaca515d83b29f8a16453eba5832'
historical=git('ls-tree','-r','--name-only',old,'--','docs/exec-plans/evidence/KL-080').decode().splitlines()
archives={o['path'] for o in m.historical_originals()}
assert all(git('rev-parse',old+':'+p)==git('rev-parse',head+':'+p) for p in historical if p not in archives)
archive_errors,archive_paths=m.archive_audit(root,head);assert archive_errors==[],archive_errors
for o in m.historical_originals():assert m.read_archive(root,o['path'],head)==m.archive_original(root,o)
save('preserved-baseline.json',{'base_commit':base,'tested_commit':head,'scope_errors':[],'fixture_scope_errors':[],'protected_count':len(protected),'protected_listing_sha256':hashlib.sha256(json.dumps(protected,sort_keys=True).encode()).hexdigest(),'nonmigrated_historical_evidence_files_preserved':len(historical)-4,'historical_evidence_revision':old,'approved_archive_representations':sorted(archives),'archive_audit_errors':archive_errors,'archive_original_roundtrips':4,'changed_blob_sha256':{p:hashlib.sha256(git('show',head+':'+p)).hexdigest() for p in changed},'requirement_statuses_unchanged':True,'production_activation_unchanged':True})
save('entry.json',json.loads(Path('/private/tmp/kl080-hg051-entry.json').read_text()))
save('final-cleanup.json',json.loads((raw/'final-cleanup.json').read_text()))
(out/'capture.py').write_bytes(Path('/private/tmp/kl080-hg051-capture.py').read_bytes())
(out/'driver.py').write_bytes(Path('/private/tmp/kl080-hg051-final.py').read_bytes())
print('CAPTURED',out,'stored_bytes',sum(p.stat().st_size for p in out.iterdir()),'SOURCE_CASES106 HOSTED780 ALL17PASS')
