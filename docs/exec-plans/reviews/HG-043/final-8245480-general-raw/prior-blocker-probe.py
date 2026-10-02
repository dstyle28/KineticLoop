"""Independently rerun the rejected GENERAL reproduction at the final exact SHA."""
import importlib.util
import json
import subprocess
import tempfile
import types
from pathlib import Path

ROOT = Path.cwd()
HEAD = '8245480918251739339987de69bfe41fa0b39af5'
source = subprocess.check_output(['git', 'show', HEAD + ':tools/harness/validate_harness.py'])
validator = types.ModuleType('exact_reviewed_validator')
validator.__file__ = str(ROOT / 'tools/harness/validate_harness.py')
exec(compile(source, validator.__file__, 'exec'), validator.__dict__)
spec = importlib.util.spec_from_file_location('review_fixture', ROOT / 'tests/harness/test_review_evidence_provenance.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
fixtures.v = validator
report = {'reviewed_head_sha': HEAD, 'finding': 'RESOLVED',
          'contract': 'Fallback is allowed only for references absent at the reviewed revision.',
          'validator_source_blob': subprocess.check_output(['git', 'rev-parse', HEAD + ':tools/harness/validate_harness.py'], text=True).strip(),
          'cases': []}
for kind in ('symlink', 'directory'):
    with tempfile.TemporaryDirectory(prefix='hg043-general-nonregular-') as temp:
        history = fixtures.History(Path(temp))
        ref = fixtures.OWN + 'independent.log'
        target = history.root / ref
        if kind == 'symlink':
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to('../../../evidence/KL-001/check.log')
        else:
            history.put(ref + '/child.log')
        history.reviewed = history.commit('nonregular entry exists at reviewed head')
        reviewed_entry = history.git('ls-tree', '-z', history.reviewed, '--', ref)
        if kind == 'symlink':
            target.unlink()
        else:
            (target / 'child.log').unlink()
            target.rmdir()
        history.put(ref, 'replacement regular reviewer log\n')
        endpoint = history.review([ref])
        errors = history.errors(endpoint)
        suffix = validator.suffix_errors(history.root, history.reviewed, endpoint, 'KL-001', 'review')
        assert reviewed_entry, 'The reference must actually exist at the reviewed revision.'
        assert not validator.revision_regular_file(history.root, ref, history.reviewed)
        assert validator.revision_regular_file(history.root, ref, endpoint)
        assert suffix == []
        assert errors == ['integration-review-evidence:KL-001:GENERAL:' + ref], errors
        report['cases'].append({'kind_at_reviewed': kind, 'reference': ref,
                               'reviewed_entry': reviewed_entry,
                               'review_record_entry': history.git('ls-tree', '-z', endpoint, '--', ref),
                               'strict_suffix_errors': suffix,
                               'actual_integration_errors': errors,
                               'expected': 'integration-review-evidence rejection because reference was present but nonregular at reviewed SHA'})
print(json.dumps(report, indent=2))
