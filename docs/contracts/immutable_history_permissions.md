# Immutable history and write-permission contract

This contract implements the physical protection boundary derived from frozen
`DOC-PROTOCOL-V1.2` and `DOC-DB-V0.2`. It does not change authorization meaning,
T1–T8 atomic boundaries, or the frozen lock order.

## Deny-by-default role model

Physical tables and functions are owned by a non-login migration owner. `PUBLIC`
has no table privileges. Ordinary application and audit roles receive `SELECT`
only. DML belongs to non-login logical command principals that own narrow
`SECURITY DEFINER` routines; application credentials receive only explicit
`EXECUTE` on a command entrypoint. The same principal spans relations that one
frozen transaction must mutate atomically, while split table ownership uses
operation-specific grants. Runtime credentials are never table owners, superusers,
`BYPASSRLS`, or members of migration/writer roles.

The executable S01–S51 matrix lives in
`src/kineticloop/persistence/immutability.py`:

- I-class command owners receive `SELECT, INSERT`; `UPDATE` and `DELETE` are absent.
- M-class command owners receive `SELECT, INSERT, UPDATE`; `DELETE` is absent.
- S03/S04 creation shares the originating-command principal so event/outbox rows
  can be inserted atomically. OutboxDispatcher receives only `SELECT, UPDATE` on
  S04 delivery metadata and cannot fabricate work with `INSERT`.
- S50/S51 share the SafetyRegistry principal required for atomic T2-GLOBAL revoke;
  its entrypoint must also enforce the exclusive registry gate and frozen lock order.
- S23 build state receives guarded owner `UPDATE`; it grants no command authority.
- S15/S16 receive guarded owner `UPDATE` only during their build phase. S15 is
  immutable from READY onward; S16 mutations are rejected when its parent is READY
  or SEALED. Only SEALED content is canonical history.
- no runtime permission cell grants `DELETE`. Privacy erasure is a separate,
  reviewed maintenance path that preserves permitted tombstone/unavailable history.

Grant generation first revokes `PUBLIC` and every concrete runtime/writer role from
each table, then grants the exact cell. This removes stale cross-owner grants rather
than assuming they do not exist. Production migrations must apply the generated
grants after table creation and add relation-specific transition triggers for
M/B/B→I tables.

## Defense in depth

Permissions establish who may issue a statement. Repository and trigger guards
establish which transition that owner may issue. Immutable relations reject
`UPDATE` and `DELETE` even if a future grant is accidentally widened. Mutable and
build relations validate old state, new state, revision/fence expectations, and the
command's T1–T8 transaction guards. A trigger is not allowed to call a model,
network service, or acquire locks contrary to the frozen order.

Relation rows carry a conservative inventory of possible guard requirements, but
that union is not an executable command contract and must never be applied to every
path. Authoritative `COMMAND_ENTRYPOINTS` bind command identity, orchestrating
principal, each touched relation/operation and its writer principal, atomic group,
ordered locks, and path-specific guards. They explicitly keep S15 build work on the
build lock while SealFactset takes user → build, and keep T2 external-execution fact
acceptance independent of the registry while taking user → execution and atomically
advancing S01 execution basis. T7 START/RESUME takes registry-shared → user →
execution and checks current authorization. T2-SEAL, T2 external execution, and T7
also include their S02 receipt mutations in the same transaction. Grants are
incomplete unless the applicable entrypoint contract is materialized.

The KL-012 PostgreSQL fixture demonstrates the minimum enforcement shape:

1. the application role cannot insert, update, delete, alter, or disable guards;
2. the immutable-history writer can append but cannot update or delete;
3. only the transition owner can perform the declared `OPEN → SEALED` update;
4. even that owner cannot reverse or reshape a sealed transition;
5. the originating command can insert S04 but cannot update delivery metadata;
6. OutboxDispatcher can perform the guarded delivery update but cannot insert S04;
7. the application appends immutable history only through an actual
   `SECURITY DEFINER` routine owned by a NOLOGIN writer, cannot assume that role,
   and cannot issue equivalent direct DML.

The fixture is intentionally minimal. KL-013 owns full baseline DDL, including
installing these grants and lifecycle guards on every physical table and typed child
relation and command routine. Any deployment mapping multiple logical principals to
a process must retain a non-forgeable routine/role binding; a generic write
connection or caller-controlled `SET ROLE` is prohibited.

## Protocol mapping

- INV-02: model output and ordinary application SQL have no command-owner write role.
- INV-16: historical revisions are append-only, preserving cutoff-aware replay.
- T1–T8: each unique writer remains scoped to its declared command transaction;
  this contract adds no cross-stage transaction and performs no external work.
- SafetyRegistry/S01 ordering: unchanged. Permission checks do not replace the
  registry gate, S01 coordination lock, current-state rereads, or final guards.
