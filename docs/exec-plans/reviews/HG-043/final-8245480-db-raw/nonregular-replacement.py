"""Reproduce the exact reviewed revision's nonregular-path fallback mismatch."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import types

ROOT = Path.cwd()
HEAD = '8245480918251739339987de69bfe41fa0b39af5'
OUT = ROOT / 'docs/exec-plans/reviews/HG-043/final-8245480-db-raw'
source = subprocess.check_output(['git', 'show', HEAD + ':tools/harness/validate_harness.py'])
validator = types.ModuleType('exact_reviewed_validator')
validator.__file__ = str(ROOT / 'tools/harness/validate_harness.py')
exec(compile(source, validator.__file__, 'exec'), validator.__dict__)
spec = importlib.util.spec_from_file_location('fixture', ROOT / 'tests/harness/test_review_evidence_provenance.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.v = validator
report = []
for mode in ('symlink', 'tree', 'gitlink'):
    with tempfile.TemporaryDirectory(prefix='hg043-db-review-edge-') as tmp:
        history = fixture.History(Path(tmp))
        ref = fixture.OWN + 'replaced-evidence'
        target = history.root / ref
        if mode == 'symlink':
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to('../../../evidence/KL-001/check.log')
            history.reviewed = history.commit('nonregular evidence before review')
            target.unlink()
        elif mode == 'tree':
            child = history.put(ref + '/child')
            history.reviewed = history.commit('nonregular evidence before review')
            child.unlink()
            target.rmdir()
        else:
            history.git('update-index', '--add', '--cacheinfo', '160000,' + history.base + ',' + ref)
            history.git('commit', '-qm', 'gitlink evidence before review')
            history.reviewed = history.git('rev-parse', 'HEAD')
        history.put(ref, 'reviewer-created replacement blob\n')
        record = history.review([ref])
        errors = history.errors(record)
        entry_before = history.git('ls-tree', '-z', history.reviewed, '--', ref)
        entry_after = history.git('ls-tree', '-z', record, '--', ref)
        assert entry_before and not validator.revision_regular_file(history.root, ref, history.reviewed)
        assert validator.revision_regular_file(history.root, ref, record)
        assert validator.suffix_errors(history.root, history.reviewed, record, 'KL-001', 'review') == []
        assert errors == ['integration-review-evidence:KL-001:GENERAL:' + ref], errors
        report.append({'mode': mode, 'reference': ref, 'reviewed': history.reviewed,
                       'review_record': record, 'entry_at_reviewed': entry_before,
                       'entry_at_review_record': entry_after,
                       'integration_errors': errors, 'expected': 'integration-review-evidence rejection: referenced path existed as nonregular at reviewed SHA; contract permits later fallback only for an absent path'})
(OUT / 'nonregular-replacement.json').write_text(json.dumps({
    'reviewed_head_sha': HEAD, 'result': 'PRIOR_BLOCKER_CLOSED',
    'cases': report}, indent=2) + '\n')
print(json.dumps({'reviewed_head_sha': HEAD, 'rejected_replacement_modes': [r['mode'] for r in report]}))
