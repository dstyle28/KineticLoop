# KineticLoop v1.1 — AI Review Package

> **Document type:** Consolidated PRD + Technical Specification + Architecture / Design Document  
> **Audience:** Staff/Senior Backend Engineers, AI/Agent Engineers, Technical PMs, architecture reviewers  
> **Status:** Review baseline; suitable as upstream input for DDL, API contracts, state machines, evals, and implementation planning  
> **Date:** 2026-09-17  
> **Primary objective:** `FAT_LOSS_PRIORITY`  
> **Backend direction:** Python-first  
> **LLM runtime direction:** OpenAI Responses API + Function Calling / Structured Outputs; **do not depend on OpenAI Agents API for V1**  
> **Canonical production store:** PostgreSQL  
> **P0 runtime:** Local-first, end-to-end runnable before cloud deployment  
> **Current migration source:** Google Sheet `Fitness Training Log Manager`  

---

## 0. How to Review This Document

This document is intentionally self-contained so an AI reviewer does not need prior chat context.

Please review it along these dimensions:

1. **AI intelligence vs determinism:** Is too much coaching judgment still hard-coded? Is any safety-critical state left prompt-only?
2. **Agent boundaries:** Can the Fitness Coach and Nutrition Coach reason deeply enough without owning canonical state?
3. **Context architecture:** Is progressive, read-only tool access sufficient to make the agents intelligent without overwhelming them?
4. **Concurrency / race conditions:** Are planning, revision, ingestion, approval, and state-version semantics coherent?
5. **Schema design:** Does the schema preserve facts, provenance, revisions, and future multi-session/day support without over-normalizing?
6. **Workout ingestion:** Are Hevy/manual/wearable sources reconciled safely and idempotently?
7. **Sequence behavior:** Is A/B/C continuity intelligent after long gaps instead of mechanical?
8. **Provider integration:** Are external provider assumptions isolated enough that APIs/terms can change without corrupting the domain model?
9. **Local-first development:** Can a useful vertical slice run locally before building cloud infrastructure?
10. **Missing failure modes:** Identify deadlocks, stale data hazards, hidden coupling, agent prompt failure, replay bugs, and operational gaps.

When proposing changes, prefer this format:

```text
Current Design → Problem → Proposed Change → Migration Impact
```

---

# Part I — Product Requirements Document

## 1. Product Vision

KineticLoop is a persistent personal health, fat-loss, recovery, and training decision system.

It is **not** primarily a chatbot, workout template generator, wearable dashboard, or rule engine.

Its job is to maintain a trustworthy canonical model of the user's current state, allow AI coaches to reason over enough context to make useful decisions, validate those decisions against hard constraints, record what actually happened, and continuously improve future decisions.

Core loop:

```text
Observe
  ↓
Normalize
  ↓
Build canonical state
  ↓
Build decision context
  ↓
AI coach reasons + selectively queries more context
  ↓
Structured proposal
  ↓
Deterministic constraint validation
  ↓
Canonical commit
  ↓
Execution / workout
  ↓
Ingestion + reconciliation
  ↓
Progression / review / future context
```

The system should behave like a persistent coach that remembers the actual program, execution history, recovery, progression, and corrections independently of any chat thread.

---

## 2. Product Goal Hierarchy

Confirmed product objective:

```text
GOAL_STRATEGY = FAT_LOSS_PRIORITY
```

This does **not** mean “always cut more calories.” It means that, inside safety and approved program boundaries, the system optimizes primarily for sustainable fat loss while preserving sufficient strength, muscle-retention training, recovery, adherence, and health.

High-level priority:

```text
Explicit safety / health constraints
        ↓
Approved program hard constraints
        ↓
Fat-loss objective
        ↓
Strength / performance optimization
        ↓
Convenience / preference optimization
```

The exact numerical definition of the “strength-preservation floor,” calorie corridor, acceptable rate of loss, and automatic nutrition adjustment authority remains a configurable program decision, not an implicit LLM assumption.

---

## 3. Product Principles

### 3.1 Canonical state over conversational memory

No decision-critical state may depend on which conversation thread remembers the most context.

Canonical storage must own at least:

- active program version,
- structural A/B/C blueprints,
- nominal next strength blueprint,
- actual completed sessions,
- strength sets and cardio bouts,
- exercise identity / mappings,
- health observations and freshness,
- readiness / derived features,
- progression state,
- active health flags / restrictions,
- daily plan bundle and revisions,
- agent proposals and tool evidence,
- overrides,
- approvals,
- audit / domain events.

### 3.2 Deterministic truth, AI judgment

KineticLoop should **not** encode most coaching judgment as `if/else` rules.

The desired boundary is:

> **Code establishes what is true, what is allowed, and how state changes safely. AI decides what is reasonable within those facts and boundaries.**

### 3.3 AI gets enough context, but not arbitrary database access

Agents should be capable of actively querying decision-relevant history.

They should **not** receive the entire database in one prompt, and should **not** receive a general SQL tool.

Instead:

```text
Core context summary
      ↓
Agent reasoning
      ↓
Typed read-only context tools when needed
      ↓
More reasoning
      ↓
Structured proposal
```

This is **progressive context disclosure**.

Ordinary days should require little extra querying. Ambiguous or unusual days should permit deeper investigation.

### 3.4 Preserve behavior, not POC implementation

The existing Google Sheet and previous GPT-native implementation are requirements and regression sources, not production architecture authorities.

If legacy design conflicts with the new production architecture, preserve the useful invariant while replacing the implementation.

### 3.5 AI can be flexible; state transitions cannot be vague

Exercise choice, sequence restart, cardio modality, training volume, and fatigue interpretation may require contextual AI reasoning.

IDs, idempotency, stale-vs-current semantics, status transitions, permissions, canonical revisions, concurrency, and auditability are deterministic.

---

## 4. Locked Behavioral Invariants

The following are non-negotiable unless explicitly reopened:

1. Canonical state lives outside chat threads.
2. Weekday is only a schedule prior; it never mechanically overrides actual training history.
3. The system stores `last_resolved_strength_blueprint` and a **nominal** `next_strength_blueprint`.
4. Only a confirmed/resolved completed Strength A/B/C session advances the nominal A→B→C sequence.
5. Cardio, recovery, rest, walking, and wearable labels do not advance the strength sequence.
6. A long gap can reduce sequence continuity confidence; AI may rationally choose a different re-entry/start blueprint.
7. Current missing health data stays `UNKNOWN/PARTIAL`; historical values cannot silently masquerade as today’s values.
8. Sleep parsing must use correct stage/session semantics; awake/in-bed must not be silently counted as asleep.
9. Wearable “strength workout” labels never invent sets, reps, exercises, or load.
10. Hevy and manual/chat workout reports feed the same canonical ingestion pipeline.
11. Workout ingestion uses stable source identities, idempotency, corrections, reconciliation, and append-only events.
12. LLM agents never directly mutate canonical state.
13. All LLM outputs are proposals, not truth.
14. A proposal must pass deterministic schema/permission/constraint validation before activation.
15. Durable program changes require explicit approval or an explicitly configured auto-approval policy for that change class.
16. Pending durable proposals do not affect daily planning.
17. Same-day planning must be versioned and consistent across chat/UI surfaces.
18. Late-arriving data does not automatically cause plan flapping; revisions are material-event-driven.
19. User override can cancel/supersede an active plan without deleting history.
20. Daily output has a stable rendering contract and a concise copy-ready reporting block.

---

## 5. Training Program Structural Source

The uploaded `健身计划制定指南.txt` remains the structural source for the training program, but its literal exercise list is not an immutable daily schedule.

### 5.1 Weekly anchors

Baseline schedule anchors:

| Day | Baseline intent |
|---|---|
| Monday | Strength A |
| Tuesday | protected family / full rest |
| Wednesday | optional easy walk / easy Zone 2 |
| Thursday | Strength B |
| Friday | main Zone 2 |
| Saturday | Strength C |
| Sunday | Zone 2 / recovery |

These are **priors**, not locks.

### 5.2 A/B/C structural blueprints

**Strength A** preserves these roles:

- squat/lower-body primary,
- horizontal push,
- horizontal pull,
- hinge,
- vertical pull,
- anti-rotation core.

**Strength B** preserves these roles:

- deadlift/posterior-chain primary,
- incline/upper push,
- vertical pull,
- unilateral lower,
- rear-delt/scapular support,
- loaded carry.

**Strength C** preserves these roles:

- moderate squat/leg-press pattern,
- horizontal push,
- supported horizontal pull,
- knee flexion,
- lateral delt,
- arms,
- anti-extension core,
- lower systemic fatigue / hypertrophy emphasis.

AI may vary exact exercises when justified, while preserving blueprint purpose, progression continuity, fatigue management, and long-horizon equipment/modality balance.

---

## 6. V1 Product Scope

### 6.1 Included

- canonical program state,
- exercise catalog,
- workout ingestion,
- A/B/C continuity state,
- health/recovery facts and freshness,
- deterministic derived features,
- progressive read-only context tools,
- Fitness Coach Agent,
- Nutrition Coach Agent,
- daily plan bundle,
- deterministic validation / constraint kernel,
- user overrides,
- durable change proposals / approvals,
- event/audit log,
- Google Sheet migration,
- local end-to-end runtime,
- historical replay / agent evaluation.

### 6.2 Deferred

- fully autonomous durable program changes,
- generalized medical diagnosis or treatment,
- unrestricted LLM database queries,
- full multi-user SaaS billing / enterprise admin,
- microservice decomposition,
- full event sourcing,
- dependency on OpenAI Agents API managed runtime,
- required cloud deployment before core coaching quality is validated.

---

# Part II — AI-Native Decision Architecture

## 7. Architecture Principle

Previous design versions pushed too much judgment into a deterministic “modality resolver” and rule engine.

The revised architecture intentionally moves **coaching judgment** back into the AI layer while keeping deterministic truth and hard constraints outside the model.

```text
                  Canonical PostgreSQL
                          │
                  Derived Facts / Features
                          │
                  Context & Tool Gateway
                  │                    │
           Core Context          Read-only Tools
                  │                    │
                  └─────────┬──────────┘
                            ▼
                    Fitness Coach Agent
                            │
                     Structured Proposal
                            │
                       Constraint Kernel
                            │
                            ▼
                    Orchestrator / Commit
                            │
                            ▼
                    Canonical Daily Plan
```

The Nutrition Coach uses the same pattern.

---

## 8. What Is Deterministic vs AI-Driven

| Concern | Owner | Rationale |
|---|---|---|
| Raw provider ingestion | deterministic | exact external facts |
| Source freshness / watermark | deterministic | truth semantics |
| Unit normalization | deterministic | correctness |
| Sleep aggregation semantics | deterministic | correctness |
| Rolling set counts / time windows | deterministic | arithmetic |
| A/B/C nominal pointer advancement | deterministic | reproducible state transition |
| Sequence continuity interpretation after long gap | **AI** | contextual coaching judgment |
| Readiness features / normalized signals | deterministic | shared facts |
| Meaning of those signals for today | **AI** | contextual judgment |
| Strength vs Zone2 vs Recovery vs Rest | **AI**, inside hard eligibility | coaching decision |
| Cardio modality | **AI**, inside hard restrictions | context-dependent |
| Exercise choice | **AI** | coaching judgment |
| Sets/reps/load/RPE proposal | **AI** within configured corridors | coaching judgment |
| Exercise identity mapping | deterministic approved mapping; AI may propose unknown mappings | ontology must remain stable |
| Nutrition daily allocation | **AI** within active program envelope | contextual judgment |
| Long-term calorie baseline | Program Version / durable proposal | durable policy |
| IDs / idempotency | deterministic | correctness |
| State mutation | deterministic | correctness |
| Concurrency/CAS | deterministic | correctness |
| User explicit override | deterministic fact | user authority |
| Durable change activation | approval state machine | human control |

The key rule is:

> **Do not hard-code a coaching preference merely because it can be expressed as an if-statement.**

---

## 9. Constraint Kernel

The old term “Rule Engine” is intentionally replaced with **Constraint Kernel**.

The Constraint Kernel is **not a coach**.

It owns only:

### 9.1 Data truth constraints

Examples:

- stale is not current,
- unknown is not zero,
- raw wearable strength metadata cannot become invented set details,
- units must be valid,
- referenced canonical IDs must exist.

### 9.2 State consistency constraints

Examples:

- optimistic concurrency,
- valid lifecycle transition,
- idempotency,
- supersession semantics,
- active Program Version binding,
- same-day bundle revision control.

### 9.3 Permissions

Examples:

- Fitness Coach cannot mutate calorie baseline,
- Nutrition Coach cannot mutate program structure,
- agents cannot approve their own durable changes,
- agents cannot write DB state.

### 9.4 Explicit hard constraints

Examples:

- `USER_OVERRIDE = FORCE_REST`,
- active prohibited movement restriction,
- unavailable exercise / unknown exercise ID in prescription,
- configured absolute load/risk corridor,
- known-corrupt state blocks activation.

### 9.5 Approval boundaries

Examples:

- split change,
- program phase change,
- permanent calorie baseline change,
- permanent frequency change,
- durable exercise policy changes.

The Constraint Kernel should **not** decide whether yesterday’s leg fatigue means cycling is better than walking unless a true hard restriction exists.

---

# Part III — Agent Design

## 10. Agent Execution Model

Agents receive a compact **Core Context** and may call typed, read-only tools when additional information is useful.

They do not receive arbitrary SQL, unrestricted file system access, or write tools.

```text
Core Context
   ↓
Agent
   ├─ sufficient? → propose
   │
   └─ insufficient? → read-only tool
                         ↓
                    more evidence
                         ↓
                       reason
                         ↓
                     propose
```

This allows **adaptive planning depth**:

- ordinary days → shallow reasoning, few/no tool calls,
- unusual days → deeper historical inspection,
- long layoff → inspect 30–60 day strength history,
- ambiguous progression → inspect exercise-specific history,
- conflicting recovery signals → inspect trends and recent load,
- plateau → inspect weight/nutrition/training trends.

---

## 11. Fitness Coach Agent

### 11.1 Responsibilities

The Fitness Coach may decide:

- daily modality,
- whether nominal sequence should continue, reset, or use re-entry logic,
- which A/B/C blueprint best fits the day,
- exercise selection,
- ordering,
- load / reps / sets / RPE,
- substitutions,
- accessories,
- cardio modality and duration,
- how strongly recent fatigue should matter today,
- whether to preserve, hold, reduce, or progress an exercise,
- whether weekly target gaps are worth addressing today.

### 11.2 Core input context

Example:

```json
{
  "planning_run_id": "planrun_...",
  "state_version": 184,
  "local_date": "2026-09-17",
  "goal_strategy": "FAT_LOSS_PRIORITY",
  "active_program_version": "program_17",
  "schedule_prior": {
    "preferred_modality": "STRENGTH",
    "protected": false,
    "time_budget_min": 70
  },
  "sequence_prior": {
    "last_resolved_blueprint": "A",
    "nominal_next_blueprint": "B",
    "days_since_last_strength": 15,
    "continuity_strength": "LOW"
  },
  "readiness_features": {
    "classification": "YELLOW",
    "completeness": "COMPLETE",
    "hard_gate": false,
    "signals": ["SHORT_SLEEP"]
  },
  "recent_load_summary": {},
  "active_health_flags": [],
  "program_constraints": {},
  "candidate_action_space": {}
}
```

`continuity_strength` is a feature/prior, not an absolute command.

### 11.3 Read-only tools

Representative tools:

```text
get_recent_sessions(days, modality?)
get_session_detail(session_id)
get_exercise_history(exercise_id, days)
get_movement_exposure(pattern, days)
get_muscle_volume(muscle_group, days)
get_progression_context(exercise_ids)
get_readiness_history(days)
get_health_metric_trend(metric, days)
get_body_weight_trend(days)
get_nutrition_summary(days)
get_active_program()
get_blueprint(code)
search_exercise_catalog(role, equipment?, constraints?)
get_active_health_flags()
```

Every tool response should include, where relevant:

```text
source
observed_at/effective_at
freshness
confidence/evidence class
query window
```

### 11.4 Anti-goals

Fitness Coach must not:

- issue SQL,
- directly mutate DB state,
- create arbitrary permanent exercise mappings,
- change durable calorie baseline,
- approve a durable Program change,
- claim stale health data is current,
- invent exercise IDs,
- invent completed sets,
- silently bypass user override,
- define new Program Versions.

### 11.5 Output contract

Representative structure:

```json
{
  "proposal_id": "fp_...",
  "planning_run_id": "planrun_...",
  "state_version": 184,
  "decision": {
    "modality": "STRENGTH",
    "sequence_action": "REENTRY",
    "chosen_blueprint": "A",
    "reason_codes": [
      "LONG_STRENGTH_GAP",
      "PRESERVE_MOVEMENT_COVERAGE"
    ]
  },
  "session": {
    "target_duration_min": 65,
    "target_rpe_cap": 8,
    "exercises": []
  },
  "training_demand": {
    "systemic": "MODERATE",
    "lower_body": "MODERATE",
    "glycolytic": "MODERATE"
  },
  "tool_evidence_ids": ["toolcall_1", "toolcall_2"]
}
```

---

## 12. Sequence Semantics

The nominal sequence remains deterministic:

```text
A → B → C → A
```

But `nominal_next_blueprint` is a **continuity prior**, not a permanent command.

Canonical training state stores:

```text
last_resolved_strength_blueprint
last_resolved_strength_at
nominal_next_strength_blueprint
```

Planning features additionally compute:

```text
days_since_last_strength
recent_strength_frequency
recent_blueprint_coverage
recent_movement_exposure
interruption_context
sequence_continuity_strength
```

Example:

```text
last completed = A
nominal next = B
last strength = 2 days ago
→ strong prior toward B
```

versus:

```text
last completed = A
nominal next = B
last strength = 15 days ago
→ weak prior; AI may choose B, A re-entry, C, or other approved re-entry strategy with rationale
```

The system should **not** encode a simplistic rule such as:

```python
if days_since_last_strength > 10:
    blueprint = "A"
```

On workout completion, the actual resolved completed blueprint becomes the new basis for the next nominal pointer.

Example:

```text
nominal next was B
AI selected A re-entry
A was completed/resolved
→ nominal next becomes B
```

Only completed/resolved A/B/C changes the pointer.

---

## 13. Recovery / Fatigue Semantics

Deterministic code computes features; AI interprets their relevance.

Example facts:

```json
{
  "lower_body_hard_sets_48h": 11,
  "lower_body_hard_sets_72h": 15,
  "hours_since_last_lower_body_session": 22,
  "soreness": 2,
  "sleep_state": "NORMAL",
  "hrv_trend": "BASELINE",
  "zone2_minutes_7d": 55
}
```

The system should not hard-code:

```text
lower-body work in 72h → bike only
```

Instead the Fitness Coach may conclude that walking, cycling, reduced-duration Zone 2, recovery work, or even normal training remains reasonable depending on the total context.

Only true hard safety/health restrictions should force a deterministic modality exclusion.

---

## 14. Nutrition Coach Agent

### 14.1 Responsibilities

The Nutrition Coach focuses on short-horizon nutrition / recovery decisions such as:

- daily calorie allocation inside the active Program envelope,
- protein / carbohydrate / fat allocation,
- training-day fueling,
- carbohydrate timing,
- short-horizon adjustments based on training demand, body-weight trend, intake adherence, and recovery.

### 14.2 Inputs

It reads:

- active Program nutrition policy,
- canonical intake trends,
- canonical weight trend,
- expenditure observations / confidence,
- readiness/recovery features,
- `TrainingDemandContract` from the Fitness proposal,
- user constraints/preferences.

It may use its own typed read-only tools for deeper trend inspection.

### 14.3 Anti-goals

It must not:

- alter training exercise selection or progression,
- change Program structure,
- permanently change calorie baseline without durable approval,
- diagnose medical conditions,
- treat stale expenditure as verified current expenditure,
- write canonical state directly.

### 14.4 Output

```json
{
  "proposal_id": "np_...",
  "planning_run_id": "planrun_...",
  "daily_target": {
    "calories_kcal": 0,
    "protein_g": 0,
    "carbs_g": 0,
    "fat_g": 0
  },
  "timing": {},
  "reason_codes": [],
  "tool_evidence_ids": []
}
```

Actual numeric corridors come from the active Program Version; they are not hard-coded into the Agent prompt.

---

## 15. Cross-Domain Coordination

Agents do **not** debate each other peer-to-peer.

Recommended orchestration:

```text
Shared canonical context
      ↓
Fitness Coach proposal
      ↓
TrainingDemandContract
      ↓
Nutrition Coach proposal
      ↓
Cross-domain consistency check
      ↓
optional targeted repair
      ↓
validation + commit
```

Because `FAT_LOSS_PRIORITY` is confirmed, a soft training-vs-nutrition conflict should generally try to preserve the approved fat-loss program envelope before requesting a durable calorie-policy change.

This does **not** mean deterministic code decides the exact training compromise.

Recommended behavior:

1. Detect that both proposals cannot simultaneously satisfy the active Program envelope.
2. If the nutrition proposal can be repaired within the approved daily corridor, ask Nutrition Coach for a bounded repair.
3. Otherwise, send a structured conflict constraint to Fitness Coach and allow one bounded replan that preserves the strength-retention intent where possible.
4. If no valid plan exists inside active constraints, return `NEEDS_REVIEW` or a conservative fallback.
5. Never let Agents retry each other indefinitely.

Maximum repair counts should be configurable and tested.

---

# Part IV — Daily Planning Lifecycle

## 16. Planning Inputs / Readiness Gate

Morning planning cannot assume every provider has finished syncing at a specific clock time.

KineticLoop tracks per-source:

```text
freshness
watermark
received_at
expected_local_date
completeness
finality/partiality where available
```

A daily input gate decides whether planning runs with:

```text
COMPLETE
PARTIAL
UNKNOWN
```

The gate should not assume any provider emits a particular “complete” event unless officially documented.

Possible triggers:

- source ingestion,
- app foreground,
- scheduled check,
- explicit user plan request,
- planning deadline,
- user-provided new health/recovery information.

At deadline, missing signals remain `PARTIAL/UNKNOWN`; old values are not silently substituted.

---

## 17. Planning Run Protocol

```text
1. PRECHECK
   - canonical state integrity
   - active Program Version
   - current user override
   - existing active DailyPlanBundle

2. INPUT STATUS
   - source freshness/completeness
   - health observation quality

3. DERIVED FEATURES
   - training load windows
   - progression features
   - readiness features
   - sequence continuity features
   - weight/nutrition trends

4. BUILD CORE CONTEXT
   - state_version=N
   - current program
   - schedule prior
   - constraints
   - compact summaries

5. FITNESS AGENT
   - may call bounded read-only tools
   - returns FitnessProposal

6. FITNESS DOMAIN VALIDATION
   - schema
   - IDs
   - permissions
   - hard constraints

7. TRAINING DEMAND CONTRACT

8. NUTRITION AGENT
   - may call bounded read-only tools
   - returns NutritionProposal

9. NUTRITION DOMAIN VALIDATION

10. CROSS-DOMAIN CONSISTENCY
    - optional bounded targeted repair

11. FINAL CONSTRAINT VALIDATION

12. SHORT DB TRANSACTION
    - verify state_version / active program
    - detect competing same-day revision
    - persist new bundle revision
    - supersede previous if required
    - append events/outbox

13. RENDER
    - stable daily output contract
```

Important:

**Do not keep a DB transaction open while waiting for LLM inference.**

---

## 18. Context Consistency During Tool Calls

Tool calls happen outside the final commit transaction.

Each tool call must record:

```text
planning_run_id
state_version_seen
input arguments
result metadata
result hash / evidence reference
started_at / completed_at
```

The complete evidence used by the Agent is persisted as an `AgentRun` trace.

Before activation, the orchestrator compares the relevant canonical `state_version`.

If relevant state changed materially:

```text
proposal becomes STALE
→ rebuild/replan
```

This provides reproducibility without requiring a full temporal database snapshot for every LLM run.

---

## 19. Same-Day Revision Policy

Late data should not cause plan flapping.

Revisions are **material-event-only**.

Candidate material events include:

- explicit user replan,
- user reports illness/pain/major soreness,
- completed workout changes expected next session,
- major new recovery observation,
- explicit schedule/equipment/time change,
- source correction that materially changes the decision basis.

Minor numerical drift should not create an automatic new plan.

The revision policy should support:

```text
materiality classification
debounce / cooldown
max automatic revisions/day
UI-request bypass
training-started lock semantics
```

Exact thresholds remain configuration / Decision Points.

---

# Part V — Prescription / Plan Model

## 20. Multi-Session Future Without Overbuilding V1

A user may eventually have multiple active training prescriptions on the same local date, for example:

```text
AM Zone 2
PM Strength
```

V1 will support **one planned training session/day by policy**, but the data model must not make multiple sessions impossible.

Recommended model:

```text
DailyPlanBundle
  ├─ 0..N TrainingPrescriptions
  └─ 0..1 NutritionPrescription revision
```

There is one canonical active **DailyPlanBundle revision** per user/local date.

V1 policy:

```text
max_active_training_prescriptions_per_bundle = 1
```

Future policy can increase this without redesigning the core DB.

---

## 21. DailyPlanBundle Lifecycle

```text
DRAFT
  ↓
VALIDATING
  ├─ FAIL → REJECTED
  ├─ REVIEW → NEEDS_REVIEW
  └─ PASS → ACTIVE
               ├─ revision → SUPERSEDED
               ├─ user cancellation → CANCELLED
               └─ day closed → CLOSED
```

Previous revisions are never overwritten/deleted.

---

## 22. User Override

Supported explicit commands should include concepts such as:

```text
CANCEL_ACTIVE_PLAN
FORCE_REST
FORCE_RECOVERY
REPLAN_WITH_TIME_LIMIT
EQUIPMENT_UNAVAILABLE
```

Example:

```text
ACTIVE strength plan
   ↓
USER_OVERRIDE(FORCE_REST)
   ↓
old bundle/prescription → CANCELLED or SUPERSEDED
   ↓
override stored as canonical fact
   ↓
new plan generated under forced-rest constraint
```

A user override by itself does not advance A/B/C sequence. Only confirmed completed/resolved strength sessions do.

---

# Part VI — Workout Ingestion & Exercise Semantics

## 23. Canonical Workout Ingestion Pipeline

All workout completion sources converge on one service:

```text
Hevy
chat/manual report
wearable session metadata
future import
      ↓
Raw Source Event
      ↓
Normalize
      ↓
Resolve source identity
      ↓
Idempotency / correction detection
      ↓
Exercise mapping
      ↓
Canonical workout facts
      ↓
Prescription matching
      ↓
Blueprint resolution
      ↓
Progression / volume / sequence update
      ↓
Event log
```

Hevy is the preferred structured strength logging path.

Chat/manual remains a first-class correction and fallback path.

Exact Hevy polling/webhook capabilities must be verified against official documentation during implementation; the architecture does not require a webhook.

---

## 24. Source Authority Is Field-Specific

Avoid one global source ranking.

Examples:

- Hevy may be strongest for sets logged there.
- Explicit user correction may supersede Hevy for a specific set.
- Apple Health / wearable may be stronger for heart-rate time series.
- A wearable “strength” label is not authoritative for exercise/set details.

Each canonical fact should preserve provenance.

---

## 25. Idempotency and Corrections

Preferred external identity:

```text
source_system
source_object_type
source_object_id
source_revision_or_hash
```

Exact replay:

```text
NO_OP_DUPLICATE
```

Explicit correction:

```text
patch same canonical entity
preserve stable ID
append before/after correction event
```

If a chat-recorded workout later arrives from Hevy, reconciliation should merge/associate evidence rather than duplicate the session.

---

## 26. Exercise Catalog / Mapping

Provider exercise identity and KineticLoop semantic identity must be separated.

```text
provider exercise
      ↓
SourceExercise
      ↓
versioned mapping
      ↓
CanonicalExercise
      ↓
movement pattern / muscles / equipment
      ↓
BlueprintRoleCompatibility
```

Mapping strategy:

```text
approved exact mapping
      ↓
deterministic alias mapping
      ↓
AI mapping proposal (optional)
      ↓
review / policy approval
      ↓
versioned durable mapping
```

The AI may propose that a new Hevy exercise is compatible with `SQUAT_PRIMARY`, but should not silently create a permanent canonical mapping.

Unknown mapping must **not** cause the workout to disappear.

The system should distinguish:

```text
FACT: user performed this source exercise and these sets
```

from:

```text
INTERPRETATION: this session satisfies Blueprint A role X
```

The first can be recorded immediately; the second can remain unresolved.

---

## 27. Blueprint Resolution

A completed workout receives a resolution such as:

```text
MATCHED_A
MATCHED_B
MATCHED_C
PARTIAL_A
PARTIAL_B
PARTIAL_C
UNPLANNED_STRENGTH
UNRESOLVED
```

Sequence advancement is allowed only for a qualifying completed/resolved A/B/C session.

AI may assist with ambiguous interpretation, but the final resolution workflow must be versioned and auditable.

---

# Part VII — Data Model / PostgreSQL Design

## 28. Schema Principles

Do not reproduce the 35-tab Google Sheet 1:1.

Separate:

1. raw/source facts,
2. canonical facts,
3. durable Program configuration,
4. runtime state,
5. planning/agent evidence,
6. prescriptions/approvals,
7. derived/read models,
8. audit/events.

Use relational typed columns for core identity and frequently queried state; use JSONB for provider payloads, structured agent evidence, rule/config payloads, and non-core extension data.

---

## 29. Core Table Set

### 29.1 Identity / integration

```text
users
source_connections
sync_cursors
raw_source_events
source_artifacts
```

Key concepts:

```text
user timezone
provider connection status
stream cursor/watermark
provider object identity
payload hash
received_at vs observed_at
```

### 29.2 Program

```text
program_versions
schedule_anchors
program_targets
program_rules
strength_blueprints
blueprint_roles
approval_policies
```

Exactly one `ACTIVE` Program Version per user.

Pending change proposals do not modify the active version.

### 29.3 Exercise catalog

```text
exercises
source_exercises
exercise_mappings
exercise_mapping_proposals
blueprint_role_compatibility
```

### 29.4 Training facts

```text
workout_sessions
workout_exercises
strength_sets
cardio_bouts
session_blueprint_resolutions
workout_evidence_links
```

### 29.5 Runtime training state

```text
user_training_state
```

Representative fields:

```text
user_id
last_resolved_strength_blueprint
last_resolved_strength_at
nominal_next_strength_blueprint
state_version
updated_at
```

### 29.6 Health / recovery

```text
health_observations
daily_health_snapshots
readiness_snapshots
health_flags
```

`daily_health_snapshots` is derived/read-optimized; raw observations retain provenance.

### 29.7 Nutrition / body composition

```text
nutrition_days
nutrition_observations
expenditure_observations
body_weight_observations
body_composition_reports
body_composition_measurements
```

Nutrition providers should expose a capability/granularity model, e.g.:

```text
DAILY_ONLY
DAILY_AND_MEAL
FOOD_LEVEL
EXPENDITURE_AVAILABLE
```

Do not assume a provider supports food-level automation unless verified.

### 29.8 Planning / Agent runtime

```text
planning_runs
context_snapshots
agent_runs
agent_tool_calls
agent_proposals
validation_results
```

### 29.9 Daily plans

```text
daily_plan_bundles
training_prescriptions
prescription_items
nutrition_prescriptions
user_overrides
```

### 29.10 Durable change / review

```text
durable_change_proposals
proposal_approvals
```

### 29.11 Audit / async

```text
domain_events
outbox_events
job_runs
dead_letter_items
```

---

## 30. Critical Database Constraints

### Active Program

```sql
CREATE UNIQUE INDEX one_active_program_per_user
ON program_versions(user_id)
WHERE status = 'ACTIVE';
```

### Active daily bundle

```sql
CREATE UNIQUE INDEX one_active_daily_bundle
ON daily_plan_bundles(user_id, local_date)
WHERE status = 'ACTIVE';
```

This does **not** prevent future multi-session/day because a bundle may contain multiple training prescriptions.

### External workout identity

```sql
CREATE UNIQUE INDEX workout_external_identity
ON workout_sessions(user_id, source_provider, provider_workout_id)
WHERE provider_workout_id IS NOT NULL;
```

### Runtime optimistic concurrency

`user_training_state.state_version` is updated using compare-and-swap semantics.

```sql
UPDATE user_training_state
SET ...,
    state_version = state_version + 1
WHERE user_id = :user_id
  AND state_version = :expected_state_version;
```

Zero affected rows means the planning run is stale.

---

## 31. Representative Planning Tables

### `planning_runs`

```text
id UUID PK
user_id UUID
local_date DATE
base_state_version BIGINT
program_version_id UUID
status
trigger_type
input_completeness
created_at
completed_at
```

### `context_snapshots`

```text
id UUID PK
planning_run_id UUID
core_context JSONB
context_hash TEXT
schema_version TEXT
created_at
```

### `agent_runs`

```text
id UUID PK
planning_run_id UUID
agent_type
model_provider
model_name
prompt_version
schema_version
status
latency_ms
token_usage JSONB
created_at
```

### `agent_tool_calls`

```text
id UUID PK
agent_run_id UUID
tool_name
arguments JSONB
result_reference JSONB
result_hash TEXT
state_version_seen BIGINT
started_at
completed_at
```

### `agent_proposals`

```text
id UUID PK
agent_run_id UUID
proposal_type
payload JSONB
schema_valid BOOLEAN
created_at
```

This makes the Agent decision explainable without exposing private chain-of-thought.

---

# Part VIII — Python Backend / Runtime Design

## 32. Chosen Backend Direction

Backend is **Python-first**.

Recommended baseline:

```text
Python 3.12+
FastAPI
Pydantic v2
SQLAlchemy 2
Alembic
psycopg 3
PostgreSQL
OpenAI Python SDK / Responses API
pytest
ruff
pyright or mypy
uv
Docker / Docker Compose
OpenTelemetry
```

### Why Python is acceptable here

KineticLoop’s hardest problems are:

- agent reasoning/evaluation,
- data transformation,
- historical replay,
- health/training analytics,
- typed tool contracts,
- iterative experimentation.

Python is strong for these workflows.

### Required engineering discipline

The project must avoid “dynamic dict soup.”

All API / tool / agent boundaries should use explicit Pydantic models.

Preferred contract flow:

```text
Pydantic domain / API models
      ↓
OpenAPI
      ↓
generated TypeScript / Swift clients where useful
```

---

## 33. OpenAI Integration Decision

### V1: do not depend on OpenAI Agents API

KineticLoop should use:

```text
OpenAI Responses API
+ Function Calling / tools
+ Structured Outputs
+ application-owned orchestration loop
```

Reasons:

- canonical state must remain in KineticLoop,
- state/replay semantics must remain application-owned,
- lower vendor/runtime coupling,
- daily planning is a bounded task rather than a days-long managed agent process,
- easier deterministic evaluation and debugging.

OpenAI Agents API may be reconsidered later for workloads where managed long-running execution provides clear value, but it must never become the canonical business state store.

---

## 34. Internal Module Architecture

Start as a **modular monolith + worker**, not microservices.

Suggested Python layout:

```text
kineticloop/
├── apps/
│   ├── api/
│   └── worker/
├── kineticloop/
│   ├── identity/
│   ├── program/
│   ├── training/
│   ├── exercise_catalog/
│   ├── health/
│   ├── nutrition/
│   ├── planning/
│   ├── agents/
│   ├── context_tools/
│   ├── constraints/
│   ├── prescriptions/
│   ├── progression/
│   ├── approvals/
│   ├── integrations/
│   │   ├── hevy/
│   │   ├── oura/
│   │   ├── healthkit/
│   │   └── nutrition/
│   ├── events/
│   └── db/
├── migrations/
├── tests/
├── evals/
├── fixtures/
└── docs/
```

No domain module should call OpenAI directly except through the agent runtime boundary.

No Agent tool should bypass the application/domain layer and execute arbitrary SQL.

---

# Part IX — API / Tool Specification

## 35. External API Sketch

### Resolve / retrieve daily plan

```text
POST /v1/daily-plans/resolve
GET  /v1/daily-plans/{local_date}
```

Representative request:

```json
{
  "local_date": "2026-09-17",
  "trigger": "USER_REQUEST",
  "constraints": {
    "time_available_min": 45,
    "equipment_unavailable": [],
    "explicit_override": null
  }
}
```

### User override

```text
POST /v1/daily-plans/{bundle_id}/override
```

### Manual/chat workout ingestion

```text
POST /v1/workouts/ingest
```

### Durable change proposal

```text
GET  /v1/program-change-proposals
POST /v1/program-change-proposals/{id}/approve
POST /v1/program-change-proposals/{id}/reject
```

Exact REST naming may change; domain semantics are more important than endpoint spelling at this stage.

---

## 36. Internal Agent Tool Contracts

Tools should behave like typed domain queries, not HTTP scraping or general SQL.

Example Pydantic-style conceptual contract:

```python
class GetRecentSessionsInput(BaseModel):
    days: int = Field(ge=1, le=180)
    modality: str | None = None

class SessionSummary(BaseModel):
    session_id: UUID
    local_date: date
    modality: str
    resolved_blueprint: str | None
    status: str
    source: str

class GetRecentSessionsOutput(BaseModel):
    as_of_state_version: int
    sessions: list[SessionSummary]
```

Every tool should have:

- bounded query scope,
- typed arguments,
- typed response,
- authorization by user/planning run,
- provenance/freshness metadata where relevant,
- observability,
- sensible result limits.

---

# Part X — Durable Changes / Human Approval

## 37. Durable Change State Machine

```text
PROPOSED
   ↓
PENDING_APPROVAL
   ├─ REJECT → REJECTED
   └─ APPROVE → create ProgramVersion N+1
                     ↓
                   ACTIVE
```

Until activation, daily planning binds exclusively to the current ACTIVE Program Version.

Pending proposals are invisible to the daily decision context except in explicit review surfaces.

### Auto-approval

Auto-approval may exist, but it is a policy by `change_class`, not a global boolean.

Example change classes:

```text
EXERCISE_SUBSTITUTION_POLICY
TRAINING_FREQUENCY
PROGRAM_PHASE
CALORIE_BASELINE
TARGET_RATE_OF_LOSS
DELOAD_TIMING
```

Exact default auto-approval modes remain a Decision Point.

---

# Part XI — Provider / Integration Architecture

## 38. Integration Principle

Unify the **canonical schema**, not the transport.

```text
Hevy adapter       ─┐
Oura adapter        │
HealthKit bridge    ├─→ normalized domain facts
Nutrition adapter   │
DEXA parser         ─┘
```

External provider capability must be verified before implementation.

Provider-specific limitations should not leak into core domain tables more than necessary.

---

## 39. Hevy

Desired role:

- primary structured strength-workout logging source,
- exercise/source identity input,
- completed set data when available.

Implementation rule:

- do not assume a webhook exists,
- design an adapter that can support polling/cursors if needed,
- preserve provider object IDs and revisions/hashes,
- reconcile edited provider workouts into the same canonical session.

Fallback:

- manual/chat workout ingestion,
- retry/backoff,
- raw payload retention for later replay where permitted.

---

## 40. HealthKit

HealthKit is an iOS-local data source, not a backend webhook bus.

Recommended architecture:

```text
iPhone HealthKit
     ↓
KineticLoop iOS bridge/app
     ↓
Backend health ingestion endpoint
```

The bridge should preserve source provenance and use incremental reads where supported.

P0 backend can use fixtures before the iOS bridge is built.

---

## 41. Oura

Oura integration requires a dedicated compliance/terms review before final implementation.

Do **not** silently assume that raw REST-derived Oura data may be sent to a third-party LLM.

Architecture should support at least these separable concepts:

```text
Oura deterministic ingestion / analytics path
Oura data eligible for AI context (subject to current terms)
```

If AI use of Oura data is restricted or uncertain, fallback behavior is:

- keep permitted deterministic/non-LLM features,
- omit disallowed Oura-derived AI context,
- rely on other permitted health sources,
- lower readiness/context confidence rather than substituting fake/stale data.

No legal conclusion is encoded in this design.

---

## 42. Nutrition / MacroFactor-style Provider

KineticLoop should model provider granularity explicitly.

Do not assume real-time automated access to:

- expenditure,
- meal detail,
- food detail,
- proprietary analytics,

unless officially verified.

A lag-aware expenditure model should distinguish:

```text
last_verified_expenditure
source_effective_date
received_at
freshness
confidence
optional_local_estimate
```

A local estimate is not a verified observation and should not overwrite history when later provider data arrives.

Fallback:

- last verified value + lower confidence,
- body-weight trend and intake facts,
- prevent durable calorie baseline changes when data quality is insufficient.

---

## 43. DEXA / File Ingestion

Recommended flow:

```text
raw report/file
  ↓
immutable object storage
  ↓
structured extraction
  ↓
deterministic type/range/unit validation
  ↓
canonical body-composition facts
  ↓
manual correction when extraction is uncertain
```

Raw artifact hash, extraction version, confidence, and corrections should be retained.

---

# Part XII — Google Sheet Migration

## 44. Current POC Value

The current `Fitness Training Log Manager` is not a trivial log. It already contains operational semantics for:

- Program,
- Weekly Schedule,
- Program Targets,
- Exercise Pool,
- Exercise State,
- Progression State,
- Planner Context,
- Post-Workout Review,
- Readiness Rules / Snapshots,
- Session Prescriptions,
- Prescription Exercises,
- Validator,
- Sessions,
- Strength Sets,
- Cardio,
- Health Flags,
- Coach State,
- Exercise Aliases,
- Source Program Slots,
- Event Log,
- Data QA,
- Planner Evals,
- Workout Ingest Evals.

Migration principle:

> **Preserve semantics and regression behavior; rebuild database constraints and service ownership.**

Do not reproduce spreadsheet formulas as canonical DB state.

---

## 45. Sheet → Production Mapping

| Sheet concept | Production destination |
|---|---|
| Program | `program_versions` |
| Weekly Schedule | `schedule_anchors` |
| Program Targets | `program_targets` |
| Target Status | derived SQL/read model |
| Program Rules | versioned config / Constraint Kernel |
| Exercise Pool | `exercises` |
| Exercise Aliases | `source_exercises`, `exercise_mappings` |
| Source Program Slots | blueprints / blueprint roles |
| Sessions | `workout_sessions` |
| Strength Sets | `workout_exercises`, `strength_sets` |
| Cardio | `cardio_bouts` |
| Readiness Rules | versioned feature/derived-state config |
| Readiness Snapshots | `readiness_snapshots` |
| Health Metric Contract | code/schema contract |
| Session Prescriptions | `daily_plan_bundles`, `training_prescriptions` |
| Prescription Exercises | `prescription_items` |
| Prescription Validator | Constraint Kernel + `validation_results` |
| Planner Context | `planning_runs`, `context_snapshots` |
| Coach State | explicit runtime state tables |
| Coach Decisions | proposals / decisions / events |
| Event Log | `domain_events` |
| Progression State | derived progression service state |
| Exercise State | derived/read model |
| Planner Evals | regression/eval fixtures |
| Workout Ingest Evals | regression/eval fixtures |
| Dashboard / Review tabs | application read models |

---

## 46. Migration Sequence

```text
M0 Snapshot workbook / preserve source
M1 Profile IDs, dates, units, duplicates, corrupt state
M2 Import durable config: Program / rules / schedule / exercises / blueprints
M3 Import canonical workout facts
M4 Import relevant health/body facts where semantically trustworthy
M5 Recompute derived state in production code
M6 Replay existing eval fixtures
M7 Shadow-run Sheet vs Postgres outputs
M8 Switch Postgres to SSOT
M9 Keep Sheet as optional report/export/read-only view
```

Known POC QA failures should become migration regression fixtures, not be silently repaired without trace.

---

# Part XIII — Testing / AI Evaluation

## 47. Testing Layers

### 47.1 Deterministic unit tests

Test:

- sleep aggregation,
- date/timezone semantics,
- rolling windows,
- program activation,
- state transitions,
- idempotency,
- corrections,
- CAS conflicts,
- sequence pointer advancement,
- validation constraints.

### 47.2 Historical replay

Use past canonicalized history to ask:

```text
Given state as it existed then,
what would the current Agent propose?
```

Compare:

- modality,
- blueprint,
- exercise choice,
- progression,
- subsequent actual performance/recovery,
- human/reference judgments.

### 47.3 Agent scenario evals

Mandatory scenarios include:

```text
LONG_SEQUENCE_GAP
SAME_DAY_CROSS_CHAT_REQUEST
RECENT_HEAVY_LOWER_BODY_BUT_GOOD_RECOVERY
LOWER_BODY_SORENESS_AND_POOR_SLEEP
UNKNOWN_HEALTH_DATA
LATE_HEALTH_DATA_AFTER_PLAN
USER_FORCE_REST
UNKNOWN_HEVY_EXERCISE
WORKOUT_REPLAY_DUPLICATE
EXPLICIT_WORKOUT_CORRECTION
STATE_VERSION_CHANGES_DURING_AGENT_RUN
PENDING_PROGRAM_CHANGE
PROTECTED_DAY_WITH_USER_OVERRIDE
EQUIPMENT_UNAVAILABLE
SHORT_TIME_BUDGET
```

### 47.4 “Smartness” evaluation

The system must be evaluated not only for safety but for whether AI is actually adding value.

Measure:

- unnecessary tool calls,
- missed relevant historical context,
- excessive deterministic behavior,
- irrational novelty / exercise rotation,
- inappropriate sequence continuation after long gaps,
- failure to consider conflicting evidence,
- quality of rationale,
- stability across equivalent contexts,
- response sensitivity to truly material changes.

---

## 48. Existing Regression Bugs to Preserve

At minimum:

```text
sleep_core_is_not_total_sleep
completed_cardio_is_not_lost
weekday_does_not_override_sequence
same_day_cross_chat_plan_is_canonical
stale_health_is_not_current_health
wearable_strength_label_does_not_create_sets
workout_replay_is_idempotent
correction_preserves_entity_identity
pending_program_change_is_invisible
state_change_rejects_stale_agent_proposal
unknown_exercise_does_not_drop_workout_fact
long_gap_sequence_is_not_mechanical
```

---

# Part XIV — Observability / Auditability

## 49. Every Plan Should Be Explainable

A single correlation/planning ID should connect:

```text
source data
→ normalized facts
→ state version
→ derived features
→ Agent core context
→ Agent tool calls
→ Agent proposal
→ validation results
→ active plan revision
→ later workout execution
```

Store **reason codes and evidence references**, not private chain-of-thought.

---

## 50. Operational Metrics

Representative metrics:

```text
provider_sync_lag_seconds
provider_sync_failure_rate
input_completeness_rate
planning_runs
planning_stale_rejections
agent_tool_calls_per_run
agent_tool_error_rate
agent_schema_failure_rate
agent_latency
agent_repair_rate
validator_failures_by_code
revisions_per_day
workout_duplicate_rate
exercise_mapping_unresolved_rate
sequence_resolution_unresolved_rate
nutrition_expenditure_age_hours
dead_letter_count
```

---

# Part XV — Security / Privacy

## 51. Baseline Controls

- provider credentials in secret storage,
- TLS in transit,
- DB/storage encryption at rest,
- service-level least privilege,
- no Agent DB credentials,
- Context Gateway uses allowlists,
- minimize raw health data sent to LLMs,
- retention policy for raw provider payloads/files,
- user export/delete capability,
- immutable audit trail for important mutations,
- separate raw health observations from derived coaching features where useful.

Do not pass broad records to an Agent simply because the system possesses them.

---

# Part XVI — Local-First Development Plan

## 52. P0 Must Run End-to-End Locally

Initial development should not require production cloud infrastructure.

Recommended local topology:

```text
Laptop
│
├─ FastAPI API
├─ Python worker
├─ PostgreSQL
├─ minimal CLI or web UI
├─ Context Tool Gateway
├─ Fitness/Nutrition orchestration
└─ local fixtures
        │
        └─ OpenAI API over HTTPS
```

External providers can run in two modes:

```text
FIXTURE
LIVE
```

Example configuration:

```text
HEVY_MODE=fixture|live
OURA_MODE=fixture|live
HEALTHKIT_MODE=fixture|live
NUTRITION_MODE=fixture|live
```

---

## 53. Local Vertical Slice Acceptance

Before cloud deployment, a developer must be able to run one command/workflow that performs:

```text
1. Load program + exercise catalog
2. Ingest previous workout fixture
3. Ingest health/recovery fixture
4. Normalize and compute features
5. Start planning run
6. Fitness Coach receives core context
7. Fitness Coach optionally calls read-only tools
8. Fitness Coach returns structured proposal
9. Constraint Kernel validates
10. Nutrition Coach runs
11. Cross-domain consistency resolves
12. DailyPlanBundle becomes ACTIVE in local Postgres
13. Plan is rendered
14. Simulated workout is ingested
15. Progression/sequence/event state updates
```

This is the first meaningful product milestone.

---

# Part XVII — Development / Rollout Plan

## 54. Phase 0 — Contracts + Canonical Database

Build:

- Python project skeleton,
- Pydantic contracts,
- Postgres schema,
- Alembic migrations,
- Program/exercise import,
- domain events,
- state versioning,
- Sheet migration tooling,
- regression harness.

Exit criterion:

- deterministic regression suite runs without LLM.

---

## 55. Phase 1 — Canonical Training Data

Build:

- workout source adapter interface,
- Hevy adapter or fixtures,
- manual/chat ingestion API,
- workout reconciliation,
- exercise catalog/mapping,
- blueprint resolution,
- sequence state,
- progression facts.

Exit criterion:

- completed workout changes canonical state correctly and idempotently.

---

## 56. Phase 2 — Context & Tool Gateway

Build:

- Core Context Builder,
- typed read-only tools,
- provenance/freshness output,
- tool authorization,
- tool logging,
- result limits,
- state-version awareness.

Exit criterion:

- a model can intelligently inspect historical training without raw DB access.

---

## 57. Phase 3 — Fitness Coach Shadow Mode

Build:

- Responses API orchestration,
- Fitness proposal schema,
- tool-calling loop,
- Constraint Kernel,
- daily rendering contract,
- replay/scenario evals.

Run in shadow/recommendation-only mode first.

Exit criterion:

- Agent passes safety/consistency tests and demonstrates meaningful contextual reasoning beyond deterministic baselines.

---

## 58. Phase 4 — Active Daily Training Plans

Enable:

- canonical active DailyPlanBundle,
- material-event revisions,
- user override,
- low-risk auto-application according to policy,
- stale-plan CAS rejection.

Exit criterion:

- same-day requests return the same canonical plan unless a material revision occurs.

---

## 59. Phase 5 — Health / Recovery Integration

Build:

- HealthKit bridge or fixture path,
- normalized observations,
- sleep semantics,
- readiness feature engine,
- source completeness/freshness gate,
- Oura path subject to verified current integration/compliance rules.

Exit criterion:

- planning works safely under COMPLETE, PARTIAL, and UNKNOWN health data.

---

## 60. Phase 6 — Nutrition Coach

Build:

- nutrition facts,
- weight/expenditure freshness,
- Nutrition Context/tools,
- TrainingDemandContract,
- cross-domain consistency / bounded repair,
- daily nutrition prescription.

Exit criterion:

- training + nutrition decisions are coherent under `FAT_LOSS_PRIORITY` without silently changing durable policy.

---

## 61. Phase 7 — Program Analyst / Durable Review

Build future:

- weekly/monthly analysis,
- plateau detection,
- durable change proposal generation,
- approval UI,
- Program Version activation.

Exit criterion:

- AI can propose medium/long-horizon changes but cannot silently apply them outside configured approval policy.

---

## 62. Cloud Deployment Comes After Local Validation

Recommended rollout:

```text
Local E2E
  ↓
Historical replay
  ↓
Shadow mode
  ↓
Hosted staging
  ↓
Recommendation-only production
  ↓
Low-risk auto-apply
  ↓
Broader automation
```

The exact managed Postgres, worker, scheduler, and cloud runtime remain implementation choices.

A candidate future stack is managed Postgres + containerized Python API/worker, but V1 architecture must not depend on a specific vendor.

---

# Part XVIII — Failure Modes / Fallbacks

## 63. Required Degraded Modes

| Failure | Required behavior |
|---|---|
| LLM unavailable | return existing active plan if still valid; otherwise deterministic conservative fallback or explicit unavailable state |
| Agent malformed output | schema retry if bounded; then fail safely, no activation |
| Too many tool calls | enforce tool budget; request proposal from current evidence or fail gracefully |
| Provider outage | retain cursor; retry/backoff; mark data stale/partial |
| Health data late | plan with explicit partial confidence after deadline; only material late data can trigger revision |
| State changes during Agent run | reject stale proposal via CAS; rerun if needed |
| Unknown exercise mapping | store actual workout fact; mark semantic resolution unresolved |
| Duplicate workout | idempotent no-op |
| Edited provider workout | patch/reconcile same canonical session; emit correction event |
| Pending durable proposal | ignored by daily planning |
| User says rest after plan activated | cancel/supersede plan; persist override; replan under forced-rest constraint |
| Agent/provider integration uncertainty | exclude unsupported data rather than invent behavior |
| Nutrition expenditure stale | lower confidence; use last verified data/optional labeled estimate; block unsafe durable adaptation |

---

# Part XIX — Architecture Change Log from Prior Design

## 64. Rule Engine → Constraint Kernel

**Current Design:** deterministic resolver/rules owned many coaching decisions.  
**Problem:** system felt mechanical and underused AI reasoning.  
**Proposed Change:** deterministic code owns truth/invariants/hard constraints; AI owns most contextual coaching judgments.  
**Migration Impact:** move soft modality/cardio/fatigue rules into Agent context/evals; keep safety/state rules deterministic.

---

## 65. Fixed Context → Progressive Read-Only Tool Access

**Current Design:** Agent consumed one prebuilt immutable context package.  
**Problem:** unusual scenarios require deeper history and cannot always be anticipated by a static context builder.  
**Proposed Change:** give a compact Core Context plus bounded typed read tools; persist tool evidence.  
**Migration Impact:** add Context Tool Gateway, tool contracts, tool-call tracing, result limits, eval coverage.

---

## 66. Deterministic Modality Resolver → AI Modality Decision Inside Hard Eligibility

**Current Design:** deterministic layer selected Strength/Zone2/Recovery/Rest.  
**Problem:** many modality choices are coaching trade-offs rather than safety invariants.  
**Proposed Change:** deterministic features + hard exclusions; Fitness Coach chooses modality.  
**Migration Impact:** replace “final modality” engine with feature/eligibility computation plus Agent decision.

---

## 67. Hard `next_strength_blueprint` → Nominal Sequence Prior

**Current Design:** `next_strength_blueprint` treated as authoritative next session.  
**Problem:** after a long layoff, blindly continuing can be irrational.  
**Proposed Change:** maintain deterministic nominal pointer, but expose continuity strength and allow AI to choose re-entry/reset/alternative blueprint.  
**Migration Impact:** add sequence continuity features and structured `sequence_action` to FitnessProposal; completion still deterministically advances pointer from actual resolved session.

---

## 68. One Active Prescription Per Day → One Active Daily Bundle, Future Multi-Session Children

**Current Design:** database uniqueness on `(user_id, local_date)` active prescription.  
**Problem:** future users may train multiple times/day.  
**Proposed Change:** one canonical active DailyPlanBundle/day containing 0..N TrainingPrescriptions; V1 policy limits N to 1.  
**Migration Impact:** split daily-plan identity from session-prescription identity.

---

## 69. TypeScript-First → Python-First Backend

**Current Design:** TypeScript backend was initially favored for shared types.  
**Problem:** KineticLoop’s agent/data/eval workflow benefits strongly from Python ecosystem; frontend type-sharing is solvable through OpenAPI generation.  
**Proposed Change:** Python/FastAPI/Pydantic backend; typed contracts everywhere; Swift/TypeScript clients generated where useful.  
**Migration Impact:** all design schemas should be expressible as Pydantic models and OpenAPI contracts.

---

## 70. Managed Agent Runtime → Application-Owned Orchestration

**Current Design:** OpenAI Agents API was considered.  
**Problem:** canonical state, replay, orchestration semantics, and vendor coupling should remain under KineticLoop control.  
**Proposed Change:** Responses API + Function Calling / Structured Outputs with an application-owned Python orchestration loop.  
**Migration Impact:** build lightweight Agent runtime abstraction; do not encode business lifecycle in provider-managed state.

---

## 71. Cloud-First → Local-First Vertical Slice

**Current Design:** production managed infrastructure appeared early in the roadmap.  
**Problem:** infrastructure can obscure the most important early question: is the coach actually intelligent and useful?  
**Proposed Change:** local Postgres + FastAPI + worker + fixtures first; cloud after E2E and shadow validation.  
**Migration Impact:** adapters must support fixture/live modes; infrastructure abstractions should remain simple.

---

# Part XX — Open Questions & Decision Points

The following are intentionally **not** decided by this document.

| Decision | Options / trade-off |
|---|---|
| Managed PostgreSQL vendor | Supabase / RDS / Neon / other; operational convenience vs coupling |
| Production worker runtime | Cloud Run / managed workers / VM/container / other |
| Queue implementation | Postgres-backed queue vs managed queue; simplicity vs scale/isolation |
| Scheduler | DB cron / managed scheduler / app worker scheduler |
| Tool-call budget | hard max, token/cost budget, adaptive depth |
| Model selection | one model vs tiered fast/deep models; cost/latency vs reasoning quality |
| Model fallback | alternate OpenAI model/provider vs deterministic fallback only |
| Daily planning deadline | fixed local time vs wake-time-derived vs user-triggered |
| Pre-completeness UX | wait, provisional plan, or plan-on-request with PARTIAL confidence |
| Material revision threshold | explicit event classes + configurable metric thresholds |
| Max revisions/day | fixed small number vs policy-configurable |
| Training-start lock | how much plan can change once the user starts executing it |
| Strength preservation floor | session count / effective sets / performance hybrid |
| Daily calorie corridor | fixed vs training-demand-adjusted within active Program |
| Durable calorie change approval | always manual vs class/threshold-based auto approval |
| Known exercise substitution | auto vs review based on compatibility/risk |
| New exercise mapping | always human vs high-confidence policy approval |
| Sequence gap semantics | continuity feature formula and whether any minimum/maximum hard thresholds exist |
| Readiness classification | keep GREEN/YELLOW/RED as compressed feature vs richer continuous feature model |
| Oura AI data path | must be revalidated against current official terms/capabilities before implementation |
| Nutrition provider | exact provider and available automation granularity |
| Local TDEE estimator | none initially vs labeled estimate with confidence/reconciliation |
| Multi-session/day policy | session slots, same-day fatigue dependencies, nutrition coupling |
| Auto-approval per change class | default modes need explicit product decision |
| User override scope | day-only, session-only, duration, persistence across replans |
| Privacy / retention | raw provider retention duration and LLM context minimization policy |
| Web UI | CLI/minimal admin first vs user-facing web first |
| iOS timing | early HealthKit bridge vs fixture-first backend development |

---

# Part XXI — Locked Architecture Decisions

Unless explicitly reopened, reviewers should treat these as accepted:

```text
ADR-001  PostgreSQL is the production canonical state store.
ADR-002  Google Sheet is migration input and later optional view/export, not production SSOT.
ADR-003  Backend is Python-first.
ADR-004  V1 uses FastAPI + Pydantic-style typed contracts.
ADR-005  OpenAI Agents API is not a core V1 dependency.
ADR-006  V1 uses application-owned orchestration around Responses API/tools/structured outputs.
ADR-007  LLMs are proposal generators and contextual decision-makers, not canonical-state writers.
ADR-008  Agents may actively query bounded read-only context tools.
ADR-009  Agents never receive arbitrary SQL access.
ADR-010  Constraint Kernel owns truth, state consistency, permissions, hard constraints, and approvals—not general coaching judgment.
ADR-011  Fitness Coach chooses modality inside hard eligibility constraints.
ADR-012  A/B/C nominal sequence is a prior; long gaps may trigger AI re-entry reasoning.
ADR-013  Only completed/resolved A/B/C sessions advance nominal sequence.
ADR-014  Hevy/manual/chat workout evidence converges through one canonical ingestion pipeline.
ADR-015  Wearable labels never fabricate strength set details.
ADR-016  `FAT_LOSS_PRIORITY` is the primary program objective below health/safety and approved hard constraints.
ADR-017  Durable Program changes require approval or an explicit change-class auto-approval policy.
ADR-018  Pending durable proposals are invisible to daily planning.
ADR-019  Daily plan history is revisioned; previous plans are not overwritten.
ADR-020  Data model supports future multiple sessions/day; V1 policy allows one planned training session/day.
ADR-021  Planning uses optimistic concurrency/state versions and rejects stale proposals.
ADR-022  Late provider data triggers revisions only when materially decision-relevant.
ADR-023  V1 is built and validated locally end-to-end before production cloud rollout.
ADR-024  Production starts as modular monolith + worker, not microservices.
ADR-025  Existing workbook behavior/evals become regression fixtures.
```

---

# Part XXII — Definition of “Production-Ready Enough to Start Coding”

The architecture is ready for implementation when the next spec pass freezes:

1. initial Postgres DDL,
2. Python package/module boundaries,
3. Pydantic contracts for Core Context and Agent proposals,
4. Context Tool contracts,
5. Constraint Kernel rule registry categories,
6. DailyPlanBundle lifecycle,
7. Workout ingestion state machine,
8. sequence resolution/advancement state machine,
9. Program proposal/approval state machine,
10. Sheet migration mapping + reconciliation rules,
11. local Docker Compose/dev workflow,
12. initial regression/eval dataset,
13. provider adapter interfaces,
14. observability/event conventions.

After these are frozen, engineering can implement Phase 0–2 without waiting for every external provider decision.

---

# Appendix A — Short Mental Model

```text
The Program defines long-horizon intent.
Canonical state defines what actually happened and what is currently active.
Deterministic feature code calculates trustworthy facts.
The Context Gateway gives AI enough evidence to reason intelligently.
The Fitness Coach decides how training should adapt today.
The Nutrition Coach decides how daily fueling should adapt today.
The Constraint Kernel prevents invalid, unauthorized, or unsafe state transitions.
The Orchestrator commits only validated decisions.
Workout ingestion records what really happened.
Progression and review feed the next decision cycle.
The Event Log explains every meaningful change.
```

The core philosophy is:

> **Mechanical systems make KineticLoop trustworthy. AI reasoning makes KineticLoop useful.**

---

# Appendix B — Source / Context Notes

This document consolidates and updates the project design from:

- `Personal_Fitness_Coach_Full_Handoff_2026-09-16.md`
- `健身计划制定指南.txt`
- `Fitness Training Log Manager` Google Sheet
- architecture decisions made in the subsequent KineticLoop design discussion

Important semantic rule:

- the historical training guide provides structural program intent,
- the Google Sheet provides POC semantics, operational history, and regression cases,
- the latest architecture decisions in this document supersede conflicting legacy implementation choices.

External provider API/legal capability details are intentionally isolated and must be re-verified against current official documentation before final provider implementation.
