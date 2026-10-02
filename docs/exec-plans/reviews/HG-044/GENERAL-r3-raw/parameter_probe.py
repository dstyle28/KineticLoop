import copy
import hashlib
import importlib.util
import inspect
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from _pytest.junitxml import mangle_test_address
ROOT=Path('/Users/davetian/.codex/worktrees/8578/KineticLoop')
OUT=ROOT/'docs/exec-plans/reviews/HG-044/GENERAL-r3-raw'
spec=importlib.util.spec_from_file_location('parameter_fixture',ROOT/'tests/harness/test_m3_milestone_closure.py')
t=importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
v=t.v
nodes=[line for line in Path('/private/tmp/hg044-actual-collection.txt').read_text().splitlines() if line.startswith('tests/') and '.py::' in line]
mismatches=[]
for node in nodes:
    p=node.split('::')
    current=('.'.join([p[0].removesuffix('.py').replace('/','.'),*p[1:-1]]),p[-1])
    actual=mangle_test_address(node)
    expected=('.'.join(actual[:-1]),actual[-1])
    if current != expected:
        mismatches.append(dict(nodeid_sha256=hashlib.sha256(node.encode()).hexdigest(),nodeid_length=len(node),address_prefix=node.partition('[')[0],expected_name_prefix=expected[1][:100],validator_name_prefix=current[1][:100]))
assert len(mismatches)==25
history=t.History(Path(tempfile.mkdtemp(prefix='hg044-general-r3-param-',dir='/private/tmp'))/'repo')
assert not v.m3_execution_evidence_errors(history.root,history.payload,history.evaluated,history.evaluated,history.records)
payload=copy.deepcopy(history.payload)
run=next(r for r in payload['executions'] if r['command']=='uv run kl test-harness')
node=next(n for n in nodes if n.startswith('tests/harness/') and '[' in n and '::' in n.partition('[')[2])
proper=mangle_test_address(node)
run['stdout']=history.raw('real-param-case.log','1 passed in 0.1s\n')
tree=ET.Element('testsuite')
ET.SubElement(tree,'testcase',classname='.'.join(proper[:-1]),name=proper[-1])
run['junit']=history.raw('real-param-case.xml',ET.tostring(tree,encoding='unicode'))
collection={'command':'uv run pytest --collect-only -q tests/harness','tested_commit':history.tested,'exit_code':0,'nodeids':[node],'stdout':history.raw('real-param-case-collect.log',node+'\n1 test collected in 0.1s\n')}
run['collection']=history.raw('real-param-case-collect.json',json.dumps(collection))
revision=history.commit('independent valid actual parameter-id JUnit reproduction')
errors=v.m3_execution_evidence_errors(history.root,payload,revision,revision,history.records)
assert errors==['milestone-m3-regression:incomplete-executed-collection'],errors
output={'reviewed_head_sha':'19dc5a4f8edc8869873a76a4fe27b0280761d7c9','protected_base_sha':'fa729ca4bcca0f2c2e7a2aa0601890d1356b8842','collected_nodes':len(nodes),'mismatch_count':len(mismatches),'mismatches':mismatches,'pytest_mangle_source':inspect.getsource(mangle_test_address),'positive_baseline_errors':[],'valid_junit_errors':errors,'tested_commit':history.tested,'evidence_revision':revision,'fixture_root':str(history.root),'raw_refs':{k:run[k] for k in ('stdout','junit','collection')},'all_selectors_and_freshness_pass':True}
(OUT/'parameter_probe.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({'mismatch_count':len(mismatches),'collected_nodes':len(nodes),'positive_baseline_errors':[],'valid_junit_errors':errors,'reviewed_head_sha':output['reviewed_head_sha']}))
