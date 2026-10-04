"""HG052-owned M3 execution/capture glue; unchanged suite selectors and daemon helpers."""
import argparse
import sys
if sys.flags.optimize:
    raise RuntimeError("HG052 guards require Python optimization disabled")
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from build_closure import ROOT, v

spec = importlib.util.spec_from_file_location('hg052_db_ci', ROOT / 'tools/harness/db_ci.py')
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)
COMMANDS = v.M3_REGRESSION_COMMANDS


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2) + '\n')


def inventory():
    return dict(containers=db.output(['docker', 'ps', '-a', '--format', '{{json .}}']).splitlines(),
                volumes=db.output(['docker', 'volume', 'ls', '--format', '{{json .}}']).splitlines())


def clean_legacy(command):
    # Only test_migrations' documented non-yield default lifecycle can remain.
    # Suite-specific yield fixtures must clean themselves; no alias override is used.
    before = inventory()
    if before['containers'] or before['volumes']:
        if 'tests/db/test_migrations.py' not in command.split():
            raise ValueError('unexplained suite resources:'+json.dumps(before))
        from kineticloop.db.lifecycle import DatabaseLifecycle
        lifecycle = DatabaseLifecycle(ROOT)
        project = lifecycle.namespace.project_name
        for line in before['containers']:
            item = json.loads(line)
            inspected = json.loads(db.output(['docker','container','inspect',item['ID']]))[0]
            assert inspected['Config']['Labels'].get('com.docker.compose.project') == project, before
        for line in before['volumes']:
            item = json.loads(line)
            inspected = json.loads(db.output(['docker','volume','inspect',item['Name']]))[0]
            assert inspected['Labels'].get('com.docker.compose.project') == project, before
        lifecycle.destroy()
    after = inventory()
    assert not after['containers'] and not after['volumes'], after
    return dict(before=before, after=after, cleanup='only default legacy lifecycle if present')


def inner(revision, directory):
    directory.mkdir(parents=True, exist_ok=False)
    runs = []; status = 'FAIL'; report = dict(tested_commit=revision, status=status, executions=runs)
    try:
        write(directory/'environment.json', db.environment_preflight('local-isolated', revision))
        assert COMMANDS == json.loads((ROOT/'docs/exec-plans/evidence/HG-052/command-plan.json').read_text())['commands']
        pre = ['uv','run','pytest','-q',
            'tests/unit/protocol/test_execution.py::test_all_fixture_namespaces_fail_before_reset',
            'tests/unit/protocol/test_boundary_acceptance.py::test_boundary_namespace',
            'tests/unit/protocol/test_shadow_isolation.py::test_namespace_and_boundary',
            'tests/unit/protocol/test_test_only_demo.py::test_namespace_and_boundary',
            'tests/unit/protocol/test_interleaving_namespace.py::test_namespace',
            'tests/unit/protocol/test_full_test_execution.py::test_namespace',
            'tests/unit/workflow/test_full_action_preparation.py::test_namespace',
            'tests/unit/workflow/test_deterministic_planning.py::test_namespace',
            'tests/unit/workflow/test_source_decision_conformance.py::test_namespace']
        check=db.run_capture(pre,directory,'namespace-preflight'); write(directory/'namespace-preflight.json',check)
        assert check['exit_code']==0,check
        for i, command in enumerate(COMMANDS,1):
            assert db.resolve_revision('HEAD') == revision
            assert not db.output(['git','status','--porcelain','--untracked-files=all'])
            name=f'{i:02d}'; args=shlex.split(command)
            run=dict(command=command,tested_commit=revision)
            runs.append(run)
            if command != 'uv run kl check-harness':
                selectors = ['tests/unit'] if i==1 else ['tests/harness'] if i==2 else args[4:]
                collect_command='uv run pytest --collect-only -q '+' '.join(selectors)
                collected=db.run_capture(shlex.split(collect_command), directory, name+'-collection')
                raw=(directory/(name+'-collection.log')).read_text()
                nodes=[line for line in raw.splitlines() if re.match(r'^tests/[^\s]+\.py::',line)]
                write(directory/(name+'-collection.json'),dict(command=collect_command,tested_commit=revision,
                    exit_code=collected['exit_code'],nodeids=nodes,stdout=collected['stdout']))
                run['collection_file']=name+'-collection.json'
                assert collected['exit_code']==0 and nodes and len(nodes)==len(set(nodes))
                junit=directory/(name+'.xml')
                args += ['--junitxml='+str(junit)]
                if i==2:
                    args += ['--evidence-dir',str(directory/'harness-run')]
                run['junit_file']=junit.name
            executed=db.run_capture(args,directory,name,timeout=7200)
            run.update(exit_code=executed['exit_code'],actual_argv=args,stdout_file=name+'.log',duration_seconds=executed['duration_seconds'])
            assert executed['exit_code']==0,executed
            if command=='uv run kl check-harness':
                raw=(directory/(name+'.log')).read_text(); assert 'HARNESS_CHECK_PASS' in raw and 'HARNESS_CHECK_FAIL' not in raw
            else:
                run['passed_count']=v.m3_pytest_count((directory/(name+'.log')).read_text())
                counts=db.junit_counts(junit); assert counts['tests']==run['passed_count'],counts
            run['namespace_cleanup']=clean_legacy(command)
            write(directory/'execution-index.json',report)
        status='PASS'
    except BaseException as error:
        report['error']=type(error).__name__+': '+str(error)
        raise
    finally:
        report['status']=status
        try:
            report['final_inventory']=inventory()
        except BaseException as error:
            report['status']='FAIL'
            report['inventory_error']=type(error).__name__
        write(directory/'execution-index.json',report)
    return int(report["status"] != "PASS")


def local(revision, destination):
    db.local_client_preflight()
    assert not os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT')
    context=db.output(['docker','context','show'])
    endpoint=db.output(['docker','context','inspect',context,'--format','{{.Endpoints.docker.Host}}'])
    assert endpoint.startswith('unix:///'), endpoint
    assert db.resolve_revision('HEAD')==revision
    assert not db.output(['git','status','--porcelain','--untracked-files=all'])
    destination=destination.resolve(); assert not destination.exists() and not destination.is_relative_to(ROOT)
    destination.mkdir(parents=True)
    root_hash=hashlib.sha256(str(ROOT.resolve()).encode()).hexdigest()[:12]
    name=f'kineticloop-hg052-{revision[:7]}-{root_hash}-{uuid.uuid4().hex[:12]}'
    assert re.fullmatch(r'kineticloop-hg052-[a-f0-9]{7}-[a-f0-9]{12}-[a-f0-9]{12}',name)
    volume=name+'-data'; image='kineticloop-hg052:'+revision[:12]
    created=False
    envelope=dict(tested_commit=revision,source_tree=db.output(['git','rev-parse',revision+'^{tree}']),
        resolved_root_sha256=hashlib.sha256(str(ROOT.resolve()).encode()).hexdigest(),
        container=name,volume=volume,owner=name,host_endpoint=endpoint,status='FAIL')
    try:
        build=db.run_capture(['docker','build','--tag',image,'tools/harness/local_db'],destination,'image-build',timeout=1200)
        assert build['exit_code']==0,build
        envelope['image']=json.loads(db.output(['docker','image','inspect',image]))[0]['Id']
        assert not db.resource_exists('container',name) and not db.resource_exists('volume',volume)
        created=True
        db.output(['docker','volume','create','--label','kineticloop.owner='+name,volume])
        db.output(['docker','create','--privileged','--name',name,'--mount','type=volume,source='+volume+',target=/var/lib/docker','--label','kineticloop.owner='+name,image])
        db.output(['docker','start',name])
        inspected=json.loads(db.output(['docker','inspect',name]))[0]
        envelope['mounts']=db.owned_mounts(inspected,volume)
        assert inspected['HostConfig']['PidMode'] != 'host'
        assert inspected['HostConfig']['NetworkMode'] != 'host'
        assert not inspected['HostConfig'].get('Binds')
        assert not any(re.match(r'(?i)(GITHUB|GH_|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|DOCKER_HOST|DOCKER_CONTEXT|BUILDX|BUILDKIT)',e) for e in inspected['Config']['Env'])
        for attempt in range(60):
            if subprocess.run(['docker','exec',name,'docker','info'],capture_output=True,timeout=10).returncode==0:
                break
            time.sleep(1)
        else:
            raise ValueError('daemon readiness timeout')
        bundle=destination/'source.bundle'; db.output(['git','bundle','create',str(bundle),'HEAD'])
        envelope['bundle']=db.file_record(bundle)
        db.output(['docker','cp',str(bundle),name+':/source.bundle'])
        db.output(['docker','exec',name,'git','clone','/source.bundle','/workspace/KineticLoop'])
        db.output(['docker','exec','--workdir','/workspace/KineticLoop',name,'git','checkout','--detach',revision])
        prefix=['docker','exec','--workdir','/workspace/KineticLoop',name]
        sync=db.run_capture(prefix+['uv','sync','--locked'],destination,'dependency-sync',timeout=1200)
        assert sync['exit_code']==0,sync
        run=db.run_capture(prefix+['uv','run','python','docs/exec-plans/evidence/HG-052/m3_runner.py','inner','--revision',revision,'--directory','/evidence/run'],destination,'executor',timeout=43200)
        assert run['exit_code']==0,run
        envelope['status']='PASS'
    except BaseException as error:
        envelope['error']=type(error).__name__+': '+str(error)
    finally:
        envelope['diagnostic_errors']=[]
        if created:
            try:
                copied=subprocess.run(['docker','cp',name+':/evidence/run',str(destination/'run')],capture_output=True,timeout=180)
                if copied.returncode:
                    envelope['diagnostic_errors'].append('evidence-copy-exit-'+str(copied.returncode))
            except BaseException as error:
                envelope['diagnostic_errors'].append('evidence-copy:'+type(error).__name__)
            try:
                with (destination/'daemon.log').open('wb') as log:
                    logged=subprocess.run(['docker','logs',name],stdout=log,stderr=subprocess.STDOUT,timeout=120)
                    if logged.returncode:
                        envelope['diagnostic_errors'].append('daemon-log-exit-'+str(logged.returncode))
            except BaseException as error:
                envelope['diagnostic_errors'].append('daemon-log:'+type(error).__name__)
        for kind,key,resource in [('container','container_removed',name),('volume','volume_removed',volume)]:
            try:
                envelope[key]=db.cleanup_owned(kind,resource,name) if created else True
            except BaseException as error:
                envelope[key]=False
                envelope['diagnostic_errors'].append('cleanup-'+kind+':'+type(error).__name__)
        if envelope['diagnostic_errors']:
            envelope['status']='FAIL'
        if not envelope['container_removed'] or not envelope['volume_removed']:
            envelope['status']='FAIL'
        write(destination/'local-executor.json',envelope)
    print(json.dumps(envelope,indent=2),flush=True)
    return int(envelope['status']!='PASS')


def export(revision, directory):
    """Capture raw bytes after immutable execution, retaining failures and ancillary proof."""
    source=directory/'run'; index=json.loads((source/'execution-index.json').read_text())
    outer=json.loads((directory/'local-executor.json').read_text())
    successful=(outer['status']==index['status']=='PASS' and outer['tested_commit']==index['tested_commit']==revision
        and outer['container_removed'] is True and outer['volume_removed'] is True
        and not outer['diagnostic_errors'] and index.get('final_inventory')==dict(containers=[],volumes=[]))
    dest=f'docs/exec-plans/evidence/HG-052/captures-{revision}'
    def capture(path, command, code):
        target=dest+'/'+str(path.relative_to(directory)).replace('/','_')+'.json'
        v.compact_evidence.capture(ROOT,target,path.read_bytes(),revision,command,code)
        return dict(path=target,sha256=hashlib.sha256((ROOT/target).read_bytes()).hexdigest())
    payload=dict(change_id='HG-052',tested_commit=revision,status='PASS' if successful else 'FAIL',commands=COMMANDS,executions=[])
    handled=set()
    payload['provenance']={}
    for key,path in [('outer',directory/'local-executor.json'),('execution_index',source/'execution-index.json'),('environment',source/'environment.json')]:
        if path.exists():
            payload['provenance'][key]=capture(path,'HG052 executor provenance',0 if successful else 1)
            handled.add(path)
    for i,run in enumerate(index['executions'],1):
        command=run['command']; code=run.get('exit_code',125); name=f'{i:02d}'
        item=dict(command=command,tested_commit=revision,exit_code=code)
        for key, field in [('stdout','stdout_file'),('junit','junit_file')]:
            if field in run and (source/run[field]).exists():
                path=source/run[field]; item[key]=capture(path,command,code); handled.add(path)
        if 'collection_file' in run:
            path=source/run['collection_file']; collection=json.loads(path.read_text()); collect_command=collection['command']
            log=source/(name+'-collection.log'); collection['stdout']=capture(log,collect_command,collection['exit_code']); handled.add(log)
            # JSON transformation replaces only the raw-reference path/hash with committed captures.
            modified=directory/(name+'-collection-bound.json'); write(modified,collection)
            item['collection']=capture(modified,collect_command,collection['exit_code']); handled.add(path)
        payload['executions'].append(item)
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path not in handled and path.name!='source.bundle' and not path.name.endswith('-collection-bound.json'):
            capture(path,'HG052 executor provenance',0 if index['status']=='PASS' else 1)
    write(ROOT/f'docs/exec-plans/evidence/HG-052/m3-regression-{revision}.json',payload)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['local','inner','export']); p.add_argument('--revision',required=True); p.add_argument('--directory',type=Path,required=True)
    a=p.parse_args(); assert re.fullmatch(r'[0-9a-f]{40}',a.revision)
    if a.mode=='export': export(a.revision,a.directory)
    else: raise SystemExit((local if a.mode=='local' else inner)(a.revision,a.directory))
