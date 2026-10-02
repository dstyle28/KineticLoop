# HG-042 final merged-owner preparation audit

Read-only preparation audit at protected `93b38f20a3f3d71206515fb0f4d852f5b0b6d344` (HG043 normally merged after KL027). The HG042 draft was rebasing with only derived index/manifest conflicts during this inspection; current authority was resolved from the protected Git HEAD index and HG043 contract, not conflict markers. This is not final independent review or new acceptance PASS evidence. No repository files, DB, Docker resource, task result or review were modified.

## Actual KL027 merge/evidence

- Normal two-parent merge `1099d85bd4aa76ec8221700e55b4e77a84479126`: protected parent `6d1348c5a731afb74fdf6f2345109a446cdb597c`, PR source `e6cd006720b0f81a1d7d5efa1105c68a06c34d96`.
- Reviewed implementation/result `ff93c08c7c32fba9e8dede0c161bb4f97bc98259` is ancestral to source. Its only suffix commit changes 23 paths, all under `docs/exec-plans/reviews/KL-027/`. Source, both demo test modules, contract and historical result blobs are identical at reviewed/source/protected HEAD.
- GENERAL, PROTOCOL and DB_CONCURRENCY each record PASS at exactly ff93. HG043 regular available Git-blob review provenance independently checked: GENERAL 7 references at reviewed + 6 own-review references at source; PROTOCOL 3+5; DB_CONCURRENCY 1+7; zero invalid references. The strict whole-directory linear review suffix permits the absent-at-reviewed review-created references. This cannot relabel task evidence or mutate historical UNMERGED result.
- All 12 committed task log SHA256 values match `checks-72a9a5f/checks.json`; seven own-task XML count records agree (namespace 1, trajectory 1, revoke 9, expiry 3, repair 1, scope 43, full DB 61), with zero failure/error/skip. JSON also records unit232/harness676. Tested SHA remains `72a9a5f3f9529028708f64ece3bbec6d791413a7`. No historical evidence is new KL028 PASS.
- This audit proves Git merge/provenance and local committed raw evidence, not hosted-CI status independently fetched here. Parent must retain actual final CI proof for integration records.

## Owner reachability verified

KL027 now concretely composes declared isolated TEST metadata/admitted immutable source evidence -> restricted RecordActualExecution owner -> CanonicalViewService Begin/Write/Complete/Seal -> PreparationService projection/build/READY -> ProtocolExecutionService T3 -> actual KL024 admission/acquire -> KL075 snapshot/forward stages -> KL076 F/D/N -> KL079 two action-specific resolutions/full validation -> COMMIT_READY -> KL077 full T6 -> exact current eligibility -> real START. Target seals/projections/builds/snapshots/F-D-N/certificates/issuances/sessions are not seeded. Ordinary PAUSE/RESUME has real lifecycle. ApplyControl and AcceptFactRevision derive locked current epoch/frontier and persist atomic bookkeeping. Registry revocation uses actual trusted admin owner.

The KL028 prospective selector names map to the intended new files; those tests are not implemented and all statuses remain NOT_RUN. Nineteen obligations have available owner capacity (6 PU + 13 DC), conditional B04 DC is separate, and 11 minimum deferred obligations remain, becoming 12 if B04 only reaches registry guard support. The packet retains all31 (8PU14DC8E2E1WF). Internal KL027 service E2E labels never satisfy product §22 API -> workflow -> DB -> eligibility/rendering. B11/B12 have no merged pure commit-state evaluator; no SQL/hash/relabeled DC/mini-model is PU.

## Concrete B04 gap: conditional is required

`src/kineticloop/persistence/transactions.py` makes full TEST reauthorization unavailable:

- `_prepare_full_execution` (~4140) requires command_kind exactly CommitBundle.
- `prepare_authorization_basis` (~3937) rejects full persisted kl079 policy unless `full_execution_members` exists.
- S42 insertion (~1642) requires full member issuance_reason AI_PLAN and explicitly rejects full TEST reauthorize mode.
- `require_execution_request` (~4382) explicitly rejects full TEST replacement/reauthorize/fallback/offline modes.

The generic Reauthorize transaction owner and actual `registry_guard_reauthorize` do exist. A guard-positive/relevant-revoke-negative test can be executable task support; it cannot make B04@DC PASS. Complete actual reauthorization requires separately bounded owner/composition refinement using a new admitted revalidation intent/current attempt/latest manifest and owner-produced validation/existing prescription. No full-to-legacy policy downgrade, raw target seed, terminal reopening, no-op mutation, private-context assignment or bypass is allowed. Current packet's conditional/deferred wording correctly permits task check PASS with exact requirement NOT_RUN.

## Precision notes for packet oracles

1. B09: different immutable dependency bounds often inherit another minimum. T3 manifest expiry already reflects projections/artifacts, and resolutions can inherit source freshness. Permit tied minima and compare each exact required bound/certificate entry plus mathematical minimum; do not require every dependency to become a uniquely shortest bound through timestamp mutation. Source/policy/config may choose prospective bounds before actual owners run; target certificate/output overwrites cannot construct evidence.
2. B15/B17: require a real three-node transitive path A -> B -> C and complete registered closure. Registration can additionally require A -> C because RegisterArtifact requires explicit complete transitive dependency_ids. Do not interpret “exact A->B->C” as forbidding this required edge or demand exclusively two edges. Revoke leaf C with direct A unrevoked, persist actual graph/identities/hashes, and deny real guarded owners.
3. B11/B12/B13/B15/B17: use independent stage-valid T3 prepublication READY, T6 current live COMMIT_READY, and T7 lifecycle-valid trajectories. Reusing an already PUBLISHED build or committed/terminal intent is not a positive T3/T6 guard control, and historical replay does not test new permission. New T7 START must have a distinct absent session; CONTINUE IN_PROGRESS; RESUME authenticated PAUSE/current immutable binding.
4. B01 actual CanonicalViewService.read_canonical and PreparationService.capture_source guards reject owner-built BUILDING/READY. A malformed PublishReady mismatch against an otherwise SEALED source does not reach this oracle.
5. B13 can inject a task-local cursor/connection failure after the actual registry_revoke_artifact routine writes but before its transaction context commits. Snapshot full S50/S51/management receipts/audit/outbox proves rollback; no temporary trigger/DDL/target mutation is required.
6. B14 support may use actual S51 exclusive-gate unavailability/timeout while owner STOP progresses independently through S01. This is task DC support; it is never B14WF/E2E PASS. Require exact fail-closed gate cause and zero target effects; transport failure or another guard cannot substitute.
7. Namespace machinery must be copied/adapted inside the own two new test files. Importing KL027's OwnedLifecycle/fixture executes the KL027 prefix/label/root invariant and violates KL028 ownership. Read-only source builders may only accept explicit validated URLs and must have no lifecycle/output-seed dependency.

## Named frozen authority

Protocol §§0.3a/2.1a commit linearization + shared/exclusive gate + lock/fresh-read; §2.3 half-open trusted time; §4.1a BUILDING/READY/SEALED barriers; §4.4 publication; §§5.3/5.3a complete current issuance guards and minimum validity; §§5.4/5.5 current non-bearer execution/lifecycle checks; §5.6 independent STOP; §8 T2-GLOBAL/T3/T6/T7 atomic boundaries. DB S15/S16/S42/S45/S49/S50/S51, §3 Reauthorize new admitted intent/no reopen, §§4.1/4.3 fixed S51->S01/fresh trusted post-lock time, §5 atomic boundaries, §12 immutable certificate and approved TIMELESS. Product layers: technical spec §22 lines321–324 and current supplemental acceptance exact31 obligations. No frozen semantic change or product PASS follows from this preparation.
