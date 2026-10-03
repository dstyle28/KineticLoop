# KL-080 independent SECURITY_DATA_BOUNDARY review

Reviewed implementation/result SHA: `7e19587458d611155051d0c89d36e0b89f98b8a1`.
Protected base: `fc8a044ffa4d15a74ce5dc59298ae411f1f4009b`.
Tested implementation: `15a7167e44b8044c94688cf7e367e2d02a962e31`.
Status: **CHANGES_REQUIRED**. Recommendation: **DO NOT MERGE**.

The packet DoD is unsatisfied: the required legacy positive execution fails in both
its named selector and the full own suite, and the committed hosted full DB record
is still pending. The result truthfully records BLOCKED/FAIL/UNMERGED. Neither a
task PASS nor product, release, M3 or merge PASS is justified. The two BLOCKER
findings in SECURITY_DATA_BOUNDARY.json concern these completion gates. The
observed legacy rejection is fail-closed; it is not evidence of an authority bypass.

This review independently read the packet, indexed relevant frozen clauses,
Integration/Acceptance boundaries, HG045 diagnosis/feasibility, M3 contract and the
ten named prerequisite result artifacts. Exact Git diff and committed raw evidence
were inspected without consulting other current KL080 review conclusions. The 34
entry prerequisite result hashes match committed blobs, and their recorded merge
commits precede the protected base. Prerequisite historical PASS remains context.

The runtime diff is narrowly limited to canonical physical source values and the
shared internal read helper: S13 ELIGIBLE and S12 MATCHED are required, without
aliases, migrations, runtime/wire/rule changes or public authority creation. Existing
same-subject joins, policy, provenance, command_authority=NONE, immutable hashes,
membership and actual-vs-target guards remain. The pure resolver still separates
deduplication, contradiction/retraction, coverage and finite expiry; S27 ADMITTED
and derived S36 CONFIRMED keep their distinct meanings. Provider ingestion,
credentials, consent, exports, AI context exposure, retention and redaction owners
are untouched. New raw evidence contains synthetic fixture data and identities;
no new real-data export or provider capability surface was found in this diff.

Full T6 still reconstructs genuine preparation outputs before exact admission
freshness. The shared helper is a parameterized read with exact subject/ID/policy
and ELIGIBLE predicate; it writes nothing and grants no authority. The canonical
positive captures query reach, exact revisions, bindings and finite certificate
minima. Seven separately labeled support cases are query support, not end-to-end
invalid-source T6 reach. The prior-deployment test uses 65 independently verified
protected-base blobs in a separate process, genuine owners through COMMIT_READY,
six connections to the current task DB, and the untouched request. Its raw witness
records only `_progress_sources -> _verify_full_progress` reach and zero effects;
the later freshness helper is not reached.

Actual full execution produces two TEST issuances and four START/RESUME bindings.
The trajectory checks concrete PRODUCTION/EVALUATION peers for zero heads,
issuances and bindings, and checks non-TEST heads/issuances globally. It does not
implement or certify a real shadow owner. F2 repair, source/runtime authority loss,
bounded expiry, ACK-loss/concurrent dedup and rollback checks preserve historical
rows and receipt-only non-executable replay. Exact expiry equality remains PU only.
No production activation configuration, executable shadow or product requirement
status changes occur. Hevy/HealthKit obligations remain unchanged.

The lifecycle derives exact task/label/HEAD7/resolved-root digest, rejects ambient
or foreign targets before commands, passes the selected lifecycle to nested
bootstrap, supplies explicit owned URLs and asserts current_database on connections.
Imported builders do not invoke their foreign pytest lifecycles. The raw suite
contains 106 own namespace and 106 empty cleanup witnesses; the witness index was
independently matched to raw line numbers. Final cleanup inventories only the own
Compose label and reports no remaining resources. The four bounded older files
contain only the six permitted literal edits; other current fixture changes are
source-enum/hash corrections. Git comparisons show frozen/current authorities,
historical task artifacts, shared harness and workflows unchanged, and source,
tests and contracts byte-identical between tested and reviewed revisions.

Every final-check stdout/JUnit hash and reported executed/failure/error/skip count
was independently checked from regular Git blobs. The own suite is 105 passed,
one failed; the trajectory selector is one passed, one failed. Other recorded named
checks pass without skips. This review performed read-only verification and schema
validation, did not rerun PostgreSQL or invoke any DB lifecycle, and created only
its two task-scoped review bookkeeping files. It makes no independent live-provider,
clinical, API, release, historical-model reproduction or full hosted DB PASS claim.
