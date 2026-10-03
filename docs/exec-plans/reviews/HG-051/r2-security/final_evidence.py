from pathlib import Path
import importlib.util, sys, json, subprocess, yaml, xml.etree.ElementTree as ET
ROOT=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
W=Path('/private/tmp/hg051-r2-security-20261003')
SOURCE='0557dbd8f2196df871af20c0982bdc2526f0ad6e'; BASE='b877db0edd2e4550d6ea81750656112fb7f2e223'
final=sys.argv[1]
spec=importlib.util.spec_from_file_location('r2_final_decoder',W/'gate/tools/harness/compact_evidence.py'); ce=importlib.util.module_from_spec(spec); spec.loader.exec_module(ce)
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT)
assert git('rev-parse',final).decode().strip()==final
changed=git('diff','--name-only',SOURCE,final).decode().splitlines()
assert all(p.startswith('docs/exec-plans/evidence/HG-051/') or p=='docs/exec-plans/governance/HG-051.yaml' for p in changed),changed
for p in ('tools/harness/compact_evidence.py','tools/harness/validate_harness.py','HISTORICAL_EVIDENCE_MAPPING.schema.json'):
 assert git('show',SOURCE+':'+p)==git('show',final+':'+p)
gov=yaml.safe_load(git('show',final+':docs/exec-plans/governance/HG-051.yaml'))
assert gov['tested_commit']==SOURCE and gov['change_status']=='PASS'
checks=[]
for check in gov['checks_run']:
 assert check['result']=='PASS',check
 raw=ce.read(ROOT,check['evidence_ref'],final,tested=SOURCE,command=check['command'],exit_code=0)
 checks.append(dict(check_id=check['check_id'],command=check['command'],ref=check['evidence_ref'],raw_sha256=ce.digest(raw),raw_bytes=len(raw),envelope_bindings_valid=True,stdout_tail=raw[-240:].decode(errors='replace')))
assert {'focused','harness','unit','authority','lint','typecheck','scope_frozen_prerequisites','inventory_roundtrip','diff','budget'}<=set(x['check_id'] for x in checks)
audit=ce.audit(ROOT,BASE,final,'HG-051'); assert not audit['errors'],audit
failed='docs/exec-plans/evidence/HG-051/installed-schema/failed-bf7bd40/EXECUTION.json'
assert git('show',SOURCE+':'+failed)==git('show',final+':'+failed)
report=dict(status='PASS',reviewed_sha=final,source_tested_sha=SOURCE,base_sha=BASE,changed_since_tested=changed,checks=checks,reviewed_budget=audit,retained_failed_attempts=True,note='Only ordinary execution envelopes and recovered stdout supplied fresh check evidence; schema/archive metadata were not used as execution proof. App/fullDB gate remains parent-owned and prospective.')
print(json.dumps(report,indent=2))
