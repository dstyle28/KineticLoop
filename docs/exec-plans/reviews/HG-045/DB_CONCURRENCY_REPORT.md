# HG-045 independent DB concurrency review

Disposition: **PASS**, zero blocking findings and zero required follow-ups.

- Identity: `harness-governance-v0.1/HG-045`.
- Protected base: `26906bd7f4444914c228e98377f2b164fee0dd5d`.
- Tested implementation: `263c82e761747b88ac56f96be014e158f494dae0`.
- Reviewed implementation/result/evidence: `478a46a418fc759c1843ce24702ccee7aafcddc2`.

This review independently inspected the actual protected-base-to-reviewed diff, the governance record, the complete KL-080 packet, the validator and negative tests, committed selected captures and raw logs. It followed AGENTS.md, the current index, the governance and thread review contracts, and the pr-merge-reviewer/db-transaction-reviewer skills. Relevant frozen authority was Protocol 3.2–3.3, 6.2 and registry/transaction clauses, and DB S12/S13/S27/S36 plus sections 4.1 and 5 transaction boundaries. No full suite or DB lifecycle was rerun; the reviewer performed read-only Git/hash/definition/provenance checks.

## Frozen transaction and lock boundaries

The entire diff contains no runtime, migration, DB test, unit test or completed-result modification. A direct Git-blob comparison verified FROZEN_BASELINE.json and every frozen file unchanged. Existing backlog task definitions are value-identical; only NOT_STARTED KL-080 is appended, with no result, requirement PASS claim or evidence reference. HG-045 changes governance enforcement, not current database behavior.

KL-080's implementation boundary restricts deterministic source readers to physical S13 ELIGIBLE and S12 MATCHED, and transactions.py to full T6 source freshness/strict validation and a narrow internal shared read helper. It explicitly preserves S27 PlanningIntent ADMITTED, derived S36 CONFIRMED, runtime identifiers/RULES/registration and request shapes. It forbids authorization/policy/registry changes, alias conversion, migrations, model/network waits under coordination, and changing S01/S27/S02/S29/SafetyRegistry order or T1–T8 boundaries. These constraints preserve the frozen shared registry-before-S01 order and atomic T6 output/authorization/head/intent/receipt/event/outbox boundary. Future real PostgreSQL proofs include current fence/lease/basis denials, rollback/ACK-loss/concurrent dedup, revocation and finite expiry rather than relying on mocks.

## Reconstruction and freshness proofs

The inspected actual full T6 code in transactions.py calls `_progress_sources` at line 4219 before the exact admission query at line 4319. `_progress_sources` invokes `_verify_full_progress`, whose actual persisted S36/S37 reconstruction rebuilds the artifact through current readers. The packet correctly requires three different proofs: canonical full T6 reaches/passes that exact query; invalid prior-deployment input denies during earlier reconstruction with otherwise valid ingress/current basis and complete zero effects; separately labeled real-PG support tests exercise the same exact freshness predicate. The support helper must be shared by actual T6 and the test, remain internal and narrow, and cannot bypass reconstruction or supply an end-to-end claim.

The prior-deployment route is explicit and feasible by source inspection. Protected-base `tests/db/test_full_test_execution.py::ready` (lines 412–423) creates the unconsumed full request after genuine upstream/preparation owners and COMMIT_READY. `test_full_action_preparation.py::preparation_chain` produces both action S36 records and shared validation, and the runtime hash uses the pinned version/RULES, which the corrective packet preserves. Protected-base pure source probe and actual readers establish that ADMITTED+CONFIRMED is the historically accepted representative. A separate subprocess may use only exact Git-verified protected-base runtime/helper blobs, current KL-080 lifecycle and explicit own URLs, stop before old T6, and hand the unchanged typed request to corrected current T6. Other malformed values receive pure/preparation denials and exact-query support; they cannot be furnished with invented historical certificates. Target SQL seeds, guard patches, immutable-row changes, old pytest lifecycles and retrospective acceptance certification are explicitly prohibited. This is prospective feasibility, not evidence that future PostgreSQL checks have run.

## Isolation, fixture scope and M3 enforcement

KL-080 derives Compose/database namespaces from its task, fixed label, HEAD7 and resolved-root SHA12, requires preflight before every lifecycle, passes the selected lifecycle to nested bootstrap, asserts current_database per connection, and inventories only owned cleanup resources. Foreign/default/ambient lifecycles are forbidden. Eight exclusive keys include transaction_interfaces, user_coordination, protocol_interleaving_suite, test_only_demo_suite, authorization_core, canonical_fact_schema, planning_ledger and registry_coordination. Unchanged hosted full DB CI remains mandatory for older suites.

Validator definition/packet/plan hashes bind these constraints. The four older fixture content guards require exactly six identified literal corrections, reject omitted fixture paths, and preserve every other byte. Uncertain S12 sources become AMBIGUOUS; denied S13 sources remain NOT_ELIGIBLE. Historical artifacts and immutable rows cannot be rewritten. Negative tests cover weakened or missing scope, namespaces, checks/oracles, reviews, fixture changes, and corrective M3 contributions.

M3 now requires exactly 17 integrated task identities including KL-080 and eight exits including all twelve named source checks. An independent AST comparison verified every HG-044 exit mapping and contract digest unchanged and its full regression command list preserved as an exact prefix. Each new source command and canonical digest agrees with the packet, including all three guard proofs. Schema/contract and negative tests reject omission of corrective integration, exit, selector, oracle or regression. Existing boundary/interleaving ledgers, KL-074 support, M1/M2 prerequisites and collection/JUnit/provenance gates are preserved. HG-045 creates no M3 closure.

## Evidence verification and limits

A reviewer-run read-only audit verified all nine selected capture-file hashes, raw-log hashes, byte lengths and exact raw_utf8 equality at the reviewed Git revision. Each capture binds the specified base/tested SHA, exit code zero and PASS. Selected logs record 36 focused, 925 harness and 241 unit tests passing. The tested-to-reviewed diff contains only HG-045 governance/evidence bookkeeping. Failed development diagnostics remain separate and unselected.

For KL-028 and KL-029, independent Git ancestry checks verified result→reviewed→review-record→normal merge→protected base. Each review suffix is linear and confined to its own review directory; result bytes are identical across result, reviewed, review-record, merge and current reviewed revisions. These newly appended integrations do not recertify or rewrite historical UNMERGED result payloads.

All KL-080 execution checks remain NOT_RUN. This PASS certifies the reviewed governance design and enforcement only; it is not runtime conformance, hosted CI, M3 closure, product requirement or release PASS. This report is review-created bookkeeping under HG-045's own REVIEW_RECORD_ONLY exception.
