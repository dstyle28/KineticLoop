'Bounded target-group metadata closure at two fixed roots; not native audit.\nEvery changed native evidence path is enumerated. Other raw bodies/native errors\nare not certified. An actual K/H installed operation must repeat full native work.\n'
from pathlib import Path
import hashlib,json,subprocess,time,importlib.util,re,os
D=Path(__file__).resolve().parent;R=D.parents[3];P='3768c1b4366677934cb952ef808343edcee4e438';Q='3965cac382d333bd97f6c67fec8ecbe805b5932f';O='9700a1b95d05c856897f74f125cfdf6fb3f6e646';KEY='aa44ef95cbd9dfea6a741f359cb2c8884c51e7d9c1909eed35d63d526de16280'
O_DIR=Path(os.environ.get('MULTI_PREPARATION_OUTPUT',str(D)));O_DIR.mkdir(parents=True,exist_ok=True)
LIMITS=json.loads((D/'BUDGETS.json').read_bytes())['incorporated_original']['incremental_work_limits'];used={k:0 for k in LIMITS};start=time.monotonic_ns();commands=[];cache={};metadata=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def charge(k,n):
 used[k]+=n;assert used[k]<=LIMITS[k],(k,used[k]);assert time.monotonic_ns()-start<=120000000000

def git(*args):
 charge('git_operations',1);t=time.monotonic_ns();p=subprocess.run(['git',*args],cwd=R,capture_output=True,timeout=10);charge('git_output_bytes',len(p.stdout)+len(p.stderr));commands.append({'argv':['git',*args],'exit_code':p.returncode,'stdout_bytes':len(p.stdout),'stdout_sha256':sha(p.stdout),'stderr_bytes':len(p.stderr),'stderr_sha256':sha(p.stderr),'elapsed_ns':time.monotonic_ns()-t});assert p.returncode==0,args;return p.stdout

def blob(obj):
 oid=obj['blob']
 if oid not in cache:
  b=git('cat-file','blob',oid);assert len(b)==obj['bytes'];charge('blob_cache_objects',1);charge('blob_cache_bytes',len(b));cache[oid]=b
 return cache[oid]
source=R/'tools/harness/compact_evidence.py';assert source.read_bytes()==git('show',P+':tools/harness/compact_evidence.py')
s=importlib.util.spec_from_file_location('current_protected_group_codec',source);native=importlib.util.module_from_spec(s);s.loader.exec_module(native);native.git=lambda root,*args:git(*args)
alltrees={};inventories={};matched={};coverage=[];raw_original=None
for rev in [Q,P]:
 paths=git('diff','--no-renames','--name-only','--diff-filter=ACMRT','-z',O,rev,'--').decode().split('\0')[:-1]
 paths=sorted(p for p in paths if re.match(r'^docs/exec-plans/(?:evidence|reviews)/(?:HG|KL)-[0-9]{3}[A-Z]?/',p));charge('path_entries',len(paths));charge('paths',len(set(paths)-set(p for r in inventories.values() for p in r)))
 entries={}
 for line in git('ls-tree','-rl','-z',rev,'--','docs/exec-plans/evidence','docs/exec-plans/reviews').split(b'\0'):
  if not line:continue
  fields,path=line.split(b'\t');mode,kind,oid,size=fields.split();name=path.decode()
  if name in paths:
   assert kind==b'blob' and mode in (b'100644',b'100755');entries[name]={'path':name,'mode':mode.decode(),'blob':oid.decode(),'bytes':int(size)}
 assert set(entries)==set(paths);alltrees[rev]=entries;inventories[rev]=paths
 rows=[];members=[]
 for path in paths:
  obj=entries[path];rec={'object':obj,'inspection':'BINARY_OR_OVERSIZE_NOT_PARSED_AS_PLAIN'}
  if not path.endswith(('.gz','.xz')):
   assert obj['bytes']<=262144,(path,obj['bytes']);b=git('cat-file','blob',obj['blob']);assert len(b)==obj['bytes'];rec['sha256']=sha(b)
   try:value=json.loads(b,object_pairs_hook=native.unique)
   except (ValueError,UnicodeError):value=None
   rec['inspection']='PLAIN_NOT_ORDINARY_ENVELOPE'
   if type(value) is dict and value.get('kineticloop_evidence') in ('gzip-v1','xz-v1'):
    rec['inspection']='ORDINARY_ENVELOPE_METADATA';rec['declared_raw_sha256']=value.get('raw_sha256')
    if value.get('raw_sha256')==KEY:
     env=native.envelope(b);assert env is not None;raw=native.read(R,path,rev);charge('decoded_bytes',len(raw));charge('comparison_bytes',2*len(raw));assert len(raw)==26433 and sha(raw)==KEY
     if raw_original is None:raw_original=raw
     assert raw==raw_original;charge('captures',1)
     payload=entries[env['payload']];stored=blob(payload);assert sha(stored)==env['stored_sha256']
     member={'revision':rev,'envelope':dict(obj,sha256=sha(b)),'payload':dict(payload,sha256=sha(stored)),'metadata':env,'raw_bytes_equal':'OBSERVED_EXACT_BYTES','native_read':'OBSERVED_CURRENT_P_NATIVE_ORDINARY_RETURN'};members.append(member)
   if sha(b)==KEY:raise ValueError('TARGET_PLAIN_BULK_COPY_DENIES_GROUP:'+path)
  rows.append(rec)
 matched[rev]=members;coverage.append({'revision':rev,'native_changed_path_count':len(paths),'changed_paths_sha256':sha(json.dumps(paths).encode()),'rows':rows})
union={}
for rev,members in matched.items():
 for m in members:
  path=m['envelope']['path']
  if path in union:assert union[path]['envelope']==m['envelope'] and union[path]['payload']==m['payload']
  else:union[path]=m
payloads={m['payload']['path']:m['payload'] for m in union.values()};aliases=[]
known_oids={p['blob'] for p in payloads.values()}
for rev,entries in alltrees.items():
 for path,obj in entries.items():
  if obj['blob'] in known_oids and path not in payloads:aliases.append({'revision':rev,'object':obj,'reason':'SAME_STORED_BODY_UNREFERENCED_ALIAS'})
assert not aliases,aliases
owners=sorted({m['envelope']['path'].split('/')[3] for m in union.values()});assert len(owners)>=3
charge('groups',1);charge('output_bytes',0)
out={'status':'BOUNDED_DECLARED_RAW_GROUP_ROOT_UNION_OBSERVED','roots':[Q,P],'original_base':O,'raw_sha256':KEY,'raw_bytes':26433,'members':sorted(union.values(),key=lambda x:x['envelope']['path']),'root_members':{r:[m['envelope']['path'] for m in a] for r,a in matched.items()},'physical_paths':sorted([m['envelope'] for m in union.values()]+list(payloads.values()),key=lambda x:x['path']),'owners':owners,'stored_payload_aliases':aliases,'targeted_metadata_inventory_complete_at_fixed_roots':True,'other_raw_codec_and_classifier_guards':'NOT_RUN','actual_K_or_H_inventory':'NOT_RUN','full_native_audit':'NOT_RUN','execution_attribution':'UNVERIFIED','acceptance_eligible':False,'execution_reuse':False,'consumed':used,'elapsed_ns':time.monotonic_ns()-start,'commands':commands,'coverage':coverage}
encoded=(json.dumps(out,separators=(',',':'))+'\n').encode();charge('output_bytes',len(encoded));out['consumed']=used;out['elapsed_ns']=time.monotonic_ns()-start
(O_DIR/'CURRENT_GROUP_OBSERVATION.json').write_text(json.dumps(out,separators=(',',':'))+'\n');print(json.dumps({'owners':owners,'envelopes':len(union),'payloads':len(payloads),'physical_paths':len(out['physical_paths']),'physical_bytes':sum(x['bytes'] for x in out['physical_paths']),'changed_path_counts':{r:len(a) for r,a in inventories.items()},'git_operations':used['git_operations'],'elapsed_ns':out['elapsed_ns'],'full_native_audit':'NOT_RUN'}))
if __name__=='__main__':pass
