#!/usr/bin/env python3
"""Validate Harness contracts; Git arguments enable revision-bound PR checks."""
import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = 'KineticLoop_Harness_Backlog_v0.2.json'
TRACEABILITY = 'KineticLoop_Harness_Traceability_v0.3.json'
PROJECT_PLAN = '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md'
M1_CLOSURE_TRACEABILITY_TASK_FIELDS = (
    'task_identity',
    'id',
    'milestone',
    'depends_on',
    'conditional_depends_on',
    'commands',
    'transaction_boundaries',
    'invariant_ids',
    'table_ids',
    'context_files',
    'entry_conditions',
    'environment_requirements',
    'deliverables',
    'definition_of_done',
    'parallel_write_policy',
    'requirements_covered',
    'checks_required_for_this_task',
    'check_contracts',
    'evidence_paths',
    'resource_keys',
    'write_paths',
    'write_paths_status',
    'review_requirements',
    'packet_refinement',
    'status',
)
TRACEABILITY_TASK_FIELDS = M1_CLOSURE_TRACEABILITY_TASK_FIELDS + ('shared_hotspot',)
INDEX = 'CURRENT_DOCUMENT_INDEX.json'
MANIFEST = 'HARNESS_DOCUMENT_MANIFEST.json'
GOVERNANCE_SCHEMA = 'HARNESS_CHANGE.schema.json'
INTEGRATION_SCHEMA = 'INTEGRATION_RECORD.schema.json'
MILESTONE_CLOSURE_SCHEMA = 'MILESTONE_CLOSURE.schema.json'
M1_TASK_IDS = {f'KL-{number:03d}' for number in range(1, 10)}
M1_CLOSURE_M2_TASK_IDS = {
    'KL-010', 'KL-011', 'KL-012', 'KL-013', 'KL-014',
    'KL-015', 'KL-016', 'KL-017', 'KL-018', 'KL-055',
}
# Current M2 may grow through later governance without rewriting the historical M1
# closure revision that proved the original refinement set.
M2_REFINED_TASK_IDS = M1_CLOSURE_M2_TASK_IDS | {'KL-072'}
M2_TASK_IDS = M2_REFINED_TASK_IDS
M2_REGRESSION_COMMANDS = [
    'uv run pytest -q -p no:cacheprovider',
    'uv run kl check-harness',
]
M2_EXIT_TASK_CHECKS = {
    'schema_rebuild_from_zero': {
        'KL-013': {'empty_db_upgrade_head', 'database_rebuild_is_deterministic'},
        'KL-072': {'two_phase_empty_db_upgrade_head'},
        'KL-017': {'single_migration_head', 'complete_db_suite_passes'},
    },
    'migration_dependency_graph_documented': {
        'KL-010': {'fk_dependency_graph_is_acyclic', 'authority_roots_precede_dependents'},
        'KL-013': {'fk_order_matches_topology'},
    },
    'no_writer_bypasses_owner_subject_guard': {
        'KL-012': {'owned_transition_only', 'direct_sql_bypass_rejected'},
        'KL-015': {'transaction_owner_matrix_complete', 'subject_guard_required',
                   'direct_write_bypass_rejected'},
        'KL-017': {'subject_namespace_isolation', 'application_role_scope_enforced'},
        'KL-072': {'safety_registry_object_ownership_enforced',
                   'safety_registry_runtime_login_boundary_enforced'},
    },
    'shadow_registry_gates_precede_affected_contracts': {
        'KL-014': {'shadow_and_test_scope_fail_closed'},
        'KL-015': {'registry_lease_required_for_publish_commit_and_session_entry',
                   'complete_frozen_lock_order_enforced'},
        'KL-016': {'shared_gate_command_matrix_fails_closed',
                   'exclusive_global_gate_serializes', 'stop_has_no_registry_dependency'},
        'KL-017': {'test_authorization_is_isolated', 'evaluation_storage_is_isolated'},
        'KL-072': {'safety_registry_migrated_schema_integration'},
    },
}
M2_REQUIRED_CHECK_IDS = {
    'KL-072': {
        'baseline_migration_unchanged',
        'single_successor_migration_head',
        'successor_migration_contains_no_cluster_role_ddl',
        'safety_registry_role_preflight_fails_before_object_changes',
        'two_phase_empty_db_upgrade_head',
        'safety_registry_migrated_schema_integration',
        'complete_safety_registry_suite_uses_migrated_schema',
        'safety_registry_object_ownership_enforced',
        'safety_registry_command_routine_privileges_enforced',
        'safety_registry_definer_search_path_and_schema_acl_enforced',
        'safety_registry_runtime_login_boundary_enforced',
        'safety_registry_role_owner_boundary_enforced',
        'safety_registry_migrated_db_regressions_pass',
    },
    'KL-014': {
        'build_preparation_stays_outside_t2',
        'preparation_and_registry_management_stay_outside_atomic_boundaries',
    },
    'KL-015': {
        'registry_lease_required_for_publish_commit_and_session_entry',
        'preparation_work_stays_outside_coordination_locks',
        'factset_build_stays_outside_subject_coordination',
        'complete_frozen_lock_order_enforced',
        'multi_key_lock_order_is_stable',
        'reverse_lock_order_is_rejected',
        'receipt_before_s01_is_rejected',
        'event_outbox_atomicity_enforced',
        'outbox_dispatcher_does_not_lock_subject_guard',
        'stale_fence_commit_is_rejected',
        'dispatch_first_winner_and_replay_non_resend',
        'ack_loss_replay_preserves_natural_uniqueness',
        't6_ack_loss_replay_returns_same_issuance',
    },
    'KL-017': {
        'cross_subject_denial_is_non_enumerating',
        'complete_db_suite_passes',
    },
    'KL-018': {
        'artifact_registry_successor_migration_chain',
        'artifact_identity_is_immutable',
        'artifact_dependency_closure_required',
        'artifact_dependencies_must_be_pre_registered',
        'artifact_dependency_graph_is_acyclic',
        'artifact_dependency_closure_is_bounded',
        'artifact_registration_requires_management_capability',
        'artifact_registration_command_routine_privileges_enforced',
        'artifact_registration_session_authority_enforced',
        'artifact_registration_uses_exclusive_registry_gate',
        'artifact_registration_direct_write_rejected',
        'unregistered_or_revoked_artifact_denied',
        't3_t6_t7_require_artifact_refs',
        'artifact_registry_db_constraints_pass',
        'artifact_contract_unit_suite_passes',
        'artifact_validity_is_null_total',
        'artifact_timeless_policy_is_registered_dependency',
        'artifact_persistence_denials_are_stable',
        'artifact_dependency_dense_graph_is_bounded',
        'artifact_registration_lock_timeout_is_atomic',
        'artifact_registration_post_write_failure_is_atomic',
        'artifact_registration_safety_registry_privilege_regression',
        'complete_db_suite_passes',
    },
    'KL-055': {
        'provider_subject_source_binding_is_trusted',
        'evidence_envelope_closed_s09_schema',
        'provider_credentials_do_not_cross_evidence_or_diagnostic_boundary',
        'provider_contract_is_hermetic',
        'provider_fixtures_pass_hardened_synthetic_guard',
    },
}
KL015_REQUIRED_INVARIANT_IDS = [f'INV-{number:02d}' for number in range(1, 19)]
KL015_REQUIRED_TRANSACTION_BOUNDARIES = ['T1-T8']
KL015_REQUIRED_TABLE_IDS = [
    *(f'S{number:02d}' for number in range(1, 46)),
    *(f'S{number:02d}' for number in range(48, 52)),
]
# SHA256 of canonical JSON {check_id, command, pass_oracle}. These security-critical
# contracts must change through an explicit Harness governance edit; keeping an ID
# while weakening its executable command or oracle fails closed.
M1_CLOSURE_KL018_REQUIRED_CHECK_IDS = {
    'artifact_dependencies_must_be_pre_registered',
    'artifact_dependency_graph_is_acyclic',
    'artifact_dependency_closure_is_bounded',
    'artifact_registration_requires_management_capability',
    'artifact_registration_uses_exclusive_registry_gate',
    'artifact_registration_direct_write_rejected',
}
M1_CLOSURE_KL017_REQUIRED_CHECK_IDS = {
    'cross_subject_denial_is_non_enumerating',
}
M1_CLOSURE_KL017_CRITICAL_CONTRACT_DIGESTS = {
    'subject_namespace_isolation': 'f4372d9ad4ad1395f9fbf07611ba68813e0c46de01249de56e312f3731f7e2ff',
    'test_authorization_is_isolated': 'f89d192eedb9c346bcaa7ef047a859e8c0cb6d462e42d018e2a5b0e6ae5392ab',
    'evaluation_storage_is_isolated': 'e3b35eaae47e664a203bf700ce4f28a796e7787226faf92146673ce2b80015e6',
    'application_role_scope_enforced': 'a1b2c42c5c8aed9e3caa1ad43404aabde2d449a2fe0a6294637449977baad975',
    'subject_isolation_e2e_passes': '2c6c1aed417611a457c2eda86771cb0a8dee38db398311f940b7b3c7b5b775f1',
    'cross_subject_denial_is_non_enumerating': 'a1a5fccddd0d93ee54ff8f118732452c977ce234439593acefb1a32a27089bd4',
}
M1_CLOSURE_KL018_CRITICAL_CONTRACT_DIGESTS = {
    'artifact_identity_is_immutable': '5a5d6976957b081e045743ba114df6e8aebf782c4cc66123026dafbee59456eb',
    'artifact_dependency_closure_required': '6f69a7171def4c61b7d7390a0272495b2ddd75b5902375447cc9aac410def2ce',
    'artifact_dependencies_must_be_pre_registered': '935e593ad9d7d2bdf05257326866c139e2ff4471ea0f2fdffee1e01adc1a087d',
    'artifact_dependency_graph_is_acyclic': '2db1302d2bd5319910e6c9aa9d861fa8f3ef1c7d9f4d2f813fe229f72f915960',
    'artifact_dependency_closure_is_bounded': '18805edc8865ec58437c7752aad50ac34d685c55c487e0baf0d7cff12f91bd9e',
    'artifact_registration_requires_management_capability': '055c6d74460bb1bcc64da38cf018f29df96b7829e8eebcfd365a8b7cffba7658',
    'artifact_registration_uses_exclusive_registry_gate': '4b43e27668003b90fb22932b54e776a5a8f2280b2a674e0eb518411c0a90b540',
    'artifact_registration_direct_write_rejected': 'd5e91d07031d5fb89a4aca4658aef275d7684cc8325f4532bf20b69e7c3a2643',
    'unregistered_or_revoked_artifact_denied': 'e45c0d2b3765a6e2a9a8534b21410a02c67f270a8a9f33c1ed5bec6b22deb4cb',
    't3_t6_t7_require_artifact_refs': 'b4ef957a9ee368b6e074fa04ab340490904927371239ab0f42244ad22f5c4d6e',
}

M2_CRITICAL_CONTRACT_DIGESTS = {
    'KL-072': {
        'baseline_migration_unchanged': '18331c511a80b48d3e8c3bf2504954e468d02dc888cd7fa2a7ce8c568538ea18',
        'single_successor_migration_head': '4ee1bd768c1e190419ac52f43109c7cb49d0167484f589890d9cd4146a52c299',
        'successor_migration_contains_no_cluster_role_ddl': '5b52c22832ae9f6eb4e64c7ac61b8af7fc2db361b2c82f0226585a421816b08f',
        'safety_registry_role_preflight_fails_before_object_changes': '4108abfa9b45652bde4f9f4ba9011deb05fae3c2c4a0e6a41ca24e3490d1465b',
        'two_phase_empty_db_upgrade_head': 'ccea39a134e60f8f8a3e9bec320b2d431d29dba92951c94c6d7b786201f017a9',
        'safety_registry_migrated_schema_integration': '936fc29507088c503e2b4ee63ba5acf3c997b555692306924ad1635e215be5b6',
        'complete_safety_registry_suite_uses_migrated_schema': 'df0a4e0ea1f68ef49969d9bfaf096d8349a5cb96a4320037dec1fc5ab5442496',
        'safety_registry_object_ownership_enforced': '2b55aa8f3756c8777fa444dcaae960b29138591356343042fdc8c15ff95d1663',
        'safety_registry_command_routine_privileges_enforced': '1dc169d0cdb6a01e173500842305fb958e86736a35f872337af9d33142b096cc',
        'safety_registry_definer_search_path_and_schema_acl_enforced': 'b9ba8ffa6abd75d6894a50ba2bb2d2bece263a2ab3b30fca1c3797220787a8d5',
        'safety_registry_runtime_login_boundary_enforced': 'de25a21eeb874fc38e07530b948c664f3dbc731d4d5165d54201630e09fa4ca2',
        'safety_registry_role_owner_boundary_enforced': '04133a11d8b6ad8a3f1f0386674ae1a3d56cf35b8bb9be022bc1587d1cee7f79',
        'safety_registry_migrated_db_regressions_pass': '7a48e66c4016fb4ba4f945c1cbcb6f3d1558f24af7dfe8d58851b0543a399b2b',
        'harness_validation_passes': '2dbb33f46e379c228225cd02bc8afdf39689c54008b8ca7b1b019e0d2c4139bf',
    },
    'KL-014': {
        'strict_t1_t8_contract_matrix': 'f7fff61a6a44a0ac8ee0e57be4145b8ba8602d3f3348acad80e0eba45cf047ad',
        'build_preparation_stays_outside_t2': 'bfcfd359b83698cfb96d8986ddba85e620fb4c6eb51c1c5c55f4f39be37d0aed',
        'preparation_and_registry_management_stay_outside_atomic_boundaries': 'a2d6965d4bcb0ac6c9c8c61f49ce9eee21fccdda97d69193b537ad945bc96ec2',
        'identity_idempotency_and_basis_fields': '9d87f21fcec3ef684dda3572e8e5865b51096829f2c2482ffb08d1bf9e6ce9f7',
        'shadow_and_test_scope_fail_closed': '3aaa19becec551cc9eb9b8396d3b33a87ed9072b0f186e66147fbc8cab4dbb8f',
    },
    'KL-015': {
        'transaction_owner_matrix_complete': '10458fc375a0982d6795c19a419999ebb27564fd146c95a092ea747bd54a0c30',
        'catalog_mapping_and_release_owner_boundaries_complete': '1bb1261aa5640da7fdbafa31812c91879b233ee116ee69e5ce91d7427b168bcc',
        'registry_lease_required_for_publish_commit_and_session_entry': '97d957a3cba60ae035c30df4be6b4b46d7af9737c03bb54e6104afe75a1be1ab',
        'preparation_work_stays_outside_coordination_locks': '64ecd2f92279e5e0d3d243c40fe929a48b29b36f56ebd78bacc153a38ec6e9ae',
        'factset_build_stays_outside_subject_coordination': '773498075ad55a7ac92ff672ae04c2897807bb3df7073de5b263449c21d26883',
        'subject_guard_required': '5e515f490a6d9b54621f3c55da06e9b324b60bc26b4b1016f10be31ae966da67',
        'complete_frozen_lock_order_enforced': 'd8b5fd7ff163fb58c5791cc61b01dd19280215bb49f7cf0c6fa693df757b8889',
        'multi_key_lock_order_is_stable': 'cd947a603d940b366393516120d0a870fdafaa69c6475a6ddb2b927a8913cda5',
        'reverse_lock_order_is_rejected': 'b3a61a67ef63c23dd263918530833bbafbe507e44e9874235130905b085bba46',
        'receipt_before_s01_is_rejected': '256fd5073276fe82812d6afc26d9ed7d4c2c6f754565d0ea596a2479fdbf0f2b',
        'artifact_identity_required': '746290a1755b3b563c7edf343230923aa43c362a018230a3fa1a40cbebae9266',
        'direct_write_bypass_rejected': 'b10f700f6c090f6bae91f9b3a9b25906fff8bb1a68564a6b38b652519cbdc671',
        'event_outbox_atomicity_enforced': '63a96e4486095e240fd1e080195ae8772386e02ce96f56393712276104a1a1c8',
        'outbox_dispatcher_does_not_lock_subject_guard': '78493bf5b16948e2cccc8796cd05e45d4680d19edc94138b4d9bbcc17b249366',
        'stale_fence_commit_is_rejected': '54e6aefccb148342b7d39003e1045035c8022e22f45d189f4fa045ca1f25401c',
        'dispatch_first_winner_and_replay_non_resend': '81a0efb991b343baab90742c8bea62f6a1ebf492cda0b48f3ad9ddf7d5fa0b6a',
        'ack_loss_replay_preserves_natural_uniqueness': '283df1d589323633f8302d397e5ad617f267c60935359eac5173e153ea3d1508',
        't6_ack_loss_replay_returns_same_issuance': 'db76c689857128c515c6137642cd189798105ff029a4686e36615f6a02329703',
        'transaction_db_conformance_passes': 'c0a56d2f9acecef30bd5715fe72a4bcb10866cec4702893f213c0a39da40b576',
        'harness_validation_passes': '2dbb33f46e379c228225cd02bc8afdf39689c54008b8ca7b1b019e0d2c4139bf',
    },
    'KL-016': {
        'shared_gate_command_matrix_fails_closed': '0711c176d2c1b0487c4f1a22ac3afcec93ef50b9de9bf3478b1db62b0f4a5a03',
        'reauthorize_shared_gate_precedes_s01_and_fails_closed': 'ea48e409c531b8bc1156140e0ce093f9247d6ad73516c93996cd46694d5fbb52',
        'continue_session_rechecks_shared_gate_and_fails_closed': '600456a617778faff3e8c22156c9bac3a1c0ff93db1bb59ff9f32493465242d3',
        'exclusive_global_gate_serializes': 'd2fc834e2bd924a37c3fe180e687519cd17f13bc09cdf005a5c0aa43bfed9f53',
        'revoke_artifact_atomic_linearization_and_idempotency': '46b9c47de463a4fec8445b3c89b788c578679d49e4f9e3ea71f014649db233d5',
        'registry_unavailable_or_timeout_denies': '487d7388e3d5583b58d6484235b7f9a811788c8d9f6f10b5a5f317846b5aad79',
        'global_revoke_never_locks_s01': '5edfb2de841a8afab3bf324945860139af75c0b1fa7581eef2c91c1f991c7fd9',
        'stop_has_no_registry_dependency': 'ec49d6b0473172e218ff75d07e437af29de62520db520050f0ed91e584b27a16',
        'safety_registry_db_regressions_pass': 'df141dcc2acec0f58fcf4932e9c3ba9c1186a0bef529e3658f787b6d1ad124f1',
        'harness_validation_passes': '2dbb33f46e379c228225cd02bc8afdf39689c54008b8ca7b1b019e0d2c4139bf',
    },
    'KL-017': {
        'subject_namespace_isolation': 'f4372d9ad4ad1395f9fbf07611ba68813e0c46de01249de56e312f3731f7e2ff',
        'test_authorization_is_isolated': 'f89d192eedb9c346bcaa7ef047a859e8c0cb6d462e42d018e2a5b0e6ae5392ab',
        'evaluation_storage_is_isolated': 'e3b35eaae47e664a203bf700ce4f28a796e7787226faf92146673ce2b80015e6',
        'application_role_scope_enforced': 'a1b2c42c5c8aed9e3caa1ad43404aabde2d449a2fe0a6294637449977baad975',
        'subject_isolation_e2e_passes': '2c6c1aed417611a457c2eda86771cb0a8dee38db398311f940b7b3c7b5b775f1',
        'cross_subject_denial_is_non_enumerating': 'a1a5fccddd0d93ee54ff8f118732452c977ce234439593acefb1a32a27089bd4',
        'complete_db_suite_passes': 'd2817afbc8d3369de8f81ac185dae69176d64b715714d532059f1f5ceb59f4b6',
    },
    'KL-018': {
        'artifact_registry_successor_migration_chain': '330fc8082d050d343039e4664acdabcd8375969bb8b08657c83f9b73e65873ba',
        'artifact_identity_is_immutable': '5a5d6976957b081e045743ba114df6e8aebf782c4cc66123026dafbee59456eb',
        'artifact_dependency_closure_required': '6f69a7171def4c61b7d7390a0272495b2ddd75b5902375447cc9aac410def2ce',
        'artifact_dependencies_must_be_pre_registered': '935e593ad9d7d2bdf05257326866c139e2ff4471ea0f2fdffee1e01adc1a087d',
        'artifact_dependency_graph_is_acyclic': '2db1302d2bd5319910e6c9aa9d861fa8f3ef1c7d9f4d2f813fe229f72f915960',
        'artifact_dependency_closure_is_bounded': '18805edc8865ec58437c7752aad50ac34d685c55c487e0baf0d7cff12f91bd9e',
        'artifact_registration_requires_management_capability': 'a5cf669fce9470c22d98c1e3c786b73e63a6c8d278de4aec2a19f839013755e4',
        'artifact_registration_command_routine_privileges_enforced': '226da89307321450f86d10347284e6b5f2972b95ecd9cf76a270cdbec833ed70',
        'artifact_registration_session_authority_enforced': 'ac6e147d90503ca0634a97e83bac1d6a65699040e5bbfcabd5602b1978665bb3',
        'artifact_registration_uses_exclusive_registry_gate': '99d8388734ed54c72c4228f8a0307bb383be2221f6943d64fa90d7d463602ee5',
        'artifact_registration_direct_write_rejected': 'a975ba38dec8f823adb5b367e0b74155f6d1940eb442c04006b01c16909409af',
        'unregistered_or_revoked_artifact_denied': 'e45c0d2b3765a6e2a9a8534b21410a02c67f270a8a9f33c1ed5bec6b22deb4cb',
        't3_t6_t7_require_artifact_refs': 'b4ef957a9ee368b6e074fa04ab340490904927371239ab0f42244ad22f5c4d6e',
        'artifact_registry_db_constraints_pass': '1e20c4a67b42583177a1175ebb86fc0ddd370a50256b56f56c5a4c1e7def31fb',
        'artifact_contract_unit_suite_passes': 'b63c11a97dbcc7b9ee50590bceb7841d5d08aae30b1042d85f98d6301174e934',
        'artifact_validity_is_null_total': '1e5934aedb85f773768f800e529a109952dce44d3895691e7329da51da3b566b',
        'artifact_timeless_policy_is_registered_dependency': '3ec0ce43558c22345c347312aae9fb85dce5a083405142f42a809e875f7e8743',
        'artifact_persistence_denials_are_stable': '337104968a84b1e522659aeb2e9cfb755a05ce637a64a3210eecf9d7260d379f',
        'artifact_dependency_dense_graph_is_bounded': '0a75079f107813f3f21078e82d35c6bc568cd5f6810b8137dd5780b19729198d',
        'artifact_registration_lock_timeout_is_atomic': '99ef0ba4580989d953e45e00e54b9d6d7f6b2fced3c5f96cf21614d939e5e89b',
        'artifact_registration_post_write_failure_is_atomic': 'e1c9e30faf89313ea32a608df635836d89c9f206ca0b927ee16616776812ae10',
        'artifact_registration_safety_registry_privilege_regression': '36b43e170c7c766e11382a4c429b0fb94967db88aabf33e86b3ef953c36a0d9f',
        'complete_db_suite_passes': '12f8a9f03fdd1117803e5bbc1de8e614014f2ffab173b4142850d4770ac32464',
        'harness_validation_passes': '2dbb33f46e379c228225cd02bc8afdf39689c54008b8ca7b1b019e0d2c4139bf',
    },
    'KL-055': {
        'provider_and_stream_ids_are_canonical': '693c802ea77603a2d4ee8291c782087a85252ba06ef5d7528a1ca849a830f0ed',
        'evidence_provenance_and_times_required': '07532bee2529ee6ec92c3281c672a9d950ec48fde21b9e4dacac0ec745bb133e',
        'server_assigns_known_at': '085f0303e26e3db855a4d98e10045728db0a2315471f90fdeb45a6772c0d5817',
        'provider_has_no_fact_or_command_authority': 'f27587ee00c780744299d5453b8f4f13d1a62f2761456327e63f74ca12c181f8',
        'transport_health_differs_from_coverage': 'efa0aed772b80aa91847c5ff4fb64ccb2eb0fb421417fd40d2daf1cac757e931',
        'provider_contract_is_hermetic': '2b8ae59751721aee491edd4edbcf29963ca48d423ccd0e1ab2f51ff82103a951',
        'provider_fixtures_pass_hardened_synthetic_guard': '9e43a2e97f8003ad08480ad0e884d95c0ef98d157d8b47fec71c1fa81614bd61',
        'provider_subject_source_binding_is_trusted': '637472b15b54f1458b5a374a0450efa1150dc4c5bf2475fffd116bc9da9bbbd6',
        'evidence_envelope_closed_s09_schema': '58d01940cbf7e04eaff82daf085c1a003089ad46efa7f01dade5c8ee56ee7ec7',
        'provider_credentials_do_not_cross_evidence_or_diagnostic_boundary': 'dda6bb6c86340f6ebb62a8854ae9add3b8832cad3f332bf59a4051133ec4622b',
    },
}
for _task_id, _contracts in M2_CRITICAL_CONTRACT_DIGESTS.items():
    M2_REQUIRED_CHECK_IDS.setdefault(_task_id, set()).update(_contracts)
KL014_REQUIRED_COMMAND_SURFACE = [
    'T1: ReceiveEvidence',
    'T1-PREPARATION (outside T1): RecordCandidate',
    ('T2-IN: DecideAssociation, DecideAdmission, AcceptFactRevision, ApplyControl, '
     'ClearControl, ApproveChange, ActivateApprovedProgram, RecordActualExecution, '
     'CompleteReportedWorkout'),
    'BUILD-PREPARATION (outside T2): BeginBuild, WriteCandidate, CompleteFactset',
    'T2-SEAL: SealFactset',
    'REGISTRY-MANAGEMENT (outside T2-GLOBAL): RegisterArtifact',
    'T2-GLOBAL: RevokeArtifact',
    'T3-PREPARATION (outside T3): RecordProjection, BuildManifest',
    'T3: PublishManifest',
    'T4: AdmitOrReviseIntent, CancelIntent',
    'T5: AcquireLease, RenewLease, ReserveCall, PermitDispatch',
    ('T5-PREPARATION (outside T5): RecordToolResult, RecordProposal, '
     'RecordDemandFeatures'),
    'T6-PREPARATION (outside T6): ResolveEvidence, RecordValidation',
    'T6: CommitBundle, Reauthorize',
    'T7: StartSession, ResumeSession, ContinueSession',
    'T8: SettleCall, MarkUnknown, ReapIntent; CancelIntent is shared with T4',
    'Results: one typed success result per public command plus CommandRejected',
    ('Internal-only: IssueAuthorization, InvalidateAuthorization, RecordSnapshot, '
     'AdvanceAttempt, CancelUndispatched'),
]
KL072_REQUIRED_COMMAND_SURFACE = [
    'PublishManifest',
    'CommitBundle',
    'Reauthorize',
    'StartSession',
    'ResumeSession',
    'ContinueSession',
    'RevokeArtifact',
]
KL016_REQUIRED_COMMAND_SURFACE = [
    'RevokeArtifact',
    'PublishManifest',
    'CommitBundle',
    'Reauthorize',
    'StartSession',
    'ResumeSession',
    'ContinueSession',
]
M2_REQUIRED_SECURITY_REVIEWS = {'KL-014', 'KL-017', 'KL-018', 'KL-055', 'KL-072'}
M1_CLEAN_START_CHECKS = {
    'compose_config_valid': (
        'PYTHONPATH="$PWD/src" '
        '/Users/davetian/Personal_Projects/KineticLoop/.venv/bin/python '
        'tools/db/verify.py compose-config-valid'),
    'postgres_ready': (
        'PYTHONPATH="$PWD/src" '
        '/Users/davetian/Personal_Projects/KineticLoop/.venv/bin/python '
        'tools/db/verify.py postgres-ready'),
}
M1_CLEAN_START_RELEVANT_PATHS = [
    'compose.yaml',
    'pyproject.toml',
    'uv.lock',
    'src/kineticloop/cli.py',
    'src/kineticloop/db/**',
    'tools/db/verify.py',
]
M2_REQUIRED_DB_REVIEWS = {
    'KL-010', 'KL-011', 'KL-012', 'KL-013', 'KL-014',
    'KL-015', 'KL-016', 'KL-017', 'KL-018', 'KL-072',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(path):
    return (isinstance(path, str) and bool(path) and '\\' not in path
            and all(p not in ('', '.', '..') for p in path.split('/')))


def matches(path, patterns):
    """Match glob components; * cannot cross / and ** matches whole directories."""
    if not relative_path(path):
        return False

    def match(parts, pattern):
        if not pattern:
            return not parts
        if pattern[0] == '**':
            return match(parts, pattern[1:]) or bool(parts and match(parts[1:], pattern))
        return bool(parts and fnmatch.fnmatchcase(parts[0], pattern[0])
                    and match(parts[1:], pattern[1:]))

    return any(relative_path(p) and match(path.split('/'), p.split('/')) for p in patterns)


def unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate-key:' + str(key))
        result[key] = value
    return result


def load_artifact_text(text, suffix):
    if suffix == '.json':
        return json.loads(text, object_pairs_hook=unique_mapping)
    import yaml

    class StrictLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        loader.flatten_mapping(node)
        return unique_mapping((loader.construct_object(k), loader.construct_object(v))
                              for k, v in node.value)

    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        return yaml.load(text, Loader=StrictLoader)
    except yaml.YAMLError as ex:
        raise ValueError('yaml-parse:' + str(ex)) from ex


def load_artifact(path):
    return load_artifact_text(path.read_text(), path.suffix)


def load_artifact_at_revision(root, path, revision):
    return load_artifact_text(
        git(root, 'show', revision + ':' + path).decode(),
        Path(path).suffix,
    )


def blob_sha_at_revision(root, path, revision):
    return hashlib.sha256(git(root, 'show', revision + ':' + path)).hexdigest()


def blob_size_at_revision(root, path, revision):
    return len(git(root, 'show', revision + ':' + path))


def section(text, heading):
    match = re.search(r'^## ' + re.escape(heading) + r'\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    return match.group(1) if match else None


def subsection(text, heading):
    match = re.search(r'^### ' + re.escape(heading) + r'\s*\n(.*?)(?=^## |^### |\Z)',
                      text, re.M | re.S)
    return match.group(1) if match else None


def bullets(text):
    return [line[2:].strip() for line in text.splitlines() if line.startswith('- ')]


def packet_errors(task, text):
    errors = []
    name = task['id']
    if task['task_identity'] not in text:
        errors.append('packet-identity:' + name)
    if task['status'] == 'SUPERSEDED':
        return errors
    if task['title'] not in text:
        errors.append('packet-title:' + name)
    deps = section(text, 'Dependencies')
    if deps is None or set(re.findall(r'KL-[0-9]{3}[A-Z]?', deps.split('### Conditional dependencies')[0])) != set(task['depends_on']):
        errors.append('packet-deps:' + name)
    conditional = subsection(text, 'Conditional dependencies')
    expected_conditional = {
        dependency if isinstance(dependency, str)
        else dependency['task_id'] + ' when ' + dependency['condition']
        for dependency in task.get('conditional_depends_on', [])
    }
    found_conditional = set() if conditional is None else {
        value for value in bullets(conditional) if value != 'none'
    }
    if conditional is None or found_conditional != expected_conditional:
        errors.append('packet-conditional-deps:' + name)
    checks = section(text, 'Checks required for this task PR')
    if checks is None or sorted(bullets(checks)) != sorted(task['checks_required_for_this_task']):
        errors.append('packet-checks:' + name)
    if name in M2_REFINED_TASK_IDS:
        read_first = section(text, 'Read first') or ''
        if bullets(read_first) != task.get('context_files', []):
            errors.append('packet-context-files:' + name)
        entry = section(text, 'Entry conditions') or ''
        expected_entry = [value.replace(
            'docs/exec-plans/milestones/M1.json',
            '`docs/exec-plans/milestones/M1.json`',
        ) for value in task.get('entry_conditions', [])]
        if bullets(entry) != expected_entry:
            errors.append('packet-entry-condition:' + name)
        impact = section(text, 'Frozen impact map') or ''
        impact_fields = {
            'Invariants': task.get('invariant_ids', []),
            'Transactions': task.get('transaction_boundaries', []),
            'Logical tables': task.get('table_ids', []),
        }
        for label, expected in impact_fields.items():
            match = re.search(r'^- ' + re.escape(label) + r':\s*(.*)$', impact, re.M)
            found = [] if not match or match.group(1).strip() == 'none' else [
                value.strip() for value in match.group(1).split(',') if value.strip()
            ]
            if found != expected:
                errors.append('packet-impact-map:' + name + ':' + label.lower().replace(' ', '-'))
        deliverables = section(text, 'Deliverables') or ''
        if bullets(deliverables) != task.get('deliverables', []):
            errors.append('packet-deliverables:' + name)
        definition = (section(text, 'Definition of Done') or '').strip()
        if definition != task.get('definition_of_done', ''):
            errors.append('packet-definition-of-done:' + name)
        contract_section = section(text, 'Machine-readable check contract') or ''
        contract_match = re.search(r'```json\s*(\{.*?\})\s*```', contract_section, re.S)
        if not contract_match:
            errors.append('packet-check-contract:' + name)
        else:
            try:
                packet_contract = json.loads(
                    contract_match.group(1), object_pairs_hook=unique_mapping)
                expected_contract = {
                    'check_contracts': task.get('check_contracts'),
                    'evidence_paths': task.get('evidence_paths'),
                }
                if packet_contract != expected_contract:
                    errors.append('packet-check-contract:' + name)
            except (ValueError, TypeError):
                errors.append('packet-check-contract:' + name)
    if task.get('write_paths_status') == 'ENFORCEABLE':
        scope = section(text, 'Resource / write isolation') or ''
        resource_block = re.search(r'^Resource keys:\s*\n((?:- [^\n]+\n?)+)', scope, re.M)
        expected_resources = set(task.get('resource_keys', []))
        found_resources = set() if not resource_block else {
            value for value in bullets(resource_block.group(1)) if value != 'none'
        }
        if found_resources != expected_resources:
            errors.append('packet-resource-keys:' + name)
        write_block = re.search(
            r'^Expected (?:implementation )?write paths:\s*\n((?:- [^\n]+\n?)+)',
            scope,
            re.M,
        )
        if not write_block or sorted(bullets(write_block.group(1))) != sorted(task['write_paths']):
            errors.append('packet-write-paths:' + name)
        environment_block = re.search(
            r'^Environment requirements:\s*\n((?:- [^\n]+\n?)+)', scope, re.M)
        found_environment = [] if not environment_block else [
            value for value in bullets(environment_block.group(1)) if value != 'none'
        ]
        if found_environment != task.get('environment_requirements', []):
            errors.append('packet-environment:' + name)
        policy = re.search(r'^Parallel write policy: \*\*([^*]+)\*\*', scope, re.M)
        if not policy or policy.group(1) != task.get('parallel_write_policy'):
            errors.append('packet-parallel-policy:' + name)
        if name == 'KL-072':
            hotspot = re.search(r'^Shared hotspot: \*\*(true|false)\*\*', scope, re.M)
            expected_hotspot = str(task.get('shared_hotspot', False)).lower()
            if not hotspot or hotspot.group(1) != expected_hotspot:
                errors.append('packet-shared-hotspot:' + name)
    if name == 'KL-014':
        command_surface = section(text, 'Public command surface') or ''
        if bullets(command_surface) != task.get('commands', []):
            errors.append('packet-command-surface:' + name)
    if name in {'KL-016', 'KL-072'}:
        command_surface = section(text, 'Registry-gated command surface') or ''
        if bullets(command_surface) != task.get('commands', []):
            errors.append('packet-command-surface:' + name)
    return errors


def git(root, *args):
    proc = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if proc.returncode:
        raise ValueError('git:' + proc.stderr.decode(errors='replace').strip())
    return proc.stdout


def resolve(root, ref):
    # --end-of-options prevents a user-supplied ref from becoming a Git option.
    return git(root, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()


def tree_object(root, commit):
    """Return the complete Git tree object ID for an already-resolved commit."""
    return git(root, 'rev-parse', '--verify', '--end-of-options', commit + '^{tree}').decode().strip()


def changed_paths(root, before, after):
    return git(root, 'diff', '--no-renames', '--name-only', '-z', before, after, '--').decode().split('\0')[:-1]


def is_ancestor(root, ancestor, descendant):
    return subprocess.run(
        ['git', 'merge-base', '--is-ancestor', ancestor, descendant],
        cwd=root, capture_output=True).returncode == 0


def result_paths(task_id):
    return [f'docs/exec-plans/completed/{task_id}_RESULT.{ext}' for ext in ('yaml', 'json')]


def result_paths_at_revision(root, task_id, revision):
    return [
        candidate for candidate in result_paths(task_id)
        if subprocess.run(
            ['git', 'cat-file', '-e', revision + ':' + candidate],
            cwd=root, capture_output=True).returncode == 0
    ]


def evidence_pattern(task_id):
    return f'docs/exec-plans/evidence/{task_id}/**'


def review_patterns(task_id):
    return [f'docs/exec-plans/reviews/{task_id}/**']


def governance_record_paths(change_id):
    return [f'docs/exec-plans/governance/{change_id}.{ext}' for ext in ('yaml', 'json')]


def governance_allowed_patterns(change_id):
    return [
        PROJECT_PLAN,
        BACKLOG,
        TRACEABILITY,
        INDEX,
        MANIFEST,
        GOVERNANCE_SCHEMA,
        INTEGRATION_SCHEMA,
        MILESTONE_CLOSURE_SCHEMA,
        '.github/workflows/**',
        'docs/exec-plans/active/**',
        f'docs/exec-plans/evidence/{change_id}/**',
        'docs/exec-plans/integrations/**',
        'docs/exec-plans/milestones/**',
        'docs/exec-plans/reviews/KL-*/**',
        f'docs/exec-plans/reviews/{change_id}/**',
        f'docs/exec-plans/governance/{change_id}.yaml',
        f'docs/exec-plans/governance/{change_id}.json',
        'docs/harness/**',
        'tests/harness/**',
        'tools/harness/**',
    ]


def traceability_projection(task, fields=TRACEABILITY_TASK_FIELDS):
    """Return the exact task-definition fields mirrored by this traceability version."""
    return {field: task.get(field) for field in fields}


def traceability_task_map(document, prefix='traceability'):
    """Validate traceability identity/index integrity without collapsing duplicates."""
    errors = []
    tasks = document.get('tasks') if isinstance(document, dict) else None
    if not isinstance(tasks, list):
        return [prefix + '-tasks'], {}
    by_identity = {}
    seen_ids = set()
    for position, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(prefix + '-task-shape:' + str(position))
            continue
        identity, task_id = task.get('task_identity'), task.get('id')
        if not isinstance(identity, str) or not identity:
            errors.append(prefix + '-task-identity:' + str(position))
            continue
        if not isinstance(task_id, str) or not re.fullmatch(r'KL-[0-9]{3}[A-Z]?', task_id):
            errors.append(prefix + '-task-id:' + identity)
            continue
        if identity != 'harness-backlog-v0.2/' + task_id:
            errors.append(prefix + '-task-identity-mismatch:' + identity)
        if identity in by_identity:
            errors.append(prefix + '-duplicate-task-identity:' + identity)
        else:
            by_identity[identity] = task
        if task_id in seen_ids:
            errors.append(prefix + '-duplicate-task-id:' + task_id)
        else:
            seen_ids.add(task_id)
    return errors, by_identity


def configure_ci_merge_gate(root, args):
    """Bind a PR checkout to one task result or one Harness governance record."""
    if not args.ci_pr_base or not args.ci_pr_head:
        raise ValueError('ci-revisions-required')
    base, head = resolve(root, args.ci_pr_base), resolve(root, args.ci_pr_head)
    if resolve(root, 'HEAD') != head:
        raise ValueError('ci-head-not-checked-out')
    git(root, 'merge-base', '--is-ancestor', base, head)
    task_candidates = []
    governance_candidates = []
    review_candidates = []
    for path in changed_paths(root, base, head):
        match = re.fullmatch(r'docs/exec-plans/completed/(KL-[0-9]{3}[A-Z]?)_RESULT\.(?:yaml|json)', path)
        if match:
            task_candidates.append(match.group(1))
        match = re.fullmatch(r'docs/exec-plans/governance/(HG-[0-9]{3})\.(?:yaml|json)', path)
        if match:
            governance_candidates.append(match.group(1))
        match = re.fullmatch(r'docs/exec-plans/reviews/(HG-[0-9]{3})/[A-Z_]+\.json', path)
        if match:
            review_candidates.append(match.group(1))
    task_ids, change_ids = set(task_candidates), set(governance_candidates)
    if not task_ids and not change_ids and len(set(review_candidates)) == 1:
        change_ids = set(review_candidates)
        args.governance_review_only = True
    if (len(task_ids), len(change_ids)) not in ((1, 0), (0, 1)):
        raise ValueError(f'ci-change-record-count:task={len(task_ids)},governance={len(change_ids)}')
    selected = next(iter(task_ids or change_ids))
    review_path = root / 'docs/exec-plans/reviews' / selected / 'GENERAL.json'
    if not review_path.is_file():
        raise ValueError('ci-general-review-missing:' + selected)
    review = load_artifact(review_path)
    if not isinstance(review, dict) or not isinstance(review.get('reviewed_head_sha'), str):
        raise ValueError('ci-general-review-invalid:' + selected)
    args.protected_base = base
    if task_ids:
        args.task_id = selected
        args.reviewed_head = review['reviewed_head_sha']
    else:
        args.governance_change_id = selected
        args.governance_reviewed_head = review['reviewed_head_sha']


def suffix_errors(
        root, start, end, task_id, kind, scope_patterns=None,
        allow_unrelated_merges=False):
    """Require ancestry and check every bookkeeping commit, including reverted changes."""
    errors = []
    try:
        start, end = resolve(root, start), resolve(root, end)
        git(root, 'merge-base', '--is-ancestor', start, end)
        commits = git(root, 'rev-list', '--reverse', start + '..' + end).decode().splitlines()
        allowed = review_patterns(task_id) if kind == 'review' else result_paths(task_id) + [evidence_pattern(task_id)]
        for commit in commits:
            parents = git(root, 'rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
            if len(parents) != 1 and not allow_unrelated_merges:
                errors.append(kind + '-suffix-merge:' + commit)
                continue
            if not parents:
                errors.append(kind + '-suffix-root:' + commit)
                continue
            for path in changed_paths(root, parents[0], commit):
                if (scope_patterns is not None
                        and not matches(path, scope_patterns)
                        and not matches(path, allowed)):
                    continue
                if not matches(path, allowed):
                    errors.append(kind + '-stale-change:' + path)
                elif kind == 'tested' and matches(path, [evidence_pattern(task_id)]):
                    exists = subprocess.run(['git', 'cat-file', '-e', parents[0] + ':' + path], cwd=root, capture_output=True)
                    if exists.returncode == 0:
                        errors.append('tested-evidence-not-addition:' + path)
    except ValueError as ex:
        errors.append(kind + '-revision:' + str(ex))
    return errors


def governance_suffix_errors(root, start, end, change_id, kind):
    """Restrict post-test and post-review governance bookkeeping commits."""
    errors = []
    try:
        start, end = resolve(root, start), resolve(root, end)
        git(root, 'merge-base', '--is-ancestor', start, end)
        commits = git(root, 'rev-list', '--reverse', start + '..' + end).decode().splitlines()
        allowed = (review_patterns(change_id) if kind == 'review'
                   else governance_record_paths(change_id) + [evidence_pattern(change_id)])
        for commit in commits:
            parents = git(root, 'rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
            if len(parents) != 1:
                tested_descendants = [
                    parent for parent in parents if is_ancestor(root, start, parent)
                ]
                prior_ancestors = [
                    parent for parent in parents if is_ancestor(root, parent, start)
                ]
                safe_tested_reintegration = (
                    kind == 'tested'
                    and len(parents) == 2
                    and len(tested_descendants) == 1
                    and len(prior_ancestors) == 1
                    and set(tested_descendants).isdisjoint(prior_ancestors)
                    and tree_object(root, commit) == tree_object(root, tested_descendants[0])
                )
                if safe_tested_reintegration:
                    continue
                errors.append('governance-' + kind + '-suffix-merge:' + commit)
                continue
            for path in changed_paths(root, parents[0], commit):
                if not matches(path, allowed):
                    errors.append('governance-' + kind + '-stale-change:' + path)
                elif kind == 'tested' and matches(path, [evidence_pattern(change_id)]):
                    exists = subprocess.run(
                        ['git', 'cat-file', '-e', parents[0] + ':' + path],
                        cwd=root, capture_output=True)
                    if exists.returncode == 0:
                        errors.append('governance-tested-evidence-not-addition:' + path)
    except ValueError as ex:
        errors.append('governance-' + kind + '-revision:' + str(ex))
    return errors


def evidence_exists(root, ref, revision=None):
    if not relative_path(ref):
        return False
    if revision is not None:
        return subprocess.run(
            ['git', 'cat-file', '-e', revision + ':' + ref],
            cwd=root, capture_output=True).returncode == 0
    path = root / ref
    return path.is_file() and root.resolve() in path.resolve().parents


def semantic_result_errors(obj, task, root, evidence_revision=None):
    errors = []
    if obj['task_identity'] != task['task_identity'] or obj['display_task_id'] != task['id']:
        errors.append('result-task-identity')
    if obj['task_status'] == 'PASS' and obj['task_checks_status'] != 'PASS':
        errors.append('pass-without-check-pass')
    commands = obj['commands_run']
    if obj['task_status'] == 'PASS' and not commands:
        errors.append('pass-empty-commands')
    check_ids = [c['check_id'] for c in commands]
    expected = set(task['checks_required_for_this_task'])
    if len(check_ids) != len(set(check_ids)) or set(check_ids) - expected:
        errors.append('result-check-ids')
    if obj['task_status'] == 'PASS' or obj['task_checks_status'] == 'PASS':
        if set(check_ids) != expected or any(c['result'] != 'PASS' for c in commands):
            errors.append('required-checks-not-pass')
    contracts = {
        item['check_id']: item for item in task.get('check_contracts', [])
        if isinstance(item, dict) and isinstance(item.get('check_id'), str)
    }
    for c in commands:
        contract = contracts.get(c['check_id'])
        if contract is not None and c.get('command') != contract.get('command'):
            errors.append('command-contract-command:' + c['check_id'])
        evidence_ref = c.get('evidence_ref')
        if (contract is not None and task.get('evidence_paths')
                and not isinstance(evidence_ref, str)):
            errors.append('command-evidence-scope:' + c['check_id'])
        elif (contract is not None and task.get('evidence_paths')
              and not matches(evidence_ref, task['evidence_paths'])):
            errors.append('command-evidence-scope:' + c['check_id'])
        if (c['result'] in ('PASS', 'FAIL')
                and not evidence_exists(root, evidence_ref, evidence_revision)):
            errors.append('command-evidence:' + c['check_id'])
    for requirement in obj['requirements_covered']:
        if requirement['status'] in ('PASS', 'APPROVED_NA'):
            if not evidence_exists(root, requirement.get('evidence_ref'), evidence_revision):
                errors.append('requirement-evidence:' + requirement['requirement_id'])
            if requirement.get('tested_commit') != obj['tested_commit']:
                errors.append('requirement-revision:' + requirement['requirement_id'])
            if '@' not in requirement['requirement_id']:
                errors.append('requirement-layer:' + requirement['requirement_id'])
    return errors


def requirement_ids(root):
    """Expand all requirement sources to concrete ID@layer obligations."""
    ids = set()
    sources = load_artifact(root / 'CURRENT_REQUIREMENT_SET.json')['sources']
    for source in sources:
        data = load_artifact(root / source['path'])
        for entry in data.get('original_layer_obligations', []):
            ids.add(entry['obligation_id'])
        for group in ('supplemental_boundary_requirements', 'interleaving_requirements', 'requirements'):
            for entry in data.get(group, []):
                name = entry.get('requirement_id', entry.get('id'))
                ids.update(name + '@' + layer for layer in entry['layers'])
    return ids


def hash_refresh_errors(root, base_revision, name, task, changed, protected_paths):
    """Only change hashes/byte counts of already-indexed, authorized changed files."""
    old = json.loads(git(root, 'show', base_revision + ':' + name))
    new = load_artifact(root / name)
    errors = []
    groups = ('documents', 'machine_readable') if name == INDEX else ('files',)
    old_meta = {k: v for k, v in old.items() if k not in groups}
    new_meta = {k: v for k, v in new.items() if k not in groups}
    if old_meta != new_meta:
        errors.append('derived-index-metadata:' + name)
    for group in groups:
        before, after = old.get(group, []), new.get(group, [])
        if [e['path'] for e in before] != [e['path'] for e in after]:
            errors.append('derived-index-paths:' + name)
            continue
        for previous, current in zip(before, after):
            if previous == current:
                continue
            path = previous['path']
            permitted = (path not in protected_paths and path in changed
                         and (matches(path, task['write_paths']) or (name == MANIFEST and path == INDEX)))
            if not permitted:
                errors.append('derived-index-unauthorized:' + path)
                continue
            if {k: v for k, v in previous.items() if k not in ('sha256', 'bytes')} != {k: v for k, v in current.items() if k not in ('sha256', 'bytes')}:
                errors.append('derived-index-entry:' + path)
            target = root / path
            if not target.is_file() or current.get('sha256') != sha(target):
                errors.append('derived-index-hash:' + path)
            if 'bytes' in current and (not target.is_file() or current['bytes'] != target.stat().st_size):
                errors.append('derived-index-bytes:' + path)
    return errors


def governance_index_errors(
        root, base_revision, record, changed, protected_paths, target_revision=None):
    """Allow declared additions while preserving every existing authority identity."""
    old = json.loads(git(root, 'show', base_revision + ':' + INDEX))
    new = (load_artifact_at_revision(root, INDEX, target_revision)
           if target_revision else load_artifact(root / INDEX))
    errors = []
    if {k: v for k, v in old.items() if k not in ('documents', 'machine_readable')} != {
            k: v for k, v in new.items() if k not in ('documents', 'machine_readable')}:
        errors.append('governance-index-metadata')
    declared_additions = set(record.get('authority_entries_added', []))
    observed_additions = set()
    after_paths = [
        entry['path']
        for group in ('documents', 'machine_readable')
        for entry in new.get(group, [])
    ]
    if len(after_paths) != len(set(after_paths)):
        errors.append('governance-index-duplicate-path')
    document_ids = [entry['document_id'] for entry in new.get('documents', [])]
    if len(document_ids) != len(set(document_ids)):
        errors.append('governance-index-duplicate-id')
    for group in ('documents', 'machine_readable'):
        before = {entry['path']: entry for entry in old.get(group, [])}
        after = {entry['path']: entry for entry in new.get(group, [])}
        removed = set(before) - set(after)
        if removed:
            errors.extend('governance-index-removal:' + path for path in sorted(removed))
        observed_additions |= set(after) - set(before)
        for path in sorted(set(before) & set(after)):
            previous, current = before[path], after[path]
            if target_revision:
                try:
                    target_valid = (
                        current.get('sha256')
                        == blob_sha_at_revision(root, path, target_revision)
                    )
                except ValueError:
                    target_valid = False
                if not target_valid:
                    errors.append('governance-index-hash:' + path)
            if previous == current:
                continue
            if path in protected_paths:
                errors.append('governance-index-frozen:' + path)
                continue
            if {k: v for k, v in previous.items() if k != 'sha256'} != {
                    k: v for k, v in current.items() if k != 'sha256'}:
                errors.append('governance-index-entry:' + path)
            if not target_revision:
                target_valid = (
                    (root / path).is_file()
                    and current.get('sha256') == sha(root / path)
                )
            if path not in changed or (not target_revision and not target_valid):
                errors.append('governance-index-hash:' + path)
        for path in sorted(set(after) - set(before)):
            current = after[path]
            if path not in declared_additions:
                errors.append('governance-index-undeclared-addition:' + path)
            try:
                target_valid = (
                    current.get('sha256') == blob_sha_at_revision(root, path, target_revision)
                    if target_revision else
                    (root / path).is_file() and current.get('sha256') == sha(root / path)
                )
            except ValueError:
                target_valid = False
            if path in protected_paths or not target_valid:
                errors.append('governance-index-addition-hash:' + path)
    if observed_additions != declared_additions:
        errors.append('governance-index-additions-mismatch')
    return errors


def task_index_authority_errors(root, base_revision, task, changed, protected_paths):
    """Permit a baseline-authorized index owner to add only files in its write scope."""
    old = json.loads(git(root, 'show', base_revision + ':' + INDEX))
    new = load_artifact(root / INDEX)
    errors = []
    if {k: v for k, v in old.items() if k not in ('documents', 'machine_readable')} != {
            k: v for k, v in new.items() if k not in ('documents', 'machine_readable')}:
        errors.append('authority-index-metadata')
    for group in ('documents', 'machine_readable'):
        before = {entry['path']: entry for entry in old.get(group, [])}
        after = {entry['path']: entry for entry in new.get(group, [])}
        for path in sorted(set(before) - set(after)):
            errors.append('authority-index-removal:' + path)
        for path, current in after.items():
            target = root / path
            if path in before:
                previous = before[path]
                if previous == current:
                    continue
                if path in protected_paths:
                    errors.append('authority-index-frozen:' + path)
                if {k: v for k, v in previous.items() if k != 'sha256'} != {
                        k: v for k, v in current.items() if k != 'sha256'}:
                    errors.append('authority-index-entry:' + path)
                if path not in changed or not matches(path, task['write_paths']):
                    errors.append('authority-index-unauthorized:' + path)
            elif path in protected_paths or not matches(path, task['write_paths']):
                errors.append('authority-index-addition:' + path)
            if (path not in before or before[path] != current) and (
                    not target.is_file() or current.get('sha256') != sha(target)):
                errors.append('authority-index-hash:' + path)
    return errors


def governance_manifest_errors(root, base_revision, changed, target_revision=None):
    """Refresh existing entries and append changed, hashed governance artifacts."""
    old = json.loads(git(root, 'show', base_revision + ':' + MANIFEST))
    new = (load_artifact_at_revision(root, MANIFEST, target_revision)
           if target_revision else load_artifact(root / MANIFEST))
    errors = []
    if {k: v for k, v in old.items() if k != 'files'} != {k: v for k, v in new.items() if k != 'files'}:
        errors.append('governance-manifest-metadata')
    before, after = old.get('files', []), new.get('files', [])
    before_paths = [entry['path'] for entry in before]
    after_paths = [entry['path'] for entry in after]
    if (after_paths[:len(before_paths)] != before_paths
            or len(after_paths) != len(set(after_paths))):
        errors.append('governance-manifest-paths')
        return errors
    for previous, current in zip(before, after):
        path = previous['path']
        if target_revision:
            try:
                target_hash = blob_sha_at_revision(root, path, target_revision)
                target_size = blob_size_at_revision(root, path, target_revision)
            except ValueError:
                target_hash, target_size = None, None
            if current.get('sha256') != target_hash:
                errors.append('governance-manifest-hash:' + path)
            if 'bytes' in current and current['bytes'] != target_size:
                errors.append('governance-manifest-bytes:' + path)
        if previous == current:
            continue
        if {k: v for k, v in previous.items() if k not in ('sha256', 'bytes')} != {
                k: v for k, v in current.items() if k not in ('sha256', 'bytes')}:
            errors.append('governance-manifest-entry:' + path)
        if not target_revision:
            target_hash = sha(root / path) if (root / path).is_file() else None
            target_size = ((root / path).stat().st_size
                           if (root / path).is_file() else None)
        if path not in changed or (not target_revision
                                   and current.get('sha256') != target_hash):
            errors.append('governance-manifest-hash:' + path)
        if (not target_revision and 'bytes' in current
                and current['bytes'] != target_size):
            errors.append('governance-manifest-bytes:' + path)
    for current in after[len(before):]:
        path = current['path']
        try:
            target_hash = (
                blob_sha_at_revision(root, path, target_revision)
                if target_revision else sha(root / path)
            )
            target_size = (
                blob_size_at_revision(root, path, target_revision)
                if target_revision else (root / path).stat().st_size
            )
        except (ValueError, OSError):
            target_hash, target_size = None, None
        if path not in changed or current.get('sha256') != target_hash:
            errors.append('governance-manifest-addition:' + path)
        if 'bytes' in current and current['bytes'] != target_size:
            errors.append('governance-manifest-bytes:' + path)
    return errors


def integration_record_errors(
        root, path, record, schema, result_schema, review_schema, tasks):
    errors = ['integration-schema:' + path.name + ':' + issue.message
              for issue in schema.iter_errors(record)]
    if errors:
        return errors
    task_id = record['display_task_id']
    task = tasks.get(task_id)
    if not task or task['task_identity'] != record['task_identity'] or path.stem != task_id:
        return ['integration-identity:' + path.name]
    try:
        result_commit = resolve(root, record['result_commit'])
        reviewed = resolve(root, record['reviewed_head_sha'])
        review_commit = resolve(root, record['review_record_commit'])
        merge_commit = resolve(root, record['merge_commit'])
        head = resolve(root, 'HEAD')
        for before, after, label in (
                (result_commit, reviewed, 'result-to-reviewed'),
                (reviewed, review_commit, 'reviewed-to-review-record'),
                (merge_commit, head, 'merge-to-head')):
            try:
                git(root, 'merge-base', '--is-ancestor', before, after)
            except ValueError:
                errors.append('integration-ancestry:' + task_id + ':' + label)
        try:
            git(root, 'merge-base', '--is-ancestor', review_commit, merge_commit)
        except ValueError:
            exact_tree_squash = tree_object(root, review_commit) == tree_object(root, merge_commit)
            delayed_post_merge_review = (
                reviewed == merge_commit
                and is_ancestor(root, merge_commit, review_commit)
            )
            if not exact_tree_squash and not delayed_post_merge_review:
                errors.append('integration-ancestry-or-exact-tree:' + task_id + ':review-to-merge')
        else:
            delayed_post_merge_review = False
        result_paths_at_commit = result_paths_at_revision(root, task_id, result_commit)
        result_paths_at_review = result_paths_at_revision(root, task_id, reviewed)
        if len(result_paths_at_commit) != 1:
            errors.append(
                'integration-result-representation-count:' + task_id + ':'
                + str(len(result_paths_at_commit)))
        if len(result_paths_at_review) != 1:
            errors.append(
                'integration-reviewed-result-representation-count:' + task_id + ':'
                + str(len(result_paths_at_review)))
        if len(result_paths_at_commit) == 1 and len(result_paths_at_review) == 1:
            result_path = result_paths_at_commit[0]
            reviewed_result_path = result_paths_at_review[0]
            if result_path != reviewed_result_path:
                errors.append('integration-result-path-mismatch:' + task_id)
            result_bytes = git(root, 'show', result_commit + ':' + result_path)
            reviewed_result_bytes = git(root, 'show', reviewed + ':' + reviewed_result_path)
            if result_bytes != reviewed_result_bytes:
                errors.append('integration-result-content-mismatch:' + task_id)
            result = load_artifact_text(
                result_bytes.decode(),
                Path(result_path).suffix)
            issues = list(result_schema.iter_errors(result))
            errors.extend('integration-result-schema:' + task_id + ':' + issue.message
                          for issue in issues)
            if not issues:
                if (result.get('display_task_id') != task_id
                        or result.get('task_identity') != record['task_identity']):
                    errors.append('integration-result-identity:' + task_id)
                if result['task_status'] != 'PASS':
                    errors.append('integration-result-not-pass:' + task_id)
                errors.extend(
                    'integration-result-semantic:' + task_id + ':' + issue
                    for issue in semantic_result_errors(
                        result, task, root, evidence_revision=reviewed))
                result_base = resolve(root, result['base_commit'])
                tested = resolve(root, result['tested_commit'])
                if not is_ancestor(root, result_base, tested):
                    errors.append('integration-result-base-tested-ancestry:' + task_id)
                errors.extend(
                    'integration-' + issue
                    for issue in suffix_errors(
                        root, tested, reviewed, task_id, 'tested',
                        task['write_paths'] + [f'docs/exec-plans/active/{task_id}.md']))
                delayed_scope = (
                    [path for path in task['write_paths'] if path not in (INDEX, MANIFEST)]
                    + result_paths(task_id)
                    + [evidence_pattern(task_id), f'docs/exec-plans/active/{task_id}.md']
                )
                if delayed_post_merge_review:
                    errors.extend(
                        'integration-delayed-' + issue
                        for issue in suffix_errors(
                            root, reviewed, review_commit, task_id, 'review',
                            delayed_scope, allow_unrelated_merges=True))
                else:
                    errors.extend(
                        'integration-' + issue
                        for issue in suffix_errors(
                            root, reviewed, review_commit, task_id, 'review'))
        for review_type in task['review_requirements']:
            review_path = f'docs/exec-plans/reviews/{task_id}/{review_type}.json'
            review = load_artifact_text(
                git(root, 'show', review_commit + ':' + review_path).decode(), '.json')
            review_issues = list(review_schema.iter_errors(review))
            errors.extend(
                'integration-review-schema:' + task_id + ':' + review_type + ':' + issue.message
                for issue in review_issues)
            if review_issues:
                continue
            if review.get('task_identity') != task['task_identity']:
                errors.append('integration-review-identity:' + task_id + ':' + review_type)
            if (review.get('review_type') != review_type
                    or review.get('status') != 'PASS'
                    or resolve(root, review.get('reviewed_head_sha', '')) != reviewed):
                errors.append('integration-review-binding:' + task_id + ':' + review_type)
            for ref in review.get('evidence_refs', []):
                if not evidence_exists(root, ref, reviewed):
                    errors.append(
                        'integration-review-evidence:' + task_id + ':' + review_type + ':' + ref)
    except ValueError as ex:
        errors.append('integration-revision:' + task_id + ':' + str(ex))
    return errors


def milestone_closure_errors(
        root, closure, schema, integration_schema, result_schema, review_schema, backlog, tasks):
    """Validate the M1 closure as revision-bound evidence, not a status assertion."""
    errors = [
        'milestone-schema:M1.json:' + issue.message
        for issue in schema.iter_errors(closure)
    ]
    if errors:
        return errors
    if (closure['milestone_identity'] != 'harness-backlog-v0.2/M1'
            or closure['display_milestone_id'] != 'M1'
            or closure['closure_status'] != 'PASS'):
        errors.append('milestone-identity-or-status:M1')
    if closure['historical_model_evidence'] != {
            'status': 'UNVERIFIED_HISTORICAL_DECLARATION',
            'independently_reproducible_protocol_model': False,
    }:
        errors.append('milestone-model-evidence-overclaim:M1')
    if closure['product_requirement_pass_claims']:
        errors.append('milestone-product-requirement-overclaim:M1')
    try:
        evaluated = resolve(root, closure['evaluated_commit'])
        head = resolve(root, 'HEAD')
        if not is_ancestor(root, evaluated, head):
            errors.append('milestone-evaluated-unreachable:M1')
        evaluated_backlog = load_artifact_at_revision(root, BACKLOG, evaluated)
        evaluated_trace = load_artifact_at_revision(root, TRACEABILITY, evaluated)
        evaluated_task_errors, evaluated_tasks = task_definition_errors(
            root, evaluated_backlog, evaluated, historical_m1_closure=True)
    except ValueError as ex:
        return errors + ['milestone-evaluated-revision:M1:' + str(ex)]

    active_m1 = {
        task['id'] for task in evaluated_backlog['tasks']
        if task['milestone'] == 'M1' and task['status'] != 'SUPERSEDED'
    }
    declared_ids = [item['display_task_id'] for item in closure['integrations']]
    if active_m1 != M1_TASK_IDS or set(declared_ids) != active_m1 or len(
            declared_ids) != len(set(declared_ids)):
        errors.append('milestone-active-task-set:M1')
    for item in closure['integrations']:
        task_id = item['display_task_id']
        expected_path = f'docs/exec-plans/integrations/{task_id}.json'
        if (item['task_identity'] != f'harness-backlog-v0.2/{task_id}'
                or item['integration_record'] != expected_path):
            errors.append('milestone-integration-binding:' + task_id)
            continue
        try:
            record = load_artifact_at_revision(root, expected_path, evaluated)
            if item['sha256'] != blob_sha_at_revision(root, expected_path, evaluated):
                errors.append('milestone-integration-hash:' + task_id)
            if record.get('integration_status') != 'MERGED':
                errors.append('milestone-integration-unmerged:' + task_id)
            if (record.get('task_identity') != item['task_identity']
                    or record.get('display_task_id') != task_id):
                errors.append('milestone-integration-binding:' + task_id)
            merge_commit = resolve(root, record.get('merge_commit', ''))
            if not is_ancestor(root, merge_commit, evaluated):
                errors.append('milestone-integration-unreachable:' + task_id)
            integration_issues = integration_record_errors(
                root, root / expected_path, record, integration_schema, result_schema,
                review_schema,
                evaluated_tasks)
            errors.extend(
                'milestone-integration-invalid:' + task_id + ':' + issue
                for issue in integration_issues)
        except (ValueError, OSError, KeyError, TypeError) as ex:
            errors.append('milestone-integration-invalid:' + task_id + ':' + str(ex))

    expected_exit_checks = {
        'clean_checkout_starts_test_environment',
        'm1_m2_task_contracts_complete',
        'historical_model_evidence_not_overclaimed',
    }
    exit_ids = [item['check_id'] for item in closure['exit_checks']]
    if set(exit_ids) != expected_exit_checks or len(exit_ids) != len(set(exit_ids)):
        errors.append('milestone-exit-check-set:M1')
    for exit_check in closure['exit_checks']:
        if exit_check['result'] != 'PASS':
            errors.append('milestone-exit-check-failed:' + exit_check['check_id'])
        if not exit_check['evidence']:
            errors.append('milestone-exit-evidence-missing:' + exit_check['check_id'])
        for evidence in exit_check['evidence']:
            path = evidence['path']
            if not relative_path(path):
                errors.append('milestone-exit-evidence-path:' + exit_check['check_id'])
                continue
            try:
                revision = resolve(root, evidence['revision'])
                if not is_ancestor(root, revision, evaluated):
                    errors.append('milestone-exit-evidence-unreachable:' + exit_check['check_id'])
                if evidence['sha256'] != blob_sha_at_revision(root, path, revision):
                    errors.append('milestone-exit-evidence-hash:' + exit_check['check_id'])
            except ValueError as ex:
                errors.append(
                    'milestone-exit-evidence-missing:' + exit_check['check_id'] + ':' + str(ex))
    evidence_paths = {
        item['check_id']: {evidence['path'] for evidence in item['evidence']}
        for item in closure['exit_checks']
    }
    clean_start_evidence = evidence_paths.get('clean_checkout_starts_test_environment', set())
    clean_start_records: list[dict] = next(
        (item['evidence'] for item in closure['exit_checks']
         if item['check_id'] == 'clean_checkout_starts_test_environment'), [])
    expected_clean_paths = {
        check_id: [item for item in clean_start_records
                   if Path(item['path']).name.startswith(check_id + '-')]
        for check_id in M1_CLEAN_START_CHECKS
    }
    if (set(clean_start_evidence) != {item['path'] for item in clean_start_records}
            or any(len(items) != 1 for items in expected_clean_paths.values())
            or len(clean_start_records) != len(M1_CLEAN_START_CHECKS)):
        errors.append('milestone-exit-evidence-semantic:clean_checkout_starts_test_environment')
    for check_id, items in expected_clean_paths.items():
        if len(items) != 1:
            continue
        evidence = items[0]
        try:
            revision = resolve(root, evidence['revision'])
            if revision != evaluated:
                errors.append('milestone-exit-evidence-stale:' + check_id)
            payload = load_artifact_at_revision(root, evidence['path'], revision)
            if (not isinstance(payload, dict)
                    or payload.get('check_id') != check_id
                    or payload.get('command') != M1_CLEAN_START_CHECKS[check_id]
                    or payload.get('status') != 'PASS'):
                errors.append('milestone-exit-evidence-oracle:' + check_id)
                continue
            tested = resolve(root, payload.get('tested_commit', ''))
            if (not is_ancestor(root, tested, evaluated)
                    or any(matches(path, M1_CLEAN_START_RELEVANT_PATHS)
                           for path in changed_paths(root, tested, evaluated))):
                errors.append('milestone-exit-evidence-freshness:' + check_id)
        except (ValueError, OSError, KeyError, TypeError):
            errors.append('milestone-exit-evidence-oracle:' + check_id)
    contract_evidence = evidence_paths.get('m1_m2_task_contracts_complete', set())
    if not {BACKLOG, TRACEABILITY}.issubset(contract_evidence):
        errors.append('milestone-exit-evidence-semantic:m1_m2_task_contracts_complete')
    model_evidence = evidence_paths.get('historical_model_evidence_not_overclaimed', set())
    if 'KineticLoop_Evidence_Manifest_v0.1.json' not in model_evidence:
        errors.append('milestone-exit-evidence-semantic:historical_model_evidence_not_overclaimed')

    try:
        errors.extend('milestone-task-contract:' + issue for issue in evaluated_task_errors)
        trace_errors, trace_tasks = traceability_task_map(
            evaluated_trace, 'milestone-traceability')
        errors.extend(trace_errors)
        for task_id in M1_CLOSURE_M2_TASK_IDS:
            task = evaluated_tasks.get(task_id)
            trace_task = trace_tasks.get(f'harness-backlog-v0.2/{task_id}')
            if (task is None or trace_task != traceability_projection(
                    task, M1_CLOSURE_TRACEABILITY_TASK_FIELDS)):
                errors.append('milestone-m2-projection:' + task_id)
    except (ValueError, OSError, KeyError, TypeError) as ex:
        errors.append('milestone-m2-contract-revision:' + str(ex))
    return errors


def m2_milestone_closure_errors(
        root, closure, schema, integration_schema, result_schema, review_schema, backlog, tasks):
    """Validate M2 closure from integrated task evidence and a fresh full regression."""
    errors = [
        'milestone-schema:M2.json:' + issue.message
        for issue in schema.iter_errors(closure)
    ]
    if errors:
        return errors
    if (closure['milestone_identity'] != 'harness-backlog-v0.2/M2'
            or closure['display_milestone_id'] != 'M2'
            or closure['closure_status'] != 'PASS'):
        errors.append('milestone-identity-or-status:M2')
    if closure['historical_model_evidence'] != {
            'status': 'UNVERIFIED_HISTORICAL_DECLARATION',
            'independently_reproducible_protocol_model': False,
    }:
        errors.append('milestone-model-evidence-overclaim:M2')
    if closure['product_requirement_pass_claims']:
        errors.append('milestone-product-requirement-overclaim:M2')
    try:
        evaluated = resolve(root, closure['evaluated_commit'])
        head = resolve(root, 'HEAD')
        if not is_ancestor(root, evaluated, head):
            errors.append('milestone-evaluated-unreachable:M2')
        evaluated_backlog = load_artifact_at_revision(root, BACKLOG, evaluated)
        evaluated_task_errors, evaluated_tasks = task_definition_errors(
            root, evaluated_backlog, evaluated)
        errors.extend('milestone-task-contract:' + issue for issue in evaluated_task_errors)
    except ValueError as ex:
        return errors + ['milestone-evaluated-revision:M2:' + str(ex)]

    active_m2 = {
        task['id'] for task in evaluated_backlog['tasks']
        if task['milestone'] == 'M2' and task['status'] != 'SUPERSEDED'
    }
    try:
        m1 = load_artifact_at_revision(root, 'docs/exec-plans/milestones/M1.json', evaluated)
        errors.extend('milestone-m2-prerequisite:' + issue for issue in milestone_closure_errors(
            root, m1, schema, integration_schema, result_schema, review_schema,
            evaluated_backlog, evaluated_tasks))
        if not is_ancestor(root, m1['evaluated_commit'], evaluated):
            errors.append('milestone-m2-prerequisite:unreachable')
    except (ValueError, OSError, KeyError, TypeError):
        errors.append('milestone-m2-prerequisite:missing-or-invalid')
    declared_ids = [item['display_task_id'] for item in closure['integrations']]
    if active_m2 != M2_TASK_IDS or set(declared_ids) != active_m2 or len(
            declared_ids) != len(set(declared_ids)):
        errors.append('milestone-active-task-set:M2')
    for item in closure['integrations']:
        task_id = item['display_task_id']
        expected_path = f'docs/exec-plans/integrations/{task_id}.json'
        if (item['task_identity'] != f'harness-backlog-v0.2/{task_id}'
                or item['integration_record'] != expected_path):
            errors.append('milestone-integration-binding:' + task_id)
            continue
        try:
            record = load_artifact_at_revision(root, expected_path, evaluated)
            if item['sha256'] != blob_sha_at_revision(root, expected_path, evaluated):
                errors.append('milestone-integration-hash:' + task_id)
            if record.get('integration_status') != 'MERGED':
                errors.append('milestone-integration-unmerged:' + task_id)
            if (record.get('task_identity') != item['task_identity']
                    or record.get('display_task_id') != task_id):
                errors.append('milestone-integration-binding:' + task_id)
            merge_commit = resolve(root, record.get('merge_commit', ''))
            if not is_ancestor(root, merge_commit, evaluated):
                errors.append('milestone-integration-unreachable:' + task_id)
            integration_issues = integration_record_errors(
                root, root / expected_path, record, integration_schema, result_schema,
                review_schema, evaluated_tasks)
            errors.extend(
                'milestone-integration-invalid:' + task_id + ':' + issue
                for issue in integration_issues)
        except (ValueError, OSError, KeyError, TypeError) as ex:
            errors.append('milestone-integration-invalid:' + task_id + ':' + str(ex))

    expected_exit_checks = {
        'm2_task_integrations_valid',
        'm2_regression_suite_passes',
        'frozen_authority_and_requirement_claims_preserved',
    } | set(M2_EXIT_TASK_CHECKS)
    exit_ids = [item['check_id'] for item in closure['exit_checks']]
    if set(exit_ids) != expected_exit_checks or len(exit_ids) != len(set(exit_ids)):
        errors.append('milestone-exit-check-set:M2')
    evidence_by_check = {
        item['check_id']: item['evidence'] for item in closure['exit_checks']
    }
    for exit_id, task_checks in M2_EXIT_TASK_CHECKS.items():
        expected_evidence = set()
        try:
            for task_id, check_ids in task_checks.items():
                record = load_artifact_at_revision(
                    root, f'docs/exec-plans/integrations/{task_id}.json', evaluated)
                reviewed = resolve(root, record['reviewed_head_sha'])
                paths = result_paths_at_revision(root, task_id, reviewed)
                if len(paths) != 1:
                    raise ValueError('result-representation')
                result = load_artifact_at_revision(root, paths[0], reviewed)
                commands = {item['check_id']: item for item in result['commands_run']}
                for check_id in check_ids:
                    command = commands[check_id]
                    if command['result'] != 'PASS':
                        raise ValueError('task-check-not-pass')
                    expected_evidence.add((command['evidence_ref'], reviewed))
            declared = [(item['path'], item['revision'])
                        for item in evidence_by_check.get(exit_id, [])]
            if set(declared) != expected_evidence or len(declared) != len(set(declared)):
                errors.append('milestone-exit-task-evidence:' + exit_id)
        except (ValueError, OSError, KeyError, TypeError):
            errors.append('milestone-exit-task-evidence:' + exit_id)
    # Gate constructors prove their checks before their own merge through the
    # integration chain. Their merged boundaries must precede KL-015 use.
    try:
        consumer = load_artifact_at_revision(
            root, 'docs/exec-plans/integrations/KL-015.json', evaluated)
        consumer_result = load_artifact_at_revision(
            root, result_paths_at_revision(root, 'KL-015', consumer['reviewed_head_sha'])[0],
            consumer['reviewed_head_sha'])
        for prerequisite in ('KL-014', 'KL-016', 'KL-017', 'KL-072'):
            gate = load_artifact_at_revision(
                root, f'docs/exec-plans/integrations/{prerequisite}.json', evaluated)
            if not is_ancestor(root, gate['merge_commit'], consumer_result['tested_commit']):
                errors.append('milestone-gate-order:' + prerequisite + ':KL-015')
    except (ValueError, OSError, KeyError, TypeError, IndexError):
        errors.append('milestone-gate-order:invalid-chain')
    for exit_check in closure['exit_checks']:
        if exit_check['result'] != 'PASS':
            errors.append('milestone-exit-check-failed:' + exit_check['check_id'])
        if not exit_check['evidence']:
            errors.append('milestone-exit-evidence-missing:' + exit_check['check_id'])
        for evidence in exit_check['evidence']:
            path = evidence['path']
            if not relative_path(path):
                errors.append('milestone-exit-evidence-path:' + exit_check['check_id'])
                continue
            try:
                revision = resolve(root, evidence['revision'])
                if not is_ancestor(root, revision, evaluated):
                    errors.append('milestone-exit-evidence-unreachable:' + exit_check['check_id'])
                if evidence['sha256'] != blob_sha_at_revision(root, path, revision):
                    errors.append('milestone-exit-evidence-hash:' + exit_check['check_id'])
            except ValueError as ex:
                errors.append(
                    'milestone-exit-evidence-missing:' + exit_check['check_id'] + ':' + str(ex))

    integration_paths = {
        item['path'] for item in evidence_by_check.get('m2_task_integrations_valid', [])
    }
    expected_integration_paths = {
        f'docs/exec-plans/integrations/{task_id}.json' for task_id in M2_TASK_IDS
    }
    if integration_paths != expected_integration_paths or any(
            item['revision'] != evaluated
            for item in evidence_by_check.get('m2_task_integrations_valid', [])):
        errors.append('milestone-exit-evidence-semantic:m2_task_integrations_valid')

    regression_records = evidence_by_check.get('m2_regression_suite_passes', [])
    if (len(regression_records) != 1
            or not re.fullmatch(
                r'docs/exec-plans/evidence/HG-023/m2-regression-[0-9a-f]{7,40}\.json',
                regression_records[0]['path'])):
        errors.append('milestone-exit-evidence-semantic:m2_regression_suite_passes')
    else:
        evidence = regression_records[0]
        try:
            revision = resolve(root, evidence['revision'])
            payload = load_artifact_at_revision(root, evidence['path'], revision)
            tested = resolve(root, payload.get('tested_commit', ''))
            errors.extend(m2_execution_evidence_errors(root, payload, revision))
            if (revision != evaluated
                    or payload.get('check_id') != 'm2_regression_suite_passes'
                    or payload.get('commands') != M2_REGRESSION_COMMANDS
                    or payload.get('status') != 'PASS'
                    or not is_ancestor(root, tested, evaluated)
                    or governance_suffix_errors(root, tested, evaluated, 'HG-023', 'tested')):
                errors.append('milestone-exit-evidence-oracle:m2_regression_suite_passes')
        except (ValueError, OSError, KeyError, TypeError):
            errors.append('milestone-exit-evidence-oracle:m2_regression_suite_passes')

    authority_records = evidence_by_check.get(
        'frozen_authority_and_requirement_claims_preserved', [])
    if ({item['path'] for item in authority_records}
            != {'FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json'}
            or any(item['revision'] != evaluated for item in authority_records)):
        errors.append(
            'milestone-exit-evidence-semantic:'
            'frozen_authority_and_requirement_claims_preserved')
    return errors


def m2_execution_evidence_errors(root, payload, revision):
    """Require retained successful executions, including real DB test collection."""
    prefix = 'milestone-regression-execution:'
    runs = payload.get('executions', []) if isinstance(payload, dict) else []
    if not isinstance(runs, list) or len(runs) != len(M2_REGRESSION_COMMANDS):
        return [prefix + 'command-set']
    errors = []
    for command, run in zip(M2_REGRESSION_COMMANDS, runs):
        if (not isinstance(run, dict) or run.get('command') != command
                or run.get('exit_code') != 0
                or run.get('tested_commit') != payload.get('tested_commit')):
            errors.append(prefix + 'failed-or-unbound-command')
            continue
        try:
            log = run['stdout']
            if (not relative_path(log['path'])
                    or not matches(log['path'], [evidence_pattern('HG-023')])
                    or blob_sha_at_revision(root, log['path'], revision) != log['sha256']):
                raise ValueError('stdout-binding')
            output = git(root, 'show', revision + ':' + log['path']).decode()
            if not output.strip():
                raise ValueError('empty-stdout')
            if command == M2_REGRESSION_COMMANDS[1]:
                if 'HARNESS_CHECK_PASS' not in output or 'HARNESS_CHECK_FAIL' in output:
                    raise ValueError('harness-oracle')
                continue
            report = run['junit']
            if (not relative_path(report['path'])
                    or not matches(report['path'], [evidence_pattern('HG-023')])
                    or blob_sha_at_revision(root, report['path'], revision) != report['sha256']):
                raise ValueError('junit-binding')
            tree = ET.fromstring(git(root, 'show', revision + ':' + report['path']))
            cases = list(tree.iter('testcase'))
            if not cases or any(
                    list(case.iter(tag)) for case in cases
                    for tag in ('failure', 'error', 'skipped')):
                raise ValueError('failed-skipped-or-empty-tests')
            names = {(case.get('classname', ''), case.get('name', '').split('[')[0])
                     for case in cases}
            required_cases = {
                ('tests.db.test_migrations', 'test_empty_db_upgrade_head'),
                ('tests.db.test_transaction_interfaces', 'test_reverse_lock_order_is_rejected'),
                ('tests.db.test_transaction_interfaces', 'test_event_outbox_atomicity_enforced'),
                ('tests.db.test_transaction_interfaces', 'test_stale_fence_commit_is_rejected'),
                ('tests.db.test_transaction_interfaces',
                 'test_ack_loss_replay_preserves_natural_uniqueness'),
            }
            if not required_cases <= names:
                raise ValueError('missing-db-coverage')
            if not re.search(r'\b[1-9][0-9]* passed\b', output):
                raise ValueError('pytest-oracle')
        except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as ex:
            errors.append(prefix + str(ex))
    return errors


def task_definition_errors(
        root, backlog, revision=None, *, historical_m1_closure=False):
    """Validate one revision's complete backlog, packet, resource and DAG state."""
    errors = []
    tasks = {task['id']: task for task in backlog['tasks']}
    identities = [task['task_identity'] for task in backlog['tasks']]
    if len(tasks) != len(backlog['tasks']) or len(identities) != len(set(identities)):
        errors.append('task-identity-duplicate')
    resource_path = 'docs/harness/RESOURCE_LOCKS.md'
    resource_text = (git(root, 'show', revision + ':' + resource_path).decode()
                     if revision else (root / resource_path).read_text())
    known_resources = set(re.findall(r'^- `([^`]+)`$', resource_text, re.M))
    for task in backlog['tasks']:
        name = task['id']
        packet_path = 'docs/exec-plans/active/' + name + '.md'
        if revision:
            packet = subprocess.run(
                ['git', 'show', revision + ':' + packet_path],
                cwd=root, capture_output=True)
            if packet.returncode == 0:
                errors.extend(packet_errors(task, packet.stdout.decode()))
            elif task['status'] != 'SUPERSEDED':
                errors.append('packet:' + name)
        else:
            packet = root / packet_path
            if packet.exists():
                errors.extend(packet_errors(task, packet.read_text()))
            elif task['status'] != 'SUPERSEDED':
                errors.append('packet:' + name)
        for dep in task['depends_on']:
            if dep not in tasks:
                errors.append('unknown-dep:' + name + '->' + dep)
        conditional_dependencies = task.get('conditional_depends_on', [])
        for conditional in conditional_dependencies:
            if isinstance(conditional, str):
                dep = conditional
            elif (isinstance(conditional, dict)
                  and isinstance(conditional.get('task_id'), str)
                  and isinstance(conditional.get('condition'), str)
                  and conditional['condition'].strip()):
                dep = conditional['task_id']
            else:
                errors.append('invalid-conditional-dep:' + name)
                continue
            if dep not in tasks:
                errors.append('unknown-conditional-dep:' + name + '->' + dep)
        resources = task.get('resource_keys', [])
        if len(resources) != len(set(resources)):
            errors.append('duplicate-resource-key:' + name)
        for resource in resources:
            if resource not in known_resources:
                errors.append('unknown-resource-key:' + name + '->' + resource)
        if name in M2_REFINED_TASK_IDS:
            contracts = task.get('check_contracts')
            evidence_paths = task.get('evidence_paths')
            contract_ids = (
                [item.get('check_id') for item in contracts]
                if isinstance(contracts, list) and all(isinstance(item, dict) for item in contracts)
                else []
            )
            generic = re.compile(r'(?:^task_scope_|todo|tbd|placeholder)', re.I)
            if (not contracts or len(contract_ids) != len(set(contract_ids))
                    or contract_ids != task.get('checks_required_for_this_task')):
                errors.append('check-contract-ids:' + name)
            elif any(
                    set(item) != {'check_id', 'command', 'pass_oracle'}
                    or not all(isinstance(item.get(field), str) and item[field].strip()
                               for field in ('check_id', 'command', 'pass_oracle'))
                    or generic.search(item['check_id'])
                    or generic.search(item['command'])
                    or generic.search(item['pass_oracle'])
                    for item in contracts):
                errors.append('check-contract-generic-or-invalid:' + name)
            expected_evidence = [f'docs/exec-plans/evidence/{name}/**']
            if evidence_paths != expected_evidence or not all(
                    relative_path(path[:-3]) for path in evidence_paths or []):
                errors.append('evidence-path:' + name)
            if task.get('packet_refinement') != 'ENFORCEABLE':
                errors.append('m2-packet-not-enforceable:' + name)
            if 'M1 closure PASS: docs/exec-plans/milestones/M1.json' not in task.get(
                    'entry_conditions', []):
                errors.append('m2-entry-condition:' + name)
            required_checks = (
                M1_CLOSURE_KL017_REQUIRED_CHECK_IDS
                if historical_m1_closure and name == 'KL-017'
                else M1_CLOSURE_KL018_REQUIRED_CHECK_IDS
                if historical_m1_closure and name == 'KL-018'
                else M2_REQUIRED_CHECK_IDS.get(name, set())
            )
            if not required_checks.issubset(set(contract_ids)):
                errors.append('m2-required-semantic-checks:' + name)
            if name == 'KL-014' and task.get('commands') != KL014_REQUIRED_COMMAND_SURFACE:
                errors.append('m2-kl014-command-surface')
            if name == 'KL-016' and task.get('commands') != KL016_REQUIRED_COMMAND_SURFACE:
                errors.append('m2-kl016-command-surface')
            if name == 'KL-072' and task.get('commands') != KL072_REQUIRED_COMMAND_SURFACE:
                errors.append('m2-kl072-command-surface')
            if (name == 'KL-072' and (task.get('shared_hotspot') is not True
                    or 'registry_coordination' not in task.get('resource_keys', []))):
                errors.append('m2-kl072-registry-hotspot')
            if (name == 'KL-018' and not historical_m1_closure and (
                    not {'migration_chain', 'persistence_permissions'} <= set(
                        task.get('resource_keys', []))
                    or 'migrations/versions/*_artifact_registry.py' not in task.get(
                        'write_paths', [])
                    or 'tests/db/test_migrations.py' not in task.get('write_paths', [])
                    or 'tests/db/test_safety_registry.py' not in task.get('write_paths', []))):
                errors.append('m2-kl018-registry-migration-scope')
            if (name == 'KL-017' and not historical_m1_closure and (
                    'KL-018' not in task.get('depends_on', [])
                    or 'registry_coordination' not in task.get('resource_keys', [])
                    or 'tests/db/test_migrations.py' not in task.get('write_paths', [])
                    or 'tests/db/test_safety_registry.py' not in task.get('write_paths', []))):
                errors.append('m2-kl017-successor-migration-scope')
            if name == 'KL-015':
                if task.get('invariant_ids') != KL015_REQUIRED_INVARIANT_IDS:
                    errors.append('m2-kl015-frozen-impact:invariants')
                if task.get('transaction_boundaries') != KL015_REQUIRED_TRANSACTION_BOUNDARIES:
                    errors.append('m2-kl015-frozen-impact:transactions')
                if task.get('table_ids') != KL015_REQUIRED_TABLE_IDS:
                    errors.append('m2-kl015-frozen-impact:tables')
            contract_map = {
                item.get('check_id'): item for item in contracts or []
                if isinstance(item, dict)
            }
            critical_contracts = (
                M1_CLOSURE_KL017_CRITICAL_CONTRACT_DIGESTS
                if historical_m1_closure and name == 'KL-017'
                else M1_CLOSURE_KL018_CRITICAL_CONTRACT_DIGESTS
                if historical_m1_closure and name == 'KL-018'
                else M2_CRITICAL_CONTRACT_DIGESTS.get(name, {})
            )
            for check_id, expected_digest in critical_contracts.items():
                contract = contract_map.get(check_id)
                actual_digest = hashlib.sha256(json.dumps(
                    contract, ensure_ascii=False, sort_keys=True,
                    separators=(',', ':'),
                ).encode()).hexdigest() if contract is not None else ''
                if actual_digest != expected_digest:
                    errors.append('m2-security-contract:' + name + ':' + check_id)
            if (name in M2_REQUIRED_SECURITY_REVIEWS
                    and 'SECURITY_DATA_BOUNDARY' not in task.get('review_requirements', [])):
                errors.append('m2-security-review-required:' + name)
            if (name in M2_REQUIRED_DB_REVIEWS
                    and 'DB_CONCURRENCY' not in task.get('review_requirements', [])):
                errors.append('m2-db-review-required:' + name)
        if (task.get('status') == 'READY'
                and (task.get('packet_refinement') != 'ENFORCEABLE'
                     or task.get('write_paths_status') != 'ENFORCEABLE')):
            errors.append('ready-write-scope-unrefined:' + name)
    refined = [tasks[name] for name in sorted(M2_REFINED_TASK_IDS) if name in tasks]
    for position, left in enumerate(refined):
        for right in refined[position + 1:]:
            overlaps = {
                left_path for left_path in left.get('write_paths', [])
                for right_path in right.get('write_paths', [])
                if (left_path == right_path
                    or matches(left_path.replace('*', 'x'), [right_path])
                    or matches(right_path.replace('*', 'x'), [left_path]))
            }
            if overlaps and not set(left.get('resource_keys', [])) & set(
                    right.get('resource_keys', [])):
                errors.append(
                    'unlocked-write-path-overlap:' + left['id'] + ':' + right['id'])
    pending = set(tasks)
    while pending:
        ready = set()
        for name in pending:
            conditional = tasks[name].get('conditional_depends_on', [])
            dependencies = set(tasks[name]['depends_on']) | {
                item if isinstance(item, str) else item.get('task_id')
                for item in conditional
            }
            if not dependencies & pending:
                ready.add(name)
        if not ready:
            errors.append('dag-cycle')
            break
        pending -= ready
    return errors, tasks


def validate(root, args):
    from jsonschema import Draft202012Validator

    errors = []
    index, frozen, backlog = (load_artifact(root / n) for n in (INDEX, 'FROZEN_BASELINE.json', BACKLOG))
    manifest = load_artifact(root / MANIFEST)
    traceability = load_artifact(root / TRACEABILITY)
    traceability_errors, _ = traceability_task_map(traceability)
    errors.extend(traceability_errors)
    for entry in index['documents'] + index.get('machine_readable', []) + frozen['files']:
        path = root / entry['path']
        if not relative_path(entry['path']) or not path.is_file():
            errors.append('missing:' + entry['path'])
        elif sha(path) != entry['sha256']:
            errors.append('hash:' + entry['path'])
    for entry in manifest.get('files', []):
        path = root / entry['path']
        if not relative_path(entry['path']) or not path.is_file():
            errors.append('manifest-missing:' + entry['path'])
        elif sha(path) != entry['sha256']:
            errors.append('manifest-hash:' + entry['path'])
        elif entry.get('bytes') != path.stat().st_size:
            errors.append('manifest-bytes:' + entry['path'])
    task_errors, tasks = task_definition_errors(root, backlog)
    errors.extend(task_errors)

    schemas = {}
    known_requirements = requirement_ids(root)
    schema_files = {
        'RESULT': 'THREAD_RESULT.schema.json',
        'REVIEW': 'THREAD_REVIEW.schema.json',
        'GOVERNANCE': GOVERNANCE_SCHEMA,
        'INTEGRATION': INTEGRATION_SCHEMA,
        'MILESTONE': MILESTONE_CLOSURE_SCHEMA,
    }
    for kind, schema_name in schema_files.items():
        schema = load_artifact(root / schema_name)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as ex:
            raise ValueError('invalid-schema:' + kind + ':' + str(ex)) from ex
        schemas[kind] = Draft202012Validator(schema)
    milestone_dir = root / 'docs/exec-plans/milestones'
    milestone_records = {'M1': [], 'M2': []}
    if milestone_dir.exists():
        for path in sorted(milestone_dir.glob('*.json')):
            record = load_artifact(path)
            milestone_id = record.get('display_milestone_id') if isinstance(record, dict) else None
            if path.stem in milestone_records:
                milestone_records[path.stem].append((path, record))
            elif milestone_id in milestone_records:
                milestone_records[milestone_id].append((path, record))
            else:
                errors.append('milestone-unsupported-record:' + path.name)
    if not milestone_records['M1']:
        m1_closure_valid = False
    elif len(milestone_records['M1']) != 1:
        errors.append('milestone-closure-count:M1:' + str(len(milestone_records['M1'])))
        m1_closure_valid = False
    else:
        closure_path, closure = milestone_records['M1'][0]
        if closure_path.name != 'M1.json':
            errors.append('milestone-closure-path:M1:' + closure_path.name)
        closure_errors = milestone_closure_errors(
            root, closure, schemas['MILESTONE'], schemas['INTEGRATION'],
            schemas['RESULT'], schemas['REVIEW'], backlog, tasks)
        errors.extend(closure_errors)
        m1_closure_valid = not closure_errors and closure_path.name == 'M1.json'
    if len(milestone_records['M2']) > 1:
        errors.append('milestone-closure-count:M2:' + str(len(milestone_records['M2'])))
    elif milestone_records['M2']:
        closure_path, closure = milestone_records['M2'][0]
        if closure_path.name != 'M2.json':
            errors.append('milestone-closure-path:M2:' + closure_path.name)
        errors.extend(m2_milestone_closure_errors(
            root, closure, schemas['MILESTONE'], schemas['INTEGRATION'],
            schemas['RESULT'], schemas['REVIEW'], backlog, tasks))
    for task in tasks.values():
        if task['milestone'] == 'M2' and task['status'] == 'READY' and not m1_closure_valid:
            errors.append('ready-m1-closure-invalid:' + task['id'])
    results = {}
    completed = root / 'docs/exec-plans/completed'
    for path in sorted(list(completed.glob('*_RESULT.yaml')) + list(completed.glob('*_RESULT.json'))):
        obj = load_artifact(path)
        issues = list(schemas['RESULT'].iter_errors(obj))
        if issues:
            errors.extend('result-schema:' + path.name + ':' + e.message for e in issues)
            continue
        task = tasks.get(obj['display_task_id'])
        if task is None:
            errors.append('result-unknown-task:' + path.name)
            continue
        if path.name not in [Path(p).name for p in result_paths(task['id'])] or task['id'] in results:
            errors.append('result-duplicate-or-path:' + path.name)
        results[task['id']] = (path, obj)
        errors.extend(path.name + ':' + e for e in semantic_result_errors(obj, task, root))
        requirement_names = [r['requirement_id'] for r in obj['requirements_covered']]
        if len(requirement_names) != len(set(requirement_names)):
            errors.append('result-duplicate-requirement:' + path.name)
        for requirement in obj['requirements_covered']:
            name = requirement['requirement_id']
            covered = task['requirements_covered']
            if name not in known_requirements or (name not in covered and name.split('@')[0] not in covered):
                errors.append('result-unknown-or-unassigned-requirement:' + name)

    reviews = []
    governance_reviews = []
    for path in sorted((root / 'docs/exec-plans/reviews').glob('*/*.json')):
        obj = load_artifact(path)
        issues = list(schemas['REVIEW'].iter_errors(obj))
        if issues:
            errors.extend('review-schema:' + path.name + ':' + e.message for e in issues)
            continue
        if re.fullmatch(r'HG-[0-9]{3}', path.parent.name):
            expected_identity = 'harness-governance-v0.1/' + path.parent.name
            if obj['task_identity'] != expected_identity or path.stem != obj['review_type']:
                errors.append('governance-review-identity-or-path:' + str(path.relative_to(root)))
                continue
            for ref in obj.get('evidence_refs', []):
                if not evidence_exists(root, ref):
                    errors.append('governance-review-evidence:' + ref)
            governance_reviews.append((path, obj))
            continue
        task = tasks.get(path.parent.name)
        if not task or task['task_identity'] != obj['task_identity'] or path.stem != obj['review_type']:
            errors.append('review-identity-or-path:' + str(path.relative_to(root)))
            continue
        for ref in obj.get('evidence_refs', []):
            if not evidence_exists(root, ref):
                errors.append('review-evidence:' + ref)
        reviews.append((path, obj, task))

    governance_records = {}
    governance_dir = root / 'docs/exec-plans/governance'
    if governance_dir.exists():
        for path in sorted(list(governance_dir.glob('HG-*.yaml')) +
                           list(governance_dir.glob('HG-*.json'))):
            record = load_artifact(path)
            issues = list(schemas['GOVERNANCE'].iter_errors(record))
            if issues:
                errors.extend('governance-schema:' + path.name + ':' + issue.message
                              for issue in issues)
                continue
            change_id = record['display_change_id']
            if path.stem != change_id or change_id in governance_records:
                errors.append('governance-duplicate-or-path:' + path.name)
            governance_records[change_id] = (path, record)
            if record['change_identity'] != 'harness-governance-v0.1/' + change_id:
                errors.append('governance-identity:' + change_id)
            check_ids = [check['check_id'] for check in record['checks_run']]
            if len(check_ids) != len(set(check_ids)):
                errors.append('governance-duplicate-check:' + change_id)
            for check in record['checks_run']:
                if check['result'] != 'PASS' or not evidence_exists(root, check['evidence_ref']):
                    errors.append('governance-check-evidence:' + change_id + ':' + check['check_id'])
            if record['change_status'] == 'PASS' and record['frozen_impact'] != 'NONE':
                errors.append('governance-pass-frozen-impact:' + change_id)

    integrations = root / 'docs/exec-plans/integrations'
    if integrations.exists():
        for path in sorted(integrations.glob('*.json')):
            record = load_artifact(path)
            errors.extend(integration_record_errors(
                root, path, record, schemas['INTEGRATION'], schemas['RESULT'],
                schemas['REVIEW'], tasks))

    if (args.protected_base or args.reviewed_head or
            getattr(args, 'governance_reviewed_head', None)):
        # PR checks use committed artifacts and may not silently ignore working edits.
        if git(root, 'status', '--porcelain', '--untracked-files=all').strip():
            errors.append('git-worktree-not-clean')
    if args.protected_base:
        base_sha, head = resolve(root, args.protected_base), resolve(root, 'HEAD')
        git(root, 'merge-base', '--is-ancestor', base_sha, head)
        changed = set(changed_paths(root, base_sha, head))
        old_frozen = json.loads(git(root, 'show', base_sha + ':FROZEN_BASELINE.json'))
        protected_paths = {e['path'] for e in old_frozen['files']} | {'FROZEN_BASELINE.json'}
        errors.extend('protected-baseline-change:' + p for p in sorted(changed & protected_paths))
        if args.task_id:
            task = tasks.get(args.task_id)
            # The PR may not widen its own definition to authorize additional writes.
            old_tasks = json.loads(git(root, 'show', base_sha + ':' + BACKLOG))['tasks']
            baseline_task = next((t for t in old_tasks if t['id'] == args.task_id), None)
            if not task or not baseline_task or baseline_task.get('write_paths_status') != 'ENFORCEABLE':
                errors.append('write-scope-unrefined-or-unknown:' + args.task_id)
            else:
                allowed = baseline_task['write_paths'] + result_paths(args.task_id) + review_patterns(args.task_id) + [evidence_pattern(args.task_id)]
                for path in sorted(changed):
                    if (path == INDEX and
                            INDEX in baseline_task.get('authority_update_paths', [])):
                        errors.extend(task_index_authority_errors(
                            root, base_sha, baseline_task, changed, protected_paths))
                    elif path in (INDEX, MANIFEST):
                        errors.extend(hash_refresh_errors(root, base_sha, path, baseline_task, changed, protected_paths))
                    elif not matches(path, allowed):
                        errors.append('write-scope:' + args.task_id + ':' + path)
        elif getattr(args, 'governance_change_id', None):
            change_id = args.governance_change_id
            selected = governance_records.get(change_id)
            if not selected:
                errors.append('governance-record-missing:' + change_id)
            else:
                _, record = selected
                review_only = getattr(args, 'governance_review_only', False)
                if record['change_status'] != 'PASS':
                    errors.append('governance-change-not-pass:' + change_id)
                record_base = resolve(root, record['base_commit'])
                reviewed = resolve(root, args.governance_reviewed_head)
                if not review_only and record_base != base_sha:
                    errors.append('governance-base-mismatch:' + change_id)
                if review_only:
                    governance_base = record_base
                    governance_changed = set(changed_paths(root, governance_base, reviewed))
                    governance_target = reviewed
                    old_frozen = json.loads(
                        git(root, 'show', governance_base + ':FROZEN_BASELINE.json'))
                    governance_protected = {
                        entry['path'] for entry in old_frozen['files']
                    } | {'FROZEN_BASELINE.json'}
                    errors.extend(
                        'protected-baseline-change:' + path
                        for path in sorted(governance_changed & governance_protected)
                    )
                else:
                    governance_base = base_sha
                    governance_changed = set(changed_paths(root, governance_base, reviewed))
                    governance_target = None
                    governance_protected = protected_paths
                for path in sorted(changed):
                    allowed = (review_patterns(change_id) if review_only
                               else governance_allowed_patterns(change_id))
                    if not matches(path, allowed):
                        prefix = ('governance-review-only-scope:' if review_only
                                  else 'governance-write-scope:')
                        errors.append(prefix + change_id + ':' + path)
                for path in sorted(governance_changed if review_only else ()):
                    if not matches(path, governance_allowed_patterns(change_id)):
                        errors.append('governance-write-scope:' + change_id + ':' + path)
                declared = set(record['files_changed'])
                if declared != governance_changed:
                    errors.append('governance-files-changed-mismatch:' + change_id)
                changed_task_review_types: dict[str, set[str]] = {}
                for path in sorted(governance_changed):
                    if not re.match(r'docs/exec-plans/reviews/KL-[0-9]{3}[A-Z]?/', path):
                        continue
                    match = re.fullmatch(
                        r'docs/exec-plans/reviews/(KL-[0-9]{3}[A-Z]?)/([A-Z_]+)\.json',
                        path)
                    if not match:
                        errors.append('governance-task-review-path:' + change_id + ':' + path)
                        continue
                    task_id, review_type = match.groups()
                    changed_task_review_types.setdefault(task_id, set()).add(review_type)
                    if subprocess.run(
                            ['git', 'cat-file', '-e', governance_base + ':' + path],
                            cwd=root, capture_output=True).returncode == 0:
                        errors.append(
                            'governance-task-review-not-addition:'
                            + change_id + ':' + path)
                changed_integrations = {
                    match.group(1)
                    for path in governance_changed
                    if (match := re.fullmatch(
                        r'docs/exec-plans/integrations/(KL-[0-9]{3}[A-Z]?)\.json',
                        path))
                }
                changed_task_reviews = set(changed_task_review_types)
                for task_id in sorted(changed_task_reviews - changed_integrations):
                    errors.append(
                        'governance-task-review-without-integration:'
                        + change_id + ':' + task_id)
                for task_id in sorted(changed_task_reviews & changed_integrations):
                    integration_path = f'docs/exec-plans/integrations/{task_id}.json'
                    if subprocess.run(
                            ['git', 'cat-file', '-e', governance_base + ':' + integration_path],
                            cwd=root, capture_output=True).returncode == 0:
                        errors.append(
                            'governance-task-integration-not-addition:'
                            + change_id + ':' + task_id)
                    required_reviews = set(tasks.get(task_id, {}).get('review_requirements', []))
                    if changed_task_review_types[task_id] != required_reviews:
                        errors.append(
                            'governance-task-review-types:'
                            + change_id + ':' + task_id)
                errors.extend(governance_index_errors(
                    root, governance_base, record, governance_changed, governance_protected,
                    governance_target))
                errors.extend(governance_manifest_errors(
                    root, governance_base, governance_changed, governance_target))

                old_tasks = {task['id']: task for task in
                             json.loads(git(root, 'show', governance_base + ':' + BACKLOG))['tasks']}
                if review_only:
                    replay_backlog = load_artifact_at_revision(root, BACKLOG, reviewed)
                    replay_task_errors, replay_tasks = task_definition_errors(
                        root, replay_backlog, reviewed)
                    errors.extend(replay_task_errors)
                else:
                    replay_tasks = tasks
                changed_task_ids = {
                    task_id for task_id in set(old_tasks) | set(replay_tasks)
                    if old_tasks.get(task_id) != replay_tasks.get(task_id)
                }
                args.governance_changed_task_ids = changed_task_ids
                args.governance_base_tasks = old_tasks
                args.governance_reviewed_tasks = replay_tasks
                refined = set(record['packets_refined'])
                for task_id in sorted(changed_task_ids - refined):
                    errors.append(
                        'governance-task-definition-scope:'
                        + change_id + ':' + task_id)

                base_traceability = load_artifact_at_revision(
                    root, TRACEABILITY, governance_base)
                reviewed_traceability = (
                    load_artifact_at_revision(root, TRACEABILITY, reviewed)
                    if review_only else load_artifact(root / TRACEABILITY)
                )
                base_trace_errors, base_trace_by_identity = traceability_task_map(
                    base_traceability, 'governance-base-traceability')
                reviewed_trace_errors, reviewed_trace_by_identity = traceability_task_map(
                    reviewed_traceability, 'governance-reviewed-traceability')
                errors.extend(base_trace_errors)
                errors.extend(reviewed_trace_errors)
                changed_trace_identities = {
                    identity
                    for identity in set(base_trace_by_identity) | set(reviewed_trace_by_identity)
                    if base_trace_by_identity.get(identity) != reviewed_trace_by_identity.get(identity)
                }
                refined_identities = {
                    replay_tasks[task_id]['task_identity']
                    for task_id in refined if task_id in replay_tasks
                }
                for identity in sorted(changed_trace_identities - refined_identities):
                    errors.append(
                        'governance-traceability-scope:'
                        + change_id + ':' + str(identity))
                for task_id in sorted(refined):
                    task = replay_tasks.get(task_id)
                    if not task:
                        continue
                    trace_task = reviewed_trace_by_identity.get(task['task_identity'])
                    if (trace_task is None
                            or trace_task.get('id') != task_id
                            or traceability_projection(task) != trace_task):
                        errors.append('governance-traceability-mismatch:' + task_id)
                observed = set()
                for task_id in refined:
                    task = replay_tasks.get(task_id)
                    old_task = old_tasks.get(task_id)
                    if not task:
                        errors.append('governance-refined-task-unknown:' + task_id)
                        continue
                    if old_task is None:
                        task_artifact_patterns = (
                            result_paths(task_id) + review_patterns(task_id)
                            + [f'docs/exec-plans/integrations/{task_id}.json']
                        )
                        if task.get('status') != 'NOT_STARTED':
                            errors.append('governance-new-task-status:' + task_id)
                        if any(matches(path, task_artifact_patterns)
                               for path in governance_changed):
                            errors.append('governance-new-task-artifact:' + task_id)
                        if task.get('packet_refinement') == 'ENFORCEABLE':
                            observed.add(task_id)
                    else:
                        if result_paths_at_revision(root, task_id, governance_base):
                            errors.append('governance-refine-completed-task:' + task_id)
                        if ((old_task.get('packet_refinement') == 'MUST_REFINE_BEFORE_READY'
                             and task.get('packet_refinement') != 'MUST_REFINE_BEFORE_READY')
                                or (old_task != task and
                                    task.get('packet_refinement') == 'ENFORCEABLE')):
                            observed.add(task_id)
                    if (task.get('write_paths_status') != 'ENFORCEABLE' or
                            not task.get('write_paths') or
                            any('TO_BE_REFINED' in path for path in task.get('write_paths', []))):
                        errors.append('governance-refinement-incomplete:' + task_id)
                changed_packets = {
                    Path(path).stem for path in governance_changed
                    if re.fullmatch(r'docs/exec-plans/active/KL-[0-9]{3}[A-Z]?\.md', path)
                }
                if refined != observed or refined != changed_packets:
                    errors.append('governance-refined-packets-mismatch:' + change_id)
        else:
            errors.append('protected-change-kind-required')

    for path, review, task in reviews:
        # Historical reviews describe their own PR, not every later repository HEAD.
        if review['status'] != 'PASS' or not args.reviewed_head or task['id'] != args.task_id:
            continue
        reviewed = review['reviewed_head_sha']
        errors.extend(suffix_errors(root, reviewed, 'HEAD', task['id'], 'review'))
        result = results.get(task['id'])
        if not result:
            errors.append('review-missing-result:' + task['id'])
            continue
        result_path, obj = result
        try:
            if git(root, 'show', resolve(root, reviewed) + ':' + str(result_path.relative_to(root))) != result_path.read_bytes():
                errors.append('review-result-not-bound:' + task['id'])
            if obj['task_status'] != 'PASS':
                errors.append('review-result-not-pass:' + task['id'])
            git(root, 'merge-base', '--is-ancestor', resolve(root, obj['base_commit']), resolve(root, obj['tested_commit']))
            errors.extend(suffix_errors(root, obj['tested_commit'], reviewed, task['id'], 'tested'))
            refs = [c.get('evidence_ref') for c in obj['commands_run']] + [r.get('evidence_ref') for r in obj['requirements_covered']]
            for ref in filter(None, refs):
                if git(root, 'show', resolve(root, reviewed) + ':' + ref) != (root / ref).read_bytes():
                    errors.append('review-evidence-not-bound:' + ref)
        except ValueError as ex:
            errors.append('review-revision:' + str(ex))
    if args.reviewed_head:
        if not args.task_id:
            errors.append('review-suffix:task-id-required')
        else:
            errors.extend(suffix_errors(root, args.reviewed_head, 'HEAD', args.task_id, 'review'))
            task = tasks.get(args.task_id)
            relevant = [review for _, review, t in reviews if t['id'] == args.task_id and review['status'] == 'PASS']
            types = {r['review_type'] for r in relevant if resolve(root, r['reviewed_head_sha']) == resolve(root, args.reviewed_head)}
            if not task or not set(task['review_requirements']) <= types:
                errors.append('required-reviews-not-pass:' + args.task_id)
    if getattr(args, 'governance_reviewed_head', None):
        change_id = args.governance_change_id
        reviewed = resolve(root, args.governance_reviewed_head)
        review_only = getattr(args, 'governance_review_only', False)
        if review_only:
            protected_base = resolve(root, args.protected_base)
            if not is_ancestor(root, reviewed, protected_base):
                errors.append('governance-review-only-reviewed-not-merged:' + change_id)
            errors.extend(governance_suffix_errors(
                root, protected_base, 'HEAD', change_id, 'review'))
        else:
            errors.extend(governance_suffix_errors(root, reviewed, 'HEAD', change_id, 'review'))
        selected = governance_records.get(change_id)
        if not selected:
            errors.append('governance-record-missing:' + change_id)
        else:
            record_path, record = selected
            try:
                if git(root, 'show', reviewed + ':' + str(record_path.relative_to(root))) != record_path.read_bytes():
                    errors.append('governance-record-not-bound:' + change_id)
                git(root, 'merge-base', '--is-ancestor',
                    resolve(root, record['base_commit']), resolve(root, record['tested_commit']))
                errors.extend(governance_suffix_errors(
                    root, record['tested_commit'], reviewed, change_id, 'tested'))
                for check in record['checks_run']:
                    ref = check['evidence_ref']
                    if git(root, 'show', reviewed + ':' + ref) != (root / ref).read_bytes():
                        errors.append('governance-evidence-not-bound:' + ref)
            except ValueError as ex:
                errors.append('governance-review-revision:' + str(ex))
            required = {'GENERAL'}
            old_tasks = getattr(args, 'governance_base_tasks', {})
            reviewed_tasks = getattr(args, 'governance_reviewed_tasks', tasks)
            changed_task_ids = getattr(args, 'governance_changed_task_ids', set())
            for task_id in changed_task_ids:
                required.update(old_tasks.get(task_id, {}).get('review_requirements', []))
                required.update(reviewed_tasks.get(task_id, {}).get('review_requirements', []))
            types = {
                review['review_type'] for _, review in governance_reviews
                if review['task_identity'] == 'harness-governance-v0.1/' + change_id and
                review['status'] == 'PASS' and
                resolve(root, review['reviewed_head_sha']) == reviewed
            }
            if not required <= types:
                errors.append('governance-required-reviews-not-pass:' + change_id)
    return errors, len(tasks), sum(t['status'] != 'SUPERSEDED' for t in tasks.values())


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protected-base', help='Trusted, already-integrated base commit for PR protection.')
    parser.add_argument('--reviewed-head', help='Reviewed implementation/result revision; requires --task-id.')
    parser.add_argument('--task-id')
    parser.add_argument('--ci-pr-base', help='Pull request base SHA supplied by CI.')
    parser.add_argument('--ci-pr-head', help='Pull request head SHA supplied by CI.')
    parser.set_defaults(governance_change_id=None, governance_reviewed_head=None)
    args = parser.parse_args(argv)
    try:
        if args.ci_pr_base or args.ci_pr_head:
            configure_ci_merge_gate(root, args)
        errors, count, active = validate(root, args)
    except (ValueError, KeyError, TypeError, OSError, ImportError) as ex:
        errors, count, active = ['validation-error:' + str(ex)], 0, 0
    if errors:
        print('HARNESS_CHECK_FAIL')
        print('\n'.join(errors))
        return 1
    print(f'HARNESS_CHECK_PASS tasks={count} active={active}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
