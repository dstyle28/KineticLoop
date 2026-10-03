from pathlib import Path
import importlib.util, json, subprocess
ROOT=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
W=Path('/private/tmp/hg051-r2-security-20261003')
spec=importlib.util.spec_from_file_location('r2_originals',W/'gate/tools/harness/compact_evidence.py'); ce=importlib.util.module_from_spec(spec); spec.loader.exec_module(ce)
records=[]
for original in ce.historical_originals():
    ref=original['execution_record']; raw=ce.blob(ROOT,ref['path'],ref['revision'],ce.PLAIN_LIMIT)
    assert len(raw)==ref['bytes'] and ce.digest(raw)==ref['sha256']
    report=json.loads(raw)
    if 'executions' in report: report=next(x for x in report['executions'] if x['evidence_ref']==original['path'])
    for key in ('tested_commit','command','exit_code','result'): assert report[key]==original['execution'][key]
    evidence=report if report['evidence_ref']==original['path'] else report['junit']
    assert evidence.get('path',evidence.get('evidence_ref'))==original['path'] and evidence['sha256']==original['raw_sha256']
    records.append(dict(path=ref['path'],revision=ref['revision'],sha256=ce.digest(raw),original_path=original['path'],recorded_result=report['result'],recorded_exit=report['exit_code']))
for ref in ce.historical_template()['preserved_records']:
    raw=ce.blob(ROOT,ref['path'],ref['revision'],ce.PLAIN_LIMIT)
    assert len(raw)==ref['bytes'] and ce.digest(raw)==ref['sha256']
    records.append(dict(path=ref['path'],revision=ref['revision'],sha256=ce.digest(raw),snapshot_intact=True))
print(json.dumps(dict(status='PASS',records=records,purpose='Exact original ordinary record integrity and immutable metadata consistency, not fresh historical execution certification'),indent=2))
