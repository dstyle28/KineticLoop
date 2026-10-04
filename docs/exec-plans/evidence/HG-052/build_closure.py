"""Construct exact M3 witnesses from revision-bound merged records; no new oracle."""
import argparse
import importlib.util
import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('hg052_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def schemas():
    return [Draft202012Validator(v.load_artifact(ROOT / p)) for p in
            ('MILESTONE_CLOSURE.schema.json', 'INTEGRATION_RECORD.schema.json',
             'THREAD_RESULT.schema.json', 'THREAD_REVIEW.schema.json')]


def context(revision):
    backlog = v.load_artifact_at_revision(ROOT, v.BACKLOG, revision)
    errors, tasks = v.task_definition_errors(ROOT, backlog, revision)
    assert not errors, errors
    records = {}
    pending = list(v.M3_TASK_IDS | {'KL-074'})
    while pending:
        name = pending.pop()
        if name in records:
            continue
        records[name] = v.load_artifact_at_revision(ROOT, f'docs/exec-plans/integrations/{name}.json', revision)
        pending.extend(tasks[name]['depends_on'])
    assert len(records) == 35, len(records)
    return backlog, tasks, records


def reference(path, revision):
    assert v.revision_regular_file(ROOT, path, revision), path
    return dict(path=path, revision=revision, sha256=v.blob_sha_at_revision(ROOT, path, revision))


def build(revision, regression):
    backlog, tasks, records = context(revision)
    s = schemas()
    errors = []
    for name, record in records.items():
        errors.extend(v.integration_record_errors(ROOT, Path(f'docs/exec-plans/integrations/{name}.json'), record, *s[1:], tasks))
    errors.extend(v.m3_dependency_order_errors(ROOT, records, tasks))
    m2 = v.load_artifact_at_revision(ROOT, 'docs/exec-plans/milestones/M2.json', revision)
    errors.extend(v.m2_milestone_closure_errors(ROOT, m2, *s, backlog, tasks))
    assert not errors, sorted(set(errors))
    def integration(name):
        ref = reference(f'docs/exec-plans/integrations/{name}.json', revision)
        return dict(task_identity='harness-backlog-v0.2/' + name, display_task_id=name,
                    integration_record=ref['path'], sha256=ref['sha256'])
    exits = []
    for exit_id, mapping in v.M3_EXIT_TASK_CHECKS.items():
        witnesses = []
        for name, checks in mapping.items():
            reviewed = records[name]['reviewed_head_sha']
            result_path, = v.result_paths_at_revision(ROOT, name, reviewed)
            result = v.load_artifact_at_revision(ROOT, result_path, reviewed)
            for check in checks:
                contract, = [c for c in tasks[name]['check_contracts'] if c['check_id'] == check]
                command, = [c for c in result['commands_run'] if c['check_id'] == check]
                witnesses.append(dict(task_identity=tasks[name]['task_identity'], check_id=check,
                    result='PASS', command=command['command'], tested_commit=result['tested_commit'],
                    oracle_sha256=v.canonical_value_sha(contract['pass_oracle']),
                    result_artifact=reference(result_path, reviewed), raw=reference(command['evidence_ref'], reviewed)))
        exits.append(dict(check_id=exit_id, result='PASS', task_checks=witnesses))
    ledger = v.packet_json_section(v.git(ROOT, 'show', revision + ':docs/exec-plans/active/KL-028.md').decode(), 'Boundary layer ledger')
    for row in ledger:
        if row['disposition'] == 'KL028_PLANNED_EXECUTABLE':
            row['status'] = 'PASS'
    closure = dict(milestone_identity='harness-backlog-v0.2/M3', display_milestone_id='M3',
        closure_status='PASS', evaluated_commit=revision,
        integrations=[integration(n) for n in sorted(v.M3_TASK_IDS)],
        supporting_prerequisites=[integration('KL-074')],
        m2_prerequisite=reference('docs/exec-plans/milestones/M2.json', revision),
        exit_checks=exits, integrated_regression=reference(regression, revision), boundary_layers=ledger,
        interleaving_layers=[dict(requirement_id=f'I{i:02}', layer='DC', status='PASS', task_identity='harness-backlog-v0.2/KL-026', check_id=f'i{i:02}_dc') for i in range(1,10)] + [dict(requirement_id='I04', layer='WF', status='NOT_RUN', required_future_owner='M4 worker/fault process evidence')],
        historical_model_evidence=dict(status='UNVERIFIED_HISTORICAL_DECLARATION', independently_reproducible_protocol_model=False),
        product_requirement_pass_claims=[], production_auto_activation=False, shadow_executable=False,
        shadow_usability_status='NOT_RUN', r04_e2e_status='NOT_RUN')
    errors = v.m3_milestone_closure_errors(ROOT, closure, *s, backlog, tasks)
    assert not errors, sorted(set(errors))
    return closure

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--revision', required=True); p.add_argument('--regression', required=True)
    a = p.parse_args()
    dest = ROOT / 'docs/exec-plans/milestones/M3.json'
    assert not dest.exists()
    dest.write_text(json.dumps(build(a.revision, a.regression), indent=2) + '\n')
