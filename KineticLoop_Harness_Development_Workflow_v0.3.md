# KineticLoop Harness Development Workflow v0.3

1. Orchestrator resolves current documents and task identity.
2. Derive READY from merged dependencies, gate-builder/consumer semantics, packet refinement, environment, resource keys, and concrete implementation write paths.
3. Start one fresh implementation thread/worktree for one task.
4. Implementation changes only declared implementation write paths plus its standardized result path.
5. Run task checks on `tested_commit`; commit the result artifact before review.
6. Start fresh independent review on that implementation/result SHA.
7. Reviewer commits review artifacts only under `docs/exec-plans/reviews/<TASK_ID>/**`. This REVIEW_RECORD_ONLY suffix does not invalidate the review if the merge gate mechanically proves no other path changed.
8. Any later implementation/config/test/migration/contract/result change invalidates prior affected reviews.
9. Merge only after task checks, review(s), write/resource guards and applicable gates pass.
10. Merge/integration state is recorded separately; dependent tasks consume only merged repository artifacts, never prior chat history.

KL-001 establishes the executable harness checks. Other M1 tasks must refine concrete write paths before READY.
