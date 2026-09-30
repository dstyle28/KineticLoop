# CanonicalViewService — KL-023

Authority: Protocol v1.2 §§2, 4.1a, 8; logical DB v0.2 S01–S04,
S15–S16, T2, §8.2 and §11. KL-015 remains the single transaction owner.
These checks implement KL-023; B01–B03/I08 and release requirements remain
with their downstream acceptance owners, including KL-032.

`CanonicalViewService` takes an idle PostgreSQL connection and a trusted
`BuilderIdentity(RoleIdentity, subject_id)` supplied by authenticated ingress.
Commands cannot assert another actor or subject. The actor's role must match
the registered PRODUCTION/TEST subject namespace. The exact builder
identity is frozen at BeginBuild and required for every build mutation and seal.
Ingress must bind RoleIdentity and subject_id before constructing the service;
these Python value objects are not authentication tokens. Evaluation actors cannot
construct this live service; replay/evaluation artifacts remain under S46/S47.

The typed commands are `BeginBuild`, `WriteCandidate`, `CompleteFactset` and
`SealFactset`. Build keys are local to the subject/build/command; seal keys are
subject/actor/command receipt keys and must be distinct across builds. Begin IDs
and operation IDs are deterministic. Begin serializes the absent S15 identity
using a transaction advisory lock, then checks the committed S01 snapshot
without locking S01. WriteCandidate locks only S15, inserts exactly one S16
operation and advances member_revision once. The physical natural key forbids
multiple operations for the same kind/key/scope within one build. A subsequent
replacement uses a new build. Build key/request hash/outcome records live in
S15's typed payload, are committed with their mutations, and freeze at READY.
Same keys and payloads return original identities even after SEALED. Complete
also replays by build/closed revision/digest across transport keys, and Seal by
build/completion identity across transport keys, without new head/event/outbox writes. Changed
payloads and new writes to closed revisions fail.

EvidenceBasis explicitly lists the complete selected association, admission and
mapping revisions, knowledge boundary and effective scope. Reconstruction checks
that every selected revision is retained as a typed logical member; a selected
fact must retain its admission revision. UNRESOLVED associations, denied admissions
and contrary evidence remain members. This service does not decide qualification,
resolve provider evidence, infer missing actuals or authorize execution.

FULL/DELTA reconstruction orders `(kind, logical key, action scope)` and applies
SET/REMOVE to the nearest FULL checkpoint. Every ancestor must exist, belong to
the subject, be SEALED, have consistent depth and have its own matching closed
digest/count. Cycles, missing/foreign/unsealed parents, duplicate logical members,
unsupported kinds/operations and chains beyond the command's explicit depth bound
fail. BeginBuild requires the supplied maximum depth to equal the selected immutable
policy's `factset_max_delta_depth`; it captures that bound immutably. At the depth boundary, BeginBuild reconstructs the sealed
parent outside coordination and stores a complete FULL checkpoint in the closed
S15 typed content; subsequent S16 operations overlay it. This uses existing JSONB
storage and introduces no migration. A FULL has depth zero and no parent dependency.
Deletion creates tombstones and never deletes historical facts.

Complete reads S15/S16 and ancestors in one read-only repeatable-read snapshot.
Reconstruction, typed-reference validation and digest/count derivation run before
acquiring the build gate. The digest binds all ordered logical members and the
complete EvidenceBasis. The S15 lock then compares the expected member_revision;
if a writer has advanced it, completion fails without a READY transition. A
successful Complete freezes exactly that revision, count, digest and certificate.
The certificate additionally binds subject/build/frontier/epoch, authenticated
builder, program/policy/mapping, parent and maximum depth. It cannot be reused for
another revision or basis. READY content is immutable and noncanonical.

T2-SEAL uses the existing S01 → S02 → S15 owner path and verifies the exact READY
revision, completion identity/certificate/digest/count, current frontier and epoch,
and active program/policy against the captured basis. It never loads S16 or
recomputes the logical membership under S01. S15 SEALED, S01 head, S02 receipt,
S03 event and S04 outbox commit atomically. Failure leaves all surfaces unchanged.
Historical S02 replay returns the original seal result without reacquiring S15,
reconstructing members or repointing a newer head. `read_canonical` accepts only
validated SEALED chains and rechecks their certificates and logical digest/count.

The database suite uses `kineticloop_kl023_<shortsha>` and
`kineticloop-kl023-<shortsha>`, with a registered TEST subject, dedicated policy and
environment. The fixture destroys only its own Compose resources. Writer/Complete
and T2-IN/SEAL tests use bounded barriers and `pg_blocking_pids` observations, assert
persisted outcomes in both serial orders, and never use sleeps as an oracle.
They also prove that S01 is obtainable during reconstruction/build gating,
that seal executes no S16 statements, that injected failures roll back all five
surfaces, and that old replay preserves a newer head. Regression suites run
sequentially with the packet's separate KL023-owned KL022 namespace overrides.
