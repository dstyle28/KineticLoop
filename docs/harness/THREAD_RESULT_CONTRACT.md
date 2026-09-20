# Thread Result Contract v0.3

A task's durable handoff **must be committed in the task PR before independent review** at `docs/exec-plans/completed/<TASK_ID>_RESULT.yaml` (or equivalent generated JSON). A PR body may link to it but may not be the only record.

The result separates four different meanings:

- task definition state (`READY/IN_PROGRESS/REVIEW/DONE`) — scheduler state;
- task checks (`NOT_RUN/PASS/FAIL`) — checks required for this PR;
- requirement obligations (`NOT_RUN/PASS/FAIL/APPROVED_NA`) — product/protocol evidence, never inferred from task completion;
- integration (`UNMERGED/MERGED`) — Git integration fact.

Required shape is governed by `THREAD_RESULT.schema.json`. Minimum example:

```yaml
task_identity: harness-backlog-v0.2/KL-xxx
display_task_id: KL-xxx
task_definition_version: v0.2
base_commit: <sha>
tested_commit: <sha>
merge_commit: null

task_status: PASS | BLOCKED | SPEC_CHANGE_REQUIRED
task_checks_status: PASS | FAIL | NOT_RUN
integration_status: UNMERGED
summary: ...

commands_run:
  - check_id: harness_document_index_valid
    command: uv run kl check-harness
    result: PASS
    evidence_ref: docs/exec-plans/evidence/KL-xxx/harness-check.log

requirements_covered:
  - requirement_id: I01@DC
    status: NOT_RUN
    evidence_ref: null

files_changed: []
decisions: []
known_limitations: []
follow_up_tasks: []
spec_change_request: null
```

`tested_commit` is the exact revision on which required task checks ran. Review identity is recorded in the separate review artifact; the result does not need to predict or later copy `reviewed_head_sha`. `merge_commit` is populated by an integration record after merge and is not required to appear in the pre-review result.

## Semantic validity rules

Schema validity alone is insufficient. Harness validation must enforce at least:

- `task_status: PASS` requires `task_checks_status: PASS`;
- a PASS task must report exactly one final PASS command for every `checks_required_for_this_task` ID using `check_id`; duplicate, unknown, missing, FAIL or NOT_RUN required checks reject PASS; documentation tasks must also name a concrete verification check;
- an executed PASS/FAIL command must have a non-empty evidence reference;
- a requirement obligation may be `PASS` only with a non-empty evidence reference bound to the exact requirement/layer and tested revision;
- `APPROVED_NA` requires an approval/evidence reference;
- product requirement PASS is never inferred from task PASS;
- after independent review begins, the result payload is immutable for that review cycle. Changes to it require rereview.

A task may PASS while some related product requirements remain NOT_RUN. It may not claim a requirement PASS without exact evidence for the required layer and revision.

## Tested revision to reviewed revision

`base_commit` must be an ancestor of `tested_commit`, which must be an ancestor of the reviewed implementation/result revision. After testing, only the task's own result file and **new** files under `docs/exec-plans/evidence/<TASK_ID>/**` may be committed before review. Existing evidence must not be overwritten or deleted in this suffix. Any code, configuration, migration, test, task packet, contract, or index change requires rerunning the required checks on a new `tested_commit`.

Both bookkeeping suffixes must be linear; every intervening commit is checked, so an implementation change followed by a revert does not preserve old evidence. Merge/rebase integration changes require retesting before starting a new bookkeeping suffix.

All executed PASS/FAIL commands require an existing repository-relative evidence file. Product PASS/APPROVED_NA entries use a concrete `requirement_id@layer`, an existing evidence file and `tested_commit` equal to the result's tested revision. The result and all referenced evidence must be committed at the reviewed revision. Raw logs remain available for independent review; existence alone is not a claim that their contents prove a requirement.
