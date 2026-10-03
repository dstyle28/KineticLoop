# HG-051 approved historical storage mapping governance

Identity: harness-governance-v0.1/HG-051. Protected base:
b877db0edd2e4550d6ea81750656112fb7f2e223 (normally merged HG050).
The human explicitly approved the four-blob lossless current-tree representation
migration. This governance implements its prerequisite; it does not migrate KL080.
Exclusive reservation: harness_core and security_data_boundary, released by HG050.
KL080 retains its eight independent resources and draft blocked state. No messaging
other chats, installation/pins/admission, DB lifecycle, workflow, runtime or frozen edit.

Exact implementation write paths (no wildcard source/test authority):
- tools/harness/compact_evidence.py
- tools/harness/validate_harness.py
- HISTORICAL_EVIDENCE_MAPPING.schema.json
- docs/harness/EVIDENCE_STORAGE_POLICY.md
- docs/harness/HARNESS_GOVERNANCE_CONTRACT.md
- docs/harness/THREAD_RESULT_CONTRACT.md
- docs/harness/THREAD_REVIEW_CONTRACT.md
- docs/harness/MERGE_GATE.md
- docs/harness/M3_CLOSURE_CONTRACT.md
- tools/harness/README.md
- tests/harness/test_compact_evidence.py
- tests/harness/test_review_evidence_provenance.py
- tests/harness/test_validator.py
- tests/harness/test_m3_milestone_closure.py
- tests/harness/test_source_decision_scope.py
- docs/exec-plans/active/KL-080.md
- KineticLoop_Harness_Backlog_v0.2.json
- KineticLoop_Harness_Traceability_v0.3.json
- CURRENT_DOCUMENT_INDEX.json
- HARNESS_DOCUMENT_MANIFEST.json
- docs/exec-plans/governance/HG-051.yaml
- own docs/exec-plans/evidence/HG-051/** and reviews/HG-051/** only

Plan committed before implementation: index the exact new schema; admit exactly
one task-owned mapping at docs/exec-plans/evidence/KL-080/HISTORICAL_EVIDENCE_MAPPING.json
in a later normal forward KL080 commit, mapping only the four INVENTORY.json blobs.
Separate archival envelopes from gzip-v1 execution envelopes. Mapping binds original
path/revision/blob/raw hash/length and preserved result/review/provenance snapshots;
storage revision binds envelope/payload hashes/length. Immutable inventory authorizes
only those bytes. Unknown metadata remains null. Archival retrieval recovers bytes
without certifying execution/PASS; ordinary evidence read rejects archive objects,
encoded/wrapped/nested forms included. Original verification always requires the
regular original blob at its original commit and never substitutes HEAD/archive.
Preserve original ancestry, non-migrated bytes and all failed outcomes. Refine only
KL080 preservation wording with exact projections; no check/oracle/resource/dependency
changes. Migration must precede a new tested SHA: no historical overwrite in a
post-test or post-review bookkeeping suffix.

Enforce unchanged plain 256KiB / stored gzip 8MiB / recovered 64MiB / PR 16MiB limits,
including mapping, envelopes, payloads and review suffix; reject duplicates/orphans,
foreign/out-of-scope/deleted/rebound mappings, symlinks/traversal and unavailable
original revision. Demonstrate measured inventory retrieval in temporary Git fixtures
using existing blobs, never commit duplicate large raw/payload fixtures.

Checks: focused harness provenance/budget/M3/scope negatives; full kl test-harness;
kl test-unit; kl lint; kl typecheck; kl check-harness; committed original/inventory
roundtrip, authority/frozen/scope/budget audits. Capture real stdout/stderr/exit and
JUnit/collection when appropriate at committed tested SHA; preserve failures.
Fresh-context independent GENERAL, PROTOCOL, DB_CONCURRENCY and
SECURITY_DATA_BOUNDARY reviews bind implementation/governance/evidence SHA. Fix and
rereview findings; append only own linear REVIEW_RECORD_ONLY suffix after final PASS.
Create/attach one PR. Root owns trusted-validator installation/pins/admission,
final App/full-DB gate and normal merge. No KL080/M3/product/release closure claim.
