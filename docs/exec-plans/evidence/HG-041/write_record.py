"""Append governance PASS record only after all exact-tested checks pass."""
import json
import subprocess
from pathlib import Path

import yaml

root=Path.cwd(); here=root/'docs/exec-plans/evidence/HG-041'; base=(here/'protected-base.txt').read_text().strip(); tested=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
keys=['scope_audit','candidate_feasibility','action_scope_regressions','legacy_unit_regression','harness_validation','harness_tests','unit_tests','lint','typecheck','diff_clean']
checks=[]
for key in keys:
 data=json.loads((here/f'{key}-{tested[:7]}.json').read_text()); assert data['tested_commit']==tested and data['result']=='PASS' and data['exit_code']==0
 raw=json.loads((root/data['evidence_ref']).read_text()); assert raw['tested_commit']==tested and raw['exit_code']==0
 checks.append({k:data[k] for k in ['check_id','command','result','evidence_ref']})
path='docs/exec-plans/governance/HG-041.yaml'
files=subprocess.check_output(['git','diff','--name-only',base],text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
record={'change_identity':'harness-governance-v0.1/HG-041','display_change_id':'HG-041','base_commit':base,'tested_commit':tested,'change_status':'PASS','summary':'Define fresh enforceable NOT_STARTED KL079 for isolated mechanical TEST TRAINING/NUTRITION action-specific S36 resolutions, closed ordered full S37 per-member validation and guarded COMMIT_READY under existing physical schema. Preserve singular TRAINING anchor and exact per-action owner verification, legacy identities/positive behavior, frozen guards and no-authority boundaries. Refine only unstarted KL077 dependency/entry/read/source contract to consume normally merged prerequisite; retain full bundle and ordinary PAUSE/current T7 tests. KL027 already depends transitively. Append verified KL026/KL078 integration chains; preserve and disclose KL076 bookkeeping limitation. Pin exact packet/scope with negative governance tests. No upstream or downstream implementation, migration, CI, frozen or product-status changes.','packets_refined':['KL-077','KL-079'],'files_changed':sorted(set(files+[path])),'checks_run':checks,'frozen_impact':'NONE','authority_entries_added':[],'known_limitations':[
 'Governance PASS only. All KL079/KL077 prospective checks remain NOT_RUN. No task implementation/DC/product/layer/M3/release or production authority PASS is inferred.',
 'Candidate feasibility is pure actual-metadata/legacy-mechanical-FDN representation diagnostic and eight closed-binding negative controls, not actual new owner acceptance, ingress, PostgreSQL, concurrency or issuance evidence. The actual legacy Resolution model rejects NUTRITION; future named real-PG owner pipeline/stage/denial/replay/atomicity/repair/legacy checks remain mandatory.',
 'Physical S37 has one same-subject S36 FK; additional immutable typed binding is not a physical FK. KL079 producer and COMMIT_READY guard must verify exact additional action/proposal/resolution/source identities, and KL077 must independently recheck each issuance at T6 under unchanged current guards. No migration or caller-claimed completeness substitute.',
 'KL076 PR79 is normally merged at protected base with immutable PASS result/reviews. Its integration record is deferred because DB_CONCURRENCY-run.log is absent at reviewed 290a4d6 and was appended only in review suffix; direct merge/result/review ancestry is verified in integration-provenance.json. No historical artifact rewrite or validator relaxation.',
 'Environment setup failures are preserved in setup-diagnostics.json; cached offline locked runtime succeeds. No real database lifecycle is run in this governance task. Dirty KL055 is preserved.',
 'Fresh independent GENERAL/PROTOCOL/DB_CONCURRENCY review binds final governance/evidence head. Only own review suffix follows; exact final-head applicable hosted CI and normal merge are separate facts.'
]}
(root/path).write_text(yaml.safe_dump(record,sort_keys=False,width=98)); print(path,tested,len(record['files_changed']))
