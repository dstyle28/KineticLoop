import copy,hashlib,itertools,json,sys
from pathlib import Path
ROOT=Path('/Users/davetian/.codex/worktrees/hg067-host-resource-contract/KineticLoop');E=ROOT/'docs/exec-plans/evidence/HG-067';OUT=Path('/private/tmp/hg067-security-r1')
sys.path[:0]=[str(E),str(ROOT)]
from definition_oracle import *
from test_definition import example,denial,emergency
from tools.harness import validate_harness as v
rows=[]
def probe(name,thing,fn,expected):
 raw=canonical(thing);error=None
 try:
  result=fn(copy.deepcopy(thing));actual=True
 except Exception as ex:actual=False;error=type(ex).__name__+':'+str(ex).splitlines()[0][:160]
 rows.append({'id':name,'input_sha256':hashlib.sha256(raw).hexdigest(),'expected_accept':expected,'observed_accept':actual,'matched':actual==expected,'error':error})
def full(x):return validate_record(seal_record(x))
for route,layout in [('PREIMPORT','EXISTING_CHECKOUT'),('FINAL','BARE_CLONE'),('FINAL','MATERIALIZED_CHECKOUT')]:
 base=example(route,layout);prefix=route+'-'+layout
 probe(prefix+'-positive',base,full,True)
 for field in LIMITS:
  x=copy.deepcopy(base);x['counters'][field]=LIMITS[field]['limit']+1
  # result_bytes is deliberately tested without sealing below.
  if field!='result_bytes':probe(prefix+'-over-'+field,x,full,False)
 x=copy.deepcopy(base);x['counters']['result_bytes']+=1;probe(prefix+'-wrong-size',x,validate_record,False)
 for field,new in [('publishable_positives',1),('continuation_authorized',True),('acceptance_eligible',True),('execution_reuse',True),('native_limits_unchanged',False),('observer_exit',0),('observer_state','EXITED'),('counter_state','LOWER_BOUND')]:
  x=copy.deepcopy(base);x[field]=new;probe(prefix+'-forged-'+field,x,full,False)
 for i in range(len(base['native_contexts'])):
  for state in ['NOT_REACHED','DENIED','INTERRUPTED']:
   x=copy.deepcopy(base);x['native_contexts'][i].update(status=state,complete=False,result_sha256=None);probe(prefix+f'-native-{i}-{state}',x,full,False)
 for phase in range(9):
  x=copy.deepcopy(base);x['phases'][phase]['status']='NOT_STARTED';x['phases'][phase]['elapsed_ns']=0;probe(prefix+f'-omit-phase-{phase}',x,full,False)
 for who in ['driver','child']:
  for state,exitcode in [('UNKNOWN',None),('EXITED',-9),('NOT_STARTED',None)]:
   x=copy.deepcopy(base);x[who+'_state']=state;x[who+'_exit']=exitcode;probe(prefix+'-'+who+'-'+state,x,full,False)
 x=copy.deepcopy(base);x['elapsed_ns']=OVERALL_NS[route]+1;probe(prefix+'-deadline',x,full,False)
 x=copy.deepcopy(base);x['public_authority']=True;probe(prefix+'-unknown-field',x,full,False)
for layout,field,stage,status in itertools.product(['BARE_CLONE','MATERIALIZED_CHECKOUT'],['store_device','store_inode','objects_device','objects_inode'],['SOURCE_BEFORE','SOURCE_AFTER','FINAL_BOUNDARY'],['DENIED','INTERRUPTED']):
 x=denial('FINAL',stage,status=='INTERRUPTED');x['acquisition']=layout
 for which in ['initial','terminal']:
  if x[which]:x[which]['source_kind']='BARE_OWNED' if layout=='BARE_CLONE' else 'CHECKOUT'
 which='initial' if stage=='SOURCE_BEFORE' else 'terminal';x[which][field]+=19
 x['reasons']=['SOURCE_CHANGED']+(['INTERRUPTION'] if status=='INTERRUPTED' else [])
 if stage=='FINAL_BOUNDARY':x['post_worker_rechecks'][0]['status']=status;x['post_worker_rechecks'][1].update(status='NOT_STARTED',elapsed_ns=0)
 label='truthful-'+layout+'-'+field+'-'+stage+'-'+status
 probe(label,x,full,True)
 y=copy.deepcopy(x);y['reasons']=['HOST_IO_ERROR']+(['INTERRUPTION'] if status=='INTERRUPTED' else []);probe(label+'-wrong-cause',y,full,False)
for layout,field in itertools.product(['BARE_CLONE','MATERIALIZED_CHECKOUT'],['store_device','store_inode','objects_device','objects_inode']):
 x=example('FINAL',layout);x['initial'][field]+=23;x['terminal'][field]+=23;probe('forged-equal-'+layout+'-'+field,x,full,False)
for route in ['PREIMPORT','FINAL']:
 names=trace_template(route);events=[{'event':n,'role':{'START_C':'D','NATIVE_OUTPUT':'C','WORKER_START':'C','WORKER_DONE':'C','C_EXIT':'D'}.get(n,'S'),'ledger':'7'*32,'at_ns':i*1000000,'failure':None} for i,n in enumerate(names)]
 check=lambda x:validate_trace(x,route)
 probe('trace-'+route+'-positive',events,check,True)
 for i,n in enumerate(names):
  if n not in ['START_S','STOP_S']:
   x=copy.deepcopy(events);x.pop(i);probe('trace-'+route+'-omit-'+n+'-'+str(i),x,check,False)
 for n in ['LOCK_ACQUIRED','AUTH_BEFORE','SOURCE_BEFORE','ASSET_BINDING','FINAL_CHECK','COMMIT_ELIGIBLE']:
  x=copy.deepcopy(events);next(y for y in x if y['event']==n)['role']='C';probe('trace-'+route+'-wrong-owner-'+n,x,check,False)
 x=copy.deepcopy(events);x[-3]['ledger']='8'*32;probe('trace-'+route+'-ledger-reset',x,check,False)
 x=copy.deepcopy(events);x[-1]['at_ns']=OVERALL_NS[route]+1;probe('trace-'+route+'-late-stop',x,check,False)
 if route=='FINAL':
  x=copy.deepcopy(events);next(y for y in x if y['event']=='PUBLISH_ACK')['failure']='unknown';probe('trace-uncertain-publication',x,check,False)
for field,new in [('complete',True),('publishable_positives',1),('continuation_authorized',True),('acceptance_eligible',True),('execution_reuse',True),('driver_exit',0),('observer_exit',0),('counter_state','EXACT')]:
 x=emergency();x[field]=new;probe('emergency-'+field,x,validate_emergency,False)
x=emergency();probe('emergency-positive',x,validate_emergency,True)
for i,raw in enumerate([b'{"x":0,"x":1}',b'{"x":NaN}',b'['*33+b'0'+b']'*33,b'{"x":"'+b'a'*16385+b'"}',b' '*1048577]):
 probe('decoder-'+str(i),raw.hex(),lambda _:decode_bounded(raw),False)
# Direct selected governance guard probes; existing native scope guards are left untouched.
record={'checks_run':[{'check_id':x} for x in sorted(v.HG067_REQUIRED_CHECKS)],'packets_refined':[],'authority_entries_added':[]}
probe('governance-valid',record,lambda x:not v.host_resource_projection_errors(x,set()) or (_ for _ in ()).throw(ValueError('guard')),True)
for field in ['missing','duplicate','foreign','projection','authority']:
 x=copy.deepcopy(record)
 if field=='missing':x['checks_run'].pop()
 elif field=='duplicate':x['checks_run'].append(x['checks_run'][0])
 elif field=='foreign':x['checks_run'][0]['check_id']='different'
 elif field=='projection':x['packets_refined']=['KL-081']
 else:x['authority_entries_added']=['NEW']
 probe('governance-'+field,x,lambda x:not v.host_resource_projection_errors(x,set()) or (_ for _ in ()).throw(ValueError('guard')),False)
report={'reviewed_head_sha':'ddffdbf75d6ff7b774fa84b00c20e57fc3a24fa5','purpose':'Reviewer synthetic conformance only; no actual runtime/native authorization or enforcement proof','cases':rows,'total':len(rows),'matched':sum(x['matched'] for x in rows),'unexpected':[x['id'] for x in rows if not x['matched']]}
(OUT/'HOSTILE_PROBES.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
raise SystemExit(bool(report['unexpected']))
