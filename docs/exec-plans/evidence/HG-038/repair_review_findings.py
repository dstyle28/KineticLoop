"""Apply HG038's own unmerged packet repairs; preserve original rejected evidence."""
import hashlib
import importlib.util
import json
import pprint
import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
HERE = ROOT / 'docs/exec-plans/evidence/HG-038'
names = ['KL-026', 'KL-027', 'KL-075', 'KL-076', 'KL-077']
assert subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip() == 'codex/hg038-m3-next-wave'
subprocess.run(['python3', str(HERE / 'draft.py')], check=True)
drafts = {n: json.loads((HERE / f'{n}.definition.draft.json').read_text()) for n in names}
p = ROOT / 'KineticLoop_Harness_Backlog_v0.2.json'
backlog = json.loads(p.read_text())
for n in names:
    assert next(t for t in backlog['tasks'] if t['id'] == n)['status'] == 'NOT_STARTED'
    assert not (ROOT / f'docs/exec-plans/completed/{n}_RESULT.yaml').exists()
backlog['tasks'] = [drafts.get(t['id'], t) for t in backlog['tasks']]
p.write_text(json.dumps(backlog, indent=2) + '\n')
for n in names:
    (ROOT / f'docs/exec-plans/active/{n}.md').write_bytes((HERE / f'{n}.packet.draft.md').read_bytes())
vp = ROOT / 'tools/harness/validate_harness.py'
s = vp.read_text()
for variable, hashes in [
    ('M3_NEXT_WAVE_DEFINITION_HASHES', {n: hashlib.sha256(json.dumps(t, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest() for n, t in drafts.items()}),
    ('M3_NEXT_WAVE_PACKET_HASHES', {n: hashlib.sha256((HERE / f'{n}.packet.draft.md').read_bytes()).hexdigest() for n in names}),
]:
    s, count = re.subn(variable + r' = \{.*?\}', lambda _: variable + ' = ' + pprint.pformat(hashes), s, flags=re.S)
    assert count == 1
vp.write_text(s)
(ROOT / 'tests/harness/test_m3_next_wave_scope.py').write_bytes((HERE / 'test_m3_next_wave_scope.draft.py').read_bytes())
spec = importlib.util.spec_from_file_location('hg038_validator', vp)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
p = ROOT / 'KineticLoop_Harness_Traceability_v0.3.json'
trace = json.loads(p.read_text())
trace['tasks'] = [v.traceability_projection(drafts[t['id']]) if t['id'] in drafts else t for t in trace['tasks']]
p.write_text(json.dumps(trace, indent=2) + '\n')
for n in names:
    assert v.m3_next_wave_definition_errors(drafts[n]) == []
    assert v.packet_errors(drafts[n], (ROOT / f'docs/exec-plans/active/{n}.md').read_text()) == []
subprocess.run(['python3', str(HERE / 'refresh_hashes.py')], check=True)
print('HG038_REVIEW_FINDINGS_REPAIRED')
