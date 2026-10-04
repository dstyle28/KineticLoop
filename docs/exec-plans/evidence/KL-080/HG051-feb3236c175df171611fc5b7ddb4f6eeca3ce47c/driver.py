import concurrent.futures, hashlib, json, os, shlex, subprocess, threading, time
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path.cwd()
head = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
out = Path('/private/tmp/kl080-hg051-final') / head
out.mkdir(parents=True,exist_ok=False)
task = next(t for t in json.loads((root/'KineticLoop_Harness_Backlog_v0.2.json').read_text())['tasks'] if t['id']=='KL-080')
contracts = task['check_contracts']
independent = {'harness_validation_passes','unit_regressions_pass','harness_regressions_pass','lint_passes','typecheck_passes'}
env = {**os.environ,'PATH':'/private/tmp/kl001-bootstrap/bin:'+os.environ['PATH'],
       'UV_CACHE_DIR':'/private/tmp/kl080-uv-cache','UV_OFFLINE':'1'}

def run(c):
    check,command = c['check_id'],c['command']
    args = shlex.split(command); log = out/(check+'.log'); xml = out/(check+'.xml')
    local = dict(env); is_pytest = args[:3]==['uv','run','pytest']
    if is_pytest:
        collect = ['uv','run','pytest','--collect-only','-q',args[-1]]
        p = subprocess.run(collect,env=env,text=True,capture_output=True)
        raw = out/(check+'.collection.log')
        raw.write_text('TESTED_COMMIT='+head+'\nCOMMAND='+shlex.join(collect)+'\n'+p.stdout+p.stderr+'\nEXIT_CODE='+str(p.returncode)+'\n')
        nodes = [l.strip() for l in p.stdout.splitlines() if l.startswith('tests/') and '::' in l]
        assert p.returncode==0 and nodes
        (out/(check+'.collection.json')).write_text(json.dumps({'tested_commit':head,'command':shlex.join(collect),'exit_code':p.returncode,'nodeids':nodes},indent=2)+'\n')
        local['PYTEST_ADDOPTS']='--junitxml='+str(xml)+(' -s' if check=='source_suite_dc' else '')
    elif check=='unit_regressions_pass':
        local['PYTEST_ADDOPTS']='--junitxml='+str(xml)

    stop = threading.Event(); watcher = None
    if check=='harness_regressions_pass':
        temp = out/'harness-work'; temp.mkdir()
        local['TMPDIR']=str(temp)
        # Preserve exact inode contents before the unmodified runner removes its
        # TemporaryDirectory. No flags, test selection or source bytes change.
        targets={'junit.xml':xml,'collection.log':out/'harness.collection.log',
                 'collection.json':out/'harness.collection.json',
                 'execution.json':out/'harness.execution.json',
                 'pytest.log':out/'harness.pytest.log','manifest.json':out/'harness.manifest.json'}
        def retain():
            selected = None
            while not stop.is_set():
                if selected is None:
                    candidates = list(temp.glob('kl-harness-run-*'))
                    if candidates: selected=min(candidates,key=lambda p:p.stat().st_ctime_ns)
                if selected is not None:
                    for name,target in targets.items():
                        if not target.exists():
                            try: os.link(selected/name,target)
                            except FileNotFoundError: pass
                stop.wait(.002)
        watcher=threading.Thread(target=retain); watcher.start()
    try:
        with log.open('w') as stream:
            stream.write('TESTED_COMMIT='+head+'\nCOMMAND='+command+'\n');stream.flush()
            process=subprocess.run(args,env=local,stdout=stream,stderr=subprocess.STDOUT)
            stream.write('\nEXIT_CODE='+str(process.returncode)+'\n')
    finally:
        stop.set()
        if watcher is not None: watcher.join()
    row={'check_id':check,'command':command,'result':'PASS' if process.returncode==0 else 'FAIL',
         'exit_code':process.returncode,'tested_commit':head,'stdout':str(log),
         'sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    if xml.exists():
        tree=ET.parse(xml); cases=tree.findall('.//testcase')
        row['counts']={'executed':len(cases),'failures':len(tree.findall('.//failure')),
                       'errors':len(tree.findall('.//error')),'skipped':len(tree.findall('.//skipped'))}
        assert cases and row['counts']['skipped']==0
        if is_pytest:assert len(cases)==len(nodes)
        if process.returncode==0:assert not row['counts']['failures'] and not row['counts']['errors']
        row['junit']={'path':str(xml),'sha256':hashlib.sha256(xml.read_bytes()).hexdigest()}
    if check in {'harness_regressions_pass','unit_regressions_pass'}:assert xml.exists()
    assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==head
    assert not subprocess.check_output(['git','status','--porcelain']).strip()
    (out/(check+'.execution.json')).write_text(json.dumps(row,indent=2)+'\n')
    print(check,row['result'],row.get('counts',{}),flush=True)
    return row

def serial():
    selected=[next(c for c in contracts if c['check_id']=='source_namespace_pu')]+[c for c in contracts if c['check_id'] not in independent|{'source_namespace_pu'}]
    rows=[]
    for c in selected:
        rows.append(run(c));(out/'checks.json').write_text(json.dumps({'tested_commit':head,'executions':rows},indent=2)+'\n')
    return rows

ordered=[next(c for c in contracts if c['check_id']==k) for k in ['harness_regressions_pass','unit_regressions_pass','harness_validation_passes','lint_passes','typecheck_passes']]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    own=pool.submit(serial); others=[pool.submit(run,c) for c in ordered]
    rows=own.result()+[f.result() for f in others]
assert len(rows)==17
(out/'final-checks.json').write_text(json.dumps({'tested_commit':head,'executions':rows},indent=2)+'\n')
print('ALL_SEVENTEEN_EXECUTED',head,flush=True)
