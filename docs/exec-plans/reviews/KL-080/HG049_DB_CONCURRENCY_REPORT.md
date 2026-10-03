# KL-080 HG049 independent DB_CONCURRENCY review

Status: **CHANGES_REQUIRED**. The inspected database implementation and revised execution oracles are satisfactory. One BLOCKER remains: the normal evidence storage gate fails, so task DoD and overall review PASS are unavailable. No merge recommendation or waiver is made.

Task `harness-backlog-v0.2/KL-080`; protected base `034d6301316d0dade784a61b159c027b83fbce3a`; tested implementation `f85277e27ab5393b7f77b6fea25d4197294d3153`; reviewed implementation/result/evidence `275d7f849b31c9fe123c8d8594b88a85d1c25355`.

Used `.agents/skills/pr-merge-reviewer/SKILL.md` and `.agents/skills/db-transaction-reviewer/SKILL.md`. Inspected the exact diff, revised packet, indexed frozen authorities, merged prerequisite results, result payload and recovered raw captures independently. No sibling or previous KL-080 review conclusions were used. No database lifecycle, foreign pytest lifecycle, implementation/governance/controller modification, commit, push, merge or external message occurred. Old report files remain unchanged; the canonical DB review JSON records this new SHA-bound review.

## Authority and revision binding

Read Protocol 3.2–3.3, 6.2–6.5, T6/T7 and applicable invariants; DB S01/S02/S12/S13/S27/S36/S37/S38, fixed lock order and authoritative-time/transaction clauses; HG045 source audit/feasibility; current storage/review contracts. All 27 indexed document/machine hashes match protected-base bytes and remain unchanged at the reviewed revision. Frozen baseline, current requirements, command registry, migrations and hosted CI files have no task diff.

Read the ten direct prerequisite results and their preparation/execution/fixture limitations. Their real two-parent merges and reviewed SHAs are ancestors of protected base; actual result hashes and required PASS reviews match the entry record. Original result UNMERGED payloads remain their pre-integration fact. M2 has `closure_status: PASS`. Transitive early integration records were inspected separately from the direct normal merges; historical integration shapes are not relabeled as new task merges. Historical prerequisites do not certify current task or product PASS.

The 190 paths changed between tested and reviewed SHAs are confined to the result and new HG049 evidence. Source, tests, contracts, migrations, configuration and policies are identical. The previous KL-080 evidence directories and prior review files are unchanged from resume entry `477b213f67429f571b60d5701f02892ab9c1cbbf`.

## Native transaction assessment

The production diff adds strict physical S13 `ELIGIBLE` and S12 `MATCHED` checks in preparation, corrects the pure resolver to those frozen values, and extracts `_read_full_source_freshness` from full T6. This private helper returns immutable S13 revision, authoritative start and expiry for the exact subject/admission/policy with `decision='ELIGIBLE'`. It grants no authority and creates no public request, mutable alias, policy or migration change.

Actual full T6 still rechecks current owner/fence/request/attempt under held locks, validates root budget and reconstructs owner-produced F/D/N, two S36 and shared S37 through `_progress_sources` before the exact query. Source/member/hash/provenance/policy checks remain fail-closed. S27 `ADMITTED` and derived S36 `CONFIRMED` remain distinct. Nutrition remains TARGET; no planned value fills actual execution. Four bounded older fixture files contain exactly the six packet-authorized source-literal corrections; other older fixtures change prospective source values and dependent assertions/hashes only.

The native shared S51 registry gate precedes S01 coordination, then S27, S38, S44 where needed, followed by receipt/remaining aggregate locks. No lock method or its caller changes. Trusted database-time lease/deadline, request-revision, owner/fence, epoch, execution basis, control, revocation and exact member guards remain intact. Receipt/event/outbox, head switch, prescriptions/issuances and intent/attempt success remain in current T6; T7 uses existing owners. No model/network work enters coordination. Natural/command uniqueness and historical replay paths remain unchanged.

## Raw real-PostgreSQL proofs

All **91** new gzip-v1 captures decode from regular Git blobs at the reviewed SHA, with exact tested SHA, zero exits, stored/raw hashes and lengths verified. Every task stdout binds its exact command. Independently parsed JUnit and collection multisets match the source selectors/full suites, with no failure/error/skip/xfail substitution.

| Check group | Executed cases |
|---|---:|
| Preparation owners | 4 |
| Canonical full T6 | 1 |
| Earlier reconstruction denial | 1 |
| Exact freshness support | 7 |
| Owner trajectories | 2 |
| Current denials | 77 |
| Repair/replay/expiry | 14 |
| Own full DB / PU suites | 106 / 6 |
| Unit / harness regressions | 247 / 1,347 |
| Hosted full DB suite | 780 |

Canonical mechanical/full preparations reach actual COMMIT_READY through input, canonical seal, preparation/publication, lease/snapshot/forward and F/D/N/S36/S37 writers. Full preparation has two action S36, shared S37, concrete FKs, source identities/hashes and finite validity. Duplicate-source positives retain two facts but one counted event/exposure; conflicting quantities deny. Failed-owner wrappers compare exact complete snapshots around the individual failed command; earlier successful preparation outputs are correctly distinguished.

Canonical full T6 reaches the actual helper with exact S13 identity/revision/start/end. Both members bind their S36 and shared S37, and finite certificates end at the minimum dependency. Source/prepared immutable rows remain unchanged. Full T6 and both members' START → ordinary PAUSE → RESUME → CONTINUE execute. Persisted TEST sessions bind exact member P/A, immutable START revision 1 and RESUME revision 2; CONTINUE preserves binding. Each owner receipt/event/outbox link and full source/proposal/resolution/validation history are checked. Production/evaluation peers have no head, issuance or binding.

Mechanical execution presents the untouched owner-produced S37 through a typed authenticated legacy CommitBundle whose key/hash/fingerprint, policy, current request/attempt/owner/fence/lease, basis and closure derive from owner state. Recovered trace shows passing ingress, fence and native head acquisition, then actual `prepare_authorization_basis` denial: `policy, demand, and calendar authorization bounds must exist`. The genuine S37 references N while D references F; this unchanged legacy dependency guard requires them to agree outside the full profile. The observer only reads and delegates. It sees head `f72ea4e2-c81a-4b66-975b-1fa30d3ae785` inside native uncommitted T6 at head revision 0 with no bundle. Independently equal before/after snapshots cover all **37** source/output/receipt/event/outbox/state/root/request/attempt/head/session/binding tables. Both committed head arrays are empty. No later certificate guard, policy downgrade or mechanical execution success is claimed.

The separate prior-deployment child uses exact protected-base runtime/helper blobs and stops at COMMIT_READY. Independently recomputed hashes match all **65** blobs; its six connections use the current owned KL-080 database. Corrected T6 receives the untouched typed request and rejects `ADMITTED+CONFIRMED` at `_progress_sources -> _verify_full_progress`, before freshness, with immutable rows and complete failed-command snapshots preserved. Other malformed S13 values have exhaustive pure/preparation denials and seven read-only PostgreSQL predicate cases. These are labeled support, not a reconstruction bypass or end-to-end freshness reach.

F2 uses the same root, revision 2/new attempt and forward owners; mixed old F/D/N/S36/S37 deny while original outputs, budget and deadline remain intact. Concurrent commit/pause duplicates show the second connection blocked on S01 and only one receipt/event/outbox with stable replay identities. Historical replay becomes non-executable after control/source invalidation or runtime revoke. Injected faults after member, issuance, head, success and outbox writes roll back complete task snapshots. Four recovered database-time observations are strictly later than expiry; equality is PU only. Hosted post-lock fence/lease/expiry and synthetic legacy execution tests remain support coverage rather than substituted source trajectories.

## Lifecycle and hosted provenance

The full local log has **106 namespace** and **106 cleanup** witnesses. Every namespace is exactly `kineticloop-kl080-source-f85277e-9a070975b04f` / `kineticloop_kl080_source_f85277e_9a070975b04f`, independently derived from tested SHA and resolved-root bytes. Every case records migration `e8c2f1a6b904`, selected nested bootstrap, reset/start/destroy, and empty container/volume/network inventory. Namespace preflight runs before bootstrap; task/child connections assert `current_database()`. Imported modules provide builders, not their pytest lifecycles. Temporary UTC process timezone matches registered `test:UTC-v1` and is restored; clock/guard semantics remain unchanged.

Hosted raw manifest binds actual checkout `f85277e27ab5393b7f77b6fea25d4197294d3153`, GitHub-hosted Linux/x86_64 and run `37128318475`, with empty initial and final resources. Protected workflow ref `034d630...` is distinct from tested checkout. Independently recomputed **14** artifact/log hashes and lengths match. Collection, execution and JUnit contain the same **780** passing cases. Named older suites execute positively: mechanical 68, full preparation 59, full execution 85, demo 61, factsets 7, preparation 5, protocol interleavings 9 and transaction interfaces 55. Reset, readiness, peer worktree DB isolation, destroy and peer removal succeed. No foreign local lifecycle was run in this review.

## Blocker and disposition

Independent exact-revision audit command:

`python3 tools/harness/compact_evidence.py audit --base 034d6301316d0dade784a61b159c027b83fbce3a --head 275d7f849b31c9fe123c8d8594b88a85d1c25355 --identity KL-080`

It counts **38,263,916 bytes in 351 changed evidence/review blobs**, above **16,777,216**. Four retained plain blobs also exceed 262,144: `15a7167.../harness_regressions_pass.xml` (3,456,356), `15a7167.../source_suite_dc.log` (12,503,732), `d6bfb285.../harness_regressions_pass.parallel.xml` (3,456,356), and `d6bfb285.../source_suite_dc.log` (12,480,477). Preserving earlier unmerged-PR evidence within this resumed branch does not remove it from the protected-base PR budget.

Seventeen named commands pass, including ordinary `kl check-harness`; they remain separate from the failed selected-task storage gate and final admission/controller gates. The result correctly records `task_checks_status: PASS`, `task_status: BLOCKED`, `integration_status: UNMERGED`, no covered product requirements and no task/review/merge/M3/release PASS claim. Satisfactory DB behavior cannot waive DoD. Resolve storage/preservation through separately authorized reviewed governance, preserve historical evidence and obtain actual normal-gate PASS. Renew exact-SHA review if implementation/result/evidence changes. No additional DB defect or necessary frozen semantic change was found in this task scope.
