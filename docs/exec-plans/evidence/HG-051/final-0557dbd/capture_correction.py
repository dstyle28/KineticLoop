"""Persist complete correction check execution at exact committed source."""
import importlib.util,json,shutil,subprocess
from pathlib import Path
import yaml
root=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
sha='0557dbd8f2196df871af20c0982bdc2526f0ad6e';base='b877db0edd2e4550d6ea81750656112fb7f2e223'
source=Path('/private/tmp/hg051-checks-'+sha[:7]);execution=json.loads((source/'EXECUTION.json').read_bytes())
assert execution['tested_commit']==execution['source_end_sha']==sha and not execution['source_end_status']
assert all(r['exit_code']==0 and r['tested_commit']==sha for r in execution['executions'])
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==sha
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root)
spec=importlib.util.spec_from_file_location('hg051_corrected_capture',root/'tools/harness/compact_evidence.py');ce=importlib.util.module_from_spec(spec);spec.loader.exec_module(ce)
out=root/'docs/exec-plans/evidence/HG-051'/('final-'+sha[:7]);out.mkdir()
def capture(path,name,record):
 ref=str((out/(name+'.json')).relative_to(root));ce.capture(root,ref,path.read_bytes(),sha,record['command'],record['exit_code'],None);return ref
checks=[]
for r in execution['executions']:
 checks.append(dict(check_id=r['check_id'],command=r['command'],result='PASS',evidence_ref=capture(Path(r['log']),r['check_id'],r)))
by_id={r['check_id']:r for r in execution['executions']}
for kind in ['focused','unit']:capture(source/(kind+'.xml'),kind+'-junit',by_id[kind])
for path in sorted((source/'harness').iterdir()):
 if path.is_file():capture(path,'harness-'+path.name.replace('.','-'),by_id['harness'])
shutil.copyfile(source/'EXECUTION.json',out/'EXECUTION.json')
shutil.copyfile('/private/tmp/hg051-installed-schema-driver-final.log',out/'driver.log')
shutil.copyfile('/private/tmp/hg051-driver-0557dbd.log',out/'duplicate-launch-rejected.log')
shutil.copyfile(__file__,out/'capture_correction.py')
p=root/'docs/exec-plans/governance/HG-051.yaml';record=yaml.safe_load(p.read_bytes())
record['tested_commit']=sha;record['change_status']='PASS';record['checks_run']=checks
record['known_limitations']=[
 'Governance only: actual KL080 artifacts remain unmigrated; no KL080/M3/product/release closure.',
 'User delegated completion of reviewed trusted installation/pins, exact admission and final App/full-DB gate to this task. These remain prospective after fresh reviews; no credential/controller logic/protection change is authorized or performed.',
 'Prior tests/reviews retain original SHAs and historical outcomes; source correction stales the old four reviews. Fresh GENERAL, PROTOCOL, DB_CONCURRENCY and SECURITY_DATA_BOUNDARY reviews must bind this corrected governance/evidence revision.',
 'All failures and interrupted rounds remain committed without acceptance credit. bf7bd40 authority/unit FAIL and interrupted harness exit2 are preserved; restoring exact old checks fixed governance bookkeeping before this fresh clean run.',
 'Original source-suite exit1 failures, BLOCKED/FAIL/UNMERGED result, CHANGES_REQUIRED reviews and unknown timestamps remain immutable. No absent SECURITY review is fabricated.',
 'Archival retrieval proves bytes only; execution/review/acceptance cannot use it. Original verification requires exact original regular objects and normal ancestry.',
 'Only own-task linear REVIEW_RECORD_ONLY files may follow the corrected reviewed SHA. Hosted quality/merge gates and mandatory App-bound final gate must pass at final PR head before normal merge.',
 'An attempted duplicate launch was refused because the clean run directory already existed; no checks or evidence were overwritten. The original run completed at the exact unchanged source.'
]
changed=subprocess.check_output(['git','diff','--no-renames','--name-only',base,'HEAD'],cwd=root,text=True).splitlines()
new=[str(q.relative_to(root)) for q in out.rglob('*') if q.is_file()]
record['files_changed']=sorted(set(changed+new+[str(p.relative_to(root))]))
p.write_text(yaml.safe_dump(record,sort_keys=False,width=110));print(json.dumps(dict(tested_commit=sha,checks=len(checks),files=len(record['files_changed'])),indent=2))
