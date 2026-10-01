# Source-bound TEST preparation

`PreparationService` supplies the existing RecordProjection and BuildManifest
PREPARATION owners. Trusted ingress supplies `PreparationIdentity` independently
of each request, over an idle internal owner connection. Its TEST actor, registered
subject/policy/environment and principal binding must match. Subject connections,
role changes, PRODUCTION and EVALUATION registrations fail closed. This identity
is an ingress binding; outputs carry `executable: false` and no authorization.

Call `capture_source(actual_sealed_factset_id)` after CanonicalViewService has
built, populated, completed and sealed that subject's factset. The returned typed
`SourceBasis` binds the exact immutable source hash, captured frontier/epoch,
program, policy, mapping and catalog. RecordProjection verifies it again inside
its independent transaction. BUILDING, READY, missing and foreign sources reject.
It does not read or lock S01 or S51, or claim that an old sealed source is current.

Compute the projection before calling `record_projection(RecordProjection(...))`.
Supply its kind, exact engine artifact identity, query window, result, explicit
validity and complete typed dependency signature. The server verifies the policy
signature, exact positive FACT members and collection/absence signatures and
derives POLICY/PROGRAM/FACTSET/MAPPING/CATALOG references from the sealed source.
ENGINE names the exact engine identity/version. The engine proof, source, window,
content hash and computation request hash remain durable canonical provenance.
Caller revision/provenance injection is forbidden. For a new immutable
subject/kind/basis identity, the server supplies revision **1** only at this exact
S21 insertion. REQUIRED_FIELDS, caller column permissions and metadata stay intact.
Changing content, engine, window or validity under that same identity conflicts;
a new source basis creates a new immutable identity with baseline revision 1.
Dependency order is canonical. S21 and the entire S22 closure commit together or
roll back together. No update/replacement of either history is available.

`build_manifest(BuildManifest(...))` verifies the exact policy role list, immutable
projection parents, source and artifact roots/closure and inserts one BUILDING
S23 with the complete captured candidate. All persisted candidate hashes derive
from the exact source, dependency rows and artifact identity/validity proofs.
Missing/duplicate roles, foreign parents/artifacts or source changes reject.
`complete_manifest(CompleteManifest(build_id))` takes only that S23 row's local
lock, checks its durable owner and changes BUILDING to READY while preserving its
candidate basis. READY/PUBLISHED replay returns the historical completion; other
terminal states cannot reopen. Captured source/frontier/epoch and candidate content
cannot be relabeled or mutated through generic preparation callbacks.

Projection and build creation use owner-local advisory identity locks to serialize
missing-row contenders; completion uses the exact S23 row lock. The internal
restricted session receives a server-only plan and must insert exactly its rows
and perform exactly its READY transition. A generic callback, fabricated lock
inventory or source context cannot obtain this capability. Public wire schemas,
the command/owner capability matrices, PREPARATION boundaries, execute_command
rejection and the unrelated S34–S37 workflow remain unchanged.

ACK-loss retries authenticate ingress but return historical identities before
current eligibility checks and never mutate rows. Begin replay returns its original
BUILDING outcome even after READY/PUBLISHED; completion replay returns its original
READY outcome. A changed same-key request conflicts. These are historical outcomes,
not current or execution authority.

Only actual ProtocolExecutionService.publish/T3 can publish S24/S25, advance S01
head/generation, or write the publication receipt/event/outbox. It independently
rechecks current factset/frontier/epoch/program/policy, dependency hashes, validity,
artifact activation and revocation under the unchanged shared S51 → S01 lock order.
This repair stops at T3. It does not implement Fitness/Demand/Nutrition, T6/T7,
production issuance or shadow execution.

The named tests use their own SHA/resolved-root-derived KL078 Compose/database
namespace. They validate before construction, selected-lifecycle bootstrap, nested
reset/start/Compose calls and finally cleanup. Sources are registered immutable
TEST fixtures only; S15/S16, S21/S22, S23 and S24/S25 always come from their actual
owners. Local tests never invoke legacy seed/reset fixtures. Existing hosted CI
owns the full legacy DB regression suite on its fresh runner.
