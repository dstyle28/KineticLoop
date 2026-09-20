# KineticLoop — Technical Specification v1.2.1 Development Baseline

**Status:** Development-ready technical baseline; frozen protocol/DB semantics unchanged  
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

Authorization-relevant operations use the frozen registry/user coordination ordering. The registry gate is part of the lock protocol, not an optional SafetyRegistry check:

```text
T3 / T6 / T7:
  SafetyRegistry SHARED gate
    → read fresh committed registry state
    → user coordination state S01
      → user quota buckets (stable key order)
      → planning intents (stable ID order)
      → call reservations (stable ID order)
      → daily plan head
      → execution aggregate
      → exact receipt / remaining rows

T2-GLOBAL revoke:
  SafetyRegistry EXCLUSIVE gate
    → registry revoke/revision commit
  # MUST NOT acquire user S01

User STOP / user-level protective control:
  user coordination path only
  # MUST remain available even if registry/inference paths are degraded
```

A T3/T6/T7 implementation MUST NOT perform a stale registry pre-check, release the gate, and later commit under only S01. Queue/outbox scanning cannot hold its own row lock and then reverse-acquire either coordination gate.

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

```text
RESERVED
  ├─ CANCELLED_BEFORE_DISPATCH   # mutually exclusive terminal branch
  └─ DISPATCH_INTENT             # network may now occur
       ├─ DISPATCHED → SETTLED | OUTCOME_UNKNOWN
       ├─ SETTLED
       └─ OUTCOME_UNKNOWN
```

1. Reserve slot/resource upper bound in a short transaction.
2. Revalidate lease/fence/request/deadline and atomically choose either cancellation or `DISPATCH_INTENT`.
3. Only the first successful `DISPATCH_INTENT` transition winner may perform exactly one physical network request outside the transaction.
4. Settle actual usage or retain `OUTCOME_UNKNOWN`. A replayed permit receipt is diagnostic/idempotent evidence and MUST NOT authorize a second send.

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

The frozen protocol defines 34 original production acceptance specs. Their declared layers expand to **67 distinct `(test_id, layer)` obligations**; every obligation must be tracked separately. The development requirement set also includes supplemental frozen-boundary requirements and nine named interleaving requirements covering SafetyRegistry, validity closure, Factset sealing and dispatch/lease races.

`NOT_RUN` and `SKIPPED` are never equivalent to PASS. `N/A` requires an approved release-scope rationale. The bounded offline model evidence remains historical evidence only; it does not promote any real-stack PU/DC/WF/E2E obligation to PASS.

## 23. First implementation vertical slices

### 23.1 Protocol demonstration — isolated test authorization

Before real AI, run a deterministic full T6/T7 path in a dedicated test database or explicitly test-scoped subject/policy:

```text
seed test user/program/evidence
→ seal factset
→ compute projections
→ publish DecisionManifest
→ create PlanningIntent
→ deterministic Fitness + Demand + Nutrition fixture
→ evidence resolution + validation
→ T6 commit test bundle + simulated test-only Authorization A1
→ assert is_executable(A1) and START succeeds
→ revoke / expire dependency
→ assert CONTINUE/RESUME/new START fail
→ inspect audit + replay
```

This path proves transaction/authorization semantics. Its credentials, subjects and authorization scope are rejected by production paths.

### 23.2 Real-data shadow evaluation — no live commit

Real user/provider data may later drive the real Fitness Coach, but shadow evaluation does **not** call live T6 bundle/head success semantics:

```text
real admitted evidence / current Manifest
→ isolated shadow-evaluation run
→ Fitness proposal
→ PrescriptionDemandFeatures
→ fixture Nutrition until M8, then real Nutrition
→ evidence resolution + validation
→ persist evaluation artifacts/comparison metrics only
→ return SHADOW_ONLY / NOT_EXECUTABLE in debug/eval surfaces
```

Shadow evaluation MUST NOT switch S38, issue S42, create S45, reserve real planned exposure, or appear in ordinary executable plan retrieval. If a future design needs production-head shadow bundles, that is a protocol/ADR change.

### 23.3 Artifact and security prerequisites

Before real data leaves the local process for a model/provider, record exact model/prompt/tool/runtime/policy artifact identities, use test/production role separation, test subject isolation, secret/config separation, and verify outbound-data/log-redaction policy.

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
