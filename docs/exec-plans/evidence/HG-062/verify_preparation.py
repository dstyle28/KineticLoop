from pathlib import Path
import subprocess,json,hashlib,re
p=Path('/private/tmp/hg058-remaining-rule'); bind=json.loads((p/'ORIGINAL_BINDINGS.json').read_text()); base=bind['base']
def git(*args): return subprocess.check_output(['git',*args])
def sha(b): return hashlib.sha256(b).hexdigest()
def validate(x,s):
 if 'anyOf' in s:
  for q in s['anyOf']:
   try: validate(x,q); return
   except AssertionError: pass
  raise AssertionError('anyOf')
 t=s.get('type'); types={'object':dict,'array':list,'string':str,'boolean':bool,'integer':int,'number':(int,float),'null':type(None)}
 if t: assert isinstance(x,types[t]) and (t not in ('integer','number') or not isinstance(x,bool)),t
 if isinstance(x,dict):
  assert set(s.get('required',[]))<=set(x)
  if s.get('additionalProperties') is False: assert set(x)<=set(s.get('properties',{}))
  for k,v in x.items():
   if k in s.get('properties',{}): validate(v,s['properties'][k])
 elif isinstance(x,list):
  for v in x: validate(v,s['items'])
 elif isinstance(x,str):
  assert len(x)<=s.get('maxLength',1<<30)
  if 'pattern' in s: assert re.search(s['pattern'],x)
 elif isinstance(x,(int,float)) and not isinstance(x,bool):
  assert x>=s.get('minimum',float('-inf'))
  assert x<=s.get('maximum',float('inf'))
forms=json.loads((p/'CLOSED_DOCUMENTARY_FORMS.json').read_text()); checks=[]; mapping=[]
for row in bind['rows']:
 for report in row['reports']:
  b=git('show',row['original_merge']+':'+report['path']); assert sha(b)==report['sha256']; assert b==git('show',base+':'+report['path'])
  matches=[]
  for name,q in forms['profiles'].items():
   try: validate(json.loads(b),q['schema']); matches.append(name)
   except AssertionError: pass
  assert len(matches)==1; checks.append({'report':report['path'],'immutable_M_current_byte_equality':True,'unique_prospective_grammar':matches[0],'computation_execution_review_acceptance':'NOT_CERTIFIED'})
 authority=[]
 for rev in [row['tested'],row['reviewed']]:
  idx=json.loads(git('show',rev+':CURRENT_DOCUMENT_INDEX.json')); entries=idx['documents']+idx.get('machine_readable',[])
  selected=[]
  for suffix in ['HARNESS_CHANGE.schema.json','THREAD_REVIEW.schema.json','docs/harness/HARNESS_GOVERNANCE_CONTRACT.md','docs/harness/THREAD_REVIEW_CONTRACT.md']:
   e=[e for e in entries if e['path'].endswith(suffix)]; assert len(e)==1; e=e[0]; b=git('show',rev+':'+e['path']); assert sha(b)==e['sha256']; selected.append({'path':e['path'],'sha256':sha(b)})
  authority.append({'revision':rev,'indexed_bindings':selected})
 assert authority[0]['indexed_bindings']==authority[1]['indexed_bindings']
 mapping.append({'owner':row['owner'],'original_authorities':authority,'record_storage':'R/M/current identical; T is producer revision','review_binding':'original GENERAL at M, status ORIGINAL_REVIEW_LABEL_ONLY, RRO NOT_CERTIFIED','forms':[c['unique_prospective_grammar'] for c in checks if c['report'] in [r['path'] for r in row['reports']]]})
# Deliberate research-only YAML list extraction, no runtime parser or semantic verifier.
text=(p/'HG-048-record.yaml').read_text(); declared=text.split('files_changed:\n',1)[1].split('\nchecks:',1)[0]; paths=set(re.findall(r'^- ([^\n]+)$',declared,re.M))
scope=json.loads((p/'sample-SCOPE_AUDIT.json').read_text()); assert len(scope['files_changed'])==len(set(scope['files_changed'])); assert set(scope['files_changed'])<=paths
bench=json.loads((p/'sample-BENCHMARK_INDEX.json').read_text()); comp=json.loads((p/'sample-COMPARISON.json').read_text()); row=next(r for r in bind['rows'] if r['owner'].endswith('HG-048'))
codec_path='docs/exec-plans/evidence/HG-048/CODEC_SOURCE.json'; codec=git('show',row['original_merge']+':'+codec_path); assert codec_path in paths and json.loads(codec)==bench['codec_source']; assert codec==git('show',base+':'+codec_path)
assert subprocess.run(['git','merge-base','--is-ancestor',bench['codec_source']['source_revision'],row['tested']],capture_output=True).returncode==1
runs={r['label']:r for r in bench['final_runs']}; comparisons={r['run']:r for r in comp['runs']}; assert set(runs)==set(comparisons)
for label,c in comparisons.items():
 r=runs[label]
 for field in ['workers','tests','exit_code','wall_seconds']: assert c[field]==r[field]
checks += [{'scope_canonical_declared_subset':True,'complete_diff_or_frozen_equality':'NOT_CERTIFIED'},{'comparison_fields_match_explicit_benchmark_runs':True,'execution_identity_equality':'NOT_CERTIFIED'},{'research_only_original_codec_document_equality':True,'runtime_companion_selector':'NONE','source_nonancestor_T_preserved':True,'source_path_identity':'UNVERIFIED'}]
(p/'AUTHORITY_MAPPING.json').write_text(json.dumps({'authority':'DRAFT_ORIGINAL_AUTHORITY_MAPPING_ONLY','protected_base':base,'profiles':mapping,'protected_hg060_hg061_contract':{'path':'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md','sha256':sha(git('show',base+':docs/harness/HARNESS_GOVERNANCE_CONTRACT.md')),'amendment':'New documentary global-inventory category only; HG061 initial form unchanged'},'runtime_acceptance':'NOT_RUN'},indent=2)+'\n')
(p/'PREPARATION_CHECKS_R3.json').write_text(json.dumps({'purpose':'Read-only original-byte, prospective grammar and limited documentary binding research; NOT task/runtime acceptance','checks':checks,'original_producer_execution':'UNVERIFIED','historical_review_acceptance':'NOT_CERTIFIED','runtime_acceptance':'NOT_RUN'},indent=2)+'\n')
print(json.dumps({'read_only_research_checks':len(checks),'grammar_matches':5,'task_or_runtime_PASS':False}))
