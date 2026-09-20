---
name: protocol-guardian
description: Check whether a KineticLoop change preserves frozen Evidence, Decision Publication, Authorization, Planning Workflow, Replay, invariants and T1-T8 semantics. Use for protocol-sensitive implementation or review.
---
1. Read the task packet first.
2. Identify every `invariant_id`, transaction boundary and frozen table touched.
3. Open only the relevant frozen Protocol/DB sections.
4. Compare the code path against command ownership, atomic guard, lock order, idempotency and failure semantics.
5. Reject convenience branches that weaken production/shadow separation or authority checks.
6. If semantics must change, emit `SPEC_CHANGE_REQUIRED` with the exact frozen clause and proposed ADR; do not implement the semantic change.
7. Return concise findings with file/test references.
