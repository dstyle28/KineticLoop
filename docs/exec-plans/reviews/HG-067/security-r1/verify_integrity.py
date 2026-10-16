import ast,collections,gzip,hashlib,json,subprocess,sys,xml.etree.ElementTree as ET,zlib
from pathlib import Path
import jsonschema,yaml
ROOT=Path('/Users/davetian/.codex/worktrees/hg067-host-resource-contract/KineticLoop')
OUT=Path('/private/tmp/hg067-security-r1')
B='276bcaebbf3b64b4ea128b175a0463b2f650ac7c'; T='c3ac6d57c4183ce0c9eb0a7806ebc30673ca58a2'; R='ddffdbf75d6ff7b774fa84b00c20e57fc3a24fa5'
E='docs/exec-plans/evidence/HG-067/'; C=E+'checks-c3ac6d57c418/'
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def blob(p,rev=R):
 row=git('ls-tree','-l',rev,'--',p).decode().strip().split('\t'); assert len(row)==2 and row[1]==p
 mode,typ,oid,size=row[0].split();assert mode in ['100644','100755'] and typ=='blob'
 raw=git('cat-file','blob',oid);assert len(raw)==int(size);return raw
def sha(raw):return hashlib.sha256(raw).hexdigest()
def j(p,rev=R):return json.loads(blob(p,rev))
def pair(raw):return [len(raw),sha(raw)]
assert git('rev-parse','HEAD').decode().strip()==R and not git('status','--porcelain')
assert subprocess.run(['git','merge-base','--is-ancestor',B,T],cwd=ROOT).returncode==0
assert git('rev-list','--parents','-n','1',R).decode().split()==[R,T]
index=j('CURRENT_DOCUMENT_INDEX.json'); authority=[]
for row in index['documents']+index['machine_readable']:
 assert sha(blob(row['path']))==row['sha256'];authority.append(row['path'])
changes=git('diff','--name-status',B,R).decode().splitlines()
sys.path.insert(0,str(ROOT));from tools.harness import validate_harness as v
assert all(v.matches(row.split('\t')[-1],v.HG067_ALLOWED_PATTERNS) for row in changes)
immutable=['tools/harness/compact_evidence.py','tools/harness/local_gate.py','tools/harness/github_app.py','tools/harness/db_ci.py','CURRENT_REQUIREMENT_SET.json','FROZEN_BASELINE.json','HARNESS_CHANGE.schema.json','THREAD_REVIEW.schema.json','docs/harness/REVIEW_SOURCE_DECLARATIONS.json']
for p in immutable:assert blob(p,B)==blob(p)
for row in index['documents']:
 if row['document_id'] in ['DOC-PROTOCOL-V1.2','DOC-DB-V0.2','DOC-INTEGRATION-V0.1','DOC-ACCEPTANCE-GATES-V1.2.2']:assert blob(row['path'],B)==blob(row['path'])
assert blob('HARNESS_DOCUMENT_MANIFEST.json',T)==blob('HARNESS_DOCUMENT_MANIFEST.json')
suffix=git('diff','--name-status',T,R).decode().splitlines()
assert len(suffix)==67 and all(x.startswith('A\t') and (x[2:].startswith(E) or x[2:]=='docs/exec-plans/governance/HG-067.yaml') for x in suffix)
assert not v.governance_suffix_errors(ROOT,T,R,'HG-067','tested')
for row in j(E+'NORMATIVE_PROMOTION.json')['appendices']:
 before=blob(row['path'],B);after=blob(row['path']);assert after.startswith(before)
 assert pair(before)==[row['base_bytes'],row['base_sha256']]
 assert pair(after[len(before):])==[row['append_bytes'],row['append_sha256']]
source_rows=j(E+'DELIVERY_PROVENANCE.json')
for row in source_rows:
 raw=blob(row['delivery']);old=Path(row['source']).read_bytes()
 assert pair(old)==[row['source_bytes'],row['source_sha256']] and sha(raw)==row['delivery_sha256']
 if not row['adapted']:assert raw==old
fixtures=j(E+'FIXTURE_BINDINGS.json');sources={}
for row in fixtures:
 p=row['source']
 if p not in sources:
  raw=Path(p).read_bytes();assert pair(raw)==[row['source_bytes'],row['source_sha256']];d=json.loads(raw)
  sources[p]=[x for x in d['cases'] if x['id'].startswith('final_truthful_changed_')] if row['label']=='security' else d
 raw=blob(E+row['file']);assert sha(raw)==row['sha256'];d=json.loads(raw)
 assert d==sources[p][row['index']] and d['accepted'] is False
 assert sha(json.dumps(d,sort_keys=True,separators=(',',':')).encode())==row['record_semantic_sha256']
assert len(fixtures)==56
# Reconstruct compressed evidence independently, without author identity helper or summary/count oracles.
captures={};envs={};ci=j(C+'CHECK_INDEX.json')
for row in ci['capture_manifest']:
 path=row['evidence_ref'];env=j(path);stored=blob(env['payload']);assert pair(stored)==[env['stored_bytes'],env['stored_sha256']]
 assert env['tested_commit']==T and env['exit_code']==0 and env['raw_bytes']<=64*1024*1024
 dec=zlib.decompressobj(31);raw=dec.decompress(stored,env['raw_bytes']+1)
 assert dec.eof and not dec.unused_data and not dec.unconsumed_tail
 assert pair(raw)==[env['raw_bytes'],env['raw_sha256']]==[row['bytes'],row['sha256']]
 assert Path(row['source']).read_bytes()==raw
 captures[path[len(C):]]=raw;envs[path[len(C):]]=env
commands=json.loads(captures['COMMANDS.json']);assert len(commands)==10 and all(x['exit_code']==0 for x in commands)
for check in ci['checks']:
 row=next(x for x in commands if x['check_id']==check['check_id']);env=envs[check['evidence_ref'][len(C):]]
 assert row['command']==check['command']==env['command'] and row['stdout_stderr_sha256']==env['raw_sha256']
wrapper=json.loads(captures['AUTHOR_WRAPPER.json']);assert wrapper['observed_exit_code']==0 and wrapper['tested_commit']==T
assert sha(Path(wrapper['stdout_path']).read_bytes())==wrapper['stdout_sha256']
receipts=json.loads(captures['definitions-COMMAND_RECEIPTS-json.json']);assert len(receipts)==2 and all(x['child_exit']==0 for x in receipts)
identities={}
for name,count in [('definitions',439),('validator',185),('unit',247),('harness',1794)]:
 execution=json.loads(captures[name+'-execution-json.json']);collection=json.loads(captures[name+'-collection-json.json']);xml=ET.fromstring(captures[name+'-junit-xml.json'])
 assert execution['exit_code']==collection['exit_code']==0 and not execution['errors'] and not collection['errors'] and not collection['started'] and not collection['reports']
 ids=next(iter(collection['collections'].values()));counts=collections.Counter(ids)
 assert len(ids)==len(counts)==count and all(x==ids for x in execution['collections'].values())
 assert collections.Counter(execution['started'])==counts
 assert len(execution['reports'])==3*count
 for phase in ['setup','call','teardown']:
  reports=[x for x in execution['reports'] if x['phase']==phase]
  assert collections.Counter(x['nodeid'] for x in reports)==counts and all(x['outcome']=='passed' for x in reports)
 assert not any(list(xml.iter(x)) for x in ['error','failure','skipped'])
 # Split only structural :: before the parameter suffix; embedded :: in parameters remain data.
 pairs=[]
 for node in ids:
  base,bracket,param=node.partition('['); parts=base.split('::');parts[0]=parts[0][:-3].replace('/','.') if parts[0].endswith('.py') else parts[0].replace('/','.')
  pairs.append(('.'.join(parts[:-1]),parts[-1]+bracket+param))
 assert collections.Counter((x.get('classname'),x.get('name')) for x in xml.iter('testcase'))==collections.Counter(pairs)
 if name=='definitions':assert ids==j(E+'EXPECTED_IDENTITIES.json')['identities']
 identities[name]={'cases':count,'phases':3*count,'identity_sha256':sha(json.dumps(ids,separators=(',',':')).encode()),'all_identity_relations_equal':True,'collection_exit':0,'execution_exit':0}
result=yaml.safe_load(blob('docs/exec-plans/governance/HG-067.yaml'));jsonschema.validate(result,j('HARNESS_CHANGE.schema.json'))
assert result['base_commit']==B and result['tested_commit']==T and result['checks_run']==ci['checks']
assert not result['authority_entries_added'] and not result['packets_refined'] and result['frozen_impact']=='NONE'
failed=j(E+'PREPARATION_ATTEMPTS.json')
for row in failed['external_originals']:assert pair(Path(row['path']).read_bytes())==[row['bytes'],row['sha256']]
assert failed['acceptance']=='FAIL' and failed['definitions_exit']==failed['author_wrapper_observed_exit']==1
future=j(E+'FUTURE_CHECKS.json');assert len(future['checks'])==14 and all(x['status']=='NOT_RUN' for x in future['checks'])
assert future['project_native_feasibility']==future['privileged_host_runtime_feasibility']=='NOT_DETERMINED'
# Check all own history artifact sizes and stored copies by immutable edge, not ambient cache.
history=[]
for rev in git('rev-list','--reverse',B+'..'+R).decode().splitlines():
 parent=git('rev-parse',rev+'^').decode().strip();rows=git('diff','--name-status',parent,rev).decode().splitlines();total=0;files=0
 for row in rows:
  kind,p=row.split('\t');assert kind in ['A','M'] and v.matches(p,v.HG067_ALLOWED_PATTERNS)
  raw=blob(p,rev)
  if p.startswith(E):
   assert len(raw)<=(8*1024*1024 if p.endswith('.gz') else 262144);total+=len(raw);files+=1
 assert total<=16*1024*1024
 history.append({'revision':rev,'edge_changed_files':len(rows),'own_evidence_files':files,'own_evidence_bytes':total})
summary={'reviewed_head_sha':R,'base':B,'tested':T,'authority_hashes':len(authority),'scope_files':len(changes),'source_bindings':len(source_rows),'retained_inert_fixtures':len(fixtures),'captured_outputs':len(captures),'identities':identities,'fresh_author_checks':8,'author_child_exit_codes':[x['exit_code'] for x in commands],'author_wrapper_exit':0,'definition_child_exits':[x['child_exit'] for x in receipts],'failed_first_T_preserved':True,'history':history,'tested_suffix_additions':len(suffix),'native_suffix_guard_errors':[],'immutable_runtime_and_product_paths':immutable,'future_checks_not_run':14,'native_runtime_fit':'NOT_DETERMINED','project_native_inventory_audit_run':False,'limitations':['Captured outputs independently reconstructed and cross-checked; execution was observed by author tools, not rerun by this reviewer.','No installed host/native resource enforcement or App/DB execution performed.']}
(OUT/'INTEGRITY.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
