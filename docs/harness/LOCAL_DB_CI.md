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

## HG-050 installation-token freshness

The App client validates the server's timezone-aware UTC `expires_at` and rejects
invalid credentials or lifetimes with no usable interval beyond a 60-second safety
margin. It refreshes at that wall-clock boundary or its conservative monotonic age
limit (at most 3,000 seconds, anchored before JWT/validation/mint latency). An
observed wall-clock rollback also invalidates the cache. Renewal clears the old
credential first, repeats the exact App/installation/owner/selected-repository and
permission checks, and mints only for the configured repository ID. A failed
renewal cannot fall back to stale credentials. This protects against host suspension
with a stalled monotonic clock; it does not claim detection of arbitrary clock
corruption between observations.

A sanitized typed HTTP 401 on an installation-token GET permits exactly one refresh
and one retry of that same request. Installation validation and mint calls do not
recursively retry. A second 401, failed renewal, 403, other HTTP error, redirect or
transport failure terminates the request. POST and PATCH never automatically
replay. Tokens, JWTs, HTTP bodies and headers are excluded from diagnostic errors.

Live snapshot, admission, App/check ID verification, cleanup and publication rules
remain unchanged. Renewal obtains fresh snapshots through the normal controller;
worker success alone cannot authorize publication. Historical failed runs remain
failed and cannot be imported or manually republished. After independent review,
the administrator must install the complete pinned release and create a new exact
revision/controller-bound admission. The candidate never updates its installation,
configuration, signing key or pins. The normal App-owned full DB gate remains
required at the final stable reviewed PR head.

HG054 changes the pinned standalone `compact_evidence.py` decoder and
`validate_harness.py` validator. The installed controller must continue using only
its complete reviewed installed assets; candidate imports, changed/missing pins,
source-checkout dependencies and fallback decoders are forbidden. Root must obtain
independent installation review, compare every ASSETS hash and actual controller
identity, then admit the exact head/controller before App/fullDB use of xz-v1 or
forward re-encoding. Stale installed_commit metadata, an old receipt or hosted
check cannot substitute for those pins/admission. The HG054 worker neither installs
its candidate nor accesses signing credentials or publishes App results. Existing
isolated trusted full database validation remains required; no docs-only waiver.


## HG065 private installed ORIGINAL custody operation (prospective)

No executable privilege is added by HG065. Its closed definition requires a private
installed host ORIGINAL audit, separate from the unchanged strict live P-to-H
worker audit. Public CLI, environment, JSON, worker or caller-supplied trust flags
cannot request/import a custody verdict. The installed host derives authority
itself from its authenticated snapshot, exact installed assets/admission and owned
Git clone; it imports no candidate Python and propagates every ORIGINAL failure.

The ten exact reviewed appendices are incorporated conjunctively:
[DEFINITION.md](../exec-plans/evidence/HG-065/DEFINITION.md),
[RULE_TABLE.json](../exec-plans/evidence/HG-065/RULE_TABLE.json),
[PROOF_SCHEMA.json](../exec-plans/evidence/HG-065/PROOF_SCHEMA.json),
[OUTPUT_SCHEMA.json](../exec-plans/evidence/HG-065/OUTPUT_SCHEMA.json),
[LOCATOR_TABLE.md](../exec-plans/evidence/HG-065/LOCATOR_TABLE.md),
[BUDGETS.json](../exec-plans/evidence/HG-065/BUDGETS.json),
[CALLER_MATRIX.json](../exec-plans/evidence/HG-065/CALLER_MATRIX.json),
[TRUSTED_HOST_PROJECTION.md](../exec-plans/evidence/HG-065/TRUSTED_HOST_PROJECTION.md),
[SCOPE_PROPOSAL.md](../exec-plans/evidence/HG-065/SCOPE_PROPOSAL.md),
[GUARD_DISPOSITION.md](../exec-plans/evidence/HG-065/GUARD_DISPOSITION.md).
[Delivery provenance](../exec-plans/evidence/HG-065/DELIVERY_PROVENANCE.json)
and [source adaptations](../exec-plans/evidence/HG-065/SOURCE_ADAPTATIONS.json)
resolve original embedded scratch/input references to immutable source pins and
task-local delivery. Preserved preparation/non-grant labels describe their original
preparation state. Normal HG065 merge makes only these prospective definitions
authoritative; it supplies no historical or runtime PASS. The executable definition
fixtures are synthetic premises and immutable-data observations, never production
trust constructors. No scratch file is an acceptance dependency.

For final admitted operation, unchanged native selected-record rules select S from
the live P-to-H diff after installed authentication, admission and owned clone
verification and before run_worker. Require final P ancestor H. Execute complete
original O-to-H native inventory/codec/classifier/storage/history/all-map checks and
closed custody accounting, retaining all non-duplicate errors. Record the host's
actual exit, original inventory and diagnostic output; no supplied study/receipt
can substitute. Authenticate unchanged App snapshots before/after the operation,
after worker and before publication. Any failure or movement invalidates the run.

Private root preimport is a distinct read-only original operation using existing
root-owned selected task authority and the exact protected packet/Q/map context.
It reads frozen Q as Git data with authenticated P; final forward merge/ancestry,
native live selection, runtime/admission/execution/publication stay NOT_RUN. O-to-Q
also contains a normally imported foreign record, so it is never a final native
one-selected-record diff. Public task/base arguments cannot acquire this purpose.

Worker ci-pr/gate_validate arguments remain strict actual --ci-pr-base P and
--ci-pr-head H with no custody credential. Every original/live/native/selected/
prerequisite/result/review/fullRRO/source/M3/admission/release/App/hosted obligation
remains required. Complete independently reviewed installed assets/controller_files,
installation-wide lock, isolation, exact admission, unit/harness/fullDB/cleanup
and normal merge remain unchanged. This definition installs nothing and grants
no DB/App lease, signing permission or evidence-import path.

## HG066 prospective complete-owner custody and staged execution

HG066 normatively incorporates the exact reviewed sources in
`docs/exec-plans/evidence/HG-066/DELIVERY_PROVENANCE.json`, including
MULTI_OWNER_RULE.md, EXECUTION_CONTRACT.md, all seven closed schemas,
CLAUSE_SUPERSESSION.json, SCOPE_CORRECTION.json, CHECK_OWNERSHIP.json,
STAGING_CHECKS.json, PHASE_MATRIX.json, GRAMMAR_AND_INVOCATION.md,
REASON_IMPLICATION_MATRIX.json and the incorporated budget, caller, locator,
guard and original-source definitions. The source paths are relative to
`docs/exec-plans/evidence/HG-066/`. Their preparation status statements describe
historical preparation only; this clause promotes the reviewed definitions
prospectively without promoting any preparation execution or receipt.

MULTI_OWNER_RULE and the appended consolidated/R3/R4 clauses narrowly supersede
the former two-owner/six-case narrative and only the clauses enumerated in
CLAUSE_SUPERSESSION. All unlisted predicates remain conjunctive. The ten HG065
normative source blobs remain byte-exact and are referenced, never rewritten.
Every complete exact-raw collision group includes exactly one selected and every
foreign owner, all original declarations, owner-local payloads, normal deliveries,
introductions, parent/incoming edges and physical bytes. Unrelated native objects
remain counted and digested with zero custody credit. Both roots, both codecs and
actual plain bytes participate in native traversal. No fixed observation count,
owner/hash allowlist, omitted group, plain-copy credit or deduplication credit is
permitted. All native classifier/metadata/codec/source/admission/map/history guards
remain fatal; all22 capacities/units, execution/projected512, context120s/read10s
remain unchanged. Any exhausted group discards all positives. Either exhaustion
reason always implies incomplete PREIMPORT_DENIED/zero, including a rejected
reservation whose actual consumed value stays below cap; no fabricated charge.

Historical execution remains UNVERIFIED, acceptance_eligible=false and
execution_reuse=false. Preserve c4b, the independently bound6358 parent gap and
unknown child distinct from driver143, three741>512 denials, HG004 archival/missing
GENERAL, HG047 full RRO failure and original5da0 FAIL. This definition delivery
performs no actual K/H audit, installation, admission, App or DB operation; those
remain NOT_RUN and full native budget feasibility NOT_DETERMINED. Frozen Protocol,
DB, Evidence Admission, T1–T8, lock order, authorization, production/shadow/provider
trust and every product requirement state remain unchanged.

The binding A1–A5 route is mandatory. A1 executes the strict public ORIGINAL child
and retains its observed nonzero; only a separate exact expected-denial regression
may exit0 after independently deriving the entire unfiltered inventory, physical
counts/bytes/digest/traversal and exact diagnostics. Unknown exit, interruption,
timeout, missing/extra errors or incomplete native work fails. A2 uses the separate
nonfinal PREIMPORT grammar binding actual K/tree/controller, protected P and
original Q; final/live/admission/App stay NOT_RUN and host/driver exits stay distinct.

A3 starts only after actual separate normal HG066 merge, complete independently
reviewed baseline installation and an explicit narrow root regrant to SAME HG058.
The clean Q-retaining K uses exactly nine STAGING_SCOPE patterns (three production,
five existing test paths and own preimport-stage helpers), eight fresh K preparatory
checks, NEW complete independent GENERAL+SECURITY reviews of all11 ASSETS/controller/
source provenance and root installation outside checkout. FULL authenticated native
O-to-ACTUAL-K is required BEFORE ordered[K,P] import. Recheck K/P/controller/authority
at the boundary and obtain explicit root continuation. No Q substitute or deferral.

A4 prepares all helpers/manifest before fresh committed T, runs the twenty exact
individual author CHECK_OWNERSHIP commands with complete positive collection/start/
execution/phase/JUnit identities, and commits evidence by truthful R. Eight K checks
never substitute T acceptance. Both NEW full task reviews bind R; only own linear
REVIEW_RECORD_ONLY suffix produces H. The nineteen root hard prerequisites remain
PENDING_EXTERNAL_OBSERVATION outside selected checks_run and outside Git; no post-R
author evidence import. At H root requires complete final installation review/install,
exact admission, private full O-to-H AND strict P-to-H before accounted publication,
exact public denial, selected ci-pr/unchanged worker, actual App unit+harness/fullDB/
cleanup, live hosted gates/current snapshots and normal merge. Changed pins invalidate
stale evidence. A5 appends exactly literal tools/harness/local_gate.py to the protected
HG058 allowance, preserving existing entries/order; selected twenty-check enforcement
is prospective only. Original Q and historical global inventory retain native semantics.

No HG058 implementation lease follows from HG066 task PASS alone. SAME HG058 remains
frozen until actual normal merge and root-confirmed complete installed readiness and
regrant. KL081 waits for actual HG058 merge/readiness. Old PR99/102 and dirty KL055 stay
preserved. No gate_validate/config/schema/workflow/permission or runtime implementation
is authorized here; DB/App executor remains free and unreserved.

## HG067 prospective HOST resource contract

The normal independently reviewed merge of harness-governance-v0.1/HG-067
prospectively adopts the exact R4 definitions bound in
`docs/exec-plans/evidence/HG-067/DELIVERY_PROVENANCE.json`: RULE.md,
ROLE_EVENT_CONTRACT.md, RECORD_GRAMMAR.md, SOURCE_OBSERVATION_CONTRACT.md,
HOST_RESULT.schema.json, HOST_EMERGENCY.schema.json, HOST_LIMITS.json,
NATIVE_LIMITS.json, CLOCK_RESOURCE_POLICY.md, CLOCK_RESOURCE_DELTA.json,
CLOCK_DERIVATION.json, CALLER_PHASE_MATRIX.json, CLAUSE_SUPERSESSION.json,
FUTURE_CHECKS.json, OBSERVATION_COVERAGE.json and definition_oracle.py.
Their original preparation statuses (including PROPOSED_NOT_APPROVED and
DRAFT_NOT_AUTHORITY) remain exact historical statements. This explicit prospective
promotion takes effect only through HG067's normal reviewed merge. It adopts the
finite proposed definitions, never a preparation receipt, historical execution,
numerical fit, runtime enforcement or task/product/release PASS. Schema PLUS
bounded semantic oracle is mandatory; task-local models are nonoperational.

Only CLAUSE_SUPERSESSION's enumerated HOST-domain ambiguities are superseded.
All HG065/HG066 original appendices and unlisted predicates remain conjunctive.
HOST and unchanged NATIVE must both freshly succeed: no native parsing, classifier,
codec, storage, history, source or custody duty moves to HOST or consumes its cache
or verdict. Native22 units/capacities/read10s/context120s and all HG066 narrowing
remain unchanged. The finite HOST30 ledger begins before config and continues
through terminal handling, with before-work reservations, repeated-work accounting
and no per-phase/file/batch/retry reset. Complete all-path/full-byte/mode/index-hidden/
staged/untracked/helper-isolation checks remain mandatory.

PREIMPORT1800s, FINAL129600s, one worker108000s with3600s terminal reservation,
HOST stream120s and20s termination observation follow the exact source policy.
Existing worker1200/6600/120s, API60s/sign15s, retry/expiry/rollback and cleanup guards
are unchanged. S/D/C brokers and HOST helpers retain HOST RSS membership, unknown
children default HOST, and allocation lifetime cannot be relabeled/refunded.
Unenforceable metering, IPC, descendant/RSS or cancellation bounds deny. Lower-bound
measurements are never future maxima or feasibility PASS. The surviving descendant
after direct-child-9 remains an unclosed actual enforcement obligation.

The immutable acquired owned_store and actual reached initial/terminal facts
remain distinct. Both FINAL layouts require strict success equality; matching
failed source/import/recheck paths preserve actual changed identities and reasons.
Partial facts use bounded lossless emergency routing without fabricated values,
exits or authority. All14 FUTURE_CHECKS remain NOT_RUN; full native/host/worker fit
remains NOT_DETERMINED. Historical execution UNVERIFIED, acceptance_eligible=false,
execution_reuse=false. No runtime classifier/controller/App/DB/config/schema/
permission, frozen semantics or product requirement state changes here.

Actual normal HG067 merge, complete root-reviewed installed readiness and explicit
SAME HG058 regrant are additional prerequisites to continuation. Fresh K/eight checks,
BOTH complete11asset reviews/root install/authenticated full O-to-ACTUAL-K BEFORE
ordered[K,P]/exact pin rechecks/explicit CONTINUE remain required. Fresh T20/truthfulR/
new reviews/strict own RROH/root19/final install/admission/private O-to-H AND strict
P-to-H/public denial/unchanged worker/App unit+harness/fullDB/cleanup/live hosted gates/
normal protected merge remain required. No earlier preparation replaces acceptance.
KL081 waits for actual HG058 merge/readiness. Old PR99/102, dirty KL055, HG064 failed
ancestry and HG063 queued cleanup remain preserved; no old driver is rerun.
