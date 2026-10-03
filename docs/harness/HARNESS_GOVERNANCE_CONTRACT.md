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

A governance change may add a fresh follow-up task identity when newly discovered work
cannot be imposed retroactively on a merged task. The new task must begin
`NOT_STARTED`, have one complete enforceable packet and exact backlog/traceability
projections, and have no result, review, or integration artifact. Its dependencies
must preserve the already-merged work as historical input. A task definition that
already has a result at the protected base is immutable: governance must create a
new dependent task instead of changing its checks, scope, dependencies, or semantic
claims.

A governance change may retire an unstarted task by changing `NOT_STARTED` to
`SUPERSEDED`. Retirement is a disposition, never task PASS: it creates no task
result or requirement evidence and removes the task from the active count. The
governance change must preserve the task identity and requirement mapping, limit the
definition edit to the status, title, replacement dependencies, structured
`superseded_by` / `disposition_reason` metadata, deliverables and definition of done,
and replace the active packet with a traceability-only packet. A new explicit
retirement packet with structured disposition metadata must contain exactly one
standalone `Scheduling barrier: MUST NOT be scheduled.` line; pre-existing historical
supersessions retain their exact identity-bound scheduling sentence. `superseded_by`
must be a non-empty exact, ordered and duplicate-free projection of changed
replacement dependencies, and the packet must exactly project both it and the durable
reason. Completed tasks are immutable. A `SUPERSEDED` task cannot have a result and
cannot be reactivated or otherwise refined through ordinary governance.

Governance changes may add a milestone schema at the repository root and milestone
records under `docs/exec-plans/milestones/`. The schema is indexed as machine-readable
authority; individual closure instances remain revision-bound records and are not
separate authority entries. Both may be appended to the delivery manifest.

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

One non-generalizable emergency repair is admitted for `HG-024` with `KL-073` only.
That PR may contain both records solely to break the pre-existing database-CI
deadlock caused by KL-015's calendar-decayed test clock. The validator binds the
exact identities, the single implementation path
`tests/db/test_transaction_interfaces.py`, the exact governance/packet/derived-hash
files, and only the HG-024/KL-073 result, evidence, and review directories. It
requires both records to bind the same reviewed implementation/result head, every
KL-073 check to PASS with committed evidence, and the complete GENERAL, PROTOCOL,
and DB_CONCURRENCY review sets for both identities. No production path, migration,
Frozen authority, unrelated task artifact, wildcard database-test path, second
governance ID, or second task ID is admitted. The exception is exhausted by these
literal identities and cannot authorize any later mixed PR.

An already-merged governance change that lacks its required review may use one
review-only remediation PR. CI discovers exactly one existing governance change from
changed files under `docs/exec-plans/reviews/<CHANGE_ID>/` and restricts the entire PR
to that directory. The validator replays the original record against its recorded
protected base, including declared files, write scope, derived metadata, Frozen
baseline protection, evidence binding and required review types. This exception does
not admit a review-only task PR or allow governance content to change.

For that post-merge review, the tested-to-reviewed suffix may contain the two-parent
PR reintegration merge only when exactly one parent descends from `tested_commit`, the
other parent is already an ancestor of `tested_commit`, and the merge's complete Git
tree is exactly equal to the tested-descendant parent's tree. All intervening
governance bookkeeping commits remain path-checked. The reviewed-to-HEAD suffix stays
linear and review-record-only; arbitrary, content-changing and unrelated-parent merges
remain stale.

Post-merge state is recorded separately under
`docs/exec-plans/integrations/<TASK_ID>.json` and conforms to
`INTEGRATION_RECORD.schema.json`. The record binds the task result, reviewed head,
review-record commit and merge commit; it never rewrites the pre-review task result.
The referenced result commit must contain exactly one supported representation,
`<TASK_ID>_RESULT.yaml` or `<TASK_ID>_RESULT.json`, and that artifact must parse and
conform to the result schema. The reviewed head must contain the same representation
with byte-identical content. The bound result must be PASS and satisfy all semantic
result checks, including required task checks and revision-bound evidence.

Integration review references follow the precise source binding in the Thread Review
Contract: regular Git blobs at the reviewed SHA, or review-created bookkeeping blobs
at the exact recorded review commit after proof of a linear, exclusively own-task
REVIEW_RECORD_ONLY suffix. This never substitutes reviewer logs for the task's
pre-review test evidence or uses later unbound additions. Neither delayed post-merge
review nor exact-tree squash relaxes that proof for review-created references.

An already-merged task that lacks required review or integration bookkeeping may be
closed by one governance remediation PR. That PR may add only the task's required
review records together with its integration record; a changed task review directory
without the matching changed integration record fails closed. Every required review
must be PASS and bind the exact integrated merge tree. This exception does not permit
task implementation, result, evidence, packet, requirement, or frozen-authority
changes.

The integration revision chain is intentionally asymmetric. `result_commit` must
be a Git ancestor of `reviewed_head_sha`, and `reviewed_head_sha` must be a Git
ancestor of `review_record_commit`. `merge_commit` must be a Git ancestor of the
current HEAD. Only the `review_record_commit` to `merge_commit` edge has a squash
merge exception: that edge is valid when it has normal Git ancestry or when the
two commits' complete Git tree object IDs are exactly equal. The validator does
not accept matching path subsets, selected-file content comparisons, patch
equivalence, or any other near match in place of complete tree identity.
For the governance remediation exception above, the reverse ancestry direction is
accepted only when `reviewed_head_sha` equals `merge_commit` exactly and
`merge_commit` is an ancestor of `review_record_commit`; this records a genuinely
post-merge review of the integrated tree without relabeling a later commit as the
historical merge.


## HG-046 workflow compatibility

The authorized prospective local-first CI change has an exact task-specific scope.
It may update only the final generic `ci.yml`/`db.yml` compatibility assertions in
`tests/db/test_startup_readiness.py`, replacing the legacy workflow hashes with
structural assertions for the new approved triggers and hosted fallback. All
KL-074-specific exact workflow bytes/hash, negative mutations, hosted provenance,
probe behavior, fixtures, packets and historical results remain unchanged. This
named compatibility scope also updates the old `paths-ignore` string check in
`tests/db/test_workflow.py` to require exclusively manual full-DB dispatch and no
historical auto-writeback. These two exact test paths do not authorize other database test or runtime edits, and the
exception applies only to HG-046. The full DB suite must pass at the new tested SHA.

The same unmerged HG-046 concern also owns conservative DB classification, the
externally installed local controller/App client and isolated trusted validation/
pytest entrypoints, their negative tests and local installation contract. Master
protection configuration is explicitly authorized by the user and recorded in
HG-046 setup evidence. No signing credential is a repository artifact. The
controller is activated only after independent review of its implementation;
required checks may be installed earlier to block merges pending validation.

Prospective compact evidence follows [Evidence Storage Policy](EVIDENCE_STORAGE_POLICY.md);
all existing revision bindings and PASS oracles remain mandatory.
