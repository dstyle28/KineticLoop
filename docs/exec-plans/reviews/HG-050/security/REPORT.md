# HG-050 independent security review

Verdict: PASS, with no BLOCKER, REQUIRED_FOLLOWUP or NONBLOCKING findings.
Identity: `harness-governance-v0.1/HG-050`. Reviewed implementation/governance/evidence
SHA: `26482f7f7147fe33cf37d8028574196c97c82ec6`. Protected base:
`034d6301316d0dade784a61b159c027b83fbce3a`. Implementer tested SHA:
`f302b22c0838ef2928913392e7c2a6af9e8f8698`.

Applied the repository `pr-merge-reviewer` skill and independently inspected
AGENTS.md, CURRENT_DOCUMENT_INDEX.json, HG-050 governance/SCOPE, the current
governance, review v0.2, evidence storage and local DB CI contracts, the exact
base-to-reviewed diff, unchanged controller and reviewed raw execution evidence.
HG-050 is a governance change with no active task packet or packet refinements.

The client retains installation tokens only in process memory. Its sanitized
typed HTTP status errors omit response body, headers, JWT and token in displayed
diagnostics; URL/timeout failures are sanitized. API origin, forbidden redirects,
empty proxy configuration, 60-second HTTP timeout and signing path are unchanged.
Each generation clears the previous credential before JWT/installation/mint work,
rechecks configured installation/App/owner/selected-repository and exact permissions,
and requests only the configured repository ID. Failed renewal cannot reuse the
previous token. Timezone-aware zero-offset server expiry, a strict 60-second
margin, pre-JWT monotonic age cap and mint-end validation protect freshness;
observed rollback invalidates the cache. Forward wall jumps still expire a token
when monotonic time stalls. The documented observation limit is accurate.

Only an installation-token GET receiving a typed HTTP 401 receives one renewal
and one identical retry. The direct installation-validation/mint API calls cannot
recurse. Repeated 401 invalidates the new generation; POST/PATCH, 403, other HTTP
status, redirect and transport failures do not replay. A separate controller
failure PATCH can proactively acquire credentials without converting a failed run
to success. No controller, classifier, dependency, workflow, runtime, historical,
frozen, requirement, installation, admission or signing authority changed.
The validator diff is limited to HG-050's exact scope and mandatory specialist.

Independent execution: the existing focused suite passed all 102 cases with
synthetic credentials. Eight additional reviewer probes passed: JWT and
installation-validation latency count against the pre-mint cap; wall and monotonic
rollback during mint reject the generation; real App plus fake API rejects wrong
admission and start-check identity before worker execution, rejects completion
response identity without a published-check record, and fails closed on repeated
401 during the final publication snapshot. Existing real-App tests cover renewed
snapshots, check 21, cleanup, stale head/base, failed renewal, repeated 401, PATCH
401 and test-only no writes. Existing sentinel assertions and reviewer artifact
checks confirm credentials do not enter receipt/diagnostic outputs. These are
deterministic boundary probes, with worker execution stubbed and no live network.

The read-only audit verifies all 81 declared paths and tested-to-reviewed scope,
byte identity of implementation/tests/contracts at both SHAs, ancestry and 30
exact-revision compact envelopes with hashes/lengths and task command bindings.
Final whole-harness raw proof has 1,405 matching serial/worker/start/call/JUnit
cases, 4,215 passed setup/call/teardown reports, no skips/failures and successful
wrapper completion. Implementer focused 102 and unit 241 PASS logs, authority,
lint, typecheck, scope, diff and recovery probe evidence remain SHA-bound.
The initial wrapper failure (`source-changed-during-execution`, despite 1,405 pytest
passes) and the retry fixture failure (1,404 passes, one failure) remain separately
preserved failed executions. Only the final clean run supplies harness PASS.

Reviewer audit initially used an incorrect expected unit count of 166. It failed
after the evidence and harness assertions; inspection of the original unit log
established 241. The corrected audit passed. Both reviewer logs are retained in
compact form; this correction changes no implementation evidence or verdict oracle.

Review-created probes/logs are bookkeeping under this review directory, requiring
the parent's exact linear REVIEW_RECORD_ONLY commit. They do not replace pre-review
task evidence. Product, M3, release, real full DB and installed-controller gates
remain NOT_RUN here. The root owns the separately reviewed installation, exact
pins/admission and final stable-head App gate; this review supplies no publication
authority or retrospective correction of historical failures.
