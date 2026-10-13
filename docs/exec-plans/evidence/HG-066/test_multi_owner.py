'Prospective semantic regressions, not execution or native audit acceptance.'
import copy,json
from data_io import read_json
from pathlib import Path
import pytest,jsonschema
import multi_custody_study as m
import multi_fixture as f
D=Path(__file__).resolve().parent;P=read_json('CURRENT_ROOT_UNION_PROOF.json');R=f.root_states(P);S=f.sources();OWNERS=sorted({x['declaration']['identity'].split('/')[-1] for x in P['members']})

def test_current_all_seven_root_union_components_exact_accounting_not_runtime():
 jsonschema.validate(P,json.loads((D/'MULTI_PROOF_SCHEMA.json').read_bytes()));x=m.custody_predicate(P,original_sources=S,root_states=R)
 assert (x['owners'],x['representations'],x['physical_paths'],x['physical_bytes'])==(7,17,24,41682)
 assert x['native_full_audit']=='NOT_RUN' and x['runtime_eligibility']=='NOT_DETERMINED' and not x['acceptance_eligible'] and not x['execution_reuse']

def test_current_union_cannot_conform_to_actual_K_H_operational_proof():
 with pytest.raises(jsonschema.ValidationError):jsonschema.validate(P,json.loads((D/'OPERATION_PROOF_SCHEMA.json').read_bytes()))

def test_complete_neutral_seven_owner_sources_graphs_and_names():
 p,s,r=f.neutral(P,S,R);assert m.custody_predicate(p,original_sources=s,root_states=r)['owners']==7

@pytest.mark.parametrize('o',OWNERS)
@pytest.mark.parametrize('mutation',['mode','identity','pointer','schema','record-blob','introduction','edge','deleted-state','payload-history','borrowed-payload','omitted-reference','missing-root-state'])
def test_invalid_one_owner_discards_whole_group(o,mutation):
 p=copy.deepcopy(P);r=copy.deepcopy(R);s=dict(S);x=next(x for x in p['members'] if x['envelope']['path'].split('/')[3]==o)
 if mutation=='mode':x['envelope']['mode']='120000'
 if mutation=='identity':x['declaration']['identity']='harness-governance-v0.1/HG-999'
 if mutation=='pointer':x['declaration']['pointers']=['files_changed/999999']
 if mutation=='schema':s.pop((x['declaration']['revision'],'HARNESS_CHANGE.schema.json'))
 if mutation=='record-blob':x['declaration']['object']['blob']='0'*40
 if mutation=='introduction':x['introduction']='0'*40
 if mutation=='edge':x['history']['edges'].pop()
 if mutation=='deleted-state':x['history']['nodes'][x['introduction']]=None
 if mutation=='payload-history':x['payload_history']['original']=p['members'][0]['envelope']
 if mutation=='borrowed-payload':x['payload']=next(a['payload'] for a in p['members'] if a['envelope']['path'].split('/')[3]!=o)
 if mutation=='omitted-reference':p['members'].remove(x)
 if mutation=='missing-root-state':r['protected'].pop(x['envelope']['path'])
 b=m.Budget(dict(m.LIMITS),now=lambda:0);out=m.atomic_study([p],b,original_sources=s,root_states=r)
 assert out['reasons'] and out['accounted_paths']==out['accounted_bytes']==0 and out['groups']==['CUSTODY_DENIED']

@pytest.mark.parametrize('n',range(6),ids=OWNERS[1:])
@pytest.mark.parametrize('mutation',['missing','parent-order','wrong-F','wrong-owner','missing-relation','duplicate-owner','unrelated-node'])
def test_each_foreign_delivery_is_independently_required(n,mutation):
 p=copy.deepcopy(P);d=p['deliveries'][n]
 if mutation=='missing':p['deliveries'].pop(n)
 if mutation=='parent-order':d['parents'].reverse()
 if mutation=='wrong-F':d['original_record']='0'*40
 if mutation=='wrong-owner':d['foreign_owner']='HG-999'
 if mutation=='missing-relation':d['relation_observations'].pop()
 if mutation=='duplicate-owner':p['deliveries'].append(copy.deepcopy(d))
 if mutation=='unrelated-node':d['commit']='0'*40
 with pytest.raises(m.Denial):m.custody_predicate(p,original_sources=S,root_states=R)

def test_omitting_coherent_owner_cannot_split_independent_inventory_into_pairs():
 p=copy.deepcopy(P);o='HG-065';p['members']=[x for x in p['members'] if x['envelope']['path'].split('/')[3]!=o];p['physical_paths']=[x for x in p['physical_paths'] if x['path'].split('/')[3]!=o];p['inventory_intersection']=[x['path'] for x in p['physical_paths']];p['deliveries']=[x for x in p['deliveries'] if x['foreign_owner']!=o]
 with pytest.raises(m.Denial):m.custody_predicate(p,original_sources=S,root_states=R)

def test_later_foreign_owner_absent_Q_is_not_rebound_to_Q_declaration():
 x=next(m for m in P['members'] if '/HG-065/' in m['envelope']['path']);assert R['selected'][x['envelope']['path']] is None
 p=copy.deepcopy(P);x=next(m for m in p['members'] if '/HG-065/' in m['envelope']['path']);x['declaration']['revision']=p['original_selected']
 with pytest.raises(m.Denial):m.custody_predicate(p,original_sources=S,root_states=R)

def test_shared_parent_conflict_and_transient_revert_remain_denials():
 p=copy.deepcopy(P);x=p['members'][-1]['history'];rev=next(iter(x['parents']));x['parents'][rev]=['0'*40]
 with pytest.raises(m.Denial):m.custody_predicate(p,original_sources=S,root_states=R)
 p=copy.deepcopy(P);x=p['members'][-1]['history'];rev=next(v for v in x['nodes'] if x['nodes'][v] is not None);x['nodes'][rev]=None
 with pytest.raises(m.Denial):m.custody_predicate(p,original_sources=S,root_states=R)

def test_same_owner_second_physical_payload_and_alias_denied():
 p=copy.deepcopy(P);x=p['members'][1];alias=copy.deepcopy(x['payload']);alias['path']=alias['path'].replace('/superseded-','/other-');x['payload']=alias;p['physical_paths'].append(alias);p['inventory_intersection']=sorted(x['path'] for x in p['physical_paths'])
 with pytest.raises(m.Denial):m.custody_predicate(p,original_sources=S,root_states=R)

def test_no_definition_purpose_or_private_receipt_credential_field():
 for value in [True,{'approved':True},'PUBLIC_CLI']:
  p=copy.deepcopy(P);p['private_context']=value
  with pytest.raises(m.Denial):m.custody_predicate(p,original_sources=S,root_states=R)
