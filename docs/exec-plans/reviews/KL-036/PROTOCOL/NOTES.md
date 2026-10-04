# KL-036 independent protocol review

Reviewed implementation/result SHA: `96ebb9e0e95211fc684273e7b69a49dc11e11e87`.
Protected base: `af09be228fbc89d074b6e863c83e1fdda343d55b`.
Recorded tested SHA: `6a3f10ef424f41bb690d8835f952484b0ca4f87b`.
Status: PASS. No BLOCKER, REQUIRED_FOLLOWUP, or NONBLOCKING findings.

This review independently inspected the committed diff, task packet, result,
prerequisite results/integrations and recovered raw check evidence. It applied
the repository pr-merge-reviewer and protocol-guardian skills. It did not use
other reviewers' conclusions, execute database fixtures, run App/full-DB gates,
change installation, or perform Git publication.

## Authority and revision verification

CURRENT_DOCUMENT_INDEX.json resolves the frozen Protocol and DB baseline. Their
committed SHA256 values match the index. Review covered Protocol section 2,
sections 6.2–6.7 and T5/T8 in section 8, together with DB S01–S04/S27–S32,
command ownership/replay section 3, locking/candidate/time sections 4.1–4.3,
and T5/T8 section 5. Invariants INV-10/11/12/13/17 retain their meanings.
Existing T6 contracts and implementation serve as success/denial observations.

The protected base contains PASS results and MERGED integration records for
namespaced KL-024, KL-026, KL-025, KL-075 and KL-019. Their recorded merges are
ancestors of the protected base. M3 retains empty product PASS claims, disabled
production auto-activation and non-executable shadow. The one linear commit
between tested and reviewed SHA adds only the own result and new own evidence;
source, tests, contracts, configuration and authority remain byte-identical.

## Protocol behavior

The bounded TEST worker calls existing AcquireLease/RenewLease and guarded
CREATED-to-LEASED AdvanceAttempt owners. Historical lease responses cannot start
or sustain work. It grants no dispatch, T6, authorization, attempt-creation,
terminal-reopening or budget-reset capability. Heartbeat/stop waits occur with
committed idle connections.

The separately registered TEST ReapIntent wrapper checks subject, policy,
environment, principal and separate internal service before replay and under
S01. Its scan commits before coordination and supplies expectations only. First
use takes S01, S27, sorted applicable S31, receipt and current S29. The private
prepared branch rechecks exact request ID/revision, attempt ID/status, owner,
fence, intent status, deadline and expiry after locks. Fresh database time
derives DEADLINE_EXCEEDED/LEASE_LOST, or CANCELLED/CANCELLED only with explicit
immutable TEST recovery policy. Caller-selected terminals, generic FAILED and
mismatched prepared writes cannot enter this branch. The historical synthetic
generic branch remains unchanged.

Nullable owner acceptance is limited to current unacquired ADMITTED/PENDING,
fence zero, CREATED attempt, null expiry and elapsed deadline. It does not admit
a stale unowned candidate after acquisition. S27/S29 closure, receipt, event and
outbox are atomic. Same-key/hash replay requires current TEST registration,
returns historical identities and executable=false, and creates no new effects.
Missing receipts or changed payloads cannot authorize a fresh stale transition.

Unknown cleanup uses separate existing MarkUnknown transactions. Possible sends
retain occupation; interrupted cleanup leaves safe outstanding accounting.
CancelUndispatched cannot refund after permit. Late verified settlement changes
accounting only and cannot restore planning, sending or T6 authority. No model,
provider or network operation was added inside coordination.

## Independent evidence inspection

All sixteen final required checks have zero exit code, exact tested SHA and
lossless committed envelope/payload hashes and byte lengths. Raw records were
read through Git at the reviewed SHA, rather than relying on ambient files or
navigation counts. All standalone selectors collect and execute one case; the
unit file collects/executes two, the DB file seven, unit regressions 249, and
harness regressions 1492. Collection, started cases, passing call phases and
JUnit identities/counts agree. Setup/call/teardown all pass, with no failures,
errors or skips. Both harness workers collect the same 1492 cases, and the
runner's complete execution, clean source, tested SHA, zero exits and file
hashes agree. Unittest class paths were normalized for JUnit comparison without
altering parameter identities. Lint, typecheck and harness validation raw outputs
report success.

Each final DB selector and the whole file includes migrated task-owned namespace
and equal before/after foreign inventory, removed owned resources and joined
children. Complete relation snapshots include revision history and T6 closure.
Raw witnesses include distinct OS/backend PIDs, PostgreSQL blocker/lock records,
committed scan/idle waits, trusted elapsed server time, and ten complete rollback
observations in the DB suite. The suite includes 44 complete zero-effect
observations and ten PostgreSQL blocker observations.

The independent-worker selector records actual consumed ordinary work, saturated
queue capacity, a separately successful admission process, committed heartbeat,
worker exit -15, a distinct reaper PID and bounded independent termination.
Restart/takeover retains original deadline/budget and stale authority denies.
The accounting selector records unchanged unknown occupation until reliable
settlement. The T6 selector uses the actual ProtocolExecutionService/T6 owner,
records FOUND_VALID_PLAN/COMMITTED, and verifies complete identical history after
queued stale reaping and commit-before-scan. No tested success is seeded.

## Limits of this PASS

This is the packet's bounded isolated TEST slice. Privileged internal service
sessions, upstream immutable S26/S34–S37 and COMMIT_READY preparation are explicitly
declared instrumentation. This does not prove restricted-login ACL containment,
full planning/model/provider workflow, product W/I obligations, M4/release,
production readiness, installed-App/full-DB admission, or merge PASS. No frozen
meaning requires a change or ADR for the implementation reviewed here.
