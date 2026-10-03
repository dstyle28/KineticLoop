from pathlib import Path
import json,subprocess,sys,time
root=Path('/Users/davetian/.codex/worktrees/harness-concurrency/KineticLoop')
out=Path('/private/tmp/hg048-final-measurements')
expected='0045808352507b7af67a3a2135408421d8bcc6bc'
print('Final benchmark source: '+expected,flush=True)
for label,workers in [('initial-w2',2),('w4',4),('serial',1),('repeat-w2',2)]:
 tested=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
 if tested!=expected: raise RuntimeError('Benchmark source changed')
 print(json.dumps({'starting':label,'workers':workers,'tested_commit':tested}),flush=True)
 command=[str(root/'.venv/bin/python'),'-m','kineticloop.db.cli','test-harness','--workers',str(workers),'--evidence-dir',str(out/label),'-q','--durations=20']
 result=subprocess.run(command,cwd=root)
 manifest=json.loads((out/label/'manifest.json').read_text())
 print(json.dumps({'finished':label,'exit_code':result.returncode,'seconds':manifest['wall_seconds'],'errors':manifest['errors']}),flush=True)
 if result.returncode: sys.exit(result.returncode)
rows=[];canonical=None
for label in ('initial-w2','w4','serial','repeat-w2'):
 manifest=json.loads((out/label/'manifest.json').read_text())
 observer=json.loads((out/label/'execution.json').read_text())
 nodes=next(iter(observer['collections'].values()))
 if canonical is None: canonical=nodes
 if nodes!=canonical: raise RuntimeError('Cross-mode collection mismatch')
 if sorted(observer['started'])!=sorted(canonical): raise RuntimeError('Execution mismatch')
 rows.append({'run':label,'workers':manifest['workers'],'wall_seconds':manifest['wall_seconds'],'exit_code':manifest['exit_code'],'tests':len(nodes),'phase_outcomes':{outcome:sum(r['outcome']==outcome for r in observer['reports']) for outcome in ('passed','failed','skipped')}})
summary={'tested_commit':expected,'same_collection_all_runs':True,'tests':len(canonical or []),'runs':rows,'hardware':{'physical_cpus':18,'logical_cpus':18,'memory_bytes':38654705664},'limitations':['Sequential runs on the same macOS ARM64 host; normal background applications and filesystem caches were not disabled.','Developer harness evidence does not replace trusted serial local-db-gate.']}
(out/'comparison.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
