"""Persist exact-SHA review after independent bounded probes complete."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import jsonschema

root = Path.cwd()
out = root / 'docs/exec-plans/reviews/HG-044/PROTOCOL-r6-raw'
capture = json.loads((out / 'bounded-tool-result.json').read_text())
assert capture['exit_code'] == 0 and 'session_id' not in capture
cases = list(ET.parse(out / 'bounded.xml').getroot().iter('testcase'))
assert len(cases) == 26
assert all(not list(case.iter(tag)) for case in cases for tag in ('failure', 'error', 'skipped'))
ancestry = json.loads((out / 'ancestry.json').read_text())
gates = json.loads((out / 'gate-probe.json').read_text())
assert len(ancestry['integrations']) == 32
assert set(ancestry['absent_m3_integrations']) == {'KL-028', 'KL-029'}
for gate in gates:
    assert gate['committed_plan_prefix_call']['errors'] == []
    assert set(gate['errors']) == {'git-worktree-not-clean', 'governance-required-reviews-not-pass:HG-044'}
(out / 'assessment.md').write_text('''Protocol review PASS for cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54, protected base 2c44f456a0daf8e6933f20fc3eadc7e1869d6fff, selected tested revision 06dab6dbb38221e7111c18811cb20b42b8cc2397. No BLOCKER, REQUIRED_FOLLOWUP, or NONBLOCKING findings; no SPEC_CHANGE_REQUIRED.

Independently inspected the full scoped source, schema, M3 contract, bounded plan addendum and derived authority diff. The 319 exact declared paths are regular Git blobs in HG044's scope. The validator's pre-existing executable mode is retained. All 70 existing functions other than the authorized governance allowlist and validate entrypoint remain byte-identical, including M1/M2/integration/HG043 provenance validators. M1/M2 schema branches and existing definitions are structurally identical. Frozen Protocol/DB/baseline, provider Integration Spec, product requirement state, runtime/migrations, DB tests, CI, peer packets/backlog/traceability and closure/integration instances are unchanged. Every indexed/manifest hash matches its reviewed Git blob. The plan's protected prefix is byte-preserved and the appended mapping block is pinned.

The exact 16 active M3 identities, M1 KL074 support and recursively validated M2/M1 prerequisite are kept distinct. Independently validated 32 available transitive integration chains with exact result/review/merge bindings and prerequisite merges before both consumer base and tested SHA, explicitly including KL078→KL076 and KL079→KL077. KL028 and KL029 integration records are absent at the reviewed revision; task status or synthetic fixtures supply neither MERGED nor actual closure. A first reviewer probe incorrectly expected only KL029 absent; its assertion traceback is preserved separately, the expectation was corrected against Git, and the corrected full audit passed.

All 52 mapped named check contracts match their canonical digests. Their original reach and oracles preserve actual full F/D/N owner trajectory and F2 repair, lifecycle-valid current T7 denials and immutable START/resume history, both ordered DC contenders, registry gate→S01 lock order, T2-GLOBAL successful-commit linearization without effective_at backdating/scheduling, relevant/transitive vs unrelated revoke, validity minimum/missing/TIMELESS policy, READY/SEALED barriers and truthful strict-ingress/registration/T7/evaluation-storage distinctions. No provider command authority, planned-to-actual substitution, owner bypass, external wait inside a coordination transaction, or change to T1–T8 is introduced.

All 31 B rows and 10 I dispositions remain exact. Nineteen planned executable B rows require integrated named evidence; 12 deferred rows remain NOT_RUN, including full B04@DC reauthorization despite mandatory guard support, eight API/workflow/DB/eligibility/rendering E2E rows, B11/B12 pure-evaluator PU and B14@WF. I04@WF remains NOT_RUN. PU equality does not become PG equality or WF/E2E; historical archived evaluation inputs do not become shadow-owner outputs. Product claims remain empty, historical model reproducibility false, production activation/shadow execution false, and shadow usability/R04 E2E NOT_RUN. No M3→M4 or KL029→KL045 cycle or downstream release waiver appears.

The independent 26-case bounded run passed, covering the positive synthetic complete Git chain, production/shadow/product overclaim rejection, deferred-layer preservation, omission of each multiselect suite, genuine pytest bracketed parameter IDs (including :: and disposition-like text), dependency order, M1/M2 schema preservation, plan guard and real-Git protected-prefix positive/negative/ambient-source cases. Both ordinary and review-only actual validate branches executed the committed base/reviewed prefix guard successfully; their only errors were the expected pending-review/dirty-bookkeeping conditions, not merge PASS. The original optional-target TypeError and repaired diagnostic remain failed/unselected records. Selected implementation evidence at 06dab6d retains exact hashes and 90 focused/880 harness/241 unit PASS plus lint/type/validation/scope/source_diff PASS; it was independently inspected, not relabelled as newly executed reviewer evidence. No full suite, database, Docker or foreign namespace was run by this reviewer.

The scoped source whitespace check passes across every protected-base path except the own review-record directory. The broad check retains its FAIL: 308 warnings are confined to eight historical raw diff/pytest/whitespace capture files in that directory. Literal diff context, nested diagnostic and failed pytest formatting bytes are review evidence; they are not implementation whitespace. This explicit task-scoped source_diff exception is acceptable here with raw bytes, schema/provenance and SHA/suffix checks preserved; it is not a general whitespace waiver or a broad-check PASS. Inventories store exact Git object/hash identities without recursive historical blob copies. A clean final exact-head merge gate and applicable unchanged hosted CI remain separate coordinator obligations; this protocol PASS creates no merge, product or release fact.
''')
refs = ['audit.json', 'path-inventory.json', 'bounded-source-diff.patch', 'check-contracts.json',
        'boundary-ledger.json', 'selected-evidence.json', 'derived-hashes.json', 'ancestry.json',
        'gate-probe.json', 'whitespace.json', 'bounded.xml', 'bounded-tool-result.json', 'assessment.md']
inventory = []
for path in sorted(out.rglob('*')):
    if path.is_file():
        data = path.read_bytes()
        inventory.append(dict(path=str(path.relative_to(root)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
(out / 'capture-integrity.json').write_text(json.dumps(inventory, indent=2) + '\n')
record = dict(task_identity='harness-governance-v0.1/HG-044',
    reviewed_head_sha='cf0b99359d04c136d01fd4c5eeec8a23cd0bbc54', review_type='PROTOCOL',
    status='PASS', findings=[], review_contract_version='v0.2',
    evidence_refs=['docs/exec-plans/governance/HG-044.yaml', 'docs/harness/M3_CLOSURE_CONTRACT.md'] +
        ['docs/exec-plans/reviews/HG-044/PROTOCOL-r6-raw/' + ref for ref in refs + ['capture-integrity.json']])
jsonschema.Draft202012Validator(json.loads((root / 'THREAD_REVIEW.schema.json').read_text())).validate(record)
(out.parent / 'PROTOCOL.json').write_text(json.dumps(record, indent=2) + '\n')
print('Schema-valid exact-SHA independent PROTOCOL review: PASS; 26 bounded cases')
