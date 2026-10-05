# Prospective evidence storage policy — HG047

Keep evidence lossless and task-owned. This policy changes storage, not task,
requirement, review, integration or M3 PASS meaning. Historical plain references
remain valid; this PR migrates or deletes no historical artifacts.

New command output may be referenced by a small JSON envelope with
`kineticloop_evidence: gzip-v1`. Its sole payload is deterministic gzip (mtime zero,
no original filename), named `<raw_sha256>.gz` in the same directory as the envelope
under `docs/exec-plans/evidence/<owner>/` or `docs/exec-plans/reviews/<owner>/`.
Place review envelopes in a child directory such as `raw/`; root review JSON
filenames remain reserved for the canonical typed review records.
The envelope contains exact stored/raw SHA256 and byte lengths, full tested commit,
command, integer exit code, timestamp when available (otherwise null), and observed
test counts. Counts are navigation metadata; semantic validators inspect recovered
raw bytes. Capture once and reference that envelope from multiple checks or reviews
only when they actually share the execution. Never rewrite repeated raw log lines
or ordered arrays. Deduplicate genuinely set-valued report outputs before generating
them; the budget report emits unique sorted failures and paths.

Both envelope and payload must be normalized repository-relative regular Git blobs
at the **same existing bound revision**. No symlink, traversal, directory, borrowed
owner, HEAD fallback or later payload is accepted. Outer evidence hashes identify
the envelope blob; `raw_sha256` identifies the recovered original. The decoder
checks stored length/hash before bounded single-member decompression, exact raw
length/hash afterwards, and rejects truncation, concatenated members and trailing
bytes. The tested commit must exist and precede the evidence revision; task checks
also bind the exact result tested SHA and command, with zero exit code for PASS.
Review-created evidence uses the existing exact review-record revision only after
its own linear REVIEW_RECORD_ONLY suffix is proven. A present manifest with an
absent or invalid payload cannot satisfy evidence availability or PASS. M3 reads
logs, JUnit, collection JSON and collection stdout through this same decoder;
selector, case, count, skip/failure and provenance rules still apply.
Reserved compact content is recognized regardless of filename extension; renaming
an envelope cannot turn its metadata into plain execution proof. Ancillary M3
envelopes also bind the execution or exact collection command, as appropriate.
Recognition covers JSON's UTF-8, UTF-16 and UTF-32 encodings, including BOM and
byte-order variants. Malformed reserved encodings fail; opaque plain bytes stay lossless.
Wrapping a reserved storage object inside a list or another object is invalid;
it cannot convert a missing-payload manifest into plain evidence. The same
classification applies after bounded decompression: decoded reserved storage
objects, including wrapped or malformed ones, are rejected before any raw
evidence oracle. Nested envelopes are not recursively decoded. Actual
non-envelope output remains byte-for-byte lossless.

The protected-base `kl check-harness` gate budgets only added/changed evidence and
review artifacts owned by the selected task/governance PR, including its review
suffix. Historical untouched artifacts are excluded. Limits (inclusive) are:

| Artifact | Limit |
|---|---:|
| Plain artifact / JSON envelope | 256 KiB |
| Individual gzip payload | 8 MiB |
| Decompressed payload | 64 MiB |
| Total changed evidence and review blobs in PR | 16 MiB |

These limits accommodate the measured historical KL028 24.8 MB log compressed to
3.12 MB, while requiring a different capture for the HG044 8.2 MB report with
183,879 dependency edges but only 103 distinct edges. Four identical 6.7 MB Git
diff copies should instead be one recorded base/head pair. Source/test changes and
generated evidence bytes must be reported separately in the PR.

The gate rejects `complete-diff.patch`, recursive `raw_utf8` in new plain JSON,
orphan gzip payloads and exact duplicate bulk artifacts (at least 16 KiB). JSON
content is checked for `raw_utf8` regardless of its filename extension.
Shared content-addressed payloads are permitted. Store base/head SHAs and inspect
`git diff <base> <head>` on demand; do not persist complete diff dumps. Do not
truncate, fabricate PASS, waive CI or change historical evidence to fit a budget outside the exact HG051 authorization below.
Over-limit failures point to the capture tool. If a real execution exceeds these
limits after compression, report the blocker and refine capture/storage through
reviewed governance; splitting real independent executions is acceptable.

```sh
# First execute a real check, preserving its exit code and exact stdout/stderr.
uv run kl test-harness > /tmp/hg047-harness.log 2>&1
kl_capture_exit=$?
python tools/harness/compact_evidence.py capture \
  --input /tmp/hg047-harness.log \
  --output docs/exec-plans/evidence/HG-047/harness.json \
  --tested "$(git rev-parse HEAD)" --command 'uv run kl test-harness' \
  --exit-code "$kl_capture_exit"
# Commit both envelope and payload before review. Retrieval requires their bound SHA.
python tools/harness/compact_evidence.py read \
  docs/exec-plans/evidence/HG-047/harness.json --revision <bound-sha> > /tmp/recovered.log
python tools/harness/compact_evidence.py audit \
  --base <protected-base> --head <pr-head> --identity HG-047
uv run kl check-harness --ci-pr-base <protected-base> --ci-pr-head <pr-head>
```

Capture records the caller's actual execution metadata; it does not execute a
command, certify a test oracle or grant PASS. Safe retrieval is byte-preserving,
including non-UTF8 logs. No external account or storage service is needed.

## HG051 exact historical representation authorization

The human-approved forward storage migration is limited to the four exact KL080
original objects pinned by `HISTORICAL_EVIDENCE_MAPPING.schema.json` and inventoried
in `docs/exec-plans/evidence/HG-051/INVENTORY.json`. HG051 adds governance only;
a later KL080 forward commit may replace those four current-tree raw representations
with `kineticloop_evidence: historical-gzip-v1` envelopes at the same paths and
same-directory `<raw_sha256>.gz` payloads. No owner/path rename, external archive,
splitting, exception to budgets, history rewrite or other historical migration is
permitted. All other existing KL080 evidence stays byte-identical. Original commits
must remain in normal merge ancestry; squash/rebase/history pruning cannot replace
that requirement. Fetch the original commits in shallow repositories before original
verification. Unavailable originals fail verification, never borrow HEAD or archives.

Exactly one new task-owned `docs/exec-plans/evidence/KL-080/HISTORICAL_EVIDENCE_MAPPING.json`
uses `kineticloop_evidence: historical-mapping-v1`, purpose `ARCHIVAL_RETRIEVAL_ONLY`,
and the schema's exact ordered four entries. Each original pins namespaced owner,
path, original evidence commit, regular Git blob ID, raw SHA256/length, exact known
execution metadata and its unchanged historical record reference. Unknown timestamps
stay null. The historical BLOCKED/FAIL/UNMERGED result and CHANGES_REQUIRED reviews
retain their original tested/reviewed bindings and exact hashed record snapshots;
two source-suite failures remain FAIL/exit 1. The two harness XML captures retain
their original recorded success without becoming fresh execution or task PASS.

A mapping entry separately pins one full storage commit, envelope path/hash/length,
and payload path/hash/length. All four use the same existing storage commit; it
precedes the mapping commit. Storage envelopes/payloads must be regular Git blobs
at that storage commit and byte-identical at the evaluated mapping revision.
Build the mapping after committing storage via `compact_evidence.py archive-map`.
This avoids self-referential commit hashes. Commit migration and mapping before a
new tested SHA; neither post-test nor post-review bookkeeping may overwrite history.
The mapping is a forward addition, not a rebindable replacement.

Ordinary `read`, result/review verification and M3 readers reject both archival
formats, including encoded, renamed, wrapped or nested metadata. Historical proof
continues to read the original regular plain blob at its original bound revision.
The separate `archive-read --revision <exact mapping commit>` recovers raw bytes and
checks storage integrity without certifying original review/PASS; it can recover
bytes even when original commits are unavailable. The PR audit additionally requires
original blobs and preserved records to exist, match the fixed authorization, and
precede storage/evaluation in normal ancestry. Missing/duplicate/orphan/out-of-scope
mappings or payloads fail closed. Retrieval never changes any status or requirement.

Every added/changed mapping, envelope, payload and review counts toward unchanged
256KiB plain, 8MiB stored gzip, 64MiB recovered and 16MiB aggregate bounds. Existing
gzip-v1 execution capture/decoding and all its command/tested-SHA/exit checks remain
unchanged. This named authorization creates no general historical storage waiver.

## HG054 optional bounded XZ and own unmerged forward re-encoding

`capture --codec xz` selects `kineticloop_evidence: xz-v1` and same-directory
`<raw_sha256>.xz`. Default capture remains `gzip-v1`; both formats use identical
execution metadata and raw identity fields. XZ encoding pins FORMAT_XZ, CRC64 and
preset 6. Repeated encoding must be deterministic on the executing runner;
compressed bytes need not match across liblzma versions. Each bound envelope pins
its actual stored bytes. The decoder selects only the declared codec: no extension
guessing, fallback or archive-reader delegation. XZ requires one CRC64 stream,
EOF, no trailing/unused bytes, a fixed 64 MiB decoder memory limit and at most
`raw_bytes + 1` output; declared raw length/hash must match exactly. Gzip guards,
UTF-8/16/32 reserved-object classification, nested-object rejection, regular Git
blob/revision/owner binding and semantic test oracles remain mandatory.
All numerical budgets above remain unchanged for both codecs. `.gz` and `.xz`
payloads both count; retaining both codec copies cannot evade duplicate-bulk rules.

Forward re-encoding is explicitly authorized only for same-owner, already compact,
unmerged gzip-v1/xz-v1 regular blobs absent from the protected PR base. No plain,
archival, foreign-owner, renamed-owner, invalid or sanitized-as-original input is
admitted. The explicit `reencode` action is separate from capture/read/audit; source
is a full existing ancestor commit and must match the current selected envelope and
payload bytes. The raw bytes/hash/length, tested commit, command,
exit code, timestamp and test counts remain exactly equal. Only codec marker,
payload extension/path, stored hash and stored length change. This representation
operation is not a new execution and cannot promote any earlier failure or review.

During this explicit codec change, optional `--destination-dir` may relocate the
selected envelopes into one new child directory under exactly the same owner and
evidence/review subtree. Replacement envelope names are the SHA256 of each original
envelope, so independent execution metadata remains distinct while identical raw
bytes can share one same-directory content-addressed payload. Every original and
replacement path is snapshot-bound by the immutable mapping. Refuse source,
current-tree or protected-base destination collisions, foreign/subtree moves and
unaccounted source retirement. A relocated original envelope must be absent from
the resulting tree; its original bound Git object remains available in ancestry.
This authorizes no codec-free relocation or general deletion. The default action
keeps each envelope at its original path. Neither side of a map may be converted
again in the same unmerged branch.

The same forward commit includes a uniquely named task-owned child
`COMPACT_REENCODING.json` ordinary audit record with `compact_reencoding: v1`.
It has exactly identity, protected_base, source_revision and entries. Each entry
pins original and replacement envelope/payload path, regular Git blob ID,
SHA256 and byte length, plus unchanged execution fields. Source snapshots stay
readable at their original revision in normal Git ancestry; unavailable objects
fail closed. Audit validates all mappings and each intervening commit, rejecting
unmapped envelope/payload mutations, deletion/reversion, missing/remapped originals,
metadata changes and protected-base paths. Maps are immutable. A mapped envelope
cannot be converted a second time in that unmerged branch; independent envelopes
may use separate uniquely named records. Maps, including encoded/wrapped forms,
are never readable as execution output. New result references bind hashes of new
envelopes at new evidence revisions; historical records retain original bindings.

Obsolete current payloads are removed only when every current same-owner envelope
reference has been accounted for; shared payloads remain while any ref uses them.
Historical result/review record bytes are not rewritten by the action. Perform all
representation mutations before the new tested/result/review revisions, rerun
checks and obtain fresh required reviews. Re-encoding and mappings are never
REVIEW_RECORD_ONLY. Provenance ambiguity stays BLOCKED. Existing harmless envelope
filename/JSON-encoding compatibility preserves exact metadata/payload identity;
it does not authorize owner changes or unmapped codec conversions.

```sh
python tools/harness/compact_evidence.py reencode \
  --base <full-protected-base> --source <full-source-commit> --identity <own-id> \
  --path docs/exec-plans/evidence/<own-id>/<run>/check.json \
  --record docs/exec-plans/evidence/<own-id>/<unique-conversion>/COMPACT_REENCODING.json \
  --codec xz
# Commit conversion and record together, then establish a NEW tested SHA.
```

This authorization is independent of HG051. Its exact historical gzip schema,
original pins, archival-only reader and failure facts remain unchanged; XZ is not
an archival format. HG054 migrates no KL036/KL080/merged artifacts and grants no
product, release, App or database PASS. Current installed controller assets do not
admit new formats until root completes separately reviewed complete installation
and exact-head/controller admission under LOCAL_DB_CI.md.

Local mutation requires an exclusive writer in the task worktree. Serialize capture,
re-encoding, edits and commits; stop any concurrent producer/editor before conversion.
Rollback restores local originals for ordinary single-writer failures; it does not
provide concurrent-writer or crash recovery. An interrupted operation stays BLOCKED
until original files are restored or its complete mapping/representations validate.
This discipline grants no database transaction or execution authority.
Maps already admitted at the protected base are immutable historical bindings,
reverified against their original admitted base and source even if no artifacts
changed. New conversions must additionally prove the actual PR base precedes their
source. A normal forward merge of a newer protected base may retain an already
committed same-owner unmerged map without rewriting its admitted base or source.
This requires exact map bytes on the task first-parent lineage before the first
import, a valid original admission whose unique merge-base with the actual base
is the recorded base, and a full unchanged old-base-to-pre-import audit. Source
must remain unmerged into the actual base; no mapped path or record may have been
used in the protected-base advance. All source/replacement proofs and per-edge
immutability checks continue across import and later commits. A pre-admission
protected parent never inherited this task map. Every actual-base descendant containing the source must also contain the
original map admission; reversing merge-parent order cannot backdate a late map.
Late side-branch or working-only maps, older-base claims after an intermediate import, previously merged/deleted
sources, and unavailable originals fail closed. Fresh conversions retain the
strict actual-base-to-source requirement; committed retained maps do not grant
new conversion authority. A removed map marker, including wrapped/encoded variants, cannot turn
storage metadata into ordinary execution output.
Inherited-map verification is global across all admitted owners, including unrelated
PRs and a no-change audit. It uses each immutable map's own admitted identity/base;
unavailable originals or changed/deleted mappings fail closed. Map bytes and both
snapshot bindings are checked at every intervening revision/parent descended from
the protected base, so later restoration cannot hide mutation. Side branches before
admission need no retroactive map existence; their later merge must preserve all
admitted bindings. This global historical
verification does not authorize a new foreign-owner conversion: new mappings and
ancestral representation mutations remain restricted to the selected PR owner.
Changed storage blobs are classified globally at every intervening
revision, including renamed/wrapped/nested metadata and Unicode forms on branches
before admission, even when metadata is named with a payload extension. Classification
reads actual bounded stored bytes and never guesses a decoder from the extension.
Literal JSON strings inside a valid binary stream are ordinary payload bytes. A
JSON/encoding classifier error on a stored-payload path may be disregarded only
after full bound retrieval proves that exact payload at that exact revision (or
parent for prior-state classification). The proof checks the declared codec,
same-directory ownership, regular Git objects, stored/raw hashes and lengths,
bounded decoding, non-nested raw classification and ancestry. Frozen archival
payloads require their existing exact inventory/original proof. Unproven aliases,
size/type/integrity failures and later mapping/mutation guards remain fail-closed.
Recognized execution envelopes must pass bound retrieval at that revision; archival
objects remain subject to the exact frozen archival inventory and original proof,
including its storage-before-mapping commit. Deletion before HEAD cannot hide a foreign conversion. Changed
compact metadata
and payloads are checked across owners on edges descended from the protected base.
Task and governance tested/review suffix validators reject conversion records and
existing compact representation changes even under allowed bookkeeping paths;
restoration in a later suffix commit does not restore freshness. Newly captured
independent review output remains ordinary review evidence.


## HG056 ordinary source compatibility

Reserved field names used as ordinary reader literals, quoted prose, or JSON string
values are plain content and remain byte-identical. Recognition requires storage
key/value or assignment structure, including partial object keys. Actual reserved
metadata stays fail-closed in source dictionaries, assignments, comments, escaped
string wrappers, malformed/truncated JSON and UTF-8/16/32 or conflicting BOM forms.
This classification is content-based across all owners, paths, suffixes and bounded
recovery. It executes no source and grants no execution, review, admission or PASS
meaning. All binding, ancestry, per-edge, archival and retained-map proofs remain
mandatory; no original source hash or filename is a runtime exemption.
