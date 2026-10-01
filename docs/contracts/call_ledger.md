# Call ledger — KL025

`CallLedgerService` submits typed ReserveCall, PermitDispatch, CancelUndispatched,
MarkUnknown and SettleCall commands to the merged repository transaction owners.
It uses the actual planning root's top-level `limits`, `reserved` and `settled`
maps; it preserves every unrelated root payload field. No new coordinator, table,
planning lease API or provider transport is introduced.

`kl025-v1` accounting binds provider, model, configuration fingerprint and price
accounting version. Every configured dimension has a finite nonnegative integer
unit. Supported dimensions are calls, tokens, tools, input_tokens, output_tokens
and cost_micros. Unknown dimensions, bools, floats, missing/extra counters and
unbounded values fail closed. Each physical request reserves exactly one call;
reliable settlement retains that physical request count. Admission compares
settled actual + all outstanding reserved maxima + the new maximum with every
root limit. Equality is allowed. Pending and OUTCOME_UNKNOWN occupation remains
reserved usage; it is never reported as confirmed provider charges.

This version explicitly sets `AccountingIdentity.strict_money=false`; it rejects
a strict money claim because it does not establish complete provider billing
coverage. Integer cost_micros, when configured, participates in root arithmetic,
but does not supply that missing provider guarantee. Count/token limits remain
enforceable. A complete verified pricing/billing configuration is future work.

Only a locked RESERVED reservation may cancel and release its exact maximum.
Cancellation may release an obsolete reservation because its locked source proves
that no permit exists. It supplies no stale planning authority. Only the first
committed RESERVED → DISPATCH_INTENT winner receives `sendable=true`. That permit
is a single physical-send permission, with no business-write or T6 authority.
Same-key replay retains the original identity and is `sendable=false`; changed
payload conflicts. Another key cannot permit the same reservation again.

DISPATCH_INTENT is the possible-send boundary. DISPATCHED is optional diagnosis
and is not implemented here. Crashes before sending, after sending, lost permit
ACKs, timeout and post-permit cancellation cannot release occupation or reset the
reservation. Recovery never sends the same reservation again. A consumer invokes
its sender only after the permission transaction has committed and released its
locks, only for its first sendable result. SDK implicit retry must be disabled;
each explicit future physical retry requires a fresh covered reservation. Unit
evidence uses an instrumented owner and fake sender, with no live network call.

The existing owner's expected-transition vocabulary is `DISPATCH_INTENT` or
`UNKNOWN`; the latter names the persisted OUTCOME_UNKNOWN source. MarkUnknown
accepts DISPATCH_INTENT only and preserves the root counters. SettleCall accepts
DISPATCH_INTENT or UNKNOWN, an exact expected settlement revision and a reliable
receipt/reconciliation. A blocked contender rereads the locked transition and
rejects a stale expectation.

`ReliableReceipt` binds the reservation, accounting identity, exact actual
dimension map, provider request ID, immutable receipt ID, source and provenance
reference. Its shape does not establish trust. The dedicated settlement ingress
requires its injected trusted receipt verifier before coordination begins.
Untrusted, duplicate and conflicting evidence cannot refund occupation twice.
Settlement atomically removes the exact outstanding maximum and adds verified
actual usage. Actual above any configured reservation maximum remains recorded
without clamping and atomically sets the root's accounting-only
`call_bound_violation=true` marker. The marker irreversibly denies new reservations
even while every aggregate root limit retains capacity. Subsequent cancellation,
in-bound settlement, join, revision and takeover preserve the marker. An in-bound
or exactly-at-bound receipt does not introduce it. Each receipt still accounts
for exactly one physical call; additional physical invocations require separate
reservations. Late settlement updates only
accounting and immutable evidence, preserving terminal/revised intent, attempt,
lease, control and authorization state.

Applicable ordering remains S01 → S27 → S31 → S02 with remaining applicable
locks acquired in frozen order. S27 accounting, S31 state, S32 transition and
S02/S03/S04 bookkeeping commit atomically. Ledger commands never acquire a
registry lock backwards and never wait on a model or network inside coordination.
The task's PU/DC evidence does not discharge full W01/W03/W05/W06/W08 workflow,
end-to-end or release obligations and changes no product requirement status.

Reservation cancellation is a bounded internal owner registration; the frozen
39-command public ingress set remains closed and rejects CancelUndispatched.
The typed `read` model returns immutable bounds/actual maps as historical
accounting observations. It cannot grant send, execution or business-write authority.
