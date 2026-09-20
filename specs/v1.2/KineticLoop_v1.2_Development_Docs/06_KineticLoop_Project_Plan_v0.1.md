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
