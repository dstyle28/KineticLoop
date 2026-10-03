# HG-050 prospective token expiry correction

Identity: harness-governance-v0.1/HG-050. Base: 034d6301316d0dade784a61b159c027b83fbce3a,
merged HG049. Root grants exclusive harness_core and security_data_boundary.
Open PR/ref read before edits found only concurrent KL080 PR92; HG050 unused.
Preflight is diagnostic context, not authority or retrospective PASS.

Exact write scope: tools/harness/github_app.py; tests/harness/test_local_gate.py;
docs/harness/LOCAL_DB_CI.md; tools/harness/validate_harness.py (HG050 exact allowlist
and required GENERAL/SECURITY_DATA_BOUNDARY only); CURRENT_DOCUMENT_INDEX.json and
HARNESS_DOCUMENT_MANIFEST.json derived metadata; own governance/evidence/reviews.
No packet refinements. No runtime/controller/classifier/workflow/dependency/frozen,
historical artifact, installation/admission/signing/protection changes.

Acceptance: deterministic fake clocks/API exercise UTC expiry/margin/age, suspended
monotonic and backward wall clocks, mint latency, malformed responses, stale clear,
identity revalidation, exact bounded GET401 retry and no write/other-error replay.
Actual gate.main with real App exercises final snapshot/renewal/check21 publication,
renewal/stale-head/base/cleanup/authentication failure and test-only no writes.
Real Git governance fixtures exercise mandatory specialist and exact path rejection.

Root owns later separately reviewed controller installation/admission/full DB window.
Only own REVIEW_RECORD_ONLY append follows independent exact-SHA reviews. Product,
M3 and release requirements remain NOT_RUN; preserved HG049 failure and separate
unchanged-controller rerun do not serve as corrective evidence.
