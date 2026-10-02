import hashlib, json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path.cwd()
OUT=ROOT/'docs/exec-plans/reviews/HG-043/final-8245480-protocol-raw'
SHA='8245480918251739339987de69bfe41fa0b39af5'
key=sys.argv[1]
commands={
 'focused':[str(ROOT/'.venv/bin/python'),'-m','pytest','-q','-p','no:cacheprovider','tests/harness/test_review_evidence_provenance.py'],
 'preserved_guards':[str(ROOT/'.venv/bin/python'),'-m','pytest','-q','-p','no:cacheprovider','tests/harness/test_validator.py','-k','exact_complete_tree_squash_merge or review_recorded_after_merge or delayed_review_rejects_task_change_after_merge or delayed_review_must_bind_the_merge_tree or squash_tree_with_unrelated_content_change or squash_tree_with_mode_only_difference or exact_tree_exception_does_not_replace_review_binding_ancestry'],
 'replay':[str(ROOT/'.venv/bin/python'),str(ROOT/'docs/exec-plans/evidence/HG-043/replay.py')],
}
command=commands[key]
start=time.time()
run=subprocess.run(command,env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),PYTHONDONTWRITEBYTECODE='1'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
record={'reviewed_head_sha':SHA,'purpose':'Independent PROTOCOL reviewer run; not task acceptance evidence','command':command,'exit_code':run.returncode,'elapsed_seconds':time.time()-start,'raw_sha256':hashlib.sha256(run.stdout).hexdigest(),'raw_byte_count':len(run.stdout),'raw_utf8':run.stdout.decode()}
(OUT/(key+'.json')).write_text(json.dumps(record,indent=2)+'\n')
print(key,run.returncode,record['elapsed_seconds'])
if key in ('focused','preserved_guards'): print(record['raw_utf8'])
if key=='replay' and run.returncode==0:
 r=json.loads(record['raw_utf8'])
 print({k:{'original_errors':len(v['original_validator_errors']),'repaired_errors':len(v['repaired_validator_errors']),'refs':len(v['references'])} for k,v in r['candidates'].items()})
raise SystemExit(run.returncode)
