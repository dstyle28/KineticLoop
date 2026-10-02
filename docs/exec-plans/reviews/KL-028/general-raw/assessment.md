# Independent GENERAL review of harness-backlog-v0.2/KL-028

Reviewed implementation/result: `994cf425360c75a366f186e91857a5d75ed02ebe`.
Tested implementation: `debd5e58f98b4b20a2dd1ae132799d2373797622`.
Protected base: `9268fc8dd8c071c02dc5c698274dbf6fcd112776`.

Outcome: PASS, with no BLOCKER or REQUIRED_FOLLOWUP findings. This is a task review recommendation; integration and hosted merge checks remain separate.

I independently read the task packet and matching reviewer skill, current authority index, frozen Protocol §§0.3a/2.1a/4.1a/5.3–5.6/7.4, DB S42–S45/S49–S51/§§4.1/4.3/5/12, current acceptance §§2–3, M2 closure, prerequisite results/integrations/reviews, the implementation diff, and the applicable merged owner/helper contracts and source. The packet permits task PASS with the exact 12 deferred layers still NOT_RUN. Nothing in the tests changes frozen authority, command ownership, production activation, shadow execution, or planned-to-actual semantics.

The audit script independently reads regular Git blobs at the reviewed revision. It verifies all index hashes; protected-base preservation; scope; normal prerequisite merge ancestry and SHA-bound PASS review records; exact tested/result revision bindings; all 29 check headers, selectors, log hashes and JUnit counts; all 31 layer dispositions; runtime namespace/digest/migration/empty-cleanup witnesses; complete zero-effect denial histories; real blocker PIDs and S51→S01 traces. It also reconstructs receipt/event/outbox joins from persisted snapshots, checks exact server certificate minima/digests/source revisions/windows/materialized closures, and compares immutable lifecycle histories. The supplied oracle-audit.json and entry-audit.json were context, not substitutes for these independent checks.

The single tested-to-reviewed suffix commit adds only task-owned new evidence and the result; it changes no existing evidence or implementation. Each of the three implementation blobs is identical at tested and reviewed commits. All four read-only merged helper blobs are unchanged from the protected base. The protected base has no KL-028 result, integration or review record. The final result's files_changed list matches the complete diff, not the review files subsequently created here.

## Exact check assessments

| Check | Independent assessment of source and persisted oracle |
|---|---|
| boundary_namespace_pu | Exact runtime full SHA/resolved-root/label/digest names; malformed, peer, foreign/default, stale and ambient inputs fail before runner calls, including nested finally cleanup. Permitted fake-runner control executes. |
| b01_pu | Actual reconstruct rejects otherwise identical closed BUILDING/READY states and unsealed ancestors; SEALED FULL/DELTA returns exact digest/count. |
| b01_dc | Actual CanonicalView build/write/complete states reach unsealed read and SEALED-source capture guards; complete user/global before/after equality. Seal/capture/publication succeeds with exact S15/S16 certificate and receipt chain. |
| b02_dc | Two real S01 serial orders use admitted AcceptFactRevision and owner seal, with blocker PID observation. Update-first leaves READY/no pointer and no loser writes; seal-first preserves historical SEALED basis while epoch/frontier advance. Current-frontier rebuild seals. |
| b03_dc | READY and SEALED owner writes deny, and existing permitted internal DB principal hits immutable member/content/certificate triggers. Independent admitted correction produces new build/seal; old S15/S16 rows remain identical. |
| b04_dc | Owner-produced full source trajectory succeeds through actual CommitBundle and exact two certificates. Relevant leaf revoke denies still-live full commit with zero effects. Actual Reauthorize registry guard is deliberately aborted after its gate, labeled support only, with B04@DC NOT_RUN. Source confirms full TEST Reauthorize remains unsupported. |
| b05_dc | Unrelated registered artifact is outside materialized closure; revoke revision advances while current non-bearer eligibility and fresh START succeed. Existing A/P/START remain unchanged. Relevant leaf revoke control denies a fresh current CONTINUE. |
| b06_dc | Actual T3 and global revoke race both ways. Revoke-first typed publication waits on S51 then denies with no publication/head/bookkeeping; valid publication-first positive succeeds once and later fresh current publication denies. |
| b07_dc | Independent START/CONTINUE/RESUME trajectories establish positive current permission. RESUME follows real ordinary PAUSE; new START uses absent target. Fresh keys after relevant leaf revoke deny current registry cause with full session/binding/head/source/issuance/bookkeeping equality. |
| b08_pu | Each dependency independently loses start/end or gains unknown/future/expired/nonincreasing validity; actual evaluator raises. Valid closure checks exact certificate identity/revision and digest. |
| b09_pu | Each required dependency independently becomes minimum; actual evaluator returns exact minimum and deterministic ordered certificate. Client shortening succeeds, extension cannot lengthen, missing/expired bounds deny. |
| b09_dc | Twelve owner-produced full TEST cases vary admitted upstream finite bounds and client shortening. Exact two S42 certificates contain all required source identities/revisions/windows and exact trusted-time minimum/digest/method/materialized closure. Inherited tied manifest/projection/resolution bounds are permitted by packet. No timestamp overwrite. |
| b10_pu | Actual evaluator permits just before expiry and denies equality/after with TIME_INELIGIBLE while original cached ACTIVE remains unchanged; non-bearer observation is explicit. |
| b11_dc | Backdated effective_at remains audit metadata; actual uncommitted revoke blocks real relevant T3/T6/T7 waiter on S51, commit denies. Exact global management joins/revision and prior START/A/P history remain intact. Independent unrevoked controls succeed. |
| b12_dc | Future effective_at has the same successful-commit immediate denial, with effective_at > recorded_at; no scheduler or historical rewrite. Separate positive controls and full zero-effect history. |
| b13_dc | Task-local cursor fails only after actual trusted revoke SQL routine returns its written result; actual owner transaction rolls back. Entire global history equals before; affected real T3/full T6/T7 succeed afterward. No target-table or role/schema perturbation. |
| b14_registry_failclosed_stop_support_dc | Three real shared-gate timeouts and three faults at actual registry query deny T3/full T6/T7 with zero effects. Merged restricted ApplyControl independently completes STOP under S01 while S51 is held, persisting S17/S18/S43/epoch/receipt/event/outbox. Separate unrevoked controls succeed. DC support remains explicitly distinct from deferred B14 WF/E2E. |
| b15_dc | Actual T3/full T6/T7 each race leaf revoke in both orders. Winner finishes after owned guarded writes but before commit; loser blocking is observed via PostgreSQL. Revoke-first zero effects; operation-first historical success then fresh current denial. Exact S51→S01 traces and S50/S51 management revision chains. |
| b16_dc | Lifecycle-valid CONTINUE/RESUME positives precede real epoch STOP or registry revoke. Fresh commands reach exact current-authorization denial, preserving original START/A/P and all failed operation state/bookkeeping. |
| b17_pu | Actual complete-closure validator rejects A-only and direct-only; complete A/B/C graph succeeds. Actual validity evaluator denies revoked leaf despite unrevoked direct ancestors. |
| b17_dc | Actual RegisterArtifact builds A→B→C plus required A→C closure edge. Omitted leaf injection reaches actual owner incomplete-closure guard; complete unrevoked T3/full T6/T7 succeed. Leaf revoke denies all three despite unrevoked direct A with full zero effects. |
| b18_pu | Actual registration validity and closure evaluator reject missing policy/reason/edge, wrong policy kind, revoked or unprovable approval; approved static TIMELESS plus finite bound succeeds at finite minimum. |
| boundary_full_unit_suite | Seven cases, zero failure/error/skip/xfail; exact final source unchanged. Independent review rerun: seven passed at reviewed HEAD. |
| boundary_full_db_suite | Sixty-four cases, zero failure/error/skip/xfail, exact owned migration and 64 empty cleanup inventories; raw persisted oracles checked independently. |
| harness_validation_passes | Exact command, tested header and hash; HARNESS_CHECK_PASS tasks=76 active=73. |
| unit_regressions_pass | Exact command and tested header; JUnit 239 cases with zero failure/error/skip. |
| harness_regressions_pass | Exact command and tested header; JUnit 790 cases with zero failure/error/skip. |
| lint_passes | Exact command and tested header; All checks passed. |
| typecheck_passes | Exact command and tested header; no issues in 150 source files. |

## Truthful layers and limitations

The independently matched ledger contains 31 exact B-layer obligations: 19 mechanical PASS and 12 NOT_RUN. Deferred obligations are B04@DC, B04/B05/B07/B08/B10/B14/B16/B18@E2E, B11/B12@PU and B14@WF. Their reasons and future owner gaps agree with the packet and result. B04 guard support does not become full reauthorization; B14 timeout/query-fault/STOP support does not become worker/process or public-product evidence. No aggregate product, M3, release or shadow-usability closure is claimed.

The merged source builder creates only explicitly ratified isolated TEST immutable upstream inputs/supporting registrations, then actual RecordActualExecution, CanonicalView, Preparation, PublishManifest, admission/acquisition, snapshot/forward stages, F/D/N/full resolutions/validation and T6/T7 own all tested outputs. The loaded private helper's connect function is rebound to explicit KL028 URLs; foreign pytest fixture functions are never invoked. The selected migration bootstrap receives the validated KL028 lifecycle. No production source, migration, grant, shared fixture, lifecycle, Compose, CI, lockfile, packet or frozen-baseline edit occurs.

I did not create or run a PostgreSQL lifecycle or foreign fixture during review, as assigned. DC assurance here rests on independent source and Git-bound final raw evidence inspection, not a new reviewer DB execution. The seven PU tests did rerun successfully at the reviewed SHA; that evidence is review bookkeeping, not replacement task evidence. Hosted PR uniqueness, final CI status, normal merge and integration are outside this local review. The inherited KL077 descriptive DEMAND_FEATURE proposal_id metadata follow-up remains explicitly recorded in the result and does not weaken guarded D→F/N/full-action authority.
