# Exact binding rules for documentary archival observation

This appendix supplements RULE_PROPOSAL.md and CLOSED_DOCUMENTARY_FORMS.json.
It is prospective, owner-neutral, and does not verify the original computation.

## Shared bindings and operation boundary

For every profile, use the uniquely bound original check ref as the report input.
Never select another report because it contains PASS. Resolve record/ref/review at
original M and current validation_revision and require the record and main report
byte-identical. Resolve R from original GENERAL; validate its original schema, namespaced owner,
review type and immutable byte/reference-chain bindings. Expose its status as an
ORIGINAL_REVIEW_LABEL_ONLY and historical_review_acceptance=NOT_CERTIFIED. Do not
request or certify review-only suffix validity from this observer. Any known actual
historical RRO failure remains a separate failure and is never repaired. All existing
independent global review/source-reference and selected review/full RRO guards run
unchanged in their own contexts; documentary eligibility does not satisfy them.
Require protected first-parent M and B<=T<=R<=M<=current protected base. All revisions
are full commits. R binds the result record at R/M, not a nonexistent record at T;
T identifies the original producer checkout. Commands bind to that original record
B/T pair even when the result/report was written after T. A regular tree entry means exactly mode100644/100755 and typeblob.
No working, symlink, submodule, directory, later-original or current-only substitution.

The selected owner is ineligible. The only caller is global archival governance
inventory; all other purposes reject without attempting documentary recognition.
The immutable profile version, original record/report/review blobs and B/T/R/M/base/
validation revision bind the observation. No reusable success Boolean is returned.

Strict schema types are necessary but insufficient. Only path strings used for immutable Git lookup must be canonical relative UTF-8
without NUL, CR/LF, backslash, absolute or dot components; owner evidence/review
references must be under O's respective subtree. Declared interpreter/argv strings,
mount Destination, container/image/volume identifiers and excluded development
original_path are inert host attribution: absolute paths are allowed, with no NUL
or CR/LF, but never read/resolved/opened/normalized into an eligible Git reference.
All revision/OID/hash strings use full lowercase40/64hex as appropriate. Array
identities/path entries are unique; counters/byte lengths/durations are nonnegative,
positive test counts are >0, workers >=1; booleans are actual JSON booleans.
JSON depth64/node262144 ceilings apply before schema validation. Unknown grammar
fields reject, including at all nested levels. Arrays with no original items have
string-item grammar; no arbitrary object can appear later. Source is never executed.

Nested component claims are not raw execution evidence. This observer validates
only their original references/identity/type and internal consistency. A component
can become independently verified execution only through its existing dedicated
check/reader, with actual command/T/exit/output and execution oracles. The archival
observer must label all otherwise unchecked component outcomes CLAIM_ONLY.

Explicit secondary refs below bind to M (or an explicitly supplied original source
revision), not HEAD. Bulk immutable tree-entry lookup proves existence/regular mode;
it supplies no raw output hash, decoded availability or execution proof. Existing independent global review-reference guards and strict main-report decoding
guards remain mandatory in their own callers. Metadata-only archival linkage does
not claim reference execution/decoding or RRO validity. Any reader
that actually reads a secondary execution capture must use its existing native
strict decoder and original revision; denial cannot become documentary validity.
This observation cannot populate decoder/source/RRO/storage/execution caches.

## Deterministic original authority and reference selection

At T and R, read original CURRENT_DOCUMENT_INDEX as strict bounded JSON. Select
exactly one entry each for HARNESS_CHANGE.schema.json,THREAD_REVIEW.schema.json,
docs/harness/HARNESS_GOVERNANCE_CONTRACT.md and docs/harness/THREAD_REVIEW_CONTRACT.md.
Verify their indexed hashes against regular blobs at the same original revision;
schema/contract bytes must agree T/R; mismatch rejects this closed profile. No inferred authority from filename recency/prose.
These establish record/review identity; they do not define the lost producer oracle.
The new closed grammars are explicitly prospective and require no invented old
machine declaration. Historical schema validation uses a nonretrieving registry.

Canonical owner governance and GENERAL paths resolve uniquely at original M. GENERAL
must bind R and the same namespaced O. Its evidence_refs must either directly name
this report, or name the canonical owner governance record containing exactly one
check with this report reference and exact declared command/T. This is at most one
record hop, never an arbitrary evidence graph, source search or caller-supplied link.
Record at R/M/current is byte-identical; main report at M/current is byte-identical.
The report may postdate T but must already exist at M. Preserve original review
status and known RRO failure explicitly; neither is elevated by this identity proof.

For comparison's original benchmark companion: candidates are references explicitly
present in the original GENERAL evidence_refs, also present in original record
files_changed, with the exact benchmark-index grammar. Require exactly one. The main benchmark
codec_source five-field tuple is immutable documentary attribution only. No codec
companion selector, recursive scan, source lookup or companion verification is
required or allowed by this profile; optional original-companion research does not
grant runtime eligibility. Original scope paths and
secondary artifact entries always use explicit original report fields, never prose.
Select type grammars after immutable original linkage; no class is selected from
status/PASS. Profiles do not use sample basenames, owner IDs or digests as eligibility.

## Controller lifecycle receipt

Bind snapshot.base,policy.base,worker.base to B; snapshot.head,policy.head,worker.head
to T; tree equals the immutable tree OID of T. snapshot repository/pr numbers and
controller/run identifiers retain their original reviewed attribution only, never
current account/controller/admission authorization. Receipt/worker status must be
PASS as original claim, test_only literal true, policy/worker full_database_required
agree and are true. Worker checks have unique check_id, nonempty argv, integer exit
0, interrupted false and stdout byte/hash/path fields; stdout paths are canonical
and resolve under the original report directory at M. worker.artifacts maps the
closed grammar's exact relative names to SHA256 strings and each key resolves under
that directory. Binding is to that original tuple, not the parent producing command.
Reported DB errors/failures/skips are zero; container_removed/volume_removed true.
All cleanup/DB counts remain archival claims until independently proven by the
original native receipt contract. No parent exit is synthesized from these fields.

## Committed integrity report

Bind tested_commit to T and audit.base to B. result_commit is an original intermediate
result U: require T<=U<=R, not U==R; bind audit.head to U. audit.identity equals D.
Status and governance_schema are PASS claims; suffix/audit.errors are empty arrays;
full_database_required true. Reported counts nonnegative. Preserve and expose U
separately from R; no cross-revision substitution. Native old audit computation is
not rerun or declared VERIFIED by this profile. A purported successful report with
nonempty errors contradicts its claim and is INVALID.

## Cross-mode comparison

Bind tested_commit to T. Resolve exactly one original benchmark-index form explicitly
listed in the original governance files_changed and referenced by the original
GENERAL review; ambiguity/missing linkage rejects. Both reports must be unchanged
at M/current. Match each comparison run identifier to one benchmark final_runs label;
no unmatched/duplicate/missing labels. workers/tests/exit/wall fields agree exactly;
comparison tests equals every final-run tests, and same_collection_all_runs is true
as claim. Each reported phase counter is nonnegative; failed/skipped zero. Hardware
fields are documentary attribution. Node-set equality is not certified by these
scalars; original dedicated captures/readers remain required for such a proof.

## Frozen scope report

Bind base_commit to B and tested_commit to T. files_changed is a duplicate-free canonical subset of the original governance
files_changed, including originally declared owner evidence documents. This compares
original declarations only, not a fresh scope audit or complete-diff projection.
Missing other original changed paths is not new scope certification; every listed
path must still be originally declared. The complete actual diff/scope guards stay
separate. No arbitrary current caller supplies the subset.
frozen_and_execution_policy_unchanged is true as claim; errors empty; requirements_status
starts literally NOT_RUN: and is nonempty after the colon. Controller-change entries are canonical path tokens. A token containing a slash must exactly equal one files_changed entry; a basename token must match exactly one basename in that list. Zero or multiple matches rejects. This documentary mapping cannot authorize a write or certify actual controller equality. compatibility_note is nonempty documentary text, never parsed as authority.
All original real tree/scope/frozen guards remain separate and mandatory.

## Benchmark packaging index

Bind tested_commit=T,base_commit=B. The closed five-field codec_source tuple is
original report attribution only: validate its exact closed grammar/full40hex
revision and OID/full64hex SHA/positive integer upstream PR/inert use string, then
retain all values as CLAIM_ONLY. It may name an unmerged parallel revision and need
not be ancestor T. Source tree-path identity, source availability and source
execution remain UNVERIFIED. No companion scan/read, arbitrary OID/source lookup or
source hash computation is performed. Original record/report/GENERAL provenance
binds this tuple to its original claim; it does not corroborate actual code identity.
Adding a verified source-origin profile requires separate governance.
Final run labels unique, T-bound, positive tests/workers and integer exit0; artifacts
exact closed map names, paths under original owner and regular entries at M. Commands
match the corresponding unique original governance harness check command in the R/M record bound to T.
Quality map's command matches its unique original declared check; exits0 and explicit
artifact refs bind at M. Duplicate/ambiguous command linkage rejects.
Development runs use their own exact producer revision and component command/exit,
not T. Preserve any interrupted130 and missing execution artifact; no final execution
can borrow that capture. Excluded artifact entries retain original path/hash/byte
length/reason as claims, never a success omission. They are not required to exist at
M when explicitly excluded; no recovered output is certified. Roundtrip entries are
unique original owner refs resolving regular at M, with nonnegative lengths and64hex
claimed raw hash. An envelope hash/length string is not newly verified raw equality.
Every unchecked roundtrip remains CLAIM_ONLY. Malformed codec tuple, unknown actual evidence pointer or nonregular entry
rejects rather than granting output availability. A syntactically valid unverified
codec attribution never grants source or output availability.

## Bounds and prospective amendment

Per report: at most32 unique blobs actually read,32MiB aggregate,4MiB validator/
1MiB other blob; at most512 secondary metadata entries resolved,1MiB combined tree
listing,64 bounded Git operations; parser limits as above. Deduplicate immutable
object reads. Resolving an entry is not reading/certifying its contents. Native
mandatory independent global-reference/selected-review/decoding proofs retain their
own budgets and may be reused
only from an exact immutable validation context; they are not replaced by this
observer. Exhaustion fails INVALID, not fallback or truncated inspection.

The rule expressly amends HG060's global historical executed-PASS treatment only
for this bound documentary category. It does not claim missing original source/
producer execution is valid; it records it as unverified without blocking archival
inventory solely for the absence. HG061's VERIFIED semantics and INVALID criteria
remain untouched for its distinct source-verifiable profile. Explicit exact-tuple
execution contradictions still INVALID; unknown-source/unknown-exit is not a claim
that a producer ran. Fresh/selected checks cannot use either archival category.

## Authenticated contradiction inputs

The observer inspects only its already bound original governance check fields, main
report, uniquely selected companion reports and bounded original GENERAL fields,
plus existing native command/capture observations supplied through an authenticated
validation context. A native observation is usable only when its existing reader
has verified immutable capture bytes/hash, original revision and exact namespaced
owner/check/B/T/declared-command/report tuple. Plain dictionaries, caller flags,
prose inference or externally supplied status strings are not authenticated inputs.
The global inventory must finish its normal native observation pass before consuming
the archival observation; it may not hide previously authenticated contradictory
facts to get coherence. Inability to finish that pass is incomplete inventory, not
documentary success. No new recursive evidence search is introduced here.

Exact command equality uses the original UTF-8 command bytes with only the existing
contract's permitted line-folding representation; argv linkage uses the existing
bounded nonexpanding tokenizer. Do not remove flags, reorder operands, replace
interpreters or normalize host paths. Any ambiguity rejects. Nested child observations
with their distinct command/revision are retained but do not contradict or certify
the parent. Known parent exit0 routes to the existing ordinary observed-exit path,
not UNVERIFIED_MISSING_PRODUCER_EXIT. A parent known nonzero/interrupted/unstarted/
incomplete/error/failure/skipped observation rejects; absence alone remains unknown.
The observer neither overwrites nor supplies native observation, review/RRO or
raw-execution results.
