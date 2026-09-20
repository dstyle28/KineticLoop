# KineticLoop — Technical Specification v1.2 FROZEN Baseline

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
