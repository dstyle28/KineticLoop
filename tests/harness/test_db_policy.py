from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'trusted_db_policy', Path(__file__).parents[2] / 'tools/harness/db_policy.py')
assert spec is not None and spec.loader is not None
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


@pytest.mark.parametrize('path', [
    'src/kineticloop/db/lifecycle.py', 'tests/db/test_workflow.py', 'uv.lock',
    'pyproject.toml', 'compose.yaml', '.github/workflows/ci.yml', 'unknown.conf',
    'docs/harness/MERGE_GATE.md', 'docs/exec-plans/active/KL-001.md',
    'CURRENT_DOCUMENT_INDEX.json', 'FROZEN_BASELINE.json', 'AGENTS.md',
    'docs/exec-plans/evidence/HG-037/kl074-readiness.workflow.proposal.yml',
    'docs/exec-plans/evidence/HG-046/run.log',
    'docs/exec-plans/evidence/HG-046/execute.py', 'docs/notes/../run.md',
])
def test_unknown_and_execution_policy_paths_always_require_db(path):
    assert not policy.documentation_only(path, ('100644', '100644'))


@pytest.mark.parametrize('mode', ['100755', '120000', '160000'])
def test_documentation_modes_cannot_hide_executable_or_external_content(mode):
    assert not policy.documentation_only('docs/notes/info.md', ('100644', mode))
    assert not policy.documentation_only('docs/notes/info.md', (mode, '000000'))


@pytest.mark.parametrize('path', ['README.md', 'docs/notes/info.md',
    'docs/exec-plans/reviews/HG-046/GENERAL.json'])
def test_only_inert_regular_records_are_exempt(path):
    assert policy.documentation_only(path, ('000000', '100644'))


def test_complete_git_diff_catches_rename_modes_and_tree_changes(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path, text=True).strip()

    def commit():
        git('add', '.')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
            'commit', '-qm', 'test')
        return git('rev-parse', 'HEAD')

    git('init', '-q')
    (tmp_path / 'source.py').write_text('print("test")\n')
    base = commit()
    (tmp_path / 'docs/notes').mkdir(parents=True)
    (tmp_path / 'source.py').rename(tmp_path / 'docs/notes/renamed.md')
    moved = commit()
    decision = policy.classify(tmp_path, base, moved)
    assert decision['full_database_required'] is True
    assert decision['changed_paths'] == ['docs/notes/renamed.md', 'source.py']
    assert decision['requiring_paths'] == ['source.py']
    assert policy.execution_tree(tmp_path, base) != policy.execution_tree(tmp_path, moved)
    (tmp_path / 'docs/notes/renamed.md').write_text('inert prose\n')
    docs = commit()
    assert policy.classify(tmp_path, moved, docs)['full_database_required'] is False
    assert policy.execution_tree(tmp_path, moved) == policy.execution_tree(tmp_path, docs)
    (tmp_path / 'docs/notes/renamed.md').chmod(0o755)
    executable = commit()
    assert policy.classify(tmp_path, docs, executable)['full_database_required'] is True
    assert policy.execution_tree(tmp_path, docs) != policy.execution_tree(tmp_path, executable)
