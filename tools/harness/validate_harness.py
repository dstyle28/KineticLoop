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
M3_CHECK_CONTRACT_DIGESTS.update({'KL-080:source_matrix_pu': '19af2ee64ff3252048fe1647b4db2a5650da19a422dd53dbe8ea373d0c7d04f8', 'KL-080:source_basis_pu': '01bb79e806cd5d4d1cb2fa0ac6bb9f9a14b495db3a70cfc8d91aabd938e8e394', 'KL-080:source_namespace_pu': '3fc5b595fb73d9b5c125974a2c79879ad82219e40735c82cd2e22f3fc5fc62d6', 'KL-080:source_preparation_owners_dc': 'f909c9abe19c9172763608774fef3e6e059b38753724a6c7de3ff288a21e5a04', 'KL-080:source_canonical_full_t6_dc': '9912e7ef6a61a4f6fc3e08283d75526c37be7616562b792489acb299a1eaa6b8', 'KL-080:source_invalid_reconstruction_dc': '5af6a7a4affcfb962f2026fe92efdbe50de776d654461e790036e2467358cfa9', 'KL-080:source_freshness_predicate_support_dc': 'd321e7e4fa2ca78de7a67560a8fb54fa97b46d9f172a9eab2ae655265a51f10f', 'KL-080:source_owner_trajectories_dc': 'c160c417b07acf895af1990dfa4b1484f04540e8208963df9ece774a1918dfdb', 'KL-080:source_current_denials_dc': 'f31dc1775decf90c5c6570ae622e11785a049a1d263bb1eb1b132f7303b3e405', 'KL-080:source_repair_replay_expiry_dc': 'e2789843bb544a414b1eb9a894b218db9e3c2fb75ff634b553686ace4436d879', 'KL-080:source_suite_dc': '28f767bb41b5680cd4d20551473364bcac8910e8511cc867ccb63936eadadc80', 'KL-080:source_suite_pu': '91323a2050340406822bbbfdd6ac6cea046d323cd96324c61a7159e948ee4f8d'})
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
            and task.get('packet_refinement') == 'ENFORCEABLE') or (name in (WAVE_REFINED_TASK_IDS | {'KL-019', 'KL-025', 'KL-074', 'KL-026', 'KL-027', 'KL-075', 'KL-076', 'KL-077', 'KL-078', 'KL-079', 'KL-080', 'KL-028', 'KL-029'})
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


def governance_allowed_patterns(change_id):
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

    if change_id == 'HG-048':
        return [INDEX, MANIFEST, 'src/kineticloop/cli.py', 'pyproject.toml', 'uv.lock',
                'tools/harness/run_harness_tests.py', 'tools/harness/parallel_observer.py',
                'tools/harness/validate_harness.py', 'tests/harness/test_parallel_runner.py',
                'tools/harness/README.md', 'docs/exec-plans/evidence/HG-048/**',
                'docs/exec-plans/reviews/HG-048/**', 'docs/exec-plans/governance/HG-048.yaml']
