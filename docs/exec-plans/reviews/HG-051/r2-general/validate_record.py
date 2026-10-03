import importlib.util,json,subprocess
from pathlib import Path
from jsonschema import Draft202012Validator
R=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop');H='4073ca6ef64a625c398483fb5fbfe41b1ef3237c';own='docs/exec-plans/reviews/HG-051/r2-general/'
s=importlib.util.spec_from_file_location('record_ce',R/'tools/harness/compact_evidence.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
r=json.loads((R/'docs/exec-plans/reviews/HG-051/GENERAL.json').read_bytes());Draft202012Validator(json.loads((R/'THREAD_REVIEW.schema.json').read_bytes())).validate(r)
assert r['status']=='PASS' and r['findings']==[] and r['reviewed_head_sha']==H
for ref in r['evidence_refs']:
 assert c.normalized(ref)
 if ref.startswith(own):
  # New review-created ordinary blobs are absent from reviewed SHA and will bind
  # the exact own linear REVIEW_RECORD_ONLY commit created by parent.
  assert not subprocess.check_output(['git','ls-tree',H,'--',ref],cwd=R).strip();c.read(R,ref,None)
 else:c.read(R,ref,H)
 assert 'HISTORICAL_EVIDENCE_MAPPING' not in ref and ref!='HISTORICAL_EVIDENCE_MAPPING.schema.json'
paths=list((R/own).iterdir());assert all(p.is_file() and not p.is_symlink() and p.stat().st_size<=c.PLAIN_LIMIT for p in paths)
report=dict(status='PASS',reviewed_sha=H,schema='THREAD_REVIEW.schema.json',ordinary_refs_checked=len(r['evidence_refs']),review_files_checked=len(paths),max_plain_bytes=max(p.stat().st_size for p in paths),review_stored_bytes=sum(p.stat().st_size for p in paths),new_ref_binding='parent exact own linear REVIEW_RECORD_ONLY commit',zero_blockers=True)
(R/own/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
