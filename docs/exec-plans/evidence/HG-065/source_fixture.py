"""Load independently bound immutable bytes for the author model only.

No host credential is constructed. Actual originals retain exact source hashes;
neutral fixtures below are explicitly synthetic and have no original authority.
"""
import hashlib
import json
from portable_support import git_source
from pathlib import Path


def original_sources(root):
    root=Path(root)
    # The complete prior source manifest is immutable. Its tuples predate this R2
    # predicate and bind independently observed original records and schemas.
    manifest=json.loads((root/'ORIGINAL_SOURCE_BINDINGS.json').read_bytes())
    result={}
    for entry in manifest['inputs']:
        origin=entry['origin']
        if origin['kind']!='IMMUTABLE_GIT_BLOB':continue
        data=git_source(entry)
        assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256']
        binding={'path':origin['path'],'mode':origin.get('mode','100644'),'blob':origin['blob'],
                 'bytes':len(data),'sha256':entry['sha256']}
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==binding['blob']
        key=(origin['revision'],origin['path'])
        value={'object':binding,'content':data}
        if key in result:assert result[key]==value
        result[key]=value
    return result


def neutral_value(value):
    if type(value) is dict:return {neutral_value(k):neutral_value(v) for k,v in value.items()}
    if type(value) is list:return [neutral_value(v) for v in value]
    if type(value) is str:return value.replace('HG-058','HG-201').replace('HG-059','HG-202')
    return value


def neutral_sources_and_proof(proof,sources):
    """Explicit synthetic data; native-read tags are premises, never fresh reads."""
    import yaml
    p=neutral_value(proof);out={}
    for key,source in sources.items():
        newkey=neutral_value(list(key));obj=neutral_value(source['object'])
        if ('/docs/exec-plans/' in '/'+obj['path'] and '/governance/' in obj['path']) or obj['path'].endswith('COMPACT_REENCODING.json'):
            record=yaml.safe_load(source['content'])
            data=(json.dumps(neutral_value(record),separators=(',',':'))+'\n').encode()
            obj.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                       blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest())
        else:data=source['content']
        out[tuple(newkey)]={'object':obj,'content':data}
    for member in p['members']:
        d=member['declaration'];d['object']=out[(d['revision'],d['object']['path'])]['object']
    m=p['map_binding'];m['object']=out[(p['original_selected'],m['object']['path'])]['object']
    return p,out
