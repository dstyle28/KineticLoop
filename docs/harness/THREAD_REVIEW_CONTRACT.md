# Thread Review Contract v0.2

Every task receives an independent GENERAL review. Additional specialist review is required when the task touches the corresponding risk surface:

- frozen Protocol / T1–T8 / authorization semantics → PROTOCOL;
- PostgreSQL locks, fencing, idempotency, migration chain or coordination rows → DB_CONCURRENCY;
- remote AI context, provider/health data export, credentials, retention/redaction → SECURITY_DATA_BOUNDARY.

Review artifacts are committed under `docs/exec-plans/reviews/<TASK_ID>/<REVIEW_TYPE>.json` and conform to `THREAD_REVIEW.schema.json`.

## Reviewed revision and the review-record append exception

`reviewed_head_sha` is the implementation/result revision actually reviewed. Normally any implementation, configuration, migration, test, contract, or product-document change after that SHA makes the affected review `STALE`.

A narrow exception exists so the review can itself be persisted without invalidating itself: after `reviewed_head_sha`, commits may append or update only the following task-scoped review bookkeeping paths:

- `docs/exec-plans/reviews/<TASK_ID>/**`

These commits are called **REVIEW_RECORD_ONLY** commits. They MUST NOT modify application code, tests, migrations, contracts, task packets, requirement status, frozen files, or the task result payload. A mechanical merge-gate check must prove that `reviewed_head_sha` is an ancestor of HEAD and every intervening commit changes only allowed review-record paths. The suffix must be linear; merge commits require a new review. Path matching uses whole directory components, so another task such as KL-001A is never covered by KL-001. If any other path changes, the review is stale and must be rerun.

The task result is committed before review and is part of the reviewed revision. Do not mutate the result after review merely to copy the reviewed SHA; the review artifact itself is the authority for `reviewed_head_sha`.

Reviewers may create logs, reports and other review bookkeeping during independent review. Those files are review evidence, not pre-review task test evidence. An integration record's exact `review_record_commit` binds those references without adding a schema field: ordinary review references must resolve at `reviewed_head_sha`; a reference absent there (no Git entry of any type at that path) may resolve at `review_record_commit` only inside `docs/exec-plans/reviews/<same TASK_ID>/`, after a mechanical proof that the entire ancestral suffix is linear and exclusively REVIEW_RECORD_ONLY. Whole directory components are mandatory. Every reference must be a normalized repository-relative path to an available regular Git blob at its bound revision; directories, symlinks, traversal and ambient working-tree/HEAD existence are not evidence. Git commit/tree/blob identity supplies content addressing.

This exception cannot supply implementation, result or task-check evidence created after review. Result and task evidence retain their existing reviewed-revision guarantees. It does not relax delayed post-merge review freshness or exact-tree squash ancestry: a delayed review with intervening unrelated commits can continue to cite ordinary reviewed-revision evidence, but cannot use this review-created evidence exception unless the entire suffix also passes the strict own-task linear proof.

`CHANGES_REQUIRED` findings are closed only by a new implementation revision and a new review artifact. Untracked comments do not close findings.

The validator applies revision freshness to the selected task PR. Historical reviews of previously integrated tasks retain their recorded revision and are not invalidated by later unrelated task commits.
