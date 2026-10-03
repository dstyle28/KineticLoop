"""Protected-base exact governance scope, immutable authorities and historical tasks."""
import json
import subprocess
from pathlib import Path

from tools.harness.validate_harness import governance_allowed_patterns, matches

root = Path.cwd()
base = '26906bd7f4444914c228e98377f2b164fee0dd5d'
head = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
def blob(path, revision):
    return subprocess.check_output(['git','show',revision+':'+path])
changed = subprocess.check_output(['git','diff','--name-only',base,head],text=True).splitlines()
assert changed and all(matches(p,governance_allowed_patterns('HG-045')) for p in changed)
frozen = json.loads(blob('FROZEN_BASELINE.json',base))
for path in ['FROZEN_BASELINE.json',*[e['path'] for e in frozen['files']]]:
    assert blob(path,head) == blob(path,base), path
before = json.loads(blob('KineticLoop_Harness_Backlog_v0.2.json',base))
after = json.loads(blob('KineticLoop_Harness_Backlog_v0.2.json',head))
assert after['tasks'][:-1] == before['tasks']
assert after['tasks'][-1]['id'] == 'KL-080' and after['tasks'][-1]['status'] == 'NOT_STARTED'
assert after['tasks'][-1]['evidence_refs'] == after['tasks'][-1]['requirements_covered'] == []
assert not any(p.startswith(('src/','tests/db/','tests/unit/','tests/fixtures/',
                             'docs/exec-plans/completed/')) for p in changed)
assert 'docs/exec-plans/milestones/M3.json' not in changed
print(json.dumps(dict(protected_base=base,tested_commit=head,scope='PASS',frozen='UNCHANGED',
                     historical_task_definitions='BYTE_EQUIVALENT_VALUES',
                     future_checks='NOT_RUN',product_pass_claims=[],changed=changed),indent=2))
