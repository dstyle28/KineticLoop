"""FINAL failed identity observations: hypothetical conformance, no actual source audit."""
import copy
import hashlib
import pytest
from test_definition import example,denial,conform,emergency,ERRORS
from definition_oracle import InvalidDefinition,canonical,seal_record,validate_record,validate_emergency

LAYOUTS=['BARE_CLONE','MATERIALIZED_CHECKOUT']
FIELDS=['store_device','store_inode','objects_device','objects_inode']
STAGES=['SOURCE_BEFORE','SOURCE_AFTER','FINAL_BOUNDARY']
STATUSES=['DENIED','INTERRUPTED']

def failed_observation(layout,stage,status,field='objects_inode'):
 value=denial('FINAL',stage,status=='INTERRUPTED')
 value['acquisition']=layout
 if layout=='MATERIALIZED_CHECKOUT':
  for name in ['initial','terminal']:
   if value[name] is not None:value[name]['source_kind']='CHECKOUT'
 value['reasons']=['SOURCE_CHANGED']+(['INTERRUPTION'] if status=='INTERRUPTED' else [])
 name='initial' if stage=='SOURCE_BEFORE' else 'terminal'
 value[name][field]+=17
 if stage=='FINAL_BOUNDARY':
  value['post_worker_rechecks'][0]['status']=status
  value['post_worker_rechecks'][1].update(status='NOT_STARTED',elapsed_ns=0)
 return value,name

@pytest.mark.parametrize('layout',LAYOUTS)
@pytest.mark.parametrize('field',FIELDS)
@pytest.mark.parametrize('stage',STAGES)
@pytest.mark.parametrize('status',STATUSES)
def test_actual_failed_identity_scalars_not_replaced_by_bound_values(layout,field,stage,status):
 value,name=failed_observation(layout,stage,status,field)
 before=copy.deepcopy(value);bound=value['owned_store'][field];observed=value[name][field]
 assert observed!=bound
 sealed=seal_record(value)
 result=validate_record(sealed)
 assert result=={'definition_conforms':True,'observations_authenticated':False,'runtime_or_native_pass':False}
 assert value==before and sealed[name][field]==observed and sealed['owned_store'][field]==bound
 assert sealed['publishable_positives']==0 and not sealed['continuation_authorized']
 if status=='INTERRUPTED':assert sealed['counter_state']=='LOWER_BOUND' and 'INTERRUPTION' in sealed['reasons']
 if stage=='SOURCE_BEFORE':
  assert all(n['status']=='NOT_REACHED' for n in sealed['native_contexts'])
  assert sealed['driver_state']==sealed['child_state']=='NOT_STARTED'
 if stage=='FINAL_BOUNDARY':assert all(p['status']=='COMPLETE' for p in sealed['phases'][:-1])

@pytest.mark.parametrize('layout',LAYOUTS)
@pytest.mark.parametrize('stage',STAGES)
@pytest.mark.parametrize('status',STATUSES)
def test_matching_failed_snapshots_still_conform(layout,stage,status):
 value,name=failed_observation(layout,stage,status)
 for field in FIELDS:value[name][field]=value['owned_store'][field]
 assert conform(value)['definition_conforms']

@pytest.mark.parametrize('layout',LAYOUTS)
@pytest.mark.parametrize('field',FIELDS)
@pytest.mark.parametrize('status',STATUSES)
def test_first_snapshot_can_report_import_discrepancy(layout,field,status):
 value,name=failed_observation(layout,'SOURCE_BEFORE',status,field)
 value['reasons']=['IMPORT_DENIED']+(['INTERRUPTION'] if status=='INTERRUPTED' else [])
 assert conform(value)['definition_conforms'] and value[name][field]!=value['owned_store'][field]

@pytest.mark.parametrize('layout',LAYOUTS)
@pytest.mark.parametrize('field',FIELDS)
@pytest.mark.parametrize('which',['initial','terminal','both'])
def test_forged_success_cannot_use_observed_store_mismatch(layout,field,which):
 value=example('FINAL',layout)
 for name in (['initial','terminal'] if which=='both' else [which]):value[name][field]+=17
 with pytest.raises(InvalidDefinition,match='FINAL_SUCCESS_ACQUIRED_STORE_IDENTITY'):conform(value)

@pytest.mark.parametrize('layout',LAYOUTS)
def test_matching_success_keeps_all_original_guards(layout):
 value=example('FINAL',layout);out=validate_record(value)
 assert out['definition_conforms'] and not out['observations_authenticated']
 assert value['initial']==value['terminal']
 assert all(value[name][field]==value['owned_store'][field] for name in ['initial','terminal'] for field in FIELDS)
 assert value['initial']['release']==value['initial']['revision']

@pytest.mark.parametrize('layout',LAYOUTS)
@pytest.mark.parametrize('stage',STAGES)
@pytest.mark.parametrize('status',STATUSES)
def test_changed_store_requires_corresponding_failure_reason(layout,stage,status):
 value,_=failed_observation(layout,stage,status)
 value['reasons']=['HOST_IO_ERROR']+(['INTERRUPTION'] if status=='INTERRUPTED' else [])
 with pytest.raises(InvalidDefinition,match='MISMATCH_FAILURE_PATH'):conform(value)

@pytest.mark.parametrize('layout',LAYOUTS)
@pytest.mark.parametrize('status',STATUSES)
@pytest.mark.parametrize('bad_path',['initial_continued','terminal_auth_only','postworker_auth_only','unreached_snapshot'])
def test_failed_identity_cannot_claim_unrelated_or_unreached_path(layout,status,bad_path):
 if bad_path=='initial_continued':
  value=denial('FINAL','SOURCE_AFTER',status=='INTERRUPTED');name='initial'
 elif bad_path=='terminal_auth_only':
  value=denial('FINAL','AUTHENTICATE_AFTER',status=='INTERRUPTED');name='terminal'
 elif bad_path=='postworker_auth_only':
  value=denial('FINAL','FINAL_BOUNDARY',status=='INTERRUPTED');name='terminal'
  value['post_worker_rechecks'][1]['status']=status
 else:
  value=denial('FINAL','OWNED_IMPORT',status=='INTERRUPTED');name='initial'
  value['initial']=copy.deepcopy(example('FINAL')['initial'])
 value['acquisition']=layout
 if layout=='MATERIALIZED_CHECKOUT':
  for n in ['initial','terminal']:
   if value[n] is not None:value[n]['source_kind']='CHECKOUT'
 value[name]['objects_inode']+=17
 value['reasons']=['SOURCE_CHANGED']+(['INTERRUPTION'] if status=='INTERRUPTED' else [])
 with pytest.raises(ERRORS):conform(value)

@pytest.mark.parametrize('layout',LAYOUTS)
def test_known_identity_and_lower_bound_counters_remain_distinct(layout):
 value,name=failed_observation(layout,'FINAL_BOUNDARY','INTERRUPTED','store_device')
 value['counters'].update(metadata_read_bytes=123,file_read_bytes=0)
 sealed=seal_record(value);assert validate_record(sealed)['definition_conforms']
 assert sealed[name]['store_device']==value[name]['store_device']
 assert sealed['owned_store']['store_device']!=sealed[name]['store_device']
 assert sealed['counters']['metadata_read_bytes']==123 and sealed['counters']['file_read_bytes']==0

@pytest.mark.parametrize('stage',['OWNED_IMPORT','POST_WORKER_SOURCE_AFTER'])
def test_explicit_partial_routing_binds_exact_known_failure_facts(stage):
 bound={'store_device':1,'store_inode':20,'objects_device':1,'objects_inode':21}
 observed=copy.deepcopy(bound);observed['objects_inode']=38
 partial={'stage':stage,'original_bound':bound,'actual_observed':observed,'missing_fields':['metadata_snapshot_sha256'],
  'sample_elapsed_ns':123,'driver_exit':None,'child_exit':None}
 raw=canonical(partial);assert len(raw)<=2097152
 e=emergency();e['partial_log_sha256']=hashlib.sha256(raw).hexdigest()
 if stage=='OWNED_IMPORT':
  e.update(status='DENIED',reason='IMPORT_DENIED',driver_state='NOT_STARTED',driver_exit=None,
    child_state='NOT_STARTED',child_exit=None,observer_state='LIVE',observer_exit=None)
 assert validate_emergency(e)['definition_conforms']
 assert e['partial_log_sha256']==hashlib.sha256(canonical(partial)).hexdigest()
 assert observed['objects_inode']==38 and bound['objects_inode']==21
 assert not e['complete'] and e['counter_state']=='LOWER_BOUND' and e['publishable_positives']==0
 with pytest.raises(ERRORS):validate_record(e)
