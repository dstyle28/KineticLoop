import ast,copy,hashlib,json,os,shlex,subprocess,sys,time,xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import jsonschema,yaml
ROOT=Path('/Users/davetian/.codex/worktrees/hg065-custody-delivery/KineticLoop')
OUT=Path('/private/tmp/hg065-security-r1'); E=ROOT/'docs/exec-plans/evidence/HG-065'
B='e8e93bd32a83bd2fd6bf89951863d59b37e9d2b3';T='dfd4c20b93112e9403eb21286c705cd31847eefd';R='a2f2ff79565375e9bd0cca9013b11e61bf607cac'
sys.path[:0]=[str(ROOT),str(E)]
from tools.harness import compact_evidence as native,validate_harness as validator
import custody_study as study
from source_fixture import original_sources,neutral_sources_and_proof
records=[];git_cache={};reads=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def identity(b):return {'bytes':len(b),'sha256':sha(b)}
def git(*a):
 if a not in git_cache:
  p=subprocess.run(['git',*a],cwd=ROOT,capture_output=True,timeout=20)
  assert p.returncode==0,(a,p.returncode,p.stderr)
  git_cache[a]=p.stdout;reads.append({'argv':['git',*a],'exit_code':p.returncode,**identity(p.stdout)})
 return git_cache[a]
def raw(p,rev=R):return git('show',rev+':'+p)
def obj(rev,p):
 row=git('ls-tree','-l','-z',rev,'--',p)
 if not row:return None
 assert row.count(b'\0')==1
 meta,name=row[:-1].split(b'\t');mode,kind,oid,n=meta.split();assert kind==b'blob' and name.decode()==p
 b=git('cat-file','blob',oid.decode());assert len(b)==int(n)
 return dict(path=p,mode=mode.decode(),blob=oid.decode(),**identity(b))
def note(name,**values):records.append({'check':name,**values})
assert git('rev-parse','HEAD').decode().strip()==R
assert not git('status','--porcelain')
assert sha(raw('docs/exec-plans/evidence/HG-065/PACKET.md'))=='cb9b4803c9f6cd1ddef10166515375e3f45c0d55bb1c47b3a2c9cf1572d3e79c'
changed=git('diff','--name-only',B,R).decode().splitlines();assert len(changed)==192
assert all(validator.matches(p,validator.governance_allowed_patterns('HG-065')) for p in changed)
assert git('rev-list','--parents',T+'..'+R).decode().split()==[R,T]
suffix=git('diff','--name-status',T,R).decode().splitlines()
assert len(suffix)==64 and all((r.startswith('A\tdocs/exec-plans/evidence/HG-065/')) or r=='M\tdocs/exec-plans/governance/HG-065.yaml' for r in suffix)
assert raw('HARNESS_DOCUMENT_MANIFEST.json',T)==raw('HARNESS_DOCUMENT_MANIFEST.json')
for p in ['tools/harness/compact_evidence.py','tools/harness/local_gate.py','tools/harness/gate_validate.py','FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','HARNESS_CHANGE.schema.json','THREAD_REVIEW.schema.json','05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md']:
 assert raw(p,B)==raw(p);note('unchanged_boundary',path=p,**identity(raw(p)))
idx=json.loads(raw('CURRENT_DOCUMENT_INDEX.json'));count=0
for row in idx['documents']+idx['machine_readable']:
 assert sha(raw(row['path']))==row['sha256'];count+=1
note('scope_and_sha',base=B,tested=T,reviewed=R,changed=len(changed),authority_hashes=count,suffix_additions=63,result_modifications=1)
for p in ['capture_result.py','run_checks.py','precommit_artifacts.py','verify_definitions.py','portable_support.py','custody_study.py','source_fixture.py','definition_observer.py','test_custody_definition.py','observe_immutable.py','observe_inherited_components.py']:
 rel='docs/exec-plans/evidence/HG-065/'+p;assert raw(rel,T)==raw(rel);note('helper_at_T',path=rel,**identity(raw(rel)))
delivery=json.loads((E/'DELIVERY_PROVENANCE.json').read_bytes());candidate=json.loads((E/'PREPARATION_MANIFEST.json').read_bytes())
assert sha((E/'PREPARATION_MANIFEST.json').read_bytes())==delivery['candidate_manifest_sha256']=='73bc70e560791de77c04da8c229db5c2bc90135fd3a2b574c63ad05600af5e7e'
for item in delivery['normative']:
 b=(E/item['path']).read_bytes();assert identity(b)=={k:item[k] for k in ('bytes','sha256')}
 original=next(x for x in candidate['candidate_files'] if x['path']==item['path']);assert original['sha256']==sha(b)
 source=Path('/private/tmp/hg058-custody-rule-r2')/item['path'];assert source.read_bytes()==b
 note('exact_normative_delivery',path=item['path'],**identity(b))
assert sha((E/'PREPARATION_PROPOSAL.md').read_bytes())=='491e755a9f95bf85f3e98a24853d31a7d015cbafaab850b09210c08a7f000d04'
assert sha((E/'PREPARATION_HUMAN_APPROVAL.json').read_bytes())=='8677ef9fa5d81082932cc6afa0ce931ce523b93cdb7e8d5bb83ce24e879e34cc'
# Independent AST preservation and literal value checks; historical code is data only.
old='7b6f760bd36446a464e33d68ecdd2747c29997eb'
assert git('rev-parse','codex/hg064-custody-definitions').decode().strip()==old
oldtest=raw('docs/exec-plans/evidence/HG-064/test_custody_definition.py',old)
newtest=(E/'test_custody_definition.py').read_bytes()
a=ast.parse(oldtest.replace(b'HG064',b'HG065').replace(b'HG-064',b'HG-065').replace(b'hg064',b'hg065'));b=ast.parse(newtest)
assert ast.dump(a)==ast.dump(b)
oldfix=json.loads(raw('docs/exec-plans/evidence/HG-064/FIXTURE_INPUTS.json',old));newfix=json.loads((E/'FIXTURE_INPUTS.json').read_bytes())
assert {k:v for k,v in oldfix.items() if k!='group'}=={k:v for k,v in newfix.items() if k!='group'}
assert newfix['group']=={'members':[{'path':m['path']} for m in oldfix['group']['members']],'payload_paths':oldfix['group']['payload_paths']}
fn=next(n for n in b.body if isinstance(n,ast.FunctionDef) and n.name=='test_native_reserved_classifier_duties_not_suppressed')
bodies=ast.literal_eval(fn.decorator_list[0].args[1]);assert len(bodies)==4
for data in bodies:
 try:native.envelope(data)
 except ValueError as ex:note('hostile_constant_native_denied',diagnostic=str(ex),**identity(data))
 else:raise AssertionError('hostile accepted')
assert native.envelope(newtest) is None and native.reencoding_record(newtest) is None
note('hg064_ast_projection',ast_sha256=sha(ast.dump(b).encode()),hostile_constants=4,branch_preserved=old)
# Bind every raw author artifact natively at exact R and to actual fresh scratch.
checkindex=E/'checks-dfd4c20b9311/CHECK_INDEX.json';assert sha(checkindex.read_bytes())=='7c34a0327e52dd61dc0d57c7ffbf5d3691d3b39cbb40b0a0ca37f30d37147597'
ci=json.loads(checkindex.read_bytes());assert ci['tested_commit']==T and ci['base_commit']==B
count=0
for check in ci['checks']:
 name=check['check_id'];assert check['exit_code']==0 and check['execution_state']=='COMPLETED' and check['tested_commit']==T and check['base_commit']==B
 assert shlex.join(check['argv'])==check['command']
 meta=json.loads((Path('/private/tmp/hg065-author-'+T[:12])/(name+'-command.json')).read_bytes())
 for key in ['argv','command','environment','started_at_unix','execution_state','exit_code','elapsed_seconds','tested_commit','base_commit']:assert meta[key]==check[key]
 decoded={}
 for art in check['artifacts']:
  data=native.read(ROOT,art['evidence_ref'],R,tested=T,command=art['command'],exit_code=0)
  assert identity(data)==art['raw_identity'];assert Path(art['source_file']).read_bytes()==data
  envelope=raw(art['evidence_ref']);assert identity(envelope)==art['envelope_identity'];en=json.loads(envelope)
  assert identity(raw(en['payload']))==art['payload_identity'];assert en['tested_commit']==T
  decoded[Path(art['source_file']).name]=data;count+=1
  note('fresh_native_raw_binding',check_id=name,evidence_ref=art['evidence_ref'],source_file=art['source_file'],tested_commit=T,**identity(data))
 if name in ['definitions','validator','unit','harness']:
  prefix='definition-' if name=='definitions' else '' if name=='harness' else name+'-'
  c=json.loads(decoded[prefix+'collection.json']);x=json.loads(decoded[prefix+'execution.json']);j=ET.fromstring(decoded[prefix+'junit.xml'])
  assert c['exit_code']==x['exit_code']==0 and not c['errors'] and not x['errors']
  nodes=c['collections'] if name=='definitions' else c['collections']['serial']
  xc=[x['collections']] if name=='definitions' else list(x['collections'].values())
  assert len(nodes)==len(set(nodes)) and all(n==nodes for n in xc)
  assert len(xc)==(2 if name=='harness' else 1)
  assert Counter(x['started'])==Counter(nodes) and len(x['reports'])==3*len(nodes)
  for phase in ['setup','call','teardown']:
   rows=[r for r in x['reports'] if r.get('when',r.get('phase'))==phase]
   assert Counter(r['nodeid'] for r in rows)==Counter(nodes)
   assert all(r['outcome']=='passed' and r.get('wasxfail') is None for r in rows)
  assert not c['started'] and not c['reports']
  cases=list(j.iter('testcase'));assert len(cases)==len(nodes)
  assert not list(j.iter('failure'))+list(j.iter('error'))+list(j.iter('skipped'))
  expected=[]
  for node in nodes:
   addr,sep,params=node.partition('[');parts=addr.split('::')
   expected.append(('.'.join([parts[0][:-3].replace('/','.'),*parts[1:-1]]),parts[-1]+sep+params))
  assert Counter(expected)==Counter((e.get('classname'),e.get('name')) for e in cases)
  assert len(nodes)=={'definitions':156,'validator':176,'unit':247,'harness':1785}[name]
  if name=='definitions':assert nodes==json.loads((E/'FIXTURE_IDENTITIES.json').read_bytes())['identities']
  note('complete_positive_identity_equality',check_id=name,cases=len(nodes),nodeid_digest=sha(json.dumps(nodes).encode()),phases=3)
 note('actual_command_exit',check_id=name,argv=check['argv'],exit_code=0,command_meta=identity((Path('/private/tmp/hg065-author-'+T[:12])/(name+'-command.json')).read_bytes()))
assert count==37
# Original source facts independently read from immutable Git, never imported.
proof=json.loads((E/'ACTUAL_CUSTODY_PROOF.json').read_bytes());sources=original_sources(E)
result=study.custody_predicate(proof,original_sources=sources);assert result['representations']==6 and result['physical_paths']==8 and result['physical_bytes']==12746
assert result['acceptance_eligible'] is False and result['execution_reuse'] is False
seen=set();parents={};native_raw=[]
for member in proof['members']:
 d=member['declaration'];assert obj(d['revision'],d['object']['path'])==d['object']
 record=yaml.safe_load(raw(d['object']['path'],d['revision']));jsonschema.validate(record,json.loads(raw('HARNESS_CHANGE.schema.json',d['revision'])))
 for ptr in d['pointers']:
  v=record
  for piece in ptr.split('/'):v=v[int(piece)] if isinstance(v,list) else v[piece]
  assert v==member['envelope']['path']
 if d['identity']==proof['selected_identity']:assert len(record['files_changed'])==562 and record['base_commit']==proof['delivery']['commit'] and record['base_commit']!=proof['original_base']
 for hist,intro in [(member['history'],member['introduction']),(member['payload_history'],member['payload_introduction'])]:
  for rev,binding in hist['nodes'].items():
   key=(rev,hist['path'])
   if key not in seen:assert obj(*key)==binding;seen.add(key)
  for rev,ps in hist['parents'].items():
   actual=git('show','-s','--format=%P',rev).decode().strip().split();assert ps==actual
   if rev in parents:assert parents[rev]==ps
   parents[rev]=ps
 data=native.read(ROOT,member['envelope']['path'],proof['original_selected']);assert sha(data)==member['raw_sha256'] and len(data)==member['raw_bytes'];native_raw.append(data)
 note('original_member_independent',path=member['envelope']['path'],declaration=d['revision'],pointers=d['pointers'],raw=identity(data))
assert all(v==native_raw[0] for v in native_raw)
assert list(parents[proof['delivery']['commit']])==proof['delivery']['parents']
for end in [proof['protected_base'],proof['original_selected']]:git('merge-base','--is-ancestor',proof['delivery']['commit'],end)
git('merge-base','--is-ancestor',proof['delivery']['original_record'],proof['delivery']['parents'][1])
m=proof['map_binding'];assert raw(m['object']['path'],proof['original_selected'])==raw(m['object']['path'],m['admission']);assert obj(proof['original_selected'],m['object']['path'])==m['object']
neutral,ns=neutral_sources_and_proof(proof,sources);assert study.custody_predicate(neutral,original_sources=ns)['status']=='CUSTODY_PREDICATE_DEMONSTRATED'
note('original_graph_and_neutral',git_path_states=len(seen),ordered_parent_rows=len(parents),result=result,neutral_synthetic_only=True)
# Focused independent hostile substitutions; definitions model cannot authorize host.
mutations={
 'declaration_object_sha':lambda p:p['members'][0]['declaration']['object'].update(sha256='0'*64),
 'pointer_wrong_exact_slot':lambda p:p['members'][0]['declaration'].update(pointers=['files_changed/0']),
 'history_object_other_member':lambda p:p['members'][0]['history'].update(original=p['members'][1]['envelope']),
 'payload_history_other_path':lambda p:p['members'][0]['payload_history'].update(path=p['members'][1]['envelope']['path']),
 'foreign_delivery_order':lambda p:p['delivery']['parents'].reverse(),
 'map_original_base':lambda p:p['map_binding'].update(original_base='1'*40),
 'source_role_tag':lambda p:p['members'][0]['representation'].update(native_read_observation='REVIEW_SOURCE_LINEAGE'),
 'caller_credential':lambda p:p.update(installed=True),
 'omitted_physical':lambda p:p['physical_paths'].pop(),
 'omitted_member':lambda p:p['members'].pop(),
 'changed_shared_parent':lambda p:next(iter(p['members'][0]['history']['parents'].values())).reverse(),
}
for name,mutation in mutations.items():
 p=copy.deepcopy(proof);mutation(p)
 if p==proof:continue
 try:study.custody_predicate(p,original_sources=sources)
 except (study.Denial,ValueError) as ex:note('hostile_substitution_denied',case=name,reason=str(ex))
 else:raise AssertionError(name)
# Independently exercise final clock/counter exhaustion with an already completed predicate.
clock=[0];budget=study.Budget({'groups':1},now=lambda:clock[0]);real=study.custody_predicate
try:
 def late(p,**kwargs):
  r=real(p,**kwargs);budget.used['groups']=2;clock[0]=study.DEADLINE_NS+1;return r
 study.custody_predicate=late
 result=study.atomic_study([proof],budget,original_sources=sources)
 assert not result['complete'] and result['accounted_paths']==result['accounted_bytes']==0 and result['groups']==['CUSTODY_DENIED']
 assert {'LIMIT_EXHAUSTED','DEADLINE_EXCEEDED'}<=set(result['reasons']) and result['elapsed_ns']==study.DEADLINE_NS+1 and result['consumed']['groups']==2
 note('simultaneous_late_exhaustion',result=result)
finally:study.custody_predicate=real
# Forward invalidation and truthful additive correction preserve frozen history.
oldR='fede00846c326c65672d69e047fd7a11f57c8bb0';oldT='75c4244719ae0274666abfbde1686489f18ea800'
git('merge-base','--is-ancestor',oldR,T)
old_manifest=json.loads(raw('HARNESS_DOCUMENT_MANIFEST.json',oldT));new_manifest=json.loads(raw('HARNESS_DOCUMENT_MANIFEST.json',T))
assert any('__pycache__' in r['path'] for r in old_manifest['files']) and not any('__pycache__' in r['path'] for r in new_manifest['files'])
for p in git('ls-tree','-r','--name-only',oldR,'--','docs/exec-plans/evidence/HG-065').decode().splitlines():
 if not p.endswith('/precommit_artifacts.py'):assert raw(p,oldR)==raw(p)
assert git('diff','--name-status',oldR,T).decode().splitlines()==['M\tHARNESS_DOCUMENT_MANIFEST.json','A\tdocs/exec-plans/evidence/HG-065/CANDIDATE_INVALIDATION.json','M\tdocs/exec-plans/evidence/HG-065/precommit_artifacts.py']
clar=json.loads((E/'PREPARATION_EXIT_CLARIFICATION.json').read_bytes());assert sha(raw('docs/exec-plans/evidence/HG-065/PRE_T_ATTEMPTS.json',oldT))==clar['supersedes_exit_interpretation_only']['sha256']
for row in clar['observations']:
 assert row['observed_wrapper_exit_code']==0 and row['child_exit_code'] is None and row['recorded_value_was_inferred']
 assert identity(Path(row['log']['path']).read_bytes())=={k:row['log'][k] for k in ('bytes','sha256')}
note('historical_failure_preservation',prior_candidate=oldR,prior_tested=oldT,old_manifest_failed=True,all_old_execution_evidence_unchanged=True,precommit_helper_forward_strengthened=True,preparation_child_exits=[None,None],acceptance_reuse=False)
# Independently classify every new artifact and run native full storage/history audit.
for p in changed:
 if not p.startswith('docs/exec-plans/evidence/HG-065/'):continue
 data=raw(p);native.envelope(data);assert native.reencoding_record(data) is None
 assert len(data)<= (native.STORED_LIMIT if p.endswith(('.gz','.xz')) else native.PLAIN_LIMIT)
note('native_all_current_artifacts_classified',count=sum(p.startswith('docs/exec-plans/evidence/HG-065/') for p in changed))
audit=native.audit(ROOT,B,R,'HG-065');assert not audit['errors'],audit
note('native_storage_history',result=audit)
# Precommit inventories must match exact committed trees, not current filesystem promises.
for receipt,rev in [('PRECOMMIT_CANDIDATE1.json','de696b52ff704b8fdd7e3ed1db127296638afe5c'),('PRECOMMIT_TESTED.json',oldT),('PRECOMMIT_CORRECTED_TESTED.json',T)]:
 doc=json.loads((E/receipt).read_bytes());assert not doc['errors']
 for row in doc['rows']:assert identity(raw(row['path'],rev))=={k:row[k] for k in ('bytes','sha256')}
 note('precommit_exact_rows',receipt=receipt,revision=rev,rows=len(doc['rows']))
last=json.loads(Path('/private/tmp/hg065-precommit-R2.json').read_bytes());assert not last['errors'] and len(last['rows'])==192
for row in last['rows']:assert identity(raw(row['path']))=={k:row[k] for k in ('bytes','sha256')}
assert last['staged_tree']==git('rev-parse',R+'^{tree}').decode().strip()
note('precommit_R_exact_tree',rows=192,tree=last['staged_tree'])
assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)
report={'base':B,'tested':T,'reviewed':R,'reviewer_scope':'SECURITY_DATA_BOUNDARY definitions only','checks':records,'immutable_read_count':len(reads),'immutable_reads_digest':sha(json.dumps(reads,sort_keys=True).encode()),'future_runtime_root_gates':'NOT_RUN'}
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
(OUT/'immutable_reads.json').write_text(json.dumps(reads,indent=2)+'\n')
print(json.dumps({'status':'PASS','records':len(records),'read_count':len(reads),'report':identity((OUT/'verification.json').read_bytes())}))
