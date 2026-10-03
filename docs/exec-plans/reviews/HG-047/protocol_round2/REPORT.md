# HG-047 independent PROTOCOL review — round two

Verdict: **PASS**, with no open findings. This is a fresh protocol/code review of
`b7370940c8b9165f471322baaeef7d9e250dfac6`, not merge or release approval.
Protected base: `391c9198fa8ec647e377a0572700bc7568468c85`.
Selected tested source: `536c9b7b7c5bfa9b36a0b38e513bce34ed6eb31d`.

## Prior finding P-01 is closed at this reviewed revision

The prior PROTOCOL review at `47de76d206df89124ffe41c59b0b983af4defc97`
correctly found that valid outer gzip storage could deliver invalid inner storage
metadata to the M3 stdout oracle. The new check in
`tools/harness/compact_evidence.py:207-210` applies reserved-storage classification
after bounded single-member decompression and exact raw length/hash validation.
It rejects nested objects, wrapped objects and malformed reserved content before
availability, budget or semantic callers can accept them. It does not recursively
decode inner envelopes. Ordinary raw bytes retain their original representation.

An independently constructed synthetic probe reused the existing M3 `History`
fixture but constructed its malicious outer envelope manually. Its inner envelope
referred to a deleted payload containing a skipped-test log, while its timestamp
contained a positive pytest phrase. The otherwise valid outer envelope bound the
real fixture tested SHA, command, zero exit, lengths and hashes. The probe retained
the ordinary JUnit and collection records and used the complete
`m3_execution_evidence_errors` function, not just the decoder:

| Decoder loaded | Direct inner available | Outer available | Complete M3 result | Outer budget result |
|---|---|---|---|---|
| Prior immutable `47de76d` | false | true | no errors | no errors |
| Reviewed implementation | false | false | `milestone-m3-regression:evidence-nested-envelope` | `evidence-nested-envelope` |

The actual probe result is `probe.json` in this directory. Its fixture commit IDs
identify disposable synthetic Git history, not repository integration or real M3
execution evidence. This directly reproduces the old defect and demonstrates its
closure without relying on a stale-revision or unrelated failure.

## Independent validation

Reviewer execution: **52 passed in 355.81s (0:05:55), exit 0**. Exact stdout
is retained as `focused-pytest.log` in this directory.

The focused execution used the existing Python 3.12 environment from the repository
root, with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src` and
`/private/tmp/hg044-venv/bin/python -m pytest -q -p no:cacheprovider`, selecting:

- `tests/harness/test_compact_evidence.py::test_decoded_reserved_storage_cannot_bypass_direct_rejection`
- `tests/harness/test_compact_evidence.py::test_even_valid_nested_storage_is_rejected_and_capture_cleans_up`
- `tests/harness/test_compact_evidence.py::test_nonreserved_encoded_raw_is_lossless_in_plain_and_compact_forms`
- `tests/harness/test_compact_evidence.py::test_bounded_single_member_decoder`
- `tests/harness/test_compact_evidence.py::test_revision_command_and_exit_binding`
- `tests/harness/test_compact_evidence.py::test_reference_at_wrong_revision_cannot_borrow_payload_from_head`
- `tests/harness/test_compact_evidence.py::test_validation_session_reuses_only_complete_successful_proof`
- `tests/harness/test_compact_evidence.py::test_validation_session_never_caches_working_files_or_head`
- `tests/harness/test_m3_milestone_closure.py::test_compact_nested_storage_cannot_supply_m3_execution_stdout`
- `tests/harness/test_m3_milestone_closure.py::test_compact_regression_decodes_all_semantic_sources`

These cover the 35 new P-01 regressions, UTF-8/16/32 and wrapped/truncated forms,
missing/corrupt/command/tested/exit mismatches, valid nested rejection and capture
cleanup, ordinary encoded JSON, four bounded gzip failure shapes, exact provenance,
cache argument/lifetime behavior, and all nine compact M3 log/JUnit/collection
variants. Negative M3 nested tests assert the specific decoded-storage rejection.
Skipped JUnit, bad logs, wrong collection and ancillary-command mismatches fail;
ordinary matching compact proof succeeds. Source inspection additionally checked
BOM/endian and malformed-encoding handling and repository/owner/cache isolation.

All eight selected command envelopes were independently loaded from the immutable
reviewed Git revision and decoded with the governance record's exact command,
tested SHA and integer zero exit. Envelope/metadata timestamps and the execution
record agree. Stored and raw hashes/lengths, same-revision regular payloads and
HG-047 ownership validate. The recovered harness and unit output records **1,306**
and **241** passed respectively; applying the raw pytest oracle returns those
counts without failed/skipped substitutes. Lint reports success, typecheck reports
166 source files, and authority output records `HARNESS_CHECK_PASS tasks=77 active=74`.
The empty diff-check output is valid for its zero-exit command, not test-count proof.

The tested-to-reviewed governance suffix validates with no errors; the sole commit
is the committed result/evidence append. Protected-base diff hygiene passes.
The committed evidence budget is **90 files / 106,313 bytes**, with no errors.
Every current-index entry's SHA256 matches its bound Git blob. The preserved
`development-166bf3e/unit.json` decodes to exit 1 with 1 failed/240 passed;
`development-b30a9c6/authority.json` decodes to exit 1. Neither is selected PASS.
Historical round-one evidence/reviews retain their original revisions in Git.

## Protocol and authority boundaries

The complete protected-base source, test and contract diff, governance scope,
selected raw evidence and merged HG-045/HG-046 records were inspected independently.
Relevant frozen authority is Protocol v1.2 sections 0–3 and DB v0.2 sections 4–5,
plus current acceptance gates, M3 closure, result, review and storage contracts.
No frozen table, INV-01–INV-18 implementation, T1–T8 transaction boundary, command
owner, admission/authorization rule, registry/S01 lock order, provider trust or
production/shadow separation is changed. Runtime, migrations, DB tests, frozen
baseline, requirement set, workflows/classifier and merged HG-045/HG-046 artifacts
are unchanged. There is no SPEC_CHANGE_REQUIRED finding.

All 11 top-level M3 assignments are AST-identical to protected base, including
membership, corrective KL-080 contracts, ordered regression commands and exit
mappings. Exact revisions/hashes, owned raw references, result-command bindings,
positive counts, collection selectors, JUnit case equality and failure/skip
rejection remain in `tools/harness/validate_harness.py:2738-2813`.
No deferred layer, M1/M2 prerequisite, historical declaration or requirement is
promoted. The only controller edits add the trusted installed decoder to its pin
and worker-copy sets; candidate source does not supply that import.

The per-operation cache retains successful immutable full-SHA proof verdicts,
keyed by canonical repository, revision, path and tested/command/exit constraints.
Mutable references and failures reread, and exit resets the context. It changes
neither M3 raw-oracle evaluation nor persisted proof meaning.

## Remaining gates and evidence provenance

This PASS closes the protocol review finding only. GENERAL and
SECURITY_DATA_BOUNDARY must independently pass on this result revision. The reviewed
controller/validator/decoder release still needs separate administrator installation
with complete exact pins and final-head/controller admission, followed by the
mandatory full DB/App gate and applicable hosted quality/merge checks. No merge
recommendation is made before those gates are satisfied.

No full harness, unit, DB, hosted or live installed-controller execution was rerun
by this reviewer; full harness/unit figures above are independently checked committed
captures. Task, review, MERGED, M3, product and release PASS remain distinct.
Production auto-activation stays disabled, real-data shadow remains non-executable,
and related product/release requirements remain NOT_RUN.

This report and reviewer outputs are new files under `protocol_round2/`, absent
at the reviewed SHA. Their binding requires the later own-task linear
REVIEW_RECORD_ONLY suffix. The canonical report path existed at the reviewed SHA
with round-one content, so it is deliberately not used as this review's evidence
reference. Decoder source citations above are code-review citations, not raw-proof
references. No source/result, other review, installation, database, commit or push
was changed by this reviewer.
