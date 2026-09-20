# KineticLoop — Acceptance & Release Gates v1.2 FROZEN

## 1. Current evidence status

Protocol v1.2 is frozen for implementation, not validated for production auto-activation.

The bounded offline protocol model passed its encoded suite: 34/34 original acceptance model cases, 18/18 additional boundary cases, 9/9 critical interleaving scenarios, 589 complete schedules, 2,997 visited prefixes, 0 model-level deadlock/invariant violations, and 8/8 seeded negative mutants detected.

This does **not** substitute for real PostgreSQL concurrency tests, process crash/fault injection, API/E2E tests, provider integrations, or live LLM evaluation. Production auto-activation remains disabled.

## 2. Production acceptance categories

### Evidence

Must prove, among other cases, that planned sets never fabricate actuals; unresolved risk cannot disappear; duplicate sources do not multiply underlying events; ambiguous event association remains ambiguous; unknown exposure is not zero; contradiction cannot be cherry-picked; corrections withdraw action basis; and summaries cannot acquire command authority.

### Decision publication

Must prove projection completion does not bump generation; projection reuse is dependency-based; unpublished inputs cannot leak through tools; absence dependencies are tracked; and urgent revoke wins against stale Manifest publication.

### Authorization

Must prove revoke precedes replan; stale Manifest cannot reauthorize after epoch change; START/revoke linearizes; expiry needs no background job; reauthorization does not rewrite history; fallback is not privileged; STOP works under queue saturation; and unauthorized actuals are still recorded truthfully.

### Workflow

Must prove crashes do not refund possibly dispatched external budget; cancel/dispatch permit is atomic; every physical SDK retry is accounted; single-flight does not swallow new constraints; old workers cannot commit after fence takeover; late results cannot reopen terminal intents; Fitness changes invalidate dependent Nutrition; commit ACK loss is idempotent; and search failure is not misreported as proven infeasibility.

### Replay

Must prove future corrections and future personal mappings are excluded by historical cutoff, replay modes stay distinct, and replay cannot mutate live production state.

## 3. Auto-activation gate

Production auto-activation is allowed only after:

1. Frozen protocol is implemented without semantic weakening.
2. All relevant 34 acceptance tests pass at specified PU/DC/WF/E2E layers.
3. A complete production policy bundle is published for the actions being auto-authorized.
4. Authorization audit and degraded-mode UX are validated.
5. Safety/control channel has independent capacity and tested failure behavior.
6. Release evaluation binds exact model/prompt/engine/policy artifacts.
7. Observability and rollback are operational.

## 4. Durable-change gate

Automatic durable Program changes have a higher gate than daily prescription generation. Before enabling them, intervention/execution/adherence/outcome semantics, result windows, evaluation metrics, monitoring, rollback, and change-class policy must be implemented and validated.

## 5. Default safe configuration

The frozen development baseline remains `LOCAL_SHADOW / deny-by-default`: no production issuance, no durable auto-approval, empty fallback catalog, offline START disabled, and unconfigured evidence/envelope requirements deny permission expansion.
