"""Closed inert definition/output schema; no provenance reader or authorization API."""
import re
from definition_oracle import Denied, PATTERNS, CAPS, LINEAGE_LIMIT
INTEGER={'COUNTER_CLAIM','POSITIVE_COUNT_CLAIM','PERCENT_CLAIM','CLOCK_HOURS_CLAIM','CLOCK_SUBMINUTE_CLAIM','EXPLICIT_ZERO_EXIT_CLAIM'}
RELATIONS={
 **{k:{'equals':'integer_alias_list_min2'} for k in ['same_transcribed_summary_count','same_single_report_pytest_count','same_transcribed_ratio_count','same_declared_current_harness_count','same_declared_current_unit_count']},
 'progress_sum':{'parts':'progress_alias_list','equals':'integer_alias'},
 'progress_percent':{'parts':'progress_alias_list','percentages':'percent_alias_list','total':'integer_alias'},
 'collection_total':{'collected':'integer_alias','passed':'integer_alias','deselected':'nullable_integer_alias'},
 'elapsed_clock':{'seconds':'duration_alias','hms':'clock_alias_list_exact3'},
 'positive_claim':{'aliases':'integer_alias_list'},
 'not_record_T':{'aliases':'revision_alias_list'},
 'active_not_more_than_tasks':{'tasks':'integer_alias','active':'integer_alias'},
 'decreased_count':{'before':'integer_alias','after':'integer_alias'}}
DIMENSIONS={'documentary_validation':'BOUND_ORIGINAL_CLAIM','semantic_validation':'UNVERIFIED_ORIGINAL_COMPUTATION','historical_execution':'UNVERIFIED_RECORD_REVISION_EXECUTION','historical_review_acceptance':'NOT_CERTIFIED','acceptance_eligible':False}
ENTRY_KEYS={'entry',*DIMENSIONS,'purpose','limitations','revision_claims','exit_attribution','delivery_lineage'}
RESULT_KEYS={'component_claims','profile','entries','native_ordinals','lineage_gap_count','documentary_unverified_count','acceptance_eligible','review_acceptance_certified','covered_tuples'}
GAP_KEYS={'limitation','B','T','original_delivery','C','tested_tree','delivery_tree','tested_parents','delivery_parents','observed_ancestry_exit','tested_delivery_ancestor','equivalence_certified','source_head_role'}
def keys(value,expected,label):
 if type(value) is not dict or set(value)!=set(expected):raise Denied(label+'-schema')
def rev(v):return type(v) is str and bool(re.fullmatch('[0-9a-f]{40}',v))
def relation_schema(rel,aliases):
 if type(rel) is not dict or type(rel.get('kind')) is not str or rel['kind'] not in RELATIONS:raise Denied('relation-kind')
 spec=RELATIONS[rel['kind']];keys(rel,{'kind',*spec},'relation')
 def one(v,role):
  if type(v) is not str or v not in aliases:raise Denied('relation-alias')
  typ=aliases[v]
  allowed=INTEGER if role=='integer' else {'PYTEST_PROGRESS_CLAIM'} if role=='progress' else {'PERCENT_CLAIM'} if role=='percent' else {'DURATION_CLAIM'} if role=='duration' else {'GIT_REVISION_CLAIM'} if role=='revision' else {'CLOCK_HOURS_CLAIM','CLOCK_SUBMINUTE_CLAIM'}
  if typ not in allowed:raise Denied('relation-alias-role')
 for name,typ in spec.items():
  val=rel[name]
  if typ=='nullable_integer_alias' and val is None:continue
  if '_list' in typ:
   minimum=2 if typ.endswith('min2') else 1
   if type(val) is not list or len(val)<minimum or len(val)>1024 or any(type(x) is not str for x in val) or len(set(val))!=len(val):raise Denied('relation-array')
   if typ.endswith('exact3') and len(val)!=3:raise Denied('relation-clock-arity')
   for alias in val:one(alias,typ.split('_')[0])
   if typ=='clock_alias_list_exact3' and [aliases[v] for v in val]!=['CLOCK_HOURS_CLAIM','CLOCK_SUBMINUTE_CLAIM','CLOCK_SUBMINUTE_CLAIM']:raise Denied('relation-clock-order')
  else:one(val,'integer' if typ.startswith('nullable') else typ.split('_')[0])
 if rel['kind']=='progress_percent' and len(rel['parts'])!=len(rel['percentages']):raise Denied('relation-progress-arity')
def profile_relations(profile):
 if type(profile.get('claim_relations')) is not list:raise Denied('relation-list')
 aliases={}
 for token in profile['tokens']:
  if type(token) is not dict or set(token) not in [{'slot'},{'literal'}]:raise Denied('token-definition-schema')
  if 'literal' in token and (type(token['literal']) is not str or not token['literal']):raise Denied('literal-definition')
  if 'slot' in token:
   slot=token['slot']
   if type(slot) is not dict or not {'type','binding','max_bytes','alias'}<=set(slot) or not set(slot)<={'type','binding','max_bytes','alias','spelling'}:raise Denied('slot-definition-schema')
   a=slot.get('alias');typ=slot.get('type')
   if type(a) is not str or not a or type(typ) is not str or typ not in PATTERNS:raise Denied('slot-alias-type')
   if type(slot['max_bytes']) is not int or not 0<slot['max_bytes']<=CAPS[typ]:raise Denied('slot-definition-cap')
   binding=slot['binding']
   if typ in ['DECLARED_COMMAND','ORIGINAL_CHECK_LABEL']:
    if type(binding) is not str or not re.fullmatch('[0-9]+',binding) or int(binding)>=profile['record_check_shape']['ordered_report_ref_check_count']:raise Denied('slot-definition-command-binding')
   elif binding not in [None,'D','B','T','REPORT_T','SOURCE_T','PRODUCER_Z_PREFIX']:raise Denied('slot-definition-binding')
   if typ=='OWNER_DISPLAY':
    keys(slot.get('spelling'),{'case','hyphenated'},'owner-spelling')
    if slot['spelling']['case'] not in ['lower','upper'] or type(slot['spelling']['hyphenated']) is not bool or binding!='D':raise Denied('owner-spelling-values')
   elif 'spelling' in slot:raise Denied('extra-spelling')
   if a in aliases and aliases[a]!=typ:raise Denied('alias-role-conflict')
   aliases[a]=typ
 for rel in profile['claim_relations']:relation_schema(rel,aliases)
def entry_tuple(t):
 if type(t) is not tuple or len(t)!=7 or any(type(x) is not str or not x for x in t):raise Denied('output-entry-tuple')
 owner,check,B,T,cmd,ref,C=t
 if not re.fullmatch(r'harness-governance-v0\.1/HG-[0-9]{3}',owner) or not all(rev(v) for v in [B,T,C]):raise Denied('output-entry-identity')
 if len(check.encode())>1024 or len(cmd.encode())>4096 or any(x in check+cmd for x in ['\r','\n','\x00']):raise Denied('output-entry-command')
 if not ref.startswith('docs/exec-plans/evidence/'+owner.split('/')[1]+'/') or '\\' in ref or any(x in ['','.','..'] for x in ref.split('/')):raise Denied('output-entry-ref')
def gap_schema(g,entry):
 keys(g,GAP_KEYS,'output-lineage')
 if g['limitation']!=LINEAGE_LIMIT or type(g['observed_ancestry_exit']) is not int or g['observed_ancestry_exit']!=1 or g['tested_delivery_ancestor'] is not False or g['equivalence_certified'] is not False or g['source_head_role']!='NOT_USED_FOR_RUNTIME_BINDING':raise Denied('output-lineage-values')
 if not all(rev(g[k]) for k in ['B','T','original_delivery','C','tested_tree','delivery_tree']):raise Denied('output-lineage-objects')
 if (g['B'],g['T'],g['C'])!=(entry[2],entry[3],entry[6]) or g['T']==g['original_delivery']:raise Denied('output-lineage-binding')
 for k in ['tested_parents','delivery_parents']:
  a=g[k]
  if type(a) is not tuple or len(a)>64 or len(set(a))!=len(a) or not all(rev(x) for x in a):raise Denied('output-lineage-parents')
def validate_output_definitions(output):
 if type(output) is not dict or output.get('mandatory_dimensions')!={k:[v] for k,v in DIMENSIONS.items()} or output.get('unknown_output_field_enum_or_fabricated_acceptance')!='DENY':raise Denied('required-output-definition')
 if output.get('exclusive_caller')!='GLOBAL_ARCHIVAL_GOVERNANCE_INVENTORY':raise Denied('output-caller-definition')
def component_schema(values,role,entry_T):
 if type(values) is not list or len(values)!=len(role['component_claims']):raise Denied('output-components-count')
 for value,template in zip(values,role['component_claims']):
  expected={k[:-6] if k.endswith('_alias') else 'revision' if k=='revision_binding' else k for k in template}|{'execution_certified'}
  keys(value,expected,'output-component')
  if value['execution_certified'] is not False:raise Denied('output-component-certification')
  for k,v in template.items():
   field=k[:-6] if k.endswith('_alias') else 'revision' if k=='revision_binding' else k
   actual=value[field]
   if k in ['passed_alias','stopped_alias']:
    if type(actual) is not int or not 1<=actual<=1000000:raise Denied('output-component-count')
   elif k=='revision_alias':
    if not rev(actual) or actual==entry_T:raise Denied('output-component-prior-revision')
   elif k=='revision_binding':
    if actual!=entry_T:raise Denied('output-component-revision-binding')
   elif actual!=v:raise Denied('output-component-enum')
def output_entry_schema(e,claim,role,output):
 keys(e,ENTRY_KEYS,'entry-output');entry_tuple(e['entry'])
 for k,v in DIMENSIONS.items():
  if type(e[k]) is not type(v) or e[k]!=v:raise Denied('entry-noncertification-dimension')
 if e['purpose']!=claim['purpose'] or e['purpose'] not in output['purpose_enums']:raise Denied('entry-purpose')
 gap=e['delivery_lineage'];limits=list(claim['limitations'])
 if e['purpose']!='EXPLICIT_NON_EXECUTION_COMPOSITE':limits.append('NO_NATIVE_RECORD_REVISION_EXECUTION_CERTIFICATION')
 if gap is not None:limits.append(LINEAGE_LIMIT);gap_schema(gap,e['entry'])
 if type(e['limitations']) is not list or e['limitations']!=limits or len(set(limits))!=len(limits) or not all(x in output['limitation_enums'] for x in limits):raise Denied('entry-limitations')
 bindings=e['revision_claims'];required=set(role['revision_bindings'])
 if 'PRODUCER_Z_PREFIX' in required:required.add('PRODUCER_Z')
 keys(bindings,required,'entry-revision-claims');T=e['entry'][3]
 for k,v in bindings.items():
  if k=='PRODUCER_Z_PREFIX':
   if type(v) is not str or not re.fullmatch('[0-9a-f]{7}',v) or v!=bindings['PRODUCER_Z'][:7]:raise Denied('entry-producer-prefix')
  elif not rev(v) or v==T:raise Denied('entry-revision-role')
 exit_value=e['exit_attribution'];purpose=e['purpose']
 if purpose not in ['POST_TEST_DIAGNOSTIC','FINAL_REVISION_EXIT_ATTRIBUTION']:
  if exit_value is not None:raise Denied('entry-extra-exit-attribution')
 else:
  keys(exit_value,{'kind','producer','value','execution_certified'},'entry-exit')
  expected_kind='TRANSCRIBED_EXIT_ZERO_AT_OTHER_PRODUCER' if purpose=='POST_TEST_DIAGNOSTIC' else 'TRANSCRIBED_EXIT_ZERO_AT_RECORD_REVISION'
  producer=bindings['PRODUCER_Z'] if purpose=='POST_TEST_DIAGNOSTIC' else T
  if exit_value['kind']!=expected_kind or exit_value['producer']!=producer or type(exit_value['value']) is not int or exit_value['value']!=0 or exit_value['execution_certified'] is not False:raise Denied('entry-exit-values')

def validate_role(role,profile):
 keys(role,{'profile','token_roles','phases','component_claims','check_claims','revision_bindings','literal_policy'},'role-definition')
 aliases={t['slot']['alias']:t['slot']['type'] for t in profile['tokens'] if 'slot' in t}
 expected={str(i):'CLOSED_ORIGINAL_STATEMENT' if 'literal' in t else t['slot']['binding'] or 'INERT_ATTRIBUTION' for i,t in enumerate(profile['tokens'])}
 if role['profile']!=profile['profile'] or role['token_roles']!=expected or type(role['literal_policy']) is not str:raise Denied('role-token-binding')
 if type(role['phases']) is not list or type(role['component_claims']) is not list or type(role['check_claims']) is not list or type(role['revision_bindings']) is not list:raise Denied('role-field-types')
 bindings=sorted({t['slot']['binding'] for t in profile['tokens'] if 'slot' in t and t['slot']['binding'] in ['REPORT_T','SOURCE_T','PRODUCER_Z_PREFIX']})
 if role['revision_bindings']!=bindings:raise Denied('role-revision-bindings')
 for n,phase in enumerate(role['phases']):
  base={'phase','kind','terminal_alias','progress_aliases','percent_aliases','collection_aliases','deselected_alias','native_execution'}
  kind=phase.get('kind') if type(phase) is dict else None
  if kind not in ['TRANSCRIBED_PYTEST_PASS_SUMMARY','TRANSCRIBED_SOURCE_SUITE_PASS_SUMMARY']:raise Denied('phase-kind')
  keys(phase,base|({'revision_binding','suite'} if kind=='TRANSCRIBED_SOURCE_SUITE_PASS_SUMMARY' else set()),'phase')
  if type(phase['phase']) is not int or phase['phase']!=n or phase['native_execution']!='NOT_CERTIFIED' or aliases.get(phase['terminal_alias'])!='POSITIVE_COUNT_CLAIM':raise Denied('phase-terminal')
  for k,types in [('progress_aliases',{'PYTEST_PROGRESS_CLAIM'}),('percent_aliases',{'PERCENT_CLAIM'}),('collection_aliases',INTEGER)]:
   values=phase[k]
   if type(values) is not list or any(type(x) is not str or aliases.get(x) not in types for x in values) or len(set(values))!=len(values):raise Denied('phase-array-role')
  if phase['deselected_alias'] is not None and aliases.get(phase['deselected_alias']) not in INTEGER:raise Denied('phase-deselected-role')
  if kind=='TRANSCRIBED_SOURCE_SUITE_PASS_SUMMARY' and (phase['revision_binding']!='SOURCE_T' or phase['suite'] not in ['harness','unit','database']):raise Denied('phase-source-suite')
 if len(role['check_claims'])!=profile['record_check_shape']['ordered_report_ref_check_count']:raise Denied('role-check-count')
 for n,claim in enumerate(role['check_claims']):
  keys(claim,{'ordinal','purpose','limitations'},'check-role')
  if type(claim['ordinal']) is not int or claim['ordinal']!=n or claim['purpose'] not in ['CONTENT_REVISION_OR_SCOPE_CLAIM','EXPLICIT_NON_EXECUTION_COMPOSITE','FINAL_RERUN_ASSERTION','FINAL_REVISION_EXIT_ATTRIBUTION','ORIGINAL_CHECK_CLAIM','OTHER_REPORT_REVISION_CLAIM','POST_TEST_DIAGNOSTIC']:raise Denied('check-role-purpose')
  if type(claim['limitations']) is not list or any(type(x) is not str for x in claim['limitations']) or len(set(claim['limitations']))!=len(claim['limitations']):raise Denied('check-role-limitations')
 components={
 'CURRENT_HARNESS_ASSERTION':({'role','revision_binding','passed_alias','state'},'REPORTED_PASS'),
 'CURRENT_UNIT_ASSERTION':({'role','revision_binding','passed_alias','state'},'REPORTED_PASS'),
 'INCOMPLETE_FULL_INVOCATION':({'role','revision','passed_alias','stopped_alias','state','reason'},'INCOMPLETE'),
 'PRIOR_DB_ASSERTION':({'role','revision_alias','passed_alias','state'},'REPORTED_PRIOR_PASS')}
 seen=[]
 for item in role['component_claims']:
  if type(item) is not dict or type(item.get('role')) is not str or item['role'] not in components:raise Denied('component-definition-role')
  fields,state=components[item['role']];keys(item,fields,'component-definition');seen.append(item['role'])
  if item['state']!=state:raise Denied('component-definition-state')
  for k in ['passed_alias','stopped_alias']:
   if k in item and (type(item[k]) is not str or aliases.get(item[k]) not in INTEGER):raise Denied('component-definition-count-alias')
  if 'revision_alias' in item and aliases.get(item['revision_alias'])!='GIT_REVISION_CLAIM':raise Denied('component-definition-revision-alias')
  if 'revision_binding' in item and item['revision_binding']!='T':raise Denied('component-definition-revision-binding')
  if 'revision' in item and item['revision']!='UNSPECIFIED_IN_ORIGINAL_REPORT':raise Denied('component-definition-unspecified-revision')
  if 'reason' in item and item['reason']!='DOCKER_API_DENIED':raise Denied('component-definition-reason')
 if seen and seen!=list(components):raise Denied('component-definition-order-or-count')
