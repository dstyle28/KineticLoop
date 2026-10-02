"""Persist independent security review only after bounded probes pass."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import jsonschema

root = Path.cwd()
prefix = 'docs/exec-plans/reviews/HG-044/SECURITY_DATA_BOUNDARY-r5-raw/'
out = root / prefix
audit = json.loads((out / 'audit.json').read_text())
guard = json.loads((out / 'reviewed-result-guard.json').read_text())
probes = json.loads((out / 'bounded-probes.json').read_text())
assert audit['status'] == guard['status'] == 'PASS'
assert type(probes['exit_code']) is int and probes['exit_code'] == 0
cases = list(ET.parse(out / 'bounded-probes.xml').getroot().iter('testcase'))
assert len(cases) == 24 and all(not list(c.iter(tag)) for c in cases for tag in ('failure', 'error', 'skipped'))
assessment = '''Independent SECURITY_DATA_BOUNDARY review at 027bc2368e36e28aa9956489cb57af297882d671 against protected master 2c44f456a0daf8e6933f20fc3eadc7e1869d6fff; selected tested SHA 7206b60aa4f930caf1bac62db0f397978ea0ec34.

PASS with no findings. Read AGENTS/current index, PR review skill, governance/merge/review contracts, own governance/preparation/authority confirmation, M3 contract and bounded plan addendum, relevant frozen registry/authorization/replay/DB transaction and Integration provider/context boundary sections. Independently retained the complete 220-file base-to-reviewed diff as exact raw bytes, inspected implementation/tests/contracts and selected evidence, and checked every changed regular blob against the declared protected-base scope.

Eight selected records bind the exact tested/base revision and PASS; seven raw execution captures also match the independent capture-integrity record byte counts and SHA256 values. The scope capture has its distinct structured PASS representation. Selected focused/harness/unit counts are 88/878/241. The sole tested-to-reviewed commit adds only the final own governance record and new evidence. Earlier failed/interrupted rounds remain historical; the source_diff exclusion is documented, limited to own review bookkeeping, and preserves literal raw diff context bytes rather than rewriting failed reports.

All 27 indexed authority hashes and 161 manifest byte/hash entries match committed regular blobs. Frozen baseline/files are unchanged. Existing M1/M2 schema branches and every existing validator function except the intentional governance scope/main dispatch remain byte-identical. All 52 named check contract digests match exact task contracts. All 32 available transitive task integration chains independently validate regular result/review/raw check sources, exact identity, required SHA-bound reviews and Git ancestry. M3 dependency helper independently checks every available reviewed result is exactly one regular blob, including unmapped M3 tasks, M1 KL074 support and dependencies. KL028/KL029 implementations/results are merged but integration records are absent; no actual M3 instance exists and premature closure remains rejected.

Twenty-four bounded independent pure/Git pytest probes passed: all four real pytest-generated parameter collection/JUnit cases, both omitted multiselect cases, sixteen integrated-regression failure cases including strict integer exit codes and real skip summary rejection, and both checked-blob/source parsing cases. No full suite or local DB/Docker/foreign fixture lifecycle was rerun.

Closure mapping preserves exact 16 M3 identities, separate M1 KL074 support, all dependencies before consumer base/tested commits, one fresh integrated regression after every M3 merge, exact selectors/collection/JUnit cases and regular path/revision/hash provenance. All 31 B and 10 I dispositions remain: 19 planned executable B rows, 12 deferred B layers, I04@WF, shadow usability and R04@E2E stay NOT_RUN. B04 guard support does not become full reauthorization; PU equality does not become PG equality; DC/ingress/registration/owner reach is not relabelled WF/E2E. Historical evaluation storage fixtures are not shadow owner output.

Production activation and executable shadow remain false, product requirement claims empty, historical model evidence unverified/unreproduced. No frozen/runtime/CI/provider trust or command authority change, data export, credential-bearing evidence, live authorization or execution bypass was found. Changed evidence credential-pattern scan was clean; reviewed raw material is synthetic test/Git/check bookkeeping. Synthetic Git fixtures prove validator behavior only. Review PASS is distinct from task/milestone/product/release PASS and MERGED; final unchanged hosted isolated CI and coordinator serialization remain external merge prerequisites.
'''
(out / 'assessment.md').write_text(assessment)
refs = ['docs/exec-plans/governance/HG-044.yaml', 'docs/harness/M3_CLOSURE_CONTRACT.md',
        'docs/exec-plans/evidence/HG-044/capture-integrity-7206b60.json',
        'docs/exec-plans/evidence/HG-044/RAW_DIFF_SCOPE.md']
refs += [prefix + name for name in ('audit.py', 'audit.json', 'complete-diff.patch',
                                   'reviewed-result-guard.py', 'reviewed-result-guard.json',
                                   'run.py', 'bounded-probes.json', 'bounded-probes.stdout',
                                   'bounded-probes.stderr', 'bounded-probes.xml',
                                   'source-diff.stdout', 'source-diff.stderr', 'assessment.md', 'finalize.py')]
review = dict(task_identity='harness-governance-v0.1/HG-044',
              reviewed_head_sha='027bc2368e36e28aa9956489cb57af297882d671',
              review_type='SECURITY_DATA_BOUNDARY', status='PASS', findings=[],
              evidence_refs=refs, review_contract_version='v0.2',
              summary='Independent security/data boundary PASS: exact committed blob provenance, selected capture integrity, legal tested suffix, 32 available integrations/dependency chains and 52 pinned check contracts verified; 24 bounded repaired-selector/strict-exit/real pytest parameter/source probes pass. M1/M2/HG043/frozen semantics remain intact. No actual M3 closure, product/release PASS, production activation, executable shadow, provider command elevation, credential exposure or data export. Missing KL028/KL029 integration records still reject closure; deferred layers and historical evaluation limits remain truthful. Raw evidence preserved; final hosted CI and merge serialization remain required.')
jsonschema.Draft202012Validator(json.loads((root / 'THREAD_REVIEW.schema.json').read_text())).validate(review)
(root / 'docs/exec-plans/reviews/HG-044/SECURITY_DATA_BOUNDARY.json').write_text(json.dumps(review, indent=2) + '\n')
print('SECURITY_DATA_BOUNDARY_PASS', len(cases))
