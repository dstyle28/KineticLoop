"""Persist a schema-valid exact-SHA GENERAL review only after bounded evidence passes."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import jsonschema

root = Path.cwd()
out = root / 'docs/exec-plans/reviews/HG-044/GENERAL-r6-raw'
audit = json.loads((out/'audit.json').read_text())
bounded = json.loads((out/'bounded.json').read_text())
wiring = json.loads((out/'gate-wiring.json').read_text())
assert audit['status'] == 'PASS' and all(audit['checks'].values())
assert bounded['exit_code'] == 0 and wiring['status'] == 'PASS'
cases = list(ET.parse(out/'bounded.xml').getroot().iter('testcase'))
assert len(cases) == 17 and not any(list(c.iter(tag)) for c in cases for tag in ('error','failure','skipped'))
assert hashlib.sha256((out/'bounded.stdout').read_bytes()).hexdigest() == bounded['stdout_sha256']
assert hashlib.sha256((out/'bounded.stderr').read_bytes()).hexdigest() == bounded['stderr_sha256']
assessment = '''# GENERAL independent review — HG044 r6

PASS at cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54. No BLOCKER,
REQUIRED_FOLLOWUP or NONBLOCKING findings. Protected base is
2c44f456a0daf8e6933f20fc3eadc7e1869d6fff; selected tested revision is
06dab6dbb38221e7111c18811cb20b42b8cc2397. This review supersedes the
historical r5 GENERAL review without relabelling its earlier revision.

The complete committed path/mode/blob/SHA256 inventory matches the governance
declaration and bounded write scope. All source changes were independently read
and are retained as a bounded seven-path diff, without recursively recapturing
historical raw review files. Plan-prefix protection reads explicit committed base
and reviewed revisions in both actual validate branches. Normal CI discovery
still derives HG044; its unchanged discovery code and review-only branch were
inspected independently. Both isolated real-Git prefix cases passed, accepting
the appended prefix and rejecting a changed protected prefix despite contrary
ambient plan bytes. The exact earlier failing log/traceback and repaired diagnostic
retain their bytes/hashes; the repaired diagnostic has only expected dirty-capture
and stale-prior-review failures. Direct current-SHA branch probes also reach the
real guard without the previous optional-target exception.

All eight selected checks match the selected tested revision, commands and raw
hashes, including 90 focused / 880 harness / 241 unit PASS. Seventeen bounded
review cases passed, covering prefix, omitted selectors, genuine parameter IDs,
float/boolean execution and collection exit codes, collection skips, legacy
M1/M2 validation/schema, governance scope and ratified mapping. No redundant full
suite, PostgreSQL lifecycle, Docker or foreign fixture namespace was run.

Every mapped named check contract digest and selector agrees with current task
authority. M1/M2 schema branches/definitions and all existing non-dispatch validator
functions, including HG043 provenance/integration functions, remain byte-identical.
Frozen files, backlog, task packets, runtime, CI, statuses and peer artifacts are
unchanged. No actual M3 closure is created. M3 validation retains exact integration
and prerequisite ancestry, one fresh integrated regression, regular committed raw
provenance, positive collection/JUnit agreement, all 31 B / 10 I dispositions,
the 12 deferred B layers and I04@WF / shadow usability / R04@E2E NOT_RUN. No
production activation, executable shadow or product/release PASS is implied.

The independent scoped source whitespace check passes. The broad check fails
only on retained own-HG044 raw review diff/log whitespace; the complete broad
diagnostic is hashed and its affected paths recorded, without recursive expansion.
The first review-audit attempt rejected the existing executable validator mode and
mistook nested raw diff lines for diagnostic headings; the corrected inventory
and diagnostic parser pass. These were reviewer-tool assumptions, not source
defects. Initial raw outputs are retained and unselected.

This is review PASS only. Fresh specialist reviews, a clean exact-head merge gate,
and applicable unchanged hosted CI remain separate merge prerequisites. Only the
own-task REVIEW_RECORD_ONLY suffix is allowed after this reviewed revision.
'''
(out/'assessment.md').write_text(assessment)
manifest = {p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(out.iterdir()) if p.is_file() and p.name != 'raw-hashes.json'}
(out/'raw-hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
prefix = 'docs/exec-plans/reviews/HG-044/GENERAL-r6-raw/'
review = dict(task_identity='harness-governance-v0.1/HG-044',
    reviewed_head_sha=audit['reviewed'],review_type='GENERAL',status='PASS',findings=[],
    evidence_refs=[prefix+n for n in ('assessment.md','audit.json','inventory.json','functions.json',
        'mapping.json','selected-captures.json','source-diff.patch','whitespace.json',
        'bounded.json','bounded.stdout','bounded.stderr','bounded.xml','gate-wiring.json','raw-hashes.json')],
    review_contract_version='v0.2')
jsonschema.Draft202012Validator(json.loads((root/'THREAD_REVIEW.schema.json').read_text())).validate(review)
(root/'docs/exec-plans/reviews/HG-044/GENERAL.json').write_text(json.dumps(review,indent=2)+'\n')
print('GENERAL PASS at '+audit['reviewed']+'; 17 bounded cases passed; zero findings.')
