# SafetyRegistry shared/exclusive gate contract

This contract materializes frozen S49--S51 coordination without changing Protocol or DB
semantics. It is a lock/gate API and task-local PostgreSQL fixture, not a migration.

## Command boundary and order

`PublishManifest`, `CommitBundle`, `Reauthorize`, `StartSession`, `ResumeSession`, and
executable `ContinueSession` execute in this order inside one short authoritative
transaction:

1. acquire the singleton `system` S51 row with PostgreSQL `FOR SHARE`;
2. after the gate is held, lock S01 with `FOR UPDATE`;
3. after both locks, read current S49/S50 registrations, complete registered dependency
   closure, validity, revocation, and the command-appropriate T6 issuance or T7 execution
   eligibility;
4. only then invoke the domain mutation.

The connection uses PostgreSQL's default `READ COMMITTED` isolation. A shared-gate statement
that waits behind an exclusive holder therefore locks and returns the newly committed S51
row, and all eligibility reads occur in later statements. After S51 and S01 are held, the
owner reads authoritative database time in a separate statement issued after the S01 locking
statement returns and uses it for authorization and artifact validity; caller-captured time,
time expressions evaluated by a statement still waiting for S01, pre-gate snapshots, and
caches are not accepted. A supplied minimum
revision rejects a demonstrably stale authority, while a higher unrelated current revision
does not invalidate an otherwise eligible authorization.

Registry absence and bounded lock timeout are denials. The gate is held until transaction
commit, so a global revoke cannot linearize between eligibility checking and the protected
mutation. No network, model, historical scan, or dependency-closure construction belongs in
this API; the caller supplies a complete, bounded closure of immutable identities.

Every helper requires an idle PostgreSQL connection and owns the top-level transaction through
commit. Invocation inside an existing transaction is rejected, so the API cannot return while
S51 remains held in an outer transaction or allow a caller to reverse the S51-before-S01 order.

## Global revoke

`RevokeArtifact` requires the trusted admin role and acquires S51 with `FOR UPDATE`. It never
reads or locks S01. In the same T2-GLOBAL transaction it appends S50, advances S51, and writes
the management receipt, audit event, and outbox identity. The successful commit—not
`effective_at`—is the execution linearization point. `effective_at` remains audit metadata,
so a future value does not schedule eligibility and a past value does not rewrite historical
authorization facts.

The receipt is checked after the exclusive gate. A repeated command key and request hash
returns the stored original result; reusing the key with another hash is rejected. Any insert
failure rolls back every T2-GLOBAL effect.

## Commands outside the gate

STOP is deliberately absent from the closed registry command set. Its helper starts at S01
and never later acquires S51, so registry unavailability or an exclusive management holder
cannot prevent STOP.
