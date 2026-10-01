"""Commit exact HG040 governance PASS facts, never prospective task/product PASS."""
import json
import subprocess
import sys
from pathlib import Path

import yaml

root=Path.cwd(); here=root/'docs/exec-plans/evidence/HG-040'
base=(here/'protected-base.txt').read_text().strip(); tested=sys.argv[1]
subprocess.run(['git','merge-base','--is-ancestor',tested,'HEAD'],check=True)
checks=[]
for key in ['scope_audit','upstream_scope_regressions','original_gateway_reproduction','candidate_gateway_feasibility','harness_validation','harness_tests','unit_tests','lint','typecheck','diff_clean']:
 r=json.loads((here/f'{key}-{tested[:7]}.json').read_text());assert r['result']=='PASS' and r['tested_commit']==tested
 checks.append({k:r[k] for k in ['check_id','command','result','evidence_ref']})
path='docs/exec-plans/governance/HG-040.yaml'
files=subprocess.check_output(['git','diff','--name-only',base],text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
record={'change_identity':'harness-governance-v0.1/HG-040','display_change_id':'HG-040','base_commit':base,'tested_commit':tested,'change_status':'PASS',
 'summary':'After actual HG039 normal merge, add complete NOT_STARTED KL078 to repair existing RecordProjection/BuildManifest preparation capabilities: immutable server-owned S21 revision provenance, exact actual same-subject SEALED S15 binding, atomic projection dependency closure and local immutable BUILDING/READY completion. Require owner-produced CanonicalViewService to projection/dependency/build to actual T3 plus named PU/real-PG denials/replay/duplicate/rollback/no-authority oracles. Refine only unresulted KL076 upstream dependency/read context/source requirement. Pin exact task scope/packet/checks with negative governance tests; preserve completed results, failed diagnostics, frozen/public boundaries, existing CI and all product/release/layer states. No KL078 implementation.',
 'packets_refined':['KL-076','KL-078'],'files_changed':sorted(set(files+[path])),'checks_run':checks,'frozen_impact':'NONE','authority_entries_added':[],
 'known_limitations':[
 'Governance PASS only. Every prospective KL078 implementation check remains NOT_RUN; KL076 remains unmerged without result at protected base. No requirement, product, release, M3 or downstream task PASS.',
 'Candidate feasibility is an in-memory actual-gateway diagnostic with four positive and nine negative controls, not real PostgreSQL or typed-ingress/provenance/replay/T3 acceptance. KL078 must execute every named actual owner PU/DC selector and full own suite on tested SHA, then existing hosted full DB/quality/gates.',
 'Original five actual pre-SQL failures and independent preliminary assessment preserved verbatim. Research setup failure logs remain historical FAIL, corrected reruns do not overwrite them.',
 'Preparation keeps independent short transactions with no S01/registry coordination. Exact immutable source verification and S23 local locks cannot become blanket FK exemption, arbitrary callback permissions, fabricated lock inventories, SUBJECT translation or raw output seeds. Public wire/matrix/execute_command rejection and frozen T3 current-basis/lock/authority meaning unchanged.',
 'KL075 normal merge and byte-identical result/review ancestry verified independently. Optional integration record deferred: three raw review evidence_refs were appended only after reviewed SHA, so the existing integration validator rejects the record. No historical edits or guard relaxation are included.',
 'KL026 PR76 is normally merged at70dc4863ccdca95f7a44e79b68501a698262e323. HG040 now has coordinator-assigned uncontested merge priority, rebased and retested on that protected base. Coordinator schedules KL078 in a fresh task thread after this governance merge.',
 'Fresh independent GENERAL/PROTOCOL/DB_CONCURRENCY reviews bind final governance/evidence head. Only own review-record suffix may follow; normal exact-head merge requires all applicable hosted CI/gates PASS. Preserve dirty KL055 and blocked KL076 worktrees; KL026 cleanup was already completed by its owner.'
 ]}
(root/path).write_text(yaml.safe_dump(record,sort_keys=False,width=98))
print(path,'tested='+tested,'declared='+str(len(record['files_changed'])))
