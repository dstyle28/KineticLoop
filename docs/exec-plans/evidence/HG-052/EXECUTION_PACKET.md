# Draft: post-KL080 integration and minimal TEST M3 closure

Preparation only. Not dispatched, not a repository change, not closure approval.
Provisional identity: harness-governance-v0.1/HG-052. At inspected master 1d3075151246b2774640a3d7acec836f47ab2b8d,
committed governance IDs are HG-001 through HG-051; HG-052 is absent. Recheck live
master, open PRs and active reservations before assigning the ID; rename every own
path/reference consistently if occupied. Parent coordinates admission after KL080
normal merge. One fresh governance chat/worktree/branch/PR; do not reuse KL080.

## Authority and entry

Read AGENTS.md; CURRENT_DOCUMENT_INDEX.json; docs/harness/M3_CLOSURE_CONTRACT.md;
MILESTONE_CLOSURE.schema.json; INTEGRATION_RECORD.schema.json; HARNESS_CHANGE.schema.json;
docs/harness/HARNESS_GOVERNANCE_CONTRACT.md; THREAD_REVIEW_CONTRACT.md;
EVIDENCE_STORAGE_POLICY.md; LOCAL_DB_CI.md; RESOURCE_LOCKS.md; tools/harness/README.md;
indexed tools/harness/validate_harness.py; matching task-thread-runner,
protocol-guardian, db-transaction-reviewer and pr-merge-reviewer skills. Read merged
M2/M1 and relevant task results/reviews through their revision-bound integrations.
Use current indexed authority, not plan appendices read in isolation.

This is already an enforceable closure contract: HG044 ratified the mechanical
mapping and HG045 added KL080; HG046 supplies the dedicated local Linux daemon
option. No separate prior governance PR is required merely to refine a KL task
packet or enable M3. This draft concretizes execution of those existing rules;
packets_refined stays []. Do not amend validators, schemas, task definitions or
frozen semantics to obtain PASS. A discovered missing capability outside the
bounded evidence runner below requires stopping and proposing separate reviewed
governance; it is not implicitly authorized here. M4 packet refinement is a separate
concern and excluded.

Entry requires actual normally merged PR92 at its approved head, all required
quality/merge-gate/App checks successful, actual merge SHA independently verified,
latest master incorporated before testing, no conflicting reservations or active
controller/DB run. Current expected KL080 reviewed/result bytes and reviews must
remain exact; do not assume GitHub merge because a local branch exists.

## Exact write scope and resources

Authorized paths only:
- docs/exec-plans/integrations/KL-080.json (new actual MERGED bookkeeping)
- docs/exec-plans/milestones/M3.json (new closure instance only after proof exists)
- docs/exec-plans/governance/HG-052.yaml (one governance record; no parallel JSON)
- docs/exec-plans/evidence/HG-052/** (only own new packet, bounded runner/verifier,
  exact captures, manifests, closure construction/provenance and failed attempts)
- docs/exec-plans/reviews/HG-052/** (four independent canonical reviews and their
  own compact audit outputs, including honest failed findings if any)

These paths match governance_allowed_patterns's generic governance record,
integration, milestone, own evidence and own review allowances. files_changed must
be the exact protected-base→reviewed diff, not these globs. Enumerate actual files
when recording it. No CURRENT_DOCUMENT_INDEX.json/HARNESS_DOCUMENT_MANIFEST.json
edit is needed: a closure instance is not a new authority and newly added evidence
need not be appended to the delivery manifest. No changes to KL080 result, reviews,
evidence, source/tests/contracts, another integration, any task packet/backlog,
traceability, frozen files, lifecycle/Compose, CI, tool/runtime/controller or hashes.
No historical migration authorization transfers from KL080/HG051 to this task.

Reserve existing exclusive keys harness_core and release_evidence and exact two
new integration/milestone paths. Serialize the physical local executor/App gate
with the coordinator; never run alongside its final KL080 controller. These are
orchestration reservations, not invented HARNESS_CHANGE schema fields. Repository
protocol/database owners remain read-only. A dedicated disposable daemon isolates
legacy fixture resources, so do not reserve or borrow another task's live DB.
Do not mutate any preexisting task worktree, including dirty unrelated KL055.

Suggested own evidence filenames (all code committed before its tested SHA):
EXECUTION_PACKET.md, m3_runner.py, verify_m3.py, build_closure.py,
preflight.json, command-plan.json, environment.json, execution-index.json,
m3-regression-<testedSHA>.json, closure-validation.json, storage-audit.json,
namespace-and-cleanup.json, plus numbered captures and content-addressed payloads.
Use one new run directory outside the checkout per attempt; never overwrite proof.

## KL080 integration fields, pending actual merge

Expected record (replace only pending merge value after independent verification):
```json
{
  "task_identity": "harness-backlog-v0.2/KL-080",
  "display_task_id": "KL-080",
  "result_commit": "417b65ee68244dc86ab02add231b24dc662be790",
  "reviewed_head_sha": "417b65ee68244dc86ab02add231b24dc662be790",
  "review_record_commit": "f38a4c1fa9a87b6be5539eafe67b641613448dc4",
  "merge_commit": "PENDING_ACTUAL_NORMAL_MERGE_SHA",
  "integration_status": "MERGED"
}
```
KL080's actual task tested_commit is feb3236c175df171611fc5b7ddb4f6eeca3ce47c;
it remains inside its existing result, not a new integration field. Its protected
base was 1d3075151246b2774640a3d7acec836f47ab2b8d. Use the final corrected result
at 417b65e, not its prior 5812ff2 packaging representation. Review-record f38a4c1
contains all four PASS reviews and genuine missing-log correction. Verify ancestry,
byte-identical result at result/reviewed revisions, required exact evidence refs,
linear own-review suffix and actual merge reachability using the ordinary integration
validator. If actual PR head changes, these constants are invalid until reassessed.
Do not insert the pending placeholder in a schema-valid PASS artifact.

## Closure content

Exactly 17 active M3 identities: KL019–KL029 and KL075–KL080. All 35 transitive
prerequisite/support identities have records once KL080 is added; perform actual
semantic validation, not presence counting. Include KL074 exactly as M1 supporting
prerequisite, not an M3 member. Require M2 including historical M1 to validate.
All dependency merges precede each consumer's base and tested commits.
Use exact M3_EXIT_TASK_CHECKS and pinned contract/oracle hashes from the indexed
validator; bind every historical result and raw witness at its integration's
reviewed SHA. Historical executions do not become fresh integrated regression.
Build M3.json using the existing schema, including exact 31-row KL028 ledger:
19 planned executable rows PASS and 12 deferred rows NOT_RUN; nine DC interleavings
PASS, I04@WF NOT_RUN. Shadow usability and R04 E2E remain NOT_RUN; product claims [],
production_auto_activation false, shadow_executable false; historical model remains
UNVERIFIED_HISTORICAL_DECLARATION with independent reproducibility false.

## Isolation and 93-command execution

All fresh integrated commands run at one immutable full SHA T in a clean copied
checkout inside a run-owned disposable Linux Docker daemon, using the unchanged
LOCAL_DB_CI isolation model. Record actual OS/architecture, image ID/digest, tool
versions, full source SHA/tree, clean-state checks, bundle provenance and daemon
endpoint. Local ARM64 is local ARM64, never hosted/x64 evidence.

Important tooling distinction: db_ci.py local has a fixed full-DB plan and no
custom-command option. Do NOT claim that calling it ran the 93 M3 commands. An own
committed evidence runner may orchestrate the exact existing commands inside an
identically isolated daemon, reusing unchanged preflight/mount/ownership/cleanup
helpers where appropriate. This is task-owned execution/capture glue, not a change
to db_ci.py, installed controller, classifier, command semantics, fixture code or
namespace implementation. Review the runner's isolation and capture behavior before
privileged execution. If this cannot be done within the current isolation contract,
stop and seek bounded separately reviewed tooling governance rather than monkeypatch
shared command plans or weaken checks.

Outer container and volume must be fresh run-owned names containing HG052, T[:7],
resolved host root SHA256 prefix12 and a unique run token, validated before mutation;
owner labels and exact deletion targets mandatory. Copy a Git bundle, with normal
history and all referenced evidence commits, into the container. No host bind mount,
host Docker socket, host network/PID namespace, GitHub/signing credential, proxy
forwarding or ambient builder/remote Docker override enters it. Use locked dependency
sync. Internal socket unix:///var/run/docker.sock; daemon must begin empty. Capture
failure evidence and always clean exactly the owned outer container+volume; verify
absence afterward. No global Docker prune or foreign lifecycle.

Inside this fresh daemon, suites retain their existing supported fixture namespaces,
including literal legacy KL prefixes or names derived from T and the copied root.
Those are isolated instances in the new daemon, NOT another task's local resources.
Do not demand that a KL fixture accept HG052 as a new owner alias; do not set another
task's owner override or point any selector at its existing host database. Use each
suite's default supported environment after inspecting its fixture contract. Run
namespace PU preflights before the first DB lifecycle as separate extra checks;
record them separately without changing the exact ordered 93-command list. Run
selectors serially; concurrency already inside a test remains its actual oracle.
Inspect actual namespace inventory/cleanup per suite and daemon, fail on unexplained
leftover resources rather than indiscriminately deleting them.

Extract the exact list at T from M3_REGRESSION_COMMANDS and compare it byte-for-byte
and order-for-order with the 93 lines below; drift requires reassessment. Before each
pytest command collect exact selectors with `uv run pytest --collect-only -q ...`
(unit→tests/unit; harness→tests/harness), capture original stdout and exit status,
then execute the exact logical command with raw stdout and JUnit retained. Use the
existing runner's retained harness JUnit/manifest and any documented JUnit export;
record actual argv/environment for instrumentation, never mislabel a different test
selection or modified semantics as the command. Do not invent unimplemented CLI
options. The main regression record commands array remains the exact indexed list.

For every pytest execution, collection JSON must contain command/tested_commit/
integer exit_code/nodeids/hashed collection stdout. Positive raw collected counts,
node identities including complete bracketed parameter text, executed identities and
JUnit cases/counts must agree exactly, and each declared selector must contribute.
No failed/error/skipped/deselected/xfail/xpass/zero-case/duplicate case passes. For
check-harness require exit0 and HARNESS_CHECK_PASS with no HARNESS_CHECK_FAIL.
Record actual measured per-command counts; do not copy old 247/1492/780 counts or
infer all selectors from one umbrella run. Preserve extra observer/runner manifests
as provenance; they do not replace exact collection/JUnit/raw records.

The regression JSON is an ordinary regular JSON blob named
m3-regression-<T>.json under HG052 evidence with change_id, tested_commit:T,
status:PASS only after completion, exact commands and matching executions. Each
execution carries exact command, T, integer zero exit and stdout reference; every
pytest execution adds JUnit and collection refs. Raw refs are {path,sha256}, where
sha256 binds stored regular Git blob bytes (envelope bytes if compact), not the raw
hash inside an envelope; their revision is the containing evidence revision E.
No self-reference to an as-yet-uncreated commit. Validate through the real decoder
and m3_execution_evidence_errors, not a weaker custom surrogate.

## Storage policy

The new governance PR has its own 16MiB changed-evidence-and-review budget relative
to its protected base. KL080's unchanged 16.57MB history is not charged again and
must not be copied or rewritten. Use compact_evidence.py capture for actual output:
plain/envelope ≤256KiB, each deterministic same-dir gzip ≤8MiB, raw payload ≤64MiB,
total new/changed evidence+reviews ≤16MiB inclusive. Preserve all failure captures.
Plan plain small summaries and lossless compressed full logs/JUnit/collection; no
recursive raw_utf8, complete diff dumps, orphan payloads or duplicated bulk artifacts.
Share same-directory content-addressed payloads only when exact raw bytes match;
each command/run retains correct distinct metadata. Use one common capture directory
where useful. Reserve at least 1MiB measured headroom for four reviews/fixes before
final review; this is a planning allowance, not a larger budget. Audit each committed
stage with `python tools/harness/compact_evidence.py audit --base B --head SHA
--identity HG-052`. Actual bytes and errors[] required at final head. If real proof
cannot fit losslessly, retain it outside repo, report blocker and seek reviewed
storage refinement; never erase failed proof or silently split the required one-SHA
93-command regression into unrelated claims.

## Commit and SHA sequence (two distinct tested revisions)

B = actual latest protected master containing normally merged KL080.
1. In the new governance branch commit actual KL080 integration, own execution
   packet, frozen command plan, and complete bounded runner/verifier/build script.
   Verify scope and all35 integrations. Any helper adjustment precedes T.
2. Freeze clean T with integration already present. Run all93 integrated commands
   at T. Nothing modifies T's source, tests, authorities or integration. Preserve
   failures; if a runner fix is needed commit it and restart at new T (never mix SHAs).
3. Append fresh own evidence and final m3-regression-T.json in E. T→E permits only
   own governance record and NEW own evidence. Existing evidence modifications,
   integration/bookkeeping of another task, code/authority or milestone edits stale
   regression. Verify the actual governance tested-suffix and all raw bindings.
4. Generate and COMMIT M3.json pointing evaluated_commit E, M2/ref hashes at E and
   regression ref revision E. This is C. M3.json must be an unchanged regular HEAD
   blob when validated; a dirty ambient JSON cannot substitute. C lies AFTER E;
   do not extend the regression evaluated revision through this closure addition.
5. Use clean C as the governance record's tested_commit. Run final governance checks
   below at C; append their own evidence and a PASS governance record only after
   successful validation. Its checks_run contains C-bound checks, not raw T commands
   mislabeled C. A C-bound closure-validation check verifies the complete genuine
   T→E integrated regression. Freeze reviewed R containing the final record/evidence.
6. Obtain independent reviews at R. Only own reviews/HG052/** may follow R in linear
   REVIEW_RECORD_ONLY commits. No late result/evidence/closure correction fits that
   exception; fix then revalidate/review as needed. Check all evidence refs actually
   exist in Git, force-add specific legitimate ignored log files if necessary.
7. Normal push, honest PR, live quality/merge-gate and final App gate, normal merge.
   Parent owns controller admission/execution and merge; this worker never races it.

## Final checks, reviews and gates

At C execute and retain exact SHA-bound stdout for:
- uv run kl lint
- uv run kl typecheck
- uv run kl test-unit
- uv run kl test-harness (retain durable runner evidence, not just a temporary link)
- uv run kl check-harness (must actually validate committed M3 and integrations)
- own `uv run python docs/exec-plans/evidence/HG-052/verify_m3.py --revision C`
  using the normal schema/integration/M3/compact functions, reporting all35
  integrations,17 M3 identities,8 exits,93 fresh runs, layer statuses, SHA provenance,
  cleanup/storage, no interpretation that promotes deferred or product requirements.
Verify count of exits from actual M3_EXIT_TASK_CHECKS (currently8); reject drift.
A separate full_database_regression check is optional developer evidence unless
required by subsequent authorized packet; if claimed, use the unchanged full DB
runner and verifier with exact C and full manifest, not the93-command record.
Final App full DB remains mandatory and separate regardless of developer coverage.

Governance record conforms HARNESS_CHANGE.schema.json: identity, B, tested C,
change_status PASS, summary, packets_refined [], exact files_changed, C-bound
checks_run, frozen_impact NONE; authority_entries_added [] if included. No task result
is added or edited. Do not add unsupported schema fields to hold orchestration data.

Require fresh-context GENERAL, PROTOCOL, DB_CONCURRENCY and SECURITY_DATA_BOUNDARY
reviews at R under this packet, all zero blocking findings. Important distinction:
the generic validator mechanically requires GENERAL here (no task definitions change);
its HG044/HG051 special four-review clauses do not automatically apply to HG052.
Four reviews are the coordinator's explicit completion/admission requirement in this
packet, not a false claim about existing schema enforcement. Do not expand validator
scope simply to add a special case for this task.

After reviews, run the actual supported governance-selection entrypoint:
`uv run kl check-harness --ci-pr-base B --ci-pr-head H`.
It derives exactly one governance ID from the changed record and the reviewed SHA
from GENERAL.json, then applies governance checks. The CLI inspected at the base
has no --governance-change-id or --governance-reviewed-head flags; do not invent
those options or pass --task-id HG-052. The internal governance fields are populated
by configure_ci_merge_gate, not exposed as standalone CLI flags.
Validate exact review refs at R/H,
linear suffix, clean tree, budget, final PR head, strict current master ancestry.
GitHub quality and merge-gate must succeed at H. Installed trusted controller/App
local-db-gate runs full DB at live admitted B/H because evidence/integration paths
are not exempt. No local JSON upload or old KL080 receipt substitutes. Any installed
validator/controller incompatibility goes to parent for reviewed installation;
never candidate-side override/admission trick or manual success publication.

## Fail closed / honest outputs

Stop with durable FAIL/BLOCKED or SPEC_CHANGE_REQUIRED as appropriate for: missing
normal merge/gate; changed expected KL080 reviewed head; ID/resource conflict;
invalid integration/M2/history; contract or frozen drift; missing exact command,
selector or raw witness; no supported safe isolation; foreign namespace/credential
exposure; mismatched collections/JUnit/counts; failure/skip/timeout/interruption;
cleanup failure; ambiguous or missing Git refs; unsupported compact metadata;
budget impossibility; any source/fixture/runtime/authority change needed outside
scope; stale tested/reviewed suffix; review findings; failed or stale live gate.
No budget increase, alias relaxation, suppression, historical rewrite, M3→M4 cycle,
product release assertion or passing verdict manufactured from archival retrieval.
Report task/governance PASS, review PASS, App/CI PASS, normal MERGED and M3 closure
as separate facts. No actual closure exists until its complete record validates.

## Exact ordered M3 regression commands

The following list is extracted statically from the indexed validator at 1d3075151246b2774640a3d7acec836f47ab2b8d;
no tests or database commands were executed to prepare this draft.

01. `uv run kl test-unit`
02. `uv run kl test-harness`
03. `uv run kl check-harness`
04. `uv run pytest -q tests/db/test_boundary_acceptance.py`
05. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b01_unsealed_canonical_denial`
06. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b02_stale_frontier_seal_race`
07. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b03_sealed_immutability_ready_barrier`
08. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b04_relevant_revoke_issue_reauthorize`
09. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b05_unrelated_revoke_preserves_eligibility`
10. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b06_revoke_before_publish`
11. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b07_revoke_current_execution_denial`
12. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b09_server_minimum_certificate`
13. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b11_backdated_revoke_commit_linearization`
14. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b12_future_revoke_immediate_at_commit`
15. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b13_revoke_rollback_zero_effects`
16. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b14_registry_failclosed_stop_support`
17. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b15_fresh_registry_both_orders`
18. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b16_continue_resume_after_invalidation`
19. `uv run pytest -q tests/db/test_boundary_acceptance.py::test_b17_transitive_revoke_denied`
20. `uv run pytest -q tests/db/test_call_ledger.py`
21. `uv run pytest -q tests/db/test_deterministic_planning.py`
22. `uv run pytest -q tests/db/test_factsets.py`
23. `uv run pytest -q tests/db/test_factsets.py::test_complete_serializes_with_candidate_writer`
24. `uv run pytest -q tests/db/test_factsets.py::test_seal_frontier_atomicity_and_old_replay`
25. `uv run pytest -q tests/db/test_full_action_preparation.py`
26. `uv run pytest -q tests/db/test_full_test_execution.py`
27. `uv run pytest -q tests/db/test_full_test_execution.py::test_continue_resume_rechecks`
28. `uv run pytest -q tests/db/test_full_test_execution.py::test_replay_and_atomicity`
29. `uv run pytest -q tests/db/test_migrations.py`
30. `uv run pytest -q tests/db/test_migrations.py tests/db/test_transaction_interfaces.py`
31. `uv run pytest -q tests/db/test_planning.py`
32. `uv run pytest -q tests/db/test_planning_progress.py`
33. `uv run pytest -q tests/db/test_preparation.py`
34. `uv run pytest -q tests/db/test_protocol_execution.py`
35. `uv run pytest -q tests/db/test_protocol_interleavings.py`
36. `uv run pytest -q tests/db/test_protocol_interleavings.py::test_artifact_revoke_vs_issue`
37. `uv run pytest -q tests/db/test_protocol_interleavings.py::test_artifact_revoke_vs_publish`
38. `uv run pytest -q tests/db/test_protocol_interleavings.py::test_artifact_revoke_vs_start`
39. `uv run pytest -q tests/db/test_protocol_interleavings.py::test_cancel_vs_dispatch`
40. `uv run pytest -q tests/db/test_protocol_interleavings.py::test_expiry_vs_start`
41. `uv run pytest -q tests/db/test_protocol_interleavings.py::test_publish_vs_user_revoke`
42. `uv run pytest -q tests/db/test_protocol_interleavings.py::test_seal_vs_input_update`
43. `uv run pytest -q tests/db/test_protocol_interleavings.py::test_start_vs_user_revoke`
44. `uv run pytest -q tests/db/test_protocol_interleavings.py::test_takeover_vs_commit`
45. `uv run pytest -q tests/db/test_safety_registry.py`
46. `uv run pytest -q tests/db/test_safety_registry.py::test_t2_global_commit_rollback_and_effective_at_semantics`
47. `uv run pytest -q tests/db/test_shadow_isolation.py::test_declared_evaluation_storage_isolation`
48. `uv run pytest -q tests/db/test_shadow_isolation.py::test_evaluation_principal_live_denials`
49. `uv run pytest -q tests/db/test_shadow_isolation.py::test_shadow_payload_owner_denials`
50. `uv run pytest -q tests/db/test_shadow_isolation.py::test_test_authorization_crossing_denials`
51. `uv run pytest -q tests/db/test_test_only_demo.py`
52. `uv run pytest -q tests/db/test_test_only_demo.py::test_expiry_then_deny`
53. `uv run pytest -q tests/db/test_test_only_demo.py::test_fdn_repair`
54. `uv run pytest -q tests/db/test_test_only_demo.py::test_full_trajectory`
55. `uv run pytest -q tests/db/test_test_only_demo.py::test_production_shadow_denials`
56. `uv run pytest -q tests/db/test_test_only_demo.py::test_revoke_then_deny`
57. `uv run pytest -q tests/db/test_transaction_interfaces.py`
58. `uv run pytest -q tests/db/test_transaction_interfaces.py::test_t6_authorization_evaluator_persists_exact_minimum_certificate`
59. `uv run pytest -q tests/e2e/test_authorization_evaluator.py`
60. `uv run pytest -q tests/unit/protocol/test_authorization.py`
61. `uv run pytest -q tests/unit/protocol/test_authorization.py::test_timeless_dependency_requires_auditable_policy_in_same_transitive_closure`
62. `uv run pytest -q tests/unit/protocol/test_authorization.py::test_validity_closure_uses_every_bound_and_denies_missing_or_elapsed_basis`
63. `uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py`
64. `uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b01_unsealed_canonical_denial`
65. `uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b08_missing_validity_denied`
66. `uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b09_server_minimum_closure`
67. `uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b10_expiry_without_status_job`
68. `uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b17_transitive_closure_omission_denied`
69. `uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b18_timeless_policy_reason_required`
70. `uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_boundary_namespace`
71. `uv run pytest -q tests/unit/protocol/test_execution.py`
72. `uv run pytest -q tests/unit/protocol/test_factsets.py`
73. `uv run pytest -q tests/unit/protocol/test_interleaving_namespace.py::test_time_boundaries`
74. `uv run pytest -q tests/unit/protocol/test_shadow_isolation.py tests/db/test_shadow_isolation.py`
75. `uv run pytest -q tests/unit/protocol/test_shadow_isolation.py::test_namespace_and_boundary`
76. `uv run pytest -q tests/unit/protocol/test_shadow_isolation.py::test_strict_shadow_wire`
77. `uv run pytest -q tests/unit/protocol/test_test_only_demo.py::test_namespace_and_boundary`
78. `uv run pytest -q tests/unit/workflow/test_call_ledger.py`
79. `uv run pytest -q tests/unit/workflow/test_planning.py`
80. `uv run pytest -q tests/unit/workflow/test_source_decision_conformance.py::test_source_matrix`
81. `uv run pytest -q tests/unit/workflow/test_source_decision_conformance.py::test_basis_and_actual_separation`
82. `uv run pytest -q tests/unit/workflow/test_source_decision_conformance.py::test_namespace`
83. `uv run pytest -q tests/db/test_source_decision_conformance.py::test_preparation_owners`
84. `uv run pytest -q tests/db/test_source_decision_conformance.py::test_canonical_full_t6`
85. `uv run pytest -q tests/db/test_source_decision_conformance.py::test_invalid_source_reconstruction`
86. `uv run pytest -q tests/db/test_source_decision_conformance.py::test_freshness_predicate_support`
87. `uv run pytest -q tests/db/test_source_decision_conformance.py::test_owner_trajectories`
88. `uv run pytest -q tests/db/test_source_decision_conformance.py::test_current_denials`
89. `uv run pytest -q tests/db/test_source_decision_conformance.py::test_repair_replay_expiry`
90. `uv run pytest -q tests/db/test_source_decision_conformance.py`
91. `uv run pytest -q tests/unit/workflow/test_source_decision_conformance.py`
92. `uv run pytest -q tests/unit/workflow/test_deterministic_planning.py`
93. `uv run pytest -q tests/unit/workflow/test_full_action_preparation.py`
