# Independent GENERAL assessment of KL-027

Task: `harness-backlog-v0.2/KL-027`. Protected base:
`6d1348c5a731afb74fdf6f2345109a446cdb597c`. Tested implementation:
`72a9a5f3f9529028708f64ece3bbec6d791413a7`. Reviewed implementation/result:
`ff93c08c7c32fba9e8dede0c161bb4f97bc98259`.

This is a full independent GENERAL review of the committed task, including its
complete fixture, source/owner boundaries, current indexed authority, raw final
evidence, entry prerequisites and bookkeeping suffix. Historical review opinions
were inspected to identify the prior finding, then independently checked against
the actual new implementation and raw evidence. No implementation/result edit,
commit, HEAD change, DB lifecycle or foreign fixture execution occurred. The only
writes are this task's GENERAL review records. `audit.py` contains the independently
performed mechanical checks; `audit.json` retains their complete observations.

## Authority, prerequisites, lineage and scope

All current indexed document and machine-readable SHA256 values were recomputed.
The Protocol 5.3–5.6 and 6.1–6.9 requirements, relevant DB ownership/identity/lock
clauses, acceptance 2–4, HG038 preparation and M2 closure were inspected. Actual
namespaced PASS results and every required PASS review for KL017/019/022/023/024/
025/074/075/076/077/078/079 were read and checked against protected-base Git.
Every claimed normal merge is an actual two-parent first-parent PR merge with the
reviewed revision on its source ancestry, and each source suffix is linear and
confined to its own review directory. Result schemas, semantic check completeness,
tested ancestry and tested-to-reviewed bookkeeping were checked for prerequisites.
M2 is PASS with 12 unchanged integration-record hashes. Missing later prerequisite
integration files do not substitute for merge evidence: their actual normal Git
merges were proved, and their original result UNMERGED payloads were preserved.

KL027 result/review/integration records are absent at the protected base. The final
task result is schema- and semantically valid, names all 12 exact PASS commands,
has empty requirements_covered, and reports UNMERGED. Base → tested → reviewed
ancestry is valid. The sole final tested-to-reviewed commit updates the task result
and adds new task evidence; every new evidence path was absent at its parent.
All three test/contract blobs are identical at tested and reviewed revisions.
The full diff consists only of the three declared files and own task bookkeeping.
Production code, migrations, grants, CI/lifecycle, frozen/index/requirement files
are unchanged. The implementation diff passes `git diff --check`; trailing spaces
in the archived e78a59b pytest failure log/XML are preserved raw traceback output,
not implementation changes or a functional finding.

## Exact check evidence and oracles

All final raw logs independently match their recorded SHA256, full tested SHA,
resolved root, exact packet command and exact oracle header. XML counts and actual
testcase counts agree with the log summaries; failures/errors/skips are zero.

| Packet check | Actual count / success evidence |
|---|---|
| demo_namespace_and_boundary_pu | 1 passed |
| demo_owner_trajectory_e2e | 1 passed |
| demo_revoke_denials_dc | 9 passed |
| demo_expiry_denials_dc | 3 passed |
| demo_fdn_repair_e2e | 1 passed |
| demo_scope_denials_dc | 43 passed |
| demo_suite_e2e | 61 passed |
| harness_validation_passes | HARNESS_CHECK_PASS |
| unit_regressions_pass | 232 passed |
| harness_regressions_pass | 676 passed |
| lint_passes | All checks passed |
| typecheck_passes | Success: no issues found |

The actual suite contains 61 namespace/runtime/admitted-input/sealed-source/cleanup
witnesses, 410 forward stages, 174 F/D/N outputs, 173 full outputs, 56 full prepared
chains, 12 lifecycle/current preconditions, 6 real T7 successes immediately before
authority loss, 44 exact zero-effect denials and 9 historical identity-only replays.
Independent parsing checks 182 persisted snapshots for one-to-one successful
receipt/event/outbox linkage; recomputes output/demand/nutrition hashes and physical
F→D→N relationships; and checks 44 issuance certificate instances for closure
digest and minimum finite validity. Each issuance binds the exact member content,
proposal, action resolution, shared validation and both action-resolution validity
dependencies. These are raw-file checks, not a reliance on the implementation's
oracle-audit summary. XML records no skipped/xfail/zero-collection substitute.

## Source and owner trajectory

The only dynamic test imports are the own namespace PU module and merged migration
bootstrap. Imported bootstrap_two_phase receives the selected lifecycle; no foreign
pytest fixture/reset/cleanup is called. Explicit source inputs are registered TEST
subject/policy/environment/program, bounded immutable artifacts and admitted
USER_REPORTED/NONE evidence/association/admission. The restricted actual-input
recipe uses execute_command, S01 lock and idempotent_outcome, with S14/S43/S01 and
receipt/event/outbox atomically produced. It does not derive actuals from plans.
The post-source audit expressly proves every target output table empty.

Actual CanonicalViewService begin/write/complete/seal produces S15/S16 and a fixed
membership certificate. Merged preparation owners capture the exact sealed source,
record source-bound projection/dependencies, build/complete READY and publish T3.
Real KL024 admission/acquisition and KL075 snapshot/stages precede KL076 F/D/N and
KL079 both action resolutions/shared validation. Full request and persisted policy
select the strict T6 reconstruction; no legacy or synthetic completeness path is
used. T6 produces two ordered TRAINING/NUTRITION members, exact P/A, immutable
server-minimum certificates, intent success and COMMITTED attempt atomically.
The observer-only real T7 spy returns its original decision unchanged; current
non-bearer eligibility is true before successful START for both members. Real
ordinary PAUSE precedes positive RESUME, which appends exactly one revision-2 S45
and preserves original START binding/A and all upstream rows.

## Authority-loss, expiry and repair

Each CONTINUE/RESUME/new START denial has its own owner-produced trajectory. Live
IN_PROGRESS/current binding, PAUSED/latest immutable binding after real ordinary
PAUSE, or a distinct absent START target is established before loss. CONTINUE and
RESUME additionally perform the operation successfully before loss, then use a
fresh key (and re-pause after successful RESUME). For new START the same P/A is
observed through the existing live session, while its target is separately absent;
the actual fresh START rechecks its own guard. STOP reads the locked current epoch
and atomically produces S17/S18/S43/S01; artifact revoke uses the strict actual
SafetyRegistry owner. Expected epoch is updated after STOP to avoid merely testing
an expectation mismatch. Exact registry/current-authority/expiry causes exclude
lifecycle, binding, idempotency and transport substitutes. Exhaustive snapshots
prove no failed-command effects, including first-use head/session placeholders.
Historical START/bundle replays return the same IDs with executable=false and
unchanged snapshots; earlier F/D/N, certificates and started history remain intact.

Admission freshness expiry is derived from trusted DB time, included in server
validity closure and asserted as the issuance minimum. Before/after eligibility
checks use actual guarded owners. The four real-PG lock-wait cases lock S29, S38 or
S44 as appropriate, record trusted clock_timestamp in the query that observes the
actual blocked waiter, and assert before_wait ≤ blocked_at < immutable source_end.
The blocker remains held until an independent reader records time > source_end.
Finally-safe rollback then releases it. T6 rejects expired resolution; T7 returns
TIME_INELIGIBLE; each snapshot remains identical. Raw final times independently
satisfy those inequalities for T6/START/CONTINUE/RESUME, with real blocking PIDs and
correct owner lock queries. The one-second owner timeout is unchanged; the launcher
waits until half a second before expiry after blocker setup. The earlier two-second
attempt's four failures/interruption remain honestly archived. Thus the previous
GENERAL blocking temporal observation is resolved on a new tested revision with
all twelve fresh checks. Pure equality is separately asserted over the actual
eligibility, lease and deadline predicates and is never presented as DC equality.

F2 repair uses a real structured constraint revision under the same live root,
fresh attempt/acquisition/snapshot and frozen forward stages. Old F1/D1/N1 and
resolution/validation rows remain unchanged, mixed old sources are rejected at
preparation/progression/T6, and recomputed F2/D2/N2 produces a coherent full bundle.
Original root limits, reservations/settlement payload and deadline are unchanged;
neither terminal reopening nor a backward stage transition is used.

## Scope, namespace and state discipline

Namespace validation runs before lifecycle construction and every nested bootstrap,
reset/start/command/connection/cleanup. Exact SHA first7, resolved-root bytes SHA256
first12 and fixed demo label are enforced, with malformed/foreign/ambient/peer-root
and nested cleanup pure negatives. Every DB connection checks current_database.
All 61 final witnesses use kineticloop-kl027-demo-72a9a5f-02d718cec5f6 and its matching
database at migration e8c2f1a6b904. Each cleanup records selected bootstrap/reset/
start/destroy and empty container/volume/network inventories. Resource ownership
remains test_only_demo_suite; this GENERAL reviewer invokes no real DB operation.

Scope negatives reject foreign subject/principal/policy/environment/production or
evaluation roles/connections, executable shadow/production wire and policy scopes,
missing mandatory context/evidence/N/snapshot/validation, stale epoch/basis/fence/
manifest and missing or mismatched full sources/certificates. Shadow-policy source
setup stops before execution authority; TEST-issued rows remain TEST. No production
auto-activation, new public command, provider/model/network wait, HTTP/live-model
claim or product/layer/M3/G-SHADOW/release closure is introduced.

Independent read-only pure rerun: 25 passed, zero skipped, 1.87 seconds, covering
the own namespace/equality tests, execution/full execution identities, full-action
preparation and unchanged public commands. Raw log and XML are in this directory.

## Findings and merge conditions

No GENERAL blocker remains. The inherited DEMAND_FEATURE proposal_id explanatory
metadata points to the shared validation's N anchor instead of physical D.ref_s34_id
F. The raw audit confirms this while separately proving authoritative D→F, N→F/D,
member-specific resolution/proposal and full shared validation. Actual upstream
_progress_sources and _verify_full_progress reconstruct these exact bindings under
the existing guards; the descriptive attribute is not a guard input. Retain KL077's
separately scoped metadata correction; do not alter immutable historical certificates
or expand KL027's tests-only scope.

GENERAL PASS is independent of PROTOCOL/DB_CONCURRENCY PASS, final unchanged hosted
quality/PostgreSQL/selected-task merge gates and normal MERGED. Those remain required
before ordinary merge. Following this reviewed SHA only a linear task-scoped
REVIEW_RECORD_ONLY suffix is allowed; substantive changes require fresh checks and
reviews. No product or release PASS follows from this task result or this review.
