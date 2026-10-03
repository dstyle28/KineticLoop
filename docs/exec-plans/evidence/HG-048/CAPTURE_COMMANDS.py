from pathlib import Path
import hashlib,importlib.util,json,shlex,shutil,subprocess,sys,time
root=Path('/Users/davetian/.codex/worktrees/harness-concurrency/KineticLoop')
tested='0045808352507b7af67a3a2135408421d8bcc6bc'
base='391c9198fa8ec647e377a0572700bc7568468c85'
final=Path('/private/tmp/hg048-final-measurements')
quality=Path('/private/tmp/hg048-final-quality')/tested
while not (final/'comparison.json').exists() or not (quality/'quality.json').exists(): time.sleep(5)
q=json.loads((quality/'quality.json').read_text())
if q['tested_commit']!=tested or any(c['exit_code'] for c in q['checks']): raise RuntimeError('Final quality checks are not all PASS')
comparison=json.loads((final/'comparison.json').read_text())
if comparison['tested_commit']!=tested or not comparison['same_collection_all_runs']: raise RuntimeError('Comparison not bound')
if subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=tested: raise RuntimeError('Source changed before capture')
spec=importlib.util.spec_from_file_location('upstream_compact', '/private/tmp/hg048-upstream-compact.py')
assert spec and spec.loader
codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(codec)
folder=root/'docs/exec-plans/evidence/HG-048'
raw_folder='docs/exec-plans/evidence/HG-048/raw'
index={'tested_commit':tested,'base_commit':base,'codec_source':json.loads(Path('/private/tmp/hg048-codec-source.json').read_text()),'final_runs':[],'development_runs':[],'quality':{},'roundtrips':[],'excluded_development_artifacts':[]}
def store(path,prefix,source,command,exit_code,timestamp=None):
 ref=raw_folder+'/'+prefix+'.json';raw=path.read_bytes()
 if not (root/ref).exists(): codec.capture(root,ref,raw,source,command,exit_code,timestamp)
 recovered=codec.read(root,ref,None,tested=source,command=command,exit_code=exit_code)
 if recovered!=raw:raise RuntimeError('Raw roundtrip mismatch')
 index['roundtrips'].append({'ref':ref,'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)})
 return ref
for epoch,directory,key,labels in [
 ('final',final,'final_runs',['initial-w2','w4','serial','repeat-w2']),
 ('development',Path('/private/tmp/hg048-measurements'),'development_runs',['initial-w2','w4','serial']),
]:
 for label in labels:
  run=directory/label;m=json.loads((run/'manifest.json').read_text());source=m['tested_commit']
  command=shlex.join([str(root/'.venv/bin/python'),'-m','kineticloop.db.cli','test-harness','--workers',str(m['workers']),'--evidence-dir',str(run),'-q','--durations=20'])
  records={}
  for p in sorted(run.iterdir()):
   if epoch=='development' and label in ('initial-w2','w4') and p.name=='execution.json':
    index['excluded_development_artifacts'].append({'label':label,'original_path':str(p),'raw_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'raw_bytes':p.stat().st_size,'reason':'Obsolete successful prototype phase record excluded from PR budget; full raw logs, JUnit, collection and manifest retained. Complete final and interrupted-run phase records are committed.'})
    continue
   if p.is_file():records[p.name]=store(p,epoch+'-'+label+'-'+p.name.replace('.','-'),source,command,m['exit_code'])
  entry={'label':label,'tested_commit':source,'workers':m['workers'],'exit_code':m['exit_code'],'wall_seconds':m['wall_seconds'],'command':command,'artifacts':records}
  if epoch=='final':
   if m['exit_code'] or m['errors'] or m['mode']!='EXECUTION' or not m['execution_complete']:raise RuntimeError('Incomplete final execution')
   for item in m['files']:
    data=(run/item['path']).read_bytes()
    if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise RuntimeError('Original manifest hash mismatch')
   e=json.loads((run/'execution.json').read_text());nodes=next(iter(e['collections'].values()))
   if len(nodes)!=1071 or sorted(e['started'])!=sorted(nodes):raise RuntimeError('Case identity mismatch')
   parallel_cases=[v for v in e['reports'] if v['nodeid'].startswith('tests/harness/test_parallel_runner.py::') and v['phase']=='call']
   if len(parallel_cases)!=18 or any(v['outcome']!='passed' for v in parallel_cases):raise RuntimeError('Focused regression coverage incomplete')
   entry['nodes_sha256']=hashlib.sha256(json.dumps(nodes,separators=(',',':')).encode()).hexdigest()
   entry['tests']=len(nodes)
  index[key].append(entry)
for label in ['lint','typecheck','unit','authority','diff']:
 record=json.loads((quality/(label+'.json')).read_text());command=shlex.join(record['command'])
 refs={p.name:store(p,'quality-'+label+'-'+p.name.replace('.','-'),tested,command,record['exit_code'],record['started_at_utc']) for p in [quality/(label+'.log'),quality/(label+'.json')]}
 if label=='unit':refs['unit.xml']=store(quality/'unit.xml','quality-unit-junit',tested,command,record['exit_code'],record['started_at_utc'])
 index['quality'][label]={'command':command,'exit_code':record['exit_code'],'wall_seconds':record['wall_seconds'],'artifacts':refs}
(folder/'BENCHMARK_INDEX.json').write_text(json.dumps(index,indent=2)+'\n')
(folder/'COMPARISON.json').write_text(json.dumps(comparison,indent=2)+'\n')
shutil.copyfile(quality/'quality.json',folder/'QUALITY.json')
shutil.copyfile('/private/tmp/hg048-scope-audit.json',folder/'SCOPE_AUDIT.json')
shutil.copyfile('/private/tmp/hg048-codec-source.json',folder/'CODEC_SOURCE.json')
for src,dst in [('hg048-final-benchmark.py','BENCHMARK_COMMANDS.py'),('hg048-final-quality.py','QUALITY_COMMANDS.py'),('hg048-final-identity.py','IDENTITY_COMMANDS.py'),('hg048-scope-audit.py','SCOPE_AUDIT.py'),('hg048-package-evidence.py','CAPTURE_COMMANDS.py')]:
 shutil.copyfile('/private/tmp/'+src,folder/dst)
print(json.dumps({'captured_artifacts':len(index['roundtrips']),'raw_bytes':sum(v['raw_bytes'] for v in index['roundtrips']),'stored_bytes':sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())}),flush=True)
