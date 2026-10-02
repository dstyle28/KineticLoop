# HG044 independent PROTOCOL review

Reviewed implementation/result SHA: `351f0eda41ad492e66115f9ea1e41e3e0f9abf3d`.
Protected base: `9268fc8dd8c071c02dc5c698274dbf6fcd112776`.
Selected task-check SHA: `e748b37ec92e119190afad87478b7ecb951e5b5d`.

Recommendation: **CHANGES_REQUIRED**, one BLOCKER. No frozen semantic amendment is
needed. All review writes are confined to this review record and PROTOCOL-raw.
No application edits, DB lifecycle, foreign fixture namespace, commit, push, PR,
or external app messaging was performed.

## BLOCKER: retained regression can omit a requested selector

`m3_execution_evidence_errors` checks that each collected node belongs to any
requested selector, and compares executed JUnit cases with that recorded
collection. It never checks the converse: each requested selector must be
represented. An exact multi-file command/collection command, with correctly
hashed regular Git blobs, can therefore carry a positive one-case raw collection,
stdout and JUnit for only the first requested file and return no errors.

The standalone read-only validator reproduction in
`omitted-selector-reproduction.json` confirms this for both combined regression
commands, including the KL029 shadow unit/DB suite with **zero DB shadow cases**.
It uses a separate temporary synthetic Git repository; these records are validator
input, never project evidence. The existing positive test fixture likewise chooses
`command.split()[0]` for combined suites (test lines 51–63).

This fails `M3_CLOSURE_CONTRACT.md`'s full integrated regression requirement:
"selectors cannot be replaced or omitted". The intended protocol exit still
requires fresh integrated shadow boundary evidence; mutually agreeing truncated
collection/JUnit cannot establish a complete suite. Require nonempty exact
collected/executed coverage for each selector and add a negative test with one
selector omitted while preserving hashes, fresh ancestry, commands, counts and
matching JUnit. Correct the positive synthetic fixture to represent both paths.
Rerun required checks on the repaired SHA and obtain fresh reviews.

## Independently confirmed scope and protocol facts

The authority index, governance record, current M3 plan/HG042 addendum, new M3
closure contract, review/result/merge contracts, current requirement set and
Acceptance/Release Gates were read directly. Frozen Protocol §§0.3a, 2.1a,
5.3/5.3a, 5.4/5.5, 7.4 and final freeze restrictions, plus DB S42–S47 and
§§4–5 establish registry commit/fresh-read, lock order, immutable validity/history,
current execution eligibility, isolated evaluation and disabled production.

`audit.json` independently verifies all 52 mapped task-check contracts, exact
commands and canonical oracle digests. Available merged checks bind to their
actual result/tested SHA/raw Git blobs; KL028/KL029 remain prospective and absent.
The mappings require full KL027 F/D/N T6/T7 trajectory/repair, lifecycle-valid
current revoke/expiry and CONTINUE/RESUME denials with immutable START/replay,
all nine actual KL026 DC races with separate PU equality, KL023/028 barriers,
KL028 relevant/unrelated/rollback/closure/validity/TIMELESS checks and all six
KL029 named boundary checks. No M3→M4 or KL029→KL045 dependency is introduced.

The unchanged KL028 ledger retains 31 B-layer dispositions: 19 prospective
executable rows and 12 deferred rows, including B04 full DC despite mandatory
guard support, eight E2E layers, B11/B12 PU and B14 WF. I04 WF, shadow usability
and R04 E2E remain NOT_RUN; exact schema/row comparison prevents promotion or
reach/layer relabelling. Product aggregate claims remain empty, production false,
shadow non-executable and historical model evidence unreproduced. HG044 creates
no actual M3 closure or task/integration status changes.

Every frozen file matches its baseline hash and base bytes. M1/M2 schema branches
and ten existing validator functions, including HG043 integration/review-evidence
guards, are byte-identical. The plan prefix and own governance scope hold. The
selected tested→reviewed suffix validates as new own evidence/governance only.

All seven selected committed captures match their record/raw SHA256 and byte
counts. Raw output independently confirms 79 focused, 869 harness and 232 unit
passes, lint/typecheck success and HARNESS_CHECK_PASS. These successful checks do
not close the omitted-selector blocker. An additional focused pure/Git execution
passed 18 checks (61 intentionally unselected); that reviewer run is distinct from
full task acceptance and contains no DB lifecycle. `audit.json`'s PASS describes
the named audit checks only; the review recommendation is CHANGES_REQUIRED.
