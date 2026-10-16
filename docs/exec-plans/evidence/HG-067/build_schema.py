"""Closed R4 definition schemas; no installed code or native execution."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
PHASES = {
 'PREIMPORT': ['BOOTSTRAP','AUTHENTICATE_BEFORE','SOURCE_BEFORE','OWNED_IMPORT','ASSET_BINDING','NATIVE','SOURCE_AFTER','AUTHENTICATE_AFTER','FINAL_BOUNDARY'],
 'FINAL': ['BOOTSTRAP','AUTHENTICATE_BEFORE','OWNED_IMPORT','SOURCE_BEFORE','ASSET_BINDING','NATIVE','SOURCE_AFTER','AUTHENTICATE_AFTER','FINAL_BOUNDARY']}
CONTEXTS = {'PREIMPORT': ['ORIGINAL_PREIMPORT'], 'FINAL': ['ORIGINAL_FINAL','STRICT_LIVE_FINAL']}
REASONS = ['HOST_LIMIT_EXHAUSTED','HOST_DEADLINE_EXCEEDED','HOST_READ_TIMEOUT','AUTH_DENIED','OWNERSHIP_DENIED',
 'LOCK_DENIED','SOURCE_CHANGED','SOURCE_UNCLEAN','LITERAL_MISMATCH','MODE_MISMATCH','UNSUPPORTED_SOURCE','IMPORT_DENIED',
 'ASSET_MISMATCH','NATIVE_DENIED','NATIVE_INCOMPLETE','OUTPUT_EXHAUSTED','MEMORY_ENFORCEMENT_UNAVAILABLE','INTERRUPTION',
 'UNKNOWN_CHILD_EXIT','ACCOUNTING_INCOMPLETE','HOST_IO_ERROR','INTERNAL_CONTRACT_ERROR','HOST_DRIVER_FAILURE',
 'HOST_CHILD_FAILURE','OBSERVER_LOST','CLEANUP_FAILED','PUBLICATION_UNCERTAIN','HOST_CLOCK_RESERVATION_DENIED']
def obj(props, **extra):
 return dict(type='object', properties=props, required=list(props), additionalProperties=False, **extra)
def integer(maximum=None):
 d={'type':'integer','minimum':0}
 if maximum is not None:d['maximum']=maximum
 return d
def enum(*values):return {'enum':list(values)}
def nullable(x):return {'anyOf':[x,{'type':'null'}]}
def scalar(n):return {'type':'string','pattern':'^[0-9a-f]{'+str(n)+'}$','minLength':n,'maxLength':n}
def array(items, maximum, minimum=0):return {'type':'array','items':items,'minItems':minimum,'maxItems':maximum}
def generate():
 limits=json.loads((ROOT/'HOST_LIMITS.json').read_text())['limits']
 pins=obj({'revision':scalar(40),'protected':scalar(40),'tree':scalar(40),'controller':scalar(64),'release':scalar(40),
  'repository_id':integer(),'task':{'const':'harness-governance-v0.1/HG-058'},'store_device':integer(),'store_inode':integer(),
  'objects_device':integer(),'objects_inode':integer(),'metadata_snapshot_sha256':scalar(64),'authority_sha256':scalar(64),
  'source_kind':enum('CHECKOUT','BARE_OWNED')})
 owned=obj({k:integer() for k in ['store_device','store_inode','objects_device','objects_inode']})
 native=obj({'kind':enum('ORIGINAL_PREIMPORT','ORIGINAL_FINAL','STRICT_LIVE_FINAL'),
  'status':enum('NOT_REACHED','COMPLETE','DENIED','INTERRUPTED'),'complete':{'type':'boolean'},'result_sha256':nullable(scalar(64))},
  oneOf=[{'properties':{'status':{'const':'NOT_REACHED'},'complete':{'const':False},'result_sha256':{'type':'null'}}},
   {'properties':{'status':{'const':'COMPLETE'},'complete':{'const':True},'result_sha256':scalar(64)}},
   {'properties':{'status':enum('DENIED','INTERRUPTED'),'complete':{'const':False}}}])
 worker=obj({'state':enum('NOT_STARTED','COMPLETE','DENIED','INTERRUPTED'),'started_ns':nullable(integer()),'ended_ns':nullable(integer()),'elapsed_ns':integer()})
 rechecks={'type':'array','minItems':2,'maxItems':2,'prefixItems':[
  obj({'phase':{'const':p},'status':enum('NOT_STARTED','COMPLETE','DENIED','INTERRUPTED'),'elapsed_ns':integer()}) for p in ['SOURCE_AFTER','AUTHENTICATE_AFTER']]}
 props={'format':{'const':'host-preparation-result-draft-v4'},'invocation':scalar(32),'route':enum('PREIMPORT','FINAL'),
  'status':enum('PREPARATION_COMPLETE','DENIED','INTERRUPTED'),
  'limits_sha256':{'const':hashlib.sha256((ROOT/'HOST_LIMITS.json').read_bytes()).hexdigest()},
  'acquisition':enum('EXISTING_CHECKOUT','BARE_CLONE','MATERIALIZED_CHECKOUT','NO_CHECKOUT_UNMATERIALIZED'),
  'initial':nullable(pins),'terminal':nullable(pins),'owned_store':nullable(owned),
  'complete':{'type':'boolean'},'counter_state':enum('EXACT','LOWER_BOUND'),
  'elapsed_ns':integer(),'elapsed_observation':{'const':'LAST_SAMPLE_BEFORE_FINAL_ENCODING'},
  'counters':obj({k:integer() for k in limits}),
  'reservation_failed':{'type':'boolean'},'rejected':nullable(obj({'field':enum(*limits),'requested':integer(),'pending':integer()})),
  'phases':{'type':'array','minItems':9,'maxItems':9}, 'native_contexts':{'type':'array','maxItems':2},
  'worker':worker,'post_worker_rechecks':rechecks,
  'native_limits_unchanged':{'const':True},'reasons':dict(array(enum(*REASONS),len(REASONS)),uniqueItems=True),
  'driver_state':enum('NOT_STARTED','EXITED','UNKNOWN'),'child_state':enum('NOT_STARTED','EXITED','UNKNOWN'),
  'driver_exit':nullable({'type':'integer'}),'child_exit':nullable({'type':'integer'}),
  'observer_state':{'const':'LIVE'},'observer_exit':{'type':'null'},
  'publishable_positives':{'const':0},'continuation_authorized':{'const':False},'acceptance_eligible':{'const':False},'execution_reuse':{'const':False}}
 props['owned_store']['description']='Original observed acquisition-time binding, never overwritten to match later observations; not a reusable authority receipt.'
 props['initial']['description']='Actual reached SOURCE_BEFORE complete snapshot, including known failed observations; FINAL mismatch requires the R4 failed initial-source path.'
 props['terminal']['description']='Latest actual complete SOURCE_AFTER snapshot including post-worker recheck; FINAL changed observations require consistent R4 source/recheck failure, never substitution of expected values.'
 branches=[]
 for route in PHASES:
  phase_items=[obj({'phase':{'const':p},'status':enum('NOT_STARTED','COMPLETE','DENIED','INTERRUPTED'),'elapsed_ns':integer()}) for p in PHASES[route]]
  routeprops={'phases':{'prefixItems':phase_items},
   'native_contexts':{'minItems':len(CONTEXTS[route]),'maxItems':len(CONTEXTS[route]),
       'prefixItems':[dict(native, allOf=[{'properties':{'kind':{'const':k}}}]) for k in CONTEXTS[route]]}}
  if route=='PREIMPORT':
   routeprops.update(acquisition={'const':'EXISTING_CHECKOUT'},initial=nullable(dict(pins,allOf=[{'properties':{'source_kind':{'const':'CHECKOUT'}}}])),
      terminal=nullable(dict(pins,allOf=[{'properties':{'source_kind':{'const':'CHECKOUT'}}}])))
  else:routeprops['acquisition']=enum('BARE_CLONE','MATERIALIZED_CHECKOUT','NO_CHECKOUT_UNMATERIALIZED')
  branches.append({'if':{'properties':{'route':{'const':route}}},'then':{'properties':routeprops}})
 branches += [
  {'if':{'properties':{'status':{'const':'PREPARATION_COMPLETE'}}},
   'then':{'properties':{'complete':{'const':True},'counter_state':{'const':'EXACT'},'initial':pins,'terminal':pins,'owned_store':owned,
    'reservation_failed':{'const':False},'rejected':{'type':'null'},'reasons':{'maxItems':0},
    'counters':obj({k:integer(v['limit']) for k,v in limits.items()}),
    'driver_state':{'const':'EXITED'},'child_state':{'const':'EXITED'},'driver_exit':{'const':0},'child_exit':{'const':0}}},
   'else':{'properties':{'complete':{'const':False},'reasons':{'minItems':1}}}},
  {'if':{'properties':{'reservation_failed':{'const':True}}},
   'then':{'properties':{'rejected':props['rejected']['anyOf'][0],'reasons':{'contains':{'const':'HOST_LIMIT_EXHAUSTED'}}}},
   'else':{'properties':{'rejected':{'type':'null'}}}},
  {'if':{'properties':{'status':{'const':'INTERRUPTED'}}},
   'then':{'properties':{'counter_state':{'const':'LOWER_BOUND'},'reasons':{'contains':{'const':'INTERRUPTION'}}}},
   'else':{'properties':{'reasons':{'not':{'contains':{'const':'INTERRUPTION'}}}}}}
 ]
 for field in ['driver','child']:
  branches.append({'if':{'properties':{field+'_state':{'const':'EXITED'}}},
     'then':{'properties':{field+'_exit':{'type':'integer'}}},'else':{'properties':{field+'_exit':{'type':'null'}}}})
 schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:kineticloop:draft:host-result-v4',
    **obj(props), 'allOf':branches,
    'x-required-conformance-oracle':'definition_oracle.py validate_record AND closed schema, both required; SOURCE_OBSERVATION_CONTRACT.md defines conditional bound/observed equality and failed paths; neither authenticates observations',
    'x-observation-boundary':'only installed trusted live execution can establish actual counters, elapsed, pins, native hashes and output/clock enforcement'}
 emergency=obj({'format':{'const':'host-preparation-emergency-draft-v4'},'invocation':scalar(32),'route':enum('PREIMPORT','FINAL'),
    'status':enum('DENIED','INTERRUPTED'),'reason':enum(*REASONS),'complete':{'const':False},'counter_state':{'const':'LOWER_BOUND'},
    'elapsed_ns':integer(),'driver_state':enum('NOT_STARTED','EXITED','UNKNOWN'),'child_state':enum('NOT_STARTED','EXITED','UNKNOWN'),
    'driver_exit':nullable({'type':'integer'}),'child_exit':nullable({'type':'integer'}),
    'observer_state':enum('LIVE','EXITED','LOST'),'observer_exit':nullable({'type':'integer'}),
    'partial_log_sha256':nullable(scalar(64)), 'publishable_positives':{'const':0},'continuation_authorized':{'const':False},
    'acceptance_eligible':{'const':False},'execution_reuse':{'const':False}})
 emergency.update({'$schema':schema['$schema'],'$id':'urn:kineticloop:draft:host-emergency-v4','x-maximum-utf8-bytes':4096,
  'x-required-conformance-oracle':'definition_oracle.py validate_emergency AND closed schema'})
 return schema,emergency
if __name__=='__main__':
 for name,value in zip(['HOST_RESULT.schema.json','HOST_EMERGENCY.schema.json'],generate()):
  (ROOT/name).write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
 print('generated two closed R4 schemas')
