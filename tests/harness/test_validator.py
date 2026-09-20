"""Regression fixtures for Harness admission, evidence and real Git revision checks."""
import contextlib
import copy
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('harness_validator', ROOT / 'tools/harness/validate_harness.py')
assert spec is not None and spec.loader is not None
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def refresh(root):
    index = json.loads((root / v.INDEX).read_text())
    for entry in index['documents'] + index['machine_readable']:
        entry['sha256'] = v.sha(root / entry['path'])
    dump(root / v.INDEX, index)
    manifest = json.loads((root / v.MANIFEST).read_text())
    for entry in manifest['files']:
        entry['sha256'] = v.sha(root / entry['path'])
        entry['bytes'] = (root / entry['path']).stat().st_size
    dump(root / v.MANIFEST, manifest)


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kl-harness-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        manifest = json.loads((ROOT / v.MANIFEST).read_text())
        for name in [e['path'] for e in manifest['files']] + [v.MANIFEST]:
            dst = self.root / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dst)
        refresh(self.root)
        self.task = json.loads((self.root / v.BACKLOG).read_text())['tasks'][0]
        self.git('init', '-q')
        self.base = self.commit('fixture baseline')

    def git(self, *args):
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.check_output(
            ['git', '-c', 'user.name=Harness Test', '-c', 'user.email=harness@example.invalid',
             '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', *args],
            cwd=self.root, env=env, stderr=subprocess.STDOUT).decode().strip()

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def put(self, name, content='fixture\n'):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def check(self, expected=0, key='', *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = v.main(list(args), root=self.root)
        self.assertEqual(code, expected, out.getvalue())
        self.assertIn(key or ('HARNESS_CHECK_PASS' if expected == 0 else 'HARNESS_CHECK_FAIL'), out.getvalue())

    def result(self, ext='yaml', tested=None):
        evidence = 'docs/exec-plans/evidence/KL-001/checks.log'
        self.put(evidence, 'checks passed on the tested revision\n')
        obj = {
            'task_identity': self.task['task_identity'], 'display_task_id': 'KL-001',
            'base_commit': self.base, 'tested_commit': tested or self.base,
            'task_status': 'PASS', 'task_checks_status': 'PASS', 'integration_status': 'UNMERGED',
            'summary': 'Fixture checks', 'files_changed': [], 'requirements_covered': [],
            'commands_run': [{'check_id': c, 'command': 'fixture-check ' + c, 'result': 'PASS',
                              'evidence_ref': evidence} for c in self.task['checks_required_for_this_task']],
        }
        path = self.root / ('docs/exec-plans/completed/KL-001_RESULT.' + ext)
        self.save_result(path, obj)
        return path, obj

    def save_result(self, path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(obj) if path.suffix == '.yaml' else json.dumps(obj))

    def review(self, reviewed, task_id='KL-001'):
        obj = {'task_identity': self.task['task_identity'], 'reviewed_head_sha': reviewed,
               'review_type': 'GENERAL', 'review_contract_version': 'v0.2', 'status': 'PASS', 'findings': []}
        dump(self.root / f'docs/exec-plans/reviews/{task_id}/GENERAL.json', obj)
        return self.commit('persist review')

    def reviewed_result(self):
        path, obj = self.result()
        reviewed = self.commit('record result and new evidence')
        self.review(reviewed)
        return path, obj, reviewed

    def test_current_structure_passes(self):
        self.check()

    def test_yaml_and_json_valid_results_pass(self):
        for ext in ('yaml', 'json'):
            path, _ = self.result(ext)
            self.check()
            path.unlink()

    def test_yaml_and_json_invalid_schema_rejected(self):
        for ext in ('yaml', 'json'):
            path, obj = self.result(ext)
            del obj['tested_commit']
            self.save_result(path, obj)
            self.check(1, 'result-schema:')
            path.unlink()

    def test_empty_fail_not_run_and_missing_checks_rejected(self):
        path, original = self.result()
        for change in ('empty', 'FAIL', 'NOT_RUN', 'missing', 'duplicate', 'unknown'):
            obj = copy.deepcopy(original)
            if change == 'empty':
                obj['commands_run'] = []
            elif change == 'missing':
                obj['commands_run'].pop()
            elif change == 'duplicate':
                obj['commands_run'].append(obj['commands_run'][0])
            elif change == 'unknown':
                obj['commands_run'][0]['check_id'] = 'invented-check'
            else:
                obj['commands_run'][0]['result'] = change
            self.save_result(path, obj)
            self.check(1)

    def test_missing_and_escaping_evidence_rejected(self):
        path, obj = self.result()
        for ref in (None, '', 'missing.log', '../outside.log', '/tmp/outside.log'):
            obj['commands_run'][0]['evidence_ref'] = ref
            self.save_result(path, obj)
            self.check(1)

    def test_requirement_pass_needs_layer_evidence_and_revision(self):
        path, obj = self.result()
        for status in ('PASS', 'APPROVED_NA'):
            obj['requirements_covered'] = [{'requirement_id': 'I01@DC', 'status': status}]
            self.save_result(path, obj)
            self.check(1, 'result-schema:')
        obj['requirements_covered'] = [{'requirement_id': 'I01', 'status': 'PASS',
                                       'evidence_ref': obj['commands_run'][0]['evidence_ref'],
                                       'tested_commit': self.base}]
        self.save_result(path, obj)
        self.check(1, 'requirement-layer:')

    def test_duplicate_yaml_keys_rejected(self):
        path, _ = self.result()
        path.write_text(path.read_text() + '\ntask_status: BLOCKED\n')
        self.check(1, 'duplicate-key:')

    def test_malformed_yaml_fails_with_diagnostic(self):
        path, _ = self.result()
        path.write_text('task_status: [\n')
        self.check(1, 'yaml-parse:')

    def test_pass_task_with_failed_check_summary_rejected(self):
        path, obj = self.result()
        obj['task_checks_status'] = 'FAIL'
        self.save_result(path, obj)
        self.check(1, 'result-schema:')

    def test_requirement_wrong_revision_and_unknown_id_rejected(self):
        path, obj = self.result()
        obj['requirements_covered'] = [{'requirement_id': 'invented@DC', 'status': 'PASS',
                                       'evidence_ref': obj['commands_run'][0]['evidence_ref'],
                                       'tested_commit': 'a' * 40}]
        self.save_result(path, obj)
        self.check(1, 'requirement-revision:')
        self.check(1, 'result-unknown-or-unassigned-requirement:')

    def test_ready_task_with_unresolved_scope_rejected(self):
        path = self.root / v.BACKLOG
        obj = json.loads(path.read_text())
        obj['tasks'][1]['status'] = 'READY'
        dump(path, obj)
        refresh(self.root)
        self.check(1, 'ready-write-scope-unrefined:KL-002')

    def test_duplicate_result_formats_rejected(self):
        self.result('yaml')
        self.result('json')
        self.check(1, 'result-duplicate-or-path:')

    def test_deleted_check_section_and_empty_check_list_rejected(self):
        path = self.root / 'docs/exec-plans/active/KL-001.md'
        original = path.read_text()
        block = v.section(original, 'Checks required for this task PR')
        for replacement in ('', '\n'):
            path.write_text(original.replace(block, replacement))
            self.check(1, 'packet-checks:KL-001')

    def test_extra_write_path_and_dependency_drift_rejected(self):
        path = self.root / 'docs/exec-plans/active/KL-001.md'
        original = path.read_text()
        path.write_text(original.replace('- uv.lock', '- uv.lock\n- secrets/**'))
        self.check(1, 'packet-write-paths:KL-001')
        path.write_text(original.replace('## Dependencies\nnone', '## Dependencies\nKL-002'))
        self.check(1, 'packet-deps:KL-001')

    def test_conditional_dependency_and_resource_drift_rejected(self):
        packet = self.root / 'docs/exec-plans/active/KL-001.md'
        original = packet.read_text()
        packet.write_text(original.replace('- none\n\n## Entry conditions',
                                           '- KL-002 when enabled\n\n## Entry conditions'))
        self.check(1, 'packet-conditional-deps:KL-001')
        packet.write_text(original.replace('- harness_core', '- release_evidence'))
        self.check(1, 'packet-resource-keys:KL-001')

    def test_unknown_dependency_and_cycle_fail_cleanly(self):
        p = self.root / v.BACKLOG
        original = json.loads(p.read_text())
        for dependency in ('KL-999', 'KL-002'):
            b = copy.deepcopy(original)
            b['tasks'][0]['depends_on'] = [dependency]
            dump(p, b)
            refresh(self.root)
            self.check(1, 'unknown-dep:' if dependency == 'KL-999' else 'dag-cycle')

    def test_conditional_dependency_shape_unknown_target_and_cycle_rejected(self):
        path = self.root / v.BACKLOG
        original = json.loads(path.read_text())
        cases = [
            ({'task_id': 'KL-002', 'condition': ''}, 'invalid-conditional-dep:KL-001'),
            ({'task_id': 'KL-999', 'condition': 'enabled'}, 'unknown-conditional-dep:KL-001'),
            ({'task_id': 'KL-002', 'condition': 'enabled'}, 'dag-cycle'),
        ]
        for dependency, diagnostic in cases:
            backlog = copy.deepcopy(original)
            backlog['tasks'][0]['conditional_depends_on'] = [dependency]
            dump(path, backlog)
            refresh(self.root)
            self.check(1, diagnostic)

    def test_unknown_and_duplicate_resource_keys_rejected(self):
        path = self.root / v.BACKLOG
        original = json.loads(path.read_text())
        for resources, diagnostic in [
            (['invented_resource'], 'unknown-resource-key:KL-001'),
            (['harness_core', 'harness_core'], 'duplicate-resource-key:KL-001'),
        ]:
            backlog = copy.deepcopy(original)
            backlog['tasks'][0]['resource_keys'] = resources
            dump(path, backlog)
            refresh(self.root)
            self.check(1, diagnostic)

    def test_path_components_enforced_in_real_git_diff(self):
        self.put('src/kineticloop_extra/entry.py')
        self.commit('unauthorized lookalike path')
        self.check(1, 'write-scope:', '--protected-base', self.base, '--task-id', 'KL-001')

    def test_legal_implementation_and_bookkeeping_pass(self):
        self.put('src/kineticloop/entry.py')
        tested = self.commit('implementation')
        self.result(tested=tested)
        self.commit('result and evidence')
        self.check(0, '', '--protected-base', self.base, '--task-id', 'KL-001')

    def test_authorized_hash_refresh_passes(self):
        p = self.root / 'tools/harness/validate_harness.py'
        p.write_text(p.read_text() + '\n# implementation fixture\n')
        refresh(self.root)
        self.commit('implementation with derived checksums')
        self.check(0, '', '--protected-base', self.base, '--task-id', 'KL-001')

    def test_index_authority_change_rejected(self):
        p = self.root / v.INDEX
        obj = json.loads(p.read_text())
        obj['documents'][0]['document_id'] = 'REASSIGNED'
        dump(p, obj)
        refresh(self.root)
        self.commit('index authority tampering')
        self.check(1, 'derived-index-unauthorized:', '--protected-base', self.base, '--task-id', 'KL-001')

    def test_index_addition_rejected(self):
        p = self.root / v.INDEX
        obj = json.loads(p.read_text())
        self.put('tools/harness/new.py')
        obj['machine_readable'].append({'path': 'tools/harness/new.py'})
        dump(p, obj)
        refresh(self.root)
        self.commit('unauthorized index entry')
        self.check(1, 'derived-index-paths:', '--protected-base', self.base, '--task-id', 'KL-001')

    def test_frozen_and_baseline_coordinated_tamper_rejected(self):
        baseline = self.root / 'FROZEN_BASELINE.json'
        obj = json.loads(baseline.read_text())
        path = self.root / obj['files'][0]['path']
        path.write_text(path.read_text() + '\nchanged frozen semantics\n')
        obj['files'][0]['sha256'] = v.sha(path)
        dump(baseline, obj)
        refresh(self.root)
        self.commit('self-consistent frozen tampering')
        self.check(1, 'protected-baseline-change:', '--protected-base', self.base, '--task-id', 'KL-001')

    def test_result_then_review_only_suffix_passes(self):
        _, _, reviewed = self.reviewed_result()
        self.check(0, '', '--protected-base', self.base, '--task-id', 'KL-001', '--reviewed-head', reviewed)

    def test_ci_merge_gate_binds_base_task_and_reviewed_revision(self):
        self.reviewed_result()
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_merge_gate_rejects_coordinated_frozen_tamper(self):
        baseline = self.root / 'FROZEN_BASELINE.json'
        frozen = json.loads(baseline.read_text())
        protected = self.root / frozen['files'][0]['path']
        protected.write_text(protected.read_text() + '\ncoordinated CI tamper\n')
        frozen['files'][0]['sha256'] = v.sha(protected)
        dump(baseline, frozen)
        refresh(self.root)
        tested = self.commit('coordinated frozen tamper')
        self.result(tested=tested)
        reviewed = self.commit('record tampered result')
        self.review(reviewed)
        self.check(0)
        self.check(1, 'protected-baseline-change:',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_merge_gate_requires_exact_head_and_review(self):
        self.result(tested=self.base)
        head = self.commit('result without review')
        self.check(1, 'ci-general-review-missing:KL-001',
                   '--ci-pr-base', self.base, '--ci-pr-head', head)
        self.review(head)
        self.check(1, 'ci-head-not-checked-out',
                   '--ci-pr-base', self.base, '--ci-pr-head', head)

    def test_code_change_after_review_rejected(self):
        _, _, reviewed = self.reviewed_result()
        self.put('src/kineticloop/entry.py')
        self.commit('code after review')
        self.check(1, 'review-stale-change:', '--task-id', 'KL-001', '--reviewed-head', reviewed)

    def test_other_task_review_directory_rejected(self):
        _, _, reviewed = self.reviewed_result()
        self.put('docs/exec-plans/reviews/KL-001A/notes.md')
        self.commit('another task review')
        self.check(1, 'review-stale-change:', '--task-id', 'KL-001', '--reviewed-head', reviewed)

    def test_code_change_after_testing_rejected(self):
        self.put('src/kineticloop/entry.py')
        self.commit('untested implementation')
        self.result(tested=self.base)
        reviewed = self.commit('result with stale test revision')
        self.review(reviewed)
        self.check(1, 'tested-stale-change:', '--task-id', 'KL-001', '--reviewed-head', reviewed)

    def test_reverted_code_change_after_testing_rejected(self):
        path = self.put('src/kineticloop/entry.py')
        self.commit('untested implementation')
        path.unlink()
        self.commit('revert implementation')
        self.result(tested=self.base)
        reviewed = self.commit('result pointing past reverted code')
        self.review(reviewed)
        self.check(1, 'tested-stale-change:', '--task-id', 'KL-001', '--reviewed-head', reviewed)

    def test_nonancestor_tested_revision_rejected(self):
        branch = self.git('branch', '--show-current')
        self.git('checkout', '-qb', 'unrelated')
        self.put('src/kineticloop/unrelated.py')
        tested = self.commit('other branch')
        self.git('checkout', '-q', branch)
        self.result(tested=tested)
        reviewed = self.commit('result for nonancestor')
        self.review(reviewed)
        self.check(1, 'tested-revision:', '--task-id', 'KL-001', '--reviewed-head', reviewed)

    def test_overwritten_evidence_after_testing_rejected(self):
        self.put('docs/exec-plans/evidence/KL-001/checks.log', 'old evidence')
        tested = self.commit('existing evidence')
        self.result(tested=tested)
        reviewed = self.commit('overwrite evidence after testing')
        self.review(reviewed)
        self.check(1, 'tested-evidence-not-addition:', '--task-id', 'KL-001', '--reviewed-head', reviewed)

    def test_missing_review_and_uncommitted_result_rejected(self):
        self.result()
        reviewed = self.commit('result without review')
        self.check(1, 'required-reviews-not-pass:', '--task-id', 'KL-001', '--reviewed-head', reviewed)
        self.put('uncommitted.txt')
        self.check(1, 'git-worktree-not-clean', '--task-id', 'KL-001', '--reviewed-head', reviewed)

    def test_invalid_review_schema_rejected(self):
        dump(self.root / 'docs/exec-plans/reviews/KL-001/GENERAL.json', {'status': 'PASS'})
        self.check(1, 'review-schema:')

    def test_review_cannot_point_before_result_commit(self):
        self.result()
        self.commit('result after reviewed revision')
        self.review(self.base)
        self.check(1, 'review-revision:', '--task-id', 'KL-001', '--reviewed-head', self.base)

    def test_historical_review_is_not_compared_to_new_head(self):
        self.reviewed_result()
        self.put('src/kineticloop/later_task.py')
        self.commit('later integrated work')
        self.check()


if __name__ == '__main__':
    unittest.main()
