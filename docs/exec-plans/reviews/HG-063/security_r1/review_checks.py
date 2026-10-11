import ast,copy,contextlib,hashlib,io,json,shlex,subprocess,sys,zlib
from pathlib import Path
from collections import Counter
from dataclasses import replace
import xml.etree.ElementTree as ET
import yaml,jsonschema
ROOT=Path('/Users/davetian/.codex/worktrees/hg063-plain-archival-definitions/KineticLoop')
OUT=Path('/private/tmp/hg063-security-r1')
B='161744c5760561349bdeb17d628e38220640c95b';T='3e8b99a49d9a3f4e7dbb77cd6a66ebf3cbbd1afa';R='f22a78a622caa1e461099e690583b40f5cf5b925'
H='docs/exec-plans/evidence/HG-063/'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(p,rev=R):
 e=git('ls-tree','-z',rev,'--',p).split(b'\0');assert len(e)==2 and e[-1]==b''
 mode,kind,rest=e[0].split(b' ',2);oid,path=rest.split(b'\t');assert mode in [b'100644',b'100755'] and kind==b'blob' and path.decode()==p
 return git('cat-file','blob',oid.decode())
def sha(v):return hashlib.sha256(v).hexdigest()
def identity(v):return {'bytes':len(v),'sha256':sha(v)}
assert git('rev-parse','HEAD').decode().strip()==R and not git('status','--porcelain')
assert sha(blob(H+'PACKET.md'))=='572867a8963ec4d3b143f5dc15a11aca385b491c47f37133dde8ed98747b79f8'
indexpath=H+'checks-'+T[:12]+'/CHECK_INDEX.json'; raw=blob(indexpath)
assert sha(raw)=='ca94a39501d8e703a82fb7f83b3e29d99d07fce8a8a1112ff2448a8abfa75f9b'; idx=json.loads(raw)
result=yaml.safe_load(blob('docs/exec-plans/governance/HG-063.yaml'));jsonschema.validate(result,json.loads(blob('HARNESS_CHANGE.schema.json')))
assert idx['base_commit']==result['base_commit']==B and idx['tested_commit']==result['tested_commit']==T
checks={}; decoded={};artifact_count=0
for c,rc in zip(idx['checks'],result['checks_run'],strict=True):
 assert type(c['exit_code']) is int and c['exit_code']==0 and c['execution_state']=='COMPLETED'
 assert c['tested_commit']==T and c['base_commit']==B and c['command']==shlex.join(c['argv'])
 assert (c['check_id'],c['command'],c['output_ref'])==(rc['check_id'],rc['command'],rc['evidence_ref']) and rc['result']=='PASS'
 for a in c['artifacts']:
  eb=blob(a['evidence_ref']);assert identity(eb)==a['envelope_identity'];e=json.loads(eb)
  assert e['kineticloop_evidence']=='gzip-v1' and e['tested_commit']==T and e['command']==a['command'] and type(e['exit_code']) is int and e['exit_code']==0
  pb=blob(e['payload']);assert identity(pb)==a['payload_identity']=={'bytes':e['stored_bytes'],'sha256':e['stored_sha256']}
  d=zlib.decompressobj(31);data=d.decompress(pb,64*1024*1024+1);assert d.eof and not d.unused_data and not d.unconsumed_tail
  assert identity(data)==a['raw_identity']=={'bytes':e['raw_bytes'],'sha256':e['raw_sha256']}
  decoded[Path(a['evidence_ref']).name]=data;artifact_count+=1
 checks[c['check_id']]={'exit_code':0,'command':c['command'],'raw_output_sha256':sha(decoded[Path(c['output_ref']).name])}
assert set(checks)=={'definitions','validator','unit','harness','lint','typecheck','authority','diff'}
positive={}
for name,workers in [('validator',1),('unit',1),('harness',2)]:
 col=json.loads(decoded[name+'-collection.json.json']);exe=json.loads(decoded[name+'-execution.json.json']);xml=ET.fromstring(decoded[name+'-junit.xml.json'])
 assert col['exit_code']==exe['exit_code']==0 and not col['errors'] and not exe['errors']
 nodes=col['collections']['serial'];assert len(nodes)==len(set(nodes))>0
 assert len(exe['collections'])==workers and all(x==nodes for x in exe['collections'].values())
 assert Counter(exe['started'])==Counter(nodes)
 for phase in ['setup','call','teardown']:
  rows=[r for r in exe['reports'] if r['phase']==phase];assert Counter(r['nodeid'] for r in rows)==Counter(nodes) and all(r['outcome']=='passed' for r in rows)
 cases=xml.findall('.//testcase');assert not any(xml.findall('.//'+s) for s in ['failure','error','skipped'])
 expected=[]
 for node in nodes:
  addr,sep,param=node.partition('[');p=addr.split('::');expected.append(('.'.join([p[0][:-3].replace('/','.'),*p[1:-1]]),p[-1]+sep+param))
 assert Counter(expected)==Counter((c.get('classname'),c.get('name')) for c in cases)
 positive[name]={'cases':len(nodes),'workers':workers,'nodeids_sha256':sha(json.dumps(nodes,separators=(',',':')).encode()),'all_three_phases_and_junit':'EXACT_PASS'}
manifest=json.loads(decoded['harness-manifest.json.json']);assert manifest==next(c for c in idx['checks'] if c['check_id']=='harness')['harness_manifest']
assert manifest['tested_commit']==T and not manifest['dirty_source'] and manifest['execution_complete'] and not manifest['errors']
assert manifest['exit_code']==manifest['pytest_exit_code']==0
fixtureids=json.loads(blob(H+'FIXTURE_IDENTITIES.json'))['identities']
lines=decoded['definitions.json'].decode().splitlines();f=next(json.loads(l) for l in lines if l.startswith('{"fixture_count"'))
assert f['fixture_count']==255 and f['positive_identities']==fixtureids and len(set(fixtureids))==255
sys.path[:0]=[str(ROOT),str(ROOT/H)]
import verify_definitions as verify
from tools.harness import validate_harness as validator
with contextlib.redirect_stdout(io.StringIO()) as binding_log:
 bindings=verify.verify_pins();verify.verify_git_bindings(bindings)
binding_observations=json.loads(binding_log.getvalue())
assert len(binding_observations['observations'])==39
assert validator.governance_suffix_errors(ROOT,T,R,'HG-063','tested')==[]
changes=git('diff','--name-only',B,R).decode().splitlines();assert set(changes)==set(result['files_changed'])
assert all(validator.matches(p,validator.HG063_ALLOWED_PATTERNS) for p in changes)
suffix=[]
for c in git('rev-list','--reverse',T+'..'+R).decode().splitlines():
 ps=git('show','-s','--format=%P',c).decode().split();assert len(ps)==1
 rows=git('diff-tree','--no-commit-id','--name-status','-r',ps[0],c).decode().splitlines()
 for row in rows:
  status,path=row.split('\t');assert status=='A' and (path.startswith(H) or path=='docs/exec-plans/governance/HG-063.yaml')
 suffix.append({'commit':c,'parent':ps[0],'added_files':len(rows)})
for p in ['CURRENT_DOCUMENT_INDEX.json','HARNESS_DOCUMENT_MANIFEST.json']:
 assert blob(p,T)==blob(p,R)
untouched=['FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','THREAD_REVIEW.schema.json','HARNESS_CHANGE.schema.json','docs/harness/THREAD_REVIEW_CONTRACT.md','docs/harness/EVIDENCE_STORAGE_POLICY.md','tools/harness/compact_evidence.py','tools/harness/local_gate.py','.github/workflows/ci.yml']
for p in untouched:assert blob(p,B)==blob(p,R)
def functions(raw):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(raw).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
old=functions(blob('tools/harness/validate_harness.py',B));new=functions(blob('tools/harness/validate_harness.py'))
assert {n for n in old if old[n]!=new[n]}=={'governance_allowed_patterns','validate'}
assert set(new)-set(old)=={'plain_archival_projection_errors'}
evidence=[p for p in changes if p.startswith(H)];sizes={p:len(blob(p)) for p in evidence}
assert all(n<=(8*1024*1024 if p.endswith('.gz') else 262144) for p,n in sizes.items()) and sum(sizes.values())<=16*1024*1024
from fixture_support import CATALOG,ROLES,OUTPUT,ROWS,case
from definition_oracle import observe,inventory,Denied,typed,CAPS,exact_output_correspondence
from definition_schema import validate_role
probes=[];inputs=[];mandatory=[];native=[];gaps=[]
def deny(label,call):
 try:call()
 except Denied as e:probes.append({'case':label,'result':'DENY','reason':str(e)})
 else:raise AssertionError('ACCEPTED '+label)
for profile in CATALOG['profiles']:
 body,ctx,row,values=case(profile);role=next(r for r in ROLES['profiles'] if r['profile']==profile['profile']);validate_role(role,profile)
 o=observe(CATALOG,ROLES,body,ctx);inputs.append((body,ctx));mandatory.extend(o['covered_tuples']);gaps.extend(e['entry'] for e in o['entries'] if e['delivery_lineage'])
 count=len(o['entries']);tuples=tuple(o['covered_tuples']);gt=tuple(e['entry'] for e in o['entries'] if e['delivery_lineage'])
 def inv(candidate=o,inputs_=((body,ctx),),mandatory_=tuples,gap_=gt,count_=count,native_=()):return inventory(inputs_,count_,mandatory_,True,gap_,native_,catalog=CATALOG,roles=ROLES,output_types=OUTPUT,candidate_outputs=[candidate])
 inv()
 mutations=[('certification',lambda x:x['entries'][0].update(acceptance_eligible=True)),('omission',lambda x:x['entries'].pop()),('boolean_count',lambda x:x.update(documentary_unverified_count=True)),('unknown_key',lambda x:x.update(trusted=True)),('profile',lambda x:x.update(profile='NATIVE_CAPTURE_PATH'))]
 if len(o['entries'])>1:mutations.append(('coordinated_order',lambda x:(x['entries'].reverse(),x['covered_tuples'].reverse())))
 for label,mut in mutations:
  altered=copy.deepcopy(o);mut(altered);deny(profile['profile']+':'+label,lambda:inv(altered))
 deny(profile['profile']+':native_failure',lambda:observe(CATALOG,ROLES,body,replace(ctx,parent_states=('OBSERVED_EXACT_NONZERO',)*len(ctx.checks))))
 deny(profile['profile']+':selected_caller',lambda:observe(CATALOG,ROLES,body,replace(ctx,caller='SELECTED_GOVERNANCE')))
 deny(profile['profile']+':extra_body',lambda:observe(CATALOG,ROLES,body+b'PASS\n',ctx))
for row in ROWS['rows']:
 if row['disposition']=='KEEP_NATIVE_CAPTURE_PATH':
  for c in row['checks']:native.append((row['owner'],c['check_id'],row['original_B'],row['record_T'],c['command'],row['ref'],ROWS['authority_revision']))
mandatory.extend(native)
def allinv(**kw):
 args=dict(observation_inputs=tuple(inputs),declared_count=276,mandatory_tuples=tuple(mandatory),independent_complete=True,mandatory_lineage_gap_tuples=tuple(gaps),mandatory_native_tuples=tuple(native),catalog=CATALOG,roles=ROLES,output_types=OUTPUT);args.update(kw);return inventory(**args)
full=allinv();assert full['documentary_unverified_count']==276 and full['lineage_gap_count']==7 and len(full['observations'])==39
for label,kw in [('gap_omitted',{'mandatory_lineage_gap_tuples':()}),('native_fabricated',{'mandatory_native_tuples':tuple(native)+tuple(mandatory[:1])}),('report_omitted',{'observation_inputs':tuple(inputs[1:])}),('duplicate_report',{'observation_inputs':tuple(inputs)+tuple(inputs[:1])}),('boolean_total',{'declared_count':True}),('missing_independent_completion',{'independent_complete':False})]:deny(label,lambda:allinv(**kw))
for k,good,bads in [('INERT_REPO_DIRECTORY_CLAIM','docs/a/',['docs/a//','docs/../a/','docs//a/']),('INERT_REPO_PATH_CLAIM','docs/a',['docs/a/','docs/./a','docs//a'])]:
 s={'type':k,'max_bytes':CAPS[k]};assert typed(s,good)
 for bad in bads:assert not typed(s,bad);probes.append({'case':k+':'+bad,'result':'DENY'})
deep=0
for _ in range(65):deep=[deep]
deny('comparison_depth',lambda:exact_output_correspondence(deep,deep));deny('comparison_bytes',lambda:exact_output_correspondence('x'*524289,'x'*524289))
assert len(CATALOG['profiles'])==33 and sum(len(x['phases']) for x in ROLES['profiles'])==76 and sum(len(x['claim_relations']) for x in CATALOG['profiles'])==71
report=dict(reviewed_head_sha=R,base_commit=B,tested_commit=T,checks=checks,artifact_count=artifact_count,positive_identity_provenance=positive,definition_fixture_identity_count=255,original_bindings=binding_observations,closed_productions=33,phases=76,relations=71,documentary_count=276,lineage_gap_count=7,native_report_controls=6,suffix=suffix,evidence_bytes=sum(sizes.values()),largest_plain_bytes=max(n for p,n in sizes.items() if not p.endswith('.gz')),unchanged_guards=untouched,hostile_probes=probes,hostile_probe_count=len(probes),check_index_sha256=sha(raw),status='PASS')
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['status','artifact_count','positive_identity_provenance','closed_productions','phases','relations','documentary_count','lineage_gap_count','evidence_bytes','largest_plain_bytes','hostile_probe_count']},indent=2))
