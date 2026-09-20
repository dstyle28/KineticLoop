# KineticLoop Development Docs v1.2.1 — Release Notes

This release responds to the Development Readiness Review. Frozen Protocol v1.2 and DB Schema Design v0.2 are byte-preserved and remain authoritative.

## Closed documentation/execution-plan findings

- **F01:** selected explicit shadow semantics: isolated test-only full T6/T7; real-data shadow is evaluation-only/non-executable.
- **F02:** corrected SafetyRegistry shared/exclusive lock ordering and DISPATCH_INTENT state diagram in System/Tech docs.
- **F03:** expanded machine acceptance registry to 67 original layer obligations + B01–B18 + I01–I09.
- **F04:** moved minimal artifact/replay/security/evaluation foundations earlier; M11 remains integrated review, not first security step.
- **F05:** replaced v0.1 partial backlog with task-level v0.2 records and implementation traceability.
- **F06:** added stable document map and evidence manifest; model report is included, source/report JSON absence is explicit.
- **F07:** M2 migration order follows dependency roots; provider work split into M9A launch-scope and M9B optional extensions.

No production tests have been newly run by regenerating these documents. Auto-activation remains disabled.
