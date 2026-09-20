# Thread Routing v0.2

READY is computed, not manually asserted. A task is dispatchable only when:

1. all hard `depends_on` tasks are MERGED;
2. every applicable `conditional_depends_on` predicate is either false or the task is MERGED;
3. entry gates required for **use** are closed; tasks that construct the gate are exempt from that gate;
4. `packet_refinement` allows READY;
5. required environment exists;
6. no in-flight writer holds an overlapping exclusive `resource_key` or write path.

Worktree-local PostgreSQL/Compose namespaces are mandatory for concurrent DB write tasks. `migration_chain` is exclusive.

The orchestrator records task identity as `<backlog namespace>/<display id>` and never joins historical evidence on display ID alone.


## Write-scope refinement

A task with template or unresolved `write_paths` is not READY. The orchestrator must require concrete task-specific paths before dispatch. Standard task result/review bookkeeping paths are implicit allowances defined by `HARNESS_OPERATING_MODEL.md`, not implementation write-scope overlap.
