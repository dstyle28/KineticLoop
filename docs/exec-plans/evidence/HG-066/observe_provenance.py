'Exact target-group original record and introduction/delivery edges only.\nNo historical scripts or whole native audits. Original objects are inert data.\n'
from pathlib import Path
import hashlib,json,subprocess,time,importlib.util,copy
import yaml,jsonschema
import os
from data_io import read_json
D=Path(__file__).resolve().parent;R=D.parents[3];P='3768c1b4366677934cb952ef808343edcee4e438';Q='3965cac382d333bd97f6c67fec8ecbe805b5932f';O='9700a1b95d05c856897f74f125cfdf6fb3f6e646'
O_DIR=Path(os.environ.get('MULTI_PREPARATION_OUTPUT',str(D)));O_DIR.mkdir(parents=True,exist_ok=True)
LIMITS=json.loads((D/'BUDGETS.json').read_bytes())['incorporated_original']['incremental_work_limits'];used={k:0 for k in LIMITS};start=time.monotonic_ns();commands=[];sources={};trees={};objects={};parents={};sourcepins=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def charge(k,n):
 used[k]+=n;assert used[k]<=LIMITS[k],(k,used[k]);assert time.monotonic_ns()-start<=120000000000

def git(*args):
 charge('git_operations',1);t=time.monotonic_ns();p=subprocess.run(['git',*args],cwd=R,capture_output=True,timeout=10);charge('git_output_bytes',len(p.stdout)+len(p.stderr));commands.append({'argv':['git',*args],'exit_code':p.returncode,'stdout_bytes':len(p.stdout),'stdout_sha256':sha(p.stdout),'stderr_bytes':len(p.stderr),'stderr_sha256':sha(p.stderr),'elapsed_ns':time.monotonic_ns()-t});assert p.returncode==0,(args,p.stderr);return p.stdout

def tree(rev,paths):
 key=(rev,tuple(sorted(paths)))
 if key not in trees:
  vals={}
  for row in git('ls-tree','-l','-z',rev,'--',*sorted(paths)).split(b'\0'):
   if not row:continue
   fields,path=row.split(b'\t');mode,kind,oid,size=fields.split();charge('path_entries',1);assert kind==b'blob' and mode in (b'100644',b'100755')
   vals[path.decode()]={'path':path.decode(),'mode':mode.decode(),'blob':oid.decode(),'bytes':int(size)}
  trees[key]=vals
 return trees[key]

def obj(rev,path,*,snapshot=False):
 key=(rev,path)
 if key not in objects:
  value=tree(rev,[path])[path];assert value['bytes']<=262144;b=git('cat-file','blob',value['blob']);assert len(b)==value['bytes'];value=dict(value,sha256=sha(b));objects[key]=(value,b)
  sourcepins.append({'revision':rev,'object':value,'snapshot':None})
 if snapshot:
  value,b=objects[key];name='inputs/original/'+rev+'/'+path;t=O_DIR/name;t.parent.mkdir(parents=True,exist_ok=True);assert not t.exists() or t.read_bytes()==b
  if not t.exists():t.write_bytes(b)
  sources[key]={'object':value,'content':b};next(x for x in sourcepins if x['revision']==rev and x['object']['path']==path)['snapshot']=name
 return objects[key]

obs=json.loads((O_DIR/'CURRENT_GROUP_OBSERVATION.json').read_bytes()) if os.environ.get('MULTI_PREPARATION_OUTPUT') else read_json('CURRENT_GROUP_OBSERVATION.json');members=obs['members'];owners=obs['owners'];protected_rows=git('rev-list','--first-parent','--parents',O+'..'+P).decode().splitlines();deliveries={};declarations={}
for owner in owners:
 path='docs/exec-plans/governance/'+owner+'.yaml'
 if owner=='HG-058':f=Q
 else:
  ds=[]
  for row in protected_rows:
   fields=row.split()
   if len(fields)!=3:continue
   d,b,j=fields
   if path in tree(j,[path]) and path not in tree(b,[path]):ds.append((d,b,j))
  assert len(ds)==1,(owner,ds);d,b,j=ds[0]
  # Exact final declaration identity retained through strictly own review suffix;
  # the contiguous same-blob segment at J begins at original result F.
  expected,_=obj(j,path);f=j
  while True:
   ps=git('rev-list','--parents','-n','1',f).decode().split()[1:];parents[f]=ps
   assert len(ps)==1,(owner,'nonlinear_original_record_suffix',f)
   prev=tree(ps[0],[path]).get(path)
   if prev is None or prev['blob']!=expected['blob']:break
   f=ps[0]
  git('merge-base','--is-ancestor',f,j);git('merge-base','--is-ancestor',d,P)
  deliveries[owner]={'commit':d,'parents':[b,j],'original_record':f,'foreign_owner':owner,'relation_observations':['ORIGINAL_RECORD_TO_PR_HEAD','DELIVERY_TO_PROTECTED','CORRECT_PARENT_ORIENTATION']}
 binding,data=obj(f,path,snapshot=True);record=yaml.safe_load(data);schema_binding,schema=obj(f,'HARNESS_CHANGE.schema.json',snapshot=True);jsonschema.validate(record,json.loads(schema));assert record['change_identity']=='harness-governance-v0.1/'+owner
 refs={}
 for field in ('files_changed','evidence_refs'):
  for n,ref in enumerate(record.get(field,[])):refs.setdefault(ref,[]).append(field+'/'+str(n))
 for n,c in enumerate(record['checks_run']):refs.setdefault(c['evidence_ref'],[]).append('checks_run/'+str(n)+'/evidence_ref')
 declarations[owner]=(f,binding,refs)
 for m in [m for m in members if m['envelope']['path'].split('/')[3]==owner]:
  assert m['envelope']['path'] in refs,(owner,m['envelope']['path'],'missing_original_declaration_member')
  if owner!='HG-058':assert record['base_commit']==deliveries[owner]['parents'][0]

# Discover first introduction along only the bound declaration's first-parent chain;
# native current endpoints' exact original objects must already exist at F.
introductions={}
for member in members:
 owner=member['envelope']['path'].split('/')[3];f=declarations[owner][0]
 for binding in [member['envelope'],member['payload']]:
  path=binding['path']
  if path in introductions:continue
  assert obj(f,path)[0]==binding,(owner,path,'original_record_object_changed');cursor=f
  while True:
   ps=git('rev-list','--parents','-n','1',cursor).decode().split()[1:];parents[cursor]=ps
   assert len(ps)==1,(path,'unexpected_merge_before_introduction')
   before=tree(ps[0],[path]).get(path)
   if before is None:break
   assert before['blob']==binding['blob'] and before['mode']==binding['mode'],(path,'intermediate_changed_object')
   cursor=ps[0]
  introductions[path]=cursor

histories={}
for binding in obs['physical_paths']:
 path=binding['path'];owner=path.split('/')[3];intro=introductions[path]
 endpoints=[Q] if owner=='HG-058' else [P]
 # Q is an additional retained endpoint only for foreign deliveries already there.
 if owner!='HG-058' and path in tree(Q,[path]):endpoints.append(Q)
 nodes={};edges=set();rows={}
 for end in endpoints:
  git('merge-base','--is-ancestor',intro,end)
  data=[r.split() for r in git('rev-list','--ancestry-path','--parents',intro+'..'+end).decode().splitlines()]
  data.append(git('rev-list','--parents','-n','1',intro).decode().split())
  charge('commits',len(data));charge('parent_edges',sum(len(x)-1 for x in data))
  for row in data:
   child,*ps=row
   if child in rows:assert rows[child]==ps
   rows[child]=ps
   if child in parents:assert parents[child]==ps
   parents[child]=ps;edges.update((p,child) for p in ps)
 for rev in sorted(set(rows)|{p for p,c in edges}):
  state=tree(rev,[path]).get(path)
  if state is not None:
   assert state=={k:binding[k] for k in ('path','mode','blob','bytes')},(path,rev,'history_mutation');state=binding
  nodes[rev]=state
 imports={}
 for p,c in sorted(edges):
  if nodes[p] is None and nodes[c] is not None and c!=intro:
   ps=rows[c];assert owner!='HG-058' and len(ps)==2 and nodes[ps[0]] is None and nodes[ps[1]]==binding
   delivery=deliveries[owner]['commit'];git('merge-base','--is-ancestor',delivery,c)
   if c!=delivery:git('merge-base','--is-ancestor',delivery,ps[1])
   imports[c]=ps
 histories[path]={'path':path,'original':binding,'nodes':nodes,'edges':[list(x) for x in sorted(edges)],'imports':imports,'parents':rows,'boundaries':sorted(set(nodes)-set(rows))}

proofmembers=[]
for m in members:
 owner=m['envelope']['path'].split('/')[3];f,binding,refs=declarations[owner];e=m['envelope'];p=m['payload'];env=m['metadata']
 proofmembers.append({'envelope':e,'payload':p,'raw_sha256':obs['raw_sha256'],'raw_bytes':obs['raw_bytes'],'declaration':{'identity':'harness-governance-v0.1/'+owner,'revision':f,'object':binding,'pointers':refs[e['path']],'ref':e['path'],'authority_chain':'PROTECTED_PACKET_FROZEN_ORIGINAL' if owner=='HG-058' else 'NORMAL_FOREIGN_DELIVERY_ORIGINAL'},'introduction':introductions[e['path']],'history':histories[e['path']],'payload_introduction':introductions[p['path']],'payload_history':histories[p['path']],'protected_state':'ABSENT' if owner=='HG-058' else 'EXACT_ORIGINAL','representation':{'codec':env['kineticloop_evidence'],'raw_sha256':obs['raw_sha256'],'raw_bytes':obs['raw_bytes'],'stored_sha256':p['sha256'],'stored_bytes':p['bytes'],'raw_bytes_equal':'OBSERVED_EXACT_BYTES','native_read_observation':'OBSERVED_NATIVE_CODEC_AND_CLASSIFIER_RETURNED_ORDINARY'}})
old=json.loads((R/'docs/exec-plans/evidence/HG-065/ACTUAL_CUSTODY_PROOF.json').read_bytes());mapping=old['map_binding']
for rev in [Q,mapping['admission']]:obj(rev,mapping['object']['path'],snapshot=True)
proof={'selected_identity':'harness-governance-v0.1/HG-058','original_base':O,'protected_base':P,'original_selected':Q,'members':proofmembers,'physical_paths':obs['physical_paths'],'inventory_intersection':sorted(x['path'] for x in obs['physical_paths']),'deliveries':[deliveries[o] for o in sorted(deliveries)],'map_binding':mapping}
(O_DIR/'CURRENT_ROOT_UNION_PROOF.json').write_text(json.dumps(proof,separators=(',',':'))+'\n')
(O_DIR/'ORIGINAL_SOURCE_BINDINGS.json').write_text(json.dumps({'sources':sourcepins},separators=(',',':'))+'\n')
(O_DIR/'PROVENANCE_OBSERVATION.json').write_text(json.dumps({'status':'BOUNDED_ROOT_UNION_PROVENANCE_OBSERVED','owners':owners,'deliveries':proof['deliveries'],'introductions':introductions,'shared_parent_rows':parents,'commands':commands,'consumed':used,'elapsed_ns':time.monotonic_ns()-start,'actual_head_or_import':'NOT_RUN','native_full_audit':'NOT_RUN','historical_execution':'UNVERIFIED'},separators=(',',':'))+'\n')
print(json.dumps({'owners':len(owners),'members':len(proofmembers),'paths':len(histories),'git_operations':used['git_operations'],'elapsed_ns':time.monotonic_ns()-start,'native_full_audit':'NOT_RUN'}))
