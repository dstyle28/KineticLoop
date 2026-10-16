# Bounded host preparation and complete checkout verification — draft R4

Status: PREPARATION_ONLY; no task identity allocated. This is a prospective
governance definition for independent review, not installed code or permission to
resume HG058. K is 9eb6ccc3f34a2914464213d466fae7a3015af977; protected P is
276bcaebbf3b64b4ea128b175a0463b2f650ac7c. A later governance delivery must resolve
its own current index and latest protected base. O, Q, every prior source pin and
all original HG058 gates remain conjunctive.

## 1. Resolution and narrow supersession

There are two resource domains in one authenticated host invocation. HOST covers
only the prerequisite and binding work enumerated below. NATIVE covers all
original inventory, selected/live validation, source retrieval, metadata used to
interpret evidence, classifier, codec, map, history, storage and custody work.
The complete fresh HOST and complete fresh NATIVE outcomes must both succeed.
Neither is an alternative to the other. HOST is not an extension or reserve for
NATIVE. The host ledger cannot dispatch or answer a native reader.

This narrowly resolves the former ambiguity in HG066's whole-invocation wording:
whole NATIVE invocation still shares all 22 unchanged capacities/units across all
owners, groups, readers and repeats. Whole HOST invocation shares the new finite
capacities across every host phase, file, copy, retry, snapshot and process.
There is no per-file, batch, owner, phase, retry or worker-return reset. The
existing temporary standalone ledgers are not a permitted lifecycle. No existing
native duty may be moved before NATIVE start to evade its capacities or clock.

Only these host prerequisites are separated from the native ledger: initial and
terminal identity/ref/HEAD/tree/cleanliness checks; inert Git metadata snapshots;
owned object acquisition, verification and copies; independently installed asset
binding; authentication and source-store/installation/config/lock ownership and
snapshot checks. A metadata or blob read performed by a native consumer, including
the same bytes previously read by HOST, must run and be charged again in NATIVE.
No host receipt, cache, parsed body, verdict or preloaded metadata satisfies it.
Auth cannot be inferred from a ledger or a successful source copy.

NATIVE_LIMITS.json preserves HG066 BUDGETS.json's exact 22 capacities, units,
10,000 ms per read, 120,000 ms per context, reserve-before-allocation, rejected
reservation implication, all-status final checks and all-or-none semantics.
Execution/projected lists remain 512; exact native source-schema rules remain.
The existing strict P-to-H and O-to-H obligations are not collapsed into one pass.
Each existing native validation context keeps its own already-authorized scope;
this rule creates no new context or restart permission. Repetition within one
context shares that context. A failed context cannot restart into readiness.

## 2. Host lifecycle, callers, process and event ownership

ROLE_EVENT_CONTRACT.md and CLOCK_RESOURCE_POLICY.md are the normative complete R4 contract for this section.
It fixes one live installed observer S as sole HOST ledger/lock/auth/publication
owner; D and C are bounded installed data-only driver/executor roles. It defines
both route-specific acquisition/phase orders, pending versus eligible data,
actual distinct exits, observer failure, output/final-check/publication order and
all repeated phase clocks without resetting. No candidate receipt is authority.
PREIMPORT reached snapshots MUST be CHECKOUT on every status. FINAL BARE_CLONE
is genuinely bare; MATERIALIZED_CHECKOUT has every physical obligation;
clone --no-checkout is unsupported for completion and never BARE_OWNED.

The existing API60s/signing15s/one fresh-auth GET retry/expiry margin/rollback/
exact permissions remain conjunctive with the unchanged proposed HOST caps.
No native capacity/unit/read10s/context120s or existing worker timeout changes.
FINAL proposes36h overall with one30h worker interval and a1h terminal reservation.
Every phase stays under the SAME absolute route deadline; first-to-last intervals
include all worker/reentry waits without the superseded600s contraction or reset.
Unknown enforcement, observer/lock loss, failed cleanup or changed pins deny.

## 3. Literal checks and data isolation

Enumerate every HEAD tree row without owner/path/suffix/content filtering. Record
every physical tracked path separately even if blob OIDs, bytes or filesystem
inodes repeat. Inspect directories without following symlinks; bind each path
component to the anchored source root. Reject traversal, malformed/duplicate rows,
missing paths, unsupported Gitlinks/types and symlinked metadata/object-store
escape. Preserve the existing regular 100644/100755 and literal 120000 handling.
Compare every regular file's full physical bytes with the exact immutable blob,
and every symlink's literal target bytes with its blob. Compare regular executable
mode exactly. Require exact length and EOF on both streams. Check lstat/open with
O_NOFOLLOW|O_NONBLOCK/fstat and inode/device/type/size/mtime stability before and
after reads; any mutation or inconsistent stream denies. Parent-directory and
source root identity checks must prevent replacement/escape, including between
snapshots. No hash-only, size-only, mtime-only or previous-result substitution.

Independently inspect the complete index/staged state and ordinary porcelain
untracked state. assume-unchanged, skip-worktree, sparse index/checkout, disabled
filemode and EOL/filter configuration cannot omit a tracked physical byte or
mode check. Preserve the existing untracked/ignore policy exactly; this rule
authorizes no added ignored path, exclude pattern or hidden file. Uncommitted
.gitignore changes are literal changes. Candidate info/exclude/config cannot
introduce a new suppression; only an independently bound existing host policy
can establish that policy. Unsupported index extensions/sparse states deny if
full equivalence cannot be proved. A clean status string alone never suffices.

Use fixed trusted Git binary/argv/environment and inert owned metadata snapshots,
never candidate Git config, executable hooks, attributes filters, helpers,
credential helpers, replacements, grafts or network remotes. No candidate module
is imported in privileged process. Literal source comparisons do not invoke
checkout/smudge/textconv. All metadata/ref copying is finite, stable and no-follow.
Object import uses an inert source view, dissociates temporary alternates before
use, verifies complete imported refs/objects and relevant source identities, and
does not rely on candidate configuration. Fresh private owned paths with fixed
permissions prevent hostile shared-store writes. Changed source metadata after
import still denies even if the imported old snapshot is self-consistent.

Streaming/batched cat-file is permitted only as a transport optimization: strict
framing, expected OID/type/length/order, full per-path literal comparison, all
stdout/stderr/stdin accounting, no unread trailing output, no process reuse across
invocations. A shared expected blob may be streamed again for each physical path;
if retained, its actual cache allocation must fit the host cache and every
per-path comparison is charged. No physical path/content deduplication credit.

## 4. Capacities and accounting

HOST_LIMITS.json is the exact proposed numerical definition, with a closed list
of units and counter kinds. Values are inclusive. They are policy ceilings for
review, not approved numbers or a promise the project/import/history will fit.
All work attempted in this invocation, including unsuccessful processes and
repeated snapshots/copies, is charged in its actual domain. Reservations must be
made before allocation/queue insertion/read/process start; rejected reservations
set a sticky failure without inventing consumption. Process output is drained
incrementally with bounded buffers; excess denies and the process group is killed
and reaped, with observed outputs/exits retained. No unbounded communicate/read.

Distinct-path identity is (anchored store instance, normalized absolute physical
path), not OID, owner or hardlink inode. Discovery reserves the distinct-path set
before insertion; every actual returned row/directory/ref/index entry additionally
increments entry_visits, including repeated observations. Missing-path attempts
record their attempted path before lstat. Separate copies are distinct paths.
Worklist_entries and all LIVE counters are high-water maxima, not totals; every
queued item is reserved before insertion. CUMULATIVE counters never decrement.

file_read_bytes counts all actual filesystem input bytes for HOST, including
metadata, source files, installed assets, object/pack/index and copied inputs;
file_write_bytes counts all actual owned output/copy bytes. metadata_read_bytes
is an additional subset cap. object_copy_bytes additionally counts every byte
successfully copied into owned object storage, with each copy/retry counted. If
Git performs opaque copying, a trusted bounded acquisition primitive must meter
input/output before consumption or apply conservative reservations covering its
entire finite source plus actual bounded destination accounting. A final stat
alone is not acceptable accounting. A compressed transport size does not stand
for expanded bytes. Source/destination preflight does not replace actual counts.

git_output_bytes counts all stdout AND stderr actually read, including framing,
diagnostics and failed commands; git_input_bytes counts actual stdin sent.
git_operations counts every started Git process including failed commands, with
process_operations additionally counting signing/other host child starts. No
logical-blob-read charge is fabricated for a shared batch process. Network bytes
are separately counted, including every retry, before decoding, with bounded
streaming API bodies; no secret body is persisted. Credential strings remain
in memory only and contribute to owned allocation high-water. Their lengths are
bounded; no raw key/token/config secret is emitted in diagnostics.

comparison_bytes counts lengths on BOTH sides of every actual literal comparison
including metadata, refs and installed bindings, and all repeated comparisons.
Reserve based on bounded forthcoming chunks, charge actual observed operands;
do not charge unexecuted comparisons. Hashing reads remain file/Git bytes even if
they are not comparison bytes. Whole-file size pre-reservation may fail early;
it must not fabricate actual comparison bytes. Index/tree/JSON decoding remains
bounded by metadata/output, entry, character and allocation caps before decoding.

cache_insertions/cache_insert_bytes are cumulative successful insertions and
actual bytes including reinsertion after eviction; live objects/bytes are capped
separately. Eviction can reduce LIVE usage but cannot refund cumulative work.
No cached verdict/authentication; immutable host data keys bind invocation,
purpose, store identity, exact object/ref/snapshot and source/controller pins.
Every terminal path destroys host caches. Native never consumes host cache data.

allocation_live_bytes includes all owned host byte buffers, strings, containers,
queued paths, caches, decoded metadata and record serialization, excluding only
the already measured trusted interpreter baseline. Reserve conservative upper
bounds before allocation: raw requested buffer capacity; decoded strings at
4*bounded codepoints+256; path/metadata records at least 512 plus referenced
storage; pointers/containers at a verified interpreter-specific worst-case bound.
Implementations must validate those conservative bounds for their runtime and
deny unsupported runtimes. Check actual retained sizes after construction too;
an underestimated reservation is terminal. The separate process-group RSS cap applies to HOST S/D/C brokers and HOST helpers
exactly as CLOCK_RESOURCE_POLICY.md defines. Enrolled native/unchanged worker
payload domains keep existing independent guards; all waits remain in the one
finite invocation. No allocation may be relabeled to escape HOST.
No portable enforcement is assumed: inability to enforce it blocks implementation.

Final checks observe actual elapsed, every counter/high-water, rejected reservation,
all subprocess termination/EOF, bindings and retained allocations on EVERY status.
No clamping. Exhaustion, deadline, read failure, snapshot mismatch, missing native
work, unknown child exit or interruption yields DENIED/INTERRUPTED, incomplete,
zero publishable custody/continuation and no positive residue. Failed native
result remains failed even when HOST has spare capacity. A failed HOST result
invalidates earlier successful native output for this invocation. Diagnostic
partial counters are explicitly lower bounds when interruption prevents exact
observation; they cannot be labeled complete or become a success later.

## 5. Closed output conformance and observation boundary

RECORD_GRAMMAR.md, ROLE_EVENT_CONTRACT.md and CLOCK_RESOURCE_POLICY.md jointly define the complete R4
success/denial/interruption/emergency grammar and process/publication order.
HOST_RESULT.schema.json PLUS definition_oracle.py are conjunctive: schema-only
validation is insufficient. HOST_EMERGENCY.schema.json PLUS validate_emergency
are likewise conjunctive. The oracle is bounded definition conformance on
hypothetical inputs, not authentication, actual accounting, a native audit or
privileged runtime execution. Every actual observation-dependent check remains
mandatory and NOT_RUN until installed integration validation.

A complete fixed-order first-pass phase vector is required on EVERY status. Denials and
interruptions have an ordered completed prefix, exactly one terminal failed
phase and an unreachable suffix.
The separate post_worker_rechecks vector preserves later repeated-check failures
at FINAL_BOUNDARY without rewriting earlier reached first-pass phases as absent.
Route-native contexts and complete/status/hash, reservation/detail/reason,
exact scalar, source-layout/snapshot and known versus
unknown exit implications are mechanically checked. Actual over-cap values and
LOWER_BOUND observations are retained; nothing is clamped or inferred to zero.

The oracle checks actual whole canonical serialized record-byte length including
its own result_bytes field and all declared phase/overall duration observations.
S also enforces actual allocation/I/O/clock bounds during and after serialization,
publication acknowledgements and final checks. Serialized elapsed is an actual
sample at its declared cutoff, not a predicted future end-to-end duration.
Full records describe a LIVE observer with null self-exit and separately observed
D/C exits. A lost observer can yield only an external emergency non-success
record, never an invented self-exit or reusable authority receipt.

All records have zero publishable_positives and false continuation/acceptance/
reuse. S's independent already-authorized live operation is the only possible
eligibility/publication owner; a diagnostic record cannot supply that authority.
Native outputs remain PENDING_DATA until the actual terminal guards complete.
PREIMPORT still grants no import or CONTINUE; final App/DB/root gates remain.

## 6. Capacity rationale and preparation limits

The independently observed 7,769 paths / 503,495,343 bytes require at least
1,006,990,686 compared bytes and that many per-path input bytes for one literal
pass across both sources. Two complete snapshots need 2,013,981,372 comparison
bytes before assets/metadata, not zero for the second snapshot. Proposed 16,384
tracked entries per snapshot gives >2x observed path count; 65,536 physical paths
allows source/owned metadata and directories, but is not a projected import count.
8 GiB comparison and 4 GiB Git output accommodate two full observed snapshots
with finite headroom. 16 GiB file input / 8 GiB file output / 4 GiB object copies
are independent conservative policy ceilings for unknown import/history costs;
we do not infer their sufficiency from the checkout sizes. The 64 MiB blob cap
covers the observed 24,792,180-byte largest blob while avoiding whole-tree cache.
Bounded streaming is mandatory regardless of those aggregate byte capacities.

The isolated scale fixture retains exactly 7,769 tracked paths, the observed
per-path sizes/modes and total bytes, plus repeated equal content and large blobs.
Its deterministic synthetic content, object compression, history, filesystem,
authentication and timings differ from the project. It can show the proposed
literal/accounting model operates at those path/byte totals; it cannot prove
project native feasibility, object-history fit, privileged host security or
runtime speed. A real slow/overrun fixture shows fail-closed deadline behavior.
R3 proposes120s host streams, unchanged1,800s preimport, one129,600s FINAL
absolute deadline and108,000s whole-worker interval with3,600s terminal headroom.
CLOCK_RESOURCE_POLICY.md compares every changed value/unit/domain to R2, derives
finite route headroom from the unchanged1200/6600/120s source, and retains observed
1694.281s DB /406.811s harness /2210.9460785s controller as historical lower bounds
only. This proposal changes no existing worker execution limit or native bound.
All numerical choices require review.

## 7. Merge and resumption gates

This entire draft, limits, schemas, rationale, fixture sources, retained exact
inputs, observed commands/exits, complete positive test identities and manifest
must first receive fresh full GENERAL and SECURITY draft reviews dispatched by
root. Review FAIL/INCOMPLETE is preserved, never retried into a replacement PASS.
Root alone allocates one separate governance task/worktree/author after draft
readiness. Its current authority, packet, resource leases, result/checks, normal
independent task reviews, App/DB/live gates and normal protected merge still apply.
The future governance delivery must incorporate these reviewed definitions
prospectively and enumerate this exact narrow supersession; draft filenames alone
are not authority. No parallel duplicate governance allocation is permitted.

Only after that normal merge may root regrant SAME HG058 implementation. Require
new committed K, affected failures resolved first, eight complete fresh K checks,
new full GENERAL and SECURITY reviews of all 11 installed assets/controller/source
provenance, root installation and full authenticated O-to-actual-K BEFORE ordered
[K,P] import, exact pin rechecks and explicit CONTINUE. T's twenty author commands,
truthful R, fresh full R reviews, own strict RRO suffix H, nineteen root external
prerequisites, final reviewed installation, exact admission, full O-to-H AND
strict P-to-H, public denial, unchanged worker/ci-pr, App/unit/harness/fullDB,
cleanup, hosted checks and normal merge all remain. This draft runs none of those.

Preserve every historical candidate/report/failed/interrupted command and raw
exit, including c4b mapping gap; 6358 missing independent parent and unknown child
distinct from driver143; three 741>512 denials; HG004 archival-only lineage and
missing GENERAL; HG047 strict RRO failure; original 5da0 first bulk failure; R5
GENERAL positive failure UNKNOWN; R6 service review incomplete; 9b074 and R7
timeouts/unknown causes; R7 original failed fixture input retention gap and later
separate diagnostics; 592 cache assertion failure and retained bundle; R8 actual
root session5884 preimport read failure. Never rerun completed session5884/18967.
Historical execution stays UNVERIFIED, acceptance_eligible=false,
execution_reuse=false. No historical gap is closed by this new resource rule.
KL081 stays NOT_STARTED. DB/App executor remains unreserved. Frozen Protocol/DB,
Evidence Admission, T1–T8, lock order, authorization, production/shadow separation,
provider command trust and every product requirement meaning remain unchanged.

R4 SOURCE_OBSERVATION_CONTRACT.md is conjunctive and narrowly defines originally
bound versus actually observed FINAL source identities. Success remains strict;
known changed identities remain lossless only on consistent failed source paths.
No R3 proposed clock/capacity/membership, native or literal guard changes.
