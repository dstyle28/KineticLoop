# KineticLoop — Project Plan v0.3

状态：**PRE-DEVELOPMENT / READY TO START WITH EXPLICIT BLOCKING GATES**  
协议基线：`DOC-PROTOCOL-V1.2` = `05_KineticLoop_Protocol_v1.2_FROZEN.md`  
逻辑数据基线：`DOC-DB-V0.2` = `04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md`  
当前模式：`LOCAL_SHADOW / deny-by-default`  
生产自动激活：**DISABLED**

> v0.3 incorporates the Development Readiness Review findings without reopening frozen protocol semantics. M1 and non-controversial M2 work may begin immediately; tasks whose contracts depend on shadow/T6, registry locking, acceptance-gate completeness or evidence handoff have explicit entry blockers.

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
- KL-010..KL-018 DDL/contracts/registry/roles/artifacts;
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
