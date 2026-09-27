# SafetyRegistry shared/exclusive gate contract

This contract materializes frozen S49--S51 coordination without changing Protocol or DB
semantics. The production repository executes only the narrow command routines installed by
the SafetyRegistry successor migration; PostgreSQL tests use the migrated schema rather than
fixture-local S01/S49/S50/S51 definitions.

## Deployment and role boundary

An empty deployment is intentionally two phase. An externally provisioned
`kl_cluster_bootstrap` session applies only the immutable KL-013 baseline, disconnects, and an
external administrator hands every baseline schema object to NOLOGIN `kl_migration_owner`.
A new NOSUPERUSER/NOCREATEROLE `kl_migration_deployer` session, with only SET membership in
`kl_migration_owner` and `kl_writer_safety_registry`, applies the successor. Its first action is
a fail-closed catalog preflight over the owner, application, audit, trusted-admin, and deployer
roles. The successor contains no cluster-role or role-membership DDL.

All S01--S51 tables, sequences, and non-command guards remain owned by
`kl_migration_owner`. The six command-specific shared-gate routines are executable only by
`kl_application`; the non-overloaded revoke routine is executable only by NOLOGIN
`kl_trusted_admin`. Those seven fixed-search-path SECURITY DEFINER routines are owned by
NOLOGIN `kl_writer_safety_registry`. Runtime login roles receive external membership in the
execution roles but cannot SET either owner role or issue direct S49/S50/S51 DML.

Each command routine fixes its complete `search_path` to exactly `pg_catalog, kineticloop,
pg_temp`, with the temporary schema explicit and last, and schema-qualifies every KineticLoop
object reference. The `kineticloop` schema is owned by `kl_migration_owner`; PUBLIC and every
runtime, execution, writer, bootstrap, and deployment role lack schema CREATE authority. After
Phase A and the ownership handoff, the external bootstrap role is de-elevated. The application
and trusted-admin logins retain exactly one inherited, non-SET, non-admin execution-role
membership, own no migrated objects, and cannot administer or assume deployment or owner roles.

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

The T6 routines require S01's current manifest and active policy to identify a current S24
whose subject, policy, captured authorization epoch, registry revision, validity, and primary
S49 reference remain eligible. The T7 routines require a current S42 for the subject whose
certificate epoch still equals S01, whose validity interval includes authoritative database
time, whose registry revision is not from the future, which has no targeted S43 invalidation,
and whose migrated S42 closure contains every supplied S49 identity with current validity.
These registry predicates do not replace the remaining downstream T6/T7 command-owner guards.

T3 differs from T6/T7 because it creates the next current Manifest. Its shared-gate routine
therefore locks S51 then S01 and validates the caller-supplied candidate artifact closure
without requiring an outgoing current S24. The T3 command owner, while both locks remain held,
must bind that exact leased closure to the single READY build, validate every declared root,
persist the full root and closure identities in the new immutable S24, and atomically advance
the S01 pointer. The registered artifact bound to active S05 anchors the selected graph;
S48-bound artifacts must name releases reachable from that policy artifact and any S19-bound
artifact must equal the selected catalog. Declared roots are exactly the graph roots of the
leased closure, not an arbitrary subset or superset. This permits bootstrap, policy/release transitions, and consecutive
publications without treating the previous Manifest as authority for the incoming closure.

Every helper requires an idle PostgreSQL connection and owns the top-level transaction through
commit. Invocation inside an existing transaction is rejected, so the API cannot return while
S51 remains held in an outer transaction or allow a caller to reverse the S51-before-S01 order.
Database failure before mutation is a fail-closed availability denial. A failure raised by the
mutation or while committing is propagated as an unknown outcome and is never mislabeled as a
deterministic registry denial; the caller must reconcile through the command's idempotency key.

## Global revoke

`RevokeArtifact` requires database-session membership in `kl_trusted_admin` and acquires S51
with `FOR UPDATE`. It never reads or locks S01. In the same T2-GLOBAL transaction it appends
S50, advances S51, and writes
the management receipt, audit event, and outbox identity. The successful commit—not
`effective_at`—is the execution linearization point. `effective_at` remains audit metadata,
so a future value does not schedule eligibility and a past value does not rewrite historical
authorization facts.

The effecting `effective_at` and `reason_code` values must match the command's canonical
`revocation_payload_hash`; neither is accepted as unhashed side input. The receipt is checked
after the exclusive gate. A repeated command key and request hash
returns the stored original result; reusing the key with another hash is rejected. Any insert
failure rolls back every T2-GLOBAL effect.

The routine persists `session_user` as the management operator. Caller-supplied actor identity
or capability fields are never database authorization inputs and cannot replace the
session-bound trusted-admin membership check.

The management receipt/audit/outbox relations are physical T2-GLOBAL companions to S50, not
alternate S02/S03/S04 logical relations. Frozen S02/S03/S04 remain the subject-command chain;
the migrated integration suite exercises that chain as the immutable basis of the current S42
used by T7, while proving a global revoke does not rewrite it.

## Commands outside the gate

STOP is deliberately absent from the closed registry command set. Its helper starts at S01
and never later acquires S51, so registry unavailability or an exclusive management holder
cannot prevent STOP.
