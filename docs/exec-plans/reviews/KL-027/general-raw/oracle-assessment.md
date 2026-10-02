# Independent GENERAL review: harness-backlog-v0.2/KL-027

Reviewed implementation/result: `1df15275291ee99b98bd063e856d45c83ccc6f81`.
Protected base: `6d1348c5a731afb74fdf6f2345109a446cdb597c`.
Source-tested implementation: `8b446eda05bfb8201fb48c89fda5d03eb40c2218`.

Read root AGENTS, current index, complete KL027 packet, pr-merge-reviewer skill,
Protocol 5.3–5.6/6.1–6.9, named DB ownership/lock tables and clauses, acceptance
2–4, HG038 preparation, execution contract and actual matching owner code.
Read prerequisite results/reviews/integrations, including transitive KL078/KL079,
and M2 closure. Independently audited ancestry rather than trusting entry-audit.
`audit.py` is a read-only audit; its complete successful output is `audit.json`.

Scope: actual base-to-head paths are precisely the own DB/unit tests, own contract,
result and evidence. No production source, migration, frozen authority, requirement
set, workflow, dependency, completed prerequisite or product closure changed.
Tested-to-reviewed diff is result/new raw evidence only; implementation and contract
are byte-identical. Normal protected first-parent two-parent PR merges contain all
required prerequisite PASS results/reviews, with task-only linear review suffixes.
M2 PASS is an ancestor; it is not treated as G-SHADOW closure.

Twelve exact check commands and headers match the protected packet; recorded
log hashes match actual committed bytes. JUnit collection/execution counts are
1 namespace, 1 full trajectory, 9 revoke/positive controls, 3 expiry, 1 repair,
43 scope, 61 own-suite, 232 unit, 676 harness. All have zero errors/failures/skips.
Harness validation logs contain HARNESS_CHECK_PASS; lint/typecheck exit successfully.
No xfail substitute exists in the new tests.

Independent read-only rerun on reviewed head:
`PATH=/private/tmp/kl001-bootstrap/bin:$PATH UV_CACHE_DIR=/private/tmp/kl027-general-uv-cache uv run --offline pytest -q tests/unit/protocol/test_test_only_demo.py -rA`
passed both tests in 0.73 seconds, captured in `unit-review.log`.
Initial cache access was unavailable in the filesystem sandbox; writable temporary
UV_CACHE_DIR resolved it without escalation or source changes. No DB lifecycle,
reset, Docker test or foreign DB fixture was run by this reviewer; DB resource
ownership remained with the independent DB_CONCURRENCY reviewer.

## Exact oracle assessment

- Namespace PU: `fixture_namespace` binds full HEAD, fixed demo label and resolved
  root digest. OwnedLifecycle validates before construction/nested bootstrap/reset,
  start/runner/connection/destroy; ambient names/runtime overrides fail. Imported
  migration bootstrap receives the selected lifecycle. Before every DB fixture it
  runs the PU. Raw full suite records 61 namespaces and 61 empty exact project
  cleanup inventories, revision e8c2f1a6b904. All URL/current_database checks match.
- Source-to-output: seed_source registers only TEST metadata/admitted immutable
  source/artifacts. Actual fact uses restricted RecordActualExecution; no target
  S15/S16, projection/build, snapshot, F/D/N, certificate or T6/T7 seed exists.
  Actual CanonicalViewService builds/completes/seals, merged preparation records
  source-bound projection/dependencies/build, actual T3 publishes. KL024 admits
  and acquires; KL075 snapshot/forward stages and KL076/079 immutable computations
  and both action resolutions/shared validation create actual COMMIT_READY.
  Full trajectory checks exact IDs, hashes, membership, basis, receipt/event/outbox,
  server finite minimum and ordered TRAINING/NUTRITION issuance pair. Observer spy
  calls/returns the original T7 guard, records actual eligible=true, then real START
  for both members. Snapshot and source hashes are not fabricated PASS certificates.
- Revoke: each operation/change uses an independent owner-produced subject and
  fresh command key. CONTINUE has actual START/IN_PROGRESS/current binding. RESUME
  has authenticated ordinary PAUSE/PAUSED and original START/current binding;
  positive resume appends one immutable revision. Before loss, both CONTINUE/RESUME
  actually succeed; resumed cases pause again and use the new binding. New START
  target is absent and exact P/A is eligible through the live existing session;
  actual START guard checks the distinct fresh target. STOP derives locked current
  epoch, appends exact S17/S18/S43 and atomic receipt/event/outbox. Artifact revoke
  uses merged strict global owner. Denials assert intended exact registry causes,
  fresh key/no replay and complete persistent inventory equality. Historical START
  and bundle replay return identical immutable IDs, executable=false, zero writes.
- Expiry: 3 independent operation trajectories use actual finite admitted-source
  expiry. Issuance minimum equals source admission_end; trusted DB clock observes
  crossing. Pre-loss lifecycle/eligibility and successful CONTINUE/RESUME establish
  authority before expiry. Actual registry rejection and unchanged rows preserve
  old A/certificates/bindings. Full suite adds four observed post-lock T6/START/
  CONTINUE/RESUME expiry cases, trusted pre-spawn/post timestamps, actual blocked queries,
  TIME_INELIGIBLE T7 or expired-resolution T6 and complete zero effects. However,
  the actual observed blocked state has no trusted timestamp asserted before source
  expiry: connection/scheduling delay can consume the approximately half-second
  window after the pre-spawn observation. These witnesses do not establish expiry
  crossed *during* an observed lock wait. This exact oracle gap is BLOCKER B01.
  Equality is
  separately actual pure-predicate PU; no DC equality or caller-clock claim exists.
- F2: same-root structured KL024 revision creates request 2/new attempt, reacquires
  and traverses forward stages. New F records original F parent/hash; computed D2
  and N2 (fuel 60) replace no old rows. Mixing old D/N/resolutions/validation fails
  preparation, progression and T6 with unchanged rows. Root deadline and budget
  payload remain identical. Backward transition and old attempt reject. Coherent
  new complete closure commits/starts through real owners.
- Scope: 43 cases cover authenticated subject/policy/environment/principal,
  production/evaluation role/connection, shadow/production wire and policy scopes,
  missing policy/runtime/context/evidence/N/validation, immutable IDs/hashes/action
  bindings, current epoch/generation/manifest/execution basis/fence, STOP/revocation,
  and full-policy legacy downgrade. Missing source denies at the actual owner and
  any preceding legal admission/stage persists only as explicitly documented.
  Shadow policy has no daily head/issuance/binding/executable result. Input revision
  uses restricted admitted S14/S43/current frontier/epoch and invalidates fresh
  CONTINUE while preserving source F/D/N and historical execution.
- Full own suite: all 61 independent cases execute without skips. Raw witnesses
  include 410 forward stages, 174 F/D/N output audits, 173 full action output audits,
  44 exact zero-effect denials, 12 lifecycle preconditions and 9 historical replay
  identity-only audits. Task status never promotes requirement/layer/M3/G-SHADOW/
  release/production state.

## Inherited limitation independently assessed

Actual full-suite witness confirms D `70df6b37-c4c3-50b0-95a2-6e05e8e69cad`
physically references F `063632fe-2e06-5db2-bb51-9a178aae144a`, while DEMAND_FEATURE
certificate proposal_id names N `f184607d-5905-5241-aed9-7dcf7f54c7e1`.
Source `transactions.py:3940` selects validation.ref_s34_id as demand_basis[2];
line 4070 copies it to the descriptive attribute. Exact demand identity/revision
remains D. `_progress_sources` checks D.ref_s34_id/F hash, N.F/D/manifest/policy;
`_verify_full_progress` reconstructs current full validation and both action
bindings; `require_full_execution_request` rechecks these under fresh locks and
exact per-member proposal/resolution. The erroneous attribute is not an authority
guard input and does not permit invalid execution. This is an inherited separately
scoped NONBLOCKING audit metadata follow-up, declared in KL077 and KL027 results.

BLOCKER B01 requires a tests-only temporal witness repair, all twelve fresh checks
and fresh reviewed implementation/result SHA. Capture clock_timestamp with the
actual pg_stat_activity blocked observation and assert it is strictly before the
source end while the blocker remains held; then observe trusted time after expiry,
release and retain exact zero-effect post-lock rejection assertions.

Final normal hosted quality/PostgreSQL and selected-task merge
gates remain separate mandatory facts after all fresh reviews are persisted. This
GENERAL review is CHANGES_REQUIRED and does not establish hosted CI, MERGED,
product or release closure.
