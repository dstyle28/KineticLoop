'Fresh hostile synthetic definition tests; no production/native project audit.'
import copy,json,os,subprocess,sys,time
from pathlib import Path
import pytest,jsonschema
import sequence_model as m
D=Path(__file__).resolve().parent
P=m.fixture_premise()
E=m.fixture_events(P)

def deny(events,premise=P):
    with pytest.raises((m.Denial,jsonschema.ValidationError)):m.evaluate_synthetic_sequence(events,premise)
def phase(events,name):return next(e['facts'] for e in events if e['phase']==name)
def test_complete_staged_route_keeps_actual_operations_not_run():
    r=m.evaluate_synthetic_sequence(E,P)
    assert r['phases']==21 and r['native_actual_O_to_K']==r['installed_host']=='NOT_RUN'
    assert r['acceptance_eligible'] is r['execution_reuse'] is False

def test_whole_native_inventory_oracle_counts_unrelated_path_too():
    x=m.fixture_inventory_oracle(P['inventory_objects'],P['bodies'],P['retained_groups'],P['object_bytes'])
    assert x['files']==9 and len(x['errors'])==4
    assert x['stored_bytes']==sum(o['bytes'] for o in P['inventory_objects'])

@pytest.mark.parametrize('name',m.PHASE['ordered_phases'],ids=m.PHASE['ordered_phases'])
def test_each_mandatory_phase_cannot_be_omitted(name):deny([e for e in copy.deepcopy(E) if e['phase']!=name])
@pytest.mark.parametrize('name',m.PHASE['ordered_phases'],ids=m.PHASE['ordered_phases'])
def test_each_phase_cannot_be_reassigned_to_other_owner(name):
    e=copy.deepcopy(E);r=next(x for x in e if x['phase']==name);r['actor']='AUTHOR' if r['actor']=='ROOT' else 'ROOT';deny(e)
@pytest.mark.parametrize('name',m.PHASE['ordered_phases'],ids=m.PHASE['ordered_phases'])
def test_phase_receipt_or_flag_cannot_create_new_authority(name):
    e=copy.deepcopy(E);phase(e,name)['trusted_receipt']=True;deny(e)

def test_every_adjacent_reorder_and_duplicate_phase_denies():
    for n in range(len(E)-1):
        e=copy.deepcopy(E);e[n],e[n+1]=e[n+1],e[n];deny(e)
    for n in range(len(E)):
        e=copy.deepcopy(E);e.insert(n,e[n]);deny(e)

MUTATIONS={
 'public-root-caller':lambda e:phase(e,'PREIMPORT').update(entry='PUBLIC_AUDIT_CLI'),
 'test-only-controller':lambda e:phase(e,'PREIMPORT').update(entry='TEST_ONLY_CONTROLLER'),
 'candidate-config':lambda e:phase(e,'PREIMPORT').update(config_private_regular=False),
 'unauthenticated-App':lambda e:phase(e,'PREIMPORT').update(app_authenticated=False),
 'unknown-root-task':lambda e:phase(e,'PREIMPORT').update(existing_root_task_selection='harness-governance-v0.1/HG-999'),
 'missing-executor-lock':lambda e:phase(e,'PREIMPORT').update(lock_held=False),
 'foreign-store':lambda e:phase(e,'PREIMPORT').update(owned_store=False),
 'candidate-Python':lambda e:phase(e,'BOOTSTRAP_INSTALL').update(imports_installed_only=False),
 'self-install':lambda e:phase(e,'BOOTSTRAP_INSTALL').update(root_installed=False),
 'installation-in-checkout':lambda e:phase(e,'BOOTSTRAP_INSTALL').update(outside_checkout=False),
 'bootstrap-review-not-independent':lambda e:phase(e,'BOOTSTRAP_REVIEW').update(independent=False),
 'stale-install-commit':lambda e:phase(e,'BOOTSTRAP_INSTALL')['bundle'].update(installed_commit=P['roots']['original_selected']),
 'missing-one-asset':lambda e:phase(e,'BOOTSTRAP_REVIEW')['bundle']['assets'].pop(),
 'partial-controller-files':lambda e:phase(e,'BOOTSTRAP_REVIEW')['bundle']['controller_files'].pop('compact_evidence.py'),
 'different-image':lambda e:phase(e,'BOOTSTRAP_REVIEW')['bundle'].update(image='0'*64),
 'stale-P':lambda e:phase(e,'PREIMPORT').update(P='0'*40),
 'proof-Q-only':lambda e:phase(e,'PREIMPORT').update(K=P['roots']['original_selected']),
 'new-K-original-declaration':lambda e:phase(e,'PREIMPORT').update(original_declaration=P['roots']['bootstrap']),
 'K-moved-after-proof':lambda e:phase(e,'IMPORT_RECHECK').update(K='0'*40),
 'P-moved-after-proof':lambda e:phase(e,'IMPORT_RECHECK').update(P='0'*40),
 'stale-controller':lambda e:phase(e,'IMPORT_RECHECK').update(controller='0'*64),
 'reuse-JSON-instead-of-operation':lambda e:phase(e,'IMPORT_RECHECK').update(actual_operation_reobserved=False),
 'deferred-original-native-work':lambda e:phase(e,'PREIMPORT').update(native_predicates='WILL_RUN_AFTER_IMPORT'),
 'native-denial':lambda e:phase(e,'PREIMPORT')['output'].update(status='PREIMPORT_DENIED',ready_for_exact_import=False,preserved_duplicate_paths=0,preserved_duplicate_bytes=0,denial_reasons=['NATIVE_GUARD_DENIED']),
 'partial-original':lambda e:phase(e,'PREIMPORT')['output'].update(complete=False,original_guard_status='PARTIAL'),
 'premature-final-accounted':lambda e:phase(e,'PREIMPORT')['output'].update(type='RETAINED_REPRESENTATION_CUSTODY_V1',status='CUSTODY_ACCOUNTED_ORIGINAL_INVENTORY'),
 'pretend-preimport-live-pass':lambda e:phase(e,'PREIMPORT')['output'].update(live_guard_status='ALL_NATIVE_OBSERVED'),
 'preimport-admission-pass':lambda e:phase(e,'PREIMPORT')['output'].update(admission_status='PASS'),
 'P-imported-before-K-freeze':lambda e:phase(e,'STAGE_FROZEN').update(P_imported=True),
 'reversed-import-parents':lambda e:phase(e,'BASE_IMPORT')['parents'].reverse(),
 'Q-instead-actual-predecessor':lambda e:phase(e,'BASE_IMPORT')['parents'].__setitem__(0,P['roots']['original_selected']),
 'map-or-source-rewrite':lambda e:phase(e,'BASE_IMPORT').update(maps_sources_unchanged=False),
 'no-import-edge-check':lambda e:phase(e,'BASE_IMPORT').update(every_import_edge='ENDPOINT_EQUAL_ONLY'),
 'dirty-K':lambda e:phase(e,'STAGE_FROZEN').update(clean=False),
 'staging-record-edit':lambda e:phase(e,'STAGE_FROZEN')['changed_paths'].append('docs/exec-plans/governance/HG-058.yaml'),
 'staging-map-edit':lambda e:phase(e,'STAGE_FROZEN')['changed_paths'].append('docs/exec-plans/evidence/HG-058/recovery-conversion/COMPACT_REENCODING.json'),
 'old-evidence-edit':lambda e:phase(e,'STAGE_FROZEN')['changed_paths'].append('docs/exec-plans/evidence/HG-058/old.json'),
 'staging-policy-edit':lambda e:phase(e,'STAGE_FROZEN')['changed_paths'].append('docs/harness/EVIDENCE_STORAGE_POLICY.md'),
 'bootstrap-tests-as-T':lambda e:phase(e,'AUTHOR_CHECKS')['rows'][0].update(tested=P['roots']['bootstrap'],bootstrap_reused=True),
 'bootstrap-no-positive-identities':lambda e:phase(e,'STAGE_CHECKS').update(positive_identities='EMPTY'),
 'bootstrap-skip':lambda e:phase(e,'STAGE_CHECKS').update(skips=1),
 'bootstrap-required-not-run':lambda e:phase(e,'STAGE_CHECKS').update(native_inventory_maps_edges=None),
 'author-required-NOT_RUN':lambda e:phase(e,'AUTHOR_CHECKS')['rows'][0].update(result='NOT_RUN',exit_code=None),
 'author-exit-bool':lambda e:phase(e,'AUTHOR_CHECKS')['rows'][0].update(exit_code=False),
 'author-exit-nonzero':lambda e:phase(e,'AUTHOR_CHECKS')['rows'][0].update(exit_code=1),
 'author-positive-identities-lost':lambda e:phase(e,'AUTHOR_CHECKS')['rows'][0].update(execution=[]),
 'author-phase-incomplete':lambda e:phase(e,'AUTHOR_CHECKS')['rows'][0]['phases'].update(teardown=[]),
 'post-R-evidence':lambda e:phase(e,'REVIEW_SUFFIX').update(post_R_task_evidence=True),
 'fake-root-PASS-in-author-R':lambda e:phase(e,'RESULT_R').update(external_gates='PASS'),
 'external-NOT_RUN-selected-row':lambda e:phase(e,'RESULT_R').update(no_external_NOT_RUN_selected_rows=False),
 'task-review-stale':lambda e:phase(e,'TASK_REVIEWS').update(R=P['roots']['bootstrap']),
 'RRO-merge':lambda e:phase(e,'REVIEW_SUFFIX').update(linear_own_review_only=False),
 'final-stale-install':lambda e:phase(e,'FINAL_INSTALL')['bundle'].update(installed_commit=P['roots']['bootstrap']),
 'stale-admission':lambda e:phase(e,'ADMISSION').update(H=P['roots']['result']),
 'wrong-native-selection':lambda e:phase(e,'ADMISSION').update(native_selected_identity='harness-governance-v0.1/HG-202'),
 'final-live-NOT_RUN':lambda e:phase(e,'FINAL_ORIGINAL_AND_LIVE').update(strict_P_to_H='NOT_RUN'),
 'accounted-before-live':lambda e:phase(e,'FINAL_ORIGINAL_AND_LIVE').update(accounted_output_published_after_live=False),
 'ORIGINAL-failure-swallowed':lambda e:phase(e,'FINAL_ORIGINAL_AND_LIVE').update(all_native_errors_propagated=False),
 'worker-private-credential':lambda e:phase(e,'WORKER_AND_HOSTED').update(private_credential_passed=True),
 'worker-original-base':lambda e:phase(e,'WORKER_AND_HOSTED')['worker_args'].__setitem__(1,P['roots']['original']),
 'fullDB-omitted':lambda e:phase(e,'WORKER_AND_HOSTED')['gates'].pop('app_full_database'),
 'cleanup-failed':lambda e:phase(e,'WORKER_AND_HOSTED')['gates'].update(cleanup='FAIL'),
 'public-final-child-relabel0':lambda e:phase(e,'FINAL_PUBLIC_DENIAL').update(child_exit=0),
 'snapshot-moved-before-publication':lambda e:phase(e,'FINAL_SNAPSHOT').update(snapshot_unchanged=False),
 'bypass-merge':lambda e:phase(e,'NORMAL_MERGE').update(no_bypass=False),
}
@pytest.mark.parametrize('case',list(MUTATIONS),ids=list(MUTATIONS))
def test_staged_authority_binding_scope_execution_and_final_hostile_regression(case):
    e=copy.deepcopy(E);MUTATIONS[case](e);deny(e)

def test_coordinated_K_rebinding_and_Q_substitution_still_denies_independent_facts():
    e=json.loads(json.dumps(E).replace(P['roots']['bootstrap'],'f'*40))
    deny(e)
    e=json.loads(json.dumps(E).replace(P['roots']['bootstrap'],P['roots']['original_selected']))
    deny(e)

def test_every_author_required_command_has_exact_T_R_individual_ownership():
    own=json.loads((D/'CHECK_OWNERSHIP.json').read_bytes())
    assert len(own['author_required'])==20 and len({x['check_id'] for x in own['author_required']})==20
    assert all(x['phase']=='T' and x['evidence_revision']=='R' and x['observed_exit']==0 and not x['bootstrap_reuse'] for x in own['author_required'])
    assert all(x['hard_prerequisite'] and not x['selected_checks_run'] for x in own['root_required'])
    assert own['final_ci_pr']['owner']=='ROOT' and own['final_ci_pr']['phase']=='FINAL_H'

def test_literal_protected_allowlist_adds_only_local_gate_and_stage_remains_narrow():
    d=json.loads((D/'SCOPE_CORRECTION.json').read_bytes())
    assert d['proposed']==d['original']+['tools/harness/local_gate.py']
    assert m.fixture_scope('tools/harness/local_gate.py')
    assert m.fixture_scope('docs/exec-plans/evidence/HG-058/preimport-stage/new.json')
    for path in ['tools/harness/gate_validate.py','docs/exec-plans/active/HG-058.md','HARNESS_CHANGE.schema.json','CURRENT_DOCUMENT_INDEX.json','docs/exec-plans/evidence/HG-058/preimport-stageA/a.json','docs/exec-plans/evidence/HG-058/recovery-conversion/COMPACT_REENCODING.json']:
        assert not m.fixture_scope(path)
    for path in ['../tools/harness/local_gate.py','tools//harness/local_gate.py','/tools/harness/local_gate.py','tools/harness/../local_gate.py','tools/harness/local_gate.py\n']:
        with pytest.raises(m.Denial):m.fixture_scope(path)

def test_all_five_findings_have_precise_prospective_supersession_rows():
    d=json.loads((D/'CLAUSE_SUPERSESSION.json').read_bytes())
    assert {x['finding'] for x in d['clauses']}=={'A1','A2','A3','A4','A5'}
    assert d['hg065_ten_normative_source_bytes']=='PRESERVED' and d['final_output_schema']=='VERSIONED_V2_TYPE_ORIGINAL_GUARD_CONJUNCTION_UNCHANGED'


def test_original_purpose_562_source_and_512_projection_caps_remain_unchanged():
    b=json.loads((D/'BUDGETS.json').read_bytes());old=json.loads((D.parent/'HG-065/BUDGETS.json').read_bytes())
    assert b['incorporated_original']==old
    assert m.LIMITS['list_entries']==512 and b['raise_or_reset_allowed'] is False
    assert 'full source562' in (D/'EXECUTION_CONTRACT.md').read_text() or 'Original_source562' in (D/'EXECUTION_CONTRACT.md').read_text()


def test_preimport_type_cannot_pass_unchanged_final_accounted_schema():
    out=phase(E,'PREIMPORT')['output']
    jsonschema.validate(out,m.PRESCHEMA)
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(out,m.FINAL_SCHEMA)
    forged=copy.deepcopy(out);forged.update(type='RETAINED_REPRESENTATION_CUSTODY_V1',status='CUSTODY_ACCOUNTED_ORIGINAL_INVENTORY')
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(forged,m.FINAL_SCHEMA)

def test_closed_sequence_grammar_accepts_neutral_original_bindings_without_owner_hash_allowlist():
    schema=json.loads((D/'SEQUENCE_SCHEMA.json').read_bytes())
    for p in [P,m.fixture_premise(selected='HG-301',foreign='HG-302',body_salt=' OTHER')]:
        jsonschema.validate(m.fixture_events(p),schema)
    e=copy.deepcopy(E);phase(e,'PREIMPORT')['unexpected_field']=1
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(e,schema)

def test_exact_preparatory_commands_are_separate_from_final_author_acceptance():
    rows=json.loads((D/'STAGING_CHECKS.json').read_bytes())['rows']
    assert len(rows)==8 and {x['check_id'] for x in rows}==set(m.PHASE['stage_check_ids'])
    assert all(x['observed_exit']==0 and x['stage_binding']=='K' and x['authority_binding']=='P' and not x['reuse_for_T'] for x in rows)
    assert all(x['command_template'].startswith('uv run ') for x in rows)
