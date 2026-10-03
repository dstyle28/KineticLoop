# Reference Harness validator

Install the locked development environment and run the stable checks:

```sh
uv sync --locked
uv run kl lint
uv run kl typecheck
uv run kl test-unit
uv run kl test-harness
uv run kl check-harness
```

`uv run kl test-protocol-model` exits with status 2 and `PROTOCOL_MODEL_NOT_RUN`
until the unavailable model source is supplied. It never creates protocol evidence from
the Harness fixture suite.

Without Git arguments, the validator checks current hashes, task packets/DAG, and every result/review artifact's schema and local evidence. Both YAML and JSON results are validated; duplicate result representations are rejected. Missing dependencies or malformed artifacts fail validation.

For a task PR, use the trusted integrated baseline and the revision named by the independent review:

```sh
uv run kl check-harness \
  --protected-base <integrated-baseline-sha> \
  --task-id KL-001 --reviewed-head <reviewed-implementation-and-result-sha>
```

Pull-request CI derives the task from the single changed result artifact, reads the
GENERAL review's `reviewed_head_sha`, verifies that the event head is checked out,
and invokes the same gate with trusted `pull_request.base.sha` and
`pull_request.head.sha` values:

```sh
uv run kl check-harness \
  --ci-pr-base <pull-request-base-sha> \
  --ci-pr-head <pull-request-head-sha>
```

Harness-definition PRs use one `docs/exec-plans/governance/HG-xxx.yaml` record
instead of a task result. The same CI command detects the governance record,
requires PASS status, enforces its fixed path allowlist, verifies packet refinement
and requires the bound GENERAL review plus the base/head union of specialist reviews
for every changed task definition. Task results and governance records cannot be
mixed in one PR.

Integration records resolve both supported result representations at the recorded
result commit and reviewed head. Exactly one must exist at each revision, with the
same path and byte content; the bound result must be PASS and semantically valid.

This requires a clean checkout and committed artifacts. The selected task's required reviews must pass, its result/evidence must exist at the reviewed revision, and both revision suffixes must satisfy the contracts. Historical reviews of other tasks are schema-checked, not compared with the current PR head. The trusted baseline must already contain the Harness files; the initial documentation installation is not a feature PR checked against an empty repository.

Evidence references are repository-relative regular files, not URLs or unchecked log labels. Store new per-task evidence under `docs/exec-plans/evidence/<TASK_ID>/`. Commands carry `check_id` matching the task's check registry. Failed intermediate attempts may remain in raw evidence; a PASS result records one successful final execution per required check.

`CURRENT_DOCUMENT_INDEX.json` and `HARNESS_DOCUMENT_MANIFEST.json` have a restricted derived-hash allowance. Relative to the trusted baseline, their entries, ordering, identities and metadata must stay unchanged; only hashes/byte counts for already-listed, actually changed, authorized implementation files may refresh. The package manifest may also refresh the current index's checksum. Neither allowance can change frozen authority entries or authorize additional implementation paths. Adding current-index entries requires a separately authorized task definition.

The checked-in package manifest describes the original package files with refreshed checksums; newly added implementation/tests need not be appended to that delivery inventory. The original ZIP remains a historical package, not a current working-tree snapshot.

`kl test-harness` uses two local pytest-xdist processes by default, capped at four.
Use `uv run kl test-harness --workers 1` for serial execution or `--workers 4` for
an explicitly larger local run. Pytest selection/verbosity options remain available;
use `-k` to filter. The runner owns worker topology and retains a verified JUnit copy. Existing
`--junitxml` / `--junit-xml` options export the same JUnit bytes to the requested path. `-s` requires
serial mode. A collection preflight refuses parallel tests outside `tests/harness`
or marked `harness_serial`; such tests require the explicit serial path. Future
shared-resource tests must carry that marker or use a separately isolated suite.
Database and migration tests are never admitted to parallel harness execution.

For clean committed source, `uv run kl test-harness --workers 2 --evidence-dir
/ABSOLUTE/NEW/RUN` (outside the checkout) retains raw collection/pytest logs, all worker collections,
actual started node IDs and phase reports, parent-generated JUnit and a manifest
with exact revision, versions, hashes and wall times. A run directory cannot be
reused. Different worker collections, missing/duplicate execution, skips, worker
crashes, missing JUnit identities or source changes fail closed. Pytest failure
exit codes are retained. This developer evidence does not publish or replace the
App-bound local database gate: the installed controller continues to own its
serial pytest observer and execution policy. No controller installation is
changed by this entrypoint.
