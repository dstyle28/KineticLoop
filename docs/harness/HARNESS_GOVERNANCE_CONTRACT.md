# Harness Governance Contract v0.1

Task implementation PRs remain governed by one task, one result, one review and one
merge. Changes to the Harness definition itself use a separate, explicit governance
record under `docs/exec-plans/governance/<CHANGE_ID>.yaml`.

A governance PR may refine task packets, backlog metadata, validator behavior,
schemas and derived document hashes. It may not change Frozen Protocol/DB files or
`FROZEN_BASELINE.json`. The committed change record must conform to
`HARNESS_CHANGE.schema.json`, name the protected base and tested revision, enumerate
the exact changed files and refined packets, and link every executed check to
committed evidence. The selected governance record must have `change_status: PASS`;
`BLOCKED` and `SPEC_CHANGE_REQUIRED` records are durable outcomes but cannot merge.

Governance reviews use `docs/exec-plans/reviews/<CHANGE_ID>/<TYPE>.json`. A PASS
GENERAL review is always required. For every task definition changed between the
protected base and reviewed head, the gate requires the union of specialist review
types declared by both revisions. A governance PR therefore cannot remove its own
PROTOCOL, DB_CONCURRENCY or SECURITY_DATA_BOUNDARY review requirement. After the
reviewed governance/result revision, only that change's review directory may be
modified without rereview.

The CI merge gate derives either exactly one task result or exactly one governance
record from the protected-base diff. Mixing both PR types, changing an undeclared
path, omitting a review, or changing implementation/governance content after review
fails closed.

Post-merge state is recorded separately under
`docs/exec-plans/integrations/<TASK_ID>.json` and conforms to
`INTEGRATION_RECORD.schema.json`. The record binds the task result, reviewed head,
review-record commit and merge commit; it never rewrites the pre-review task result.
The referenced result commit must contain exactly one supported representation,
`<TASK_ID>_RESULT.yaml` or `<TASK_ID>_RESULT.json`, and that artifact must parse and
conform to the result schema. The reviewed head must contain the same representation
with byte-identical content. The bound result must be PASS and satisfy all semantic
result checks, including required task checks and revision-bound evidence.
