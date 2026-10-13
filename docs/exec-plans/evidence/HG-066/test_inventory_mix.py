'Faithful mixed whole-inventory worlds; synthetic, never native certification.'
import copy,json
import pytest
import sequence_model as m

def add_raw(p,owners=('HG-201',),salt='ordinary unrelated',references=1,raw_override=None):
    raw=raw_override if raw_override is not None else (salt+'\n').encode()*600;key=m.sh(raw)
    for owner in owners:
        m.nf.put_representation(p['inventory_objects'],p['bodies'],p['object_bytes'],f'docs/exec-plans/evidence/{owner}/mix-{key[:8]}',raw,references=references,stem='unrelated')
    p['inventory_objects'].sort(key=lambda x:x['path']);return key

def oracle(p):return m.fixture_inventory_oracle(p['inventory_objects'],p['bodies'],p['retained_groups'],p['object_bytes'])
def refresh_report(p,inv):
    r=json.loads(p['public_child']['stdout']);r.update(files=inv['files'],stored_bytes=inv['stored_bytes'],inventory_sha256=inv['digest'],errors=inv['errors']);p['public_child']['stdout']=json.dumps(r)
    p['independent_facts']['AUTHOR_CHECKS']['public_denial']=m.fixture_public_assertion(p['public_child'],inv,p['public_roots'])
    p['independent_facts']['FINAL_ORIGINAL_AND_LIVE'].update(original_inventory_digest=inv['digest'],complete_owner_set=sorted({x['path'].split('/')[3] for rows in p['retained_groups'].values() for x in rows if x['kind']=='ENVELOPE'}))

def mixed():
    p=m.fixture_multiphase_premise(6);add_raw(p,salt='existing owner distinct ordinary');add_raw(p,('HG-299',),salt='another owner distinct ordinary');return p

@pytest.mark.parametrize('owners',[('HG-201',),('HG-299',)],ids=['existing-owner','another-owner'])
@pytest.mark.parametrize('references',[1,2],ids=['one-reference','shared-ordinary-payload'])
def test_valid_unrelated_raw_stays_in_full_inventory_without_custody_credit(owners,references):
    p=m.fixture_multiphase_premise(6);before=oracle(p);key=add_raw(p,owners,references=references);after=oracle(p)
    assert after['files']==before['files']+1+references and after['stored_bytes']==before['stored_bytes']+sum(x['bytes'] for x in p['inventory_objects'] if x['raw_key']==key or x['path'].endswith(key+'.gz'))
    assert after['digest']!=before['digest'] and after['errors']==before['errors'] and len(after['errors'])==14
    assert after['preserved_paths']==before['preserved_paths'] and after['preserved_bytes']==before['preserved_bytes']
    assert key not in p['retained_groups'];refresh_report(p,after)
    assert m.evaluate_synthetic_sequence(m.fixture_events(p),p)['runtime_eligibility']=='NOT_DETERMINED'

def test_two_unrelated_raws_in_existing_and_other_owner_keep_all_physical_bytes():
    p=m.fixture_multiphase_premise(6);before=oracle(p);p=mixed();after=oracle(p)
    assert after['files']==before['files']+4 and after['stored_bytes']==sum(x['bytes'] for x in p['inventory_objects'])
    assert after['stored_bytes']==sum(x['bytes'] for x in p['inventory_objects']) and after['digest']==m.sh(p['inventory_objects'])
    assert after['errors']==before['errors'] and after['preserved_paths']==before['preserved_paths']==23
    refresh_report(p,after);assert m.evaluate_synthetic_sequence(m.fixture_events(p),p)['phases']==21

@pytest.mark.parametrize('size',[100,16383,16384],ids=['small-ordinary','threshold-minus-one','threshold-exact'])
def test_raw_threshold_and_separate_group_physical_accounting(size):
    p=m.fixture_multiphase_premise(6);before=oracle(p);key=add_raw(p,('HG-201','HG-299'),raw_override=b'x'*size);newkey=key
    if size>=16384:
        with pytest.raises(m.Denial,match='UNEXPECTED_OR_MISSING_COLLISION_GROUP'):oracle(p)
        p['retained_groups'][newkey]=m.fixture_group_binding(p['inventory_objects'],newkey)
    after=oracle(p)
    assert len(after['errors'])==len(before['errors'])+(size>=16384)
    assert after['preserved_paths']==before['preserved_paths']+(4 if size>=16384 else 0)
    assert after['preserved_bytes']==before['preserved_bytes']+(sum(x['bytes'] for x in p['inventory_objects'] if x['raw_key']==key or x['path'].endswith(key+'.gz')) if size>=16384 else 0)

def test_multiple_independently_bound_complete_raw_groups_derive_all_diagnostics():
    p=mixed();before=oracle(p);key=add_raw(p,('HG-201','HG-299','HG-300'),salt='second retained complete group',references=2)
    with pytest.raises(m.Denial,match='UNEXPECTED_OR_MISSING_COLLISION_GROUP'):oracle(p)
    # New independent synthetic ORIGINAL world; never a supplied runtime allowlist.
    p['retained_groups'][key]=m.fixture_group_binding(p['inventory_objects'],key);after=oracle(p)
    assert len(after['errors'])==len(before['errors'])+4 and after['preserved_paths']==before['preserved_paths']+9
    assert after['preserved_bytes']==before['preserved_bytes']+sum(x['bytes'] for x in p['inventory_objects'] if x['raw_key']==key or x['path'].endswith(key+'.gz'))
    refresh_report(p,after);assert m.evaluate_synthetic_sequence(m.fixture_events(p),p)['acceptance_eligible'] is False

@pytest.mark.parametrize('mutation',['native-error','bool-byte','bad-mode','bad-hash','bad-raw','bad-owner','payload-missing','envelope-missing','payload-unreferenced','payload-kind','payload-fields','duplicate-path','unknown-field','unsafe-path','plain-bulk-error'])
def test_unrelated_malformed_objects_deny_whole_inventory(mutation):
    p=mixed();rows=[x for x in p['inventory_objects'] if '/mix-' in x['path'] and x['path'].split('/')[3]=='HG-299'];e=next(x for x in rows if x['kind']=='ENVELOPE');q=next(x for x in rows if x['kind']=='PAYLOAD')
    if mutation=='native-error':e['native_errors']=['bad-codec']
    if mutation=='bool-byte':e['bytes']=True
    if mutation=='bad-mode':q['mode']='120000'
    if mutation=='bad-hash':q['sha256']='invalid'
    if mutation=='bad-raw':p['bodies'][e['raw_key']]='00'
    if mutation=='bad-owner':e['payload']=e['payload'].replace('HG-299','HG-201')
    if mutation=='payload-missing':p['inventory_objects'].remove(q)
    if mutation=='envelope-missing':p['inventory_objects'].remove(e)
    if mutation=='payload-unreferenced':p['inventory_objects'].append({**q,'path':q['path']+'-alias'})
    if mutation=='payload-kind':q['kind']='PLAIN'
    if mutation=='payload-fields':q['raw_key']=e['raw_key']
    if mutation=='duplicate-path':p['inventory_objects'].append(copy.deepcopy(q))
    if mutation=='unknown-field':e['credential']=True
    if mutation=='unsafe-path':e['path']=e['path'].replace('/mix-','/../mix-')
    if mutation=='plain-bulk-error':p['inventory_objects'].append({**q,'path':q['path']+'.plain','kind':'PLAIN','bytes':262145})
    p['inventory_objects'].sort(key=lambda x:x['path'])
    with pytest.raises(m.Denial):oracle(p)

@pytest.mark.parametrize('mutation',['foreign-only-extra-group','same-owner-second-payload','added-bound-group-reference','missing-bound-group-member','bound-source-byte-change','missing-group-binding','filtered-collision-key'])
def test_unexpected_invalid_or_incomplete_collision_never_produces_partial_credit(mutation):
    p=mixed()
    if mutation=='foreign-only-extra-group':add_raw(p,('HG-299','HG-300'),salt='unrelated unexpected collision')
    if mutation=='same-owner-second-payload':
        key=next(iter(p['retained_groups']));directory='docs/exec-plans/evidence/HG-201/another';payload=directory+'/'+key+'.gz'
        p['inventory_objects'].extend([{'path':payload,'mode':'100644','kind':'PAYLOAD','bytes':119,'sha256':m.sh(b'new-payload'),'raw_key':None,'payload':None,'native_errors':[]},{'path':directory+'/alias.json','mode':'100644','kind':'ENVELOPE','bytes':701,'sha256':m.sh(b'new-envelope'),'raw_key':key,'payload':payload,'native_errors':[]}])
    if mutation=='added-bound-group-reference':
        e=next(x for x in p['inventory_objects'] if x['kind']=='ENVELOPE' and x['raw_key'] in p['retained_groups']);p['inventory_objects'].append({**e,'path':str(__import__('pathlib').Path(e['path']).parent)+'/new-reference.json'})
    if mutation=='missing-bound-group-member':p['inventory_objects'].remove(next(x for x in p['inventory_objects'] if x['kind']=='ENVELOPE' and x['raw_key'] in p['retained_groups']))
    if mutation=='bound-source-byte-change':next(x for x in p['inventory_objects'] if x['kind']=='ENVELOPE' and x['raw_key'] in p['retained_groups'])['bytes']+=1
    if mutation=='missing-group-binding':p['retained_groups']={}
    if mutation=='filtered-collision-key':p['retained_groups']['0'*64]=p['retained_groups'].pop(next(iter(p['retained_groups'])))
    p['inventory_objects'].sort(key=lambda x:x['path'])
    with pytest.raises(m.Denial):oracle(p)

@pytest.mark.parametrize('mutation',['unrelated-pair-omitted','plain-omitted','same-byte-different-object','partial-errors','extra-error','duplicate-error','wrong-total','wrong-digest'])
def test_full_mixed_inventory_public_assertion_rejects_omissions_and_nonexact_diagnostics(mutation):
    p=mixed();inv=oracle(p);refresh_report(p,inv);child=copy.deepcopy(p['public_child'])
    if mutation=='unrelated-pair-omitted':p['inventory_objects']=[x for x in p['inventory_objects'] if x['path'].split('/')[3]!='HG-299'];p['object_bytes']={x['path']:p['object_bytes'][x['path']] for x in p['inventory_objects']};inv=oracle(p)
    if mutation=='plain-omitted':p['inventory_objects']=[x for x in p['inventory_objects'] if x['kind']!='PLAIN'];p['object_bytes']={x['path']:p['object_bytes'][x['path']] for x in p['inventory_objects']};inv=oracle(p)
    if mutation=='same-byte-different-object':x=next(x for x in p['inventory_objects'] if '/mix-' in x['path'] and x['kind']=='ENVELOPE');raw=bytes.fromhex(p['object_bytes'][x['path']]).replace(b'synthetic',b'SYNTHETIC');p['object_bytes'][x['path']]=raw.hex();x['sha256']=m.sh(raw);inv=oracle(p)
    r=json.loads(child['stdout'])
    if mutation=='partial-errors':r['errors']=r['errors'][:-1]
    if mutation=='extra-error':r['errors'].append('unrelated:native-error')
    if mutation=='duplicate-error':r['errors'].append(r['errors'][0])
    if mutation=='wrong-total':r['stored_bytes']-=1
    if mutation=='wrong-digest':r['inventory_sha256']='0'*64
    child['stdout']=json.dumps(r)
    with pytest.raises(m.Denial):m.fixture_public_assertion(child,inv,p['public_roots'])

def test_inventory_only_without_original_group_bindings_never_grants_preservation_credit():
    p=mixed();inv=m.fixture_inventory_oracle(p['inventory_objects'],p['bodies'],object_bytes=p['object_bytes']);assert len(inv['errors'])==14
    assert inv['preserved_paths']==inv['preserved_bytes']==0
