'Pinned native ordinary codec/classifier checks over synthetic immutable bytes.\n\nGit commit resolution/ancestry are SYNTHETIC assumptions, never history evidence.\nNo filesystem reader, Git write, archival audit, controller or installed call occurs.\n'
from pathlib import Path
import importlib.util,hashlib,json,re
D=Path(__file__).resolve().parent;R=D.parents[3]
PIN=json.loads((D/'NATIVE_FIXTURE_SOURCE_PIN.json').read_bytes());source=R/PIN['path']
assert hashlib.sha256(source.read_bytes()).hexdigest()==PIN['sha256']
spec=importlib.util.spec_from_file_location('hg058_r3_native_synthetic',source);native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)

def field_row(path,kind,data,raw_key=None,payload=None,codec=None):
 return {'path':path,'mode':'100644','kind':kind,'bytes':len(data),'sha256':native.digest(data),'raw_key':raw_key,'payload':payload,'codec':codec,'native_errors':[]}

def put_plain(objects,object_bytes,path,raw):
 object_bytes[path]=raw.hex();row=field_row(path,'PLAIN',raw);objects.append(row);return row

def put_representation(objects,bodies,object_bytes,directory,raw,codec='gzip-v1',references=1,stem='capture'):
 assert codec in native.CODECS
 key=native.digest(raw);bodies[key]=raw.hex();stored=native.encode(raw,codec);payload=directory+'/'+key+native.CODECS[codec]
 objects.append(field_row(payload,'PAYLOAD',stored,codec=codec));object_bytes[payload]=stored.hex()
 for n in range(references):
  path=directory+f'/{stem}-{n}.json';meta={native.MARKER:codec,'payload':payload,'stored_sha256':native.digest(stored),'stored_bytes':len(stored),'raw_sha256':key,'raw_bytes':len(raw),'tested_commit':'6'*40,'command':'synthetic independently bound ordinary bytes','exit_code':0,'timestamp':None,'test_counts':{}}
  data=json.dumps(meta,sort_keys=True,separators=(',',':')).encode();objects.append(field_row(path,'ENVELOPE',data,key,payload,codec));object_bytes[path]=data.hex()
 return key

def read_synthetic(path,objects,object_bytes):
 'Real pinned native.read, exact in-memory blobs; simulated Git premises only.'
 index={x['path']:x for x in objects}
 def blob_at(root,name,revision,limit):
  if name not in index:raise ValueError('evidence-missing')
  row=index[name]
  if row['mode'] not in ['100644','100755']:raise ValueError('evidence-regular-blob')
  data=bytes.fromhex(object_bytes[name])
  if limit is not None and len(data)>limit:raise ValueError('evidence-size')
  return data
 def git(root,*args):
  if args[:3]==('rev-parse','--verify','--end-of-options') and len(args)==4:
   rev=args[-1].removesuffix('^{commit}')
   if re.fullmatch('[0-9a-f]{40}',rev):return (rev+'\n').encode()
  if len(args)==4 and args[:2]==('merge-base','--is-ancestor') and all(re.fullmatch('[0-9a-f]{40}',v) for v in args[2:]):return b''
  raise ValueError('UNMODELED_SYNTHETIC_GIT_CALL')
 oldgit,oldblob=native.git,native._blob_at_commit
 try:
  native.git=git;native._blob_at_commit=blob_at
  return native.read(Path('/private/tmp/synthetic-no-filesystem'),path,'f'*40)
 finally:native.git,native._blob_at_commit=oldgit,oldblob
