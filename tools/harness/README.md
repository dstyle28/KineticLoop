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

This requires a clean checkout and committed artifacts. The selected task's required reviews must pass, its result/evidence must exist at the reviewed revision, and both revision suffixes must satisfy the contracts. Historical reviews of other tasks are schema-checked, not compared with the current PR head. The trusted baseline must already contain the Harness files; the initial documentation installation is not a feature PR checked against an empty repository.

Evidence references are repository-relative regular files, not URLs or unchecked log labels. Store new per-task evidence under `docs/exec-plans/evidence/<TASK_ID>/`. Commands carry `check_id` matching the task's check registry. Failed intermediate attempts may remain in raw evidence; a PASS result records one successful final execution per required check.

`CURRENT_DOCUMENT_INDEX.json` and `HARNESS_DOCUMENT_MANIFEST.json` have a restricted derived-hash allowance. Relative to the trusted baseline, their entries, ordering, identities and metadata must stay unchanged; only hashes/byte counts for already-listed, actually changed, authorized implementation files may refresh. The package manifest may also refresh the current index's checksum. Neither allowance can change frozen authority entries or authorize additional implementation paths. Adding current-index entries requires a separately authorized task definition.

The checked-in package manifest describes the original package files with refreshed checksums; newly added implementation/tests need not be appended to that delivery inventory. The original ZIP remains a historical package, not a current working-tree snapshot.
