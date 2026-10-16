# DB concurrency review observations

Reviewed revision: 96ebb9e0e95211fc684273e7b69a49dc11e11e87. Protected base: af09be228fbc89d074b6e863c83e1fdda343d55b. Tested implementation: 6a3f10ef424f41bb690d8835f952484b0ca4f87b. This is independent review evidence, not a new test run.

The tested-to-reviewed suffix is the single linear result/new-evidence commit. Frozen authorities and packet match the protected base. KL024/KL026/KL025/KL075/KL019 actual result/integration records at the base identify PASS prerequisites, and all five merge commits are base ancestors. M3 remains isolated TEST, production activation false and shadow non-executable.

I inspected the bounded worker/reaper implementation, all changed transaction guards, exact owner call paths and own test file. S01 serializes first use and authenticated historical replay; typed reaper rechecks exact request/attempt/owner/fence/status/deadline/expiry under S01/S27, locks sorted applicable S31, then S02/S29, and derives distinct frozen terminal targets with fresh post-lock clock_timestamp(). Strict prepared update/completion guards permit only exact S27/S29 writes. Reap closure and receipt/event/outbox are one transaction; unknown accounting stays in separate existing CallLedgerService transactions. Idle waits, nullable unowned basis and T6 immutable success receive direct tests. No implementation defect was identified in those boundaries.

Independently decoded and verified 70 compact artifact envelopes and payloads as regular blobs at the reviewed SHA, checked both hashes/lengths and single-member gzip completion, and required exact final tested SHA/zero exit codes. Final sixteen-check evidence accounting:

- harness_regressions_pass: exact node IDs and all three phases/JUnit agree (1492 cases); exit 0.
- worker_identity_namespace_pu: exact node IDs and all three phases/JUnit agree (1 cases); exit 0.
- worker_lease_deadline_pu: exact node IDs and all three phases/JUnit agree (1 cases); exit 0.
- worker_takeover_fencing_dc: exact node IDs and all three phases/JUnit agree (1 cases); exit 0.
- reaper_stale_candidate_dc: exact node IDs and all three phases/JUnit agree (1 cases); exit 0.
- reaper_unowned_deadline_dc: exact node IDs and all three phases/JUnit agree (1 cases); exit 0.
- reaper_atomicity_history_dc: exact node IDs and all three phases/JUnit agree (1 cases); exit 0.
- reaper_unknown_accounting_dc: exact node IDs and all three phases/JUnit agree (1 cases); exit 0.
- worker_independent_reaper_wf: exact node IDs and all three phases/JUnit agree (1 cases); exit 0.
- reaper_preserves_committed_success_wf: exact node IDs and all three phases/JUnit agree (1 cases); exit 0.
- worker_reaper_unit_suite: exact node IDs and all three phases/JUnit agree (2 cases); exit 0.
- worker_reaper_db_suite: exact node IDs and all three phases/JUnit agree (7 cases); exit 0.
- unit_regressions_pass: exact node IDs and all three phases/JUnit agree (249 cases); exit 0.
- lint_passes: raw capture decoded, exit 0; output inspected.
- typecheck_passes: raw capture decoded, exit 0; output inspected.
- harness_validation_passes: raw capture decoded, exit 0; output inspected.

Actual raw process/SQL observations:

- worker_takeover_fencing_dc: 4 distinct child/backend PID pairs; before/after resource inventories equal; child cleanup verified; event counts {'before_inventory': 1, 'before_process_inventory': 1, 'migrated_namespace': 1, 'child_ready': 4, 'child_result': 3, 'elapsed_server_time': 2, 'postgres_blocker': 2, 'child_denial': 1, 'zero_effects': 10, 'after_inventory': 1, 'after_process_inventory': 1}.
- worker_independent_reaper_wf: 4 distinct child/backend PID pairs; before/after resource inventories equal; child cleanup verified; event counts {'before_inventory': 1, 'before_process_inventory': 1, 'migrated_namespace': 1, 'child_ready': 4, 'ordinary_work_received': 1, 'outside_transaction_wait': 2, 'child_result': 3, 'heartbeat_committed': 1, 'elapsed_server_time': 2, 'independent_terminal': 1, 'zero_effects': 5, 'worker_loss': 1, 'scan_released': 1, 'after_inventory': 1, 'after_process_inventory': 1}.
- reaper_preserves_committed_success_wf: 2 distinct child/backend PID pairs; before/after resource inventories equal; child cleanup verified; event counts {'before_inventory': 1, 'before_process_inventory': 1, 'migrated_namespace': 1, 'elapsed_server_time': 1, 'scan_released': 2, 'child_ready': 2, 'preflight_released': 1, 'outside_transaction_wait': 1, 'postgres_blocker': 2, 'child_result': 1, 'child_denial': 1, 'zero_effects': 5, 't6_success_preserved': 1, 'after_inventory': 1, 'after_process_inventory': 1}.
- worker_reaper_db_suite: 18 distinct child/backend PID pairs; before/after resource inventories equal; child cleanup verified; event counts {'before_inventory': 1, 'before_process_inventory': 1, 'migrated_namespace': 1, 'child_ready': 18, 'child_result': 13, 'elapsed_server_time': 13, 'postgres_blocker': 10, 'child_denial': 4, 'zero_effects': 44, 'scan_released': 9, 'preflight_released': 4, 'outside_transaction_wait': 6, 'complete_rollback': 10, 'legacy_pending_alias': 1, 'accounting_only_late_settlement': 1, 'ordinary_work_received': 1, 'heartbeat_committed': 1, 'independent_terminal': 1, 'worker_loss': 1, 't6_success_preserved': 1, 'after_inventory': 1, 'after_process_inventory': 1}.

Required correction DB036-01: takeover CAS race witness is preflight, not the guarded owner transaction. In test_takeover_fences_distinct_processes both child roles call ObservedLease.acquire_lease without preflight_gate. Its synchronous _lease first calls _replay; replay_outcome itself acquires S01. The test holds S01 before releasing each child gate, so both recorded blockers necessarily precede the guarded CAS transaction. The raw capture confirms waits on user_decision_state but does not identify a post-preflight owner transaction. Later outcomes do show fence 1 → 2, one denial, preserved root limits and current-worker progress; they do not repair that concurrency witness. Existing preflight_gate instrumentation already solves this in the stale-candidate, permit/cancel and T6 tests. Use it for both takeover contenders, observe each replay preflight released/idle, then queue their real owner transactions behind S01 with bounded blocker witnesses. Rerun the exact selector, whole-file suite and required packet checks at a new committed tested revision and obtain fresh SHA-bound reviews.

Verified task DB suite raw events include ten rollback points over all 67 relation contents, forty-four full-relation no-effect comparisons, same-key identical historical outcomes, ten PostgreSQL blocker observations, six outside-transaction waits, actual worker -15 exit with consumed saturated ordinary queue and separate admission/reaper PIDs, and actual T6 commit followed by byte-identical full-history preservation. These observations do not grant product/W/I/M4/release or full planner workflow PASS. Privileged isolated internal service and coherent synthetic immutable upstream T6 preparation are declared instrumentation. No DB lifecycle, foreign fixture, installed-App/full-DB gate, source/result/evidence edit, commit or installation mutation was performed by this review.
