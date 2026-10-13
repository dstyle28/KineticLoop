'Reverse exhaustion implications without fabricated charges; closed reason matrix.'
import copy,itertools
import pytest,jsonschema
import sequence_model as m
P=m.fixture_premise();BASE=P['independent_facts']['PREIMPORT']['output'];REASONS=m.PRESCHEMA['properties']['denial_reasons']['items']['enum'];EXHAUST={'LIMIT_EXHAUSTED','DEADLINE_EXCEEDED'};INCOMPLETE={'INTERRUPTED','INCOMPLETE_CONTEXT'}
def output(b,**kw):return m.fixture_preimport_output(m.fixture_preimport_bindings(P['roots']),BASE['inventory'],b,P['disposition'],**kw)
def validate(x):jsonschema.validate(x,m.PRESCHEMA)
def rejects(x):
    with pytest.raises(jsonschema.ValidationError):validate(x)

def test_exact_security_genuine_rejected_reservation_then_only_complete_flip():
    b=m.FixtureBudget(clock=lambda:0);b.observe('json_nodes',65535)
    with pytest.raises(m.Denial,match='RESERVATION_LIMIT'):b.reserve('json_nodes',1,pending=1)
    x=output(b);validate(x);assert x['consumed']['json_nodes']==65535 and x['elapsed_ns']==0
    assert x['status']=='PREIMPORT_DENIED' and x['denial_reasons']==['LIMIT_EXHAUSTED'] and not x['complete'] and x['preserved_duplicate_paths']==x['preserved_duplicate_bytes']==0
    y=copy.deepcopy(x);y['complete']=True;assert y['consumed']==x['consumed'];rejects(y)

@pytest.mark.parametrize('field',list(m.LIMITS))
def test_each_rejected_capacity_reservation_retains_below_cap_consumed_value(field):
    b=m.FixtureBudget(clock=lambda:0);b.observe(field,m.LIMITS[field]-1);before=dict(b.used)
    with pytest.raises(m.Denial):b.reserve(field,1,pending=1)
    assert b.used==before
    for kw in [{},{'native_denial':True},{'unperformed':True}]:
        x=output(b,**kw);validate(x);assert x['consumed']==before and x['elapsed_ns']==0 and x['status']=='PREIMPORT_DENIED' and not x['complete'] and not x['ready_for_exact_import']
        assert x['preserved_duplicate_paths']==x['preserved_duplicate_bytes']==0
        y=copy.deepcopy(x);y['complete']=True;rejects(y)

@pytest.mark.parametrize('reasons',[['LIMIT_EXHAUSTED'],['DEADLINE_EXCEEDED'],['LIMIT_EXHAUSTED','DEADLINE_EXCEEDED']])
def test_exhaustion_reason_requires_incomplete_denied_zero_even_without_overcap_observations(reasons):
    x=copy.deepcopy(BASE);x.update(status='PREIMPORT_DENIED',complete=False,ready_for_exact_import=False,preserved_duplicate_paths=0,preserved_duplicate_bytes=0,host_exit_code=1,denial_reasons=reasons);validate(x)
    assert all(x['consumed'][k]<=v for k,v in m.LIMITS.items()) and x['elapsed_ns']<=120000000000
    for key,value in [('complete',True),('status','PREIMPORT_PRESERVATION_OBSERVED'),('status','PREIMPORT_UNPERFORMED'),('preserved_duplicate_paths',1),('preserved_duplicate_bytes',1),('ready_for_exact_import',True)]:
        y=copy.deepcopy(x);y[key]=value;rejects(y)

@pytest.mark.parametrize('starting',['positive','ordinary-denial','unperformed'])
@pytest.mark.parametrize('exhaustion',['reservation','deadline','both'])
def test_every_status_finalization_discards_positive_residue_and_retains_actual_observations(starting,exhaustion):
    now=[0];b=m.FixtureBudget(clock=lambda:now[0]);kwargs={} if starting=='positive' else {'native_denial':True} if starting=='ordinary-denial' else {'unperformed':True}
    baseline=output(b,**kwargs);validate(baseline);assert baseline['status']=={'positive':'PREIMPORT_PRESERVATION_OBSERVED','ordinary-denial':'PREIMPORT_DENIED','unperformed':'PREIMPORT_UNPERFORMED'}[starting]
    if exhaustion in ['reservation','both']:
        b.observe('json_nodes',65535)
        with pytest.raises(m.Denial):b.reserve('json_nodes',1,pending=1)
    if exhaustion in ['deadline','both']:now[0]=120000000001
    x=output(b,**kwargs);validate(x);assert x['status']=='PREIMPORT_DENIED' and not x['complete'] and not x['ready_for_exact_import']
    assert x['preserved_duplicate_paths']==x['preserved_duplicate_bytes']==0 and x['consumed']['json_nodes']==(65535 if exhaustion!='deadline' else 0)
    assert x['elapsed_ns']==(120000000001 if exhaustion!='reservation' else 0)
    assert 'UNPERFORMED' not in x['denial_reasons']
    assert ('LIMIT_EXHAUSTED' in x['denial_reasons'])==(exhaustion!='deadline') and ('DEADLINE_EXCEEDED' in x['denial_reasons'])==(exhaustion!='reservation')
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(x,m.FINAL_SCHEMA)

def reason_record(reasons,status,complete):
    if status=='PREIMPORT_UNPERFORMED':
        x=output(m.FixtureBudget(clock=lambda:0),unperformed=True);x.update(denial_reasons=reasons,complete=complete);return x
    x=copy.deepcopy(BASE);x.update(status=status,complete=complete,denial_reasons=reasons)
    if status=='PREIMPORT_DENIED':x.update(ready_for_exact_import=False,preserved_duplicate_paths=0,preserved_duplicate_bytes=0,host_exit_code=1)
    if set(reasons)&INCOMPLETE:x['original_guard_status']='PARTIAL'
    return x

@pytest.mark.parametrize('reason',REASONS)
@pytest.mark.parametrize('status',['PREIMPORT_PRESERVATION_OBSERVED','PREIMPORT_DENIED','PREIMPORT_UNPERFORMED'])
@pytest.mark.parametrize('complete',[False,True])
def test_complete_existing_single_reason_status_completion_implication_matrix(reason,status,complete):
    x=reason_record([reason],status,complete)
    expected=(reason=='UNPERFORMED' and status=='PREIMPORT_UNPERFORMED' and not complete) or (reason!='UNPERFORMED' and status=='PREIMPORT_DENIED' and (not complete or reason not in EXHAUST|INCOMPLETE))
    if expected:validate(x)
    else:rejects(x)

@pytest.mark.parametrize('reasons',list(itertools.combinations(REASONS,2)))
def test_existing_reason_pairs_preserve_exact_unperformed_and_incomplete_exhaustion_semantics(reasons):
    x=reason_record(list(reasons),'PREIMPORT_DENIED',False)
    if 'UNPERFORMED' in reasons:rejects(x)
    else:
        validate(x);x['complete']=True
        if set(reasons)&(EXHAUST|INCOMPLETE):rejects(x)
        else:validate(x)

def test_legitimate_complete_ordinary_denials_and_distinct_host_driver_exits_remain_valid():
    for reason in ['NATIVE_GUARD_DENIED','BINDING_CHANGED','CALLER_DENIED']:
        x=reason_record([reason],'PREIMPORT_DENIED',True);x['driver_exit_code']=143;validate(x);assert x['host_exit_code']==1 and x['driver_exit_code']==143
        assert x['complete'] and not x['ready_for_exact_import'] and x['preserved_duplicate_paths']==x['preserved_duplicate_bytes']==0
