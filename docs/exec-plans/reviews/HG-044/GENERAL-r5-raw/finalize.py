"""Persist the completed independent GENERAL review without changing source."""
import hashlib
import json
from pathlib import Path
import re
import jsonschema

ROOT = Path.cwd()
HERE = ROOT / 'docs/exec-plans/reviews/HG-044/GENERAL-r5-raw'
REV = '027bc2368e36e28aa9956489cb57af297882d671'
audit = json.loads((HERE / 'audit.json').read_text())
integrations = json.loads((HERE / 'integrations.json').read_text())
targeted = (HERE / 'targeted-short-temp.log').read_text()
assert all(audit['checks'].values())
assert not any(row['errors'] for row in integrations['integrations'] + integrations['available_exit_witnesses'])
assert not integrations['dependency_order_errors']
assert re.search(r'24 passed, 64 deselected in ', targeted)
assert 'ERROR ' not in targeted and 'FAILED ' not in targeted
assessment = '''# HG-044 independent GENERAL review, round 5

PASS at reviewed implementation/result SHA 027bc2368e36e28aa9956489cb57af297882d671.
Protected base is 2c44f456a0daf8e6933f20fc3eadc7e1869d6fff; selected tested SHA is
7206b60aa4f930caf1bac62db0f397978ea0ec34. No blocker or required follow-up found.

Reviewed AGENTS/current authority, governance/merge/review contracts, the HG044
record and preparation/authority confirmation, M3 contract and plan addendum,
complete base-to-reviewed diff, schema/validator/test source and selected raw
checks. The diff is confined to seven implementation/authority paths and own
governance/evidence/reviews. No frozen, task-definition, runtime, DB lifecycle,
CI, peer, integration, product status or actual M3 closure is changed. The plan
prefix is byte-identical; derived index hashes and exact file declaration pass.

The exact sixteen M3 identities, separate M1 KL074 support, M2/M1 prerequisite,
transitive dependency integrations and base/tested ordering are enforced. All
mapped named checks match pinned full contracts and command/oracle/result/raw
regular-blob bindings. Thirty-two available integration chains, twenty-four
available mapped witnesses and their dependency ordering independently replay
without errors. KL028 and KL029 integration records remain absent; their missing
prospective evidence is not PASS. The synthetic complete-chain fixture supplies
validator input only and never actual closure evidence.

The fresh regression binds one integrated tested revision through the unchanged
governance suffix guard, exact ordered command set, raw stdout/JUnit/collection
hashes, positive matching counts and complete per-selector contributions. The
repairs require actual integer zero exit codes, retain bracketed pytest parameter
IDs including ::, and distinguish disposition summaries from node parameter text.
The bounded short-temp replay passed all 24 selected cases, with 64 intentionally
deselected by the reviewer selection. This is independent targeted review evidence,
not a fresh closure regression. It includes both omitted multi-selector negatives,
float/bool exit negatives, genuine four parameter formats and legacy M1/M2 checks.

The exact 31 B/10 I ledgers preserve nineteen executable B layers and all twelve
deferred B layers, I04@WF, shadow usability and R04@E2E as NOT_RUN. B04 guard support
never promotes full reauthorization. PU/DC/WF/E2E reach labels, historical model
limits, empty product claims, disabled production activation and non-executable
shadow are preserved. Existing M1/M2 schema branches and integration/result/review
and legacy milestone validator functions are unchanged.

Every selected check has the exact command, tested/base SHA, integer zero exit
and valid retained raw bytes/hash/count; selected focused/harness/unit counts are
88/878/241 PASS. The selected tested-to-reviewed suffix is a single linear own
governance/new-evidence commit. Earlier failed captures and CHANGES_REQUIRED rounds
remain historical and are not selected acceptance evidence.

The source_diff exclusion is acceptable for this governance scope: it excludes
only own HG044 review records, preserving literal raw unified-diff context spaces.
The failed broad historical whitespace capture remains unchanged and unselected;
all implementation, authority, governance and task-check evidence paths remain
covered by the independently clean source diff. SHA-bound review schema, regular
Git evidence provenance and review-only suffix controls still apply to the excluded
review directory. This does not waive any semantic or task acceptance check.

Review limitations and retained unsuccessful attempts: the first default-temp
bounded pytest attempt returned 1 with 22 fixture setup errors (`git add .` could
not create a temporary file: Invalid argument) and two passing legacy cases. Its
complete raw log is retained, never relabelled. A fresh shorter /private/tmp fixture
directory succeeded. The first independent audit incorrectly required an exact
command for every unmapped task selector; the contract requires every mapped
selector exactly and all plain suites, including unit aggregate coverage. That
overstrict reviewer assertion and raw failure are retained in audit-first.*;
the corrected contract-based audit passes. Neither attempt changes repository
source. No local PostgreSQL/Docker lifecycle or full-suite rerun was performed.
Applicable hosted isolated CI and all specialist reviews remain separate merge
requirements; this GENERAL PASS is not a merge or milestone/product PASS.
'''
(HERE / 'assessment.md').write_text(assessment)
commands = [
    {'check': 'audit-first', 'exit_code': 1, 'result': 'FAIL', 'raw': 'audit-first.log', 'note': 'Retained overstrict reviewer assertion; corrected to ratified suite/mapped-selector contract.'},
    {'check': 'audit', 'exit_code': 0, 'result': 'PASS', 'raw': 'audit.log'},
    {'check': 'integrations', 'exit_code': 0, 'result': 'PASS', 'raw': 'integrations.log'},
    {'check': 'targeted-default-temp', 'exit_code': 1, 'result': 'FAIL', 'raw': 'targeted-pytest.log', 'note': '22 temporary Git fixture setup errors; raw preserved.'},
    {'check': 'targeted-short-temp', 'exit_code': 0, 'result': 'PASS', 'raw': 'targeted-short-temp.log', 'command': "PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 TMPDIR=/private/tmp /private/tmp/hg044-venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=/private/tmp/hg044-general-r5-pytest tests/harness/test_m3_milestone_closure.py -k 'genuine_pytest_parameter or each_multiselect or integrated_regression_fails_closed or legacy_m1_m2 or existing_schema_branches'"},
]
for row in commands:
    raw = (HERE / row['raw']).read_bytes()
    row['raw_sha256'] = hashlib.sha256(raw).hexdigest(); row['raw_byte_count'] = len(raw)
(HERE / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
review = {'task_identity': 'harness-governance-v0.1/HG-044', 'reviewed_head_sha': REV,
          'review_type': 'GENERAL', 'status': 'PASS', 'findings': [],
          'evidence_refs': [str((HERE / p).relative_to(ROOT)) for p in ('assessment.md', 'audit.json', 'audit.log', 'audit.py', 'audit-first.json', 'audit-first.log', 'complete-diff.patch', 'integrations.json', 'integrations.log', 'integrations.py', 'targeted-pytest.log', 'targeted-short-temp.log', 'commands.json', 'source-diff.log')],
          'review_contract_version': 'v0.2'}
jsonschema.Draft202012Validator(json.loads((ROOT / 'THREAD_REVIEW.schema.json').read_text())).validate(review)
(HERE.parent / 'GENERAL.json').write_text(json.dumps(review, indent=2) + '\n')
print('GENERAL_PASS', REV)
