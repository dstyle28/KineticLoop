"""Persist governance result after every revision-bound check passes."""
import json
import subprocess
from pathlib import Path

import yaml

root = Path.cwd()
here = root / 'docs/exec-plans/evidence/HG-043'
base = '1099d85bd4aa76ec8221700e55b4e77a84479126'
tested = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
checks = []
for key in ('provenance', 'harness', 'unit', 'lint', 'typecheck', 'validation', 'replay', 'diff'):
    check = json.loads((here / f'{key}-{tested[:7]}.json').read_text())
    assert check['tested_commit'] == tested and check['exit_code'] == 0 and check['result'] == 'PASS'
    checks.append({k: check[k] for k in ('check_id', 'command', 'result', 'evidence_ref')})
path = 'docs/exec-plans/governance/HG-043.yaml'
files = subprocess.check_output(['git', 'diff', '--name-only', base], text=True).splitlines()
files += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
record = {
    'change_identity': 'harness-governance-v0.1/HG-043', 'display_change_id': 'HG-043',
    'base_commit': base, 'tested_commit': tested, 'change_status': 'PASS',
    'summary': 'Bind ordinary integration review evidence to regular Git blobs at the reviewed SHA; '
               'bind reviewer-created own-task bookkeeping to the exact review-record commit only '
               'after a strict ancestral linear exclusively own-review suffix proof. Preserve result '
               'and task-test evidence guarantees, delayed review and exact-tree squash semantics.',
    'packets_refined': [], 'files_changed': sorted(set(files + [path])), 'checks_run': checks,
    'frozen_impact': 'NONE', 'authority_entries_added': [],
    'known_limitations': [
        'Governance validator repair only. No task, product requirement, DB, release or production PASS is inferred.',
        'Five candidates replayed from protected Git ancestry in ephemeral fixtures; no official integration records written. HG042 owns later bookkeeping.',
        'Review-created logs are reviewer bookkeeping, never pre-review task acceptance evidence.',
        'Delayed review with unrelated intervening commits retains ordinary reviewed evidence support but cannot use the new strict suffix exception.',
        'No database runtime is run locally for this validator repair; independent specialist audit and all final applicable hosted PostgreSQL CI are required before ordinary merge.',
        'Fresh GENERAL/PROTOCOL/DB_CONCURRENCY review binds final governance/evidence head. Only own HG043 review suffix follows.',
    ],
}
(root / path).write_text(yaml.safe_dump(record, sort_keys=False, width=98))
print(path, tested, len(record['files_changed']))
