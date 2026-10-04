# KL-080 independent DB concurrency review

Reviewed implementation/result: `417b65ee68244dc86ab02add231b24dc662be790`.
Protected base: `1d3075151246b2774640a3d7acec836f47ab2b8d`.
Tested implementation: `feb3236c175df171611fc5b7ddb4f6eeca3ce47c`.

Verdict: PASS. No BLOCKER, REQUIRED_FOLLOWUP or NONBLOCKING findings in the reviewed DB scope. This is a specialist review, not final controller admission, merge, M3 closure or product/release approval. The result correctly records task PASS, task checks PASS and UNMERGED. Final normal gates and controller admission remain coordinator-owned.

## Corrected index rereview

The new four-file change adds the corrected authoritative hosted index, its generator and validation report, and updates the result to supersede the old index. Independently inspected the exact old-to-new Git diff: no source, tests, contracts, raw execution or prior evidence bytes changed. The corrected index has exactly 15 canonical artifact keys. The updated verifier reads each path directly at the new SHA, verifies regular Git-blob availability, outer SHA256, strict envelope decoding, raw SHA256/length, tested SHA/zero exit and the hosted manifest hashes. It performs no alias substitution. The superseded index hash and unchanged bytes are also verified.

The earlier DB probe resolved the corrected duplicate-key entries internally and therefore did not flag the two stale canonical index references; that was a limitation of the earlier review. This rereview explicitly verifies every canonical reference and supersedes the prior staged review. The repaired navigation metadata is not a new database run or retroactive modification of failed history. No conclusion from another reviewer is used as evidence for this verdict.

## Independent method

Read AGENTS, the current index, KL-080 packet, PR review and DB transaction review skills, all ten prerequisite result summaries and their actual MERGED integration records at protected base, Protocol 3.2–3.3/6.2/T6–T7, DB S12/S13/S27/S36/S37 and lock/transaction clauses, HG045 source/feasibility material, M3 closure and evidence/review contracts. Inspected actual base-to-reviewed source/test changes and existing transaction owners. Production/test/contract bytes have no changes between tested and reviewed revisions. Source/test/contract diff contains exactly the packet's 19 paths.

Ran an independent read-only verifier against regular Git blobs at the exact reviewed revision, using the repository's strict compact decoder. It recovers and validates fresh command stdout, JUnit, collection counts, hosted manifest artifact hashes, detailed DB witnesses, archival originals and storage audit. `verify.py` is the probe source; `verification.json` records its successful result. Initial temporary verifier attempts rejected an API identity spelling and an overbroad packet-path extraction; these verifier issues were corrected before the successful final probe, without changing repository or task evidence.

No reviewer PostgreSQL lifecycle, reset, connection, cleanup or test execution was performed. The real PostgreSQL conclusions use independently decoded committed executions, not a claim of a new reviewer database run. No source, result, integration or history edits were made by this reviewer. Files were staged under `/private/tmp` for the coordinator because the worktree owner was active.

## Source and transaction findings

The production diff is limited to two physical source checks in the persistence reader, two pure source literals, and the full-T6 exact S13 query extracted into a private shared read helper. Both pure and persisted input paths require S13 ELIGIBLE and physical S12 MATCHED. S27 ADMITTED and derived S36 CONFIRMED remain distinct. No enum aliases, command/request/schema/runtime changes, target seeding, guard bypass, migration, frozen edits or external calls enter coordination transactions.

Full T6 still reconstructs genuine preparation outputs through `_progress_sources` before collecting freshness. The helper reads immutable S13 by exact subject, admission ID, policy and ELIGIBLE decision; it does not acquire locks or confer authority. Existing S51 shared coordination, S01, intent, daily-head and remaining guarded receipt/attempt/validation order stays unchanged. The production owner retains current fence, revision, trusted-time, registry, policy, execution-basis and full member checks. No call-ledger/lease ownership or T1–T8 atomic boundary changes are introduced.

The new suite invokes real source publication, lease, F/D/N, both distinct full S36, shared S37 and COMMIT_READY owners. Source rows only are seeded; execution/preparation targets remain owner-produced. Four preparation cases cover both profiles and duplicate-event positive paths. Canonical full T6 reaches the real shared query and asserts exact S13 identity/revision, finite minimum dependency validity and both member bindings.

The prior-deployment malformed ADMITTED/CONFIRMED fixture uses exact ancestor Git runtime/helper blobs in a separate process, explicit own URLs and current_database assertions, stopping before T6. Current code denies the untouched request at `_progress_sources -> _verify_full_progress`; the freshness helper is not reached. Seven separately labeled PostgreSQL query probes cover canonical positive and malformed physical decisions, wrong subject/policy/ID. They make no end-to-end freshness claim.

The mechanical trajectory preserves untouched owner S37 and well-formed authenticated CommitBundle. Current ingress, fence and native head creation pass before actual `prepare_authorization_basis` denies with `policy, demand, and calendar authorization bounds must exist`. The raw witness contains the native revision-zero first-use head and identical complete before/after snapshots with no remaining head. No later certificate guard or mechanical execution success is claimed.

Canonical full TRAINING and NUTRITION each traverse START, ordinary PAUSE, RESUME and CONTINUE. Exact current binding identities/revisions are asserted; the recovered witness contains two issuances, two sessions and four START/RESUME bindings, all TEST_ONLY. The suite preserves complete immutable source and preparation history and asserts no production/evaluation head or issuance.

Same-root F2 uses the actual new request revision and attempt, forward preparation, six mixed-old-source denials and a new valid full commit. Prior immutable rows, root deadline and budget payload remain intact. Receipt replay after control, input or runtime loss remains historical and non-executable. Both duplicate commit and duplicate pause witnesses show an actual second PostgreSQL process blocked on S01 FOR UPDATE, followed by identical non-executable replay, one new receipt/event/outbox and no double application. Five injected failure boundaries cover member, issuance, head, success and outbox with complete snapshot equality. Current-state denial cases and the unchanged hosted interleaving/transaction suites retain stale revision/fence/lease/control/basis and revocation coverage. Four timing witnesses use database time strictly beyond expiry; equality remains pure coverage.

## Evidence and preservation

All 17 exact packet commands have successful fresh evidence at the tested SHA. Local suite: 106 cases, no failures/errors/skips; pure suite: six; unit regressions: 247; harness regressions: 1,492. Full suite stdout contains 106 owned namespace and 106 empty cleanup witnesses. Namespace derives the fixed source label, HEAD7 and resolved-root SHA12; nested bootstrap uses only the selected lifecycle and each connection checks current_database.

The authoritative index is `docs/exec-plans/evidence/KL-080/HG051-hosted-index-correction/hosted-db-verification.json`. Hosted run 37161315464 manifest binds actual tested commit feb3236, despite its protected-master workflow-ref SHA. Independent recovery verifies raw checks and artifact hashes, 780 JUnit cases without failures/errors/skips, matching collection/execution records and empty final resources. The unchanged hosted VM lifecycle supplies older suites; no foreign local fixture lifecycle is borrowed.

The HG051 four-object mapping validates exact authorized original regular blobs, recovered bytes, stored hashes, historical execution records and preserved result/review snapshots in normal ancestry. Storage precedes the tested mapping commit. Ordinary execution decoding rejects archival representations. Both historical source-suite FAIL/exit-1 records and original BLOCKED/FAIL/UNMERGED/CHANGES_REQUIRED bindings remain historical; archive retrieval supplies no new execution PASS. The normal exact-revision storage audit passes and enforces unchanged budgets plus byte-identical non-migrated historical evidence. Final review-suffix budget and exact linear REVIEW_RECORD_ONLY proof must still be checked after the coordinator installs all reviews.
