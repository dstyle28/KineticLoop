# Immutable history and write-permission contract

This contract implements the physical protection boundary derived from frozen
`DOC-PROTOCOL-V1.2` and `DOC-DB-V0.2`. It does not change authorization meaning,
T1–T8 atomic boundaries, or the frozen lock order.

## Deny-by-default role model

Physical tables and functions are owned by a non-login migration owner. `PUBLIC`
has no table privileges. Ordinary application and audit roles receive `SELECT`
only. Each relation has one command-owner role derived from its frozen unique
writer. Runtime credentials are never table owners, superusers, `BYPASSRLS`, or
members of migration roles.

The executable S01–S51 matrix lives in
`src/kineticloop/persistence/immutability.py`:

- I-class command owners receive `SELECT, INSERT`; `UPDATE` and `DELETE` are absent.
- M-class command owners receive `SELECT, INSERT, UPDATE`; `DELETE` is absent.
- S23 build state receives guarded owner `UPDATE`; it grants no command authority.
- S15/S16 receive guarded owner `UPDATE` only during their build phase. S15 is
  immutable from READY onward; S16 mutations are rejected when its parent is READY
  or SEALED. Only SEALED content is canonical history.
- no runtime permission cell grants `DELETE`. Privacy erasure is a separate,
  reviewed maintenance path that preserves permitted tombstone/unavailable history.

Grant generation first revokes `PUBLIC` and all named-role privileges, then grants
the exact cell. Production migrations must apply the generated grants after table
creation and must add relation-specific transition triggers for M/B/B→I tables.

## Defense in depth

Permissions establish who may issue a statement. Repository and trigger guards
establish which transition that owner may issue. Immutable relations reject
`UPDATE` and `DELETE` even if a future grant is accidentally widened. Mutable and
build relations validate old state, new state, revision/fence expectations, and the
command's T1–T8 transaction guards. A trigger is not allowed to call a model,
network service, or acquire locks contrary to the frozen order.

The KL-012 PostgreSQL fixture demonstrates the minimum enforcement shape:

1. the application role cannot insert, update, delete, alter, or disable guards;
2. the immutable-history writer can append but cannot update or delete;
3. only the transition owner can perform the declared `OPEN → SEALED` update;
4. even that owner cannot reverse or reshape a sealed transition.

The fixture is intentionally minimal. KL-013 owns full baseline DDL, including
installing these grants and lifecycle guards on every physical table and typed child
relation. Any deployment mapping multiple logical owners to a process must retain a
non-forgeable command-to-role binding; a generic write connection is prohibited.

## Protocol mapping

- INV-02: model output and ordinary application SQL have no command-owner write role.
- INV-16: historical revisions are append-only, preserving cutoff-aware replay.
- T1–T8: each unique writer remains scoped to its declared command transaction;
  this contract adds no cross-stage transaction and performs no external work.
- SafetyRegistry/S01 ordering: unchanged. Permission checks do not replace the
  registry gate, S01 coordination lock, current-state rereads, or final guards.
