# R4 closed records and bounded definition oracle

The closed schema AND definition_oracle.py are mandatory conjunctive conformance
checks, including every non-success status. Shape-only acceptance is insufficient.
The oracle accepts only bounded JSON data: at most1MiB input/full serialized output,
depth32, conservative lexical/node bound65536, strings16384, fixed phase/context
counts, no duplicate keys/non-finite numbers, at most16 size fixed-point iterations.
Its output explicitly says observations_authenticated=false and runtime/native
PASS=false. It accepts no credential, source store, controller callback or host
authority object and cannot dispatch native work. A valid hypothetical record
cannot establish any pin/hash/counter/clock/authentication fact.

Full records always contain exactly nine phases in the selected route's order.
PREPARATION_COMPLETE has all COMPLETE, exact counters, zero reasons, no rejected
reservation, matching initial/terminal pins, complete acquired-store binding and
all required native contexts COMPLETE. DENIED has a COMPLETE prefix, exactly one
DENIED phase and NOT_STARTED suffix; INTERRUPTED similarly has one INTERRUPTED
phase. A not-started phase has duration0. A reached phase's duration cannot exceed
the observed overall sample; overlapping/reentered phase durations are not summed.
Every phase interval remains subordinate to the SAME absolute invocation deadline:
1,800s PREIMPORT or129,600s FINAL; overall/worker overrun requires non-success
and HOST_DEADLINE_EXCEEDED. There is no separate600s phase ceiling. That reason requires an actual declared overrun; a
per-read timeout instead uses HOST_READ_TIMEOUT and retains its actual observation
in future installed bounded diagnostics, not a fabricated phase overrun.

PREIMPORT has exactly ORIGINAL_PREIMPORT; FINAL has exactly ORIGINAL_FINAL then
STRICT_LIVE_FINAL on every status. A NOT_REACHED native context has complete=false
and null hash. COMPLETE has complete=true and an exact64hex hash. DENIED or
INTERRUPTED has complete=false and may retain an actual diagnostic hash or null.
Contexts form COMPLETE prefix, at most one failed context, then NOT_REACHED suffix.
No context can run after a failed/not-reached predecessor. NATIVE phase NOT_STARTED
requires all contexts NOT_REACHED and D/C NOT_STARTED; NATIVE COMPLETE requires
all contexts COMPLETE. Failed native projections require corresponding host
failure/interruption. Actual native records remain separate original evidence;
the projection never recasts their own status or supplies missing observations.

Snapshot fields are null until their phase is reached; completed SOURCE_BEFORE
requires initial, completed SOURCE_AFTER requires terminal, and terminal requires
initial. PREIMPORT snapshots always bind CHECKOUT, including on denials. Its
imported native-store root must be distinct from the original checkout root.
Successful FINAL source snapshots follow acquisition and bind the same acquired
source/native-store identity: BARE_CLONE to BARE_OWNED, MATERIALIZED_CHECKOUT to
CHECKOUT. NO_CHECKOUT_UNMATERIALIZED must stop in or before OWNED_IMPORT with
UNSUPPORTED_SOURCE and no reached source snapshot. It never becomes bare by fiat.
Completed imports require owned_store; unreachable import has null owned_store.
Success compares all scalar/store/metadata/authority snapshot pins exactly.
Git/controller/digest/invocation hex strings have exact lengths/ASCII hex patterns;
trailing newline, prefix/suffix, wrong type and boolean-as-integer are rejected.

reservation_failed=true iff rejected detail is present. It requires non-success,
HOST_LIMIT_EXHAUSTED and a strictly positive requested+pending reservation that
would exceed the inclusive field cap with actual consumed counters. Actual over-
cap counters also require non-success/HOST_LIMIT_EXHAUSTED. Conversely that reason
requires a rejection or actual over-cap observation. Denial schemas do not clamp
over-cap actuals. A refused reservation does not fabricate consumed bytes/paths.
LOWER_BOUND cannot complete; DENIED/LOWER_BOUND requires ACCOUNTING_INCOMPLETE,
and that reason requires LOWER_BOUND. INTERRUPTION and INTERRUPTED imply each
other for full records, with LOWER_BOUND. A native interruption requires the same.

D/C NOT_STARTED or UNKNOWN means null exit, EXITED means an actual integer exit.
UNKNOWN requires INTERRUPTED/LOWER_BOUND, INTERRUPTION and UNKNOWN_CHILD_EXIT;
the latter reason requires an unknown D/C observation. Nonzero observed exits
require corresponding HOST_DRIVER_FAILURE/HOST_CHILD_FAILURE, non-success, and
are never replaced with null or0. If C failed, D cannot be reported EXITED0.
Early auth/source denial has D/C NOT_STARTED, not an unknown execution. Success
requires two separately observed EXITED0 values. Full records have S LIVE/null
self-exit, not a predicted S zero. Actual external wrapper observation is separate.

Emergency records are closed, <=4KiB, always LOWER_BOUND/incomplete/ineligible.
INTERRUPTED reasons are exactly INTERRUPTION, UNKNOWN_CHILD_EXIT or OBSERVER_LOST;
DENIED uses a non-interruption reason. EXITED binds an observed integer; UNKNOWN,
NOT_STARTED, LIVE or LOST bind null as applicable. Unknown/lost observations require
interruption; reason UNKNOWN_CHILD_EXIT requires an actual unknown D/C field;
OBSERVER_LOST requires S LOST. Other precise observations remain in bounded
hash-bound partial diagnostics, never guessed. Full-output exhaustion can use the
already-reserved emergency envelope, not additional room for positive output.

Canonical encoding is sorted keys, compact separators, ensure_ascii=true,
allow_nan=false, ASCII/UTF8 bytes. result_bytes must equal the length of the WHOLE
canonical record including its own counter. seal_record solves only that size
fixed point; it neither meters a real write nor authenticates a synthetic record.
Actual installed S must reserve/check memory/output/write bytes, verify actual
complete write and recheck live deadlines/bindings after terminal work. Those
observation-dependent properties and native output authenticity remain NOT_RUN.
No JSON oracle, hypothetical native hash or event trace can prove them.

## R3 whole-route and relational obligations

CLOCK_RESOURCE_POLICY.md is conjunctive with this grammar. FINAL worker is one
fixed state/start/end/elapsed record; PREIMPORT worker is NOT_STARTED with null
start/end and elapsed0. A started interval has exact start/end samples within
the invocation sample and elapsed=end-start; UNKNOWN end retains a lower-bound
interrupted observation, never a fabricated end. COMPLETE worker requires FINAL
route and every original preworker phase reached/completed; both repeated
source/auth checks must complete before host success. Repeated failures are
reported in the fixed post_worker_rechecks vector and FINAL_BOUNDARY failure,
while the first-pass phase history remains truthful. All its elapsed observations
include first entry to that repeated observation, matching the named phase span.

EXACT counters enforce metadata<=all filesystem input, object copies<=all
filesystem output and Git+signing+known HOST broker starts<=HOST process starts.
LOWER_BOUND records preserve incomplete subcounts without manufacturing totals.
C reached requires D reached on full AND emergency projections. Successful
release pins equal actual revision; successful PREIMPORT acquired root AND object
store identity pairs must both be distinct. Denied/interrupted mismatches remain
valid diagnostic facts and cannot be promoted to completion.

## R4 observed versus originally bound source identities

SOURCE_OBSERVATION_CONTRACT.md is the precise failure matrix for FINAL snapshots.
owned_store retains the originally observed acquisition binding; initial/terminal
retain actual complete observations, not expected-value replacements. On success
all four root/object device/inode fields still match; on DENIED/INTERRUPTED a known
mismatch is permitted only with the corresponding source/import reason and
failed initial/preworker/postworker source path. Unreached/partial observations
use the explicit lossless bounded raw-log/emergency route without inventing
snapshot fields, observed exits or exact counters. All other guards remain.
