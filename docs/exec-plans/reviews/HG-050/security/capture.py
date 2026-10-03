"""Capture already executed reviewer outputs losslessly, without rerunning tests."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location('review_capture', ROOT / 'tools/harness/compact_evidence.py')
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)
SHA = '26482f7f7147fe33cf37d8028574196c97c82ec6'
PREFIX = 'docs/exec-plans/reviews/HG-050/security/raw/'
FOCUSED = '.venv/bin/python -m pytest tests/harness/test_local_gate.py -q --basetemp=/private/tmp/hg050-security-review-pytest --junitxml=/private/tmp/hg050-security-review-focused.xml'
ADDITIONAL = '.venv/bin/python -m pytest docs/exec-plans/reviews/HG-050/security/probes.py -q --basetemp=/private/tmp/hg050-security-additional-pytest --junitxml=/private/tmp/hg050-security-additional.xml'
AUDIT = '.venv/bin/python docs/exec-plans/reviews/HG-050/security/audit.py'
for name, source, command, status in [
    ('focused-junit', '/private/tmp/hg050-security-review-focused.xml', FOCUSED, 0),
    ('additional-log', '/private/tmp/hg050-security-additional.log', ADDITIONAL, 0),
    ('additional-junit', '/private/tmp/hg050-security-additional.xml', ADDITIONAL, 0),
    ('audit-initial', '/private/tmp/hg050-security-audit.log', AUDIT, 1),
    ('audit-final', '/private/tmp/hg050-security-audit-final.log', AUDIT, 0),
]:
    ce.capture(ROOT, PREFIX + name + '.json', Path(source).read_bytes(), SHA,
               command, status, None)
