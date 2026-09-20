# KineticLoop Task Thread Index — Harness v0.2 / hardening v0.3

Current machine source: `KineticLoop_Harness_Backlog_v0.2.json`.

| Task | Milestone | Status | Refinement | Depends on |
|---|---|---|---|---|
| KL-001 — Initialize Python repo/tooling/CI | M1 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | — |
| KL-002 — Local PostgreSQL Docker/test DB lifecycle | M1 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-001 |
| KL-003 — Canonical ID/time/hash utilities | M1 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-001 |
| KL-004 — Error registry + command receipt base contracts | M1 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-003 |
| KL-005 — Acceptance requirement registry + fixture generator | M1 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-001 |
| KL-006 — Stable document index + evidence handoff manifest | M1 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-001 |
| KL-007 — Subject/test/admin/evaluation role vocabulary | M1 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-001 |
| KL-008 — Shadow/test semantic contract | M1 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-005, KL-007 |
| KL-009 — Secret/config separation + synthetic data/log-redaction harness | M1 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-001, KL-007 |
| KL-010 — Physical schema dependency topology | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-002, KL-003 |
| KL-011 — Typed canonical fact child-table design | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-010 |
| KL-012 — Immutable history + write-permission protections | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-010, KL-007 |
| KL-013 — Alembic baseline migration | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-010, KL-011, KL-012 |
| KL-014 — Pydantic T1-T8 command/result contracts | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-004, KL-008 |
| KL-015 — Repository transaction interfaces | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-013, KL-014, KL-016 |
| KL-016 — SafetyRegistry shared/exclusive gate contract | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-010 |
| KL-017 — Production/test/evaluation subject isolation in persistence | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-007, KL-013 |
| KL-018 — Minimal artifact registry/release identity | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-013, KL-016 |
| KL-055 — Provider identity + EvidenceEnvelope + adapter interface | M2 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-003, KL-014 |
| KL-019 — Minimal publish/commit/start protocol execution slice | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-017, KL-020, KL-021, KL-022, KL-023, KL-024, KL-025 |
| KL-020 — S01 coordination + command idempotency | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-015 |
| KL-021 — SafetyRegistry T2-GLOBAL implementation | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-016, KL-018, KL-020 |
| KL-022 — Authorization evaluator + validity closure | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-015, KL-018, KL-021 |
| KL-023 — Factset build/ready/seal | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-015 |
| KL-024 — Planning intent + lease/fencing minimal implementation | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-015 |
| KL-025 — Call reservation ledger + dispatch permit | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-024 |
| KL-026 — Nine interleavings on real PostgreSQL | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-019 |
| KL-027 — Full deterministic test-only T6/T7 protocol demo | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-017, KL-019, KL-022, KL-023, KL-024, KL-025 |
| KL-028 — Supplemental B01-B18 production boundary suite | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-021, KL-022, KL-023, KL-027 |
| KL-029 — Shadow isolation enforcement | M3 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-008, KL-017, KL-027 |
| KL-036 — Worker lease/fencing + independent reaper | M4 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-024, KL-026 |
| KL-037 — Transactional outbox dispatcher + idempotent consumers | M4 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-020 |
| KL-038 — Physical-request fault injection and UNKNOWN budget suite | M4 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-025, KL-036 |
| KL-039 — Independent STOP/control execution lane + safety metrics | M4 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-021, KL-036 |
| KL-030 — Evidence receive/assertion/admission | M5 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-027 |
| KL-031 — Workout actual typed schema | M5 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-011, KL-030 |
| KL-032 — Event association/dedup | M5 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-030 |
| KL-033 — Sequence/progression/exposure projections | M5 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-031, KL-032 |
| KL-034 — Correction invalidation propagation | M5 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-033 |
| KL-035 — Google Sheet migration staging/import | M5 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-009, KL-031, KL-032 |
| KL-056 — Cross-source workout/recovery reconciliation harness | M5 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-030, KL-032, KL-055 |
| KL-040 — DecisionManifest + snapshot | M6 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-033, KL-021 |
| KL-041 — Context tool gateway | M6 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-040 |
| KL-042 — FitnessProposal contracts | M7 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-014, KL-041 |
| KL-043 — Responses API adapter with ledger-controlled calls | M7 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-025, KL-018, KL-042 |
| KL-044 — Evidence resolver + validation | M7 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-041, KL-042 |
| KL-045 — Real-data shadow evaluation store/API | M7 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-008, KL-029, KL-043, KL-044 |
| KL-046 — Historical planning replay | M7 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-040, KL-044 |
| KL-047 — Fixed predeclared Fitness eval set + scorer | M7 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-005, KL-018 |
| KL-048 — Remote-context outbound/redaction gate | M7 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-009, KL-018, KL-041 |
| KL-049 — Nutrition Agent + bounded cross-domain repair | M8 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-042, KL-043, KL-044, KL-047 |
| KL-050 — Publish launch_source_scope and provider capability registry | M9A | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-055 |
| KL-051 — Hevy adapter: workout events, corrections, exercise mapping | M9A | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-050, KL-055, KL-030, KL-032 |
| KL-052 — Apple HealthKit iOS bridge: anchored sync, deletions, provenance | M9A | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-050, KL-055, KL-030 |
| KL-059 — Launch-source degradation and outage suite | M9A | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-050, KL-051, KL-052, KL-056 |
| KL-053 — Oura adapter placeholder (superseded by KL-057) | M9B | SUPERSEDED | MUST_REFINE_BEFORE_READY | KL-057 |
| KL-054 — Optional nutrition/DEXA imports placeholder (superseded by KL-058) | M9B | SUPERSEDED | MUST_REFINE_BEFORE_READY | KL-058 |
| KL-057 — Oura deterministic adapter + AI/compliance gate | M9B | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-055, KL-040 |
| KL-058 — Nutrition/body import contracts (MacroFactor export + DEXA) | M9B | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-055, KL-030 |
| KL-060 — Staging observability/SLOs | M10 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-043, KL-045 |
| KL-061 — Release registry + full eval/replay hardening | M10 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-047, KL-060 |
| KL-062 — Shadow comparison + reproducible release evidence bundle | M10 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-061, KL-045, KL-049, KL-059 |
| KL-063 — Leakage audit + point-in-time replay validation | M10 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-046, KL-061 |
| KL-064 — Operational dashboards for revoke, ledger, tool and sync health | M10 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-036, KL-037, KL-038, KL-059 |
| KL-065 — Security/privacy integrated staging review | M10 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-048, KL-062 |
| KL-066 — Release gate runner + evidence verifier | M10 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-005, KL-028, KL-062, KL-063, KL-064, KL-065 |
| KL-070 — Integrated auto-activation evidence review | M11 | NOT_STARTED | MUST_REFINE_BEFORE_READY | KL-061, KL-028 |
| KL-071 — Independent protocol/security/reliability launch review | M11 | NOT_STARTED | READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED | KL-066, KL-070 |
