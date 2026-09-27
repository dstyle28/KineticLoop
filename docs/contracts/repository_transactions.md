# Repository transaction interfaces

`kineticloop.persistence.transactions` is the sole shared transaction harness for
repository command owners. It does not make domain decisions and does not perform
network, model, resolver, projection, or bulk-build work.

Every owner receives a fresh idle PostgreSQL connection and owns the outer commit.
Callbacks never receive that connection, a raw cursor, or an arbitrary SQL execution
method. They receive structured `insert` and `update` operations only after the
required guards; schema/table identifiers are generated from the owner's logical-table
capability and columns are quoted by psycopg. Preparation and build sessions have
separate narrower capabilities, so they cannot express S51/S01 access through the
shared interface.
For subject commands, the interface enforces this monotonic sequence:

`S51 (when required) → S01 → S30 → S27 → S31 → S38 → S44 → S02 → remaining aggregate rows`.

Requests for multiple quota, intent, reservation, execution, or remaining aggregate
rows are canonicalized and locked in stable key/UUID order. Any later-to-earlier
request fails locally before issuing SQL. Receipt competition is unavailable until
S01 is held, so a command cannot win or wait on a receipt and then wait for S01.

PublishManifest, CommitBundle, Reauthorize, StartSession, ResumeSession, and
ContinueSession must call the merged SafetyRegistry command-specific guard. That
routine obtains shared S51 and then S01, revalidates the exact bounded artifact
closure, and returns the protected registry revision. Artifact consumers must also
match the registered artifact ID, kind, identity, version, and content hash.

The preparation interface exposes only subject-bound structured mutations.
RecordProjection, BuildManifest, ResolveEvidence, RecordValidation, and T5 worker
preparation cannot request coordination locks through it or address another subject.
Factset build commands have a separate subject-bound interface which locks only their
S15 build; sealing remains a T2-SEAL owner operation that starts at S01.

Durable command execution locks S01 before S02, then locks declared remaining
aggregate rows in canonical table/key order, compares the request hash, and saves the
complete successful outcome in the receipt. Structured mutations must bind the
authenticated transaction subject. The state mutation, S03 event, S04 outbox row, and
successful receipt outcome commit in one transaction. ACK-loss replay returns that
exact outcome without rerunning the mutation. Database natural keys remain the last
line of defense.

`T6CommitCoordinator` is the one repository owner for CommitBundle. It is the atomic
database boundary jointly required by PrescriptionCommitService and
AuthorizationService; neither service receives a partial S39/S40/S41 or S42 commit
interface.

PermitDispatch locks S01, S27, then S31 and atomically commits its S02 receipt, S03
event, and S04 outbox row with the state transition. Only the first
`RESERVED → DISPATCH_INTENT` winner receives `sendable=true`; replay of the same permit
key receives the durable permit with `sendable=false`. The physical provider request
occurs after commit.
Outbox claiming is an isolated S04 transaction with no S01 or business mutation
callback. Consumers release the outbox row before invoking a new idempotent command.

Exercise catalog revisions are written only by
`ExerciseCatalogService.PublishRevision`; adoption is T2 classification/invalidation.
Exercise mappings are written only by `ExerciseMappingService.DecideMapping`; current
selection is explicit in the sealed factset. Releases are written only by
`ReleaseEvaluationService.RecordRelease`, outside live T1–T8; production activation is
the T2 user-activation entry. T3 consumes the exact immutable S19/S20 identities in its
sealed basis and the already activated exact S48 release/policy. It cannot adopt or
activate them.
