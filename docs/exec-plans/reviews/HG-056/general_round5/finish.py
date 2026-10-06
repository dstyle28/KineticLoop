"""Finish bounded independent review metadata without repeating verified decodes."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
import jsonschema
import yaml
ROOT=Path(__file__).resolve().parents[5]
OUT=Path(__file__).resolve().parent
B='3ec7f7a38d974256a928c3687f63e4d90019e42b'
T='9650c791e58aeb3aa79dcd20911863b33dc4d62f'
R='d8aaf7c897e5a7653daa30b8d3bd906ba859652d'
OLD='f535ab5cf257c8c8268e0415cc61294d6262bd7b'
D='docs/exec-plans/evidence/HG-056/checks-repair-'+T+'-4e68e83c/'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(path,rev=R):
 entry=git('ls-tree','-z',rev,'--',path)
 assert entry.startswith((b'100644 blob ',b'100755 blob ')) and entry.split(b'\t')[1].rstrip(b'\0').decode()==path
 return git('show',rev+':'+path)
def sha(data):return hashlib.sha256(data).hexdigest()
def functions(data):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(data).body if isinstance(n,ast.FunctionDef)}
run=json.loads(blob(D+'RUN.json'))
for kind in ('GENERAL','SECURITY_DATA_BOUNDARY'):
 assert blob('docs/exec-plans/reviews/HG-056/round4/'+kind+'.json')==blob('docs/exec-plans/reviews/HG-056/'+kind+'.json',OLD)
old_paths=git('ls-tree','-r','--name-only',OLD,'--','docs/exec-plans/reviews/HG-056').decode().splitlines()
assert all(blob(p,OLD)==blob(p) for p in old_paths if p not in ('docs/exec-plans/reviews/HG-056/GENERAL.json','docs/exec-plans/reviews/HG-056/SECURITY_DATA_BOUNDARY.json'))
prior_paths=git('ls-tree','-r','--name-only',T,'--','docs/exec-plans/evidence/HG-056').decode().splitlines()
assert all(blob(p,T)==blob(p) for p in prior_paths)
assert blob(D+'ROUND4_RESULT.yaml')==blob('docs/exec-plans/governance/HG-056.yaml',OLD)
try:yaml.safe_load(blob('docs/exec-plans/governance/HG-056.yaml'))
except yaml.YAMLError as error:
 schema={'status':'FAIL','exception':type(error).__name__,'context_line':error.context_mark.line+1,'problem_line':error.problem_mark.line+1,'problem':error.problem}
else:raise AssertionError('expected confirmed result parse failure')
for section in ('documents','machine_readable'):
 old=json.loads(blob('CURRENT_DOCUMENT_INDEX.json',B))[section]
 new=json.loads(blob('CURRENT_DOCUMENT_INDEX.json'))[section]
 assert len(old)==len(new)
 for a,b in zip(old,new):
  assert {k:v for k,v in a.items() if k!='sha256'}=={k:v for k,v in b.items() if k!='sha256'}
  assert sha(blob(b['path']))==b['sha256']
old=json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json',B))
new=json.loads(blob('HARNESS_DOCUMENT_MANIFEST.json'))
assert {k:v for k,v in old.items() if k!='files'}=={k:v for k,v in new.items() if k!='files'}
old_rows={x['path']:x for x in old['files']}
new_rows={x['path']:x for x in new['files']}
assert old_rows.keys()<=new_rows.keys()
for path,row in new_rows.items():
 assert path in old_rows or path.startswith('docs/exec-plans/evidence/HG-056/')
 raw=blob(path)
 assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
old_decoder=functions(blob('tools/harness/compact_evidence.py',B))
new_decoder=functions(blob('tools/harness/compact_evidence.py'))
assert sorted(set(new_decoder)-set(old_decoder))==['source_target_keys','source_write_keys']
assert sorted(n for n in old_decoder if old_decoder[n]!=new_decoder[n])==['envelope','reserved_ascii']
old_v=functions(blob('tools/harness/validate_harness.py',B))
new_v=functions(blob('tools/harness/validate_harness.py'))
assert old_v.keys()==new_v.keys() and sorted(n for n in old_v if old_v[n]!=new_v[n])==['governance_allowed_patterns','validate']
spec=importlib.util.spec_from_file_location('review_decoder',ROOT/'tools/harness/compact_evidence.py')
ce=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)
assert (ROOT/'tools/harness/compact_evidence.py').read_bytes()==blob('tools/harness/compact_evidence.py')
original_rev='f93364d90aaae9b0b62706fd4e4fe395a8cd8ec5'
original_path='docs/exec-plans/reviews/KL-036/SECURITY_DATA_BOUNDARY/audit.py'
original=blob(original_path,original_rev)
assert git('ls-tree',original_rev,'--',original_path).startswith(b'100644 blob cde206aee1eb240862863069104ad291ff98dedb\t')
assert len(original)==8063 and sha(original)=='a602ee684cdd7b4d8169388d2a2fe821fc6bc5beadf0d69a593c2ed260ffe382'
assert original==blob('docs/exec-plans/evidence/HG-056/original-reader.fixture')
assert ce.envelope(original) is None and ce.reencoding_record(original) is None
assert ce.read(ROOT,original_path,original_rev)==original
blocker=json.loads(blob('docs/exec-plans/evidence/HG-056/diagnostics/hg056-kl036-history-blocker.json'))
assert not git('ls-tree',blocker['revision'],'--',blocker['path'])
assert git('ls-tree',blocker['parent'],'--',blocker['path']).startswith(b'100644 blob ')
cadb_paths=[p for p in prior_paths if 'checks-repair-cadb6ccb' in p]
cadb_run=json.loads(blob(next(p for p in cadb_paths if p.endswith('/RUN.json'))))
assert next(x for x in cadb_run['checks'] if x['check_id']=='typecheck')['result']=='FAIL'
probes=json.loads(blob(next(p for p in cadb_paths if p.endswith('/additional-probes.json'))))
assert len(probes['observations'])==3 and all(x['envelope']=='plain' and x['reencoding_record']=='plain' and x['expected']=='reject' for x in probes['observations'])
report={'purpose':'INDEPENDENT_GENERAL_METADATA_ONLY','B':B,'T':T,'R':R,'governance_schema':schema,
 'initial_verifier_attempts':[{'invocations':2,'stage':'governance safe_load','observed_failure':'ScannerError from actual result on the retained invocation','first_invocation_output':'Not retained after tool yielded; session identifier was inadvertently omitted from displayed output'},
 {'runs':1,'stage':'round4 copy origin comparison','outcome':'reviewer assertion failure: compared to result commit0c rather than review-record commit f535; corrected in finish.py'}],
 'checks_verified_before_verifier_exceptions':[{k:x[k] for k in ('check_id','command','result','exit_code','raw_bytes','raw_sha256')} for x in run['checks']],
 'execution_assertions_completed_before_exceptions':{'executed':892,'compact':888,'phases':2676,'workers':['gw0','gw1'],'junit_and_worker_identity_sets':'PASS','collection_only':2118,'collection_starts':0,'collection_reports':0,'collection_junit_cases':0,'isolated_stdout':103},
 'preceding_verifier_assertions':'Seven bound reads, all artifact manifest hashes, phase identities, literal scope, regular Git modes, frozen/requirement/backlog/map bytes, exact T-R parent and source-equivalent suffix all passed before result safe_load.',
 'isolated_identity_artifact_claimed':False,'source_scope_review':'PASS','derived_hashes_and_manifest':'PASS',
 'prior_review_artifacts_unchanged':len(old_paths)-2,'round4_copies_exact':True,'round4_result_snapshot_exact':True,
 'prior_evidence_unchanged_T_R':len(prior_paths),'cadb_typecheck':'FAIL_PRESERVED','cadb_self_probes':3,
 'prior_required_outcomes':json.loads(blob(D+'PRIOR_REQUIRED_CHECKS.json')),
 'original_helper':{'pins':'PASS','plain_classification':'PASS','bound_read_byte_identical':True,'executed':False},
 'external_unmapped_deletion_tree_confirmed':True,'immutable_whole_oracle':'FAIL_RETAINED_NO_RERUN',
 'source_inspection_authority':'NOT_IMPLEMENTED','decoder_new_functions':['source_target_keys','source_write_keys'],
 'decoder_changed_functions':['envelope','reserved_ascii'],'validator_changed_functions':['governance_allowed_patterns','validate'],
 'new_general_defects':1,'exact_R_storage_audit':'ROOT_OWNED_NOT_CLAIMED','whole_cycles_rerun':False,
 'independent_execution':'Own verifier/finish metadata checks only; no input/helper execution, private historical payload/DB/network/install/admit/App/merge.'}
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
review=json.loads((OUT/'GENERAL.json').read_text())
jsonschema.validate(review,json.loads(blob('THREAD_REVIEW.schema.json')))
assert (OUT/'GENERAL.json').read_bytes()==(ROOT/'docs/exec-plans/reviews/HG-056/GENERAL.json').read_bytes()
assert review['reviewed_head_sha']==R and review['status']=='CHANGES_REQUIRED'
for name in ('verify.py','finish.py','report.json','REVIEW.md','GENERAL.json'):
 data=(OUT/name).read_bytes()
 assert len(data)<=ce.PLAIN_LIMIT and ce.envelope(data) is None and ce.reencoding_record(data) is None
validation={'status':'PASS','review_schema':'PASS','reviewed_head_sha':R,'review_status':'CHANGES_REQUIRED','governance_result_schema':'FAIL','own_outputs_plain':'PASS','result_not_modified':True,'canonical_copy_identical':True}
(OUT/'review-validation.json').write_text(json.dumps(validation,indent=2)+'\n')
print(json.dumps(validation,indent=2))
