"""Synthetic definition contexts plus exact immutable sample values; NOT trusted runtime proofs."""
import json
from pathlib import Path
from dataclasses import replace
from definition_oracle import FixtureContext,GUARDS,GAP_GUARDS,LineageObservation
from definition_data import strict_json
ROOT=Path(__file__).parent
read=lambda x:strict_json((ROOT/x).read_bytes(),262144 if x in ['TEMPLATE_CATALOG.json','SLOT_ROLES.json'] else 1048576)
OUTPUT=read('OUTPUT_TYPES.json');GRAMMAR=read('PLAIN_GRAMMAR.json');CATALOG=read('TEMPLATE_CATALOG.json');ROLES=read('SLOT_ROLES.json');SAMPLES=read('RECONSTRUCTION_SAMPLES.json');ROWS=read('ROWS.json');
from definition_binding_package import load_binding_package
BINDINGS=load_binding_package(ROOT)
def case(profile,neutral=False):
 sample=next(x for x in SAMPLES['samples'] if x['profile']==profile['profile']);row=next(x for x in ROWS['rows'] if x.get('grammar')==profile['profile']);values=dict(sample['slot_values']);owner=row['owner'];B=row['original_B'];T=row['record_T'];checks=tuple((x['check_id'],x['command']) for x in row['checks']);ref=row['ref'];bindings={}
 for token in profile['tokens']:
  if 'slot' in token and token['slot'].get('binding') in ['REPORT_T','SOURCE_T','PRODUCER_Z_PREFIX']:bindings[token['slot']['binding']]=values[token['slot']['alias']]
 if profile['decision']=='D3_POST_TEST_DIAGNOSTIC_PRODUCER':
  bindings['PRODUCER_Z']=next(x['producer_attribution']['Z'] for x in BINDINGS['rows'] if x['row']==row['row'])
 if neutral:
  owner='harness-governance-v0.1/HG-901';B='a'*40;T='b'*40;ref='docs/exec-plans/evidence/HG-901/report.log'
  checks=tuple(('fixture_check_'+str(n),'python3 fixture_command_'+str(n)+'.py') for n in range(len(checks)))
  if profile['decision']=='D4_COMPOSITE_WITH_INCOMPLETE_COMPONENT':
   composite_ordinal=next(q['ordinal'] for q in next(x for x in ROLES['profiles'] if x['profile']==profile['profile'])['check_claims'] if q['purpose']=='EXPLICIT_NON_EXECUTION_COMPOSITE');checks=tuple((name,row['checks'][n]['command'] if n==composite_ordinal else cmd) for n,(name,cmd) in enumerate(checks))
  bindings={k:('c'*7 if k=='PRODUCER_Z_PREFIX' else 'c'*40 if k=='PRODUCER_Z' else 'd'*40 if k=='REPORT_T' else 'e'*40) for k in bindings}
  for token in profile['tokens']:
   if 'slot' not in token:continue
   z=token['slot'];k=z['type'];binding=z.get('binding');v=values[z['alias']]
   if k=='OWNER_DISPLAY':v=('hg' if z['spelling']['case']=='lower' else 'HG')+('-' if z['spelling']['hyphenated'] else '')+'901'
   elif k=='DECLARED_COMMAND':v=checks[int(binding)][1]
   elif k=='ORIGINAL_CHECK_LABEL':v=checks[int(binding)][0]
   elif binding=='B':v=B
   elif binding=='T':v=T
   elif binding in bindings:v=bindings[binding]
   elif k=='INERT_HOST_PATH':v='/fixture/root'
   elif k=='GIT_REVISION_CLAIM':v='f'*40
   elif k=='SHA256_CLAIM':v='1'*64
   values[z['alias']]=v
 roles=next(x for x in ROLES['profiles'] if x['profile']==profile['profile']);states=tuple('EXPLICIT_NON_EXECUTION_COMPOSITE' if q['purpose']=='EXPLICIT_NON_EXECUTION_COMPOSITE' else 'UNKNOWN' for q in roles['check_claims']);absent=profile['decision']=='D1_MISSING_ORIGINAL_GENERAL'
 ctx=FixtureContext(owner,B,T,ref,checks,bindings,GUARDS,C='9'*40 if neutral else ROWS['authority_revision'],review_state='ABSENT_REQUIRED_GENERAL' if absent else 'PRESENT_BOUND_GENERAL',absence_proof=absent,parent_states=states,composite_declared_non_execution='EXPLICIT_NON_EXECUTION_COMPOSITE' in states)
 actual=next(x for x in BINDINGS['rows'] if x['row']==row['row'])
 if actual.get('lineage_gap'):
  a=actual['lineage_gap'];M='8'*40 if neutral else a['original_delivery']
  gap=LineageObservation(B,T,M,ctx.C,'6'*40 if neutral else a['tested_object']['tree'],'7'*40 if neutral else a['delivery_object']['tree'],('5'*40,) if neutral else tuple(a['tested_object']['parents']),('4'*40,) if neutral else tuple(a['delivery_object']['parents']),a['observed_ancestry_exit'])
  ctx=replace(ctx,guards=GAP_GUARDS,original_delivery=M,lineage_gap=gap)
 body=''.join(t['literal'] if 'literal' in t else values[t['slot']['alias']] for t in profile['tokens']).encode()
 return body,ctx,row,values
