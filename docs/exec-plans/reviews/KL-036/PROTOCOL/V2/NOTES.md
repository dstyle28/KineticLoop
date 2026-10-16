# KL-036 fresh protocol review, cycle V2

Reviewed revision: `900d667394599345a51cec851160d33c01ebce7f`.
Protected base: `af09be228fbc89d074b6e863c83e1fdda343d55b`.
Required-check tested revision: `e81cc2ccff69bf32a42f7c81b4671c99879b544b`.
Task: `harness-backlog-v0.2/KL-036`.

Status: CHANGES_REQUIRED. One BLOCKER concerns evidence-storage admission. No new protocol implementation correction or SPEC_CHANGE_REQUIRED was identified. This review cannot recommend merge while the required storage condition remains unsatisfied.

## Authority and scope

Read AGENTS, current index, active packet, pr-merge-reviewer/protocol-guardian skills, relevant named prerequisite contracts/results/integrations, result/review/storage/resource/M3 contracts, and the packet's frozen Protocol invariants INV-10/11/12/13/17, sections 2, 6.2–6.7 and T5/T8; frozen DB S01–S04/S27–S32 and sections 3–5. Current indexed document hashes match the reviewed blobs. Current authorities and prerequisites remain byte-identical to protected base. Actual merged prerequisite results are PASS, and each recorded KL024/KL026/KL025/KL075/KL019 merge is an ancestor of protected base; admission result hashes match those protected-base blobs. M3 records PASS with production_auto_activation=false and shadow_executable=false.

Inspected all committed production/test/contract changes and result plus required final-run artifacts directly, without using other review conclusions. Outside own evidence/reviews/result, changes are only the three declared source files, two own test files and own worker/reaper contract. No frozen, enum, migration, grant, shared fixture, lifecycle, CI, requirement registry or provider write occurs. The implementation/test/contract trees at tested and reviewed revisions are identical. The two intervening commits are linear and change only own result and newly added own evidence files, retaining tested provenance.

## Protocol assessment

The worker invokes existing AcquireLease/RenewLease and guarded CREATED→LEASED progression. Unique operation keys avoid using historical acquisition/heartbeat as authority, and either replay causes failure. Waiting follows owner commit on an idle connection. It neither prepares model results nor dispatches, grants authorization, creates attempts, reopens roots or modifies budgets/deadline.

The separately registered TEST reaper commits discovery before coordination. Actual first use orders S01→S27→sorted applicable S31→S02→S29. Registration precedes replay and is rechecked under S01 against current active policy; the private prepared token is not a caller terminal/compatibility flag. Exact current request/attempt/owner/fence/deadline/lease/status facts are revalidated, and fresh trusted clock_timestamp after the remaining S29 lock derives the frozen distinct targets. Deadline closes S27 DEADLINE_EXCEEDED and S29 LEASE_LOST; lease-only CANCELLED requires the explicit current registered TEST recovery policy. The exact unowned ADMITTED/PENDING, null-owner, fence-zero, CREATED basis accepts only elapsed original deadline. Generic legacy synthetic completion remains unchanged and is not used as new authority.

Exact prepared S27/S29 writes plus receipt/event/outbox are atomic, with server guard acceptance time persisted. Successful same-key/full-request-hash replay is authenticated, historical, and non-executable; changed payload conflicts and absent receipts cannot recreate terminal work. Terminal intent/attempt success remains T6-only. No authorization, Evidence Admission, provider authority, production/shadow, replay-knowledge or frozen transaction/lock-order meaning changes.

Unknown-call cleanup uses separate existing MarkUnknown owner transactions. Possible dispatch retains occupation and cannot become resend permission or cancellation refund. Stale accounting discovery is handled only for specific owner transition/revision rejections, confirmed via ledger read; other failures propagate. Reliable late settlement changes accounting only. Reaper does not inline S31/S32 accounting, restore planning authority, or wait on provider/model/network inside coordination.

## Independent evidence verification

Read required artifacts as regular Git blobs at reviewed revision, including cross-directory own-task deduplicated captures. Checked stored and recovered byte lengths/SHA256, single complete compressed member without trailing bytes, exact tested SHA, command and integer successful exit. All 16 check commands match the packet. Verified actual raw collection stdout/node IDs, all execution worker collections, started IDs, call IDs and JUnit identities/counts, with no errors/skips/failures/deselection and all setup/call/teardown outcomes passing. Standalone selectors each execute one case; whole task PU=2, task PostgreSQL DC/WF=7, unit regression=249, harness regression=1492. Harness manifest is exact-tested and clean-source, complete with no errors; each listed raw file hash/length matches. Lint/typecheck/harness validation raw outputs record success.

Actual final suite raw observations contain 20 distinct owned child ready records, 12 SQL blocker records, 14 elapsed trusted-time records, 11 idle outside-transaction wait records, 10 released candidate scans, 48 complete-relation zero-effect assertions and 10 injected complete rollbacks. Examined actual PID/backend PID, pg_blocking_pids/pg_locks, expiry, lock trace, terminal and accounting/T6 observations alongside their assertions. Each standalone DB run and suite preserves identical before/after foreign inventories, exact owned SHA7/rootSHA12 namespace, migration e8c2f1a6b904 and bounded joined/terminated children.

The worker-loss test runs an actual finite worker loop consuming a bounded ordinary queue, observes a committed heartbeat, fills the ordinary queue, and runs distinct admission/reaper processes. Recorded worker termination is -15, independent reaper terminates the root, and restart before reaping raises fence while retaining root limits/deadline. Complete stale-worker denial assertions cover snapshot/attempt/dispatch/T6. Actual ReserveCall/PermitDispatch precedes unknown accounting; permitted cancellation loses with complete equality. Separate reliable settlement wins against discovered MarkUnknown, which fully rolls back and the same reaper continues another reservation.

T6 uses actual existing commit owner with explicitly instrumented upstream S26/S34–S37/COMMIT_READY inputs. Success/head/bundle/auth are not seeded. Scan-before-commit/recheck-after-commit and commit-before-scan preserve complete relation history, including FOUND_VALID_PLAN/COMMITTED and issuance. Privileged TEST service and input seeds are declared instrumentation, not restricted-login ACL containment, full planner/model workflow, product/W/I/M4/release or App/full-DB evidence. Requirements covered is empty, activation/shadow remain disabled, and result correctly stays BLOCKED/UNMERGED.

## Blocking storage correction

Independently enumerated the protected-base-to-reviewed-revision changed evidence/review regular blobs and summed their exact Git blob bytes: 634 artifacts, 18,099,028 bytes. The unchanged policy's inclusive 16 MiB limit is 16,777,216 bytes, so overage is 1,321,812 bytes before new cycle-V2 review notes. The result's storage blocker and failed exact-head audit are consistent with this independent finding; a passing task test-harness/check-harness execution is not protected-base storage admission.

Required correction: resolve capture/storage through separate reviewed prospective governance and then supply a compliant exact-revision storage audit and fresh SHA-bound reviews. Preserve lossless real execution and failures; do not truncate, waive the gate, erase history, mutate frozen semantics or promote test checks to task/product/merge PASS. No storage or source correction was performed by this reviewer.

No task checks were rerun, no database/lifecycle operation or App/full-DB gate executed, and no installation/source/tests/contracts/results/evidence/Git state changed. Review output is limited to canonical PROTOCOL.json and this new V2 note; earlier notes were preserved.
