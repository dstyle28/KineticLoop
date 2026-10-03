"""Read-only exact HG050 scope and historical/frozen preservation audit."""
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = '034d6301316d0dade784a61b159c027b83fbce3a'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def main():
    head = git('rev-parse', 'HEAD')
    git('merge-base', '--is-ancestor', BASE, head)
    spec = importlib.util.spec_from_file_location('scope_validator', ROOT / 'tools/harness/validate_harness.py')
    assert spec and spec.loader
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    changed = set(git('diff', '--name-only', BASE, head).splitlines())
    assert all(v.matches(p, v.governance_allowed_patterns('HG-050')) for p in changed)
    old_paths = git('ls-tree', '-r', '--name-only', BASE).splitlines()
    preserved = [p for p in old_paths if p.startswith(('docs/history/', 'docs/exec-plans/'))]
    preserved += [e['path'] for e in json.loads(git('show', BASE + ':FROZEN_BASELINE.json'))['files']]
    preserved += ['FROZEN_BASELINE.json', 'CURRENT_REQUIREMENT_SET.json', v.BACKLOG,
                  v.TRACEABILITY, v.PROJECT_PLAN, 'pyproject.toml', 'uv.lock',
                  'tools/harness/local_gate.py', 'tools/harness/db_policy.py']
    assert not changed.intersection(preserved)
    # The validator change is exactly the prospective allowlist + specialist rule.
    old = git('show', BASE + ':tools/harness/validate_harness.py')
    expected = old.replace('def governance_allowed_patterns(change_id):\n',
        "def governance_allowed_patterns(change_id):\n"
        "    if change_id == 'HG-050':\n"
        "        return [INDEX, MANIFEST, 'tools/harness/github_app.py',\n"
        "                'tests/harness/test_local_gate.py', 'docs/harness/LOCAL_DB_CI.md',\n"
        "                'tools/harness/validate_harness.py', 'docs/exec-plans/governance/HG-050.yaml',\n"
        "                'docs/exec-plans/evidence/HG-050/**', 'docs/exec-plans/reviews/HG-050/**']\n")
    expected = expected.replace("            required = {'GENERAL'}\n",
        "            required = {'GENERAL'}\n"
        "            if change_id == 'HG-050':\n"
        "                required.add('SECURITY_DATA_BOUNDARY')\n")
    assert (ROOT / 'tools/harness/validate_harness.py').read_text().strip() == expected
    assert not v.governance_manifest_errors(ROOT, BASE, changed)
    index = json.loads((ROOT / v.INDEX).read_bytes())
    for entry in index['documents'] + index['machine_readable']:
        assert v.sha(ROOT / entry['path']) == entry['sha256']
    record_path = ROOT / 'docs/exec-plans/governance/HG-050.yaml'
    if record_path.exists():
        record = v.load_artifact(record_path)
        assert record['packets_refined'] == [] and record['base_commit'] == BASE
        reviewed = head
        for review in (ROOT / 'docs/exec-plans/reviews/HG-050').glob('*.json'):
            reviewed = json.loads(review.read_bytes())['reviewed_head_sha']
        assert set(record['files_changed']) == set(v.changed_paths(ROOT, BASE, reviewed))
        assert not v.governance_suffix_errors(ROOT, record['tested_commit'], reviewed, 'HG-050', 'tested')
    print(json.dumps({'status': 'PASS', 'base_commit': BASE, 'head': head,
                      'changed_paths': sorted(changed), 'preserved_paths': len(set(preserved)),
                      'product_m3_release': 'NOT_RUN'}, indent=2))


if __name__ == '__main__':
    main()
