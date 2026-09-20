# KineticLoop Agent Guide — Harness v0.2

KineticLoop uses **one task, one fresh thread, one worktree, one PR**. The repository, not chat history, is the durable system of record.

## Start here
1. Resolve current authority through `CURRENT_DOCUMENT_INDEX.json`.
2. Read your packet at `docs/exec-plans/active/<TASK_ID>.md`.
3. Read merged prerequisite result artifacts and only the canonical sections the packet names.
4. Use the matching repository skill under `.agents/skills/`.

## Authority order
1. `DOC-PROTOCOL-V1.2` — frozen Protocol.
2. `DOC-DB-V0.2` — frozen logical DB baseline.
3. current Integration Spec.
4. current Acceptance/Release Gates and `CURRENT_REQUIREMENT_SET.json`.
5. current Harness Project Plan + task packet.
6. already-merged code/contracts/results.

Historical files under `docs/history/` are never default authority. Machine task identity is namespaced (for example `harness-backlog-v0.2/KL-062`); do not correlate evidence on `KL-062` alone.

## Non-negotiable rules
- Production auto-activation stays disabled until release gates pass.
- Real-data shadow is non-executable: no live head, production authorization, or execution binding.
- Test-only T6/T7 uses isolated subjects/policies/environments.
- Provider data is evidence, not command authority.
- Planned values never fill actual execution.
- No direct-write bypass around command owners/transaction guards.
- Frozen SafetyRegistry / S01 lock order is mandatory.
- External model/network waits never occur inside coordination transactions.
- Frozen Protocol/DB changes require an approved protocol-version task/ADR; feature tasks do not regenerate `FROZEN_BASELINE.json`.

## State discipline
Task PASS, product requirement PASS, review PASS, and MERGED are separate facts. A task may PASS while related requirements remain NOT_RUN. `NOT_RUN` or `SKIPPED` is not requirement PASS.

## Thread/result contract
- Work only the assigned task and declared write/resources scope.
- Split if the PR becomes multi-concern.
- Commit `docs/exec-plans/completed/<TASK_ID>_RESULT.yaml` in the task PR; PR body alone is insufficient.
- Record `base_commit`, `tested_commit`, task checks, related requirement statuses, decisions, limitations and follow-ups.
- Reviews are fresh-context and SHA-bound; new commits stale prior review evidence.

## Git/worktree/environment
- One task per branch/worktree/PR, based on latest merged prerequisites.
- Worktrees do not isolate databases: concurrent DB tasks require unique DB and Docker Compose namespaces.
- `migration_chain` and overlapping exclusive resource keys are serialized.

## Standard engineering entrypoints
KL-001 must establish stable commands. Target interface:
```bash
uv run kl check-harness
uv run kl test-unit
uv run kl test-protocol-model
```
Until those exist, use only commands explicitly named by the task packet.

## Escalation
Stop and emit `SPEC_CHANGE_REQUIRED` if implementation would change authorization meaning, Evidence Admission, T1–T8 atomic boundaries, frozen lock order/invariants, production/shadow separation, or provider trust/command authority.

## Review persistence
Independent reviews bind to the reviewed implementation SHA. The only allowed post-review suffix without rereview is the task-scoped REVIEW_RECORD_ONLY append defined in `docs/harness/THREAD_REVIEW_CONTRACT.md`.
