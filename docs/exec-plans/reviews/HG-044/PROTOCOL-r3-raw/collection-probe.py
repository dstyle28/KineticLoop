"""Independent valid-pytest-name oracle probes; provenance is outside this pure probe."""
import hashlib
import importlib.util
import inspect
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from _pytest.junitxml import mangle_test_address

root = Path(__file__).resolve().parents[5]
out = Path(__file__).parent
reviewed = '19dc5a4f8edc8869873a76a4fe27b0280761d7c9'
spec = importlib.util.spec_from_file_location('collection_probe', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
assert v.resolve(root, 'HEAD') == reviewed
actual_path = Path('/private/tmp/hg044-actual-collection.txt')
raw_actual = actual_path.read_bytes()
nodes = [line for line in raw_actual.decode().splitlines() if re.match(r'^tests/[^\s]+\.py::', line)]
embedded = [n for n in nodes if '[' in n and '::' in n.partition('[')[2]]
summarylike = [n for n in nodes if re.search(r'\b[1-9][0-9]* (?:deselected|errors?|skipped)\b', n, re.I)]
assert len(embedded) == 25 and len(summarylike) == 3
results = []
for node in ('tests/harness/test_probe.py::test_valid[plain]',
             'tests/harness/test_probe.py::test_valid[selector::case]',
             'tests/harness/test_m3_milestone_closure.py::test_zero_skip_xfail_failure_cannot_supply_oracle[1 skipped]'):
    stdout = b'1 passed in 0.1s\n'
    names = mangle_test_address(node)
    tree = ET.Element('testsuite')
    ET.SubElement(tree, 'testcase', classname='.'.join(names[:-1]), name=names[-1])
    collect_raw = (node + '\n1 test collected in 0.1s\n').encode()
    collection = {'command': 'uv run pytest --collect-only -q tests/harness',
                  'tested_commit': reviewed, 'exit_code': 0, 'nodeids': [node],
                  'stdout': {'path': 'docs/exec-plans/evidence/HG-999/collection.log'}}
    blobs = {'stdout.log': stdout, 'junit.xml': ET.tostring(tree),
             'collection.json': json.dumps(collection).encode(), 'collection.log': collect_raw}
    prefix = 'docs/exec-plans/evidence/HG-999/'
    collection['stdout']['sha256'] = hashlib.sha256(collect_raw).hexdigest()
    blobs['collection.json'] = json.dumps(collection).encode()
    def ref(name):
        return {'path': prefix + name, 'sha256': hashlib.sha256(blobs[name]).hexdigest()}
    run = {'command': 'uv run kl test-harness', 'tested_commit': reviewed, 'exit_code': 0,
           'stdout': ref('stdout.log'), 'junit': ref('junit.xml'), 'collection': ref('collection.json')}
    payload = {'change_id': 'HG-999', 'tested_commit': reviewed, 'status': 'PASS',
               'commands': ['uv run kl test-harness'], 'executions': [run]}
    # Isolate collection/JUnit content handling from the separately audited Git gates.
    v.M3_REGRESSION_COMMANDS = ['uv run kl test-harness']
    v.governance_suffix_errors = lambda *args: []
    v.m3_evidence_bytes = lambda _root, evidence, _evaluated: blobs[Path(evidence['path']).name]
    records = {task: {'merge_commit': reviewed} for task in v.M3_TASK_IDS}
    errors = v.m3_execution_evidence_errors(root, payload, reviewed, reviewed, records)
    expected = [] if node.endswith('[plain]') else [
        'milestone-m3-regression:incomplete-executed-collection' if 'selector::case' in node
        else 'milestone-m3-regression:collection-oracle']
    assert errors == expected, errors
    results.append({'node': node, 'official_pytest_junit': {'classname': '.'.join(names[:-1]),
                    'name': names[-1]}, 'validator_errors': errors})
report = {'reviewed_head_sha': reviewed, 'probe_exit_code': 0, 'status': 'BLOCKER_CONFIRMED',
          'synthetic_oracle_only': True, 'actual_collection_sha256': hashlib.sha256(raw_actual).hexdigest(),
          'actual_node_count': len(nodes), 'embedded_parameter_delimiter_count': len(embedded),
          'disposition_text_parameter_count': len(summarylike),
          'affected_test_prefixes': sorted({n.partition('[')[0] for n in embedded}),
          'disposition_text_nodes': summarylike,
          'official_pytest_mangle_source': inspect.getsource(mangle_test_address), 'results': results}
(out / 'collection-probe.json').write_text(json.dumps(report, indent=2) + '\n')
print('BLOCKER_CONFIRMED: 25 valid parameter delimiter IDs and 3 disposition-text IDs; compact pure reproductions agree')
