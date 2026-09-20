# KineticLoop Harness Development Workflow v0.2

This file is explanatory only. **Scheduling authority is `KineticLoop_Harness_Backlog_v0.2.json` plus gate/resource state.**

Typical initial wave after KL-001 merges:
- KL-002 local PostgreSQL isolation
- KL-003 canonical IDs/time/hash
- KL-005 requirement registry
- KL-006 current document/evidence index
- KL-007 role vocabulary
- KL-009 secret/redaction harness

Do not treat this list as a READY list. The orchestrator computes readiness from merged dependencies, applicable gates, `packet_refinement`, and resource conflicts.

M2 write concurrency must respect `migration_chain`, `command_contracts`, `registry_coordination` and explicit write paths. M3 interleavings run only after KL-019 provides the minimal real-DB publish/commit/start path.
