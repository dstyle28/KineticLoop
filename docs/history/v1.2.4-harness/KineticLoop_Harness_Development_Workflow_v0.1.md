# KineticLoop Harness Development Workflow v0.1

## Operating decision
KineticLoop development uses thread-per-task harness execution. The long-lived coordinator context owns **prioritization and merge state only**. It does not become the place where all implementation details accumulate.

## Unit of work
```text
Milestone = evidence/merge checkpoint
Task      = one PR-sized independent unit
Thread    = fresh agent context for exactly one Task
Worktree  = isolated checkout for that Thread
Review    = separate fresh thread
```

## How a task starts
1. Orchestrator reads `KineticLoop_Harness_Backlog_v0.1.json`.
2. Select a task whose dependencies are merged and entry gates are satisfied.
3. Create a worktree/branch from the current integration branch.
4. Start a fresh Codex thread with `docs/harness/TASK_THREAD_PROMPT_TEMPLATE.md`.
5. The task agent reads only its packet and progressive references.

## How it ends
The task agent commits code/tests/docs and creates a result artifact. A separate review thread uses `pr-merge-reviewer`. Only merged repository state becomes context for future tasks.

## Initial execution waves
These are scheduling hints, not new dependencies.

### Wave 1 — bootstrap
Start `KL-001`. Once its minimal repo exists, `KL-003`, `KL-005`, `KL-006`, `KL-007`, and `KL-009` can largely proceed independently; `KL-002` follows the repo bootstrap and can run in parallel with those.

### Wave 2 — base contracts
After the M1 gate, run `KL-010` first to establish physical dependency topology. `KL-014`, `KL-016`, `KL-017`, `KL-018`, and `KL-055` can then proceed in separate worktrees where their write sets are isolated. `KL-013` waits for the schema roots it migrates.

### Wave 3 — protocol core
Serialize critical coordination implementations where they share S01/SafetyRegistry/authorization contracts. Run their read-only/test reviewers in parallel.

### Wave 4+
Once common evidence/provider contracts are merged, Hevy and HealthKit adapter threads may run in parallel. Oura remains non-blocking. Fitness and Nutrition agent work stays behind the protocol/context gates.

## Why this is preferable
Independent threads reduce context pollution and make each PR auditable against a narrow packet. Codex worktrees provide isolated checkouts for parallel chats, while repository-local `AGENTS.md` and skills support progressive disclosure rather than a giant always-loaded prompt.
