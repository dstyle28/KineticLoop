"""Exact Git retention and actual captured guard-case coverage, no rerun."""
import collections, json, subprocess, types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]; OUT=Path(__file__).resolve().parent
R='0b089d7d3b0212a4e5458dc7891cbb4e831cd6f6'; B='3ec7f7a38d974256a928c3687f63e4d90019e42b'; T='1cb64a1baef54fc7801e4084a18db962c3528a70'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def blob(path,rev=R):return git('show',rev+':'+path)
ce=types.ModuleType('retained_ce'); ce.__file__=str(ROOT/'tools/harness/compact_evidence.py');exec(compile(blob('tools/harness/compact_evidence.py'),'exact_decoder','exec'),ce.__dict__)
D='docs/exec-plans/evidence/HG-056/checks-repair-'+T+'-9bc7f4cc/'
env=json.loads(blob(D+'harness-execution.json.json'));stored=blob(env['payload']);assert ce.digest(stored)==env['stored_sha256']
raw=ce.decode(stored,env['kineticloop_evidence'],env['raw_bytes']);assert ce.digest(raw)==env['raw_sha256']
ids=json.loads(raw)['started'];assert len(ids)==len(set(ids))==951
names=['test_unrelated_owner_rejects_transient_admitted_binding_mutation','test_transient_foreign_conversion_cannot_disappear_before_head','test_unmapped_foreign_compact_mutation_and_restoration_fails','test_transient_reserved_new_map_on_pre_admission_branch_fails_globally','test_retained_map_missing_bound_objects_fail_closed','test_retained_map_recreation_on_base_imported_side_branch_rejects','test_handwritten_or_late_side_branch_map_after_base_import_rejects','test_reference_at_wrong_revision_cannot_borrow_payload_from_head']
counts={name:sum(name in identity for identity in ids) for name in names};assert all(counts.values())
protected_roots=['docs/exec-plans/evidence/HG-054','docs/exec-plans/evidence/HG-055','docs/exec-plans/governance/HG-054.yaml','docs/exec-plans/governance/HG-055.yaml','docs/exec-plans/evidence/KL-036','docs/exec-plans/reviews/KL-036']
assert not git('diff','--name-only',B,R,'--',*protected_roots).strip()
previous_R='d8aaf7c897e5a7653daa30b8d3bd906ba859652d'
oldroots=['docs/exec-plans/reviews/HG-056/security_round5','docs/exec-plans/reviews/HG-056/round5','docs/exec-plans/evidence/HG-056/checks-repair-9650c791e58aeb3aa79dcd20911863b33dc4d62f-4e68e83c','docs/exec-plans/evidence/HG-056/checks-repair-cadb6ccb3e5493548ee8f02803994cd0266ee084-f27e4fef']
historical_diff=git('diff','--name-status',previous_R,R,'--',*oldroots).decode().splitlines()
assert all(line.startswith('A\t') for line in historical_diff)
assert blob('docs/exec-plans/reviews/HG-056/round5/SECURITY_DATA_BOUNDARY.json')==blob('docs/exec-plans/reviews/HG-056/SECURITY_DATA_BOUNDARY.json')
S='docs/exec-plans/evidence/HG-056/checks-repair-cadb6ccb3e5493548ee8f02803994cd0266ee084-f27e4fef/'
run=json.loads(blob(S+'RUN.json'));check=next(c for c in run['checks'] if c['check_id']=='typecheck');assert check['result']=='FAIL' and check['exit_code']==1
failure=ce.read(ROOT,check['evidence_ref'],R,tested=run['tested_commit'],command=check['command'],exit_code=1)
probes=json.loads(blob(S+'additional-probes.json'));assert len(probes['observations'])==3 and all(x['envelope']==x['reencoding_record']=='plain' and x['expected']=='reject' for x in probes['observations'])
result={'R':R,'B':B,'T':T,'retention_negative_cases_in_actual951_execution':counts,'protected_prerequisite_and_KL036_roots_byte_unchanged':protected_roots,'round5_and_superseded_existing_evidence_byte_unchanged_since_original_R':oldroots,'review_suffix_additions':historical_diff,'superseded_typecheck':{'tested_commit':run['tested_commit'],'result':'FAIL','exit_code':1,'raw_bytes':len(failure),'raw_sha256':ce.digest(failure),'exact_read_binding_verified':True},'superseded_three_plain_hostile_observations_preserved':probes,'scope':'Guard bodies unchanged; actual captured negative-case identity/phase evidence verified independently. No guard fixture or historical full cycle rerun; no historical authority inferred.'}
(OUT/'retention-and-superseded.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'retention_cases':counts,'historical_and_prerequisite_roots_unchanged':True,'superseded_failures_preserved':True}))
