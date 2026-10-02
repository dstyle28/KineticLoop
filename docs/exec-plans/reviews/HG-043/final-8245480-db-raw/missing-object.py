"""Independent exact-SHA missing object availability / absence boundary probe."""
import importlib.util
import types
import subprocess
import tempfile
import json
from pathlib import Path
ROOT=Path.cwd(); HEAD='8245480918251739339987de69bfe41fa0b39af5'
OUT=ROOT/'docs/exec-plans/reviews/HG-043/final-8245480-db-raw'
source=subprocess.check_output(['git','show',HEAD+':tools/harness/validate_harness.py'])
v=types.ModuleType('exact_validator');v.__file__=str(ROOT/'tools/harness/validate_harness.py');exec(compile(source,v.__file__,'exec'),v.__dict__)
s=importlib.util.spec_from_file_location('fixture',ROOT/'tests/harness/test_review_evidence_provenance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.v=v
cases=[]
for source_kind in ('reviewed','review_record'):
 with tempfile.TemporaryDirectory(prefix='hg043-db-object-') as tmp:
  h=m.History(Path(tmp));ref=m.OWN+'unique-missing.log'
  h.put(ref,'unique object for '+source_kind+'\n')
  if source_kind=='reviewed':
   h.reviewed=h.commit('ordinary exact reviewed blob');bound=h.reviewed;oid=h.git('rev-parse',bound+':'+ref);h.put(ref,'later replacement cannot override present entry\n');record=h.review([ref])
  else:
   record=h.review([ref]);bound=record;oid=h.git('rev-parse',bound+':'+ref)
  path=h.root/'.git/objects'/oid[:2]/oid[2:];assert h.root.resolve() in path.resolve().parents;path.unlink()
  entry=v.revision_git_entry(h.root,ref,bound);assert entry is not None
  assert not v.revision_regular_file(h.root,ref,bound)
  errors=h.errors(record);assert errors==['integration-review-evidence:KL-001:GENERAL:'+ref],errors
  cases.append({'source_kind':source_kind,'bound_commit':bound,'entry': [x.decode() for x in entry],'errors':errors})
report={'reviewed_head_sha':HEAD,'result':'PASS','cases':cases,'scope':'Only temporary isolated Git object fixtures mutated; real Git repository and DB untouched.'}
(OUT/'missing-object.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
