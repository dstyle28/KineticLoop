# HG-047 SECURITY_DATA_BOUNDARY — round 4

PASS at `b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91`. Zero BLOCKER and zero REQUIRED_FOLLOWUP findings.
G-01 remains a NONBLOCKING compatibility limitation. This verdict is specialist
review PASS only; merge, final full DB/App, requirements, M3 and release remain separate.

Base: `d08927706a01a397dac2c78ca4aec7e9918a389c`.
Tested source: `7b35dc5dd7c488b60651175574e37b5d9389d335`.

## Independent scope and boundary review

Read AGENTS, current index, pr-merge-reviewer skill, governance/SCOPE, storage,
review/result, merge and local controller contracts; inspected relevant frozen
Evidence Admission and T1–T8 clauses and the complete changed-path inventory.
Inspected the implementation, tests and contract diff independently. No prior
review verdict was used as proof.

The decoder resolves one immutable revision, checks normalized regular Git blobs,
same-directory owner and content-addressed payload, tested ancestry and optional
exact command/exit bindings. Stored limits/hash precede bounded single-member
zlib decompression; raw limits/hash and EOF/tail checks follow. Corrupt, missing,
truncated, concatenated or trailing data fails closed. Renamed/UTF-8/16/32 storage
objects remain reserved; wrapped, malformed and decoded nested storage cannot
supply an execution oracle. Actual nonreserved data remains lossless except G-01.
Counts are navigation only: M3 still examines raw log/JUnit/collection semantics.

The 4096-entry per-operation cache keys repository, exact SHA, path, tested SHA,
command and exit. Only successful immutable checks enter it. Mutable references,
working files and failures are never cached, and exceptional exit clears it.
Existing invalid evidence cannot be repaired through the review-only suffix.

The controller adds only decoder asset pinning and worker copying. Its eleven
installed assets require complete exact hashes; the installed validator imports
the decoder by installed file path. Missing/tampered/symlinked decoder and candidate
shadow imports reject. Reviewed code is copied into /gate. No installation,
configuration, signer, admission, App, Docker or external mutation was performed
by this review. Runtime, DB, workflows, classifier, provider authority, frozen
files and requirement authority remain byte-identical to base.

## Integration and raw Linux evidence

The repaired shared validator equals the entire premerge HG047 parent plus the
exact HG048 allowlist, and README equals both complete parent contributions.
All 116 nonshared HG048 files and 211 retained HG047 files match their parents.
Index and manifest hashes match exact candidate blobs. The source equals the
tested source and its result suffix is permitted. Intermediate a878a70 is retained;
only repaired 7b35dc5 is selected. Its bootstrap governance status is BLOCKED,
so historical checks are not silently promoted to fresh integrated-source PASS.

Independently retrieved 98 committed compact envelopes and all 13 selected
checks. The candidate budget passes at 3,733,970 bytes across 257 artifacts.
Hashes, owners and bound revisions were checked against committed Git objects.

Raw Linux ARM64 JUnit proves 1324 unique harness cases and 241 unique unit cases,
zero failures/errors/skips. Harness collection order equals trusted observer
node IDs; JUnit identity multisets equal all collected IDs. The observer records
session.items, not phase events; completed JUnit cases provide completion proof.
All eleven worker receipt artifact hashes, seven worker command records and six
host command records verify. Unique owned container/data-volume names and only
the nested-daemon data-volume mount are recorded; both cleanup flags are true.

All eleven pins match installed reviewed b737094 Git bytes. The installed
validator differs from integrated candidate validate_harness.py; this is disclosed
and expected, and candidate source authority is checked separately. The driver
uses full_db=False/test_only=True, reads no signer/admission, creates no App object,
and publishes nothing. This is DEVELOPMENT_NO_PUBLICATION, not the final gate.

The reconstructed initial RUNNING metadata matches the receipt's complete hash.
Final PASS metadata is separately preserved and adds only final execution fields;
raw execution records are unchanged. The metadata note and failed packager script
remain available. The earlier App failure at 8a78241 remains failure with 1304
passing cases and two errors and recorded cleanup. Old evidence/reports are retained.

## Reviewer executions and findings

291 focused decoder, provenance, compact M3, installed-import/copy and failed-start
cleanup tests passed on macOS with zero failures/errors/skips. The independent
exact-Git audit and 21 UTF-encoding/wrapped-storage probes passed. Commands and
hashes are in checks.json; verification.json contains the detailed proof inventory.
The first reviewer audit used an incorrect node-ID parser that split :: inside
parameter strings; the failure log is retained. The corrected comparison partitions
at the first parameter bracket and the complete rerun passed.

G-01 — NONBLOCKING: ordinary JSON with duplicate keys passes through when literal,
but a Unicode escape causes unique() to reject it before reserved storage identity
is established. Reproduced independently with literal/escaped ordinary event text.
This is a narrow fail-closed availability/compatibility issue; no malformed proof is
admitted, no accepted bytes change, and selected evidence is unaffected. A future
compatibility correction should enforce duplicate keys for reserved storage while
preserving ordinary bytes and test literal/escaped parity.

Final reviewed controller installation with complete pins, exact-head/controller
admission, fresh required reviews and root-run successful full DB/App gate remain
mandatory before merge. This review relies on the documented trusted operator/project
model and recorded execution evidence; it does not assert hostile-code sandboxing
or remote attestation. No product requirement, release or production/shadow authority
is advanced by this review.
