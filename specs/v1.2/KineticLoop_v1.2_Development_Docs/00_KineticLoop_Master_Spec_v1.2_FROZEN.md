# KineticLoop — Master Product, Design & Technical Specification v1.2 FROZEN

**Purpose:** single AI/human-friendly development handoff  
**Protocol:** FROZEN  
**Logical DB schema:** FROZEN implementation baseline  
**Development:** NOT STARTED  
**Production auto-activation:** DISABLED

## Document authority

This file integrates the updated PRD, System Design, Technical Specification, frozen Protocol, DB logical design, and Project Plan. In a conflict, authority order is:

1. Frozen Protocol v1.2
2. Frozen DB Logical Baseline v0.2 for schema/write-path implementation
3. Technical Spec
4. System Design
5. PRD
6. Project Plan / backlog

The standalone files in this package are canonical for editing; this Master Spec is the convenient integrated reading artifact.

---

# Part I — Product Requirements

**Development:** NOT STARTED  
**Status:** Development baseline aligned to Protocol v1.2 FROZEN  
**Product state:** Development not yet started  
**Production auto-activation:** Disabled  
**Default environment:** `LOCAL_SHADOW / deny-by-default`

> Authority note: this PRD defines product intent and behavior. If any wording conflicts with `05_KineticLoop_Protocol_v1.2_FROZEN.md`, the frozen protocol governs evidence, authorization, transaction, failure, and replay semantics.

## 1. Product vision

KineticLoop is a persistent personal health, fat-loss, recovery, nutrition, and training decision system. It is not primarily a chatbot, static workout generator, wearable dashboard, or rule engine.

The product maintains a trustworthy canonical model of the user's state, gives AI coaches enough context and bounded read-only tools to make useful contextual judgments, validates those judgments against evidence and authorization policy, records what actually happened, and uses the resulting history for later decisions and evaluation.

Core product loop:

```text
Observe / report
  → preserve evidence
  → admit qualified facts for specific uses
  → publish a coherent DecisionManifest
  → AI coach reasons and may query bounded context tools
  → structured proposal
  → evidence obligations + policy/constraint validation
  → authorization issuance when allowed
  → execution
  → actual ingestion / correction / reconciliation
  → projections / replay / future planning
```

## 2. Product objective hierarchy

The confirmed product strategy is:

```text
GOAL_STRATEGY = FAT_LOSS_PRIORITY
```

Priority order:

1. Explicit safety/health controls and authorization restrictions.
2. Active Program hard constraints and frozen protocol rules.
3. Sustainable fat-loss objective.
4. Strength, muscle-retention, performance, and recovery optimization.
5. Convenience and user preference.

`FAT_LOSS_PRIORITY` does not mean blindly lowering calories. Calorie corridors, strength-preservation floors, acceptable rates of change, cumulative exposure limits, and durable adjustment authority belong to versioned Program/Policy configuration.

## 3. Product principles

### 3.1 Canonical state lives outside chat

Decision-critical truth must not depend on which conversation happens to remember something. Canonical storage owns program versions, evidence and admissions, actual sessions, exercise mappings, health/nutrition observations, projections, manifests, planning state, prescriptions, authorizations, execution bindings, overrides, approvals, and audit events.

### 3.2 AI judgment is first-class; rules do not impersonate coaching

KineticLoop deliberately avoids encoding general coaching intelligence as a forest of `if/else` rules.

**Code owns:** evidence identity, admissibility, provenance, consistency, permissions, hard limits, authorization, concurrency, idempotency, revisioning, and auditability.  
**AI owns:** modality judgment, sequence re-entry, exercise selection, fatigue interpretation, progression proposals, substitutions, training/nutrition trade-offs, and explanations—inside authorized boundaries.

### 3.3 Evidence is not automatically fact; fact is not automatically authority

Raw provider data, user statements, extracted assertions, admitted facts, projections, proposals, prescriptions, authorization, and actual execution are separate state axes. A structured model output does not become truth or execution authority merely because it is valid JSON.

### 3.4 Progressive context disclosure

Agents receive mandatory decision context plus bounded read-only tools. They do not receive arbitrary SQL access or an indiscriminate dump of the full database. Ordinary days should need little extra retrieval; ambiguous days may trigger deeper evidence/history queries.

### 3.5 Product flexibility must not weaken state semantics

AI may be flexible in *what plan is sensible*. IDs, evidence use, authorization, stale-vs-current semantics, versioning, transaction boundaries, and failure behavior remain deterministic.

## 4. Training behavior

### 4.1 Weekly schedule is a prior, not a lock

Baseline anchors remain:

| Day | Baseline intent |
|---|---|
| Monday | Strength A |
| Tuesday | protected rest/family |
| Wednesday | optional easy walk / Zone 2 |
| Thursday | Strength B |
| Friday | main Zone 2 |
| Saturday | Strength C |
| Sunday | Zone 2 / recovery |

The current day never mechanically overrides actual training history, recovery, restrictions, user constraints, or a long training gap.

### 4.2 A/B/C are structural blueprints

**A:** squat/lower primary; horizontal push; horizontal pull; hinge; vertical pull; anti-rotation core.  
**B:** posterior-chain/deadlift primary; incline/upper push; vertical pull; unilateral lower; rear-delt/scapular support; loaded carry.  
**C:** moderate squat/leg-press; horizontal push; supported horizontal pull; knee flexion; lateral delt; arms; anti-extension core; lower systemic-fatigue/hypertrophy emphasis.

AI may select exact exercises while preserving blueprint purpose, progression continuity, equipment/movement balance, explicit restrictions, and active Program policy.

### 4.3 Sequence is a continuity prior

The system records the last resolved strength blueprint and a nominal next blueprint. Only an admitted completed/resolved A/B/C session can advance nominal sequence. Cardio, recovery, rest, walking, and wearable workout labels do not.

After a long gap, nominal sequence confidence may be low. Fitness Coach may select `CONTINUE`, `RESET`, `REENTRY`, or another valid blueprint based on history and current context. The model does not invent unsupported blueprints.

### 4.4 Fatigue interpretation stays intelligent

Features such as lower-body hard sets, last lower session, soreness, recovery, and Zone 2 gap are deterministic inputs—not deterministic verdicts like “72h after legs means bike.” The Fitness Coach interprets those facts within safety/authorization policy.

## 5. Nutrition behavior

Nutrition Coach may set short-horizon calorie/macronutrient allocation, fueling, and timing inside the active Program envelope. It cannot silently alter durable calorie baseline, training structure, or Program version.

Cross-domain coordination uses `PrescriptionDemandFeatures`—which explicitly distinguish prescribed quantity, target, and estimate—plus evidence and policy envelopes. A model's qualitative self-rating such as “moderate systemic demand” cannot by itself become a safety boundary.

## 6. Evidence and protection behavior

The product preserves raw evidence even when parsing or admission is unresolved. Admission is action-scoped, including at minimum exposure accounting, progression authorization, protective hold, restriction establishment/clearance, sequence advancement, nutrition adjustment, and durable change.

Important asymmetry:

> Evidence insufficient to expand permission may still be sufficient to trigger a reversible protective hold.

Unknown or unresolved exposure is not converted to zero. The system can represent a confirmed lower bound, possible additional exposure, and unknown upper bound.

## 7. Daily plan and authorization

A `DailyPlanBundle` is the canonical daily planning aggregate. V1 policy allows at most one planned training session per bundle, while the model deliberately supports future multi-session days.

Prescription content and execution authorization are distinct. A prescription can exist without a valid current authorization. Authorization is immutable issuance bound to exact prescription content, DecisionManifest, policy, authorization epoch, evidence/validation basis, scope, and validity window.

Safety/control events may revoke execution authority immediately without waiting for AI re-planning. System-wide artifact revocation also participates in publish/issue/start/continue guards.

## 8. User controls

V1 must support explicit commands such as STOP, FORCE_REST, cancellation, and approved durable changes through authenticated command paths. Ordinary free text, quoted text, uploaded files, provider notes, or model summaries do not automatically acquire command authority.

Durable approval binds a specific proposal revision/content hash and relevant basis. If the proposal changes, old approval does not silently apply.

## 9. V1 scope

Included:

- canonical Program and exercise catalog;
- immutable evidence and action-scoped admission;
- unified workout ingestion and correction;
- actual training/cardio facts and exposure projections;
- health/recovery/nutrition facts with freshness semantics;
- DecisionManifest publication;
- progressive read-only context tools;
- Fitness Coach and Nutrition Coach in application-owned orchestration;
- bounded planning workflow with root budget, lease, fencing, and dispatch ledger;
- evidence obligation validation and authorization issuance;
- user overrides, controls, durable proposals/approvals;
- event/outbox/audit model;
- historical reconstruction and current-policy backtest;
- local end-to-end runtime and shadow mode;
- migration from the existing Google Sheet/POC.

Deferred or disabled until later gates:

- production auto-activation before frozen acceptance tests pass;
- fully autonomous durable Program changes;
- generalized medical diagnosis/treatment;
- arbitrary Agent SQL access;
- production multi-session/day behavior;
- offline START;
- managed OpenAI Agents API as core runtime;
- microservice decomposition;
- cloud-first development.

## 10. Nonfunctional requirements

The system must be auditable, replay-aware, idempotent, failure-bounded, and fail closed for missing safety-critical configuration. Long LLM/network work never runs while holding user coordination transactions. User STOP/revoke capacity must remain independent from normal inference queue saturation.

Privacy retention/deletion may make some historical replay impossible; when artifacts are unavailable, the system reports that limitation instead of fabricating reconstruction.

## 11. Success criteria

V1 product success is not “the model generated a workout.” It is the ability to demonstrate locally and then in staging that:

- evidence can be ingested and corrected without inventing actuals;
- a coherent manifest is published;
- AI can reason with mandatory context and bounded tools;
- unsafe/stale/under-evidenced actions are not authorized;
- valid shadow plans are reproducible and explainable;
- revocation beats stale plans;
- actual execution remains recordable even without authorization;
- replay respects point-in-time knowledge boundaries;
- the 34 frozen production acceptance specifications ultimately pass at their required PU/DC/WF/E2E layers.

## 12. Product output contract

User-facing daily training output should include the selected modality/blueprint, objective, duration, overall effort target, cardio decision, warm-up, exercise groups/roles, recent-performance context, progression/hold/substitution rationale, work sets/rests/RPE, branches, relevant constraints, and a concise final copy-ready reporting block.

Rendering is downstream of canonical prescription/authorization state; a streaming Agent draft is never displayed as executable merely because it looks complete.

---

# Part II — System Design

**Development:** NOT STARTED  
**Status:** Architecture implementation baseline  
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
  → CANCELLED_BEFORE_DISPATCH
  → DISPATCH_INTENT
       → DISPATCHED
       → SETTLED
       → OUTCOME_UNKNOWN
```

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

## 17. Change control

Frozen semantics requiring protocol-version/ADR treatment include the 18 invariants, T1–T8 atomic boundaries, evidence/admission semantics, Manifest publication, Authorization/SafetyRegistry guards, planning budget/lease/fencing behavior, command authority, replay knowledge boundary, and failure terminal semantics.

Physical indexes, partitioning, ORM choices, field naming, caching, and explicitly configurable policy values can evolve without reopening the protocol if they do not weaken those semantics.

---

# Part III — Technical Specification

**Status:** Pre-implementation technical baseline  
**Implementation:** NOT STARTED  
**DDL:** NOT YET GENERATED  
**Auto-activation:** DISABLED

## 1. Locked implementation direction

### Backend

```text
Python 3.12+
FastAPI
Pydantic v2
SQLAlchemy 2
Alembic
psycopg 3
PostgreSQL
pytest
ruff
pyright or mypy
uv
Docker / Docker Compose
OpenTelemetry
Sentry (production/staging candidate)
```

### AI

```text
OpenAI Responses API
+ typed function/tool calling
+ structured outputs
+ application-owned orchestration
```

OpenAI Agents API is not a V1 runtime dependency.

### Runtime topology

- API process
- planner/background worker
- independent reaper/watchdog
- PostgreSQL
- outbox dispatcher
- minimal CLI/web for local testing
- future iOS HealthKit bridge

## 2. Repository target

```text
kineticloop/
├── apps/
│   ├── api/
│   └── worker/
├── kineticloop/
│   ├── commands/
│   ├── evidence/
│   ├── program/
│   ├── training/
│   ├── exercise_catalog/
│   ├── health/
│   ├── nutrition/
│   ├── projections/
│   ├── publication/
│   ├── planning/
│   ├── context_tools/
│   ├── agents/
│   ├── validation/
│   ├── authorization/
│   ├── execution/
│   ├── replay/
│   ├── integrations/
│   ├── events/
│   └── db/
├── migrations/
├── tests/
│   ├── protocol_unit/
│   ├── db_concurrency/
│   ├── worker_faults/
│   └── e2e/
├── evals/
├── fixtures/
└── docs/
```

## 3. Typed contract policy

All external/API/Agent/tool/domain boundaries use explicit Pydantic models. Avoid `dict[str, Any]` for decision-critical payloads. Typed payloads include schema/version identity, subject binding, exact basis IDs/hashes, and explicit missing/unknown semantics.

Generated OpenAPI may be used to produce TypeScript/Swift clients later.

## 4. Command API shape

Commands are explicit application operations, not direct table mutation. Representative write commands:

- `ReceiveEvidence`
- `RecordCandidate`
- `DecideAssociation`
- `DecideAdmission`
- `AcceptFactRevision`
- `ApplyControl` / `ClearControl`
- `ApproveChange` / `ActivateApprovedProgram`
- `PublishManifest`
- `AdmitOrReviseIntent`
- `AcquireLease` / `RenewLease`
- `ReserveCall` / `PermitDispatch`
- `CommitBundle` / `Reauthorize`
- `StartSession` / `ResumeSession`
- `RecordActualExecution`
- `SettleCall` / `MarkUnknown` / `ReapIntent`
- `RunReplay`

Each command carries authenticated subject/actor identity at the service boundary plus an idempotency key. Same key + same request hash replays the original result; same key + different payload is rejected.

## 5. Core IDs and versions

Decision-critical aggregates use stable IDs plus immutable revisions. The system distinguishes:

- source evidence revision;
- assertion/admission revision;
- underlying event identity;
- fact revision and factset revision;
- projection version/basis;
- DecisionManifest/generation;
- PlanningIntent/request revision/attempt/fence;
- proposal revision/hash;
- prescription revision/content hash;
- authorization issuance;
- execution binding;
- policy/release artifact versions.

## 6. Transactions T1–T8

| Tx | Purpose |
|---|---|
| T1 | Receive raw evidence and idempotent receive event |
| T2 | Admit/correct canonical inputs or apply user-level controls/epoch invalidation |
| T3 | Atomically publish DecisionManifest and increment generation |
| T4 | Admit/revise PlanningIntent and quotas |
| T5 | Lease/fencing and physical-call budget/dispatch transitions |
| T6 | Commit validated bundle/prescriptions + authorization issuance + intent success |
| T7 | START/RESUME exact prescription+authorization execution binding |
| T8 | Settle/reap unknown calls and stale/dead worker state |

A separate T2-GLOBAL safety-registry revoke transaction linearizes global artifact revocation.

## 7. User coordination and lock order

Conflicting writes for one user serialize via a user coordination record. Frozen logical lock order:

```text
user coordination state
  → user quota buckets (stable key order)
  → planning intents (stable ID order)
  → call reservations (stable ID order)
  → daily plan head
  → execution aggregate
  → exact receipt / remaining rows
```

Queue/outbox scanning cannot hold its own row lock and then reverse-acquire the user coordination lock.

## 8. Factset implementation contract

Factsets use BUILDING → READY → SEALED semantics.

- BUILDING/READY are non-canonical build artifacts.
- Candidate members/digest can be prepared outside the short coordination transaction.
- T2-SEAL revalidates captured input frontier, seals the exact prepared content, and atomically moves `current_factset_id`.
- Only SEALED factsets are canonical immutable history.
- FULL checkpoint + bounded DELTA chains are permitted physical storage strategies.

## 9. DecisionManifest contract

A Manifest includes exact bindings for factset/input frontier, active Program, policy bundle, projection IDs+bases, mapping/catalog revisions, captured authorization epoch, source watermarks, local date/timezone policy, validity, and content hash.

Publication is atomic. A READY build with stale input frontier/epoch/program/policy cannot be relabeled and published.

## 10. Context/tool contract

A planning attempt records a DecisionSnapshot containing mandatory context and Manifest identity. Context tools are named domain operations such as:

```text
get_recent_sessions
get_session_detail
get_exercise_history
get_movement_exposure
get_muscle_volume
get_readiness_history
get_health_metric_trend
get_body_weight_trend
get_nutrition_trend
get_active_program
get_blueprint
search_exercise_catalog
get_active_controls
```

Every result records tool/version, arguments hash, query scope/window, exact input revision refs, result hash/blob, coverage/truncation, trust class, and timing. Tool data not bound to the intended knowledge frontier cannot be adopted into the attempt.

## 11. Fitness proposal contract

Fitness Coach can propose modality, blueprint/re-entry decision, session duration, exercise selection/order, sets/reps/load/RPE targets, optional branches, and reason codes. Proposal content is immutable once recorded; repair produces a new revision.

The proposal does not assert that planned quantities actually occurred and does not issue approval/authorization.

## 12. PrescriptionDemandFeatures

A deterministic service computes features from the exact Fitness proposal and versions each field semantically as `PRESCRIBED_QUANTITY`, `TARGET`, or `ESTIMATE`. Examples include working sets, lower-body prescribed sets, target RPE distribution, estimated duration, movement exposure, and estimated demand ranges.

Nutrition proposals bind the Fitness proposal hash, demand-feature hash, DecisionManifest, and policy. Any authorization-relevant Fitness change invalidates the dependent demand/nutrition result.

## 13. Evidence obligation and validation

The Agent may include citations for explanation, but the authoritative Evidence Resolver determines the complete policy-defined relevant evidence set. Its output separates support, contradiction, supersession/retraction, event association, coverage, consistency, source watermarks, truncation, and basis hash.

Validation is a certificate bound to exact request revision, manifest/epoch, proposal hashes, demand hash, evidence resolutions, policy, and cumulative execution basis. PASS is not itself an authorization token; T6 rechecks all mutable guards.

## 14. Authorization evaluator

`is_executable()` evaluates current execution permission from exact prescription+authorization, subject/scope, current time, authorization epoch, user controls, global SafetyRegistry, content hash, validity closure, and execution state.

Never implement eligibility as `WHERE status='VALID'` alone.

## 15. Planning intent state machine

Intent terminal outcomes include:

```text
FOUND_VALID_PLAN
PROVEN_CONSTRAINT_CONFLICT
SEARCH_BUDGET_EXHAUSTED
MODEL_REFUSAL
MODEL_OUTPUT_INVALID
DEPENDENCY_UNAVAILABLE
STALE_RETRY_EXHAUSTED
DEADLINE_EXCEEDED
CANCELLED
```

Search failure is not proof of infeasibility. `PROVEN_CONSTRAINT_CONFLICT` requires deterministic/formal evidence for the represented constraint problem.

Attempts move through context → Fitness → demand features → Nutrition → validation → commit-ready → committed, with stale/failed/cancelled/lease-lost exits. Retry creates a new attempt under the same root budget.

## 16. Call ledger

Before any physical model/provider call:

1. Reserve slot/resource upper bound in a short transaction.
2. Revalidate lease/fence/request/deadline and persist `DISPATCH_INTENT`.
3. Perform exactly one network request outside the transaction.
4. Settle actual usage or retain `OUTCOME_UNKNOWN`.

After `DISPATCH_INTENT`, a crash does not refund root budget. Late responses may settle ledger evidence but cannot recover lost commit authority.

## 17. Idempotency

Dangerous operations have both command receipts and durable natural identities where possible (Manifest build, bundle commit, authorization issuance, source revision, START binding, reservation operation slot). Receipt retention cleanup must not reopen dangerous replay paths.

Commit-ACK loss is resolved by querying the existing committed identity, not by blindly issuing a second authorization.

## 18. SafetyRegistry

Global safety artifacts/revocations are separately namespaced from user data. T2-GLOBAL revoke commit immediately invalidates applicable dependency chains for new publish/issue/start/continue checks. Backdated `effective_at` never retroactively rewrites what authorization existed historically; V1 does not implement scheduled future revoke.

## 19. Replay

Replay tools and caches bind mode, knowledge cutoff, release bundle, and subject. Historical reconstruction uses historically known evidence/policies/artifacts where available; current-policy backtest uses the old knowledge cutoff with explicitly selected current logic. Replay cannot write live authorization or production commands.

## 20. API response modes for plan retrieval

A plan surface must distinguish at least:

```text
AI_GENERATED_CURRENT
REUSED_VALID_PLAN
PREAUTHORIZED_FALLBACK
UNAVAILABLE
```

It should expose last decision time, missing-data indicators, and execution scope. System failure must not be phrased as a personalized coaching judgment.

## 21. Default V1 configuration

`v1-local-shadow-deny-by-default`:

- production authorization disabled;
- evidence can be stored without automatically qualifying progression/sequence/nutrition;
- missing obligation/envelope policy denies permission expansion;
- durable auto-approval disabled;
- fallback catalog empty;
- offline START disabled;
- STOP/risk path enabled as a distinct control path;
- explicit test-only policies may simulate T6/T7 in isolated tests.

## 22. Test layers

- **PU:** protocol unit/state-machine tests.
- **DC:** real PostgreSQL multi-transaction concurrency.
- **WF:** worker/process fault injection.
- **E2E:** API → workflow → DB → eligibility/rendering.

The frozen protocol defines 34 production acceptance specs. The offline bounded model has passed its encoded cases, but this does not count as the real PU/DC/WF/E2E evidence required before auto-activation.

## 23. First implementation vertical slice

Before real AI:

```text
seed evidence
→ candidate/admission/canonical facts
→ build+seal factset
→ projections
→ publish DecisionManifest
→ create PlanningIntent
→ deterministic fake Fitness/Nutrition proposals
→ evidence resolution + validation
→ commit SHADOW DailyPlanBundle
→ render
→ apply correction/revoke
→ verify stale authority cannot be reused
→ replay audit
```

Only after this passes should the fake proposal be replaced with a real Fitness Coach call through the Responses API.

## 24. Deployment progression

```text
Local protocol implementation
→ local shadow vertical slice
→ real PostgreSQL concurrency/fault tests
→ Fitness Coach shadow
→ Nutrition Coach shadow
→ live provider adapters in shadow
→ staging/observability/release evaluation
→ auto-activation readiness review
```

Cloud vendor-specific deployment is deliberately downstream of local correctness.

---

# Part IV — Acceptance & Release Gates

## 1. Current evidence status

Protocol v1.2 is frozen for implementation, not validated for production auto-activation.

The bounded offline protocol model passed its encoded suite: 34/34 original acceptance model cases, 18/18 additional boundary cases, 9/9 critical interleaving scenarios, 589 complete schedules, 2,997 visited prefixes, 0 model-level deadlock/invariant violations, and 8/8 seeded negative mutants detected.

This does **not** substitute for real PostgreSQL concurrency tests, process crash/fault injection, API/E2E tests, provider integrations, or live LLM evaluation. Production auto-activation remains disabled.

## 2. Production acceptance categories

### Evidence

Must prove, among other cases, that planned sets never fabricate actuals; unresolved risk cannot disappear; duplicate sources do not multiply underlying events; ambiguous event association remains ambiguous; unknown exposure is not zero; contradiction cannot be cherry-picked; corrections withdraw action basis; and summaries cannot acquire command authority.

### Decision publication

Must prove projection completion does not bump generation; projection reuse is dependency-based; unpublished inputs cannot leak through tools; absence dependencies are tracked; and urgent revoke wins against stale Manifest publication.

### Authorization

Must prove revoke precedes replan; stale Manifest cannot reauthorize after epoch change; START/revoke linearizes; expiry needs no background job; reauthorization does not rewrite history; fallback is not privileged; STOP works under queue saturation; and unauthorized actuals are still recorded truthfully.

### Workflow

Must prove crashes do not refund possibly dispatched external budget; cancel/dispatch permit is atomic; every physical SDK retry is accounted; single-flight does not swallow new constraints; old workers cannot commit after fence takeover; late results cannot reopen terminal intents; Fitness changes invalidate dependent Nutrition; commit ACK loss is idempotent; and search failure is not misreported as proven infeasibility.

### Replay

Must prove future corrections and future personal mappings are excluded by historical cutoff, replay modes stay distinct, and replay cannot mutate live production state.

## 3. Auto-activation gate

Production auto-activation is allowed only after:

1. Frozen protocol is implemented without semantic weakening.
2. All relevant 34 acceptance tests pass at specified PU/DC/WF/E2E layers.
3. A complete production policy bundle is published for the actions being auto-authorized.
4. Authorization audit and degraded-mode UX are validated.
5. Safety/control channel has independent capacity and tested failure behavior.
6. Release evaluation binds exact model/prompt/engine/policy artifacts.
7. Observability and rollback are operational.

## 4. Durable-change gate

Automatic durable Program changes have a higher gate than daily prescription generation. Before enabling them, intervention/execution/adherence/outcome semantics, result windows, evaluation metrics, monitoring, rollback, and change-class policy must be implemented and validated.

## 5. Default safe configuration

The frozen development baseline remains `LOCAL_SHADOW / deny-by-default`: no production issuance, no durable auto-approval, empty fallback catalog, offline START disabled, and unconfigured evidence/envelope requirements deny permission expansion.

---

# Part V — Architecture Decisions

## 1. Locked decisions

- **ADR-001:** PostgreSQL is production canonical state.
- **ADR-002:** Google Sheet is migration/regression input and optional reporting view, not production SSOT.
- **ADR-003:** Backend is Python-first.
- **ADR-004:** FastAPI + Pydantic v2 typed contracts are the V1 application baseline.
- **ADR-005:** OpenAI Agents API is not a core V1 dependency.
- **ADR-006:** AI orchestration is application-owned around Responses API/tools/structured outputs.
- **ADR-007:** LLMs propose and reason; they do not directly mutate canonical state or issue authority.
- **ADR-008:** Agents may query bounded read-only context tools; arbitrary SQL is prohibited.
- **ADR-009:** Coaching judgment remains AI-driven where it is contextual; deterministic code owns evidence, constraints, authorization, and state transitions.
- **ADR-010:** Nominal A/B/C sequence is a prior; long gaps may trigger AI re-entry reasoning.
- **ADR-011:** Only admitted completed/resolved A/B/C actuals advance sequence.
- **ADR-012:** Hevy/manual/chat actual evidence converges through one canonical ingestion path; wearable labels cannot invent strength details.
- **ADR-013:** `FAT_LOSS_PRIORITY` is the primary performance objective below safety and approved hard constraints.
- **ADR-014:** Durable Program changes require explicit approval or explicit change-class auto-approval policy; pending proposals are invisible to daily planning.
- **ADR-015:** Daily plan/prescription/authorization history is revisioned and append-oriented; old history is not overwritten.
- **ADR-016:** V1 policy allows one planned training session/day, while the bundle/schema support future multi-session behavior.
- **ADR-017:** Decision publication, planning, authorization, and replay follow frozen Protocol v1.2.
- **ADR-018:** Authorization and prescription content are distinct objects; reauthorization creates a new issuance.
- **ADR-019:** User-level `authorization_epoch` and global SafetyRegistry are independent revocation barriers.
- **ADR-020:** Planning is a persistent bounded workflow with root budgets, reservation ledger, leases, fencing, and independent reaper.
- **ADR-021:** Factsets become canonical only when SEALED.
- **ADR-022:** Replay distinguishes Historical Reconstruction from Current Policy Backtest and enforces knowledge cutoffs.
- **ADR-023:** Product is local-first and shadow-first; production auto-activation is disabled until gates pass.
- **ADR-024:** Production architecture starts as modular monolith + worker/reaper, not microservices.

## 2. Frozen protocol surface

Changes to any of the following require a new protocol version or an explicit ADR with compatibility decision:

- INV-01–INV-18 semantics;
- T1–T8 transaction/atomicity boundaries and T2-GLOBAL global revoke semantics;
- Evidence Admission scopes and protective asymmetry;
- DecisionManifest publication/generation rules;
- Authorization/SafetyRegistry guards and validity closure;
- planning root budget, dispatch ledger, lease/fencing, request-revision semantics;
- command authority and durable approval binding;
- replay knowledge boundaries;
- terminal failure semantics.

## 3. Non-protocol implementation freedom

The following may evolve without reopening protocol semantics when behavior is preserved:

- SQL syntax and physical normalization choices;
- table/index names and ordering;
- partitioning/archival/caching;
- ORM/repository implementation;
- nonsemantic error wording;
- explicitly configurable policy thresholds/TTL values;
- cloud vendor and deployment packaging.

## 4. Historical design changes now incorporated

- rule-engine-first → Constraint/Evidence/Authorization kernel + real AI coaching judgment;
- fixed prompt context → mandatory context + progressive tool retrieval;
- deterministic modality resolver → AI modality decision inside hard eligibility/authorization;
- hard next-blueprint pointer → nominal continuity prior + AI re-entry reasoning;
- one prescription/day schema lock → one active daily bundle, V1 one training slot, future multiple slots;
- TypeScript-first backend → Python-first backend;
- managed Agents runtime → application-owned Responses API orchestration;
- cloud-first → local-first vertical slice;
- state-version-only CAS → DecisionManifest generation + authorization epoch + input revision bindings;
- model citations as evidence → authoritative action-scoped Evidence Resolver;
- retry counters → persistent PlanningIntent + root reservation ledger;
- mutable authorization status → immutable authorization issuance + revocation events;
- user-only revoke → user epoch + global artifact SafetyRegistry.

---

# Part VI — Frozen Protocol Specification (verbatim canonical appendix)

# KineticLoop v1.2 — FROZEN Protocol Specification

状态：**FROZEN — Protocol v1.2**  
范围：五个协议的状态机、事务边界、故障语义与自动激活验收。  
依据：v1.1 Review Package，以及本轮已接受的架构修正。  
交付边界：本文件冻结协议语义，不含 PostgreSQL DDL。配套模型报告只验证有限状态反例，不代表生产实现、数据库并发或自动激活验收。

本冻结版吸收 r2 对 Factset build/seal、全局制品撤销和授权有效期闭包的修正，并完成最终 freeze review。自本文件起，Evidence / Decision Publication / Authorization / Planning Workflow / Replay 的权限语义、状态迁移和 T1–T8 原子边界属于冻结契约；后续实现不得静默改变。

## 0. 规范约定与冻结条件

本文 MUST / MUST NOT 表示不可违反的协议要求；SHOULD 表示可以经 ADR 说明理由后替换的建议。所有 ID、版本、时间与授权身份由服务端绑定，模型回显值不产生权限。

协议保证的是证据使用、状态一致性、行动准入和故障有界；不把符合策略等同于医学安全，不把可重复计算等同于经验事实。

AI 继续负责 modality、sequence re-entry、exercise selection、fatigue interpretation、progression proposal、substitution 与 daily nutrition reasoning。代码负责证据资格、证据义务、策略限制、执行授权与状态迁移。

### 0.1 版本变化纪律

- 修改本协议语义需要新 protocol version 与兼容性决定。
- Admission、mapping、projection engine、constraint、authorization、fallback、prompt 等执行版本 MUST 可定位到不可变制品或其内容摘要。
- “不可变”表示禁止原地重写审计历史，不表示无限期保存健康数据。保留、删除和脱敏按明确政策执行；删除导致历史不可复现时 MUST 显示证据缺失，不得编造重建结果。
- 本文的主体边界都包含 user/tenant scope；同一 hash、exercise ID 或日期不得绕过主体隔离。

### 0.2 状态轴必须分开

| 对象 | 负责表达 | 不负责表达 |
|---|---|---|
| Evidence / Assertion | 来源陈述与候选解释 | 自动执行权限 |
| AdmissionDecision | 某证据在特定用途下的资格 | 普遍真实性或医学诊断 |
| DecisionManifest | 原子发布的决策视图 | 当前仍可执行 |
| PlanningIntent / Attempt | 搜索目标、预算与运行进度 | 已批准行动 |
| PrescriptionRevision | 不可变建议内容 | 授权是否有效 |
| AuthorizationIssuance | 一次有条件、有限期的授权 | 永久有效资格 |
| Execution | 实际开始、继续、停止与完成 | 计划必然已执行 |

### 0.3 两个协调计数器

`decision_generation` 只在 DecisionManifest 原子发布时递增。

`authorization_epoch` 是用户级、单调递增的执行失效屏障。它在保护性暂停、停止命令、相关证据撤回、限制变化、授权政策切换等被定义为失效事件的事务中递增。它不依赖 Manifest 发布，不用于触发 projection 的自我重算。

V1 使用粗粒度用户级 epoch：一次失效可能使多个授权需要重新签发。这是有意接受的可用性代价，避免在 V1 引入复杂的按动作失效图。

新输入 MUST 经版本化的 mutation classification 分成 `INVALIDATING` 或 `NON_INVALIDATING_PENDING_PUBLICATION`。无法分类而可能影响现有授权时采用前者。原始高频样本的单纯到达不默认递增两个计数器。

### 0.3a 制品撤销注册表

除两个用户计数器外，增加全局 SafetyRegistry。不可变 ArtifactRecord 包含 artifact identity/hash、类型、已注册的依赖 identity、有效期政策；新增 identity 不得覆盖旧 identity。依赖在注册时固定且已存在，使依赖图无环；发布者必须提交包含 policy、admission、mapping、projection、validator、prompt/model 与 release 的完整适用依赖闭包。不能由 Agent 选择忽略上游制品。

全局 `registry_revision` 只表示注册表撤销前沿，用于一致性与审计，**不是要求所有 A 必须相等的全局 epoch**。撤销无关 artifact 不使 A 失效；任一被绑定的传递依赖被撤销则失权。系统级停止可撤销被所有相关 release 绑定的 system safety artifact；新 release 必须绑定经批准的新 identity，不能解除旧撤销。

撤销事件追加后不可恢复原 identity。修复使用新制品、新 release、重新验证和新 issuance。历史 A 不改写；UI 当前状态由 evaluator 计算。注册表未知、缺少依赖或权威查询不可用时禁止 publish/issue/START/RESUME/CONTINUE。

Registry 不可用不阻止用户 STOP、收缩权限、接收实际执行事实或预算对账。

**全局撤销的执行线性化点固定为 T2-GLOBAL 撤销事务成功提交。** `recorded_at`（或物理实现中的等价 commit timestamp）表示系统从何时开始拒绝依赖该 artifact 的 publish / issue / START / RESUME / CONTINUE。`effective_at` 仅用于事故、业务或审计语义，不得通过回填过去时间来追溯改写“当时系统实际上是否已授权”。V1 不用 `effective_at` 表达计划中的未来撤销；若未来支持 scheduled revocation，必须引入独立、显式的状态与准入语义，不能复用 emergency revoke。

### 0.4 与 v1.1 的关系

本文件替代 v1.1 中与证据准入、generation、授权、规划重试和 replay 冲突的语义，其余业务约束继续适用：每用户一个 active Program；每用户/local date 一个 active DailyPlanBundle revision；V1 每 bundle 最多一个计划训练 session；只有符合准入规则的实际已完成 A/B/C 训练推进序列；pending durable proposal 不参与日常规划。

上述唯一性与禁止条件必须在最终提交边界强制执行，不能只由前端或 Agent 遵守。Multiple-session 扩展另需定义跨 session 的执行暴露与营养耦合，不因数据结构允许多个 child 就自动获得产品授权。

## 1. 总体不变量

| ID | 不变量 |
|---|---|
| INV-01 | Prescription 中的计划值 MUST NOT 补全 actual execution。 |
| INV-02 | 模型自报 confidence、reasoning、citation 或 command text 不产生 admission/approval/authorization。 |
| INV-03 | 同一 underlying event 的多来源记录 MUST NOT 增加独立训练事件计数。 |
| INV-04 | 无法证明成功，不等于没有 physiological exposure。 |
| INV-05 | Evidence Resolver 的覆盖范围由动作政策定义，不能由 Agent 的引用列表缩窄。 |
| INV-06 | Projection 是否可复用由 dependency basis 决定，不由其 generation 数字是否最新决定。 |
| INV-07 | 只有 Manifest 的原子发布递增 decision_generation。 |
| INV-08 | 用户与全局制品紧急失效不等待模型、projection、Manifest、替代计划或逐用户 fanout。 |
| INV-09 | Authorization 的内容、epoch、scope、依赖有效期闭包、控制状态及传递制品未撤销资格必须共同有效。 |
| INV-10 | 失效的旧 Manifest / 旧 attempt / 被撤销制品不能重新产生执行权限。 |
| INV-11 | 所有 attempt、repair、stale restart 和实际外部请求共享根预算。 |
| INV-12 | 外部调用结果未知不恢复已占用预算；晚到结果不恢复失去的提交权。 |
| INV-13 | 新 request revision 使旧 attempt 失权，不重置根预算。 |
| INV-14 | 替换 Fitness 内容必然使依赖其内容的 Demand 与 Nutrition 失效。 |
| INV-15 | 模型摘要始终为非命令推断；转换或重复总结不能提升 trust / authority。 |
| INV-16 | Replay 不能读取 knowledge cutoff 之后才被系统知道的个体证据及人工修正。 |
| INV-17 | LLM 等待、外部网络调用、长时间特征计算 MUST NOT 发生在协调事务内。 |
| INV-18 | 授权只决定建议可否执行，不能阻止保存用户实际上已经发生的训练事实。 |

## 2. 共同事务与时间模型

### 2.1 用户协调边界

本规范要求一个用户级逻辑协调点，不指定最终表结构。下列操作必须通过同一短事务协调机制串行化相互冲突的读写：

- 输入修订发布与失效分类；
- ProtectiveHold / revoke / control command；
- Manifest 原子发布；
- intent request revision、lease/fence 更新；
- 处方提交与授权签发；
- START / RESUME execution。

实现可以采用统一协调记录的行锁与 CAS。仅在事务外先读取版本，再执行无保护写入，不满足协议。多个锁有固定全局顺序；数据库事务冲突允许有界重试，但必须重新读取 guard，不能重放旧许可。

所有对外可见的状态变化与 outbox 事件在同一事务提交。outbox 可重复投递，消费者 MUST 幂等；数据库内的失效屏障立即生效，不依赖 outbox 已送达。

### 2.1a 全局撤销与准入的协调

V1 采用逻辑共享/排他 registry gate。publish、issue、START、RESUME 和具有执行许可含义的 CONTINUE，在同一权威事务内先取得共享 gate，再按用户锁序取得 S01，重读已提交 registry、当前 epoch 与时间，判断并写结果。全局 revoke 取得排他 gate，追加撤销、推进 registry_revision、写幂等回执/审计并提交；不取任何用户锁、不扫描用户 A。

固定顺序为 registry gate → user → quota → intent → reservation → plan head → execution → receipt。不需要 registry 的用户 STOP / 输入更新 / 预算命令直接从 user 开始，且不得之后反向申请 registry。共享持有期间不得运行模型、外部网络、完整依赖图重建或历史检索；闭包预计算，事务只核对固定身份与有界资格。

共享 gate 内的撤销读取 MUST 看见 gate 获得前已提交的撤销。拿锁前的事务快照不能当作新鲜读；实际隔离级别与语句顺序由后续 DC 验证。仅靠“读两次 registry_revision”仍可能在第二次读后、提交前插入 revoke，不满足要求。

允许等价的数据库原子串行化实现，但不能用异步缓存替代此语义。撤销成功 ACK 表示权威 T2-GLOBAL 提交完成；该提交即全局撤销的执行线性化点。此后服务端的新执行准入必须拒绝相关依赖。`effective_at` 不得使这一线性化点向过去或未来漂移。已经成功的 START 只保留过去发生的记录，CONTINUE 必须重新判断；无法远程停止已经发生的身体动作。V1 不允许离线扩大执行资格。

全局 gate 的持锁上界、写入优先与超时中止策略需压测验证。因 gate 超时无法判断时 fail closed；不得为可用性自动降级为缓存放行。

### 2.2 线性化语义

当 START 与 REVOKE 并发时，以成功提交到用户协调点的顺序为准：

- REVOKE 先提交：START MUST 失败。
- START 先提交：允许记录当时的开始；随后 REVOKE 使继续执行失权，保留开始历史。
- 服务端不能撤销已发生的物理动作；离线客户端不能获得“实时撤销已送达”的保证。

### 2.3 时间

授权和 deadline 使用服务端可信时间与 UTC instant；local_date 同时绑定 timezone / calendar policy。有效区间使用 `[valid_from, valid_until)`。自然过期不依赖后台作业更新 status。

跨午夜、时区变化和夏令时不得使同一授权被错误地用于另一个 session scope。客户端时间不是授权依据。

## 3. 协议一：Evidence Admission Protocol

### 3.1 核心对象

| 对象 | 必须保留的语义 |
|---|---|
| EvidenceRevision | 来源身份、来源修订、内容摘要、observed/effective time、系统 known time、记录时间、trust class、command authority |
| CandidateAssertion | 主体、谓词、值/单位、assertion type、否定、模态、不确定性、字段级 provenance、extractor version |
| EventAssociationDecision | 哪些 evidence 指向同一 underlying event、匹配依据、版本、歧义与撤回关系 |
| AdmissionDecision | assertion/evidence basis、action scope、结果、policy version、reason codes、supersedes、knowledge/effective interval |
| EvidenceResolution | 固定 Manifest 与动作下的支持、反证、重复、被替代项、覆盖情况及 provenance |

聊天文本必须保留原文 span；文件抽取应保留页码、坐标或稳定 span、原始抽取文本。用户报告保留 `USER_REPORTED` 性质，即使被接受用于特定动作也不升级为客观测量。

计划可作为理解语境，但不能作为实际完成量的补全来源。缺失字段保持缺失；零、未测量、不适用和解析失败必须有不同语义。

### 3.2 用途资格与不对称

V1 至少支持：

```text
DISPLAY
ACCOUNT_OBSERVED_EXPOSURE
AUTHORIZE_PROGRESSION
TRIGGER_PROTECTIVE_HOLD
ESTABLISH_RESTRICTION
CLEAR_RESTRICTION
ADVANCE_SEQUENCE
AUTHORIZE_NUTRITION_ADJUSTMENT
AUTHORIZE_DURABLE_CHANGE
```

结果为 `ELIGIBLE / NOT_ELIGIBLE / UNRESOLVED`。这是用途资格，不是全局 verified 布尔值。

资格政策 MUST 区分扩大权限与保护性收缩。存在不确定风险时可以触发临时 hold，而不形成已诊断 injury。建立、解除长期限制使用各自政策，不允许由“暂停期限到了”推导为健康事实已恢复。

`AUTHORIZE_DURABLE_CHANGE=ELIGIBLE` 只表示满足证据前提，不取代用户批准或已配置的变更类自动批准政策。

### 3.3 状态迁移

EvidenceRevision 和已写入 Assertion 内容不可原地更改。业务状态通过追加决策与 supersession 得到：

```text
EvidenceRevision
  → CandidateAssertion
  → AdmissionDecision(scope, ELIGIBLE | NOT_ELIGIBLE | UNRESOLVED)
  → newer AdmissionDecision supersedes previous decision
```

| 事件 | 允许行为 | 禁止行为 |
|---|---|---|
| 抽取含歧义 | 保存候选、定向确认、按范围限制使用 | 用模型 confidence 直接批准 progression |
| 新反证/更正 | 追加 evidence/admission 修订，失效相关使用资格 | 覆写原 admission 历史 |
| 人工解除限制 | 验证独立 command capability 与 clearance policy | 从普通聊天摘要、计划完成或未再上报推导解除 |
| 来源重复 | 关联同一事件、保留多来源证据 | 重复累加独立样本 |
| 事件匹配歧义 | 保留 ambiguous association，按政策限制计数 | 按相近时间武断合并，或默认当作多个独立成功 |

多来源不自动等于独立佐证：provider 可能转发同一上游测量。源血缘可识别时 MUST 保留；未知时不假设独立。

### 3.4 Exposure 区间

Exposure 至少包含已确认下界、可能上界、单位、统计口径、窗口、resolution status 和 basis。

上界没有依据时 MUST 为 unknown/unbounded，而不是从原处方中复制一个有限值。跨来源有重复不确定性时，禁止机械相加各个上界或下界而不说明事件关联假设。

Policy 决定未知上界下允许哪些行动。不得把 missing、unresolved 或不能计入 progression 的暴露当成零。

### 3.5 Authoritative Evidence Resolver

输入：主体、动作类型、动作参数、exercise/movement identity、Manifest ID、obligation policy version。

输出 MUST 分开：

```text
supporting_events
contradicting_events
superseded_or_retracted_items
event_association_status
coverage: COMPLETE_FOR_POLICY | PARTIAL | UNKNOWN
consistency: CONSISTENT | CONFLICTED | UNRESOLVED
query_scope_and_window
source_watermarks
truncation_status
basis_hash
```

“完整”只表示满足已定义来源和时间窗口的政策覆盖，不宣称掌握现实世界的一切事实。Conflict 与 coverage 是两个维度，不能用一个枚举混合。

Agent citations 用于解释，并可被检查是否真实支持陈述；它们 MUST NOT 缩小 resolver 查询范围。结果截断、关键来源缺失或 resolver 故障时，需证据义务的动作不得获得授权。

Resolver 必须读取固定 Manifest 的 admitted basis。它不自行读取 cutoff 之后的新事实；当前紧急风险由独立 hold / epoch 检查拦截。

### 3.6 Blueprint 与 correction

`BlueprintResolutionProposal` 是解释；`SequenceEligibilityDecision` 是用途资格。PROBABLE_A 可以与 sequence_eligible=false 共存。

序列是按有效训练发生顺序、已接受完成标准及版本化 tie-break 规则重建的投影。历史补录或更正不能按到达顺序追加一次 pointer advancement。部分训练仍可贡献已接受的 exposure。

更正必须：保存新版本 → 追加 admission/association 决策 → 标记依赖过期 → 对影响现有行动依据的更正推进 authorization_epoch → 重建投影 → 发布新 Manifest。

V1 可保守失效该用户所有尚未提交的 attempt。历史 Manifest 仍不可变，改变的是其可用于新行动的资格。

### 3.7 信任与命令

模型摘要固定为 `MODEL_DERIVED / NON_COMMAND`，并保留源证据引用。Provider free text、文件、用户引用和模型输出都不能构造 approval/clearance capability。

Durable approval V1 采用专用确认界面，服务端绑定 proposal ID、内容摘要、作用范围、基础 program/policy 和防重放身份。批准后的实际激活仍需重新检查当前政策、依赖和权限；批准不是无限期可执行通行证。

### 3.8 事务与失败

- 原始接收可独立提交，使证据不因解析失败丢失。
- 会影响现有授权的 admission 撤回/修改，其生效与 epoch 推进 MUST 同事务完成。
- 解析服务失效：保留原始证据与 unresolved；禁止伪造 canonical projection。
- 风险信号走保护路径，不得等待完整抽取成功。
- Provider 更正乱序、来源回滚或关联冲突：保留版本与冲突，不使用最后到达者自动覆盖一切。

## 4. 协议二：Decision Publication Protocol

### 4.1 三层定义

`InputRevision` 是可定位的不可变输入修订；`ProjectionBasis` 是该投影实际读取的修订集合及计算版本；`DecisionManifest` 是正式发布给 planner 的兼容输入集合。

每个 projection type MUST 声明 dependency signature，包含读取集合、窗口、缺失值语义、mapping/policy/engine 依赖，以及用于发现“新增行”的集合修订。仅列出已读行无法覆盖 absence dependency。

### 4.1a Factset 构建与封存

```text
BUILDING → READY → SEALED
```

BUILDING/READY 是 build artifact，未进入 canonical immutable history。只有 SEALED 的 factset 及其 members 可供 canonical readers 使用。BUILDING 可由唯一 builder 修改并增加 member_revision；CompleteFactset 关闭 builder 写入、计算并固定摘要/数量/完成凭据后进入 READY。READY 内容不可再编辑；修改需要新 build ID。SEALED 的成员、摘要和输入依据不可更新。

1. T2-IN 在短用户事务接受 admission/association/fact 修订、推进 input frontier；相关失效同时推进 epoch 和 execution basis。无需等待 factset 构建。
2. 捕获已提交 frontier、epoch、program/policy/mapping basis；事务外完成 FULL/DELTA 成员重建、压缩、完整性验证及摘要计算。canonical read 不读取这些候选。
3. CompleteFactset 在 builder 的写入屏障下原子置 READY；摘要必须对应同一已关闭的 member revision，不能一边写成员一边封存。
4. T2-SEAL 取得 user → build 锁，复核 captured frontier/epoch、完成凭据、member revision 和摘要身份，将 READY→SEALED 与 current_factset pointer/event/receipt 原子提交。此处不能重新扫描或重算全体 members。
5. 复核失败保持 head 不变；build 不获得 canonical 资格，可由清理命令转 STALE/ABANDONED。终止状态不是重新编辑 READY 的后门。

T2-IN 与 T2-SEAL 是两个不同原子命令，不宣称跨构建阶段原子。两者之间 current_factset 可以落后于 input frontier；此时不能用旧 factset 生成新授权视图。既有授权由即时 epoch/有效期守卫处理，不等待新 head。重复 SealFactset 返回原封存身份，不把已经落后的旧集合重新切为 current。

### 4.2 Manifest 内容

```text
manifest_id, user_scope, decision_generation
admitted_factset_revision / immutable revision references
program_revision, policy_bundle_id
projection_ids + their dependency bases
mapping / event-association revisions
captured_authorization_epoch
source coverage / watermarks
created_at, valid_until, local_date / timezone policy
artifact_roots, artifact_dependency_closure_hash, registry_revision_at_publish
content_hash
```

DecisionSnapshot 是一次 attempt 对 Manifest、mandatory context 与读取证据的绑定，不是第二个可修改的事实源。

### 4.3 发布状态机

```text
BUILDING → READY → PUBLISHED
    ├─ BUILD_FAILED
    └─ STALE
READY → STALE | REJECTED
```

失败或 stale 的 build 可以产生新 build，不能原地修改已 PUBLISHED 的 Manifest。Manifest 历史保留；“是否最新”和“是否可用于新授权”由当前协调状态与 guard 判定。

### 4.4 发布算法与事务边界

1. 短一致读取取得输入修订前沿、active program/policy、authorization_epoch。
2. 事务外构建/复用 projections，生成 dependency signatures 与 READY manifest。
3. 发布短事务先进入 registry 共享边界再进入用户协调边界，重新验证输入前沿、SEALED factset、依赖、active program/policy、epoch、有效期及传递制品撤销状态。
4. 任一需要的依据变化则判 STALE；不得只把旧内容贴上新 epoch。
5. 同事务递增 decision_generation、保存不可变 Manifest、更新 current-manifest pointer、写 outbox。

依赖不受变化影响的投影允许复用。Projection 自身完成不递增 decision_generation。重复发布相同 build 使用 idempotency key，不得重复递增。

### 4.5 两种工具读取

**默认：** 工具读取 snapshot/Manifest 所引用的不可变事实与投影。

**V1 受限扩展：** 必须查询尚未物化的历史时，可按 Manifest 中的修订与 knowledge boundary 做稳定历史查询。若只能查询 live mutable view，必须证明其相关 input frontier 与 Manifest 一致，并在同一一致读取中取得数据与版本，随后校验未改变；否则返回 STALE/UNAVAILABLE。

**仅检查 generation before == generation after 不足以放行 live 查询。** 新输入可能已经接受但尚未发布 Manifest，generation 仍不变。必须绑定输入修订，或拒绝该 live 读取。

generation 与 epoch 的检查来自权威协调存储。落后的读副本不得用来证明“没有新撤销”。

### 4.6 Mandatory context

至少包含目标优先级、Program、当前约束、restrictions/holds、overrides、sequence、progression、recent execution、数据质量与时间，以及 manifest/epoch/policy 身份。

这些块可以使用经验证的结构化摘要，不得为 token 预算静默省略。无法容纳或缺少必须证据时，返回结构化不足，不要求模型“尽力猜”。

投影标记 unavailable 可以出现在部分决策视图中，但不得伪装为完整值；哪些动作因此被禁用由 action obligations 决定。

### 4.7 失败语义

- Builder 崩溃：未发布的 view 不可见；旧授权只在自身有效性仍成立时可继续使用。
- 接受输入但投影未完成：不发布混合视图；需要失效的行动已由 epoch 先行阻断。
- Publish 与 urgent revoke 竞争：revoke 先成功则 publish 的 epoch guard 失败；publish 先成功则随后的 epoch 变化阻断基于它的新授权。
- Projection code 错误：撤回受影响发行版本，按政策推进失效屏障，重新构建；不能修改历史输出冒充当时结果。

## 5. 协议三：Authorization Protocol

### 5.1 内容、签发与状态

PrescriptionRevision 内容不可变。AuthorizationIssuance 绑定：

```text
authorization_id, user_scope
prescription_revision_id + canonical content_hash
decision_manifest_id, policy_bundle_id
authorization_epoch
evidence_resolution_ids / obligation results
execution_scope, valid_from, valid_until
issuance_reason: AI_PLAN | REUSE | FALLBACK | REVALIDATION
```

JSON/hash 的规范化规则必须版本化：单位、枚举、缺失值、字段排序和默认值不能产生不稳定依赖。安全判断不得只依赖未绑定的自由文本。

授权签发记录不可变；suspension/revocation/cancellation 是追加事件。数据库状态列可以作为投影缓存，不能成为唯一执行判据。

### 5.2 授权状态机

```text
ISSUED → SUSPENDED | REVOKED | EXPIRED
SUSPENDED → REVOKED | EXPIRED
```

同一授权不允许 SUSPENDED/REVOKED/EXPIRED → ISSUED。问题解除后签发新授权。相同处方内容可对应多个不同时期的授权；重新签发必须满足当时全部 guard。

保护性 hold 可有 review_due_at；到期表示需要处理，不默认清除。若特定政策允许自动解除，必须是显式、版本化的解除依据，并且仍需重新签发，不能恢复旧授权。

### 5.3 Authorize guard

新签发必须同时满足：

```text
attempt is current and authorized to commit
request_revision matches
fence token and unexpired lease match
root intent is live and before deadline
snapshot manifest is the current published manifest
manifest captured epoch == current authorization_epoch
manifest / evidence / projection / policy validity closure holds
all bound transitive artifacts are known, admissible and not revoked
no applicable protective hold / stop / restriction conflict
all authoritative evidence obligations pass
single and rolling policy envelopes pass
proposal dependency hashes match
prescription content has passed semantic validation
```

新签发、处方提交、旧 bundle supersession、intent 成功终态和 outbox MUST 在一个短协调事务内原子完成。最终事务内无需重跑 LLM，但必须重检所有可变 guard；外部计算的 validation certificate 绑定上述 basis，basis 不匹配即失效。

Policy envelope 同时约束处方与已接受的实际执行暴露；不能只累计计划量或只累计实际量而重复/漏计。V1 必须明确窗口、单位、去重、未知暴露处理和实际执行替代原计划预留的规则。

### 5.3a 授权有效期闭包

签发 MUST 服务端计算并保存不可变 validity certificate：依赖 identity/revision、valid_from/valid_until 或经政策批准的 TIMELESS、计算方法版本、closure digest。客户端只可请求更短期限，不能提交最终授权过期时刻或删去不利依赖。

```text
authorization.valid_until = min(
  requested_absolute_end,
  manifest.valid_until,
  authoritative_evidence_resolution.valid_until,
  all_relevant_projection.valid_until,
  all_required_evidence_admission_freshness_end,
  all_transitive_artifact_validity_end,
  issuance_time + policy.max_authorization_ttl,
  applicable_session_or_calendar_end
)
```

所有依赖须在签发时已经生效，最早结束必须晚于签发时刻。此版本不签发等待未来依赖生效的预约授权。关键 validity 未定义、缺失、计算失败或已过期即 DENY；不能把 NULL 当无限期。

TIMELESS 仅供显式政策批准、理由可审计的静态依赖，依然受撤销影响；不能据此让时敏健康证据无限期使用。TIMELESS approval 所依赖的政策也是撤销闭包的一部分。日界线和 session boundary 使用绑定的 timezone/calendar policy，不能由客户端日期计算。

闭包只允许缩短 A，不允许自动延长已签发 A。续期必须新 issuance。后来的非失效新 Manifest 不强迫替换旧 A；被撤销、撤回或过期的既有依据必须使旧 A 失权。

### 5.4 执行资格函数

```text
is_executable(prescription, authorization, actor, now, execution_scope)
```

必须检查主体、内容 hash、scope、当前可信时间、epoch、控制事件、hold、policy admissibility、依赖持续准入、传递制品未撤销、处方当前可执行关系和 execution 状态。A.valid_until 尚未到期不单独构成许可。只读 eligibility 响应不作为稍后执行的 bearer permit；START/RESUME/CONTINUE 在自己的协调点重新判断。

已有授权不要求始终引用最新 Manifest：非失效性的普通发布不强迫正在训练的用户切换计划；但相关失效输入 MUST 推进 epoch，或由显式有效性谓词捕获。新签发则必须使用最新可授权 Manifest。

### 5.5 START / CONTINUE / RESUME / COMPLETE

| 命令 | 必须行为 |
|---|---|
| START_SESSION(P,A,key) | 同事务检查执行资格，创建或幂等返回 execution，绑定确切 P/A 与开始时刻 |
| CONTINUE / foreground check | 按执行政策重新检查是否失权；不得仅依赖开始时曾有效 |
| PAUSE / stop / revoke | 记录停止资格与原因；安全事件不受 training-start lock 影响 |
| RESUME | 需要当前有效授权；必要时签发新 A，追加 resume binding，保留原 START A |
| COMPLETE / ingest actual | 保存实际事实，即使动作发生于授权失效后；不得倒填一个当时不存在的授权 |

普通重计划只能影响尚未执行部分的明确新安排，不能改写已经完成的实际组次或静默替换已开始 session 的处方。

### 5.6 紧急控制通道

有授权的 STOP / FORCE_REST，以及符合 protective policy 的风险信号，在短事务内：

```text
persist control / hold
increment authorization_epoch
append revocation/invalidation record
invalidate commit authority of old attempts
append outbox
COMMIT
```

该事务不调用模型，不等待 projection，不受普通规划预算或 revision cooldown 限制。可单独限制滥用流量，但不得复用普通规划队列导致停止请求饥饿。

“自由文本风险可即时识别”不是确定性保证。V1 必须提供明确的停止/不适入口。对进入风险上报通道的未解析文本，可先施加适用的 pending hold，再解析；任意普通聊天的风险识别只能按经评测的检测能力声明，不能声称零漏检。风险解析不可用时的权限收缩必须写入 rollout policy。

### 5.7 降级与 UI

PreauthorizedFallback 表示已审核的模板与适用谓词，不表示不经当前检查即可执行。实际使用时仍需匹配当前 basis、hold、scope、有效期与政策，并签发当次授权。

必须区分：`AI_GENERATED_CURRENT / REUSED_VALID_PLAN / PREAUTHORIZED_FALLBACK / UNAVAILABLE`。显示最后决策时间、数据缺失与可执行范围；系统不可用不得包装为个性化健康判断。

复用旧内容可以通过当前资格检查继续使用仍有效的 A，或签发新 A；禁止直接延长旧授权的 valid_until。

客户端只可渲染已提交处方为可执行。流式草案与 planning progress 不具有授权。离线模式仅允许政策规定的有限期凭据，明确无法保证撤销实时到达；不符合离线条件时不得离线启动。

## 6. 协议四：Persistent Bounded Planning Workflow

### 6.1 对象与独立版本

PlanningIntent 包含稳定根 ID、主体、local date/purpose、request revision、constraints fingerprint、deadline、根预算、状态。

PlanningAttempt 绑定 intent、request revision、Manifest、captured epoch、fence token、模型/提示/工具/策略版本和 proposal dependencies。

Concurrency partition 与语义去重键分离。Fingerprint 是服务端规范化约束的摘要，不能仅根据自然语言表面相同判定意图相同。

### 6.2 Intent 状态机

```text
ADMITTED → RUNNING → FOUND_VALID_PLAN
    │          ├─ PROVEN_CONSTRAINT_CONFLICT
    │          ├─ SEARCH_BUDGET_EXHAUSTED
    │          ├─ MODEL_REFUSAL
    │          ├─ MODEL_OUTPUT_INVALID
    │          ├─ DEPENDENCY_UNAVAILABLE
    │          ├─ STALE_RETRY_EXHAUSTED
    │          ├─ DEADLINE_EXCEEDED
    │          └─ CANCELLED
    └─ DEADLINE_EXCEEDED | CANCELLED
```

终态不可重新打开。单次 attempt 的错误可以按预算内政策修复，不必立即成为 intent 同名终态。成功只能与真实处方/授权提交同时发生；模型产生合法 JSON 不等于成功。

`PROVEN_CONSTRAINT_CONFLICT` 必须附形式化约束与输入 basis 下的冲突证明或确定性检测证据；结论只覆盖该形式化问题。模型多次未成功只能归为搜索/输出失败，不能推导现实目标不可满足。

### 6.3 Attempt 状态机

```text
CREATED → LEASED → BUILDING_CONTEXT → FITNESS
   → DEMAND_FEATURES → NUTRITION → VALIDATING → COMMIT_READY → COMMITTED
```

任一未提交状态可转 `STALE / FAILED / CANCELLED / LEASE_LOST`。上述终态 attempt 不得直接继续提交；重试产生新 attempt，消耗同一根预算。

修复发生在工作流明确的 transition 上，每次消耗相应预算。不得让 Agent 任意构造回到起点的控制指令。

### 6.4 Single-flight 与 request revision

| 新请求 | 处理 |
|---|---|
| 相同 scope、fingerprint、当前 basis | join 当前 intent/attempt |
| 同一目标的时间/器械等变化 | 同事务递增 request_revision，旧 attempt 失权，保留预算和 deadline |
| STOP / FORCE_REST / risk | 进入独立控制路径；不得等待旧模型 |
| 已终态后明确重新请求 | 经用户级准入后创建新 intent |
| 不同 session purpose | 按执行和冲突政策判断是否可并发；不得仅因 key 不同绕过同日限制 |

约束更新不默认延长 deadline。自动事件是否能创建新 intent 必须由版本化 admission policy 决定，防止自触发循环。新 root 受用户小时/日配额、模型容量与系统准入约束。

### 6.5 Lease 与 fencing

领取或接管 intent 原子产生更大的 fencing token 与 lease expiry；heartbeat 只能由当前 owner/token 延长，不能超过 intent deadline。

所有共享工作流写入及提交检查 token、lease、request revision 与 intent 状态。旧 worker 不因仍持有进程或网络连接而拥有写入权。

独立 Watchdog/Reaper 扫描过期 lease/deadline、封闭旧提交权、标记未确定外部调用、在允许时安排接管。恢复任务、取消和 admission 使用独立容量，不能被普通推理队列耗尽。

网络请求不能被数据库 fencing 从物理上撤回。一个已经获准 dispatch 的旧进程可能稍后才真正发出请求；其预留预算必须覆盖这次可能调用，但其结果不能恢复业务提交权。

### 6.6 Reservation ledger 与不可判定发送窗口

每次可能到达 provider 的物理请求必须有唯一 call reservation。推荐状态：

```text
RESERVED
  ├─ CANCELLED_BEFORE_DISPATCH
  └─ DISPATCH_INTENT
       ├─ DISPATCHED
       ├─ SETTLED
       └─ OUTCOME_UNKNOWN
DISPATCHED → SETTLED | OUTCOME_UNKNOWN
OUTCOME_UNKNOWN → SETTLED  (仅可靠对账)
```

`DISPATCH_INTENT` 在网络调用前持久化，语义为“此请求从现在起可能已发出”。这是故障判定边界；`DISPATCHED` 仅是后续诊断信息，不能承担“唯一可能计费”的边界。

执行顺序：

1. 预留短事务：校验 intent/lease/request revision、截止时间与根预算，原子占用 call slot、token/cost 上界。
2. 发送许可短事务：重新校验 owner/fence/deadline，将 reservation 转 DISPATCH_INTENT。
3. 事务外发送一次请求。SDK 隐式重试必须禁用，或每次实际重试都在同一受控账本内预留；不能把一次 SDK 调用当成一次物理请求。
4. 收到结果后幂等结算 actual usage；应用结果前再次检查业务写入资格。

若第 3 步之后、第 4 步之前崩溃，即使从未写过 DISPATCHED，恢复者仍必须按可能已消耗处理。新 worker 不得用同一 reservation 再发一次；必须新预留，或使用已验证具有所需幂等语义的 provider 协议。

仅 RESERVED 且通过原子状态竞争确定不存在发送许可时，允许取消并释放。DISPATCH_INTENT 之后缺少响应、网络超时或取消请求都不构成“未消耗”的证明。

### 6.7 三类预算

| 类别 | 含义 |
|---|---|
| Enforceable limits | 本服务可限制的请求次数、工具次数、输入规模、provider 支持的输出上限、启动/提交截止时间 |
| Reserved usage | 已预留的最大可计入消耗，包含 pending 与 outcome unknown |
| Settled actual usage | 可靠 provider 回执/对账确认的消耗 |

预算检查使用 settled + 所有未结算预留 + 本次预留，不允许并发透支。上界必须覆盖实际配置下所有计费维度；无法界定时不能宣传严格货币上限，应拒绝该配置或明确采用仅次数/token 的强限制。

未知结果可按预留值计入 intent 的预算占用，但不能在财务报表中伪称 provider 已确认收取该金额。截止时间约束本地继续工作和提交权，不保证远端推理与计费已停止。

晚到响应允许通过专门的幂等结算入口补齐账本和不可变证据，不允许旧 worker 任意修改 intent、request revision 或授权。

### 6.8 跨 Agent 依赖

```text
FitnessProposal hash F
  → PrescriptionDemandFeatures hash D (basis F + method versions)
    → NutritionProposal hash N (basis F,D,Manifest,policy)
```

Fitness 任何授权相关内容变化都使旧 D/N 不适用于新 bundle。修复后必须生成新 D，并重新运行或按显式可验证规则重新计算 N；不能只改 N 的引用 hash。所有额外请求继续消耗根预算。

Demand 字段明确区分 `PRESCRIBED_QUANTITY / TARGET / ESTIMATE`，不作为实际执行或生理事实。Cross-domain checker 使用可计算特征、证据与 Policy Envelope；不得只依赖 Agent 自评的 MODERATE 等标签。

### 6.9 失败与终态竞争

- SDK/模型 transient error：在根预算与 deadline 内重试；不可重试错误直接结束相应路径。
- Refusal：独立分类，不用格式修复 prompt 强行重试。
- malformed/incomplete：不得激活局部结果；修复需预算和明确政策。
- COMMIT 响应丢失：按 intent/commit id 查询事实，不能重新无条件签发授权。
- CANCEL、deadline 与 COMMIT 竞争：由协调事务顺序决定；watchdog 不得把已成功提交的 intent 改回失败。
- Provider outage：熔断、并发上限与重试配额控制共享容量；fallback 仍走 Authorization Protocol。
- 正常队列饱和：可以拒绝新的规划，不得使停止/撤销通道不可用。

## 7. 协议五：Replay Protocol

### 7.1 两种模式

| 模式 | 问题 | 规则 |
|---|---|---|
| Historical Reconstruction | 当时系统依据什么做了什么 | 使用当时可知的证据、当时政策/算法/映射；优先重放已保存输入输出与验证记录 |
| Current Policy Backtest | 当前版本面对当时可知证据会如何决定 | 固定过去 knowledge cutoff，使用明确指定的当前政策/算法版本，重新计算候选与投影 |

Historical Reconstruction 不承诺重新调用同名模型得到逐字相同输出。历史响应和工具证据是复原决策链的主要依据；旧模型不可用或随机性导致不同必须标注，不伪称精确复现。

### 7.2 时间边界

每类实体逐一定义 effective time、系统首次持久获知的 known time、recorded time、supersession 的生效及获知时间。known_at 由可信接收流程分配，不能接受 provider 传入的时间来回填系统知情历史。

迟到证据可以具有早的 effective_at 和晚的 known_at；过去 cutoff 查询必须仍排除它。政策下的历史更正、event merge/split、admission 撤回及 mapping 变更都遵守同样边界。

Replay 的所有上下文工具、检索索引、projection、resolver 和 cache key 都绑定 replay mode、cutoff、release bundle 与主体。不得从 live current tables 偷取结果。

### 7.3 当前算法与未来知识

Current Backtest 允许使用当前通用算法，但不能携带 cutoff 之后才人工得知的个体映射、偏好、限制解除或结果标签。用当前逻辑对当时原始证据重新推导的结果，必须标记为 counterfactual derivation，不冒充当时已知事实。

用未来 evaluation outcomes 调参后再在相同历史上报告提升，不构成独立验证。Release evaluation 必须声明训练/调参/测试切分、冻结时间、可用数据与泄漏检查。当前模型的广泛训练知识无法被简单还原为过去模型知识，报告必须说明这一反事实评估限制。

### 7.4 Replay 状态机

```text
DEFINED → INPUTS_RESOLVED → RUNNING → COMPLETED
                ├─ BLOCKED_MISSING_ARTIFACT
                ├─ INVALID_KNOWLEDGE_BOUNDARY
                └─ FAILED
```

Replay 环境不能签发 production authorization、写用户 live state 或触发通知。输出写入隔离 evaluation scope；模拟授权显式标记为 simulation。

### 7.5 Outcome separation

必须分别记录 prescription、actual execution、adherence estimate 与 outcome，保留各自证据和不确定性。未上报不是零执行或正常恢复。

新方案的反事实输出不能直接与旧方案下真实 outcome 配对并宣称因果效果。历史回放可评估一致性、授权违规、判断差异和参考评价；疗效/训练效果结论需要另行定义的研究或实验设计。

Weekly Analyst 可以提出关联性解释与 durable proposal；进入自动 durable change 前，必须完成 intervention/outcome 定义、结果窗口、release gate、监控及回滚协议。

### 7.6 最小 Replay 输出

```text
replay_mode, cutoff, release_bundle, input_manifest/hash
included / excluded evidence and reasons
admission / mapping / projection versions
recorded-output replay or fresh-model-run marker
proposal + validation + simulated authorization results
missing artifacts / stochastic limitations / leakage audit
```

## 8. 端到端事务清单

| 事务 | 原子写入与 guard | 事务外工作 |
|---|---|---|
| T1 Evidence receive | 来源幂等、raw revision、可信 known_at | 解析、关联候选 |
| T2 Admission/control update | T2-IN：admission/hold 修订、frontier/必要 epoch、失效事件；T2-SEAL：完成凭据+SEALED/head；T2-GLOBAL：registry 排他、撤销/revision/receipt；各自独立原子 | factset/projection 构建、闭包计算、通知投递 |
| T3 Manifest publish | registry 共享资格、sealed basis/epoch 校验、generation 递增、manifest/current pointer、outbox | 构建与复用 projections |
| T4 Intent admit/update | single-flight、request revision、配额、旧 attempt 失权 | 上下文与推理 |
| T5 Lease/reservation | lease/fence、预算预留、dispatch permission 各自原子迁移 | 网络请求 |
| T6 Commit/issue | registry 共享资格、有效期闭包与全部 guard、处方、授权、bundle supersession、intent success、outbox | 模型、证据检索、计算验证 |
| T7 Start/resume/continue | registry 共享资格、当前执行资格、execution binding/检查事件、幂等、outbox | 用户物理执行 |
| T8 Settle/reap | 幂等结算或旧 owner 失权、unknown/terminal 状态 | provider reconciliation、重新调度 |

T2/T3/T4/T5/T6/T7/T8 对相同用户/intent 的竞争 MUST 遵循统一锁序和 guard。流水线各阶段独立事务不是跨阶段原子保证；必须由不可变 basis、版本与最终 guard 连接。

## 9. 自动激活验收矩阵

这些是生产验收规范。配套 34 个模型对应案例已运行，但真实 PU/DC/WF/E2E 验收仍未完成；逐项抽象边界见 fixtures.json/model_report.json。每项应包含 Given/When/Then、故障注入位置和持久状态断言；关键并发项应覆盖不同事务提交顺序。

| ID | 反例/故障 | 必须断言 |
|---|---|---|
| E01 PLAN_NEVER_COMPLETES_ACTUAL | 计划三组，用户仅完成一组 | 不产生另外两组 actual；不虚增 progression |
| E02 UNRESOLVED_RISK_DOES_NOT_DISAPPEAR | 风险通道文本尚未完整解析 | 按政策建立 pending hold；相关行动不能因 unresolved 放行 |
| E03 DUPLICATE_SOURCES_DO_NOT_MULTIPLY_EVENTS | 同一训练来自 chat/Hevy/watch | 独立事件数为一，来源仍保留 |
| E04 AMBIGUOUS_EVENT_MATCH_IS_NOT_TRUTH | 两次接近的训练可能重复 | 不强制合并或认定独立成功；保留关联不确定性 |
| E05 UNKNOWN_EXPOSURE_IS_NOT_ZERO | 完成量不完整 | 下界保留，上界无依据时 unknown；不生成虚假零 |
| E06 CONTRADICTION_CANNOT_BE_CHERRY_PICKED | 引用早期成功、忽略后来失败 | Resolver 返回反证，义务按完整政策集合判断 |
| E07 CORRECTION_WITHDRAWS_ACTION_BASIS | 更正曾授权 progression 的记录 | admission/projection/新授权资格失效；历史仍可重建 |
| E08 SUMMARY_CANNOT_GRANT_AUTHORITY | 外部备注经多轮总结成偏好/批准 | summary 不获得命令或批准资格 |
| D01 PROJECTION_DOES_NOT_BUMP_GENERATION | readiness 计算完成 | generation 不变，直到 Manifest 原子发布 |
| D02 REUSE_USES_BASIS_NOT_AGE | 无关输入变化 | 合法复用未受影响 projection，无假 stale 循环 |
| D03 UNPUBLISHED_INPUT_CANNOT_LEAK | generation 不变但新输入已接受 | live tool 不能混入未绑定修订 |
| D04 ABSENCE_DEPENDENCY_IS_TRACKED | 新插入 restriction/事件 | 集合修订或 epoch 捕捉变化 |
| D05 PUBLISH_CANNOT_OVERWRITE_URGENT_EPOCH | 构建期间 hold 生效 | 旧 build 发布失败或不能授权；不得贴新 epoch 强行发布 |
| A01 REVOKE_PRECEDES_REPLAN | revoke 后模型不可用 | 旧授权仍立即失效，不等待替代计划 |
| A02 STALE_MANIFEST_CANNOT_REAUTHORIZE | epoch 更新而 generation 未更新 | 旧 Manifest 不能签发新 A |
| A03 START_REVOKE_SERIALIZES | START 与 REVOKE 并发 | 按提交顺序决定；不得出现 revoke 后成功开始 |
| A04 EXPIRY_NEEDS_NO_STATUS_JOB | 超过 valid_until，缓存 VALID | evaluator 返回不可执行 |
| A05 REAUTH_DOES_NOT_REWRITE_HISTORY | P7 重新签发 A2 | A1 不恢复，原 START 仍绑定 A1 |
| A06 FALLBACK_IS_NOT_PRIVILEGED | hold 生效且 AI 故障 | fallback 同样受限，无适用项则 UNAVAILABLE |
| A07 STOP_PATH_SURVIVES_QUEUE_SATURATION | 推理队列/预算耗尽 | 停止与撤销仍可处理 |
| A08 ACTUALS_SURVIVE_UNAUTHORIZED_EXECUTION | 用户失权后仍实际训练 | 保存 actual 和当时授权状态，不伪造授权或丢记录 |
| W01 CRASH_DOES_NOT_REFUND_EXTERNAL_BUDGET | DISPATCH_INTENT 后任意位置崩溃 | 预留保留；即使无 DISPATCHED 也不可退款 |
| W02 RESERVE_CANCEL_RACE_IS_ATOMIC | 取消与发送许可竞争 | 不能同时释放预算并获得发送许可 |
| W03 SDK_RETRIES_ARE_ACCOUNTED | provider transient error | 每次物理请求被预算覆盖，无隐式免费重试 |
| W04 SINGLE_FLIGHT_PRESERVES_NEW_CONSTRAINTS | 70min/full gym → 20min/no equipment | request revision 增长，旧 attempt 无提交权，预算不重置 |
| W05 OLD_WORKER_CANNOT_COMMIT | token 7 过期，token 8 接管 | token 7 仅可经专门入口结算，不可提交处方 |
| W06 LATE_RESULT_CANNOT_REOPEN_INTENT | 已取消/过 deadline 才返回 | 结果可审计，intent 不复活 |
| W07 FITNESS_CHANGE_INVALIDATES_NUTRITION | F1/D1/N1 → F2 | D1/N1 不得直接用于 F2；重新计算消耗原预算 |
| W08 COMMIT_ACK_LOSS_IS_IDEMPOTENT | DB 已提交，响应丢失 | 查询返回原结果，不重复签发或重复 supersede |
| W09 SEARCH_FAILURE_IS_NOT_INFEASIBILITY | 多次模型失败 | 不产生 PROVEN_CONSTRAINT_CONFLICT |
| R01 FUTURE_CORRECTION_IS_EXCLUDED | 九月更正八月记录 | 八月 cutoff 不读取九月知识 |
| R02 REPLAY_MODES_ARE_SEPARATE | 同一 cutoff 两种 replay | 分别绑定历史和当前 release，不混用 |
| R03 FUTURE_PERSONAL_MAPPING_IS_EXCLUDED | 后来人工完成个体映射 | backtest 不直接导入该未来知识 |
| R04 REPLAY_CANNOT_WRITE_LIVE | 模拟得到有效计划 | 无 production authorization 或 live mutation |

## 10. 自动激活前必须发布的政策配置

以下不要求在本协议里拍定训练/营养数值，但自动激活环境 MUST 有显式、版本化的值与责任人。缺少配置时禁止对应动作，不允许模型补齐。

| 配置包 | 必须确定的内容 | 缺失时行为 |
|---|---|---|
| Admission / exposure | 各用途门槛、模糊事件关联、未知暴露、反证优先规则 | 保留 unresolved，阻止需该证据的扩大权限 |
| Safety/control | protective trigger、作用范围、解除条件、风险解析故障策略 | 不开放依赖未定义保护协议的自动行动 |
| Publication | 各 projection dependency signature、输入失效分类、Manifest freshness | 不发布可授权 view |
| Policy envelope | 单次/累计/变化速率、实际与计划暴露对账、nutrition coupling | 不允许相关自动处方 |
| Authorization | scope、TTL、START/CONTINUE 检查频率、离线许可、重新签发政策 | 不签发相应执行资格 |
| Workflow | 根预算、deadline、lease、重试/修复规则、用户准入与容量 | 不启动无界 planning |
| Fallback | 模板、适用/禁止谓词、证据与有效期 | UNAVAILABLE |
| Replay/release | 历史制品保留、切分、泄漏审计、release 指标/阈值、回滚条件 | 不宣称评测通过或开放自动 durable change |

## 11. Freeze 决议、变更控制与实施顺序

### 11.1 Freeze 决议

Protocol v1.2 自本 release 起标记为 **FROZEN**。Freeze 的含义是：

1. 五个协议的权限含义、状态轴和允许/禁止迁移冻结。
2. 18 条 invariant 与 T1–T8 原子边界冻结。
3. `decision_generation`、`authorization_epoch`、SafetyRegistry、Factset build→seal、DISPATCH_INTENT、Authorization validity closure 的语义冻结。
4. 34 项生产验收规格仍是自动激活 gate；有限状态模型 PASS 不把 PU/DC/WF/E2E 标为已实现。
5. 默认环境继续是 `LOCAL_SHADOW / deny-by-default`；FROZEN 不等于 production auto-activation approved。

### 11.2 Freeze 后允许的实现演进

在不减弱冻结语义的前提下，以下内容可以继续演进：字段名、物理分表、索引顺序、分区、ORM 结构、缓存实现、SQL 语法、数值型 TTL / policy threshold，以及经过测试证明等价的数据库锁实现。

以下变化 **必须** 新建 protocol version 或明确 ADR + compatibility decision，不能在 migration / repository / prompt 中静默修改：Evidence admission 资格含义、Manifest 发布规则、Authorization guard、SafetyRegistry 撤销语义、Planning budget/lease/fencing 语义、Replay knowledge boundary、任一 invariant、T1–T8 原子边界或 command authority。

### 11.3 实施顺序

1. 从冻结逻辑 schema 推导 PostgreSQL DDL 与 migration。
2. 生成 Pydantic command/domain contracts、错误码和 repository transaction interfaces。
3. 将有限状态模型的关键交错迁移到真实 PostgreSQL DC 测试，并实现 worker fault-injection。
4. 实现 local modular monolith、planner worker、independent reaper 和 `LOCAL_SHADOW` 配置。
5. 接入 canonical evidence/workout 数据与 Decision Publication。
6. 接入 Fitness Coach 的 read-only context tools 与 OpenAI Responses API，在 shadow mode 运行。
7. 完成 34 项 PU/DC/WF/E2E、授权审计、降级 UX 和 release evaluation 后，才允许讨论 production auto-activation。

可以立即开始开发，但不得将“协议已冻结”解释为“自动处方已经被验证安全或可上线”。

## 12. Freeze 证据与尚未实现的验证

配套 `protocol_model/run_model.py` 生成带源码摘要的报告：34 个原规格模型案例、18 个补充边界、9 组有限交错和 8 个故障变体。P01–P03 验证 factset；P04–P05/P16/P17 验证制品；P06–P08/P14/P18 验证 validity；P09–P13/P15 验证相邻约束。原 18 条 invariant ID 与 T1–T8 保留；T2 子命令是不同原子事务，不是一个长事务。

模型通过只关闭已编码反例。管理员权限、共享 gate 的真实数据库读语义、实际进程故障、完整暴露/政策域、跨主体隔离和离线 UX 尚未实现。独立 freeze review 已接受本轮新增的全局撤销权限与锁边界，并补充了 T2-GLOBAL commit 作为撤销执行线性化点的明确语义。协议因此标记为 FROZEN；仍未生成 DDL，生产 PU/DC/WF/E2E 与自动激活 gate 均未完成。


---

# Part VII — Frozen Logical DB Schema Design (verbatim canonical appendix)

# KineticLoop — DB Schema Design v0.2 FROZEN Logical Baseline

状态：**FROZEN logical baseline for implementation；不含 SQL；Protocol v1.2 已冻结。**

Canonical architecture baseline：`KineticLoop_v1.2_Protocol_FROZEN.md`。本文件是其下游设计，不能以表结构覆盖协议。v1.1 中相冲突的 Evidence / generation / planning / authorization / replay 语义不再适用。

范围：从 INV-01–18 与 T1–T8 反推逻辑关系、身份与版本、约束、查询索引、唯一 command/write entrypoint、事务与锁；为 34 项验收规格建立实现落点。不引入新的架构层，不实现 DDL、ORM、数据库迁移或生产服务。

## 1. 数据建模纪律

### 1.1 三类数据，不混用权威

- **I：immutable history**。证据修订、admission、Manifest、处方、授权签发、授权事件等只追加，禁止普通运行角色更新/删除其语义内容。
- **M：mutable operational state**。当前指针、lease、fence、request revision、预算余额、投递状态等允许在唯一命令入口及 guard 内更新；变更同时写审计事件。
- **B：build/job state**。可变运行元数据与不可变完成结果分离；不能因为 build status 为 READY 就具有行动授权。

“Immutable”不取代隐私删除政策。敏感 payload 可以存储为受控 blob reference；依法或按产品政策删除后留下允许保留的 tombstone / artifact-unavailable 语义，不伪称还能完整 replay。这里不规定无限保留期。

### 1.2 共同字段与引用约束

所有用户数据使用 `subject_id`（经认证的用户/租户作用域），不接受模型指定主体。每个引用都必须证明相同主体；推荐以 `(subject_id, entity_id)` 为复合候选键并建立相应复合外键。全局只读 catalog / policy 使用独立 namespace，不能以 `subject_id=NULL` 作为任意跨用户读取的豁免。

I 类行共同包含 `id, subject_id, recorded_at, content_schema_version`，内容对象另带 `content_hash, hash_scheme_version`。有历史获知含义的对象另带 `known_at`；有现实发生时间的对象另带 `effective_at` 或有效区间。各表以下只列额外关键字段，类型暂以 ID / Integer / Instant / Decimal / Enum / TypedPayload / BlobRef 表示。

历史修订引用稳定实体 ID 与明确 revision ID。`supersedes_id` 是追加关系，不能更新旧行来擦除其历史；当前生效区间由追加决策推导。发生时间冲突有明确的 source revision / server ordering tie-break，不能使用 UUID 大小猜测先后。

用于幂等/唯一性的 logical_member_key、scope、slot 必须有明确且非空的规范值；不适用使用类型化的 NONE 语义，不能依赖 NULL 的默认唯一性行为防重。known_at 表示可信持久接收边界；只读一个事务开始时间不足以证明该时刻数据已经提交可见。历史决策优先按已保存的 Manifest/证据选择重建，任意时间 cutoff 则必须绑定可靠的持久接收记录或已提交知识前沿。

### 1.3 保证的三种强制位置

| 标记 | 含义 | 例子 |
|---|---|---|
| DB | 后续可落成唯一性、外键、非空、行内检查及写权限限制 | 同用户一天一个 head；同一 issuance ID 不可重写 |
| TX | 持锁短事务内读取、判断和原子更新 | 当前 epoch/fence；根预算不并发透支 |
| DOMAIN | 版本化领域代码或 resolver 的判断，结果绑定 basis 后由 TX 复核 | 证据是否充分；累计暴露是否符合政策 |

不得把跨行安全判断写成一个调用外部表的普通 CHECK 来假装持续有效。PostgreSQL 的 CHECK 不为其他行的未来变化提供这种保证；复合外键与唯一性适合表达身份和关系约束。[PostgreSQL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)

索引是查询或唯一性工具，不是完整授权协议。基于 `now()` 的“尚未过期”不能成为授权唯一性的动态 partial-index 条件；过期必须运行时检查。Partial unique index 仅用于行内稳定状态谓词，例如 ADMITTED/RUNNING。[PostgreSQL Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html)

### 1.4 控制计数与输入修订

S01 仅存两个协议计数器：`decision_generation`、`authorization_epoch`。`current_factset_id` 和 `input_frontier_hash` 是不可变输入修订集合的指针/摘要，不是第三个授权 epoch。`execution_basis_event_id` 指向最近一次改变计划/执行暴露的已提交事件，是累计 envelope 校验的输入依据，不是新的授权机制。

Projection 完成不改 generation。Manifest 发布不自动改 epoch。Admission/输入发生变化时先分类：需要失效则同事务推进 epoch；无关的原始样本不进入该锁热点。

## 2. 逻辑表目录

以下 51 个关系是候选逻辑表，不是对物理分区数量、索引数量或 ORM 类数量的冻结。关系中的 payload 必须有闭合的类型契约；关键身份、用途、时间、权限与 join key 不能藏在自由文本中。

### S01 `user_decision_state` — M

- **作用/字段：** `subject_id` 主键；current_factset_id、input_frontier_hash、active_program_id、active_policy_bundle_id、current_manifest_id、decision_generation、authorization_epoch、last_control_event_id、execution_basis_event_id。
- **约束：** DB：每主体一行、计数非负、指针同主体。TX：generation 仅 T3 成功发布时递增；epoch 只由失效命令推进；指针与事件同事务。
- **索引：** 主键是用户协调锁入口；与独立 registry 共享/排他 gate 分开，不串行化不同用户的普通写入。
- **唯一写入所有者：** DecisionStateCoordinator；决策发布/输入/控制字段经 T2/T3 更新；改变计划或执行暴露的 T2/T6/T7 同事务更新 execution_basis_event_id；其余事务仅锁住并读取 guard。
- **映射：** INV-07, INV-08, INV-09, INV-10, INV-17；T2, T3, T4, T5, T6, T7, T8。

### S02 `command_receipts` — M

- **作用/字段：** command_kind、client_key、actor_scope、request_hash、status、result_entity_refs、error_code、accepted_at、completed_at。
- **约束：** DB：主体/actor_scope/command_kind/client_key 唯一。TX：同 key 同 hash 返回既有结果；不同 hash 拒绝。数据库 mutation 的 receipt 与结果同事务，不能先写 SUCCESS 再操作。
- **索引：** 幂等唯一键；completed_at 支持保留策略。不因删除旧 receipt 允许危险命令重放，见 §3。
- **唯一写入所有者：** CommandGateway 与对应原子事务；模型无权写。
- **映射：** INV-02, INV-08, INV-11, INV-13, INV-18；T1, T2, T3, T4, T5, T6, T7, T8。

### S03 `domain_events` — I

- **作用/字段：** aggregate_type/id、aggregate_revision、event_type、causation_command_id、correlation_intent_id、typed payload、effective/known time。
- **约束：** DB：聚合内 revision 唯一、引用同主体。TX：与可见状态变化同事务；不要求所有原始 telemetry 使用同一个用户序号。
- **索引：** subject/aggregate/revision；subject/known_at；correlation_intent_id。
- **唯一写入所有者：** 每个领域 command 的事务；EventWriter 负责格式，不绕过领域入口。
- **映射：** INV-07, INV-08, INV-12, INV-13, INV-16, INV-18；T1, T2, T3, T4, T5, T6, T7, T8。

### S04 `outbox_deliveries` — M

- **作用/字段：** domain_event_id、destination、delivery_status、next_attempt_at、delivery_lease、attempt_count、last_error。
- **约束：** DB：event/destination 唯一。TX：与对应 event 同事务创建；投递成功不是业务提交的前提。
- **索引：** 待投递状态/next_attempt_at、lease expiry。claim 使用队列专属锁，不反向取得 S01。
- **唯一写入所有者：** 原命令创建、OutboxDispatcher 更新投递元数据；不修改事件内容。
- **映射：** INV-08, INV-12, INV-17；T1, T2, T3, T4, T5, T6, T7, T8。

### S05 `policy_bundles` — I

- **作用/字段：** policy_namespace/version、admission/obligation/envelope/authorization/fallback/workflow 配置、dependency signatures、engine artifact refs、配置完整性报告、review provenance。
- **约束：** DB：namespace/version 唯一、不可变。DOMAIN：各模块闭合 schema、引用版本可解析。未配置与显式禁用不同；hash 不是人工审核通过的证明。
- **索引：** namespace/version；content_hash 仅做同 namespace 内容定位。
- **唯一写入所有者：** PolicyRegistry.PublishBundle；生效只经 T2 激活到用户指针，不能修改全局 alias 静默改变执行规则。
- **映射：** INV-02, INV-05, INV-06, INV-09, INV-15, INV-16；T2, T3, T6, T7。

### S06 `program_versions` — I

- **作用/字段：** program_id、revision、parent_version_id、goals、结构化 blueprint/schedule/targets、nutrition policy refs、activation basis。
- **约束：** DB：主体/program/revision 唯一。TX：唯一 active 权威是 S01.active_program_id；pending proposal 不能改变该指针。不再维护第二个独立可写 ACTIVE 标记。
- **索引：** subject/program/revision；subject/known_at。
- **唯一写入所有者：** ProgramService.ActivateApprovedProgram，或明确授权的初始 Program import；激活 T2 重检批准与 basis。
- **映射：** INV-02, INV-07, INV-09, INV-16；T2, T3, T6。

### S07 `durable_change_proposals` — I

- **作用/字段：** proposal_family_id、revision、change_class、base_program_id、base_manifest_id、exact proposed change、origin proposal/artifact、content_hash。
- **约束：** DB：family/revision 唯一、基础版本同主体。DOMAIN：变化类别与 payload 相符。改变内容必须新 revision，不修改已被批准对象。
- **索引：** subject/change_class/known_at；base_program_id。
- **唯一写入所有者：** ProgramReviewService.SubmitChangeProposal；此入口不能激活 Program。
- **映射：** INV-02, INV-09, INV-15, INV-16；T2。

### S08 `approval_issuances` — I

- **作用/字段：** proposal_revision_id、bound_content_hash、actor_id、command_receipt_id、approved_scope、base_program/policy、approval time/expiry、approval_mode。
- **约束：** DB：一次批准 command 只产生一个 issuance；subject/proposal/hash 绑定。TX：用户批准入口或明确的 change-class 自动批准政策才能写；激活时再检查有效期、基础版本与当前权限。
- **索引：** proposal_revision_id；subject/actor/time。使用同 issuance 重放 Program activation 必须返回原 activation，而非再次创建新版本。
- **唯一写入所有者：** ApprovalService.ApproveChange；撤回通过追加 domain event，不篡改 issuance。
- **映射：** INV-02, INV-09, INV-15, INV-16；T2。

### S09 `evidence_revisions` — I

- **作用/字段：** source_connection_id、source_object_type/id、source_revision/observation_key、payload hash/blob、observed_at、known_at、trust_class、source_class、command_authority=NONE。
- **约束：** DB：可靠 provider revision 时来源对象/revision 唯一；无可靠 revision 时用稳定接收 observation key 去重。payload hash 相同只可去重存储，不能删除独立时间点的测量或回滚后的新观察。
- **索引：** subject/source/object/revision；subject/known_at；subject/observed_at。
- **唯一写入所有者：** EvidenceService.ReceiveEvidence；known_at 由可信持久接收边界产生，不能回填 provider 时间。
- **映射：** INV-01, INV-02, INV-03, INV-15, INV-16, INV-18；T1。

### S10 `candidate_assertions` — I

- **作用/字段：** assertion_family/revision、evidence_revision_id、predicate、typed value/unit、negation/modality、assertion_type、field provenance、extractor artifact、uncertainty。
- **约束：** DB：证据引用同主体；结构 schema 闭合。DOMAIN：否定、未知、零不能混合；模型 confidence 仅诊断。候选无 admission/command 写权。
- **索引：** evidence_revision_id；subject/predicate/effective_at；assertion_family/revision。
- **唯一写入所有者：** ExtractionService.RecordCandidate；失败候选留痕，不自动进入事实投影。
- **映射：** INV-01, INV-02, INV-04, INV-15, INV-16；T1, T2。

### S11 `underlying_events` — I

- **作用/字段：** event_id、subject、event_kind、creation provenance、初始已知时间；表示稳定的现实事件身份。
- **约束：** DB：event_id 同主体唯一。DOMAIN：创建 ID 不等于确认事件发生，不等于获得 progression credit。事件合并/拆分由新 association decision 表达。
- **索引：** subject/event_kind/known_at。
- **唯一写入所有者：** EvidenceAssociationService；禁止由 Agent 自造 ID 后直接计数。
- **映射：** INV-03, INV-04, INV-16, INV-18；T2。

### S12 `event_association_decisions` — I

- **作用/字段：** association_family/revision、evidence_revision_id、candidate_event_ids、accepted_event_id（可空）、MATCHED/AMBIGUOUS/RETRACTED、method/policy、supersedes、source lineage。
- **约束：** DB：family/revision 唯一；单项决定的 accepted_event 只能有一个。TX：同一关联前序不能产生两个同时生效的 successor；merge/split 的关联批次原子进入新的 factset。
- **索引：** evidence_revision_id/known_at；accepted_event_id；supersedes_id。
- **唯一写入所有者：** EvidenceAssociationService.DecideAssociation；AI matching 仅提供候选。
- **映射：** INV-03, INV-04, INV-05, INV-16；T2。

### S13 `admission_decisions` — I

- **作用/字段：** assertion_id、action_scope、decision=ELIGIBLE/NOT_ELIGIBLE/UNRESOLVED、policy_bundle_id、evidence basis、reason_codes、supersedes_id、effective/known times。
- **约束：** DB：assertion/scope/decision revision 唯一；scope 非空。TX：同 scope 的当前决策更替经同一协调点，禁止并发分叉；撤回追加新决策。不允许 verified boolean 代替用途资格。
- **索引：** subject/assertion/action_scope/known_at；supersedes_id；policy_bundle_id。
- **唯一写入所有者：** AdmissionService.DecideAdmission；触发失效的决策与 epoch 变化同 T2。
- **映射：** INV-01, INV-02, INV-04, INV-05, INV-08, INV-16；T2。

### S14 `canonical_fact_revisions` — I，领域事实版本根

- **作用/字段：** stable_fact_id、revision、fact_kind、underlying_event_id、source assertion/admission refs、effective/known time、typed fact payload、supersedes_id。
- **领域形状：** WORKOUT_ACTUAL（稳定 set/bout 子身份、实际动作/数值/缺失状态）、HEALTH_OBSERVATION、NUTRITION_INTAKE、BODY_MEASUREMENT、OUTCOME_OBSERVATION。每种形状独立领域 schema；计划处方不属于此 union。
- **约束：** DB：stable_fact/revision 唯一、kind/identity/单位形状一致、actual 字段不可引用处方作为完成证据。DOMAIN：字段 provenance 与各用途 admission 对齐。被接受的用户报告仍保留 USER_REPORTED 性质。
- **索引：** subject/kind/effective_at；subject/stable_fact/revision；underlying_event_id；known_at。
- **唯一写入所有者：** CanonicalFactService.AcceptFactRevision，嵌入 T2 admission/修订事务。
- **映射：** INV-01, INV-03, INV-04, INV-16, INV-18；T2。
- **物理化边界：** 这是一个逻辑版本根，不是任意 key/value EAV。DDL 阶段可为高频 strength_sets、cardio_bouts、health/nutrition 数值拆 typed child relations，但必须保持 revision/admission 与事务边界；不能把未定义 payload 留给 LLM。

### S15 `factset_revisions` — B→I（仅 SEALED 成为 canonical history）

- **作用/字段：** factset_id、status=BUILDING/READY/SEALED/STALE/ABANDONED、captured_input_frontier、captured_epoch、parent_factset_id、storage_mode=FULL/DELTA、delta_depth、member_revision、completed_member_revision、membership_digest、completion_certificate、association/admission/mapping basis、knowledge boundary、effective scope、sealed_at。
- **约束：** DB：ID 唯一，canonical 引用目标必须 SEALED。TX：BUILDING 唯一 builder 可写；READY 固定成员/摘要，未成为 canonical；T2-SEAL 复核 frontier/epoch/完成凭据后原子封存+切 S01 head。SEALED 不可编辑；重复 seal 不重新切旧 head；失败保留原 head。
- **索引：** subject/status/created_at（清理 build）；subject/known_at（SEALED）；parent_factset_id。
- **唯一写入所有者：** CanonicalViewService.BeginBuild/WriteCandidate/CompleteFactset 只写 build；SealFactset 独占 T2-SEAL。构建不持 S01 长锁。
- **映射：** INV-03, INV-05, INV-06, INV-07, INV-16, INV-17；T2（SEAL）, T3。

### S16 `factset_members` — B→I（仅父对象 SEALED 后）

- **作用/字段：** factset_id、member_operation=SET/REMOVE、member_kind、类型化 fact/admission/association/mapping revision 引用、logical_member_key、action_scope；REMOVE 是 tombstone。
- **约束：** DB：factset/kind/logical_member_key/scope 唯一；引用同主体且类型匹配。TX：仅父 BUILDING 可写；写成员与推进 member_revision 同一 build 事务；Complete 与 writer 在同一 build gate 串行化；READY/SEALED 禁止增删改。所有 canonical reader 排除未 SEALED 成员。
- **索引：** factset/kind/logical_member_key；被引用 revision 的反向索引。
- **唯一写入所有者：** CanonicalViewService.WriteCandidate；不由 SealFactset 批量写 members。
- **映射：** INV-03, INV-05, INV-06, INV-16, INV-17；T2（SEAL/read guard）, T3。

### S17 `control_events` — I

- **作用/字段：** control_id、control_revision、kind（HOLD/STOP/OVERRIDE/RESTRICTION/CLEAR）、scope、command/evidence/admission refs、policy、effective/known times、review_due_at、previous_event_id。
- **约束：** DB：control/revision 唯一、CLEAR 必须引用被解除对象及 clearance basis。DOMAIN：普通文本/摘要不能产生 command authority。TX：改变执行权限与 epoch 同事务。
- **索引：** subject/control/revision；subject/scope/known_at；关联 evidence_id。
- **唯一写入所有者：** ControlService.ApplyControl / ClearControl（同一 writer）；紧急路径可先 hold 再完整解析。
- **映射：** INV-02, INV-08, INV-09, INV-10, INV-15, INV-16；T2。

### S18 `control_heads` — M，同步投影

- **作用/字段：** subject/control_id、last_event_id/revision、current state、execution_scope、review_due_at。
- **约束：** DB：subject/control_id 唯一。TX：与 S17 同事务更新；不能靠异步消费者更新执行安全状态。失配或不可验证时 authorization fail closed，不从缓存推导已解除。
- **索引：** subject/active-state/scope；待 review 时间（仅调度，不自动清除）。
- **唯一写入所有者：** ControlService；可从 S17 重建但重建期间不得错放行。
- **映射：** INV-08, INV-09, INV-10；T2, T6, T7。

### S19 `exercise_catalog_revisions` — I

- **作用/字段：** namespace、exercise_identity、revision、movement/equipment/unit semantics、compatibility、known_at。
- **约束：** DB：namespace/exercise/revision 唯一；个人 catalog 受主体隔离，全局 catalog 只读。DOMAIN：不同器械/load convention 不因名称相近自动兼容。
- **索引：** namespace/exercise/revision；movement/equipment 用于 bounded catalog search。
- **唯一写入所有者：** ExerciseCatalogService.PublishRevision；被采用为用户输入的变化经 T2 分类/失效。
- **映射：** INV-02, INV-05, INV-06, INV-16；T2, T3。

### S20 `exercise_mapping_decisions` — I

- **作用/字段：** source_exercise_identity、catalog_revision_id、mapping scope、ACCEPTED/UNRESOLVED/RETRACTED、policy/method、approval ref、supersedes、known/effective times。
- **约束：** DB：mapping family/revision 唯一、catalog FK。TX：当前采用映射经 factset 明确选择；模糊映射不直接进入 sequence/progression qualification。
- **索引：** subject/source_exercise/known_at；catalog_revision_id；supersedes_id。
- **唯一写入所有者：** ExerciseMappingService.DecideMapping。
- **映射：** INV-02, INV-05, INV-06, INV-16；T2, T3。

### S21 `projection_versions` — I

- **作用/字段：** projection_kind、engine artifact、input_basis_hash、window、typed result、quality/coverage、computed_at、validity boundary。
- **约束：** DB：subject/kind/engine/basis/window 的计算身份唯一或幂等；DOMAIN：Exposure 上下界与 unknown 分离，sequence 只由已准入 actual 计算。不得用 computation time 冒充输入 known time。
- **索引：** subject/kind/basis_hash；window end；engine version 反向影响查询。
- **唯一写入所有者：** ProjectionService.RecordResult；T3 准备阶段独立短事务，完成不更新 S01 generation。
- **映射：** INV-03, INV-04, INV-06, INV-07, INV-16；T3。

### S22 `projection_dependencies` — I

- **作用/字段：** projection_id、dependency_kind、明确 FK（factset/fact revision/mapping/catalog/program/policy）、collection predicate signature、collection revision/digest、query window。
- **约束：** DB：projection/dependency semantic key 唯一，闭合 target kinds 与对应 FK。DOMAIN：同时保留正依赖和 absence/集合依赖；不宣称列几个读取行就足以覆盖新增记录。
- **索引：** 各 dependency target 的反向索引；projection_id；kind/collection signature。
- **唯一写入所有者：** ProjectionService，与 S21 结果封存同事务。
- **映射：** INV-05, INV-06, INV-07, INV-16；T2, T3。

### S23 `manifest_builds` — B

- **作用/字段：** build_id、captured_factset/frontier/epoch/program/policy、candidate binding refs、BUILDING/READY/STALE/FAILED/PUBLISHED、error_code。
- **约束：** DB：build_id 唯一；完成的 candidate 内容不可在 READY 后偷偷改变。TX：PUBLISHED 只在生成 S24 的 T3 内发生；旧 epoch build 不能重贴 epoch。
- **索引：** subject/build status/created_at；captured input frontier。
- **唯一写入所有者：** DecisionPublicationService.Build / Publish。
- **映射：** INV-06, INV-07, INV-10, INV-17；T3。

### S24 `decision_manifests` — I

额外绑定 artifact_roots、dependency_closure_hash、registry_revision_at_publish；发布 guard 读取当前 registry，不能只保存历史 revision。

- **作用/字段：** build_id、generation、factset_id、input_frontier_hash、program/policy/catalog/mapping bindings、captured_epoch、source watermarks、local_date/calendar policy、valid_until、manifest_hash。 artifact_roots、artifact_dependency_closure_hash、registry_revision_at_publish。
- **约束：** DB：subject/generation 唯一、build_id 唯一、所有主体引用匹配、valid_until 晚于发布时间。TX：完整 basis、epoch、当前 Program/policy 复核后与 S01 pointer/generation 同事务提交。
- **索引：** subject/generation；subject/published_at；captured_epoch；factset_id。
- **唯一写入所有者：** DecisionPublicationService.PublishManifest。
- **映射：** INV-05, INV-06, INV-07, INV-09, INV-10, INV-16；T3, T6。

### S25 `manifest_projection_bindings` — I

- **作用/字段：** manifest_id、projection_role、projection_id 或显式 unavailable_reason、validated_basis_hash。
- **约束：** DB：manifest/role 唯一，projection 与 unavailable 二选一。TX/DOMAIN：必须角色齐全，basis 兼容；缺失不是零。与 Manifest 同事务封存。
- **索引：** manifest/role；projection_id 反向定位受影响历史。
- **唯一写入所有者：** DecisionPublicationService.PublishManifest。
- **映射：** INV-04, INV-05, INV-06, INV-07, INV-10；T3。

### S26 `decision_snapshots` — I

- **作用/字段：** attempt_id、manifest_id、request_revision_id、captured_epoch、mandatory context payload/hash、context-builder version、token accounting、source cutoff。
- **约束：** DB：attempt/snapshot sequence 唯一；引用同主体。DOMAIN：mandatory evidence 不被静默裁剪；命令权限与推断摘要类型固定。重建内容产生新 snapshot，不改原记录。
- **索引：** attempt_id；manifest_id；context_hash 仅作同主体缓存识别。
- **唯一写入所有者：** ContextService.RecordSnapshot；T4/T5 准备阶段受 attempt guard 保护。
- **映射：** INV-05, INV-10, INV-13, INV-15, INV-16；T4, T5, T6。

### S27 `planning_intents` — M

- **作用/字段：** purpose/date/calendar scope、root_request_id、status、current_request_revision_id、current_attempt_id、deadline、lease_owner/expires_at、fence_token、各维度 root limits/reserved/settled counters、stale_restart_count、result_bundle/auth refs。
- **约束：** DB：同主体/date/purpose 的 ADMITTED/RUNNING intent 唯一；root request 自然身份唯一；计数非负。TX：budget aggregate 原子占用，终态不可重开，request 更新不重置预算/deadline。
- **索引：** active partition 唯一索引；status/deadline；status/lease expiry 供 reaper 发现候选。
- **唯一写入所有者：** PlanningWorkflowService；late settlement 仅经限定账本入口更新核算字段，不复活 intent。
- **映射：** INV-10, INV-11, INV-12, INV-13, INV-17；T4, T5, T6, T8。

### S28 `planning_request_revisions` — I

- **作用/字段：** intent_id、revision、normalized constraints、constraint_fingerprint、calendar policy、command_receipt_id、origin actor/trigger。
- **约束：** DB：intent/revision 唯一；request_hash 与 canonical normalization version 绑定。TX：写新行与 S27 当前指针切换同 T4，旧 attempt 即刻失权。
- **索引：** intent/revision；intent/fingerprint（不要求永久唯一，因为用户可改回旧约束）。
- **唯一写入所有者：** PlanningWorkflowService.AdmitOrReviseIntent。
- **映射：** INV-10, INV-11, INV-13；T4, T6。

### S29 `planning_attempts` — M，执行元数据

- **作用/字段：** intent_id、attempt_no、request_revision_id、manifest/snapshot_id、captured_epoch、fence_token、status、model/prompt/tool/runtime artifact versions、failure_code、started/completed times。
- **约束：** DB：intent/attempt_no 唯一。TX：写入阶段校验 intent/request/fence/lease；terminal attempt 不恢复。proposal 正文单独存 S34，不能用 attempt 更新覆盖模型输出历史。
- **索引：** intent/attempt_no；status/updated_at；manifest_id。
- **唯一写入所有者：** PlanningWorkflowService.AdvanceAttempt；worker 仅调用命令。
- **映射：** INV-10, INV-11, INV-12, INV-13, INV-14, INV-17；T4, T5, T6, T8。

### S30 `planning_quota_buckets` — M

- **作用/字段：** subject、quota_kind、UTC window start/end、policy_version、admitted_count、limit。
- **约束：** DB：subject/kind/window/policy 唯一。TX：新 intent 与额度扣减同 T4；修改 request 不新扣 root 配额也不恢复原配额。
- **索引：** quota 唯一键；window_end 供保留策略。用户级配额不取代系统/provider 容量控制。
- **唯一写入所有者：** PlanningWorkflowService.AdmitIntent。
- **映射：** INV-11, INV-13；T4。

### S31 `call_reservations` — M，状态与核算投影

- **作用/字段：** intent/attempt_id、operation_slot、provider/model/config fingerprint、reserved amounts、price-accounting version、status、dispatch_owner/fence/permit_id、provider_request_id（可空）、actual_usage、settlement_revision。
- **约束：** DB：intent/attempt/operation_slot 唯一，reservation ID 唯一；状态 enum 闭合。TX：原子预留后才允许 DISPATCH_INTENT；只有 RESERVED 可取消退款；网络未知不能重置为 RESERVED。
- **索引：** intent/status；status/last_transition_at；provider/request_id（有可靠身份才唯一，不能以空值构造身份）。
- **唯一写入所有者：** CallLedgerService.Reserve / PermitDispatch / CancelUndispatched / Settle / MarkUnknown；业务字段修改受 PlanningWorkflow 协调。
- **映射：** INV-11, INV-12, INV-17；T5, T8。

### S32 `call_ledger_events` — I

- **作用/字段：** reservation_id、transition_revision、event_type、amount deltas、receipt/reconciliation source、dispatch permit identity、occurred/recorded times。
- **约束：** DB：reservation/transition_revision 唯一、可靠 settlement receipt 唯一。TX：与 S31 状态、S27 预算 counter 同事务；结算重复回执无双重扣减/释放。
- **索引：** reservation/revision；intent correlation；receipt identity。
- **唯一写入所有者：** CallLedgerService；旧 worker 仅能提交绑定 reservation 的证据给结算入口，不能任意设置 terminal/result。
- **映射：** INV-11, INV-12, INV-16；T5, T8。

### S33 `tool_evidence_records` — I

- **作用/字段：** attempt/snapshot_id、tool_name/version、arguments hash/payload、query scope/window、input revision refs、result hash/blob、coverage/truncation、trust_class、start/end times。
- **约束：** DB：attempt/tool_operation_slot 唯一或记录重试序号；scope 必须同主体。DOMAIN：结果能回溯固定 Manifest；live 输入未绑定则不准采用。
- **索引：** attempt/operation_slot；snapshot_id；result_hash 仅同主体。
- **唯一写入所有者：** ContextToolGateway.RecordResult；读取与记录属于 T5 工作阶段，不持用户锁等待远端。
- **映射：** INV-05, INV-10, INV-15, INV-16, INV-17；T5。

### S34 `proposal_revisions` — I

- **作用/字段：** proposal_family/revision、attempt/snapshot、kind=FITNESS/NUTRITION/BLUEPRINT、payload/hash、producer artifact、citations、parent proposal（修复）、fitness_proposal_id/hash 与 demand_feature_id/hash（Nutrition 必填）。
- **约束：** DB：family/revision 唯一、kind 与必填依赖一致、类型化 FK、same subject。DOMAIN：proposal 不含实际完成事实或批准权限；重新修复创建新 revision。
- **索引：** attempt/kind/revision；fitness_proposal_id；demand_feature_id。
- **唯一写入所有者：** ProposalService.RecordProposal；模型输出由服务器验证后记录，无 canonical write capability。
- **映射：** INV-01, INV-02, INV-13, INV-14, INV-15；T5, T6。

### S35 `prescription_demand_features` — I

- **作用/字段：** fitness_proposal_id/hash、method version、feature payload/hash、逐字段 semantic class、估计区间、window/basis。
- **约束：** DB：Fitness/method/basis 唯一；code-computed producer，不接受模型填充事实元数据。DOMAIN：PRESCRIBED_QUANTITY/TARGET/ESTIMATE 分离，不当作实际生理消耗。
- **索引：** fitness_proposal_id；content_hash。
- **唯一写入所有者：** DemandFeatureService.ComputeAndRecord；不推进 Manifest generation。
- **映射：** INV-01, INV-02, INV-07, INV-14；T5, T6。

### S36 `evidence_resolutions` — I

- **作用/字段：** manifest_id、action_type/parameters hash、exercise identity、resolver/policy version、support/contradiction/association refs、coverage、consistency、truncation、query basis hash、resolution expiry。
- **约束：** DB：动作与 manifest/policy 绑定。DOMAIN：权威 resolver 从政策范围计算，不由 Agent citations 构造。覆盖完整与无冲突是不同维度；结果 hash 相同不能证明适用于另一动作。
- **索引：** subject/manifest/action fingerprint；被影响 evidence revision 的可定位引用。
- **唯一写入所有者：** EvidenceResolver.ResolveActionEvidence；T6 准备阶段，最终提交复核 basis。
- **映射：** INV-02, INV-03, INV-04, INV-05, INV-09, INV-16；T6。

### S37 `validation_results` — I

- **作用/字段：** attempt、request_revision、manifest/epoch、proposal hashes、demand hash、resolver results、policy_bundle、execution_basis_event_id 及相关 execution/head 修订、PASS/FAIL/REVIEW、codes、valid_until、validator artifact。
- **约束：** DB：validation identity 唯一、明确目标 FK。DOMAIN：逐项验证/证据义务。TX：PASS certificate 只有全部 binding 仍匹配才可消费；不是 bearer authorization。
- **索引：** attempt/result；manifest_id；policy_bundle_id；失败码统计索引按实际查询决定。
- **唯一写入所有者：** ValidationService.RecordResult；最终 T6 提交命令不能省略 guard。
- **映射：** INV-02, INV-05, INV-09, INV-10, INV-13, INV-14；T6。

### S38 `daily_plan_heads` — M

- **作用/字段：** subject/local_date、calendar_policy、current_bundle_revision_id、head_revision、day lifecycle。
- **约束：** DB：subject/local_date 唯一。TX：唯一 active bundle 由此指针表达；旧 bundle 不覆写，切换与新处方/授权/intent success 同 T6；不能维护两个各自可写的 ACTIVE 真相。
- **索引：** 唯一 subject/local_date；current_bundle_revision_id。
- **唯一写入所有者：** PrescriptionCommitService.CommitBundle；取消/关闭同一 writer 由明确控制命令调用。
- **映射：** INV-09, INV-10, INV-13, INV-14；T2, T6, T7。

### S39 `daily_bundle_revisions` — I

- **作用/字段：** day scope、revision_no、parent_revision_id、intent/attempt/manifest、commit_receipt_id、generation_mode、content_hash、validation_result_id。
- **约束：** DB：subject/date/revision 唯一、commit receipt 唯一。TX：内容、成员、授权全部成功才切换 head。REUSED_VALID_PLAN 可返回现有 bundle 而不制造无内容变化的 revision。
- **索引：** subject/date/revision；intent_id；manifest_id。
- **唯一写入所有者：** PrescriptionCommitService.CommitBundle。
- **映射：** INV-09, INV-10, INV-13, INV-14, INV-16；T6。

### S40 `prescription_revisions` — I

- **作用/字段：** prescription_identity/revision、kind=TRAINING/NUTRITION、typed content、source proposal/fallback template、content_hash、hash_scheme_version。
- **约束：** DB：subject/prescription/revision 唯一、kind 与 typed payload 一致。DOMAIN：已验证内容；不存可写 authorization_status。相同内容重新授权不强制创建新处方。
- **索引：** identity/revision；subject/content_hash（不跨用户复用身份）。
- **唯一写入所有者：** PrescriptionCommitService；draft/proposal 留在 S34，不把未验证流式片段放入 executable registry。
- **映射：** INV-01, INV-02, INV-09, INV-14, INV-16；T6。

### S41 `bundle_prescription_members` — I

- **作用/字段：** bundle_revision_id、prescription_revision_id、kind、session_slot、order。
- **约束：** DB：bundle/kind/slot 唯一、kind 与处方复合引用一致。V1 TRAINING 只允许单个明确 slot，NUTRITION 只允许一个 daily slot；以关系唯一性与 allowed-slot 检查表达，不仅在 UI 限制 count。
- **索引：** bundle/kind；prescription_revision_id。
- **唯一写入所有者：** PrescriptionCommitService，与 S39/S40 同 T6。
- **映射：** INV-09, INV-14；T6, T7。

### S42 `authorization_issuances` — I

额外绑定 artifact closure、registry_revision_at_issue、validity_certificate（每项依赖身份/修订/期限或批准的 TIMELESS、计算版本、摘要）。valid_until 是闭包最早到期，不能晚于任一关键依赖。不可原地延长。

- **作用/字段：** prescription_revision_id/bound_hash、manifest/epoch、policy、validation_result_id、scope、valid_from/until、issuance_reason、issuing_command_id。 artifact_dependency_closure、registry_revision_at_issue、validity_certificate（依赖 identity/revision/validity、计算版本与 closure digest）。
- **约束：** DB：issuance id 唯一、command/处方/scope 唯一、处方与 hash 绑定、有效期行内检查。TX：完整最新签发 guard。A1 与 A2 可绑定同一 P；禁止更新旧 A 的有效期或“恢复”历史。
- **索引：** subject/prescription/scope/issued_at；subject/epoch；valid_until 仅筛选候选。
- **唯一写入所有者：** AuthorizationService.Issue，必须被 T6 CommitBundle/Reauthorize 命令原子调用，不能开放通用 INSERT API。
- **映射：** INV-02, INV-08, INV-09, INV-10, INV-16；T6, T7。

### S43 `authorization_events` — I

- **作用/字段：** authorization_id（定向事件）或 invalidated_epoch/scope（用户屏障事件）、event_kind、cause_control/admission/command、recorded time。
- **约束：** DB：事件 target 类型闭合且互斥、幂等因果键。TX：屏障变更和 S01 epoch 同事务；定向 suspension/revocation 经同一协调锁。禁止 RESTORE_VALID 事件。
- **索引：** subject/authorization_id/event time；subject/invalidated_epoch；cause id。
- **唯一写入所有者：** AuthorizationService.Invalidate，受 T2 control/admission 命令调用。
- **映射：** INV-08, INV-09, INV-10, INV-16；T2, T6, T7。

### S44 `workout_sessions` — M，实际会话身份与生命周期

- **作用/字段：** session_id、underlying_event_id、origin=APP_STARTED/EXTERNAL_REPORTED、lifecycle、start/completion times、latest_actual_fact_revision_id、execution_revision。
- **约束：** DB：subject/session 唯一；当前确认关联的 event/session 身份不得重复。TX：START 受 T7 guard；外部实际训练由 T2 接受，无授权也可保存。实际 set/bout 修订在 S14，不覆写原事实。
- **索引：** subject/start time；underlying_event_id；subject/in-progress state。
- **唯一写入所有者：** ExecutionService，通过 Start/Resume 或 AcceptExternalExecution 调用；identity correction 保留 alias/association 历史，不删除旧实体。
- **映射：** INV-01, INV-03, INV-09, INV-16, INV-18；T2, T7。

### S45 `execution_bindings` — I

- **作用/字段：** session_id、binding_revision、kind=START/RESUME、prescription_revision_id、authorization_id、accepted_at、command_receipt_id、execution_scope。
- **约束：** DB：session/binding_revision 唯一、START 每 session 最多一条、P/A 主体与内容关联匹配。TX：当前资格通过才写；外部训练无有效 A 时不伪造 binding，S44.origin 表达其来源。
- **索引：** session/binding_revision；authorization_id；prescription_revision_id。
- **唯一写入所有者：** ExecutionService.StartSession / ResumeSession。停止与完成事件保存在 S03，原绑定不被更新为新 A。
- **映射：** INV-09, INV-10, INV-16, INV-18；T7。

### S46 `replay_runs` — M，隔离 evaluation 存储

- **作用/字段：** replay_mode、knowledge_cutoff、release_bundle_id、historical_manifest_id、evaluation_subject、status、input selection hash、randomness/available-model limitations。
- **约束：** DB：run_id 唯一；有显式 mode/cutoff；无可写 production FK target。DOMAIN：cutoff tool policy 全链路一致；权限角色不可写 live 命令。
- **索引：** release/mode/cutoff；status。
- **唯一写入所有者：** ReplayService；不是 T6 生产提交路径。
- **映射：** INV-15, INV-16, INV-17；T1–T8 的只读历史重建，不加入 live 事务。

### S47 `replay_artifacts` — I，隔离 evaluation 存储

- **作用/字段：** replay_run_id、artifact_kind、input/derived/output payload/hash、source revision refs、included/excluded reasons、leakage audit、simulation marker。
- **约束：** DB：run/artifact identity 唯一。DOMAIN：区分 RECORDED_OUTPUT 与 FRESH_MODEL_RUN；artifact 缺失返回明确错误。模拟 authorization 不进入 S42。
- **索引：** run/kind；source reference 仅用于获准的历史读取。
- **唯一写入所有者：** ReplayService.RecordArtifact。
- **映射：** INV-02, INV-15, INV-16；T1–T8 的只读历史重建，不加入 live 事务。

### S48 `evaluation_releases` — I

- **作用/字段：** release_id、model/prompt/engine/policy artifact bundle、dataset/split ids、freeze times、metrics/threshold config、evaluation report refs、rollout decision provenance。
- **约束：** DB：release identity 唯一。DOMAIN：评测报告与用于生产的制品精确绑定；若无实测结果，不可声明 PASSED。修改阈值或模型产生新 release。
- **索引：** release id；artifact hashes；recorded_at。
- **唯一写入所有者：** ReleaseEvaluationService.RecordRelease；生产选择此 release/policy 仍经 T2 用户激活入口。
- **映射：** INV-02, INV-09, INV-15, INV-16；T2（激活绑定）；evaluation 独立运行。

### S49 `safety_artifacts` — I（全局 namespace）

- **作用/字段：** artifact_id、artifact_kind、content_hash、declared_dependency_ids、validity_spec、TIMELESS approval policy/reason（如适用）、registered_at、registrar_identity。与 S05/S19/S48 中制品有确切身份绑定。
- **约束：** DB：kind/content identity 唯一；identity 不可复用。DOMAIN：依赖为已注册 identity，无环、完整且有界；未知/缺失 validity 不具准入资格。依赖引用不得藏于自然语言；DDL 可规范化为 child edges，不改变逻辑含义。
- **索引：** artifact_id；kind/content_hash；dependency identity 反向检索（审计/影响分析，不要求逐用户撤销）。
- **唯一写入所有者：** SafetyRegistry.RegisterArtifact（独立管理命令）；禁止普通 Agent/user writer 注册或修改。新注册与 T3/T6/T7 的可见性通过 registry gate 协调。
- **映射：** INV-02, INV-08, INV-09, INV-10, INV-16；T2（GLOBAL）, T3, T6, T7。

### S50 `artifact_revocation_events` — I（全局 namespace）

- **作用/字段：** revocation_id、artifact_id、registry_revision、effective_at、recorded_at、reason_code、operator/capability identity、command_key/request_hash、causation incident、outbox delivery identity。`recorded_at`/commit time 是 V1 的执行失效线性化时间；`effective_at` 仅用于业务/事故/审计语义，不具有追溯或未来调度授权效果。
- **约束：** DB：command identity 唯一、artifact 引用 S49。TX：T2-GLOBAL 追加与 S51 revision/receipt 原子；**成功提交是全局撤销执行线性化点**。`effective_at` 不得回填改变过去授权事实，也不得在 V1 充当 scheduled revoke；撤销只能收缩，不恢复旧 identity。重复同 key/hash 返回原结果，不同 hash 拒绝。
- **索引：** artifact_id（存在已提交撤销即 deny）；registry_revision（同步/audit）；operator/recorded_at。
- **唯一写入所有者：** SafetyRegistry.RevokeArtifact，独立 emergency capability；不调用模型、不取用户 S01、不逐用户写 S43。全局 receipt/event 放在此管理 namespace，不伪造 subject_id。
- **映射：** INV-02, INV-08, INV-09, INV-10, INV-16；T2（GLOBAL）, T3, T6, T7。

### S51 `safety_registry_state` — M（全局协调点）

- **作用/字段：** registry_scope（V1 单一 system scope）、registry_revision、last_revocation_id；共享/排他 gate 的逻辑协调身份。
- **约束：** DB：scope 唯一。TX：管理变更取排他 gate；T3/T6/T7 取共享 gate并读取取得 gate 后已提交的撤销；revision 与 S50 原子更新。不要求 A.captured_revision 等于当前值，不因无关撤销失权。
- **索引：** registry_scope 主键；禁止每次准入更新同一全局计数器。
- **唯一写入所有者：** SafetyRegistry 管理入口；用户 STOP / 输入接收 / reaper 不依赖此 gate。审计查询缓存不授予执行资格。
- **映射：** INV-08, INV-09, INV-10, INV-17；T2（GLOBAL）, T3, T6, T7。

## 3. 唯一 command/write entrypoint、幂等与错误

下表的 owner 是唯一逻辑写入服务，不要求变成独立微服务。内部 helper 不得绕过该入口的 actor/subject/guard。所有 prep-result 写入是独立短事务，T 编号表示所属协议阶段，绝不意味着从准备开始一直保持事务。

| Command | Owner / transaction | 幂等身份 | 必须拒绝的典型错误 |
|---|---|---|---|
| ReceiveEvidence | EvidenceService / T1 | source object + reliable revision，或 adapter observation key | SOURCE_IDENTITY_CONFLICT、SUBJECT_MISMATCH |
| RecordCandidate | ExtractionService / T1 后准备阶段 | evidence revision + extractor version + extraction operation | PROVENANCE_MISSING、ASSERTION_SCHEMA_INVALID |
| DecideAssociation / DecideAdmission / AcceptFactRevision | 对应 S12/S13/S14 writer；CanonicalInputCoordinator 原子编排 T2 | command key + expected current input/basis + payload hash | BASIS_STALE、ADMISSION_CONFLICT、EVENT_ASSOCIATION_AMBIGUOUS |
| ApplyControl / ClearControl | ControlService / T2 | explicit command key；自动 hold 用 risk evidence + policy + scope | COMMAND_NOT_AUTHORIZED、CLEARANCE_INSUFFICIENT |
| ApproveChange / ActivateApprovedProgram | ApprovalService / ProgramService / T2 | approval command；activation bound approval + exact proposal revision | APPROVAL_STALE、APPROVAL_CONTENT_MISMATCH、POLICY_DISABLED |
| RecordProjection / BuildManifest | ProjectionService / PublicationService / T3 准备阶段 | type + engine + exact basis；build key | DEPENDENCY_UNAVAILABLE、BASIS_INCOMPATIBLE |
| PublishManifest | DecisionPublicationService / T3 | build_id（自然唯一）+ command key | BUILD_STALE、EPOCH_MISMATCH、POLICY_MISMATCH |
| AdmitOrReviseIntent | PlanningWorkflowService / T4 | client request key，不以 date/purpose 替代 | QUOTA_EXHAUSTED、INTENT_TERMINAL、REQUEST_CONFLICT |
| AcquireLease / RenewLease | PlanningWorkflowService / T5 | lease-operation key + expected owner/fence | LEASE_LOST、DEADLINE_EXCEEDED |
| ReserveCall / PermitDispatch | CallLedgerService / T5 | intent + attempt + operation slot；permit key | BUDGET_EXHAUSTED、FENCE_MISMATCH、DISPATCH_ALREADY_POSSIBLE |
| RecordToolResult / RecordProposal / RecordDemandFeatures | S33/S34/S35 writer / T5 准备阶段 | attempt operation slot + artifact version | SNAPSHOT_STALE、DEPENDENCY_HASH_MISMATCH |
| ResolveEvidence / RecordValidation | S36/S37 writer / T6 准备阶段 | action/manifest/policy/basis fingerprint | EVIDENCE_INSUFFICIENT、COVERAGE_INCOMPLETE、POLICY_UNCONFIGURED |
| CommitBundle / Reauthorize | PrescriptionCommitService + AuthorizationService / T6 | commit command key + intent/result fingerprint | REQUEST_STALE、FENCE_MISMATCH、EPOCH_MISMATCH、HOLD_ACTIVE、AUTH_SCOPE_DENIED |
| StartSession / ResumeSession | ExecutionService / T7 | authenticated command key + session ID + binding revision | AUTH_EXPIRED、AUTH_REVOKED、CONTENT_MISMATCH、EXECUTION_CONFLICT |
| RecordActualExecution / CompleteReportedWorkout | CanonicalFactService + ExecutionService / T2 | source observation / actual report key | SOURCE_IDENTITY_CONFLICT；不能因无授权而拒收事实 |
| CancelIntent | PlanningWorkflowService / T4 或 T8 | cancel command key + intent ID | 已完成则返回已完成事实，不伪造撤销旧成功 |
| SettleCall / MarkUnknown / ReapIntent | CallLedgerService / WorkflowService / T8 | provider receipt；reservation + expected transition；intent + expected fence/deadline | SETTLEMENT_CONFLICT、STALE_REAPER_CANDIDATE |
| RunReplay / RecordRelease | ReplayService / ReleaseEvaluationService | mode/cutoff/release/input-run key | KNOWLEDGE_BOUNDARY_VIOLATION、ARTIFACT_UNAVAILABLE |

**共同错误：** IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD、SUBJECT_MISMATCH、INVALID_TRANSITION、CONFIG_UNAVAILABLE。错误码不允许直接暴露其他主体对象是否存在。

**错误重试：** timeout/deadlock/serialization retry 是基础设施失败，可在 deadline 与有限次数内重试整个短事务并重读 guard；guard rejection 不是数据库重试。STALE 只能由 workflow 明确产生新 attempt，消耗原预算。不存在“所有 409 都重试”的统一策略。

**幂等 replay：** 同 key 同 payload 重复命令返回原结果身份及 `replayed=true`。历史上 START 成功不表示现在仍可继续执行，响应另外计算当前 authorization eligibility。客户端不能把重放旧成功当作新一次许可。

**发送许可特殊规则：** 只有成功把 RESERVED 变成 DISPATCH_INTENT 的首次 transition winner 可执行那一次网络调用。PermitDispatch 的幂等重复结果只能用于查账，必须标记不可再次发送；不得因拿到同一 permit 响应又调用 provider。

**receipt 保留：** 对收到确认的持久业务命令，使用自然唯一键（build_id、commit identity、session binding、source revision）作为第二道防重放；清理 receipts 不清理这些约束。无法保留自然身份的命令，保留不可重放 tombstone 或显式关闭已过期 key namespace。未知 request key 不自动等于合法新授权。

**Reauthorize：** 使用新的、已准入的 planning/revalidation intent；可不调用模型，但仍满足 T6 的 current attempt/manifest/epoch/deadline guard。不能重新打开原终态 intent，也不能绕过 hold 或最新 Manifest。

## 4. 固定锁序与读写边界

### 4.1 V1 锁序

```text
registry gate S51（仅 T3/T6/T7，共享；全局管理独占且不取 S01）
  → subject coordination row S01
  → relevant user quota buckets S30（稳定 key 排序）
  → planning intent S27（如多个，按稳定 ID 排序）
  → reservations S31（按稳定 ID 排序）
  → daily head S38
  → execution aggregate S44
  → exact command receipt / remaining aggregate rows
```

事务只取实际需要的锁，但不能逆序。所有 unique-key 竞争也在这一协议下处理；特别是不得先抢 receipt 的唯一键再等待另一个事务已持有的 S01。T1 原始接收仅处理来源幂等且不再反向取得 S01；需要紧急 hold 时由另一个 T2 事务处理。

用户安全入口应在 raw evidence 可用后立即执行 T2。若产品要求“风险提交成功”意味着 hold 已生效，则 API 必须等 T2 成功再确认该语义；T1 成功只能表示已收件，不能宣称安全措施已落实。

同用户锁仅覆盖毫秒级目标的短事务；这里是性能目标而非已测 SLA。不得在其中进行模型调用、外部文件获取、完整历史 resolver、投影计算或大范围重建。

PostgreSQL 行锁与事务结束相关，死锁仍可能发生；固定顺序降低交叉持锁风险，数据库中止后必须重试完整事务而非沿用旧 guard。[PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)

没有 registry 依赖的事务直接从 S01 开始，且不能再反向申请 S51。Factset build 事务只锁 build，不锁 S01；T2-SEAL 按 S01→build 获取，READY 内容已固定，不扫描 member。全局 registry 控制不使用用户 subject receipt；S50 带管理命令幂等身份。

全局 revoke 与 publish/issue/START 的通过/拒绝以受 gate 保护的原子提交顺序为准；锁前缓存/快照无效。物理 SQL 必须确保取得 gate 后的读取看见先前已提交撤销。registry 不可读或 gate 超时则 deny；用户 STOP 继续走独立 S01 通道。

### 4.2 队列与 reaper

扫描 lease/deadline/outbox 索引只用于发现候选。reaper 不应持住 intent 行再反向申请 S01；先无锁读取候选 ID，随后按统一顺序锁住并重检 fence/status/deadline。过时扫描结果返回 STALE_REAPER_CANDIDATE。

OutboxDispatcher 在自己的 claim/delivery 事务中不能获取业务 S01。业务消费者调用新幂等命令，不携带 outbox 行锁跨入业务写入。队列可重复，业务结果不得重复。

### 4.3 时间、快照与副本

时间 guard 在获得协调锁后读取可信数据库/服务端时间，不能使用在排队前保存的时间证明 lease 尚有效。guard acceptance time 记录到事件；响应发出时若授权已过期，仍需明确不可执行，不把历史成功缓存成当前许可。

历史/工具读取可使用短一致事务取得 input revisions 与数据，或直接读取不可变引用；长时间推理不持 MVCC snapshot。只读副本可用于允许陈旧的展示，但 epoch/fence/START/commit 的权威 guard 必须读取主协调存储。

## 5. T1–T8 事务落点

| Tx | 必须原子完成的读写 | 提交前 guard | 显式排除 |
|---|---|---|---|
| T1 | S09 raw evidence + S02 receipt + S03/S04 接收事件；解析候选另开短事务写 S10 | subject/source idempotency、内容身份冲突 | 不接受未解析候选为训练成功；不重算特征 |
| T2 | IN：S12/S13/S14 或 S17/S18 + S01 frontier/epoch/basis + S43/events/receipt；SEAL：S15 READY→SEALED + S01 factset head/events/receipt；GLOBAL：S50 + S51 revision/管理 receipt；三者是独立原子命令 | IN：输入/actor/失效分类；SEAL：captured frontier/epoch/member revision/完成凭据；GLOBAL：管理 capability/identity + exclusive registry gate | 不把 IN 与 SEAL 假装跨构建原子；不在 S01 锁内批量写 S16；不逐用户 revoke |
| T3 | READY S23 guard；S24/S25 + S01 generation/current pointer + S23 published + S03/S04/S02 | sealed factset/input frontier、所有 dependency basis、当前 program/policy/epoch、validity、shared registry/current artifact eligibility | 不在事务内算 projection；不发布混合结果 |
| T4 | S30 准入配额、S27 intent、S28 request revision、S29 初始/失效状态、S02/S03/S04 | single-flight partition、request fingerprint、root admission limits | 不因改约束重置预算/deadline |
| T5 | lease/fence 变更；或 S31 reservation + S32 ledger + S27 counters；或 dispatch permit transition；均为独立短事务 | intent live、request revision、owner/fence/lease/deadline、预算余量 | 网络请求发生在 DISPATCH_INTENT 持久化之后、事务之外 |
| T6 | S39/S40/S41、S42、S38 head switch、S27 result/success、S29 committed、S02/S03/S04 | current snapshot/generation/epoch/request/fence/lease、policy、validation bindings、当前执行暴露、scope 和 active bundle、shared registry/current artifact eligibility、依赖有效期闭包 | 不靠 schema valid / validation PASS 单独放行；不先提交 bundle 再异步签授权 |
| T7 | S44 execution + S45 START/RESUME binding + S02/S03/S04 | 当前 A/P/content/scope、依赖有效期、epoch/holds、shared registry/current artifact eligibility、session lifecycle、重复 start | 不需要在线 LLM；不改历史 START 绑定 |
| T8 | S31/S32 与 S27 核算；或 reaper 对 S27/S29 的失权/终态；S02/S03/S04 | receipt identity、当前 reservation transition；或当前 fence/lease/deadline | 不恢复 unknown 预算；不让迟到响应恢复提交权限 |

T2-IN 保证 admission/correction 与必要失效同事务。T2-SEAL 是后续独立原子封存，不与输入事务捆绑。T2-GLOBAL 是全局管理事务。IN 后 SEAL 前旧 current_factset 允许保留供历史读取，但 T3 必须拒绝其落后 frontier；用户风险即时失效不等封存。

T6 的预算 guard 检查未超额、intent 未终止、deadline 未过；不要求必须还有剩余模型额度。恰好用完预算后得到有效结果仍可提交。只有需要继续搜索但没有预算，才进入 SEARCH_BUDGET_EXHAUSTED。

累计 exposure 验证结果同时绑定 S01.execution_basis_event_id。另一个 T6 计划提交、T7 START/RESUME/停止或 T2 实际执行更正使依据改变时，旧 validation 必须重新计算，不能因 Manifest/epoch 未变就复用。状态改变、对应 S03 事件与该指针在同一事务提交；本次 T6 先检查旧依据，提交新计划后推进该指针。这样避免两份各自通过、合起来超出 envelope 的并发提案。

### 5.1 四组强制交错

| 竞争 | 顺序 A | 顺序 B | 不允许的状态 |
|---|---|---|---|
| Publish vs Revoke | Publish 先提交 G，随后 revoke 推 epoch；G 不再可新签发 | Revoke 先提交，旧 build 的 epoch guard 失败 | 新 epoch 配旧内容的重贴标签 Manifest |
| START vs Revoke | START 先提交，保留 P/A 开始绑定；后续继续资格失效 | Revoke 先提交，START 返回 AUTH_REVOKED/EPOCH_MISMATCH | 已提交 revoke 后靠旧缓存成功 START |
| Cancel vs DISPATCH_INTENT | Cancel 先完成 RESERVED→CANCELLED，PermitDispatch 失败 | Dispatch permit 先完成，Cancel 结束 intent 但预留保留且远端可能继续 | 既释放预算又获得发送许可 |
| Lease takeover vs Commit | Commit 在 lease 有效时先成功；reaper 重检成功状态，不接管/改失败 | Takeover 先成功或 lease 已过；旧 fence commit 失败 | 旧 worker 晚返回覆盖新 worker 或复活终态 |

故障注入还需覆盖 COMMIT ACK 丢失、DISPATCH_INTENT 后尚未网络调用、网络调用后尚未写 DISPATCHED、写结算前进程退出。命令边界故障已有模型对应案例，实际进程/网络/数据库故障仍待执行；不视为真实并发证明。

## 6. 18 条 invariant 的强制位置

| Invariant | 主表落点 | 强制方式 | 验收证据 |
|---|---|---|---|
| INV-01 | S09,S10,S13,S14,S34,S35,S40,S44 | 事实/处方类型分离；准入禁止计划补全实际 | E01,A08 |
| INV-02 | S08,S10,S13,S17,S34,S36,S37,S42 | command capability 与模型输出隔离；唯一 writer | E08,E06 |
| INV-03 | S11,S12,S14,S16,S21 | underlying event identity + association policy + projection dedup | E03,E04 |
| INV-04 | S13,S14,S21,S25,S36 | 上下界/未知类型与 action-scoped admission | E05,E02 |
| INV-05 | S16,S22,S26,S33,S36,S37 | action-driven resolver + completeness/basis binding | E06,D03,D04 |
| INV-06 | S15,S16,S21,S22,S24,S25 | revision dependencies + collection/absence signatures | D02,D04 |
| INV-07 | S01,S21,S23,S24,S25 | generation 唯一 writer T3 + 原子发布 | D01,D05 |
| INV-08 | S01,S17,S18,S43,S49,S50,S51 | T2-IN/GLOBAL 独立同步屏障，不逐行等待旧 authorization 更新 | A01,A07,E02 |
| INV-09 | S37,S38,S40,S42,S43,S45,S49,S50,S51 | 内容/有效期闭包 + epoch/registry runtime guard + transaction | A03,A04,A05,A06 |
| INV-10 | S01,S24,S27,S28,S29,S42,S49,S50,S51 | epoch/request/fence/current manifest/current artifact 联合 guard | A02,D05,W05,W06 |
| INV-11 | S27,S30,S31,S32 | ledger + root counter 原子占用，SDK 物理调用全覆盖 | W01,W02,W03,W04 |
| INV-12 | S27,S31,S32 | UNKNOWN 占用与晚到结算权限隔离 | W01,W05,W06,W08 |
| INV-13 | S27,S28,S29,S37 | request revision 不可变、旧 attempt 提交失败 | W04 |
| INV-14 | S34,S35,S37,S39,S41 | 类型化依赖与 content hash 校验 | W07 |
| INV-15 | S09,S10,S26,S33,S34,S47 | summary 固定非命令；命令仅可来自专用入口 | E08,R04 |
| INV-16 | S09,S12,S13,S14,S20,S24,S42,S46,S47,S48 | 双时间/不可变版本 + cutoff-aware reads + eval 隔离 | R01,R02,R03,R04 |
| INV-17 | S01,S23,S27,S29,S31,S33 | 短事务；准备结果外算；dispatch 外部网络在事务外 | W01,W05,A07 + lock-duration instrumentation |
| INV-18 | S09,S14,S44,S45 | 外部 actual 不要求授权；缺绑定不能伪造 | A08,E01 |

仅“存在表/索引”不能证明 invariant 成立。所有 DOMAIN 判断必须有 fixture，所有 TX 判断必须在真实数据库的竞争与故障条件下验证。

## 7. 34 项验收的 Given / When / Then 与测试层级

PU = protocol unit/state-model；DC = 真 PostgreSQL 多事务并发；WF = worker/process fault injection；E2E = API→workflow→DB→UI eligibility。以下为 fixture 设计，不是可执行实现，也不是通过报告。

| ID | Given | When | Then | 层级 | 主表 |
|---|---|---|---|---|---|
| E01 | 处方 3 组，原文只完成 1 组 | 解析/准入/进阶 | 只有有证据的 actual，额外组不计完成 | PU,E2E | S10,S13,S14 |
| E02 | 风险通道收到尚未解析文本 | 解析不可用 | 适用 pending hold 生效，进阶被阻断 | PU,WF,E2E | S17,S18,S43 |
| E03 | 三来源指向一次训练 | 关联与 projection | 独立事件数 1，三来源仍留存 | PU,DC | S11,S12,S21 |
| E04 | 相近训练是否重复不明确 | reconciliation | 保留歧义，不强制合并/双计成功 | PU | S12,S36 |
| E05 | 完成量下界确定，上界未知 | 计算 exposure | 上界 unknown，不取计划值或零 | PU | S14,S21 |
| E06 | 成功后有反证，Agent 只引成功 | 解析加重义务 | Resolver 包含反证并按完整范围判断 | PU,E2E | S36,S37 |
| E07 | 原事实已用于授权 | 新更正撤回依据 | admission/epoch/投影资格变化原子生效 | DC,E2E | S13,S15,S01,S43 |
| E08 | 备注夹带批准指令，经多轮摘要 | context 与批准入口 | 保持非命令，不能产生 approval | PU,E2E | S10,S26,S08 |
| D01 | projection ready，Manifest 未发布 | 写计算结果 | generation 不变 | PU,DC | S21,S01 |
| D02 | 无关输入变化，进阶依赖未变 | BuildManifest | 复用原投影且 basis 验证通过 | PU | S22,S25 |
| D03 | 接受新输入但未发新 Manifest | tool live query | 不混入未绑定修订 | DC,E2E | S15,S24,S33 |
| D04 | 原查询不存在限制/相关事件 | 并发插入新记录 | 集合依赖或 epoch 捕捉变化 | DC | S22,S17,S01 |
| D05 | 旧 epoch 的 READY build | revoke 与 publish 交错 | 只允许 §5.1 两种合法结果 | PU,DC | S23,S24,S01 |
| A01 | 活跃计划可执行，模型服务故障 | revoke | 旧 A 立即失权，无需替代计划 | DC,WF,E2E | S01,S43 |
| A02 | epoch 已增加，Manifest 仍旧 | 重新签发相同 P | 旧 Manifest 签发失败 | PU,DC | S24,S42 |
| A03 | 有效 P/A，尚未 START | START/revoke 竞争 | 按提交顺序；无晚越权 START | PU,DC | S01,S43,S45 |
| A04 | 缓存仍标 VALID，实际已过期 | Start/eligibility | AUTH_EXPIRED，与后台 job 无关 | PU,E2E | S42,S45 |
| A05 | P7 已通过 A1 开始 | 签 A2 并 RESUME | 原 START 保留 A1，新 binding 引 A2 | PU,DC | S42,S45 |
| A06 | hold 有效，模型不可用 | fallback 选择 | 同样受限，无适用项则 UNAVAILABLE | PU,E2E | S05,S18,S42 |
| A07 | 普通规划队列和预算耗尽 | STOP 请求 | 独立容量处理撤销 | WF,E2E | S17,S01,S43 |
| A08 | 用户在无有效 A 时实际训练 | ingest actual | 保存事实，无虚构 execution binding | PU,E2E | S14,S44,S45 |
| W01 | 已 RESERVED 或 DISPATCH_INTENT | 各边界 kill worker | 仅许可前可退款，可能发送后 UNKNOWN 占用 | PU,WF | S27,S31,S32 |
| W02 | RESERVED，有取消与发送请求 | 两事务交错 | 取消释放与发送许可不能同时成立 | PU,DC | S31,S32,S27 |
| W03 | provider 返回 transient error | SDK/runtime retry | 每次物理请求有独立预算覆盖 | WF,E2E | S31,S32 |
| W04 | rev1=70min/full gym 正在运行 | rev2=20min/no equipment | rev1 失权，根预算/deadline 未重置 | PU,DC,E2E | S27,S28,S29 |
| W05 | token7 worker 暂停，lease 到期 | token8 接管，7 晚提交 | 7 不可提交；可信回执仅可结算 | PU,DC,WF | S27,S29,S32,S42 |
| W06 | intent 已取消或 deadline 结束 | 模型晚返回 | 不复活 intent/attempt，不新签 A | PU,WF | S27,S29,S42 |
| W07 | F1/D1/N1 已存在 | 修复出 F2 | D1/N1 不能用于 F2，重算计原预算 | PU,E2E | S34,S35,S37 |
| W08 | T6 已成功 commit | ACK 丢失后重发 | 返回相同 result/issuance，不重复写 | DC,WF,E2E | S02,S39,S42 |
| W09 | 两次搜索失败，无形式冲突证明 | workflow 结束 | 非 PROVEN_CONSTRAINT_CONFLICT | PU | S27,S37 |
| R01 | 九月更正八月事实 | cutoff=八月 replay | 排除九月获知修订 | PU,E2E | S14,S46,S47 |
| R02 | 相同 cutoff，历史/当前 release 不同 | 两模式 replay | 分别绑定指定 artifact bundle | PU | S46,S48 |
| R03 | 九月人工建立个体映射 | 八月 current backtest | 不导入未来个体知识 | PU,E2E | S20,S46,S47 |
| R04 | replay 产生模拟有效结果 | 尝试生产提交 | 角色/存储隔离拒绝，无 live issuance | DC,E2E | S46,S47,S42 |

四组交错 PU 可在 DDL 前用内存状态模型穷举；DC/WF 必须在后续实际数据库/worker 上运行。内存测试通过不能替代 PostgreSQL 行锁、唯一性冲突与进程故障验证。

## 8. V1 最小安全配置与存储成本边界

### 8.1 配置起点：`v1-local-shadow-deny-by-default`

这是可实现的默认配置定义，不是已经安装到服务的配置；不声称它可以提供自动处方。

| 配置 | 初始值/语义 | 放开条件 |
|---|---|---|
| 模式 | LOCAL_SHADOW；production issuance disabled | 协议与 auto-activation gate 通过 |
| Evidence 接收 | 可保存；来源明确；不默认获准 progression/sequence/nutrition | 对应用途 admission policy 已审核 |
| 进阶/序列/营养调整 | 未配置义务或 envelope 时 DENY，不猜默认值 | scope policy + resolver + fixtures 完成 |
| Durable auto approval | DISABLED；显式用户确认专用入口 | 独立 change-class policy 与 P1 release evidence |
| Protective controls | 专用 STOP/risk入口；pending hold 不自动过期解除 | 明确 clearance policy 才可解除 |
| Fallback catalog | 空；无适用项为 UNAVAILABLE | 每个模板具有完整 applicability/prohibited predicates |
| Offline START | DISABLED | 定义离线授权窗口、失效风险与产品策略后另行放开 |
| 模型/工具预算 | 缺任一必需限制则不启动；测试值由 fixture 显式给定 | 由评测/成本决定数值并发布完整 policy bundle |
| Replay | 可读获准历史、只写隔离 evaluation | 无生产写权限升级路径 |

测试 fixture 可以使用人工测试授权政策进入 T6/T7 的模拟环境，必须明确 test-only，并且不能误装为生产发行配置。静态配置存在不代表“缺配置时禁用”的运行代码已经验证。

### 8.2 Factset 与快照规模

S15/S16 采用 FULL checkpoint + DELTA 的有界链：DELTA 只记录 logical member 的 SET/REMOVE；解析按固定顺序覆盖至最近 FULL。policy 配置最大链深度，超限则构建新 FULL；未封存的链不发布。删除成员不删除历史事实。

Factset 不只包含成功准入事实，还要保留 resolver 所需的 UNRESOLVED/反证/admission 决策，否则会在物化阶段提前 cherry-pick。当前使用资格是各 scope 的决定，不是把所有未成功 evidence 从历史删除。

封存摘要对重建后的集合内容计算，重建/压缩发生在事务外；CompleteFactset 关闭写入并固定结果，T2-SEAL/T3 只核对 captured frontier 和完成结果，不再全量算 hash。规模过大时采用不可变成员块/分区属于物理优化，必须保持原子封存、cutoff 与 FK/完整性验证，不能先切 current pointer 再补成员。

Mandatory context 是有界的结构化摘要；完整 provider payload 与工具原始大结果用 blob ref，不在每个 snapshot 复制终身历史。后续深查仍绑定不可变修订/knowledge boundary。

### 8.3 查询与容量

- 当前授权查询读取 S01、S18、S42/S43、S49/S50/S51 与 session/head；制品闭包有界，撤销按 artifact identity 查询。S18 是同步维护、可验证的投影。全局共享 gate 的尾延迟与撤销优先待压测。
- revoke 用 epoch 屏障使旧签发失权，不在安全事务里更新用户所有旧 authorization rows。
- 原始 telemetry T1 与决策 T2 分开，避免每个 sample 锁 S01；输入准入/物化按源批次与 policy 分类。
- Reaper、outbox 和用户最近事实使用针对性索引；不默认给所有 JSON payload 建全字段 GIN。
- 先测试锁持有时间、热点用户写率、factset delta 重建、ledger write amplification 与历史存储增长，再决定分区/归档。逻辑设计本身不是百万 DAU 容量证明。

## 9. 本轮 protocol review 与未决事项

### 9.1 无需改变协议的逻辑决定

- Program 与 daily bundle 的当前真相采用单一 head pointer；历史内容保持不可变。
- 控制状态采用 append-only control_events + 同事务更新的 control_heads；不依赖异步撤销。
- AuthorizationIssuance 与事件、执行绑定分离；不恢复 A1，不因 A2 重写 START。
- 预算采用 ledger 历史 + reservation/intent 同事务余额，UNKNOWN 占用与 confirmed actual charge 分开。
- manifest/tool 查询使用 input revision，所有动作提交再查当前 epoch/request/fence。

### 9.2 冻结前必须确认的实施语义

| 项目 | 本设计提出的精确定义 | 验证要求 |
|---|---|---|
| 幂等 dispatch | 仅首次 permit transition winner 能发送；重放 receipt 不再次发送 | W01/W02/W03 的 executable state model + worker test |
| 时效线性化 | 持锁后的 guard acceptance time 记录；后续响应不能把已过期资格呈现为当前有效 | A03/A04 与锁等待跨 deadline fixture |
| Revocation / risk ACK | raw received 与 protective action applied 是不同响应语义；安全 ACK 要等 T2 | E02/A01/A07 的 API/E2E |
| 当前指针与重建 | active head/cache 是同步投影，必须可验证；失配 fail closed | DC：绕过 writer 的尝试被拒，重建不短暂放行 |
| 暴露对账 | 实际执行替换同一 session 对应计划暴露，不重复相加；部分执行保留 remaining/unknown | 执行域 fixture + Policy Envelope 契约 |

这五项已有部分抽象模型验证；交错仅覆盖报告列出的有限场景，完整暴露对账、真实数据库锁与 worker 故障尚未验证。若测试迫使改变授权含义或原子边界，先修订冻结 Protocol 的新版本/ADR，再变更本设计；不能以迁移脚本偷偷修补协议。

字段名、索引顺序、分区、数值 TTL 与已定义政策阈值可在不减弱上述含义的前提下后续调整。FK 可延迟性、不可变写权限/trigger、隔离级别和时间函数选择属于 DDL/事务实现审查项目，不在本文件中冒充已经落地。

### 9.3 下一阶段交付边界

1. 已交付 frozen-spec model/fixtures/report；冻结协议已完成；实现阶段不得把模型 PASS 当作生产验收。
2. 自动激活前完成完整 production policy 配置；本文件的 shadow 配置不能替代 auto-activation 配置。
3. 下一步生成 PostgreSQL DDL、typed command contracts 与 repository transaction interfaces。
4. 在真实 PostgreSQL 上运行 DC/WF/E2E，再构建 local vertical slice、AI Fitness Planner、shadow mode；通过 gate 后才签发生产执行授权。

## 10. 本文件验证范围

配套 v0.2 traceability 验证 51 个逻辑关系、18 条 invariant、T1–T8 和原 34 个验收 ID；model report 单独记录有限模型结果。新增 18 个边界模型测试不替换原生产验收。未建立 PostgreSQL 表、未执行真实 worker 故障、未验证线上容量。Protocol v1.2 已 FROZEN；本逻辑 schema 作为 DDL 推导基线冻结，但物理 SQL/索引/分区仍需实现审查。

## 11. r2 新命令与错误合同

以下是旧 §3 的补充；完整命令入口仍由原所有者负责。模型方法是服务内部原型，不等同于完成 typed API 契约。

| 命令 | 唯一所有者 / 原子边界 | 幂等身份 / 重放 | 拒绝码 |
|---|---|---|---|
| BeginBuild / WriteCandidate | CanonicalViewService，build-only | build command key / member operation key + expected member revision；同 key 异 payload 拒绝 | BUILD_CLOSED、IDEMPOTENCY_CONFLICT |
| CompleteFactset | CanonicalViewService，build 写屏障 | build_id + closed_member_revision + completion digest；相同完成凭据返回原 READY/SEALED | MEMBERS_NOT_SUPPORTED、BUILD_CHANGED |
| SealFactset | CanonicalViewService / T2-SEAL | build_id + completion identity；重放只返回旧封存结果，不能重切 head | FACTSET_NOT_READY、BUILD_STALE、BUILD_CHANGED |
| RegisterArtifact | SafetyRegistry / registry exclusive | immutable artifact identity/hash；已有不同内容拒绝，不覆盖 | IMMUTABLE_ARTIFACT、ARTIFACT_UNKNOWN、VALIDITY_UNDEFINED |
| RevokeArtifact | SafetyRegistry / T2-GLOBAL | authenticated management actor + command key + artifact/payload hash；同 key 同 hash 返回原撤销 | COMMAND_NOT_AUTHORIZED、ARTIFACT_UNKNOWN、IDEMPOTENCY_CONFLICT |
| Commit/Issue | AuthorizationService / T6 | 原 commit identity；旧结果重放只表示历史结果，另查当前资格 | ARTIFACT_REVOKED、ARTIFACT_EXPIRED、REGISTRY_UNAVAILABLE、VALIDITY_UNDEFINED、DEPENDENCY_EXPIRED，及原 guard 码 |
| START/RESUME/CONTINUE | ExecutionService / T7 | session/action key + exact P/A；历史回执不作为新执行许可 | 上述 registry/validity 码 + AUTH_EXPIRED、EPOCH_MISMATCH、AUTH_REVOKED |

Registry 故障/管理员身份与通用幂等 gateway 仍是生产适配器义务；模型只实现选定命令的回执和相关边界，不冒充所有 API contract 已完成。

## 12. 依赖有效期与审计落点

S42 保存完整 validity certificate；S24/S21/S36 和 S49 的期限均有身份对应。授权有效期取所有关键依赖结束、政策 TTL、请求上限及 calendar/session boundary 的最小值。TIMELESS 必须指向显式批准政策和理由；缺失值拒绝。证据/admission freshness 必须由 resolver 的最早到期或明确成员期限传递，不能只保存查询完成时间。

执行检查同时读取用户失效屏障与当前 registry。普通新 Manifest 与无关 artifact revoke 不影响旧 A；依据撤回由 T2-IN 同步 epoch 捕获，制品撤销由 T2-GLOBAL 捕获，到期直接由时间判断。S42 历史保持不可变。


---

# Part VIII — Project Plan (verbatim current plan)

# KineticLoop — Project Plan v0.1

状态：**PRE-DEVELOPMENT / READY TO START**  
架构基线：`KineticLoop_v1.2_Protocol_FROZEN.md`  
逻辑数据基线：`KineticLoop_DB_Schema_Design_v0.2_FROZEN.md`  
当前产品模式：`LOCAL_SHADOW / deny-by-default`  
生产自动激活：**DISABLED**

## 1. 项目目标

第一阶段不是“尽快做一个会生成训练文字的聊天机器人”，而是交付一个可在本地完整运行、可追溯、可回放、可故障注入的 KineticLoop vertical slice：

```text
Evidence / workout input
  → admission + canonical facts
  → projections + DecisionManifest
  → bounded PlanningIntent
  → Fitness Coach read-only tools
  → structured proposal
  → authoritative evidence / validation
  → shadow prescription bundle
  → execution/actual ingestion
  → replay + audit
```

初始版本只生成 shadow prescription，不签发 production execution authorization。所有实现必须符合 frozen protocol；发现实现需要改变协议权限含义时，停止该实现路径并提交 ADR / protocol revision，而不是在代码里绕开。

## 2. 锁定技术栈

### Backend

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.x + psycopg 3
- Alembic
- PostgreSQL（本地 Docker Compose 开始；云数据库后置）
- pytest + pytest-asyncio
- Hypothesis 用于状态/性质测试（进入真实 domain model 后）
- Ruff + Pyright/Mypy
- uv 负责 Python dependency / environment

### AI runtime

- OpenAI Responses API
- Function calling / Structured Outputs
- **不使用 OpenAI Agents API 作为核心 runtime**
- KineticLoop 自己拥有 orchestration、budget、tool dispatch、state machine、audit 与 retry semantics

### Runtime topology

```text
FastAPI modular monolith
PostgreSQL
Planner worker
Independent reaper/watchdog
Local web/debug console
Provider adapters / fixtures
```

V1 不拆微服务。边界以 Python package/module + transaction owner 表达。

## 3. Repository 目标结构

```text
kineticloop/
├── apps/
│   ├── api/
│   ├── worker/
│   └── reaper/
├── kineticloop/
│   ├── domain/
│   │   ├── evidence/
│   │   ├── publication/
│   │   ├── authorization/
│   │   ├── planning/
│   │   ├── execution/
│   │   └── replay/
│   ├── contracts/
│   ├── persistence/
│   ├── services/
│   ├── projections/
│   ├── context_tools/
│   ├── agents/
│   ├── integrations/
│   └── observability/
├── migrations/
├── tests/
│   ├── protocol_unit/
│   ├── db_concurrency/
│   ├── worker_faults/
│   ├── e2e/
│   └── replay/
├── evals/
├── fixtures/
├── docs/
└── docker-compose.yml
```

## 4. Milestone roadmap

### M0 — Frozen baseline [DONE]

Deliverables:
- Protocol v1.2 FROZEN.
- DB logical schema v0.2 frozen baseline.
- 18 invariants / T1–T8 / 34 acceptance specs.
- bounded protocol model and negative controls.
- machine-readable traceability.

Exit: this release package is the canonical implementation baseline.

### M1 — Engineering foundation

Deliverables:
- repo/bootstrap, uv, lint/type/test CI;
- Docker Compose PostgreSQL;
- config model with `LOCAL_SHADOW` default;
- shared ID/time/hash conventions;
- error code registry;
- test DB lifecycle and deterministic fixture loader.

Exit gate:
- clean bootstrap from empty checkout;
- one command starts Postgres + API test environment;
- no production issuance code path enabled by default.

### M2 — PostgreSQL DDL + typed contracts

Deliverables:
- physical schema derived from S01–S51;
- composite subject FKs and immutable-history write protections;
- indexes/unique constraints/partial uniqueness where allowed;
- Alembic initial migration;
- Pydantic commands/results for T1–T8;
- repository interfaces with explicit transaction ownership.

Implementation order should follow authority rather than table number:
1. shared identity/event/idempotency primitives;
2. S01/S02/S03/S04;
3. Evidence/Factset core S09–S18;
4. SafetyRegistry S49–S51;
5. Manifest/projection S21–S26;
6. Planning/ledger S27–S37;
7. Prescription/authorization/execution S38–S45;
8. Replay/evaluation S46–S48;
9. Program/catalog/config relations.

Exit gate:
- schema can be recreated from zero;
- migration + contract generation tests pass;
- frozen invariants have an explicit DB/TX/DOMAIN enforcement owner.

### M3 — Real protocol core on PostgreSQL

Implement command owners, not generic CRUD:
- EvidenceService / CanonicalInputCoordinator;
- CanonicalViewService build→complete→seal;
- DecisionPublicationService;
- ControlService;
- SafetyRegistry;
- AuthorizationService + `is_executable`;
- PlanningWorkflowService;
- CallLedgerService;
- ExecutionService;
- Replay isolation boundary.

First concurrency targets:
- publish vs user revoke;
- START vs revoke;
- cancel vs DISPATCH_INTENT;
- lease takeover vs commit;
- artifact revoke vs issue/start/publish;
- factset seal vs input update;
- dependency expiry vs START.

Exit gate:
- DC tests run against real PostgreSQL;
- no test relies only on in-memory locking assumptions;
- rollback/deadlock/serialization retry re-reads guards.

### M4 — Worker, reaper and fault-injection

Deliverables:
- planner lease/fencing loop;
- reservation → DISPATCH_INTENT → settlement ledger;
- independent reaper process;
- outbox dispatcher;
- process-kill tests at specified W01/W05/W06/W08 boundaries;
- SDK retry disabled or fully ledger-controlled.

Exit gate:
- unknown provider outcome never refunds budget;
- old fence cannot commit;
- late result cannot reopen intent;
- STOP/control path remains independent of model queue.

### M5 — Canonical training data vertical slice

Deliverables:
- exercise catalog and mapping path;
- workout/session/set/cardio canonical typed storage;
- chat/manual report ingestion preserving provenance and uncertainty;
- duplicate underlying event association;
- progression/sequence/exposure projections;
- historical correction + invalidation propagation;
- Google Sheet migration adapter for existing training history.

Exit gate:
- E01/E03/E04/E05/E07/A08 can be demonstrated E2E without LLM planning.

### M6 — Decision context + read-only tools

Deliverables:
- DecisionManifest builder;
- mandatory context contract;
- snapshot-bound tools: recent sessions, exercise history, movement exposure, readiness history, weight/nutrition trends, program/blueprints, restrictions;
- provenance/freshness/coverage on every tool response;
- untrusted free text remains data, never command authority.

Exit gate:
- D01–D05 and E06/E08 have real DB/API tests;
- no tool can silently read unpublished input.

### M7 — Fitness Coach shadow planner

Deliverables:
- Responses API client;
- structured FitnessProposal schema;
- adaptive tool exploration under root PlanningIntent budget;
- modality, sequence re-entry, exercise selection, sets/reps/RPE proposal;
- PrescriptionDemandFeatures generated by code;
- validator/evidence obligations;
- shadow DailyPlanBundle commit with **no production execution issuance**.

Core quality evals:
- long-gap A/B/C re-entry;
- recent lower-body load with different recovery contexts;
- progression increase requires authoritative evidence;
- uncertainty causes appropriate permission contraction without forcing generic rest;
- irrelevant history injection does not destabilize plan materially.

Exit gate:
- local E2E can ingest history → publish context → agent queries tools → generate → validate → store shadow plan → audit/replay.

### M8 — Nutrition Coach + cross-domain bundle

Deliverables:
- daily nutrition proposal contract;
- Fitness proposal hash / DemandFeature dependency binding;
- fat-loss-priority arbitration policy;
- single + rolling policy envelopes;
- training/nutrition repair consumes same root budget;
- F change invalidates D/N.

Exit gate:
- W07 plus cumulative corridor-edge scenarios pass;
- durable baseline changes remain separate proposals and are not silently activated.

### M9 — Live provider adapters, still shadow

Sequence adapters independently so canonical contracts stay provider-neutral:
- Hevy;
- iOS HealthKit bridge;
- Oura path subject to current compliance design;
- nutrition/weight sources;
- body composition / DEXA import.

Each adapter must first pass fixture replay, idempotency, correction and late-data tests before contributing to planning manifests.

Exit gate:
- live data can flow into the same canonical pipeline without provider-specific planner logic.

### M10 — Staging / observability / release evaluation

Deliverables:
- structured tracing by command/intent/manifest/authorization;
- SLO/error dashboards for stale runs, revoke latency, lock waits, budget unknowns;
- prompt/model/policy release registry;
- Historical Reconstruction + Current Policy Backtest;
- fixed evaluation datasets and leakage checks;
- shadow comparison reports.

Exit gate:
- model/prompt change cannot ship without bound release artifact and evaluation record.

### M11 — Auto-activation readiness review

No production issuance until all required frozen acceptance tests have implementation evidence.

Required evidence includes:
- 34 PU/DC/WF/E2E acceptance specs;
- global/user revoke latency and failure behavior;
- authorization audit and validity closure;
- fallback/UNAVAILABLE UX;
- provider outage and model outage degradation;
- policy bundle with explicit admission/envelope/authorization values;
- security review for command authority, prompt injection and subject isolation;
- staging shadow outcome review.

Passing M11 authorizes a separate launch decision; it is not automatically granted by completing earlier milestones.

## 5. Workstreams and ownership boundaries

| Workstream | Owns | Must not own |
|---|---|---|
| Persistence | DDL, transactions, locks, repository | coaching judgment |
| Evidence | ingestion, association, admission, canonical facts | automatic progression choice |
| Publication | projections, Manifest consistency | execution authorization |
| Authorization | evidence obligations, policy guards, issue/revoke/evaluate | AI plan quality scoring |
| Planning | intent/budget/lease/fence/repair workflow | canonical facts |
| AI Fitness | contextual coaching proposal | direct DB mutation / permission grants |
| AI Nutrition | nutrition proposal | training fact mutation / durable activation |
| Execution | START/RESUME/actual ingestion | fabricate authorization for actual behavior |
| Replay/Eval | point-in-time evaluation | live production mutation |
| Integrations | provider transport/normalization | provider-specific planner authority |

## 6. Initial implementation backlog

### Foundation
- KL-001 initialize repo/tooling/CI.
- KL-002 local Postgres Docker environment.
- KL-003 shared identifiers, UTC/local-date policy, canonical JSON/hash utility.
- KL-004 error code and command receipt contracts.
- KL-005 test fixture framework seeded from frozen acceptance JSON.

### DDL/Contracts
- KL-010 translate S01–S51 into physical table plan.
- KL-011 choose typed child tables for `canonical_fact_revisions` high-volume domains.
- KL-012 define immutable history permissions/triggers or repository protections.
- KL-013 implement Alembic baseline migration.
- KL-014 create Pydantic T1–T8 command/result contracts.
- KL-015 create transaction/repository interfaces.

### First real protocol tests
- KL-020 S01 user coordination and command idempotency.
- KL-021 SafetyRegistry S49–S51 + T2-GLOBAL commit semantics.
- KL-022 Authorization validity evaluator.
- KL-023 Factset build/complete/seal.
- KL-024 planning intent + lease/fencing.
- KL-025 call reservation ledger + DISPATCH_INTENT.
- KL-026 port nine interleavings to real PostgreSQL tests.

### Canonical training slice
- KL-030 evidence receive/assertion/admission.
- KL-031 workout actual typed schema.
- KL-032 event association/dedup.
- KL-033 sequence/progression/exposure projections.
- KL-034 correction invalidation.
- KL-035 existing Sheet migration staging/import.

### AI shadow slice
- KL-040 DecisionManifest + snapshot.
- KL-041 context tool gateway.
- KL-042 FitnessProposal Pydantic/JSON schema.
- KL-043 OpenAI Responses API adapter with ledger-controlled physical calls.
- KL-044 evidence resolver + validation.
- KL-045 shadow bundle commit and debug UI/API.
- KL-046 historical replay of daily planning.

## 7. Definition of Done by layer

### Protocol implementation DoD
A command is not “implemented” until idempotency, failure code, transaction owner, audit event and corresponding frozen tests exist.

### AI feature DoD
An Agent feature is not “implemented” merely because prompt output looks good. It needs structured contract, tool permissions, budget accounting, validator behavior, replay evidence and failure/degradation behavior.

### Integration DoD
A provider adapter needs idempotent receive, source revision semantics, correction/late-data handling, provenance and fixture tests before its data may influence a Manifest.

### Production authorization DoD
No implementation can enable production issuance by environment flag alone. A release must reference an approved policy bundle, evaluation release and completed auto-activation gate evidence.

## 8. Deliberately deferred decisions

These remain configurable or later design tasks and do not block starting implementation:
- managed Postgres vendor / cloud runtime;
- exact production policy thresholds and TTL values;
- multi-session-per-day product enablement (schema keeps a path, V1 remains one planned training session per bundle);
- local TDEE estimator;
- full weekly Program Analyst / automated durable changes;
- offline START;
- large-scale partitioning/archival;
- microservice split.

## 9. First build target

The first meaningful demo is **not** an AI chat UI. It is a deterministic local flow with real PostgreSQL:

```text
seed user/program/evidence
→ seal factset
→ compute projection
→ publish DecisionManifest
→ create PlanningIntent
→ acquire lease + reserve fake model call
→ write deterministic FitnessProposal fixture
→ validate
→ commit SHADOW bundle
→ inspect audit/replay
→ inject revoke/correction and prove old authority cannot be reused
```

Once this passes in real PostgreSQL, replace the deterministic proposal fixture with the Fitness Coach Responses API path without changing the surrounding protocol.

