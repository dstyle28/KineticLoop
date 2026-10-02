import hashlib, importlib.util, json, subprocess, tempfile, zlib
from pathlib import Path
import yaml
ROOT=Path.cwd()
OUT=ROOT/'docs/exec-plans/reviews/HG-043/final-8245480-protocol-raw'
SHA='8245480918251739339987de69bfe41fa0b39af5'
BASE='1099d85bd4aa76ec8221700e55b4e77a84479126'
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(path,sha=SHA): return git('show',sha+':'+path)
spec=importlib.util.spec_from_file_location('validator',ROOT/'tools/harness/validate_harness.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
record=yaml.safe_load(blob('docs/exec-plans/governance/HG-043.yaml'))
tested=record['tested_commit']
changed=git('diff','--name-only',BASE,SHA).decode().splitlines()
assert set(changed)==set(record['files_changed'])
assert not [p for p in changed if p.startswith(('src/','migrations/','.github/','docs/exec-plans/integrations/'))]
assert v.governance_suffix_errors(ROOT,tested,SHA,'HG-043','tested')==[]
checks=[]
for c in record['checks_run']:
 raw=blob(c['evidence_ref']); obj=json.loads(raw); data=obj['raw_utf8'].encode()
 assert obj['tested_commit']==tested and obj['base_commit']==BASE
 assert obj['check_id']==c['check_id'] and obj['command']==c['command'] and obj['evidence_ref']==c['evidence_ref']
 assert c['result']==obj['result']=='PASS' and obj['exit_code']==0
 assert hashlib.sha256(data).hexdigest()==obj['raw_sha256'] and len(data)==obj['raw_byte_count']
 assert v.revision_regular_file(ROOT,c['evidence_ref'],SHA)
 checks.append({'check_id':c['check_id'],'tested_commit':tested,'evidence_ref':c['evidence_ref'],'available_regular_blob':True,'raw_digest_and_size_valid':True,'output_tail':obj['raw_utf8'][-180:] if c['check_id']!='replay' else 'five protected-ancestry replay candidates'})
# Verify tested implementation bytes are precisely those reviewed, not convenient later replacements.
impl=['tools/harness/validate_harness.py','tests/harness/test_review_evidence_provenance.py','docs/harness/THREAD_REVIEW_CONTRACT.md','docs/harness/HARNESS_GOVERNANCE_CONTRACT.md']
assert all(blob(p,tested)==blob(p) for p in impl)
index=json.loads(blob('CURRENT_DOCUMENT_INDEX.json'))
for group in ('documents','machine_readable'):
 for item in index[group]:
  assert hashlib.sha256(blob(item['path'])).hexdigest()==item['sha256'],item['path']
prior='docs/exec-plans/reviews/HG-043/round-2896d24/PROTOCOL.json'
assert json.loads(blob(prior))['status']=='CHANGES_REQUIRED'
assert blob(prior)==blob('docs/exec-plans/reviews/HG-043/PROTOCOL.json')
missing=json.loads(blob('docs/exec-plans/evidence/HG-043/missing-object-787663f.json'))
assert missing['regular_file_predicate'] and missing['integration_errors']==[]
report={'reviewed_head_sha':SHA,'protected_base':BASE,'checks':checks,'declared_files_exact':True,'tested_implementation_identical_to_reviewed':impl,'frozen_and_product_paths_unchanged':True,'authority_hashes_verified':True,'prior_changes_required_and_missing_object_probe_preserved':True,'strict_tested_to_reviewed_governance_suffix':[]}
(OUT/'committed-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
