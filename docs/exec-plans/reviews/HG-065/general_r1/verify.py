import ast,collections,hashlib,json,os,shlex,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
import yaml,jsonschema
ROOT=Path('/Users/davetian/.codex/worktrees/hg065-custody-delivery/KineticLoop'); OUT=Path('/private/tmp/hg065-general-r1')
B='e8e93bd32a83bd2fd6bf89951863d59b37e9d2b3'; T='dfd4c20b93112e9403eb21286c705cd31847eefd'; R='a2f2ff79565375e9bd0cca9013b11e61bf607cac'; E='docs/exec-plans/evidence/HG-065/'
sys.path.insert(0,str(ROOT));from tools.harness import compact_evidence as n,validate_harness as v
commands=[]
def git(*args):
 p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True); commands.append({'argv':['git',*args],'exit_code':p.returncode,'stdout_sha256':sha(p.stdout),'stdout_bytes':len(p.stdout),'stderr_sha256':sha(p.stderr)});assert p.returncode==0,(args,p.stderr);return p.stdout
def sha(x):return hashlib.sha256(x).hexdigest()
def ident(x):return dict(bytes=len(x),sha256=sha(x))
def obj(path,rev=R):return git('show',rev+':'+path)
def js(path):return json.loads(obj(path))
report={'B':B,'T':T,'R':R,'checks':[]}
assert git('rev-parse','HEAD').decode().strip()==R and not git('status','--porcelain')
assert git('rev-parse','refs/heads/master').decode().strip()==B
paths=git('diff','--name-only',B,R).decode().splitlines();report['changed_paths']=len(paths)
assert len(v.governance_allowed_patterns('HG-065'))==11 and all(v.matches(p,v.governance_allowed_patterns('HG-065')) for p in paths)
record=yaml.safe_load(obj('docs/exec-plans/governance/HG-065.yaml'));jsonschema.validate(record,js('HARNESS_CHANGE.schema.json'))
assert sorted(record['files_changed'])==sorted(paths) and record['base_commit']==B and record['tested_commit']==T
assert not record['packets_refined'] and not record['authority_entries_added']
assert sha(obj(E+'PACKET.md'))=='cb9b4803c9f6cd1ddef10166515375e3f45c0d55bb1c47b3a2c9cf1572d3e79c'
assert obj(E+'PACKET.md')==Path('/private/tmp/hg065-packet.md').read_bytes()
index=js('CURRENT_DOCUMENT_INDEX.json');report['authority']=[]
for x in index['documents']+index['machine_readable']:
 raw=obj(x['path']);assert sha(raw)==x['sha256'];report['authority'].append({'path':x['path'],**ident(raw)})
assert len(report['authority'])==30
for p in ['tools/harness/compact_evidence.py','tools/harness/local_gate.py','THREAD_REVIEW.schema.json','HARNESS_CHANGE.schema.json','CURRENT_REQUIREMENT_SET.json','FROZEN_BASELINE.json']:
 assert obj(p,B)==obj(p,R)
report['native_unchanged']=True
assert obj('HARNESS_DOCUMENT_MANIFEST.json',T)==obj('HARNESS_DOCUMENT_MANIFEST.json',R)
report['selected_manifest_errors']=v.governance_manifest_errors(ROOT,B,set(paths),R);assert not report['selected_manifest_errors']
report['suffix_errors']=v.governance_suffix_errors(ROOT,T,R,'HG-065','tested');assert not report['suffix_errors']
report['suffix_edges']=[]
for c in git('rev-list','--reverse',T+'..'+R).decode().splitlines():
 parents=git('rev-list','--parents','-n','1',c).decode().split()[1:];assert len(parents)==1
 rows=git('diff','--name-status',parents[0],c).decode().splitlines();assert all((l.startswith('A\t'+E) or l=='M\tdocs/exec-plans/governance/HG-065.yaml') for l in rows)
 report['suffix_edges'].append(dict(parent=parents[0],child=c,changes=len(rows),name_status_sha256=sha('\n'.join(rows).encode())))
idx=js(E+'checks-'+T[:12]+'/CHECK_INDEX.json');assert ident(obj(E+'checks-'+T[:12]+'/CHECK_INDEX.json'))['sha256']=='7c34a0327e52dd61dc0d57c7ffbf5d3691d3b39cbb40b0a0ca37f30d37147597'
assert idx['tested_commit']==T and idx['base_commit']==B
assert {x['check_id'] for x in idx['checks']}=={'definitions','validator','unit','harness','lint','typecheck','authority','diff'}
bindings=[];decoded={}
for check in idx['checks']:
 assert check['exit_code']==0 and check['execution_state']=='COMPLETED' and check['tested_commit']==T
 meta=json.loads(Path('/private/tmp/hg065-author-'+T[:12]+'/'+check['check_id']+'-command.json').read_bytes())
 for key in meta: assert meta[key]==check[key],(check['check_id'],key)
 assert shlex.join(check['argv'])==check['command']
 assert next(x for x in record['checks_run'] if x['check_id']==check['check_id'])=={'check_id':check['check_id'],'command':check['command'],'result':'PASS','evidence_ref':check['output_ref']}
 for a in check['artifacts']:
  raw=n.read(ROOT,a['evidence_ref'],R,tested=T,command=a['command'],exit_code=0)
  assert ident(raw)==a['raw_identity'] and raw==Path(a['source_file']).read_bytes()
  env=obj(a['evidence_ref']);assert ident(env)==a['envelope_identity'];payload=obj(json.loads(env)['payload']);assert ident(payload)==a['payload_identity']
  decoded[a['source_file']]=raw;bindings.append({'ref':a['evidence_ref'],'source_file':a['source_file'],**ident(raw),'command':a['command'],'tested_commit':T})
 report['checks'].append({'check_id':check['check_id'],'command':check['command'],'observed_exit':check['exit_code'],'source_metadata':ident(Path('/private/tmp/hg065-author-'+T[:12]+'/'+check['check_id']+'-command.json').read_bytes())})
assert len(bindings)==37;report['bindings']=bindings
report['positive_identities']={}
for name in ['definitions','validator','unit','harness']:
 check=next(x for x in idx['checks'] if x['check_id']==name)
 def get(suffix):
  aa=[x for x in check['artifacts'] if x['source_file'].endswith(suffix)];assert len(aa)==1,(name,suffix);return decoded[aa[0]['source_file']]
 c=json.loads(get('collection.json'));x=json.loads(get('execution.json'));j=ET.fromstring(get('junit.xml'))
 assert c['exit_code']==x['exit_code']==0 and not c['errors'] and not x['errors']
 nodes=c['collections'] if name=='definitions' else c['collections']['serial'];assert len(nodes)==len(set(nodes))
 expected=js(E+'FIXTURE_IDENTITIES.json')['identities'] if name=='definitions' else nodes
 assert nodes==expected
 if name=='definitions':assert x['collections']==nodes
 else:assert len(x['collections'])==(2 if name=='harness' else 1) and all(z==nodes for z in x['collections'].values())
 assert collections.Counter(x['started'])==collections.Counter(nodes)
 assert not c['started'] and not c['reports']
 for phase in ['setup','call','teardown']:
  rows=[z for z in x['reports'] if z.get('when' if name=='definitions' else 'phase')==phase]
  assert collections.Counter(z['nodeid'] for z in rows)==collections.Counter(nodes)
  assert all(z['outcome']=='passed' and z.get('wasxfail') is None for z in rows)
 assert len(x['reports'])==3*len(nodes)
 assert not j.findall('.//failure') and not j.findall('.//error') and not j.findall('.//skipped')
 tuples=[]
 for node in nodes:
  address,sep,params=node.partition('[');parts=address.split('::');tuples.append(('.'.join([parts[0][:-3].replace('/','.'),*parts[1:-1]]),parts[-1]+sep+params))
 assert collections.Counter(tuples)==collections.Counter((z.get('classname'),z.get('name')) for z in j.findall('.//testcase'))
 report['positive_identities'][name]={'count':len(nodes),'ordered_identities_sha256':sha(json.dumps(nodes,separators=(',',':')).encode()),'full_collection_start_setup_call_teardown_junit_equality':True}
# All changed bodies inspected as Git objects; current native classifiers on every own artifact.
report['inventory']=[];total=0
for path in paths:
 raw=obj(path);report['inventory'].append({'path':path,**ident(raw)})
 if path.startswith(E):
  total+=len(raw);assert len(raw)<=(8388608 if path.endswith(('.gz','.xz')) else 262144)
  m=n.envelope(raw);assert n.reencoding_record(raw) is None
  if m is not None:n.read(ROOT,path,R)
assert total<=16777216;report['stored_bytes']=total
# Normative ten compared directly to approved source, not merely author hashes.
pro=js(E+'DELIVERY_PROVENANCE.json');report['normative']=[]
source=Path('/private/tmp/hg058-custody-rule-r2')
for item in pro['normative']:
 raw=obj(E+item['path']);assert raw==(source/item['path']).read_bytes() and ident(raw)=={k:item[k] for k in ('bytes','sha256')};report['normative'].append(item)
# Entire AST equality with failed predecessor after only declared task identity substitutions.
old='7b6f760bd36446a464e33d68ecdd2747c29997eb'
assert git('rev-parse','refs/heads/codex/hg064-custody-definitions').decode().strip()==old
oldtest=obj('docs/exec-plans/evidence/HG-064/test_custody_definition.py',old).decode();newtest=obj(E+'test_custody_definition.py').decode()
assert ast.dump(ast.parse(oldtest.replace('HG064','HG065').replace('hg064','hg065').replace('HG-064','HG-065')))==ast.dump(ast.parse(newtest))
report['full_test_ast_equal']=True
oldfix=json.loads(obj('docs/exec-plans/evidence/HG-064/FIXTURE_INPUTS.json',old));newfix=js(E+'FIXTURE_INPUTS.json')
report['fixture_keys']={'old':list(oldfix),'new':list(newfix),'old_group':list(oldfix['group']),'new_group':list(newfix['group'])}
for key in newfix:
 if key!='group':assert newfix[key]==oldfix[key]
assert newfix['group']=={'members':[{'path':m['path']} for m in oldfix['group']['members']],'payload_paths':oldfix['group']['payload_paths']}
report['projection_equal']=True
# Escape spelling retains actual hostile constants and all four are rejected natively.
fn=next(z for z in ast.parse(newtest).body if isinstance(z,ast.FunctionDef) and 'classifier' in z.name and any(isinstance(q,ast.Constant) and isinstance(q.value,bytes) for q in ast.walk(z)))
vals=[z.value for z in ast.walk(fn) if isinstance(z,ast.Constant) and isinstance(z.value,bytes)]
report['hostile_constants']=[]
for body in vals:
 try:n.envelope(body)
 except ValueError as ex:report['hostile_constants'].append({**ident(body),'native_denial':str(ex)})
 else:raise AssertionError('hostile accepted')
assert len(vals)==4
# preserved unsuccessful prior cycle and clarification are additive.
assert obj(E+'PRE_T_ATTEMPTS.json')==obj(E+'PRE_T_ATTEMPTS.json','75c4244719ae0274666abfbde1686489f18ea800')
clar=js(E+'PREPARATION_EXIT_CLARIFICATION.json');assert all(x['child_exit_code'] is None and x['recorded_value_was_inferred'] for x in clar['observations'])
for x in clar['observations']:assert ident(Path(x['log']['path']).read_bytes())=={k:x['log'][k] for k in ('bytes','sha256')}
report['preparation_correction']='Additive explicit unknown child exits, original bytes preserved; preparation not accepted.'
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');(OUT/'git_commands.json').write_text(json.dumps(commands,indent=2)+'\n')
print(json.dumps({'status':'PASS','paths':len(paths),'bindings':len(bindings),'identities':report['positive_identities'],'stored_bytes':total}))
