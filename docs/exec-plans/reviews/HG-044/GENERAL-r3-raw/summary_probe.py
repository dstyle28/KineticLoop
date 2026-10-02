import copy
import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from _pytest.junitxml import mangle_test_address
ROOT=Path('/Users/davetian/.codex/worktrees/8578/KineticLoop')
OUT=ROOT/'docs/exec-plans/reviews/HG-044/GENERAL-r3-raw'
previous=json.loads((OUT/'parameter_probe.json').read_text())
spec=importlib.util.spec_from_file_location('summary_fixture',ROOT/'tests/harness/test_m3_milestone_closure.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
v=t.v
history=t.History.__new__(t.History)
history.root=Path(previous['fixture_root'])
history.prefix='docs/exec-plans/evidence/HG-999/'
for key,ref in previous['raw_refs'].items():
    (OUT/('parameter-case-'+key+Path(ref['path']).suffix)).write_bytes((history.root/ref['path']).read_bytes())
payload=json.loads((history.root/history.prefix/('m3-regression-'+previous['tested_commit'][:7]+'.json')).read_text())
records={n:json.loads((history.root/f'docs/exec-plans/integrations/{n}.json').read_text()) for n in v.M3_TASK_IDS}
assert not v.m3_execution_evidence_errors(history.root,payload,previous['evidence_revision'],previous['evidence_revision'],records)
run=next(r for r in payload['executions'] if r['command']=='uv run kl test-harness')
node='tests/harness/test_parameters.py::test_case[1 skipped]'
proper=mangle_test_address(node)
run['stdout']=history.raw('summary-param-case.log','1 passed in 0.1s\n')
tree=ET.Element('testsuite');ET.SubElement(tree,'testcase',classname='.'.join(proper[:-1]),name=proper[-1])
run['junit']=history.raw('summary-param-case.xml',ET.tostring(tree,encoding='unicode'))
collection={'command':'uv run pytest --collect-only -q tests/harness','tested_commit':previous['tested_commit'],'exit_code':0,'nodeids':[node],'stdout':history.raw('summary-param-collect.log',node+'\n1 test collected in 0.1s\n')}
run['collection']=history.raw('summary-param-collect.json',json.dumps(collection))
revision=history.commit('independent successful parameter-id containing summary words')
errors=v.m3_execution_evidence_errors(history.root,payload,revision,revision,records)
assert errors==['milestone-m3-regression:collection-oracle'],errors
for key,ref in {**{k:run[k] for k in ('stdout','junit','collection')},'collection_stdout':collection['stdout']}.items():
    (OUT/('summary-case-'+key+Path(ref['path']).suffix)).write_bytes((history.root/ref['path']).read_bytes())
output={'reviewed_head_sha':previous['reviewed_head_sha'],'positive_baseline_errors':[],'valid_junit_and_collection_errors':errors,'nodeid':node,'all_selectors_and_freshness_pass':True,'evidence_revision':revision}
(OUT/'summary_probe.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output))
