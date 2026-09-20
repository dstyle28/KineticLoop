# KineticLoop — Acceptance & Release Gates v1.2.1

## 1. Current evidence status

Protocol v1.2 and DB logical schema v0.2 remain frozen implementation baselines. Development and production acceptance remain separate from the historical bounded-model claim.

The historical freeze artifacts declare: 34/34 original model cases, 18/18 supplemental boundary cases, 9 interleaving scenarios, 589 complete schedules, 2,997 prefixes, and 8/8 seeded mutants. In this development handoff, the available report is bundled and hashed, but the model source and detailed `model_report.json` are not available; therefore this package does **not** claim independent reproduction of those numbers.

Real PostgreSQL DC, process WF, API/E2E and live LLM obligations remain NOT_RUN until implemented.

## 2. Requirement-set model

### 2.1 Original frozen acceptance specs

The 34 original E/D/A/W/R specs remain unchanged. Their declared layers expand to **67 separate test obligations**. A test ID is not globally PASS until every release-required declared layer has evidence.

### 2.2 Supplemental production boundary requirements

The release registry additionally tracks stable `B01–B18` requirements covering Factset build/seal barriers, SafetyRegistry relevant/unrelated artifact behavior, validity closure, emergency-revoke time semantics, registry outage/fresh-read behavior, CONTINUE/RESUME rechecks, transitive artifact closure and explicit TIMELESS validity. These are production requirements; historical P01–P18 model-case PASS does not auto-pass them.

### 2.3 Named interleaving requirements

`I01–I09` track the nine named races:

1. publish vs user revoke;
2. START vs user revoke;
3. cancel vs DISPATCH_INTENT;
4. lease takeover vs commit with clock;
5. artifact revoke vs issue;
6. artifact revoke vs START;
7. artifact revoke vs publish;
8. factset seal vs input update;
9. dependency expiry vs START.

At minimum these require real PostgreSQL DC evidence; selected cases also require WF/E2E evidence as specified in the machine-readable acceptance file.

## 3. Shadow/test acceptance gate

Before real-data shadow is considered usable:

- an isolated test-only full T6/T7 demo proves valid authorization → START succeeds → revoke/expiry blocks later execution;
- test authorization cannot be consumed by a production subject/role;
- real-data shadow writes only evaluation artifacts and never switches S38, issues S42, writes S45, or presents `AI_GENERATED_CURRENT`;
- Fitness/Demand/Nutrition dependency semantics remain complete even while Nutrition is a deterministic fixture.

## 4. Auto-activation gate

Production auto-activation requires:

1. frozen protocol implemented without semantic weakening;
2. all release-required 67 original layer obligations PASS;
3. all release-required B and I requirements PASS;
4. complete policy bundle for each auto-authorized action;
5. authorization/revoke/degraded UX evidence;
6. independent STOP/control capacity;
7. exact model/prompt/tool/runtime/policy release binding;
8. privacy/subject isolation/outbound-data/log-redaction evidence;
9. observability and rollback operational;
10. every gate result bound to requirement-set version/hash, code revision, migration version, policy/release identity and evidence artifact.

`NOT_RUN` and `SKIPPED` are failures to satisfy a required gate. `N/A` is allowed only with an approved release-scope rationale recorded in the gate artifact.

## 5. Durable-change gate

Automatic durable Program changes remain higher-risk and require intervention/execution/adherence/outcome semantics, result windows, evaluation metrics, monitoring, rollback and explicit change-class policy beyond the daily-plan gate.

## 6. Default safe configuration

`LOCAL_SHADOW / deny-by-default`: production issuance disabled, durable auto-approval disabled, empty fallback catalog, offline START disabled, missing evidence/envelope policies deny permission expansion, and real-data shadow remains `SHADOW_ONLY / NOT_EXECUTABLE`.
