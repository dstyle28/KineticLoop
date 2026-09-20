# Task Thread Prompt Template

Use this to start a fresh Codex thread/worktree:

> Implement **{{TASK_ID}}** only. Read root `AGENTS.md`, then `docs/exec-plans/active/{{TASK_ID}}.md`. Start from the latest branch containing all listed prerequisites. Do not import assumptions from other chat threads. Read only the canonical references the packet names, on demand. Keep the change to one reviewable PR. Run the required tests/evidence. If implementation requires changing frozen authority semantics, stop and return `SPEC_CHANGE_REQUIRED` instead of inventing a local rule. Before requesting independent review, create and commit the thread result artifact described in `docs/harness/THREAD_RESULT_CONTRACT.md`. The reviewer may then append only the task-scoped review artifact under the REVIEW_RECORD_ONLY exception; any implementation change requires rereview.
