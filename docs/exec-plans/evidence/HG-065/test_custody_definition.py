"""Actual bounded author checks; no task/runtime acceptance asserted."""
import copy
import hashlib
import importlib.util
import json
import tracemalloc
import os
from portable_support import verify_delivery_sources
from pathlib import Path

import jsonschema
import pytest

import custody_study as study
from custody_study import Budget,Denial,bounded_structure,cache_key,validate_output,LIMITS
from source_fixture import original_sources,neutral_sources_and_proof

ROOT=Path(__file__).resolve().parent
SOURCES=original_sources(ROOT)
PROOF=json.loads((ROOT/'ACTUAL_CUSTODY_PROOF.json').read_bytes())
SPEC=importlib.util.spec_from_file_location('definition_current_native_codec',ROOT.parents[3]/'tools/harness/compact_evidence.py')
NATIVE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NATIVE)
SCHEMA=json.loads((ROOT/'PROOF_SCHEMA.json').read_bytes())
OUTPUT=json.loads((ROOT/'OUTPUT_SCHEMA.json').read_bytes())


def custody_predicate(proof):
    return study.custody_predicate(proof,original_sources=SOURCES)


def atomic_study(proofs,budget):
    return study.atomic_study(proofs,budget,original_sources=SOURCES)


def check_edge_history(history,introduction):
    selected=PROOF['selected_identity'].split('/')[-1]
    endpoints=([PROOF['original_selected']] if history['path'].split('/')[3]==selected else
               [PROOF['protected_base'],PROOF['original_selected']])
    return study.check_edge_history(history,introduction,endpoints=endpoints)


def context():
    return {'repository':'neutral/example','object_format':'sha1','installed_release':'1'*40,
            'controller_assets_sha256':'2'*64,'authority_sha256':'3'*64,
            'selected_identity':'harness-governance-v0.1/HG-201','original_base':'4'*40,
            'protected_base':'5'*40,'original_selected':'6'*40,'head':'7'*40,
            'packet_blob':'8'*40,'map_blob':'9'*40,'source':'a'*40,'admission':'b'*40,
            'declaration_blob':'c'*40,'delivery':'d'*40,'group_sha256':'e'*64,
            'edges_sha256':'f'*64,'invocation':'synthetic-context-one'}


def neutral(proof):
    if isinstance(proof,dict):return {neutral(k):neutral(v) for k,v in proof.items()}
    if isinstance(proof,list):return [neutral(v) for v in proof]
    if isinstance(proof,str):return proof.replace('HG-058','HG-201').replace('HG-059','HG-202')
    return proof


def test_actual_all_six_custody_predicate_is_not_runtime_eligibility():
    jsonschema.validate(PROOF,SCHEMA)
    result=custody_predicate(PROOF)
    assert (result['representations'],result['physical_paths'],result['physical_bytes'])==(6,8,12746)
    assert result['execution_attribution']=='UNVERIFIED'
    assert result['native_full_audit']=='NOT_RUN' and result['runtime_eligibility']=='NOT_DETERMINED'
    assert result['acceptance_eligible'] is False and result['execution_reuse'] is False


@pytest.mark.parametrize('n',range(6),ids=['original-selected-failure','original-selected-c4b','foreign-final74c',
                                        'foreign-superseded09c','foreign-superseded836','foreign-interruption6358'])
def test_original_member_exact_binding_and_native_read_observation(n):
    m=PROOF['members'][n]
    assert m['declaration']['ref']==m['envelope']['path']
    assert m['declaration']['pointers'][0].startswith('files_changed/')
    assert m['representation']['native_read_observation']=='OBSERVED_NATIVE_CODEC_AND_CLASSIFIER_RETURNED_ORDINARY'
    check_edge_history(m['history'],m['introduction'])
    check_edge_history(m['payload_history'],m['payload_introduction'])


def test_neutral_names_satisfy_same_structural_predicate_no_id_hash_allowlist():
    p,sources=neutral_sources_and_proof(PROOF,SOURCES)
    jsonschema.validate(p,SCHEMA)
    assert study.custody_predicate(p,original_sources=sources)['status']=='CUSTODY_PREDICATE_DEMONSTRATED'


MUTATIONS={
 'unknown-field':lambda p:p.update(credential=True),
 'display-only-identity':lambda p:p.update(selected_identity='HG-058'),
 'revision-newline':lambda p:p.update(original_selected=p['original_selected']+'\n'),
 'empty-group':lambda p:p.update(members=[]),
 'omitted-sixth-member':lambda p:p['members'].pop(),
 'duplicate-envelope':lambda p:p['members'].append(copy.deepcopy(p['members'][0])),
 'duplicate-physical-path':lambda p:p['physical_paths'].append(copy.deepcopy(p['physical_paths'][0])),
 'missing-payload':lambda p:p['physical_paths'].pop(),
 'extra-inventory-path':lambda p:p['inventory_intersection'].append('docs/exec-plans/evidence/HG-201/alias.gz'),
 'wrong-physical-bytes':lambda p:p['physical_paths'][0].update(bytes=4251),
 'bool-physical-bytes':lambda p:p['physical_paths'][0].update(bytes=True),
 'symlink':lambda p:p['members'][0]['envelope'].update(mode='120000'),
 'gitlink':lambda p:p['members'][0]['envelope'].update(mode='160000'),
 'directory-mode':lambda p:p['members'][0]['envelope'].update(mode='040000'),
 'path-traversal':lambda p:p['members'][0]['envelope'].update(path='docs/exec-plans/evidence/HG-058/../alias'),
 'absolute-path':lambda p:p['members'][0]['envelope'].update(path='/private/tmp/capture'),
 'foreign-payload':lambda p:p['members'][0]['payload'].update(path=p['members'][-1]['payload']['path']),
 'different-directory':lambda p:p['members'][0]['payload'].update(path=p['members'][0]['payload']['path'].replace('superseded-','other-')),
 'raw-identity-conflict':lambda p:p['members'][0].update(raw_sha256='0'*64),
 'plain-bulk-small-size':lambda p:p['members'][0].update(raw_bytes=16383),
 'raw-size-bool':lambda p:p['members'][0].update(raw_bytes=True),
 'source-role-in-custody':lambda p:p['members'][0]['representation'].update(native_read_observation='REVIEW_SOURCE_INSPECTION'),
 'unverified-byte-equality':lambda p:p['members'][0]['representation'].update(raw_bytes_equal=True),
 'wrong-codec':lambda p:p['members'][0]['representation'].update(codec='zip'),
 'wrong-stored-sha':lambda p:p['members'][0]['representation'].update(stored_sha256='0'*64),
 'missing-declaration-pointers':lambda p:p['members'][0]['declaration'].update(pointers=[]),
 'body-string-declaration':lambda p:p['members'][0]['declaration'].update(pointers=['known_limitations/0']),
 'wrong-declaration-owner':lambda p:p['members'][0]['declaration'].update(identity='harness-governance-v0.1/HG-059'),
 'new-candidate-self-declaration':lambda p:p['members'][0]['declaration'].update(revision='0'*40),
 'filename-declaration-inference':lambda p:p['members'][0]['declaration']['object'].update(path='fake.yaml'),
 'selected-present-in-protected':lambda p:p['members'][0].update(protected_state='EXACT_ORIGINAL'),
 'foreign-not-protected':lambda p:p['members'][-1].update(protected_state='ABSENT'),
 'wrong-map-owner':lambda p:p['map_binding'].update(identity='HG-059'),
 'late-map-context':lambda p:p['map_binding'].update(member_relationship='NEW_MAP'),
 'manufactured-native-audit-pass':lambda p:p['map_binding'].update(native_full_audit='PASS'),
 'single-parent-delivery':lambda p:p['delivery'].update(parents=p['delivery']['parents'][:1]),
 'duplicate-parent-delivery':lambda p:p['delivery'].update(parents=[p['delivery']['parents'][0]]*2),
 'missing-delivery-ancestry':lambda p:p['delivery']['relation_observations'].pop(),
 'wrong-foreign-record':lambda p:p['delivery'].update(original_record='0'*40),
 'wrong-delivered-owner':lambda p:p['delivery'].update(foreign_owner='HG-203'),
 'missing-history-edge':lambda p:p['members'][0]['history']['edges'].pop(),
 'missing-payload-edge':lambda p:p['members'][0]['payload_history']['edges'].pop(),
 'duplicate-edge':lambda p:p['members'][0]['history']['edges'].append(p['members'][0]['history']['edges'][0]),
 'missing-introduction':lambda p:p['members'][0].update(introduction='0'*40),
 'missing-boundary':lambda p:p['members'][0]['history']['boundaries'].pop(),
 'invented-import':lambda p:p['members'][0]['history']['imports'].update({'0'*40:['1'*40,'2'*40]}),
}


@pytest.mark.parametrize('case',list(MUTATIONS),ids=list(MUTATIONS))
def test_structural_provenance_hostile_mutation_rejects(case):
    p=copy.deepcopy(PROOF)
    MUTATIONS[case](p)
    with pytest.raises((Denial, jsonschema.ValidationError)):
        jsonschema.validate(p,SCHEMA)
        custody_predicate(p)


def test_transient_deletion_and_restoration_rejected_despite_equal_endpoints():
    p=copy.deepcopy(PROOF);h=p['members'][1]['history'];intro=p['members'][1]['introduction']
    child=next(v for v in h['nodes'] if v not in h['boundaries'] and v!=intro)
    h['nodes'][child]=None
    with pytest.raises(Denial):custody_predicate(p)


def test_reversed_original_foreign_import_parent_order_rejected():
    p=copy.deepcopy(PROOF);h=p['members'][-1]['history'];child=next(iter(h['imports']))
    h['imports'][child].reverse()
    with pytest.raises(Denial):custody_predicate(p)


def test_wide_structural_input_denied_before_large_pending_allocation():
    value={str(n):None for n in range(100000)}
    tracemalloc.start();baseline=tracemalloc.get_traced_memory()[0]
    try:
        with pytest.raises(Denial,match='LIMIT_EXHAUSTED'):bounded_structure(value)
        assert tracemalloc.get_traced_memory()[1]-baseline<1000000
    finally:tracemalloc.stop()


@pytest.mark.parametrize('value',[list(range(513)),[[[0]]]],ids=['unchanged-list-cap','depth-cap'])
def test_structure_caps_fail_closed(value):
    with pytest.raises(Denial):bounded_structure(value,depth_limit=1)


def test_budget_exact_boundary_positive_then_overrun_preserves_observed_charge():
    b=Budget({'groups':1});b.charge('groups',1)
    with pytest.raises(Denial):b.charge('groups',1)
    assert b.used['groups']==2 and b.exhausted


@pytest.mark.parametrize('amount',[-1,True,1.1],ids=['negative','bool','float'])
def test_budget_invalid_counter_type_rejects(amount):
    with pytest.raises(Denial):Budget({'groups':1}).charge('groups',amount)


def test_deadline_exact_boundary_then_actual_overrun_preserved():
    clock=[0];b=Budget({'groups':2},now=lambda:clock[0]);clock[0]=120000000000;b.charge('groups',1)
    clock[0]+=1
    with pytest.raises(Denial,match='DEADLINE_EXCEEDED'):b.charge('groups',1)
    assert clock[0]==120000000001


def test_mixed_group_exhaustion_discards_every_positive_result():
    out=atomic_study([PROOF,PROOF],Budget({'groups':1}))
    assert not out['complete'] and out['accounted_paths']==out['accounted_bytes']==0
    assert out['groups']==['CUSTODY_DENIED','CUSTODY_DENIED']


def test_cross_group_duplicate_paths_reject_without_double_accounting():
    out=atomic_study([PROOF,PROOF],Budget({'groups':2}))
    assert out['accounted_paths']==out['accounted_bytes']==0
    assert out['groups']==['CUSTODY_DENIED','CUSTODY_DENIED'] and 'INVENTORY_MISMATCH' in out['reasons']


def test_cross_task_context_discards_every_group():
    out=atomic_study([PROOF,neutral(PROOF)],Budget({'groups':2}))
    assert not out['complete'] and out['groups']==['CUSTODY_DENIED','CUSTODY_DENIED']


@pytest.mark.parametrize('field',list(context()),ids=lambda x:'cache-'+x)
def test_cache_every_context_dimension_separates_verdict(field):
    c=context();base=cache_key(c,PROOF['physical_paths'][0],'ORIGINAL_CUSTODY')
    if field=='object_format':
        c[field]='sha256'
        with pytest.raises(Denial):cache_key(c,PROOF['physical_paths'][0],'ORIGINAL_CUSTODY')
    else:
        c[field]=('neutral/other' if field=='repository' else
                  'harness-governance-v0.1/HG-202' if field=='selected_identity' else
                  'synthetic-context-two' if field=='invocation' else '0'*len(c[field]))
        assert cache_key(c,PROOF['physical_paths'][0],'ORIGINAL_CUSTODY')!=base


@pytest.mark.parametrize('purpose',['EXECUTION','REVIEW_SOURCE_LINEAGE','RRO','M3','ADMISSION','LIVE_BASE','UNKNOWN'])
def test_cache_purpose_cannot_cross_into_custody(purpose):
    with pytest.raises(Denial):cache_key(context(),PROOF['physical_paths'][0],purpose)


@pytest.mark.parametrize('invocation',['','x'*129,'unicode-中','x\n'])
def test_invalid_invocation_rejects(invocation):
    c=context();c['invocation']=invocation
    with pytest.raises(Denial):cache_key(c,PROOF['physical_paths'][0],'ORIGINAL_CUSTODY')


def test_context_unknown_field_is_not_credential():
    c=context();c['trusted']=True
    with pytest.raises(Denial):cache_key(c,PROOF['physical_paths'][0],'ORIGINAL_CUSTODY')


def output():
    return {'type':'RETAINED_REPRESENTATION_CUSTODY_V1','status':'CUSTODY_DENIED','invocation_id':'synthetic-output',
            'selected_identity':PROOF['selected_identity'],'original_base':PROOF['original_base'],
            'protected_base':PROOF['protected_base'],'head':PROOF['original_selected'],'audit_phase':'ORIGINAL',
            'complete':False,'accounted_paths':0,'accounted_bytes':0,'physical_paths':PROOF['physical_paths'],
            'execution_attribution':'UNVERIFIED','acceptance_eligible':False,'execution_reuse':False,
            'original_guard_status':'NOT_RUN','live_guard_status':'NOT_RUN','denial_reasons':['INCOMPLETE_CONTEXT'],
            'elapsed_ns':123456789,'consumed':{key:0 for key in json.loads((ROOT/'BUDGETS.json').read_bytes())['incremental_work_limits']}}


def test_closed_output_denied_example_is_diagnostic_only():
    jsonschema.validate(output(),OUTPUT)


@pytest.mark.parametrize('field,value',[('acceptance_eligible',True),('execution_reuse',True),
                                      ('execution_attribution','PASS'),('type','ACCOUNTED_PROTECTED_IMPORT'),
                                      ('audit_phase','LIVE'),('accounted_paths',1),('accounted_bytes',1),
                                      ('elapsed_ns',True),('complete',True),('unknown',True)])
def test_closed_output_cannot_relabel_custody_as_acceptance(field,value):
    d=output();d[field]=value
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(d,OUTPUT)


def test_accounted_output_requires_both_native_original_and_strict_live_observed():
    d=output();d.update(status='CUSTODY_ACCOUNTED_ORIGINAL_INVENTORY',complete=True,
                        accounted_paths=8,accounted_bytes=12746,denial_reasons=[])
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(d,OUTPUT)
    d.update(original_guard_status='ALL_NATIVE_OBSERVED',live_guard_status='ALL_NATIVE_OBSERVED')
    validate_output(d,OUTPUT) # synthetic schema example, not an actual runtime result


@pytest.mark.parametrize('field,value',[('accounted_paths',7),('accounted_bytes',12745),
                                      ('elapsed_ns',120000000001)])
def test_accounted_output_exact_physical_counts_and_deadline(field,value):
    d=output();d.update(status='CUSTODY_ACCOUNTED_ORIGINAL_INVENTORY',complete=True,
                        accounted_paths=8,accounted_bytes=12746,denial_reasons=[],
                        original_guard_status='ALL_NATIVE_OBSERVED',live_guard_status='ALL_NATIVE_OBSERVED')
    d[field]=value
    with pytest.raises((Denial,jsonschema.ValidationError)):validate_output(d,OUTPUT)


def test_inherited_map_actual_components_and_original_schema_bindings():
    d=json.loads((Path(os.environ['HG065_OBSERVATIONS'])/'INHERITED_COMPONENT_OBSERVATIONS.json').read_bytes())
    assert d['owner']=='HG-054' and len(d['components'])==2
    assert all(x['status']=='OBSERVED_EXACT_SNAPSHOTS_METADATA_AND_RAW_BYTES'
               and not x['native_reader_denials'] for x in d['components'])
    assert d['native_full_map_history_audit']=='NOT_RUN' and d['all_map_inventory']=='NOT_RUN'
    assert all(x['result']=='OBSERVED_ORIGINAL_SCHEMA_VALID' for x in d['original_declaration_schema_checks'])


@pytest.mark.parametrize('codec',['gzip-v1','xz-v1'])
def test_unchanged_native_codec_preserves_exact_ordinary_bytes(codec):
    raw=b'ordinary report\n'*1200
    stored=NATIVE.encode(raw,codec)
    assert NATIVE.decode(stored,codec,len(raw))==raw
    assert NATIVE.envelope(raw) is None


@pytest.mark.parametrize('codec',['gzip-v1','xz-v1'])
@pytest.mark.parametrize('mutation',['trailing','truncated','wrong-bound'])
def test_native_codec_integrity_denials_preserved(codec,mutation):
    raw=b'opaque ordinary body'*1200;stored=NATIVE.encode(raw,codec)
    if mutation=='trailing':stored+=b'garbage'
    elif mutation=='truncated':stored=stored[:-1]
    with pytest.raises(ValueError):NATIVE.decode(stored,codec,len(raw)+(1 if mutation=='wrong-bound' else 0))


@pytest.mark.parametrize('body',[b'{\x22kineticloop_evidence\x22:',b'[{\x22kineticloop_evidence\x22:\x22gzip-v1\x22}]',
                               b'{\x22kineticloop_evidence\x22:1,\x22kineticloop_evidence\x22:2}',
                               b'{\x22payload\x22:\x22x\x22,\x22stored_sha256\x22:\x22x\x22,\x22raw_sha256\x22:\x22x\x22'])
def test_native_reserved_classifier_duties_not_suppressed(body):
    with pytest.raises(ValueError):NATIVE.envelope(body)


def test_native_storage_limits_identical_to_current_authority_and_prior_rule():
    b=json.loads((ROOT/'BUDGETS.json').read_bytes())
    assert [NATIVE.PLAIN_LIMIT,NATIVE.STORED_LIMIT,NATIVE.RAW_LIMIT,NATIVE.TOTAL_LIMIT]==[
        b['storage_limits'][k] for k in ('plain_bytes','stored_payload_bytes','raw_payload_bytes','total_changed_bytes')]
    old=json.loads((ROOT/'FIXTURE_INPUTS.json').read_bytes())['prior_rule']
    assert b['incremental_work_limits']==old['incremental_work_limits']
    assert b['ordinary_execution_list_cap']==512


def test_original6358_child_unknown_remains_separate_from_driver143():
    d=json.loads((Path(os.environ['HG065_OBSERVATIONS'])/'ACTUAL_PREPARATION_DISPOSITION.json').read_bytes())
    assert d['child_exit_6358'] is None and d['driver_exit_6358']==143
    assert d['historical_execution_attribution']=='UNVERIFIED'


def test_public_and_worker_callers_have_no_custody_dispatch_or_receipt_input():
    d=json.loads((ROOT/'CALLER_MATRIX.json').read_bytes())
    assert sum(row['may_construct_private_context'] for row in d['rows'])==2
    assert all(not row['may_consume_supplied_custody_receipt'] for row in d['rows'])
    assert all(not row['may_construct_private_context'] for row in d['rows'][2:])


def test_complete_definition_input_hashes_and_snapshots_match_manifest():
    # Packaging-only adaptation: immutable Git and exact delivered/projection bytes.
    # External preparation history stays pinned, never required for acceptance.
    verify_delivery_sources()


def test_no_native_full_audit_or_historical_script_execution_claim():
    d=json.loads((Path(os.environ['HG065_OBSERVATIONS'])/'IMMUTABLE_COMMAND_READS.json').read_bytes())
    assert not d['full_audit_run'] and not d['historical_scripts_executed']
    assert all(row['argv'][0]=='git' and row['exit']==0 for row in d['commands'])


R2_CONTRADICTIONS={
 'swapped-envelope-history':lambda p:p['members'][0].update(history=copy.deepcopy(p['members'][1]['history']),
                                                          introduction=p['members'][1]['introduction']),
 'envelope-used-for-payload-history':lambda p:p['members'][0].update(payload_history=copy.deepcopy(p['members'][0]['history']),
                                                                  payload_introduction=p['members'][0]['introduction']),
 'foreign-used-for-selected-payload-history':lambda p:p['members'][0].update(payload_history=copy.deepcopy(p['members'][-1]['payload_history']),
                                                                          payload_introduction=p['members'][-1]['payload_introduction']),
 'same-declaration-tuple-conflicting-blob':lambda p:p['members'][1]['declaration']['object'].update(blob='0'*40,sha256='0'*64),
 'reversed-top-level-delivery':lambda p:p['delivery']['parents'].reverse(),
 'nonexistent-top-level-delivery':lambda p:p['delivery'].update(commit='0'*40),
 'wrong-original-declaration-pointer':lambda p:p['members'][0]['declaration'].update(pointers=['files_changed/999999']),
 'other-member-pointer':lambda p:p['members'][0]['declaration'].update(pointers=p['members'][1]['declaration']['pointers']),
 'duplicate-pointer':lambda p:p['members'][0]['declaration']['pointers'].append(p['members'][0]['declaration']['pointers'][0]),
 'wrong-protected-endpoint':lambda p:p.update(protected_base='0'*40),
 'wrong-original-base-and-map-claim':lambda p:(p.update(original_base='0'*40),p['map_binding'].update(original_base='0'*40)),
}


@pytest.mark.parametrize('case',list(R2_CONTRADICTIONS),ids=list(R2_CONTRADICTIONS))
def test_r2_contradictory_member_source_delivery_and_endpoint_rejects(case):
    p=copy.deepcopy(PROOF);R2_CONTRADICTIONS[case](p)
    jsonschema.validate(p,SCHEMA)
    with pytest.raises(Denial):custody_predicate(p)


def test_r2_disconnected_self_cycle_and_disconnected_acyclic_chain_reject():
    for cycle in [True,False]:
        h=copy.deepcopy(PROOF['members'][0]['history']);a,b='0'*40,'1'*40
        if cycle:
            h['nodes'][a]=h['original'];h['parents'][a]=[a];h['edges'].append([a,a])
        else:
            h['nodes'].update({a:None,b:None});h['parents'][b]=[a];h['boundaries'].append(a);h['edges'].append([a,b])
        with pytest.raises(Denial,match='HISTORY_(CYCLE|DISCONNECTED)'):
            check_edge_history(h,PROOF['members'][0]['introduction'])


def test_r2_independent_original_source_corruption_and_absence_reject():
    d=PROOF['members'][0]['declaration'];key=(d['revision'],d['object']['path'])
    for absent in [False,True]:
        sources=copy.deepcopy(SOURCES)
        if absent:sources.pop(key)
        else:sources[key]['content']+=b'changed'
        with pytest.raises(Denial,match='DECLARATION_SOURCE_(INVALID|UNAVAILABLE)'):
            study.custody_predicate(PROOF,original_sources=sources)


def test_r2_original_native_record_lists_and_projected_proof_lists_keep_their_own_limits():
    d=PROOF['members'][0]['declaration'];record=study.load_source_record(SOURCES[(d['revision'],d['object']['path'])]['content'])
    schema_source=SOURCES[(d['revision'],'HARNESS_CHANGE.schema.json')]
    schema=json.loads(schema_source['content'])
    assert 'maxItems' not in schema['properties']['files_changed']
    assert len(record['files_changed'])==562
    # Native original schema is read completely, without truncating source refs.
    jsonschema.validate(record,schema)
    with pytest.raises(Denial):bounded_structure(list(range(513)))
    assert LIMITS['list_entries']==512


def test_r2_each_complete_output_counter_exact_boundary_and_overrun_denial():
    checked=[]
    for counter,maximum in LIMITS.items():
        d=output();d.update(complete=True,denial_reasons=['OBJECT_MISMATCH']);d['consumed'][counter]=maximum
        validate_output(d,OUTPUT)
        d['consumed'][counter]=maximum+1
        with pytest.raises((Denial,jsonschema.ValidationError)):validate_output(d,OUTPUT)
        d.update(complete=False,denial_reasons=['OBJECT_MISMATCH','LIMIT_EXHAUSTED'])
        validate_output(d,OUTPUT)
        assert d['consumed'][counter]==maximum+1 and d['accounted_paths']==d['accounted_bytes']==0
        checked.append(counter)
    assert set(checked)==set(LIMITS)


def test_r2_each_actual_exceeded_counter_discards_every_group_and_preserves_counter():
    for counter,maximum in LIMITS.items():
        b=Budget(dict(LIMITS));b.used[counter]=maximum+1
        out=atomic_study([PROOF],b)
        assert not out['complete'] and out['groups']==['CUSTODY_DENIED']
        assert out['accounted_paths']==out['accounted_bytes']==0 and 'LIMIT_EXHAUSTED' in out['reasons']
        assert out['consumed'][counter]==maximum+1


def test_r2_complete_ordinary_denial_deadline_exact_boundary_and_overrun():
    d=output();d.update(complete=True,denial_reasons=['OBJECT_MISMATCH'],elapsed_ns=120000000000)
    validate_output(d,OUTPUT)
    d['elapsed_ns']+=1
    with pytest.raises((Denial,jsonschema.ValidationError)):validate_output(d,OUTPUT)
    d.update(complete=False,denial_reasons=['OBJECT_MISMATCH','DEADLINE_EXCEEDED'])
    validate_output(d,OUTPUT);assert d['elapsed_ns']==120000000001


def test_r2_deadline_expires_after_last_unchanged_predicate_discards_result(monkeypatch):
    clock=[0];b=Budget({'groups':1},now=lambda:clock[0]);original=study.custody_predicate
    def slow(proof,**kwargs):
        result=original(proof,**kwargs);clock[0]=120000000001;return result
    monkeypatch.setattr(study,'custody_predicate',slow)
    out=atomic_study([PROOF],b)
    assert not out['complete'] and out['groups']==['CUSTODY_DENIED']
    assert out['elapsed_ns']==120000000001 and out['accounted_paths']==out['accounted_bytes']==0
    assert 'DEADLINE_EXCEEDED' in out['reasons']


def test_r2_deadline_final_publication_check_after_complete_predicate(monkeypatch):
    # The first check, post-predicate check and loop check are in time; publication
    # is the fourth check. Its actual overrun cannot leave a surviving positive.
    clock=[0];calls=[0];b=Budget({'groups':1},now=lambda:clock[0]);original=b.check
    def final_check():
        calls[0]+=1
        if calls[0]==4:clock[0]=120000000001
        original()
    monkeypatch.setattr(b,'check',final_check)
    out=atomic_study([PROOF],b)
    assert calls[0]>=4 and not out['complete'] and out['groups']==['CUSTODY_DENIED']
    assert out['elapsed_ns']==120000000001


def test_r2_post_predicate_counter_overrun_discards_mixed_invocation(monkeypatch):
    b=Budget(dict(LIMITS));original=study.custody_predicate;calls=[0]
    def overrun(proof,**kwargs):
        result=original(proof,**kwargs);calls[0]+=1;b.used['git_operations']=16385;return result
    monkeypatch.setattr(study,'custody_predicate',overrun)
    out=atomic_study([PROOF,PROOF],b)
    assert calls[0]==1 and not out['complete'] and out['groups']==['CUSTODY_DENIED']*2
    assert out['consumed']['git_operations']==16385 and out['accounted_paths']==out['accounted_bytes']==0


def test_r2_unperformed_status_has_exact_unperformed_reason_and_no_accounting():
    d=output();d.update(status='CUSTODY_UNPERFORMED',denial_reasons=['UNPERFORMED'])
    validate_output(d,OUTPUT)
    for bad in [[],['UNPERFORMED','OBJECT_MISMATCH'],['OBJECT_MISMATCH']]:
        d['denial_reasons']=bad
        with pytest.raises(jsonschema.ValidationError):validate_output(d,OUTPUT)


def test_r2_mixed_counter_and_deadline_overruns_preserve_both_actual_observations():
    d=output();d.update(complete=False,elapsed_ns=120000000001,denial_reasons=['LIMIT_EXHAUSTED','DEADLINE_EXCEEDED'])
    d['consumed']['git_operations']=16385;validate_output(d,OUTPUT)
    assert d['elapsed_ns']==120000000001 and d['consumed']['git_operations']==16385
    d['denial_reasons']=['LIMIT_EXHAUSTED']
    with pytest.raises(jsonschema.ValidationError):validate_output(d,OUTPUT)


def test_r2_late_exhaustion_on_ordinary_predicate_denial_is_incomplete(monkeypatch):
    clock=[0];b=Budget(dict(LIMITS),now=lambda:clock[0])
    def deny(proof,**kwargs):
        clock[0]=120000000001;b.used['git_operations']=16385;raise Denial('OBJECT_MISMATCH')
    monkeypatch.setattr(study,'custody_predicate',deny)
    out=atomic_study([PROOF],b)
    assert not out['complete'] and out['groups']==['CUSTODY_DENIED']
    assert {'OBJECT_MISMATCH','LIMIT_EXHAUSTED','DEADLINE_EXCEEDED'}<=set(out['reasons'])
    assert out['consumed']['git_operations']==16385 and out['elapsed_ns']==120000000001


def test_r2_missing_independent_original_source_cannot_claim_complete_invocation():
    out=study.atomic_study([PROOF],Budget(dict(LIMITS)),original_sources={})
    assert not out['complete'] and out['groups']==['CUSTODY_DENIED']
    assert 'DECLARATION_SOURCE_UNAVAILABLE' in out['reasons']


def test_r2_completed_ordinary_denial_with_valid_context_has_zero_accounting():
    p=copy.deepcopy(PROOF);p['members'][0]['history']['original']=p['members'][1]['envelope']
    out=atomic_study([p],Budget(dict(LIMITS)))
    assert out['complete'] and out['groups']==['CUSTODY_DENIED']
    assert out['accounted_paths']==out['accounted_bytes']==0
