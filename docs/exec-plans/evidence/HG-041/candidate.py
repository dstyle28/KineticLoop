"""Pure representation diagnostic over actual metadata and KL076 computation.

No database connection, owner insertion or prospective task PASS. Closed candidate
bindings deliberately are not accepted as current Resolution/Validation models.
"""
import copy
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

from kineticloop.persistence.metadata import build_metadata
from kineticloop.workflow.deterministic_planning import Resolution, validate
from kineticloop.workflow.planning import digest

ROOT = Path(__file__).resolve().parents[4]


def candidate():
    spec = importlib.util.spec_from_file_location('kl076_pure', ROOT/'tests/unit/workflow/test_deterministic_planning.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    base, config, facts, now = module.source_case()
    f,d,n,r = module.chain(base,config,facts,now)
    assert validate(f,d,n,r,config,now)['semantic_validation']=='PASS'
    parameters={'fuel_units':n.fuel_units,'semantic_class':'TARGET','units':'fixture_units'}
    bindings=[]
    for action,proposal,params,resolution in [('TRAINING',f,f.action.payload(),r.payload()),('NUTRITION',n,parameters,{**r.payload(),'id':str(uuid4()),'action_type':'NUTRITION','nutrition_id':n.id,'nutrition_hash':n.content_hash,'demand_id':d.id,'demand_hash':d.content_hash,'action_parameters_hash':digest(parameters)})]:
        query={'action_type':action,'proposal_id':proposal.id,'proposal_hash':proposal.content_hash,'fitness_id':f.id,'fitness_hash':f.content_hash,'demand_id':d.id,'demand_hash':d.content_hash,'nutrition_id':n.id,'nutrition_hash':n.content_hash,'manifest_id':base.manifest_id,'manifest_hash':r.manifest_hash,'policy_id':base.policy_id,'policy_hash':base.policy_hash,'source_hash':r.source_hash,'action_parameters_hash':digest(params)}
        bindings.append({'action_type':action,'proposal_id':proposal.id,'proposal_hash':proposal.content_hash,'action_parameters_hash':digest(params),'resolution_id':resolution['id'],'resolution_hash':digest(resolution),'query_basis_hash':digest(query)})
    return {'contract':'kl079-full-actions-v1','required_actions':['TRAINING','NUTRITION'],'action_bindings':bindings,'ref_s36_id':r.id,'ref_s34_id':n.id,'ref_s35_id':d.id}, (f,d,n,r)


def check(candidate, expected):
    # Illustrative closed binding comparison, not the future authoritative owner.
    if candidate != expected or len({b['resolution_id'] for b in candidate['action_bindings']})!=2:
        raise ValueError('exact full action binding required')


def run():
    metadata=build_metadata()
    table=metadata.tables['kineticloop.validation_results']
    assert [c.name for c in table.columns if c.name.startswith('ref_s36')]==['ref_s36_id']
    assert str(table.c.typed_payload.type)=='JSONB'
    assert any(fk.name=='fk_s37_s36' for fk in table.foreign_key_constraints)
    table42=metadata.tables['kineticloop.authorization_issuances']
    assert {'ref_s36_id','ref_s37_id','ref_s40_id'}<=set(table42.c.keys())
    expected,chain=candidate(); check(expected,expected)
    bad=[]
    for name in ['missing','duplicate','reordered','cross_action','parameters','proposal','anchor','policy_basis']:
        changed=copy.deepcopy(expected)
        bindings=changed['action_bindings']
        if name=='missing': bindings.pop()
        elif name=='duplicate': bindings[1]=copy.deepcopy(bindings[0])
        elif name=='reordered': bindings.reverse()
        elif name=='cross_action': bindings[1]['resolution_id']=bindings[0]['resolution_id']
        elif name=='anchor': changed['ref_s36_id']=bindings[1]['resolution_id']
        else: bindings[1][{'parameters':'action_parameters_hash','proposal':'proposal_hash','policy_basis':'query_basis_hash'}[name]]=digest('foreign')
        try: check(changed,expected)
        except ValueError: bad.append(name)
        else: raise AssertionError(name)
    f,d,n,r=chain
    try: Resolution.model_validate({**r.payload(),'action_type':'NUTRITION'})
    except ValueError: gap='ACTUAL_LEGACY_MODEL_REJECTS_NUTRITION'
    else: raise AssertionError('original gap disappeared')
    report={'diagnostic_only':True,'real_pg':False,'task_checks':'NOT_RUN','original_gap':gap,'schema':'singular same-subject S37 FK with immutable JSONB; S42 independent per-row S36/S37 refs','positive_mechanical_fdn':True,'distinct_resolution_ids':True,'negative_controls':bad,'nutrition_parameters':{'fuel_units':n.fuel_units,'semantic_class':'TARGET','units':'fixture_units'},'candidate':expected}
    print(json.dumps(report,sort_keys=True))
    return report


if __name__=='__main__': run()
