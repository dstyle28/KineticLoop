# KineticLoop — Project Plan v0.6 (Harness Contract Hardened)

状态：**PRE-DEVELOPMENT / HARNESS-CONTRACT-HARDENED / THREAD-PER-TASK**  
协议基线：`DOC-PROTOCOL-V1.2` = `05_KineticLoop_Protocol_v1.2_FROZEN.md`  
逻辑数据基线：`DOC-DB-V0.2` = `04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md`  
当前模式：`LOCAL_SHADOW / deny-by-default`  
生产自动激活：**DISABLED**

> v0.6 incorporates the Harness audit hardening: current document/requirement identity, namespaced historical task IDs, committed result/review artifacts, separate task-vs-requirement state, resource-key scheduling, worktree DB isolation, gate-builder exceptions, conditional provider dependencies, and an explicit minimal publish/commit/start slice before interleaving tests. Frozen Protocol/DB semantics are unchanged.

## 0. Harness execution contract

This plan is executed with **one task = one independent agent thread = one Git worktree = one pull request**. The orchestrator thread is not an implementation thread. It admits ready tasks, supplies minimal context packets, tracks dependencies, runs merge gates, and records decisions.

A task thread starts from a clean branch/worktree and receives only:

1. root `AGENTS.md`;
2. its generated task packet under `docs/exec-plans/active/`;
3. the small list of referenced canonical docs in that packet;
4. repository code/tests relevant to the task.

It MUST NOT depend on prior chat history. Cross-thread knowledge becomes real only after it is committed as code, tests, docs, ADR, generated schema, or evidence. A thread that discovers a missing protocol decision stops and emits a `SPEC_CHANGE_REQUEST`; it does not invent authority semantics locally.

### 0.1 Thread lifecycle

```text
READY task
  → create worktree + fresh thread
  → read task packet
  → inspect only necessary references
  → implement + test
  → self-review
  → commit task result in PR
  → independent review bound to PR head
  → merge gate
  → merge / integration record
  → unlock dependent tasks
```

### 0.2 Context discipline

- `AGENTS.md` is a map, not the encyclopedia.
- Never preload the entire Master Spec into every coding thread.
- Frozen Protocol/DB sections are opened on demand based on `invariant_ids`, `transaction_boundaries`, and `table_ids` in the task packet.
- Raw test logs stay in the task thread/evidence files; dependent threads consume summaries and committed artifacts.
- When a task grows beyond one reviewable PR or starts touching a second independent concern, split it into child tasks before continuing.

### 0.3 Parallelism

Read-only exploration/review can be highly parallel. Write tasks may run in parallel only if dependencies are satisfied and their expected write sets do not overlap critical coordination surfaces. Tasks touching S01/S27/S31/S38/S42/S49–S51 or the same migration file are serialized unless an explicit integration plan says otherwise.

### 0.4 Milestone rule

A milestone is not a long-running thread. It is a **merge/evidence checkpoint** over a set of task threads. Milestone completion is computed from merged task results and required acceptance evidence.

## 1. Execution strategy

The first implementation goal is not an AI chat UI. It is a reproducible local protocol slice with real PostgreSQL, exact audit artifacts, and failure evidence. Two paths are intentionally separate:

```text
A. protocol demo (test-only): full T6/T7 + simulated authorization
B. real-data shadow: proposals/evaluation only; no live head/authorization
```

A developer must never make path B pass by adding `if shadow: skip_authorization` inside live CommitBundle.

## 2. Locked stack

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x, psycopg 3, Alembic, PostgreSQL.
- pytest / pytest-asyncio; Hypothesis for state/property tests.
- Ruff + Pyright or Mypy; uv.
- Docker Compose local-first.
- OpenAI Responses API + typed tools/structured outputs; **no OpenAI Agents API core runtime**.
- OpenTelemetry + structured logs; Sentry candidate for staging/production.

## 3. Cross-cutting entry gates

### G-FOUNDATION
Before M2 command/transaction implementation: stable document IDs, evidence handoff status, 67 original layer obligations plus supplemental/interleaving requirement registry, synthetic fixtures, subject/test/admin role model.

### G-SHADOW
Before KL-014/KL-015/KL-045 or any shadow persistence contract: implement the explicit split between isolated test authorization and non-executable real-data shadow evaluation.

### G-REGISTRY
Before T3/T6/T7 implementation: repository/transaction contract must encode `SafetyRegistry shared → S01` and T2-GLOBAL exclusive registry semantics; user STOP must not depend on registry.

### G-REALDATA
Before importing the real Google Sheet or retaining real health/training data: subject isolation, access scope, secrets, retention/logging behavior and redaction tests exist.

### G-REMOTE-AI
Before sending real context to a remote model: exact release/artifact identity, outbound-data allowlist/redaction, fixed evaluation subset, refusal/bad-output/timeout cases and input/output evidence capture exist.

## 4. Milestone roadmap

### M0 — Frozen protocol/schema baseline [DONE]
Frozen Protocol v1.2 and DB logical schema v0.2 remain authoritative. Historical bounded-model PASS is retained as declared evidence, not production validation.

### M1 — Engineering foundation + evidence/traceability handoff
Deliverables:
- repo/bootstrap, uv, lint/type/test CI;
- Docker PostgreSQL + deterministic test DB lifecycle;
- canonical IDs/time/hash/error registry;
- stable `DOCUMENT_INDEX.json`;
- evidence manifest binding available report/hash and explicitly marking missing model source/report JSON as unresolved evidence handoff;
- acceptance registry: original 34 → 67 layer obligations + supplemental boundary IDs + nine interleavings;
- complete typed backlog records for M1/M2 and rolling records thereafter;
- subject/test/admin/evaluation role vocabulary; config/secret separation; synthetic fixtures.

Exit evidence:
- clean checkout starts test environment;
- all M1/M2 tasks have dependencies/DoD/test oracle/evidence paths;
- no claim that bounded model is independently reproducible until source evidence is supplied.

### M2 — Contracts, physical schema roots and transaction design
Do **not** treat logical table numbering as migration order. Build by FK/authority dependency:
1. identity, command receipt, event/outbox roots;
2. policy/program/catalog/artifact identity roots required by downstream FKs;
3. S01 user coordination + S49–S51 SafetyRegistry coordination;
4. evidence/admission/fact/factset roots;
5. projection/Manifest roots;
6. planning/ledger roots;
7. prescription/authorization/execution roots;
8. replay/evaluation roots;
9. remaining domain-specific typed children and indexes.

Deliverables:
- Pydantic command/result contracts;
- explicit command owner, transaction boundary, errors and idempotency;
- registry shared/exclusive gate interfaces;
- migrated-schema SafetyRegistry runtime integration through a non-login command-owner boundary;
- immutable/history write protections;
- role/subject/test-scope restrictions;
- Alembic baseline derived from dependency topology;
- explicit shadow/test-evaluation storage boundary.

Exit evidence:
- schema rebuild from zero;
- migration dependency graph documented;
- no writer can bypass owner/subject guard;
- G-SHADOW and G-REGISTRY closed before affected contracts merge.

### M3 — Minimal real PostgreSQL protocol demonstration
First implement the smallest end-to-end frozen protocol slice, not all 51 domains.

Required positive/negative trajectory:
```text
valid test A1 → is_executable=true → START succeeds
→ revoke / dependency expiry
→ CONTINUE/RESUME/new START denied
```

Use deterministic Fitness + Demand + Nutrition fixtures so T6 dependency semantics remain complete.

Required DC/state evidence includes:
- nine named interleavings;
- READY/SEALED write barriers;
- relevant vs unrelated artifact revoke;
- registry shared-gate fresh read;
- validity closure / missing validity / TIMELESS policy;
- T2-GLOBAL effective_at commit semantics;
- START/revoke/expiry ordering.

Exit: test-only authorization works only in isolated scope; no production subject can use it.

### M4 — Worker/reaper/outbox + real fault boundaries
Deliverables:
- lease/fencing; reservation/DISPATCH_INTENT ledger; independent reaper; outbox;
- process-kill tests for before/after send permission, late results, ACK loss, takeover;
- revoke/lock/unknown-budget metrics;
- STOP/control capacity separate from inference queue.

Exit: faults are induced by process termination/real DB transactions where applicable, not only mocked exceptions.

### M5 — Canonical training data vertical slice
Deliverables: typed workout/session/set/cardio storage; association/dedup; user/chat provenance; progression/sequence/exposure projections; correction invalidation; Sheet migration staging.

Entry: G-REALDATA must close before real Sheet import.
Exit: E01/E03/E04/E05/E07/A08 real-stack evidence without LLM planning.

### M6 — Decision context + read-only tools
Deliverables: Manifest builder, mandatory context, snapshot-bound tools, provenance/freshness/coverage, unpublished-input protection.
Exit: D01–D05 and E06/E08 real-stack evidence; no tool silently crosses input frontier.

### M7 — Fitness Coach real-data shadow evaluation
Entry: G-REMOTE-AI; fixed small evaluation set and predeclared scoring rules exist.

Deliverables:
- Responses API adapter under call ledger;
- structured FitnessProposal; adaptive bounded tool use;
- deterministic PrescriptionDemandFeatures;
- fixture Nutrition with complete F→D→N hash semantics;
- validation/evidence resolution;
- **shadow evaluation artifact only** — no S38 head switch, no S42 production issuance, no S45, no live PlanningIntent success claim;
- refusal, malformed output, timeout, tool failure and budget exhaustion fixtures.

Exit: real-data shadow is reproducible and explicitly `SHADOW_ONLY / NOT_EXECUTABLE`; it cannot displace an active plan.

### M8 — Nutrition Coach + cross-domain reasoning
Replace fixture Nutrition with real Nutrition Agent; preserve F/D/N hash binding, rolling envelopes and shared root budget.
Exit: W07 + corridor-edge/cumulative cases; no silent durable baseline mutation.

### M9A — Launch-scope live provider adapters
Before M9 starts, publish an explicit `launch_source_scope` policy/list. M10 depends only on sources in that list.

Each required adapter must pass receive/idempotency/correction/late-data/provenance fixtures. Manual/chat input remains a supported canonical path.

### M9B — Optional provider extensions [NON-BLOCKING FOR M10]
Oura, additional nutrition sources, DEXA/body-composition and other adapters can proceed independently unless explicitly promoted into `launch_source_scope`.

### M10 — Staging / observability / complete release evaluation
Deliverables: full tracing/SLOs, production release registry, Historical Reconstruction + Current Policy Backtest, larger frozen eval suites, leakage audit, shadow comparison.

M10 is not the first time release identity/replay/security exists; it hardens the minimal capabilities introduced earlier.

### M11 — Integrated auto-activation readiness review
Requires evidence-bound gates, not task-completion claims. All required layer obligations/supplemental/interleaving requirements must have result artifacts tied to exact code/migration/policy/release identities. `NOT_RUN`/`SKIPPED` ≠ PASS; N/A requires approved release-scope justification.

M11 produces a launch recommendation/decision input only; it does not automatically enable production authorization.

## 5. Required implementation tasks

The machine-readable backlog is authoritative for task records. Key tasks include:
- KL-001..KL-009 foundation/evidence/acceptance/shadow/security;
- KL-010..KL-018 plus KL-072 DDL/contracts/registry/migrated-runtime/roles/artifacts;
- KL-020..KL-029 PostgreSQL protocol demo and full boundary/interleaving evidence;
- KL-030..KL-035 canonical data;
- KL-040..KL-048 context/Fitness shadow/eval;
- KL-050+ provider adapters and staging tasks.

Each task record includes `owner_role`, `depends_on`, `commands`, `transaction_boundaries`, `invariant_ids`, `table_ids`, `required_test_layers`, `deliverables`, `definition_of_done`, `entry_conditions`, `status`, and `evidence_refs`.

## 6. First build target

```text
# test-only protocol demo
seed isolated test subject
→ admitted facts / SEALED factset
→ projections / Manifest
→ PlanningIntent
→ deterministic F + D + N fixtures
→ validation
→ T6 test-only P/A
→ START succeeds
→ revoke/expire
→ later execution denied
→ replay/audit evidence

# later real-data shadow
real context → AI proposal → validation
→ isolated evaluation artifact
→ SHADOW_ONLY / NOT_EXECUTABLE
```

This separation is a release invariant for development.


## Integration workstream (development contract)

`DOC-INTEGRATION-V0.1` is an implementation prerequisite for provider adapters.

- **M1/M2:** define ProviderId/StreamId, EvidenceEnvelope, connection status and adapter interface; add provider fixture harness.
- **M5/M6:** implement cross-source reconciliation contracts using synthetic Hevy/HealthKit/manual fixtures.
- **M9A launch scope:** Hevy + Apple HealthKit bridge, plus manual/chat fallback; each adapter must pass source-specific correction/partial-coverage tests.
- **M9B non-blocking:** Oura deterministic adapter, nutrition imports, DEXA. Oura AI exposure remains disabled until INT-06 compliance gate.
- **M10:** staging/shadow evaluation must explicitly test loss of each launch provider and documented degradation behavior.

M10 does not wait for optional M9B sources unless a source is promoted into `launch_source_scope` by ADR.


## Harness task source

The machine-readable task source is `KineticLoop_Harness_Backlog_v0.2.json`. Individual execution packets live in `docs/exec-plans/active/`. The canonical task result schema is documented in `docs/harness/THREAD_RESULT_CONTRACT.md`.

## 12. Harness contract hardening rules

- Current authority is resolved only through `CURRENT_DOCUMENT_INDEX.json`; historical files are explicitly namespaced.
- Task identity is `<backlog namespace>/<display id>`. Display IDs alone are insufficient for historical joins.
- `requirements_covered` and `checks_required_for_this_task` are separate. Task PASS never auto-promotes requirement PASS.
- All tasks require a GENERAL head-bound review; specialist review triggers are packet metadata.
- Parallel writers require non-conflicting `resource_keys` and write paths. DB worktrees require unique DB/Compose namespaces.
- Gate-construction tasks (for example shadow/remote-AI/source-scope gates) are not blocked by the gate they create.
- Optional providers become hard dependencies only if the versioned `launch_source_scope` includes them.
- `KL-019` owns the minimal real-DB PublishManifest/CommitBundle/StartSession slice; `KL-026` tests interleavings against that implementation and may not substitute direct fixture writes.
- Packets marked `MUST_REFINE_BEFORE_READY` cannot be scheduled until their DoD/test oracle/write scope are made concrete.


## Harness Contract Hardening v0.3 addendum

- Independent review is bound to the reviewed implementation SHA, with one narrow REVIEW_RECORD_ONLY suffix exception so review evidence can be committed without self-invalidating.
- Task result is committed before review and is immutable during that review cycle.
- `write_paths` covers implementation scope; own result/review bookkeeping paths are separate standardized allowances.
- KL-001 has an enforceable concrete write set and must implement positive/negative harness fixtures.
- Other M1 tasks remain `MUST_REFINE_BEFORE_READY` until their task-specific write sets are derived from the repo layout established by KL-001.
- A validator PASS must distinguish structural validity from proved negative guard behavior.
