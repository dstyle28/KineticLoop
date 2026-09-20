# KineticLoop — Architecture Decisions & Change Control v1.2.1 Development Baseline

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

## 5. Development-readiness implementation decisions

These decisions refine implementation/documentation without changing frozen protocol semantics:

- **ADR-025 — Shadow split:** real-data shadow evaluation is noncanonical/non-executable and MUST NOT switch the live daily head or create production authorization. Complete T6/T7 demonstrations use isolated test-only subjects/policies.
- **ADR-026 — Canonical gate ordering:** T3/T6/T7 use SafetyRegistry shared gate before S01; T2-GLOBAL uses the registry exclusive gate and no S01; user STOP/control does not depend on registry availability.
- **ADR-027 — Acceptance requirement set:** release evidence tracks every original `(test_id, layer)` obligation independently, plus supplemental frozen-boundary requirements and named interleavings. `NOT_RUN`/`SKIPPED` never mean PASS.
- **ADR-028 — Early release/security foundation:** minimal artifact identity, subject/test/admin isolation, replay isolation, outbound-data/log-redaction controls and fixed evaluation fixtures arrive before real-data remote AI, not only in final staging.
- **ADR-029 — Provider-scope decoupling:** staging/release evaluation depends on an explicit V1 `launch_source_scope`; optional adapters do not block M10 unless promoted to launch scope.
- **ADR-030 — Evidence handoff honesty:** historical bounded-model PASS remains declared freeze evidence, but the development package MUST state whether source/report fixtures are actually bundled and independently reproducible.
