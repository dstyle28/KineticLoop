import sys,json,copy,hashlib,ast
from pathlib import Path
R=Path('/Users/davetian/.codex/worktrees/hg066-multi-owner-contract/KineticLoop');D=R/'docs/exec-plans/evidence/HG-066';O=Path('/private/tmp/hg066-general-r1');sys.path[:0]=[str(D),str(R)]
import sequence_model as m
from tools.harness import validate_harness as v
import jsonschema
probes=[]
def deny(label,fn):
 try:fn()
 except (m.Denial,jsonschema.ValidationError):probes.append(label);return
 raise AssertionError('accepted '+label)
p=m.fixture_premise();events=m.fixture_events(p);m.evaluate_synthetic_sequence(events,p)
for i,event in enumerate(events):
 deny('omit_phase:'+event['phase'],lambda i=i:m.evaluate_synthetic_sequence(events[:i]+events[i+1:],p))
 e=copy.deepcopy(events);e[i]['facts']['credential']=True
 deny('injected_authority:'+event['phase'],lambda e=e:m.evaluate_synthetic_sequence(e,p))
for field,cap in m.LIMITS.items():
 b=m.FixtureBudget(clock=lambda:0);b.observe(field,cap-1)
 deny('reservation:'+field,lambda:b.reserve(field,1,pending=1))
 x=m.fixture_preimport_output(m.fixture_preimport_bindings(p['roots']),p['independent_facts']['PREIMPORT']['output']['inventory'],b,p['disposition'])
 jsonschema.validate(x,m.PRESCHEMA);assert x['consumed'][field]==cap-1 and x['complete'] is False and x['status']=='PREIMPORT_DENIED' and x['preserved_duplicate_bytes']==x['preserved_duplicate_paths']==0
 x['complete']=True;deny('false_complete:'+field,lambda:jsonschema.validate(x,m.PRESCHEMA))
p2=m.fixture_multiphase_premise(6)
for mutation in ['missing_group','foreign_member_missing','foreign_bytes_changed','duplicate_path','extra_unrelated_byte']:
 q=copy.deepcopy(p2)
 if mutation=='missing_group':q['retained_groups']={}
 elif mutation=='foreign_member_missing':q['retained_groups'][next(iter(q['retained_groups']))].pop()
 elif mutation=='foreign_bytes_changed':q['inventory_objects'][-1]['bytes']+=1
 elif mutation=='duplicate_path':q['inventory_objects'].append(q['inventory_objects'][-1])
 else:q['object_bytes']['docs/exec-plans/evidence/HG-999/extra']='00'
 deny('whole_inventory:'+mutation,lambda q=q:m.fixture_inventory_oracle(q['inventory_objects'],q['bodies'],q['retained_groups'],q['object_bytes']))
for exitcode in [0,None,-15]:
 q=copy.deepcopy(p['public_child']);q['exit_code']=exitcode
 if exitcode==-15:q.update(interrupted=True,complete=False)
 inv=m.fixture_inventory_oracle(p['inventory_objects'],p['bodies'],p['retained_groups'],p['object_bytes'])
 deny('public_child:'+str(exitcode),lambda q=q:m.fixture_public_assertion(q,inv,p['public_roots']))
record={'base_commit':'a'*40,'tested_commit':'b'*40,'checks_run':[{'check_id':k,'result':'PASS','command':cmd.format(P='a'*40,T='b'*40,O='9700a1b95d05c856897f74f125cfdf6fb3f6e646',unique_scratch='/private/tmp/hg058-fresh/harness')} for k,cmd in v.HG058_AUTHOR_COMMANDS.items()]}
assert v.hg058_selected_check_errors(record)==[]
for i in range(20):
 for variant in ['missing','duplicate','stale','root','notrun','suffix']:
  q=copy.deepcopy(record)
  if variant=='missing':q['checks_run'].pop(i)
  elif variant=='duplicate':q['checks_run'].append(q['checks_run'][i])
  elif variant=='stale':q['checks_run'][i]['command']='old receipt'
  elif variant=='root':q['checks_run'][i]['check_id']='final_private_original_H'
  elif variant=='notrun':q['checks_run'][i]['result']='NOT_RUN'
  else:q['checks_run'][i]['command']+=' --collect-only'
  assert v.hg058_selected_check_errors(q);probes.append(f'author:{i}:{variant}')
# Immutable reviewed manifest comparison reads preparation only as source, never acceptance.
sha=lambda b:hashlib.sha256(b).hexdigest();base=Path('/private/tmp/hg058-multi-owner-rule-r4')
assert sha((base/'CANDIDATE_MANIFEST.json').read_bytes())=='42a445a470825422ee123ee416a8ee2a7805eab3b57ca746f0ebcf6b14603802'
assert sha((base/'DEFINITION_REVISION.json').read_bytes())=='2c3843f14a26771749721e19a8fc26465f845467583fba9311222f95af385a36'
manifest={x['path']:x for x in json.loads((base/'CANDIDATE_MANIFEST.json').read_bytes())['files']}
prov=json.loads((D/'DELIVERY_PROVENANCE.json').read_bytes());a={x['path']:x for x in json.loads((D/'SOURCE_ADAPTATIONS.json').read_bytes())['files']}
for row in prov['reviewed_sources']:
 assert manifest[row['path']]['sha256']==row['sha256']
 orig=(base/row['path']).read_bytes();assert sha(orig)==row['sha256']
 raw=(D/row['path']).read_bytes()
 if row['path'] in a:
  lines=raw.decode().splitlines(keepends=True)
  for x in reversed(a[row['path']]['changes']):lines[x['destination_start']:x['destination_end']]=x['original'].splitlines(keepends=True)
  assert ''.join(lines).encode()==orig
 else:assert raw==orig
out={'independent_hostile_probes':len(probes),'probe_ids':probes,'approved_source_files_compared':len(prov['reviewed_sources']),'source_only_candidate_read':True,'scratch_not_execution_dependency':True,'historical_execution':'UNVERIFIED','runtime':'NOT_RUN'}
(O/'probes.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='probe_ids'}))
