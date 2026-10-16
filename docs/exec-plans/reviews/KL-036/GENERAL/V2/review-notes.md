# Independent GENERAL review — cycle V2

Task: harness-backlog-v0.2/KL-036  
Reviewed implementation/result: 900d667394599345a51cec851160d33c01ebce7f  
Protected base: af09be228fbc89d074b6e863c83e1fdda343d55b  
Exact tested revision: e81cc2ccff69bf32a42f7c81b4671c99879b544b

Read AGENTS.md, the indexed authorities, KL-036 packet, pr-merge-reviewer and acceptance-test-writer skills, the named relevant Protocol sections 2/6.2–6.7/8 and DB S01–S04/S27–S32/3/4.1–4.3/5, M3 closure, release/state/storage/result/review contracts, prerequisite results/integrations and merged owner contracts/APIs. All indexed document and machine-readable authority hashes match the reviewed tree. KL-024/026/025/075/019 actual result records report PASS, integrations report MERGED, result bytes match their reviewed bindings, and each exact merge is an ancestor of the protected base. M3 records minimal isolated TEST closure PASS with production activation false and shadow execution false.

Independently inspected the full committed changed implementation/test/contract diff and task bookkeeping. The 641 changed paths comprise only the seven declared implementation/test/contract/result paths plus 634 own evidence/review artifacts. No migration, grant, dependency, shared fixture/lifecycle, enum, public command registry, frozen authority, historical completed task, or unrelated task change is present. Both tested-to-reviewed suffix commits are linear and contain only the own result and newly added own evidence; no prior evidence was overwritten in that suffix.

Decoded all 70 artifact references in the final sixteen-check index through the unchanged revision-bound decoder at the exact reviewed SHA. Regular-blob provenance, same-revision compact-payload availability, stored/recovered integrity, tested ancestry, exact command metadata and zero exits passed. The harness wrapper artifacts bind the exact kl test-harness command; its recovered manifest names the real collection and xdist execution argv, clean tested SHA, complete execution, zero exits and no errors. This review does not rerun task checks or claim fresh execution.

All raw collection stdout node identities occur exactly once. Complete collection IDs equal execution start IDs, every setup/call/teardown phase, and JUnit identities; all phases pass, all counts are positive, and no failure/error/skip/deselection or lost worker supplies eligibility. Standalone selectors each contain one exact case, and the two task whole-file suites contain every declared selector.

| Required check | Independently matched collection/execution/JUnit count |
|---|---:|
| harness_regressions_pass | 1492 |
| worker_identity_namespace_pu | 1 |
| worker_lease_deadline_pu | 1 |
| worker_takeover_fencing_dc | 1 |
| reaper_stale_candidate_dc | 1 |
| reaper_unowned_deadline_dc | 1 |
| reaper_atomicity_history_dc | 1 |
| reaper_unknown_accounting_dc | 1 |
| worker_independent_reaper_wf | 1 |
| reaper_preserves_committed_success_wf | 1 |
| worker_reaper_unit_suite | 2 |
| worker_reaper_db_suite | 7 |
| unit_regressions_pass | 249 |
| lint_passes | non-pytest; exact command exits 0 |
| typecheck_passes | non-pytest; exact command exits 0 |
| harness_validation_passes | non-pytest; exact command exits 0 |

The raw process/SQL observations agree with the source assertions. The whole DB suite records 20 distinct-process starts, 12 actual blocker observations, 11 committed idle-wait observations, 48 complete no-effect snapshots, and ten complete rollback witnesses across receipt/event/outbox/S29/ACK faults. Every standalone DB execution and the whole DB suite records migrated schema e8c2f1a6b904 and exact task-owned before/after inventories with equal foreign database/project/container/volume/network state and owned resource/child removal. The worker-loss witness has distinct worker/reaper/admission PIDs, a negative killed-worker exit, committed heartbeat, consumed ordinary job, saturated bounded queue, independent terminal progress and bounded exits. Waiting and discovery observations have idle connections without tuple locks; expiry uses elapsed trusted SQL time rather than sleeping as a race oracle.

Reviewed strict typed ReapIntent ingress, exact private prepared values and once-only mutation checks, S01→S27→sorted applicable S31→S02→S29 order, current request/attempt/owner/fence/deadline/status rechecks, fresh post-lock clock, nullable unowned ADMITTED/PENDING fence-zero CREATED basis, and frozen distinct deadline intent/attempt terminals. Lease-only cancellation is derived from the exact registered TEST recovery policy. The generic legacy completion branch is preserved and is never the new runtime authority. Receipt replay is authenticated, historical and non-executable; stale/changed/missing-receipt paths have complete unchanged relations.

Accounting uses separate actual ReserveCall/PermitDispatch/CancelUndispatched/MarkUnknown/SettleCall owners. The settlement-before-MarkUnknown process race confirms full stale rollback and continuation of the same reaper to another reservation; unrelated guard failures propagate. Outstanding UNKNOWN occupation cannot refund or resend; reliable late settlement changes accounting and preserves terminal planning/T6 denial. Actual takeover competitors increase fence once and preserve root budget/deadline. Stale RecordSnapshot/AdvanceAttempt/PermitDispatch/T6 paths deny with complete no-effect snapshots, alongside a successful current-worker path.

The T6 preservation case executes the merged ProtocolExecutionService/T6CommitCoordinator; success is never seeded. Both scan-before-commit/recheck-after-commit and commit-before-scan preserve complete head/bundle/auth/receipt/event/attempt relations. Synthetic upstream S26/S34–S37 and COMMIT_READY preparation, privileged isolated internal service sessions, trusted TEST reconciliation verification and PENDING compatibility perturbation are clearly declared instrumentation. They do not confer restricted-login containment, full planner/provider workflow, product/W/I/M4/release, production, shadow, App/full-DB, or merge PASS.

Final captures satisfy the launcher's credential-pattern guard with only its exact tracked synthetic password-mutation node-ID exception; recovered bytes are unchanged. Five quarantined original failure files were checked by hash and byte length only, without reading or printing their contents. Each matches its committed quarantine metadata. Sanitized historical trial diagnostics are labeled non-original and do not supply final eligibility. Earlier trial failures and incomplete/superseded captures are distinct from the complete final execution.

No additional concrete implementation or task-oracle defect was identified in this GENERAL review. DoD/readiness is nevertheless unsatisfied because the independently audited own evidence/review aggregate exceeds the unchanged cap; see storage-audit.txt. The result correctly separates task_checks_status PASS from task_status BLOCKED and integration_status UNMERGED, with empty requirement claims. Four fresh review types and coordinator-owned final admission remain separate conditions.

Review status: CHANGES_REQUIRED. Required finding: GENERAL-V2-001 (BLOCKER). No earlier review conclusion or implementer explanation was used as approval evidence.
