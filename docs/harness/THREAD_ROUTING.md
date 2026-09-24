# Thread Routing v0.2

READY is computed, not manually asserted. A task is dispatchable only when:

1. all hard `depends_on` tasks are MERGED;
2. every applicable `conditional_depends_on` predicate is either false or the task is MERGED;
3. entry gates required for **use** are closed; tasks that construct the gate are exempt from that gate;
4. `packet_refinement` allows READY;
5. required environment exists;
6. no in-flight writer holds an overlapping exclusive `resource_key` or write path.

Every M2 task additionally requires the unique M1 closure record to validate as
PASS. Missing, duplicate, stale, incomplete or overclaiming closure evidence makes a
READY M2 task invalid.

Worktree-local PostgreSQL/Compose namespaces are mandatory for concurrent DB write tasks. `migration_chain` is exclusive.

The orchestrator records task identity as `<backlog namespace>/<display id>` and never joins historical evidence on display ID alone.


## Write-scope refinement

A task with template or unresolved `write_paths` is not READY. The orchestrator must require concrete task-specific paths before dispatch. Standard task result/review bookkeeping paths are implicit allowances defined by `HARNESS_OPERATING_MODEL.md`, not implementation write-scope overlap.

Packet refinement is a Harness governance change, not an implementation task. It follows `HARNESS_GOVERNANCE_CONTRACT.md`, updates the machine backlog and packet together, and must make the task checks, DoD, resource keys and write paths concrete before the task can enter READY computation.

## M2 execution waves

- Wave A: KL-010 and KL-014 may run concurrently.
- Wave B: after KL-010, KL-011, KL-012 and KL-016 may run concurrently except that
  dependency-lock writers remain serialized.
- Wave C: KL-013.
- Wave D: KL-017 and KL-018 may run concurrently.
- Wave E: KL-015 and KL-055 may run concurrently.

Dependency-lock writers start from latest merged master in this order:
KL-014 → KL-016 → KL-013 → KL-055. Normal dependency checks still apply, and the
resource/write-path gate can further serialize a nominal wave.
