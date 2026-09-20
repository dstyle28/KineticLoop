# Harness Negative Test Matrix v0.1

KL-001 must implement executable fixtures proving the harness rejects at least:

1. `task_status: PASS` with `task_checks_status != PASS`;
2. PASS task with empty `commands_run`;
3. executed PASS/FAIL command without `evidence_ref`;
4. requirement obligation marked PASS without evidence;
5. APPROVED_NA without approval/evidence reference;
6. packet dependency/check/write-path drift from canonical backlog metadata;
7. unknown dependency or DAG cycle;
8. task marked READY while packet refinement/write scope is unresolved;
9. frozen Protocol/DB changed together with `FROZEN_BASELINE.json` on a normal feature branch;
10. review PASS followed by application/config/test/migration/contract change;
11. review PASS followed only by allowed task-scoped review-record append (this one must remain valid);
12. a task writing outside its declared implementation `write_paths` (excluding standardized task bookkeeping paths).

Each fixture records the expected validator exit code and diagnostic key. Positive fixtures must cover the matching valid forms.

13. directory-prefix lookalikes (`src/kineticloop_extra`, another task's review directory) must fail path checks;
14. both YAML and JSON result artifacts must reject invalid schema, duplicate keys, empty PASS checks, FAIL/NOT_RUN required checks, unknown/duplicate/missing check IDs, missing evidence files and escaping evidence paths;
15. deleting a packet check section/list or adding unauthorized packet write paths must fail;
16. a review using an unrelated/non-ancestor tested revision, uncommitted result/evidence, implementation changes after testing, overwritten evidence or a reverted implementation change must fail;
17. authorized derived-hash refresh must pass, but index entry additions/removals, path/authority changes, refreshes for unrelated files and frozen entries must fail;
18. required review artifacts must actually exist, conform to their schema and match the reviewed revision; old reviews of other tasks must not be compared to the current PR head.
