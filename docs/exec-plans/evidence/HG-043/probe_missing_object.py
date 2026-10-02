import importlib.util
import json
import tempfile
import subprocess
import types
from pathlib import Path

root=Path.cwd(); spec=importlib.util.spec_from_file_location('fixture',root/'tests/harness/test_review_evidence_provenance.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
source=subprocess.check_output(['git','show','787663f7d8ca2521858c0aaf5fa762d6c0169662:tools/harness/validate_harness.py'])
old=types.ModuleType('missing_object_validator'); old.__file__=str(root/'tools/harness/validate_harness.py'); exec(compile(source,old.__file__,'exec'),old.__dict__); m.v=old
with tempfile.TemporaryDirectory(prefix='hg043-missing-object-') as temp:
 h=m.History(Path(temp)); ref=m.OWN+'unique.log'; h.put(ref,'unique missing object probe\n'); review=h.review([ref]); oid=h.git('rev-parse',review+':'+ref)
 object_path=h.root/'.git/objects'/oid[:2]/oid[2:]; assert h.root.resolve() in object_path.resolve().parents; object_path.unlink()
 print(json.dumps({'source_sha':'787663f7d8ca2521858c0aaf5fa762d6c0169662','review_blob':oid,'regular_file_predicate':m.v.revision_regular_file(h.root,ref,review),'integration_errors':h.errors(review)}))
