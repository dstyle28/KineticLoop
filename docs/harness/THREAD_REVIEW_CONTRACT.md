# Thread Review Contract v0.2

Every task receives an independent GENERAL review. Additional specialist review is required when the task touches the corresponding risk surface:

- frozen Protocol / T1–T8 / authorization semantics → PROTOCOL;
- PostgreSQL locks, fencing, idempotency, migration chain or coordination rows → DB_CONCURRENCY;
- remote AI context, provider/health data export, credentials, retention/redaction → SECURITY_DATA_BOUNDARY.

Review artifacts are committed under `docs/exec-plans/reviews/<TASK_ID>/<REVIEW_TYPE>.json` and conform to `THREAD_REVIEW.schema.json`.

## Reviewed revision and the review-record append exception

`reviewed_head_sha` is the implementation/result revision actually reviewed. Normally any implementation, configuration, migration, test, contract, or product-document change after that SHA makes the affected review `STALE`.

A narrow exception exists so the review can itself be persisted without invalidating itself: after `reviewed_head_sha`, commits may append or update only the following task-scoped review bookkeeping paths:

- `docs/exec-plans/reviews/<TASK_ID>/**`

These commits are called **REVIEW_RECORD_ONLY** commits. They MUST NOT modify application code, tests, migrations, contracts, task packets, requirement status, frozen files, or the task result payload. A mechanical merge-gate check must prove that `reviewed_head_sha` is an ancestor of HEAD and every intervening commit changes only allowed review-record paths. The suffix must be linear; merge commits require a new review. Path matching uses whole directory components, so another task such as KL-001A is never covered by KL-001. If any other path changes, the review is stale and must be rerun.

The task result is committed before review and is part of the reviewed revision. Do not mutate the result after review merely to copy the reviewed SHA; the review artifact itself is the authority for `reviewed_head_sha`.

Reviewers may create logs, reports and other review bookkeeping during independent review. Those files are review evidence, not pre-review task test evidence. An integration record's exact `review_record_commit` binds those references without adding a schema field: ordinary review references must resolve at `reviewed_head_sha`; a reference absent there (no Git entry of any type at that path) may resolve at `review_record_commit` only inside `docs/exec-plans/reviews/<same TASK_ID>/`, after a mechanical proof that the entire ancestral suffix is linear and exclusively REVIEW_RECORD_ONLY. Whole directory components are mandatory. Every reference must be a normalized repository-relative path to an available regular Git blob at its bound revision; directories, symlinks, traversal and ambient working-tree/HEAD existence are not evidence. Git commit/tree/blob identity supplies content addressing.

This exception cannot supply implementation, result or task-check evidence created after review. Result and task evidence retain their existing reviewed-revision guarantees. It does not relax delayed post-merge review freshness or exact-tree squash ancestry: a delayed review with intervening unrelated commits can continue to cite ordinary reviewed-revision evidence, but cannot use this review-created evidence exception unless the entire suffix also passes the strict own-task linear proof.

`CHANGES_REQUIRED` findings are closed only by a new implementation revision and a new review artifact. Untracked comments do not close findings.

The validator applies revision freshness to the selected task PR. Historical reviews of previously integrated tasks retain their recorded revision and are not invalidated by later unrelated task commits.

Prospective compact evidence follows [Evidence Storage Policy](EVIDENCE_STORAGE_POLICY.md);
all existing revision bindings and PASS oracles remain mandatory.

HG051 authorizes only the exact four KL080 historical current-tree representations
pinned by [Evidence Storage Policy](EVIDENCE_STORAGE_POLICY.md) and
`HISTORICAL_EVIDENCE_MAPPING.schema.json`. Original bytes, Git commits, result/review
bindings and failures remain historical. Archival mapping/retrieval is never
execution evidence or task/requirement/review/M3 PASS. Migration precedes new testing;
no post-test overwrite or post-review suffix exception is added. Normal ancestry
must retain originals, and unavailable original revisions fail original verification.

## HG059 declared historical source lineage (prospective)

The indexed `REVIEW_SOURCE_DECLARATIONS.schema.json` and
`docs/harness/REVIEW_SOURCE_DECLARATIONS.json` supply explicit purpose assertions
for six exact historical record/reference tuples. THREAD_REVIEW.schema.json and
historical review bytes remain unchanged. A declaration is reviewed authority,
never a runtime source path/hash allowlist. Governance independently establishes
that each cited use is source inspection rather than command output; filename,
content, extension, decoder error and apparent language cannot establish purpose.
Further declarations require ordinary independent governance review; HG058 may
consume but cannot extend or modify this authority.

Load both definitions from the exact immutable validation revision, never ambient
files. Reject duplicate JSON keys, unknown fields, unknown format/purpose, malformed
identities or full SHA violations. The document and original review record are each
at most 256 KiB raw; at most 64 declarations; each path at most 1024 ASCII characters,
each owner at most 80 characters. Other strings are fixed enums or 40-character
lowercase Git OIDs. Paths use only ASCII letters/digits/underscore/dot/hyphen and
single forward-slash components; reject absolute, empty, dot, dot-dot, backslash,
control, traversal and non-normalized paths. Reject duplicate or conflicting
`(owner, review_type, review_record_path, reference)` keys, including entries whose
commit/blob/reviewed SHA disagree. No invalid declaration may fall through to an
undeclared/evidence route. Bound original-record JSON parsing by these byte limits
and the unchanged review schema; do not recursively parse cited source.

Validate each original regular Git review record against THREAD_REVIEW.schema.json,
its full namespaced owner, canonical `<owner-id>/<review_type>.json` path, type,
reviewed SHA and exact evidence_refs membership. Its declared original commit must
be retained in protected-base ancestry; reject missing, unrelated or unmerged
original records. The review currently evaluated must have the exact declared
original blob and bytes. Integration-bound reviewed and review-record revisions
must agree with the declaration; it supplies no alternate integration binding.
Source-vs-output purpose must be independently reviewed for this exact use; an
output use cannot be relabeled by citing the same physical path.

`REVIEW_SOURCE_LINEAGE` is a distinct non-execution source-availability receipt and
cache. It intentionally replaces the full storage-aware REVIEW_RECORD_ONLY
prerequisite **only for declared source retrieval**. Resolve the exact reviewed
Git revision first. A present nonregular, oversized, unreadable or otherwise invalid
entry denies without fallback. Only complete Git-entry absence permits the exact
declared original final review-record commit. The fallback source itself and every
changed path in every intervening commit must be within the whole-component
`docs/exec-plans/reviews/<same-owner-id>/` directory. Prove reviewed ancestor,
exactly one parent per intervening commit, and inspect every edge including reverted
changes. Reject merge, foreign-owner, unrelated, traversal, ambient or later fallback.
Regular modes 100644/100755 only; raw source at most 256 KiB inclusive, bounded Git
reads (check type/size before reading; bounded subprocess output, deadlines and
aggregate work, fail closed on exhaustion). Maximum lineage proof is 4096 commits,
65536 changed-path entries, 64 MiB aggregate Git output, 10 seconds per Git read and
120 seconds per declaration proof. Declaration/reference processing is capped at
64 entries per validation context; caches retain at most those 64 source receipts.
HG058 must test these finite bounds; exhaustion denies, never truncates proof. No evaluation, import, network, decoding or content repair.
Return source identity only: proof kind, exact declaration/record identity, selected
revision, normalized path, mode, blob OID, byte count and SHA256. The receipt returns no source body or evidence verdict.
Cache keys include validation/protected-base revisions,
declaration blob, evaluated record blob, owner/type/reference and both bound SHAs;
cache entries never cross proof kinds or validation contexts.

This receipt does not invoke `storage_bookkeeping_only`, certify representation
immutability, set `review_only_suffix`, populate an RRO cache, or supply execution,
storage, review, task, requirement, M3, release or admission verdicts. HG047's strict
RRO failure remains: the original b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91 →
89b3d3f55de1c8e9882bfb7f5b109eb4c15da3c2 →
39a9a562cb4b9604916099b1a2af48e270c5b8d7 chain fails storage classification on
`general_round4/verify-attempt1.py` (`evidence-envelope-json`). Source availability
cannot turn that failure into RRO PASS or selected freshness PASS.

HG058 may dispatch a validated declaration before decoding at exactly these callers:

| Caller | Permitted source result | Independent guards retained |
|---|---|---|
| Global validate governance/task review loops (`review_reference_available`) | Historical source-citation availability only | Recorded identities/status; no new PASS |
| Integration review loop (`integration_record_errors` / `review_evidence_exists`) | Exact integration-agreeing source availability | Ancestry, result/review equality, status and full suffix |
| Selected task review loop (`review_evidence_exists`) | Exact evaluated-record source availability | Selected freshness, full suffix, status, result and identity |
| Selected governance review loop (`review_evidence_exists`) | Exact evaluated-record source availability | Selected freshness, full suffix, status, result and identity |

Undeclared refs retain existing bound readers. Ordinary/compact review output,
execution, result/task/requirement checks, M3, compact decoding, global storage,
history/reencoding and controller admission receive no source role or receipt.
The same path used as output still undergoes strict decoding. No catch-and-retry
on decoder failure and no blanket switch of evidence_refs. A global historical
source-availability error may clear; this proves no other predicate. HG059 defines
this boundary only; it implements no source retrieval, dispatch or cache.
