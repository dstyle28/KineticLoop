# HG-047 independent GENERAL review

Verdict: **PASS**. No BLOCKER, REQUIRED_FOLLOWUP or NONBLOCKING findings.
This is a fresh independent review of the complete protected-base diff and
retained proof; author self-review and historical compact reviews are not the
basis of this verdict.

- Identity: `harness-governance-v0.1/HG-047`, PR 91.
- Protected base: `391c9198fa8ec647e377a0572700bc7568468c85`.
- Tested implementation: `2dc15b7c79b835197449ca705f82f221eee6f05d`.
- Reviewed implementation/result: `47de76d206df89124ffe41c59b0b983af4defc97`.

All ordinary references below bind to the reviewed SHA. This report is
review-created bookkeeping and must be committed through the contract's own-task
linear REVIEW_RECORD_ONLY suffix.

The authority index, governance record and SCOPE.md define a prospective storage
change. I inspected the complete 59-path diff, relevant result/review/governance,
M3 and merge contracts, and merged prerequisite HG-045/HG-046 governance records.
Independent Git checks confirmed the exact files_changed set, base-to-tested-to-
reviewed ancestry, and the single post-test result/new-evidence-only suffix.
Existing evidence is neither overwritten nor deleted in that suffix. All current
indexed authority hashes match their committed bytes. Frozen authorities/baseline,
requirements, task projections, runtime, migrations, DB tests, workflows and the
DB classifier are unchanged. Merged HG-045/HG-046 governance, evidence and reviews
are byte-preserved; the earlier compact HG-046 identity remains historical.

The reader resolves one commit for envelope and payload, requires regular blobs,
checks lengths and hashes, and bounds single-member gzip recovery. Metadata
constraints are part of successful evidence validation. Plain historical bytes
remain readable, while reserved malformed/wrapped/renamed or conflicting-encoding
storage records fail closed. M3 semantic checks inspect recovered stdout, JUnit,
collection and collection stdout with existing outer identities and command
bindings. Budgets cover changed evidence and review artifacts, including review
suffixes, without accepting summaries as proof.

The cache stores only successful immutable verdicts, keyed by canonical repository,
full commit, path and tested/command/exit constraints. Its 4096-entry bound retains
no raw log buffers. Nested validation operations share it; final cleanup resets it
after success or exception. Mutable refs, working files and failures reread; a
later operation detects missing/corrupt objects. Git-object immutability within one
operation is explicit. The installed decoder is pinned as an asset and copied
beside the trusted worker validator; the two controller additions do not weaken
policy, installation admission or credential separation.

Actual independent verification:

- Independently recovered all 16 retained HG-047 envelopes at the reviewed SHA.
  For the eight selected checks, compared gzip recovery and decoder output, raw
  and stored hashes/lengths, tested SHA, exact command, exit code, execution
  metadata and counts. Raw harness proof reports **1271 passed**; raw unit proof
  reports **241 passed**. Lint, typecheck (166 source files), authority, scope,
  diff hygiene and benchmark outputs support their selected PASS records.
- Inspected the committed benchmark: five reads use 25 to 3 Git calls for each
  plain case and 55 to 7 for compact proof. This is a bounded microbenchmark,
  not a claim about complete gate duration.
- Ran the focused command below: **207 passed, 37 deselected in 67.28s**, exit 0.
  It exercises the compact reader/writer, encodings, budgets, provenance, cache
  bounds/freshness/exception cleanup and installed decoder negatives.
- Ran `git diff --check` for the exact protected base and reviewed SHA: exit 0.
  Invoked suffix validators and the compact budget audit directly: no errors;
  **40 changed evidence files, 41,195 stored bytes** at the reviewed SHA.
  The unchanged classifier independently returns `full_database_required=True`.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /private/tmp/hg044-venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/private/tmp/hg047-general-pytest tests/harness/test_compact_evidence.py tests/harness/test_local_gate.py -k 'compact or decoder or validation_session or validation_cache or new_validation_operation'
```

No duplicate full harness, unit or database execution was performed for this
review. Full DB, the final exact reviewed-head trusted App/controller gate and
applicable quality/merge checks remain mandatory before merge. Administrator
installation of the independently reviewed controller/validator/decoder release,
complete pins and new exact-head/controller admission is still required. This
review changes no installation, configuration, credentials or admission. It does
not assert merge, M3, product/release, production activation or executable shadow
PASS.

Bound evidence: `docs/exec-plans/governance/HG-047.yaml`,
`docs/exec-plans/evidence/HG-047/SCOPE.md`, and
`docs/exec-plans/evidence/HG-047/selected-2dc15b7/` (execution.json plus all eight
selected command envelopes). Relevant contracts are resolved by
`CURRENT_DOCUMENT_INDEX.json` at the reviewed SHA, especially
`docs/harness/EVIDENCE_STORAGE_POLICY.md`, `THREAD_REVIEW_CONTRACT.md`,
`HARNESS_GOVERNANCE_CONTRACT.md`, `M3_CLOSURE_CONTRACT.md` and `LOCAL_DB_CI.md`.
