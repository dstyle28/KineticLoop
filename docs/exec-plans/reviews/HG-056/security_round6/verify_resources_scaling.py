"""Exact-source classification and actual collector profiling; no input executes."""
import ast, json, subprocess, time, types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]; OUT=Path(__file__).resolve().parent
R='0b089d7d3b0212a4e5458dc7891cbb4e831cd6f6'; T='1cb64a1baef54fc7801e4084a18db962c3528a70'
def blob(path): return subprocess.check_output(['git','show',R+':'+path],cwd=ROOT)
ce=types.ModuleType('resource_ce');ce.__file__=str(ROOT/'tools/harness/compact_evidence.py')
exec(compile(blob('tools/harness/compact_evidence.py'),'exact_decoder','exec'),ce.__dict__)
rows=[]
for write in (False,True):
 target=b'record["kineticloop_evidence"], ordinary' if write else b'record["kineticloop_evidence"]'
 raw=b'('*256+target+b')'*256+(b'="gzip-v1", "x"' if write else b'')
 try: ast.parse(raw)
 except SyntaxError as ex: native=ex.msg
 assert native=='too many nested parentheses'
 for classify in (ce.envelope,ce.reencoding_record):
  try: classify(raw); outcome='plain'
  except ValueError as ex: outcome=str(ex)
  assert outcome=='evidence-source-classification'
  rows.append({'kind':'actual_native','write':write,'classifier':classify.__name__,'native_error':native,'outcome':outcome,'sha256':ce.digest(raw),'bytes':len(raw)})
original_parse=ce.ast.parse
for error in (MemoryError,RecursionError):
 def unavailable(*args,**kwargs): raise error()
 ce.ast.parse=unavailable
 try:
  for classify in (ce.envelope,ce.reencoding_record):
   try: classify(b'record["kineticloop_evidence"], ordinary = "gzip-v1", "x"');outcome='plain'
   except ValueError as ex: outcome=str(ex)
   assert outcome=='evidence-source-classification'
   rows.append({'kind':'simulated_resource','error':error.__name__,'classifier':classify.__name__,'outcome':outcome})
 finally: ce.ast.parse=original_parse
(OUT/'resources-scaling.json').write_text(json.dumps({'R':R,'resource_checks':rows,'profiling_status':'RUNNING'},indent=2)+'\n')
D='docs/exec-plans/evidence/HG-056/checks-repair-'+T+'-9bc7f4cc/'
path=D+'full_collection.json'; env=json.loads(blob(path)); stored=blob(env['payload'])
assert len(stored)==env['stored_bytes'] and ce.digest(stored)==env['stored_sha256']
raw=ce.decode(stored,env['kineticloop_evidence'],env['raw_bytes'])
assert len(raw)==env['raw_bytes'] and ce.digest(raw)==env['raw_sha256']
profile=[]
for copies in (1,2):
 metrics={'calls':0,'parse_bytes':0,'maximum_parse_span':0}
 def counted(source,*args,**kwargs):
  metrics['calls']+=1;metrics['parse_bytes']+=len(source);metrics['maximum_parse_span']=max(metrics['maximum_parse_span'],len(source))
  return original_parse(source,*args,**kwargs)
 ce.ast.parse=counted; begin=time.monotonic()
 try: plain=ce.envelope(raw*copies) is None
 finally: ce.ast.parse=original_parse
 assert plain
 profile.append({'copies':copies,'input_bytes':len(raw)*copies,'seconds':round(time.monotonic()-begin,3),'outcome':'plain',**metrics})
ratio={field:profile[1][field]/profile[0][field] if profile[0][field] else None for field in ('calls','parse_bytes','seconds')}
result={'R':R,'resource_checks':rows,'profiling_status':'COMPLETE','actual_collector_ref':path,'raw_sha256':ce.digest(raw),'raw_bytes':len(raw),'profiles':profile,'ratios':ratio,'input_execution':False,'new_production_budget':False,'interpretation':'Observed work on one and two complete copies of actual committed collector bytes; source inspection resets local target spans per logical statement and does not rescan all preceding statements. No universal complexity proof or production work ceiling inferred.'}
(OUT/'resources-scaling.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
