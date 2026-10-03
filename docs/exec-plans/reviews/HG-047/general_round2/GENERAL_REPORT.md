# HG-047 GENERAL review — round 2

Verdict: PASS, with one NONBLOCKING compatibility finding and no BLOCKER findings.
This is an independent GENERAL review of PR 91's immutable implementation/result
revision `b7370940c8b9165f471322baaeef7d9e250dfac6`, against protected base
`391c9198fa8ec647e377a0572700bc7568468c85`. The selected tested revision is
`536c9b7b7c5bfa9b36a0b38e513bce34ed6eb31d`.

This review makes no merge recommendation before the remaining final-head gates.
Task-local PASS, review PASS, App-bound full DB/hosted checks, merge, M3, product
requirements and release/activation remain separate. The full DB suite and active
controller installation were outside this reviewer’s execution scope.

## Scope and binding verification

Read AGENTS.md, CURRENT_DOCUMENT_INDEX.json, the pr-merge-reviewer skill, HG-047's
governance record and SCOPE, current governance/result/review/merge contracts,
Evidence Storage Policy, relevant controller installation contract, and merged
HG-045/HG-046 governance records. HG-047 is a governance change; its reviewed
result is `docs/exec-plans/governance/HG-047.yaml`.

Inspected the complete protected-base diff, the new decoder and tests, validator
call-site changes, controller changes, policies, index/manifest changes, and
committed evidence. `general_round2/verification.json` records mechanical checks:

- All 109 changed paths are exactly declared in the governance result and match
  the HG-047 allowlist. No task packet or requirement-status change is introduced.
- Base → tested → reviewed ancestry holds. The single tested-to-result commit is
  linear, changes only the governance record, and adds 18 new HG-047 evidence
  files; existing task evidence is not overwritten in that suffix.
- Frozen files and FROZEN_BASELINE, runtime, migrations, DB tests, requirements,
  backlog/traceability, KL-080, workflows, DB classifier, other controller assets,
  and merged HG-045/HG-046 governance/evidence/reviews are byte-identical to base.
- Index/manifest entries retain their identities and paths. All current hashes and
  byte counts satisfy the derived metadata validators. `git diff --check` passes.
- The unchanged classifier requires full database execution for this diff.
- Prospective compact budget passes: 90 evidence/review artifacts, 106,313 stored
  bytes at the reviewed SHA, before this review-only suffix.

## Implementation assessment

The decoder resolves an exact commit once, requires normalized regular Git blobs,
keeps manifest and payload at that same revision, and checks owner/content-address
naming, command/tested/exit bindings, stored length/hash and bounded raw length/hash.
Single-member gzip rejects truncation, unused/trailing data and unconsumed input.
Prospective budgets leave untouched historical plain evidence outside the budget.
The remaining M3 test/log/JUnit/collection/selector/provenance oracles remain in
place and operate on recovered bytes, not navigation counts.

The P-01 change applies reserved-storage classification after decompression and
before returning raw bytes to availability or semantic callers. Nested metadata
is rejected rather than recursively interpreted as command stdout. The new cases
cover 24 encoded direct/compressed negative variants, valid-nested capture cleanup,
three ordinary encoded JSON positive cases, and seven complete M3 execution
negative variants: 35 new cases in total. M3 variants preserve the normal adjacent
JUnit/collection proof and require the specific decoded-storage rejection.

The per-operation cache stores only successful availability verdicts for full
40-character revision keys. It binds canonical root, path, tested SHA, command and
exit constraint, is capped at 4,096 entries, shares only nested operation scope,
and resets in finally. Mutable refs, working files and failed reads are not
memoized. The explicit trust assumption is immutable Git objects during one
validation operation; fresh operations recheck lost/corrupt objects.

`local_gate.py` differs only by adding `compact_evidence.py` to ASSETS and the
installed worker-copy tuple. The validator imports the decoder beside its own
file, not from candidate import search paths. Missing/changed/symlinked installed
bytes remain rejected by the existing pin check. Installation, keys, admissions,
workflow protections and active trusted controller state were not changed here.

## Evidence and independent execution

The read-only verification script first checked candidate source bytes against the
reviewed Git blobs, then independently decompressed all 36 committed HG-047
compact envelopes with bounded zlib. Every stored/raw digest and length matched,
all payloads matched deterministic gzip capture, and the production reader
returned the identical bytes at the bound revision.

All eight selected result checks exactly match execution metadata, commands,
tested SHA, timestamps, exit zero and envelope paths. Raw output confirms:

| Selected check | Observed raw result |
|---|---|
| Harness | 1,306 passed in 2,304.77 seconds |
| Unit | 241 passed in 183.57 seconds |
| Lint | All checks passed |
| Typecheck | No issues in 166 source files |
| Authority | HARNESS_CHECK_PASS, tasks=77, active=74 |
| Scope | PASS; protected paths unchanged |
| Source diff | Empty output, recorded exit zero |
| Benchmark | PASS; fewer Git calls for all three five-read workloads |

The earlier development-166bf3e unit failure and development-b30a9c6 authority
failure remain in committed evidence with nonzero exits and their failure raw
bytes. They are not selected PASS checks. The original round-one P-01 finding and
reviewed SHA remain recoverable from Git; this review uses the new result SHA.

Independent focused command (from the candidate worktree):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /private/tmp/hg044-venv/bin/python -m pytest -q -p no:cacheprovider tests/harness/test_compact_evidence.py tests/harness/test_local_gate.py -k 'validation_session or validation_cache or validation_operation or decoded_reserved_storage or even_valid_nested_storage or nonreserved_encoded_raw or installed_compact_decoder or isolated_validator or worker_copies_decoder'
```

Result: **41 passed, 231 deselected in 20.06 seconds**, exit zero. The exact raw
output is `general_round2/focused.log`. No full 1,306-test rerun or DB run is
claimed by this reviewer. An initial reviewer script assumed authority output was
only a PASS token; its assertion was corrected to preserve and validate the actual
`tasks=77 active=74` suffix, then the complete verifier passed.

## G-01 — NONBLOCKING: ordinary duplicate-key JSON can be rejected

At `tools/harness/compact_evidence.py:129`, `storage_pairs` calls `unique` before
establishing that an object contains reserved storage fields. Ordinary raw JSON
`{"event":"a","x":1,"x":2}` remains byte-identical, but changing the event value
to `"\u0061"` triggers JSON inspection and `evidence-duplicate-key`, despite having
no reserved fields. The independent isolated Git reproduction is recorded in
`general_round2/ordinary_json_probe.json` with its script beside it.

This narrows the policy's ordinary-output losslessness claim. It is nonblocking
because it rejects evidence explicitly; it neither corrupts accepted bytes nor
creates a false PASS or weakens provenance, and it does not affect the selected
execution proof. A future storage-compatibility correction should separate
reserved-object duplicate validation from preservation of unreserved raw bytes
and add literal/escaped parity coverage.

## Persistence and remaining gates

The canonical GENERAL record binds the exact reviewed result SHA and cites this
new report and proof under `general_round2/`, all absent at that SHA. The canonical
old report path already exists there, so it is only a pointer and is not cited as
new review evidence. New review references must be committed through the exact
linear HG-047 REVIEW_RECORD_ONLY suffix before the final merge-gate validation.

Fresh PROTOCOL and SECURITY_DATA_BOUNDARY reviews, the reviewed pinned controller
installation, exact final-head admission and mandatory App-bound full DB plus
applicable hosted quality/merge checks remain the coordinator’s next gates.
