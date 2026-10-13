'Exact original normal-delivery review record/suffix bindings, data only.\nNo historical scripts/classifier/full audit is executed or certified.\n'
from pathlib import Path
import json,hashlib,subprocess,time,os
import jsonschema
from data_io import read_json
D=Path(__file__).resolve().parent;OUT=Path(os.environ.get('MULTI_PREPARATION_OUTPUT',str(D)));R=D.parents[3];P='3768c1b4366677934cb952ef808343edcee4e438';rows=[];commands=[];start=time.monotonic_ns()
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):
 t=time.monotonic_ns();p=subprocess.run(['git',*args],cwd=R,capture_output=True,timeout=10);commands.append({'argv':['git',*args],'exit_code':p.returncode,'stdout_bytes':len(p.stdout),'stdout_sha256':sha(p.stdout),'stderr_bytes':len(p.stderr),'stderr_sha256':sha(p.stderr),'elapsed_ns':time.monotonic_ns()-t});assert p.returncode==0;assert len(commands)<=16384 and time.monotonic_ns()-start<=120000000000;assert sum(x['stdout_bytes']+x['stderr_bytes'] for x in commands)<=67108864;return p.stdout
proof=json.loads((OUT/'CURRENT_ROOT_UNION_PROOF.json').read_bytes()) if os.environ.get('MULTI_PREPARATION_OUTPUT') else read_json('CURRENT_ROOT_UNION_PROOF.json')
for d in proof['deliveries']:
 f=d['original_record'];j=d['parents'][1];owner=d['foreign_owner'];schema=json.loads(git('show',f+':THREAD_REVIEW.schema.json'))
 refs=[]
 for kind in ['GENERAL','SECURITY_DATA_BOUNDARY']:
  path=f'docs/exec-plans/reviews/{owner}/{kind}.json';meta=git('ls-tree','-l',j,'--',path).decode();left,p=meta.split('\t');mode,typ,oid,size=left.split();assert mode in ('100644','100755') and typ=='blob' and int(size)<=262144
  b=git('cat-file','blob',oid);value=json.loads(b);jsonschema.validate(value,schema);assert value['task_identity']=='harness-governance-v0.1/'+owner and value['reviewed_head_sha']==f and value['review_type']==kind and value['status']=='PASS'
  assert git('show',P+':'+path)==b
  refs.append({'path':path,'mode':mode,'blob':oid,'bytes':len(b),'sha256':sha(b),'reviewed_head_sha':f,'original_status':'PASS_PRESERVED_NOT_RE_REVIEWED'})
 suffix=git('rev-list','--reverse',f+'..'+j).decode().splitlines();cursor=f;edges=[]
 for rev in suffix:
  ps=git('rev-list','--parents','-n','1',rev).decode().split()[1:];assert ps==[cursor]
  changed=git('diff','--no-renames','--name-only','-z',cursor,rev,'--').decode().split('\0')[:-1];assert changed and all(p.startswith('docs/exec-plans/reviews/'+owner+'/') for p in changed)
  edges.append({'parent':cursor,'child':rev,'paths':changed});cursor=rev
 assert cursor==j
 rows.append({'owner':owner,'delivery':d['commit'],'ordered_parents':d['parents'],'original_record':f,'review_records':refs,'linear_own_review_path_suffix_edges':edges,'full_native_storage_aware_RRO':'NOT_RUN_NOT_CERTIFIED','historic_review_execution':'NOT_RE_EXECUTED'})
out={'status':'ORIGINAL_DELIVERY_RECORD_AND_REVIEW_BINDINGS_OBSERVED','rows':rows,'commands':commands,'complete_native_or_global_audit':'NOT_RUN','historical_scripts_executed':False,'actual_eligibility':'NOT_DETERMINED','elapsed_ns':time.monotonic_ns()-start};(OUT/'DELIVERY_REVIEW_OBSERVATIONS.json').write_text(json.dumps(out,separators=(',',':'))+'\n');print('original_review_records',sum(len(x['review_records']) for x in rows),'exact_suffix_edges',sum(len(x['linear_own_review_path_suffix_edges']) for x in rows),'native_RRO_NOT_RUN')
