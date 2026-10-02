# HG-046 independent PROTOCOL r3

Reviewed head: `fb720bc37c8e9ec436b0673de71c282f9778e6a8`.
Assigned protected base: `26906bd7f4444914c228e98377f2b164fee0dd5d`.
Selected tested source: `fb7d62b73d80a56b8bce1d0f7cbd29f14aff77ab`.

CHANGES_REQUIRED: the mixed BOM/body encoding route still violates the prospective
policy's fail-closed guarantee for malformed reserved storage records. Independent
source inspection finds that `envelope()` chooses the BOM's encoding, successfully
decodes the conflicting body into NUL-interleaved text, then returns `None` from its
byte-marker prefilter. `read()` returns the original bytes as plain evidence;
availability and budget paths consequently skip payload and execution metadata
guards. The SECURITY r3 retained guarded probe independently reproduces both
UTF-16LE BOM + UTF-32LE body and UTF-16BE BOM + UTF-32BE body: absent payload,
mismatched tested/command/exit, availability true, identical plain retrieval and
budget errors empty. Its actual exit 1 is an assertion detecting the bypass, never
a PASS. I decoded its captured output and inspected `verify.py`; I did not rerun
that probe. Detect/reject malformed reserved encodings before plain fallback,
while preserving genuinely opaque historical bytes, and add focused regressions.

The retained r1/r2 findings and unsuccessful probes remain unchanged. The prior
extension bypass and valid UTF-16/32 bypass have dedicated corrected source paths
and tests; the new mixed-encoding defect is narrower. This finding concerns Harness
proof storage/availability. No successful false M3 closure is demonstrated, and no
frozen Evidence Admission or authorization change is proposed.

I independently decoded all seven selected committed governance envelopes using
regular Git blobs at the reviewed head, stdlib gzip and exact stored/raw length and
SHA256 checks. Tested SHA, command and zero exits match the governance record.
Recovered output reports 1005 harness, 241 unit and 114 compact tests, with matching
authority/lint/typecheck/diff oracles. The separate base-drift proof correctly has
actual exit 1. The selected tested-to-reviewed suffix is one linear commit adding
only own evidence and governance bookkeeping. Index/manifest authority metadata is
unchanged; only derived hashes/lengths refresh.

Actual M3 log counts, JUnit failure/skip/count/name checks, exact collection
commands/nodeids/selectors and same-revision provenance remain enforced after
decoding. All ancillary envelopes now bind exact execution or collection commands.
Capture summaries alone cannot create PASS. The bounded nine-case reviewer run is
recorded separately in `m3-compact.json`: actual exit 0, 9 passed and 90 deselected
in 142.78 seconds. Deselection reflects the explicitly bounded reviewer selection;
this is not an integrated M3 execution.

No invariant, frozen table or T1-T8 boundary is touched. The diff contains Harness
tooling/tests/contracts, derived hashes and own HG-046 artifacts. Frozen baseline
and bound files, requirement set, backlog and result/review/M3 schemas are byte
unchanged. Runtime command ownership, SafetyRegistry/S01 lock order, provider trust,
production disabled state and non-executable real-data shadow remain unchanged.
Product/release requirements retain NOT_RUN; no SPEC_CHANGE_REQUIRED is needed.

This review is assigned-base scoped and makes no merge recommendation. Master
advanced through HG-045/PR89 to `fc8a044ffa4d15a74ce5dc59298ae411f1f4009b`;
coordinator serialization, protected-base refresh, retest and fresh review are
required before merge. Hosted applicable CI remains mandatory. This review's new
evidence, including the shared same-task security probe, must be committed through
the exact own linear REVIEW_RECORD_ONLY suffix; it cannot substitute for pre-review
task evidence. No broad Harness, authority or historical checks were rerun.
