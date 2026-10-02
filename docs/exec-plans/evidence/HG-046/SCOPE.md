# HG-046 scope and authorization

The user explicitly approved a separate CI cost optimization: eliminate duplicate
push/PR runs, prefer local full DB regression with exact SHA/raw evidence, retain
explicit hosted fallback, update validation rules and independently review it.
Protected base: 26906bd7f4444914c228e98377f2b164fee0dd5d (merged HG-044).
HG-045 PR89 is an unrelated open reviewed PR and is untouched.

Identity: harness-governance-v0.1/HG-046. Scope is .github/workflows/ci.yml and
db.yml; tools/harness/db_ci.py, db_ci_pytest.py and local_db image; corresponding
tests/harness tests; local DB CI and merge/M3 execution policy docs; derived index/
manifest hashes; own governance/evidence/review records. One compatibility assertion block in tests/db/test_startup_readiness.py may
replace the two obsolete generic-workflow hashes with the approved new policy
assertions; the governance contract and exact HG-046 allowlist declare this.
No runtime, migrations,
fixture rewrites, frozen files, historical results, product PASS or branch
protection edits. GENERAL, DB_CONCURRENCY and SECURITY_DATA_BOUNDARY reviews are
required by this task's risk surfaces.

The public repository has no self-hosted runners. An operator-started disposable
Linux container with its own nested daemon avoids granting public PRs a permanent
local runner. No host mounts/socket, credentials or other task DB lifecycle.
Selected proof includes actual complete local DB regression and lifecycle,
negative runner/evidence tests, lint/typecheck/unit/harness and frozen/scope audit.
Image download/build and test dependencies use normal network access outside any
coordination transaction. Stop before merge for the coordinator.
