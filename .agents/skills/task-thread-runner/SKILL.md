---
name: task-thread-runner
description: Execute exactly one KineticLoop harness task packet in a fresh thread/worktree and produce a reviewable PR/result artifact.
---
1. Read root `AGENTS.md` and the assigned task packet.
2. Confirm prerequisites are merged and entry conditions hold.
3. State the task goal and non-goals internally; do not expand scope.
4. Read canonical references progressively, not the entire documentation set.
5. Implement the smallest coherent change; split the task if it develops a second independent outcome.
6. Run the packet's required checks.
7. Self-review for accidental frozen-spec changes and unrelated edits.
8. Produce the thread result contract. If blocked by missing semantics, return `SPEC_CHANGE_REQUIRED`.
