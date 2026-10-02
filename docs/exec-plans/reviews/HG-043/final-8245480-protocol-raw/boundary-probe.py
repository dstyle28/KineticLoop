import importlib.util, json, subprocess, tempfile, types
from pathlib import Path
ROOT=Path.cwd(); OUT=ROOT/'docs/exec-plans/reviews/HG-043/final-8245480-protocol-raw'
spec=importlib.util.spec_from_file_location('fixtures',ROOT/'tests/harness/test_review_evidence_provenance.py')
t=importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
v=t.v
old=types.ModuleType('old'); old.__file__=str(ROOT/'tools/harness/validate_harness.py')
source=subprocess.check_output(['git','show','2896d2422999fdf8a2cbca75eb316798c015ad17:tools/harness/validate_harness.py'],cwd=ROOT)
exec(compile(source,old.__file__,'exec'),old.__dict__)
report={'reviewed_head_sha':'8245480918251739339987de69bfe41fa0b39af5','purpose':'Independent reviewer adversarial real-Git probe; no task acceptance assertion','cases':[]}
for kind in ('symlink','directory','gitlink','missing_blob_reviewed','missing_blob_recorded'):
 with tempfile.TemporaryDirectory(prefix='hg043-protocol-boundary-') as tmp:
  h=t.History(Path(tmp)); ref=t.OWN+'bound-source'; target=h.root/ref
  if kind=='symlink':
   target.parent.mkdir(parents=True); target.symlink_to('../../../evidence/KL-001/check.log'); h.reviewed=h.commit('reviewed symlink'); target.unlink()
  elif kind=='directory':
   h.put(ref+'/child'); h.reviewed=h.commit('reviewed directory'); (target/'child').unlink(); target.rmdir()
  elif kind=='gitlink':
   h.git('update-index','--add','--cacheinfo',f'160000,{h.base},{ref}'); h.git('commit','-qm','reviewed gitlink'); h.reviewed=h.git('rev-parse','HEAD')
  elif kind=='missing_blob_reviewed':
   h.put(ref,'unique reviewed object');h.reviewed=h.commit('reviewed blob'); missing=h.git('rev-parse',h.reviewed+':'+ref)
  h.put(ref,'regular review-record replacement'); endpoint=h.review([ref])
  if kind=='missing_blob_recorded': missing=h.git('rev-parse',endpoint+':'+ref)
  if kind.startswith('missing_blob'):
   (h.root/'.git/objects'/missing[:2]/missing[2:]).unlink()
  entry=v.revision_git_entry(h.root,ref,h.reviewed)
  suffix=v.suffix_errors(h.root,h.reviewed,endpoint,'KL-001','review')
  new=v.review_evidence_exists(h.root,ref,h.reviewed,endpoint,'KL-001',not suffix)
  prior=old.review_evidence_exists(h.root,ref,h.reviewed,endpoint,'KL-001',not suffix)
  errors=h.errors(endpoint)
  assert suffix==[] and not new
  assert 'integration-review-evidence:KL-001:GENERAL:'+ref in errors
  report['cases'].append({'kind':kind,'reviewed_entry':[i.decode() for i in entry] if entry else None,'record_entry':[i.decode() for i in v.revision_git_entry(h.root,ref,endpoint)],'strict_suffix_errors':suffix,'prior_2896d24_accepted':prior,'final_accepted':new,'integration_errors':errors})
(OUT/'boundary-probe.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
