# HG-048 bounded harness test concurrency

Identity: `harness-governance-v0.1/HG-048`. Protected base: latest merged master
`391c9198fa8ec647e377a0572700bc7568468c85`; rebase and retest if HG-047 merges.
HG-046 and KL-001 are merged prerequisites. HG-047 remains separately owned by
PR 91; its Git evidence-read optimization must be retained on integration.

Implement bounded local process workers for `kl test-harness`, with explicit serial
mode, fail-closed collection scope and worker-aware developer evidence. Audit all
harness fixtures for shared mutable resources. Measure 1, 2 and 4 workers on the
same committed source and environment; retain raw logs, JUnit, collection and
actual execution IDs, versions, wall times and failures. Select a conservative
default from measurements. Evaluate independent lint/type/unit concurrency only
if material relative to the harness bottleneck.

Write scope: `src/kineticloop/cli.py`, `pyproject.toml`, `uv.lock`,
`tools/harness/run_harness_tests.py`, `tools/harness/parallel_observer.py`,
`tools/harness/validate_harness.py` (exact HG-048 governance allowlist only),
`tests/harness/test_parallel_runner.py`, `tools/harness/README.md`,
`CURRENT_DOCUMENT_INDEX.json`, `HARNESS_DOCUMENT_MANIFEST.json` (derived hashes),
and own governance/evidence/review paths. Exclusive resources: these exact paths;
no DB, migration_chain, shared checkout, PR91 branch, controller installation or
live settings. Tests using DB or exclusive resources stay serial. Developer
parallel evidence cannot substitute for the installed serial trusted controller.

Required checks: focused positive/negative worker/evidence tests; serial, 2-worker,
4-worker full harness with identical node sets and all outcomes; repeat selected
parallel mode for nondeterminism; unit, lint, typecheck, check-harness; protected
scope/frozen audit and diff hygiene. Commit the HG-048 governance result with exact
base/tested SHA and raw evidence before independent GENERAL review. Product
requirements remain NOT_RUN. Mandatory App-bound full DB gate remains separate;
no stale controller evidence is reused or relabeled PASS.

No frozen Protocol/DB, runtime commands, migrations, database fixtures, authority
semantics, acceptance coverage, credentials, installed controller or task status
changes. Installation compatibility is a separately reviewed administrator step
if the installed validator needs the new governance allowlist.
