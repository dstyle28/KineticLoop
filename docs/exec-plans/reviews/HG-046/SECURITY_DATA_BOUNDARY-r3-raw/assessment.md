# HG-046 independent SECURITY_DATA_BOUNDARY review, round 3

Reviewed head: `fb720bc37c8e9ec436b0673de71c282f9778e6a8`.
Approved base: `26906bd7f4444914c228e98377f2b164fee0dd5d`.
Selected tested source: `fb7d62b73d80a56b8bce1d0f7cbd29f14aff77ab`.
Result: **CHANGES_REQUIRED**, one BLOCKER, `HG046-SEC-003`.

Read AGENTS, current authority index, reviewer skill, committed governance record,
storage policy and governance/review/merge/M3 contracts. Inspected actual code/test
and contract changes and preserved r1/r2 security findings. No runtime, DB,
migration, frozen baseline, schema, task/backlog, requirement status or historical
authority change is present.

The previous filename and standard JSON encoding bypasses are corrected. The
bounded independent fixture verifies seven standard encodings reject absent
payloads. However, conflicting UTF-16 BOM / UTF-32 body bytes in both LE and BE
orders still return `envelope=None`, availability true, unchanged metadata bytes
from retrieval, and audit errors empty. Payloads are absent; expected tested SHA,
command and exit are deliberately wrong. Complete bytes are malformed JSON, but
removing the conflicting BOM reveals the exact reserved storage object. This is
recognizable damaged compact content covered by the policy's explicit malformed
encoding rejection, rather than an arbitrary opaque historical log.

`verification.json` preserves the actual exit **1**, exact input hex, hashes,
committed fixture revisions and complete outcomes, captured once. `focused.json`
preserves the single permitted compact-suite execution: **114 passed**, exit **0**.
Both captures bind the reviewed head and exact commands. No broad harness,
authority, historical, DB or external execution was repeated.

The same verification independently decodes all seven selected committed records
at the reviewed SHA, checking exact tested/command/zero-exit binding, lengths and
stored/raw hashes. Actual recovered output establishes 1005 harness, 241 unit and
114 focused passes. Tested-to-reviewed bookkeeping is valid. The approved-base
prospective audit reports 92 changed evidence/review blobs, 85,932 stored bytes,
and no errors. These facts do not close the malformed encoding blocker.

Inspection and bounded negatives cover lossless binary bytes, reserved wrapping,
duplicate keys, normalized owner paths, regular Git blobs and symlinks, pinned
revision/no later repair, exact execution metadata, bounded single gzip member,
hash/length integrity, prospective plain/gzip/raw/PR caps, full-diff and raw_utf8
rejection, orphan payloads and duplicate bulk. Preserve r1/r2 and this failed proof.
Repair requires a new implementation SHA and fresh reviews. Protected master
advanced through HG-045; coordinator base refresh, retest, review and hosted CI
remain separate obligations. This assessment makes no merge recommendation or
product/release PASS claim.
