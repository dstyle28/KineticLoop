"""Verify exact governance incorporation and execute all portable R4 definition identities."""
import argparse
import ast
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from run_author import identity
E = Path(__file__).resolve().parent
R = E.parents[3]
B = '276bcaebbf3b64b4ea128b175a0463b2f650ac7c'
sys.path.insert(0, str(R))
from tools.harness import validate_harness as v

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=R)

def static(base, tested):
    assert base == B and git('rev-parse', tested).decode().strip() == tested
    rows = json.loads((E/'DELIVERY_PROVENANCE.json').read_bytes())
    for row in rows:
        raw = git('show', tested+':'+row['delivery'])
        assert sha(raw) == row['delivery_sha256']
        if not row['adapted']:
            assert sha(raw) == row['source_sha256'] and len(raw) == row['source_bytes']
    # Exact path-only adaptations; compare entire AST after the declared transformations.
    for name in ('test_definition.py', 'test_r3.py', 'test_reviewer_cases.py'):
        old = (E/'originals'/(name+'.txt')).read_text()
        source = next(r for r in rows if r['delivery'].endswith('/'+name))
        assert sha(old.encode()) == source['source_sha256']
        new = (E/name).read_text()
        if name == 'test_definition.py':
            expected = old.replace("Path('/private/tmp/hg058-host-resource-rule')", "ROOT/'fixtures'/'r1'")
            assert ast.dump(ast.parse(expected)) == ast.dump(ast.parse(new))
        elif name == 'test_r3.py':
            expected = old
            for leaf in ('HOST_LIMITS.json','NATIVE_LIMITS.json'):
                expected = expected.replace("open('/private/tmp/hg058-host-resource-rule-r2/"+leaf+"')", "(ROOT/'fixtures'/'r2'/'"+leaf+"').open()")
            assert ast.dump(ast.parse(expected)) == ast.dump(ast.parse(new))
        else:
            # Original parameter construction and complete decorated test are byte-exact.
            assert old[old.index('assert len(security)'):] == new[new.index('assert len(security)'):]
            old_ast = ast.parse(old)
            new_ast = ast.parse(new)
            assert [ast.dump(x) for x in old_ast.body if isinstance(x,ast.FunctionDef)] == [ast.dump(x) for x in new_ast.body if isinstance(x,ast.FunctionDef) and x.name != 'retained']
    fixtures = json.loads((E/'FIXTURE_BINDINGS.json').read_bytes())
    assert Counter(r['label'] for r in fixtures) == {'security':48,'general':8}
    for row in fixtures:
        raw = (E/row['file']).read_bytes()
        assert sha(raw) == row['sha256']
        value = json.loads(raw)
        assert sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode()) == row['record_semantic_sha256']
        assert value['accepted'] is False and value['input']['format']=='host-preparation-result-draft-v3'
    future = json.loads((E/'FUTURE_CHECKS.json').read_bytes())
    assert len(future['checks'])==14 and all(x['status']=='NOT_RUN' for x in future['checks'])
    assert future['project_native_feasibility']==future['privileged_host_runtime_feasibility']=='NOT_DETERMINED'
    native = json.loads((E/'NATIVE_LIMITS.json').read_bytes())
    assert native == json.loads((E/'fixtures/r2/NATIVE_LIMITS.json').read_bytes())
    native_source=git('show',native['source_revision']+':'+native['source_path'])
    assert sha(native_source)==native['source_sha256']
    assert native['unchanged_definition']==json.loads(native_source)['incorporated_original']
    assert native_source==git('show',tested+':'+native['source_path'])
    clock = json.loads((E/'CLOCK_DERIVATION.json').read_bytes())
    assert sum(x['limit_seconds'] for x in clock['capture_limits_seconds']) == 94800
    assert 94800+64*120+60*11+16*20 == clock['known_conservative_sum_seconds'] == 103460
    assert clock['worker_operation_proposed_seconds']-103460 == 4540
    for binding in clock['source_bindings']:
        raw=git('show',binding['revision']+':'+binding['path'])
        assert len(raw)==binding['bytes'] and sha(raw)==binding['sha256']
    for path in ('tools/harness/compact_evidence.py','tools/harness/local_gate.py','tools/harness/github_app.py','tools/harness/db_ci.py','HARNESS_CHANGE.schema.json','CURRENT_REQUIREMENT_SET.json','FROZEN_BASELINE.json'):
        assert git('show',base+':'+path)==git('show',tested+':'+path)
    for path in ('docs/harness/EVIDENCE_STORAGE_POLICY.md','docs/harness/HARNESS_GOVERNANCE_CONTRACT.md','docs/harness/LOCAL_DB_CI.md','docs/exec-plans/active/HG-058.md'):
        before=git('show',base+':'+path);after=git('show',tested+':'+path)
        assert after.startswith(before) and b'HG067 prospective HOST resource contract' in after[len(before):]
        assert b'only through HG067' in after[len(before):]
    packet=git('show',tested+':docs/exec-plans/active/HG-058.md').decode()
    assert all(x['id']+' → ' in packet for x in future['checks'])
    changed=git('diff','--name-only',base,tested).decode().splitlines()
    assert all(v.matches(p,v.HG067_ALLOWED_PATTERNS) for p in changed)
    assert len(v.HG067_ALLOWED_PATTERNS)==11 and v.governance_allowed_patterns('HG-067')==v.HG067_ALLOWED_PATTERNS
    assert v.HG067_REQUIRED_CHECKS=={'definitions','validator','unit','harness','lint','typecheck','authority','diff'}
    record={'checks_run':[{'check_id':x} for x in v.HG067_REQUIRED_CHECKS],'packets_refined':[]}
    assert not v.host_resource_projection_errors(record,set())
    assert v.host_resource_projection_errors(record,{'KL-081'})
    oldtree=ast.parse(git('show',base+':tools/harness/validate_harness.py').decode())
    newtree=ast.parse((R/'tools/harness/validate_harness.py').read_text())
    for name in ('HG058_ALLOWED_PATTERNS','HG058_AUTHOR_COMMANDS'):
        def assignment(tree):
            return next(ast.dump(x) for x in tree.body if isinstance(x,ast.Assign) and any(isinstance(y,ast.Name) and y.id==name for y in x.targets))
        assert assignment(oldtree)==assignment(newtree)
    # Exact Git-owned inventory, independent of ignored filesystem caches.
    inventory=json.loads((E/'DELIVERY_INVENTORY.json').read_bytes())
    actual=git('ls-tree','-r','--name-only',tested,'--','docs/exec-plans/evidence/HG-067').decode().splitlines()
    assert sorted(actual)==sorted(inventory['paths'])
    for row in inventory['files']:
        raw=git('show',tested+':'+row['path']);assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
    print('static_exact_source_AST_scope_clock_inventory=PASS',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--tested',required=True);args=p.parse_args()
    static(args.base,args.tested)
    out=Path(tempfile.mkdtemp(prefix='hg067-definitions-'))
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=':'.join([str(R),str(R/'src'),str(E),os.environ.get('PYTHONPATH','')]),KINETICLOOP_HARNESS_ROOT=str(E),KINETICLOOP_HARNESS_WORKERS='1')
    env.pop('PYTEST_ADDOPTS',None)
    tests=['test_definition.py','test_r3.py','test_r4.py','test_reviewer_cases.py']
    receipts=[]
    for label,options in [('collection',['--collect-only']),('execution',['--junitxml='+str(out/'junit.xml')])]:
        argv=[sys.executable,'-m','pytest',*tests,'-q','--rootdir='+str(E),'-p','tools.harness.parallel_observer','-p','no:cacheprovider',*options]
        actual=dict(env,KINETICLOOP_HARNESS_OBSERVER=str(out/(label+'.json')))
        start=time.monotonic_ns()
        with (out/(label+'.log')).open('wb') as output:
            proc=subprocess.run(argv,cwd=E,env=actual,stdout=output,stderr=subprocess.STDOUT)
        receipts.append({'argv':argv,'cwd':str(E),'environment':{k:actual[k] for k in ('PYTHONPATH','PYTHONDONTWRITEBYTECODE','KINETICLOOP_HARNESS_ROOT','KINETICLOOP_HARNESS_WORKERS','KINETICLOOP_HARNESS_OBSERVER')},'child_exit':proc.returncode,'elapsed_ns':time.monotonic_ns()-start,'log_sha256':sha((out/(label+'.log')).read_bytes())})
        (out/'EXECUTION.json').write_text(json.dumps(receipts,indent=2)+'\n')
        print('definition_'+label+'_child_exit='+str(proc.returncode),flush=True)
        if proc.returncode:raise SystemExit(proc.returncode)
    positive=identity(out/'execution.json',out/'junit.xml',out/'collection.json')
    expected=json.loads((E/'EXPECTED_IDENTITIES.json').read_bytes())['identities']
    assert positive['identities']==expected and positive['cases']==439 and positive['phases']==1317
    (out/'IDENTITIES.json').write_text(json.dumps(positive,indent=2)+'\n')
    print('definition_observations='+str(out),flush=True)
    print('439 exact portable definition identities and 1317 phases PASS; runtime NOT_RUN',flush=True)
if __name__=='__main__':main()
