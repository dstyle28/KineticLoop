# KL-036 fresh DB concurrency review, cycle V2

Reviewed implementation/result revision: 900d667394599345a51cec851160d33c01ebce7f.
Protected base: af09be228fbc89d074b6e863c83e1fdda343d55b.
Required-check tested revision: e81cc2ccff69bf32a42f7c81b4671c99879b544b.

This is an independent review using pr-merge-reviewer and db-transaction-reviewer. Earlier reviews and implementer conclusions were not used as proof. Review inspection did not run DB/Docker lifecycle, App/full-DB gates, install dependencies, modify implementation/result/evidence, commit, push or merge.

## Decision

CHANGES_REQUIRED. No new DB transaction correction was identified. One storage/readiness BLOCKER remains: 634 changed regular evidence/review blobs total 18,099,028 bytes at the exact reviewed revision, above the unchanged 16,777,216-byte limit by 1,321,812 bytes. The task result honestly records BLOCKED even though all sixteen exact commands exited successfully. Successful execution and valid technical concurrency behavior cannot turn this unsatisfied admission condition into task or review PASS. New review bookkeeping will also count toward the budget when committed.

Required correction: resolve the aggregate through conforming lossless capture/storage refinement or a separately approved prospective storage-governance change, preserving original execution and failure facts. Commit the corrected task result and required evidence, bind any necessary retest to the new tested revision, then obtain new independent reviews of the new full implementation/result SHA. Do not waive the budget, erase failures, change frozen authority, or label the current BLOCKED result PASS.

## Authority and prerequisites

Read AGENTS, current document index, KL-036 packet and reviewer skills. Applied frozen Protocol §§2, 6.2-6.7 and T5/T8, DB S01-S04/S27-S32, owner/idempotency and §§4.1-4.3 lock/time/discovery clauses. Read the named repository transaction, subject-scope, planning, progress, call-ledger and protocol-execution contracts, M3 closure and release-layer separation, result/review and storage contracts.

Independently compared the five merged prerequisite results at the protected base to their pinned result commits. They report task/check PASS with exact namespaced identities; each integration is MERGED and each recorded merge is an ancestor of the protected base. See ancestry-audit.json. Both commits after the tested SHA are linear and alter only the own result and new own evidence. The implementation/tests/contracts therefore remain the tested bytes. M3 stays the minimal isolated TEST closure and confers no new product or release obligation.

## Owner and transaction review

T5 worker acquisition/renewal uses the existing planning owner and its exact current attempt/request, owner/fence, status, lease and post-lock time CAS. Acquire raises the fence; renewal cannot cross the root deadline. The finite worker loop performs only CREATED-to-LEASED instrumentation through the merged guarded progress owner, then waits on a committed idle service connection. It cannot create attempts, reset root budget/deadline, dispatch, commit T6 or mark success. Lease replay does not establish worker authority.

T8 discovery is a bounded SELECT transaction without row locks and commits before S01. Typed reaping revalidates registered TEST subject/policy/environment/principal before execution/replay and again under S01 against active policy. It uses a private prepared token, server canonical full-request hashing, exact current request/attempt/owner/fence/deadline/expiry/state comparisons, and fresh post-lock database time. First use orders S01, S27, sorted applicable S31, S02, then current S29. No backwards SafetyRegistry acquisition is introduced; T6 retains its existing shared-registry-to-S01 owner.

The nullable basis is constrained to current unacquired ADMITTED/PENDING, NULL owner/expiry, fence zero and CREATED attempt after deadline. Only authenticated prepared reaping accepts NULL owner. The exact S27/S29 identities and update values are guarded once each; completion must contain both. Deadline derives DEADLINE_EXCEEDED/LEASE_LOST; lease-only CANCELLED/CANCELLED requires the exact explicit registered TEST recovery policy. The historical generic completion branch remains unchanged. Mutation, receipt, event and outbox remain one transaction, with server guard acceptance time. Authenticated same-key/hash replay is historical and non-executable; changed payload, stale facts and absent receipts cannot produce a mutation.

Independent accounting goes through existing MarkUnknown owner transactions after scan commit. Only the owner's exact stale-revision/transition errors trigger a ledger read; unchanged candidate or unrelated errors propagate. A confirmed settlement winner is preserved and processing continues. Unknown occupation cannot be cancelled, refunded or reused to dispatch; reliable later settlement changes accounting only and cannot reopen a terminal root or T6 authority. There is no provider/network wait inside coordination.

## Independent evidence inspection

Decoded every artifact referenced by the complete sixteen-check final CHECK_INDEX through the repository's strict revision-bound decoder; verified stored/raw hashes and sizes, normalized same-owner paths, exact tested SHA, command, integer zero exit, and no missing payloads. Recovered raw collection, execution, stdout and JUnit were inspected independently rather than accepting navigation summaries.

For every pytest run, collection has positive exact IDs; executed IDs and every setup/call/teardown phase match its full collection, all phases pass, and JUnit classname/name identities match exactly without failed/error/skipped cases. Counts: each of nine named selectors executes one case; task PU suite executes two; task PostgreSQL suite seven; unit regression 249; harness regression 1492. Lint, typecheck and harness validation exit zero. Harness manifest binds the tested SHA, clean source and complete execution.

Raw suite observations contain 20 distinct child OS PIDs/backend PIDs, seven completed preflight barriers, 12 PostgreSQL blocker witnesses, 11 idle wait witnesses, 48 zero-effect observations and ten complete fault rollbacks. The snapshot helper selects every kineticloop relation as sorted complete JSON rows, including revision provenance and T6 relations: 67 relations were compared. Denials are actual owner guard failures, not mocks or merely row-count checks.

Takeover contenders both finish replay preflight on idle sessions before release to actual guarded acquisition; S01 queues are witnessed through pg_stat_activity, pg_blocking_pids and granted/ungranted pg_locks. The winner raises fence to two, the loser reports the actual CAS-basis-lost guard, root budget/deadline stay equal, and obsolete RecordSnapshot/AdvanceAttempt/PermitDispatch/T6 calls preserve complete relations. Successful current-worker progression runs.

Stale reaping queues behind actual takeover after discovery commits; its recheck denies and complete history is unchanged. Actual renewal also invalidates cached facts. Real trusted expired/live times are witnessed separately from pure-unit equality.

Unowned actual admission produces ADMITTED/NULL/fence0/CREATED. Deadline reaping uses a distinct child process without acquiring a lease, with full stale identity and fault rollback denial checks. Legacy PENDING is explicitly declared compatibility instrumentation. Same-key/hash concurrent reaping produces one receipt/event/outbox and identical non-executable historical outcomes; missing receipt and payload conflict deny. Faults before receipt, event, outbox, S29 and after successful receipt write roll back complete history.

Actual PermitDispatch and CancelUndispatched contenders finish preflight before the guarded S01 queue. Permit wins and cancellation reports reservation-transition denial with complete no-effect comparison. MarkUnknown interruption retains occupation; successful cleanup persists OUTCOME_UNKNOWN and replay cannot resend or refund. Reliable late settlement preserves terminal planning and actual stale T6 denial.

Settlement-race raw observations bind reaper PID 99485 and settlement PID 99486. The accounting scan and settlement preflight both commit before the deterministic lock queue. Settlement wins; stale MarkUnknown rolls back completely, emits digest 66671174cbbf1381e8f35480faa9d3f315f07963b55d3af04735ac820c7189ae matching the observed complete post-settlement relation contents, creates no receipt, and the same reaper completes one other reservation. Final SETTLED/OUTCOME_UNKNOWN states, occupation, settlement totals and CANCELLED root are checked.

The independent worker consumes an actual bounded ordinary queue; its remaining slot is filled and further enqueue fails. Separate admission and reaper processes still operate. A committed heartbeat is observed, worker PID 99491 is terminated with exit -15, independent reaper PID 99493 expires authority, and terminal takeover denies. Before-terminal restart/takeover preserves root limits/deadline and fences prior writes.

T6 success is produced by the existing ProtocolExecutionService/T6CommitCoordinator. Immutable S26/S34-S37 plus COMMIT_READY are declared upstream TEST instrumentation; no bundle/head/auth/success/receipt winner is seeded. Commit-after-scan/recheck and commit-before-scan preserve full history including FOUND_VALID_PLAN/COMMITTED, with digest 6868a120f4c4390be52f58414f8a94a62d4f61929041d12d8072fabf60a290d8. Historical T6 replay is non-executable and old fence denial preserves complete contents.

## Namespace, cleanup and limits

Own constructor/nested runner/reset/bootstrap/seed/destroy gates bind the full tested HEAD and SHA256 of the resolved worktree. The observed namespace is kineticloop_kl036_e81cc2c_17e8ad78fba3 and kineticloop-kl036-e81cc2c-17e8ad78fba3; migration is e8c2f1a6b904. Exact inherited Compose command shapes and pinned Compose file reject appended project/file overrides and foreign readiness/SQL targets before runner invocation. Service user/session_user kineticloop is distinct from authenticated registered client. This is privileged internal isolated TEST instrumentation and does not prove restricted-login ACL containment or production readiness.

Each DB selector and whole suite has equal before/after resource inventory, no collision before construction, owned children joined/terminated, own project/containers/volumes/networks/database removed, and foreign databases/projects/containers/volumes/networks unchanged. Actual worker kill is distinguished from unexpected child failure. All other child exits are zero.

requirements_covered remains empty. No product W/I, M4, release, App/full-DB admission or merge PASS is inferred; production auto-activation and executable shadow remain false. No frozen-spec change is needed for the reviewed implementation. Storage governance is required before this task can satisfy completion/readiness.
