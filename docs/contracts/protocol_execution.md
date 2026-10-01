# Isolated TEST publication, commit and first START — KL019

`ProtocolExecutionService` accepts only `PublishReady`, the unchanged strict
`contracts.commands.CommitBundle`, and the unchanged strict `StartSession`. Trusted
ingress separately supplies `ExecutionIdentity`: an authenticated TEST RoleIdentity,
exact registered subject, immutable active policy, environment and canonical database
subject principal. Request role/scope fields cannot establish authentication. The
service checks registry metadata before replay and again after S51/S01 for a new
command. Owner connections are internal, idle connections; no public callback, SQL,
connection selection, cursor or aggregate lock API exists. Deployment supplies the
existing internal owner privileges; this task's isolated PostgreSQL fixture uses the
privileged internal test connection, and grants no privilege to subject sessions.

Publication has a separate typed request without `authorization_scope`. The frozen
T3 PublishManifest wire still rejects TEST_ONLY. The adapter rereads READY S23 and
registered immutable artifact identities, then the sole T3 owner verifies its full
candidate and prepares exact S24/S25 data. Generation, validity, closure, published
build, pointer and receipt/event/outbox are one transaction. Changed-key natural-build
retry cannot publish a second generation.

After real KL024 admission/acquisition, T6 checks the current intent/request/attempt,
role-prefixed authenticated lease owner, fence, lease/deadline, Manifest/generation,
epoch and execution basis. The locked policy action scope must remain exactly
TEST_ONLY; production, shadow and evaluation scope mappings deny without effects.
The strict wire's canonical expected_owner_id names the
same authenticated actor; the adapter translates it to KL024's existing role-prefixed
lease key. Locked immutable snapshot/proposal/demand/resolution/validation inputs must
bind that exact chain. The synthetic certificate version used by this bounded slice
requires mandatory context, proposal/demand/resolution hashes, semantic-validation
and policy-envelope PASS, and the exact prior execution basis. These inputs do not
implement the missing upstream validation/planning engines.

An absent first daily head can be created only by CommitBundle, after S51/S01/S27 at
S38's stage, for the exact live intent day. Its date must equal the trusted database
clock's day in the immutable policy's `execution_calendar.timezone`. Calendar policy,
next midnight, ACTIVE lifecycle, null parent and revision zero are server controlled.
S01 serializes the missing natural key; database uniqueness remains authoritative.
The normal guarded T6 writes then switch that exact head to revision one and append
S39/S40/S41/S42, complete normalized artifact closure, terminal success/COMMITTED,
execution basis and bookkeeping. No generic S38 insert capability is added.
The existing certificate evaluator computes every finite bound; a requested absolute
end can shorten it. The adapter accepts only a first bundle, and preserves existing
head-update and Reauthorize owner behavior.

For first START, the existing T7 owner can create only the authenticated request's
absent S44 key at its execution stage, with APP_STARTED identity and server lifecycle.
It rereads exact current P/A/hash/scope/bundle/epoch/control/artifact eligibility and
binds the expected binding revision. Its existing mutation capability advances the
session; the owner supplies the accepted timestamp internally, without adding a
caller-writable timestamp column. Exact S44/S45/S01 and S02/S03/S04 complete or roll
back together. Existing READY/PLANNED, RESUME/CONTINUE and external-execution semantics
are retained. Changed-key START cannot append another START. Successful first START
reports its accepted outcome; every historical retry reports executable=false.
Publication/issuance replay returns historical IDs, never a reusable current permit.

The fixture seeds only registered isolated TEST upstream inputs: immutable
policy/program/artifact/control basis, SEALED factset, projection dependencies and
READY build, plus an explicitly identified prior upstream execution-basis event.
T3 alone produces publication outputs. KL024 services produce the real intent,
request, attempt, root budgets, deadline and lease. Missing RecordSnapshot and
AdvanceAttempt owners require declared privileged synthetic setup of S26, the exact
current attempt's COMMIT_READY/fence context, and S34–S37 certificates outside target
transactions. This is input preparation, never workflow success or owner-driven
planning progress. No S24/S25/S38–S45 or successful intent is seeded for the new flow.
Negative privileged perturbations are labeled separately. Prerequisite regression
fixtures keep their historical synthetic seeds and all assertions byte for byte.

All local lifecycle targets bind tested short SHA and the resolved worktree's exact
12-hex digest, with separate exec/tx/plan/ledger namespaces. The task-owned transaction
launcher validates both existing KL022 overrides before pytest; its fixture is byte
unchanged. Planning and ledger receive only the validator's literal namespace
transformation. Instrumented reset/runner/cleanup proof is separate from real required
PostgreSQL regressions. Broader database CI remains on unchanged hosted ubuntu-latest.

This is task PU/DC evidence only. I01, I02, I04, I07 and A03@DC remain NOT_RUN. No
production activation, executable shadow, provider command authority, downstream
model loop or full workflow/release claim is introduced.
