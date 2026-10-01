"""Ratify HG037 only after verifying real HG036 normal merge ancestry."""
import hashlib
import importlib.util
import json
import pprint
import subprocess
from pathlib import Path

ROOT = Path.cwd()
HERE = ROOT / 'docs/exec-plans/evidence/HG-037'
def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()
base = git('rev-parse', 'HEAD')
assert git('branch', '--show-current') == 'codex/hg037-postgres-readiness-packet'
assert base == git('rev-parse', 'origin/master'), 'must rebase/fetch actual master first'
record = ROOT / 'docs/exec-plans/governance/HG-036.yaml'
assert record.exists(), 'HG036 has not merged'
merge = git('log', '--format=%H', '--merges', '--grep=Merge pull request.*hg036', '-1')
assert merge and len(git('rev-list', '--parents', '-n', '1', merge).split()) == 3
subprocess.run(['git', 'merge-base', '--is-ancestor', merge, base], check=True)
(HERE / 'protected-base.txt').write_text(base+'\n')
t = json.loads((HERE / 'KL-074.task-definition.draft.json').read_text())
b = json.loads((ROOT / 'KineticLoop_Harness_Backlog_v0.2.json').read_text())
assert not any(x['id'] == 'KL-074' or x['task_identity'] == t['task_identity'] for x in b['tasks'])
for p in ['docs/exec-plans/completed/KL-074_RESULT.yaml','docs/exec-plans/completed/KL-074_RESULT.json','docs/exec-plans/reviews/KL-074','docs/exec-plans/integrations/KL-074.json']:
    assert not (ROOT / p).exists(), p
b['tasks'].append(t)
b['task_count'] = len(b['tasks'])
b['active_task_count'] = sum(x['status'] != 'SUPERSEDED' for x in b['tasks'])
(ROOT / 'KineticLoop_Harness_Backlog_v0.2.json').write_text(json.dumps(b,indent=2)+'\n')
(ROOT / 'docs/exec-plans/active/KL-074.md').write_bytes((HERE / 'KL-074.packet.draft.md').read_bytes())
path = ROOT / 'tools/harness/validate_harness.py'
s = path.read_text()
s = s.replace("WAVE_REFINED_TASK_IDS | {'KL-019', 'KL-025'}", "WAVE_REFINED_TASK_IDS | {'KL-019', 'KL-025', 'KL-074'}")
s = s.replace('    errors.extend(execution_packet_errors(task, text))', '    errors.extend(readiness_packet_errors(task, text))\n    errors.extend(execution_packet_errors(task, text))')
s = s.replace('        for dep in task[\'depends_on\']:', '        errors.extend(readiness_definition_errors(task))\n        for dep in task[\'depends_on\']:')
s = s.replace('def task_fixture_scope_errors(root, base, head, task_id, changed):', '''def task_fixture_scope_errors(root, base, head, task_id, changed):
    if task_id == 'KL-074':
        errors = []
        for path in ('compose.yaml', 'src/kineticloop/db/lifecycle.py'):
            if path in changed:
                errors.extend(readiness_content_errors(
                    path, git(root, 'show', base + ':' + path),
                    git(root, 'show', head + ':' + path)))
        return errors''')
guard = (HERE / 'guard.draft.py').read_text()
guard = guard.replace('READINESS_TASK_DEFINITION = None  # filled from ratified proposal', 'READINESS_TASK_DEFINITION = '+pprint.pformat(t,width=98,sort_dicts=False))
guard = guard.replace('READINESS_PACKET_BOUNDARIES = None  # filled from ratified proposal', 'READINESS_PACKET_BOUNDARIES = '+pprint.pformat(json.loads((HERE/'boundaries.draft.json').read_text()),width=98,sort_dicts=False))
s += '\n'+guard
# Functions/constants must exist before CLI invocation.
s = s.replace("if __name__ == '__main__':\n    sys.exit(main())", '')
s += "\n\nif __name__ == '__main__':\n    sys.exit(main())\n"
path.write_text(s)
(ROOT/'tests/harness/test_readiness_scope.py').write_bytes((HERE/'test_readiness_scope.draft.py').read_bytes())
spec = importlib.util.spec_from_file_location('hg037_validator', path)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
trp = ROOT/'KineticLoop_Harness_Traceability_v0.3.json'
tr = json.loads(trp.read_text()); tr['tasks'].append(v.traceability_projection(t)); trp.write_text(json.dumps(tr,indent=2)+'\n')
rp = ROOT/'docs/harness/RESOURCE_LOCKS.md'
rp.write_text(rp.read_text()+'\n- `postgres_lifecycle`\n\n`postgres_lifecycle` serializes the concrete lifecycle/Compose readiness writers; it does not grant transaction, migration or shared-database authority. KL074 must use task-owned coldstart namespaces and dedicated hosted VM regression Docker.\n')
assert v.readiness_definition_errors(t) == []
assert v.packet_errors(t,(ROOT/'docs/exec-plans/active/KL-074.md').read_text()) == []
print('HG036_MERGED', merge, 'protected_base',base)
