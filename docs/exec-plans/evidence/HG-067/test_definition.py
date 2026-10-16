"""Hypothetical conformance tests. No actual host/native observations are created."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
import jsonschema
from definition_oracle import (ROOT,LIMITS,PHASES,CONTEXTS,FULL_SCHEMA,InvalidDefinition,
 canonical,decode_bounded,seal_record,validate_record,validate_bytes,validate_emergency,
 trace_template,validate_trace,phase_clock,OVERALL_NS,WORKER_NS,TAIL_NS,GRACE_NS)

ERRORS=(InvalidDefinition,jsonschema.ValidationError,ValueError,UnicodeError)
def example(route='PREIMPORT', acquisition=None):
 if acquisition is None:acquisition='EXISTING_CHECKOUT' if route=='PREIMPORT' else 'BARE_CLONE'
 owned={'store_device':1,'store_inode':20,'objects_device':1,'objects_inode':21}
 pins={'revision':'a'*40,'protected':'b'*40,'tree':'c'*40,'controller':'d'*64,'release':'a'*40,
  'repository_id':1,'task':'harness-governance-v0.1/HG-058',
  'store_device':1,'store_inode':10,'objects_device':1,'objects_inode':11,
  'metadata_snapshot_sha256':'e'*64,'authority_sha256':'f'*64,'source_kind':'CHECKOUT'}
 if route=='FINAL':pins.update(owned,source_kind='BARE_OWNED' if acquisition=='BARE_CLONE' else 'CHECKOUT')
 value={'format':'host-preparation-result-draft-v4','invocation':'0'*32,'route':route,
  'status':'PREPARATION_COMPLETE','limits_sha256':FULL_SCHEMA['properties']['limits_sha256']['const'],
  'acquisition':acquisition,'initial':pins,'terminal':copy.deepcopy(pins),'owned_store':owned,
  'complete':True,'counter_state':'EXACT','elapsed_ns':20000000,'elapsed_observation':'LAST_SAMPLE_BEFORE_FINAL_ENCODING',
  'counters':dict.fromkeys(LIMITS,0),'reservation_failed':False,'rejected':None,
  'phases':[{'phase':p,'status':'COMPLETE','elapsed_ns':1000000} for p in PHASES[route]],
  'native_contexts':[{'kind':kind,'status':'COMPLETE','complete':True,'result_sha256':'1'*64} for kind in CONTEXTS[route]],
  'worker':{'state':'NOT_STARTED','started_ns':None,'ended_ns':None,'elapsed_ns':0},
  'post_worker_rechecks':[{'phase':p,'status':'NOT_STARTED','elapsed_ns':0} for p in ['SOURCE_AFTER','AUTHENTICATE_AFTER']],
  'native_limits_unchanged':True,'reasons':[],'driver_state':'EXITED','driver_exit':0,'child_state':'EXITED','child_exit':0,
  'observer_state':'LIVE','observer_exit':None,'publishable_positives':0,'continuation_authorized':False,
  'acceptance_eligible':False,'execution_reuse':False}
 value['counters']['process_operations']=2
 if route=='FINAL':
  value['worker']={'state':'COMPLETE','started_ns':10000000,'ended_ns':15000000,'elapsed_ns':5000000}
  for p in value['phases']:
   if p['phase'] in ['SOURCE_AFTER','AUTHENTICATE_AFTER','FINAL_BOUNDARY']:p['elapsed_ns']=10000000
  for p in value['post_worker_rechecks']:p.update(status='COMPLETE',elapsed_ns=10000000)
 return seal_record(value)

def denial(route='PREIMPORT', phase_name='BOOTSTRAP', interrupted=False):
 value=example(route);index=PHASES[route].index(phase_name)
 value.update(status='INTERRUPTED' if interrupted else 'DENIED',complete=False,
    counter_state='LOWER_BOUND' if interrupted else 'EXACT',reasons=['INTERRUPTION'] if interrupted else ['HOST_IO_ERROR'])
 for i,p in enumerate(value['phases']):
  p['status']='COMPLETE' if i<index else value['status'] if i==index else 'NOT_STARTED'
  if i>index:p['elapsed_ns']=0
 state={p['phase']:p['status'] for p in value['phases']}
 if state['SOURCE_BEFORE']=='NOT_STARTED':value['initial']=None
 if state['SOURCE_AFTER']=='NOT_STARTED':value['terminal']=None
 if state['OWNED_IMPORT']=='NOT_STARTED':value['owned_store']=None
 if state['FINAL_BOUNDARY']=='NOT_STARTED':
  value['worker']={'state':'NOT_STARTED','started_ns':None,'ended_ns':None,'elapsed_ns':0}
  for p in value['post_worker_rechecks']:p.update(status='NOT_STARTED',elapsed_ns=0)
 if state['NATIVE'] in ('NOT_STARTED','DENIED','INTERRUPTED'):
  value.update(driver_state='NOT_STARTED',driver_exit=None,child_state='NOT_STARTED',child_exit=None)
  for n in value['native_contexts']:n.update(status='NOT_REACHED',complete=False,result_sha256=None)
 return seal_record(value)

def conform(value):return validate_record(seal_record(value))

@pytest.mark.parametrize('route,acquisition',[('PREIMPORT','EXISTING_CHECKOUT'),('FINAL','BARE_CLONE'),('FINAL','MATERIALIZED_CHECKOUT')])
def test_hypothetical_route_positive_definition_only(route,acquisition):
 v=example(route,acquisition);out=validate_record(v)
 assert out=={'definition_conforms':True,'observations_authenticated':False,'runtime_or_native_pass':False}
 assert validate_bytes(canonical(v))==out

@pytest.mark.parametrize('route',list(PHASES))
@pytest.mark.parametrize('phase_index',range(9))
@pytest.mark.parametrize('interrupted',[False,True])
def test_every_status_ordered_prefix_hypothetical(route,phase_index,interrupted):
 v=denial(route,PHASES[route][phase_index],interrupted)
 assert conform(v)['observations_authenticated'] is False

@pytest.mark.parametrize('kind',['reverse','duplicate','missing','not_started_duration','complete_after_failure','wrong_failure_kind','no_failure'])
def test_hostile_non_success_phase_projection(kind):
 v=denial('PREIMPORT','OWNED_IMPORT')
 if kind=='reverse':v['phases'].reverse()
 elif kind=='duplicate':v['phases'][0]['phase']=v['phases'][1]['phase']
 elif kind=='missing':v['phases'].pop()
 elif kind=='not_started_duration':v['phases'][-1]['elapsed_ns']=1
 elif kind=='complete_after_failure':v['phases'][-1]['status']='COMPLETE'
 elif kind=='wrong_failure_kind':v['phases'][3]['status']='INTERRUPTED'
 elif kind=='no_failure':v['phases'][3]['status']='NOT_STARTED'
 with pytest.raises(ERRORS):conform(v)

@pytest.mark.parametrize('status',['PREPARATION_COMPLETE','DENIED','INTERRUPTED'])
def test_preimport_reached_bare_kind_rejected_every_status(status):
 v=example() if status=='PREPARATION_COMPLETE' else denial('PREIMPORT','FINAL_BOUNDARY',status=='INTERRUPTED')
 for field in ['initial','terminal']:v[field]['source_kind']='BARE_OWNED'
 with pytest.raises(ERRORS):conform(v)

@pytest.mark.parametrize('case',['wrong_final_kind','wrong_final_identity','preimport_shared_store','early_initial','early_terminal',
 'missing_initial','missing_terminal','missing_import','unreached_import','changed_success_pin','no_checkout_success','no_checkout_snapshot'])
def test_route_snapshot_acquisition_counterexamples(case):
 v=example('FINAL') if case.startswith('wrong_final') or case.startswith('no_checkout') else example()
 if case=='wrong_final_kind':v['initial']['source_kind']='CHECKOUT'
 elif case=='wrong_final_identity':v['initial']['store_inode']=999
 elif case=='preimport_shared_store':v['owned_store']={k:v['initial'][k] for k in v['owned_store']}
 elif case=='early_initial':v=denial();v['initial']=example()['initial']
 elif case=='early_terminal':v=denial();v['terminal']=example()['terminal']
 elif case=='missing_initial':v['initial']=None
 elif case=='missing_terminal':v['terminal']=None
 elif case=='missing_import':v['owned_store']=None
 elif case=='unreached_import':v=denial();v['owned_store']=example()['owned_store']
 elif case=='changed_success_pin':v['terminal']['authority_sha256']='0'*64
 elif case=='no_checkout_success':v['acquisition']='NO_CHECKOUT_UNMATERIALIZED'
 elif case=='no_checkout_snapshot':v=denial('FINAL','SOURCE_BEFORE');v['acquisition']='NO_CHECKOUT_UNMATERIALIZED';v['reasons']=['UNSUPPORTED_SOURCE']
 with pytest.raises(ERRORS):conform(v)

def test_no_checkout_acquisition_truthful_denial_only():
 v=denial('FINAL','OWNED_IMPORT');v.update(acquisition='NO_CHECKOUT_UNMATERIALIZED',reasons=['UNSUPPORTED_SOURCE'],owned_store=None)
 assert conform(v)['definition_conforms']

@pytest.mark.parametrize('location',['revision','protected','tree','controller','release','metadata_snapshot_sha256','authority_sha256','invocation'])
@pytest.mark.parametrize('suffix',['\n','\r\n','x'])
def test_exact_scalar_no_trailing_bytes(location,suffix):
 v=example()
 if location=='invocation':v[location]+=suffix
 else:v['initial'][location]+=suffix
 with pytest.raises(ERRORS):conform(v)

@pytest.mark.parametrize('case',['wrong_route','wrong_order','missing_context','not_reached_complete','not_reached_hash','complete_nullhash',
 'complete_false','denied_true','unreachable_complete','later_after_failure'])
def test_native_every_status_conjunction(case):
 v=denial('FINAL','FINAL_BOUNDARY')
 if case=='wrong_route':v['route']='PREIMPORT'
 elif case=='wrong_order':v['native_contexts'].reverse()
 elif case=='missing_context':v['native_contexts'].pop()
 elif case=='not_reached_complete':v['native_contexts'][0]['status']='NOT_REACHED'
 elif case=='not_reached_hash':v['native_contexts'][0].update(status='NOT_REACHED',complete=False)
 elif case=='complete_nullhash':v['native_contexts'][0]['result_sha256']=None
 elif case=='complete_false':v['native_contexts'][0]['complete']=False
 elif case=='denied_true':v['native_contexts'][0]['status']='DENIED'
 elif case=='unreachable_complete':v=denial();v['native_contexts'][0].update(status='COMPLETE',complete=True,result_sha256='1'*64)
 elif case=='later_after_failure':v=denial('FINAL','NATIVE');v['native_contexts'][0].update(status='DENIED',complete=False);v['native_contexts'][1].update(status='COMPLETE',complete=True,result_sha256='1'*64);v['reasons']=['NATIVE_DENIED']
 with pytest.raises(ERRORS):conform(v)

@pytest.mark.parametrize('field',list(LIMITS))
def test_actual_overcap_is_retained_as_hypothetical_denial_not_clamped(field):
 v=denial('PREIMPORT','FINAL_BOUNDARY');v['counters'][field]=LIMITS[field]['limit']+1
 if field=='result_bytes':
  # Exact serialized-size field cannot be fabricated to a numerical overrun;
  # output exhaustion uses rejected preallocation/emergency instead.
  with pytest.raises(ERRORS):validate_record(v)
  return
 v['reasons']=['HOST_LIMIT_EXHAUSTED'];v=seal_record(v)
 if field=='metadata_read_bytes':v['counters']['file_read_bytes']=v['counters'][field]
 if field=='object_copy_bytes':v['counters']['file_write_bytes']=v['counters'][field]
 if field in ['git_operations','signing_operations']:v['counters']['process_operations']=v['counters']['git_operations']+v['counters']['signing_operations']+2
 v=seal_record(v)
 assert validate_record(v)['definition_conforms'] and v['counters'][field]>LIMITS[field]['limit']
 v['reasons']=['HOST_IO_ERROR']
 with pytest.raises(ERRORS):conform(v)

@pytest.mark.parametrize('case',['detail_false_flag','flag_null_detail','missing_limit_reason','fake_limit_reason','empty_rejection',
 'rejection_within_limit','interruption_as_denied','denied_as_interruption','lower_bound_without_reason','unknown_as_zero',
 'unknown_exit_exact','nonzero_without_reason','fake_nonzero_reason','child_failed_driver_zero','observer_selfzero','boolean_counter'])
def test_sticky_failure_reason_exit_counterexamples(case):
 v=denial('PREIMPORT','FINAL_BOUNDARY')
 detail={'field':'physical_paths','requested':65537,'pending':0}
 if case=='detail_false_flag':v['rejected']=detail
 elif case=='flag_null_detail':v['reservation_failed']=True
 elif case=='missing_limit_reason':v.update(reservation_failed=True,rejected=detail)
 elif case=='fake_limit_reason':v['reasons']=['HOST_LIMIT_EXHAUSTED']
 elif case=='empty_rejection':v.update(reservation_failed=True,rejected=dict(detail,requested=0),reasons=['HOST_LIMIT_EXHAUSTED'])
 elif case=='rejection_within_limit':v.update(reservation_failed=True,rejected=dict(detail,requested=1),reasons=['HOST_LIMIT_EXHAUSTED'])
 elif case=='interruption_as_denied':v['reasons']=['INTERRUPTION']
 elif case=='denied_as_interruption':v['status']='INTERRUPTED'
 elif case=='lower_bound_without_reason':v['counter_state']='LOWER_BOUND'
 elif case=='unknown_as_zero':v.update(driver_state='UNKNOWN',driver_exit=0)
 elif case=='unknown_exit_exact':v.update(driver_state='UNKNOWN',driver_exit=None,reasons=['UNKNOWN_CHILD_EXIT'])
 elif case=='nonzero_without_reason':v['driver_exit']=1
 elif case=='fake_nonzero_reason':v['reasons']=['HOST_DRIVER_FAILURE']
 elif case=='child_failed_driver_zero':v.update(child_exit=-9,reasons=['HOST_CHILD_FAILURE'])
 elif case=='observer_selfzero':v['observer_exit']=0
 elif case=='boolean_counter':v['counters']['physical_paths']=True
 with pytest.raises(ERRORS):conform(v)

def test_rejected_reservation_keeps_actual_below_cap_and_unknown_distinct():
 v=denial('PREIMPORT','FINAL_BOUNDARY');v.update(reservation_failed=True,
  rejected={'field':'physical_paths','requested':65537,'pending':0},reasons=['HOST_LIMIT_EXHAUSTED'])
 assert conform(v)['definition_conforms'] and v['counters']['physical_paths']==0
 v=denial('FINAL','FINAL_BOUNDARY',True);v.update(driver_state='UNKNOWN',driver_exit=None,
   reasons=['INTERRUPTION','UNKNOWN_CHILD_EXIT'])
 assert conform(v)['definition_conforms']
 v=denial('FINAL','FINAL_BOUNDARY',True);v.update(driver_exit=1,child_exit=-9,
  reasons=['INTERRUPTION','HOST_DRIVER_FAILURE','HOST_CHILD_FAILURE'])
 assert conform(v)['definition_conforms']

def test_phase_and_overall_observed_deadlines_and_result_whole_bytes():
 v=example();v['phases'][2]['elapsed_ns']=OVERALL_NS['PREIMPORT']+1;v['elapsed_ns']=OVERALL_NS['PREIMPORT']+10
 with pytest.raises(ERRORS):conform(v)
 v=denial('PREIMPORT','FINAL_BOUNDARY');v['phases'][2]['elapsed_ns']=OVERALL_NS['PREIMPORT']+1;v['elapsed_ns']=OVERALL_NS['PREIMPORT']+10;v['reasons']=['HOST_DEADLINE_EXCEEDED']
 assert conform(v)['definition_conforms']
 v=example();v['counters']['result_bytes']=0
 with pytest.raises(ERRORS):validate_record(v)
 sealed=seal_record(v);assert sealed['counters']['result_bytes']==len(canonical(sealed))>0
 v=example();v['elapsed_ns']=1800000000001
 with pytest.raises(ERRORS):conform(v)

def emergency():
 return {'format':'host-preparation-emergency-draft-v4','invocation':'0'*32,'route':'PREIMPORT',
  'status':'INTERRUPTED','reason':'OBSERVER_LOST','complete':False,'counter_state':'LOWER_BOUND','elapsed_ns':1,
  'driver_state':'UNKNOWN','driver_exit':None,'child_state':'UNKNOWN','child_exit':None,'observer_state':'LOST','observer_exit':None,
  'partial_log_sha256':None,'publishable_positives':0,'continuation_authorized':False,'acceptance_eligible':False,'execution_reuse':False}

@pytest.mark.parametrize('case',['valid','denied_interruption','interruption_denial','unknown_zero','false_observer_loss',
 'nonzero_unknown','complete','extra','hash_newline'])
def test_emergency_closed_status_reason_exits(case):
 v=emergency()
 if case=='valid':assert validate_emergency(v)['definition_conforms'];return
 if case=='denied_interruption':v['status']='DENIED'
 elif case=='interruption_denial':v['reason']='AUTH_DENIED'
 elif case=='unknown_zero':v['child_exit']=0
 elif case=='false_observer_loss':v['observer_state']='LIVE'
 elif case=='nonzero_unknown':v['observer_exit']=1
 elif case=='complete':v['complete']=True
 elif case=='extra':v['secret']='not allowed'
 elif case=='hash_newline':v['partial_log_sha256']='0'*64+'\n'
 with pytest.raises(ERRORS):validate_emergency(v)

def test_emergency_observed_nonzero_distinct_from_unknown():
 v=emergency();v.update(status='DENIED',reason='HOST_DRIVER_FAILURE',driver_state='EXITED',driver_exit=1,
  child_state='EXITED',child_exit=-9,observer_state='LIVE')
 assert validate_emergency(v)['definition_conforms']

def trace(route):
 roles={'START_C':'D','NATIVE_OUTPUT':'C','WORKER_START':'C','WORKER_DONE':'C','C_EXIT':'D'}
 return [{'event':name,'role':roles.get(name,'S'),'ledger':'0'*32,'at_ns':i*1000000,'failure':None}
         for i,name in enumerate(trace_template(route))]

@pytest.mark.parametrize('route',list(PHASES))
def test_hypothetical_live_observer_sequence_positive(route):
 assert validate_trace(trace(route),route)=={'sequence_conforms':True,'actual_processes_observed':False,'publication_authorized':False}

@pytest.mark.parametrize('case',['release_lock_early','observer_exit_early','child_publishes','new_ledger','lost_ack',
 'publish_before_worker','eligible_before_exits','miss_cleanup','miss_serialization','failed_event','clock_rollback','extra_event'])
def test_sequence_counterexamples(case):
 e=trace('FINAL')
 def index(name):return next(i for i,v in enumerate(e) if v['event']==name)
 if case=='release_lock_early':e.insert(index('WORKER_START'),dict(e[1],event='UNLOCK'))
 elif case=='observer_exit_early':e.insert(index('D_EXIT'),dict(e[1],event='STOP_S'))
 elif case=='child_publishes':e[index('PUBLISH_ATTEMPT')]['role']='C'
 elif case=='new_ledger':e[index('RECHECK_AUTH')]['ledger']='1'*32
 elif case=='lost_ack':e.pop(index('PUBLISH_ACK'))
 elif case=='publish_before_worker':
  before=index('WORKER_START');after=index('PUBLISH_ATTEMPT');e[before],e[after]=e[after],e[before]
 elif case=='eligible_before_exits':e[index('C_EXIT')]['event']='COMMIT_ELIGIBLE'
 elif case=='miss_cleanup':e.pop(index('CLEANUP_DONE'))
 elif case=='miss_serialization':e.pop(index('SIZE_RECORD'))
 elif case=='failed_event':e[index('FINAL_CHECK')]['failure']='HOST_IO_ERROR'
 elif case=='clock_rollback':e[index('WORKER_DONE')]['at_ns']=0
 elif case=='extra_event':e.append(copy.deepcopy(e[-1]))
 with pytest.raises(ERRORS):validate_trace(e,'FINAL')

def test_reentry_clock_and_effective_worker_deadline_no_reset():
 assert phase_clock(10,OVERALL_NS['FINAL'],OVERALL_NS['FINAL'])
 assert not phase_clock(10,OVERALL_NS['FINAL']+1,OVERALL_NS['FINAL']+1)
 e=trace('FINAL');worker=next(i for i,v in enumerate(e) if v['event']=='WORKER_START')
 for item in e[worker+1:]:item['at_ns']+=WORKER_NS+1
 assert e[-1]['at_ns']<OVERALL_NS['FINAL']
 with pytest.raises(InvalidDefinition):validate_trace(e,'FINAL')

@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'['*33+b'0'+b']'*33,b'{"a":NaN}',b' '*1048577,b'\xff'],ids=['duplicate_key','depth33','nonfinite','byte_overrun','invalid_utf8'])
def test_bounded_oracle_input_preallocation_and_unique_json(raw):
 with pytest.raises(ERRORS):decode_bounded(raw)

def test_native22_and_host30_unchanged_exact_external_bindings():
 old=ROOT/'fixtures'/'r1'
 assert (ROOT/'NATIVE_LIMITS.json').read_bytes()==(old/'NATIVE_LIMITS.json').read_bytes()
 old_limits=json.loads((old/'HOST_LIMITS.json').read_text())['limits']
 assert {k:v['limit'] for k,v in LIMITS.items()}=={k:v['limit'] for k,v in old_limits.items()}
 native=json.loads((ROOT/'NATIVE_LIMITS.json').read_text())['unchanged_definition']
 assert len(native['incremental_work_limits'])==22 and len(LIMITS)==30
 assert native['deadlines_milliseconds']=={'per_read':10000,'context':120000}
 assert json.loads((ROOT/'FUTURE_CHECKS.json').read_text())['checks']==json.loads((old/'FUTURE_CHECKS.json').read_text())['checks']

def test_both_closed_schemas_reproduce_from_frozen_generator():
 from build_schema import generate
 schemas=generate()
 for name,schema in zip(['HOST_RESULT.schema.json','HOST_EMERGENCY.schema.json'],schemas):
  jsonschema.Draft202012Validator.check_schema(schema)
  assert json.loads((ROOT/name).read_text())==schema

@pytest.mark.parametrize('field',['root','pin','counter','phase','native','owned_store'])
def test_closed_nested_objects_reject_extra_fields(field):
 v=example()
 target={'root':v,'pin':v['initial'],'counter':v['counters'],'phase':v['phases'][0],
    'native':v['native_contexts'][0],'owned_store':v['owned_store']}[field]
 target['unknown']=1
 with pytest.raises(ERRORS):conform(v)
