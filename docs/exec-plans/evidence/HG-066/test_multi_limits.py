'Whole-invocation boundaries, owner-set cache and staged-route regressions.'
import copy,json
from data_io import read_json
from pathlib import Path
import pytest,jsonschema
import multi_custody_study as m
import multi_fixture as f
import sequence_model as seq
D=Path(__file__).resolve().parent;P=read_json('CURRENT_ROOT_UNION_PROOF.json');R=f.root_states(P);S=f.sources();OUTPUT=json.loads((D/'MULTI_OUTPUT_SCHEMA.json').read_bytes())
def output():
 return {'type':'RETAINED_MULTI_OWNER_CUSTODY_V2','status':'CUSTODY_DENIED','invocation_id':'synthetic-output','selected_identity':P['selected_identity'],'original_base':P['original_base'],'protected_base':P['protected_base'],'head':'a'*40,'audit_phase':'ORIGINAL','complete':True,'accounted_paths':0,'accounted_bytes':0,'physical_paths':P['physical_paths'],'execution_attribution':'UNVERIFIED','acceptance_eligible':False,'execution_reuse':False,'original_guard_status':'ALL_NATIVE_OBSERVED','live_guard_status':'NOT_RUN','denial_reasons':['OBJECT_MISMATCH'],'elapsed_ns':0,'consumed':{k:0 for k in m.LIMITS}}
@pytest.mark.parametrize('counter',list(m.LIMITS))
def test_each_counter_complete_ordinary_denial_boundary_and_overrun(counter):
 x=output();x['consumed'][counter]=m.LIMITS[counter];m.validate_output(x,OUTPUT)
 x['consumed'][counter]+=1
 with pytest.raises((m.Denial,jsonschema.ValidationError)):m.validate_output(x,OUTPUT)
 x.update(complete=False,denial_reasons=['LIMIT_EXHAUSTED']);m.validate_output(x,OUTPUT);assert x['accounted_paths']==x['accounted_bytes']==0 and x['consumed'][counter]==m.LIMITS[counter]+1
@pytest.mark.parametrize('counter',list(m.LIMITS))
def test_shared_global_overrun_discards_all_owner_and_group_results(counter):
 b=m.Budget(dict(m.LIMITS),now=lambda:0);b.used[counter]=m.LIMITS[counter]+1
 out=m.atomic_study([P,P],b,original_sources=S,root_states=R);assert not out['complete'] and out['accounted_paths']==out['accounted_bytes']==0 and 'LIMIT_EXHAUSTED' in out['reasons'] and out['consumed'][counter]==m.LIMITS[counter]+1

def test_deadline_finalization_and_simultaneous_counter_failure_preserve_actual():
 x=output();x.update(complete=False,elapsed_ns=m.DEADLINE_NS+1,denial_reasons=['DEADLINE_EXCEEDED','LIMIT_EXHAUSTED']);x['consumed']['captures']=513;m.validate_output(x,OUTPUT)
 for reason in ['DEADLINE_EXCEEDED','LIMIT_EXHAUSTED']:
  y=copy.deepcopy(x);y['denial_reasons'].remove(reason)
  with pytest.raises((m.Denial,jsonschema.ValidationError)):m.validate_output(y,OUTPUT)

def test_final_accounted_requires_both_native_original_and_strict_live():
 x=output();x.update(status='CUSTODY_ACCOUNTED_ORIGINAL_INVENTORY',denial_reasons=[],accounted_paths=24,accounted_bytes=41682)
 with pytest.raises(jsonschema.ValidationError):m.validate_output(x,OUTPUT)
 x['live_guard_status']='ALL_NATIVE_OBSERVED';m.validate_output(x,OUTPUT)
 for field,value in [('accounted_paths',23),('accounted_bytes',41681),('acceptance_eligible',True),('execution_reuse',True),('execution_attribution','PASS')]:
  y=copy.deepcopy(x);y[field]=value
  with pytest.raises((m.Denial,jsonschema.ValidationError)):m.validate_output(y,OUTPUT)

def test_old_HG065_output_remains_original_type_and_cannot_become_V2():
 old=json.loads((D.parent/'HG-065/OUTPUT_SCHEMA.json').read_bytes());x=output()
 with pytest.raises(jsonschema.ValidationError):jsonschema.validate(x,old)
 x['type']='RETAINED_REPRESENTATION_CUSTODY_V1'
 with pytest.raises(jsonschema.ValidationError):jsonschema.validate(x,OUTPUT)

def context():
 return {'repository':'neutral/example','object_format':'sha1','installed_release':'1'*40,'controller_assets_sha256':'2'*64,'authority_sha256':'3'*64,'selected_identity':'harness-governance-v0.1/HG-201','original_base':'4'*40,'protected_base':'5'*40,'original_selected':'6'*40,'head':'7'*40,'packet_blob':'8'*40,'map_blob':'9'*40,'source':'a'*40,'admission':'b'*40,'owner_set_sha256':'c'*64,'declaration_set_sha256':'d'*64,'delivery_set_sha256':'e'*64,'root_states_sha256':'f'*64,'group_sha256':'a'*64,'edges_sha256':'b'*64,'invocation':'synthetic-complete-group'}
@pytest.mark.parametrize('key',['owner_set_sha256','declaration_set_sha256','delivery_set_sha256','root_states_sha256','group_sha256','edges_sha256','invocation','head','installed_release','authority_sha256'])
def test_one_changed_complete_set_or_context_invalidates_cache(key):
 c=context();base=m.cache_key(c,P['physical_paths'][0],'ORIGINAL_CUSTODY');c[key]=('0' if c[key][0]!='0' else '1')*len(c[key]);assert m.cache_key(c,P['physical_paths'][0],'ORIGINAL_CUSTODY')!=base
@pytest.mark.parametrize('purpose',['PUBLIC_CLI','LIVE','REVIEW_SOURCE_LINEAGE','EXECUTION','ADMISSION'])
def test_custody_cache_cannot_cross_purpose(purpose):
 with pytest.raises(m.Denial):m.cache_key(context(),P['physical_paths'][0],purpose)
@pytest.mark.parametrize('foreign_count',[2,3,6,7],ids=['three-owners','four-owners','seven-owners','future-eight-owners'])
def test_staged_K_two_owner_and_postimport_larger_complete_group(foreign_count):
 p=seq.fixture_multiphase_premise(foreign_count);e=seq.fixture_events(p);x=seq.evaluate_synthetic_sequence(e,p)
 assert x['native_actual_O_to_K']=='NOT_RUN' and x['installed_host']=='NOT_RUN'
 k=seq.fixture_inventory_oracle(p['preimport_inventory_objects'],p['bodies'],p['preimport_retained_groups'],p['preimport_object_bytes']);h=seq.fixture_inventory_oracle(p['inventory_objects'],p['bodies'],p['retained_groups'],p['object_bytes'])
 assert k['files']==9 and h['files']>k['files'] and p['independent_facts']['PREIMPORT']['output']['inventory']['digest']==k['digest']
 assert p['independent_facts']['FINAL_ORIGINAL_AND_LIVE']['original_inventory_digest']==h['digest'] and len(p['independent_facts']['FINAL_ORIGINAL_AND_LIVE']['complete_owner_set'])==1+foreign_count
 jsonschema.validate(e,json.loads((D/'SEQUENCE_SCHEMA.json').read_bytes()))
@pytest.mark.parametrize('mutation',['subset-errors','old-inventory','fake-complete','arbitrary-nonzero','missing-stderr-capture','future-receipt'])
def test_larger_group_public_assertion_rejects_filtered_or_unbound_result(mutation):
 p=seq.fixture_multiphase_premise(6);child=copy.deepcopy(p['public_child']);r=json.loads(child['stdout']);oracle=seq.fixture_inventory_oracle(p['inventory_objects'],p['bodies'],p['retained_groups'],p['object_bytes'])
 if mutation=='subset-errors':r['errors']=r['errors'][:4]
 if mutation=='old-inventory':r['files']=9
 if mutation=='fake-complete':r['native_complete']=False
 if mutation=='arbitrary-nonzero':r['errors']=['arbitrary-denial']
 if mutation=='missing-stderr-capture':child['stderr']='unexpected'
 if mutation=='future-receipt':child['private_receipt']={'accounted':True}
 child['stdout']=json.dumps(r)
 with pytest.raises(seq.Denial):seq.fixture_public_assertion(child,oracle,p['public_roots'])

def test_projected_list_captures_and_original_native_source_562_are_not_widened():
 assert len(m.LIMITS)==22 and m.LIMITS['captures']==m.LIMITS['list_entries']==512
 p=copy.deepcopy(P);p['members']*=31
 with pytest.raises(m.Denial):m.custody_predicate(p,original_sources=S,root_states=R)
 x=next(x for x in P['members'] if x['declaration']['identity'].endswith('HG-058'));source=S[(x['declaration']['revision'],x['declaration']['object']['path'])];assert len(m.load_source_record(source['content'])['files_changed'])==562
