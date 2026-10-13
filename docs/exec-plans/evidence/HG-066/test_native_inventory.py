'Both native roots/codecs and byte-derived plain duplicate traversal.'
import copy,json,lzma
import pytest
import sequence_model as m
from test_inventory_mix import refresh_report

def inv(p,bound=True):return m.fixture_inventory_oracle(p['inventory_objects'],p['bodies'],p['retained_groups'] if bound else None,p['object_bytes'])
def plain(p,path,raw):m.nf.put_plain(p['inventory_objects'],p['object_bytes'],path,raw);p['inventory_objects'].sort(key=lambda x:x['path'])
def rep(p,owner,root,codec,raw,count=1,stem='ordinary'):
    key=m.sh(raw);m.nf.put_representation(p['inventory_objects'],p['bodies'],p['object_bytes'],f'docs/exec-plans/{root}/{owner}/{stem}',raw,codec,count);p['inventory_objects'].sort(key=lambda x:x['path']);return key

def independently_derive(p):
    prior={};errors=[]
    for x in p['inventory_objects']:
        if x['kind']=='PAYLOAD':continue
        raw=bytes.fromhex(p['bodies'][x['raw_key']]) if x['kind']=='ENVELOPE' else bytes.fromhex(p['object_bytes'][x['path']])
        if len(raw)<16384:continue
        key=m.sh(raw);physical=x['payload'] if x['kind']=='ENVELOPE' else x['path']
        if key in prior and (x['kind']=='PLAIN' or physical!=prior[key]):errors.append(x['path']+':duplicate-bulk:'+prior[key])
        else:prior[key]=physical
    return sorted(set(errors))

@pytest.mark.parametrize('root',['evidence','reviews'])
@pytest.mark.parametrize('codec',['gzip-v1','xz-v1'])
@pytest.mark.parametrize('owner',['HG-201','HG-299'])
def test_actual_ordinary_codecs_and_roots_preserve_unrelated_inventory(root,codec,owner):
    p=m.fixture_multiphase_premise(6);before=inv(p);key=rep(p,owner,root,codec,b'unrelated ordinary actual codec\n'*650,count=2);after=inv(p)
    assert after['files']==before['files']+3 and after['stored_bytes']==sum(x['bytes'] for x in p['inventory_objects']) and after['digest']==m.sh(p['inventory_objects'])
    assert after['errors']==before['errors']==independently_derive(p) and after['preserved_paths']==before['preserved_paths'] and after['preserved_bytes']==before['preserved_bytes']
    refresh_report(p,after);assert m.evaluate_synthetic_sequence(m.fixture_events(p),p)['native_actual_O_to_K']=='NOT_RUN'
    payload=next(x for x in p['inventory_objects'] if x['path'].endswith(key+m.nf.native.CODECS[codec]));assert m.nf.native.decode(bytes.fromhex(p['object_bytes'][payload['path']]),codec,len(bytes.fromhex(p['bodies'][key])))==bytes.fromhex(p['bodies'][key])

@pytest.mark.parametrize('root',['evidence','reviews'])
@pytest.mark.parametrize('size',[2,16383,16384,22000])
def test_independently_bound_unrelated_plain_bytes_are_counted_without_credit(root,size):
    p=m.fixture_multiphase_premise(6);before=inv(p);plain(p,f'docs/exec-plans/{root}/HG-299/unrelated.txt',b'x'*size);after=inv(p)
    assert after['files']==before['files']+1 and after['stored_bytes']==before['stored_bytes']+size and after['digest']!=before['digest']
    assert after['errors']==before['errors']==independently_derive(p) and after['preserved_paths']==before['preserved_paths'] and after['preserved_bytes']==before['preserved_bytes']
    refresh_report(p,after);m.evaluate_synthetic_sequence(m.fixture_events(p),p)

@pytest.mark.parametrize('root',['evidence','reviews'])
@pytest.mark.parametrize('position',['before','after'])
def test_below_cap_plain_copy_enters_native_traversal_and_denies_all_custody(root,position):
    p=m.fixture_multiphase_premise(6)
    if root=='reviews':
        key=next(iter(p['retained_groups']));raw=bytes.fromhex(p['bodies'][key]);p['inventory_objects']=[x for x in p['inventory_objects'] if x['kind']=='PLAIN'];p['object_bytes']={x['path']:p['object_bytes'][x['path']] for x in p['inventory_objects']}
        for owner,count in [('HG-201',2),('HG-202',4)]+[(f'HG-{n}',2) for n in range(203,208)]:rep(p,owner,root,'gzip-v1',raw,count,stem='retained')
        p['retained_groups']={key:m.fixture_group_binding(p['inventory_objects'],key)}
    baseline=inv(p);raw=bytes.fromhex(p['bodies'][next(iter(p['retained_groups']))]);owner='HG-100' if position=='before' else 'HG-999';path=f'docs/exec-plans/{root}/{owner}/plain-copy.txt';plain(p,path,raw)
    assert len(raw)<262144;derived=inv(p,False);assert derived['errors']==independently_derive(p) and len(derived['errors'])>len(baseline['errors'])
    assert len(derived['errors'])==(16 if position=='before' else 15)
    assert derived['preserved_paths']==derived['preserved_bytes']==0
    with pytest.raises(m.Denial,match='PLAIN_BULK_COPY'):inv(p)
    # Even exact byte-derived extra diagnostics cannot qualify as the known
    # original retained denial when its custody groups are ineligible.
    child=copy.deepcopy(p['public_child']);r=json.loads(child['stdout']);r.update(files=derived['files'],stored_bytes=derived['stored_bytes'],inventory_sha256=derived['digest'],errors=derived['errors']);child['stdout']=json.dumps(r)
    with pytest.raises(m.Denial,match='UNBOUND_COLLISION_REGRESSION'):m.fixture_public_assertion(child,derived,p['public_roots'])

@pytest.mark.parametrize('pair',[('evidence','evidence'),('reviews','reviews'),('evidence','reviews')])
def test_plain_plain_duplicates_are_exact_and_cannot_be_retained(pair):
    p=m.fixture_multiphase_premise(6);raw=b'new ordinary duplicate plain\n'*700
    for n,root in enumerate(pair):plain(p,f'docs/exec-plans/{root}/HG-299/plain-{n}.txt',raw)
    derived=inv(p,False);assert derived['errors']==independently_derive(p) and len(derived['errors'])==15
    with pytest.raises(m.Denial,match='UNEXPECTED_OR_MISSING_COLLISION_GROUP'):inv(p)

@pytest.mark.parametrize('codecs',[('gzip-v1','xz-v1'),('xz-v1','gzip-v1')])
@pytest.mark.parametrize('roots',[('evidence','reviews'),('reviews','evidence')])
def test_mixed_declared_codecs_one_payload_per_owner_complete_group(codecs,roots):
    p=m.fixture_multiphase_premise(6);before=inv(p);raw=b'additional complete mixed codec raw\n'*600
    for owner,codec,root in zip(['HG-201','HG-299'],codecs,roots):key=rep(p,owner,root,codec,raw,count=2,stem='new-retained')
    with pytest.raises(m.Denial):inv(p)
    p['retained_groups'][key]=m.fixture_group_binding(p['inventory_objects'],key);after=inv(p)
    assert after['errors']==independently_derive(p) and len(after['errors'])==len(before['errors'])+2 and after['preserved_paths']==before['preserved_paths']+6
    refresh_report(p,after);m.evaluate_synthetic_sequence(m.fixture_events(p),p)

@pytest.mark.parametrize('mutation',['codec-unknown','codec-marker-mismatch','codec-payload-mismatch','wrong-extension','gzip-trailing','gzip-truncated','xz-trailing','xz-truncated','xz-wrong-check','nested-envelope','plain-reserved-wrapper','plain-embedded-raw','plain-full-diff','duplicate-json-key','invalid-utf16-envelope','missing-plain-bytes','substitute-plain-bytes','payload-raw-relabel','nonregular','root-alias','owner-alias','unsafe-path','same-owner-double-codec','same-owner-double-root','payload-alias'])
def test_independent_native_representation_and_byte_negatives(mutation):
    p=m.fixture_multiphase_premise(6);codec='xz-v1' if mutation.startswith('xz-') else 'gzip-v1';raw=b'ordinary unrelated native negative\n'*600
    key=rep(p,'HG-299','reviews',codec,raw);e=next(x for x in p['inventory_objects'] if x['raw_key']==key);q=next(x for x in p['inventory_objects'] if x['path']==e['payload']);meta=json.loads(bytes.fromhex(p['object_bytes'][e['path']]))
    def physical(x,data):p['object_bytes'][x['path']]=data.hex();x.update(bytes=len(data),sha256=m.sh(data))
    if mutation=='codec-unknown':e['codec']='bzip-v1'
    if mutation=='codec-marker-mismatch':meta['kineticloop_evidence']='xz-v1';physical(e,json.dumps(meta).encode())
    if mutation=='codec-payload-mismatch':q['codec']='xz-v1'
    if mutation=='wrong-extension':e['payload']=e['payload'].replace('.gz','.xz')
    if mutation in ['gzip-trailing','gzip-truncated','xz-trailing','xz-truncated','xz-wrong-check']:
        data=bytes.fromhex(p['object_bytes'][q['path']]);data=data+b'junk' if mutation.endswith('trailing') else data[:-5]
        if mutation=='xz-wrong-check':data=lzma.compress(raw,format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC32)
        physical(q,data);meta.update(stored_bytes=len(data),stored_sha256=m.sh(data));physical(e,json.dumps(meta).encode())
    if mutation=='nested-envelope':
        body=json.dumps(meta).encode();physical(q,m.nf.native.encode(body,codec));meta.update(stored_bytes=q['bytes'],stored_sha256=q['sha256'],raw_bytes=len(body));physical(e,json.dumps(meta).encode())
    if mutation.startswith('plain-'):
        body={'plain-reserved-wrapper':b'{\x22wrapped\x22:{\x22kineticloop_evidence\x22:\x22gzip-v1\x22}}','plain-embedded-raw':b'{\x22raw_utf8\x22:\x22bulk\x22}','plain-full-diff':b'diff --git a/x b/x\n'}[mutation];plain(p,'docs/exec-plans/reviews/HG-299/plain.json',body)
    if mutation=='duplicate-json-key':physical(e,json.dumps(meta).encode()[:-1]+b',\x22payload\x22:\x22duplicate\x22}')
    if mutation=='invalid-utf16-envelope':physical(e,json.dumps(meta).encode('utf-16')[:-1])
    if mutation in ['missing-plain-bytes','substitute-plain-bytes']:
        path='docs/exec-plans/reviews/HG-299/plain.txt';plain(p,path,b'ordinary bound\n')
        if mutation=='missing-plain-bytes':p['object_bytes'].pop(path)
        else:p['object_bytes'][path]=b'replaced bound\n'.hex()
    if mutation=='payload-raw-relabel':q['kind']='PLAIN';q['codec']=None
    if mutation=='nonregular':q['mode']='120000'
    if mutation in ['root-alias','owner-alias','unsafe-path']:
        e['path']=e['path'].replace('reviews','other') if mutation=='root-alias' else e['path'].replace('HG-299','OTHER') if mutation=='owner-alias' else e['path'].replace('/ordinary/','/../ordinary/')
    if mutation in ['same-owner-double-codec','same-owner-double-root']:
        oldkey=next(iter(p['retained_groups']));body=bytes.fromhex(p['bodies'][oldkey]);rep(p,'HG-201','reviews','xz-v1' if mutation.endswith('codec') else 'gzip-v1',body)
    if mutation=='payload-alias':p['inventory_objects'].append({**copy.deepcopy(q),'path':q['path']+'-alias'})
    p['inventory_objects'].sort(key=lambda x:x['path'])
    with pytest.raises(m.Denial):inv(p)

@pytest.mark.parametrize('mutation',['omit-review-plain','omit-xz-pair','change-unrelated-plain','missing-error','extra-error','old-digest'])
def test_exact_public_diagnostics_and_inventory_cover_all_native_forms(mutation):
    p=m.fixture_multiphase_premise(6);key=rep(p,'HG-299','reviews','xz-v1',b'ordinary unrelated actual xz\n'*700);plain(p,'docs/exec-plans/reviews/HG-299/ordinary.txt',b'ordinary independent plain\n');baseline=inv(p);refresh_report(p,baseline);child=copy.deepcopy(p['public_child']);report=json.loads(child['stdout'])
    if mutation=='omit-review-plain':p['inventory_objects']=[x for x in p['inventory_objects'] if x['kind']!='PLAIN']
    if mutation=='omit-xz-pair':p['inventory_objects']=[x for x in p['inventory_objects'] if x['path'].split('/')[3]!='HG-299' or x['kind']=='PLAIN']
    if mutation in ['omit-review-plain','omit-xz-pair']:p['object_bytes']={x['path']:p['object_bytes'][x['path']] for x in p['inventory_objects']}
    if mutation=='change-unrelated-plain':
        x=next(x for x in p['inventory_objects'] if x['path'].endswith('ordinary.txt'));data=b'ordinary independent PLAIN\n';p['object_bytes'][x['path']]=data.hex();x.update(bytes=len(data),sha256=m.sh(data))
    if mutation=='missing-error':report['errors']=report['errors'][:-1]
    if mutation=='extra-error':report['errors'].append('extra:duplicate-bulk:unexpected')
    if mutation=='old-digest':report['inventory_sha256']='0'*64
    child['stdout']=json.dumps(report)
    with pytest.raises(m.Denial):m.fixture_public_assertion(child,inv(p),p['public_roots'])


@pytest.mark.parametrize('encoding',['utf-8','utf-16','utf-32'])
@pytest.mark.parametrize('codec',['gzip-v1','xz-v1'])
def test_valid_native_envelope_encodings_are_classified_without_opaque_fallback(encoding,codec):
    p=m.fixture_multiphase_premise(6);before=inv(p);key=rep(p,'HG-299','reviews',codec,b'ordinary encoding classifier fixture\n'*600)
    e=next(x for x in p['inventory_objects'] if x['raw_key']==key);meta=json.loads(bytes.fromhex(p['object_bytes'][e['path']]));data=json.dumps(meta).encode(encoding);p['object_bytes'][e['path']]=data.hex();e.update(bytes=len(data),sha256=m.sh(data));after=inv(p)
    assert after['errors']==before['errors']==independently_derive(p) and after['preserved_paths']==before['preserved_paths']
    assert after['stored_bytes']==sum(x['bytes'] for x in p['inventory_objects'])
