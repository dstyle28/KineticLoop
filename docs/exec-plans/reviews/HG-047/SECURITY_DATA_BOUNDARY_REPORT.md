# HG-047 fresh SECURITY_DATA_BOUNDARY review

Verdict: PASS. No BLOCKER, REQUIRED_FOLLOWUP, or NONBLOCKING findings in the reviewed security/data-boundary scope.

Reviewed result revision: `b7370940c8b9165f471322baaeef7d9e250dfac6`.
Protected base: `391c9198fa8ec647e377a0572700bc7568468c85`.
Tested implementation: `536c9b7b7c5bfa9b36a0b38e513bce34ed6eb31d`.
Identity: `harness-governance-v0.1/HG-047`; PR 91.

This is a new independent review of the complete protected-base diff and committed evidence. The earlier canonical security review at `47de76d206df89124ffe41c59b0b983af4defc97` is stale for this implementation; its original record remains available in Git history. The applicable authorities were resolved through CURRENT_DOCUMENT_INDEX.json. The review used AGENTS.md, the pr-merge-reviewer skill, HG-047 governance and SCOPE, THREAD_REVIEW_CONTRACT, EVIDENCE_STORAGE_POLICY, LOCAL_DB_CI, and the merged HG-045/HG-046 results and their preserved boundaries.

## Prior P-01 correction

The four-line change in `tools/harness/compact_evidence.py:207` invokes the existing reserved-storage classifier on the fully recovered bytes, after stored/raw integrity and bounded gzip validation, before returning bytes to evidence oracles. A valid outer envelope therefore cannot turn an inner missing/corrupt/misbound envelope into plain stdout. Top-level reserved storage produces `evidence-nested-envelope`; wrapped storage or malformed reserved encodings propagate their rejection. The code never recursively decodes inner storage. Actual nonreserved output remains byte-identical, including UTF-8/16/32 bytes.

The new cases comprise 24 encoded/mutated direct-and-outer negatives, one valid-nested/capture-cleanup case, three nonreserved lossless cases, and seven full M3 cases: exactly 35. The full M3 cases verify the rejected inner and outer forms and the explicit storage rejection reason, excluding accidental failure on stale revision provenance. They cover missing/corrupt inner payloads, command/tested/exit mismatches, and list/object wrappers. This closes the earlier bypass for the reviewed SHA.

## Security and data boundaries inspected

- `compact_evidence.py:103,153`: reserved content is recognized independently of extension, with escaped keys, BOM/endian variants, malformed UTF-8/16/32, missing markers with storage fields, duplicate keys, and wrapped shapes rejected. Recognition is applied again after decompression. Metadata test counts and timestamps cannot supply the raw execution oracle.
- `compact_evidence.py:39,61,153`: bound revisions resolve once; envelope and payload are regular Git blobs at that same commit. Paths reject traversal, empty/dot components, absolute paths, backslashes and NULs; same-directory content-addressed payload naming enforces ownership. Missing, directory and symlink entries cannot borrow bytes from ambient HEAD or a later commit. Stored bytes/hash are checked before single-member gzip recovery; raw length/hash and the 64 MiB bound are checked afterward. Truncation, extra members, trailing data, and expansion beyond the declared bound fail.
- `compact_evidence.py:214,265`: capture retains exact bytes and refuses overwrite/symlink targets; unsuccessful reserved-output capture removes its newly created evidence files. The prospective audit includes changed owned review/evidence blobs, enforces individual and total budgets, and rejects orphan payloads, duplicate bulk, embedded raw copies and full diff dumps. Existing untouched historical artifacts retain their prior representation.
- `validate_harness.py:1773,1785`: the at-most-4096-entry cache holds only successful complete proof verdicts, keyed by canonical repository, exact immutable commit, path and tested/command/exit constraints. It stores no raw logs. Failures, working files and symbolic refs are not cached; nested validation shares one scope and cleanup resets the context on success or exception. A later validation rereads Git objects and detects loss/corruption. Immutability within a single validation operation remains the documented premise.
- `validate_harness.py:2677,2734`: M3 still binds outer blob hashes, exact revisions, task ownership, tested revision and commands. Stdout, JUnit, collection JSON and collection stdout all use the decoder before existing counts, selector/node-ID, skip/failure and collection checks. Review-created evidence still requires the strict own-task linear suffix; an existing invalid reviewed-revision reference cannot be repaired through that exception.
- `local_gate.py:38,49,211`: the decoder is a required pinned ASSET and is copied from the installed release into `/gate/tools/harness/`. Validator import is anchored to its own installed file location, before the candidate root is passed to validation. Missing/altered/symlinked installed bytes fail installation checks; no candidate decoder import fallback exists. The credential, admission, App permission, isolation, command ownership and publication paths are unchanged.

## Independent verification

All commands ran from the assigned worktree with `PYTHONDONTWRITEBYTECODE=1`, without DB execution or live controller changes. Source/test bytes matched the reviewed Git blobs, and the tested-to-reviewed suffix changes no implementation or tests.

1. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /private/tmp/hg044-venv/bin/python -m pytest -q -p no:cacheprovider tests/harness/test_compact_evidence.py tests/harness/test_local_gate.py::test_installed_compact_decoder_is_required_and_exact tests/harness/test_local_gate.py::test_isolated_validator_never_uses_candidate_compact_decoder tests/harness/test_local_gate.py::test_worker_copies_decoder_from_installed_release` — 235 passed; exit 0.
2. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /private/tmp/hg044-venv/bin/python -m pytest -q -p no:cacheprovider tests/harness/test_m3_milestone_closure.py::test_compact_nested_storage_cannot_supply_m3_execution_stdout` — 7 passed; exit 0.
3. Collection of the four new test functions — exactly 35 cases; exit 0. All 35 were executed across checks 1 and 2.
4. Independent standard-library gzip/SHA256 recovery, with no candidate decoder import — all 36 committed HG-047 envelopes recovered and checked against their recorded stored/raw hashes and lengths. All eight selected checks match the result and execution record's exact tested revision, command and exit. Recovered logs confirm 1,306 harness tests and 241 unit tests passing, lint/typecheck success, and HARNESS_CHECK_PASS. This verifies the committed full-suite evidence; the review did not rerun those complete suites.
5. Exact reviewed-revision budget audit — 90 changed evidence/review blobs, 106,313 stored bytes, no errors; exit 0. Protected-base `git diff --check` also exited 0.
6. Independent protected-path comparison — no change to frozen Protocol/DB/baseline, runtime, migrations, DB tests, requirement statuses, source-decision authorities, workflows/classifier, HG-045/HG-046 governance/evidence/reviews, or credential/worker infrastructure outside the two declared decoder asset/copy additions.

Raw independent review evidence is in `docs/exec-plans/reviews/HG-047/security_round2/`: `decoder-security.log`, `m3-regression.log`, `new-cases-collection.log`, `verification.log`, and `budget.log`. These paths are new at the reviewed SHA and bind only through the contract's REVIEW_RECORD_ONLY suffix. They are review evidence, not pre-review task checks. The current review JSON intentionally cites raw proof paths rather than source files whose reserved-storage literals are not admissible execution evidence.

Independent recovery also verified preserved failure output: development-070f94f harness exit 2, development-166bf3e unit exit 1, and development-b30a9c6 authority exit 1. None is selected as the fresh passing proof.

## Remaining operational gates

This PASS is the specialist review verdict only. Full DB is NOT_RUN locally. The final reviewed-head trusted controller/full-DB gate, quality checks and SHA-bound merge checks remain required. Administrator installation of the independently reviewed controller/validator/decoder with the complete new pins and exact final-head/controller admission is still pending and is outside this review's write scope. This review grants no installation, App publication, merge, M3, product requirement, release, production activation, or executable-shadow PASS.
