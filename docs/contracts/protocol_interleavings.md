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
| I03@DC | Root CancelIntent vs PermitDispatch, followed by separate CancelUndispatched cleanup; **blocked before either race**, strict TEST CancelIntent identity is not admitted at T4/T8 |
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
expiry result. I04@WF remains NOT_RUN; DC cannot close its workflow obligation.

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

## I03 blocker

The frozen strict `CancelIntent` class has T4/T8 boundaries. Its inherited TEST_ONLY
validator allows only T6/T7; production scope requires a SUBJECT capability and an
actor ID equal to subject. KL026 requires the independently authenticated TEST
identity and an isolated TEST principal. Inventing a SUBJECT translation,
`model_construct`, relaxed validation or a new identity/owner contract would
exceed this tests-only task. The failing selector retains the exact TEST_ONLY
validation rejection, with no skip/xfail. Root cancellation, intermediate terminal
with RESERVED, cleanup, dispatch-first retained occupation and replay assertions
are present but NOT_RUN behind this missing identity precondition.

A separate bounded packet/identity-contract refinement must explicitly ratify the
TEST cancellation request shape before I03 can execute. Existing S27 cancellation
permissions and separate ledger cleanup need no speculative grant. This is a task
BLOCKED condition, not an inferred requirement to change frozen semantics.
