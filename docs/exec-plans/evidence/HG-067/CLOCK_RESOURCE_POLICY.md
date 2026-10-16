# R3 proposed whole-route clocks and resource ownership

PROPOSED_NOT_APPROVED. This supersedes the R2 proposed HOST clock policy and its
RSS/group membership wording only as enumerated here. No number is merged
authority. The human's seven approved preparation constraints permit a reviewable
finite proposal; neither reviewer approved a timeout extension. This definition
runs no worker, DB, native audit, installation or old driver.

## One continuous invocation and unchanged command bounds

S remains the live installed authentication/lock/HOST-ledger/publication owner.
Its monotonic origin is before its first config/ownership/lock/auth attempt and
never resets or pauses. PREIMPORT keeps1,800s total. FINAL proposes129,600s (36h)
total, including acquisition, all native contexts, every worker command, waiting,
reentry, cleanup, cancellation/termination, output, publication and uncertainty.
Every named phase is subordinate to that SAME absolute route deadline. Its
reported interval remains first entry to last reached observation, including all
intervening waits; there is no independent600s deadline or fresh phase allowance.
Starting/reentering a phase later never moves the invocation deadline. Every
second is in the invocation; every second of WORKER_START through worker cleanup/
artifact verification is also in its single worker interval. Overlapping phase
intervals are observations, not additive time credits.

FINAL's worker interval proposes108,000s (30h), entered ONCE at WORKER_START,
covering build, daemon readiness, sync, all14 required full-DB plan commands,
artifact handling, all cleanup and termination. Before its first start S must
have at least108,000s plus3,600s of its original overall clock left. That is a
reservation against the existing deadline, not fabricated elapsed consumption
or a new clock origin for HOST. All later operations still use the same route
deadline; the last3,600s is finite reserved headroom for complete post-worker
source/auth rechecks, actual exit reconciliation, terminal output/final guards,
App attempt/ack and cleanup uncertainty. It is not permission to skip those duties
or a fresh hour granted after an exhausted invocation. A new invocation may not
restart a failure into readiness. PREIMPORT never enters the worker interval.

Existing image-build and dependency-sync limits remain1,200s each. Each of the
14 gate_plan commands keeps db_ci.run_capture's6,600s limit, including the
destroy/peer_remove commands as actually invoked by local_gate.run_worker. The
ordinary checked/control/cleanup calls retain120s; daemon readiness retains at
most60 attempts of10s plus the existing1s sleeps. Host local Git/transport stream
limit is proposed120s, matching the existing120s checked route rather than R2's
arbitrary60s. Host metadata reads stay10s; native reads stay10s and native contexts
120s; API requests stay60s, signing15s, permissions/retry/expiry/rollback unchanged.
All blocking work uses the minimum of its existing command/read limit, applicable
worker remaining time, and remaining absolute invocation time. No command may
start unless its full existing limit plus required cancellation/cleanup/tail
reservation fits; exhaustion denies before dispatch instead of starting a command
with a silently shortened advertised limit. This is host resource admission,
not command authority, an alternate worker or a shorter passing plan.

Keep the existing15s SIGTERM grace from db_ci.run_capture. Proposed trusted outer
supervision adds at most5s to observe SIGKILL/reap, hence20s termination-observation
reserve, INSIDE worker/overall limits. It does not extend a command's1,200/6,600s
execution limit. Start cancellation while that reserve remains. Unreaped/escaped
descendants, unknown exits or unavailable enforcement yield INTERRUPTED/lower-bound
diagnostics and no local eligibility; never wait unboundedly or infer a zero.
All remaining label-bound resource cleanup remains required and within the same
worker/overall budget. A failure to clean before those finite bounds is a failure,
not cleanup PASS. No old completed command or stage is rerun during preparation.

## Why these proposed finite values

At K local_gate.py:168-264, gate_plan has5 quality commands,7 db_ci plan entries
after lint/typecheck, plus destroy and peer_remove:14 default6,600s captures.
Together with build/sync this is94,800s. A conservative count ceiling of64
existing120s control/setup/copy/cleanup calls gives7,680s; the currently enumerated
serial path has at most32 such calls (including fallback evidence copy and both
four-command label-bound cleanup sequences). The separate60*(10+1)s daemon loop
adds660s. Conservatively reserving20s for EACH of16 capture endings adds320s.
Those ceilings total103,460s. Proposed108,000s leaves4,540s of finite headroom
for unmeasured in-process artifact walks/parsing/hashing/serialization and waits.
The outer129,600s additionally leaves21,600s for the whole non-worker lifecycle;
worker admission reserves3,600s of that for its complete terminal route. These
are reviewable conservative policy allowances, not measured maxima or guarantees.
Any implementation that discovers more calls or cannot enforce these envelopes
must deny or return a new concrete reviewed-spec conflict, never change the plan.

Retained HG066 evidence reports fullDB1,694.281s, harness406.811s, serial recorded
checks2,187.634s and full controller2,210.9460785s, all historical observed0.
Its raw receipts/logs and retained App-summary receipt hash are bound read-only.
Those durations are lower bounds for that run only; they establish neither a
maximum nor future project/privileged/native feasibility. R3 clock-only controls
accept a route containing those durations, a route with every existing capture
at its full source limit plus conservative controls/startup/grace, and exact
proposed whole-worker/overall boundaries. Overrun, too-late start, reentry/reset,
truncated command budget or tail omission rejects. No actual execution is reused
as a new task/requirement/acceptance PASS.

## Explicit resource membership; no payload escape into HOST

R2's 'entire process group including native/helpers' is replaced by explicit
purpose/ownership groups. HOST includes live S, credential-free installed D/C
brokers, all HOST metadata/Git/copy/signing/auth/IPC/output helpers and every owned
allocation they retain. Its proposed1GiB process_group_rss_bytes cap applies to
the aggregate resident set of those HOST-owned processes, including their fixed
interpreter baselines, not just S. All HOST allocation/cache/path/byte/start
counters retain their numerical values, whole-invocation lifetime and no-reset
rules. RSS/live high waters never reset at worker/native transitions or after
eviction. Unclassified child/retained allocation is HOST by default; a child
cannot escape its group by fork/session changes or a supplied purpose flag.

NATIVE payload execution uses explicitly enrolled installed native sub-executors
under C, with its OWN unchanged22 counters, parse/cache/allocation/read/context
constraints. WORKER payload commands/owned Docker daemon/containers keep their
existing reviewed command, isolation, labels, mounts, artifact and cleanup guards.
They are not new HOST-helper RSS allocations merely because S waits for them.
They are not granted new memory/credential/command authority or a new timeout by
this definition. No new worker memory PASS, or proof of a finite aggregate worker
RSS from the1GiB HOST cap, is claimed. Worker/native runtime memory fit is unmeasured
and their existing required acceptance/enforcement remains mandatory. S's36h
outer supervision and worker30h interval include ALL waits for those domains.

The native/worker sub-executor purpose must be enrolled by the live trusted
installed owner using exact existing context/command identity, OS process/container
identity and generation. It cannot be selected by candidate code or a receipt.
Purpose/ownership is fixed for an allocation's lifetime; retained bytes cannot be
reclassified at a phase boundary to refund HOST usage. D/C broker-owned buffers
remain HOST, even when transporting native/worker results. Any native-reader work
stays NATIVE and is freshly charged there; no HOST reader/cache supplies it.
Any HOST prerequisite performed by a broker/helper, including worker source.bundle
preparation/import, host evidence copy/validation and installation/auth snapshots,
stays HOST and is actually metered; running it beside a worker is no exemption.
Boundary I/O can therefore count in its actual originating domain AND HOST when
HOST copies/retains/compares it, without granting custody/deduplication credit.

HOST Git and signing starts are disjoint process starts, so when accounting is
EXACT, git_operations+signing_operations+observed started HOST D/C brokers cannot
exceed process_operations. Native/unchanged worker payload process starts are
not fabricated HOST starts. Resource membership, cumulative metering, descendant
control, aggregate HOST RSS and opaque import measurement are FUTURE NOT_RUN
integration obligations. If a platform cannot enforce group separation, bounds,
no-follow ownership or cancellation, it denies; no model test establishes those
properties. The unchanged worker/native acceptance gates cannot be satisfied by
choosing different resource membership or by a hypothetical oracle record.

## Exact versus partial relations

For EXACT full counters, metadata_read_bytes<=file_read_bytes and
object_copy_bytes<=file_write_bytes. Git/signing starts plus known HOST broker
starts fit process_operations. LOWER_BOUND does not imply these measured lower
bounds are exact totals: subset>reported-total is allowed in a non-success
ACCOUNTING_INCOMPLETE/interruption record, never repaired by inventing total
bytes. All stored values remain truthful lower bounds and never clamp over-cap.
Independently of counters, C EXITED/UNKNOWN implies D EXITED/UNKNOWN on every full
or emergency status; D NOT_STARTED cannot parent a reached C. UNKNOWN represents
an execution observed started with outcome lost, not an observed zero.

Only a successful full record requires every release pin equal its bound actual
K/H revision, and PREIMPORT acquired root AND acquired objects device/inode pairs
distinct from the original source pairs. Truthful denied/interrupted binding
mismatches remain representable; their mismatching values are not rewritten or
promoted. A mismatch reason ASSET_MISMATCH/IMPORT_DENIED records that failed
observation. Actual independent source/exit/accounting authenticity remains NOT_RUN.

## Rechecks without falsifying the ordered phase history

The fixed nine phase statuses describe the first ordered pass. Reentry clocks
still span first entry to last actual observation. A new fixed two-item
post_worker_rechecks vector records SOURCE_AFTER then AUTHENTICATE_AFTER after
the worker; its states form COMPLETE prefix, at most one DENIED/INTERRUPTED, then
NOT_STARTED suffix. A failed repeated check is reported at FINAL_BOUNDARY failure
while retaining the earlier completed first-pass phase, never rewriting an already
reached later phase as unreachable. Its elapsed observation is the same complete
first-to-last interval in that named phase. FINAL success requires worker COMPLETE
and both repeated checks COMPLETE; PREIMPORT has no worker/recheck vector activity.
Worker failure stops before those rechecks, followed by required finite cleanup.
Diagnostic changed/partial source snapshots retain actual facts without equality
requirements on denials. All eligible publication still requires the complete
fresh final checks, authenticated bindings, cleanup, actual exits, byte accounting
and existing App/root gates from the R2 ownership/publication contract.
