# HG041 upstream audit and producer/consumer contract

Protected base: `035644e0cfb94927d7555e245223cd92c224ea5a`, actual normal KL076 PR79 merge.
Governance only; candidate diagnostics are read-only/pure feasibility, never KL079,
DC, product, M3 or release PASS. No new owner is implemented here.

## Verified gap

`workflow/deterministic_planning.py` has `Resolution.action_type: Literal[TRAINING]`;
`resolve` hashes F.action. `persistence/deterministic_planning.py` generates one
RESOLUTION identity per attempt/kind, writes S36.action_type=TRAINING and a fitness
query basis, then S37.ref_s36_id names that resolution. `Validation` contains N/D
hashes but no action-specific N resolution. Frozen DB S36 explicitly disallows
using equal result hashes to prove another action's applicability. Existing KL077
source/output contract requires exact action resolutions and forbids filling a
missing upstream capability with seeds; its write scope excludes both producer
modules. KL076's completed task/result/evidence are immutable, so this is KL079.

## Supported physical representation and exact scope

Actual metadata and migration `76fd67f76bd4` give S37 one same-subject composite
FK to S36, one proposal FK, one D FK, plus request/attempt/manifest/policy and
execution-event FKs. There is no second resolution column. S36 and S37 already
support immutable hashed JSONB typed_payload. The packet pins one S37 anchored
to TRAINING with ordered closed per-action bindings. The additional N resolution
is explicitly owner-verified, never mislabeled a physical FK. Proposal column
remains N, D column remains D, preserving existing anchor behavior; full bindings
name F for TRAINING and N for NUTRITION. Both full S36 identities include exact
F/D/N and action-specific parameters. Legacy IDs/hashes/profile remain unchanged.

NUTRITION is only the existing mechanical fuel TARGET in fixture units from N/F/D,
not clinical intake or actual nutrition evidence. Both resolutions derive their
coverage from actual sealed admitted source membership and explicit fixed policy;
required_members alone cannot establish applicability. All finite expiry bounds
propagate; source/policy/subject/action/parameters/current-state mismatches deny.

## Full consumption chain

KL075 `AdvanceAttempt` has exact fixed source maps. VALIDATING→COMMIT_READY takes
snapshot/F/D/N/resolution/validation; the resolution entry stays TRAINING. Existing
`transactions._progress_sources` checks a single S36 and S37, so KL079's exact
transaction path must verify the additional full bindings while preserving legacy
behavior. No edit of either planning_progress module, new stage or wire extension
is needed. Both resolution requests/full validation run at VALIDATING; S29 stage
transition remains an actual guarded owner operation.

KL077's permitted files contain the downstream gaps: `ProtocolExecutionService`
currently creates one TRAINING prescription/issuance; `prepare_commit_authorization`
compares the single S37 proposal anchor with D's F, and legacy semantic validation
reads one proposal/action. KL077 must consume the new certificate's per-action
bindings, preserve N.demand_feature_id=D and D.ref_s34_id=F, validate each distinct
member content and exact S42 resolution plus shared S37, then commit the complete
bundle atomically under unchanged guards/lock order. This does not make S37 a
bearer authorization. KL079 must not implement or self-gate on future T6/T7.

Ordinary pause's separate internal descriptor, exact lifecycle revision and current
T7 continuation/resumption are already expressible within KL077's files. Those
oracles/scope are retained intact. KL027 hard-depends on KL077 and therefore KL079
transitively; adding a direct redundant edge or rewriting its claims is unnecessary.

## Prerequisites and verification limits

KL079 explicitly waits for normal merged KL076/KL075/KL078/KL024/KL019/KL017/KL074
and M2 closure; its new source/fixture/tests/docs paths and transaction/user resource
keys are exact, with no migration/CI/public registry/frozen writes. It must run its
own namespaced real-PG owner pipeline, denials, replay/conflict/duplicates/rollback,
F2 repair and legacy positive regression; hosted legacy DB CI stays unchanged.
All prospective checks remain NOT_RUN. Governance tests pin this packet and reject
scope/dependency/review/oracle weakening. Pure candidate feasibility shows two
representable bindings, actual mechanical F/D/N computation and negative binding
controls; it does not demonstrate owner acceptance, PostgreSQL or an executable
certificate. The original missing capability is retained as a diagnostic fact.
