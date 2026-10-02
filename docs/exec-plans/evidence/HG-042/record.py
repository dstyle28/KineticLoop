"""Append governance PASS only from all fresh exact-SHA successful raw checks."""
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
HERE = ROOT / 'docs/exec-plans/evidence/HG-042'
BASE = '93b38f20a3f3d71206515fb0f4d852f5b0b6d344'
tested = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
checks = []
for key in ('boundary_shadow', 'scope', 'integrations', 'harness', 'unit', 'lint', 'typecheck', 'validation', 'diff'):
    data = json.loads((HERE / f'{key}-{tested[:7]}.json').read_text())
    assert data['tested_commit'] == tested and data['base_commit'] == BASE
    assert data['result'] == 'PASS' and data['exit_code'] == 0
    raw = data['raw_utf8'].encode()
    assert data['raw_sha256'] == hashlib.sha256(raw).hexdigest() and data['raw_byte_count'] == len(raw)
    checks.append({k: data[k] for k in ('check_id', 'command', 'result', 'evidence_ref')})
path = 'docs/exec-plans/governance/HG-042.yaml'
files = subprocess.check_output(['git', 'diff', '--name-only', BASE], text=True).splitlines()
files += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
record = {
    'change_identity': 'harness-governance-v0.1/HG-042', 'display_change_id': 'HG-042',
    'base_commit': BASE, 'tested_commit': tested, 'change_status': 'PASS',
    'summary': 'Replace broad unstarted KL028/KL029 source-writing packets and generic checks with enforceable '
               'disjoint tests-only scopes, exact executable selectors/oracles, isolated task/SHA/worktree '
               'DB namespaces, truthful complete 31-layer ledger and negative scope/claim guards. Preserve '
               '19 prospective executable layers and explicitly defer 12, including unsupported full TEST '
               'reauthorization. Add justified KL029 security review and five actual verified integration '
               'records under merged HG043 provenance rules. No completed task, frozen, production, M3 '
               'closure, release or downstream implementation changes.',
    'packets_refined': ['KL-028', 'KL-029'], 'files_changed': sorted(set(files + [path])),
    'checks_run': checks, 'frozen_impact': 'NONE', 'authority_entries_added': [],
    'known_limitations': [
        'Governance PASS only. KL028/KL029 remain NOT_STARTED/ENFORCEABLE, every prospective check and '
        'all31 B layer statuses NOT_RUN. Task PASS, requirement PASS, review PASS and MERGED are separate facts.',
        'Nineteen exact layer obligations have merged mechanical owners (6PU+13DC); twelve are deferred: '
        'eight API/workflow/DB/eligibility-rendering E2E, B14 WF independent KL039 STOP lane plus worker/fault '
        'infrastructure, B11/B12 absent pure commit-state evaluator and B04 full TEST reauthorization. '
        'B04 full issue and actual Reauthorize registry guard support cannot claim its complete DC oracle; '
        'a separate bounded owner follow-up is mandatory, without legacy downgrade or fixture bypass.',
        'Real-data shadow store/API usability belongs KL045; S46/S47 fixture inputs are declared external '
        'evaluation inputs, never shadow owner outputs. M2 G-SHADOW construction is not that usability.',
        'M3 closure schema supports only M1/M2; record the separate focused governance gap without adding '
        'M3 PASS, M3-to-M4 cycle or M4 worker/outbox scope. Production activation remains disabled.',
        'Five actual normal integrations validate under merged HG043 with result hashes and exact reviewed '
        'or proven review-record-only regular Git-blob reference sources; historical completed definitions, '
        'results/reviews/test evidence remain unchanged with historical UNMERGED result statuses.',
        'Historical preparation/provenance failures are preserved. The first final check round at2ee2b0d '
        'failed generator whitespace and one existing governance-plan append regression. The corrected '
        'generator preserves packet bytes; the plan guard uses an explicit own-section end marker, '
        'allowing unrelated later governance without weakening its exact own scope. '
        'Only the newly tested all-PASS round is selected. No local DB lifecycle or foreign resources were run.',
        'Fresh independent GENERAL/PROTOCOL/DB_CONCURRENCY/SECURITY_DATA_BOUNDARY reviews bind the committed '
        'governance/evidence revision. Only own review suffix follows; every applicable final hosted CI '
        'must PASS before normal merge. Dirty KL055 and unrelated branches/resources remain untouched.',
    ],
}
(ROOT / path).write_text(yaml.safe_dump(record, sort_keys=False, width=98))
print(path, tested, len(record['files_changed']))
