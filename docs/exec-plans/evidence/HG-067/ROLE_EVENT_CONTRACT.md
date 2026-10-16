# R4 process, event and record contract

This is a prospective definition, not a running process, changed credential or
receipt authority. The installed private preimport/final entries and existing
root admission/publication authority remain the only owners. All literal checks,
native22/read10s/context120s, worker limits and historical gaps remain conjunctive.

## Live owner and executions

S is the live trusted installed controller/observer. It owns the one HOST ledger,
monotonic overall clock, installation lock, authenticated App/config/authority
state and existing final publication authority. S creates the ledger before any
config/ownership read or attempted lock/auth operation. It acquires the existing
nonblocking executor lock before source/auth execution and holds it until terminal
record handling and any already-authorized publication have completed or failed.
No exited process owns the lock or publishes. No credential is transferred.

D is a bounded credential-free installed data-driver child. C is its bounded
credential-free installed broker child, controlling enrolled installed native
sub-executors and, on FINAL, the unchanged isolated worker subtree. C/D broker
allocations remain HOST; payload membership is fixed by CLOCK_RESOURCE_POLICY.md. D observes C's actual
exit; S independently observes D and receives/reconciles C's actual observed exit.
Lost or conflicting exit observations never become zero. D and C use only the
exact independently installed release; source files are data, never privileged
imports. This names roles for the future implementation, not a public dispatcher.

S performs/meters all HOST prerequisites and retains the authoritative ledger;
there is no transfer of ledger ownership when D/C start or stop. S may use private
bounded same-invocation pipes for typed requests/observations, never a reusable
receipt. Every host operation requires S's before-work reservation and actual
after-work accounting, or S performs it itself. The implementation must deny if
it cannot independently reconcile actual I/O/allocation/exit facts. Unknown
consumption is a lower bound and cannot complete. D/C cannot select identities,
skip a phase, reset budgets, publish, authenticate, or authorize host readiness.
C creates each already-required NATIVE context at its actual entry with all
unchanged native duties/counters/clocks. No host data/cache satisfies a native
reader; native reads are fresh and charged again. IPC and observer overhead count
against HOST allocation/output/overall bounds. No new API scope/endpoint/key,
candidate permission or command-owner boundary is introduced.

## Exact acquisition and phase order

PREIMPORT phases, exactly once in this order:
BOOTSTRAP, AUTHENTICATE_BEFORE, SOURCE_BEFORE, OWNED_IMPORT, ASSET_BINDING,
NATIVE, SOURCE_AFTER, AUTHENTICATE_AFTER, FINAL_BOUNDARY.

FINAL phases, exactly once in this order:
BOOTSTRAP, AUTHENTICATE_BEFORE, OWNED_IMPORT, SOURCE_BEFORE, ASSET_BINDING,
NATIVE, SOURCE_AFTER, AUTHENTICATE_AFTER, FINAL_BOUNDARY.

PREIMPORT starts with the root-owned existing CHECKOUT at actual K. SOURCE_BEFORE
anchors its root/object-store identity, binds K/P/tree/controller/authority/refs/
index and performs full literal/index/untracked verification. A reached initial
or terminal snapshot ALWAYS says CHECKOUT, on every status. OWNED_IMPORT then
creates a distinct private bare native store from that inert stable source,
without hardlinks or retained external alternates. The original checkout remains
the initial/terminal source; imported native-store identity is a separate binding.

FINAL AUTHENTICATE_BEFORE selects exact admitted H/P and repository. OWNED_IMPORT
must finish acquisition before SOURCE_BEFORE can claim a source snapshot. It has
exactly two eligible layouts: BARE_CLONE creates a genuinely bare owned store;
MATERIALIZED_CHECKOUT creates an owned repository then materializes EVERY H path
with a trusted bounded literal writer, without executing filters/hooks/helpers.
The latter requires all complete physical/index/untracked obligations. The former
has source_kind BARE_OWNED, no physical checkout assertion, and complete H tree/
mode/type/object/import integrity checks. Both have a new owner-only source/native
store whose identity is bound after acquisition and rechecked before/after native.
No other source kind/layout may complete. Existing clone --no-checkout is a
non-bare unmaterialized worktree: it is NOT BARE_OWNED and is not an eligible layout.
A denial may truthfully record that failed acquisition choice with no valid source
snapshot; it must include UNSUPPORTED_SOURCE and cannot reach SOURCE_BEFORE.
This prospective layout correction is subject to separate implementation review;
this preparation performs no clone/materialization on the project.

ASSET_BINDING compares all 11 installed assets against the acquired native store
at K/H. S starts D/C only after that phase completes. NATIVE includes full required
O-to-actual-K, or O-to-H then strict P-to-H in their existing contexts. Each fresh
native output is PENDING_DATA, even when its own native verdict is positive.
S independently validates trusted execution/source/pins and reconciles observations;
synthetic/schema-valid records never establish these facts. Native failure stops
the route; a later context cannot run after a failed earlier context.

SOURCE_AFTER and AUTHENTICATE_AFTER run after native and before worker. PREIMPORT
rechecks the original physical checkout completely; FINAL rechecks the selected
owned source layout completely. Changed identities/bytes/modes/refs/authority or
incomplete work deny. FINAL_BOUNDARY then includes the unchanged worker, cleanup,
post-worker complete SOURCE_AFTER and AUTHENTICATE_AFTER rechecks, driver/executor
exit observation, output sizing and final guards. C waits for S's phase decisions,
runs the worker only when S permits the existing route, then exits; D observes C
and exits. PREIMPORT C/D exit after native and S's required terminal source/auth
checks. S stays live with lock/ledger throughout both zero-exit observations.

Every repeated check belongs to its original named phase interval and the same
ledger. CLOCK_RESOURCE_POLICY.md supersedes the former600s/4h proposal: FINAL
uses one36h absolute invocation deadline, a single30h whole-worker interval and
1h terminal headroom reserved before dispatch. All waits/reentry/cleanup/terminal
work remain continuously attributed, and every existing worker/native/read bound
remains conjunctive. There is no reset or dropped wait. The first ordered phase
statuses and explicit post_worker_rechecks retain both first-pass completion and
any later failure at FINAL_BOUNDARY, without falsifying an already reached phase.

## Terminal records and publication

S distinguishes three things: native pending data; diagnostic HOST records; and
eligible accounted output. Native files produced before terminal gates are named
and retained as PENDING_DATA/diagnostic only, with no acceptance/continuation credit.
They cannot be published as eligible original-final/preimport output early.
HOST_RESULT is also diagnostic data, never an accepted authority input.

After D/C have terminated, S completes all source/auth/worker/cleanup observations,
rechecks pins, clock/enforcement state, every host/native final guard and any
already-required root gate. It serializes a bounded prospective terminal record
using the exact canonical encoding. result_bytes is the exact byte count of the
WHOLE serialized record, including its own result_bytes field. Solve that size to
a bounded fixed point before output; reserve buffer/output and all pending write
bytes before allocation. Verify the actual complete write/EOF before committing
the record; failure or mismatch cannot produce completion. Meter actual write
bytes rather than assuming a successful reservation proves a write. The definition
oracle checks byte count, not a filesystem write or authenticated observation.

Elapsed values are actual monotonic observations at their declared observation
cutoff, never a predicted final duration. The observer checks the live overall,
phase and read deadlines again AFTER sizing/encoding/writing and immediately before
eligibility/publication. Serialized elapsed is the last measured sample included
in that record; it does not pretend to include its own future encoding/transport
or the observer's future exit. If a later final check expires, that complete
candidate is discarded and a non-success diagnostic is emitted. This avoids an
infinite self-observation/encoding requirement while keeping every operation,
including terminal work, under the actual clock. EXTERNAL final supervision keeps
the real end-to-end duration/exit, without reopening or replaying the invocation.

For FINAL the existing authenticated App publication remains owned solely by S
and remains subject to all existing admission/live-head/worker/DB/cleanup guards.
S does not use a saved HOST record as authority. Publication attempts, response
readback and terminal serialization remain in the SAME host ledger and overall
clock. Native pending output becomes locally eligible only after the required
publication acknowledgement AND final counters/clock/bindings/serialization checks;
use a single committed eligibility state, never a pre-worker positive file.
A remote side effect with missing/failed acknowledgement is NOT a local PASS or
merge authorization; retain observed uncertainty, invalidate local eligibility,
and use only the existing authorized failure-reporting path. Do not claim the
remote effect was erased or automatically retry into success. Root's existing
normal merge requires its complete live/receipt/gate observations conjunctively;
an App check or diagnostic record alone is insufficient.

PREIMPORT has no App publication. S returns eligible DATA_ONLY only after those
same terminal host/native guards and actual D/C zero exits; it never returns a
transferable authority receipt or import/CONTINUE grant. Root still rechecks
actual K/P/controller/authority immediately at ordered[K,P] import and explicitly
issues CONTINUE. S releases its lock after terminal handling; failure to complete
cleanup/observer accounting before eligibility denies. Lock/observer loss, pipe
failure, output exhaustion, cancellation, unknown/nonzero exit, unacknowledged
publication or deadline/enforcement failure cannot leave local eligible positives.
If S itself is lost, an external trusted root observer retains only an emergency
non-success record with actual known versus unknown exits; it acquires no new
publication authority, never infers S exit0, and never replays D/C. Post-commit
transport/observer uncertainty is retained truthfully and requires current root
gate reconciliation; a previously committed remote effect is not fabricated away.

S's self exit is NEVER claimed in a full record while S is live. The full record
has observer_state LIVE and observer_exit null, and separately observed D/C
states/exits. Success requires both D and C EXITED with observed0. The external
root observer may later bind the actual S/wrapper exit as separate evidence;
its loss/nonzero is not silently converted into success. Emergency records are
always ineligible. There is no endless chain of observers waiting for themselves
to exit before an authorized live owner can finish its own operation.

SOURCE_OBSERVATION_CONTRACT.md distinguishes S’s immutable acquisition-time
owned_store binding from actual reached source snapshots. S retains mismatches on
the failed source/import/recheck path; successful equality is unchanged. This
adds no observer, credential, authority receipt, clock or publication permission.
