"""Independent SHA-bound GENERAL review audit for HG-049."""
from pathlib import Path
from collections import Counter
import ast
import copy
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
import jsonschema
from tools.harness import compact_evidence as ce
from tools.harness import validate_harness as v

ROOT = Path(__file__).resolve().parents[5]
BASE = '95ddd75d3eb410b7dffa15a1017276c504adc9a6'
TESTED = '4db695230c2158f67394c8ac79a5f0fdf511849a'
REVIEWED = 'ceed78db431a348aae0b599a5e1b09bb082fb968'
OWN = ROOT / 'docs/exec-plans/reviews/HG-049/general'
PREFIX = 'docs/exec-plans/evidence/HG-049/checks-4db6952/'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def blob(path, revision=REVIEWED):
    return ce.blob(ROOT, path, revision)


def load(path, revision=REVIEWED):
    return json.loads(blob(path, revision))


def persist(path, data):
    assert ce.envelope(data) is None
    assert len(data) <= ce.PLAIN_LIMIT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main():
    assert git('rev-parse', 'HEAD').decode().strip() == REVIEWED
    record = v.parse_artifact_text(blob('docs/exec-plans/governance/HG-049.yaml').decode(), '.yaml')
    jsonschema.validate(record, load('HARNESS_CHANGE.schema.json'))
    assert record['change_identity'] == 'harness-governance-v0.1/HG-049'
    assert record['base_commit'] == BASE and record['tested_commit'] == TESTED
    assert record['change_status'] == 'PASS'
    changed = git('diff', '--no-renames', '--name-only', BASE, REVIEWED).decode().splitlines()
    assert set(changed) == set(record['files_changed']) and len(changed) == len(record['files_changed']) == 53
    assert all(v.matches(path, v.governance_allowed_patterns('HG-049')) for path in changed)
    assert v.governance_suffix_errors(ROOT, TESTED, REVIEWED, 'HG-049', 'tested') == []
    suffix = git('diff', '--name-status', TESTED, REVIEWED).decode().splitlines()
    assert all(line.startswith('A\tdocs/exec-plans/evidence/HG-049/checks-4db6952/') or line == 'A\tdocs/exec-plans/governance/HG-049.yaml' for line in suffix)
    parent = git('rev-list', '--parents', '-n', '1', REVIEWED).decode().split()
    assert parent == [REVIEWED, TESTED]
    source_changed = [p for p in changed if not p.startswith('docs/exec-plans/evidence/') and p != 'docs/exec-plans/governance/HG-049.yaml']
    assert set(source_changed) == {'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json', 'KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Harness_Traceability_v0.3.json', 'docs/exec-plans/active/KL-080.md', 'tools/harness/validate_harness.py', 'tests/harness/test_source_decision_scope.py'}
    for path in source_changed:
        assert blob(path, TESTED) == blob(path)
    old_backlog = load(v.BACKLOG, BASE)
    new_backlog = load(v.BACKLOG)
    old_task = next(t for t in old_backlog['tasks'] if t['id'] == 'KL-080')
    task = next(t for t in new_backlog['tasks'] if t['id'] == 'KL-080')
    expected = copy.deepcopy(old_backlog)
    target = next(t for t in expected['tasks'] if t['id'] == 'KL-080')
    target['deliverables'][1] = task['deliverables'][1]
    target['check_contracts'][7]['pass_oracle'] = task['check_contracts'][7]['pass_oracle']
    assert expected == new_backlog
    assert task['status'] == 'NOT_STARTED' and task['requirements_covered'] == [] and task['evidence_refs'] == []
    assert len(task['check_contracts']) == 17 and len(task['write_paths']) == 19 and len(task['resource_keys']) == 8
    assert len(task['review_requirements']) == 4 and len(task['depends_on']) == 10
    assert not v.source_decision_definition_errors(task)
    assert not v.packet_errors(task, blob('docs/exec-plans/active/KL-080.md').decode())
    expected_trace = load(v.TRACEABILITY, BASE)
    expected_trace['tasks'][next(i for i,t in enumerate(expected_trace['tasks']) if t['id']=='KL-080')] = v.traceability_projection(task)
    assert expected_trace == load(v.TRACEABILITY)
    for path in git('ls-tree', '-r', '--name-only', BASE).decode().splitlines():
        if path.startswith(('src/', 'tests/db/', 'docs/history/', 'docs/exec-plans/completed/', 'docs/exec-plans/reviews/', 'docs/exec-plans/evidence/', 'docs/exec-plans/integrations/', 'docs/exec-plans/milestones/')):
            assert blob(path, BASE) == blob(path)
    for path in ['FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','MILESTONE_CLOSURE.schema.json', v.PROJECT_PLAN, 'pyproject.toml','uv.lock']:
        assert blob(path, BASE) == blob(path)
    for entry in load('FROZEN_BASELINE.json', BASE)['files']:
        assert blob(entry['path'], BASE) == blob(entry['path'])
    for path in ['docs/exec-plans/completed/KL-080_RESULT.yaml', 'docs/exec-plans/completed/KL-080_RESULT.json','docs/exec-plans/integrations/KL-080.json','docs/exec-plans/milestones/M3.json']:
        assert not git('ls-tree', REVIEWED, '--', path)
    budget = ce.audit(ROOT, BASE, REVIEWED, 'HG-049')
    assert budget['errors'] == []
    execution = load(PREFIX+'EXECUTION.json')
    assert execution['tested_commit'] == TESTED
    assert execution['driver_sha256'] == ce.digest(blob(PREFIX+'driver.py'))
    assert execution['locked_dependencies_sha256'] == ce.digest(blob('uv.lock'))
    checks = {c['check_id']:c for c in record['checks_run']}
    assert set(checks) == {'harness','unit','authority','lint','typecheck','scope','diff'}
    run_checks = {c['check_id']:c for c in execution['checks']}
    assert set(run_checks) == set(checks)
    raw_hashes = {}
    for key, check in checks.items():
        run = run_checks[key]
        assert run['exit_code'] == 0 and run['tested_commit'] == TESTED
        assert run['command'] == check['command'] and run['evidence_ref'] == check['evidence_ref']
        assert check['result'] == 'PASS'
        raw = ce.read(ROOT, check['evidence_ref'], REVIEWED, tested=TESTED, command=check['command'], exit_code=0)
        raw_hashes[key] = ce.digest(raw)
    hcommand = checks['harness']['command']
    ancillary = {name:ce.read(ROOT, PREFIX+name+'.json', REVIEWED, tested=TESTED, command=hcommand, exit_code=0) for name in ['harness-manifest-json','harness-collection-json','harness-execution-json','harness-junit-xml','harness-pytest-log']}
    manifest=json.loads(ancillary['harness-manifest-json'])
    assert manifest['tested_commit']==TESTED and manifest['dirty_source'] is False
    assert manifest['execution_complete'] is True and manifest['mode']=='EXECUTION'
    assert manifest['errors']==[] and manifest['exit_code']==0 and manifest['pytest_exit_code']==0
    names={'collection.json':'harness-collection-json','execution.json':'harness-execution-json','junit.xml':'harness-junit-xml','pytest.log':'harness-pytest-log'}
    for item in manifest['files']:
        name=names.get(item['path'])
        if name:
            raw=ancillary[name]
        else:
            assert item['path']=='collection.log'
            raw=ce.read(ROOT,PREFIX+'harness-collection-log.json',REVIEWED,tested=TESTED,command=hcommand,exit_code=0)
        assert item['bytes']==len(raw) and item['sha256']==ce.digest(raw)
    collection=json.loads(ancillary['harness-collection-json'])
    observer=json.loads(ancillary['harness-execution-json'])
    selected=collection['collections']['serial']
    assert len(selected)==1347 and len(set(selected))==1347
    assert collection['errors']==[] and collection['exit_code']==0
    assert observer['errors']==[] and observer['exit_code']==0
    assert len(observer['started'])==1347 and set(observer['started'])==set(selected)
    assert all(items==selected for items in observer['collections'].values())
    assert Counter((r['nodeid'],r['phase']) for r in observer['reports'])==Counter((node,phase) for node in selected for phase in ['setup','call','teardown'])
    assert all(r['outcome']=='passed' for r in observer['reports'])
    suites=ET.fromstring(ancillary['harness-junit-xml'])
    cases=suites.findall('.//testcase')
    assert len(cases)==1347
    assert all(not suites.findall('.//'+tag) for tag in ['failure','error','skipped'])
    unit=ce.read(ROOT,PREFIX+'unit-junit.json',REVIEWED,tested=TESTED,command=checks['unit']['command'],exit_code=0)
    usuites=ET.fromstring(unit)
    assert len(usuites.findall('.//testcase'))==241
    assert all(not usuites.findall('.//'+tag) for tag in ['failure','error','skipped'])
    focused=[node for node in selected if node.startswith('tests/harness/test_source_decision_scope.py::')]
    m3=[node for node in selected if node.startswith('tests/harness/test_m3_milestone_closure.py::')]
    assert focused and m3
    precommit=[]
    for path in changed:
        if path.startswith('docs/exec-plans/evidence/HG-049/precommit/') and path.endswith('.json'):
            data=blob(path)
            metadata=ce.envelope(data)
            if metadata is not None:
                raw=ce.read(ROOT,path,REVIEWED)
                precommit.append({'path':path,'exit_code':metadata['exit_code'],'raw_hash':ce.digest(raw)})
    command=[str(ROOT/'.venv/bin/python'),'-m','pytest','-q','-p','no:cacheprovider','tests/harness/test_source_decision_scope.py']
    env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1'
    proc=subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    persist(OWN/'focused.log',proc.stdout)
    assert proc.returncode==0
    report={'status':'PASS','review_scope':'Independent GENERAL governance review; merge and exact-head external gates remain pending', 'base_commit':BASE,'tested_commit':TESTED,'reviewed_head_sha':REVIEWED,'files_changed_count':len(changed),'tested_reviewed_linear_new_evidence_suffix':True,'source_changed_paths':source_changed,'harness_collected':len(selected),'harness_completed':len(observer['started']),'harness_reports':len(observer['reports']),'harness_junit_cases':len(cases),'focused_cases_in_complete_run':len(focused),'m3_cases_in_complete_run':len(m3),'unit_junit_cases':len(usuites.findall('.//testcase')),'all_seven_checks_bound_and_passed':True,'check_raw_hashes':raw_hashes,'execution_driver_hash':execution['driver_sha256'],'precommit_lossless_dirty_probe_records':precommit,'compact_budget':budget,'focused_review_command':command,'focused_review_exit_code':proc.returncode,'audit_source_hash':ce.digest(Path(__file__).read_bytes()),'limitations':['No complete historical harness rerun; retained SHA-bound collection, per-phase observer, JUnit and raw output inspected','No PostgreSQL owner execution by this governance review; prospective KL080 and product/release checks NOT_RUN','Normal exact-head hosted CI, trusted App controller admission/publication and complete isolated DB gates remain required and unwaived']}
    persist(OWN/'AUDIT.json',(json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
