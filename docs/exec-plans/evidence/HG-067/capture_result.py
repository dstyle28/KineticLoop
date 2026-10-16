"""Capture fresh author outputs once; build truthful own result at R."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import yaml
E = Path(__file__).resolve().parent
R = E.parents[3]
sys.path.insert(0, str(R))
from tools.harness import compact_evidence as native
B = '276bcaebbf3b64b4ea128b175a0463b2f650ac7c'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tested', required=True)
    args = parser.parse_args()
    T = args.tested
    out = Path('/private/tmp/hg067-author-' + T[:12])
    author = json.loads((out / 'AUTHOR_RESULT.json').read_bytes())
    assert author['tested'] == T and author['base'] == B
    dest = E / ('checks-' + T[:12])
    dest.mkdir(exist_ok=False)
    captured = []
    def capture(path, label, command, code=0):
        target = str((dest / (label + '.json')).relative_to(R))
        raw = path.read_bytes()
        native.capture(R, target, raw, T, command, code)
        captured.append({'source': str(path), 'evidence_ref': target, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        return target
    checks = []
    for row in author['checks']:
        assert row['exit_code'] == 0
        name, command = row['check_id'], row['command']
        checks.append({'check_id': name, 'command': command, 'result': 'PASS', 'evidence_ref': capture(out / (name + '.log'), name, command)})
    assert json.loads((out/'AUTHOR_WRAPPER.json').read_bytes())['observed_exit_code'] == 0
    for name in ('COMMANDS.json','IDENTITIES.json','AUTHOR_RESULT.json','AUTHOR_WRAPPER.json'):
        capture(out/name, name.removesuffix('.json'), 'HG067 fresh author capture at ' + T)
    for name in ('validator','unit'):
        command = next(c['command'] for c in checks if c['check_id'] == name)
        for suffix in ('-collection.json','-execution.json','.junit.xml','-collection.log'):
            capture(out/(name+suffix),name+suffix.replace('.','-'),command)
    for path in sorted((out/'harness-run').iterdir()):
        if path.is_file(): capture(path,'harness-'+path.name.replace('.','-'),next(c['command'] for c in checks if c['check_id']=='harness'))
    lines=(out/'definitions.log').read_text().splitlines()
    scratch=Path(next(s.split('=',1)[1] for s in lines if s.startswith('definition_observations=')))
    command=checks[0]['command']
    # Fresh complete collection/start/phase/JUnit, all five bounded command receipts.
    # Reserved inventory and original blob bodies remain external; stored hashes and
    # exact semantic fixture comparisons bind them without nested storage metadata.
    for path in sorted(scratch.rglob('*')):
        if not path.is_file() or 'inputs' in path.parts:continue
        if path.name in ('CURRENT_GROUP_OBSERVATION.json','PROVENANCE_OBSERVATION.json'):
            continue
        # Preserve safe outputs only after unchanged native classification, never swallow a failure.
        if path.suffix in ('.json','.xml','.log'):
            raw=path.read_bytes()
            assert native.envelope(raw) is None
            capture(path,'definitions-'+str(path.relative_to(scratch)).replace('/','-').replace('.','-'),command)
    index={'base_commit':B,'tested_commit':T,'checks':checks,'capture_manifest':captured,'definition_identities':{'portable_r4':439,'phases':1317},'limitations':['Actual K/H native inventory NOT_RUN; all22 budget feasibility NOT_DETERMINED.','Historical execution UNVERIFIED; acceptance_eligible=false; execution_reuse=false.','Installed/private/admission/App/DB/cleanup/hosted/merge NOT_RUN.'],'failed_attempts':'External preparation attempts preserved; no failed storage bytes committed.'}
    (dest/'CHECK_INDEX.json').write_text(json.dumps(index,indent=2)+'\n')
    path=R/'docs/exec-plans/governance/HG-067.yaml'
    changed=subprocess.check_output(['git','diff','--name-only',B,'HEAD'],cwd=R,text=True).splitlines()
    additions=[str(p.relative_to(R)) for p in dest.iterdir() if p.is_file()]
    record={'change_identity':'harness-governance-v0.1/HG-067','display_change_id':'HG-067','base_commit':B,'tested_commit':T,'change_status':'PASS','summary':'Prospectively incorporate exact reviewed R4 finite HOST resource and source-observation definitions; refine HG058 future acceptance obligations without changing its existing scopes, eight K checks, twenty author checks or nineteen root gates. Enforce literal HG067 scope/eight checks/no product projection and GENERAL plus SECURITY review. Fresh 439 portable definition identities/1317 phases and eight author checks pass; all14 actual HOST duties remain NOT_RUN. No runtime, installed or product PASS','packets_refined':[],'files_changed':sorted(set(changed+additions+[str(path.relative_to(R))])),'checks_run':checks,'frozen_impact':'NONE','authority_entries_added':[],'known_limitations':index['limitations']+['Both NEW independent reviews pending at clean R; no publication authorization.','T-to-R only own result and ADDED own evidence; manifest frozen before T.','HG058 remains clean K9eb6 with P unimported until actual normal HG067 merge, complete installed readiness and explicit root regrant.']}
    path.write_text(yaml.safe_dump(record,sort_keys=False,width=100))
    print(json.dumps({'result':str(path),'captures':len(captured),'checks':len(checks)}))

if __name__=='__main__':
    main()
