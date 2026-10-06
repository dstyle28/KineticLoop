# HG056 bounded review-source integration proposal — NOT IMPLEMENTED

Frozen classifier/validator implementation: a8ed5ba4985f982a1e050eebd10b9a8e2ed9df86.
The running cycle must finish first; its actual unit/authority failures stay FAIL.
Complete immutable KL036 compatibility remains independently BLOCKED by the e81
same-codec consolidation edge. This proposal creates no consolidation authority.

Actual cause: review_reference_available and review_evidence_exists route source
inspection references through evidence_exists -> compact_evidence.read. The stronger
source-wrapper classification rejects metadata-bearing historical test/helper code.
Those references are source inspection, not command output or M3 execution proof.

Smallest candidate remedy: a separate bounded inspection-availability helper used
ONLY by generic/selected review-reference availability. It resolves the exact
recorded reviewed SHA (or exact own REVIEW_RECORD_ONLY record SHA after unchanged
absence/linear-suffix proof), proves a normalized regular Git blob, and statically
parses inspectable source. No execution/import, source/path/extension/owner/hash
allowlist, ambient HEAD/current-tree proof, decoder-error swallowing, blanket valid-
Python exemption, historical mutation, command/tested/exit fallback, or codec change.
A strict code-content predicate should distinguish modules with inspectable program
definitions from JSON/scalars or mere metadata assignments; parsing stays bounded.

All execution reads, command/result checks, M3 semantic sources, storage audits and
suffix representation checks continue through the strict shared decoder. Compact
review-output manifests still need their existing full payload/revision proof.
Metadata-bearing source can be inspected, but cannot manufacture execution PASS.

Required focused regressions before implementation authority: exact historical
review references; arbitrary suffix/owner inspection programs; missing/nonregular/
unavailable/wrong-revision/borrowed/suffix sources; missing or malformed compact
review output; source metadata rejected by command/result/M3/read/storage consumers;
valid JSON, dict/scalar/assignment wrappers never accepted as source inspection.
Fresh GENERAL and SECURITY_DATA_BOUNDARY review must assess this role separation.

Risk: this is purpose separation at review availability, not a storage classifier
exemption. Existing untyped evidence_refs do not explicitly declare an inspection
role. Contracts must clarify its strictly non-execution meaning before adopting it;
if the predicate or contract would broaden authority beyond the packet, obtain a
separate prospective scope decision. No implementation resource lease is held for
this proposal. Source remains frozen pending root adjudication.

Read-only binding diagnostics are in hg056-review-source-static-diagnostic.json and
hg056-hg047-review-suffix-diagnostic.json beside this proposal. HG045's three source
refs are already plain at exact reviewed478a46; the current-first availability path
misclassifies their later current source. HG047's three source refs are absent at
reviewedb71d2d and require original review-record89b3d3, whose strict suffix check
currently returns evidence-envelope-json. A proposed integration must handle this
exact original record/suffix proof rather than borrowing HEAD. Inspection verdicts
must never enter or satisfy the execution evidence cache.

## Reacquired repair scope, after round1 reviews

Root re-granted the four original HG056 implementation leases after the final guard
and review persistence. Independent classifier/fixture-ID repairs proceed. This
source-inspection proposal remains NOT_IMPLEMENTED and is not approved merely by
that resource grant. Exact historical HG047 helper blobs still fail the repaired
strict classifier; the current source-review guard and six original authority
errors remain actual failures. Bounded AST inspection (never execution) finds real
program definitions in all three helpers, without literal reserved-key or signature
dictionaries; source strings/other field structures still trigger strict rejection.

A reviewed-SHA-first lookup can recover the already-plain HG045 reviewed source,
but supplying absent-at-reviewed HG047 helper references additionally needs the
exact original review-record SHA and its complete linear own suffix proof. That
proof currently calls storage_bookkeeping_only, which classifies the helper bytes
through the strict storage decoder. A separate inspection predicate used solely
by availability cannot close this guard while leaving all strict suffix storage
checks unchanged. No current/HEAD borrowing, broad catch, path/hash exemption or
blanket Python trust has been added.

The minimum authority clarification is a non-execution source-inspection role at
review-reference and original review-suffix validation, with exact regular Git
bindings, absence-only fallback, immutable per-edge conversion/representation
checks, separate cache purpose, and explicit rejection of JSON/scalars/metadata
assignment wrappers. Existing evidence_refs are untyped and the packet explicitly
requires reserved source wrappers to fail closed. The interaction between this
inspection role and that storage obligation needs root adjudication before this
piece is implemented; no new schema or authority is inferred. It creates no KL036
consolidation permission or execution/read/storage/M3 PASS.
