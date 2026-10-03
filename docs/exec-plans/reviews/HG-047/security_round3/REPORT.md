# HG-047 SECURITY_DATA_BOUNDARY review — round 3

Verdict: PASS for the security/data-boundary review at `589e538579f519bc10d178fa02dff12332931ba7`.
No BLOCKER or REQUIRED_FOLLOWUP findings were identified. This is a specialist
review verdict, not merge, full-DB, App publication, product, M3 or release PASS.

Protected base: `391c9198fa8ec647e377a0572700bc7568468c85`.
Tested source: `f29ffa97d9057eacc4bda7ad593b843c9c52c5a2`.

The review independently read AGENTS.md, current index, the pr-merge-reviewer
skill, HG-047 governance/SCOPE, the evidence-storage/review/CI contracts,
merged HG-045/HG-046 result boundaries and relevant frozen Evidence Admission,
Replay and T1–T8 clauses. It inspected the complete base-to-reviewed path scope
and implementation/test/contract diff, then verified the committed proof directly.
Prior reviewer conclusions were not used as proof.

## Boundaries checked

- `tools/harness/compact_evidence.py:49–80,153–210`: exact commit resolution,
  normalized regular Git blobs, same-directory/owner content addressing, tested
  ancestry, exact command/exit binding, stored and recovered hashes/lengths,
  bounded single-member decompression, and rejection of truncated, trailing or
  concatenated gzip content. No ambient HEAD payload repair or archive extraction.
- `tools/harness/compact_evidence.py:99–150,207–210`: reserved metadata is
  recognized across JSON encodings/renamed files and rejected when malformed,
  wrapped, or nested after decompression. Capture cleans up rejected new payloads.
  Recovered ordinary data is byte-preserving; navigation counts grant no authority.
- `tools/harness/validate_harness.py:1768–1805,1861–1870`: the bounded cache holds
  only successful immutable checks within one operation and keys repository,
  revision, reference, tested revision, command and exit. Mutable refs/working
  files and failed reads are not cached. Existing invalid evidence cannot be
  repaired via the review-only suffix; new review evidence requires the existing
  exact task-owned linear suffix rule.
- `tools/harness/validate_harness.py:2677–2820`: decoded raw log/JUnit/collection
  content still passes the semantic oracles and exact provenance checks. Inner
  storage metadata cannot supply a fake raw success oracle.
- `tools/harness/local_gate.py:39,49–57,211–213` and validator import setup:
  the decoder is a required hashed installed asset copied from the reviewed
  release. The validator imports it by the installed path. Candidate-directory
  shadowing and missing/changed/symlinked installed decoder cases reject.
- Only the decoder asset pin/copy integration changes controller behavior.
  Classifier, signer/App code, admission, observer, workflow policy, runtime,
  migrations, DB tests and frozen authorities are byte-identical to protected
  base. No provider-data, production authorization, executable shadow or
  command-owner path is introduced.

## Independent evidence verification

`verification.json` records exact committed retrieval of all 70 HG-047 envelopes
and all 9 selected commands with tested SHA, command and zero exit binding.
The complete reviewed evidence/review budget is 2,241,854 bytes across 176 files,
with no errors. The source at the reviewed result equals the tested source, the
result suffix is valid, and current authority hashes verify.

The new Linux ARM64 development run has 1,306 unique passing harness cases and
241 unique passing unit cases, with zero failures/errors/skips. Collection and
observed harness node IDs match, and all JUnit identities match those node IDs exactly (`raw-oracles.json`). All 11 worker-receipt artifact hashes and seven
host-observed command records verify. All 11 controller assets match both their
recorded installed Git revision and the tested candidate bytes. Recorded mounts
contain only the owned nested-daemon volume; container and volume cleanup are
true. The driver uses full_db=False/test_only=True and creates no App object,
reads no signer configuration/admission, and publishes nothing.

The initial RUNNING driver metadata matches its receipt hash, and the final PASS
metadata is separately preserved with the bookkeeping reconstruction note. It
is not substituted for any execution log, exit, JUnit or cleanup result.

The earlier App check for `8a78241e9b752247c3c4f4a43c4fe54bad72ef6c` remains
failure, with 1,304 passing harness cases and two error cases plus recorded
cleanup. It is not selected as new PASS evidence. The tested repair changes only
two parametrization `ids` lists: removing those two AST keywords yields the
identical prior fixture/assertion AST. The ten affected IDs are at most 105 bytes.

## Reviewer executions

- Focused decoder, installed-import, provenance and compact M3 regressions:
  289 passed, no failures/errors/skips; raw `focused.log` and `focused.xml`.
- Installed decoder copy and failed-start cleanup: 2 passed;
  raw `controller-copy.log` and `controller-copy.xml`.
- Independent committed proof audit: PASS; `verification.log` and `verification.json`.

`checks.json` retains the exact commands, environment, platform, counts and raw
file hashes. These are new review-created proofs. Earlier reports remain intact;
no implementation, result, or task evidence was edited by this reviewer.

## Limits and remaining gate

The final reviewed-head full database execution and successful App publication
remain NOT_RUN and mandatory under unchanged HG-046 policy. Fresh independent
GENERAL/PROTOCOL reviews, exact admission and the final trusted gate must still
complete before merge. The selected development gate omits PR review validation
and full DB by design; it is never represented here as that final gate.

This review relies on the documented trusted-project-code/operator model and
recorded isolated-run cleanup, not hostile-code sandboxing or remote attestation.
It does not grant product/release PASS or resolve unrelated prospective ordinary
JSON compatibility work. There is no new security finding requiring an
implementation revision.
