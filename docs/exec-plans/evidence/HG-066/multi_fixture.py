'Immutable original inputs and explicitly synthetic neutral observations only.'
from pathlib import Path
import json,hashlib,copy
from data_io import read_json
D=Path(__file__).resolve().parent

def sources():
 rows=json.loads((D/'ORIGINAL_SOURCE_BINDINGS.json').read_bytes())['sources'];out={}
 for x in rows:
  if not x['snapshot']:continue
  from portable_sources import original_bytes
  b=original_bytes(x);obj=x['object'];assert len(b)==obj['bytes'] and hashlib.sha256(b).hexdigest()==obj['sha256'];assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==obj['blob'];out[(x['revision'],obj['path'])]={'object':obj,'content':b}
 return out

def root_states(proof,observation=None):
 observation=observation or read_json('CURRENT_GROUP_OBSERVATION.json')
 states={}
 for name,rev in [('selected',proof['original_selected']),('protected',proof['protected_base'])]:
  refs=set(observation['root_members'][rev]);present=set(refs)
  for m in proof['members']:
   if m['envelope']['path'] in refs:present.add(m['payload']['path'])
  states[name]={p['path']:p if p['path'] in present else None for p in proof['physical_paths']}
 return states

def neutral(proof,source,states):
 'Change all seven owners coherently; source originals remain synthetic only.'
 import yaml
 owners=sorted({m['declaration']['identity'].split('/')[-1] for m in proof['members']});mapping={o:f'HG-{201+i}' for i,o in enumerate(owners)}
 def change(v):
  if type(v) is dict:return {change(k):change(x) for k,x in v.items()}
  if type(v) is list:return [change(x) for x in v]
  if type(v) is str:
   for a,b in mapping.items():v=v.replace(a,b)
  return v
 p=change(copy.deepcopy(proof));r=change(copy.deepcopy(states));out={}
 for (rev,path),s in source.items():
  obj=change(s['object']);data=s['content']
  if path.endswith('.yaml') or path.endswith('COMPACT_REENCODING.json'):
   data=(json.dumps(change(yaml.safe_load(data)),separators=(',',':'))+'\n').encode();obj.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest())
  out[(rev,change(path))]={'object':obj,'content':data}
 for m in p['members']:
  dec=m['declaration'];dec['object']=out[(dec['revision'],dec['object']['path'])]['object']
 p['map_binding']['object']=out[(p['original_selected'],p['map_binding']['object']['path'])]['object']
 return p,out,r
