# HG-047 SECURITY_DATA_BOUNDARY review

Verdict: PASS. No BLOCKER, REQUIRED_FOLLOWUP, or NONBLOCKING implementation findings.

Identity: `harness-governance-v0.1/HG-047` (PR 91). Reviewed implementation/result: `47de76d206df89124ffe41c59b0b983af4defc97`. Tested implementation: `2dc15b7c79b835197449ca705f82f221eee6f05d`. Protected base: `391c9198fa8ec647e377a0572700bc7568468c85`. Review contract: v0.2.

## Independent examination

Read the current authority index, agent guide, pr-merge-reviewer skill, HG-047 governance record, evidence-storage policy, governance/review/local-CI contracts and merged HG-045/HG-046 prerequisite records. Inspected the actual base-to-reviewed diff and selected Git blobs; author summaries and historical review verdicts did not substitute for review.

- `compact_evidence.py:103-207` recognizes reserved JSON across UTF-8/16/32, BOM/endian variants and escaped keys, and rejects damaged or wrapped storage records. Plain historical bytes remain unchanged. Envelope and content-addressed payload resolve at the same commit, with normalized owner-local paths and exact regular Git blobs. No ambient HEAD or later payload fallback is present.
- Stored length/hash precede bounded single-member decompression; recovered length/hash, EOF, unused input and unconsumed tail reject corruption, truncation, extra members and expansion beyond the declared bound. Limits are 256 KiB envelope/plain changed artifact, 8 MiB stored payload, 64 MiB recovered payload and 16 MiB changed evidence/review total. Command, tested revision/ancestry and zero PASS exit provenance remain enforced for compact task/governance evidence; M3 continues reading raw semantic proof.
- `validate_harness.py:1768-1809` retains only successful verdict keys, scoped to one validation operation, capped at 4,096 entries. Keys include resolved repository path, full revision, evidence path, expected tested SHA, command and exit code. It retains no raw bytes, persists no cache, rereads mutable references/working files, never inserts failed proofs, and clears on exceptional exit. Nested validation shares the active operation intentionally; separate operations recheck object availability/integrity.
- `local_gate.py` adds the decoder to all 11 installed ASSETS and copies that installed asset to `/gate/tools/harness/`. The validator loads its sibling decoder by explicit resolved file path. Missing, changed, symlinked or unpinned installed decoders fail validation; candidate import shadowing cannot supply it.
- Prospective retention leaves merged history unchanged and preserves failed development proof. Budget enforcement includes changed evidence/review owners, rejects recursive plain `raw_utf8`, complete-diff dumps, orphan gzip and duplicate bulk output, while permitting multiple envelopes to share one payload. No network storage, credential access, deletion, production activation or executable-shadow permission is added.

## Actual verification

At the reviewed implementation, ran:

`PYTHONDONTWRITEBYTECODE=1 /private/tmp/hg044-venv/bin/python -B -m pytest -q -p no:cacheprovider tests/harness/test_compact_evidence.py tests/harness/test_local_gate.py -k 'not failed_start'`

Result: exit 0; **243 passed, 1 deselected in 66.45s**. The deselected pre-existing worker-cleanup test is unrelated to this decoder change. This run covers byte-preserving retrieval, encoded downgrade negatives, ownership/revision/regular-blob constraints, hash/size/decompression failures, provenance, cache scope/bounds/freshness, installation pins and candidate-decoder isolation. Full harness and full DB were not repeated.

Independently read all eight selected envelopes/payloads directly from Git at the reviewed SHA, checked regular modes, owner-local content-addressed names, SHA256/lengths, command/tested/exit agreement with the governance and execution records, and decompressed with Python gzip. All passed. Recovered harness and unit output reports **1,271 passed** and **241 passed** respectively; lint, typecheck, authority, scope, empty successful diff-check output and performance proof also match their recorded hashes. This independently verifies stored proof and binding, not a second execution of those checks.

Ran the compact audit for the exact base/head: **40 files, 41,195 stored bytes, no errors**. `git diff --check` passed. Independently compared protected paths: merged HG-045/HG-046 evidence/governance/reviews, workflows, classifier, DB runner, App client, runtime/migrations, frozen Protocol/DB/baseline and requirement set are unchanged. Tested-to-reviewed changes are only HG-047 governance/evidence bookkeeping.

## Remaining operational boundary

This is a security review PASS for the bound implementation; it is not final merge, App, full-DB, M3, product or release PASS. Before a successful final gate, install the reviewed Git blobs for the complete 11-file ASSETS set as one new external versioned release, verify every regular file against its full `controller_files` SHA256 map, and run isolated trusted entrypoints. Preserve the existing App identity, installation, repository, permissions and private-key location; atomically replace only the owner-only configuration pins with a retained backup. Do not source trusted modules from the candidate worktree.

Admission must newly bind the live protected base, final review-record-only PR head and new controller identity. Run the ordinary required App/full-DB gate for that exact final head and retain its actual receipt; previous success or test-only evidence cannot authorize it. This review neither examined live credentials/configuration nor performed installation, admission, publication or database execution. Persisting this report requires the existing linear task-scoped REVIEW_RECORD_ONLY suffix proof.
