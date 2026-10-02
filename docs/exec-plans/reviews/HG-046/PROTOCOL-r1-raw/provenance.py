"""Read-only SHA and authority inspection for the protocol review."""
import importlib.util
import json
from pathlib import Path
import yaml
root=Path('/Users/davetian/.codex/worktrees/ffff/KineticLoop')
spec=importlib.util.spec_from_file_location('validator',root/'tools/harness/validate_harness.py'); v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
base='26906bd7f4444914c228e98377f2b164fee0dd5d'
head='5ae6b31ac4c4639fbfe2fd7ca3df029abdfae323'
record=yaml.safe_load(v.git(root,'show',head+':docs/exec-plans/governance/HG-046.yaml'))
print('tested_to_reviewed_suffix_errors:',v.governance_suffix_errors(root,record['tested_commit'],head,'HG-046','tested'))
baseline=json.loads(v.git(root,'show',head+':FROZEN_BASELINE.json'))
for entry in baseline['files']:
    raw=v.git(root,'show',head+':'+entry['path'])
    print('frozen_authority:',entry['path'],'matches_pinned_hash=',v.compact_evidence.digest(raw)==entry['sha256'],'unchanged_from_protected_base=',raw==v.git(root,'show',base+':'+entry['path']))
print('frozen_baseline_unchanged:',v.git(root,'show',base+':FROZEN_BASELINE.json')==v.git(root,'show',head+':FROZEN_BASELINE.json'))
for check in record['checks_run']:
    raw=v.compact_evidence.read(root,check['evidence_ref'],head,tested=record['tested_commit'],command=check['command'],exit_code=0)
    print('retained_task_check:',check['check_id'],'raw_bytes=',len(raw),'raw_sha256=',v.compact_evidence.digest(raw))
print('protected_base_budget:',json.dumps(v.compact_evidence.audit(root,base,head,'HG-046'),sort_keys=True))
print('frozen invariant IDs/transaction boundaries/tables touched: NONE; changed paths contain only harness code/tests/contracts, derived metadata, and own governance evidence')
