# HG-047 GENERAL independent review, round 3

Reviewed implementation/result: `589e538579f519bc10d178fa02dff12332931ba7`.
Protected base: `391c9198fa8ec647e377a0572700bc7568468c85`.
Selected tested source: `f29ffa97d9057eacc4bda7ad593b843c9c52c5a2`.
Verdict: **PASS** for GENERAL implementation review. Findings: **0 BLOCKER,
0 REQUIRED_FOLLOWUP, 1 NONBLOCKING**. This is not a merge recommendation or a
claim that the mandatory final reviewed-head App/full-database gate has passed.

This fresh-context review read the repository guide, current authority index,
review skill, HG-047 governance record/SCOPE, storage policy, result/review,
governance, merge, M3 and local CI contracts. I inspected the complete changed
implementation, tests, contracts, derived inventories and evidence bindings.
Implementation self-reviews and old reviewer verdicts were not the basis for PASS.
No implementation, result or selected task evidence was changed.

## Independent verification

`verification.json` records the assertions performed by `verify.py`; the command
was `PYTHONDONTWRITEBYTECODE=1 /private/tmp/hg044-venv/bin/python
/private/tmp/hg047-r3-general/verify.py` from the supplied worktree. The script
reads exact Git blobs at the reviewed SHA, independently uses standard gzip and
SHA256, and then compares the production decoder's returned bytes. It verifies:

- All **70** added compact captures reproduce their exact stored/raw hashes and
  lengths, preserve same-directory content addressing, and bind ancestor tested
  commits. The **9** selected checks match the record's exact command, zero exit
  status and tested SHA.
- The **1,306** harness cases match unique host collection, worker observed
  execution and JUnit case names, preserving parameter text containing `::` and
  class-qualified names. Harness and **241** unit JUnit cases have no failure,
  error or skip; counts agree with recovered raw logs. Worker receipt hashes and
  lengths bind the raw artifacts and actual argv. This verifies recorded Linux
  ARM64 development evidence, not a newly executed Linux gate by this reviewer.
- All **11** installed release assets match their exact reviewed-release Git
  hashes and the current reviewed source. The development receipt explicitly
  records test-only execution, no App publication and no full database run.
  Container and volume cleanup succeeded.
- The E2BIG correction consists of only two explicit pytest ID lists. Removing
  those ID keywords from the AST leaves fixture data, cases, bodies and assertions
  identical to `8a78241`. All **10** affected node IDs remain collected, with a
  maximum **105 bytes**. Preserved prior raw logs/JUnit still report **1,304
  passes and 2 errors**, and their worker receipt remains FAIL.
- All **195** changed paths exactly match the declared governance files and
  authorized scope. Source at tested and reviewed revisions is equal; the tested
  suffix is valid. Frozen files, runtime, migrations, DB tests, requirements,
  workflows/classifier and merged HG-045/HG-046 artifacts are unchanged.
  Current inventory metadata is unchanged apart from permitted hashes/lengths;
  all indexed hashes and lengths verify against Git bytes.
- The prospective audit at the reviewed SHA passes: **176** evidence/review files,
  **2,241,854 stored bytes**, zero errors. This excludes these new reviewer files
  until the coordinator commits and audits the review suffix. Diff hygiene passes.
  The unchanged classifier still requires final full database execution.

Focused reviewer execution command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /private/tmp/hg044-venv/bin/python -m pytest -q tests/harness/test_compact_evidence.py tests/harness/test_local_gate.py tests/harness/test_m3_milestone_closure.py tests/harness/test_review_evidence_provenance.py tests/harness/test_validator.py -k 'compact or evidence or validation_session or budget or new_validation_operation or installed or worker_copies or regression_decodes' -p no:cacheprovider
```

Result: **307 passed, 263 deselected in 568.49s**, exit 0, recorded in
`focused.log`. Deselection is limited to the declared focused reviewer selection;
the recorded development run above executed the full harness and unit suites.

## Behavior and authority assessment

The decoder resolves a bound revision once, requires regular same-revision blobs,
checks owner/path/content addressing and ancestry, verifies stored bytes before
bounded single-member decompression, and verifies recovered bytes before return.
Decoded reserved nested/wrapped/malformed storage is rejected before M3 raw
oracles. Storage metadata cannot substitute for the compressed execution output.
M3 still checks log dispositions, JUnit, collection, node IDs, selectors and exact
command/tested bindings. Existing raw bytes remain the semantic source.

The immutable success-verdict cache keys repository, full commit, path, tested
SHA, command and exit constraint. It is bounded, operation-local, nested only
within the active operation, and cleared on exception/exit. Mutable refs,
working files and failures are not cached. The focused negatives cover corruption,
missing objects, owner/repository changes, constraint changes and next-operation
freshness. The documented immutable-Git-object assumption remains explicit.

The trusted controller changes only the pinned asset list and installed worker
copy list. Decoder imports are anchored to the installed validator location;
missing/tampered/symlinked installed assets fail closed. Candidate decoder fallback
is not introduced. Production activation, executable shadow, command ownership,
frozen safety locks and transaction boundaries are unaffected.

## G-01 — NONBLOCKING, independently reproduced

At `tools/harness/compact_evidence.py:129`, the object-pairs hook applies duplicate
key rejection before deciding whether an object represents reserved storage.
An ordinary duplicate-key object with literal text remains plain on read, whereas
the same nonreserved object with Unicode-escaped text raises
`evidence-duplicate-key`. `verification.json` records both probe results.
This is a narrow availability/compatibility limitation and warrants a prospective
correction with literal/escaped parity tests. It rejects evidence and cannot grant
a false PASS, alter accepted bytes, bypass provenance or affect the selected
checks. The reviewed result already records this limitation. It is not a blocker
for the isolated Linux ID correction or this storage review.

## Remaining gate and review evidence binding

The final full database/App gate is **NOT_RUN** for this reviewed source and is
still mandatory. All required independent reviews must bind this exact SHA,
followed by a valid review-record-only suffix and root-coordinated final gate.
No M3 closure, product/release PASS, production activation or merge is asserted.

This round uses new `general_round3/` evidence paths verified absent at the
reviewed SHA, so prior report content cannot shadow them. The coordinator must
commit these paths with only own HG-047 review bookkeeping and mechanically prove
the linear REVIEW_RECORD_ONLY suffix. Earlier reports remain untouched. The
canonical GENERAL record is updated to this reviewed SHA; no commit or push was
performed by this reviewer.
