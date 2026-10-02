# HG-046 independent security review

Protected base: `26906bd7f4444914c228e98377f2b164fee0dd5d`.
Reviewed implementation: `5ae6b31ac4c4639fbfe2fd7ca3df029abdfae323`.

Verdict: CHANGES_REQUIRED. Storage recognition depends on a lowercase `.json`
filename. An exact `gzip-v1` manifest renamed `.log` is treated as plain bytes by
`compact_evidence.read`, `evidence_exists`, and the protected-base budget audit.
Deleting its gzip payload therefore stops being an evidence-availability failure.
This also skips tested revision, command, exit, lengths, hashes, ownership and
decompression checks. Recursive `raw_utf8` JSON renamed `.txt` similarly escapes
the prospective JSON storage rule.

The isolated reproduction initializes a temporary Git repository, creates one
source commit, captures `1 passed in 0.01s\n`, commits it, deletes and commits its
payload, and verifies that the `.json` reference fails. It renames that same
manifest to `.log`, commits again, and asserts that both exact-revision
`evidence_exists(..., tested=base, command='pytest', exit_code=0)` and
`audit(base, renamed_head, 'HG-046')` accept it. No implementation files change.
The second case removes the renamed manifest and adds
`{"nested":[{"raw_utf8":"copied command output"}]}` as `nested.txt`; audit also
accepts it. The recorded output reports these observed bypasses explicitly.

Required fix: classify manifests by their storage markers independently of the
filename, or reject storage-shaped content under unsupported extensions. Route
availability checks through that classifier. Recognize plain JSON content for
the recursive `raw_utf8` rule independently of extension. Preserve opaque
historical evidence compatibility. Add negative tests for renamed, uppercase and
extensionless manifests, missing or tampered payloads, and renamed JSON wrappers.

Other inspected controls use normalized owner paths, regular Git blob modes,
existing pinned revisions, command/tested/exit binding, stored and raw bounds and
hashes, bounded single-member decompression, and strict review-only suffix
provenance. Git subprocesses use argument arrays; no external storage/network
operation or shell execution was added. Focused tests cover corruption, missing
payloads, symlinks, traversal, duplicate keys, decompression bombs, truncation,
multiple members/trailing bytes, revision pinning, budget totals/duplicates/orphans,
and raw-evidence provenance. M3 decoded logs/JUnit/collection semantics were
independently inspected in the changed implementation and tests. The broad
87-test selection was interrupted in the historical
`test_premature_real_revision_without028029_rejects` case to keep this review
bounded: 62 tests passed, 242 were deselected, and the run exited 2. Its exact
output is retained in `checks.json`; it is not a PASS for all 87 selected tests.
The separate bounded reproduction and pinned raw/budget audit exited 0 and is
retained in `adversarial.json`. Actual committed HG-046 command
output is recovered at the pinned revision; test-count metadata is not an oracle.

Task, product requirement, independent review, CI and merge facts remain separate.
This security review does not assert product PASS or merge eligibility.
