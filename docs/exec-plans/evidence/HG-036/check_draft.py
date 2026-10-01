"""Prospective draft consistency only; no implementation or shared metadata edit."""
import importlib.util
import json
from pathlib import Path

root = Path.cwd()
spec = importlib.util.spec_from_file_location('v', root / 'tools/harness/validate_harness.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
t = json.loads((root/'docs/exec-plans/evidence/HG-036/KL047_definition_draft.json').read_text())
p = (root/'docs/exec-plans/evidence/HG-036/KL047_packet_draft.md').read_text()
assert v.packet_errors(t,p) == [], v.packet_errors(t,p)
assert v.bullets(v.section(p,'Read first')) == t['context_files']
assert v.bullets(v.section(p,'Entry conditions')) == t['entry_conditions']
assert v.bullets(v.section(p,'Deliverables')) == t['deliverables']
assert v.section(p,'Definition of Done').strip() == t['definition_of_done']
for path in t['context_files']:
    assert (root/path).is_file(), path
assert len(t['write_paths']) == len(set(t['write_paths'])) == 10
assert all('*' not in path for path in t['write_paths'])
assert t['review_requirements'] == ['GENERAL','PROTOCOL']
print('PASS draft packet projection/context/exact write list/check-contract paths; all prospective checks NOT_RUN')
