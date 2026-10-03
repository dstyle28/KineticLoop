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

Every PR needs a successful `local-db-gate` from the dedicated GitHub App.
The administrator-installed classifier compares the complete live master-to-head
Git diff. Unknown paths, executable modes, dependencies, tests, configuration,
authority documents and evidence files all require full DB. Only regular README,
`docs/notes/*.md` and `.md`/`.json` task review bookkeeping are exempt. Evidence
files may be code inputs (for example the KL-074 workflow proposal) and therefore
are not generally exempt. Task-specific and stricter hosted requirements remain
authoritative. Historical task results and KL-074 hosted provenance stay unchanged.

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
and is removed with the container after success or failure. The wrapper permits only its fresh uniquely named Docker data volume,
checks there are no bind mounts/host socket/host networking, and removes both its
container and data volume. The volume is necessary for nested overlay2 storage. The local Docker image cache is retained for subsequent runs. Docker
needs permission for a privileged nested daemon; unrelated host containers and
volumes are never cleaned. No registration token or repository secret is needed. Before any Docker command,
the wrapper rejects effective Docker client proxy forwarding (including the
`DOCKER_CONFIG` override), unreadable/malformed config, and ambient
`BUILDX_BUILDER`/`BUILDKIT_HOST` overrides. This prevents implicit proxy credentials
from entering builds/containers and keeps image builds on the local daemon.

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
and its explicitly hosted evidence remain unchanged. The startup-readiness test
retains all KL-074 checks; only its two legacy generic-workflow hash pins are
replaced with assertions for the prospectively approved HG-046 CI policy. The
workflow test similarly replaces its old review-only paths-ignore string check
with exclusive manual dispatch and no historical auto-writeback assertions.

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

## Mandatory trusted controller

The manual `db_ci.py local` command is useful developer feedback and result
capture. It does not publish the required merge check. Creating a PR does not
silently start software on an engineer's laptop. Until the trusted operator runs
the installed controller, the required check is missing and merging is blocked.
A local hook alone cannot provide this enforcement because hooks can be skipped.

The administrator installs an independently reviewed revision of `local_gate.py`,
`github_app.py`, `db_policy.py`, `db_ci.py`, `db_ci_pytest.py`, `gate_validate.py`,
`gate_pytest.py`, `validate_harness.py`, `compact_evidence.py`, and the `local_db/` Docker build files into
one versioned directory outside any candidate checkout. `controller_files` pins
exact SHA256 bytes of every file named by `local_gate.ASSETS`. The configuration
and private key are owner-only regular files, outside Git, source bundles and
workers. The App has only Checks write and Contents/Pull requests/Metadata read;
no OAuth, public webhook, Contents write or Administration access is needed.

Configuration includes `app_id`, `installation_id`, `repository`, `repository_id`,
`key_path`, and `controller_files`. Production installation is an administrator
operation after independent review; a PR never updates the active controller or
its pins. Future controller changes need a separately reviewed installation.
This desktop setup only admits explicitly reviewed trusted project code. The
privileged nested daemon is not a sandbox for hostile public PR code. Automated
untrusted PR execution needs a separate disposable worker without host shares,
signer secrets or unrelated workloads.

After reviewing the exact PR revision, the trusted operator writes an owner-only
admission file outside Git. Its fields are `format: kineticloop-local-admission-v1`,
`snapshot: {repository_id, pr, base, head}`, `controller` (SHA256 of the sorted JSON
`controller_files` map), and `trusted_code_reviewed: true`. Admission authorizes
execution; the installed validator separately requires the repository's exact-SHA
independent review and task-result contracts before publication can pass.

```bash
python3 -I /ABSOLUTE/INSTALLED/local_gate.py \
  --config /PRIVATE/config.json --admission /PRIVATE/admission.json \
  --pr PR_NUMBER --evidence-dir /PRIVATE/RUN_UNIQUE
```

The controller fetches the live PR/master from GitHub, requires master ancestry,
and checks exact admission before executing candidate code. It owns the build
context, container, command plan, pytest observer, validator and verdict. All
PRs run lint, typecheck, unit, harness and revision-bound merge checks; the full DB
suite and lifecycle run when the trusted diff policy requires them. It observes
each command's exit on the host, rejects missing/skipped/mismatched execution,
validates copied files before parsing them, and removes its own container/volume.
It holds an installation-wide execution lock, rereads live head/base before
publication, and patches the same App-owned check created at run start. Failure,
interruption, stale refs or cleanup failure cannot produce success. `--test-only`
never publishes a check and does not claim PR review validation.

The receipt binds repository/PR/base/head/tree, controller/image, policy, commands,
raw hashes, unique run ID and cleanup. Store it outside Git until execution ends;
archive non-secret selected evidence in the task result. No uploaded JSON alone
can authorize publication. There is no success-import or evidence-reuse command.

Master requires `local-db-gate` from the exact dedicated App ID, strict up-to-date
branches, PR-only changes, no bypass actors and no force push/deletion. Existing
quality/merge-gate checks remain required. Full DB is not automatically repeated
on master; PR admission tests the head containing current master. Release/platform
qualification may still explicitly invoke the hosted fallback. Passing tests
reduces regression risk; it never proves bug-free software. The administrator,
trusted-code admission and signing key are explicit trust boundaries.

## HG-047 compact-evidence compatibility

The integrated validator reads compact envelopes through its own installed
`compact_evidence.py`. The controller pins that decoder in `controller_files`
and copies it with the installed validator into `/gate/tools/harness/` inside
the worker. It must never import a decoder from the candidate checkout. Missing,
changed or symlinked installed decoder bytes fail the same installation check
as other trusted assets.

Before HG-047 can receive a successful App gate, an administrator must install
the independently reviewed validator, controller and decoder as one new reviewed
release, update the complete exact `controller_files` map and create a new
revision/controller-bound admission. An old validator does not understand compact
proof; installing only the new validator leaves its required import unavailable.
This repository change does not update the active installation, pins, signing key,
admission or protection settings. The ordinary required full DB/controller gate
still applies to the final reviewed PR head.
