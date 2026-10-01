"""Persist checks before review; files_changed binds exact protected-base diff."""
import json
import subprocess
from pathlib import Path

import yaml

ROOT=Path.cwd(); HERE=ROOT/'docs/exec-plans/evidence/HG-037'
base=(HERE/'protected-base.txt').read_text().strip()
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
checks=[]
for key in ['append_only_provenance_audit','readiness_scope_regressions','harness_validation','harness_tests','unit_tests','lint','typecheck','diff_clean']:
 r=json.loads((HERE/f'{key}-{head[:7]}.json').read_text()); assert r['result']=='PASS' and r['tested_commit']==head
 checks.append({k:r[k] for k in ['check_id','command','result','evidence_ref']})
tracked=subprocess.check_output(['git','diff','--name-only',base],text=True).splitlines()
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
path='docs/exec-plans/governance/HG-037.yaml'
files=sorted(set(tracked+untracked+[path]))
record=dict(change_identity='harness-governance-v0.1/HG-037',display_change_id='HG-037',base_commit=base,tested_commit=head,change_status='PASS',summary='Append fresh NOT_STARTED KL074 PostgreSQL final-server readiness follow-up after normal HG036 merge. Preserve completed KL002 and all existing definitions/results/evidence. Ratify nine future checks with explicit TCP readiness, bounded deadline, SQL no-replay, isolated actual-image migrated coldstart provenance and cleanup; exact scope guard and meaningful positive/negative harness regressions. No product/Compose/test implementation or requirement/release claim.',packets_refined=['KL-074'],files_changed=files,checks_run=checks,frozen_impact='NONE',authority_entries_added=[],known_limitations=['Earlier GENERAL and DB_CONCURRENCY reviews of 4b1533b found startup ownership/endpoint bypasses. Their CHANGES_REQUIRED artifacts are preserved under HG037 evidence. Final source guard accepts only the complete-byte bounded readiness candidate; final independent rereviews must bind the corrected governance/evidence head.','All nine prospective KL074 implementation checks remain NOT_RUN; HG037 governance PASS is not task/product/release PASS or production activation.','Current source plus same-SHA CI missing-socket errors strongly support an init-stop-final startup race; actual deployed image digest/entrypoint and timestamped failing container logs are unverified. The future task must independently demonstrate actual-image ordering and cannot fabricate causal PASS.','No product/Compose/DB test/CI workflow/migration/authentication change is made here; KL019 owns transaction resources independently. Full legacy DB regressions require dedicated hosted VM Docker.','Local uv is unavailable; checks use existing kl017 virtualenv with PYTHONPATH. Normal hosted locked-uv CI and merge gates remain required.','Fresh independent GENERAL and DB_CONCURRENCY reviews bind the final governance+evidence head. After review only HG037 review-record paths may change.'])
(ROOT/path).write_text(yaml.safe_dump(record,sort_keys=False,width=98))
print(path, 'tested='+head, 'declared='+str(len(files)))
