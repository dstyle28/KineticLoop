# KineticLoop v1.2 FROZEN — Release Notes

## Decision

Protocol v1.2 is now **FROZEN** for implementation. Development has not started. Production prescription auto-activation remains disabled.

## Frozen artifacts

- `KineticLoop_v1.2_Protocol_FROZEN.md`
- `KineticLoop_DB_Schema_Design_v0.2_FROZEN.md`
- `KineticLoop_DB_Schema_v0.2_Traceability.json`
- `KineticLoop_Acceptance_Spec_v1.2.json`
- `KineticLoop_Protocol_Freeze_Review.md`

## Freeze clarification added

Artifact revocation is execution-invalidating from the successful commit of the T2-GLOBAL revoke transaction. `effective_at` is audit/business semantics only in v1; it cannot retroactively rewrite past authorization and cannot schedule future revocation.

## Model evidence

The bounded offline model is PASS: 34/34 original cases, 18/18 boundary cases, 9 interleaving scenarios, 589 complete schedules, 2,997 visited prefixes, 8/8 seeded mutants detected. Real PostgreSQL tests, process fault tests and live LLM calls remain zero.

## Next

Follow `KineticLoop_Project_Plan_v0.1.md`. First engineering outputs are PostgreSQL DDL, Pydantic command/domain contracts and real PostgreSQL concurrency tests.
