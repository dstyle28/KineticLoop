"""Persist exact-SHA specialist review and validate own bookkeeping."""
import json, subprocess, sys
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[5];OUT=Path(__file__).resolve().parent
R='0b089d7d3b0212a4e5458dc7891cbb4e831cd6f6';T='1cb64a1baef54fc7801e4084a18db962c3528a70';B='3ec7f7a38d974256a928c3687f63e4d90019e42b'
def blob(path):return subprocess.check_output(['git','show',R+':'+path],cwd=ROOT)
prev=json.loads(blob('docs/exec-plans/reviews/HG-056/round5/SECURITY_DATA_BOUNDARY.json'))
findings=[x for x in prev['findings'] if x['id'] in ('HG056-S4','HG056-S5')]
for x in findings:x['evidence_ref']='docs/exec-plans/reviews/HG-056/security_round6/evidence-bindings.json'
findings[1]['detail']='Source-inspection-purpose availability and suffix acceptance remain NOT_IMPLEMENTED under the separately deferred root authority decision; strict existing availability/storage/M3/cache/suffix guards remain required. Exact-R lossless bound evidence independently verifies 951 starts, all 947 compact identities, 2853 passed setup/call/teardown reports, matching workers and JUnit, 2177 collect-only identities with zero starts/reports/JUnit, isolated stdout103, all seven scoped checks PASS and no capture errors. All eleven original outcomes retain their actual bindings and failures. Prior round5 and superseded bytes, typecheckFAIL and three plain-hostile observations remain retained. These scoped checks do not replace required complete cycles, complete immutable compatibility or root-owned controller/admission/App/hosted gates; root owns the separate exact-R storage guard. No duplicate or known-failing full-cycle/CI/immutable-KL036 rerun occurred. Governance remains BLOCKED.'
refs=['docs/exec-plans/reviews/HG-056/security_round6/'+p.name for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SECURITY_DATA_BOUNDARY.json']
refs+=['docs/exec-plans/evidence/HG-056/PACKET.md','docs/exec-plans/governance/HG-056.yaml','docs/exec-plans/reviews/HG-056/round5/SECURITY_DATA_BOUNDARY.json','docs/exec-plans/evidence/HG-056/checks-repair-'+T+'-9bc7f4cc/RUN.json','docs/exec-plans/evidence/HG-056/checks-repair-'+T+'-9bc7f4cc/SOURCE_INSPECTION_ADJUDICATION.md']
review={'task_identity':'harness-governance-v0.1/HG-056','reviewed_head_sha':R,'review_type':'SECURITY_DATA_BOUNDARY','status':'CHANGES_REQUIRED','findings':findings,'evidence_refs':refs,'closed_findings_at_reviewed_revision':[{'id':'HG056-S'+str(i),'status':'CLOSED_IN_REVIEWED_FORMS','evidence_ref':'docs/exec-plans/reviews/HG-056/security_round6/classifier-probes.json'} for i in (1,2,3,6,7,8,9,10,11)],'review_contract_version':'v0.2'}
text='''Independent SECURITY_DATA_BOUNDARY review, harness-governance-v0.1/HG-056.

Reviewed R=0b089d7d3b0212a4e5458dc7891cbb4e831cd6f6, tested T=1cb64a1baef54fc7801e4084a18db962c3528a70, protected B=3ec7f7a38d974256a928c3687f63e4d90019e42b. Status CHANGES_REQUIRED: no new source blocker in these bounded original-scope forms; external S4 and S5 remain.

The repository pr-merge-reviewer skill, AGENTS/current authority index, packet, storage/governance/review contracts and existing schemas were read. Exact Git decoder source and committed evidence were independently inspected. Earlier verifier mechanics were adapted; every assertion reran against this R/T and prior reports do not supply a current verdict.

960 classifier pairs cover 40 concrete controls/forms, eight UTF encoding views and plain/gzip/XZ recovery. S1/S2/S6–S11 actual forms reject; S3 array/default-string compatibility and ordinary read expressions remain plain. Bytes-literal wrappers, malformed RHS, encoded comment targets and multiline comment/prose targets reject. All 60 temporary plain-file read probes for S11 reject. Exact original helper pins and byte-identical bound read are unchanged; helper/input never executes. Parser native nesting exhaustion and simulated MemoryError/RecursionError produce classification errors in both classifiers.

Actual 3,257,569-byte captured collector stdout and a doubled copy classify plain. AST parse work is 55,878/94,047 calls (1.683x) and 1,016,539,185/1,593,220,932 parsed bytes (1.567x), 7.158/12.084 seconds on this runner. Source resets local spans within logical statements; this observed input avoids the previous preceding-token rescan growth. No universal complexity proof or new production budget is inferred.

Exact lossless evidence verifies seven scoped PASS checks, 951 distinct executed identities including all 947 compact cases, 2853 passing phases, worker/JUnit sets and zero failures/skips. Full collect-only 2177 contains zero execution. Original eleven outcomes and immutable KL036 expected2/reached1/unmapped-consolidation failure remain actual; no forbidden rerun/relabel occurred. Codec, owner/revision/integrity/ancestry/retention/archival/history bodies remain structurally identical to B. Actual negative-case identities cover foreign/transient mutations, retained missing objects, side branches and wrong-revision borrowing; protected prerequisite/KL036 roots and existing superseded evidence remain unchanged. Deferred source-purpose acceptance/cache/suffix authority remains NOT_IMPLEMENTED.

Bounded tool/check failures are explicitly retained in bounded-tool-failures.json: first profiling input had zero AST work, an incorrect proposal path, two too-strict historical bookkeeping comparisons, and a planned-validation-file write/check ordering assertion. Correct paths/normal review-suffix additions were inspected and corrected; none was hidden or labeled task PASS. Classifier report is losslessly XZ captured under unchanged storage budgets. Root owns exact-R storage audit, controller/admission/App/hosted/fullDB and merge. No private historical logs, network, credentials, DB or input/helper execution was used. Writes are confined to this review subtree and canonical SECURITY record; no commits/source/result edits.
'''
(OUT/'REVIEW.md').write_text(text)
review['evidence_refs'].append('docs/exec-plans/reviews/HG-056/security_round6/REVIEW.md')
review['evidence_refs'].append('docs/exec-plans/reviews/HG-056/security_round6/review-validation.json')
review['evidence_refs']=list(dict.fromkeys(review['evidence_refs']))
jsonschema.validate(review,json.loads(blob('THREAD_REVIEW.schema.json')))
for path in review['evidence_refs']:
 if path.endswith('/review-validation.json'):continue
 assert (ROOT/path).is_file() and not (ROOT/path).is_symlink()
for path in (OUT/'SECURITY_DATA_BOUNDARY.json',ROOT/'docs/exec-plans/reviews/HG-056/SECURITY_DATA_BOUNDARY.json'):path.write_text(json.dumps(review,indent=2)+'\n')
result={'R':R,'T':T,'B':B,'status':'CHANGES_REQUIRED','blocking_findings':[x['id'] for x in findings],'schema':'PASS','evidence_refs_regular_files':True,'maximum_plain_review_blob_bytes':max(p.stat().st_size for p in OUT.iterdir() if p.is_file() and p.suffix!='.xz'),'no_commits_source_or_result_writes':True,'review_evidence_binding':'New own-task review paths resolve only under mechanically verified linear REVIEW_RECORD_ONLY suffix; ordinary pre-review task refs retain R binding. Working existence here is bookkeeping validation, not substitute for Git binding.'}
(OUT/'review-validation.json').write_text(json.dumps(result,indent=2)+'\n')
assert all((ROOT/path).is_file() and not (ROOT/path).is_symlink() for path in review['evidence_refs'])
print(json.dumps(result,indent=2))
