"""Persist the independent GENERAL review, bound to the fixed reviewed revision."""
import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
R = '0b089d7d3b0212a4e5458dc7891cbb4e831cd6f6'
D = 'docs/exec-plans/evidence/HG-056/checks-repair-1cb64a1baef54fc7801e4084a18db962c3528a70-9bc7f4cc/'
report = json.loads((OUT / 'report.json').read_text())
assert report['R'] == R and report['governance_schema_and_bindings'] == 'PASS'
assert report['new_general_implementation_defects'] == 0
assert report['execution']['harness']['reports'] == 2853
assert report['execution']['full-collection']['starts'] == 0
review = {
    'task_identity': 'harness-governance-v0.1/HG-056',
    'reviewed_head_sha': R,
    'review_type': 'GENERAL',
    'status': 'CHANGES_REQUIRED',
    'findings': [
        {
            'id': 'HG056-G1', 'classification': 'BLOCKER', 'origin': 'EXTERNAL_IMMUTABLE_ORACLE',
            'title': 'Required complete KL036 compatibility remains unsatisfied',
            'body': 'Retained actual immutable H1fee/B3ec compatibility has two expected maps, one validated map and real history/storage errors. Exact Git tree metadata confirms the unmapped e81cc2cc payload deletion without reading private payloads. The original helper remains pinned and its bound read is byte-identical plain content. These facts do not close the incomplete whole-oracle inventory. No known-failing compatibility rerun occurred.',
            'required_action': 'Keep FAIL/BLOCKED pending separate prospective root recovery authority. Preserve history and full inventory; no consolidation permission, filtered verdict, swallowed error or weakened ancestry/storage guard is authorized under HG056.'
        },
        {
            'id': 'HG056-G2', 'classification': 'BLOCKER', 'origin': 'DEFERRED_PROSPECTIVE_AUTHORITY',
            'title': 'Source-inspection acceptance awaits separate prospective authority',
            'body': 'Root adjudication leaves inspection-purpose availability/suffix acceptance NOT_IMPLEMENTED/BLOCKED under this grant. The committed proposal supplies no current acceptance. Exact base-to-reviewed AST comparison preserves retrieval, execution, M3, availability, cache and suffix functions; validator changes only add literal HG056 scope and mandatory SECURITY review.',
            'required_action': 'Preserve the proposal and strict boundaries until separately approved prospective governance is reviewed. No source/path/hash/owner exemption, HEAD borrowing, cache-purpose shortcut or suffix bypass is authorized here.'
        },
        {
            'id': 'HG056-G4', 'classification': 'REQUIRED_FOLLOWUP', 'origin': 'MISSING_FINAL_GATES',
            'title': 'Whole-cycle and exact-head root gates remain incomplete',
            'body': 'Seven exact-tested captures bind at reviewed R: 951 distinct executed cases including all947 compact cases, 2853 passed setup/call/teardown reports, and matching two-worker/JUnit identities. Full2177 collection has zero starts/reports/JUnit cases. Isolated103 is supported by stdout, alongside scope/lint/typecheck/diff. These scoped checks do not replace whole cycles or relabel earlier failures. Original and superseded outcomes, interruption and partial/recovered captures remain unchanged. Exact-head storage audit is separately root-owned and is not claimed by this review; protected-base CI guard, installation/admission, hosted/App/fullDB and merge acceptance remain incomplete.',
            'required_action': 'Keep BLOCKED and preserve actual outcomes. Complete justified fresh-revision and root-owned gates after external and authority blockers resolve. Collection cannot supply execution PASS; this review grants no installation, admission, duplicate full-cycle execution or merge authority.'
        }
    ],
    'evidence_refs': [
        'docs/exec-plans/evidence/HG-056/PACKET.md',
        'docs/exec-plans/governance/HG-056.yaml', D + 'RUN.json', D + 'PRIOR_REQUIRED_CHECKS.json',
        D + 'ROUND5_RESULT.yaml', D + 'RESULT_ASSEMBLY.json', D + 'SOURCE_INSPECTION_ADJUDICATION.md',
        'docs/exec-plans/evidence/HG-056/diagnostics/hg056-kl036-history-blocker.json',
        'docs/exec-plans/reviews/HG-056/round5/GENERAL.json',
        'docs/exec-plans/reviews/HG-056/round5/SECURITY_DATA_BOUNDARY.json',
        'docs/exec-plans/reviews/HG-056/general_round6/verify.py',
        'docs/exec-plans/reviews/HG-056/general_round6/report.json',
        'docs/exec-plans/reviews/HG-056/general_round6/REVIEW.md',
        'docs/exec-plans/reviews/HG-056/general_round6/finish.py',
        'docs/exec-plans/reviews/HG-056/general_round6/review-validation.json'
    ],
    'review_contract_version': 'v0.2'
}
jsonschema.validate(review, json.loads((ROOT / 'THREAD_REVIEW.schema.json').read_text()))
raw = json.dumps(review, indent=2) + '\n'
(OUT / 'GENERAL.json').write_text(raw)
(OUT.parent / 'GENERAL.json').write_text(raw)
scaling = report['collection_scaling']
text = f'''# HG056 independent GENERAL review, round 6

Reviewed R `{R}`; tested T `{report['T']}`; protected B `{report['B']}`.
Recommendation: **CHANGES_REQUIRED**. No new concrete GENERAL implementation defect
was found in the authorized classifier repair. G1 and G2 remain BLOCKER; G4 remains
required follow-up. The retained whole-oracle failures and deferred prospective
source-inspection authority prevent acceptance.

G5 is closed at this new implementation/result revision. The current governance YAML
parses and conforms to the existing schema, binds exact B/T, all changed files and
the seven check commands/captures. The prior invalid result, its independent reviews
and its exact bytes remain preserved. The result remains BLOCKED.

The seven losslessly recovered captures bind actual tested T and reviewed R. The
affected run executed 951 distinct cases, including all 947 compact cases; every
case has passed setup/call/teardown, the exact collection list is present on both
workers, and all 951 JUnit identities agree including class methods. Full collection
contains 2177 distinct ordered identities, zero execution starts/reports and zero
JUnit cases. Isolated stdout supports 103 passes; no isolated identity artifact is
claimed. Scope, lint, typecheck and diff captures bind exact commands and exits.

The exact base-to-R diff stays in literal packet scope, with regular Git blobs.
Frozen files and requirement/backlog/history projections remain identical. Index
hashes and manifest entries were independently checked. The only changed existing
decoder functions are classification and envelope recognition; retrieval, codecs,
budgets, original/source/base/ancestry/per-edge/foreign/archival/retained and suffix
guards keep their code. Validator changes add literal HG056 scope and SECURITY
review enforcement only. Source and authority bytes are identical at T and R.

The new statement/target peeks remove the old repeated all-preceding-token scan.
Independent instrumentation of actual current collection stdout, SHA-bound by its
capture, classified both inputs plain: {scaling[0]['bytes']} bytes / {scaling[0]['parse_calls']}
AST calls for one copy; {scaling[1]['bytes']} bytes / {scaling[1]['parse_calls']} AST calls for
two copies. This is observed collector-shaped work scaling, not a universal runtime
claim or a new production budget. Static inspection plus inert bounded probes
confirm the byte and multiline comment/prose target denials, corresponding ordinary
reads, and fail-closed native depth exhaustion. No fixture/helper/input was executed.

All old evidence and review bookkeeping checked from prior R remain unchanged,
except the explicitly appended preparation history and canonical current reviews.
Round5 canonical copies are exact at R. Original helper mode/blob/length/SHA256 are
unchanged, and its plain bound retrieval is byte-identical. Retained actual KL036
compatibility still has expected2/reached1 maps and real errors; only public Git tree
metadata of the deletion was inspected. Known failing compatibility, whole cycles,
CI and root's own exact-R storage audit were not rerun or duplicated.

Two reviewer-only verifier errors were preserved in report.json: wrong PyYAML
exception namespace, then comparing canonical round5 copies at the earlier reviewed
SHA before those review records existed. Both corrections touched only this verifier;
current implementation checks had passed at each stage. The corrected verifier
completed. No implementation/evidence output was modified or relabeled.

New review files bind only through a future exact linear own REVIEW_RECORD_ONLY
append. They supply independent review bookkeeping, never pre-review task execution
evidence or PASS. Root owns remaining storage/CI/installer/admission/App/fullDB/merge
gates. No DB, network, credentials, configuration or private historical logs were used.
'''
(OUT / 'REVIEW.md').write_text(text)
spec = importlib.util.spec_from_file_location('review_bookkeeping_decoder', ROOT / 'tools/harness/compact_evidence.py')
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)
checks = []
for path in sorted(OUT.iterdir()) + [OUT.parent / 'GENERAL.json']:
    if path.is_file() and path.name != 'review-validation.json':
        data = path.read_bytes()
        assert ce.envelope(data) is None and ce.reencoding_record(data) is None, path
        checks.append({'path': str(path.relative_to(ROOT)), 'bytes': len(data),
                       'sha256': hashlib.sha256(data).hexdigest(), 'classification': 'plain'})
validation = {'reviewed_head_sha': R, 'status': 'CHANGES_REQUIRED', 'review_schema': 'PASS',
              'canonical_copy_identical': True, 'review_bookkeeping_classification': checks,
              'scope': 'Only own GENERAL and general_round6 bookkeeping; no commits or source/result writes.'}
(OUT / 'review-validation.json').write_text(json.dumps(validation, indent=2) + '\n')
assert ce.envelope((OUT / 'review-validation.json').read_bytes()) is None
assert ce.reencoding_record((OUT / 'review-validation.json').read_bytes()) is None
print(json.dumps({'schema': 'PASS', 'R': R, 'status': 'CHANGES_REQUIRED', 'G5': 'CLOSED', 'bookkeeping_files': len(checks)}))
