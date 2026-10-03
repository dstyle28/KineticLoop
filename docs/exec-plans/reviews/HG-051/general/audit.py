"""Independent GENERAL review of committed HG051 provenance and scope."""
import hashlib
import importlib.util
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]
BASE = 'b877db0edd2e4550d6ea81750656112fb7f2e223'
HEAD = '7141b1dfe48df8f0e25429cf9ff646af6de4b5ce'
TESTED = '5debfe1b41a26c0b3f985917b80995a9eb38b92e'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    ce = load_module('general_compact', 'tools/harness/compact_evidence.py')
    v = load_module('general_validator', 'tools/harness/validate_harness.py')
    assert git('rev-parse', 'HEAD').decode().strip() == HEAD
    git('merge-base', '--is-ancestor', BASE, TESTED)
    git('merge-base', '--is-ancestor', TESTED, HEAD)
    changed = git('diff', '--no-renames', '--name-only', BASE, HEAD).decode().splitlines()
    assert all(v.matches(path, v.governance_allowed_patterns('HG-051')) for path in changed)
    after_test = git('diff', '--name-only', TESTED, HEAD).decode().splitlines()
    assert all(path.startswith('docs/exec-plans/evidence/HG-051/final-5debfe1/') or
               path == 'docs/exec-plans/governance/HG-051.yaml' for path in after_test)
    def artifact_tree(revision):
        entries = git('ls-tree', '-r', '-z', revision, '--', 'docs/exec-plans/evidence',
                      'docs/exec-plans/reviews', 'docs/exec-plans/completed').split(b'\0')
        return {entry.split(b'\t', 1)[1].decode(): entry.split(b'\t', 1)[0]
                for entry in entries if entry}
    prior, current = artifact_tree(BASE), artifact_tree(HEAD)
    assert all(current.get(path) == entry for path, entry in prior.items())
    frozen = json.loads(git('show', BASE + ':FROZEN_BASELINE.json'))
    for path in ['FROZEN_BASELINE.json', *[item['path'] for item in frozen['files']]]:
        assert git('rev-parse', BASE + ':' + path) == git('rev-parse', HEAD + ':' + path)
    before = json.loads(git('show', BASE + ':' + v.BACKLOG))
    after = json.loads(git('show', HEAD + ':' + v.BACKLOG))
    for old, new in zip(before['tasks'], after['tasks'], strict=True):
        if old['id'] == 'KL-080':
            expected = dict(old, definition_of_done=new['definition_of_done'])
            assert expected == new and new['definition_of_done'].startswith(old['definition_of_done'])
        else:
            assert old == new
    for group in ('documents', 'machine_readable'):
        for entry in json.loads(git('show', HEAD + ':CURRENT_DOCUMENT_INDEX.json'))[group]:
            assert hashlib.sha256(git('show', HEAD + ':' + entry['path'])).hexdigest() == entry['sha256']
    schema = ce.historical_schema()
    original_summaries = []
    for original in ce.historical_originals():
        raw = ce.archive_original(ROOT, original)
        record = original['execution_record']
        data = ce.blob(ROOT, record['path'], record['revision'])
        assert len(data) == record['bytes'] and ce.digest(data) == record['sha256']
        value = json.loads(data)
        if 'executions' in value:
            value = next(x for x in value['executions'] if x['check_id'] == 'source_suite_dc')
        for key in ('tested_commit', 'command', 'exit_code', 'result'):
            assert value[key] == original['execution'][key]
        assert original['execution']['timestamp'] is None
        original_summaries.append(dict(path=original['path'], exact_bytes=len(raw),
                                       original_revision=original['revision'],
                                       original_exit=original['execution']['exit_code']))
    preserved = schema['properties']['preserved_records']['const']
    for ref in preserved:
        data = ce.blob(ROOT, ref['path'], ref['revision'])
        assert ce.digest(data) == ref['sha256'] and len(data) == ref['bytes']
    first_result = yaml.safe_load(ce.blob(ROOT, preserved[0]['path'], preserved[0]['revision']))
    outcome = schema['properties']['historical_outcome']['const']
    assert first_result['task_status'] == outcome['task_status']
    assert first_result['task_checks_status'] == outcome['task_checks_status']
    assert first_result['tested_commit'] == outcome['tested_commit']
    for ref in preserved[1:]:
        review = json.loads(ce.blob(ROOT, ref['path'], ref['revision']))
        assert review['reviewed_head_sha'] == outcome['reviewed_head_sha']
        assert review['status'] == outcome['review_status']
    governance = yaml.safe_load(git('show', HEAD + ':docs/exec-plans/governance/HG-051.yaml'))
    execution_path = 'docs/exec-plans/evidence/HG-051/final-5debfe1/EXECUTION.json'
    executions = json.loads(git('show', HEAD + ':' + execution_path))
    assert executions['tested_commit'] == executions['source_end_sha'] == TESTED
    assert executions['source_end_status'] == ''
    checks = []
    for check, run in zip(governance['checks_run'], executions['executions'], strict=True):
        assert check['check_id'] == run['check_id'] and check['command'] == run['command']
        assert check['result'] == 'PASS' and run['exit_code'] == 0 and run['tested_commit'] == TESTED
        log = ce.read(ROOT, check['evidence_ref'], HEAD, tested=TESTED,
                      command=run['command'], exit_code=run['exit_code'])
        checks.append(dict(check_id=check['check_id'], bound_sha=TESTED, exit_code=0,
                           recovered_log_bytes=len(log), log_sha256=ce.digest(log)))
    counts = {}
    for name in ('focused-junit', 'harness-junit-xml', 'unit-junit'):
        ref = 'docs/exec-plans/evidence/HG-051/final-5debfe1/' + name + '.json'
        raw = ce.read(ROOT, ref, HEAD, tested=TESTED, exit_code=0)
        tree = ET.fromstring(raw)
        cases = tree.findall('.//testcase')
        totals = dict(cases=len(cases), failures=len(tree.findall('.//failure')),
                      errors=len(tree.findall('.//error')), skipped=len(tree.findall('.//skipped')))
        assert totals['cases'] > 0 and not any(totals[x] for x in ('failures', 'errors', 'skipped'))
        counts[name] = totals
    harness_execution = json.loads(ce.read(ROOT,
        'docs/exec-plans/evidence/HG-051/final-5debfe1/harness-execution-json.json', HEAD,
        tested=TESTED, exit_code=0))
    assert harness_execution['exit_code'] == 0 and not harness_execution['errors']
    collected = list(harness_execution['collections'].values())
    assert collected and all(value == collected[0] for value in collected)
    calls = [item for item in harness_execution['reports'] if item['phase'] == 'call']
    assert len(calls) == len(collected[0]) == counts['harness-junit-xml']['cases']
    assert all(item['outcome'] == 'passed' for item in calls)
    assert {item['nodeid'] for item in calls} == set(collected[0])
    counts['harness_execution_summary'] = dict(
        workers=len(collected), collected_cases=len(collected[0]), executed_calls=len(calls),
        exit_code=0, failure_or_skip_calls=0,
        observed_execution_sha256=ce.digest(json.dumps(harness_execution, sort_keys=True).encode()))
    budget = ce.audit(ROOT, BASE, HEAD, 'HG-051')
    assert not budget['errors']
    assert (ce.PLAIN_LIMIT, ce.STORED_LIMIT, ce.RAW_LIMIT, ce.TOTAL_LIMIT) == (
        262144, 8388608, 67108864, 16777216)
    report = dict(reviewed_head_sha=HEAD, tested_commit=TESTED, base_commit=BASE,
                  scope_paths=len(changed), post_test_capture_paths=len(after_test),
                  preserved_prior_artifacts=len(prior), frozen_impact='NONE',
                  exact_originals=original_summaries, committed_checks=checks,
                  test_counts=counts, reviewed_revision_budget=budget,
                  actual_kl080_migration=False, product_m3_release='NOT_RUN')
    (Path(__file__).parent / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: committed scope, frozen/prior preservation, indexed hashes, original provenance, ten checks, JUnit, and budgets')


if __name__ == '__main__':
    main()
