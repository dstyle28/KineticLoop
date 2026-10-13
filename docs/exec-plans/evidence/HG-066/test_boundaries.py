'Boundaries, strict negative oracle and actual synthetic child executions.'
import copy,json,os,subprocess,sys,time
from pathlib import Path
import pytest,jsonschema
import sequence_model as m
D=Path(__file__).resolve().parent;P=m.fixture_premise();E=m.fixture_events(P)
def phase(n):return next(e['facts'] for e in E if e['phase']==n)
def output(budget,**kw):
    return m.fixture_preimport_output(m.fixture_preimport_bindings(P['roots']),phase('PREIMPORT')['output']['inventory'],budget,P['disposition'],**kw)

@pytest.mark.parametrize('field',list(m.LIMITS),ids=list(m.LIMITS))
def test_each_complete_status_obeys_every_inclusive_counter_boundary_and_actual_overrun(field):
    b=m.FixtureBudget(clock=lambda:0);b.observe(field,m.LIMITS[field]);o=output(b)
    assert o['complete'] and o['ready_for_exact_import']
    d=output(b,native_denial=True);assert d['complete'] and not d['ready_for_exact_import']
    b.observe(field,1);d=output(b,native_denial=True)
    assert not d['complete'] and d['preserved_duplicate_paths']==d['preserved_duplicate_bytes']==0
    assert d['consumed'][field]==m.LIMITS[field]+1 and 'LIMIT_EXHAUSTED' in d['denial_reasons']
    forged=copy.deepcopy(o);forged['consumed'][field]+=1
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(forged,m.PRESCHEMA)
    forged=copy.deepcopy(d);forged.update(complete=True)
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(forged,m.PRESCHEMA)

def test_deadline_inclusive_then_one_over_both_ordinary_denial_and_positive_zero_residue():
    now=[0];b=m.FixtureBudget(clock=lambda:now[0]);now[0]=120000000000
    assert output(b)['complete'] and output(b,native_denial=True)['complete']
    now[0]+=1
    for extra in [{},{'native_denial':True}]:
        d=output(b,**extra);assert not d['complete'] and not d['ready_for_exact_import']
        assert d['elapsed_ns']==120000000001 and d['preserved_duplicate_paths']==0
        assert 'DEADLINE_EXCEEDED' in d['denial_reasons']

def test_deadline_expires_only_at_final_second_publication_observation():
    ticks=iter([0,0,0,120000000001]);b=m.FixtureBudget(clock=lambda:next(ticks));d=output(b)
    assert d['status']=='PREIMPORT_DENIED' and not d['complete'] and d['preserved_duplicate_bytes']==0

def test_simultaneous_limit_and_deadline_preserve_both_exceeded_observations():
    now=[0];b=m.FixtureBudget(clock=lambda:now[0]);b.observe('groups',129);now[0]=120000000001
    d=output(b);assert set(d['denial_reasons'])=={'LIMIT_EXHAUSTED','DEADLINE_EXCEEDED'}
    assert d['consumed']['groups']==129 and d['elapsed_ns']==120000000001

def test_unknown_or_interrupted_execution_never_supplies_host_exit0():
    d=output(m.FixtureBudget(clock=lambda:0),completed=False)
    assert d['host_exit_code'] is None and not d['complete'] and d['preserved_duplicate_paths']==0
    d['driver_exit_code']=143;d['denial_reasons'].append('INTERRUPTED')
    jsonschema.validate(d,m.PRESCHEMA)
    assert d['host_exit_code'] is None and d['driver_exit_code']==143

def test_unperformed_is_exact_and_cannot_hide_exhaustion():
    b=m.FixtureBudget(clock=lambda:0);u=output(b,unperformed=True)
    assert u['status']=='PREIMPORT_UNPERFORMED' and u['denial_reasons']==['UNPERFORMED']
    b.observe('groups',129);d=output(b,unperformed=True)
    assert d['status']=='PREIMPORT_DENIED' and 'LIMIT_EXHAUSTED' in d['denial_reasons']
    for key,value in [('host_exit_code',0),('complete',True),('live_guard_status','ALL_NATIVE_OBSERVED'),('denial_reasons',['UNPERFORMED','NATIVE_GUARD_DENIED'])]:
        x=copy.deepcopy(u);x[key]=value
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(x,m.PRESCHEMA)

@pytest.mark.parametrize('field', ['files','stored_bytes','maps','edges','preserved_duplicate_paths','host_exit_code','elapsed_ns'],ids=['files-bool','bytes-bool','maps-bool','edges-bool','disposition-bool','host-exit-bool','clock-bool'])
def test_closed_preimport_schema_rejects_boolean_integer_substitution(field):
    x=copy.deepcopy(phase('PREIMPORT')['output'])
    if field in x['inventory']:x['inventory'][field]=True
    else:x[field]=False
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(x,m.PRESCHEMA)

PUBLIC_MUTATIONS={
 'zero-child-exit':lambda x:x.update(exit_code=0),
 'unknown-child-exit':lambda x:x.update(exit_code=None),
 'boolean-child-exit':lambda x:x.update(exit_code=True),
 'interrupted':lambda x:x.update(interrupted=True),
 'timeout':lambda x:x.update(timeout=True),
 'incomplete':lambda x:x.update(complete=False),
 'wrong-tested':lambda x:x.update(tested='0'*40),
 'wrong-command':lambda x:x.update(command=x['command']+' --custody'),
 'missing-inventory':lambda x:x.update(stdout='{}'),
 'unexpected-stderr':lambda x:x.update(stderr='native source failure'),
 'malformed-output':lambda x:x.update(stdout='not JSON'),
 'extra-duplicate-key':lambda x:x.update(stdout=x['stdout'][:-1]+',\x22files\x22:9}'),
 'nonfinite':lambda x:x.update(stdout=x['stdout'].replace('\x22files\x22: 9','\x22files\x22: NaN')),
 'unexpected-native-error':lambda x:x.update(stdout=x['stdout'].replace('\x22errors\x22: [','\x22errors\x22: [\x22bad-codec\x22,')),
 'missing-native-error':lambda x:x.update(stdout=x['stdout'].replace(json.loads(x['stdout'])['errors'][0]+'\x22, ','')),
 'bool-inventory-count':lambda x:x.update(stdout=x['stdout'].replace('\x22files\x22: 9','\x22files\x22: true')),
 'missing-native-trace-digest':lambda x:x.update(stdout=json.dumps({k:v for k,v in json.loads(x['stdout']).items() if k!='inventory_sha256'})),
 'native-work-incomplete':lambda x:x.update(stdout=x['stdout'].replace('\x22native_complete\x22: true','\x22native_complete\x22: false')),
}
@pytest.mark.parametrize('case',list(PUBLIC_MUTATIONS),ids=list(PUBLIC_MUTATIONS))
def test_nonzero_public_child_is_not_enough_for_success(case):
    x=copy.deepcopy(P['public_child']);PUBLIC_MUTATIONS[case](x)
    with pytest.raises((m.Denial,jsonschema.ValidationError)):m.fixture_public_assertion(x,m.fixture_inventory_oracle(P['inventory_objects'],P['bodies'],P['retained_groups'],P['object_bytes']),P['public_roots'])

@pytest.mark.parametrize('mutation',['missing-other-path','new-alias','extra-owner','unreferenced-payload','extra-native-error','mode-change','byte-type','raw-body-corrupt'],ids=['full-inventory-not-six-only','alias','third-owner','unreferenced','native-error','symlink','bool-byte','raw-corruption'])
def test_independent_full_inventory_oracle_rejects_unexpected_or_incomplete_objects(mutation):
    o=copy.deepcopy(P['inventory_objects']);b=copy.deepcopy(P['bodies'])
    if mutation=='missing-other-path':
        o=[x for x in o if x['kind']!='PLAIN'];inv=m.fixture_inventory_oracle(o,b,P['retained_groups'],{x['path']:P['object_bytes'][x['path']] for x in o if x['path'] in P['object_bytes']})
        with pytest.raises(m.Denial):m.fixture_public_assertion(P['public_child'],inv,P['public_roots'])
        return
    if mutation=='new-alias':o.append(copy.deepcopy(o[0]));o.sort(key=lambda x:x['path'])
    if mutation=='extra-owner':o[-1]['path']=o[-1]['path'].replace('HG-202','HG-203')
    if mutation=='unreferenced-payload':o.append({**copy.deepcopy(o[0]),'path':'docs/exec-plans/evidence/HG-201/other.gz','kind':'PAYLOAD'});o.sort(key=lambda x:x['path'])
    if mutation=='extra-native-error':o[0]['native_errors']=['codec-EOF']
    if mutation=='mode-change':o[0]['mode']='120000'
    if mutation=='byte-type':o[0]['bytes']=True
    if mutation=='raw-body-corrupt':b[next(iter(b))]='00'
    with pytest.raises(m.Denial):m.fixture_inventory_oracle(o,b,P['retained_groups'],{x['path']:P['object_bytes'][x['path']] for x in o if x['path'] in P['object_bytes']})

def test_coherent_owner_neutral_fixture_has_same_complete_route_and_different_hashes():
    p=m.fixture_premise(selected='HG-301',foreign='HG-302',body_salt=' DIFFERENT')
    r=m.evaluate_synthetic_sequence(m.fixture_events(p),p)
    assert r['status']=='DEFINITION_ROUTE_DEMONSTRATED'
    assert p['disposition']['paths']==8 and p['independent_facts']['PREIMPORT']['output']['authority_digest']==P['roots']['authority']
    assert m.fixture_inventory_oracle(p['inventory_objects'],p['bodies'],p['retained_groups'],p['object_bytes'])['digest']!=m.fixture_inventory_oracle(P['inventory_objects'],P['bodies'],P['retained_groups'],P['object_bytes'])['digest']

@pytest.mark.parametrize('variant',['valid','unexpected','incomplete','timeout'],ids=['real-child1-enclosing-pass','real-child7-rejected','real-child1-incomplete-rejected','real-child-timeout-unknown'])
def test_actual_synthetic_child_observed_exit_and_complete_lossless_outputs(variant,tmp_path):
    argv=[sys.executable,str(D/'synthetic_cli.py'),'--fixture',str(tmp_path/'fixture.json'),'--variant',variant]
    (tmp_path/'fixture.json').write_text(P['public_child']['stdout'])
    start=time.monotonic_ns();timed=False
    try:
        c=subprocess.run(argv,capture_output=True,timeout=0.15 if variant=='timeout' else 5)
        code=c.returncode;stdout=c.stdout;stderr=c.stderr
    except subprocess.TimeoutExpired as ex:
        timed=True;code=None;stdout=ex.stdout or b'';stderr=ex.stderr or b''
    record={'kind':'ACTUAL_SYNTHETIC_CHILD_NOT_NATIVE_AUDIT','actual_argv':argv,'child_exit_code':code,'timed_out':timed,'stdout_bytes':len(stdout),'stdout_sha256':m.sh(stdout),'stderr_bytes':len(stderr),'stderr_sha256':m.sh(stderr),'elapsed_ns':time.monotonic_ns()-start,'native_project_audit':'NOT_RUN'}
    capture=Path(os.environ.get('EXECUTION_CONTRACT_CAPTURE_DIR',str(D/'checks')))/('synthetic-child-'+variant);capture.mkdir(exist_ok=True)
    (capture/'stdout.txt').write_bytes(stdout);(capture/'stderr.txt').write_bytes(stderr);(capture/'observation.json').write_text(json.dumps(record,indent=2)+'\n')
    x=copy.deepcopy(P['public_child']);x.update(exit_code=code,stdout=stdout.decode(),stderr=stderr.decode(),timeout=timed,complete=not timed)
    if variant=='valid':
        assert code==1
        r=m.fixture_public_assertion(x,m.fixture_inventory_oracle(P['inventory_objects'],P['bodies'],P['retained_groups'],P['object_bytes']),P['public_roots']);assert r['enclosing_exit_code']==0
    else:
        with pytest.raises(m.Denial):m.fixture_public_assertion(x,m.fixture_inventory_oracle(P['inventory_objects'],P['bodies'],P['retained_groups'],P['object_bytes']),P['public_roots'])
    if variant=='unexpected':assert code==7
    if variant=='timeout':assert code is None

def test_rejected_reservation_before_allocation_discards_all_positives_without_fabricated_charge():
    b=m.FixtureBudget(clock=lambda:0);b.observe('json_nodes',65535)
    with pytest.raises(m.Denial):b.reserve('json_nodes',1,pending=1)
    assert b.used['json_nodes']==65535
    d=output(b);assert d['preserved_duplicate_paths']==0 and not d['complete']
    assert d['consumed']['json_nodes']==65535 and d['denial_reasons']==['LIMIT_EXHAUSTED']

def test_structure_preflight_rejects_wide_pending_deep_list_and_oversize_strings():
    for x in [{str(n):n for n in range(32768)},list(range(513)),'z'*262145]:
        with pytest.raises(m.Denial):m.structure(x)
    x='leaf'
    for _ in range(33):x=[x]
    with pytest.raises(m.Denial):m.structure(x)

def test_denied_preimport_cannot_hide_zero_or_unknown_complete_host_exit():
    x=output(m.FixtureBudget(clock=lambda:0),native_denial=True)
    for v in [0,None]:
        d=copy.deepcopy(x);d['host_exit_code']=v
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(d,m.PRESCHEMA)

def test_preimport_disposition_uses_complete_original_group_physical_bytes_not_known_constant():
    out=phase('PREIMPORT')['output'];inv=m.fixture_inventory_oracle(P['inventory_objects'],P['bodies'],P['retained_groups'],P['object_bytes'])
    assert out['preserved_duplicate_paths']==inv['preserved_paths']==8
    assert out['preserved_duplicate_bytes']==inv['preserved_bytes']!=12746
    assert out['inventory']['stored_bytes']==inv['stored_bytes']>inv['preserved_bytes']
