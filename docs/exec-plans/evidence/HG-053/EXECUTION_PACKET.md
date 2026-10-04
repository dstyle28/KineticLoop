# HG-053 execution packet

Identity: harness-governance-v0.1/HG-053. Protected base B:
c82e50aefad5c4d9e325d4928a8f96032b81192d. One fresh chat/worktree/branch/PR.
Goal: refine only unstarted harness-backlog-v0.2/KL-036 and KL-037 against
actual merged owners, frozen clauses, executable check contracts and isolated
runtime requirements. No implementation or product PASS is claimed.

## Admission and scope
Recheck actual origin/master and open PRs, absent HG053 allocation and absent
KL036/KL037 results/reviews/integrations at B; verify M3 minimal TEST closure and
actual prerequisite integrations as Git ancestors, not chat claims.
Allowed edits: the two active packets; only their backlog and derived traceability
projections; required existing index/manifest hash and byte-count refreshes;
docs/exec-plans/governance/HG-053.yaml; own evidence and reviews directories.
No runtime/tests/shared validator/schema/CI/controller, frozen, completed, M3,
KL038/KL039 or unrelated worktree changes. New completed-owner gaps are described
prospectively, never repaired by rewriting historical packets/results. If needed
contracts cannot be represented by existing generic validator interfaces, record
the exact separate prospective governance need; do not change shared enforcement.

## Work and decision obligations
Bind Protocol §§2,6.2–6.7,8 and DB S01–S04/S27–S32, §§3,4.1–4.3,5 to real
PlanningWorkflowService, guarded progress, CallLedgerService, ReapIntent and
claim_outbox owners. Determine precise necessary persistence paths from code;
retain serialized shared resources unless exact disjoint writes genuinely suffice.
Commands must require positive non-skipped PU/DC/WF cases, distinct OS worker and
reaper processes, trusted post-lock time, current identities, complete rollback,
first-use contention and immutable history. Require task/SHA7/resolved-root SHA12
PostgreSQL/Compose isolation, before/after inventories, bounded joins and cleanup.
External waits occur outside coordination. No new state enums/schema/lock order,
authority semantics, provider trust or production/shadow activation.

## Checks and evidence
All checks initially NOT_RUN. At committed candidate C run:
- own uv run python docs/exec-plans/evidence/HG-053/verify_refinement.py
- uv run python tools/harness/document_index/check.py current_document_index_resolves
- uv run kl check-harness
- uv run kl lint
- uv run kl typecheck
- uv run kl test-unit
- uv run kl test-harness
Use exact C-bound lossless compact captures and preserve actual failures. Record
source/document versus evidence bytes; audit unchanged 256KiB plain/8MiB gzip/
64MiB recovered/16MiB aggregate limits. After C only own new evidence and governance
result bookkeeping; substantive edits require a new C and rerun.

## Review and PR readiness
Commit exact files_changed, B/C, checks_run and frozen_impact in schema-conforming
HG053 record before review. Fresh independent GENERAL, PROTOCOL, DB_CONCURRENCY,
SECURITY_DATA_BOUNDARY reviews at complete result revision R are explicitly required.
Reviewers inspect the actual diff and evidence independently; blocking findings
require fixes, retesting and rereview. Only own linear REVIEW_RECORD_ONLY suffix
may follow R. Verify uv run kl check-harness --ci-pr-base B --ci-pr-head H and
compact storage audit, then normal push/create/attach one PR and hosted checks.
The coordinator owns installed App/fullDB admission/execution and normal merge.
Never install/admit/execute the App, publish gate status, reuse payload exceptions
or message another chat. Leave clean reviewed H and readiness handoff outside Git.
Packet refinement PASS, task implementation PASS, product/review/CI/App PASS and
MERGED are separate facts. Production stays disabled; shadow stays nonexecutable.
