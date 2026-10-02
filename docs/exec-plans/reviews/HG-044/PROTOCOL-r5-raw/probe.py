"""Independent genuine pytest-format probe; isolate provenance from format oracles."""
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path.cwd(); OUT=ROOT/'docs/exec-plans/reviews/HG-044/PROTOCOL-r5-raw'
spec=importlib.util.spec_from_file_location('probe_validator',ROOT/'tools/harness/validate_harness.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
tested='7206b60aa4f930caf1bac62db0f397978ea0ec34'; change='HG-998'; prefix='docs/exec-plans/evidence/HG-998/'
files={}
def raw(stem,data):
    if isinstance(data,str):data=data.encode()
    path=prefix+stem;files[path]=data
    return {'path':path,'sha256':hashlib.sha256(data).hexdigest()}
def evidence(root,item,evaluated):
    data=files[item['path']]
    assert hashlib.sha256(data).hexdigest()==item['sha256']
    return data
v.resolve=lambda root,revision:revision
v.is_ancestor=lambda *args:True
v.governance_suffix_errors=lambda *args:[]
v.m3_evidence_bytes=evidence
records={n:{'merge_commit':tested} for n in v.M3_TASK_IDS}
payload={'change_id':change,'tested_commit':tested,'status':'PASS','commands':v.M3_REGRESSION_COMMANDS,'executions':[]}
def formats(stem,nodeids,selectors):
    tree=ET.Element('testsuite')
    for node in nodeids:
        address,bracket,param=node.partition('[');parts=address.split('::')
        ET.SubElement(tree,'testcase',classname='.'.join([parts[0].removesuffix('.py').replace('/','.'),*parts[1:-1]]),name=parts[-1]+bracket+param)
    return {'stdout':raw(stem+'.log',f'{len(nodeids)} passed in 0.01s\n'),
            'junit':raw(stem+'.xml',ET.tostring(tree)),
            'collection':raw(stem+'.json',json.dumps({'command':'uv run pytest --collect-only -q '+' '.join(selectors),'tested_commit':tested,'exit_code':0,'nodeids':nodeids,'stdout':raw(stem+'-collect.log','\n'.join(nodeids)+f'\n{len(nodeids)} tests collected in 0.01s\n')}))}
for i,command in enumerate(v.M3_REGRESSION_COMMANDS):
    run={'command':command,'tested_commit':tested,'exit_code':0}
    if command=='uv run kl check-harness':
        run['stdout']=raw(str(i)+'.log','HARNESS_CHECK_PASS tasks=76 active=73\n')
    else:
        selectors=['tests/unit'] if command=='uv run kl test-unit' else ['tests/harness'] if command=='uv run kl test-harness' else command.removeprefix('uv run pytest -q ').split()
        nodes=[s+'/sample.py::test_ok' if not '.py' in s else s if '::' in s else s+'::test_ok' for s in selectors]
        run.update(formats(str(i),nodes,selectors))
    payload['executions'].append(run)
def errors(data):return v.m3_execution_evidence_errors(ROOT,data,tested,tested,records)
assert errors(payload)==[]
reports=[]
case=OUT/'probe-case'; source=case/'tests/unit/test_parameter.py';source.parent.mkdir(parents=True,exist_ok=True)
source.write_text('import pytest\n@pytest.mark.parametrize("value", [1, 2, 3, 4], ids=["nested::id", "1 skipped", "1 error", "1 deselected"])\ndef test_parameter(value):\n    assert value > 0\n')
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1');env.pop('PYTEST_ADDOPTS',None)
def run(label,*args):
    command=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','--rootdir',str(case),'--confcutdir',str(case),*args,'tests/unit']
    process=subprocess.run(command,cwd=case,env=env,capture_output=True)
    (OUT/(label+'.stdout.log')).write_bytes(process.stdout)
    (OUT/(label+'.stderr.log')).write_bytes(process.stderr)
    assert process.returncode==0
    reports.append({'command':command,'exit_code':process.returncode,'stdout_sha256':hashlib.sha256(process.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(process.stderr).hexdigest()})
    return process.stdout
collection=run('genuine-collection','--collect-only')
execution=run('genuine-execution','--junitxml',str(OUT/'genuine-junit.xml'))
nodes=[line for line in collection.decode().splitlines() if line.startswith('tests/unit/') and '::' in line]
assert len(nodes)==4
genuine=copy.deepcopy(payload)
genuine['executions'][0].update(stdout=raw('genuine.log',execution),junit=raw('genuine.xml',(OUT/'genuine-junit.xml').read_bytes()),collection=raw('genuine.json',json.dumps({'command':'uv run pytest --collect-only -q tests/unit','tested_commit':tested,'exit_code':0,'nodeids':nodes,'stdout':raw('genuine-collect.log',collection)})))
assert errors(genuine)==[]
outcomes={'genuine_parameter_names':nodes,'genuine_validation':errors(genuine)}
for value in (False,0.0):
    negative=copy.deepcopy(genuine);negative['executions'][0]['exit_code']=value
    issues=errors(negative);assert issues==['milestone-m3-regression:failed-or-unbound-command']
    outcomes['execution_exit_'+repr(value)]=issues
    negative=copy.deepcopy(genuine)
    collection_data=json.loads(files[negative['executions'][0]['collection']['path']]);collection_data['exit_code']=value
    negative['executions'][0]['collection']=raw('negative-'+repr(value)+'.json',json.dumps(collection_data))
    issues=errors(negative);assert issues==['milestone-m3-regression:collection-binding']
    outcomes['collection_exit_'+repr(value)]=issues
negative=copy.deepcopy(genuine)
collection_data=json.loads(files[negative['executions'][0]['collection']['path']]);collection_data['stdout']=raw('negative-skip.log',collection+b'1 skipped\n')
negative['executions'][0]['collection']=raw('negative-skip.json',json.dumps(collection_data))
issues=errors(negative);assert issues==['milestone-m3-regression:collection-oracle'];outcomes['real_skip_disposition']=issues
for omitted in ('tests/db/test_transaction_interfaces.py','tests/db/test_shadow_isolation.py'):
    negative=copy.deepcopy(payload)
    target=next(r for r in negative['executions'] if omitted in r['command'].split() and len(r['command'].removeprefix('uv run pytest -q ').split())>1)
    selectors=target['command'].removeprefix('uv run pytest -q ').split()
    kept=[s+'::test_ok' for s in selectors if s!=omitted]
    target.update(formats('omitted-'+Path(omitted).stem,kept,selectors))
    issues=errors(negative);assert issues==['milestone-m3-regression:missing-selector'];outcomes['omitted_'+omitted]=issues
(OUT/'probe.json').write_text(json.dumps({'reviewed_head_sha':'027bc2368e36e28aa9956489cb57af297882d671','scope':'Pure format/content oracle probe. Git/provenance functions are isolated here and independently audited against actual history in audit.json. Synthetic baseline is validator input only.','commands':reports,'outcomes':outcomes,'status':'PASS'},indent=2)+'\n')
print('PROBE_PASS genuine 4-case pytest parameter collection/JUnit; integer exits; actual skip; two omitted selector suites')
