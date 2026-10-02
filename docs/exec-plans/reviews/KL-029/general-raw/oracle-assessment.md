# Independent GENERAL review — harness-backlog-v0.2/KL-029

Reviewed implementation/result: `eed165afbd56d3ae551c46166aaec776cf79e625`.
Protected base: `9268fc8dd8c071c02dc5c698274dbf6fcd112776`.
Required task execution: `b9fbf9b475e07765db62e67f0104a800036dda4d`.

This assessment inspected the complete active packet, current index, AGENTS.md,
pr-merge-reviewer skill, result/review contracts, result, tests and contract diff,
merged prerequisite results/integrations, M2 closure, named frozen clauses, current
acceptance gate and requirement registry. Implementation prose was not treated as
proof. The independent audit reads exact regular Git blobs at bound revisions,
checks all indexed hashes, checks prerequisite merges at the protected base, and
validates raw task witnesses and XML counts itself. It does not execute or reuse
the implementation's evidence-audit script.

## Scope, entry, and revision

Only the three implementation paths in the packet changed, together with the
task's result and new raw task evidence. No source, migration, grant, shared
fixture/helper, lifecycle, Compose, CI, dependency lock, authority or requirement
registry changed. Actual KL008, KL017 and KL027 normal merge commits are ancestors
of the protected base; their persisted reviews match their integration SHAs.
M2 mechanical closure is PASS. The tested-to-reviewed suffix has one linear
commit, adding only this task's result and new task-evidence files. The three
implementation blobs are byte-identical at tested and reviewed SHAs.

## Exact oracle assessment

| Check | Independently inspected proof |
| --- | --- |
| shadow_namespace_and_boundary_pu | Root resolution, exact lowercase HEAD, fixed shadow label and fsencode-root SHA12 validate before runner entry. The namespace, malformed SHA/digest/label, ambient override, peer root and nested cleanup negative controls use a recording runner and assert zero runner calls. Actual selected bootstrap is passed its lifecycle. Fresh review run passed at the reviewed SHA. |
| shadow_strict_wire_pu | Real ShadowEvaluationArtifact has canonical null targets and strict constructors/parsers; non-null false/zero/list/map/string targets, missing/duplicate/extra/unknown fields fail. Actual TEST scope rejects other roles/resource boundaries and bypass flags. Real ExecutionIdentity and public parser reject evaluation/shadow input; genuine valid production wire, separately authenticated identity mismatches and altered hash reach require_wire denial. Fresh review run passed. |
| shadow_evaluation_principal_live_denials_dc | Actual trusted-admin registration and owner-produced TEST live rows establish the actors and targets. Owning TEST reads its exact head, issuance and binding; evaluation reads its own declared S46/S47. Foreign and missing IDs both return SQL NULL and the same wrapper denial/declared timing class. Fifteen SELECT/INSERT/UPDATE/DELETE/TRUNCATE operations fail with actual 42501 privileges, target real owner rows and record evaluation identity; source asserts full history equality after each rollback. |
| shadow_test_authorization_crossing_denials_dc | Actual full T6 and START/CONTINUE/ordinary PAUSE/RESUME are positive controls. Fresh rebuilt principal/policy/environment mismatch commands pass require_wire then fail exact registration. Separate actor/subject/policy/environment/hash wire cases reach require_wire. Registered TEST B uses B identity/wire and A authorization, reaching the current-membership pre-T7 denial. Evaluation and production actors cannot construct TEST identities and their real principals cannot read A. No earlier guard is mislabeled as a T7 rejection. |
| shadow_owner_payload_denials_dc | Idle owner connection and valid TEST registration precede ten calls, covering actual ShadowEvaluationArtifact and canonical payload across commit_full, commit, start, continue_session and resume. Exact typed-ingress GuardRequired messages are checked and histories remain identical. Genuine public parsing also rejects shadow and altered boundary payloads. Positive full commit and session commands persist owner output. |
| shadow_declared_evaluation_storage_dc | Separate evaluation A/B registrations and only declared historical S46/S47 plus required archived FK backing are fixture inserts. origin replication role, enabled triggers/FKs and preserved registry revision are checked; external source/mode/cutoff/IDs and independently validated row hashes are retained. Both evaluation principals read their own rows. Foreign evaluation/TEST/production callers receive the same missing/foreign response. Actual storage triggers reject evaluation live rows and TEST/production replay rows with exact namespace causes. TEST histories are unchanged; allowed global archive identity additions are separately counted. |
| shadow_suite_dc | Six cases executed with zero failures/errors/skips. Four separately reset owned DB trajectories, twelve actual T7 positive eligibility observations, 26 exact before/after full-history equalities, 27 scope denials, fifteen privilege denials and four empty Compose-label cleanup inventories are independently parsed from raw logs. All SHADOW_EVIDENCE records bind the tested SHA; namespace/root/database match its digest. Owner connections verify database, migration head and bounded timeouts; bootstrap uses selected lifecycle and bounds nested Python connections. No race requirement is introduced here. |
| harness_validation_passes | Exact committed command log reports HARNESS_CHECK_PASS, with code/result authority hashes independently verified by this review. |
| unit_regressions_pass | Raw log and XML bind exact command/tested SHA: 234 executed, zero failures/errors/skips, no XFAIL/XPASS substitutes. |
| harness_regressions_pass | Raw log and XML bind exact command/tested SHA: 790 executed, zero failures/errors/skips, no XFAIL/XPASS substitutes. |
| lint_passes | Exact committed log and command record report exit 0 / lint pass. |
| typecheck_passes | Exact committed log and command record report exit 0 / typecheck pass. |

The full-history source inventory includes owner source/preparation/planning rows,
S01 frontier/epoch/current heads/execution basis, daily bundles/prescriptions/members,
immutable issuances/bindings and sessions, receipts/events/outbox, scope/principal
registrations, registry state/dependencies/revocations and other TEST subjects.
The original START binding remains in the final two-binding history. Actual
eligibility observations call the unchanged guard and return its decision; this
is an observer, not a replacement evaluator or a no-op callback.

## State discipline and decision

There is no requirement PASS claim. Shadow store/API, API/rendering, R04@E2E,
G-SHADOW usability, M3 and release closure remain NOT_RUN; archived storage
fixtures are expressly external historical inputs, not a replay writer, live TEST
manifest or shadow workflow output. Production/shadow authorization, execution
binding and production auto-activation are not introduced. Scope and protocol
owners stay unchanged, so no frozen-spec change is required.

GENERAL PASS: zero BLOCKER findings and the exact tests-only DoD is satisfied by
committed raw evidence and independent source/oracle inspection. The fresh
review rerun executes only the two PU selectors; the DB_CONCURRENCY reviewer owns
the isolated suite resource, so this GENERAL review does not initiate DB lifecycle.
This does not itself satisfy other required specialist reviews or hosted CI.
