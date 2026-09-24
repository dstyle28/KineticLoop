"""Regression fixtures for Harness admission, evidence and real Git revision checks."""
import contextlib
import copy
import importlib.util
import io
import json
import os
import re
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
        index = json.loads((ROOT / v.INDEX).read_text())
        names = (
            [entry['path'] for entry in manifest['files']]
            + [v.MANIFEST]
            + [entry['path'] for entry in index['documents'] + index['machine_readable']]
        )
        for name in dict.fromkeys(names):
            dst = self.root / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dst)
        # Governance scenarios need a pending refinement regardless of the live
        # repository's scheduling state. Establish that state in the fixture only.
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-008')
        task['packet_refinement'] = 'MUST_REFINE_BEFORE_READY'
        task['write_paths_status'] = 'TEMPLATE_NOT_ENFORCEABLE'
        task['write_paths'] = []
        dump(backlog_path, backlog)
        packet = self.root / 'docs/exec-plans/active/KL-008.md'
        text = re.sub(
            r'^\*\*Packet refinement:\*\* .*$',
            '**Packet refinement:** MUST_REFINE_BEFORE_READY',
            packet.read_text(), flags=re.M)
        text = re.sub(
            r'(^Expected implementation write paths:\n)(?:- [^\n]+\n)+',
            r'\g<1>- TO_BE_REFINED_BEFORE_READY\n', text, flags=re.M)
        packet.write_text(text)
        refresh(self.root)
        self.task = json.loads((self.root / v.BACKLOG).read_text())['tasks'][0]
        self.git('init', '-q')
        self.base = self.commit('fixture baseline')

    def git(self, *args):
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.check_output(
            ['git', '-c', 'user.name=Harness Test', '-c', 'user.email=harness@example.invalid',
             '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null',
             '-c', 'gc.auto=0', '-c', 'maintenance.auto=false', *args],
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

    def sibling_commit(self, treeish, message='squash merge'):
        tree = self.git('rev-parse', treeish + '^{tree}')
        return self.git('commit-tree', tree, '-p', self.base, '-m', message)

    def merge_commit(self, treeish, *parents, message='merge'):
        tree = self.git('rev-parse', treeish + '^{tree}')
        args = ['commit-tree', tree]
        for parent in parents:
            args.extend(('-p', parent))
        return self.git(*args, '-m', message)

    def integration_record(self, result_commit, reviewed, review_commit, merge_commit):
        dump(self.root / 'docs/exec-plans/integrations/KL-001.json', {
            'task_identity': self.task['task_identity'],
            'display_task_id': 'KL-001',
            'result_commit': result_commit,
            'reviewed_head_sha': reviewed,
            'review_record_commit': review_commit,
            'merge_commit': merge_commit,
            'integration_status': 'MERGED',
        })

    def governance_review(self, change_id, reviewed, review_type='GENERAL'):
        obj = {
            'task_identity': 'harness-governance-v0.1/' + change_id,
            'reviewed_head_sha': reviewed,
            'review_type': review_type,
            'review_contract_version': 'v0.2',
            'status': 'PASS',
            'findings': [],
        }
        dump(self.root / f'docs/exec-plans/reviews/{change_id}/{review_type}.json', obj)

    def persist_governance_change(self, change_id, tested, packets_refined,
                                  review_types, change_status='PASS'):
        evidence = f'docs/exec-plans/evidence/{change_id}/checks.log'
        self.put(evidence, 'governance checks passed\n')
        record_path = self.root / f'docs/exec-plans/governance/{change_id}.yaml'
        planned = set(self.git('diff', '--name-only', self.base, 'HEAD').splitlines())
        planned.update((evidence, str(record_path.relative_to(self.root))))
        record = {
            'change_identity': 'harness-governance-v0.1/' + change_id,
            'display_change_id': change_id,
            'base_commit': self.base,
            'tested_commit': tested,
            'change_status': change_status,
            'summary': 'Fixture governance change',
            'packets_refined': packets_refined,
            'files_changed': sorted(planned),
            'checks_run': [{
                'check_id': 'governance_contract_valid',
                'command': 'fixture governance check',
                'result': 'PASS',
                'evidence_ref': evidence,
            }],
            'frozen_impact': 'NONE',
            'authority_entries_added': [],
        }
        self.save_result(record_path, record)
        reviewed = self.commit('record governance result')
        for review_type in sorted(set(review_types) | {'GENERAL'}):
            self.governance_review(change_id, reviewed, review_type)
        self.commit('persist governance review')
        return change_id, reviewed

    def governance_change(self, change_id='HG-999', task_id='KL-008',
                          change_status='PASS'):
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        task['packet_refinement'] = 'READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED'
        task['write_paths_status'] = 'ENFORCEABLE'
        task['write_paths'] = ['src/kineticloop/shadow/**']
        dump(backlog_path, backlog)
        packet = self.root / f'docs/exec-plans/active/{task_id}.md'
        text = packet.read_text().replace(
            '**Packet refinement:** MUST_REFINE_BEFORE_READY',
            '**Packet refinement:** READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED')
        text = text.replace('- TO_BE_REFINED_BEFORE_READY', '- src/kineticloop/shadow/**')
        packet.write_text(text)
        refresh(self.root)
        tested = self.commit('refine packet')
        return self.persist_governance_change(
            change_id, tested, [task_id], task.get('review_requirements', []),
            change_status)

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
        task = next(item for item in obj['tasks']
                    if item.get('packet_refinement') == 'MUST_REFINE_BEFORE_READY')
        task['status'] = 'READY'
        dump(path, obj)
        refresh(self.root)
        self.check(1, 'ready-write-scope-unrefined:' + task['id'])

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

    def test_ci_governance_merge_gate_binds_record_and_reviews(self):
        self.governance_change()
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_allows_refined_traceability_metadata(self):
        task_id = 'KL-008'
        write_paths = ['src/kineticloop/shadow/**']
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        task['packet_refinement'] = 'READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED'
        task['write_paths_status'] = 'ENFORCEABLE'
        task['write_paths'] = write_paths
        dump(backlog_path, backlog)

        packet = self.root / f'docs/exec-plans/active/{task_id}.md'
        packet.write_text(packet.read_text().replace(
            '**Packet refinement:** MUST_REFINE_BEFORE_READY',
            '**Packet refinement:** READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED').replace(
                '- TO_BE_REFINED_BEFORE_READY', '- src/kineticloop/shadow/**'))

        traceability_path = self.root / v.TRACEABILITY
        traceability = json.loads(traceability_path.read_text())
        trace = next(item for item in traceability['tasks'] if item['id'] == task_id)
        trace['packet_refinement'] = task['packet_refinement']
        trace['write_paths_status'] = task['write_paths_status']
        trace['write_paths'] = write_paths
        dump(traceability_path, traceability)

        refresh(self.root)
        tested = self.commit('refine packet and derived traceability metadata')
        self.persist_governance_change(
            'HG-999', tested, [task_id], task['review_requirements'])
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_ignores_unrelated_unresolvable_review_sha(self):
        self.governance_review('HG-998', 'f' * 40)
        self.base = self.commit('historical governance review with unavailable revision')
        self.governance_change()
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_review_only_accepts_exact_tree_post_merge_review(self):
        self.put('tools/harness/post_merge_fixture.py')
        tested = self.commit('governance implementation')
        evidence = 'docs/exec-plans/evidence/HG-999/checks.log'
        record_path = 'docs/exec-plans/governance/HG-999.yaml'
        self.put(evidence, 'governance checks passed\n')
        self.save_result(self.root / record_path, {
            'change_identity': 'harness-governance-v0.1/HG-999',
            'display_change_id': 'HG-999',
            'base_commit': self.base,
            'tested_commit': tested,
            'change_status': 'PASS',
            'summary': 'Fixture governance change reviewed after merge',
            'packets_refined': [],
            'files_changed': sorted((
                'tools/harness/post_merge_fixture.py', evidence, record_path)),
            'checks_run': [{
                'check_id': 'governance_contract_valid',
                'command': 'fixture governance check',
                'result': 'PASS',
                'evidence_ref': evidence,
            }],
            'frozen_impact': 'NONE',
            'authority_entries_added': [],
        })
        record_commit = self.commit('record governance result')
        merge_commit = self.merge_commit(
            record_commit, self.base, record_commit, message='merge governance before review')
        self.git('checkout', '-q', '--detach', merge_commit)
        self.governance_review('HG-999', merge_commit)
        self.commit('persist post-merge governance review')
        self.check(0, '', '--ci-pr-base', merge_commit, '--ci-pr-head', 'HEAD')

    def test_ci_governance_review_only_replays_reviewed_tree_from_later_base(self):
        self.put('tools/harness/post_merge_fixture.py')
        tested = self.commit('governance implementation')
        evidence = 'docs/exec-plans/evidence/HG-999/checks.log'
        record_path = 'docs/exec-plans/governance/HG-999.yaml'
        self.put(evidence, 'governance checks passed\n')
        self.save_result(self.root / record_path, {
            'change_identity': 'harness-governance-v0.1/HG-999',
            'display_change_id': 'HG-999',
            'base_commit': self.base,
            'tested_commit': tested,
            'change_status': 'PASS',
            'summary': 'Fixture governance change reviewed after a later integration',
            'packets_refined': [],
            'files_changed': sorted((
                'tools/harness/post_merge_fixture.py', evidence, record_path)),
            'checks_run': [{
                'check_id': 'governance_contract_valid',
                'command': 'fixture governance check',
                'result': 'PASS',
                'evidence_ref': evidence,
            }],
            'frozen_impact': 'NONE',
            'authority_entries_added': [],
        })
        record_commit = self.commit('record governance result')
        reviewed = self.merge_commit(
            record_commit, self.base, record_commit, message='merge governance before review')
        self.git('checkout', '-q', '--detach', reviewed)

        validator = self.root / 'tools/harness/validate_harness.py'
        validator.write_text(validator.read_text() + '\n# later governance fixture\n')
        refresh(self.root)
        later_tip = self.commit('later governance change')
        protected_base = self.merge_commit(
            later_tip, reviewed, later_tip, message='merge later governance change')
        self.git('checkout', '-q', '--detach', protected_base)
        self.governance_review('HG-999', reviewed)
        self.commit('persist delayed governance review')

        self.check(0, '', '--ci-pr-base', protected_base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_review_only_rejects_unrelated_later_base(self):
        self.put('tools/harness/post_merge_fixture.py')
        tested = self.commit('governance implementation')
        _, reviewed = self.persist_governance_change('HG-999', tested, [], ['GENERAL'])
        unrelated_base = self.sibling_commit(reviewed, 'unrelated squash-equivalent base')
        self.git('checkout', '-q', '--detach', unrelated_base)
        self.governance_review('HG-999', reviewed)
        self.commit('persist review from unrelated base')
        self.check(1, 'governance-review-only-reviewed-not-merged:HG-999',
                   '--ci-pr-base', unrelated_base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_review_only_rejects_later_packet_repair_masking(self):
        task_id = 'KL-008'
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        task['packet_refinement'] = 'READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED'
        task['write_paths_status'] = 'ENFORCEABLE'
        task['write_paths'] = ['src/expected/**']
        dump(backlog_path, backlog)
        packet = self.root / f'docs/exec-plans/active/{task_id}.md'
        packet_text = packet.read_text().replace(
            '**Packet refinement:** MUST_REFINE_BEFORE_READY',
            '**Packet refinement:** READY_WHEN_DEPENDENCIES_AND_GATES_SATISFIED')
        packet.write_text(packet_text.replace(
            '- TO_BE_REFINED_BEFORE_READY', '- src/wrong/**'))
        refresh(self.root)
        tested = self.commit('invalid historical packet refinement')
        _, reviewed = self.persist_governance_change(
            'HG-999', tested, [task_id], task['review_requirements'])
        self.git('checkout', '-q', '--detach', reviewed)

        packet.write_text(packet.read_text().replace('- src/wrong/**', '- src/expected/**'))
        refresh(self.root)
        later_tip = self.commit('later governance repairs packet')
        protected_base = self.merge_commit(
            later_tip, reviewed, later_tip, message='merge later packet repair')
        self.git('checkout', '-q', '--detach', protected_base)
        self.governance_review('HG-999', reviewed)
        self.commit('persist delayed review of invalid historical packet')

        self.check(1, 'packet-write-paths:KL-008',
                   '--ci-pr-base', protected_base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_review_only_rejects_later_hash_repair_masking(self):
        validator = self.root / 'tools/harness/validate_harness.py'
        validator.write_text(validator.read_text() + '\n# unindexed historical change\n')
        tested = self.commit('historical governance omits derived hash refresh')
        _, reviewed = self.persist_governance_change('HG-999', tested, [], ['GENERAL'])
        self.git('checkout', '-q', '--detach', reviewed)

        refresh(self.root)
        later_tip = self.commit('later governance repairs derived hashes')
        protected_base = self.merge_commit(
            later_tip, reviewed, later_tip, message='merge later hash repair')
        self.git('checkout', '-q', '--detach', protected_base)
        self.governance_review('HG-999', reviewed)
        self.commit('persist delayed review of invalid historical hashes')

        self.check(1, 'governance-index-hash:tools/harness/validate_harness.py',
                   '--ci-pr-base', protected_base, '--ci-pr-head', 'HEAD')
        self.check(1, 'governance-manifest-hash:tools/harness/validate_harness.py',
                   '--ci-pr-base', protected_base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_review_only_rejects_later_index_deduplication(self):
        index_path = self.root / v.INDEX
        index = json.loads(index_path.read_text())
        validator_entry = next(
            entry for entry in index['machine_readable']
            if entry['path'] == 'tools/harness/validate_harness.py')
        stale_duplicate = copy.deepcopy(validator_entry)
        stale_duplicate['sha256'] = '0' * 64
        position = index['machine_readable'].index(validator_entry)
        index['machine_readable'].insert(position, stale_duplicate)
        dump(index_path, index)
        manifest_path = self.root / v.MANIFEST
        manifest = json.loads(manifest_path.read_text())
        manifest_entry = next(
            entry for entry in manifest['files'] if entry['path'] == v.INDEX)
        manifest_entry['sha256'] = v.sha(index_path)
        manifest_entry['bytes'] = index_path.stat().st_size
        dump(manifest_path, manifest)
        tested = self.commit('historical governance duplicates an index path')
        _, reviewed = self.persist_governance_change('HG-999', tested, [], ['GENERAL'])
        self.git('checkout', '-q', '--detach', reviewed)

        index = json.loads(index_path.read_text())
        seen_validator = False
        deduplicated = []
        for entry in reversed(index['machine_readable']):
            if entry['path'] == 'tools/harness/validate_harness.py':
                if seen_validator:
                    continue
                seen_validator = True
            deduplicated.append(entry)
        index['machine_readable'] = list(reversed(deduplicated))
        dump(index_path, index)
        refresh(self.root)
        later_tip = self.commit('later governance removes duplicate index path')
        protected_base = self.merge_commit(
            later_tip, reviewed, later_tip, message='merge later index repair')
        self.git('checkout', '-q', '--detach', protected_base)
        self.governance_review('HG-999', reviewed)
        self.commit('persist delayed review of duplicate historical index')

        self.check(1, 'governance-index-duplicate-path',
                   '--ci-pr-base', protected_base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_review_only_rejects_content_changing_merge(self):
        self.put('tools/harness/post_merge_fixture.py')
        tested = self.commit('governance implementation')
        change_id, reviewed = self.persist_governance_change(
            'HG-999', tested, [], ['GENERAL'])
        self.assertEqual(change_id, 'HG-999')
        review_commit = self.git('rev-parse', 'HEAD')
        merge_commit = self.merge_commit(
            review_commit, self.base, reviewed, message='content-changing merge')
        self.git('checkout', '-q', '--detach', merge_commit)
        self.governance_review('HG-999', merge_commit)
        self.commit('persist replacement review')
        self.check(1, 'governance-tested-suffix-merge:' + merge_commit,
                   '--ci-pr-base', merge_commit, '--ci-pr-head', 'HEAD')

    def test_ci_governance_review_only_rejects_non_review_write(self):
        _, reviewed = self.governance_change()
        merged = self.git('rev-parse', 'HEAD')
        review_path = self.root / 'docs/exec-plans/reviews/HG-999/GENERAL.json'
        review = json.loads(review_path.read_text())
        review['reviewed_head_sha'] = reviewed
        review['findings'] = [{'severity': 'INFO', 'summary': 'review-only fixture'}]
        dump(review_path, review)
        self.put('tools/harness/review_only_escape.py')
        self.commit('mix implementation into review-only PR')
        self.check(1, 'governance-review-only-scope:HG-999:',
                   '--ci-pr-base', merged, '--ci-pr-head', 'HEAD')

    def test_governance_tested_suffix_rejects_unrelated_merge_parent(self):
        self.put('tools/harness/post_merge_fixture.py')
        tested = self.commit('governance implementation')
        _, reviewed = self.persist_governance_change('HG-999', tested, [], ['GENERAL'])
        unrelated = self.git(
            'commit-tree', self.base + '^{tree}', '-p', self.base,
            '-m', 'unrelated sibling history')
        merge_commit = self.merge_commit(
            reviewed, unrelated, reviewed, message='merge unrelated parent')
        self.git('checkout', '-q', '--detach', merge_commit)
        self.governance_review('HG-999', merge_commit)
        self.commit('persist replacement review')
        self.check(1, 'governance-tested-suffix-merge:' + merge_commit,
                   '--ci-pr-base', merge_commit, '--ci-pr-head', 'HEAD')

    def test_ci_governance_requires_pass_change_status(self):
        self.governance_change(change_status='BLOCKED')
        self.check(1, 'governance-change-not-pass:HG-999',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_rejects_spec_change_required_status(self):
        self.governance_change(change_status='SPEC_CHANGE_REQUIRED')
        self.check(1, 'governance-change-not-pass:HG-999',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_cannot_remove_its_specialist_review(self):
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-007')
        self.assertIn('PROTOCOL', task['review_requirements'])
        task['review_requirements'] = ['GENERAL']
        dump(backlog_path, backlog)
        refresh(self.root)
        tested = self.commit('weaken specialist review requirement')
        self.persist_governance_change('HG-999', tested, [], ['GENERAL'])
        self.check(1, 'governance-required-reviews-not-pass:HG-999',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_rejects_undeclared_write(self):
        self.governance_change()
        self.put('README.md', 'out of governance scope\n')
        self.commit('unauthorized governance write')
        self.check(1, 'governance-write-scope:HG-999:README.md',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_rejects_task_review_without_integration(self):
        self.review(self.base)
        self.governance_change()
        self.check(1, 'governance-task-review-without-integration:HG-999:KL-001',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_rejects_nonrecord_task_review_path(self):
        self.put('docs/exec-plans/reviews/KL-001/notes.md')
        self.commit('persist unstructured task review note')
        self.governance_change()
        self.check(1, 'governance-task-review-path:HG-999:',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_rejects_mixed_task_and_governance_records(self):
        self.governance_change()
        self.result()
        self.commit('mix task and governance records')
        self.check(1, 'ci-change-record-count:task=1,governance=1',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_invalid_integration_record_rejected(self):
        dump(self.root / 'docs/exec-plans/integrations/KL-001.json', {
            'task_identity': 'harness-backlog-v0.2/KL-001',
            'display_task_id': 'KL-001',
            'integration_status': 'MERGED',
        })
        self.check(1, 'integration-schema:KL-001.json:')

    def test_integration_accepts_exactly_one_json_result(self):
        self.result(ext='json', tested=self.base)
        result_commit = self.commit('persist JSON result')
        review_commit = self.review(result_commit)
        dump(self.root / 'docs/exec-plans/integrations/KL-001.json', {
            'task_identity': self.task['task_identity'],
            'display_task_id': 'KL-001',
            'result_commit': result_commit,
            'reviewed_head_sha': result_commit,
            'review_record_commit': review_commit,
            'merge_commit': review_commit,
            'integration_status': 'MERGED',
        })
        self.check()

    def test_integration_accepts_exact_complete_tree_squash_merge(self):
        self.result(tested=self.base)
        result_commit = self.commit('persist result')
        review_commit = self.review(result_commit)
        merge_commit = self.sibling_commit(review_commit)
        self.git('checkout', '-q', '--detach', merge_commit)
        self.integration_record(result_commit, result_commit, review_commit, merge_commit)
        self.check()

    def test_integration_accepts_review_recorded_after_merge(self):
        self.result(tested=self.base)
        merge_commit = self.commit('merge result before review')
        self.put('later.txt', 'later integrated work\n')
        self.commit('integrate unrelated later work')
        review_commit = self.review(merge_commit)
        self.integration_record(merge_commit, merge_commit, review_commit, merge_commit)
        self.check()

    def test_delayed_review_must_bind_the_merge_tree(self):
        self.result(tested=self.base)
        result_commit = self.commit('persist result')
        self.put('merged.txt', 'content added by merge\n')
        merge_commit = self.commit('merge task with changed tree')
        review_commit = self.review(result_commit)
        self.integration_record(result_commit, result_commit, review_commit, merge_commit)
        self.check(1, 'integration-ancestry-or-exact-tree:KL-001:review-to-merge')

    def test_integration_rejects_squash_tree_with_unrelated_content_change(self):
        self.result(tested=self.base)
        result_commit = self.commit('persist result')
        review_commit = self.review(result_commit)
        self.put('unrelated.txt', 'not part of the reviewed tree\n')
        near_match = self.commit('change unrelated content')
        merge_commit = self.sibling_commit(near_match)
        self.git('checkout', '-q', '--detach', merge_commit)
        self.integration_record(result_commit, result_commit, review_commit, merge_commit)
        self.check(1, 'integration-ancestry-or-exact-tree:KL-001:review-to-merge')

    def test_integration_rejects_squash_tree_with_mode_only_difference(self):
        self.result(tested=self.base)
        result_commit = self.commit('persist result')
        review_commit = self.review(result_commit)
        readme = self.root / 'README.md'
        readme.chmod(readme.stat().st_mode | 0o111)
        mode_change = self.commit('change unrelated file mode')
        merge_commit = self.sibling_commit(mode_change)
        self.git('checkout', '-q', '--detach', merge_commit)
        self.integration_record(result_commit, result_commit, review_commit, merge_commit)
        self.check(1, 'integration-ancestry-or-exact-tree:KL-001:review-to-merge')

    def test_exact_tree_exception_does_not_replace_review_binding_ancestry(self):
        self.result(tested=self.base)
        result_commit = self.commit('persist result')
        review_commit = self.review(result_commit)
        unrelated_review_commit = self.sibling_commit(review_commit, 'parallel review record')
        self.git('checkout', '-q', '--detach', unrelated_review_commit)
        self.integration_record(
            result_commit, result_commit, unrelated_review_commit, unrelated_review_commit)
        self.check(1, 'integration-ancestry:KL-001:reviewed-to-review-record')

    def test_integration_rejects_result_changed_before_review(self):
        result_path, result = self.result(ext='yaml', tested=self.base)
        result['task_status'] = 'BLOCKED'
        result['task_checks_status'] = 'FAIL'
        self.save_result(result_path, result)
        result_commit = self.commit('persist blocked result')
        result['task_status'] = 'PASS'
        result['task_checks_status'] = 'PASS'
        self.save_result(result_path, result)
        reviewed = self.commit('replace result before review')
        review_commit = self.review(reviewed)
        dump(self.root / 'docs/exec-plans/integrations/KL-001.json', {
            'task_identity': self.task['task_identity'],
            'display_task_id': 'KL-001',
            'result_commit': result_commit,
            'reviewed_head_sha': reviewed,
            'review_record_commit': review_commit,
            'merge_commit': review_commit,
            'integration_status': 'MERGED',
        })
        self.check(1, 'integration-result-content-mismatch:KL-001')

    def test_integration_rejects_nonpass_or_semantically_invalid_result(self):
        result_path, result = self.result(ext='yaml', tested=self.base)
        result['commands_run'][0]['check_id'] = 'invented_check'
        self.save_result(result_path, result)
        result_commit = self.commit('persist semantically invalid PASS result')
        review_commit = self.review(result_commit)
        dump(self.root / 'docs/exec-plans/integrations/KL-001.json', {
            'task_identity': self.task['task_identity'],
            'display_task_id': 'KL-001',
            'result_commit': result_commit,
            'reviewed_head_sha': result_commit,
            'review_record_commit': review_commit,
            'merge_commit': review_commit,
            'integration_status': 'MERGED',
        })
        self.check(1, 'integration-result-semantic:KL-001:result-check-ids')

    def test_integration_rejects_unchanged_nonpass_result(self):
        result_path, result = self.result(ext='yaml', tested=self.base)
        result['task_status'] = 'BLOCKED'
        result['task_checks_status'] = 'FAIL'
        self.save_result(result_path, result)
        result_commit = self.commit('persist blocked result')
        review_commit = self.review(result_commit)
        dump(self.root / 'docs/exec-plans/integrations/KL-001.json', {
            'task_identity': self.task['task_identity'],
            'display_task_id': 'KL-001',
            'result_commit': result_commit,
            'reviewed_head_sha': result_commit,
            'review_record_commit': review_commit,
            'merge_commit': review_commit,
            'integration_status': 'MERGED',
        })
        self.check(1, 'integration-result-not-pass:KL-001')

    def test_integration_rejects_result_representation_switch_before_review(self):
        result_path, result = self.result(ext='yaml', tested=self.base)
        result_commit = self.commit('persist YAML result')
        result_path.unlink()
        json_path = result_path.with_suffix('.json')
        self.save_result(json_path, result)
        reviewed = self.commit('switch result representation before review')
        review_commit = self.review(reviewed)
        dump(self.root / 'docs/exec-plans/integrations/KL-001.json', {
            'task_identity': self.task['task_identity'],
            'display_task_id': 'KL-001',
            'result_commit': result_commit,
            'reviewed_head_sha': reviewed,
            'review_record_commit': review_commit,
            'merge_commit': review_commit,
            'integration_status': 'MERGED',
        })
        self.check(1, 'integration-result-path-mismatch:KL-001')

    def test_integration_rejects_both_result_representations(self):
        self.result(ext='yaml', tested=self.base)
        self.result(ext='json', tested=self.base)
        result_commit = self.commit('persist duplicate result representations')
        review_commit = self.review(result_commit)
        dump(self.root / 'docs/exec-plans/integrations/KL-001.json', {
            'task_identity': self.task['task_identity'],
            'display_task_id': 'KL-001',
            'result_commit': result_commit,
            'reviewed_head_sha': result_commit,
            'review_record_commit': review_commit,
            'merge_commit': review_commit,
            'integration_status': 'MERGED',
        })
        self.check(1, 'integration-result-representation-count:KL-001:2')

    def test_integration_rejects_missing_result_representation(self):
        review_commit = self.review(self.base)
        dump(self.root / 'docs/exec-plans/integrations/KL-001.json', {
            'task_identity': self.task['task_identity'],
            'display_task_id': 'KL-001',
            'result_commit': self.base,
            'reviewed_head_sha': self.base,
            'review_record_commit': review_commit,
            'merge_commit': review_commit,
            'integration_status': 'MERGED',
        })
        self.check(1, 'integration-result-representation-count:KL-001:0')

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
