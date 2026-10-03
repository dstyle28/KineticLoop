# Independent SECURITY_DATA_BOUNDARY review, round 4

PASS for harness-governance-v0.1/HG-046 at reviewed head
`02d95c1d86ade83128671190e1e1bf916cfe2b88`, against approved base
`26906bd7f4444914c228e98377f2b164fee0dd5d`. No security blocker remains in this
assigned diff. This is no merge recommendation.

Read AGENTS.md, current document index, pr-merge-reviewer skill, committed HG-046
governance record, evidence policy and review/result/merge/M3 contracts. Inspected
actual source, test, policy and authority-metadata diffs, plus retained rounds 1–3
findings. Frozen/runtime/DB/schema/provider/product authority paths are unchanged;
production auto-activation and executable real-data shadow remain disabled, and
this storage policy creates no requirement or release PASS.

The focused test command actually returned exit 0: 194 passed. Independent committed
Git-blob decoding recovered all eight selected envelopes from the same reviewed
revision; ordinary Python gzip/hashlib independently checked stored and recovered
lengths and hashes before comparison with the guarded reader. Selected proof records
1085 harness tests, 241 unit tests, lint, typecheck, authority and source-diff success
on `9f2f38fe69f772d1564f0fa5eee2441da038aef1`; their command/exit metadata matches the
committed governance checks. The tested-to-reviewed suffix adds own evidence and
updates only the HG-046 governance result. Full suites and authority were inspected,
not rerun by this reviewer.

Round 1 extension and round 2 standard-encoding bypasses are closed: reserved storage
recognition is content-based under arbitrary names and strict UTF-8/16/32/BOM forms;
malformed, escaped, removed-marker and wrapped objects fail. Round 3 conflicting
BOM/body examples now fail using original reserved ASCII-byte hints solely for
rejection. Neither NUL removal, escape substitution nor replacement decoding accepts
proof bytes. Opaque original bytes remain lossless. Independent 60 conflicting-BOM
classification cases and opaque controls passed; two committed UTF-16-BOM/UTF-32-body
LE/BE fixtures under uppercase and extensionless names reject read, availability and
audit with missing payload and deliberately incorrect execution expectations.

Inspected/tested guards cover normalized paths and task ownership, symlink/directory
rejection, regular Git blobs, one pinned revision for envelope and payload, absent
or damaged payloads, no later-HEAD repair, exact tested SHA/command/integer exit,
stored and raw hashes/lengths, and bounded single-member gzip rejecting truncation,
trailing bytes, concatenation and expansion beyond declared raw size. M3 callers
continue decoding real logs/JUnit/collection and binding execution/collection
commands; metadata counts alone do not replace semantic proof.

Prospective inclusive caps remain 256 KiB plain/envelope, 8 MiB stored gzip,
64 MiB recovered payload and 16 MiB changed evidence/review total. Assigned-base
committed audit reports 128366 stored bytes across 128 files and no errors. The
focused tests exercise historical exclusion, changed foreign-artifact inclusion,
complete-diff copies (including compressed), recursive raw_utf8 regardless of
extension, orphan gzip and duplicate bulk; shared actual content-addressed payloads
and repeated genuine log lines remain valid.

Protected master advanced separately to
`fc8a044ffa4d15a74ce5dc59298ae411f1f4009b` through HG-045/PR89. The selected source
ancestry probe has actual exit 1, and this review independently captured current-base
to reviewed-head ancestry exit 1. Neither is task PASS. Coordinator serialization,
protected-base refresh, retest and fresh SHA-bound reviews are required before merge;
HG-045 changes/dependency claims and hosted CI status are outside this review.

Only this typed record and its own r4 child proof/assessment files were written.
No source edits, commits, HEAD changes, external messages, broad/full harness,
authority or historical reruns were performed. Exact raw output is captured once in
content-addressed gzip with actual commands/exits and reviewed-head tested binding;
old failed rounds remain untouched. Review-created proof must be committed through
the linear own-task REVIEW_RECORD_ONLY suffix to become integration evidence.
