# KineticLoop Development Docs v1.2.2 — Release Notes

Status: development documentation refresh. Frozen Protocol v1.2 and DB Schema v0.2 semantics are unchanged.

## Added

- Provider-level `Integration & Data Source Specification v0.1`.
- Machine-readable Integration Matrix and Integration Acceptance requirements.
- Explicit V1 source scope: manual/chat baseline, Hevy + HealthKit launch targets, Oura conditional/non-blocking.
- Provider-specific ingestion, correction, freshness, provenance, cross-source reconciliation and degradation behavior.
- Oura AI/compliance gate; deterministic adapter work may proceed while production AI exposure remains denied.
- HealthKit permission-ambiguity contract and observer/anchored incremental-sync design.
- Hevy workout-event polling/reconciliation and exercise mapping contract.
- Backlog v0.3 with integration work packages KL-060–KL-066.

## Unchanged frozen authority

- `05_KineticLoop_Protocol_v1.2_FROZEN.md`
- `04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md`
