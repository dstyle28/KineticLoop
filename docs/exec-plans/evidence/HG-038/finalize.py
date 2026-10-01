"""Apply HG038 only after the actual KL074 normal merge barrier is satisfied."""
import hashlib
import importlib.util
import json
import pprint
import subprocess
from pathlib import Path

ROOT = Path.cwd()
HERE = ROOT / 'docs/exec-plans/evidence/HG-038'


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


base = git('rev-parse', 'origin/master')
assert git('branch', '--show-current') == 'codex/hg038-m3-next-wave'
subprocess.run(['git', 'merge-base', '--is-ancestor', base, 'HEAD'], check=True)
assert all(p.startswith('docs/exec-plans/evidence/HG-038/') for p in git('diff', '--name-only', base, 'HEAD').splitlines())
pr = json.loads((HERE / 'pr72-merged.json').read_text())
assert pr['state'] == 'MERGED' and not pr['isDraft']
merge = pr['mergeCommit']['oid']
assert len(git('rev-list', '--parents', '-n', '1', merge).split()) == 3
subprocess.run(['git', 'merge-base', '--is-ancestor', merge, base], check=True)
assert (ROOT / 'docs/exec-plans/completed/KL-074_RESULT.yaml').exists()
assert '127.0.0.1' in (ROOT / 'src/kineticloop/db/lifecycle.py').read_text()
assert (ROOT / '.github/workflows/kl074-readiness.yml').read_bytes() == (ROOT / 'docs/exec-plans/evidence/HG-037/kl074-readiness.workflow.proposal.yml').read_bytes()
(HERE / 'protected-base.txt').write_text(base + '\n')
b = json.loads((ROOT / 'KineticLoop_Harness_Backlog_v0.2.json').read_text())
names = ['KL-026', 'KL-027', 'KL-075', 'KL-076', 'KL-077']
drafts = {n: json.loads((HERE / f'{n}.definition.draft.json').read_text()) for n in names}
existing = {t['id']: t for t in b['tasks']}
for name in names:
    for path in [f'docs/exec-plans/completed/{name}_RESULT.yaml', f'docs/exec-plans/completed/{name}_RESULT.json', f'docs/exec-plans/reviews/{name}', f'docs/exec-plans/integrations/{name}.json']:
        assert not (ROOT / path).exists(), path
    if name in {'KL-026', 'KL-027'}:
        assert existing[name]['status'] == 'NOT_STARTED'
        b['tasks'][next(i for i,t in enumerate(b['tasks']) if t['id'] == name)] = drafts[name]
    else:
        assert name not in existing
        b['tasks'].append(drafts[name])
    (ROOT / f'docs/exec-plans/active/{name}.md').write_bytes((HERE / f'{name}.packet.draft.md').read_bytes())
b['task_count'] = len(b['tasks'])
b['active_task_count'] = sum(t['status'] != 'SUPERSEDED' for t in b['tasks'])
(ROOT / 'KineticLoop_Harness_Backlog_v0.2.json').write_text(json.dumps(b, indent=2) + '\n')

vp = ROOT / 'tools/harness/validate_harness.py'
s = vp.read_text()
s = s.replace("WAVE_REFINED_TASK_IDS | {'KL-019', 'KL-025', 'KL-074'}", "WAVE_REFINED_TASK_IDS | {'KL-019', 'KL-025', 'KL-074', 'KL-026', 'KL-027', 'KL-075', 'KL-076', 'KL-077'}")
s = s.replace('    errors.extend(readiness_packet_errors(task, text))', '    errors.extend(m3_next_wave_packet_errors(task, text))\n    errors.extend(readiness_packet_errors(task, text))')
s = s.replace('        errors.extend(readiness_definition_errors(task))', '        errors.extend(m3_next_wave_definition_errors(task))\n        errors.extend(readiness_definition_errors(task))')
s = s.replace("WAVE_REFINED_TASK_IDS | {'KL-047', 'KL-074'}", "WAVE_REFINED_TASK_IDS | {'KL-047', 'KL-074', 'KL-026', 'KL-027', 'KL-075', 'KL-076', 'KL-077'}")
guard = (HERE / 'guard.draft.py').read_text()
hashes = {n: hashlib.sha256(json.dumps(t, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest() for n,t in drafts.items()}
packet_hashes = {n: hashlib.sha256((HERE / f'{n}.packet.draft.md').read_bytes()).hexdigest() for n in names}
guard = guard.replace('None  # ratified from drafts', pprint.pformat(hashes), 1)
guard = guard.replace('None  # ratified from drafts', pprint.pformat(packet_hashes), 1)
s = s.replace("if __name__ == '__main__':\n    sys.exit(main())", '')
s += '\n' + guard + "\n\nif __name__ == '__main__':\n    sys.exit(main())\n"
vp.write_text(s)
(ROOT / 'tests/harness/test_m3_next_wave_scope.py').write_bytes((HERE / 'test_m3_next_wave_scope.draft.py').read_bytes())
spec = importlib.util.spec_from_file_location('hg038_validator', vp)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
p = ROOT / 'KineticLoop_Harness_Traceability_v0.3.json'
tr = json.loads(p.read_text())
tr['tasks'] = [v.traceability_projection(drafts[t['id']]) if t['id'] in drafts else t for t in tr['tasks']]
tr['tasks'].extend(v.traceability_projection(drafts[n]) for n in names[2:])
p.write_text(json.dumps(tr, indent=2) + '\n')
p = ROOT / 'docs/harness/RESOURCE_LOCKS.md'
p.write_text(p.read_text() + '\n- `protocol_interleaving_suite`\n- `test_only_demo_suite`\n\nHG038 gives KL026 and KL027 tests-only suites independent task-owned databases. These resources grant no production owner writes. KL075/076/077 serialize transaction_interfaces and user_coordination; merged dependencies and exact write paths remain mandatory.\n')
p = ROOT / '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md'
p.write_text(p.read_text() + '''

## M3 remaining wave — HG038

KL026 owns tests-only real PostgreSQL I01–I09 DC interleavings over merged owners,
with exact task-owned namespace and no production-fix permission. I04@WF remains
separate. KL075 implements internal guarded RecordSnapshot/AdvanceAttempt only;
KL076 supplies deterministic TEST source-bound F/D/N/resolution/validation owners;
KL077 consumes complete TEST bundle preparation and current CONTINUE/RESUME guards.
They serialize shared transaction interfaces, preserve the 39 public commands and
start NOT_STARTED. KL027 waits for these normally merged prerequisites and owns
only the composed deterministic TEST trajectory suite. KL026 may proceed alongside
owner tasks using merged interfaces and nonoverlapping resources. No M3 closure,
product requirement, release, production activation or executable shadow PASS is
established by this governance refinement. Missing product/model quality and policy
decisions remain outside these exact mechanical TEST fixture packets.
''')
for n,t in drafts.items():
    assert v.m3_next_wave_definition_errors(t) == []
    assert v.packet_errors(t, (ROOT / f'docs/exec-plans/active/{n}.md').read_text()) == []
print('KL074_NORMAL_MERGE', merge, 'protected_base', base)
