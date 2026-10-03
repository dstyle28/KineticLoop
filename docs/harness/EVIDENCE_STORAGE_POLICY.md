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
truncate, fabricate PASS, waive CI or change historical evidence to fit a budget.
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
