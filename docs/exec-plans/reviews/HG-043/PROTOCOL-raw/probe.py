"""Independent absent-path boundary probe for reviewed HG043 2896d24."""
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location(
    'provenance_fixture', ROOT / 'tests/harness/test_review_evidence_provenance.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
cases = []
for kind in ('symlink', 'directory'):
    with tempfile.TemporaryDirectory(prefix='hg043-protocol-') as temp:
        history = fixture.History(Path(temp))
        ref = fixture.OWN + 'existing'
        path = history.root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == 'symlink':
            path.symlink_to('../../../evidence/KL-001/check.log')
        else:
            history.put(ref + '/child')
        history.reviewed = history.commit('preexisting nonregular review path')
        original = fixture.v.git(history.root, 'ls-tree', '-z', history.reviewed, '--', ref).decode()
        if kind == 'symlink':
            path.unlink()
        else:
            (path / 'child').unlink()
            path.rmdir()
        history.put(ref, 'review-created replacement\n')
        review = history.review([ref])
        cases.append({
            'kind': kind, 'reference': ref, 'at_reviewed_entry': original,
            'at_review_record_entry': fixture.v.git(history.root, 'ls-tree', '-z', review, '--', ref).decode(),
            'strict_suffix_errors': fixture.v.suffix_errors(
                history.root, history.reviewed, review, 'KL-001', 'review'),
            'integration_errors': history.errors(review),
        })
print(json.dumps({
    'reviewed_head_sha': '2896d2422999fdf8a2cbca75eb316798c015ad17',
    'probe': 'Existing nonregular entries cannot use the absent-reference exception',
    'cases': cases,
}, indent=2))
