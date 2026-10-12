import copy,hashlib,json,subprocess,sys
from pathlib import Path
import jsonschema
ROOT=Path('/Users/davetian/.codex/worktrees/hg065-custody-delivery/KineticLoop');E=ROOT/'docs/exec-plans/evidence/HG-065';OUT=Path('/private/tmp/hg065-security-r1')
sys.path[:0]=[str(ROOT),str(E)]
from tools.harness import compact_evidence as n
import custody_study as s
Q='3965cac382d333bd97f6c67fec8ecbe805b5932f';P='e8e93bd32a83bd2fd6bf89951863d59b37e9d2b3';O='9700a1b95d05c856897f74f125cfdf6fb3f6e646'
proof=json.loads((E/'ACTUAL_CUSTODY_PROOF.json').read_bytes());schema=json.loads((E/'OUTPUT_SCHEMA.json').read_bytes());rows=[];commands=[]
def git(*args):
 p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,timeout=15);commands.append({'argv':['git',*args],'exit_code':p.returncode,'bytes':len(p.stdout),'sha256':hashlib.sha256(p.stdout).hexdigest()});assert p.returncode==0;return p.stdout
def raw(rev,path):return git('show',rev+':'+path)
for path,old_revs in [(proof['map_binding']['object']['path'],[proof['map_binding']['admission']]),('docs/exec-plans/evidence/HG-054/collection-conversion/COMPACT_REENCODING.json',[O,P])]:
 data=raw(Q,path);m=n.reencoding_record(data);assert all(raw(rev,path)==data for rev in old_revs)
 git('merge-base','--is-ancestor',m['protected_base'],m['source_revision'])
 for i,entry in enumerate(m['entries']):
  bodies=[];metadata=[]
  for key,rev in [('original',m['source_revision']),('replacement',Q)]:
   binding=entry[key]
   for field in ['envelope','payload']:
    content=raw(rev,binding[field]['path']);assert n.snapshot_bytes(binding[field]['path'],content)==binding[field]
   env=n.envelope(raw(rev,binding['envelope']['path']));metadata.append({k:env[k] for k in n.EXECUTION_FIELDS});bodies.append(n.read(ROOT,binding['envelope']['path'],rev))
  assert bodies[0]==bodies[1] and metadata[0]==metadata[1]==entry['execution']
  rows.append({'check':'native_map_component','map':path,'entry':i,'raw_bytes':len(bodies[0]),'raw_sha256':hashlib.sha256(bodies[0]).hexdigest(),'metadata_equal':True})
# Every output counter is inclusive, including complete ordinary denials.
def output():return {'type':'RETAINED_REPRESENTATION_CUSTODY_V1','status':'CUSTODY_DENIED','invocation_id':'independent-synthetic-output','selected_identity':proof['selected_identity'],'original_base':proof['original_base'],'protected_base':proof['protected_base'],'head':Q,'audit_phase':'ORIGINAL','complete':True,'accounted_paths':0,'accounted_bytes':0,'physical_paths':proof['physical_paths'],'execution_attribution':'UNVERIFIED','acceptance_eligible':False,'execution_reuse':False,'original_guard_status':'NOT_RUN','live_guard_status':'NOT_RUN','denial_reasons':['OBJECT_MISMATCH'],'elapsed_ns':s.DEADLINE_NS,'consumed':{k:0 for k in s.LIMITS}}
def reject(v):
 try:s.validate_output(v,schema)
 except (s.Denial,jsonschema.ValidationError):return
 raise AssertionError('accepted invalid output')
for name,limit in s.LIMITS.items():
 d=output();d['consumed'][name]=limit;s.validate_output(d,schema)
 d['consumed'][name]+=1;reject(d)
 d.update(complete=False,denial_reasons=['LIMIT_EXHAUSTED']);s.validate_output(d,schema)
 d['elapsed_ns']+=1;reject(d)
 d['denial_reasons'].append('DEADLINE_EXCEEDED');s.validate_output(d,schema)
 rows.append({'check':'counter_inclusive_overrun_simultaneous','counter':name,'limit':limit,'actual_preserved':limit+1})
for name,value in [('acceptance_eligible',True),('execution_reuse',True),('execution_attribution','PASS'),('type','ACCOUNTED_PROTECTED_IMPORT'),('audit_phase','LIVE'),('accounted_paths',1),('accounted_bytes',1),('elapsed_ns',True),('extra',True)]:
 d=output();d[name]=value;reject(d);rows.append({'check':'output_privilege_or_accounting_denied','field':name})
d=output();d.update(status='CUSTODY_UNPERFORMED',complete=False,denial_reasons=['UNPERFORMED']);s.validate_output(d,schema)
for reasons in [[],['OBJECT_MISMATCH'],['UNPERFORMED','LIMIT_EXHAUSTED']]:
 v=copy.deepcopy(d);v['denial_reasons']=reasons;reject(v)
rows.append({'check':'unperformed_exact_pairing','rejections':3})
# Cache dimension separation with neutral synthetic data only.
context={'repository':'neutral/review','object_format':'sha1','installed_release':'1'*40,'controller_assets_sha256':'2'*64,'authority_sha256':'3'*64,'selected_identity':'harness-governance-v0.1/HG-201','original_base':'4'*40,'protected_base':'5'*40,'original_selected':'6'*40,'head':'7'*40,'packet_blob':'8'*40,'map_blob':'9'*40,'source':'a'*40,'admission':'b'*40,'declaration_blob':'c'*40,'delivery':'d'*40,'group_sha256':'e'*64,'edges_sha256':'f'*64,'invocation':'synthetic-review'}
key=s.cache_key(context,proof['physical_paths'][0],'ORIGINAL_CUSTODY')
for field in context:
 c=dict(context)
 if field=='object_format':c[field]='sha256'
 elif field=='repository':c[field]='neutral/other'
 elif field=='selected_identity':c[field]='harness-governance-v0.1/HG-202'
 elif field=='invocation':c[field]='other-invocation'
 else:c[field]=('0' if c[field][0]!='0' else '1')+c[field][1:]
 try:new=s.cache_key(c,proof['physical_paths'][0],'ORIGINAL_CUSTODY')
 except s.Denial:pass
 else:assert new!=key
 rows.append({'check':'cache_dimension_isolation','field':field})
for purpose in ['EXECUTION','REVIEW_SOURCE_LINEAGE','REVIEW_RECORD_ONLY','LIVE_BASE','ADMISSION','M3']:
 try:s.cache_key(context,proof['physical_paths'][0],purpose)
 except s.Denial:pass
 else:raise AssertionError(purpose)
rows.append({'check':'cache_wrong_purpose_denied','count':6})
(OUT/'supplement.json').write_text(json.dumps({'results':rows,'commands':commands,'original_native_full_audit':'NOT_RUN','model_authority':False},indent=2)+'\n')
print(json.dumps({'status':'PASS','checks':len(rows),'git_reads':len(commands)}))
