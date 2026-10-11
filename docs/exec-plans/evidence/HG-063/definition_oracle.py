"""Bounded inert definition oracle. Fixture context is NOT a production trusted reader.
No Git, file lookup, shell, eval, import of report/source, or network during matching.
"""
from dataclasses import dataclass
from decimal import Decimal
import re

class Denied(ValueError):pass
GUARDS=('regular_record','regular_report','immutable_bytes','canonical_owner','unique_record','indexed_original_authority','original_duty_preserved','base_tested_binding','tested_delivery_lineage','protected_original_delivery','review_record_report_binding','one_hop_reference_binding','current_extant_review_guards','native_observations_complete','independent_guards_complete','budgets_complete')
LINEAGE_LIMIT='ORIGINAL_TESTED_DELIVERY_LINEAGE_NOT_ESTABLISHED'
GAP_GUARDS=tuple(x for x in GUARDS if x!='tested_delivery_lineage')+('named_base_tested_commit_objects','base_delivery_lineage','bound_original_delivery_metadata')
@dataclass(frozen=True)
class LineageObservation:
 B:str
 T:str
 M:str
 C:str
 tested_tree:str
 delivery_tree:str
 tested_parents:tuple
 delivery_parents:tuple
 observed_ancestry_exit:int
 # Synthetic immutable-reader observation only; never a production constructor.
@dataclass(frozen=True)
class FixtureContext:
 owner:str
 B:str
 T:str
 report_ref:str
 checks:tuple
 bindings:dict
 guards:tuple
 C:str
 review_state:str='PRESENT_BOUND_GENERAL'
 original_general_required:bool=True
 absence_proof:bool=False
 caller:str='GLOBAL_ARCHIVAL_GOVERNANCE_INVENTORY'
 selected_owner:bool=False
 fresh_self_archival:bool=False
 parent_states:tuple=()
 composite_declared_non_execution:bool=False
 cache_role:str=''
 original_delivery:str=''
 lineage_gap:object=None

class Budget:
 def __init__(self):self.nodes=0;self.compared=0
 def use(self,n=0):
  self.nodes+=1;self.compared+=n
  if self.nodes>262144 or self.compared>1048576:raise Denied('grammar-budget')

PATTERNS={
 'GIT_REVISION_CLAIM':r'[0-9a-f]{40}','REVISION_ABBREVIATION_CLAIM':r'[0-9a-f]{7,39}',
 'SHA256_CLAIM':r'[0-9a-f]{64}','INERT_HOST_PATH':r'(?:/|\$PWD/)[A-Za-z0-9_./@+\-]+',
 'INERT_REPO_DIRECTORY_CLAIM':r'(?:docs|tests|tools|src|migrations)/[A-Za-z0-9_./\-]+/',
 'INERT_REPO_PATH_CLAIM':r'(?:docs|tests|tools|src|migrations)/[A-Za-z0-9_./\-]+',
 'INERT_TEXT_ID':r'(?:HG|KL|hg|kl)-?[0-9]{3}[A-Za-z]?',
 'INERT_UUID_CLAIM':r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
 'INERT_ENV_LABEL':r'kl_[a-z0-9]+_[a-z0-9]+(?:_test)?',
 'DATE_CLAIM':r'[0-9]{4}-[0-9]{2}-[0-9]{2}',
 'COUNTER_CLAIM':r'[0-9]{1,7}','POSITIVE_COUNT_CLAIM':r'[0-9]{1,7}',
 'PERCENT_CLAIM':r'[0-9]{1,3}','DURATION_CLAIM':r'[0-9]+(?:\.[0-9]+)?',
 'INERT_IPV4_CLAIM':r'[0-9]{1,3}(?:\.[0-9]{1,3}){3}','INERT_PORT_CLAIM':r'[0-9]{1,5}',
 'VERSION_CLAIM':r'[0-9]+(?:\.[0-9]+){1,3}','CLOCK_HOURS_CLAIM':r'[0-9]{1,3}',
 'CLOCK_SUBMINUTE_CLAIM':r'[0-9]{2}','EXPLICIT_ZERO_EXIT_CLAIM':r'0',
 'PYTEST_PROGRESS_CLAIM':r'\.+','DECLARED_COMMAND':r'[^\x00\r\n]+','ORIGINAL_CHECK_LABEL':r'[^\x00\r\n]+','OWNER_DISPLAY':r'(?:HG|hg)-?[0-9]{3}'}
CAPS={'GIT_REVISION_CLAIM':40,'REVISION_ABBREVIATION_CLAIM':39,'SHA256_CLAIM':64,'INERT_HOST_PATH':1024,'INERT_REPO_PATH_CLAIM':1024,'INERT_REPO_DIRECTORY_CLAIM':1024,'INERT_TEXT_ID':80,'INERT_UUID_CLAIM':36,'INERT_ENV_LABEL':128,'DATE_CLAIM':10,'COUNTER_CLAIM':7,'POSITIVE_COUNT_CLAIM':7,'PERCENT_CLAIM':3,'DURATION_CLAIM':32,'VERSION_CLAIM':32,'INERT_IPV4_CLAIM':15,'INERT_PORT_CLAIM':5,'CLOCK_HOURS_CLAIM':3,'CLOCK_SUBMINUTE_CLAIM':2,'EXPLICIT_ZERO_EXIT_CLAIM':1,'PYTEST_PROGRESS_CLAIM':262144,'DECLARED_COMMAND':4096,'ORIGINAL_CHECK_LABEL':1024,'OWNER_DISPLAY':6}
def typed(s,v):
 k=s['type']
 if not isinstance(v,str) or not v or len(v.encode())>min(s['max_bytes'],CAPS[k]) or not re.fullmatch(PATTERNS[k],v):return False
 if k in ['COUNTER_CLAIM','POSITIVE_COUNT_CLAIM','PERCENT_CLAIM','CLOCK_HOURS_CLAIM','CLOCK_SUBMINUTE_CLAIM']:
  n=int(v)
  if n>1000000 or (k=='POSITIVE_COUNT_CLAIM' and n==0) or (k=='PERCENT_CLAIM' and n>100) or (k=='CLOCK_HOURS_CLAIM' and n>277) or (k=='CLOCK_SUBMINUTE_CLAIM' and n>59):return False
 if k=='DURATION_CLAIM' and Decimal(v)>1000000:return False
 if k=='INERT_IPV4_CLAIM' and any(int(x)>255 for x in v.split('.')):return False
 if k=='INERT_PORT_CLAIM' and not 1<=int(v)<=65535:return False
 if k=='VERSION_CLAIM' and any(int(x)>1000000 for x in v.split('.')):return False
 if k in ['INERT_REPO_PATH_CLAIM','INERT_REPO_DIRECTORY_CLAIM']:
  components=v[:-1].split('/') if k=='INERT_REPO_DIRECTORY_CLAIM' else v.split('/')
  if any(x in ['','.','..'] for x in components):return False
 if k=='DATE_CLAIM':
  from datetime import date
  try:date.fromisoformat(v)
  except ValueError:return False
 return True

def expected(slot,ctx):
 k=slot['type'];b=slot.get('binding')
 if k=='OWNER_DISPLAY':
  v=ctx.owner.split('/')[1];v=v.lower() if slot['spelling']['case']=='lower' else v.upper();return v if slot['spelling']['hyphenated'] else v.replace('-','')
 if k in ['DECLARED_COMMAND','ORIGINAL_CHECK_LABEL']:
  i=int(b)
  if not 0<=i<len(ctx.checks):raise Denied('check-ordinal')
  return ctx.checks[i][1 if k=='DECLARED_COMMAND' else 0]
 if b in ['B','T']:return getattr(ctx,b)
 if b in ['REPORT_T','SOURCE_T','PRODUCER_Z_PREFIX']:
  if b not in ctx.bindings:raise Denied('missing-revision-binding')
  return ctx.bindings[b]
 return None

def relation_ok(rel,vals,ctx):
 kind=rel['kind']
 if kind in ['same_transcribed_summary_count','same_single_report_pytest_count','same_transcribed_ratio_count','same_declared_current_harness_count','same_declared_current_unit_count']:return len(set(int(vals[x]) for x in rel['equals']))==1
 if kind=='progress_sum':return sum(len(vals[x]) for x in rel['parts'])==int(vals[rel['equals']])
 if kind=='progress_percent':
  total=int(vals[rel['total']]);done=0
  for part,pct in zip(rel['parts'],rel['percentages']):
   done+=len(vals[part])
   if int(vals[pct])!=done*100//total:return False
  return True
 if kind=='collection_total':return int(vals[rel['collected']])==int(vals[rel['passed']])+(int(vals[rel['deselected']]) if rel['deselected'] else 0)
 if kind=='elapsed_clock':return int(Decimal(vals[rel['seconds']]))==sum(int(vals[x])*m for x,m in zip(rel['hms'],[3600,60,1]))
 if kind=='positive_claim':return all(int(vals[x])>0 for x in rel['aliases'])
 if kind=='active_not_more_than_tasks':return int(vals[rel['active']])<=int(vals[rel['tasks']])
 if kind=='decreased_count':return int(vals[rel['before']])>int(vals[rel['after']])
 if kind=='not_record_T':return all(vals[x]!=ctx.T for x in rel['aliases'])
 raise Denied('unknown-relation')

def parse_profile(profile,raw,ctx,budget):
 from definition_schema import profile_relations
 profile_relations(profile)
 tokens=profile['tokens'];stack=[(0,0,{})];solutions=[]
 while stack:
  ti,pos,vals=stack.pop();budget.use()
  if ti==len(tokens):
   if pos==len(raw) and all(relation_ok(r,vals,ctx) for r in profile['claim_relations']):solutions.append(vals)
   if len(solutions)>1:raise Denied('ambiguous-slot-segmentation')
   continue
  token=tokens[ti]
  if set(token)=={'literal'}:
   lit=token['literal'];budget.use(len(lit.encode()))
   if raw.startswith(lit,pos):stack.append((ti+1,pos+len(lit),vals))
   continue
  if set(token)!={'slot'}:raise Denied('unknown-token')
  slot=token['slot'];k=slot.get('type')
  if k not in PATTERNS or not set(slot)<={'type','binding','max_bytes','spelling','alias'} or type(slot.get('max_bytes')) is not int or not 0<slot['max_bytes']<=CAPS[k]:raise Denied('slot-schema')
  fixed=expected(slot,ctx);alias=slot['alias']
  if alias in vals:
   if fixed is not None and vals[alias]!=fixed:continue
   fixed=vals[alias]
  if fixed is not None:
   budget.use(len(fixed.encode()))
   if raw.startswith(fixed,pos) and typed(slot,fixed):stack.append((ti+1,pos+len(fixed),dict(vals,**{alias:fixed})))
   continue
  maxend=min(len(raw),pos+slot['max_bytes']);ends=[]
  prefix=re.match(PATTERNS[k],raw[pos:maxend])
  if not prefix:continue
  maxend=min(maxend,pos+len(prefix.group()));budget.use(len(prefix.group().encode())+1)
  if ti+1==len(tokens):ends=[len(raw)]
  elif 'literal' in tokens[ti+1]:
   delimiter=tokens[ti+1]['literal']
   if not delimiter:raise Denied('empty-delimiter')
   end=raw.find(delimiter,pos+1,maxend+len(delimiter))
   while end!=-1 and end<=maxend:
    ends.append(end)
    if len(ends)>1024:raise Denied('slot-candidate-budget')
    end=raw.find(delimiter,end+1,maxend+len(delimiter))
  elif k in ['GIT_REVISION_CLAIM','SHA256_CLAIM','INERT_UUID_CLAIM','DATE_CLAIM','EXPLICIT_ZERO_EXIT_CLAIM']:ends=[pos+CAPS[k]]
  else:raise Denied('adjacent-variable-slots')
  for end in ends:
   value=raw[pos:end];budget.use(len(value.encode()))
   if typed(slot,value):stack.append((ti+1,end,dict(vals,**{alias:value})))
 return solutions

def observe(catalog,roles,body,ctx):
 if type(ctx) is not FixtureContext:raise Denied('raw-caller-context')
 if not all(type(getattr(ctx,k)) is bool for k in ['original_general_required','absence_proof','selected_owner','fresh_self_archival','composite_declared_non_execution']) or not all(type(getattr(ctx,k)) is str for k in ['owner','B','T','C','report_ref','review_state','caller','cache_role','original_delivery']) or type(ctx.checks) is not tuple or type(ctx.parent_states) is not tuple or type(ctx.bindings) is not dict:raise Denied('context-field-types')
 if ctx.caller!='GLOBAL_ARCHIVAL_GOVERNANCE_INVENTORY' or ctx.selected_owner or ctx.fresh_self_archival or ctx.cache_role:raise Denied('caller-isolation')
 if type(body) is not bytes or not 0<len(body)<=262144:raise Denied('body-size-type')
 try:raw=body.decode('utf-8')
 except UnicodeDecodeError:raise Denied('utf8')
 if any(x in raw for x in ['\x00','\r','\ufeff']):raise Denied('body-encoding')
 gap=ctx.lineage_gap
 if not ctx.original_general_required:raise Denied('independent-binding-guards')
 if gap is None:
  if ctx.guards!=GUARDS:raise Denied('independent-binding-guards')
 else:
  if type(gap) is not LineageObservation or ctx.guards!=GAP_GUARDS:raise Denied('lineage-gap-proof-or-independent-guards')
  if (gap.B,gap.T,gap.C,gap.M)!=(ctx.B,ctx.T,ctx.C,ctx.original_delivery):raise Denied('lineage-gap-object-binding')
  if any(type(x) is not str or not re.fullmatch('[0-9a-f]{40}',x) for x in [gap.B,gap.T,gap.M,gap.C,gap.tested_tree,gap.delivery_tree]):raise Denied('lineage-gap-commit-metadata')
  if any(type(parents) is not tuple or len(parents)>64 or len(set(parents))!=len(parents) or any(type(v) is not str or not re.fullmatch('[0-9a-f]{40}',v) for v in parents) for parents in [gap.tested_parents,gap.delivery_parents]):raise Denied('lineage-gap-parent-metadata')
  if type(gap.observed_ancestry_exit) is not int or gap.observed_ancestry_exit!=1 or gap.T==gap.M:raise Denied('lineage-gap-not-explicit-failed-ancestry')
  # Native success still requires its own full native lineage; this plain branch cannot waive it.
  if 'OBSERVED_EXACT_ZERO' in ctx.parent_states:raise Denied('lineage-gap-cannot-change-native-path')
 if not re.fullmatch(r'harness-governance-v0\.1/HG-[0-9]{3}',ctx.owner):raise Denied('owner')
 if not all(re.fullmatch('[0-9a-f]{40}',x) for x in [ctx.B,ctx.T,ctx.C]):raise Denied('revision')
 if ctx.report_ref.startswith('/') or '\\' in ctx.report_ref or not ctx.report_ref.startswith('docs/exec-plans/evidence/'+ctx.owner.split('/')[1]+'/') or any(x in ['','.','..'] for x in ctx.report_ref.split('/')):raise Denied('report-owner-path')
 if len({x[0] for x in ctx.checks})!=len(ctx.checks) or len(ctx.parent_states)!=len(ctx.checks) or any(type(x)!=tuple or len(x)!=2 or not all(type(v)==str and v and not any(z in v for z in ['\n','\r','\x00']) for v in x) for x in ctx.checks):raise Denied('check-tuples')
 if any(x not in ['UNKNOWN','OBSERVED_EXACT_ZERO','EXPLICIT_NON_EXECUTION_COMPOSITE'] for x in ctx.parent_states):raise Denied('authenticated-parent-contradiction')
 budget=Budget();matches=[]
 for profile in catalog['profiles']:
  if set(profile)!={'decision','profile','family','tokens','claim_relations','record_check_shape'} or profile['decision'] not in [None,'D1_MISSING_ORIGINAL_GENERAL','D2_DISTINCT_OLD_AND_RERUN_CLAIMS','D3_POST_TEST_DIAGNOSTIC_PRODUCER','D4_COMPOSITE_WITH_INCOMPLETE_COMPONENT','D5_CONTENT_REVISION_REUSE']:raise Denied('profile-schema')
  shape=profile['record_check_shape']
  if set(shape)!={'ordered_report_ref_check_count','results'} or type(shape['ordered_report_ref_check_count']) is not int or shape['results']!=['PASS']*shape['ordered_report_ref_check_count']:raise Denied('original-check-claim-shape')
  if shape['ordered_report_ref_check_count']!=len(ctx.checks):continue
  solutions=parse_profile(profile,raw,ctx,budget)
  if solutions:matches.append((profile,solutions[0]))
 if len(matches)!=1:raise Denied('unknown-or-ambiguous-whole-form')
 profile,vals=matches[0];decision=profile['decision'];needed={t['slot']['binding'] for t in profile['tokens'] if 'slot' in t and t['slot']['binding'] in ['REPORT_T','SOURCE_T','PRODUCER_Z_PREFIX']}
 if 'PRODUCER_Z_PREFIX' in needed:needed.add('PRODUCER_Z')
 if set(ctx.bindings)!=needed:raise Denied('unknown-or-missing-revision-binding')
 from definition_schema import validate_role
 if type(roles) is not dict or set(roles)!={'authority','profiles'} or type(roles['profiles']) is not list:raise Denied('roles-schema')
 role_matches=[x for x in roles['profiles'] if type(x) is dict and x.get('profile')==profile['profile']]
 if len(role_matches)!=1:raise Denied('missing-or-duplicate-role-profile')
 role=role_matches[0];validate_role(role,profile)
 if decision=='D1_MISSING_ORIGINAL_GENERAL':
  if ctx.review_state!='ABSENT_REQUIRED_GENERAL' or ctx.absence_proof is not True:raise Denied('missing-review-absence-duty')
 elif ctx.review_state!='PRESENT_BOUND_GENERAL' or ctx.absence_proof:raise Denied('original-general')
 if 'REPORT_T' in ctx.bindings and ctx.bindings['REPORT_T']==ctx.T:raise Denied('hidden-report-revision-mismatch')
 if 'SOURCE_T' in ctx.bindings and ctx.bindings['SOURCE_T']==ctx.T:raise Denied('hidden-content-reuse')
 if 'PRODUCER_Z_PREFIX' in ctx.bindings:
  if 'PRODUCER_Z' not in ctx.bindings or not re.fullmatch('[0-9a-f]{40}',ctx.bindings['PRODUCER_Z']) or ctx.bindings['PRODUCER_Z_PREFIX']!=ctx.bindings['PRODUCER_Z'][:7] or ctx.bindings['PRODUCER_Z']==ctx.T:raise Denied('producer-rebound-to-record')
 entries=[];native=[]
 for claim in role['check_claims']:
  n=claim['ordinal'];state=ctx.parent_states[n];purpose=claim['purpose']
  if state=='OBSERVED_EXACT_ZERO':native.append(n);continue
  if purpose=='EXPLICIT_NON_EXECUTION_COMPOSITE':
   if not ctx.composite_declared_non_execution or state!='EXPLICIT_NON_EXECUTION_COMPOSITE' or not re.fullmatch(r'PYTHONPATH=\"\$PWD/src\" PYTEST_ADDOPTS=\"-p no:cacheprovider\" Complete harness/unit rerun at tested_commit plus prior DB-suite evidence for the unchanged DB/production tree; Docker API is unavailable in this sandbox\.',ctx.checks[n][1]):raise Denied('not-declared-nonexecution-composite')
  elif state!='UNKNOWN':raise Denied('composite-label-on-execution')
  limits=list(claim['limitations'])
  if state=='UNKNOWN':limits.append('NO_NATIVE_RECORD_REVISION_EXECUTION_CERTIFICATION')
  if gap is not None:limits.append(LINEAGE_LIMIT)
  entries.append({'entry':(ctx.owner,ctx.checks[n][0],ctx.B,ctx.T,ctx.checks[n][1],ctx.report_ref,ctx.C),'documentary_validation':'BOUND_ORIGINAL_CLAIM','semantic_validation':'UNVERIFIED_ORIGINAL_COMPUTATION','historical_execution':'UNVERIFIED_RECORD_REVISION_EXECUTION','historical_review_acceptance':'NOT_CERTIFIED','acceptance_eligible':False,'purpose':purpose,'limitations':limits,'delivery_lineage':None if gap is None else {'limitation':LINEAGE_LIMIT,'B':gap.B,'T':gap.T,'original_delivery':gap.M,'C':gap.C,'tested_tree':gap.tested_tree,'delivery_tree':gap.delivery_tree,'tested_parents':gap.tested_parents,'delivery_parents':gap.delivery_parents,'observed_ancestry_exit':1,'tested_delivery_ancestor':False,'equivalence_certified':False,'source_head_role':'NOT_USED_FOR_RUNTIME_BINDING'},'revision_claims':dict(ctx.bindings),'exit_attribution':{'kind':'TRANSCRIBED_EXIT_ZERO_AT_OTHER_PRODUCER','producer':ctx.bindings['PRODUCER_Z'],'value':0,'execution_certified':False} if purpose=='POST_TEST_DIAGNOSTIC' else {'kind':'TRANSCRIBED_EXIT_ZERO_AT_RECORD_REVISION','producer':ctx.T,'value':0,'execution_certified':False} if purpose=='FINAL_REVISION_EXIT_ATTRIBUTION' else None})
 components=[]
 for component in role.get('component_claims',[]):
  value={}
  for key,item in component.items():
   if key.endswith('_alias'):value[key[:-6]]=int(vals[item]) if key in ['passed_alias','stopped_alias'] else vals[item]
   elif key=='revision_binding':value['revision']=getattr(ctx,item)
   else:value[key]=item
  value['execution_certified']=False;components.append(value)
 return {'component_claims':components,'profile':profile['profile'],'entries':entries,'native_ordinals':native,'lineage_gap_count':len(entries) if gap is not None else 0,'documentary_unverified_count':len(entries),'acceptance_eligible':False,'review_acceptance_certified':False,'covered_tuples':[(ctx.owner,x[0],ctx.B,ctx.T,x[1],ctx.report_ref,ctx.C) for x in ctx.checks]}

def exact_output_correspondence(expected,candidate):
 """Bounded exact value/type/order comparison, never provenance from output pins."""
 budget=Budget();stack=[(expected,candidate,0)]
 while stack:
  original,proposed,depth=stack.pop();budget.use()
  if depth>64 or type(proposed) is not type(original):raise Denied('output-does-not-correspond-to-original-observation')
  if type(original) is dict:
   if len(original)!=len(proposed) or any(type(k) is not str for k in proposed) or set(original)!=set(proposed):raise Denied('output-does-not-correspond-to-original-observation')
   stack.extend((original[k],proposed[k],depth+1) for k in original)
  elif type(original) in [list,tuple]:
   if len(original)!=len(proposed):raise Denied('output-does-not-correspond-to-original-observation')
   stack.extend((x,y,depth+1) for x,y in zip(original,proposed))
  elif type(original) is str:
   if len(proposed)>1048576:raise Denied('output-correspondence-budget')
   budget.use(len(original.encode('utf-8'))+len(proposed.encode('utf-8')))
   if original!=proposed:raise Denied('output-does-not-correspond-to-original-observation')
  elif type(original) in [int,bool,type(None)]:
   if original!=proposed:raise Denied('output-does-not-correspond-to-original-observation')
  else:raise Denied('unknown-output-correspondence-type')

def inventory(observation_inputs,declared_count,mandatory_tuples,independent_complete=False,mandatory_lineage_gap_tuples=(),mandatory_native_tuples=(),*,catalog=None,output_types=None,roles=None,candidate_outputs=None):
 """Inseparable unique parsing/emission/inventory. Outputs never establish provenance.
 Inputs are original immutable report bytes plus existing native-reader facts modeled
 by FixtureContext ONLY in fixtures; no new trusted-result dataclass/token/cache/API.
 candidate_outputs is optional untrusted corroboration: exact equality is required,
 but it cannot supply any expected fact, ordinal, profile, or attribution.
 """
 from definition_schema import keys,entry_tuple,RESULT_KEYS,output_entry_schema,component_schema,validate_output_definitions
 validate_output_definitions(output_types)
 if type(roles) is not dict or type(roles.get('profiles')) is not list:raise Denied('required-role-definition')
 if independent_complete is not True or type(observation_inputs) is not tuple or any(type(x) is not tuple for x in [mandatory_tuples,mandatory_native_tuples,mandatory_lineage_gap_tuples]):raise Denied('inventory-native-enumeration')
 for tuples in [mandatory_tuples,mandatory_native_tuples,mandatory_lineage_gap_tuples]:
  for t in tuples:entry_tuple(t)
  if len(set(tuples))!=len(tuples):raise Denied('duplicate-native-enumeration')
 if len({t[6] for t in mandatory_tuples})>1:raise Denied('mixed-current-validation-revisions')
 required=set(mandatory_tuples);native_expected=set(mandatory_native_tuples);gap_expected=set(mandatory_lineage_gap_tuples)
 if not native_expected<=required or not gap_expected<=required-native_expected:raise Denied('independent-partition-enumeration')
 if type(declared_count) is not int or declared_count<0:raise Denied('count-type')
 if type(catalog) is not dict or type(catalog.get('profiles')) is not list:raise Denied('required-catalog-definition')
 if len(observation_inputs)>len(mandatory_tuples):raise Denied('more-reports-than-mandatory-tuples')
 results=[];observed_covered=set()
 for request in observation_inputs:
  if type(request) is not tuple or len(request)!=2:raise Denied('original-observation-input-shape')
  body,ctx=request
  # Original ctx.checks ordering, raw report and immutable facts determine output.
  # No expected ordinal/profile/attribution is taken from candidate output.
  result=observe(catalog,roles,body,ctx)
  if observed_covered&set(result['covered_tuples']):raise Denied('duplicate-original-report-observation')
  observed_covered.update(result['covered_tuples']);results.append(result)
 # Ordinary native-only records are generated solely from independent native
 # enumeration. They do not become documentary observations or new native proof.
 groups={}
 for t in mandatory_native_tuples:
  if t not in observed_covered:groups.setdefault((t[0],t[2],t[3],t[5],t[6]),[]).append(t)
 for tuples in groups.values():
  results.append({'profile':'NATIVE_CAPTURE_PATH','component_claims':[],'native_ordinals':list(range(len(tuples))),'review_acceptance_certified':False,'entries':[],'covered_tuples':tuples,'documentary_unverified_count':0,'lineage_gap_count':0,'acceptance_eligible':False})
 if candidate_outputs is not None:
  if type(candidate_outputs) is not list or len(candidate_outputs)!=len(results):raise Denied('output-does-not-correspond-to-original-observation')
  for original,proposed in zip(results,candidate_outputs):exact_output_correspondence(original,proposed)
 covered=[];documentary=[];native=[];gaps=[]
 for r in results:
  keys(r,RESULT_KEYS,'report-output')
  if r['acceptance_eligible'] is not False or r['review_acceptance_certified'] is not False or type(r['profile']) is not str or any(type(r[k]) is not list for k in ['entries','covered_tuples','native_ordinals','component_claims']):raise Denied('report-output-values')
  for t in r['covered_tuples']:entry_tuple(t)
  if not r['covered_tuples'] or len(set(r['covered_tuples']))!=len(r['covered_tuples']):raise Denied('report-coverage')
  if any(tuple(t[i] for i in [0,2,3,5,6])!=tuple(r['covered_tuples'][0][i] for i in [0,2,3,5,6]) for t in r['covered_tuples']) or len({t[1] for t in r['covered_tuples']})!=len(r['covered_tuples']):raise Denied('mixed-report-owner-revision-ref-or-check')
  covered.extend(r['covered_tuples']);ordinals=r['native_ordinals']
  if any(type(n) is not int or not 0<=n<len(r['covered_tuples']) for n in ordinals) or len(set(ordinals))!=len(ordinals):raise Denied('native-ordinal-partition')
  local_native=[r['covered_tuples'][n] for n in ordinals];native.extend(local_native)
  if not set(local_native)<=native_expected:raise Denied('fabricated-native-partition')
  expected_doc=[t for n,t in enumerate(r['covered_tuples']) if n not in ordinals]
  if len(r['entries'])!=len(expected_doc):raise Denied('omitted-documentary-partition')
  if r['profile']=='NATIVE_CAPTURE_PATH':
   if expected_doc or r['component_claims']:raise Denied('native-path-documentary-or-component')
   role=None
  else:
   matching=[x for x in roles['profiles'] if x['profile']==r['profile']]
   if len(matching)!=1:raise Denied('unknown-or-duplicate-output-profile')
   role=matching[0]
   if len(role['check_claims'])!=len(r['covered_tuples']):raise Denied('output-profile-check-shape')
   component_schema(r['component_claims'],role,r['covered_tuples'][0][3])
  if r['entries'] and any(type(e) is not dict or e.get('revision_claims')!=r['entries'][0].get('revision_claims') or e.get('delivery_lineage')!=r['entries'][0].get('delivery_lineage') for e in r['entries']):raise Denied('mixed-report-revision-or-lineage-attribution')
  for e,t in zip(r['entries'],expected_doc):
   if type(e) is not dict or e.get('entry')!=t:raise Denied('substituted-documentary-partition')
   ordinal=r['covered_tuples'].index(t);output_entry_schema(e,role['check_claims'][ordinal],role,output_types);documentary.append(t)
   if e['delivery_lineage'] is not None:gaps.append(t)
  if type(r['documentary_unverified_count']) is not int or r['documentary_unverified_count']!=len(expected_doc):raise Denied('documentary-count')
  local_gap=sum(e['delivery_lineage'] is not None for e in r['entries'])
  if type(r['lineage_gap_count']) is not int or r['lineage_gap_count']!=local_gap:raise Denied('lineage-gap-count')
 if len(set(covered))!=len(covered) or set(covered)!=required or len(set(documentary))!=len(documentary) or len(set(native))!=len(native):raise Denied('missing-duplicate-extra-mandatory-entry')
 if set(native)!=native_expected or set(documentary)!=required-native_expected or set(native)&set(documentary):raise Denied('complete-documentary-native-partition')
 if set(gaps)!=gap_expected:raise Denied('hidden-extra-lineage-gap')
 if len(documentary)!=declared_count:raise Denied('exact-documentary-count')
 return {'observations':results,'lineage_gap_count':len(gaps),'documentary_unverified_count':len(documentary),'limitations_visible':True,'historical_execution_semantics_review_certified':False,'acceptance_eligible':False}
