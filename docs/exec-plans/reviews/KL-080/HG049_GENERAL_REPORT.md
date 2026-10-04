# KL-080 HG049 independent GENERAL review

Status: CHANGES_REQUIRED. Reviewed implementation/result SHA: `275d7f849b31c9fe123c8d8594b88a85d1c25355`. Protected base: `034d6301316d0dade784a61b159c027b83fbce3a`. Tested SHA: `f85277e27ab5393b7f77b6fea25d4197294d3153`. PR reference: #92. No merge recommendation.

This review independently read AGENTS.md, the current index, revised packet, pr-merge-reviewer skill, frozen Protocol 3.2–3.3/6.2 and the relevant preparation/execution clauses, frozen DB S12/S13/S27/S36/S37, acceptance/state discipline, HG045 audit/feasibility, M3 contract, review contract, merge gate and current evidence storage/local DB policies. It inspected the actual base-to-reviewed diff, committed result and raw evidence. It did not consult other reviewers' conclusions, execute a DB lifecycle, modify implementation/governance, or publish anything externally.

## Blocking finding

KL080-HG049-GENERAL-001: mandatory selected-task evidence storage still fails. Calling the protected-base `tools/harness/compact_evidence.py` audit function independently on base→reviewed produces **38,263,916 stored bytes / 351 changed evidence and review files**, exceeding **16,777,216 bytes**. These four plain files exceed **262,144 bytes**:

| Preserved plain artifact | Bytes |
|---|---:|
| `15a7167e44b8044c94688cf7e367e2d02a962e31/harness_regressions_pass.xml` | 3,456,356 |
| `15a7167e44b8044c94688cf7e367e2d02a962e31/source_suite_dc.log` | 12,503,732 |
| `d6bfb285087456a1a43d6c6b856a07eee4e1746d/harness_regressions_pass.parallel.xml` | 3,456,356 |
| `d6bfb285087456a1a43d6c6b856a07eee4e1746d/source_suite_dc.log` | 12,480,477 |

Paths above are under `docs/exec-plans/evidence/KL-080/`. The storage policy excludes historical artifacts untouched relative to the protected base; these old unmerged KL080 artifacts are added by this task PR relative to that base, so they remain budgeted. Preserving them is correct and does not waive the gate. The tested-SHA audit in committed evidence reports 32,683,413 bytes; the reviewed-SHA audit additionally counts new evidence committed after testing, hence the larger independent total. New compact envelopes and payloads validated successfully. Resolution requires separately authorized reviewed preservation/storage governance, not local deletion, in-place compression, exemptions, CI weakening or historical recertification. Required normal gates and the dedicated App/controller gate must actually pass before DoD/merge. Current result is honestly BLOCKED, checks PASS, UNMERGED; review cannot be PASS while this mandatory DoD condition fails.

## Named command and raw evidence verification

All **91** committed `.capture.json` envelopes in the new HG049 evidence directory were read using `compact_evidence.read` at the exact reviewed SHA, with exact tested SHA and zero exit code enforced. The decoder checked committed regular-blob availability, owner/path, stored/raw lengths and hashes, bounded single-member gzip, no trailing/nested envelope data, and tested ancestry. Each of the 17 final command captures also matched its exact command. Actual decoded stdout/JUnit supports the following executions; no skipped/error/failure cases were found.

| Check | Executed pytest cases / result |
|---|---:|
| source_matrix_pu | 2 |
| source_basis_pu | 2 |
| source_namespace_pu | 1 |
| source_preparation_owners_dc | 4 |
| source_canonical_full_t6_dc | 1 |
| source_invalid_reconstruction_dc | 1 |
| source_freshness_predicate_support_dc | 7 |
| source_owner_trajectories_dc | 2 |
| source_current_denials_dc | 77 |
| source_repair_replay_expiry_dc | 14 |
| source_suite_dc | 106 |
| source_suite_pu | 6 |
| harness_validation_passes | HARNESS_CHECK_PASS, exit 0 |
| unit_regressions_pass | 247 |
| harness_regressions_pass | 1,347 |
| lint_passes | All checks passed, exit 0 |
| typecheck_passes | No issues in 171 source files, exit 0 |

The 106-case DC and 6-case PU raw collection nodeids exactly match raw JUnit case names, including parameter IDs and multiplicity. The unqualified check-harness execution is real PASS evidence for its command; it does not establish that the required selected-PR storage/normal merge gate passed.

## Exact revised oracles

The runtime diff changes only physical S13 admission acceptance to ELIGIBLE, physical S12 association acceptance to MATCHED, reader-side strict checks for both, and a narrowly extracted internal exact same-subject/admission-ID/policy ELIGIBLE freshness query used by actual full T6. No schema/wire/runtime registration/lock/owner change, enum alias, migration, policy downgrade or target seeding appears. Existing fixture changes are prospective physical source literals and dependent assertion/hash changes; the four bounded older fixtures contain precisely the six allowed literal replacements, with every other byte preserved. S27 ADMITTED, derived S36 CONFIRMED, TEST_ONLY, mechanical identifiers/rules and N TARGET retain distinct meanings.

The own PU suite exercises both real pure profiles with the exhaustive malformed S13/S12 matrix, identity/membership/freshness/actual separation/dedup/retraction denials, finite boundary equality and content guards. Own lifecycle preflight rejects foreign root/SHA/digest/label/namespace and ambient overrides before lifecycle calls. Source suite raw evidence records 106 owned namespaces and 106 cleanups; all bind exact tested HEAD7 plus SHA256 of the resolved root, and cleanup inventories are empty. The observed namespace is `kineticloop-kl080-source-f85277e-9a070975b04f`. Every connection checks current_database and nested bootstrap receives the selected lifecycle. Imported helpers do not run a foreign pytest lifecycle.

Four real PostgreSQL preparation cases cover mechanical/full owners with and without duplicate actual facts, genuine COMMIT_READY, immutable source/output hashes, separate full TRAINING/NUTRITION S36 and shared S37, no execution, and canonical ELIGIBLE/MATCHED. The raw suite includes two duplicate-resolution witnesses. Actual canonical full T6 reconstructs its genuine outputs and reaches the unchanged exact freshness read, persisting two authorizations with exact S13 revision and finite minimum dependency validity. Observation wrappers call the actual guard/read functions and return their original results.

The prior-deployment representative uses 65 exact Git-verified protected-base runtime/helper blobs in a separate subprocess with explicit current owned URLs and current_database assertions. Genuine old owners reach COMMIT_READY for ADMITTED+CONFIRMED without issuing authorization. Corrected current full T6 receives the untouched request and reaches `_progress_sources -> _verify_full_progress`, denies the malformed source, preserves complete snapshots, and does **not** reach the later freshness query. Seven real-PG exact predicate support cases remain separately labeled read support, with wrong subject/policy/ID controls; they do not claim end-to-end freshness denial.

The new raw mechanical witness proves a well-formed authenticated current `CommitBundle` built from untouched owner-produced mechanical S37. Actual ingress, current-fence and native daily-head lock pass. `prepare_authorization_basis` receives that exact validation and observes a native first-use head at revision zero with no current bundle; its original dependency query denies with `policy, demand, and calendar authorization bounds must exist`. The complete before/after snapshots match, the first-use head rolls back, request bytes remain unchanged, and no later synthetic certificate guard is claimed. This satisfies the revised HG049 denial oracle; positive legacy mechanical T6/T7 is not required. Canonical full trajectory persists two TRAINING/NUTRITION members, both START revision 1 and RESUME revision 2 bindings, ordinary PAUSE and CONTINUE, immutable history, and TEST_ONLY scope. Production/evaluation peers have no heads/issuances/bindings.

Current denials and repair/replay coverage call actual owners/guards and compare complete snapshots. Raw evidence contains 48 failed-owner zero-effect witnesses, 48 source-preparation denial witnesses, 47 exact zero-effect denial witnesses, two observed concurrent duplicate witnesses, same-root F2 full commit, receipt-only historical replay, source/runtime invalidation and strictly crossed real DB clock expiry. Fault injections exercise rollback after actual writes and do not replace positive authorization logic. Expiry equality remains PU only.

## Hosted, ancestry, prerequisites and preservation

The committed hosted manifest and all 15 decoded hosted artifacts were checked directly. Every manifest artifact/stdout hash and length matches recovered raw bytes. Actual manifest tested_commit and peer checkout argv bind `f85277e27ab5393b7f77b6fea25d4197294d3153`, while workflow-ref SHA is the protected base; these are properly distinguished. Actual environment is github-hosted Linux x86_64, run 37128318475. Collection and execution node lists agree; raw JUnit contains **780** cases, no failures/errors/skips. Unchanged hosted full tests/db, lint/typecheck, compose/readiness/reset/worktree isolation and empty final cleanup all pass. This is hosted evidence, not proof of the mandatory dedicated App-bound current-review-head local-db-gate.

Direct prerequisite integration records for KL076, KL079, KL077, KL027, KL078, KL026, KL023, KL022, KL028 and KL029 independently return zero semantic integration errors under the canonical validator. All 34 entry prerequisite records were additionally compared to protected-base MERGED integration blobs, exact reviewed result hashes/PASS payloads, result-commit byte identity, SHA-bound required PASS reviews, and merge ancestry before protected base. M2 closure remains PASS and unchanged; no M3 instance/status change occurs. Indexed authority/frozen/requirement files, task packet, CI and shared tools are byte-identical to protected base.

The tested→reviewed diff has 190 paths, exclusively the own result and newly appended HG049 evidence; implementation/tests/contracts remain unchanged after testing. Both old failed evidence directories are byte-identical to their recorded prior revision `b137c0beaf9e16d6ef41ff3d334922e4240719b0`; no historical raw log or result/review was recertified. Current result correctly separates task BLOCKED, task-check PASS, UNMERGED, no product requirements covered, and independent M3/product/release states.

No additional implementation blocker was found in this GENERAL review. The storage gate blocker remains sufficient to require changes. Fresh specialist review and actual final-head normal/controller gates remain independent requirements. Only this GENERAL record and this new report are written by this reviewer; previous reports are preserved. Report-created material is review bookkeeping, not tested task evidence, and requires the linear own REVIEW_RECORD_ONLY suffix for persistence.
