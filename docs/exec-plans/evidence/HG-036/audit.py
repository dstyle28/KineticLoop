"""Revision-bound HG036 exact protected-state, merged preflight and scope audit."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path.cwd()
parser = argparse.ArgumentParser()
parser.add_argument('base_commit')
base = parser.parse_args().base_commit
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
print('protected_base_commit=' + base)
print('tested_commit=' + head)
subprocess.run(['git', 'merge-base', '--is-ancestor', base, head], check=True)
for path in ['FROZEN_BASELINE.json', '05_KineticLoop_Protocol_v1.2_FROZEN.md',
             '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md', 'src', 'migrations',
             'tests/unit', 'tests/db', 'tests/evaluation', '.github', '.agents',
             'CURRENT_REQUIREMENT_SET.json', 'KineticLoop_Acceptance_Spec_v1.2.2.json',
             'KineticLoop_Integration_Acceptance_v0.1.json',
             'KineticLoop_Evidence_Manifest_v0.1.json', 'docs/contracts',
             'docs/exec-plans/completed', 'docs/exec-plans/integrations',
             'docs/exec-plans/milestones', 'docs/exec-plans/active/KL-019.md',
             '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md']:
    subprocess.run(['git', 'diff', '--exit-code', base, head, '--', path], check=True)
print('PASS frozen/product/completed/requirement/gates/KL019/CI/provider paths unchanged')
for path in ['KineticLoop_Harness_Backlog_v0.2.json', 'KineticLoop_Harness_Traceability_v0.3.json']:
    old = json.loads(subprocess.check_output(['git', 'show', base + ':' + path]))
    new = json.loads((ROOT/path).read_text())
    assert {k:v for k,v in old.items() if k != 'tasks'} == {k:v for k,v in new.items() if k != 'tasks'}
    assert [t for t in old['tasks'] if t['id'] != 'KL-047'] == [t for t in new['tasks'] if t['id'] != 'KL-047']
    before = next(t for t in old['tasks'] if t['id'] == 'KL-047')
    after = next(t for t in new['tasks'] if t['id'] == 'KL-047')
    assert before['status'] == after['status'] == 'NOT_STARTED'
    assert before['depends_on'] == after['depends_on'] == ['KL-005','KL-018']
    assert before['review_requirements'] == after['review_requirements'] == ['GENERAL','PROTOCOL']
    assert before['requirements_covered'] == after['requirements_covered'] == []
print('PASS only KL047 refined; no new identity, no retrospective mutation or review/gate weakening')
subprocess.run(['/private/tmp/kl017-venv/bin/python', 'docs/exec-plans/evidence/HG-036/preflight.py'], check=True)
subprocess.run(['/private/tmp/kl017-venv/bin/python', 'docs/exec-plans/evidence/HG-036/check_draft.py'], check=True)
proposal = json.loads((ROOT/'docs/exec-plans/evidence/HG-036/KL047_definition_draft.json').read_text())
actual = next(t for t in json.loads((ROOT/'KineticLoop_Harness_Backlog_v0.2.json').read_text())['tasks'] if t['id'] == 'KL-047')
assert proposal == actual
assert (ROOT/'docs/exec-plans/active/KL-047.md').read_bytes() == (ROOT/'docs/exec-plans/evidence/HG-036/KL047_packet_draft.md').read_bytes()
print('PASS exact proposal ratification; future checks remain NOT_RUN')
print('EXACT_PROTECTED_BASE_TO_TESTED_INVENTORY')
print(subprocess.check_output(['git','diff','--name-status',base,head], text=True))
print('TESTED_TREE=' + subprocess.check_output(['git','rev-parse',head+'^{tree}'],text=True).strip())
