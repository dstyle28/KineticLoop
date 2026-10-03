# HG-047 independent PROTOCOL review

Verdict: **CHANGES_REQUIRED**. One BLOCKER; no other actionable findings.

Reviewed implementation/result: `47de76d206df89124ffe41c59b0b983af4defc97`.
Protected base: `391c9198fa8ec647e377a0572700bc7568468c85`.
Tested source: `2dc15b7c79b835197449ca705f82f221eee6f05d`.

## BLOCKER P-01 — Compressed storage metadata can substitute for execution stdout

`tools/harness/compact_evidence.py:199-207` returns decompressed bytes without
applying the reserved-storage classification used for ordinary evidence at
`:160-162`. An invalid inner `gzip-v1` envelope therefore fails when referenced
directly but becomes accepted evidence when its JSON is the raw payload of a valid
outer envelope. `tools/harness/validate_harness.py:2761-2766` then reads a pytest
summary from inner metadata instead of the missing execution output. This violates
storage-neutral M3 raw-proof semantics and the storage policy's prohibition on
missing-payload metadata supplying PASS.

Reproduced in disposable Git repositories using this reviewed implementation:

1. Capture an inner envelope for raw `1 skipped\n`, with timestamp
   `1 passed in 0.1s`; remove its gzip payload.
2. Capture that inner JSON as the raw bytes of an outer envelope, binding the real
   fixture tested revision, expected execution command, owner and zero exit code.
3. Direct inner `evidence_exists` is false; outer `evidence_exists` is true and
   `m3_pytest_count(read(outer))` is 1.
4. With the existing `tests/harness/test_m3_milestone_closure.py::History` fixture,
   replace only the first execution's stdout reference with that outer envelope;
   retain its ordinary JUnit/collection records, commit the appended own evidence,
   and call `m3_execution_evidence_errors` at the new exact revision. Result: `[]`.
   The same fixture's `compact_evidence.audit` also returns `errors: []`.

The missing inner payload was
`docs/exec-plans/evidence/HG-999/5a386ab1e2c5f19c1a3b19c682fefb2086888aaaf32f3d597cbf14b24ac8e96c.gz`.
These are synthetic review probes, not product or M3 execution evidence.

Required correction: reject reserved storage objects in decoded raw content, or
validate them under an explicit bounded policy before any availability/PASS oracle.
Add direct-versus-compressed parity regressions for nested/wrapped, missing,
corrupt and command/tested/exit-mismatched envelopes, including the complete M3
execution validator. A new implementation/result revision requires fresh review.

## Verification and preserved boundaries

- Independently inspected the protected-base diff, current indexed contracts,
  Protocol sections 1/2/8, DB sections 4/5, acceptance gates, and merged HG-045/HG-046
  governance. No runtime, migration, frozen baseline, requirement, historical,
  HG-045/HG-046 artifact, workflow or classifier changes. No frozen invariant,
  command owner, T1-T8 boundary, authorization, registry/S01 lock order, provider
  trust, production activation or executable-shadow semantics are changed.
- M3 membership, exit/check/digest/selector constants are unchanged (11 top-level
  M3 assignments compared), including KL-080 corrections. Ordinary M3 decoded
  log/JUnit/collection paths retain exact hashes, revisions, owner, tested SHA,
  command, cases/selectors, skip/failure and provenance checks; P-01 is the exception.
- Independently decoded all eight selected check envelopes at the reviewed SHA,
  enforcing their exact governance command, tested SHA and integer zero exit.
  Recovered harness output records 1,271 passed; unit output 241 passed; lint,
  typecheck and authority success remain in raw bytes. All stored/raw hashes and
  lengths validated. Committed budget: 40 evidence files, 41,195 bytes, no errors.
  Base/tested/reviewed ancestry and the linear governance tested suffix validate.
- Focused reviewer execution: 22 passed in 111.53s, exit 0, using existing Python
  3.12 environment, `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src`, pytest `-q -p
  no:cacheprovider`. Selection covers exact deterministic bytes, four bounded gzip
  mutations, revision/command/exit binding, wrong-revision payload, positive-cache
  constraints, mutable refs, object loss/corruption between sessions, repository/
  owner identity, bounded/nested/error cleanup, and all nine compact M3 semantic
  source cases. No full harness or DB rerun was performed for this review.
- Cache source inspection confirms only successful full immutable-revision
  proofs are cached per validation operation, keyed by repository/path/revision/
  tested/command/exit. Mutable refs reread and sessions reset. No cache regression
  was reproduced; the nested-envelope defect occurs without caching.
- Controller edits only pin and copy the installed decoder. Candidate import
  isolation and existing exact-head admission/full DB policy remain. Administrator
  installation, final exact-head App/full DB gate and applicable hosted quality/
  merge checks are still pending; this review does not authorize their omission.

Task-local check PASS, independent review, merge, M3, product and release PASS remain
separate. Production auto-activation stays disabled; real-data shadow remains
non-executable; related product/release requirements remain NOT_RUN. No live
configuration, installation, credential, source/result or other review was changed.

## Round-one evidence-reference bookkeeping correction

Removed `tools/harness/compact_evidence.py` from the review JSON's `evidence_refs`:
its source text contains reserved storage markers and is rejected by the evidence
decoder as `evidence-envelope-json`; it is not execution evidence. Source citations
remain in this report. The report and bound raw-proof envelopes support this
review; the remaining references validate at their original bound revisions.
The original round-one record remains in Git at `0fd0f3d`. This bookkeeping change
preserves CHANGES_REQUIRED, BLOCKER P-01 and reviewed SHA
`47de76d206df89124ffe41c59b0b983af4defc97`. It is not a review of the later fix and
does not close the finding or grant PASS.
