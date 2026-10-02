"""Reproduce valid pytest parameter IDs rejected by the M3 regression oracle."""
import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
from _pytest.junitxml import mangle_test_address

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
SHA = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
spec = importlib.util.spec_from_file_location('security_parameter_validator', ROOT / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT / 'src'))
command = ['/private/tmp/hg044-venv/bin/python', '-m', 'pytest', '--collect-only', '-q',
           '-p', 'no:cacheprovider', 'tests/unit', 'tests/harness']
collected = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
assert type(collected.returncode) is int and collected.returncode == 0
(OUT / 'actual-collection.log').write_bytes(collected.stdout)
nodes = [line for line in collected.stdout.decode().splitlines() if re.match(r'^tests/[^\s]+\.py::', line)]
delimiter_nodes = [node for node in nodes if '[' in node and '::' in node.split('[', 1)[1]]
summary_nodes = [node for node in nodes if re.search(r'\b[1-9][0-9]* (?:deselected|errors?|skipped)\b', node, re.I)]
assert delimiter_nodes and summary_nodes
fixture = Path('/private/tmp/hg044-security-r3-tests/hg0440/repo')
def git(*args):
    return subprocess.check_output(['git', '-c', 'user.name=Security Review Fixture', '-c',
        'user.email=review@example.invalid', '-c', 'commit.gpgsign=false', '-c',
        'core.hooksPath=/dev/null', *args], cwd=fixture).decode().strip()
payload = json.loads(next((fixture / 'docs/exec-plans/evidence/HG-999').glob('m3-regression-*.json')).read_text())
tasks = {t['id']: t for t in json.loads((fixture / v.BACKLOG).read_text())['tasks']}
records = {}
pending = list(v.M3_TASK_IDS | {'KL-074'})
while pending:
    name = pending.pop()
    if name in records:
        continue
    records[name] = json.loads((fixture / f'docs/exec-plans/integrations/{name}.json').read_text())
    pending.extend(tasks[name]['depends_on'])
head = git('rev-parse', 'HEAD')
assert not v.m3_execution_evidence_errors(fixture, payload, head, head, records)
def raw(name, value):
    path = 'docs/exec-plans/evidence/HG-999/security-parameter-' + name
    content = value.encode()
    (fixture / path).write_bytes(content)
    return {'path': path, 'sha256': hashlib.sha256(content).hexdigest()}
reproductions = []
for mode, node in [('delimiter', delimiter_nodes[0]), ('summary-token', summary_nodes[0])]:
    modified = copy.deepcopy(payload)
    run = next(r for r in modified['executions'] if r['command'] == 'uv run kl test-harness')
    run['stdout'] = raw(mode + '.log', '1 passed in 0.1s\n')
    address = mangle_test_address(node)
    tree = ET.Element('testsuite')
    ET.SubElement(tree, 'testcase', classname='.'.join(address[:-1]), name=address[-1])
    run['junit'] = raw(mode + '.xml', ET.tostring(tree, encoding='unicode'))
    collection = {'command': 'uv run pytest --collect-only -q tests/harness',
        'tested_commit': payload['tested_commit'], 'exit_code': 0, 'nodeids': [node],
        'stdout': raw(mode + '-collect.log', node + '\n1 test collected in 0.1s\n')}
    run['collection'] = raw(mode + '-collect.json', json.dumps(collection))
    git('add', '.')
    git('commit', '-qm', 'independent hash-correct valid parameterized evidence fixture')
    head = git('rev-parse', 'HEAD')
    assert not v.governance_suffix_errors(fixture, payload['tested_commit'], head, 'HG-999', 'tested')
    errors = v.m3_execution_evidence_errors(fixture, modified, head, head, records)
    expected = ['milestone-m3-regression:' + ('incomplete-executed-collection' if mode == 'delimiter' else 'collection-oracle')]
    assert errors == expected, errors
    reproductions.append({'mode': mode, 'fixture_evaluated_sha': head, 'tested_sha': payload['tested_commit'],
        'nodeid': node, 'real_pytest_junit_address': address, 'actual_errors': errors,
        'all_other_runs_positive': True, 'freshness_hash_regular_collection_junit_bindings_valid': True})
report = {'reviewed_head_sha': SHA, 'command': command, 'exit_code': collected.returncode,
    'actual_collection_ref': str((OUT / 'actual-collection.log').relative_to(ROOT)),
    'actual_collection_sha256': hashlib.sha256(collected.stdout).hexdigest(),
    'collection_node_count': len(nodes), 'parameter_delimiter_node_count': len(delimiter_nodes),
    'parameter_summary_token_node_count': len(summary_nodes), 'reproductions': reproductions}
(OUT / 'parameter-probe.json').write_text(json.dumps(report, indent=2) + '\n')
print('REPRODUCED_PARAMETER_FALSE_REJECTIONS', len(nodes), len(delimiter_nodes), len(summary_nodes))
