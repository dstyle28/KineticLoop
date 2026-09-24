# Physical schema dependency topology

This contract maps every frozen logical relation S01-S51 exactly once into a two-phase
PostgreSQL migration plan. It derives physical ordering from the current frozen Protocol
v1.2 and logical DB v0.2; it does not add fields, writer permissions, transaction
boundaries, or authorization meaning.

## Migration rule

1. Create relations in the dependency-first order exported by
   `kineticloop.persistence.schema_topology.topological_order`. A relation's
   `dependencies` must already exist when that relation is created. Self-references can
   be declared with their own relation.
2. After all 51 relations exist, add the foreign keys listed in
   `DEFERRED_REFERENCES`. These are forward pointers from mutable authority rows, plus
   the few provenance/result pointers which otherwise form a cycle.
3. Add indexes, write protections, and transaction guards in their owning tasks. This
   topology is not permission to replace a cross-row or transactional guard with a
   foreign key.

Every user-scoped reference must ultimately use a same-subject composite foreign key as
required by DB v0.2 section 1.2. External subject, actor, source-connection, and provider
identities are outside the frozen S01-S51 relation inventory and therefore do not appear
as topology nodes.

## Phase 1: create relations

The following is the stable physical order. A dash means that the relation has no
in-inventory create-time dependency. Logical numbers are identifiers, not DDL sequence
numbers.

| Order | ID | Relation | Create-time dependencies |
|---:|:---:|---|---|
| 1 | S01 | `user_decision_state` | — |
| 2 | S02 | `command_receipts` | — |
| 3 | S05 | `policy_bundles` | — |
| 4 | S06 | `program_versions` | — |
| 5 | S09 | `evidence_revisions` | — |
| 6 | S11 | `underlying_events` | — |
| 7 | S19 | `exercise_catalog_revisions` | — |
| 8 | S48 | `evaluation_releases` | — |
| 9 | S51 | `safety_registry_state` | — |
| 10 | S03 | `domain_events` | S02 |
| 11 | S04 | `outbox_deliveries` | S03 |
| 12 | S10 | `candidate_assertions` | S09 |
| 13 | S12 | `event_association_decisions` | S09, S11 |
| 14 | S13 | `admission_decisions` | S05, S09, S10 |
| 15 | S14 | `canonical_fact_revisions` | S10, S11, S13 |
| 16 | S07 | `durable_change_proposals` | S06 |
| 17 | S08 | `approval_issuances` | S02, S05, S06, S07 |
| 18 | S17 | `control_events` | S02, S05, S09, S13 |
| 19 | S18 | `control_heads` | S17 |
| 20 | S20 | `exercise_mapping_decisions` | S08, S19 |
| 21 | S15 | `factset_revisions` | S12, S13, S20 |
| 22 | S16 | `factset_members` | S12, S13, S14, S15, S20 |
| 23 | S21 | `projection_versions` | — |
| 24 | S22 | `projection_dependencies` | S05, S06, S14, S15, S19, S20, S21 |
| 25 | S23 | `manifest_builds` | S05, S06, S15, S21 |
| 26 | S49 | `safety_artifacts` | S05, S19, S48 |
| 27 | S50 | `artifact_revocation_events` | S49, S51 |
| 28 | S24 | `decision_manifests` | S05, S06, S15, S19, S20, S23, S49, S51 |
| 29 | S25 | `manifest_projection_bindings` | S21, S24 |
| 30 | S27 | `planning_intents` | S01 |
| 31 | S28 | `planning_request_revisions` | S02, S27 |
| 32 | S29 | `planning_attempts` | S24, S27, S28 |
| 33 | S26 | `decision_snapshots` | S24, S28, S29 |
| 34 | S30 | `planning_quota_buckets` | S05 |
| 35 | S31 | `call_reservations` | S27, S29 |
| 36 | S32 | `call_ledger_events` | S31 |
| 37 | S33 | `tool_evidence_records` | S26, S29 |
| 38 | S34 | `proposal_revisions` | S26, S29 |
| 39 | S35 | `prescription_demand_features` | S34 |
| 40 | S36 | `evidence_resolutions` | S05, S09, S12, S14, S24 |
| 41 | S37 | `validation_results` | S03, S05, S24, S28, S29, S34, S35, S36 |
| 42 | S38 | `daily_plan_heads` | S01 |
| 43 | S39 | `daily_bundle_revisions` | S02, S24, S27, S29, S37, S38 |
| 44 | S40 | `prescription_revisions` | S34, S49 |
| 45 | S41 | `bundle_prescription_members` | S39, S40 |
| 46 | S42 | `authorization_issuances` | S02, S05, S24, S36, S37, S40, S49, S51 |
| 47 | S43 | `authorization_events` | S02, S13, S17, S42 |
| 48 | S44 | `workout_sessions` | S01, S11, S14 |
| 49 | S45 | `execution_bindings` | S02, S40, S42, S44 |
| 50 | S46 | `replay_runs` | S24, S48 |
| 51 | S47 | `replay_artifacts` | S46 |

## Phase 2: bind forward references

These foreign keys are mandatory final-schema relationships, not optional denormalized
hints. They are delayed only so an authority root can precede the immutable or historical
rows to which its current pointer refers.

| Source field | Target | Rationale |
|---|:---:|---|
| S01.`current_factset_id` | S15 | Current input authority |
| S01.`active_program_id` | S06 | Active program authority |
| S01.`active_policy_bundle_id` | S05 | Active policy authority |
| S01.`current_manifest_id` | S24 | Published decision authority |
| S01.`last_control_event_id` | S17 | Control barrier authority |
| S01.`execution_basis_event_id` | S03 | Execution-exposure authority |
| S03.`correlation_intent_id` | S27 | Optional event correlation |
| S07.`base_manifest_id` | S24 | Proposal basis |
| S07.`origin_proposal_id` | S34 | Proposal provenance |
| S27.`current_request_revision_id` | S28 | Current request authority |
| S27.`current_attempt_id` | S29 | Current attempt authority |
| S27.`result_bundle_revision_id` | S39 | Terminal bundle result |
| S27.`result_authorization_id` | S42 | Terminal authorization result |
| S29.`snapshot_id` | S26 | Attempt snapshot |
| S34.`demand_feature_id` | S35 | Nutrition-to-demand dependency |
| S38.`current_bundle_revision_id` | S39 | Daily plan head authority |
| S51.`last_revocation_id` | S50 | Registry head authority |

Polymorphic reference sets such as S16 member targets, S22 dependency targets, S36
support/contradiction references, and S49 declared artifact dependencies must be
materialized as closed typed foreign keys or normalized child edges by the DDL task.
A free-text or unvalidated identifier is not an equivalent implementation.

S47 `source_revision_refs` uses the explicit `POST_BASE_REFERENCE_PLANS` phase. Its
target-typed child-edge tables are created only after all S01-S51 base relations exist,
must use same-subject composite foreign keys, and may not use a generic `(kind, text_id)`
target. R01 and R03 require typed S14 fact-revision and S20 mapping-decision edge
capabilities. Any additional source kind requires an explicit frozen-clause mapping in
the DDL task. Production relations never point back into evaluation storage.

## Authority roots

`AUTHORITY_ROOT_CONSTRAINTS` records the minimum order assertions consumed by tests and
future migration validation. It includes user coordination (S01), command identity
(S02), policy/program/evidence/event/catalog roots (S05/S06/S09/S11/S19), projection and
manifest roots (S21/S24), planning and ledger roots (S27/S31), plan/session/replay roots
(S38/S44/S46), and global release/artifact/registry roots (S48/S49/S51). This ordering
does not transfer write authority: the frozen command owners and T1-T8 boundaries remain
unchanged.
