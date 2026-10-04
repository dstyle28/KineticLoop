# Isolated TEST worker and independent reaper — KL036

The bounded worker uses the merged AcquireLease/RenewLease owners and guarded
AdvanceAttempt for CREATED → LEASED. Its finite heartbeat schedule waits on an
idle connection after commit. A historical lease response never starts or sustains
work. Failure stops that process; it cannot reset budgets, create attempts, reopen
roots, prepare model outputs, dispatch a request or issue authorization.

The independent reaper has a separate process and control channel. Discovery is a
bounded, lock-free read transaction that commits before S01. Scan facts confer no
write capability. The typed ReapIntent adapter requires a separately authenticated
registered TEST subject/policy/environment/principal, with a distinct internal
service session and current_user = session_user. Registration is checked before
replay and again under S01 against the active policy. Neither client identity nor
request data supplies SQL, callbacks, time, status, new fences or budget authority.

Its private transaction entrypoint establishes a non-caller-selectable preparation
token. First use orders S01 → S27 → sorted applicable S31 → S02 → current S29.
The current request ID/revision, attempt ID/state, owner/fence, deadline, expiry and
intent state must equal the scan facts. Fresh clock_timestamp() after locks decides
termination. Deadline expiry derives S27 DEADLINE_EXCEEDED / S29 LEASE_LOST.
Lease-only expiry derives CANCELLED / CANCELLED solely when the active registered
TEST policy explicitly declares worker_recovery = {version: kl036-v1,
lease_expiry: CANCEL}. Without that policy, lease-only reaping denies. Equality
terminates expired authority; exact equality is a pure-unit oracle.

The unowned case is exclusively current ADMITTED (legacy PENDING alias), NULL
owner, fence zero, NULL expiry and CREATED attempt, after its original deadline.
IS NOT DISTINCT FROM permits this exact nullable expectation only through the
authenticated private adapter. It cannot reap a leased, revised or live root.
Strict write guards accept only the complete server-prepared S27/S29 values and
exact identities, once each. Both closures and S02/S03/S04 commit or roll back
together. The event and outcome record the post-lock acceptance timestamp.

The historical generic synthetic ReapIntent branch remains unchanged. It is
compatibility instrumentation and supplies no new TEST runtime authority or
frozen/production evidence. The new wrapper never uses generic FAILED or lets a
caller choose a terminal. Same key/hash first use and replay return identical
historical identities with executable=false; changed payload conflicts. Missing
receipts and obsolete fresh candidates deny. Authentication remains mandatory
after success. A committed T6 success is immutable and never reaped.

Unknown-call discovery commits before separate MarkUnknown owner transactions.
It includes expired/terminated roots and reservations fenced out by takeover.
Possible sends retain occupation; interruption leaves safe outstanding accounting
for another scan. Only the ledger owner's explicit stale revision or transition
guard errors trigger a reread. The reaper rereads the candidate
through the ledger owner and continues only for a confirmed changed status/revision
with the same intent binding; unchanged-basis and read failures still propagate.
The completed count includes successful MarkUnknown calls only. Actual settlement
winning after discovery is witnessed in separate processes; stale rollback changes
no relations and the same reaper continues cleanup of another reservation.
RESERVED cancellation and late reliable settlement use their
existing dedicated ledger owners. Neither cleanup nor late settlement grants send,
planning or T6 authority. No provider or network waits occur in coordination.

The own tests gate every constructor, nested lifecycle route, seed reset and
cleanup on the full tested HEAD and resolved worktree. The exact names are
kineticloop_kl036_SHA7_ROOT12 and kineticloop-kl036-SHA7-ROOT12. Nested runners
accept only exact inherited lifecycle command shapes, pinned Compose file and
owned readiness/SQL targets; appended project/file overrides fail before I/O. Before/after
inventories prove foreign databases, projects, containers, volumes and networks
unchanged. Only owned bounded children are terminated or joined. Tests use actual
migrated PostgreSQL, distinct OS processes, bounded process barriers, PostgreSQL
blocker/lock witnesses and complete relation snapshots, including revision history
and T6 closure. Setup supplies declared upstream TEST inputs and a privileged
internal TEST service; it never seeds success or grants a subject login write SQL.
T6 preparation inputs are explicitly instrumented, not complete planning workflow
or product evidence. Production activation stays disabled and shadow stays
non-executable. M3, Hevy/HealthKit obligations and the retired spreadsheet policy
are unchanged. No product, W/I, M4 or release PASS follows from this task.
