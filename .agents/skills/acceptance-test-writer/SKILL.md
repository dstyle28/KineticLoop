---
name: acceptance-test-writer
description: Turn KineticLoop frozen acceptance, boundary, interleaving and integration requirements into executable tests with durable evidence.
---
1. Start from a stable requirement ID and required layer (PU/DC/WF/E2E).
2. Preserve Given/When/Then semantics exactly; do not replace a DC/WF obligation with a unit mock.
3. Bind evidence to code/migration/policy/release identity where applicable.
4. Assert persisted state, not only API text.
5. Use negative controls/mutants where they materially prove the oracle.
6. `NOT_RUN`, `SKIPPED`, or manual observation never count as PASS.
7. Record result/evidence paths in the task result artifact.
