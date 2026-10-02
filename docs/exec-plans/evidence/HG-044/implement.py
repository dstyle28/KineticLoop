"""HG044 bounded definition generator; no completion instance is generated."""
import hashlib
import json
from pathlib import Path

r = Path.cwd()
b = json.loads((r / 'KineticLoop_Harness_Backlog_v0.2.json').read_text())
tasks = {t['id']: t for t in b['tasks']}
groups = {
    'full_test_fdn_trajectory_and_repair': {'KL-027': ['demo_owner_trajectory_e2e', 'demo_fdn_repair_e2e']},
    'current_denials_and_immutable_history': {'KL-027': ['demo_revoke_denials_dc', 'demo_expiry_denials_dc'], 'KL-077': ['continue_resume_current_dc', 'full_execution_replay_atomicity_dc'], 'KL-028': ['b07_dc', 'b16_dc']},
    'nine_actual_dc_interleavings': {'KL-026': [f'i{i:02}_dc' for i in range(1, 10)] + ['time_boundary_pu']},
    'ready_sealed_barriers': {'KL-023': ['factset_complete_writer_interleaving_dc', 'factset_seal_frontier_atomicity_and_replay_dc'], 'KL-028': ['b01_pu', 'b01_dc', 'b02_dc', 'b03_dc']},
    'registry_commit_freshness_and_closure': {'KL-021': ['t2_global_commit_rollback_and_effective_at_semantics'], 'KL-028': ['b04_dc', 'b05_dc', 'b06_dc', 'b11_dc', 'b12_dc', 'b13_dc', 'b14_registry_failclosed_stop_support_dc', 'b15_dc', 'b17_pu', 'b17_dc']},
    'validity_missing_timeless_and_expiry': {'KL-022': ['validity_closure_minimum_and_missing_values_pu', 'timeless_policy_dependency_closure_pu', 't6_certificate_and_minimum_closure_dc'], 'KL-028': ['b08_pu', 'b09_pu', 'b09_dc', 'b10_pu', 'b18_pu']},
    'isolated_test_and_evaluation_boundaries': {'KL-027': ['demo_namespace_and_boundary_pu', 'demo_scope_denials_dc'], 'KL-028': ['boundary_namespace_pu'], 'KL-029': [c['check_id'] for c in tasks['KL-029']['check_contracts'] if '::' in c['command']]},
}
checks = {n: {c['check_id']: c for c in t.get('check_contracts', [])} for n,t in tasks.items()}
pinned = {(n,c):checks[n][c] for group in groups.values() for n,ids in group.items() for c in ids}
def digest(v): return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
constants = '\n# HG044 ratified M3 exit mapping. These are task checks, never aggregate product PASS.\n'
constants += 'M3_TASK_IDS = {f\'KL-{n:03d}\' for n in range(19, 30)} | {f\'KL-{n:03d}\' for n in range(75, 80)}\n'
constants += 'M3_EXIT_TASK_CHECKS = ' + repr(groups) + '\n'
constants += 'M3_CHECK_CONTRACT_DIGESTS = ' + repr({n+':'+c:digest(v) for (n,c),v in pinned.items()}) + '\n'
constants += 'M3_REGRESSION_COMMANDS = ' + repr(['uv run kl test-unit', 'uv run kl test-harness', 'uv run kl check-harness'] + sorted({v['command'] for v in pinned.values()})) + '\n'
p=r/'tools/harness/validate_harness.py'; text=p.read_text(); text=text.replace('M1_TASK_IDS = ',constants+'\nM1_TASK_IDS = ',1);p.write_text(text)
# The M1/M2 schema branches are left byte-for-byte semantically unchanged.
p=r/'MILESTONE_CLOSURE.schema.json'; s=json.loads(p.read_text()); ev={'$ref':'#/$defs/evidence'}
s['$defs']['m3_task_check']={'type':'object','additionalProperties':False,'required':['task_identity','check_id','tested_commit','result','command','oracle_sha256','result_artifact','raw'],'properties':{'task_identity':{'type':'string','pattern':r'^harness-backlog-v0\.2/KL-[0-9]{3}$'},'check_id':{'type':'string'},'tested_commit':{'type':'string','pattern':'^[0-9a-f]{40}$'},'result':{'const':'PASS'},'command':{'type':'string'},'oracle_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'result_artifact':ev,'raw':ev}}
props={'milestone_identity':{'const':'harness-backlog-v0.2/M3'},'display_milestone_id':{'const':'M3'},'closure_status':{},'evaluated_commit':{},'integrations':{'type':'array','minItems':16,'maxItems':16,'items':{'$ref':'#/$defs/integration'}},'supporting_prerequisites':{'type':'array','minItems':1,'maxItems':1,'items':{'$ref':'#/$defs/integration'}},'m2_prerequisite':ev,'exit_checks':{'type':'array','minItems':len(groups),'maxItems':len(groups),'items':{'type':'object','additionalProperties':False,'required':['check_id','result','task_checks'],'properties':{'check_id':{'enum':list(groups)},'result':{'const':'PASS'},'task_checks':{'type':'array','minItems':1,'items':{'$ref':'#/$defs/m3_task_check'}}}}},'integrated_regression':ev,'boundary_layers':{'type':'array','minItems':31,'maxItems':31,'items':{'type':'object'}},'interleaving_layers':{'type':'array','minItems':10,'maxItems':10,'items':{'type':'object'}},'historical_model_evidence':{},'product_requirement_pass_claims':{},'production_auto_activation':{'const':False},'shadow_executable':{'const':False},'shadow_usability_status':{'const':'NOT_RUN'},'r04_e2e_status':{'const':'NOT_RUN'}}
s['oneOf'].append({'allOf':[{'$ref':'#/$defs/base'},{'type':'object','additionalProperties':False,'required':list(props),'properties':props}]});p.write_text(json.dumps(s,indent=2)+'\n')
