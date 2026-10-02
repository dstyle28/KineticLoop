# HG-046 independent SECURITY_DATA_BOUNDARY review, round 2

Reviewed implementation/result head: `5182feb0ad33319336efd913f63bf8c01c74b6a7`.
Protected base: `26906bd7f4444914c228e98377f2b164fee0dd5d`.
Selected tested implementation: `58de0f7dfbf39947f2c2c1852cc927823e79b4c3`.
Result: **CHANGES_REQUIRED**, one BLOCKER, `HG046-SEC-002`.

Read current authority index, AGENTS, pr-merge-reviewer skill, committed governance record and storage/review/merge/governance contracts. Inspected the complete relevant code, tests, contract and derived-hash diff. No runtime, DB, frozen, task/backlog, schema, requirement status or history change is present.

The prior `.json` suffix blocker is closed for UTF-8: renamed `.log`, uppercase `.JSON` and extensionless envelopes with absent payloads fail availability. JSON `raw_utf8` content is detected across filenames and UTF-16 encoding. Ancillary M3 JUnit and collection sources bind expected execution/collection commands before semantic parsing.

A fresh encoding attack still bypasses the security boundary. `envelope()` scans ASCII byte substrings before JSON parsing. Standard UTF-16/UTF-32 serializations contain interleaved NULs, so `read()` returns them as historical plain bytes. The tiny isolated fixture proves that missing payload, wrong expected tested SHA, wrong command and exit 1 all pass generic evidence availability with prospective budget errors empty. These are real committed Git fixtures; the source scripts and captured output are retained. Neither broad tests nor normal/full check-harness were run during this review.

The permitted compact test file ran independently: **59 passed in 30.11s**. Its exact stdout/stderr is captured once in `focused.json` and its content-addressed gzip. Initial probe invocation failed before its script existed because the concurrently running focused capture had not yet created the review directory; that real failed output is retained separately in `extension-probe.json`. The subsequent successful probes are `probe-result.json` and `encoding-isolation.json`. All reviewer-created captures bind the reviewed head.

Independently decoded all seven selected committed check references at the exact reviewed head and checked full tested SHA, command, exit zero, stored/raw lengths/hashes and committed same-revision payloads. The recovered logs show 950 harness passes, 241 unit passes and 59 focused passes; lint, typecheck, authority and empty successful diff-check output are also present. Tested-to-reviewed governance suffix errors are empty. Protected-base budget reports 52 changed evidence/review files, 45,135 stored bytes, no errors. These metadata values do not substitute for semantic proof.

Beyond the blocker, code inspection and the focused negatives cover normalized paths, task ownership, symlink/directory and Git modes, pinned symbolic revision resolution, no later payload borrowing, exact stored/raw integrity, bounded single-member decompression, truncation/concatenation/trailing bytes, duplicate keys, size/count/exit types, review-created provenance, absent/tampered payloads, full-diff rejection, orphan payloads, shared payload reuse, duplicate bulk and total changed-PR budgets. Historical plain evidence remains accepted prospectively. Required hosted CI and merge are separate coordinator decisions; this review cannot recommend merge until the blocker is repaired and the new implementation SHA receives fresh review.
