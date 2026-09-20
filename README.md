# KineticLoop v1.2.5 — Harness Contract Hardened Package

This package hardens the thread-per-task development harness after repository bootstrap. Frozen Protocol v1.2 and DB logical schema v0.2 are unchanged.

## Status
- Protocol: **FROZEN / unchanged**
- DB logical schema: **FROZEN / unchanged**
- Harness contract: **v0.2 hardened**
- Project Plan: **v0.5 harness hardened**
- Development implementation evidence: **NOT YET CLAIMED BY THIS PACKAGE**
- Production auto-activation: **DISABLED**

## Current entrypoints
1. `CURRENT_DOCUMENT_INDEX.json` — only current document resolver.
2. `CURRENT_REQUIREMENT_SET.json` — composite obligation identity.
3. `AGENTS.md` — coding-thread map.
4. `KineticLoop_Harness_Backlog_v0.2.json` — current task source of truth.
5. `docs/exec-plans/active/<TASK_ID>.md` — per-thread packet.
6. `docs/harness/THREAD_RESULT_CONTRACT.md` + `THREAD_REVIEW_CONTRACT.md` — durable evidence contracts.

## What changed in v1.2.5
- task IDs are namespaced; known historical KL-062..066 reuse is explicitly mapped;
- missing acceptance/evidence/traceability machine files are restored and current authority is indexed;
- task PASS, requirement PASS, review PASS and merge are separate state axes;
- task results must be committed in the PR and reviews are bound to exact head SHA;
- `requirements_covered` is separated from `checks_required_for_this_task`;
- gate-builder self-dependencies are removed; optional provider dependencies are conditional;
- resource keys/write paths/worktree DB isolation are part of scheduling;
- KL-019 provides the minimal publish/commit/start implementation before KL-026 interleaving tests;
- packets with placeholder DoD are blocked from READY until refined;
- frozen baseline protection uses `FROZEN_BASELINE.json`, independent from mutable package manifests;
- KL-001 now owns the minimum Harness validator/CI entrypoints.

Historical v1.2.2 planning files under `docs/history/` are traceability only, never default authority.

Latest harness hardening: `HARNESS_HARDENING_REPORT_v0.3.md`.
