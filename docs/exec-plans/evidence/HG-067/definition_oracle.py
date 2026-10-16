"""Bounded R4 definition conformance only. Synthetic input grants no authority."""
import copy
import json
import re
from pathlib import Path
import jsonschema
from build_schema import PHASES, CONTEXTS
ROOT=Path(__file__).resolve().parent
LIMITS=json.loads((ROOT/'HOST_LIMITS.json').read_text())['limits']
FULL_SCHEMA=json.loads((ROOT/'HOST_RESULT.schema.json').read_text())
EMERGENCY_SCHEMA=json.loads((ROOT/'HOST_EMERGENCY.schema.json').read_text())
FULL_VALIDATOR=jsonschema.Draft202012Validator(FULL_SCHEMA)
EMERGENCY_VALIDATOR=jsonschema.Draft202012Validator(EMERGENCY_SCHEMA)
CLOCKS=json.loads((ROOT/'HOST_LIMITS.json').read_text())['deadlines_ms']
OVERALL_NS={route:CLOCKS[route.lower()+'_overall']*1000000 for route in ['PREIMPORT','FINAL']}
WORKER_NS=CLOCKS['worker_operation']*1000000
TAIL_NS=CLOCKS['worker_terminal_reservation']*1000000
GRACE_NS=CLOCKS['termination_observation_grace']*1000000

class InvalidDefinition(ValueError):pass
def require(condition, reason):
 if not condition:raise InvalidDefinition(reason)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def bounded_structure(value):
 pending=[(value,0)];visited=0
 while pending:
  item,depth=pending.pop();visited+=1
  require(visited<=65536 and depth<=32,'STRUCTURE_BOUND')
  if type(item) is dict:
   require(visited+len(pending)+2*len(item)<=65536,'STRUCTURE_RESERVATION')
   pending.extend((v,depth+1) for pair in item.items() for v in pair)
  elif type(item) is list:
   require(visited+len(pending)+len(item)<=65536,'STRUCTURE_RESERVATION')
   pending.extend((v,depth+1) for v in item)
  elif type(item) is str:require(len(item)<=16384,'STRING_BOUND')
  else:require(item is None or type(item) in (int,bool),'NON_JSON_VALUE')
def decode_bounded(raw,cap=1048576):
 require(type(raw) is bytes and len(raw)<=cap,'INPUT_BYTES_BOUND')
 text=raw.decode('utf-8','strict');depth=0;tokens=0;in_string=False;escaped=False
 # Conservative token/structural bound before JSON allocates containers/strings.
 for c in text:
  if in_string:
   if escaped:escaped=False
   elif c=='\\':escaped=True
   elif c=='"':in_string=False
   continue
  if c=='"':in_string=True;tokens+=1
  elif c in '[{':depth+=1;tokens+=1
  elif c in ']}':depth-=1
  elif c in ',:':tokens+=1
  require(0<=depth<=32 and tokens<=65536,'LEXICAL_BOUND')
 def pairs(items):
  result={}
  for k,v in items:
   require(k not in result,'DUPLICATE_KEY');result[k]=v
  return result
 value=json.loads(text,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(InvalidDefinition('NONFINITE')))
 bounded_structure(value)
 return value
def seal_record(value):
 """Exact complete encoding length fixed point; no assertion of actual I/O."""
 value=copy.deepcopy(value)
 for _ in range(16):
  size=len(canonical(value))
  if value['counters']['result_bytes']==size:return value
  value['counters']['result_bytes']=size
 raise InvalidDefinition('SERIALIZATION_FIXED_POINT')
def validate_record(value):
 bounded_structure(value);FULL_VALIDATOR.validate(value)
 encoded=canonical(value)
 require(len(encoded)<=1048576,'RECORD_BYTES_BOUND')
 require(value['counters']['result_bytes']==len(encoded),'RESULT_BYTES_EXACT')
 route=value['route'];status=value['status'];success=status=='PREPARATION_COMPLETE';reasons=set(value['reasons'])
 phase={p['phase']:p for p in value['phases']};states=[p['status'] for p in value['phases']]
 if success:require(states==['COMPLETE']*9,'SUCCESS_PHASES')
 else:
  failure='INTERRUPTED' if status=='INTERRUPTED' else 'DENIED'
  require(states.count(failure)==1,'ONE_TERMINAL_PHASE')
  index=states.index(failure)
  require(states==['COMPLETE']*index+[failure]+['NOT_STARTED']*(8-index),'ORDERED_FAILURE_PREFIX')
 for p in value['phases']:
  require(p['elapsed_ns']<=value['elapsed_ns'],'PHASE_EXCEEDS_OBSERVED_TOTAL')
  if p['status']=='NOT_STARTED':require(p['elapsed_ns']==0,'UNREACHED_DURATION')
 worker=value['worker'];rechecks=value['post_worker_rechecks'];ws=worker['state']
 if ws=='NOT_STARTED':
  require(worker['started_ns'] is None and worker['ended_ns'] is None and worker['elapsed_ns']==0,'UNREACHED_WORKER_CLOCK')
  require(all(p['status']=='NOT_STARTED' and p['elapsed_ns']==0 for p in rechecks),'UNREACHED_WORKER_RECHECKS')
 else:
  require(route=='FINAL' and type(worker['started_ns']) is int,'WORKER_ROUTE_START')
  require(0<=worker['started_ns']<=value['elapsed_ns'],'WORKER_START_ORDER')
  require(OVERALL_NS[route]-worker['started_ns']>=WORKER_NS+TAIL_NS,'WORKER_ADMISSION_RESERVATION')
  if worker['ended_ns'] is not None:
   require(worker['started_ns']<=worker['ended_ns']<=value['elapsed_ns'] and worker['elapsed_ns']==worker['ended_ns']-worker['started_ns'],'WORKER_ELAPSED_EXACT')
  else:
   require(ws=='INTERRUPTED' and status=='INTERRUPTED' and value['counter_state']=='LOWER_BOUND','WORKER_UNKNOWN_END')
   require(worker['elapsed_ns']<=value['elapsed_ns']-worker['started_ns'],'WORKER_ELAPSED_LOWER_BOUND')
  require(phase['FINAL_BOUNDARY']['status']!='NOT_STARTED' and phase['NATIVE']['status']=='COMPLETE','WORKER_AFTER_REQUIRED_NATIVE')
  require(phase['FINAL_BOUNDARY']['elapsed_ns']>=worker['elapsed_ns'],'WORKER_IN_FINAL_BOUNDARY')
  if ws=='COMPLETE':
   rst=[p['status'] for p in rechecks]
   if 'DENIED' in rst or 'INTERRUPTED' in rst:
    failed='INTERRUPTED' if 'INTERRUPTED' in rst else 'DENIED';i=rst.index(failed)
    require(rst==['COMPLETE']*i+[failed]+['NOT_STARTED']*(1-i),'ORDERED_RECHECK_FAILURE')
    require(status==failed and phase['FINAL_BOUNDARY']['status']==failed,'RECHECK_FAILURE_HOST')
   else:require(rst in (['COMPLETE','COMPLETE'],['COMPLETE','NOT_STARTED'],['NOT_STARTED','NOT_STARTED']),'ORDERED_RECHECK_PREFIX')
   for p in rechecks:
    if p['status']=='NOT_STARTED':require(p['elapsed_ns']==0,'UNREACHED_RECHECK_DURATION')
    else:require(p['elapsed_ns']==phase[p['phase']]['elapsed_ns'] and p['elapsed_ns']>=worker['elapsed_ns'],'RECHECK_CLOCK_CONTINUITY')
  else:
   require(not success and phase['FINAL_BOUNDARY']['status'] in ('DENIED','INTERRUPTED'),'FAILED_WORKER_HOST')
   require(all(p['status']=='NOT_STARTED' and p['elapsed_ns']==0 for p in rechecks),'FAILED_WORKER_NO_RECHECK')
   if ws=='INTERRUPTED':require(status=='INTERRUPTED','WORKER_INTERRUPTION_HOST')
 if route=='PREIMPORT':require(ws=='NOT_STARTED','PREIMPORT_NO_WORKER')
 if success and route=='FINAL':require(ws=='COMPLETE' and all(p['status']=='COMPLETE' for p in rechecks),'FINAL_WORKER_RECHECK_COMPLETENESS')
 deadline=value['elapsed_ns']>OVERALL_NS[route] or worker['elapsed_ns']>WORKER_NS
 if deadline:require(not success and 'HOST_DEADLINE_EXCEEDED' in reasons,'DEADLINE_REQUIRES_DENIAL')
 if 'HOST_DEADLINE_EXCEEDED' in reasons:require(deadline,'DEADLINE_OBSERVATION_REQUIRED')
 if 'HOST_CLOCK_RESERVATION_DENIED' in reasons:
  require(route=='FINAL' and ws=='NOT_STARTED' and phase['FINAL_BOUNDARY']['status']=='DENIED' and
   OVERALL_NS[route]-value['elapsed_ns']<WORKER_NS+TAIL_NS,'CLOCK_REJECTION_OBSERVATION')
 over=any(value['counters'][k]>v['limit'] for k,v in LIMITS.items())
 if over or value['reservation_failed']:require(not success and 'HOST_LIMIT_EXHAUSTED' in reasons,'LIMIT_IMPLICATION')
 if 'HOST_LIMIT_EXHAUSTED' in reasons:require(over or value['reservation_failed'],'LIMIT_OBSERVATION_REQUIRED')
 if value['reservation_failed']:
  rejection=value['rejected'];field=rejection['field']
  require(rejection['requested']+rejection['pending']>0,'EMPTY_REJECTION')
  require(value['counters'][field]+rejection['requested']+rejection['pending']>LIMITS[field]['limit'],'REJECTION_MUST_EXCEED')
 if value['counter_state']=='LOWER_BOUND':require(not success and ('ACCOUNTING_INCOMPLETE' in reasons or status=='INTERRUPTED'),'LOWER_BOUND_REASON')
 if 'ACCOUNTING_INCOMPLETE' in reasons:require(value['counter_state']=='LOWER_BOUND','ACCOUNTING_STATE')
 if 'INTERRUPTION' in reasons:require(status=='INTERRUPTED','INTERRUPTION_STATUS')
 require('OBSERVER_LOST' not in reasons,'LOST_OBSERVER_REQUIRES_EMERGENCY')
 if value['child_state']!='NOT_STARTED':require(value['driver_state']!='NOT_STARTED','CHILD_REQUIRES_STARTED_DRIVER')
 if value['counter_state']=='EXACT':
  counters=value['counters']
  require(counters['metadata_read_bytes']<=counters['file_read_bytes'],'EXACT_METADATA_SUBSET')
  require(counters['object_copy_bytes']<=counters['file_write_bytes'],'EXACT_OBJECT_COPY_SUBSET')
  broker_starts=sum(value[who+'_state']!='NOT_STARTED' for who in ['driver','child'])
  require(counters['git_operations']+counters['signing_operations']+broker_starts<=counters['process_operations'],'EXACT_PROCESS_STARTS')
 for who in ['driver','child']:
  state=value[who+'_state'];exitcode=value[who+'_exit']
  if state=='UNKNOWN':require(status=='INTERRUPTED' and 'UNKNOWN_CHILD_EXIT' in reasons,'UNKNOWN_EXIT_INTERRUPTION')
  if state=='EXITED' and exitcode!=0:require(not success and 'HOST_'+who.upper()+'_FAILURE' in reasons,'OBSERVED_NONZERO_REASON')
  if 'HOST_'+who.upper()+'_FAILURE' in reasons:require(state=='EXITED' and exitcode!=0,'NONZERO_OBSERVATION_REQUIRED')
 if 'UNKNOWN_CHILD_EXIT' in reasons:require('UNKNOWN' in [value['driver_state'],value['child_state']],'UNKNOWN_OBSERVATION_REQUIRED')
 if value['child_state']=='EXITED' and value['child_exit']!=0:
  require(value['driver_state']!='EXITED' or value['driver_exit']!=0,'DRIVER_CANNOT_CLEAR_CHILD_FAILURE')
 native=value['native_contexts'];nstates=[n['status'] for n in native];np=phase['NATIVE']['status']
 seen_failure=False;seen_unreached=False
 for n in native:
  if n['status']=='NOT_REACHED':seen_unreached=True
  else:require(not seen_failure and not seen_unreached,'NATIVE_ORDER')
  if n['status'] in ('DENIED','INTERRUPTED'):seen_failure=True
 if np=='NOT_STARTED':
  require(all(s=='NOT_REACHED' for s in nstates),'NATIVE_UNREACHABLE')
  require(value['driver_state']==value['child_state']=='NOT_STARTED','EXECUTION_BEFORE_NATIVE')
 elif np=='COMPLETE':require(all(s=='COMPLETE' for s in nstates),'NATIVE_COMPLETE_CONJUNCTION')
 elif np=='DENIED':require('INTERRUPTED' not in nstates,'NATIVE_INTERRUPTION_STATUS')
 if any(s=='DENIED' for s in nstates):require(not success and 'NATIVE_DENIED' in reasons,'NATIVE_DENIAL_REASON')
 if 'NATIVE_DENIED' in reasons:require('DENIED' in nstates,'NATIVE_DENIAL_OBSERVATION')
 if 'NATIVE_INCOMPLETE' in reasons:require(any(s!='COMPLETE' for s in nstates),'NATIVE_INCOMPLETE_OBSERVATION')
 if any(s=='INTERRUPTED' for s in nstates):require(status=='INTERRUPTED','NATIVE_INTERRUPTION_HOST')
 if any(s!='NOT_REACHED' for s in nstates):require(value['driver_state']!='NOT_STARTED' and value['child_state']!='NOT_STARTED','NATIVE_WITHOUT_EXECUTION')
 if success:require(all(s=='COMPLETE' for s in nstates),'NATIVE_SUCCESS')
 for name,pname in [('initial','SOURCE_BEFORE'),('terminal','SOURCE_AFTER')]:
  p=phase[pname]['status'];pins=value[name]
  if p=='NOT_STARTED':require(pins is None,'UNREACHED_SNAPSHOT')
  if p=='COMPLETE':require(pins is not None,'COMPLETED_SNAPSHOT_REQUIRED')
 if value['terminal'] is not None:require(value['initial'] is not None,'TERMINAL_WITHOUT_INITIAL')
 imported=phase['OWNED_IMPORT']['status']
 if imported=='NOT_STARTED':require(value['owned_store'] is None,'UNREACHED_OWNED_STORE')
 if imported=='COMPLETE':require(value['owned_store'] is not None,'OWNED_IMPORT_BINDING')
 if route=='FINAL':
  if value['acquisition']=='NO_CHECKOUT_UNMATERIALIZED':
   require(not success and 'UNSUPPORTED_SOURCE' in reasons,'UNMATERIALIZED_DENIAL')
   require(phase['SOURCE_BEFORE']['status']=='NOT_STARTED','UNMATERIALIZED_NO_SNAPSHOT')
  else:
   expected='BARE_OWNED' if value['acquisition']=='BARE_CLONE' else 'CHECKOUT'
   for name in ['initial','terminal']:
    if value[name] is not None:
     require(value[name]['source_kind']==expected,'FINAL_LAYOUT_KIND')
     require(value['owned_store'] is not None,'FINAL_ACQUIRED_BINDING_REQUIRED')
     matches=all(value[name][k]==v for k,v in value['owned_store'].items())
     if not matches:
      require(not success,'FINAL_SUCCESS_ACQUIRED_STORE_IDENTITY')
      if name=='initial':
       require(phase['SOURCE_BEFORE']['status']==status and
        bool(reasons.intersection({'SOURCE_CHANGED','IMPORT_DENIED'})),'FINAL_INITIAL_MISMATCH_FAILURE_PATH')
      else:
       preworker=phase['SOURCE_AFTER']['status']==status
       postworker=(phase['FINAL_BOUNDARY']['status']==status and worker['state']=='COMPLETE' and
        rechecks[0]['status']==status and rechecks[1]['status']=='NOT_STARTED')
       require('SOURCE_CHANGED' in reasons and (preworker or postworker),'FINAL_TERMINAL_MISMATCH_FAILURE_PATH')
 if success:
  require(value['initial']==value['terminal'],'EXACT_SNAPSHOT_EQUALITY')
  require(all(value[name]['release']==value[name]['revision'] for name in ['initial','terminal']),'SUCCESS_RELEASE_REVISION')
  if route=='PREIMPORT':
   require((value['initial']['store_device'],value['initial']['store_inode'])!=(value['owned_store']['store_device'],value['owned_store']['store_inode']),'SUCCESS_DISTINCT_OWNED_ROOT')
   require((value['initial']['objects_device'],value['initial']['objects_inode'])!=(value['owned_store']['objects_device'],value['owned_store']['objects_inode']),'SUCCESS_DISTINCT_OBJECT_STORE')
 return {'definition_conforms':True,'observations_authenticated':False,'runtime_or_native_pass':False}

def validate_bytes(raw):return validate_record(decode_bounded(raw))
def validate_emergency(value):
 bounded_structure(value);EMERGENCY_VALIDATOR.validate(value)
 require(len(canonical(value))<=4096,'EMERGENCY_BYTES_BOUND')
 interrupted=value['status']=='INTERRUPTED'
 require(interrupted==(value['reason'] in ['INTERRUPTION','UNKNOWN_CHILD_EXIT','OBSERVER_LOST']),'EMERGENCY_STATUS_REASON')
 for who in ['driver','child','observer']:
  state=value[who+'_state'];exitcode=value[who+'_exit']
  require((state=='EXITED')==(type(exitcode) is int),'EMERGENCY_EXIT_STATE')
  if state!='EXITED':require(exitcode is None,'EMERGENCY_UNKNOWN_NOT_ZERO')
  if state in ('UNKNOWN','LOST'):require(interrupted,'EMERGENCY_UNKNOWN_INTERRUPTED')
 if value['reason']=='UNKNOWN_CHILD_EXIT':require('UNKNOWN' in [value['driver_state'],value['child_state']],'EMERGENCY_UNKNOWN_EVIDENCE')
 if value['reason']=='OBSERVER_LOST':require(value['observer_state']=='LOST','EMERGENCY_OBSERVER_EVIDENCE')
 for who in ['driver','child']:
  if value['reason']=='HOST_'+who.upper()+'_FAILURE':
   require(value[who+'_state']=='EXITED' and value[who+'_exit']!=0,'EMERGENCY_NONZERO_OBSERVATION')
 if value['child_state']=='EXITED' and value['child_exit']!=0:
  require(value['driver_state']!='EXITED' or value['driver_exit']!=0,'EMERGENCY_DRIVER_CANNOT_CLEAR_CHILD')
 if value['child_state']!='NOT_STARTED':require(value['driver_state']!='NOT_STARTED','EMERGENCY_CHILD_REQUIRES_DRIVER')
 return {'definition_conforms':True,'observations_authenticated':False,'runtime_or_native_pass':False}

def phase_clock(first_ns,last_ns,overall_ns,route='FINAL'):
 require(type(first_ns) is type(last_ns) is type(overall_ns) is int and 0<=first_ns<=last_ns<=overall_ns,'CLOCK_ORDER')
 return overall_ns<=OVERALL_NS[route]

def trace_template(route):
 prefix=['START_S','LOCK_ACQUIRED','AUTH_BEFORE']
 acquisition=['SOURCE_BEFORE','IMPORT_COMPLETE'] if route=='PREIMPORT' else ['IMPORT_COMPLETE','SOURCE_BEFORE']
 body=['ASSET_BINDING','START_D','START_C','NATIVE_OUTPUT','SOURCE_AFTER','AUTH_AFTER']
 tail=(['WORKER_START','WORKER_DONE','RECHECK_SOURCE','RECHECK_AUTH'] if route=='FINAL' else [])
 tail+=['C_EXIT','D_EXIT','CLEANUP_DONE','SIZE_RECORD','FINAL_CHECK']
 if route=='FINAL':tail+=['PUBLISH_ATTEMPT','PUBLISH_ACK','SIZE_RECORD','FINAL_CHECK']
 return prefix+acquisition+body+tail+['COMMIT_ELIGIBLE','UNLOCK','STOP_S']

def validate_trace(events,route):
 bounded_structure(events)
 require(route in PHASES and type(events) is list and len(events)<=64,'TRACE_BOUND')
 require([e['event'] for e in events]==trace_template(route),'EVENT_SEQUENCE')
 ledger=events[0]['ledger'];start=events[0]['at_ns'];last=start
 locked=False;live=False
 for e in events:
  require(set(e)=={'event','role','ledger','at_ns','failure'},'TRACE_CLOSED')
  require(e['ledger']==ledger and type(ledger) is str and re.fullmatch('[0-9a-f]{32}',ledger) is not None,'SAME_LEDGER')
  require(type(e['at_ns']) is int and e['at_ns']>=last,'MONOTONIC_TRACE');last=e['at_ns']
  require(e['failure'] is None,'FAILED_EVENT_NO_ELIGIBILITY')
  required_role={'START_C':'D','NATIVE_OUTPUT':'C','WORKER_START':'C','WORKER_DONE':'C','C_EXIT':'D'}.get(e['event'],'S')
  require(e['role']==required_role,'PROCESS_OWNER')
  if e['event']=='START_S':live=True
  elif e['event']=='LOCK_ACQUIRED':locked=True
  elif e['event']=='UNLOCK':locked=False
  elif e['event']=='STOP_S':live=False
  else:require(live and locked,'LIVE_OWNER_LOCK')
 require(last-start<=OVERALL_NS[route],'OVERALL_TRACE_DEADLINE')
 # Reentered intervals include worker/wait; only the same absolute invocation deadline applies.
 for initial,reentry in [('SOURCE_AFTER','RECHECK_SOURCE'),('AUTH_AFTER','RECHECK_AUTH')]:
  times=[e['at_ns']-start for e in events if e['event'] in (initial,reentry)]
  require(phase_clock(times[0],times[-1],last-start,route),'REENTERED_PHASE_DEADLINE')
 boundary=next(e['at_ns']-start for e in events if e['event'] in ('WORKER_START','C_EXIT'))
 commit=next(e['at_ns']-start for e in events if e['event']=='COMMIT_ELIGIBLE')
 require(phase_clock(boundary,commit,last-start,route),'FINAL_BOUNDARY_DEADLINE')
 if route=='FINAL':
  worker_start=next(e['at_ns']-start for e in events if e['event']=='WORKER_START')
  worker_end=next(e['at_ns']-start for e in events if e['event']=='WORKER_DONE')
  require(OVERALL_NS[route]-worker_start>=WORKER_NS+TAIL_NS,'TRACE_WORKER_RESERVATION')
  require(worker_end-worker_start<=WORKER_NS,'TRACE_WORKER_DEADLINE')
 return {'sequence_conforms':True,'actual_processes_observed':False,'publication_authorized':False}

def validate_worker_schedule(value):
 """Clock-only complete unchanged source schedule, never an execution receipt."""
 bounded_structure(value)
 require(type(value) is dict and set(value)=={'captures','controls_ns','daemon','terminations','other_ns'},'SCHEDULE_CLOSED')
 derivation=json.loads((ROOT/'CLOCK_DERIVATION.json').read_text())
 limits=derivation['capture_limits_seconds']
 require(type(value['captures']) is list and len(value['captures'])==len(limits),'COMPLETE_CAPTURE_PLAN')
 total=0
 for entry,cap in zip(value['captures'],limits):
  require(type(entry) is dict and set(entry)=={'name','elapsed_ns'} and entry['name']==cap['name'],'SOURCE_CAPTURE_ORDER')
  require(type(entry['elapsed_ns']) is int and 0<=entry['elapsed_ns']<=cap['limit_seconds']*1000000000,'UNCHANGED_CAPTURE_LIMIT')
  total+=entry['elapsed_ns']
 require(type(value['controls_ns']) is list and len(value['controls_ns'])<=64,'CONTROL_COUNT')
 for elapsed in value['controls_ns']:
  require(type(elapsed) is int and 0<=elapsed<=120000000000,'CONTROL_LIMIT');total+=elapsed
 require(type(value['daemon']) is list and len(value['daemon'])<=60,'DAEMON_COUNT')
 for entry in value['daemon']:
  require(type(entry) is dict and set(entry)=={'probe_ns','sleep_ns'},'DAEMON_CLOSED')
  require(type(entry['probe_ns']) is int and 0<=entry['probe_ns']<=10000000000,'DAEMON_PROBE_LIMIT')
  require(type(entry['sleep_ns']) is int and 0<=entry['sleep_ns']<=1000000000,'DAEMON_SLEEP_LIMIT')
  total+=entry['probe_ns']+entry['sleep_ns']
 require(type(value['terminations']) is list and len(value['terminations'])<=16,'TERMINATION_COUNT')
 for entry in value['terminations']:
  require(type(entry) is dict and set(entry)=={'term_ns','kill_observe_ns'},'TERMINATION_CLOSED')
  require(type(entry['term_ns']) is int and 0<=entry['term_ns']<=15000000000,'EXISTING_TERM_GRACE')
  require(type(entry['kill_observe_ns']) is int and 0<=entry['kill_observe_ns']<=5000000000,'KILL_OBSERVATION_GRACE')
  total+=entry['term_ns']+entry['kill_observe_ns']
 require(type(value['other_ns']) is int and value['other_ns']>=0,'OTHER_ELAPSED')
 total+=value['other_ns'];require(total<=WORKER_NS,'WHOLE_WORKER_DEADLINE')
 return {'schedule_conforms':True,'whole_worker_elapsed_ns':total,'actual_execution_observed':False,'runtime_fit_established':False}
