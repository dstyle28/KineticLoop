# Local-first full database CI — HG-046

## Execution policy

Routine full database regression runs on an explicitly selected, clean committed
revision in a disposable local Linux environment. Its isolated Docker daemon is
owned by that run. No host directory, host Docker socket or GitHub credential is
mounted/passed into the executor. Existing fixtures can retain their supported
names because they share no daemon with another task. This is for trusted project
code, not untrusted public pull requests; no public self-hosted Actions runner is
registered. Local ARM64 evidence records that architecture and is not called x64
or GitHub-hosted evidence.

Run full DB regression before merging changes to persistence, database lifecycle,
migrations, deterministic/workflow logic consumed by DB owners, DB tests/helpers,
DB dependency locks, Compose, or this CI execution contract. Documentation,
review/evidence records and governance-only edits do not by themselves require
repeating the full suite. Task-specific checks and stricter hosted requirements
already frozen into a packet/result remain authoritative. This policy is
prospective; historical results, reviewed HG-045 and KL-074 hosted provenance are
not rewritten or retrospectively promoted.

GitHub keeps quality and SHA-bound merge-gate checks. Quality runs once per PR
update, plus master integration and explicit dispatch; superseded runs on the same
PR/ref are cancelled. Full hosted PostgreSQL regression runs only by explicit
workflow_dispatch with an immutable SHA, for release qualification, dependency or
platform changes, or investigating local/hosted differences. No scheduled full
regression consumes budget. A release needs its designated platform checks; local
success alone is not release or M3 PASS.

## Commands

From a clean checkout at the desired commit, with Python 3.12+ and Docker Desktop
(or another dedicated local Docker engine) available:

```bash
python3 tools/harness/db_ci.py local --revision HEAD --evidence-dir /tmp/kl-db-run-UNIQUE
python3 tools/harness/db_ci.py verify --revision FULL_COMMIT_SHA --evidence-dir /tmp/kl-db-run-UNIQUE/run
```

The host wrapper copies a Git bundle into one disposable Linux container. Its
nested Docker daemon starts empty, uses the Unix socket inside that container,
and is removed with the container after success or failure. The wrapper checks
there are no host mounts or host networking; cleanup names only the unique owned
container. The local Docker image cache is retained for subsequent runs. Docker
needs permission for a privileged nested daemon; unrelated host containers and
volumes are never cleaned. No registration token or repository secret is needed.

The exact same `run` command is used by `.github/workflows/db.yml` on a dedicated
GitHub Linux VM. It refuses remote Docker overrides, the wrong HEAD, a dirty
checkout, missing environment provenance, or an initially populated daemon before
any lifecycle/reset/destroy operation. It runs lint, typecheck, collection, every
`tests/db` case, compose validation, readiness, repeated reset and two-worktree
isolation, then cleanup. Any failed command, timeout, collection/JUnit mismatch,
skip/xfail/zero-case result or cleanup failure fails the run. Output is retained
without tee/pipeline exit-code ambiguity. Failed runs never create PASS evidence.

Hosted fallback after this workflow is on master:

```bash
gh workflow run db.yml --ref master -f revision=FULL_COMMIT_SHA
```

No daily hosted run is required. The retired KL-002 branch-specific auto-commit
job is removed; CI never rewrites an old task result. The special KL-074 workflow
and its explicitly hosted evidence remain unchanged.

## Evidence and review

`run/manifest.json` binds the tested SHA, execution environment, versions, commands,
exit codes, durations, raw stdout hashes/lengths, collection/execution node IDs,
and JUnit identities/counts. `local-executor.json` additionally binds the outer
container/image and its cleanup result. Preserve the whole evidence directory,
including failures; never overwrite a previous run. Copy selected evidence into
the current task/governance evidence directory and reference its manifest from
the committed result. The independent reviewer checks the tested/reviewed ancestry,
raw blobs and isolation envelope; local records are trusted operator evidence,
not remote hardware attestation. Do not relabel a failed GitHub run as successful.

This execution evidence does not replace a task's individual acceptance selectors,
M3 closure contribution/collection contracts, frozen lock semantics, or product
release gates. A later implementation change requires a new run. The prescribed
result/evidence and review-only suffix rules continue to apply.
