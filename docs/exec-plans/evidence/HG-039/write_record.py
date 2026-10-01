"""Bind exact HG039 final scope and PASS evidence before independent review."""
import json
import subprocess
import sys
from pathlib import Path
import yaml

root=Path.cwd();here=root/'docs/exec-plans/evidence/HG-039'
base=(here/'protected-base.txt').read_text().strip()
tested=sys.argv[1]
checks=[]
for key in ['scope_audit','identity_scope_regressions','harness_validation','harness_tests','unit_tests','lint','typecheck','diff_clean']:
 record=json.loads((here/f'{key}-{tested[:7]}.json').read_text())
 assert record['result']=='PASS' and record['tested_commit']==tested
 checks.append({k:record[k] for k in ['check_id','command','result','evidence_ref']})
path='docs/exec-plans/governance/HG-039.yaml'
files=subprocess.check_output(['git','diff','--name-only',base],text=True).splitlines()
files+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
record={'change_identity':'harness-governance-v0.1/HG-039','display_change_id':'HG-039',
 'base_commit':base,'tested_commit':tested,'change_status':'PASS',
 'summary':'Refine unresulted KL026 I03 to a strict immutable independent TEST-local cancellation request with separately trusted PlanningIdentity(TEST), exact persisted TEST subject/policy/environment/principal and canonical server-computed hash. Preserve public wire rejection/39-command registry, existing restricted CancelIntent owner, lock order, separate RESERVED cleanup, both race oracles and all product/layer statuses. Add named PU identity selector, exact packet/backlog/traceability projection and bounded governance feasibility/negative checks; no production, frozen or foreign lifecycle change.',
 'packets_refined':['KL-026'],'files_changed':sorted(set(files+[path])),
 'checks_run':checks,'frozen_impact':'NONE','authority_entries_added':[],
 'known_limitations':[
 'KL075 has first merge priority and must actually normally merge before this final tested base, independent review and normal exact-head PR merge.',
 'HG039 runs governance and pure request-feasibility checks only; no KL026 implementation, I03@DC or release/product PASS is claimed. All existing nine DC oracles remain unchanged; named cancellation_identity_pu and additional I03 negative/replay/success cases must execute in the KL026 implementation.',
 'The proposal is immutable TEST-local data/predicates only, with no DB owner or lifecycle; implementation belongs in existing exact KL026 test files. No public ingress/authentication, authorization meaning, production validator, owner permission, migration, CI or frozen file changes.',
 'Canonical hash is computed from the strict request by the trusted recipe. Caller actor, authorization grant/hash, SUBJECT relabeling, public subclass or model_construct cannot authorize cancellation.',
 'Root cancellation and actual CancelUndispatched remain separate transactions. Terminal-with-RESERVED keeps occupation safely until exact cleanup; DISPATCH_INTENT never refunds/resends. Historical replay and terminal success remain immutable non-executable facts.',
 'Fresh independent GENERAL/PROTOCOL/DB_CONCURRENCY review binds final governance/evidence SHA. Only HG039 review-record paths may follow; all normal hosted checks and merge gate must PASS.'
 ]}
(root/path).write_text(yaml.safe_dump(record,sort_keys=False,width=98))
print(path,'tested='+tested,'declared='+str(len(record['files_changed'])))
