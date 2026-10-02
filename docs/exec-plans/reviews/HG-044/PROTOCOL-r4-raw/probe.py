"""Generate official pytest formats, then challenge independent Git fixture oracles."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[5]
OUT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('r4_fixture', ROOT/'tests/harness/test_m3_milestone_closure.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
v=m.v
def report_raw(history, name, text):
    return history.raw('r4-'+name,text)
with tempfile.TemporaryDirectory(prefix='hg044-protocol-r4-') as tmp:
    temp=Path(tmp)
    h=m.History(temp/'fixture')
    assert h.errors(h.closure)==[]
    pytest_root=temp/'genuine'
    source=pytest_root/'tests/unit/test_genuine.py'
    source.parent.mkdir(parents=True)
    source.write_text('import pytest\n@pytest.mark.parametrize("n", [1,2,3,4], ids=["nested::id", "1 skipped", "1 error", "1 deselected"])\ndef test_parameter(n):\n    assert n > 0\nclass TestClass:\n    @pytest.mark.parametrize("n", [1], ids=["class::parameter"])\n    def test_class(self,n):\n        assert n == 1\n')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    env.pop('PYTEST_ADDOPTS',None)
    def pytest_run(*args):
        run=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
                            '--rootdir',str(pytest_root),*args,'tests/unit'],
                           cwd=pytest_root,env=env,capture_output=True,text=True)
        assert run.returncode==0,run.stdout+run.stderr
        return run.stdout
    collection_stdout=pytest_run('--collect-only')
    execution_stdout=pytest_run('--junitxml',str(temp/'genuine.xml'))
    junit=(temp/'genuine.xml').read_text()
    nodes=[line for line in collection_stdout.splitlines() if line.startswith('tests/unit/') and '::' in line]
    assert len(nodes)==5
    payload=copy.deepcopy(h.payload)
    run=payload['executions'][0]
    run['stdout']=report_raw(h,'genuine-execution.log',execution_stdout)
    run['junit']=report_raw(h,'genuine-junit.xml',junit)
    collect={'command':'uv run pytest --collect-only -q tests/unit','tested_commit':h.tested,
             'exit_code':0,'nodeids':nodes,'stdout':report_raw(h,'genuine-collection.log',collection_stdout)}
    run['collection']=report_raw(h,'genuine-collection.json',json.dumps(collect))
    rev=h.commit('independent reviewer genuine parameter format fixture')
    errors=v.m3_execution_evidence_errors(h.root,payload,rev,rev,h.records)
    assert errors==[],errors
    outcomes=[{'probe':'official pytest bracket and class parameters','errors':errors,'nodes':nodes}]
    # Genuine collection dispositions must still reject when all hashes bind.
    for disposition in ('1 skipped','1 error','1 deselected'):
        candidate=copy.deepcopy(payload)
        record=copy.deepcopy(collect)
        record['stdout']=report_raw(h,'disposition-'+disposition.replace(' ','-')+'.log',collection_stdout+'\n'+disposition+'\n')
        candidate['executions'][0]['collection']=report_raw(h,'disposition-'+disposition.replace(' ','-')+'.json',json.dumps(record))
        rev=h.commit('independent reviewer genuine disposition negative')
        errors=v.m3_execution_evidence_errors(h.root,candidate,rev,rev,h.records)
        assert errors==['milestone-m3-regression:collection-oracle'],errors
        outcomes.append({'probe':disposition+' summary','errors':errors})
    for value in (False,0.0,1):
        candidate=copy.deepcopy(payload)
        candidate['executions'][0]['exit_code']=value
        errors=v.m3_execution_evidence_errors(h.root,candidate,rev,rev,h.records)
        assert errors==['milestone-m3-regression:failed-or-unbound-command'],errors
        outcomes.append({'probe':'execution exit '+repr(value),'errors':errors})
        candidate=copy.deepcopy(payload)
        record=copy.deepcopy(collect)
        record['exit_code']=value
        candidate['executions'][0]['collection']=report_raw(h,'collection-exit-'+repr(value)+'.json',json.dumps(record))
        rev=h.commit('independent reviewer collection exit negative')
        errors=v.m3_execution_evidence_errors(h.root,candidate,rev,rev,h.records)
        assert errors==['milestone-m3-regression:collection-binding'],errors
        outcomes.append({'probe':'collection exit '+repr(value),'errors':errors})
    for omitted in ('tests/db/test_transaction_interfaces.py','tests/db/test_shadow_isolation.py'):
        candidate=copy.deepcopy(payload)
        command=next(c for c in v.M3_REGRESSION_COMMANDS if omitted in c.split() and len(c.removeprefix('uv run pytest -q ').split())>1)
        run=next(r for r in candidate['executions'] if r['command']==command)
        record=json.loads((h.root/run['collection']['path']).read_text())
        retained=[node for node in record['nodeids'] if not node.startswith(omitted+'::')]
        assert retained
        stem=Path(omitted).stem
        run['stdout']=report_raw(h,stem+'.log',f'{len(retained)} passed in 0.1s\n')
        tree=ET.Element('testsuite')
        for node in retained:
            address,bracket,params=node.partition('[')
            parts=address.split('::')
            ET.SubElement(tree,'testcase',classname='.'.join([parts[0].removesuffix('.py').replace('/','.'),*parts[1:-1]]),name=parts[-1]+bracket+params)
        run['junit']=report_raw(h,stem+'.xml',ET.tostring(tree,encoding='unicode'))
        record['nodeids']=retained
        record['stdout']=report_raw(h,stem+'-collect.log','\n'.join(retained)+f'\n{len(retained)} tests collected in 0.1s\n')
        run['collection']=report_raw(h,stem+'-collect.json',json.dumps(record))
        rev=h.commit('independent reviewer hash-correct omitted selector negative')
        errors=v.m3_execution_evidence_errors(h.root,candidate,rev,rev,h.records)
        assert errors==['milestone-m3-regression:missing-selector'],errors
        outcomes.append({'probe':'omitted '+omitted,'errors':errors})
    # Independent canonical ledger promotions and authority overclaims reject.
    for field,value in [('production_auto_activation',True),('shadow_executable',True),
                        ('product_requirement_pass_claims',['B04@DC']),('r04_e2e_status','PASS')]:
        closure=copy.deepcopy(h.closure)
        closure[field]=value
        assert list(m.SCHEMAS[0].iter_errors(closure))
        outcomes.append({'probe':field,'rejected':True})
    (OUT/'genuine-collection.log').write_text(collection_stdout)
    (OUT/'genuine-execution.log').write_text(execution_stdout)
    (OUT/'genuine-junit.xml').write_text(junit)
    (OUT/'probe.json').write_text(json.dumps({'reviewed_head_sha':'4bc0b0122245d54649e3f3d03a9acce7d4c6df2a',
        'status':'PASS','synthetic_git_fixture_only':True,'outcomes':outcomes},indent=2)+'\n')
    print(json.dumps({'status':'PASS','probes':len(outcomes),'genuine_cases':len(nodes)}))
