# HG-047 fresh PROTOCOL review — round 3

Identity: `harness-governance-v0.1/HG-047` (PR 91).
Reviewed implementation/result SHA: `589e538579f519bc10d178fa02dff12332931ba7`.
Protected base: `391c9198fa8ec647e377a0572700bc7568468c85`.
Task-tested source SHA: `f29ffa97d9057eacc4bda7ad593b843c9c52c5a2`.

Verdict: **PASS** for protocol review. Findings: 0 BLOCKER, 0 REQUIRED_FOLLOWUP,
0 NONBLOCKING. This is not a merge recommendation or a full-DB/App gate PASS.

## Authority and scope

This fresh review read AGENTS.md, CURRENT_DOCUMENT_INDEX.json, the HG-047 governance
record and SCOPE.md, the pr-merge-reviewer and protocol-guardian skills, the evidence
storage policy, Thread Result/Review, Governance, Merge Gate and M3 closure contracts,
and relevant frozen Protocol invariants/coordination/T1–T8 sections and DB fixed lock
order/transaction boundaries. Governance uses its explicit record rather than a KL
implementation packet. Author self-review prose and prior reviewer verdicts were not
used as implementation or execution authority.

The complete protected-base implementation diff covers the compact reader/writer and
budget audit, validator integration, controller decoder pin/copy compatibility,
tests, prospective policy links and derived metadata. No production runtime,
migration, DB test, workflow, active task packet, completed task result, integration
or milestone instance changed. HG-045/HG-046 records and evidence are unchanged.
The frozen baseline, both frozen documents, requirement set, acceptance specifications,
backlog and full-DB classifier are byte-identical to protected base. `verify.py`
independently checks their Git blobs and hashes.

Consequently no product invariant, frozen table, command owner, Evidence Admission,
authorization meaning, T1–T8 atomic boundary, registry→S01 lock order, provider trust,
planned/actual distinction or production/shadow separation is changed. No frozen
specification change or ADR is needed for this storage-only implementation.

## Raw evidence remains the oracle

`tools/harness/compact_evidence.py:103–211` classifies reserved storage content,
resolves the exact evidence revision, requires same-directory content-addressed
regular payload blobs, verifies stored and raw length/hash, performs bounded
single-member decompression, and rejects decoded reserved storage metadata before
returning raw bytes. This includes wrapped or malformed nested representations;
there is no recursive decoding that could reinterpret metadata as a pytest PASS.
The reader resolves a symbolic revision once and never borrows a payload from HEAD.
Capture fails and removes newly created artifacts when a nested payload is rejected.
Source is cited here rather than included as a raw evidence reference.

`validate_harness.py:2677–2821` retains regular-blob, reachable exact revision and
outer hash binding, then supplies decoded bytes to the existing raw pytest, JUnit
and collection checks. Compact stdout and ancillary JUnit/collection sources bind
the expected tested SHA, command and zero exit code. Summary counts and timestamps
are navigation metadata only. Named witnesses still bind the exact check contract,
command, oracle digest and result. Selector contribution, raw collection order,
executed case identity, failures, skips, xfail and xpass checks remain enforced.

The probe confirms all eleven `M3_*` assignment ASTs are unchanged. It also confirms
unchanged ASTs (apart from the bounded per-operation cache decorator) for the M3 raw
pytest oracle, layer ledger, prerequisite ancestry, frozen authority and closure
validators. The 17-task membership, KL-074 support role, KL-080 source checks, the 19
executable/12 deferred boundary rows, I01–I09 DC versus I04 WF, and product/release
nonclaims therefore retain their existing definitions.

The evidence verdict cache binds repository, full immutable revision, reference,
tested SHA, command and exit code, stores only successes, is bounded and ends with
the validation operation. Working files and symbolic refs are reread. Review evidence
continues to resolve at the reviewed SHA; only an absent path can use an exact
review-record revision after the own-task linear suffix proof. An invalid existing
envelope cannot be repaired through a later same-path review artifact.

The only controller changes add the decoder to pinned assets and the installed
worker copy list. Validation imports its colocated installed decoder. No source
selection, App authorization, admission, workflow or full-DB execution policy changed.

## Exact execution evidence and latest correction

The independent `verify.py` reads regular blobs at the reviewed SHA and validates
compressed evidence with its own bounded zlib/hash logic before parsing the raw
outputs. It checks all nine selected governance command records and all 22 round-3
compact artifacts, worker receipt hashes/commands, raw stdout dispositions, positive
JUnit case counts and unique names, collection/worker node IDs, installed source
hashes and cleanup. It does not accept envelope test-count metadata as execution proof.

The committed Linux ARM64 development run proves 1,306 harness and 241 unit cases,
with zero failures/errors/skips. The 1,306 raw collected nodes, worker executed
nodes and JUnit case names match exactly. The raw validator log says
`HARNESS_CHECK_PASS tasks=77 active=74`. Worker receipt hashes match the recovered
bytes, and both owned container and volume are recorded removed. The independently
checked complete source hashes match the reviewed tree despite the installed
release having the older b737094 identity.

The latest test correction was compared directly between failed source 8a78241 and
f29ffa9. Removing only `ids` keywords makes the entire compact-test module AST
identical; fixture bytes, four decoder cases, six budget cases and all assertions
are preserved. The tested→reviewed suffix contains only HG-047 governance/evidence,
so no source changed after the passing development execution. The failed earlier
raw harness log is preserved and independently verifies 1,304 passes plus two
E2BIG setup errors; it is not selected as current PASS.

Independent focused test execution and counts are recorded in `checks.json`,
`focused-pytest.log` and `focused.xml`. The focused run exercises compact positive
and adversarial decoding, the two ID-corrected parameterizations, M3 raw-oracle
and nested-storage rejection, immutable cache isolation and review-record revision rules. These are synthetic harness regressions, not new
product acceptance executions. `verification.json` records the separate independent
Git/raw-evidence/AST audit. The protected-base storage audit passed: 176 changed
evidence/review files, 2,241,854 bytes at the reviewed SHA.

The first broader 382-case selection was intentionally interrupted after 279 completed
cases because the full historical M3 negative matrix was unnecessary to repeat. Its
exit code was 2. Exact raw output and partial JUnit are preserved as `interrupted.log`
and `interrupted.xml`; no PASS is claimed for that partial run. The replacement
58-case targeted selection is the selected independent regression proof.

## Remaining gate and persistence boundary

The committed successful run is explicitly DEVELOPMENT_NO_PUBLICATION with
`test_only=true`, `full_db=false`, no App object, no signer/admission read and no
publication. Final reviewed-head App/full-DB execution remains **NOT_RUN** and is
mandatory under unchanged HG-046 policy. This review grants no product, M3,
production activation, executable shadow, hosted CI, release or merge PASS.

This review writes only PROTOCOL.json and the new protocol_round3 directory.
Earlier reports/proofs remain untouched. New evidence paths are absent at the
reviewed SHA and require the exact subsequent own-task REVIEW_RECORD_ONLY commit
binding under Thread Review Contract v0.2. Any source/result/test/configuration or
contract change after the reviewed SHA requires a fresh review.
