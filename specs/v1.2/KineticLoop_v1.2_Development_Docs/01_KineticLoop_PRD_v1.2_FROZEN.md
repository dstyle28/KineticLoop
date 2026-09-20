# KineticLoop — Product Requirements Document v1.2 FROZEN Baseline

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
