"""Bounded before/after read-call benchmark; never substitute timing for integrity proof."""
import collections
import importlib.util
import json
import subprocess
import time
import types
from pathlib import Path

root = Path(__file__).resolve().parents[4]
before_sha = '070f94fee7d76b8e76d10a681f0a5db1c5a9e2b5'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root).strip()
source = subprocess.check_output(['git', 'show', before_sha + ':tools/harness/compact_evidence.py'], cwd=root)
before = types.ModuleType('before')
exec(compile(source, before_sha + '/compact_evidence.py', 'exec'), before.__dict__)
spec = importlib.util.spec_from_file_location('validator', root / 'tools/harness/validate_harness.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
after = validator.compact_evidence
records = []
for label, revision, ref in (
        ('small_plain', '994cf425360c75a366f186e91857a5d75ed02ebe',
         'docs/exec-plans/evidence/KL-028/checks-debd5e5/boundary_namespace_pu.log'),
        ('large_plain', '994cf425360c75a366f186e91857a5d75ed02ebe',
         'docs/exec-plans/evidence/KL-028/checks-debd5e5/boundary_full_db_suite.log'),
        ('compact', before_sha,
         'docs/exec-plans/evidence/HG-047/development-ab4f21b/source_diff.json')):
    row = {'label': label, 'bound_revision': revision, 'ref': ref, 'repeats': 5}
    for phase, module in [('before', before), ('after', after)]:
        calls = collections.Counter()
        original = module.git
        def counted(root, *args):
            calls[' '.join(args[:2])] += 1
            return original(root, *args)
        module.git = counted
        start = time.monotonic()
        try:
            with validator.evidence_validation_session():
                for _ in range(row['repeats']):
                    if phase == 'before':
                        module.read(root, ref, revision)
                    else:
                        assert validator.evidence_exists(root, ref, revision)
        finally:
            module.git = original
        row[phase] = {'git_calls': sum(calls.values()), 'operations': dict(calls),
                      'monotonic_seconds': time.monotonic() - start}
    assert row['after']['git_calls'] < row['before']['git_calls']
    records.append(row)
print(json.dumps({'baseline_source': before_sha, 'current_source': head,
                  'status': 'PASS', 'measurements': records}, indent=2))
