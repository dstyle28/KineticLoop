# HG035 preparation API and fixture map

Read-only observations at `d93131d`. No checks have run and no merge is inferred
from these observations. KL025 worktree observations are expressly provisional.

| Surface | Existing authority/API | Minimal KL019 responsibility |
| --- | --- | --- |
| Trusted identity | RoleIdentity plus BuilderIdentity/PlanningIdentity; registered subject namespace | Separately trusted TEST ingress binding with exact subject/policy/environment and idle internal connection. Never trust actor fields alone. |
| Publication wire | contracts.commands.PublishManifest inherits SubjectCommand; TEST_ONLY admitted only T6/T7 | A separate typed service request without authorization_scope, like existing builder/planning requests, can bind authenticated TEST identity. Preserve existing strict wire bytes and capability meanings. |
| T3 | TRANSACTION_OWNER_MATRIX PublishManifest → DecisionPublicationService; execute_command, acquire_registry_lease, require_artifact, idempotent_outcome; READY S23 verified after receipt/aggregate locks | Typed adapter reads persisted candidate basis; internal structured mutation persists exact S24/S25/S23/S01 using the one owner and its prepared publication digest/validity. No second publication algorithm. |
| T4/T5 | persistence.planning.PlanningWorkflowService.admit_or_revise/acquire_lease/renew_lease | Use merged APIs after actual publication to obtain intent/request/attempt/lease. Preserve root budgets/deadline/fence. |
| Missing upstream owners | No AdvanceAttempt or RecordSnapshot owner in matrix. S26 required as immutable snapshot context; current T6 basis requires COMMIT_READY S29 | Trusted fixture explicitly bootstraps immutable S26 and current attempt context/COMMIT_READY plus S34-S37 certificates after real admission/lease, outside target transactions. This is synthetic input, never demonstrated planning progress or worker authority. Missing owners/full workflow remain KL027. |
| T6 | CommitBundle → T6CommitCoordinator; lock_intents, require_current_fence, lock_daily_head, idempotent_outcome aggregate planning_attempts/validation_results, prepare_authorization_basis | Strict existing T6 wire compared to trusted ingress and persisted current basis. One coherent S38-S42/S27/S29/S01/S02-S04 outcome; use existing complete certificate evaluator and policy scope. No second authorization implementation. |
| First S38 | lock_daily_head raises if absent; prepare_authorization_basis requires exact locked head; CommitBundle allows update-only S38 | Bounded first-use support under existing CommitBundle ownership, exact subject/date and trusted bound calendar. S01 serializes missing-key contenders; all first-row effects participate in existing T6 rollback, no preseed target head or generic INSERT capability. |
| T7 | StartSession → ExecutionService; lock_execution, require_execution_authorization; same idempotent_outcome | Strict existing T7 wire compared to trusted ingress and exact newly issued P/A/hash/scope. Current eligibility is rechecked in the owner, one exact S45 with server accepted_at and lifecycle/S01 effects. |
| First S44 | lock_execution requires existing session and READY/PLANNED with no START; START allows S44 update and S45 insert | Bounded missing-session support exclusively StartSession at execution lock stage under S01; owner creates APP_STARTED S44, then START binding atomically. Replays historical/non-executable; lifecycle and different-key repeat guards retain authority. |
| Registry/control/replay | existing safety registry and current authorization evaluator; replay_outcome receipt-only historical path | Reuse for denials/replay; no new registry/control/revoke owner, cache permission, production actor or shadow executable namespace. |

Relevant canonical clauses: Protocol §2.1/2.1a, §4.4, §5.3/5.3a, §5.4/5.5,
§6.2/6.3/6.5 and §8; DB S23-S29/S34-S45/S49-S51, §3 owner entrypoints,
§4.1 fixed lock order, §5 T3/T6/T7 and §12 validity closure. Production activation
remains disabled. Requirement mapping I01/I02/I04/I07/A03@DC is not PASS.

## Complete proposed local fixture call inventory

| Exact required suite | Lifecycle path and nested calls | Namespace boundary |
| --- | --- | --- |
| tests/unit/protocol/test_execution.py | Proposed pure domain/identity and instrumented actual constructor proof; no Docker/PG | Owned transaction launcher validates exact supplied SHA/worktree-derived target overrides before pytest; its proof exercises the actual unchanged fixture. New execution/planning/ledger constructors reject invalid selectors/SHA before lifecycle work. Instrumented runner tests are isolation proofs, never actual regression substitutes. |
| tests/db/test_protocol_execution.py | New database_urls → DatabaseLifecycle(ROOT) → validated KL019 exec namespace → test_migrations.bootstrap_two_phase → trusted input setup/registration → actual service flow → same lifecycle.destroy | SHA and resolved-worktree digest, exec suffix. No generic override/foreign namespace. No S24/S25/S39-S42/S45 or succeeded intent/start outputs seeded. No S38/S44 for first-use positives. |
| tests/db/test_transaction_interfaces.py | Module database_urls → DatabaseLifecycle → env-selected namespace → bootstrap_two_phase → _SAFETY.seed → _seed_transaction_rows; _reset_kl022_fixture → owned truncate/seed → lifecycle.destroy | Existing KINETICLOOP_KL022_COMPOSE_PROJECT and KINETICLOOP_KL022_DATABASE provide exact derived KL019 tx namespace values in the check command. Owned launcher/proof validates SHA/worktree digest and exact supplied names before pytest/reset, and proves the actual unchanged fixture consumes them for bootstrap/reset/destroy. No fixture edit, new selector or global arbitrary-override rejection. Never run fixed KL022 defaults on shared daemon. Existing seeded owner regressions remain prerequisite evidence only. |
| tests/db/test_planning.py | Function database_urls → git short HEAD → lifecycle namespace → bootstrap_two_phase → trusted synthetic policy/subject/S01/program/factset/manifest seed → registry registration → service tests → lifecycle.destroy | At preparation base fixed KL024+SHA. HG034 authorizes KL025 adaptation but actual merged KL025 bytes must be audited. Proposed exact KL019 selector adds derived plan namespace, retaining unset and exact KL025 behavior. All semantic fixture bytes preserved. |
| tests/db/test_call_ledger.py | Provisional unmerged KL025 function database_urls → validated git short HEAD → KL025+SHA namespace → bootstrap_two_phase → trusted synthetic prerequisite seed/registration → services → lifecycle.destroy | Needs actual merged reread. Proposed exact KINETICLOOP_KL025_FIXTURE_OWNER=KL-019 adds derived ledger namespace and rejects all other selectors before lifecycle work. Preserve unset behavior and full ledger assertions. Existing planning-namespace isolation test imports planning module and instruments constructors; preserve its assertions unchanged. |
| tests/unit/persistence/test_transactions.py, tests/unit/workflow/test_planning.py, tests/unit/workflow/test_call_ledger.py | Pure suites, no database lifecycle in current observed files | Reread merged KL025 unit file; no indirect lifecycle may be assumed absent. |

Nested `test_migrations.bootstrap_two_phase(lifecycle, head=True)` performs lifecycle.reset,
provision_external_roles, database ownership handoff, baseline Alembic upgrade,
external_ownership_handoff, provision_subject_scope_ddl_guard, head upgrade and role
URL construction. It receives the selected lifecycle; it does not independently
select another namespace. Existing transaction `_SAFETY.seed` is a function import;
its foreign-labelled `database_urls` fixture is NOT selected by these commands.
No local full test_migrations or test_safety_registry suite is authorized by this
inventory. All called imports, helper functions, indirect fixture dependencies and
cleanup must be reread at actual merged head before finalization.

The two planning/ledger fixture-only exceptions permit namespace helper/import/assignment bytes
only. They are future KL019 edits, not HG035 production/test implementation. Existing
historical semantic regression fixtures may seed prerequisite outputs solely for
regression purposes; new KL019 trajectory must independently prove no target-output
seed. No skip, altered oracle, arbitrary target, daemon namespace reuse or lifecycle
monkeypatch can substitute for a real required database check. Unchanged broader
`uv run pytest tests/db` runs only in the existing fresh GitHub-hosted ubuntu-latest
VM and its job-owned local Docker daemon; no CI modification is proposed.

Preparation feedback against prospective KL025 c3966cc confirms its planning namespace isolation probe resets the selector itself and rejects empty, KL-024, lowercase kl-025, arbitrary, trailing-space KL-025 and ../KL-025; KL-019 is not in that rejection list. Preserve that probe byte-for-byte when adding the planning KL019 selector. This observation requires actual merged-byte reinspection and is not formal review or prerequisite PASS.

Final merged-byte audit base: eab2b305351cf3c504f74ac74868edc58d0a3430, actual
normal PR66 merge. The final validator pins planning baseline SHA256
b7b185e069d94f0e67826de02ec630259881add0fa8f5366823d830f95917636 and ledger baseline
SHA256 d3c09d2125844b1ed7e7bc138be41b43a02c0a95efd54d2bfc3012751fe615e2. The
transaction fixture remains SHA256 722346d6e0b03087ce08f2d03bc955c227652c189bfa4ccc1a50f2b7cf3abc3a.
The final current packet and exact validator candidate transformations are authority
for future KL019 edits. The complete revision-bound audit supersedes prospective
observations and validates existing owner/API, all called helper functions, actual
merged results/reviews/evidence and unchanged production/requirement/CI bytes.
