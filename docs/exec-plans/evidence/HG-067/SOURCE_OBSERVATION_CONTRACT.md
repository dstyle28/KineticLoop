# R4 acquired binding and failed observed source identities

This narrowly corrects GENERAL-HOST-R3-01 / SEC-HOST-R3-01. No clock, capacity,
resource membership, authentication, literal verification or native rule changes.
All R3 process/lifecycle/phase/counter/exit/publication guards stay conjunctive.
All records remain diagnostic with zero authority; conformance authenticates no
source observation. Both new full reviews are required before governance allocation.

## Meanings of the existing fields

`owned_store` is the originally observed acquisition-time binding of the private
owned native store: root device/inode and object-directory device/inode. It is
captured once when those facts are available in OWNED_IMPORT, remains null before
that phase, and is required when import completed. It is not a current observation,
receipt authority, claimed proof of successful import or mutable expected value.
It is never overwritten to match a later changed store.

`initial` is the actual reached SOURCE_BEFORE snapshot. `terminal` is the actual
most recent reached SOURCE_AFTER snapshot, including a reached post-worker
SOURCE_AFTER recheck. Both report observed scalars, not copies of `owned_store`.
That applies to store_device, store_inode, objects_device AND objects_inode.
When the source changes but a complete bounded snapshot can be observed, retain
all actual observed values and its actual metadata identity; do not replace them
with the acquired values merely to conform. Known facts in an interrupted record
remain known; LOWER_BOUND describes incomplete overall accounting, not permission
to invent/erase a known identity or infer an execution exit.

The initial/terminal nullable/reached-phase rules remain unchanged. A completed
first-pass SOURCE_BEFORE/AFTER requires its snapshot. A later repeated check's
failure is recorded at FINAL_BOUNDARY and post_worker_rechecks, preserving the
already-reached first-pass history. If that later check cannot observe a complete
snapshot, keep the last actual complete snapshot without describing it as a new
successful observation, and retain the partial attempt losslessly as described
below. No unread field is filled from an expected pin.

## FINAL success and failure matrix

For BOTH BARE_CLONE and MATERIALIZED_CHECKOUT:

| Observed mismatch | Only permitted full-record path | Required cause |
|---|---|---|
| Initial differs from acquisition binding | Host DENIED/INTERRUPTED; SOURCE_BEFORE has that same failed status; later ordered phases unreachable | SOURCE_CHANGED, or IMPORT_DENIED for an acquisition discrepancy detected at the first source check |
| Preworker terminal differs from acquisition binding | Host DENIED/INTERRUPTED; first-pass SOURCE_AFTER has that same failed status; worker/rechecks unreachable | SOURCE_CHANGED |
| Post-worker terminal differs from acquisition binding | Host DENIED/INTERRUPTED at FINAL_BOUNDARY; worker COMPLETE; post_worker_rechecks SOURCE_AFTER has that same failed status; later AUTHENTICATE_AFTER recheck NOT_STARTED | SOURCE_CHANGED |

The existing ordered prefix, worker, native and reached-snapshot grammar supplies
the other entries in these paths. In particular an initial mismatch cannot be
marked COMPLETE and then run native/worker before failing at a later phase. A
known changed terminal identity cannot be marked as a successful SOURCE_AFTER
recheck and attributed only to an auth, cleanup or unrelated later error. A
SOURCE_CHANGED reason by itself does not waive these path predicates. Other
failure reasons may coexist as truthful observations. INTERRUPTED still requires
INTERRUPTION and LOWER_BOUND with actual known/nonzero/unknown exits retained.

Matching observed identities remain valid on appropriate success AND failure
paths: source bytes, mode, refs, metadata, authority or other checks may fail even
when device/inode match. SOURCE_CHANGED does not imply an inode must change.
`initial` and `terminal` still denote the selected layout: BARE_OWNED for genuine
bare acquisition, CHECKOUT for fully materialized acquisition. PREIMPORT remains
CHECKOUT on every reached status. No no-checkout-to-bare reinterpretation follows.

PREPARATION_COMPLETE remains strict: BOTH FINAL snapshots equal the originally
bound owned store on all four identity fields; initial equals terminal in every
field; release equals actual revision; exact layout/import/native/worker/recheck/
clock/counter/exit/authentication and all final guards hold. Equal but jointly
forged changed snapshots cannot become success by agreeing with each other while
disagreeing with `owned_store`. A forged/mutated owned binding also supplies no
operational authority; actual provenance is independently required in runtime.

## Lossless early/partial observation routing

An internal acquisition failure before SOURCE_BEFORE does not fabricate a reached
initial snapshot. An incomplete later snapshot does not fill unread fields from
its acquired or previous snapshot. Retain the bounded structured raw observation
with the actual stage, observed scalars, originally bound scalars if available,
missing-field list, sampled time and known/unknown exits. Its secret-free canonical
bytes must fit the existing2MiB diagnostic allowance and all original output/
allocation/time accounting. If the full schema cannot carry those facts losslessly,
emit the existing closed <=4KiB emergency non-success with partial_log_sha256
binding those exact retained bytes. For an early known import failure that is
DENIED/IMPORT_DENIED; for an interrupted attempt it is INTERRUPTED/INTERRUPTION
with actual unknown exits as applicable. Emergency counters remain LOWER_BOUND
because it does not contain a complete ledger, even if individual identity facts
are completely observed. It grants no import, continuation, custody or publication.

This explicitly routed fallback is for unavailable full fields/early acquisition
facts, not a substitute for ordinary complete mismatching snapshots in the matrix.
It is terminal diagnostic routing only: no retry, alternate source, reused proof,
new dispatch or fallback that could become eligible is permitted.
Loss of the bounded partial log or failure to retain its exact hash is itself
incomplete diagnostic custody, never a success or permission to sanitize the
failed observation. Real retention/I/O/observer enforcement stays FUTURE NOT_RUN.

## Mechanical conformance versus authenticity

Both closed schemas now describe bound versus observed field semantics; schema
PLUS the bounded definition_oracle are mandatory. Cross-field equality and the
failure matrix are checked in the oracle because standard JSON Schema cannot
compare arbitrary instance fields. R4 fixtures cover both layouts, all four
scalars, initial/preworker/post-worker attempts and both failed statuses. Positive
matching controls, lossless partial controls, reason/path negatives and forged
successes preserve all other guards. They are hypothetical inputs, not privileged
source observations, actual imports, native execution or repaired historical PASS.
