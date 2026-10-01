# KL026 protocol interleavings

This tests-only suite binds `harness-backlog-v0.2/KL-026` and the current requirement
set. It uses merged typed T3/T5/T6/T7 owners and the specifically ratified TEST-local
ApplyControl and AcceptFactRevision recipes. No production owner, migration, grant,
public command, workflow or frozen authority changes here.

Each race holds the first actual owner transaction after its guarded mutation and
finish, before commit. The second owner starts on another connection. Bounded
Events, futures and an actual `pg_blocking_pids` observation establish the order;
no sleep establishes a contender order. The final full relation snapshot must
match the winning owner's uncommitted snapshot exactly when the loser denies.
Successful second transactions also match their complete owned snapshot. Global
RevokeArtifact uses the actual strict command and administrative login; because
that login deliberately cannot SELECT arbitrary tables, its cursor pauses after
the SECURITY DEFINER function completes, still before commit. All non-management
relations must remain byte-for-byte equal to the preceding owned state, and the
exact S50/S51/management receipt/audit/outbox identities must join one-to-one.

| Requirement | Owners and persisted oracle |
| --- | --- |
| I01@DC | T3 publish vs S01 ApplyControl, both orders; stale READY denial, immutable manifest/binding/receipt/event/outbox, epoch advance and old T6 denial |
| I02@DC | START vs ApplyControl, both orders; zero failed-first-use session/binding/bookkeeping, immutable historical IDs, denied current START and CONTINUE |
| I03@DC | HG039 strict TEST-local root CancelIntent vs PermitDispatch, both orders; separate exact CancelUndispatched cleanup, terminal-with-RESERVED safety, retained DISPATCH_INTENT occupation, stale/cross-root denials, same-key conflict/concurrent history and actual successful T6 preservation |
| I04@DC | Actual CommitBundle vs AcquireLease takeover, both orders; atomic issuance/bundle/success or higher fence and no stale T6 effects; separate real lease/deadline before/after and observed-lock-wait expiry |
| I05@DC | Global revoke of exact transitive grandchild vs actual T6, both shared/exclusive orders; historical certificate/closure immutable, current START denied |
| I06@DC | Transitive revoke vs START, both orders; historical binding/replay immutable, current START/CONTINUE denied |
| I07@DC | Transitive revoke vs T3, both orders; no stale generation/head/bookkeeping, replay cannot restore issuance authority |
| I08@DC | Actual builder/write/complete/seal vs guarded admitted input revision, both S01 orders; stale seal rollback, SEALED history remains immutable and replay cannot repoint a newer actual seal |
| I09@DC | Real T6 server-computed minimum admission-freshness end; START before succeeds, after denies, expiry while waiting on actual S01 and S51 locks denies with no effects; historical binding/replay immutable and current CONTINUE denied |

Exact equality at authorization validity end, lease end and root deadline is
separate deterministic PU evidence over `evaluate_executability`,
`evaluate_validity_closure` and `require_live`. Actual PostgreSQL DC uses trusted
post-lock `clock_timestamp` before/after and while waiting. No timestamp overwrite,
caller clock, cached VALID, status job or new production clock seam establishes an
expiry result. Lease/deadline equality exercises the merged pure `require_live` helper,
not execution of the SQL owner at equality. The actual lease owner caps expiry at
the root deadline; the real deadline-crossing case legally expires both together
and does not causally isolate the SQL deadline predicate. I04@WF remains NOT_RUN;
DC cannot close its workflow obligation.

The namespace is exactly `kineticloop-kl026-interleave-<HEAD first7>-<root digest>`
and `kineticloop_kl026_interleave_<HEAD first7>_<root digest>`, where HEAD is the full
40-lowercase-hex revision and root digest is SHA256(os.fsencode(resolved root))
first12. Validation precedes construction, every nested Compose/SQL command,
bootstrap/reset and finally cleanup. Ambient, malformed, peer/default/foreign
namespaces and root drift deny. Unit evidence exercises the actual suite fixture,
bootstrap failure and nested final cleanup with a fake runner before real reset.
Every real connection and seed validates the exact database; bootstrap receives
that selected lifecycle. No foreign legacy local fixture is invoked. Full legacy
DB regression evidence belongs to unchanged hosted CI only.

Input builders copied from merged KL019 use new isolated subject/policy/program/
artifact identities. They seed registered TEST inputs, SEALED factset/projections/
READY build, and explicitly synthetic S26, COMMIT_READY and S34–S37 certificates
outside target transactions. They never seed S24/S25/S38–S42/S44/S45 or successful
intent outputs. S43 is generated only by actual ApplyControl/AcceptFactRevision
owners. This is T6 guard evidence, not full F/D/N workflow evidence. I08 instead
uses actual factset builder completion and source-bound admitted input revisions.

## TEST-local I03 cancellation

HG039 normally merged after KL075 ratifies the independent immutable
`TestCancelIntentRequest` in this test file. It carries exact TEST subject, policy,
environment and principal; root, attempt, reservation, request revision and fence;
and a bounded key. It carries no caller actor, authorization grant or hash. The
recipe uses separately trusted `PlanningIdentity(TEST)` and computes the canonical
hash from the entire strict payload. The existing idle registration guard precedes
replay; fresh SELECT-only registration binding repeats under S01.

Historical replay first uses the existing idle `replay_outcome`. After a real miss,
the recipe locks S01 and reads successful S02 by exact subject/actor/command/key,
checks hash/outcome, and returns non-executable history before live-root guards.
No receipt lock precedes S27/S31. Live cancellation locks the exact intent and
reservation, checks current request/attempt/fence and reservation linkage/state,
and updates only S27.status with the existing atomic receipt/event/outbox. An
actual FOUND_VALID_PLAN returns original completed facts without cancellation
bookkeeping. Root fields and reservation/accounting are otherwise unchanged.

Both cancellation/dispatch orders run. Real stale/foreign denials leave every
relation unchanged. Two real preflight misses are synchronized before either
mutation; the winner commits one cancellation and the contender rechecks history
under S01, with a PostgreSQL blocker witness and no duplicate bookkeeping. Same-key
changed payload conflicts. The separate actual ledger cleanup releases only
RESERVED dimensions; DISPATCH_INTENT cleanup denies with no refund or resend.

The named PU selector executes the installed model/binding/basis/history predicates,
strict immutable payload and negative identity/scope/type/hash cases. Public
TEST_ONLY CancelIntent still rejects T4/T8, with the merged 39-command registry and
validator bytes unchanged. Original blocked results/raw logs are preserved as
historical evidence, without reuse as current PASS. No production cancellation
ingress, permission/grant, clock seam or frozen meaning changes here.
