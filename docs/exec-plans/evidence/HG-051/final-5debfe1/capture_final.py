"""Persist one complete clean final run; partial earlier attempts remain historical."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import yaml

root = Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
sha = '5debfe1b41a26c0b3f985917b80995a9eb38b92e'
base = 'b877db0edd2e4550d6ea81750656112fb7f2e223'
source = Path('/private/tmp/hg051-checks-' + sha[:7])
execution = json.loads((source / 'EXECUTION.json').read_bytes())
assert execution['tested_commit'] == execution['source_end_sha'] == sha
assert not execution['source_end_status']
assert all(r['exit_code'] == 0 and r['tested_commit'] == sha for r in execution['executions'])
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip() == sha
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)
spec = importlib.util.spec_from_file_location('capture_compact', root / 'tools/harness/compact_evidence.py')
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)
owner = root / 'docs/exec-plans/evidence/HG-051'
out = owner / ('final-' + sha[:7])
out.mkdir()
checks = []

def capture(path, name, record):
    ref = str((out / (name + '.json')).relative_to(root))
    ce.capture(root, ref, path.read_bytes(), sha, record['command'], record['exit_code'], None)
    return ref

for record in execution['executions']:
    ref = capture(Path(record['log']), record['check_id'], record)
    checks.append(dict(check_id=record['check_id'], command=record['command'], result='PASS', evidence_ref=ref))
by_id = {r['check_id']: r for r in execution['executions']}
for kind in ['focused', 'unit']:
    capture(source / (kind + '.xml'), kind + '-junit', by_id[kind])
for path in sorted((source / 'harness').iterdir()):
    if path.is_file():
        capture(path, 'harness-' + path.name.replace('.', '-'), by_id['harness'])
shutil.copyfile(source / 'EXECUTION.json', out / 'EXECUTION.json')
shutil.copyfile('/private/tmp/hg051-driver-final2.log', out / 'driver.log')
shutil.copyfile(__file__, out / 'capture_final.py')
record = dict(change_identity='harness-governance-v0.1/HG-051', display_change_id='HG-051',
              base_commit=base, tested_commit=sha, change_status='PASS',
              summary='Authorize only the exact four KL080 historical current-tree lossless representations through a task-owned archival mapping. Preserve original bytes, regular Git blobs/commits, failed outcomes, tested/reviewed bindings, non-migrated evidence and unchanged limits. Archival retrieval is distinct from execution proof; original verification cannot borrow later storage.',
              packets_refined=['KL-080'], files_changed=[], checks_run=checks, frozen_impact='NONE',
              authority_entries_added=['HISTORICAL_EVIDENCE_MAPPING.schema.json'],
              known_limitations=[
                  'Governance only: KL080 actual historical artifacts are not migrated; KL080 remains draft blocked. No KL080, M3, product or release closure claim.',
                  'Root owns reviewed trusted-validator/schema asset installation, exact pins/admission, final App/full-DB gate and normal merge. Full DB/App and hosted gate status are NOT_RUN in this local governance result.',
                  'Only the final complete clean committed run supplies required-check PASS. First f9ed15a whitespace failure remains FAIL; focused/full harness were interrupted and remain NOT_RUN with unavailable terminal exit. Uncommitted stale-manifest failure and driver syntax failure are preserved without acceptance credit.',
                  'Historical source-suite exit 1 failures and BLOCKED/FAIL/UNMERGED result/CHANGES_REQUIRED reviews remain fixed in the exact indexed schema. Unknown timestamps remain null; absent historical SECURITY review is not invented.',
                  'Original revisions must remain available through normal merge ancestry. Archival retrieval may recover bytes without originals, but cannot certify old execution/review/PASS; gate verification requires original regular blobs and hashed records.',
                  'Fresh independent GENERAL, PROTOCOL, DB_CONCURRENCY and SECURITY_DATA_BOUNDARY reviews bind the governance/evidence revision. Only the own linear REVIEW_RECORD_ONLY suffix may follow.'
              ])
path = root / 'docs/exec-plans/governance/HG-051.yaml'
changed = subprocess.check_output(['git', 'diff', '--no-renames', '--name-only', base, 'HEAD'], cwd=root, text=True).splitlines()
new = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], cwd=root, text=True).splitlines()
record['files_changed'] = sorted(set(changed + new + [str(path.relative_to(root))]))
path.write_text(yaml.safe_dump(record, sort_keys=False, width=110))
print(json.dumps(dict(tested_commit=sha, checks=len(checks), declared_paths=len(record['files_changed'])), indent=2))
