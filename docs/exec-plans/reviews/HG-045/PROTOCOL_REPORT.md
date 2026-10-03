# HG-045 independent protocol review

Verdict: **PASS**. BLOCKER: 0; REQUIRED_FOLLOWUP: 0; NONBLOCKING: 0.

Identity: `harness-governance-v0.1/HG-045`. Protected base:
`26906bd7f4444914c228e98377f2b164fee0dd5d`. Tested implementation:
`263c82e761747b88ac56f96be014e158f494dae0`. Reviewed governance/evidence:
`478a46a418fc759c1843ce24702ccee7aafcddc2`. This is an independent specialist
review of that Git diff and committed evidence, using the pr-merge-reviewer and
protocol-guardian skills. It certifies this governance definition, not prospective
runtime conformance, M3 closure, integration of HG-045, or product/release PASS.

## Frozen authority and source meaning

Resolved authority through CURRENT_DOCUMENT_INDEX.json and read the governance,
merge and review contracts, Protocol 3.2–3.3/6.2 and relevant authorization,
validity, T6/T7 clauses, and DB S12/S13/S27/S36 and fixed lock order. Independently
compared Git blobs: every frozen file, FROZEN_BASELINE.json, current requirement
set, and acceptance specifications are unchanged. No runtime, unit/DB fixture,
migration, CI, completed result, historical artifact or M3 instance is modified.

The prospective correction matches frozen source authority: S13
ELIGIBLE/NOT_ELIGIBLE/UNRESOLVED and physical S12 MATCHED/AMBIGUOUS/RETRACTED.
S27 PlanningIntent ADMITTED remains valid under Protocol 6.2; derived S36
event_association_status=CONFIRMED remains distinct from physical S12. TEST_ONLY
remains an explicit isolated policy scope. The packet preserves the current
runtime identifiers, RULES, request/registration contract, source provenance,
membership, finite freshness, deduplication, contradictions and actual-versus-target
separation. Provider evidence receives no command authority.

Static inspection confirmed that the persistence reader copies the physical
source values, the pure resolver currently expects ADMITTED/CONFIRMED, and full T6
currently filters S13 ADMITTED. The committed eight-case protected-base pure probe
is correctly labeled defect diagnosis: only the malformed pair succeeds for each
profile, with rolling_minutes=40. It is never canonical conformance PASS.

## Truthful guard proofs and fixture feasibility

KL-080.md:108–122 separately pins canonical full T6 reach, invalid full T6 earlier
reconstruction denial, and exact real-PostgreSQL freshness predicate support.
Inspected transactions.py:4219/4319 and deterministic_planning.py:751: actual
_progress_sources invokes full reconstruction before the later freshness query.
The packet therefore does not demand an impossible later-guard reach for malformed
source values or count an ingress/lifecycle/hash rejection as source denial.

The historical ADMITTED+CONFIRMED representative is explicitly permitted only as
an isolated prior-deployment fixture using exact protected-base Git-verified
runtime/helper blobs in a separate owned subprocess. Current KL080 lifecycle and
explicit URLs/current_database assertions remain mandatory. Inspected the pinned
ready/preparation_chain/prepare_validation/commit_ready helpers: genuine owners
produce F/D/N, both S36, shared S37 and COMMIT_READY before T6. The returned
unconsumed request can then be presented unchanged to corrected current T6.
Reconstruction denial must preserve immutable rows and all output, receipt, event,
outbox, head, root and session state. The packet forbids temporary guard patches,
target output seeds, row rewrites, forged certificates, foreign lifecycles and
retroactive acceptance certification. Other malformed values are tested through
pure/preparation denials and explicitly labeled predicate support. FEASIBILITY.md
is planning evidence; it claims no PostgreSQL execution or future task PASS.

The support query may use only a narrowly extracted internal read helper shared
with actual T6. Canonical full T6 must independently reach and pass that actual
query. These definitions preserve admission, authorization, atomic boundaries,
SafetyRegistry/S01 lock order, owner guards, external-wait placement, and
production/shadow separation; no frozen amendment is needed.

## Prospective status and M3 preservation

Independently compared backlog values: every pre-existing task is identical to
the protected base; only KL080 is appended as NOT_STARTED with empty requirement
and evidence claims. Its 17 named commands/oracles and packet/write/resource
scope are hash-pinned and exactly projected. All new checks remain NOT_RUN.
There is no KL080 result/integration or M3.json. Six source-literal corrections in
four older fixture files are content-guarded; uncertain sources remain AMBIGUOUS,
denied sources remain NOT_ELIGIBLE, and every other byte is preserved.

The M3 active set is exactly 17. Independently compared protected-base constants:
all seven prior exit mappings, prior check digests and the entire ordered regression
command prefix are unchanged. The new exit pins all 12 source PU/DC checks, each
exact command and oracle digest, with required fresh integrated selectors/suites.
Schema cardinalities require 17 integrations/eight exits. Existing closure readers,
M1/M2 dependencies, KL074 support, HG043 regular-blob provenance, transitive
merged-prerequisite ancestry, raw collection/JUnit integrity, 31-row boundary and
10-row interleaving ledgers, deferred shadow/R04 and empty product claims retain
their meaning. Hevy/HealthKit and retired spreadsheet policy remain unchanged.

## Evidence assessment and limits

Verified ancestry base→tested→reviewed and the evidence/governance-only tested
suffix. Independently checked all nine selected captures against committed Git
raw bytes, UTF-8, byte counts, SHA256, command, zero exit code, result and tested/base
SHAs, including the integrity manifest's capture hashes. Recorded execution counts
are 36 focused, 925 harness and 241 unit passes. Preserved failing development
diagnostics and whitespace output remain unselected; the selected whitespace
check's exact preserved-raw exception is explicit and is not a scope exclusion.

Read prerequisite PASS results and independently reran the read-only integration
audit for all ten declared prerequisites: every integration had zero semantic
errors. KL028/KL029 additionally passed byte-identical historical-result, linear
own-review suffix and normal two-parent merge checks.
Historical UNMERGED result payloads remain immutable; separate integration records
describe actual merged state. Their normal merge and own review-record suffixes
do not reinterpret historical evidence. No full test suite or DB lifecycle was
rerun during this review. Real-PG corrective proofs and fresh M3 regression remain
future obligations, and final hosted checks plus the remaining required specialist
reviews are separate merge requirements.
