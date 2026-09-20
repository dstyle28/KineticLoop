# KineticLoop v1.2 — Development Documentation Package

This package is the consolidated pre-development handoff for KineticLoop.

## Status

- Protocol: **FROZEN**
- Logical DB schema: **FROZEN implementation baseline**
- Development: **NOT STARTED**
- PostgreSQL DDL: **NOT YET GENERATED**
- Production auto-activation: **DISABLED**
- Default mode: **LOCAL_SHADOW / deny-by-default**

## Recommended reading order

1. `00_KineticLoop_Master_Spec_v1.2_FROZEN.md` — one-file integrated handoff.
2. `01_KineticLoop_PRD_v1.2_FROZEN.md` — product behavior and scope.
3. `02_KineticLoop_System_Design_v1.2_FROZEN.md` — architecture and ownership.
4. `03_KineticLoop_Technical_Spec_v1.2_FROZEN.md` — runtime/contracts/workflow implementation baseline.
5. `05_KineticLoop_Protocol_v1.2_FROZEN.md` — highest-authority frozen protocol semantics.
6. `04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md` — frozen logical schema/write-path baseline.
7. `08_KineticLoop_ADR_and_Change_Control_v1.2_FROZEN.md`.
8. `09_KineticLoop_Acceptance_and_Release_Gates_v1.2_FROZEN.md`.
9. `06_KineticLoop_Project_Plan_v0.1.md` + machine-readable backlog.

## Machine-readable files

- `KineticLoop_DB_Schema_v0.2_Traceability.json`
- `KineticLoop_Acceptance_Spec_v1.2.json`
- `KineticLoop_Project_Backlog_v0.1.json`
- `DOCUMENT_MANIFEST.json`

## Authority rule

If prose conflicts, Frozen Protocol v1.2 wins for evidence, transaction, authorization, failure, and replay semantics. The DB logical baseline is authoritative for the frozen implementation mapping but cannot override the Protocol.
