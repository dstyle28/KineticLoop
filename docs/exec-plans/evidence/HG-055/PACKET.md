# HG-055 — generic PR regression ownership

Identity: harness-governance-v0.1/HG-055. Protected base: af09be228fbc89d074b6e863c83e1fdda343d55b.
User authorized one fresh worktree/branch/governance PR; coordinator explicitly
granted harness_governance and this scope while HG-054's fixed-source C14 continues.
No dependency on unmerged HG-054 code or codec/controller update.

Exact writes: .github/workflows/ci.yml; tests/harness/test_ci_execution_ownership.py;
docs/exec-plans/governance/HG-055.yaml; own evidence/HG-055/** and reviews/HG-055/**.
No task definition, product/DB/frozen authority, index/schema, controller or storage
format changes. Current plain/gzip Git evidence only. No KL-036/KL-037 artifact edit.

PR quality omits only duplicate unit/harness steps, which the required installed
App controller executes. Hosted master/manual, static/merge and special readiness/
release checks remain. Required packet commands and product PASS meanings remain.
Root retains live protection/pins check, admission, actual App/fullDB and normal merge.

Stable author checks (exact commands and observed exits recorded in CHECK_INDEX.json):
1. ci_ownership: uv run pytest -q tests/harness/test_ci_execution_ownership.py
2. existing_gate_boundary: uv run pytest -q tests/harness/test_local_db_ci.py tests/harness/test_local_gate.py
3. harness_authority: uv run kl check-harness
4. lint: uv run kl lint
5. typecheck: uv run kl typecheck
6. frozen_scope: uv run python docs/exec-plans/evidence/HG-055/verify_scope.py --base BASE --head TESTED_SHA
7. diff: git diff --check BASE TESTED_SHA

Tests require positive unchanged owners and negative missing/partial/unguarded
owners. Scope proof compares actual Git diff and frozen bytes. No extra author full
unit/harness run: final installed App owns full unit/harness/DB regression. Pending
App/CI/merge facts are not implementation PASS. Capture raw stdout/stderr once.

Fresh independent GENERAL and SECURITY_DATA_BOUNDARY bind final implementation/
governance/evidence SHA; after review only own linear REVIEW_RECORD_ONLY append.
Generic validator machine-requires GENERAL; root additionally requires the packet's
security PASS and no open blocker. Any source/result change requires fresh testing/
review. Follow 2–3 feature PRs using actual invocation/minutes/evidence measurements
in existing task notes; no unmeasured usage/speed promise or measurement platform.
