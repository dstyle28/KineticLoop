"""Bind exact governance diff and final PASS checks before independent review."""
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path.cwd(); HERE = ROOT / 'docs/exec-plans/evidence/HG-038'
base = (HERE/'protected-base.txt').read_text().strip()
head = sys.argv[1] if len(sys.argv) > 1 else subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
subprocess.run(['git', 'merge-base', '--is-ancestor', head, 'HEAD'], check=True)
checks = []
for key in ['append_only_scope_audit','next_wave_scope_regressions','harness_validation','harness_tests','unit_tests','lint','typecheck','diff_clean']:
    r = json.loads((HERE/f'{key}-{head[:7]}.json').read_text())
    assert r['result']=='PASS' and r['tested_commit']==head
    checks.append({k:r[k] for k in ['check_id','command','result','evidence_ref']})
files = subprocess.check_output(['git','diff','--name-only',base],text=True).splitlines()
files += subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
path = 'docs/exec-plans/governance/HG-038.yaml'
record = {'change_identity':'harness-governance-v0.1/HG-038','display_change_id':'HG-038',
    'base_commit':base,'tested_commit':head,'change_status':'PASS',
    'summary':'After actual KL074 normal merge, refine unstarted KL026 to nine tests-only real PostgreSQL interleavings, including actual root cancellation plus separate guarded reservation cleanup, and KL027 to a composed complete deterministic TEST demo with lifecycle-valid authority denials. Append three bounded NOT_STARTED owner prerequisites KL075 internal snapshot/stage guards, KL076 source-bound immutable TEST F/D/N preparation, KL077 complete TEST bundle/current CONTINUE/RESUME adapters with internal ordinary lifecycle PAUSE; preserve public wire registry and frozen protective-control semantics. Separate deterministic PU equality from actual post-lock real-PG expiry evidence. Pin exact packets/definitions, isolate suite namespaces and serialize production hotspots, preserve all product/layer/release obligations. Append verified missing KL019/KL047/KL074 integration chains only; preserve rejected reviews/evidence, no historical artifact rewrite or M3 closure.',
    'packets_refined':['KL-026','KL-027','KL-075','KL-076','KL-077'],
    'files_changed':sorted(set(files+[path])), 'checks_run':checks, 'frozen_impact':'NONE',
    'authority_entries_added':[],
    'known_limitations':[
        'Governance checks PASS only; all prospective KL026/027/075/076/077 implementation checks and product/release obligations start NOT_RUN; M3 is not closed.',
        'I04@DC and I04@WF are separate; KL026 has no process-WF implementation or production fix permission. Any test-discovered production bug requires a separately bounded task and fresh review.',
        'RecordSnapshot/AdvanceAttempt remain internal, absent from the 39 public commands. No upstream stage/preparation/full execution capability is implemented in this governance PR.',
        'Existing generic ApplyControl/AcceptFactRevision and projection/BuildManifest recipes are ratified only as exact trusted restricted TEST owner instrumentation, not public typed ingress/authentication implementation.',
        'I03 uses two existing owner transactions: terminal root first, guarded RESERVED cleanup afterward. No speculative CancelIntent S32 grant or atomic root-plus-ledger claim; DISPATCH_INTENT occupation persists.',
        'KL077 ordinary PAUSE is a bounded internal TEST lifecycle contraction with no execution grant; protective pause/STOP/hold remains frozen T2. Positive RESUME and authority denials require owner-produced valid lifecycle states.',
        'Exact equality is deterministic PU predicate evidence. Actual real-PG guards provide fresh clock_timestamp without a controllable equality seam; DC proves before/after and expiry crossed during observed lock waits. No PU-to-DC or DC-to-WF PASS substitution.',
        'Deterministic TEST policy predicates and complete F/D/N fixture provenance do not establish clinical, model, production quality, rollout, or provider policy. Missing real-data/model/evaluation obligations remain unclaimed.',
        'No foreign local DB fixtures or KL074-only workflow reuse. Own real-PG suites require exact SHA/resolved-root DB/Compose validation and nested lifecycle audit; legacy full DB CI remains unchanged on fresh hosted VM.',
        'Fresh independent GENERAL/PROTOCOL/DB_CONCURRENCY reviews bind the final governance/evidence SHA; after review only HG038 review-record paths may change. All normal hosted gates must pass before normal merge.',
    ]}
(ROOT/path).write_text(yaml.safe_dump(record,sort_keys=False,width=98))
print(path,'tested='+head,'declared='+str(len(record['files_changed'])))
