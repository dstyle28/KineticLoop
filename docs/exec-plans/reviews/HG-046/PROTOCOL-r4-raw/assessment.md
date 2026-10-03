# HG-046 independent PROTOCOL r4

Review PASS is scoped to approved base `26906bd7f4444914c228e98377f2b164fee0dd5d`
and reviewed head `02d95c1d86ade83128671190e1e1bf916cfe2b88`; selected tested source
is `9f2f38fe69f772d1564f0fa5eee2441da038aef1`. No current protocol blocker or
SPEC_CHANGE_REQUIRED was found. This is not a merge recommendation.

I inspected the actual assigned-base diff, current index, governance record,
storage/review/merge/M3 contracts, and relevant frozen Protocol sections 2.1a,
3.1, 8 and 11.1–11.2 and DB command ownership/SafetyRegistry clauses. No invariant,
frozen table or T1–T8 boundary is touched. Frozen baseline and bound files,
requirement set, backlog and result/review/M3 schemas are unchanged. Runtime
authorization, Evidence Admission, provider command authority, SafetyRegistry/S01
lock order and production/non-executable shadow separation retain their meaning.
Task/review PASS creates no product or release PASS; deferred requirements remain
NOT_RUN. Index/manifest changes preserve metadata and refresh derived hashes/bytes.

The r1/r2/r3 CHANGES_REQUIRED histories and retained probes were inspected without
rerunning them. Extension-independent recognition closes r1; M3 JUnit, collection
JSON and collection stdout now bind their exact execution or collection command.
UTF-8/16/32 recognition and nested-object rejection close r2. The r3 correction
retains original bytes and uses ASCII escape/NUL recognition only to reject
malformed reserved content when a conflicting BOM/body decode hides its keys.
It never accepts normalized bytes as raw proof. Valid compact content still passes
strict manifest, payload, exact tested/command/exit and stored/raw integrity checks;
opaque historical content is returned byte-identically. The focused source has
20 conflicting BOM/body combinations across literal, escaped and removed markers,
plus opaque controls. Earlier failed proofs stay historical and are not relabeled
PASS; the SECURITY r3 guarded probe's actual exit remains 1.

I independently recovered all seven selected committed proofs from regular Git
blobs at the reviewed head using stdlib gzip and exact stored/raw SHA256 and byte
length checks. Their tested SHA and commands match the governance record and all
seven have actual exit 0. Raw logs report 1085 harness, 241 unit and 194 focused
cases, plus passing lint/typecheck/authority/diff oracles. The separate base-drift
proof has actual exit 1 and empty raw output, and is not task PASS. The selected
tested-to-reviewed suffix is a single linear own evidence/governance commit.

M3 still requires positive actual raw-log counts, failure/skip dispositions, JUnit
case/count/name agreement, exact collection command/nodeids/selectors and hashed
same-revision proof. Summary counts never supply these oracles. My only executable
review check was the assigned compact_regression selection: actual exit 0, 9 passed
and 90 deselected. Its exact command, reviewed tested SHA, timestamp and lossless
raw output are captured once in `m3-compact.json`. This deliberately bounded
reviewer check is not a fresh integrated M3 execution. No broad Harness, authority
or historical check was rerun.

Protected master advanced via HG-045/PR89 to
`fc8a044ffa4d15a74ce5dc59298ae411f1f4009b`. Coordinator serialization,
protected-base refresh, retest and fresh review remain mandatory before merge;
this review introduces no HG-045 dependency or modification. Applicable hosted CI
remains mandatory. New reviewer evidence must be committed through the exact own
linear REVIEW_RECORD_ONLY suffix and cannot replace pre-review task evidence.
