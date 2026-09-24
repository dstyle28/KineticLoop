# Harness Operating Model v0.2

## Roles

- Orchestrator: computes READY from dependency/gate/resource state, dispatches one-task worktrees, and records milestone gates.
- Implementation thread: changes only its declared write scope and produces committed task evidence.
- Independent reviewer: fresh context, head-bound review artifact.
- Milestone reviewer: evaluates merged task results plus exact requirement evidence; does not infer PASS from task count.

## One task / one worktree / one PR

A thread receives root `AGENTS.md`, its task packet, `CURRENT_DOCUMENT_INDEX.json`, merged prerequisite results, and only canonical sections named by the packet. Conversation history is not a dependency.

## Admission vs gate construction

A task that **builds** a gate is not itself blocked by that gate. Gate consumers list the gate as an admission condition. `launch_source_scope` is produced by its registry task; optional providers become dependencies only when the published scope includes them.

## State axes

See `TASK_STATE_MODEL.md`. Task PASS, requirement PASS, review PASS, and Git merge are separate facts.

## Milestone closure

Milestone completion is a machine record, not a count of task result files. The M1
record at `docs/exec-plans/milestones/M1.json` conforms to
`MILESTONE_CLOSURE.schema.json` and closes only when the active M1 set is exactly
KL-001 through KL-009 and every task has a valid, reachable `MERGED` integration
record. Each exit check carries evidence path, evidence revision and SHA-256.

M1 closure does not promote product requirements. Historical protocol-model results
remain `UNVERIFIED_HISTORICAL_DECLARATION` and
`independently_reproducible_protocol_model=false` until the missing source, fixtures,
machine report and source-revision binding are supplied.

## Parallel writes

Dispatch requires no conflicting `resource_keys` or concrete implementation write paths. Worktree database/Compose namespaces are isolated. Migration-chain tasks are serialized.

M2 uses structured `check_contracts` and `evidence_paths` mirrored exactly by the
backlog, traceability record and packet. A PASS result must use every declared check
ID, execute its exact command, satisfy its explicit PASS oracle, and write evidence
only below the task-owned evidence path.

`write_paths` describes the task's implementation/configuration/test/document write scope. Two task-scoped bookkeeping paths are granted separately and do not need to be repeated in every task packet:

- implementation thread: `docs/exec-plans/completed/<TASK_ID>_RESULT.yaml` before review;
- reviewer thread: `docs/exec-plans/reviews/<TASK_ID>/**` after reviewing the implementation head.

These bookkeeping exceptions never authorize changing another task's records, task packets, requirement status, or product/frozen documents. Review-record-only commits follow `THREAD_REVIEW_CONTRACT.md`.

## Frozen safety

Frozen Protocol/DB hashes are checked against a protected baseline file that normal feature tasks do not regenerate. Any intentional frozen change requires an approved protocol-version task/ADR and a new baseline version.
