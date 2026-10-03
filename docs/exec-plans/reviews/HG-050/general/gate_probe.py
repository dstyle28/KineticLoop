"""Independent fake Git governance probe; no live credentials or network."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location('review_fixtures', ROOT / 'tests/harness/test_validator.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
rows = []
for omitted in (None, 'GENERAL', 'SECURITY_DATA_BOUNDARY'):
    fixture = fixtures.ValidatorTests()
    fixture.setUp()
    try:
        fixture.put('tools/harness/github_app.py', '# deterministic prospective correction\n')
        fixtures.refresh(fixture.root)
        tested = fixture.commit('fake client correction')
        fixture.persist_governance_change('HG-050', tested, [], ['GENERAL', 'SECURITY_DATA_BOUNDARY'])
        if omitted:
            (fixture.root / ('docs/exec-plans/reviews/HG-050/' + omitted + '.json')).unlink()
            fixture.commit('omit mandatory reviewer')
        args = ('--ci-pr-base', fixture.base, '--ci-pr-head', 'HEAD')
        fixture.check(1 if omitted else 0,
                      'ci-general-review-missing:HG-050' if omitted == 'GENERAL' else
                      'governance-required-reviews-not-pass:HG-050' if omitted else '', *args)
        rows.append({'omitted': omitted, 'expected_exit': 1 if omitted else 0, 'verified': True})
    finally:
        fixture.doCleanups()
expected = ['CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
            'tools/harness/github_app.py', 'tests/harness/test_local_gate.py',
            'docs/harness/LOCAL_DB_CI.md', 'tools/harness/validate_harness.py',
            'docs/exec-plans/governance/HG-050.yaml',
            'docs/exec-plans/evidence/HG-050/**', 'docs/exec-plans/reviews/HG-050/**']
allowed = fixtures.v.governance_allowed_patterns('HG-050')
assert allowed == expected
forbidden = ['tools/harness/local_gate.py', 'tools/harness/db_policy.py',
             'tools/harness/db_ci.py', '.github/workflows/ci.yml', '.github/workflows/db.yml',
             'pyproject.toml', 'uv.lock', 'src/kineticloop/cli.py',
             '05_KineticLoop_Protocol_v1.2_FROZEN.md', 'FROZEN_BASELINE.json',
             '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
             'docs/exec-plans/active/KL-080.md', 'docs/exec-plans/governance/HG-050.json',
             'docs/exec-plans/evidence/HG-050A/file', 'docs/exec-plans/reviews/HG-050A/file',
             'docs/exec-plans/evidence/HG-049/file', 'docs/history/old.md',
             'tests/db/test_workflow.py', 'config.json', 'admission.json', 'signing.pem']
assert all(not fixtures.v.matches(p, allowed) for p in forbidden)
print(json.dumps({'mandatory_reviews': rows, 'exact_allowlist': allowed,
                  'forbidden_paths_rejected': forbidden, 'status': 'PASS'}, indent=2))
