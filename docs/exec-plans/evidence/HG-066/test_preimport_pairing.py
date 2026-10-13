'Direct closed-schema contradictions, distinct exits and every native cap.'
import copy
import pytest,jsonschema
import sequence_model as m
P=m.fixture_premise();BASE=P['independent_facts']['PREIMPORT']['output']
def validate(v):jsonschema.validate(v,m.PRESCHEMA)
def denied(reason,complete=True,host=1):
    x=copy.deepcopy(BASE);x.update(status='PREIMPORT_DENIED',complete=complete,ready_for_exact_import=False,preserved_duplicate_paths=0,preserved_duplicate_bytes=0,host_exit_code=host,denial_reasons=reason);return x

@pytest.mark.parametrize('reason',['UNPERFORMED','INTERRUPTED','INCOMPLETE_CONTEXT'])
@pytest.mark.parametrize('host',[1,-9,143])
def test_complete_denial_cannot_hide_unperformed_or_interrupted_reason_with_integer_host(reason,host):
    with pytest.raises(jsonschema.ValidationError):validate(denied([reason],host=host))

@pytest.mark.parametrize('reasons',[['UNPERFORMED'],['UNPERFORMED','INTERRUPTED'],['UNPERFORMED','LIMIT_EXHAUSTED'],['UNPERFORMED','DEADLINE_EXCEEDED'],['UNPERFORMED','OBJECT_MISMATCH']])
def test_reverse_unperformed_reason_status_pairing_and_mixed_reasons(reasons):
    x=denied(reasons,False)
    with pytest.raises(jsonschema.ValidationError):validate(x)
    x['status']='PREIMPORT_UNPERFORMED'
    with pytest.raises(jsonschema.ValidationError):validate(x)

def test_both_directions_of_exact_unperformed_record_and_no_credential_reuse():
    u=m.fixture_preimport_output(m.fixture_preimport_bindings(P['roots']),BASE['inventory'],m.FixtureBudget(clock=lambda:0),P['disposition'],unperformed=True);validate(u)
    for key,value in [('status','PREIMPORT_DENIED'),('denial_reasons',['OBJECT_MISMATCH']),('complete',True),('host_exit_code',1),('driver_exit_code',143),('original_guard_status','ALL_NATIVE_OBSERVED')]:
        x=copy.deepcopy(u);x[key]=value
        with pytest.raises(jsonschema.ValidationError):validate(x)
    assert u['host_exit_code'] is u['driver_exit_code'] is None and u['inventory']['digest'] is None
    assert u['preserved_duplicate_paths']==u['preserved_duplicate_bytes']==0
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(u,m.FINAL_SCHEMA)

@pytest.mark.parametrize('reason',['INTERRUPTED','INCOMPLETE_CONTEXT'])
@pytest.mark.parametrize('host',[None,1,-9,143])
def test_incomplete_work_retains_actual_host_and_distinct_driver_exit(reason,host):
    x=denied([reason],False,host);x.update(original_guard_status='PARTIAL',driver_exit_code=143);validate(x)
    assert x['host_exit_code']==host and x['driver_exit_code']==143
    assert not x['complete'] and not x['ready_for_exact_import'] and x['preserved_duplicate_paths']==x['preserved_duplicate_bytes']==0
    x['complete']=True
    with pytest.raises(jsonschema.ValidationError):validate(x)

@pytest.mark.parametrize('counter',list(m.LIMITS))
def test_every_counter_actual_overrun_and_interrupted_zero_accounting(counter):
    x=denied(['INTERRUPTED','LIMIT_EXHAUSTED'],False,1);x.update(original_guard_status='PARTIAL',driver_exit_code=143);x['consumed'][counter]=m.LIMITS[counter]+1;validate(x)
    assert x['consumed'][counter]==m.LIMITS[counter]+1 and x['preserved_duplicate_paths']==x['preserved_duplicate_bytes']==0
    for change in ['complete','positive-accounting','missing-limit']:
        y=copy.deepcopy(x)
        if change=='complete':y['complete']=True
        if change=='positive-accounting':y['preserved_duplicate_paths']=1
        if change=='missing-limit':y['denial_reasons']=['INTERRUPTED']
        with pytest.raises(jsonschema.ValidationError):validate(y)

def test_interrupted_deadline_overrun_retains_both_reasons_actual_clock_and_driver():
    x=denied(['INTERRUPTED','DEADLINE_EXCEEDED'],False,-9);x.update(original_guard_status='PARTIAL',driver_exit_code=143,elapsed_ns=120000000001);validate(x)
    assert x['elapsed_ns']==120000000001
    x['denial_reasons']=['INTERRUPTED']
    with pytest.raises(jsonschema.ValidationError):validate(x)
