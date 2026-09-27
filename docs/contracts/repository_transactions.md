# Repository transaction interfaces

`kineticloop.persistence.transactions` is the sole shared transaction harness for
repository command owners. It does not make domain decisions and does not perform
network, model, resolver, projection, or bulk-build work.

Every owner receives a fresh idle PostgreSQL connection and owns the outer commit.
Callbacks never receive that connection, a raw cursor, or an arbitrary SQL execution
method. Cursor state is held outside the callback capability object. Callbacks receive
structured `insert` and `update` operations only after the required guards;
schema/table identifiers are generated from the owner's logical-table capability,
each command has an explicit fail-closed column allowlist, and columns are quoted by
psycopg. Insert allowlists are literal rather than schema-derived, so future columns
cannot silently become writable; database-generated known/recorded timestamps and
revision provenance are never callback supplied. Preparation and build sessions have separate narrower capabilities, so they
cannot express S51/S01 access through the shared interface. The generic command entry
point rejects PREPARATION, BUILD, and external owners; those owners cannot relabel
their work to obtain coordination.
For subject commands, the interface enforces this monotonic sequence:

`S51 (when required) → S01 → S30 → S27 → S31 → S38 → S44 → S02 → remaining aggregate rows`.

Requests for multiple quota, intent, reservation, execution, or remaining aggregate
rows are canonicalized and locked in stable key/UUID order. Any later-to-earlier
request fails locally before issuing SQL. Receipt competition is unavailable until
S01 and every applicable pre-receipt row are held, so a command cannot win or wait on
a receipt and then acquire an earlier lock implicitly through DML. Mutations of
S27/S31/S38/S44 and remaining aggregates must name an ID already locked by the same
command; empty, unrelated, and command-inapplicable lock requests fail closed.

PublishManifest, CommitBundle, Reauthorize, StartSession, ResumeSession, and
ContinueSession must call the merged SafetyRegistry command-specific guard. That
routine obtains shared S51 and then S01, revalidates the exact bounded artifact
closure, and returns the protected registry revision. Artifact consumers must also
match the registered artifact ID, kind, identity, version, and content hash for every
leased artifact before commit; UUID-only eligibility is not sufficient.

The preparation interface exposes only subject-bound structured mutations.
RecordProjection, BuildManifest, ResolveEvidence, RecordValidation, and T5 worker
preparation cannot request coordination locks through it or address another subject.
Factset build commands have a separate subject-bound interface: BeginBuild creates the
exact BUILDING basis, each WriteCandidate advances one member revision with one S16
member, and CompleteFactset freezes the digest, closed member revision, and versioned
completion certificate. Sealing remains a T2-SEAL owner operation that starts at S01
and revalidates that full completion basis, nonnegative member count, captured
frontier, and epoch. BeginBuild validates its captured basis in a preceding short
read transaction so the build transaction itself never carries an S01 lock. Every
T2-IN invalidation requires the command-specific canonical scope declared by the
active policy; free-form or missing classifications fail closed. Where the command
writes the cause record, the barrier scope must also equal that same-command cause
scope.

Durable first execution locks S01 before S02, then locks declared remaining
aggregate rows in canonical table/key order, compares the request hash, and saves the
complete successful outcome in the receipt. Structured mutations must bind the
authenticated transaction subject. The state mutation, S03 event, S04 outbox row, and
successful receipt outcome commit in one transaction. ACK-loss replay uses a distinct
read-only receipt entry point which takes only S01 then S02 (only the natural-key
advisory/S02 guard for T1). It returns the exact historical result without reacquiring
registry, work, artifact, or live-fence guards, so later revocation cannot erase a
committed outcome. Current eligibility is a separate decision. A missing successful
receipt and a request-hash conflict remain distinct failures. T1 serializes a missing
natural receipt key with a transaction advisory lock before admitting evidence. Both
source-revision and observation-key identities are supported, exactly one is required,
and the inserted S09 identity must match the advisory-locked database natural key:
subject/connection/type/object/revision for a source revision, or
subject/connection/observation for an observation key.
Database natural keys remain the last line of defense.

Lease-aware owners prove a command-specific basis for every locked intent:
AcquireLease proves the exact prior owner/token compare-and-swap basis, live worker
commands prove owner/token/status/unexpired lease, and ReapIntent proves the exact
expired/deadline/current-attempt basis. Acquisition persists RUNNING plus the exact
new owner, larger token, and future lease expiry bounded by the intent deadline;
renewal must extend the live lease without crossing that deadline. Reaping atomically
terminates every exact current S27/S29 chain named by the command. ReserveCall creates
an S31 bound to the verified live intent/attempt and a same-command S32 transition.
PermitDispatch additionally requires the reservation's `ref_s27_id` and dispatch
fence to match that verified live intent and token, advances its settlement revision,
and appends the corresponding S32 transition.
AcquireLease and RenewLease expose neither generic S29 mutation nor arbitrary S29
aggregate-lock capability; attempt progression remains owned by the exact guarded
attempt workflow.

`T6CommitCoordinator` is the one repository owner for CommitBundle. It is the atomic
database boundary jointly required by PrescriptionCommitService and
AuthorizationService; neither service receives a partial S39/S40/S41 or S42 commit
interface.
The T6 commit path binds every inserted reference to one exact verified
intent/request/attempt/validation chain and to the locked or same-command inserted
row. The attempt must be COMMIT_READY and bind the current S24 and current S01 epoch.
The verified intent, locked S38, and S39 must name the same local day, and S39/S38
must advance the locked head revision by exactly one. It records the locked S38
revision as S39's parent, allowing null only for the
first head, inserts S39/S40/S41/S42, materializes the exact verified S49 closure for
S42, and links supersession through the prior bundle member/prescription/authorization
chain only when a prior head exists. Supersession binds the old and replacement
authorization scope, current receipt, event kind, and causation key. It
switches S38 to the exact new bundle revision, records S27's bundle and authorization
results, marks S29 COMMITTED, points S01's execution basis to the same-transaction S03
event, and persists S02/S03/S04. S37 must remain PASS, unexpired, and match the locked
policy, manifest, request, attempt, proposal, resolution, and prior execution basis.
S42 carries an issuance reason, authorization epoch, method version, registry revision,
and a deterministic certificate over artifact, manifest, resolution, validation,
request, policy, calendar, and manifest-projection identities. Its issuance time,
method version, and expiry are server-owned; expiry is the dependency bounded
minimum or a shorter requested end. ACK-loss replay returns those same durable identities without repeating any
head, terminal, supersession, event, outbox, or closure transition.

T2 input-admission owners must change the S01 input frontier. Control owners must
append an S17 event and a same-command S18 state row. Actual-execution decisions must
advance S01's execution basis to their same-transaction S03 event. T2-IN owners can
append an `EPOCH_INVALIDATED` S43 bound to the current receipt and cause in the same
command as their decision and S01 epoch/frontier change. Factset sealing binds the
single READY S15 build's closed revision, digest, certificate, captured frontier, and
epoch to the exact current S01 pointer and SEALED state.

T3 publication locks and publishes the single READY S23 build whose captured epoch,
frontier, policy, program, and factset equal current S01. The READY candidate freezes
its dependency-basis hash, the active-policy required projection-role bindings, full
artifact closure, declared artifact roots, and artifact-closure hash. Publication
requires each role's exact active-policy dependency signature, including collection/
absence, engine, factset, policy, program, and applicable mapping/catalog bases. Any
S14 dependency must be an active S16 member of the current SEALED S15. Publication
recomputes the complete basis and rejects any missing, extra, stale, or caller-selected
replacement closure. S24 is
the next generation and binds the exact SEALED factset, projection roles/bases,
catalog/mapping selection, artifact closure digest, manifest hash, registry
state/revision, frontier, and bounded validity. S25 is the complete same-command
projection binding set; S01 and S23 must advance to exactly those published identities.
T4 admits either a new or locked intent and binds S28/S29 to that exact chain, current
epoch, and current manifest.

T7 START requires a READY/PLANNED session with no prior START; RESUME requires PAUSED
with a prior START; CONTINUE requires IN_PROGRESS with a prior START. START and RESUME
revalidate and append S45 for the exact current prescription/authorization pair;
CONTINUE revalidates the pair but cannot append S45. Every command advances the exact
session to IN_PROGRESS with revision +1 and advances S01's execution basis with its
same-transaction S03 event. START/RESUME S45 binds the validated execution scope,
database eligibility time, and next binding revision. A historical replay is
explicitly non-executable.

PermitDispatch locks S01, S27, then S31 and atomically commits its S02 receipt, S03
event, and S04 outbox row with the state transition. Only the first
`RESERVED → DISPATCH_INTENT` winner receives `sendable=true`; replay of the same permit
key receives the durable permit with `sendable=false`. The physical provider request
occurs after commit.
SettleCall and MarkUnknown prepare one exact locked S27/S31/attempt transition,
compare the command's explicit expected transition to the locked S31 source state,
enforce the frozen target state and next settlement revision, and bind one S32 event
to that same reservation, revision, server time, and receipt identity. A contender
blocked behind another settlement must re-read S31 and fail its stale expectation.
Outbox claiming is an isolated S04 transaction with no S01 or business mutation
callback. Consumers release the outbox row before invoking a new idempotent command.

T6 derives the issuance scope from the active policy's mapping for the exact S36
action type; S42 cannot select a scope. The locked S37 must bind the exact S35 named by
its S34 proposal, and the validity certificate includes that demand identity. Neither
CommitBundle nor Reauthorize may commit without S27 `FOUND_VALID_PLAN`, S29
`COMMITTED`, and the new S42 in the same transaction. CommitBundle does not acquire an
unrelated S31 reservation lock because reservations are T5/T8 state.

Exercise catalog revisions are written only by
`ExerciseCatalogService.PublishRevision`; adoption is T2 classification/invalidation.
Exercise mappings are written only by `ExerciseMappingService.DecideMapping`; current
selection is explicit in the sealed factset. Releases are written only by
`ReleaseEvaluationService.RecordRelease`, outside live T1–T8; production activation is
the T2 user-activation entry. T3 consumes the exact immutable S19/S20 identities in its
sealed basis and the already activated exact S48 release/policy. It cannot adopt or
activate them.
