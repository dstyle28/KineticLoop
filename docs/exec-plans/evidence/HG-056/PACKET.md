# HG056 — prospective storage classifier compatibility correction

Identity `harness-governance-v0.1/HG-056`; one fresh chat/worktree/`codex/` branch/PR.
Protected base B: `3ec7f7a38d974256a928c3687f63e4d90019e42b` (root may approve a newer
normal descendant after rechecking entry). HG054/HG055 and historical records stay
merged inputs. This packet is a proposal, not PASS.

**Defect/goal.** `envelope()` scans quoted reserved names anywhere in bytes, then
JSON-parses the entire input. The original KL036 reader's
`envelope.get("kineticloop_evidence")` at line35 triggers `evidence-envelope-json`.
Global changed-blob classification through `reencoding_record()` aborts the history
audit at that ordinary helper. Independently reproduced on exact current head below;
only the inherited HG054 collection map was reached before failure. Correct the
content/structure distinction between ordinary field references and actual storage
records with the smallest conservative change. No evidence-platform expansion.

**Original positive oracle.** Preserve/read, never execute or edit, regular Git blob:
`f93364d90aaae9b0b62706fd4e4fe395a8cd8ec5:docs/exec-plans/reviews/KL-036/SECURITY_DATA_BOUNDARY/audit.py`,
mode100644, blob `cde206aee1eb240862863069104ad291ff98dedb`, 8063B, SHA256
`a602ee684cdd7b4d8169388d2a2fe821fc6bc5beadf0d69a593c2ed260ffe382`.
A byte-exact task-owned fixture is allowed under HG056 evidence; its pins are a test
oracle, never a runtime allowlist.

**Authority/resources.** Read AGENTS.md, CURRENT_DOCUMENT_INDEX.json, matching
repository task-thread-runner skill, EVIDENCE_STORAGE_POLICY,
HARNESS_GOVERNANCE_CONTRACT, THREAD_REVIEW_CONTRACT, HARNESS_CHANGE.schema.json,
merged HG054/HG055 records and relevant decoder/history/suffix/reader tests. Root
owns resource grant, installer/admission/App/merge. Reserve consistently:
`harness_governance`, `harness_validator`, `evidence_storage`,
`trusted_local_ci_controller`. No KL036 resources or DB executor.

**Exact write_paths** (literal HG056 validator allowlist must match):

- `tools/harness/compact_evidence.py`
- `tools/harness/validate_harness.py`
- `tests/harness/test_compact_evidence.py`
- `tests/harness/test_review_evidence_provenance.py`
- `tests/harness/test_m3_milestone_closure.py`
- `tests/harness/test_validator.py`
- `tests/harness/test_local_gate.py`
- `docs/harness/EVIDENCE_STORAGE_POLICY.md`
- `docs/harness/HARNESS_GOVERNANCE_CONTRACT.md`
- `CURRENT_DOCUMENT_INDEX.json` (required derived hashes only)
- `HARNESS_DOCUMENT_MANIFEST.json` (own delivery rows/required derived hashes only)
- `docs/exec-plans/governance/HG-056.yaml`
- `docs/exec-plans/evidence/HG-056/**`
- `docs/exec-plans/reviews/HG-056/**`

Only needed classifier integration tests may change; unneeded paths need not change.
Validator edits: exact HG056 scope/review enforcement plus necessary classifier
integration. No scope widening for earlier IDs, codec/budget/schema changes, runtime,
auth/admission/DB/frozen edits, backlog/requirement changes, KL036/KL080 paths,
historical rewrite, CI/installer/config changes or credential access. No network
inside fixtures, helpers or compatibility audits. Normal GitHub publication, PR
creation/attachment and hosted CI inspection are authorized through ordinary
approvals; respect any actual refusal and do not use alternate routes.
All inherited/retained/source/base/ancestry/per-edge/foreign/archival guards retain
meaning. Policy clarifies ordinary-source compatibility while preserving rejection
of actual reserved objects; no suffix/path/hash/owner exemption or blanket Python
trust, no execution of input, no decoder-error swallowing.

**Acceptance/check oracles.**

1. Exact original above returns `None` from `envelope` and `reencoding_record`;
   bound ordinary `read` returns byte-identical content. Ordinary get/subscript
   reader literals, quoted prose and JSON string values remain plain across owners,
   arbitrary suffixes and plain/gzip/xz recovery. Plain classification grants no PASS.
2. Actual reserved metadata fails closed in valid Python assignment/dict/string or
   other source/prose/comment-like wrappers, even when input parses as Python.
   Keep malformed/broken/truncated JSON, encoded/escaped/removed markers, signature
   fields, duplicate keys, UTF8/16/32/BOM conflicts, list/object wrapping, nested
   recovery, fake archival/mapping records and renamed `.py/.json/.txt/.log/.gz/.xz`
   or arbitrary suffix cases. Mix real malformed records with harmless reader
   references. All existing format-negative suites remain mandatory; no mocked or
   filtered verdicts. Reject actual metadata before execution oracles regardless
   owner, rename or prefix; decoded reserved content is never nested evidence.
3. Isolated Git history fixtures carry the original helper while own/inherited maps
   validate; all existing inherited/no-change/foreign/pre-admission transient
   deletion-restoration, source-unavailable, retained-base and late/reversed-parent
   admission negatives still fail. Readers/M3/availability/suffixes/installed-only
   fixtures share classification; actual conversions never become REVIEW_RECORD_ONLY.
4. Mandatory complete **actual read-only** candidate `reencoding_audit` and storage
   `audit` on immutable KL036 head H=`1fee7a4ef9ecb484da24522962a6df4d4c2bd9b9` and B.
   Read exact owner Git objects; output only bounded metadata to task scratch under
   `/private/tmp`, no KL036 edits/helper execution/private quarantined logs/DB/network.
   Prove all inherited HG054 and selected KL036 maps reached/validated and original
   helper pins unchanged. Empty errors alone are insufficient without map inventory.
   Report every real error; incomplete/remaining-error audit stays BLOCKED. This
   compatibility oracle is not KL036 full16/App/task PASS or published admission.

**Required immutable checks.** Record exact commands/interpreter/env and real
collected/executed identities, exits and failures, once per final implementation:

- `uv run pytest tests/harness/test_compact_evidence.py -q`
- `uv run pytest tests/harness/test_review_evidence_provenance.py tests/harness/test_m3_milestone_closure.py tests/harness/test_validator.py -q`
- `uv run pytest tests/harness/test_local_gate.py -q` (uncredentialed isolated fixture)
- `uv run python docs/exec-plans/evidence/HG-056/verify_compatibility.py` (exact-original + complete actual H/B audit)
- `uv run python docs/exec-plans/evidence/HG-056/verify_scope.py --base <B>`
- `uv run kl test-unit -q`; `uv run kl test-harness --workers 2 --evidence-dir <unique-scratch> -q`
- `uv run kl lint`; `uv run kl typecheck`; `uv run kl check-harness`
- `git diff --check <B> <T>`
- final `python tools/harness/compact_evidence.py audit --base <B> --head <R> --identity HG-056`
- final `uv run kl check-harness --ci-pr-base <B> --ci-pr-head <R>`

If uv is absent, use established Python3.12 `python -m pytest`,
`python -m kineticloop.cli` and Python with explicit candidate PYTHONPATH, recording
absolute interpreter and any already-approved isolated xdist/execnet dependency path.
No shim/new platform work. Prepare scripts/fixtures before T; capture losslessly in
own evidence under unchanged budgets. Failures/interruptions stay actual failures or
NOT_RUN; no copied bulk logs/full diffs/truncation or status relabeling. After final
checks pass, repeat only for new changes/failures/unresolved concerns. Root owns
existing trusted fullDB/App runtime after reviews/hosted CI; no duplicate DB gate.

**Result/reviews.** Commit one existing-schema governance HG056.yaml with B/T,
exact files/checks/evidence and no frozen impact; no KL task RESULT. Commit result
and task evidence before fresh SHA-bound **GENERAL + SECURITY_DATA_BOUNDARY** reviews
and enforce both for HG056 in validator/current governance contract. SECURITY tests
metadata-smuggling/source-looking bypass/retention; GENERAL covers compatibility and
scope. DB_CONCURRENCY/PROTOCOL are not required for this storage-only correction;
no corresponding runtime/frozen risk surface is authorized. Stop for separately
approved scope/ADR if that changes. Review suffix is linear own REVIEW_RECORD_ONLY.

**Completion/boundaries.** Pinned decoder/validator assets require root-owned reviewed
complete installation and exact controller admission, final exact-head App/hosted
checks and normal merge. Implementation cannot activate/install itself or access
signing credentials. Later root-authorized KL036 adoption is a normal forward merge
with fresh checks/result/reviews; earlier records remain historical. No requirement,
release or production/shadow PASS follows from HG056. No genuine frozen spec conflict
was found: current policy already preserves actual non-envelope bytes and rejects
actual storage objects. If clearing the helper requires accepting actual metadata or
weakening binding/ancestry/authorization, return BLOCKED or SPEC_CHANGE_REQUIRED.
