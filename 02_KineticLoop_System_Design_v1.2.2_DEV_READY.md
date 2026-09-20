# KineticLoop — System Design v1.2.2 Development Baseline

**Development:** NOT STARTED  
**Status:** Development-ready architecture baseline; frozen protocol/DB semantics unchanged  
**Canonical protocol:** `05_KineticLoop_Protocol_v1.2_FROZEN.md`  
**Canonical logical schema:** `04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md`

## 1. Architecture thesis

KineticLoop uses **deterministic truth + bounded AI reasoning + deterministic authorization/commit**.

```text
External Sources / User Commands
          ↓
Immutable Evidence + Command Gateway
          ↓
Evidence Association / Admission / Canonical Facts
          ↓
Factset build → READY → SEALED
          ↓
Derived Projections
          ↓
DecisionManifest publication
          ↓
Mandatory Context + bounded read-only Context Tools
          ↓
Fitness Coach → PrescriptionDemandFeatures → Nutrition Coach
          ↓
Evidence Resolver + Validation / Policy Envelope
          ↓
Authorization issuance
          ↓
Execution binding + actual ingestion
          ↓
Corrections / projections / replay / evaluation
```

The architecture intentionally prevents two opposite failures:

1. **Rule-engine rigidity:** AI retains meaningful coaching judgment.
2. **LLM authority creep:** model outputs do not define truth, approvals, or execution permission.

## 2. Ownership model

| Concern | Owner |
|---|---|
| Source identity, known/effective time | deterministic ingestion |
| Assertion extraction | model/code candidate only |
| Event association/admission | versioned domain policy + deterministic writer |
| Derived features/projections | deterministic engines |
| Modality/sequence re-entry/exercise selection | Fitness Coach AI |
| Daily nutrition reasoning | Nutrition Coach AI |
| Evidence completeness/support/contradiction | authoritative Evidence Resolver |
| Hard limits/cumulative envelopes | versioned policy/validator |
| Planning retries/budget/deadline | persistent workflow engine |
| Canonical state writes | domain command services |
| Authorization | AuthorizationService + frozen guards |
| Emergency STOP/revoke | control path, no LLM dependency |
| Historical evaluation | isolated ReplayService |

## 3. Runtime topology

Start as a **Python modular monolith + worker + independent reaper + PostgreSQL**.

```text
Client / CLI / future iOS/Web
          │
       FastAPI
          │
  ┌───────┴────────────────────────────┐
  │ Domain modules / command services │
  │ Evidence · Program · Training     │
  │ Planning · Authorization · Replay │
  └───────┬────────────────────────────┘
          │
      PostgreSQL
          │
   Outbox / jobs
      │        │
   Worker   Reaper/Watchdog
      │
OpenAI Responses API + provider APIs
```

No microservice boundary is required to enforce the frozen semantics. Logical ownership is implemented as module/service boundaries first.

## 4. AI runtime design

V1 does **not** depend on OpenAI Agents API. Orchestration is application-owned using the OpenAI Responses API, tool/function calls, and structured outputs.

The Agent never receives arbitrary SQL. It receives:

1. a mandatory context snapshot bound to one DecisionManifest and request revision;
2. typed read-only tools that return versioned evidence/history;
3. a structured proposal schema.

Autonomous retrieval is allowed, but evidence obligations are external. For example, an Agent can propose a load increase; it cannot prove its own evidence sufficiency by selectively citing favorable rows.

## 5. Context architecture

Mandatory context contains at least:

- goal hierarchy and active Program;
- active controls/restrictions/holds and authorization basis;
- sequence and progression summary;
- recent actual execution/exposure;
- readiness/recovery data quality and time semantics;
- request constraints such as duration/equipment;
- DecisionManifest, policy, epoch, and source coverage identity.

Tools may drill into session history, exercise progression, movement/muscle exposure, health trends, body-weight trends, nutrition history, program details, and catalog candidates.

Tool reads are bound to immutable input revisions/Manifest knowledge boundaries. A live mutable query cannot leak accepted-but-unpublished data into a run merely because `decision_generation` has not changed.

## 6. Evidence architecture

Data moves through distinct semantic states:

```text
EvidenceRevision
  → CandidateAssertion
  → EventAssociationDecision
  → AdmissionDecision(scope)
  → CanonicalFactRevision
  → FactsetRevision
```

Key rules:

- planned sets never fill missing actual sets;
- user-reported facts retain USER_REPORTED provenance;
- multiple sources for one underlying event do not become multiple independent events;
- contradiction and supersession remain queryable;
- unresolved exposure is represented explicitly rather than coerced to zero;
- admissions are use-specific, not a global verified boolean;
- model confidence is diagnostic only.

## 7. Decision publication

`decision_generation` identifies the atomically published DecisionManifest, not every input/projection mutation.

A Manifest binds the exact factset/input frontier, Program, policy bundle, projections and their dependency bases, mapping/catalog revisions, source watermarks, captured `authorization_epoch`, validity, and content hash.

Projection completion does not bump generation. A projection may be reused when its dependency basis remains valid even if unrelated inputs changed.

## 8. Safety and revocation

There are two independent invalidation paths:

### User-level

`authorization_epoch` increments on user-specific execution-invalidating events such as STOP, protective hold, relevant restriction/admission withdrawal, or applicable policy change.

### Global artifact/release level

SafetyRegistry can revoke a policy/model/engine/artifact dependency globally. The execution-invalidating linearization point is successful commit of the T2-GLOBAL revoke transaction. `effective_at` is audit/business semantics; V1 does not use it for scheduled future revoke or retroactive rewriting of historical authorization.

Publish, issue, START, RESUME, and CONTINUE check applicable global revocation state.


### 8.1 Canonical registry/user lock coordination

The SafetyRegistry gate is part of the frozen ordering for authorization-relevant operations and must not be omitted from summaries:

```text
T3 / T6 / T7:
  SafetyRegistry SHARED gate + fresh committed registry read
    → user coordination row S01
      → user quota buckets (stable key order, if needed)
      → planning intent(s) (stable ID order, if needed)
      → call reservation(s) (stable ID order, if needed)
      → daily plan head
      → execution aggregate
      → exact receipt / remaining aggregate rows

T2-GLOBAL emergency artifact revoke:
  SafetyRegistry EXCLUSIVE gate
    → append revoke + advance registry revision
    → COMMIT
  # does not acquire user S01

User STOP / FORCE_REST / user-level protective control:
  user coordination path only
  # must not depend on SafetyRegistry availability
```

The shared gate is not a cached pre-check. It must serialize correctly with T2-GLOBAL so that a revoke committed before T3/T6/T7 authorization-relevant mutation is visible to that mutation.

## 9. Authorization architecture

Prescription content is immutable and separate from authorization.

```text
PrescriptionRevision P7
   ├─ Authorization A1 (expired/revoked)
   └─ Authorization A2 (new revalidation)
```

An issuance binds exact content hash, DecisionManifest, authorization epoch, policy bundle, validation/evidence basis, scope, validity, and issuance reason.

Validity is a closure over all critical dependencies:

```text
A.valid_until = min(
  requested end,
  Manifest validity,
  evidence-resolution validity,
  projection/admission freshness,
  artifact validity,
  policy max TTL,
  session/calendar boundary
)
```

Missing required validity is deny-by-default.

## 10. Planning workflow

Planning is a persistent finite workflow rather than an in-memory retry loop.

A root `PlanningIntent` owns request revisions, root budget, deadline, lease/fence state, and terminal result. Attempts are replaceable children; retries, repair, stale rebuilds, tool calls, Fitness/Nutrition reruns, and physical provider calls consume the same root budget.

A changed user constraint such as `70 min/full gym → 20 min/no equipment` increments request revision and invalidates old attempts without resetting root budget/deadline.

## 11. External call accounting

Every physical provider/model request requires a persisted reservation. The key crash boundary is `DISPATCH_INTENT`, written before network send.

```text
RESERVED
  ├─→ CANCELLED_BEFORE_DISPATCH   # terminal, refundable only before send permission
  └─→ DISPATCH_INTENT             # from this point the request may have been sent
        ├─→ DISPATCHED
        │     ├─→ SETTLED
        │     └─→ OUTCOME_UNKNOWN
        ├─→ SETTLED               # response may be recorded without a separate diagnostic DISPATCHED write
        └─→ OUTCOME_UNKNOWN
```

`CANCELLED_BEFORE_DISPATCH` and `DISPATCH_INTENT` are mutually exclusive winners from `RESERVED`. A cancelled reservation can never later receive dispatch permission.

After `DISPATCH_INTENT`, uncertainty does not refund root budget. SDK implicit retries must be disabled or individually accounted as physical requests.

## 12. Execution model

START/RESUME binds both exact `prescription_revision_id` and `authorization_id`. START and revoke serialize at the user coordination boundary.

Actual workouts are factual history and can be recorded even if they occurred after authorization loss or outside KineticLoop. The system records lack of valid binding rather than discarding or fabricating authorization.

## 13. Replay architecture

Two explicit modes:

- **Historical Reconstruction:** reconstruct what the system knew/did using historical artifacts/policies.
- **Current Policy Backtest:** use the historical knowledge cutoff but run explicitly selected current logic.

Replay storage is isolated from live production state and cannot issue production authorization. Later corrections or personal mappings are excluded when they were not known by the replay cutoff.

## 14. Data and write-path authority

The logical schema contains 51 candidate relations. They are intentionally split into immutable history, mutable operational state, and build/job state. The frozen DB design defines one logical writer/command entrypoint for each mutation family.

The central user coordination row establishes a fixed lock ordering for conflicting commands. Long feature computation, resolver scans, provider calls, or model calls never happen while the coordination transaction is open.

## 15. Integration architecture

Provider adapters convert external identities/revisions into immutable evidence and never directly mutate progression/sequence. Hevy/manual/chat actuals converge through one canonical path. Wearable labels may contribute objective modality/time/heart-rate/distance/calorie data when permitted, but never invent strength-set details.

HealthKit requires an iOS/device bridge in later integration phases. Oura and nutrition-provider paths remain provider-specific adapters; transport format never defines canonical semantics.

## 16. Local-first architecture

Development begins with local PostgreSQL, FastAPI, worker, reaper, fixtures, minimal CLI/API, and remote OpenAI API only where needed. Provider adapters support FIXTURE/LIVE modes.

The first meaningful slice deliberately uses a fake deterministic proposal before real AI so the frozen evidence/manifest/authorization pipeline can be proven independently of model quality.


## 17. Shadow and test execution architecture

KineticLoop uses two isolated paths:

- **Test protocol path:** isolated test database/subject + TEST_ONLY policy executes complete T6/T7, including simulated authorization and START/revoke assertions. Production subject identities and production credential roles are rejected by this path.
- **Real-data shadow path:** real evidence/context may be processed, but outputs go to a noncanonical evaluation namespace. Shadow evaluation cannot write S38 live head, S42 production issuance, S45 production execution binding, or return an executable plan mode.

The evaluation namespace records exact model/prompt/tool/policy artifacts, input hashes, outputs, validation results and comparison metrics. It exists to evaluate coaching quality without weakening the frozen live transaction semantics.

## 18. Early security and release foundations

Security and release identity are not deferred to final staging. Before real Sheet import or remote model calls, the implementation must already have subject/test/admin role separation, secret/config separation, outbound-data/log-redaction tests, minimal artifact registration, and evaluation-input/output retention rules. M11 is a final integrated review, not the first security boundary.

## 19. Change control

Frozen semantics requiring protocol-version/ADR treatment include the 18 invariants, T1–T8 atomic boundaries, evidence/admission semantics, Manifest publication, Authorization/SafetyRegistry guards, planning budget/lease/fencing behavior, command authority, replay knowledge boundary, and failure terminal semantics.

Physical indexes, partitioning, ORM choices, field naming, caching, and explicitly configurable policy values can evolve without reopening the protocol if they do not weaken those semantics.


## Integration contract reference

Provider adapters implement `DOC-INTEGRATION-V0.1`. All provider paths terminate in immutable EvidenceRevision before any canonical projection. Hevy is the preferred structured strength-actual source; HealthKit is the iOS passive health/activity bridge; Oura remains a conditional recovery source with AI context exposure denied until its compliance gate is approved.

Cross-source reconciliation uses underlying-event identity rather than universal source overwrite priority. Adapter transport health and metric coverage are distinct concepts.
