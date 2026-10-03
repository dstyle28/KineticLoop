# HG-046 GENERAL independent review, round 4

Reviewed `02d95c1d86ade83128671190e1e1bf916cfe2b88` against approved base
`26906bd7f4444914c228e98377f2b164fee0dd5d`; selected tested source is
`9f2f38fe69f772d1564f0fa5eee2441da038aef1`. Authority was resolved through
CURRENT_DOCUMENT_INDEX; the governance record substitutes for an active task
packet. Read the PR review skill and evidence/review/merge/M3 contracts.

Inspected the actual approved-base implementation, tests and contract diff.
Reserved envelopes are recognized independently of extensions and JSON-supported
UTF-8/16/32 encodings. Malformed encoding, conflicting BOM/body, escaped/removed
markers and wrapped storage cannot become plain proof. The original reserved-byte
hint rejects malformed decoding only; opaque bytes are returned unchanged.
Exact regular Git blobs bind envelope and payload to one resolved revision;
length/hash checks, bounded single-member gzip, owner/name/path guards, tested
ancestry and expected command/exit checks preserve proof boundaries. M3 decodes
logs, JUnit and collection sources before its existing semantic oracles, with
ancillary execution/collection command metadata now checked. Selected CI derives
one owner and always invokes the protected-base budget, including review suffixes.

Verification read the committed selected envelopes and actual payload bytes,
checked deterministic gzip and exact commands/exits/tested SHA, and used the raw
pytest oracle for 1085 harness, 241 unit and 194 focused passes. Lint, typecheck,
authority and empty diff-check output also match their recorded zero exits.
The 144 changed paths equal the declaration; source is byte-identical from tested
to reviewed. Runtime, DB, frozen files, schemas, task state and product requirement
state are unchanged. The prospective audit accepts 128 files / 128366 stored bytes.
Preserved r1/r2/r3 CHANGES_REQUIRED records and their raw evidence remain readable;
source changes and regression coverage close their classification findings.

Own focused rerun passed 194 tests with actual exit 0 in 92.89 seconds.
Own proof is in verification.json and focused.json, captured once with actual
command/exit and reviewed SHA. Review-created references require commitment in the
strict own-task linear REVIEW_RECORD_ONLY suffix before satisfying the merge gate.
This review does not create task, product requirement or merge PASS.

Protected master has advanced to `fc8a044ffa4d15a74ce5dc59298ae411f1f4009b`.
The preserved current-base ancestry probe has actual exit 1; independently repeating
that bounded ancestry query agrees. This review is scoped solely to the approved
base and has no HG-045 dependency or modification. Coordinator base refresh,
retest, fresh review, hosted CI and final selected gate remain required before
merge. No merge recommendation is issued.
