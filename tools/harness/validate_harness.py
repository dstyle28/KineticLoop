#!/usr/bin/env python3
"""Validate Harness contracts; Git arguments enable revision-bound PR checks."""
import argparse
import fnmatch
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_evidence_spec = importlib.util.spec_from_file_location(
    'compact_evidence', ROOT / 'tools/harness/compact_evidence.py')
assert _evidence_spec and _evidence_spec.loader
compact_evidence = importlib.util.module_from_spec(_evidence_spec)
_evidence_spec.loader.exec_module(compact_evidence)
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
EMERGENCY_GOVERNANCE_TASK = {'HG-024': 'KL-073'}
HG024_EMERGENCY_SCOPE_PATTERNS = [
    'docs/exec-plans/completed/KL-073_RESULT.yaml',
    'docs/exec-plans/evidence/KL-073/**',
    'docs/exec-plans/reviews/KL-073/**',
    'tests/db/test_transaction_interfaces.py',
]
HG024_ONE_TIME_BASE_ABSENT_PATHS = [
    'docs/exec-plans/active/KL-073.md',
    'docs/exec-plans/completed/KL-073_RESULT.yaml',
    'docs/exec-plans/completed/KL-073_RESULT.json',
    'docs/exec-plans/governance/HG-024.yaml',
    'docs/exec-plans/governance/HG-024.json',
]
HG024_ALLOWED_PATTERNS = [
    PROJECT_PLAN,
    BACKLOG,
    TRACEABILITY,
    INDEX,
    MANIFEST,
    'docs/exec-plans/active/KL-073.md',
    'docs/exec-plans/completed/KL-073_RESULT.yaml',
    'docs/exec-plans/evidence/HG-024/**',
    'docs/exec-plans/evidence/KL-073/**',
    'docs/exec-plans/governance/HG-024.yaml',
    'docs/exec-plans/reviews/HG-024/**',
    'docs/exec-plans/reviews/KL-073/**',
    'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
    'tests/db/test_transaction_interfaces.py',
    'tests/harness/test_validator.py',
    'tools/harness/validate_harness.py',
]

# HG044 ratified M3 exit mapping. These are task checks, never aggregate product PASS.
M3_TASK_IDS = {f'KL-{n:03d}' for n in range(19, 30)} | {f'KL-{n:03d}' for n in range(75, 81)}
M3_EXIT_TASK_CHECKS = {'full_test_fdn_trajectory_and_repair': {'KL-027': ['demo_owner_trajectory_e2e', 'demo_fdn_repair_e2e']}, 'current_denials_and_immutable_history': {'KL-027': ['demo_revoke_denials_dc', 'demo_expiry_denials_dc'], 'KL-077': ['continue_resume_current_dc', 'full_execution_replay_atomicity_dc'], 'KL-028': ['b07_dc', 'b16_dc']}, 'nine_actual_dc_interleavings': {'KL-026': ['i01_dc', 'i02_dc', 'i03_dc', 'i04_dc', 'i05_dc', 'i06_dc', 'i07_dc', 'i08_dc', 'i09_dc', 'time_boundary_pu']}, 'ready_sealed_barriers': {'KL-023': ['factset_complete_writer_interleaving_dc', 'factset_seal_frontier_atomicity_and_replay_dc'], 'KL-028': ['b01_pu', 'b01_dc', 'b02_dc', 'b03_dc']}, 'registry_commit_freshness_and_closure': {'KL-021': ['t2_global_commit_rollback_and_effective_at_semantics'], 'KL-028': ['b04_dc', 'b05_dc', 'b06_dc', 'b11_dc', 'b12_dc', 'b13_dc', 'b14_registry_failclosed_stop_support_dc', 'b15_dc', 'b17_pu', 'b17_dc']}, 'validity_missing_timeless_and_expiry': {'KL-022': ['validity_closure_minimum_and_missing_values_pu', 'timeless_policy_dependency_closure_pu', 't6_certificate_and_minimum_closure_dc'], 'KL-028': ['b08_pu', 'b09_pu', 'b09_dc', 'b10_pu', 'b18_pu']}, 'isolated_test_and_evaluation_boundaries': {'KL-027': ['demo_namespace_and_boundary_pu', 'demo_scope_denials_dc'], 'KL-028': ['boundary_namespace_pu'], 'KL-029': ['shadow_namespace_and_boundary_pu', 'shadow_strict_wire_pu', 'shadow_evaluation_principal_live_denials_dc', 'shadow_test_authorization_crossing_denials_dc', 'shadow_owner_payload_denials_dc', 'shadow_declared_evaluation_storage_dc']}}
M3_CHECK_CONTRACT_DIGESTS = {'KL-027:demo_owner_trajectory_e2e': '043b27b5636b361937979632e3861bbd8283c99f128b6b5fac731161d9721f3e', 'KL-027:demo_fdn_repair_e2e': '591f05baf6c7baa76dfcf07786301efb13f9802af01663db5bf55fa3d034fe23', 'KL-027:demo_revoke_denials_dc': 'b204e242a2374e3dc298da68328bab28147f714189f163de393d7a6b91a02f71', 'KL-027:demo_expiry_denials_dc': '648bd63d3b9a16766db344e7609c180eda7b82a1b56312cde45f5060a8019a7d', 'KL-077:continue_resume_current_dc': '352f9fb16bc688218d5704936e5227dcf15627e10ebc2d31a63b4400efc9c164', 'KL-077:full_execution_replay_atomicity_dc': 'c9944c8eeea23c7d167e253197ba9e65439fc89f43aa360353ed0019c8fe9a2d', 'KL-028:b07_dc': 'e246ed617b72dfeea889fa4929ab88f9da3394496d7c00b79b6e0dd511f1e1a2', 'KL-028:b16_dc': 'a1bbe7c06827c27c10504851a66fb9ccd78394d9ec8079b487d0af1dafd999dd', 'KL-026:i01_dc': '2932e90178d230d3bd2ef002933d5fece4395ab6756c4e46b9f7d65e0d19fbb8', 'KL-026:i02_dc': 'ee5a60e38ed027fd6f09aef7354e7b5ab503fe022f8837f71d4e7d1b3cd9ede5', 'KL-026:i03_dc': '2a647e52fd8fee70691e5279d3d1a2632edddb971d3c223a1c2fdd6b5dde96ae', 'KL-026:i04_dc': '4be4e09b2a3c9f9d5ae66fd0291bb9e9fcdb0c1d39c8d41f5d770b6c9e24b4d2', 'KL-026:i05_dc': '5011fb62871694abe23239063f923daa6dce59df5649036455817ed7635433be', 'KL-026:i06_dc': '65500c852227e4a2ddb6d7f39d55880a4548237a92be5ba09b7580e0a7c3cb31', 'KL-026:i07_dc': '15c1c1266d7f723631a3a0c61b516ad5f7ff79494ce690416f51ba29e5b6c8d1', 'KL-026:i08_dc': 'dbe3832eb088d50cd0d5c1ae0bba3764433133aa862542889c310ac7626c7228', 'KL-026:i09_dc': '6227a26862097ba2f06dbf4ab99e3596a3abbfdaa2e2f1bb1f0cb2133ec6010a', 'KL-026:time_boundary_pu': 'ce8e3e58e3a2ad0d67666c7681b04576473113b0d91974221a9ac9527692b674', 'KL-023:factset_complete_writer_interleaving_dc': '1b54ce3c1cb0fd1b5d117d1e7155d92ce919c218cfd56ccf36a8e0d4863723d8', 'KL-023:factset_seal_frontier_atomicity_and_replay_dc': '85ccee0e5008c8f006cb387bee09c0c441705251ab843c8f1cd20b531f4b2f64', 'KL-028:b01_pu': 'dbbaaeb4f0b1f67215c0659b0d203042c1088fc020bb31d8257dc47fa4bde2f6', 'KL-028:b01_dc': 'c0b42302bc8cfdd980187e07e6671654d46ac6d0878b9f9c08ce46a1bf110c67', 'KL-028:b02_dc': '819e95d9a8d60083f2d4143be3c1636424b59ab519be0b30852c4b7f097cf310', 'KL-028:b03_dc': '33937d58907a2abda0dfc8f9418c647c442929fa5a5f2e6fcb3a17cd54bd6f6a', 'KL-021:t2_global_commit_rollback_and_effective_at_semantics': 'a4cdb8b0847c37b1661c144e3115d8de2243a29c4913dba3d89858c1560ab855', 'KL-028:b04_dc': 'dbbee9074704daf487305816e38257798d56627d549b08a77be9e7690538e2d0', 'KL-028:b05_dc': '3fcceb7b2c85fe943707e6314616d6e3f937783e7a14868bfdc2264250463d31', 'KL-028:b06_dc': '8beb5b23a00a770d027a1c0d50c0b8d2e0ff86fae19147d1ba341566eeb3ab59', 'KL-028:b11_dc': '01ef9307f0cec128c550984172e5f49509426fe85912d1011ae58866d54e2d81', 'KL-028:b12_dc': '179302c473c7e5290f94e56941ae55e4b4311e239d8eac16b17c0f8717c6b666', 'KL-028:b13_dc': 'c5fa673aee7bf8f944a61f362e66b10558bdd28cc1daf505095b2f16a42b32de', 'KL-028:b14_registry_failclosed_stop_support_dc': '100675ab990ce9c94ed726a1b4b35ed8f2f04d618f8eded8c3e4d95915624fed', 'KL-028:b15_dc': 'cd3df20c6f6d9d4c9f499f8e033325a8341620918e54a7af9146f4ca1abe6ff5', 'KL-028:b17_pu': '512659b83a91ad16d3d05fc75e44f688036218eecd850ea93f0c59db2be43b4e', 'KL-028:b17_dc': 'be4ce4fd8cae272b9f3c710f63ff02628c6793edf1eab872300271c1e886f691', 'KL-022:validity_closure_minimum_and_missing_values_pu': '77f1f0e66c036f3a3b68610b1a1b788cf3834b8fca381276b2a10c5c853e2a0d', 'KL-022:timeless_policy_dependency_closure_pu': '661ec30174fbeb8d271d65b71723f1282bad3d92b99ff93cfcd3f951e2d8f6d1', 'KL-022:t6_certificate_and_minimum_closure_dc': '7b0537d8176fb2d010ed04e4bb4194ba52e60b83383af2b83538e1fe6ea5ce79', 'KL-028:b08_pu': '3f1c07c8f8d2d552369afc14d95acc1b5aa06fb394938a81eb1172f354fee44a', 'KL-028:b09_pu': 'abf0c2bf101bab7a7b9dfacc52cbc90d1af8c59e8aa409ed7b1d890a5be510be', 'KL-028:b09_dc': 'f3690ee3bec27585add38fae370477f70d60c4db92c7c56072152d6d9997d501', 'KL-028:b10_pu': '842c24fcb7b78cd00c33fa4d477aa1f40a916fb653aa73a771301ffafccd8502', 'KL-028:b18_pu': 'e7b63b7177b8cc20330ffaa54e4fbca3bd4c9b8ab9e3a456d3d4e72523f9f176', 'KL-027:demo_namespace_and_boundary_pu': '66647bb1b03c243b7b53945026d29c821be0d633cf017342b4690b14d86542f4', 'KL-027:demo_scope_denials_dc': '8654b63f46d0f2f8c039060dd1137637cf945efe5ab92bf9df71bbdcb91b491b', 'KL-028:boundary_namespace_pu': '8a1f0daddefc1818862deedecf9e2effa0609fd91079cb40524939441886eed3', 'KL-029:shadow_namespace_and_boundary_pu': 'b4882ae92d1328df35251a024212c6aba66ae9bb5849fc211d1bc40c97e1a98e', 'KL-029:shadow_strict_wire_pu': 'f739601de3c33239203549a8e6836ca24111055ee8f217d4ff514d6df8894f1a', 'KL-029:shadow_evaluation_principal_live_denials_dc': '9f639ac3f9f60bd05beb042cff3c83d25f41eae1a9e5ada4dbe96856633ded70', 'KL-029:shadow_test_authorization_crossing_denials_dc': '49686edec7cc25818e5b379ff97c2d3f6f52179c90086a1fd60297e88b4dab22', 'KL-029:shadow_owner_payload_denials_dc': 'b49df8a9edcf2f50351d2aff8dad4f3351516372e2af6f135b27a1f214461d01', 'KL-029:shadow_declared_evaluation_storage_dc': '3bb80c4317b9d118ad4364287dfe89701ad08368a1408ff6acd83d78f8c9b14f'}
M3_REGRESSION_COMMANDS = ['uv run kl test-unit', 'uv run kl test-harness', 'uv run kl check-harness', 'uv run pytest -q tests/db/test_boundary_acceptance.py', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b01_unsealed_canonical_denial', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b02_stale_frontier_seal_race', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b03_sealed_immutability_ready_barrier', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b04_relevant_revoke_issue_reauthorize', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b05_unrelated_revoke_preserves_eligibility', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b06_revoke_before_publish', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b07_revoke_current_execution_denial', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b09_server_minimum_certificate', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b11_backdated_revoke_commit_linearization', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b12_future_revoke_immediate_at_commit', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b13_revoke_rollback_zero_effects', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b14_registry_failclosed_stop_support', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b15_fresh_registry_both_orders', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b16_continue_resume_after_invalidation', 'uv run pytest -q tests/db/test_boundary_acceptance.py::test_b17_transitive_revoke_denied', 'uv run pytest -q tests/db/test_call_ledger.py', 'uv run pytest -q tests/db/test_deterministic_planning.py', 'uv run pytest -q tests/db/test_factsets.py', 'uv run pytest -q tests/db/test_factsets.py::test_complete_serializes_with_candidate_writer', 'uv run pytest -q tests/db/test_factsets.py::test_seal_frontier_atomicity_and_old_replay', 'uv run pytest -q tests/db/test_full_action_preparation.py', 'uv run pytest -q tests/db/test_full_test_execution.py', 'uv run pytest -q tests/db/test_full_test_execution.py::test_continue_resume_rechecks', 'uv run pytest -q tests/db/test_full_test_execution.py::test_replay_and_atomicity', 'uv run pytest -q tests/db/test_migrations.py', 'uv run pytest -q tests/db/test_migrations.py tests/db/test_transaction_interfaces.py', 'uv run pytest -q tests/db/test_planning.py', 'uv run pytest -q tests/db/test_planning_progress.py', 'uv run pytest -q tests/db/test_preparation.py', 'uv run pytest -q tests/db/test_protocol_execution.py', 'uv run pytest -q tests/db/test_protocol_interleavings.py', 'uv run pytest -q tests/db/test_protocol_interleavings.py::test_artifact_revoke_vs_issue', 'uv run pytest -q tests/db/test_protocol_interleavings.py::test_artifact_revoke_vs_publish', 'uv run pytest -q tests/db/test_protocol_interleavings.py::test_artifact_revoke_vs_start', 'uv run pytest -q tests/db/test_protocol_interleavings.py::test_cancel_vs_dispatch', 'uv run pytest -q tests/db/test_protocol_interleavings.py::test_expiry_vs_start', 'uv run pytest -q tests/db/test_protocol_interleavings.py::test_publish_vs_user_revoke', 'uv run pytest -q tests/db/test_protocol_interleavings.py::test_seal_vs_input_update', 'uv run pytest -q tests/db/test_protocol_interleavings.py::test_start_vs_user_revoke', 'uv run pytest -q tests/db/test_protocol_interleavings.py::test_takeover_vs_commit', 'uv run pytest -q tests/db/test_safety_registry.py', 'uv run pytest -q tests/db/test_safety_registry.py::test_t2_global_commit_rollback_and_effective_at_semantics', 'uv run pytest -q tests/db/test_shadow_isolation.py::test_declared_evaluation_storage_isolation', 'uv run pytest -q tests/db/test_shadow_isolation.py::test_evaluation_principal_live_denials', 'uv run pytest -q tests/db/test_shadow_isolation.py::test_shadow_payload_owner_denials', 'uv run pytest -q tests/db/test_shadow_isolation.py::test_test_authorization_crossing_denials', 'uv run pytest -q tests/db/test_test_only_demo.py', 'uv run pytest -q tests/db/test_test_only_demo.py::test_expiry_then_deny', 'uv run pytest -q tests/db/test_test_only_demo.py::test_fdn_repair', 'uv run pytest -q tests/db/test_test_only_demo.py::test_full_trajectory', 'uv run pytest -q tests/db/test_test_only_demo.py::test_production_shadow_denials', 'uv run pytest -q tests/db/test_test_only_demo.py::test_revoke_then_deny', 'uv run pytest -q tests/db/test_transaction_interfaces.py', 'uv run pytest -q tests/db/test_transaction_interfaces.py::test_t6_authorization_evaluator_persists_exact_minimum_certificate', 'uv run pytest -q tests/e2e/test_authorization_evaluator.py', 'uv run pytest -q tests/unit/protocol/test_authorization.py', 'uv run pytest -q tests/unit/protocol/test_authorization.py::test_timeless_dependency_requires_auditable_policy_in_same_transitive_closure', 'uv run pytest -q tests/unit/protocol/test_authorization.py::test_validity_closure_uses_every_bound_and_denies_missing_or_elapsed_basis', 'uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py', 'uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b01_unsealed_canonical_denial', 'uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b08_missing_validity_denied', 'uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b09_server_minimum_closure', 'uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b10_expiry_without_status_job', 'uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b17_transitive_closure_omission_denied', 'uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_b18_timeless_policy_reason_required', 'uv run pytest -q tests/unit/protocol/test_boundary_acceptance.py::test_boundary_namespace', 'uv run pytest -q tests/unit/protocol/test_execution.py', 'uv run pytest -q tests/unit/protocol/test_factsets.py', 'uv run pytest -q tests/unit/protocol/test_interleaving_namespace.py::test_time_boundaries', 'uv run pytest -q tests/unit/protocol/test_shadow_isolation.py tests/db/test_shadow_isolation.py', 'uv run pytest -q tests/unit/protocol/test_shadow_isolation.py::test_namespace_and_boundary', 'uv run pytest -q tests/unit/protocol/test_shadow_isolation.py::test_strict_shadow_wire', 'uv run pytest -q tests/unit/protocol/test_test_only_demo.py::test_namespace_and_boundary', 'uv run pytest -q tests/unit/workflow/test_call_ledger.py', 'uv run pytest -q tests/unit/workflow/test_planning.py']

# HG045 adds one prospective prerequisite without rewriting any HG044 witness.
M3_EXIT_TASK_CHECKS['source_decision_conformance'] = {'KL-080': ['source_matrix_pu', 'source_basis_pu', 'source_namespace_pu', 'source_preparation_owners_dc', 'source_canonical_full_t6_dc', 'source_invalid_reconstruction_dc', 'source_freshness_predicate_support_dc', 'source_owner_trajectories_dc', 'source_current_denials_dc', 'source_repair_replay_expiry_dc', 'source_suite_dc', 'source_suite_pu']}
M3_CHECK_CONTRACT_DIGESTS.update({'KL-080:source_matrix_pu': '19af2ee64ff3252048fe1647b4db2a5650da19a422dd53dbe8ea373d0c7d04f8', 'KL-080:source_basis_pu': '01bb79e806cd5d4d1cb2fa0ac6bb9f9a14b495db3a70cfc8d91aabd938e8e394', 'KL-080:source_namespace_pu': '3fc5b595fb73d9b5c125974a2c79879ad82219e40735c82cd2e22f3fc5fc62d6', 'KL-080:source_preparation_owners_dc': 'f909c9abe19c9172763608774fef3e6e059b38753724a6c7de3ff288a21e5a04', 'KL-080:source_canonical_full_t6_dc': '9912e7ef6a61a4f6fc3e08283d75526c37be7616562b792489acb299a1eaa6b8', 'KL-080:source_invalid_reconstruction_dc': '5af6a7a4affcfb962f2026fe92efdbe50de776d654461e790036e2467358cfa9', 'KL-080:source_freshness_predicate_support_dc': 'd321e7e4fa2ca78de7a67560a8fb54fa97b46d9f172a9eab2ae655265a51f10f', 'KL-080:source_owner_trajectories_dc': '135b9e5ed810649b51be0147e0a9b3b16125f1793cd26e895af9d4a42843df6b', 'KL-080:source_current_denials_dc': 'f31dc1775decf90c5c6570ae622e11785a049a1d263bb1eb1b132f7303b3e405', 'KL-080:source_repair_replay_expiry_dc': 'e2789843bb544a414b1eb9a894b218db9e3c2fb75ff634b553686ace4436d879', 'KL-080:source_suite_dc': '28f767bb41b5680cd4d20551473364bcac8910e8511cc867ccb63936eadadc80', 'KL-080:source_suite_pu': '91323a2050340406822bbbfdd6ac6cea046d323cd96324c61a7159e948ee4f8d'})
M3_REGRESSION_COMMANDS.extend(['uv run pytest -q tests/unit/workflow/test_source_decision_conformance.py::test_source_matrix', 'uv run pytest -q tests/unit/workflow/test_source_decision_conformance.py::test_basis_and_actual_separation', 'uv run pytest -q tests/unit/workflow/test_source_decision_conformance.py::test_namespace', 'uv run pytest -q tests/db/test_source_decision_conformance.py::test_preparation_owners', 'uv run pytest -q tests/db/test_source_decision_conformance.py::test_canonical_full_t6', 'uv run pytest -q tests/db/test_source_decision_conformance.py::test_invalid_source_reconstruction', 'uv run pytest -q tests/db/test_source_decision_conformance.py::test_freshness_predicate_support', 'uv run pytest -q tests/db/test_source_decision_conformance.py::test_owner_trajectories', 'uv run pytest -q tests/db/test_source_decision_conformance.py::test_current_denials', 'uv run pytest -q tests/db/test_source_decision_conformance.py::test_repair_replay_expiry', 'uv run pytest -q tests/db/test_source_decision_conformance.py', 'uv run pytest -q tests/unit/workflow/test_source_decision_conformance.py', 'uv run pytest -q tests/unit/workflow/test_deterministic_planning.py', 'uv run pytest -q tests/unit/workflow/test_full_action_preparation.py'])

M1_TASK_IDS = {f'KL-{number:03d}' for number in range(1, 10)}
M1_CLOSURE_M2_TASK_IDS = {
    'KL-010', 'KL-011', 'KL-012', 'KL-013', 'KL-014',
    'KL-015', 'KL-016', 'KL-017', 'KL-018', 'KL-055',
}
# Current M2 may grow through later governance without rewriting the historical M1
# closure revision that proved the original refinement set.
M2_REFINED_TASK_IDS = M1_CLOSURE_M2_TASK_IDS | {'KL-072', 'KL-073'}
WAVE_REFINED_TASK_IDS = {'KL-023', 'KL-024', 'KL-050'}
M2_TASK_IDS = M2_REFINED_TASK_IDS
PLANNING_FIXTURE_PATH = 'tests/db/test_transaction_interfaces.py'
PLANNING_FIXTURE_CONTRACT = (
    "KL-024 may change only the DATE literal 2026-09-27 to 2026-09-28 in the "
    "INTENT local_date UPDATE inside test_reauthorize_requires_atomic_intent_success. "
    "Preserve every other byte in tests/db/test_transaction_interfaces.py, including "
    "the head day GuardRequired assertion, restoration to 2026-09-26, other negative "
    "cases and successful atomic intent completion. Do not skip tests or weaken "
    "uq_s27_active_partition, transaction guards or authorization semantics."
)
PLANNING_SUBJECT_SCOPE_PATH = 'tests/db/test_subject_scope.py'
PLANNING_SUBJECT_SCOPE_CONTRACT = (
    'KL-024 may replace only the two expected-version expressions REVISION with _MIGRATIONS.HEAD_REVISION in test_populated_downgrade_fails_before_guard_or_acl_changes. Preserve every other byte in tests/db/test_subject_scope.py, including all downgrade exception, trigger, lookup, ACL, namespace, binding and retained-data assertions. Do not skip tests, alter historical migrations, change guards or weaken subject isolation.'
)
LEDGER_PLANNING_FIXTURE_PATH = "tests/db/test_planning.py"
LEDGER_PLANNING_FIXTURE_CONTRACT = 'KL-025 may add only import os, the exact _planning_namespace helper and its fixture assignment from HG-034 planning_namespace.patch to tests/db/test_planning.py. Preserve every other byte, including all six planning tests, assertions, seeds, policies, bootstrap and cleanup. KINETICLOOP_KL024_FIXTURE_OWNER unset preserves KL024 defaults; exact KL-025 derives validated task-owned SHA/worktree namespaces; every other value fails before reset/bootstrap/teardown. No arbitrary project/database target, skip, semantic fixture repair or prerequisite product edit is authorized.'
LEDGER_PLANNING_NAMESPACE_HELPER = 'def _planning_namespace(short: str) -> DatabaseNamespace:\n    if not 7 <= len(short) <= 12 or any(c not in "0123456789abcdef" for c in short):\n        raise ValueError("invalid planning fixture commit suffix")\n    owner = os.environ.get("KINETICLOOP_KL024_FIXTURE_OWNER")\n    if owner is None:\n        return DatabaseNamespace(f"kineticloop-kl024-{short}", f"kineticloop_kl024_{short}")\n    if owner != "KL-025":\n        raise ValueError("unsupported planning fixture owner")\n    suffix = DatabaseNamespace.for_worktree(ROOT).project_name[-12:]\n    return DatabaseNamespace(\n        f"kineticloop-kl025-plan-{short}-{suffix}",\n        f"kineticloop_kl025_plan_{short}_{suffix}",\n    )\n\n\n'
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
        'KL-008': {'real_data_shadow_forbids_live_head_issuance_binding',
                   'test_only_scope_requires_isolation'},
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
    'KL-073': {
        'fixed_wall_clock_fixture_removed',
        'blocked_regression_cases_pass',
        'expired_and_stale_negative_cases_preserved',
        'transaction_interface_suite_passes',
        'complete_db_suite_passes',
        'full_repository_regression_passes',
        'harness_validation_passes',
    },
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
    'KL-015', 'KL-016', 'KL-017', 'KL-018', 'KL-072', 'KL-073',
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
    errors = fitness_evaluation_packet_errors(task, text)
    name = task['id']
    if task['task_identity'] not in text:
        errors.append('packet-identity:' + name)
    if task['status'] == 'SUPERSEDED':
        disposition_reason = task.get('disposition_reason')
        superseded_by = task.get('superseded_by')
        structured_retirement = disposition_reason is not None or superseded_by is not None
        if structured_retirement:
            scheduling_barriers = re.findall(
                r'^Scheduling barrier: MUST NOT be scheduled\.$', text, re.M)
            scheduling_valid = (
                scheduling_barriers == ['Scheduling barrier: MUST NOT be scheduled.'])
        else:
            legacy_barrier = (
                r'^Task identity `' + re.escape(task['task_identity'])
                + r'` is traceability-only and MUST NOT be scheduled\.')
            scheduling_valid = len(re.findall(legacy_barrier, text, re.M)) == 1
        if not scheduling_valid:
            errors.append('packet-superseded-schedulable:' + name)
        if structured_retirement:
            disposition = section(text, 'Disposition') or ''
            if not isinstance(disposition_reason, str) or not disposition_reason.strip():
                errors.append('packet-superseded-reason:' + name)
            elif re.findall(r'^Reason: (.*)$', disposition, re.M) != [disposition_reason]:
                errors.append('packet-superseded-reason:' + name)
            replacements = re.findall(r'^- (KL-[0-9]{3}[A-Z]?)$', disposition, re.M)
            if (not isinstance(superseded_by, list)
                    or not superseded_by
                    or replacements != superseded_by
                    or len(replacements) != len(set(replacements))
                    or len(superseded_by) != len(set(superseded_by))):
                errors.append('packet-superseded-replacements:' + name)
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
    if (name in M2_REFINED_TASK_IDS or (name == 'KL-047'
            and task.get('packet_refinement') == 'ENFORCEABLE') or (name in (WAVE_REFINED_TASK_IDS | {'KL-019', 'KL-025', 'KL-074', 'KL-026', 'KL-027', 'KL-075', 'KL-076', 'KL-077', 'KL-078', 'KL-079', 'KL-080', 'KL-028', 'KL-029', 'KL-081'})
                                      and task.get('packet_refinement') == 'ENFORCEABLE')):
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
    if name == 'KL-081':
        environment = section(text, 'Environment and acceptance evidence') or ''
        if ('`kineticloop_kl081_<SHA7>_<ROOT12>`' not in environment
                or '`kineticloop-kl081-<SHA7>-<ROOT12>`' not in environment
                or 'kl036' in environment):
            errors.append('packet-recovery-namespace:KL-081')
    if name == 'KL-014':
        command_surface = section(text, 'Public command surface') or ''
        if bullets(command_surface) != task.get('commands', []):
            errors.append('packet-command-surface:' + name)
    if name in {'KL-016', 'KL-072'}:
        command_surface = section(text, 'Registry-gated command surface') or ''
        if bullets(command_surface) != task.get('commands', []):
            errors.append('packet-command-surface:' + name)
    if name == 'KL-024' and PLANNING_FIXTURE_PATH in task.get('write_paths', []):
        if (section(text, 'Fixture-only scope exception') or '').strip() != PLANNING_FIXTURE_CONTRACT:
            errors.append('packet-planning-fixture-contract:' + name)
    if name == 'KL-024' and PLANNING_SUBJECT_SCOPE_PATH in task.get('write_paths', []):
        if ((section(text, 'Subject-scope current-head exception') or '').strip()
                != PLANNING_SUBJECT_SCOPE_CONTRACT):
            errors.append('packet-planning-subject-scope-contract:' + name)
    if name == 'KL-025' and LEDGER_PLANNING_FIXTURE_PATH in task.get('write_paths', []):
        if ((section(text, 'Planning fixture namespace exception') or '').strip()
                != LEDGER_PLANNING_FIXTURE_CONTRACT):
            errors.append('packet-ledger-planning-fixture-contract:' + name)
    errors.extend(source_decision_packet_errors(task, text))
    errors.extend(m3_next_wave_packet_errors(task, text))
    errors.extend(readiness_packet_errors(task, text))
    errors.extend(execution_packet_errors(task, text))
    errors.extend(m3_boundary_shadow_packet_errors(task, text))
    return errors


def wave_definition_errors(task):
    """Keep the executable wave identity, ownership and gate boundaries explicit."""
    name = task['id']
    if name not in WAVE_REFINED_TASK_IDS:
        return []
    errors = []
    dependencies = ['KL-055'] if name == 'KL-050' else ['KL-015']
    if (task.get('task_identity') != 'harness-backlog-v0.2/' + name
            or task.get('depends_on') != dependencies
            or task.get('conditional_depends_on') != []):
        errors.append('wave-identity-or-dependency:' + name)
    resources = ({'provider_contracts', 'registry_coordination'} if name == 'KL-050'
                 else {'transaction_interfaces', 'user_coordination'})
    if name == 'KL-024':
        resources.update({'planning_ledger', 'migration_chain', 'persistence_schema'})
    if not resources <= set(task.get('resource_keys', [])):
        errors.append('wave-resource-contention:' + name)
    core = name != 'KL-050'
    policy = 'SERIALIZE_WITH_OTHER_HOTSPOT_TASKS' if core else 'PARALLEL_IF_DEPENDENCIES_MET'
    if (task.get('parallel_write_policy') != policy
            or task.get('shared_hotspot') is not core):
        errors.append('wave-scheduling-policy:' + name)
    paths = task.get('write_paths', [])
    if (task.get('packet_refinement') != 'ENFORCEABLE'
            or task.get('write_paths_status') != 'ENFORCEABLE'
            or not paths or any('*' in path or path.endswith('/__init__.py')
                                or (path in {PLANNING_FIXTURE_PATH, PLANNING_SUBJECT_SCOPE_PATH}
                                    and name != 'KL-024')
                                for path in paths)
            or (core and 'src/kineticloop/persistence/transactions.py' not in paths)
            or (not core and any(path.startswith(('src/kineticloop/persistence/',
                                                 'src/kineticloop/protocol/',
                                                 'src/kineticloop/workflow/')) for path in paths))):
        errors.append('wave-write-ownership:' + name)
    contracts = task.get('check_contracts', [])
    ids = [item.get('check_id') for item in contracts if isinstance(item, dict)]
    generic = re.compile(r'(?:^task_scope_|todo|tbd|placeholder)', re.I)
    if (not contracts or len(ids) != len(set(ids))
            or ids != task.get('checks_required_for_this_task')
            or any(not isinstance(item, dict)
                   or set(item) != {'check_id', 'command', 'pass_oracle'}
                   or any(not isinstance(item.get(field), str) or not item[field].strip()
                          or generic.search(item[field])
                          for field in ('check_id', 'command', 'pass_oracle'))
                   for item in contracts)):
        errors.append('wave-check-contract:' + name)
    if (task.get('evidence_paths') != [f'docs/exec-plans/evidence/{name}/**']
            or task.get('requirements_covered') != []):
        errors.append('wave-evidence-or-requirement-claim:' + name)
    expected_environment = ['ISOLATED_POSTGRESQL_NAMESPACE'] if core else []
    if task.get('environment_requirements') != expected_environment:
        errors.append('wave-environment:' + name)
    return errors


def planning_fixture_content_errors(before: bytes, after: bytes) -> list[str]:
    """Permit exactly the reviewed one-literal fixture repair over protected base."""
    start = before.find(b'def test_reauthorize_requires_atomic_intent_success(')
    end = before.find(b'\ndef ', start + 1)
    if end == -1:
        end = len(before)
    old = b"UPDATE kineticloop.planning_intents SET local_date=DATE '2026-09-27' WHERE id=%s"
    new = old.replace(b'2026-09-27', b'2026-09-28')
    block = before[start:end] if start >= 0 else b''
    if start < 0 or block.count(old) != 1:
        return ['planning-fixture-baseline-unexpected:KL-024']
    expected = before[:start] + block.replace(old, new) + before[end:]
    if after != expected:
        return ['planning-fixture-content-scope:KL-024']
    return []


def planning_subject_scope_content_errors(before: bytes, after: bytes) -> list[str]:
    """Permit only two current-head expressions in the named downgrade oracle."""
    start = before.find(b'def test_populated_downgrade_fails_before_guard_or_acl_changes(')
    end = before.find(b'\ndef ', start + 1)
    if end == -1:
        end = len(before)
    block = before[start:end] if start >= 0 else b''
    old_nested = b'                REVISION,\n'
    old_outer = b'            REVISION,\n'
    # Match full lines: the outer indentation must not match a nested suffix.
    old_nested = b'\n' + old_nested
    old_outer = b'\n' + old_outer
    if (start < 0 or block.count(old_nested) != 1 or block.count(old_outer) != 1
            or block.count(b'REVISION,') != 2):
        return ['planning-subject-scope-baseline-unexpected:KL-024']
    expected_block = block.replace(old_nested, old_nested.replace(
        b'REVISION', b'_MIGRATIONS.HEAD_REVISION')).replace(
        old_outer, old_outer.replace(b'REVISION', b'_MIGRATIONS.HEAD_REVISION'))
    if after != before[:start] + expected_block + before[end:]:
        return ['planning-subject-scope-content-scope:KL-024']
    return []


def ledger_planning_fixture_candidate(before: bytes) -> bytes:
    """Build only the reviewed namespace adaptation; fail on baseline drift."""
    text = before.decode()
    imports = "import subprocess\n"
    fixture = "@pytest.fixture()\ndef database_urls()"
    old = '    lifecycle.namespace = DatabaseNamespace(\n        f"kineticloop-kl024-{short}", f"kineticloop_kl024_{short}"\n    )'
    if (text.count(imports) != 1 or text.count(fixture) != 1 or text.count(old) != 1
            or "def _planning_namespace(" in text or "import os\n" in text):
        raise ValueError("unexpected planning namespace baseline")
    return text.replace(imports, "import os\n" + imports, 1).replace(
        fixture, LEDGER_PLANNING_NAMESPACE_HELPER + fixture, 1).replace(
        old, "    lifecycle.namespace = _planning_namespace(short)", 1).encode()


def ledger_planning_fixture_content_errors(before: bytes, after: bytes) -> list[str]:
    """No assertion, seed, policy, bootstrap, teardown or unrelated byte may drift."""
    try:
        expected = ledger_planning_fixture_candidate(before)
    except (ValueError, UnicodeError):
        return ["ledger-planning-fixture-baseline-unexpected:KL-025"]
    return [] if after == expected else ["ledger-planning-fixture-content-scope:KL-025"]


def task_fixture_scope_errors(root, base, head, task_id, changed):
    if task_id == 'KL-080':
        errors = []
        for path in sorted(SOURCE_FIXTURE_REPLACEMENTS):
            if path not in changed:
                errors.append('source-fixture-correction-missing:KL-080:' + path)
            else:
                errors.extend(source_fixture_content_errors(
                    path, git(root, 'show', base + ':' + path),
                    git(root, 'show', head + ':' + path)))
        return errors
    if task_id == 'KL-074':
        errors = []
        for path in ('compose.yaml', 'src/kineticloop/db/lifecycle.py'):
            if path in changed:
                errors.extend(readiness_content_errors(
                    path, git(root, 'show', base + ':' + path),
                    git(root, 'show', head + ':' + path)))
        if READINESS_WORKFLOW_PATH in changed:
            errors.extend(readiness_workflow_errors(
                git(root, 'ls-tree', '--name-only', base, '--', READINESS_WORKFLOW_PATH),
                git(root, 'show', head + ':' + READINESS_WORKFLOW_PATH)))
        return errors
    if task_id == 'KL-019':
        errors = []
        for path in EXECUTION_FIXTURE_BASE_HASHES:
            if path in changed:
                errors.extend(execution_fixture_content_errors(
                    path, git(root, 'show', base + ':' + path),
                    git(root, 'show', head + ':' + path)))
        return errors
    if task_id == 'KL-025' and LEDGER_PLANNING_FIXTURE_PATH in changed:
        return ledger_planning_fixture_content_errors(
            git(root, 'show', base + ':' + LEDGER_PLANNING_FIXTURE_PATH),
            git(root, 'show', head + ':' + LEDGER_PLANNING_FIXTURE_PATH))
    if task_id != 'KL-024':
        return []
    errors = []
    for path, check in (
            (PLANNING_FIXTURE_PATH, planning_fixture_content_errors),
            (PLANNING_SUBJECT_SCOPE_PATH, planning_subject_scope_content_errors)):
        if path in changed:
            errors.extend(check(git(root, 'show', base + ':' + path),
                                git(root, 'show', head + ':' + path)))
    return errors


def ledger_definition_errors(task):
    """Pin KL025 ledger semantics and the narrow merged-prerequisite fixture adaptation."""
    if task.get("id") != "KL-025":
        return []
    expected = {
        "task_identity": "harness-backlog-v0.2/KL-025",
        "depends_on": ["KL-024"],
        "conditional_depends_on": [],
        "commands": [
            "ReserveCall",
            "PermitDispatch",
            "CancelUndispatched",
            "SettleCall",
            "MarkUnknown",
        ],
        "transaction_boundaries": ["T5", "T8"],
        "invariant_ids": ["INV-10", "INV-11", "INV-12", "INV-13", "INV-16", "INV-17"],
        "table_ids": ["S01", "S02", "S03", "S04", "S27", "S28", "S29", "S31", "S32"],
        "context_files": [
            "05_KineticLoop_Protocol_v1.2_FROZEN.md",
            "04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md",
            "09_KineticLoop_Acceptance_and_Release_Gates_v1.2.2.md",
            "docs/contracts/repository_transactions.md",
            "docs/exec-plans/active/KL-024.md",
            "docs/exec-plans/completed/KL-015_RESULT.yaml",
            "docs/exec-plans/integrations/KL-015.json",
            "docs/exec-plans/milestones/M2.json",
        ],
        "entry_conditions": [
            "M2 closure PASS: docs/exec-plans/milestones/M2.json",
            "G-SHADOW and G-REGISTRY remain closed by merged M2 closure",
            "KL-024 implementation and PASS result with fresh required reviews are merged; prerequisite APIs and root-budget representation verified on that merged SHA",
            "Actual merged KL-024 API/root-budget/fence and all called regression fixtures are verified; apply only the authorized planning namespace adaptation and prove task-owned isolation before required checks; any other mismatch requires governance refinement before scheduling",
        ],
        "environment_requirements": ["ISOLATED_POSTGRESQL_NAMESPACE"],
        "deliverables": [
            "typed CallLedgerService over merged KL015 owners and actual merged KL024 planning API",
            "bounded guarded CancelUndispatched owner and root accounting support with exact S27/S31/S32 atomic deltas",
            "PU and migrated PostgreSQL DC budget/cancellation/fence/replay/unknown/physical-send-boundary evidence",
        ],
        "definition_of_done": "every reservation atomically occupies the same root budget across attempts/revisions; cancellation and durable dispatch permission have one winner; first committed permit alone is sendable and replay never resends; stale worker/request/attempt and deadline guards deny new work; UNKNOWN remains occupied without fictional confirmed charges; reliable late settlement updates only accounting/evidence and never restores business authority; all task checks pass without promoting product requirement or release status",
        "parallel_write_policy": "SERIALIZE_WITH_OTHER_HOTSPOT_TASKS",
        "requirements_covered": [],
        "checks_required_for_this_task": [
            "ledger_budget_dimensions_pu",
            "ledger_state_and_replay_pu",
            "ledger_root_budget_atomic_dc",
            "ledger_cancel_dispatch_exclusion_dc",
            "ledger_current_authority_dc",
            "ledger_ack_loss_and_natural_identity_dc",
            "ledger_unknown_and_late_settlement_dc",
            "ledger_physical_dispatch_boundary_pu",
            "ledger_unit_suite_passes",
            "ledger_db_suite_passes",
            "planning_fixture_namespace_isolation_pu",
            "planning_prerequisite_regressions_pass",
            "transaction_owner_regressions_pass",
            "lint_passes",
            "typecheck_passes",
            "harness_validation_passes",
        ],
        "check_contracts": [
            {
                "check_id": "ledger_budget_dimensions_pu",
                "command": "uv run pytest -q tests/unit/workflow/test_call_ledger.py::test_root_budget_and_charge_bounds",
                "pass_oracle": "Versioned budget arithmetic covers call slots and every configured token/cost dimension; settled plus all outstanding reservations plus the new upper bound cannot exceed root limits. Reject negative/unknown/unbounded monetary configurations or explicitly use only enforceable count/token limits without a strict money claim. Pending and UNKNOWN are occupied usage, never confirmed provider charges.",
            },
            {
                "check_id": "ledger_state_and_replay_pu",
                "command": "uv run pytest -q tests/unit/workflow/test_call_ledger.py::test_state_machine_and_non_sendable_replay",
                "pass_oracle": "Only RESERVED can cancel/release or win DISPATCH_INTENT. All post-permit timeout/cancel/crash states retain occupation; no transition resets to RESERVED. Same-key replay returns original identities with sendable=false; changed payload conflicts; permit cannot be interpreted as business commit authority.",
            },
            {
                "check_id": "ledger_root_budget_atomic_dc",
                "command": "uv run pytest -q tests/db/test_call_ledger.py::test_competing_reservations_share_root_budget",
                "pass_oracle": "Two migrated PostgreSQL service contenders across attempts cannot overspend any root dimension. S27 counters, one exact S31 and S32, S02 receipt, S03 event and S04 outbox commit together or all roll back; limits/deadline persist across KL024 join/revision/takeover. Natural intent/attempt/operation_slot uniqueness prevents duplicate occupation.",
            },
            {
                "check_id": "ledger_cancel_dispatch_exclusion_dc",
                "command": "uv run pytest -q tests/db/test_call_ledger.py::test_cancel_and_dispatch_have_one_winner",
                "pass_oracle": "Run both lock-winning orders with bounded barriers and PostgreSQL-observed blocking. RESERVED cancellation and dispatch permission cannot both succeed: cancel winner releases once and forbids permit; permit winner commits DISPATCH_INTENT and forbids refund. Exactly one matching S32 transition and accounting delta persist with receipt/event/outbox atomicity.",
            },
            {
                "check_id": "ledger_current_authority_dc",
                "command": "uv run pytest -q tests/db/test_call_ledger.py::test_stale_attempt_fence_and_deadline_deny",
                "pass_oracle": "Use the actual merged KL024 admission/revision/acquire/renew API. Old owner/fence, obsolete request/attempt, terminal attempt or intent, and trusted-time equality at lease/deadline deny new reservation/permit. Already committed permit may physically send after takeover but conveys no current business-write or T6 authority.",
            },
            {
                "check_id": "ledger_ack_loss_and_natural_identity_dc",
                "command": "uv run pytest -q tests/db/test_call_ledger.py::test_ack_loss_and_payload_conflicts",
                "pass_oracle": "Reserve/permit/cancel/unknown/settle ACK-loss retries never debit/release twice or create another S31/S32. Same key with changed payload conflicts. Permit replay after lost ACK or changed worker authority is historical and sendable=false; a different key cannot redispatch the same reservation. Failures at each mutation/bookkeeping boundary fully roll back.",
            },
            {
                "check_id": "ledger_unknown_and_late_settlement_dc",
                "command": "uv run pytest -q tests/db/test_call_ledger.py::test_unknown_and_late_settlement_are_accounting_only",
                "pass_oracle": "DISPATCH_INTENT without DISPATCHED, timeout, cancellation or lease loss retains all reserved bounds as OUTCOME_UNKNOWN. Reliable receipt/reconciliation idempotently replaces outstanding bounds with confirmed actual usage and immutable S32; untrusted/duplicate/conflicting receipts cannot refund twice. Late settlement after terminal/revision/takeover changes accounting only, preserving intent/attempt/control/authorization state. Competing expected-transition/revision waiters reread locked state and reject stale transitions.",
            },
            {
                "check_id": "ledger_physical_dispatch_boundary_pu",
                "command": "uv run pytest -q tests/unit/workflow/test_call_ledger.py::test_dispatch_occurs_once_after_commit",
                "pass_oracle": "A deterministic fake sender/instrumented transaction proves network invocation happens only after committed DISPATCH_INTENT and transaction release, only for the first sendable winner, once per reservation. Inject precommit rollback, lost permit ACK, postcommit/pre-send crash and post-send/pre-settle crash: replay/recovery never resend the reservation; possible-send windows retain occupation. SDK implicit retry is disabled; each explicit physical retry needs a fresh covered reservation. No live provider/model call is used.",
            },
            {
                "check_id": "ledger_unit_suite_passes",
                "command": "uv run pytest -q tests/unit/workflow/test_call_ledger.py",
                "pass_oracle": "Entire deterministic service/domain file exits 0 without failed/skipped/deselected tests.",
            },
            {
                "check_id": "ledger_db_suite_passes",
                "command": "uv run pytest -q tests/db/test_call_ledger.py",
                "pass_oracle": "Entire migrated PostgreSQL service/interleaving file exits 0 without failed/skipped/deselected tests.",
            },
            {
                "check_id": "planning_fixture_namespace_isolation_pu",
                "command": "uv run pytest -q tests/db/test_call_ledger.py::test_planning_fixture_namespace_isolation",
                "pass_oracle": "Prove unset selector preserves KL024 defaults; exact KL-025 selects bounded lowercase-hex SHA plus resolved-worktree digest namespaces; different worktrees at the same SHA differ. Empty, malformed or arbitrary selectors and invalid SHA suffixes fail before any reset/bootstrap/teardown runner call. Verify actual planning regression reset and cleanup use only the selected KL025-owned namespace; no existing planning semantic assertion changes."
            },
            {
                "check_id": "planning_prerequisite_regressions_pass",
                "command": "KINETICLOOP_KL024_FIXTURE_OWNER=KL-025 uv run pytest -q tests/unit/workflow/test_planning.py tests/db/test_planning.py",
                "pass_oracle": "Actual merged KL024 suites pass without failed/skipped/deselected tests in KL025-owned isolated planning fixture namespaces; unchanged KL024 contract and historical evidence remain intact.",
            },
            {
                "check_id": "transaction_owner_regressions_pass",
                "command": 'KINETICLOOP_KL022_COMPOSE_PROJECT="kineticloop-kl025-reg-$(git rev-parse --short HEAD)" KINETICLOOP_KL022_DATABASE="kineticloop_kl025_reg_$(git rev-parse --short HEAD)" uv run pytest -q tests/db/test_transaction_interfaces.py tests/unit/persistence/test_transactions.py',
                "pass_oracle": "Existing owner/lock/fence/receipt/settlement regressions exit 0 without failed/skipped/deselected tests in the exact KL025-owned regression namespace.",
            },
            {"check_id": "lint_passes", "command": "uv run kl lint", "pass_oracle": "Exit 0."},
            {
                "check_id": "typecheck_passes",
                "command": "uv run kl typecheck",
                "pass_oracle": "Exit 0.",
            },
            {
                "check_id": "harness_validation_passes",
                "command": "uv run kl check-harness",
                "pass_oracle": "Exit 0 and HARNESS_CHECK_PASS.",
            },
        ],
        "evidence_paths": ["docs/exec-plans/evidence/KL-025/**"],
        "resource_keys": ["planning_ledger", "transaction_interfaces", "user_coordination"],
        "write_paths": [
            "src/kineticloop/workflow/call_ledger.py",
            "src/kineticloop/persistence/call_ledger.py",
            "src/kineticloop/persistence/transactions.py",
            "tests/unit/workflow/test_call_ledger.py",
            "tests/db/test_call_ledger.py",
            "docs/contracts/call_ledger.md",
            "tests/db/test_planning.py",
        ],
        "write_paths_status": "ENFORCEABLE",
        "review_requirements": ["DB_CONCURRENCY", "GENERAL", "PROTOCOL"],
        "packet_refinement": "ENFORCEABLE",
        "shared_hotspot": True,
    }
    return [
        "ledger-definition-drift:" + field
        for field, value in expected.items()
        if task.get(field) != value
    ]


EXECUTION_TASK_DEFINITION = {'task_identity': 'harness-backlog-v0.2/KL-019',
 'status': 'NOT_STARTED',
 'depends_on': ['KL-017', 'KL-020', 'KL-021', 'KL-022', 'KL-023', 'KL-024', 'KL-025'],
 'conditional_depends_on': [],
 'commands': ['PublishManifest', 'CommitBundle', 'StartSession'],
 'context_files': ['CURRENT_DOCUMENT_INDEX.json',
                   'docs/exec-plans/active/KL-019.md',
                   'docs/exec-plans/completed/KL-015_RESULT.yaml',
                   'docs/exec-plans/completed/KL-017_RESULT.yaml',
                   'docs/exec-plans/completed/KL-020_RESULT.yaml',
                   'docs/exec-plans/completed/KL-021_RESULT.yaml',
                   'docs/exec-plans/completed/KL-022_RESULT.yaml',
                   'docs/exec-plans/completed/KL-023_RESULT.yaml',
                   'docs/exec-plans/completed/KL-024_RESULT.yaml',
                   'docs/exec-plans/completed/KL-025_RESULT.yaml',
                   'docs/contracts/repository_transactions.md',
                   'docs/contracts/planning_intents.md',
                   'docs/contracts/call_ledger.md',
                   '05_KineticLoop_Protocol_v1.2_FROZEN.md',
                   '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md'],
 'entry_conditions': ['M2 migration/contracts merged; G-SHADOW and G-REGISTRY closed by exact '
                      'accepted evidence',
                      'All hard prerequisites have actual merged PASS results and required fresh '
                      'reviews; actual merged KL025 API and fixtures reread before scheduling',
                      'Trusted upstream snapshot/COMMIT_READY and '
                      'proposal/demand/resolution/validation bootstrap boundary is documented as '
                      'synthetic input, never owner-driven planning progress',
                      'Every selected local fixture including nested bootstrap/seed/reset/destroy '
                      'calls is inventoried and its namespace adaptation is mechanically bounded '
                      'before any real reset'],
 'invariant_ids': ['INV-07', 'INV-08', 'INV-09', 'INV-10'],
 'transaction_boundaries': ['T3', 'T6', 'T7'],
 'table_ids': ['S01',
               'S02',
               'S03',
               'S04',
               'S05',
               'S06',
               'S15',
               'S18',
               'S21',
               'S22',
               'S23',
               'S24',
               'S25',
               'S26',
               'S27',
               'S28',
               'S29',
               'S34',
               'S35',
               'S36',
               'S37',
               'S38',
               'S39',
               'S40',
               'S41',
               'S42',
               'S43',
               'S44',
               'S45',
               'S49',
               'S50',
               'S51'],
 'requirements_covered': ['I01', 'I02', 'I04', 'I07', 'A03@DC'],
 'checks_required_for_this_task': ['execution_identity_and_wire_pu',
                                   'execution_fixture_namespace_isolation_pu',
                                   'publish_ready_build_dc',
                                   'commit_test_only_bundle_dc',
                                   'start_new_session_dc',
                                   'execution_stale_commit_basis_dc',
                                   'execution_current_start_denial_dc',
                                   'execution_ack_loss_replay_dc',
                                   'execution_atomic_rollback_dc',
                                   'execution_first_use_contention_dc',
                                   'execution_unit_suite_passes',
                                   'execution_db_suite_passes',
                                   'transaction_owner_regressions_pass',
                                   'planning_prerequisite_regressions_pass',
                                   'ledger_prerequisite_regressions_pass',
                                   'full_unit_regressions_pass',
                                   'full_harness_regressions_pass',
                                   'lint_passes',
                                   'typecheck_passes',
                                   'harness_validation_passes'],
 'check_contracts': [{'check_id': 'execution_identity_and_wire_pu',
                      'command': 'uv run pytest -q '
                                 'tests/unit/protocol/test_execution.py::test_identity_and_wire_scope',
                      'pass_oracle': 'Trusted identity is bound separately from request data. '
                                     'Publication service request has no authorization_scope and '
                                     'accepts only an authenticated registered TEST subject. '
                                     'Existing PublishManifest wire and TEST_ONLY-at-T6/T7 rule '
                                     'remain unchanged. Strict T6/T7 commands match authenticated '
                                     'identity plus registered subject/policy/environment; '
                                     'EVALUATION, production, shadow, cross-subject, actor '
                                     'mismatch, changed policy/environment and arbitrary extra '
                                     'authority fields deny. No owner connection or mutation '
                                     'callback is caller supplied.'},
                     {'check_id': 'execution_fixture_namespace_isolation_pu',
                      'command': 'uv run pytest -q '
                                 'tests/unit/protocol/test_execution.py::test_all_fixture_namespaces_fail_before_reset',
                      'pass_oracle': 'Exercise the owned launch/constructor proof for all four '
                                     'selected fixtures: new protocol execution, unchanged '
                                     'transaction interfaces, planning and call ledger. Derive '
                                     'lowercase 7-12 hex tested SHA plus the exact 12-hex digest '
                                     'of the resolved worktree, with distinct exec/tx/plan/ledger '
                                     'prefixes; different worktrees at the same SHA differ. Before '
                                     'launching the unchanged transaction fixture, the owned '
                                     'launcher must validate its two existing '
                                     'KINETICLOOP_KL022_COMPOSE_PROJECT/DATABASE values equal the '
                                     'exact KL019 tx derivation and reject malformed SHA/digest or '
                                     'mismatched targets before pytest/reset/bootstrap/teardown. '
                                     'Prove the actual unchanged fixture consumes those values for '
                                     'bootstrap/reset and cleanup. New execution/planning/ledger '
                                     'constructors reject invalid selectors/SHA before lifecycle '
                                     'work; preserve unset and exact KL-025 planning behavior. '
                                     'Instrumented runner proof establishes '
                                     'fail-before-launch/reset and selected cleanup; no lifecycle '
                                     'monkeypatch substitutes for a real regression, and no global '
                                     'override rejection or transaction fixture edit is required.'},
                     {'check_id': 'publish_ready_build_dc',
                      'command': 'uv run pytest -q '
                                 'tests/db/test_protocol_execution.py::test_publish_ready_build',
                      'pass_oracle': 'Start with a coherent READY S23 and S21/S22 basis but no '
                                     'S24/S25/current Manifest. Call the typed publication service '
                                     'through the existing T3 owner: exactly one immutable S24 at '
                                     'next S01 generation, complete exact S25 role/basis set, '
                                     'exact artifact roots/closure/registry revision, S23 '
                                     'PUBLISHED, S01 current pointer and one S02/S03/S04 all '
                                     'commit together. No direct SQL publication or generation '
                                     'update substitutes for the call.'},
                     {'check_id': 'commit_test_only_bundle_dc',
                      'command': 'uv run pytest -q '
                                 'tests/db/test_protocol_execution.py::test_commit_test_only_bundle',
                      'pass_oracle': 'Publish through the service first, then use merged KL024 '
                                     'admission/acquire services and explicit trusted upstream '
                                     'bootstrap only. With no daily head, bundle, prescription, '
                                     'issuance or successful intent seeded, strict TEST_ONLY '
                                     'CommitBundle uses existing T6: one coherent '
                                     'S38/S39/S40/S41/S42, exact S27 FOUND_VALID_PLAN/result and '
                                     'S29 COMMITTED plus S02/S03/S04. P/A content and all '
                                     'request/attempt/manifest/epoch/fence references match. S42 '
                                     'server validity end equals the exact minimum of every '
                                     'required finite bound; complete transitive artifact and '
                                     'approved TIMELESS closure/certificate/digest are persisted. '
                                     'Caller can request shortening only. First head parent is '
                                     'null, revision is one and calendar comes from bound trusted '
                                     'policy.'},
                     {'check_id': 'start_new_session_dc',
                      'command': 'uv run pytest -q '
                                 'tests/db/test_protocol_execution.py::test_start_new_session',
                      'pass_oracle': 'Use exact newly committed P/A and no seeded S44/S45. Typed '
                                     'StartSession enters existing T7, rechecks current '
                                     'eligibility, creates one APP_STARTED S44 at IN_PROGRESS '
                                     'revision one, appends one START S45 with exact '
                                     'P/A/hash/scope, server accepted_at and same receipt, and '
                                     'persists correct same-command S01 execution basis event and '
                                     'S02/S03/S04. Changed-key repeated START cannot create a '
                                     'second binding or event. No READY/PLANNED or already-started '
                                     'session seed substitutes for first-session creation.'},
                     {'check_id': 'execution_stale_commit_basis_dc',
                      'command': 'uv run pytest -q '
                                 'tests/db/test_protocol_execution.py::test_stale_commit_basis_denies',
                      'pass_oracle': 'Independently vary stale epoch, noncurrent '
                                     'Manifest/generation, obsolete request/attempt, owner/fence, '
                                     'lease/deadline equality, changed execution basis and '
                                     'mismatched validation/proposal/demand/resolution/closure. '
                                     'Each fresh-key service commit denies with zero new '
                                     'S38-S43/intent-success/head-switch/receipt/event/outbox '
                                     'effects; preserve prior rows byte-for-byte. Guards use '
                                     'locked current state and trusted post-lock time, never '
                                     'payload-only or cached status. Negative upstream '
                                     'perturbations are declared fixture inputs, never proof of an '
                                     'owner-driven upstream transition.'},
                     {'check_id': 'execution_current_start_denial_dc',
                      'command': 'uv run pytest -q '
                                 'tests/db/test_protocol_execution.py::test_current_start_denial',
                      'pass_oracle': 'After real issuance, independent wrong '
                                     'actor/subject/policy/environment, P/A/hash/scope/bundle '
                                     'membership, epoch, active hold/stop, revoked root or '
                                     'transitive artifact, '
                                     'missing/undefined/future-effective/expired dependency and '
                                     'valid_until equality all deny fresh START without '
                                     'S44/S45/S01/S02/S03/S04 effects. Use existing '
                                     'control/registry owner calls when available; explicitly '
                                     'label absent upstream-owner perturbations. Recheck after '
                                     'read-only eligibility to prove it is no bearer permission; '
                                     'deny EVALUATION, production and shadow execution.'},
                     {'check_id': 'execution_ack_loss_replay_dc',
                      'command': 'uv run pytest -q '
                                 'tests/db/test_protocol_execution.py::test_ack_loss_replay_is_historical',
                      'pass_oracle': 'Lose the response after actual committed publish, commit and '
                                     'START; same-key identical retries return exact historical '
                                     'identities and no duplicate '
                                     'generation/bundle/issuance/head-success/session/binding/events/outbox. '
                                     'Changed payload conflicts. Natural publication build and '
                                     'START session uniqueness survive changed-key retries. After '
                                     'authority loss/expiry/revocation, same-key START replay '
                                     'remains available with replayed=true and executable=false, '
                                     'conveys no new execution authorization, and never re-mutates '
                                     'current state; historical commit/publication observations do '
                                     'not bypass fresh START guards.'},
                     {'check_id': 'execution_atomic_rollback_dc',
                      'command': 'uv run pytest -q '
                                 'tests/db/test_protocol_execution.py::test_failures_roll_back_each_boundary',
                      'pass_oracle': 'Inject failure within each existing owner at every '
                                     'write/bookkeeping boundary: T3 S24/S25/S23/S01; T6 first S38 '
                                     'and S39/S40/S41/S42/closure/S27/S29/S01; T7 first '
                                     'S44/S45/S01; each S02/S03/S04/receipt completion. Compare '
                                     'persisted counts, exact prior pointers/statuses and rows to '
                                     'precommand baseline. All effects including first-use '
                                     'coordination rows roll back; retry after rollback succeeds '
                                     'once. No injected success or mocked PostgreSQL substitute.'},
                     {'check_id': 'execution_first_use_contention_dc',
                      'command': 'uv run pytest -q '
                                 'tests/db/test_protocol_execution.py::test_first_use_contention',
                      'pass_oracle': 'Bounded barriers and PostgreSQL-observed locks run competing '
                                     'first-day commits and first-session START commands, '
                                     'including same-key retry. S51 shared precedes S01 and frozen '
                                     'remaining lock stages; S01 serializes absent S38/S44 keys, '
                                     'natural uniqueness and current-request/session eligibility '
                                     'leave one coherent winning outcome and no partial rows. '
                                     'Missing-row support is exclusive to CommitBundle S38 and '
                                     'StartSession S44; wrong owner, subject/day/session/calendar, '
                                     'lifecycle, extra column and arbitrary unrelated insert deny. '
                                     'Existing owner matrix, reverse lock and direct-write '
                                     'negative controls remain effective.'},
                     {'check_id': 'execution_unit_suite_passes',
                      'command': 'uv run pytest -q tests/unit/protocol/test_execution.py',
                      'pass_oracle': 'Entire deterministic domain/identity/namespace file passes '
                                     'without failures or skips; namespace negative proof makes no '
                                     'Docker/database call.'},
                     {'check_id': 'execution_db_suite_passes',
                      'command': 'uv run pytest -q tests/db/test_protocol_execution.py',
                      'pass_oracle': 'Entire real migrated PostgreSQL execution service file '
                                     'passes without failures/skips/deselection in the unique '
                                     'KL019 exec namespace. The fixture audits absence of target '
                                     'publish/commit/START outputs before owner calls and '
                                     'separates explicit upstream bootstrap from asserted owner '
                                     'outputs.'},
                     {'check_id': 'transaction_owner_regressions_pass',
                      'command': 'KINETICLOOP_KL022_COMPOSE_PROJECT="kineticloop-kl019-tx-$(git '
                                 "rev-parse --short HEAD)-$(uv run python -c 'import hashlib,os; "
                                 'from pathlib import Path; '
                                 'print(hashlib.sha256(os.fsencode(Path.cwd().resolve())).hexdigest()[:12])\')" '
                                 'KINETICLOOP_KL022_DATABASE="kineticloop_kl019_tx_$(git rev-parse '
                                 "--short HEAD)_$(uv run python -c 'import hashlib,os; from "
                                 'pathlib import Path; '
                                 'print(hashlib.sha256(os.fsencode(Path.cwd().resolve())).hexdigest()[:12])\')" '
                                 'uv run python tests/unit/protocol/test_execution.py '
                                 '--run-transaction-owner-regressions',
                      'pass_oracle': 'The owned launcher validates actual tested SHA/worktree '
                                     'digest and both supplied existing namespace overrides '
                                     'against the exact KL019 tx derivation before launching only '
                                     'uv run pytest -q tests/db/test_transaction_interfaces.py '
                                     'tests/unit/persistence/test_transactions.py. Prove the '
                                     'actual byte-unchanged transaction fixture consumes both '
                                     'overrides for reset/bootstrap and cleanup. All merged '
                                     'transaction/authorization/registry-consumer owner '
                                     'regressions pass without failures/skips/deselection in that '
                                     'namespace. No fixture mutation, new transaction selector, '
                                     'global rejection of legacy arbitrary overrides, '
                                     'foreign/default namespace execution or altered semantic '
                                     'assertion is permitted.'},
                     {'check_id': 'planning_prerequisite_regressions_pass',
                      'command': 'KINETICLOOP_KL024_FIXTURE_OWNER=KL-019 uv run pytest -q '
                                 'tests/unit/workflow/test_planning.py tests/db/test_planning.py',
                      'pass_oracle': 'Actual merged KL024 domain/service suites pass without '
                                     'failures/skips/deselection in derived KL019 plan namespace; '
                                     'all seeds, calls, guards, oracles and cleanup remain '
                                     'unchanged except exact namespace selection.'},
                     {'check_id': 'ledger_prerequisite_regressions_pass',
                      'command': 'KINETICLOOP_KL025_FIXTURE_OWNER=KL-019 uv run pytest -q '
                                 'tests/unit/workflow/test_call_ledger.py '
                                 'tests/db/test_call_ledger.py',
                      'pass_oracle': 'Actual merged KL025 domain/service suites pass without '
                                     'failures/skips/deselection in derived KL019 ledger '
                                     'namespace. Existing planning namespace isolation probe '
                                     'retains its original selector expectations. Preserve all '
                                     'ledger accounting, dispatch/non-sendable replay/UNKNOWN and '
                                     'root-budget assertions; no call ledger product '
                                     'implementation change.'},
                     {'check_id': 'full_unit_regressions_pass',
                      'command': 'uv run kl test-unit',
                      'pass_oracle': 'All unit tests pass.'},
                     {'check_id': 'full_harness_regressions_pass',
                      'command': 'uv run kl test-harness',
                      'pass_oracle': 'All harness positive and negative controls pass.'},
                     {'check_id': 'lint_passes',
                      'command': 'uv run kl lint',
                      'pass_oracle': 'Exit 0.'},
                     {'check_id': 'typecheck_passes',
                      'command': 'uv run kl typecheck',
                      'pass_oracle': 'Exit 0.'},
                     {'check_id': 'harness_validation_passes',
                      'command': 'uv run kl check-harness',
                      'pass_oracle': 'Exit 0 and HARNESS_CHECK_PASS.'}],
 'evidence_paths': ['docs/exec-plans/evidence/KL-019/**'],
 'resource_keys': ['authorization_core',
                   'registry_coordination',
                   'transaction_interfaces',
                   'user_coordination'],
 'write_paths': ['src/kineticloop/persistence/protocol_execution.py',
                 'src/kineticloop/protocol/execution.py',
                 'src/kineticloop/persistence/transactions.py',
                 'tests/unit/protocol/test_execution.py',
                 'tests/db/test_protocol_execution.py',
                 'docs/contracts/protocol_execution.md',
                 'tests/db/test_planning.py',
                 'tests/db/test_call_ledger.py'],
 'write_paths_status': 'ENFORCEABLE',
 'review_requirements': ['DB_CONCURRENCY', 'GENERAL', 'PROTOCOL'],
 'packet_refinement': 'ENFORCEABLE',
 'shared_hotspot': True,
 'parallel_write_policy': 'SERIALIZE_WITH_OTHER_HOTSPOT_TASKS',
 'environment_requirements': ['ISOLATED_POSTGRESQL_NAMESPACE'],
 'deliverables': ['typed TEST-subject publish/commit/start service adapters over existing T3/T6/T7 '
                  'owners',
                  'owner-scoped first-use S38/S44 creation and real PostgreSQL atomicity, replay, '
                  'denial and contention evidence',
                  'exact local fixture inventory and byte-bound prerequisite namespace '
                  'adaptations'],
 'definition_of_done': 'an authenticated isolated TEST subject publishes a READY build through T3, '
                       'commits a coherent first-day TEST_ONLY bundle/issuance and intent success '
                       'through T6, and starts a new session using the exact newly issued P/A '
                       'through T7; existing owners, registry/evaluator and frozen lock/atomic '
                       'boundaries remain authoritative; only explicit upstream inputs are '
                       'bootstrapped, no tested output is seeded; strict '
                       'identity/policy/environment denials, stale-basis and current-execution '
                       'guards, finite server-computed validity, historical non-executable replay, '
                       'first-use contention and complete rollback pass with isolated real '
                       'PostgreSQL; no production activation, broader workflow or product '
                       'requirement PASS is claimed'}
EXECUTION_PACKET_SECTION_HASHES = {'Identity and service contract': '51fb847fb52426f5be6d0a330ec2431716dac72562d250b052359b45698a34f5', 'Existing owner reuse and bounded missing capabilities': 'c0bb590081116db74c4ff425cab87e44ea4024c444482ad6d59a060d3e7ec6a6', 'Trusted upstream bootstrap boundary': '99b84be94cb1802b0531a5eea82e9bfc73e08c42636766cd1fb50111672253ca', 'Local and hosted lifecycle boundary': 'b3f068112d3465f5e9286e5ea2c627cbca10848611445ec6dbea0d2a148a9938', 'Non-goals': 'ac82892e3bae992f0ba1b93539c6143f47b1d63d4bd9331aac6ef56aeb7dec1d'}
EXECUTION_FIXTURE_CONTRACT = 'KL-019 may change only the exact namespace imports, helper and fixture assignment generated by execution_fixture_candidate in tools/harness/validate_harness.py for tests/db/test_planning.py and tests/db/test_call_ledger.py, anchored to their actual merged KL025 complete-byte hashes. Planning adds exact KL-019 to the existing KINETICLOOP_KL024_FIXTURE_OWNER helper, retaining unset KL024 and exact KL025 behavior. Ledger adds KINETICLOOP_KL025_FIXTURE_OWNER with unset KL025 behavior and exact KL-019 derivation. Invalid/empty/whitespace selectors or malformed short SHA fail before reset/bootstrap/teardown. Both use the exact resolved-worktree digest and bounded KL019 plan/ledger prefixes. Preserve every other byte: semantic seeds, policies, test assertions/callbacks, provisioning, cleanup, planning-selector proof and ledger accounting/non-sendable replay/UNKNOWN/dispatch guards. The transaction fixture remains byte-identical and uses its two existing namespace overrides through the owned validated launcher. No transaction selector, generic fixture repair, skip, arbitrary target or tests/db wildcard is authorized.'
EXECUTION_FIXTURE_BASE_HASHES = {'tests/db/test_planning.py': 'b7b185e069d94f0e67826de02ec630259881add0fa8f5366823d830f95917636', 'tests/db/test_call_ledger.py': 'd3c09d2125844b1ed7e7bc138be41b43a02c0a95efd54d2bfc3012751fe615e2'}
EXECUTION_LEDGER_NAMESPACE_HELPER = 'def _ledger_namespace(short: str) -> DatabaseNamespace:\n    if re.fullmatch(r"[0-9a-f]{7,12}", short) is None:\n        raise ValueError("invalid ledger fixture commit suffix")\n    owner = os.environ.get("KINETICLOOP_KL025_FIXTURE_OWNER")\n    if owner is None:\n        return DatabaseNamespace(f"kineticloop-kl025-{short}", f"kineticloop_kl025_{short}")\n    if owner != "KL-019":\n        raise ValueError("unsupported ledger fixture owner")\n    suffix = DatabaseNamespace.for_worktree(ROOT).project_name[-12:]\n    return DatabaseNamespace(\n        f"kineticloop-kl019-ledger-{short}-{suffix}",\n        f"kineticloop_kl019_ledger_{short}_{suffix}",\n    )\n\n\n'


def execution_definition_errors(task):
    """Pin the minimal KL019 slice without redefining its historical legacy packet."""
    if task.get('id') != 'KL-019' or (
            task.get('packet_refinement') != 'ENFORCEABLE' and 'check_contracts' not in task):
        return []
    return ['execution-definition-drift:' + field
            for field, expected in EXECUTION_TASK_DEFINITION.items()
            if task.get(field) != expected]


def execution_packet_errors(task, text):
    if task.get('id') != 'KL-019' or (
            task.get('packet_refinement') != 'ENFORCEABLE' and 'check_contracts' not in task):
        return []
    errors = []
    for heading, expected in EXECUTION_PACKET_SECTION_HASHES.items():
        actual = (section(text, heading) or '').strip()
        if hashlib.sha256(actual.encode()).hexdigest() != expected:
            errors.append('execution-packet-boundary:' + heading)
    if (section(text, 'Fixture-only scope exceptions') or '').strip() != EXECUTION_FIXTURE_CONTRACT:
        errors.append('packet-execution-fixture-contract:KL-019')
    return errors


def execution_fixture_candidate(path: str, before: bytes) -> bytes:
    """Only the two literal namespace transformations of actual merged KL025 bytes."""
    expected_hash = EXECUTION_FIXTURE_BASE_HASHES.get(path)
    if expected_hash is None or hashlib.sha256(before).hexdigest() != expected_hash:
        raise ValueError('unexpected execution fixture baseline')
    text = before.decode()
    if path == 'tests/db/test_planning.py':
        old_guard = '    if owner != "KL-025":\n'
        new_guard = '    if owner not in {"KL-025", "KL-019"}:\n'
        anchor = '    suffix = DatabaseNamespace.for_worktree(ROOT).project_name[-12:]\n'
        branch = (
            '    if owner == "KL-019":\n'
            '        return DatabaseNamespace(\n'
            '            f"kineticloop-kl019-plan-{short}-{suffix}",\n'
            '            f"kineticloop_kl019_plan_{short}_{suffix}",\n'
            '        )\n'
        )
        if text.count(old_guard) != 1 or text.count(anchor) != 1:
            raise ValueError('unexpected planning helper baseline')
        return text.replace(old_guard, new_guard, 1).replace(anchor, anchor + branch, 1).encode()
    fixture = '@pytest.fixture()\ndef database_urls()'
    old_assignment = (
        '    lifecycle.namespace = DatabaseNamespace(\n'
        '        f"kineticloop-kl025-{short}", f"kineticloop_kl025_{short}"\n'
        '    )'
    )
    if (text.count('import re\n') != 1 or text.count(fixture) != 1
            or text.count(old_assignment) != 1 or 'import os\n' in text):
        raise ValueError('unexpected ledger helper baseline')
    return text.replace('import re\n', 'import os\nimport re\n', 1).replace(
        fixture, EXECUTION_LEDGER_NAMESPACE_HELPER + fixture, 1).replace(
        old_assignment, '    lifecycle.namespace = _ledger_namespace(short)', 1).encode()


def execution_fixture_content_errors(path: str, before: bytes, after: bytes) -> list[str]:
    try:
        expected = execution_fixture_candidate(path, before)
    except (ValueError, UnicodeError):
        return ['execution-fixture-baseline-unexpected:KL-019:' + path]
    return [] if after == expected else ['execution-fixture-content-scope:KL-019:' + path]


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


# Literal prospective scopes; HG057 never implements the HG058 reader purpose.
HG057_ALLOWED_PATTERNS = ['KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Harness_Traceability_v0.3.json', '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md', 'docs/exec-plans/active/KL-036.md', 'docs/exec-plans/active/KL-038.md', 'docs/exec-plans/active/KL-039.md', 'docs/exec-plans/active/KL-064.md', 'docs/exec-plans/active/KL-081.md', 'docs/exec-plans/active/HG-058.md', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md', 'tools/harness/validate_harness.py', 'tests/harness/test_validator.py', 'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json', 'docs/exec-plans/governance/HG-057.yaml', 'docs/exec-plans/evidence/HG-057/**', 'docs/exec-plans/reviews/HG-057/**']
HG058_ALLOWED_PATTERNS = ['tools/harness/compact_evidence.py', 'tools/harness/validate_harness.py', 'tests/harness/test_compact_evidence.py', 'tests/harness/test_review_evidence_provenance.py', 'tests/harness/test_m3_milestone_closure.py', 'tests/harness/test_validator.py', 'tests/harness/test_local_gate.py', 'docs/harness/EVIDENCE_STORAGE_POLICY.md', 'docs/harness/THREAD_REVIEW_CONTRACT.md', 'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md', 'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json', 'docs/exec-plans/governance/HG-058.yaml', 'docs/exec-plans/evidence/HG-058/**', 'docs/exec-plans/reviews/HG-058/**']
HG058_PACKET_SHA256 = '59c8f019227a50d3a7d9f86948ac6f01a9f6a8d843c942c5b20a17e22d37e941'
HG057_REQUIRED_CHECKS = {'recovery', 'validator', 'unit', 'harness', 'lint',
                         'typecheck', 'authority', 'diff'}
HG057_RECOVERY_ENTRY_CONDITIONS = ['HG-057 recovery governance is normally merged into protected master; start a fresh KL-081 branch/worktree with no KL-036 or HG-056 ancestry, results, reviews or evidence imported.', 'HG-058 has an actual merged PASS governance record, fresh GENERAL and SECURITY_DATA_BOUNDARY reviews, complete independently reviewed installed controller/validator/decoder pins and exact-head admission; installed App unit/harness/fullDB gates and cleanup have actually passed. Governance task PASS alone is not runtime prerequisite PASS.', 'Independently compare only the six functional paths at original KL-036 1fee7a4ef9ecb484da24522962a6df4d4c2bd9b9 against its protected functional base before adopting code by fresh edits; record exact blob/diff pins, preserve all failed historical facts, and never cherry-pick old bookkeeping or branch ancestry.', 'All 16 checks start NOT_RUN and run freshly under KL-081; PostgreSQL/Compose namespace uses KL081 plus actual tested SHA7 and resolved-root SHA12. Evidence is policy-compliant from its first commit, with explicit descriptive pytest IDs prepared before execution.']
HG057_REDIRECT_IDS = {'KL-038', 'KL-039', 'KL-064'}


def clean_recovery_projection_errors(before, after):
    """Compare only the approved recovery definitions against their actual base."""
    errors = []
    source = before.get('KL-036')
    successor = after.get('KL-081')
    if source is None or successor is None:
        return ['clean-recovery-successor-missing']
    if source.get('status') != 'NOT_STARTED' or 'KL-081' in before:
        errors.append('clean-recovery-entry')
    expected = json.loads(json.dumps(source).replace('KL-036', 'KL-081'))
    expected_entries = expected.pop('entry_conditions')
    observed = dict(successor)
    entries = observed.pop('entry_conditions', [])
    if observed != expected:
        errors.append('clean-recovery-functional-projection:KL-081')
    if entries != expected_entries + HG057_RECOVERY_ENTRY_CONDITIONS:
        errors.append('clean-recovery-readiness:KL-081')
    for task_id in sorted(HG057_REDIRECT_IDS):
        original = before.get(task_id, {})
        projected = dict(original)
        projected['depends_on'] = [
            'KL-081' if dependency == 'KL-036' else dependency
            for dependency in original.get('depends_on', [])]
        if projected == original or after.get(task_id) != projected:
            errors.append('clean-recovery-dependency-projection:' + task_id)
    changed = {task_id for task_id in set(before) | set(after)
               if before.get(task_id) != after.get(task_id)}
    if changed != HG057_REDIRECT_IDS | {'KL-036', 'KL-081'}:
        errors.append('clean-recovery-task-set')
    retired = after.get('KL-036', {})
    if (retired.get('status') != 'SUPERSEDED'
            or retired.get('superseded_by') != ['KL-081']
            or retired.get('depends_on') != ['KL-081']):
        errors.append('clean-recovery-disposition:KL-036')
    return errors


def governance_allowed_patterns(change_id):
    if change_id == 'HG-057':
        return HG057_ALLOWED_PATTERNS
    if change_id == 'HG-058':
        return HG058_ALLOWED_PATTERNS
    if change_id == 'HG-054':
        return ['tools/harness/compact_evidence.py', 'tools/harness/validate_harness.py',
                'tests/harness/test_compact_evidence.py',
                'tests/harness/test_review_evidence_provenance.py',
                'tests/harness/test_m3_milestone_closure.py', 'tests/harness/test_validator.py',
                'tests/harness/test_local_gate.py', 'docs/harness/EVIDENCE_STORAGE_POLICY.md',
                'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md', 'docs/harness/LOCAL_DB_CI.md',
                'tools/harness/README.md', INDEX, MANIFEST,
                'docs/exec-plans/governance/HG-054.yaml',
                'docs/exec-plans/evidence/HG-054/**', 'docs/exec-plans/reviews/HG-054/**']
    if change_id == 'HG-051':
        return [INDEX, MANIFEST, BACKLOG, TRACEABILITY,
                'HISTORICAL_EVIDENCE_MAPPING.schema.json',
                'tools/harness/compact_evidence.py', 'tools/harness/validate_harness.py',
                'tools/harness/README.md',
                'docs/harness/EVIDENCE_STORAGE_POLICY.md',
                'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
                'docs/harness/THREAD_RESULT_CONTRACT.md',
                'docs/harness/THREAD_REVIEW_CONTRACT.md', 'docs/harness/MERGE_GATE.md',
                'docs/harness/M3_CLOSURE_CONTRACT.md',
                'tests/harness/test_compact_evidence.py',
                'tests/harness/test_review_evidence_provenance.py',
                'tests/harness/test_validator.py', 'tests/harness/test_m3_milestone_closure.py',
                'tests/harness/test_source_decision_scope.py',
                'docs/exec-plans/active/KL-080.md',
                'docs/exec-plans/governance/HG-051.yaml',
                'docs/exec-plans/evidence/HG-051/**', 'docs/exec-plans/reviews/HG-051/**']
    if change_id == 'HG-050':
        return [INDEX, MANIFEST, 'tools/harness/github_app.py',
                'tests/harness/test_local_gate.py', 'docs/harness/LOCAL_DB_CI.md',
                'tools/harness/validate_harness.py', 'docs/exec-plans/governance/HG-050.yaml',
                'docs/exec-plans/evidence/HG-050/**', 'docs/exec-plans/reviews/HG-050/**']
    if change_id == 'HG-047':
        return [INDEX, MANIFEST, 'tools/harness/compact_evidence.py',
                'tools/harness/validate_harness.py', 'tools/harness/README.md',
                'tools/harness/local_gate.py', 'tests/harness/test_local_gate.py',
                'tests/harness/test_compact_evidence.py',
                'tests/harness/test_m3_milestone_closure.py',
                'tests/harness/test_review_evidence_provenance.py', 'tests/harness/test_validator.py',
                'docs/harness/EVIDENCE_STORAGE_POLICY.md', 'docs/harness/LOCAL_DB_CI.md',
                'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md', 'docs/harness/M3_CLOSURE_CONTRACT.md',
                'docs/harness/MERGE_GATE.md', 'docs/harness/THREAD_RESULT_CONTRACT.md',
                'docs/harness/THREAD_REVIEW_CONTRACT.md',
                'docs/exec-plans/governance/HG-047.yaml',
                'docs/exec-plans/evidence/HG-047/**', 'docs/exec-plans/reviews/HG-047/**']

    if change_id == 'HG-049':
        return [INDEX, MANIFEST, BACKLOG, TRACEABILITY,
                'docs/exec-plans/active/KL-080.md', 'tools/harness/validate_harness.py',
                'tests/harness/test_source_decision_scope.py',
                'docs/exec-plans/governance/HG-049.yaml',
                'docs/exec-plans/evidence/HG-049/**', 'docs/exec-plans/reviews/HG-049/**']
    if change_id == 'HG-048':
        return [INDEX, MANIFEST, 'src/kineticloop/cli.py', 'pyproject.toml', 'uv.lock',
                'tools/harness/run_harness_tests.py', 'tools/harness/parallel_observer.py',
                'tools/harness/validate_harness.py', 'tests/harness/test_parallel_runner.py',
                'tools/harness/README.md', 'docs/exec-plans/evidence/HG-048/**',
                'docs/exec-plans/reviews/HG-048/**', 'docs/exec-plans/governance/HG-048.yaml']
    if change_id == 'HG-046':
        return [INDEX, MANIFEST, '.github/workflows/ci.yml', '.github/workflows/db.yml',
                'tools/harness/db_ci.py', 'tools/harness/db_ci_pytest.py',
                'tools/harness/db_policy.py', 'tools/harness/local_gate.py',
                'tools/harness/github_app.py', 'tools/harness/gate_validate.py',
                'tools/harness/gate_pytest.py',
                'tests/harness/test_db_policy.py',
                'tests/harness/test_local_gate.py',
                'tools/harness/local_db/Dockerfile', 'tools/harness/local_db/entrypoint.sh',
                'tools/harness/validate_harness.py', 'tests/harness/test_local_db_ci.py',
                'tests/db/test_startup_readiness.py', 'tests/db/test_workflow.py',
                'docs/harness/LOCAL_DB_CI.md',
                'docs/harness/MERGE_GATE.md', 'docs/harness/M3_CLOSURE_CONTRACT.md',
                'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md',
                'docs/exec-plans/evidence/HG-046/**', 'docs/exec-plans/reviews/HG-046/**',
                'docs/exec-plans/governance/HG-046.yaml']
    if change_id == 'HG-045':
        return [BACKLOG, TRACEABILITY, PROJECT_PLAN, INDEX, MANIFEST,
                MILESTONE_CLOSURE_SCHEMA, 'docs/harness/M3_CLOSURE_CONTRACT.md',
                'tools/harness/validate_harness.py',
                'tests/harness/test_source_decision_scope.py',
                'tests/harness/test_m3_milestone_closure.py',
                'docs/exec-plans/active/KL-080.md',
                'docs/exec-plans/integrations/KL-028.json',
                'docs/exec-plans/integrations/KL-029.json',
                'docs/exec-plans/evidence/HG-045/**',
                'docs/exec-plans/reviews/HG-045/**',
                'docs/exec-plans/governance/HG-045.yaml']
    if change_id == 'HG-044':
        return [MILESTONE_CLOSURE_SCHEMA, 'tools/harness/validate_harness.py',
                'tests/harness/test_m3_milestone_closure.py',
                'docs/harness/M3_CLOSURE_CONTRACT.md', PROJECT_PLAN, INDEX, MANIFEST,
                'docs/exec-plans/evidence/HG-044/**', 'docs/exec-plans/reviews/HG-044/**',
                'docs/exec-plans/governance/HG-044.yaml']
    if change_id == 'HG-024':
        return HG024_ALLOWED_PATTERNS
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


def emergency_governance_task_pair(task_ids, change_ids):
    """Return the sole approved governance/task repair pair; reject every variant."""
    if len(task_ids) != 1 or len(change_ids) != 1:
        return None
    change_id, task_id = next(iter(change_ids)), next(iter(task_ids))
    return (change_id, task_id) if EMERGENCY_GOVERNANCE_TASK.get(change_id) == task_id else None


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
    changed = changed_paths(root, base, head)
    task_candidates = []
    governance_candidates = []
    review_candidates = []
    for path in changed:
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
    emergency_pair = emergency_governance_task_pair(task_ids, change_ids)
    emergency_task_id = emergency_pair[1] if emergency_pair else None
    emergency_scope_used = any(
        matches(path, HG024_EMERGENCY_SCOPE_PATTERNS) for path in changed
    )
    if 'HG-024' in change_ids and emergency_scope_used and emergency_pair is None:
        raise ValueError('ci-emergency-pair-required:HG-024:KL-073')
    if (len(task_ids), len(change_ids)) not in ((1, 0), (0, 1)) and emergency_task_id is None:
        raise ValueError(f'ci-change-record-count:task={len(task_ids)},governance={len(change_ids)}')
    selected = next(iter(change_ids)) if emergency_task_id else next(iter(task_ids or change_ids))
    review_path = root / 'docs/exec-plans/reviews' / selected / 'GENERAL.json'
    if not review_path.is_file():
        raise ValueError('ci-general-review-missing:' + selected)
    review = load_artifact(review_path)
    if not isinstance(review, dict) or not isinstance(review.get('reviewed_head_sha'), str):
        raise ValueError('ci-general-review-invalid:' + selected)
    args.protected_base = base
    if emergency_task_id:
        for path in HG024_ONE_TIME_BASE_ABSENT_PATHS:
            if subprocess.run(
                    ['git', 'cat-file', '-e', base + ':' + path], cwd=root,
                    capture_output=True).returncode == 0:
                raise ValueError('ci-emergency-already-consumed:' + path)
        task_review_path = root / 'docs/exec-plans/reviews' / emergency_task_id / 'GENERAL.json'
        if not task_review_path.is_file():
            raise ValueError('ci-general-review-missing:' + emergency_task_id)
        task_review = load_artifact(task_review_path)
        if (not isinstance(task_review, dict)
                or task_review.get('reviewed_head_sha') != review['reviewed_head_sha']):
            raise ValueError('ci-emergency-reviewed-head-mismatch:' + selected)
        args.governance_change_id = selected
        args.governance_reviewed_head = review['reviewed_head_sha']
        args.emergency_task_id = emergency_task_id
    elif task_ids:
        args.task_id = selected
        args.reviewed_head = review['reviewed_head_sha']
    else:
        args.governance_change_id = selected
        args.governance_reviewed_head = review['reviewed_head_sha']


def storage_bookkeeping_only(root, parent, commit, path):
    """Conversion is implementation, even inside a bookkeeping directory."""
    cache = _evidence_verdicts.get()
    key = (('storage-bookkeeping', str(root.resolve()), parent, commit, path)
           if all(re.fullmatch(r'[0-9a-f]{40}', revision) for revision in (parent, commit))
           else None)
    if cache is not None and key is not None and key in cache:
        return True
    exists = subprocess.run(['git', 'cat-file', '-e', parent + ':' + path],
                            cwd=root, capture_output=True).returncode == 0
    if path.endswith(('.gz', '.xz')):
        if exists:
            return False
    else:
        for revision in ([parent, commit] if exists else [commit]):
            entry = revision_git_entry(root, path, revision)
            if entry is None or entry[0] not in (b'100644', b'100755') or entry[1] != b'blob':
                continue
            # This classifies immutable bookkeeping history, including plain
            # evidence merged before prospective storage budgets were adopted.
            # Budget admission remains in audit; reserved objects still enforce
            # their own envelope limit during classification.
            data = compact_evidence.blob(root, path, revision)
            if compact_evidence.reencoding_record(data) is not None:
                return False
            manifest = compact_evidence.envelope(data)
            if exists and manifest and manifest.get(compact_evidence.MARKER) in compact_evidence.CODECS:
                return False
    if cache is not None and key is not None:
        if len(cache) >= EVIDENCE_VERDICT_LIMIT:
            cache.clear()
        cache.add(key)
    return True


def suffix_errors(
        root, start, end, task_id, kind, scope_patterns=None,
        allow_unrelated_merges=False, allowed_patterns=None):
    """Require ancestry and check every bookkeeping commit, including reverted changes."""
    errors = []
    try:
        start, end = resolve(root, start), resolve(root, end)
        git(root, 'merge-base', '--is-ancestor', start, end)
        commits = git(root, 'rev-list', '--reverse', start + '..' + end).decode().splitlines()
        allowed = (allowed_patterns if allowed_patterns is not None
                   else review_patterns(task_id) if kind == 'review'
                   else result_paths(task_id) + [evidence_pattern(task_id)])
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
                elif not storage_bookkeeping_only(root, parents[0], commit, path):
                    errors.append(kind + '-representation-mutation:' + path)
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
        emergency_task_id = EMERGENCY_GOVERNANCE_TASK.get(change_id)
        allowed = (
            review_patterns(change_id) + review_patterns(emergency_task_id)
            if kind == 'review' and emergency_task_id
            else review_patterns(change_id)
            if kind == 'review'
            else governance_record_paths(change_id) + [evidence_pattern(change_id)]
            + (result_paths(emergency_task_id) + [evidence_pattern(emergency_task_id)]
               if emergency_task_id else [])
        )
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
                elif not storage_bookkeeping_only(root, parents[0], commit, path):
                    errors.append('governance-' + kind + '-representation-mutation:' + path)
                elif kind == 'tested' and matches(path, [evidence_pattern(change_id)]):
                    exists = subprocess.run(
                        ['git', 'cat-file', '-e', parents[0] + ':' + path],
                        cwd=root, capture_output=True)
                    if exists.returncode == 0:
                        errors.append('governance-tested-evidence-not-addition:' + path)
    except ValueError as ex:
        errors.append('governance-' + kind + '-revision:' + str(ex))
    return errors


_evidence_verdicts: ContextVar[set[tuple] | None] = ContextVar('evidence_verdicts', default=None)
EVIDENCE_VERDICT_LIMIT = 4096


@contextmanager
def evidence_validation_session():
    """Cache only successful immutable proof checks for one validation operation."""
    if _evidence_verdicts.get() is not None:
        yield
        return
    token = _evidence_verdicts.set(set())
    try:
        yield
    finally:
        _evidence_verdicts.reset(token)


def evidence_exists(root, ref, revision=None, tested=None, command=None, exit_code=None):
    if not relative_path(ref) or '\0' in ref:
        return False
    try:
        cache = _evidence_verdicts.get()
        # Mutable refs/working files and failed proofs are never memoized. Full
        # SHA existence/type is still proven by read before a successful insert.
        key = ((str(root.resolve()), revision, ref, tested, command, exit_code)
               if isinstance(revision, str) and re.fullmatch(r'[0-9a-f]{40}', revision)
               else None)
        if cache is not None and key is not None and key in cache:
            return True
        compact_evidence.read(root, ref, revision, tested=tested, command=command,
                              exit_code=exit_code)
        if cache is not None and key is not None:
            if len(cache) >= EVIDENCE_VERDICT_LIMIT:
                cache.clear()
            cache.add(key)
        return True
    except (ValueError, OSError, TypeError):
        return False


def revision_git_entry(root, ref, revision):
    """Read an exact normalized tree entry, independently of its object's availability."""
    if not relative_path(ref) or '\0' in ref:
        return None
    entries = git(root, 'ls-tree', '-z', revision, '--', ref).split(b'\0')
    for entry in filter(None, entries):
        metadata, name = entry.split(b'\t', 1)
        if name == ref.encode():
            return tuple(metadata.split())
    return None


def review_reference_available(root, ref, reviewed):
    """Generic availability only; selected review gates still prove exact bindings.

    Retiring a mapped current representation does not remove a review's original
    regular Git objects at its recorded SHA. Never use that historical proof to
    excuse a present invalid current artifact or an unavailable reviewed source.
    """
    if evidence_exists(root, ref):
        return True
    if not relative_path(ref) or '\0' in ref:
        return False
    target = root.resolve() / ref
    if (target.exists() or any(p.is_symlink() for p in (target, *target.parents))
            or any(p.exists() and not p.is_dir() for p in target.parents)):
        return False
    return evidence_exists(root, ref, reviewed)


def revision_regular_file(root, ref, revision):
    """Resolve an exact regular tree entry to an available content-addressed Git blob."""
    entry = revision_git_entry(root, ref, revision)
    if entry is None:
        return False
    mode, kind, oid = entry
    if kind != b'blob' or mode not in (b'100644', b'100755'):
        return False
    obj = subprocess.run(['git', 'cat-file', '-t', oid.decode()], cwd=root, capture_output=True)
    return obj.returncode == 0 and obj.stdout.strip() == b'blob'


def full_database_evidence_errors(root, reviewed, tested, ref):
    """Check local/hosted full DB evidence from regular reviewed Git blobs only."""
    try:
        if not revision_regular_file(root, ref, reviewed):
            raise ValueError('manifest-not-regular-reviewed-blob')
        manifest = json.loads(git(root, 'show', reviewed + ':' + ref))
        records = [check['stdout'] for check in manifest['checks']] + manifest['artifacts']
        spec = importlib.util.spec_from_file_location('db_ci_evidence', Path(__file__).with_name('db_ci.py'))
        if spec is None or spec.loader is None:
            raise ValueError('DB evidence validator unavailable')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='kl-db-evidence-review-') as temporary:
            destination = Path(temporary)
            (destination / 'manifest.json').write_bytes(git(root, 'show', reviewed + ':' + ref))
            for item in records:
                name = item['path']
                if Path(name).name != name or name in ('', '.', '..'):
                    raise ValueError('non-sibling-raw-path')
                raw_ref = str(Path(ref).parent / name)
                if not revision_regular_file(root, raw_ref, reviewed):
                    raise ValueError('raw-not-regular-reviewed-blob:' + raw_ref)
                (destination / name).write_bytes(git(root, 'show', reviewed + ':' + raw_ref))
            module.validate_evidence(destination, tested)
        return []
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError) as error:
        return ['full-database-evidence:' + str(error)]


def review_evidence_exists(root, ref, reviewed, review_commit, task_id, review_only_suffix):
    """Bind ordinary evidence to reviewed; review-created bookkeeping to its recorded commit."""
    if not relative_path(ref) or '\0' in ref:
        return False
    if revision_regular_file(root, ref, reviewed):
        return evidence_exists(root, ref, reviewed)
    return (review_only_suffix and matches(ref, review_patterns(task_id))
            and revision_git_entry(root, ref, reviewed) is None
            and revision_regular_file(root, ref, review_commit)
            and evidence_exists(root, ref, review_commit))


def semantic_result_errors(obj, task, root, evidence_revision=None):
    errors = []
    if task.get('status') == 'SUPERSEDED':
        errors.append('result-for-superseded-task')
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
                and not evidence_exists(root, evidence_ref, evidence_revision,
                                        obj['tested_commit'], c.get('command'),
                                        0 if c['result'] == 'PASS' else None)):
            errors.append('command-evidence:' + c['check_id'])
    for requirement in obj['requirements_covered']:
        if requirement['status'] in ('PASS', 'APPROVED_NA'):
            if not evidence_exists(root, requirement.get('evidence_ref'), evidence_revision,
                                   obj['tested_commit']):
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


@evidence_validation_session()
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
        # This stricter proof also bounds the evidence exception for delayed reviews.
        # Their existing scoped freshness rule is not a proof of an own-review-only suffix.
        review_only_suffix = not suffix_errors(
            root, reviewed, review_commit, task_id, 'review')
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
                if not review_evidence_exists(
                        root, ref, reviewed, review_commit, task_id, review_only_suffix):
                    errors.append(
                        'integration-review-evidence:' + task_id + ':' + review_type + ':' + ref)
    except ValueError as ex:
        errors.append('integration-revision:' + task_id + ':' + str(ex))
    return errors


@evidence_validation_session()
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


@evidence_validation_session()
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
        if exit_id == 'migration_dependency_graph_documented':
            expected_evidence.add(('docs/contracts/physical_schema_topology.md', evaluated))
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
        shadow = load_artifact_at_revision(
            root, 'docs/exec-plans/integrations/KL-008.json', evaluated)
        for task_id in ('KL-014', 'KL-015', 'KL-017'):
            affected = load_artifact_at_revision(
                root, f'docs/exec-plans/integrations/{task_id}.json', evaluated)
            affected_result = load_artifact_at_revision(
                root, result_paths_at_revision(root, task_id, affected['reviewed_head_sha'])[0],
                affected['reviewed_head_sha'])
            if not is_ancestor(root, shadow['merge_commit'], affected_result['tested_commit']):
                errors.append('milestone-gate-order:KL-008:' + task_id)
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


def canonical_value_sha(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def m3_closure_plan_errors(text):
    marker = '## M3 exit-evidence mapping — HG044'
    end = '<!-- HG044 plan end -->'
    if text.count(marker) != 1 or text.count(end) != 1:
        return ['m3-closure-plan']
    block = text.split(marker, 1)[1].split(end, 1)[0]
    return [] if hashlib.sha256(block.encode()).hexdigest() == '016ebe910b40724dc7cf7b00ab0bc384fa0d5ef6b8749ae6ea741c6126023878' else ['m3-closure-plan']


def m3_governance_plan_prefix_errors(root, base, reviewed):
    """Compare committed plan revisions in both ordinary and review-only PR gates."""
    before = git(root, 'show', base + ':' + PROJECT_PLAN).decode()
    after = git(root, 'show', reviewed + ':' + PROJECT_PLAN).decode()
    return ([] if after.split('## M3 exit-evidence mapping — HG044', 1)[0] == before + '\n'
            else ['governance-hg044-plan-prefix'])


def m3_closure_record_errors(root, path, revision='HEAD'):
    """An optional closure instance is itself a committed regular blob, never ambient evidence."""
    try:
        ref = str(path.relative_to(root))
        if (path.is_symlink() or not revision_regular_file(root, ref, revision)
                or git(root, 'show', revision + ':' + ref) != path.read_bytes()):
            raise ValueError('not-committed-regular-unchanged-blob')
    except (ValueError, OSError, TypeError) as ex:
        return ['milestone-m3-record-source:' + str(ex)]
    return []


def m3_load_closure_record(root, path):
    """Reject nonregular sources before parsing; parse the exact checked Git revision."""
    head = resolve(root, 'HEAD')
    errors = m3_closure_record_errors(root, path, head)
    if errors:
        return None, errors
    ref = str(path.relative_to(root))
    return load_artifact_text(git(root, 'show', head + ':' + ref).decode(), '.json'), []


def m3_evidence_bytes(root, evidence, evaluated, tested=None, command=None, exit_code=None):
    """Read only content-addressed regular Git blobs at reachable exact commits."""
    path, revision = evidence['path'], evidence['revision']
    if (not relative_path(path) or resolve(root, revision) != revision
            or not is_ancestor(root, revision, evaluated)
            or not revision_regular_file(root, path, revision)
            or blob_sha_at_revision(root, path, revision) != evidence['sha256']):
        raise ValueError('evidence-binding')
    return compact_evidence.read(root, path, revision, tested=tested, command=command,
                                 exit_code=exit_code)


def m3_pytest_count(output):
    summaries = re.findall(r'\b([1-9][0-9]*) passed\b', output)
    if (not summaries or re.search(
            r'\b[1-9][0-9]* (?:failed|skipped|errors?|deselected|xfailed|xpassed)\b',
            output, re.I)):
        raise ValueError('failed-skipped-or-empty-run')
    return int(summaries[-1])


def m3_task_check_errors(root, witness, task_id, check_id, task, record, evaluated):
    """Resolve a named check through its integration, result, contract and raw log."""
    try:
        reviewed = record['reviewed_head_sha']
        paths = result_paths_at_revision(root, task_id, reviewed)
        if len(paths) != 1:
            raise ValueError('result-representation')
        result = load_artifact_at_revision(root, paths[0], reviewed)
        commands = [c for c in result['commands_run'] if c['check_id'] == check_id]
        contracts = [c for c in task['check_contracts'] if c['check_id'] == check_id]
        if len(commands) != 1 or len(contracts) != 1:
            raise ValueError('check-representation')
        command, contract = commands[0], contracts[0]
        if (canonical_value_sha(contract) != M3_CHECK_CONTRACT_DIGESTS[task_id + ':' + check_id]
                or witness['task_identity'] != task['task_identity']
                or witness['check_id'] != check_id
                or witness['tested_commit'] != result['tested_commit']
                or witness['result'] != 'PASS' or command['result'] != 'PASS'
                or witness['command'] != contract['command']
                or command['command'] != contract['command']
                or witness['oracle_sha256'] != canonical_value_sha(contract['pass_oracle'])
                or witness['result_artifact']['path'] != paths[0]
                or witness['result_artifact']['revision'] != reviewed
                or witness['raw']['path'] != command['evidence_ref']
                or witness['raw']['revision'] != reviewed
                or not matches(witness['raw']['path'], [evidence_pattern(task_id)])):
            raise ValueError('check-oracle-binding')
        m3_evidence_bytes(root, witness['result_artifact'], evaluated)
        m3_pytest_count(m3_evidence_bytes(
            root, witness['raw'], evaluated, tested=result['tested_commit'],
            command=command['command'], exit_code=0).decode())
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as ex:
        return ['milestone-m3-task-check:' + task_id + ':' + check_id + ':' + str(ex)]
    return []


def m3_execution_evidence_errors(root, payload, revision, evaluated, records):
    """Fresh integrated executions retain all selectors, collection and JUnit cases."""
    prefix = 'milestone-m3-regression:'
    try:
        change = payload['change_id']
        tested = payload['tested_commit']
        if (not re.fullmatch(r'HG-[0-9]{3}', change)
                or resolve(root, tested) != tested or payload['status'] != 'PASS'
                or payload['commands'] != M3_REGRESSION_COMMANDS
                or governance_suffix_errors(root, tested, evaluated, change, 'tested')
                or any(not is_ancestor(root, records[n]['merge_commit'], tested)
                       for n in M3_TASK_IDS)):
            raise ValueError('stale-or-unintegrated-revision')
        runs = payload['executions']
        if (not isinstance(runs, list) or len(runs) != len(M3_REGRESSION_COMMANDS)
                or [run['command'] for run in runs] != M3_REGRESSION_COMMANDS):
            raise ValueError('command-set')
        for command, run in zip(M3_REGRESSION_COMMANDS, runs):
            if (run['tested_commit'] != tested or run['exit_code'] != 0
                    or type(run['exit_code']) is not int):
                raise ValueError('failed-or-unbound-command')
            def raw(item, expected_command=None):
                if item.get('revision', revision) != revision or not matches(
                        item['path'], [evidence_pattern(change)]):
                    raise ValueError('raw-provenance')
                return m3_evidence_bytes(root, dict(item, revision=revision), evaluated,
                                         tested=tested, command=expected_command, exit_code=0)
            output = raw(run['stdout'], command).decode()
            if command == 'uv run kl check-harness':
                if 'HARNESS_CHECK_PASS' not in output or 'HARNESS_CHECK_FAIL' in output:
                    raise ValueError('harness-oracle')
                continue
            count = m3_pytest_count(output)
            tree = ET.fromstring(raw(run['junit'], command))
            cases = list(tree.iter('testcase'))
            actual = [(case.get('classname', ''), case.get('name', '')) for case in cases]
            if (not cases or len(cases) != count or len(actual) != len(set(actual))
                    or any(list(case.iter(tag)) for case in cases
                           for tag in ('failure', 'error', 'skipped'))):
                raise ValueError('failed-skipped-duplicate-or-empty-tests')
            selectors = (['tests/unit'] if command == 'uv run kl test-unit'
                         else ['tests/harness'] if command == 'uv run kl test-harness'
                         else command.removeprefix('uv run pytest -q ').split())
            collect_command = 'uv run pytest --collect-only -q ' + ' '.join(selectors)
            collection = load_artifact_text(raw(run['collection'], collect_command).decode(), '.json')
            if (collection['command'] != collect_command
                    or collection['tested_commit'] != tested or collection['exit_code'] != 0
                    or type(collection['exit_code']) is not int):
                raise ValueError('collection-binding')
            nodeids = collection['nodeids']
            collected_output = raw(collection['stdout'], collect_command).decode()
            raw_nodes = [line for line in collected_output.splitlines()
                         if re.match(r'^tests/[^\s]+\.py::', line)]
            totals = re.findall(r'^([1-9][0-9]*) tests? collected in ', collected_output, re.M)
            raw_node_lines = set(raw_nodes)
            summary_output = '\n'.join(line for line in collected_output.splitlines()
                                       if line not in raw_node_lines)
            if (not nodeids or len(nodeids) != len(set(nodeids)) or nodeids != raw_nodes
                    or len(totals) != 1 or int(totals[0]) != len(nodeids)
                    or re.search(r'\b[1-9][0-9]* (?:deselected|errors?|skipped)\b',
                                 summary_output, re.I)):
                raise ValueError('collection-oracle')
            expected = []
            for node in nodeids:
                address, bracket, parameters = node.partition('[')
                components = address.split('::')
                if not any(node == s or node.startswith(s + '[') or node.startswith(s + '::')
                           or node.startswith(s + '/') for s in selectors):
                    raise ValueError('wrong-selector')
                expected.append(('.'.join([components[0].removesuffix('.py').replace('/', '.'),
                                           *components[1:-1]]), components[-1] + bracket + parameters))
            for selector in selectors:
                if not any(node == selector or node.startswith(selector + '[')
                           or node.startswith(selector + '::') or node.startswith(selector + '/')
                           for node in nodeids):
                    raise ValueError('missing-selector')
            if set(actual) != set(expected) or len(actual) != len(expected):
                raise ValueError('incomplete-executed-collection')
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, ET.ParseError) as ex:
        return [prefix + str(ex)]
    return []


def m3_layer_errors(root, closure, evaluated):
    """Exact 31 B and 10 I dispositions; support never promotes missing product layers."""
    try:
        packet = git(root, 'show', evaluated + ':docs/exec-plans/active/KL-028.md').decode()
        expected = packet_json_section(packet, 'Boundary layer ledger')
        requirements = load_artifact_at_revision(
            root, 'KineticLoop_Acceptance_Spec_v1.2.2.json', evaluated
        )['supplemental_boundary_requirements']
        if m3_boundary_layer_errors(expected, requirements):
            raise ValueError('boundary-authority')
        for row in expected:
            if row['disposition'] == 'KL028_PLANNED_EXECUTABLE':
                row['status'] = 'PASS'
        if closure['boundary_layers'] != expected:
            raise ValueError('boundary-dispositions')
        interleavings = [dict(requirement_id=f'I{i:02}', layer='DC', status='PASS',
                             task_identity='harness-backlog-v0.2/KL-026', check_id=f'i{i:02}_dc')
                        for i in range(1, 10)]
        interleavings.append(dict(requirement_id='I04', layer='WF', status='NOT_RUN',
                                  required_future_owner='M4 worker/fault process evidence'))
        if closure['interleaving_layers'] != interleavings:
            raise ValueError('interleaving-dispositions')
    except (ValueError, OSError, KeyError, TypeError) as ex:
        return ['milestone-m3-layers:' + str(ex)]
    return []


def m3_dependency_order_errors(root, records, tasks):
    """Check both base and tested ancestry without relabeling supporting membership."""
    errors = []
    try:
        for name, record in records.items():
            reviewed = record['reviewed_head_sha']
            paths = result_paths_at_revision(root, name, reviewed)
            if len(paths) != 1 or not revision_regular_file(root, paths[0], reviewed):
                raise ValueError('result-representation:' + name)
            result = load_artifact_at_revision(root, paths[0], reviewed)
            for dep in tasks[name]['depends_on']:
                for key in ('base_commit', 'tested_commit'):
                    if not is_ancestor(root, records[dep]['merge_commit'], result[key]):
                        errors.append('milestone-m3-dependency-order:' + dep + ':' + name + ':' + key)
    except (ValueError, OSError, KeyError, TypeError) as ex:
        errors.append('milestone-m3-dependency-order:invalid:' + str(ex))
    return errors


def m3_frozen_authority_errors(root, evaluated):
    try:
        frozen = load_artifact_at_revision(root, 'FROZEN_BASELINE.json', evaluated)
        if frozen != load_artifact(root / 'FROZEN_BASELINE.json'):
            raise ValueError('baseline-drift')
        for entry in frozen['files']:
            if (not revision_regular_file(root, entry['path'], evaluated)
                    or blob_sha_at_revision(root, entry['path'], evaluated) != entry['sha256']):
                raise ValueError('file-drift:' + entry['path'])
    except (ValueError, OSError, KeyError, TypeError) as ex:
        return ['milestone-m3-frozen-authority:' + str(ex)]
    return []


@evidence_validation_session()
def m3_milestone_closure_errors(
        root, closure, schema, integration_schema, result_schema, review_schema, backlog, tasks):
    """Mechanical minimal TEST demonstration closure, independent of release/product PASS."""
    errors = ['milestone-schema:M3.json:' + issue.message for issue in schema.iter_errors(closure)]
    if errors:
        return errors
    try:
        evaluated = closure['evaluated_commit']
        if resolve(root, evaluated) != evaluated or not is_ancestor(root, evaluated, 'HEAD'):
            raise ValueError('evaluated-unreachable')
        evaluated_backlog = load_artifact_at_revision(root, BACKLOG, evaluated)
        definition_errors, evaluated_tasks = task_definition_errors(root, evaluated_backlog, evaluated)
        errors.extend('milestone-m3-task-contract:' + e for e in definition_errors)
        active = {t['id'] for t in evaluated_tasks.values()
                  if t['milestone'] == 'M3' and t['status'] != 'SUPERSEDED'}
        ids = [i['display_task_id'] for i in closure['integrations']]
        if active != M3_TASK_IDS or set(ids) != active or len(ids) != len(set(ids)):
            return errors + ['milestone-active-task-set:M3']
        supporting = closure['supporting_prerequisites']
        if [i['display_task_id'] for i in supporting] != ['KL-074'] or evaluated_tasks['KL-074']['milestone'] != 'M1':
            return errors + ['milestone-m3-supporting-prerequisites']
        m2_ref = closure['m2_prerequisite']
        if m2_ref['path'] != 'docs/exec-plans/milestones/M2.json' or m2_ref['revision'] != evaluated:
            raise ValueError('m2-prerequisite-binding')
        m2 = load_artifact_text(m3_evidence_bytes(root, m2_ref, evaluated).decode(), '.json')
        errors.extend('milestone-m3-prerequisite:' + e for e in m2_milestone_closure_errors(
            root, m2, schema, integration_schema, result_schema, review_schema,
            evaluated_backlog, evaluated_tasks))
        if not is_ancestor(root, m2['evaluated_commit'], evaluated):
            raise ValueError('m2-prerequisite-unreachable')
        records = {}
        pending = list(M3_TASK_IDS | {'KL-074'})
        declared = {i['display_task_id']: i for i in closure['integrations'] + supporting}
        while pending:
            name = pending.pop()
            if name in records:
                continue
            path = f'docs/exec-plans/integrations/{name}.json'
            if not revision_regular_file(root, path, evaluated):
                raise ValueError('missing-or-nonregular-integration:' + name)
            record = load_artifact_at_revision(root, path, evaluated)
            records[name] = record
            for source in result_paths_at_revision(root, name, record['result_commit']):
                if not revision_regular_file(root, source, record['result_commit']):
                    raise ValueError('nonregular-result:' + name)
            for kind in evaluated_tasks[name]['review_requirements']:
                if not revision_regular_file(root, f'docs/exec-plans/reviews/{name}/{kind}.json',
                                             record['review_record_commit']):
                    raise ValueError('nonregular-review:' + name + ':' + kind)
            if name in declared:
                item = declared[name]
                if (item['task_identity'] != 'harness-backlog-v0.2/' + name
                        or item['integration_record'] != path
                        or item['sha256'] != blob_sha_at_revision(root, path, evaluated)):
                    errors.append('milestone-m3-integration-binding:' + name)
            errors.extend('milestone-m3-integration:' + name + ':' + e
                          for e in integration_record_errors(
                              root, Path(path), record, integration_schema, result_schema,
                              review_schema, evaluated_tasks))
            for key in ('result_commit', 'reviewed_head_sha', 'review_record_commit', 'merge_commit'):
                if not is_ancestor(root, record[key], evaluated):
                    errors.append('milestone-m3-integration-unreachable:' + name + ':' + key)
            pending.extend(evaluated_tasks[name]['depends_on'])
        errors.extend(m3_dependency_order_errors(root, records, evaluated_tasks))
        exits = closure['exit_checks']
        exit_ids = [e['check_id'] for e in exits]
        if set(exit_ids) != set(M3_EXIT_TASK_CHECKS) or len(exit_ids) != len(set(exit_ids)):
            errors.append('milestone-exit-check-set:M3')
        for exit_check in exits:
            exit_id = exit_check['check_id']
            required = {(n,c) for n,ids in M3_EXIT_TASK_CHECKS[exit_id].items() for c in ids}
            witnesses = exit_check['task_checks']
            pairs = [(w['task_identity'].split('/')[-1], w['check_id']) for w in witnesses]
            if set(pairs) != required or len(pairs) != len(set(pairs)):
                errors.append('milestone-m3-exit-task-set:' + exit_id)
            for pair, witness in zip(pairs, witnesses):
                if pair not in required:
                    continue
                name, check = pair
                errors.extend(m3_task_check_errors(
                    root, witness, name, check, evaluated_tasks[name], records[name], evaluated))
        errors.extend(m3_layer_errors(root, closure, evaluated))
        errors.extend(m3_frozen_authority_errors(root, evaluated))
        ref = closure['integrated_regression']
        if (ref['revision'] != evaluated or not re.fullmatch(
                r'docs/exec-plans/evidence/HG-[0-9]{3}/m3-regression-[0-9a-f]{7,40}\.json', ref['path'])):
            raise ValueError('regression-source')
        payload = load_artifact_text(m3_evidence_bytes(root, ref, evaluated).decode(), '.json')
        if not matches(ref['path'], [evidence_pattern(payload['change_id'])]):
            raise ValueError('regression-provenance')
        errors.extend(m3_execution_evidence_errors(root, payload, evaluated, evaluated, records))
    except (ValueError, OSError, KeyError, TypeError, IndexError, UnicodeError) as ex:
        errors.append('milestone-m3-invalid:' + str(ex))
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
            output = compact_evidence.read(root, log['path'], revision,
                                           tested=payload['tested_commit'], command=command, exit_code=0).decode()
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
            tree = ET.fromstring(compact_evidence.read(
                root, report['path'], revision, tested=payload['tested_commit']))
            cases = list(tree.iter('testcase'))
            if not cases or any(
                    list(case.iter(tag)) for case in cases
                    for tag in ('failure', 'error', 'skipped')):
                raise ValueError('failed-skipped-or-empty-tests')
            names = {(case.get('classname', ''), case.get('name', '').split('[')[0])
                     for case in cases}
            collection = run['collection']
            if (not relative_path(collection['path'])
                    or not matches(collection['path'], [evidence_pattern('HG-023')])
                    or blob_sha_at_revision(root, collection['path'], revision)
                    != collection['sha256']):
                raise ValueError('collection-binding')
            collected = load_artifact_text(compact_evidence.read(
                root, collection['path'], revision, tested=payload['tested_commit']).decode(), '.json')
            nodeids = collected['nodeids']
            if (collected.get('command') != 'uv run pytest --collect-only -q'
                    or collected.get('exit_code') != 0
                    or collected.get('tested_commit') != payload['tested_commit']
                    or not isinstance(nodeids, list) or not nodeids
                    or len(nodeids) != len(set(nodeids))):
                raise ValueError('invalid-collection')
            collection_log = collected['stdout']
            if (not relative_path(collection_log['path'])
                    or not matches(collection_log['path'], [evidence_pattern('HG-023')])
                    or blob_sha_at_revision(root, collection_log['path'], revision)
                    != collection_log['sha256']):
                raise ValueError('collection-stdout-binding')
            collection_output = compact_evidence.read(
                root, collection_log['path'], revision, tested=payload['tested_commit']).decode()
            raw_nodeids = [line for line in collection_output.splitlines()
                          if re.match(r'^tests/[^\s]+\.py::', line)]
            collected_counts = re.findall(
                r'^([1-9][0-9]*) tests? collected in ', collection_output, re.M)
            if (raw_nodeids != nodeids or len(collected_counts) != 1
                    or int(collected_counts[0]) != len(nodeids)
                    or re.search(r'\b[1-9][0-9]* (?:deselected|errors?|skipped)\b',
                                 collection_output, re.I)):
                raise ValueError('collection-stdout-oracle')
            expected_cases = set()
            for nodeid in nodeids:
                components = nodeid.split('::')
                expected_cases.add((
                    '.'.join([components[0].removesuffix('.py').replace('/', '.'),
                              *components[1:-1]]), components[-1]))
            actual_cases = [(case.get('classname', ''), case.get('name', '')) for case in cases]
            if set(actual_cases) != expected_cases or len(actual_cases) != len(expected_cases):
                raise ValueError('incomplete-or-duplicate-collection')
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
            summaries = re.findall(r'\b([1-9][0-9]*) passed\b', output)
            if (not summaries or int(summaries[-1]) != len(cases)
                    or re.search(r'\b[1-9][0-9]* (?:failed|skipped|errors?|deselected|xfailed|xpassed)\b',
                                 output, re.I)):
                raise ValueError('pytest-oracle')
        except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as ex:
            errors.append(prefix + str(ex))
    return errors


# HG036 binds only the unstarted KL047 offline infrastructure definition.
# Future scope/semantic changes require separate governance; historical unrefined
# protected bases retain their original packet and are never relabelled.
FITNESS_EVAL_DEFINITION_DIGESTS = {'milestone': '956e5e3d52c685ebc9a545a52bd240ce4d7e92668ff76877175183aa9889a2b3',
 'title': '69e481dc5f1f6dfe073d5af9c36848d0c93057f4b73fae510f2d747538660cc6',
 'owner_role': 'ff610fb106a3a1c1cedcc6589f563a9a1da99b391e061593d0965d58ddaddceb',
 'depends_on': '3107e2f79968e3c2d35593c65c714af842d89b0097e827afa9045ae54f7336d0',
 'commands': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'transaction_boundaries': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'invariant_ids': '283710e28c0d02b671756b1c42e250fad3f32deb19679291eb7be50a1497a92c',
 'table_ids': '9a332a5ddd9c278ae54601ec2de7b3a56a656fd493698a6c6f8d5f0a37d2a65f',
 'required_test_layers': '4b42aa23b42b3ca743449b544cc16ccb8e8ec8cfd2ddcf2f62a9fac0c5760f71',
 'deliverables': '571c2148a82fcaa4fff8e80ec8a6a522f69466cb2dfa587876e467e18266308d',
 'definition_of_done': '8235f87e93611a7323d079198263d3c00797af5073c5ecfe2baee50082ab42b6',
 'entry_conditions': 'cdb8e9e5f374da25bbf860253cfe03aebb468d1bfa3c5814ab3a7de0f62e5d11',
 'thread_mode': 'e08931b96108d4d7b09720df6852f99d68e4b39207dca0c1cbab878221a358d4',
 'context_files': '32248e7aa59b56fc871aaf7f9db803fa7752ba0bfe609d644405a073a54bf4c0',
 'max_context_policy': '146220a2aa769d8163fb894618fe689e8aa94a7a4240418735beeb016306660c',
 'merge_unit': '48f009959aa958b4b832ed0ce7af1e468160c0fae875bb5592b63882743e92d6',
 'handoff_artifact': '1a5914ada8e642eebf033f0ca1addfd6274734a39c370097848884866f60b77a',
 'shared_hotspot': 'fcbcf165908dd18a9e49f7ff27810176db8e9f63b4352213741664245224f8aa',
 'parallel_write_policy': '18673037cf4a790bffe39b043258e1c9ad8de9c40878e9739555fa5551a6e773',
 'task_identity': '3418099843e2fcd2528596625e8908d22a49baddebbcb18db366756f23d6e13b',
 'requirements_covered': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'checks_required_for_this_task': '18ebe2f6b730574e34bbd90f1166ecc1e1ec212ebb9cf14db0c9a5fa58ad6160',
 'resource_keys': 'd4105520a414172165c6490416c291fd56c26aea511c2126daec93529eef2f33',
 'write_paths': 'f9fe4dabe8eb6718cceb0df885c48dacd15a0c89d77b3c19842834bba570d3df',
 'review_requirements': '0469d2acfb8a5ec7a8beb4e1a047624a8371744c73f975a708080a1c32135964',
 'conditional_depends_on': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'environment_requirements': '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
 'packet_refinement': 'bf90cfa6d2424aaea97cbc7342a33d90a3022ac6e104ade780cabd2d598818ad',
 'required_test_layers_semantics': 'a9a68d6f7dd868aa585d451f7591de3871f0b1608c2bdc84292071f167412d9f',
 'write_paths_status': 'bf90cfa6d2424aaea97cbc7342a33d90a3022ac6e104ade780cabd2d598818ad',
 'evidence_paths': '14bf48e02766e462a7140a262deed5c8895d4384867407c7b56a881c051c6dae',
 'check_contracts': 'ec38581c9638e7010124552a48c23d8af95c385223dac1eaf96d01b46036bc02'}
FITNESS_EVAL_PACKET_SHA256 = '70a1376139605a31f1ad030c13dbc12776b92e6872de0c30f5d6ed3b24fe3aed'


def fitness_evaluation_definition_errors(task):
    """Keep source-derived offline scoring separate from quality/release claims."""
    if task.get('id') != 'KL-047':
        return []
    errors = []
    for field, expected in FITNESS_EVAL_DEFINITION_DIGESTS.items():
        actual = hashlib.sha256(json.dumps(
            task.get(field), ensure_ascii=False, sort_keys=True,
            separators=(',', ':'),
        ).encode()).hexdigest()
        if actual != expected:
            errors.append('fitness-eval-definition:KL-047:' + field)
    return errors


def fitness_evaluation_packet_errors(task, text):
    if (task.get('id') != 'KL-047'
            or task.get('packet_refinement') != 'ENFORCEABLE'):
        return []
    digest = hashlib.sha256(text.encode()).hexdigest()
    return ([] if digest == FITNESS_EVAL_PACKET_SHA256
            else ['fitness-eval-packet:KL-047'])


def task_definition_errors(
        root, backlog, revision=None, *, historical_m1_closure=False):
    """Validate one revision's complete backlog, packet, resource and DAG state."""
    errors = []
    tasks = {task['id']: task for task in backlog['tasks']}
    if not revision and 'KL-080' not in tasks:
        errors.append('source-decision-task-missing:KL-080')
    identities = [task['task_identity'] for task in backlog['tasks']]
    if len(tasks) != len(backlog['tasks']) or len(identities) != len(set(identities)):
        errors.append('task-identity-duplicate')
    if backlog.get('task_count') != len(backlog['tasks']):
        errors.append('backlog-task-count')
    active_task_count = sum(
        task.get('status') != 'SUPERSEDED' for task in backlog['tasks'])
    if backlog.get('active_task_count') != active_task_count:
        errors.append('backlog-active-task-count')
    resource_path = 'docs/harness/RESOURCE_LOCKS.md'
    resource_text = (git(root, 'show', revision + ':' + resource_path).decode()
                     if revision else (root / resource_path).read_text())
    known_resources = set(re.findall(r'^- `([^`]+)`$', resource_text, re.M))
    if all(tasks.get(name, {}).get('packet_refinement') == 'ENFORCEABLE'
           for name in M3_BOUNDARY_SHADOW_IDS):
        plan_text = (git(root, 'show', revision + ':' + PROJECT_PLAN).decode()
                     if revision else (root / PROJECT_PLAN).read_text())
        errors.extend(m3_boundary_shadow_plan_errors(plan_text))
    for task in backlog['tasks']:
        name = task['id']
        if (name == 'KL-047' and (not revision
                or task.get('packet_refinement') == 'ENFORCEABLE')):
            errors.extend(fitness_evaluation_definition_errors(task))
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
        if name == 'KL-028' and task.get('packet_refinement') == 'ENFORCEABLE':
            try:
                packet_text = (git(root, 'show', revision + ':' + packet_path).decode()
                               if revision else (root / packet_path).read_text())
                authority_path = 'KineticLoop_Acceptance_Spec_v1.2.2.json'
                authority = (json.loads(git(root, 'show', revision + ':' + authority_path))
                             if revision else json.loads((root / authority_path).read_text()))
                errors.extend(m3_boundary_layer_errors(
                    packet_json_section(packet_text, 'Boundary layer ledger'),
                    authority['supplemental_boundary_requirements']))
            except (ValueError, OSError, KeyError, TypeError):
                errors.append('m3-boundary-layer-authority-read')
        if not revision or task.get('packet_refinement') == 'ENFORCEABLE':
            errors.extend(wave_definition_errors(task))
        if not revision or task.get('packet_refinement') == 'ENFORCEABLE':
            errors.extend(ledger_definition_errors(task))
        if not revision or task.get('packet_refinement') == 'ENFORCEABLE':
            errors.extend(execution_definition_errors(task))
        if not revision or task.get('packet_refinement') == 'ENFORCEABLE':
            errors.extend(m3_boundary_shadow_definition_errors(task))
        errors.extend(source_decision_definition_errors(task))
        errors.extend(m3_next_wave_definition_errors(task))
        errors.extend(readiness_definition_errors(task))
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
    refined = [tasks[name] for name in sorted(M2_REFINED_TASK_IDS | WAVE_REFINED_TASK_IDS | {'KL-047', 'KL-074', 'KL-026', 'KL-027', 'KL-075', 'KL-076', 'KL-077', 'KL-078', 'KL-079', 'KL-080'})
               if name in tasks and (name in M2_REFINED_TASK_IDS
                                     or tasks[name].get('packet_refinement') == 'ENFORCEABLE')]
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


def historical_schema_authority_errors(root: Path) -> list[str]:
    # The candidate index may describe its own bytes; it cannot authorize a
    # different inventory than the independently reviewed installed decoder.
    try:
        candidate = compact_evidence.blob(
            root, compact_evidence.MAPPING_SCHEMA, None, compact_evidence.PLAIN_LIMIT)
    except (ValueError, OSError) as ex:
        return ['historical-schema-authority:' + str(ex)]
    if candidate != compact_evidence.HISTORICAL_SCHEMA_BYTES:
        return ['historical-schema-authority:mismatch']
    return []


@evidence_validation_session()
def validate(root, args):
    from jsonschema import Draft202012Validator

    errors = historical_schema_authority_errors(root)
    if errors:
        return errors
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
    errors.extend(m3_closure_plan_errors((root / PROJECT_PLAN).read_text()))
    errors.extend(source_decision_plan_errors((root / PROJECT_PLAN).read_text()))

    schemas = {}
    known_requirements = requirement_ids(root)
    schema_files = {
        'RESULT': 'THREAD_RESULT.schema.json',
        'REVIEW': 'THREAD_REVIEW.schema.json',
        'GOVERNANCE': GOVERNANCE_SCHEMA,
        'INTEGRATION': INTEGRATION_SCHEMA,
        'MILESTONE': MILESTONE_CLOSURE_SCHEMA,
        'HISTORICAL_EVIDENCE_MAPPING': compact_evidence.MAPPING_SCHEMA,
    }
    for kind, schema_name in schema_files.items():
        schema = load_artifact(root / schema_name)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as ex:
            raise ValueError('invalid-schema:' + kind + ':' + str(ex)) from ex
        schemas[kind] = Draft202012Validator(schema)
    milestone_dir = root / 'docs/exec-plans/milestones'
    milestone_records: dict[str, list[tuple[Path, Any]]] = {'M1': [], 'M2': [], 'M3': []}
    if milestone_dir.exists():
        for path in sorted(milestone_dir.glob('*.json')):
            if path.stem == 'M3':
                record, source_errors = m3_load_closure_record(root, path)
                errors.extend(source_errors)
                if source_errors:
                    continue
            else:
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
    if len(milestone_records['M3']) > 1:
        errors.append('milestone-closure-count:M3:' + str(len(milestone_records['M3'])))
    elif milestone_records['M3']:
        closure_path, closure = milestone_records['M3'][0]
        if closure_path.name != 'M3.json':
            errors.append('milestone-closure-path:M3:' + closure_path.name)
        errors.extend(m3_closure_record_errors(root, closure_path))
        errors.extend(m3_milestone_closure_errors(
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
                if not review_reference_available(root, ref, obj['reviewed_head_sha']):
                    errors.append('governance-review-evidence:' + ref)
            governance_reviews.append((path, obj))
            continue
        task = tasks.get(path.parent.name)
        if not task or task['task_identity'] != obj['task_identity'] or path.stem != obj['review_type']:
            errors.append('review-identity-or-path:' + str(path.relative_to(root)))
            continue
        for ref in obj.get('evidence_refs', []):
            if not review_reference_available(root, ref, obj['reviewed_head_sha']):
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
        selected_owner = args.task_id or getattr(args, 'governance_change_id', None)
        if selected_owner:
            budget = compact_evidence.audit(root, base_sha, head, selected_owner)
            errors.extend('evidence-budget:' + issue for issue in budget['errors'])
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
            errors.extend(task_fixture_scope_errors(
                root, base_sha, head, args.task_id, changed))
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
                if (change_id == 'HG-024'
                        and any(matches(path, HG024_EMERGENCY_SCOPE_PATTERNS)
                                for path in governance_changed)
                        and getattr(args, 'emergency_task_id', None) != 'KL-073'):
                    errors.append('governance-emergency-pair-required:HG-024:KL-073')
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
                if change_id == 'HG-045':
                    errors.extend(source_governance_plan_prefix_errors(
                        root, governance_base, reviewed))
                if change_id == 'HG-044':
                    errors.extend(m3_governance_plan_prefix_errors(
                        root, governance_base, reviewed))
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
                    if EMERGENCY_GOVERNANCE_TASK.get(change_id) != task_id:
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
                recovery_redirects = set()
                if change_id == 'HG-057':
                    recovery_errors = clean_recovery_projection_errors(old_tasks, replay_tasks)
                    errors.extend(recovery_errors)
                    if not recovery_errors:
                        recovery_redirects = HG057_REDIRECT_IDS
                    packet_path = 'docs/exec-plans/active/HG-058.md'
                    if (blob_sha_at_revision(root, packet_path, governance_target)
                            if governance_target else sha(root / packet_path)) != HG058_PACKET_SHA256:
                        errors.append('clean-recovery-classifier-packet')
                    check_ids = [check['check_id'] for check in record['checks_run']]
                    if (set(check_ids) != HG057_REQUIRED_CHECKS
                            or len(check_ids) != len(HG057_REQUIRED_CHECKS)):
                        errors.append('clean-recovery-required-checks')
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
                        emergency_task = EMERGENCY_GOVERNANCE_TASK.get(change_id) == task_id
                        if (not emergency_task and any(
                                matches(path, task_artifact_patterns)
                                for path in governance_changed)):
                            errors.append('governance-new-task-artifact:' + task_id)
                        if task.get('packet_refinement') == 'ENFORCEABLE':
                            observed.add(task_id)
                    else:
                        if result_paths_at_revision(root, task_id, governance_base):
                            errors.append('governance-refine-completed-task:' + task_id)
                        retired = (
                            old_task.get('status') == 'NOT_STARTED'
                            and task.get('status') == 'SUPERSEDED'
                        )
                        if old_task.get('status') == 'SUPERSEDED':
                            observed.add(task_id)
                            if task.get('status') != 'SUPERSEDED':
                                errors.append(
                                    'governance-reactivate-superseded-task:' + task_id)
                            else:
                                errors.append(
                                    'governance-modify-superseded-task:' + task_id)
                        if retired:
                            observed.add(task_id)
                            retirement_fields = {
                                'status', 'title', 'depends_on', 'deliverables',
                                'definition_of_done', 'superseded_by',
                                'disposition_reason',
                            }
                            changed_fields = {
                                field for field in set(old_task) | set(task)
                                if old_task.get(field) != task.get(field)
                            }
                            if not changed_fields <= retirement_fields:
                                errors.append(
                                    'governance-retirement-definition-scope:' + task_id)
                            replacements = task.get('superseded_by')
                            reason = task.get('disposition_reason')
                            if (not isinstance(replacements, list)
                                    or not replacements
                                    or replacements != task.get('depends_on')
                                    or set(replacements) == set(old_task.get('depends_on', []))
                                    or len(replacements) != len(set(replacements))):
                                errors.append(
                                    'governance-retirement-replacement:' + task_id)
                            if not isinstance(reason, str) or not reason.strip():
                                errors.append(
                                    'governance-retirement-reason:' + task_id)
                        elif ((old_task.get('packet_refinement') == 'MUST_REFINE_BEFORE_READY'
                             and task.get('packet_refinement') != 'MUST_REFINE_BEFORE_READY')
                                or (old_task != task and
                                    task.get('packet_refinement') == 'ENFORCEABLE')):
                            observed.add(task_id)
                    if task_id in recovery_redirects:
                        observed.add(task_id)
                    if (task_id not in recovery_redirects
                            and task.get('status') != 'SUPERSEDED' and (
                            task.get('write_paths_status') != 'ENFORCEABLE' or
                            not task.get('write_paths') or
                            any('TO_BE_REFINED' in path for path in task.get('write_paths', [])))):
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
                if (not evidence_exists(root, ref, reviewed, obj['tested_commit'])
                        or git(root, 'show', resolve(root, reviewed) + ':' + ref)
                        != (root / ref).read_bytes()):
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
            review_suffix = not suffix_errors(root, args.reviewed_head, 'HEAD', args.task_id, 'review')
            for review in relevant:
                if resolve(root, review['reviewed_head_sha']) != resolve(root, args.reviewed_head):
                    continue
                for ref in review.get('evidence_refs', []):
                    if not review_evidence_exists(
                            root, ref, args.reviewed_head, 'HEAD', args.task_id, review_suffix):
                        errors.append('review-evidence-revision:' + args.task_id + ':' + ref)
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
                    if not matches(ref, [evidence_pattern(change_id)]):
                        errors.append('governance-command-evidence-scope:' + ref)
                    if (not evidence_exists(root, ref, reviewed, record['tested_commit'], check['command'], 0)
                            or git(root, 'show', reviewed + ':' + ref) != (root / ref).read_bytes()):
                        errors.append('governance-evidence-not-bound:' + ref)
                    if check['check_id'] == 'full_database_regression':
                        errors.extend(full_database_evidence_errors(
                            root, reviewed, record['tested_commit'], ref))
            except ValueError as ex:
                errors.append('governance-review-revision:' + str(ex))
            required = {'GENERAL'}
            if change_id in ('HG-051', 'HG-054', 'HG-057'):
                required.update({'PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'})
            if change_id in ('HG-050', 'HG-058'):
                required.add('SECURITY_DATA_BOUNDARY')
            old_tasks = getattr(args, 'governance_base_tasks', {})
            reviewed_tasks = getattr(args, 'governance_reviewed_tasks', tasks)
            if change_id == 'HG-047':
                required.update({'PROTOCOL', 'SECURITY_DATA_BOUNDARY'})
            if change_id == 'HG-044':
                required.update({'PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'})
            if change_id == 'HG-046':
                required.update({'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'})
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
            review_suffix = not governance_suffix_errors(root, reviewed, 'HEAD', change_id, 'review')
            for _, review in governance_reviews:
                if (review['task_identity'] != 'harness-governance-v0.1/' + change_id
                        or resolve(root, review['reviewed_head_sha']) != reviewed):
                    continue
                for ref in review.get('evidence_refs', []):
                    if not review_evidence_exists(root, ref, reviewed, 'HEAD', change_id, review_suffix):
                        errors.append('governance-review-evidence-revision:' + change_id + ':' + ref)
        emergency_task_id = getattr(args, 'emergency_task_id', None)
        if emergency_task_id:
            task = tasks.get(emergency_task_id)
            result = results.get(emergency_task_id)
            if not task or not result:
                errors.append('emergency-task-result-missing:' + emergency_task_id)
            else:
                result_path, result_obj = result
                try:
                    if git(
                            root, 'show', reviewed + ':'
                            + str(result_path.relative_to(root))) != result_path.read_bytes():
                        errors.append('emergency-task-result-not-bound:' + emergency_task_id)
                    if result_obj['task_status'] != 'PASS':
                        errors.append('emergency-task-result-not-pass:' + emergency_task_id)
                    tested = resolve(root, result_obj['tested_commit'])
                    git(root, 'merge-base', '--is-ancestor', tested, reviewed)
                    emergency_suffix = (
                        result_paths(emergency_task_id)
                        + [evidence_pattern(emergency_task_id)]
                        + governance_record_paths(change_id)
                        + [evidence_pattern(change_id)]
                    )
                    errors.extend(suffix_errors(
                        root, tested, reviewed, emergency_task_id, 'tested',
                        allowed_patterns=emergency_suffix))
                    for command in result_obj['commands_run']:
                        ref = command.get('evidence_ref')
                        if (ref and git(root, 'show', reviewed + ':' + ref)
                                != (root / ref).read_bytes()):
                            errors.append('emergency-task-evidence-not-bound:' + ref)
                except ValueError as ex:
                    errors.append('emergency-task-revision:' + str(ex))
                task_reviews = [
                    review for _, review, review_task in reviews
                    if review_task['id'] == emergency_task_id
                    and review['status'] == 'PASS'
                    and resolve(root, review['reviewed_head_sha']) == reviewed
                ]
                review_types = {review['review_type'] for review in task_reviews}
                if not set(task['review_requirements']) <= review_types:
                    errors.append('emergency-task-reviews-not-pass:' + emergency_task_id)
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




# Generated HG037 guard proposal; append only after HG036 merge.
READINESS_TASK_DEFINITION = {'id': 'KL-074',
 'milestone': 'M1',
 'title': 'PostgreSQL final-server startup readiness repair',
 'owner_role': 'platform',
 'depends_on': ['KL-002', 'KL-013', 'KL-023'],
 'commands': [],
 'transaction_boundaries': [],
 'invariant_ids': [],
 'table_ids': [],
 'required_test_layers': ['UNIT', 'DC'],
 'deliverables': ['explicit bounded container loopback TCP lifecycle readiness',
                  'aligned Compose and post-reset readiness probes',
                  'deterministic init-stop-final positive and negative regression tests',
                  'isolated migrated coldstart provenance and cleanup evidence',
                  'additive exact-head hosted workflow and durable raw artifact evidence'],
 'definition_of_done': 'Only startup readiness changes: temporary socket-only initialization '
                       'cannot authorize reset SQL; bounded explicit container TCP readiness gates '
                       'reset, Compose and post-reset probes align, SQL failures propagate without '
                       'replay, and deterministic regressions plus three isolated migrated cold '
                       'starts prove actual image ordering, ownership and cleanup. Full repository '
                       'and normal hosted CI/gates pass without product, migration, authentication '
                       'or frozen semantic changes. The additive exact-head hosted entrypoint '
                       'executes both exact commands, preserves raw failure/success artifacts and '
                       'provenance, and leaves all existing CI/gates unchanged.',
 'entry_conditions': ['merged KL-002 result and integration: '
                      'docs/exec-plans/completed/KL-002_RESULT.yaml and '
                      'docs/exec-plans/integrations/KL-002.json',
                      'merged KL-013 baseline and KL-023 current migrated prerequisite: '
                      'docs/exec-plans/completed/KL-013_RESULT.yaml and '
                      'docs/exec-plans/completed/KL-023_RESULT.yaml',
                      'exclusive postgres_lifecycle resource and exact write paths available; no '
                      'overlap with active KL019 transaction resources',
                      'dedicated hosted VM for full legacy DB suites; unique task-owned isolated '
                      'coldstart namespaces',
                      'same-repository codex/kl074- PR branch for the additive exact-head hosted '
                      'workflow; no arbitrary inputs or shared/remote Docker'],
 'status': 'NOT_STARTED',
 'evidence_refs': [],
 'thread_id': 'THREAD-KL-074',
 'thread_mode': 'INDEPENDENT_WORKTREE',
 'context_files': ['docs/exec-plans/completed/KL-002_RESULT.yaml',
                   'docs/exec-plans/integrations/KL-002.json',
                   'docs/exec-plans/completed/KL-013_RESULT.yaml',
                   'docs/exec-plans/completed/KL-023_RESULT.yaml',
                   'src/kineticloop/db/lifecycle.py',
                   'compose.yaml',
                   'tests/db/test_lifecycle.py',
                   'tests/db/test_migrations.py',
                   'docs/exec-plans/evidence/HG-037/READINESS_EVIDENCE.md',
                   'tools/harness/validate_harness.py',
                   '.github/workflows/ci.yml',
                   '.github/workflows/db.yml',
                   'docs/exec-plans/evidence/HG-037/HOSTED_EXECUTION_PREFLIGHT.md',
                   'docs/exec-plans/evidence/HG-037/kl074-readiness.workflow.proposal.yml'],
 'max_context_policy': 'READ_TASK_PACKET_FIRST_THEN_REFERENCES_ON_DEMAND',
 'merge_unit': 'ONE_PR',
 'handoff_artifact': 'docs/exec-plans/completed/KL-074_RESULT.yaml',
 'shared_hotspot': True,
 'parallel_write_policy': 'SERIALIZE_WITH_OTHER_HOTSPOT_TASKS',
 'task_identity': 'harness-backlog-v0.2/KL-074',
 'requirements_covered': [],
 'checks_required_for_this_task': ['temporary_socket_ready_not_final_ready',
                                   'permanent_tcp_unready_bounded',
                                   'delayed_final_ready_exact_reset',
                                   'sql_failure_no_replay',
                                   'compose_and_lifecycle_tcp_alignment',
                                   'isolated_migrated_coldstart',
                                   'lifecycle_regressions',
                                   'full_repository_regressions',
                                   'quality_and_harness',
                                   'hosted_entrypoint_and_evidence'],
 'resource_keys': ['postgres_lifecycle'],
 'write_paths': ['src/kineticloop/db/lifecycle.py',
                 'compose.yaml',
                 'tests/db/test_lifecycle.py',
                 'tests/db/test_startup_readiness.py',
                 'tools/db/verify_startup_readiness.py',
                 '.github/workflows/kl074-readiness.yml'],
 'review_requirements': ['GENERAL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'],
 'conditional_depends_on': [],
 'environment_requirements': ['ISOLATED_POSTGRESQL_NAMESPACE',
                              'TASK_OWNED_COMPOSE_NAMESPACE',
                              'DEDICATED_HOSTED_VM_FOR_LEGACY_DB_SUITES'],
 'packet_refinement': 'ENFORCEABLE',
 'required_test_layers_semantics': 'COVERAGE_HINT_ONLY_USE_checks_required_for_this_task_FOR_TASK_PASS',
 'check_contracts': [{'check_id': 'temporary_socket_ready_not_final_ready',
                      'command': 'uv run pytest -q tests/db/test_lifecycle.py -k temporary_socket',
                      'pass_oracle': 'A deterministic runner/clock reproduces the old socket-ready '
                                     'init-stop race against protected-base lifecycle code. '
                                     'Against repaired code, temporary initialization accepts '
                                     'socket pg_isready but rejects explicit 127.0.0.1:5432 TCP; '
                                     'zero psql/SQL occurs until final TCP readiness. Same '
                                     'scenario fails old code and passes repaired code; no sleeps '
                                     'or nondeterministic scheduler assumptions establish this '
                                     'oracle.'},
                     {'check_id': 'permanent_tcp_unready_bounded',
                      'command': 'uv run pytest -q tests/db/test_lifecycle.py -k permanent_tcp',
                      'pass_oracle': 'Socket remains ready while TCP never becomes ready. '
                                     'Monotonic deadline terminates within the requested bound '
                                     '(including bounded per-command probe duration) with '
                                     'DatabaseLifecycleError and zero destructive SQL. Normal '
                                     'missing-Docker/startup failures remain actionable; no '
                                     'unbounded subprocess or polling wait.'},
                     {'check_id': 'delayed_final_ready_exact_reset',
                      'command': 'uv run pytest -q tests/db/test_lifecycle.py -k delayed_final',
                      'pass_oracle': 'Multiple TCP failures followed by final TCP success permit '
                                     'exactly one DROP and one CREATE for the task-owned derived '
                                     'database only; post-reset readiness also explicitly uses '
                                     'container loopback TCP port 5432. Default, foreign, invalid '
                                     'or ambient-overridden targets cannot replace the owned '
                                     'namespace; socket psql behavior remains unchanged.'},
                     {'check_id': 'sql_failure_no_replay',
                      'command': 'uv run pytest -q tests/db/test_lifecycle.py -k sql_failure',
                      'pass_oracle': 'After final TCP readiness, injected DROP and CREATE failures '
                                     'independently propagate with original redacted actionable '
                                     'diagnostics. Neither destructive statement is replayed; '
                                     'CREATE is never attempted after failed DROP. No destructive '
                                     'SQL retry, reset restart, or success fabrication.'},
                     {'check_id': 'compose_and_lifecycle_tcp_alignment',
                      'command': 'uv run pytest -q tests/db/test_startup_readiness.py',
                      'pass_oracle': 'Structural checks inspect actual Compose healthcheck and '
                                     'both actual lifecycle probes: each explicitly targets '
                                     '127.0.0.1 port 5432 inside postgres, not published host port '
                                     'or socket. Tests reject a socket-healthcheck regression. SQL '
                                     'stays on the existing socket/authentication path. Namespace, '
                                     'secret redaction, ports, volume, image, normal startup and '
                                     'migrations stay unchanged.'},
                     {'check_id': 'isolated_migrated_coldstart',
                      'command': 'uv run python tools/db/verify_startup_readiness.py --iterations '
                                 '3 --startup-timeout 60 --total-timeout 300',
                      'pass_oracle': 'Three bounded cold starts use three fresh resolved temporary '
                                     'worktree roots with exact Compose '
                                     'kineticloop-kl074-cold-<shortsha>-<digest> and database '
                                     'kineticloop_kl074_cold_<shortsha>_<digest> names; shortsha '
                                     'is tested_commit first7 lowercase hex and digest is SHA256 '
                                     'of os.fsencode(resolved root) first12 lowercase hex; '
                                     'validate exact names before first reset, verify no '
                                     'preexisting owned resources/volume, and fail closed on '
                                     'malformed/mismatched/default/foreign target. Inspect actual '
                                     'configured image, resolved image ID/digest and in-container '
                                     'entrypoint SHA256/source, Docker/Compose/PostgreSQL '
                                     'versions, and timestamped startup logs/probe events. Prove '
                                     'socket-only init start, init stop, final TCP-ready start '
                                     'ordering for the actual image, zero measured lifecycle SQL '
                                     'before final readiness, then successful reset and existing '
                                     'two-phase migrated bootstrap on the identical owned '
                                     'lifecycle. Verify current_database and migrated revision, '
                                     'repeated reset sentinel removal and namespace isolation. '
                                     'Each iteration captures evidence before finally destroying '
                                     'only its exact owned containers/network/volume and proving '
                                     'absence; cleanup failure fails. Total wall time and '
                                     'subprocess durations are bounded; no foreign/default DB '
                                     'reset or destroy. If actual ordering/root cause cannot be '
                                     'demonstrated, report FAIL/NOT_RUN with limitation, never '
                                     'infer PASS from success alone. Execute through the ratified '
                                     'exact-head hosted workflow; retain raw logs/provenance plus '
                                     'downloaded artifacts bound to tested_commit before final '
                                     'result/review.'},
                     {'check_id': 'lifecycle_regressions',
                      'command': 'uv run pytest -q tests/db/test_lifecycle.py '
                                 'tests/db/test_startup_readiness.py',
                      'pass_oracle': 'All existing lifecycle assertions plus new positive/negative '
                                     'startup checks pass without skips, xfail, disabled tests or '
                                     'changed SQL/auth/namespace semantics.'},
                     {'check_id': 'full_repository_regressions',
                      'command': 'uv run pytest -q -p no:cacheprovider',
                      'pass_oracle': 'Entire repository suite passes with no suppressed '
                                     'failures/skips added by this task on a dedicated hosted VM '
                                     'with job-owned Docker. Retain all normal CI jobs/gates and '
                                     'existing DB suites; hosted VM isolates legacy prerequisite '
                                     'fixture namespaces. Do not run legacy full DB suites on '
                                     'shared developer Docker or borrow KL019/KL024/KL025 '
                                     'resources. Preserve exact head-bound full-suite evidence. '
                                     'Execute through the ratified exact-head hosted workflow; '
                                     'retain raw logs/provenance plus downloaded artifacts bound '
                                     'to tested_commit before final result/review.'},
                     {'check_id': 'quality_and_harness',
                      'command': 'uv run kl lint && uv run kl typecheck && uv run kl test-harness '
                                 '&& uv run kl check-harness',
                      'pass_oracle': 'All four commands exit 0; check-harness prints '
                                     'HARNESS_CHECK_PASS. Every normal hosted CI and applicable '
                                     'merge gate also passes at the reviewed head; no workflow '
                                     'weakening, retry concealment or fixed startup sleep.'},
                     {'check_id': 'hosted_entrypoint_and_evidence',
                      'command': 'uv run pytest -q tests/db/test_startup_readiness.py -k '
                                 'hosted_entrypoint',
                      'pass_oracle': 'Structural positive/negative tests prove the single new '
                                     'workflow matches the ratified bytes/hash, explicit PR head '
                                     'checkout, same-repository codex/kl074- entrypoint, locked '
                                     'uv, fresh ubuntu-latest runner, local default Docker daemon '
                                     'preflight, bounded pipefail commands and always-uploaded '
                                     'task-only artifacts. Existing workflows and gates remain '
                                     'byte-identical. Actual hosted '
                                     'run/job/head/run-attempt/artifact identity and downloaded '
                                     'raw coldstart/full-suite/provenance evidence must match '
                                     'tested_commit; both exact commands and their oracles pass '
                                     'without skips or continue-on-error. '
                                     'Missing/skipped/incomplete/mismatched execution is '
                                     'NOT_RUN/FAIL, never PASS. No new secrets, elevated token '
                                     'permissions, remote/self-hosted daemon, arbitrary inputs or '
                                     'command substitutions.'}],
 'evidence_paths': ['docs/exec-plans/evidence/KL-074/**'],
 'write_paths_status': 'ENFORCEABLE'}

READINESS_PACKET_BOUNDARIES = {'Repair boundary': 'Use explicit container loopback TCP pg_isready --host 127.0.0.1 --port 5432 '
                    'for startup, Compose healthcheck and post-reset readiness. Retain the '
                    'existing monotonic startup deadline and normal startup handling; bound each '
                    'probe subprocess to remaining deadline so the timeout oracle is real. A '
                    'readiness-loop backoff is allowed within that bound; no unconditional startup '
                    'sleep. Keep psql socket usage, credentials, image, ports, volumes and '
                    'namespaces unchanged. No destructive SQL retry, fixed sleeps, unbounded '
                    'waits, CI suppression, migrations, transaction/authorization semantics or '
                    'product/frozen changes.',
 'Isolation and evidence boundary': 'The dedicated probe validates exact Compose '
                                    'kineticloop-kl074-cold-<shortsha>-<digest> and database '
                                    'kineticloop_kl074_cold_<shortsha>_<digest> before any '
                                    'reset/bootstrap/cleanup: shortsha is tested_commit first7 '
                                    'lowercase hex; digest is SHA256 of os.fsencode(resolved root) '
                                    'first12 lowercase hex. Never accept caller-supplied or '
                                    'ambient namespaces. Use three fresh task-owned temporary '
                                    'roots, the unchanged checked-in Compose file, and the '
                                    'existing tests/db/test_migrations.py '
                                    'bootstrap_two_phase(lifecycle) on that same selected '
                                    'lifecycle. Reject preexisting resources and '
                                    'foreign/default/ambient targets. Record image/digest, actual '
                                    'entrypoint hash/source, timestamped logs and probe/SQL '
                                    'ordering; redact credentials. Assert migrated revision, exact '
                                    'current_database, reset sentinel removal, cross-root '
                                    'separation and finally cleanup absence. Bound iterations, '
                                    'total wall time and subprocesses. Failure or unavailable '
                                    'exact root-cause evidence must be reported; source inference '
                                    'is not deployed-image proof. Full legacy DB suites run on a '
                                    'dedicated hosted VM, not shared Docker; never overlap KL019 '
                                    'transaction resources.',
 'Hosted execution and evidence entrypoint': 'KL074 creates only '
                                             '.github/workflows/kl074-readiness.yml with exact '
                                             'bytes from '
                                             'docs/exec-plans/evidence/HG-037/kl074-readiness.workflow.proposal.yml, '
                                             'pinned by READINESS_WORKFLOW_SHA256 in '
                                             'tools/harness/validate_harness.py; an existing '
                                             'baseline file or byte drift fails closed. Open a '
                                             'same-repository codex/kl074- PR; pull_request '
                                             'opened/synchronize/reopened/ready_for_review runs '
                                             'before merge, with no caller inputs. The single '
                                             'ubuntu-latest job checks out '
                                             'github.event.pull_request.head.sha, verifies git '
                                             'HEAD, uses uv 0.12.17 and uv sync --locked, and '
                                             'rejects non-GitHub-hosted Linux or any '
                                             'DOCKER_HOST/DOCKER_CONTEXT override, nondefault '
                                             'context or nonlocal socket endpoint. Execute the '
                                             'exact three-iteration coldstart command and uv run '
                                             'pytest -q -p no:cacheprovider with pipefail and '
                                             'finite step/job deadlines. No secret access, token '
                                             'permission expansion, self-hosted/remote daemon, '
                                             'test suppression, continue-on-error or existing '
                                             'workflow/gate edits.\n'
                                             '\n'
                                             'The probe must validate '
                                             'KINETICLOOP_KL074_TESTED_COMMIT equals git HEAD and '
                                             'KINETICLOOP_KL074_EVIDENCE_DIR resolves exactly to '
                                             'docs/exec-plans/evidence/KL-074/hosted-<tested_commit> '
                                             'under the checkout before writing. Write raw '
                                             'timestamped container logs, actual image/entrypoint '
                                             'provenance, ordered probes/SQL, migrated/reset '
                                             'assertions and finally-cleanup evidence below that '
                                             'directory. This environment sets evidence output '
                                             'only, never namespaces. The always() upload '
                                             'preserves this directory on success/failure; '
                                             'incomplete upload or skipped steps cannot establish '
                                             'PASS. Before artifact expiry, download raw files (or '
                                             'byte-exact envelopes), record run/job URLs, '
                                             'event/head SHA, run ID/attempt and artifact '
                                             'ID/digest, and commit them under task evidence '
                                             'before final result/review. Verify '
                                             'hosted-provenance/logs and both exact command '
                                             'oracles against tested_commit. Final reviewed-head '
                                             'normal CI/gates also pass independently; a changed '
                                             'implementation stales checks/reviews. Missing, '
                                             'failed, skipped, mismatched or unavailable '
                                             'actual-image evidence is NOT_RUN/FAIL. Governance '
                                             'ratification is not execution evidence.',
 'Non-goals': 'Do not implement downstream protocol/product work, alter completed KL002 '
              'definitions/results/evidence, edit existing CI workflows or any workflow except the '
              'single additive .github/workflows/kl074-readiness.yml, migration/schema/auth/role '
              'ownership, other fixtures or SQL command semantics. No production/live credentials '
              'or data. No product requirement PASS, release closure or auto-activation claim. '
              'Stop with SPEC_CHANGE_REQUIRED for any frozen authorization, admission, lock, '
              'transaction, provider or shadow boundary change.',
 'Exact lifecycle readiness candidate': 'KL074 may change lifecycle source only to '
                                        'readiness_lifecycle_candidate(before) in '
                                        'tools/harness/validate_harness.py, anchored to '
                                        'READINESS_LIFECYCLE_BASE_SHA256. The complete-byte '
                                        'candidate adds explicit loopback TCP to '
                                        'startup/post-reset, passes the positive remaining '
                                        'monotonic deadline into each startup probe subprocess, '
                                        'bounds readiness backoff by remaining time, adds only '
                                        'optional runner timeout plumbing and a non-replaying '
                                        'sanitized TimeoutExpired error. It preserves every other '
                                        'byte, including normal Compose startup, '
                                        'namespace/credential ownership, socket psql, DROP/CREATE '
                                        'order, redaction and cleanup. Unexpected baseline or any '
                                        'extra startup command, namespace/credential mutation, SQL '
                                        'runner bypass, foreign endpoint or timeout drift fails '
                                        'closed. Compose changes only the exact ratified loopback '
                                        'healthcheck test.'}

def readiness_definition_errors(task):
    if task.get('id') != 'KL-074':
        return []
    return ['readiness-definition-drift:' + field
            for field in set(task) | set(READINESS_TASK_DEFINITION)
            if task.get(field) != READINESS_TASK_DEFINITION.get(field)]


def readiness_packet_errors(task, text):
    if task.get('id') != 'KL-074':
        return []
    return ['readiness-packet-boundary:' + heading
            for heading, value in READINESS_PACKET_BOUNDARIES.items()
            if (section(text, heading) or '').strip() != value]


READINESS_LIFECYCLE_BASE_SHA256 = 'de55f62dd25e3379c67b7b6306cdbd882ce8a6d3d615715a7f9d35c30c6a3686'
READINESS_LIFECYCLE_REPLACEMENTS = [('    def _run(\n'
  '        self,\n'
  '        command: Sequence[str],\n'
  '        *,\n'
  '        check: bool = True,\n'
  '    ) -> subprocess.CompletedProcess[str]:\n'
  '        try:\n'
  '            return self._runner(\n'
  '                list(command),\n'
  '                cwd=self.root,\n'
  '                env=self.environment,\n'
  '                check=check,\n'
  '                capture_output=True,\n'
  '                text=True,\n'
  '            )\n'
  '        except FileNotFoundError as error:\n'
  '            raise DatabaseLifecycleError(\n'
  '                "Docker with the Compose plugin is required for the local test database."\n'
  '            ) from error\n'
  '        except subprocess.CalledProcessError as error:\n'
  '            details = Redactor((self.user, self.password)).exception_diagnostic(error)\n'
  '            raise DatabaseLifecycleError(f"database command failed: {details}") from None\n'
  '\n',
  '    def _run(\n'
  '        self,\n'
  '        command: Sequence[str],\n'
  '        *,\n'
  '        check: bool = True,\n'
  '        timeout_seconds: float | None = None,\n'
  '    ) -> subprocess.CompletedProcess[str]:\n'
  '        try:\n'
  '            return self._runner(\n'
  '                list(command),\n'
  '                cwd=self.root,\n'
  '                env=self.environment,\n'
  '                check=check,\n'
  '                capture_output=True,\n'
  '                text=True,\n'
  '                timeout=timeout_seconds,\n'
  '            )\n'
  '        except subprocess.TimeoutExpired:\n'
  '            raise DatabaseLifecycleError("database readiness command timed out") from None\n'
  '        except FileNotFoundError as error:\n'
  '            raise DatabaseLifecycleError(\n'
  '                "Docker with the Compose plugin is required for the local test database."\n'
  '            ) from error\n'
  '        except subprocess.CalledProcessError as error:\n'
  '            details = Redactor((self.user, self.password)).exception_diagnostic(error)\n'
  '            raise DatabaseLifecycleError(f"database command failed: {details}") from None\n'
  '\n'),
 ('    def start(self, *, timeout_seconds: float = 60.0) -> None:\n'
  '        self.validate_compose()\n'
  '        self._run(self.compose_command("up", "--detach", "postgres"))\n'
  '        deadline = time.monotonic() + timeout_seconds\n'
  '        while time.monotonic() < deadline:\n'
  '            result = self._run(\n'
  '                self.compose_command(\n'
  '                    "exec",\n'
  '                    "--no-TTY",\n'
  '                    "postgres",\n'
  '                    "pg_isready",\n'
  '                    "--username",\n'
  '                    self.user,\n'
  '                    "--dbname",\n'
  '                    "postgres",\n'
  '                ),\n'
  '                check=False,\n'
  '            )\n'
  '            if result.returncode == 0:\n'
  '                return\n'
  '            time.sleep(0.5)\n'
  '        raise DatabaseLifecycleError(\n'
  '            f"PostgreSQL did not become ready within {timeout_seconds:g} seconds"\n'
  '        )\n'
  '\n',
  '    def start(self, *, timeout_seconds: float = 60.0) -> None:\n'
  '        self.validate_compose()\n'
  '        self._run(self.compose_command("up", "--detach", "postgres"))\n'
  '        deadline = time.monotonic() + timeout_seconds\n'
  '        while time.monotonic() < deadline:\n'
  '            remaining = deadline - time.monotonic()\n'
  '            if remaining <= 0:\n'
  '                break\n'
  '            result = self._run(\n'
  '                self.compose_command(\n'
  '                    "exec",\n'
  '                    "--no-TTY",\n'
  '                    "postgres",\n'
  '                    "pg_isready",\n'
  '                    "--host",\n'
  '                    "127.0.0.1",\n'
  '                    "--port",\n'
  '                    "5432",\n'
  '                    "--username",\n'
  '                    self.user,\n'
  '                    "--dbname",\n'
  '                    "postgres",\n'
  '                ),\n'
  '                check=False,\n'
  '                timeout_seconds=remaining,\n'
  '            )\n'
  '            if result.returncode == 0:\n'
  '                return\n'
  '            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))\n'
  '        raise DatabaseLifecycleError(\n'
  '            f"PostgreSQL did not become ready within {timeout_seconds:g} seconds"\n'
  '        )\n'
  '\n'),
 ('    def reset(self, *, timeout_seconds: float = 60.0) -> DatabaseConnection:\n'
  '        self.start(timeout_seconds=timeout_seconds)\n'
  '        quoted_database = f\'"{self.namespace.database_name}"\'\n'
  '        quoted_user = f\'"{self.user}"\'\n'
  '        self._psql(\n'
  '            "postgres",\n'
  '            f"DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE);",\n'
  '        )\n'
  '        self._psql(\n'
  '            "postgres",\n'
  '            f"CREATE DATABASE {quoted_database} OWNER {quoted_user};",\n'
  '        )\n'
  '        ready = self._run(\n'
  '            self.compose_command(\n'
  '                "exec",\n'
  '                "--no-TTY",\n'
  '                "postgres",\n'
  '                "pg_isready",\n'
  '                "--username",\n'
  '                self.user,\n'
  '                "--dbname",\n'
  '                self.namespace.database_name,\n'
  '            ),\n'
  '            check=False,\n'
  '        )\n'
  '        if ready.returncode != 0:\n'
  '            raise DatabaseLifecycleError("reset database failed its readiness probe")\n'
  '        return self.connection()\n'
  '\n',
  '    def reset(self, *, timeout_seconds: float = 60.0) -> DatabaseConnection:\n'
  '        self.start(timeout_seconds=timeout_seconds)\n'
  '        quoted_database = f\'"{self.namespace.database_name}"\'\n'
  '        quoted_user = f\'"{self.user}"\'\n'
  '        self._psql(\n'
  '            "postgres",\n'
  '            f"DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE);",\n'
  '        )\n'
  '        self._psql(\n'
  '            "postgres",\n'
  '            f"CREATE DATABASE {quoted_database} OWNER {quoted_user};",\n'
  '        )\n'
  '        ready = self._run(\n'
  '            self.compose_command(\n'
  '                "exec",\n'
  '                "--no-TTY",\n'
  '                "postgres",\n'
  '                "pg_isready",\n'
  '                "--host",\n'
  '                "127.0.0.1",\n'
  '                "--port",\n'
  '                "5432",\n'
  '                "--username",\n'
  '                self.user,\n'
  '                "--dbname",\n'
  '                self.namespace.database_name,\n'
  '            ),\n'
  '            check=False,\n'
  '            timeout_seconds=timeout_seconds,\n'
  '        )\n'
  '        if ready.returncode != 0:\n'
  '            raise DatabaseLifecycleError("reset database failed its readiness probe")\n'
  '        return self.connection()\n'
  '\n')]


def readiness_lifecycle_candidate(before):
    """Only the complete reviewed bounded-readiness delta is authorized."""
    if hashlib.sha256(before).hexdigest() != READINESS_LIFECYCLE_BASE_SHA256:
        raise ValueError('unexpected readiness lifecycle baseline')
    text = before.decode()
    for old, new in READINESS_LIFECYCLE_REPLACEMENTS:
        if text.count(old) != 1:
            raise ValueError('unexpected readiness lifecycle method baseline')
        text = text.replace(old, new, 1)
    return text.encode()


def readiness_content_errors(path, before, after):
    """Keep startup ownership, SQL/auth and every other source byte exact."""
    if path == 'compose.yaml':
        import yaml
        try:
            old, new = yaml.safe_load(before), yaml.safe_load(after)
            expected = ['CMD-SHELL', 'pg_isready --host 127.0.0.1 --port 5432 --username "$${POSTGRES_USER}" --dbname "$${POSTGRES_DB}"']
            if new['services']['postgres']['healthcheck']['test'] != expected:
                return ['readiness-compose-tcp-required']
            new['services']['postgres']['healthcheck']['test'] = old['services']['postgres']['healthcheck']['test']
            return [] if old == new else ['readiness-compose-content-scope']
        except (KeyError, TypeError, yaml.YAMLError):
            return ['readiness-compose-content-scope']
    if path != 'src/kineticloop/db/lifecycle.py':
        return []
    try:
        expected = readiness_lifecycle_candidate(before)
    except (ValueError, UnicodeError):
        return ['readiness-lifecycle-baseline-unexpected']
    return [] if after == expected else ['readiness-lifecycle-content-scope']


READINESS_WORKFLOW_PATH = '.github/workflows/kl074-readiness.yml'
READINESS_WORKFLOW_SHA256 = 'bbf7f77baa008a13660313c4af9b6ace506b41c22da7fee1737a4afd4870f6df'


def readiness_workflow_errors(base_listing, after):
    """Only the new, ratified exact-head hosted entrypoint is authorized."""
    if base_listing.strip():
        return ['readiness-workflow-baseline-exists']
    return [] if hashlib.sha256(after).hexdigest() == READINESS_WORKFLOW_SHA256 else ['readiness-workflow-content-scope']





M3_NEXT_WAVE_IDS = frozenset({'KL-026', 'KL-027', 'KL-075', 'KL-076', 'KL-077', 'KL-078', 'KL-079'})
M3_NEXT_WAVE_DEFINITION_HASHES = {'KL-026': '4f7c470fa4cbbe77be7dd3a3c18e1576eab282a710097cfeaf0a74a7e352ca8e', 'KL-027': 'c096b030c9cdb6ac9d71d3ed309660bcb68e5e30b7ad8316b3ccd5df4ae7e625', 'KL-075': '1f2f0fbe783abc2368fc933db23732c5416338a8f67a4fea52aac65dce78aa50', 'KL-076': '97912a9834f1fefa97455fe7466a97aba6562995de34023814476b227698b5b6', 'KL-077': 'f918fd380cfe402ce8beb6c8f22ce9e166ef0d4a66282c5c73a53a97a0bc156e', 'KL-078': 'ed872c583bdead8c9486183f31fdcebc8bf7f5591a53b724ff7ae261844c8138', 'KL-079': 'd49050bee1608949a6d20246b5b3650b02c448498e4dba5867cca5c13cb63086'}
M3_NEXT_WAVE_PACKET_HASHES = {'KL-026': '31c83ce523976265f89aa2be3890d2b428d1a23d65ae486f24e266333c854942', 'KL-027': 'c35634ce527adb3e0db39697a91874091f14a74c1a5254b910d46332e004a4cc', 'KL-075': '698722f17f1b8b977b440e79b11fe240d1605304fd95bf26f98abbf0520ee835', 'KL-076': '354dc2a62a65e8266c869a412282a363fe4347a401d52eca31cf84adf15603b7', 'KL-077': 'b081aaa48d188c2fb8c2a5367685b652580fdac162d9a4fd9e6fc273732875cc', 'KL-078': 'cc742bb17b2f282fdb78cb65971b9c9d7c39d73cb1935221c25470e266bf7784', 'KL-079': 'fba0aaf04430071435862030829ac580ea736566ee9bdaf72bdf67d5f88b57ae'}


def m3_next_wave_definition_errors(task):
    name = task.get('id')
    if name not in M3_NEXT_WAVE_IDS or (
            task.get('packet_refinement') != 'ENFORCEABLE'
            and 'check_contracts' not in task):
        return []
    actual = hashlib.sha256(json.dumps(
        task, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'),
    ).encode()).hexdigest()
    return ([] if actual == M3_NEXT_WAVE_DEFINITION_HASHES[name]
            else ['m3-next-wave-definition:' + name])


def m3_next_wave_packet_errors(task, text):
    name = task.get('id')
    if name not in M3_NEXT_WAVE_IDS or (
            task.get('packet_refinement') != 'ENFORCEABLE'
            and 'check_contracts' not in task):
        return []
    actual = hashlib.sha256(text.encode()).hexdigest()
    return ([] if actual == M3_NEXT_WAVE_PACKET_HASHES[name]
            else ['m3-next-wave-packet:' + name])


M3_BOUNDARY_SHADOW_IDS = frozenset({'KL-028', 'KL-029'})
M3_BOUNDARY_SHADOW_PLAN_SHA256 = '538045ee80d1e08b01829dc128cb7d9b48ebce0cb6f3c250acd128bf45effa2e'
M3_BOUNDARY_SHADOW_DEFINITION_HASHES = {'KL-028': '275b2e7138e4248e87655938e00a0b31a43fb2e408fb8a7e75f14d15bf9ba2a6', 'KL-029': '89fa038dddb353f5c71ce6d2389b9cbb3ef369932294ac20d15b23171e9f448d'}
M3_BOUNDARY_SHADOW_PACKET_HASHES = {'KL-028': 'cca391611cf96ca2590bee303eb1c519c53a42546ca7a9d1fe6bb5b29e32bb8d', 'KL-029': '27137bfbe5b338da563195704c36ef41990de0779ee90858db38a8de297ffe72'}
B_LAYER_OBLIGATIONS = {
    'B01': ('PU', 'DC'), 'B02': ('DC',), 'B03': ('DC',),
    'B04': ('DC', 'E2E'), 'B05': ('DC', 'E2E'), 'B06': ('DC',),
    'B07': ('DC', 'E2E'), 'B08': ('PU', 'E2E'), 'B09': ('PU', 'DC'),
    'B10': ('PU', 'E2E'), 'B11': ('PU', 'DC'), 'B12': ('PU', 'DC'),
    'B13': ('DC',), 'B14': ('WF', 'E2E'), 'B15': ('DC',),
    'B16': ('DC', 'E2E'), 'B17': ('PU', 'DC'), 'B18': ('PU', 'E2E'),
}


def m3_boundary_shadow_definition_errors(task):
    """Pin disjoint tests-only ownership and every prospective check/oracle."""
    name = task.get('id')
    if name not in M3_BOUNDARY_SHADOW_IDS:
        return []
    actual = hashlib.sha256(json.dumps(
        task, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
    ).encode()).hexdigest()
    return ([] if actual == M3_BOUNDARY_SHADOW_DEFINITION_HASHES[name]
            else ['m3-boundary-shadow-definition:' + name])


def m3_boundary_shadow_plan_errors(text):
    """Pin the explicit parallel DB plan and closure/deferred-layer limitations."""
    scoped = section(text, 'M3 boundary and shadow readiness — HG042') or ''
    marker = '<!-- HG042 plan end -->'
    if scoped.count(marker) != 1:
        return ['m3-boundary-shadow-plan']
    block = scoped.partition(marker)[0].strip()
    return ([] if hashlib.sha256(block.encode()).hexdigest() == M3_BOUNDARY_SHADOW_PLAN_SHA256
            else ['m3-boundary-shadow-plan'])


def packet_json_section(text, heading):
    block = section(text, heading) or ''
    match = re.fullmatch(r'\s*```json\s*\n(.*?)\n```\s*', block, re.S)
    if match is None:
        raise ValueError('missing JSON section: ' + heading)
    return json.loads(match[1], object_pairs_hook=unique_mapping)


def m3_boundary_layer_errors(ledger, requirements=None):
    """Keep all 31 frozen Given/When/Then obligations, without inferred PASS."""
    if not isinstance(ledger, list) or any(not isinstance(row, dict) for row in ledger):
        return ['m3-boundary-layer-ledger']
    expected = [(rid, layer) for rid, layers in B_LAYER_OBLIGATIONS.items() for layer in layers]
    actual = [(row.get('requirement_id'), row.get('layer')) for row in ledger]
    errors = []
    if actual != expected:
        errors.append('m3-boundary-layer-obligations')
    if any(row.get('status') != 'NOT_RUN' for row in ledger):
        errors.append('m3-boundary-layer-status')
    for row in ledger:
        rid, layer = row.get('requirement_id'), row.get('layer')
        deferred = layer in ('WF', 'E2E') or (rid in ('B11', 'B12') and layer == 'PU')
        disposition = 'DEFERRED_LAYER' if deferred else 'KL028_PLANNED_EXECUTABLE'
        if rid == 'B04' and layer == 'DC':
            disposition = 'DEFERRED_FULL_ORACLE_WITH_GUARD_SUPPORT'
        if (row.get('disposition') != disposition
                or (deferred and (not row.get('reason') or not row.get('required_future_owner')))
                or (not deferred and any(not row.get(field) for field in
                                        ('check_id', 'selector', 'owner', 'pass_oracle', 'frozen_clauses')))
                or (rid == 'B04' and layer == 'DC' and
                    (not row.get('qualification') or not row.get('future_owner')))):
            errors.append('m3-boundary-layer-disposition:' + str(rid) + '@' + str(layer))
    if requirements is not None:
        authority = {r['requirement_id']: r for r in requirements}
        if list(authority) != list(B_LAYER_OBLIGATIONS) or any(
                list(layers) != authority.get(rid, {}).get('layers')
                for rid, layers in B_LAYER_OBLIGATIONS.items()):
            errors.append('m3-boundary-layer-authority-set')
        for row in ledger:
            rid = row.get('requirement_id')
            if any(row.get(field) != authority.get(rid, {}).get(field)
                   for field in ('given', 'when', 'then')):
                errors.append('m3-boundary-layer-authority:' + str(rid))
    return errors


def m3_boundary_shadow_packet_errors(task, text):
    name = task.get('id')
    if name not in M3_BOUNDARY_SHADOW_IDS or (
            task.get('packet_refinement') != 'ENFORCEABLE' and 'check_contracts' not in task):
        return []
    errors = []
    if hashlib.sha256(text.encode()).hexdigest() != M3_BOUNDARY_SHADOW_PACKET_HASHES[name]:
        errors.append('m3-boundary-shadow-packet:' + name)
    try:
        statuses = packet_json_section(text, 'Prospective check status')
        if statuses != {cid: 'NOT_RUN' for cid in task['checks_required_for_this_task']}:
            errors.append('m3-boundary-shadow-prospective-status:' + name)
        if name == 'KL-028':
            errors.extend(m3_boundary_layer_errors(packet_json_section(text, 'Boundary layer ledger')))
    except (KeyError, ValueError, TypeError):
        errors.append('m3-boundary-shadow-ledger-json:' + name)
    return errors




SOURCE_DECISION_DEFINITION_SHA256 = 'd38938644a40c079417e1437bc9d807c2aa8fa5d9768cfdb70f71db47ed23bcd'
SOURCE_DECISION_PACKET_SHA256 = 'ae418be455ba140854e6e3cc73c11de4628f5e4a11477a84cc3815e2d766a816'
SOURCE_DECISION_PLAN_SHA256 = '2d570ba1ac870cfed32d84977e2b08e7d896f756185847269242c422af5b6636'
SOURCE_FIXTURE_REPLACEMENTS = {
    'tests/db/test_factsets.py': [("'unresolved','UNRESOLVED'", "'unresolved','AMBIGUOUS'"),
                                  ("'ALL','DENIED'", "'ALL','NOT_ELIGIBLE'")],
    'tests/db/test_preparation.py': [("'actual-event','UNRESOLVED'", "'actual-event','AMBIGUOUS'"),
                                    ("'TEST_ONLY','ADMITTED'", "'TEST_ONLY','ELIGIBLE'")],
    'tests/db/test_protocol_interleavings.py': [("'TEST_ONLY','ACCEPTED'", "'TEST_ONLY','ELIGIBLE'")],
    'tests/db/test_transaction_interfaces.py': [("'EXECUTION','ADMITTED'", "'EXECUTION','ELIGIBLE'")],
}


def source_decision_definition_errors(task):
    if task.get('id') != 'KL-080':
        return []
    return ([] if canonical_value_sha(task) == SOURCE_DECISION_DEFINITION_SHA256
            else ['source-decision-definition:KL-080'])


def source_decision_packet_errors(task, text):
    if task.get('id') != 'KL-080':
        return []
    return ([] if hashlib.sha256(text.encode()).hexdigest() == SOURCE_DECISION_PACKET_SHA256
            else ['source-decision-packet:KL-080'])


def source_decision_plan_errors(text):
    marker = '## Prospective source-decision conformance — HG045'
    end = '<!-- HG045 plan end -->'
    if text.count(marker) != 1 or text.count(end) != 1:
        return ['source-decision-plan']
    block = text.split(marker, 1)[1].split(end, 1)[0]
    return ([] if hashlib.sha256(block.encode()).hexdigest() == SOURCE_DECISION_PLAN_SHA256
            else ['source-decision-plan'])


def source_governance_plan_prefix_errors(root, base, reviewed):
    before = git(root, 'show', base + ':' + PROJECT_PLAN).decode()
    after = git(root, 'show', reviewed + ':' + PROJECT_PLAN).decode()
    return ([] if after.split('## Prospective source-decision conformance — HG045', 1)[0]
            == before + '\n' else ['governance-hg045-plan-prefix'])


def source_fixture_content_errors(path, before, after):
    """Only the identified source literals may change; all other bytes are pinned."""
    expected = before
    for old, new in SOURCE_FIXTURE_REPLACEMENTS[path]:
        if expected.count(old.encode()) != 1:
            return ['source-fixture-base:KL-080:' + path]
        expected = expected.replace(old.encode(), new.encode(), 1)
    return ([] if after == expected else ['source-fixture-content-scope:KL-080:' + path])


if __name__ == '__main__':
    sys.exit(main())
