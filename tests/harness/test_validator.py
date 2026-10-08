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
from types import SimpleNamespace
from typing import Any
from unittest import mock

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
        fixture_omissions = ('docs/exec-plans/milestones/', 'docs/exec-plans/evidence/HG-054/')
        for name in dict.fromkeys(names):
            if name.startswith(fixture_omissions):
                # Generic fixtures deliberately have no closure; READY-specific
                # tests exercise the fail-closed admission rule. HG054 delivery
                # maps bind real source Git ancestry, unavailable in this new
                # repository; each scenario constructs its own fixture evidence.
                continue
            dst = self.root / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dst)
        fixture_manifest_path = self.root / v.MANIFEST
        fixture_manifest = json.loads(fixture_manifest_path.read_text())
        fixture_manifest['files'] = [
            entry for entry in fixture_manifest['files']
            if not entry['path'].startswith(fixture_omissions)
        ]
        dump(fixture_manifest_path, fixture_manifest)
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
        task = self.refine_task(task_id)
        refresh(self.root)
        tested = self.commit('refine packet')
        return self.persist_governance_change(
            change_id, tested, [task_id], task.get('review_requirements', []),
            change_status)

    def emergency_candidate(self, *, include_task_review=True,
                            task_reviewed_head=None):
        record_path = self.root / 'docs/exec-plans/governance/HG-024.yaml'
        record = yaml.safe_load((ROOT / 'docs/exec-plans/governance/HG-024.yaml').read_text())
        record['summary'] += ' emergency fixture'
        self.save_result(record_path, record)
        self.put(
            'docs/exec-plans/completed/KL-073_RESULT.yaml',
            'task_identity: harness-backlog-v0.2/KL-073\n',
        )
        reviewed = self.commit('stage HG-024 and KL-073 emergency pair')
        self.governance_review('HG-024', reviewed)
        if include_task_review:
            dump(self.root / 'docs/exec-plans/reviews/KL-073/GENERAL.json', {
                'task_identity': 'harness-backlog-v0.2/KL-073',
                'reviewed_head_sha': task_reviewed_head or reviewed,
                'review_type': 'GENERAL',
                'review_contract_version': 'v0.2',
                'status': 'PASS',
                'findings': [],
            })
        self.commit('persist emergency reviews')
        return reviewed

    def refine_task(self, task_id='KL-008'):
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
        traceability_path = self.root / v.TRACEABILITY
        traceability = json.loads(traceability_path.read_text())
        trace = next(item for item in traceability['tasks'] if item['id'] == task_id)
        for field in v.TRACEABILITY_TASK_FIELDS:
            trace[field] = task.get(field)
        dump(traceability_path, traceability)
        return task

    def retire_task(self, task_id='KL-008', *, update_active_count=True,
                    preserve_requirement_mapping=True, replacement_mode='valid',
                    packet_replacement='KL-001', include_schedule_barrier=True,
                    include_reason=True, metadata_replacements=None,
                    packet_reason=None, duplicate_reason=None,
                    schedule_barrier_text='Scheduling barrier: MUST NOT be scheduled.'):
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        original_dependencies = list(task['depends_on'])
        replacements = (
            [] if replacement_mode == 'empty'
            else original_dependencies if replacement_mode == 'unchanged'
            else ['KL-999'] if replacement_mode == 'unknown'
            else ['KL-001']
        )
        reason = 'The user approved this fixture retirement because replacement work exists.'
        projected_reason = reason if packet_reason is None else packet_reason
        task.update({
            'title': task['title'] + ' (retired by explicit user decision)',
            'depends_on': replacements,
            'deliverables': ['No implementation for this retired fixture task'],
            'definition_of_done': (
                'No implementation; traceability preserved by the explicit replacement.'
            ),
            'status': 'SUPERSEDED',
            'superseded_by': (
                replacements if metadata_replacements is None
                else metadata_replacements
            ),
            'disposition_reason': reason if include_reason else '',
        })
        if not preserve_requirement_mapping:
            task['requirements_covered'] = ['INT-A01@PU']
        if update_active_count:
            backlog['active_task_count'] = sum(
                item['status'] != 'SUPERSEDED' for item in backlog['tasks'])
        dump(backlog_path, backlog)

        packet = self.root / f'docs/exec-plans/active/{task_id}.md'
        projected_replacements = (
            packet_replacement if isinstance(packet_replacement, list)
            else [] if packet_replacement is None
            else [packet_replacement]
        )
        packet.write_text(
            f'# {task_id} — SUPERSEDED\n\n'
            f'Task identity `{task["task_identity"]}` is traceability-only.\n\n'
            + (f'{schedule_barrier_text}\n\n' if include_schedule_barrier else '')
            + '## Disposition\n\n'
            + (f'Reason: {projected_reason}\n' if include_reason else 'Reason: \n')
            + (f'Reason: {duplicate_reason}\n' if duplicate_reason is not None else '')
            + '\n'
            + 'Replacement tasks:\n'
            + ''.join(f'- {replacement}\n' for replacement in projected_replacements)
        )

        traceability_path = self.root / v.TRACEABILITY
        traceability = json.loads(traceability_path.read_text())
        trace = next(item for item in traceability['tasks'] if item['id'] == task_id)
        for field in v.TRACEABILITY_TASK_FIELDS:
            trace[field] = task.get(field)
        dump(traceability_path, traceability)
        return task


    def add_governance_task(self, task_id='KL-999', status='NOT_STARTED',
                            add_review_artifact=False):
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        template = copy.deepcopy(next(item for item in backlog['tasks']
                                      if item['id'] == 'KL-072'))
        template.update({
            'id': task_id,
            'task_identity': 'harness-backlog-v0.2/' + task_id,
            'thread_id': 'THREAD-' + task_id,
            'handoff_artifact': f'docs/exec-plans/completed/{task_id}_RESULT.yaml',
            'status': status,
            'evidence_paths': [f'docs/exec-plans/evidence/{task_id}/**'],
        })
        backlog['tasks'].append(template)
        backlog['task_count'] = len(backlog['tasks'])
        backlog['active_task_count'] = sum(
            task['status'] != 'SUPERSEDED' for task in backlog['tasks'])
        dump(backlog_path, backlog)

        source_packet = self.root / 'docs/exec-plans/active/KL-072.md'
        packet_text = source_packet.read_text().replace('KL-072', task_id)
        packet_text = packet_text.replace('**Status:** NOT_STARTED', f'**Status:** {status}')
        packet_text = packet_text.replace(
            'docs/exec-plans/evidence/KL-072/**',
            f'docs/exec-plans/evidence/{task_id}/**')
        self.put(f'docs/exec-plans/active/{task_id}.md', packet_text)

        trace_path = self.root / v.TRACEABILITY
        traceability = json.loads(trace_path.read_text())
        traceability['tasks'].append({
            field: template.get(field) for field in v.TRACEABILITY_TASK_FIELDS
        })
        dump(trace_path, traceability)
        if add_review_artifact:
            dump(self.root / f'docs/exec-plans/reviews/{task_id}/GENERAL.json', {
                'task_identity': template['task_identity'],
                'reviewed_head_sha': self.base,
                'review_type': 'GENERAL',
                'review_contract_version': 'v0.2',
                'status': 'PASS',
                'findings': [],
            })
        refresh(self.root)
        return template

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

    def test_ready_m2_task_without_closure_rejected(self):
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-010')
        task['status'] = 'READY'
        dump(backlog_path, backlog)
        refresh(self.root)
        self.check(1, 'ready-m1-closure-invalid:KL-010')

    def test_duplicate_m1_closure_rejected(self):
        fixture = {'display_milestone_id': 'M1'}
        dump(self.root / 'docs/exec-plans/milestones/M1.json', fixture)
        dump(self.root / 'docs/exec-plans/milestones/M1-copy.json', fixture)
        self.check(1, 'milestone-closure-count:M1:2')

    def test_duplicate_m2_closure_rejected(self):
        fixture = {'display_milestone_id': 'M2'}
        dump(self.root / 'docs/exec-plans/milestones/M2.json', fixture)
        dump(self.root / 'docs/exec-plans/milestones/M2-copy.json', fixture)
        self.check(1, 'milestone-closure-count:M2:2')

    def test_malformed_m2_closure_discovery_rejected(self):
        dump(self.root / 'docs/exec-plans/milestones/M2.json', {
            'display_milestone_id': 'M2',
        })
        self.check(1, 'milestone-schema:M2.json:')

    def test_m2_closure_cannot_hide_by_omitting_or_changing_identity(self):
        records: tuple[object, ...] = ({}, {'display_milestone_id': 'UNKNOWN'}, [])
        for record in records:
            dump(self.root / 'docs/exec-plans/milestones/M2.json', record)
            self.check(1, 'milestone-schema:M2.json:')

    def test_unknown_milestone_file_rejected(self):
        dump(self.root / 'docs/exec-plans/milestones/unknown.json', {})
        self.check(1, 'milestone-unsupported-record:unknown.json')

    def test_m2_regression_requires_real_outputs_and_unskipped_db_cases(self):
        paths = {
            'pytest': 'docs/exec-plans/evidence/HG-023/pytest.log',
            'harness': 'docs/exec-plans/evidence/HG-023/harness.log',
            'junit': 'docs/exec-plans/evidence/HG-023/junit.xml',
            'collection': 'docs/exec-plans/evidence/HG-023/collection.json',
            'collection_stdout': 'docs/exec-plans/evidence/HG-023/collection.log',
        }
        self.put(paths['pytest'], '6 passed in 1.0s\n')
        self.put(paths['harness'], 'HARNESS_CHECK_PASS tasks=69 active=67\n')
        cases = [
            ('tests.db.test_migrations', 'test_empty_db_upgrade_head'),
            *[('tests.db.test_transaction_interfaces', name) for name in (
                'test_reverse_lock_order_is_rejected', 'test_event_outbox_atomicity_enforced',
                'test_stale_fence_commit_is_rejected',
                'test_ack_loss_replay_preserves_natural_uniqueness',
            )],
            ('tests.unit.test_example', 'test_additional_case'),
        ]
        junit = '<testsuites><testsuite>' + ''.join(
            f'<testcase classname="{cls}" name="{name}"/>' for cls, name in cases
        ) + '</testsuite></testsuites>'
        self.put(paths['junit'], junit)
        nodeids = [cls.replace('.', '/') + '.py::' + name for cls, name in cases]
        self.put(paths['collection_stdout'], '\n'.join(nodeids) + '\n\n6 tests collected in 0.1s\n')
        dump(self.root / paths['collection'], {
            'command': 'uv run pytest --collect-only -q', 'exit_code': 0,
            'tested_commit': self.base,
            'nodeids': nodeids,
            'stdout': {'path': paths['collection_stdout'],
                       'sha256': v.sha(self.root / paths['collection_stdout'])},
        })
        revision = self.commit('fixture execution evidence')

        def ref(name):
            return {'path': paths[name], 'sha256': v.sha(self.root / paths[name])}

        payload = {'tested_commit': self.base, 'executions': [
            {'command': v.M2_REGRESSION_COMMANDS[0], 'exit_code': 0,
             'tested_commit': self.base, 'stdout': ref('pytest'), 'junit': ref('junit')},
            {'command': v.M2_REGRESSION_COMMANDS[1], 'exit_code': 0,
             'tested_commit': self.base, 'stdout': ref('harness')},
        ]}
        payload['executions'][0]['collection'] = ref('collection')
        self.assertEqual(v.m2_execution_evidence_errors(self.root, payload, revision), [])
        for variant in ('exit', 'missing-output', 'unbound', 'no-executions'):
            mutated = copy.deepcopy(payload)
            if variant == 'exit':
                mutated['executions'][0]['exit_code'] = 1
            elif variant == 'missing-output':
                mutated['executions'][0].pop('stdout')
            elif variant == 'unbound':
                mutated['executions'][0]['tested_commit'] = 'a' * 40
            else:
                mutated.pop('executions')
            self.assertTrue(v.m2_execution_evidence_errors(self.root, mutated, revision))
        for report in (
                junit.replace('/>', '><skipped/></testcase>', 1),
                junit.replace('/>', '><failure/></testcase>', 1),
                '<testsuites><testsuite/></testsuites>',
                '<testsuites><testcase classname="tests.unit" name="only_unit"/></testsuites>'):
            self.put(paths['junit'], report)
            revision = self.commit('fixture invalid report')
            mutated = copy.deepcopy(payload)
            mutated['executions'][0]['junit'] = ref('junit')
            self.assertTrue(v.m2_execution_evidence_errors(self.root, mutated, revision))

        # Cutting both derived reports must not hide a collected test.
        collection = v.load_artifact(self.root / paths['collection'])
        collection['nodeids'].pop()
        dump(self.root / paths['collection'], collection)
        self.put(paths['junit'], junit.replace(
            '<testcase classname="tests.unit.test_example" name="test_additional_case"/>', ''))
        self.put(paths['pytest'], '5 passed in 1.0s\n')
        revision = self.commit('crop collection and junit together')
        mutated = copy.deepcopy(payload)
        mutated['executions'][0].update({
            'collection': ref('collection'), 'junit': ref('junit'), 'stdout': ref('pytest'),
        })
        self.assertIn('milestone-regression-execution:collection-stdout-oracle',
                      v.m2_execution_evidence_errors(self.root, mutated, revision))

    def test_m2_schema_requires_exact_task_count_and_exit_check_vocabulary(self):
        from jsonschema import Draft202012Validator

        schema = Draft202012Validator(v.load_artifact(ROOT / v.MILESTONE_CLOSURE_SCHEMA))
        integration = {
            'task_identity': 'harness-backlog-v0.2/KL-010',
            'display_task_id': 'KL-010',
            'integration_record': 'docs/exec-plans/integrations/KL-010.json',
            'sha256': 'a' * 64,
        }
        closure: dict[str, Any] = {
            'milestone_identity': 'harness-backlog-v0.2/M2',
            'display_milestone_id': 'M2',
            'closure_status': 'PASS',
            'evaluated_commit': 'a' * 40,
            'integrations': [copy.deepcopy(integration) for _ in range(12)],
            'exit_checks': [
                {'check_id': check_id, 'result': 'PASS', 'evidence': [{
                    'path': 'evidence.json', 'revision': 'a' * 40, 'sha256': 'b' * 64,
                }]}
                for check_id in (
                    'm2_task_integrations_valid',
                    'm2_regression_suite_passes',
                    'frozen_authority_and_requirement_claims_preserved',
                    *v.M2_EXIT_TASK_CHECKS,
                )
            ],
            'historical_model_evidence': {
                'status': 'UNVERIFIED_HISTORICAL_DECLARATION',
                'independently_reproducible_protocol_model': False,
            },
            'product_requirement_pass_claims': [],
        }
        self.assertFalse(list(schema.iter_errors(closure)))
        closure['integrations'].pop()
        self.assertTrue(list(schema.iter_errors(closure)))
        closure['integrations'].append(copy.deepcopy(integration))
        closure['exit_checks'][0]['check_id'] = 'generic_pass'
        self.assertTrue(list(schema.iter_errors(closure)))

    def test_m2_check_contract_missing_duplicate_and_generic_rejected(self):
        backlog_path = self.root / v.BACKLOG
        original = json.loads(backlog_path.read_text())
        for variant, key in (
                ('missing', 'check-contract-ids:KL-010'),
                ('duplicate', 'check-contract-ids:KL-010'),
                ('generic', 'check-contract-generic-or-invalid:KL-010')):
            backlog = copy.deepcopy(original)
            task = next(item for item in backlog['tasks'] if item['id'] == 'KL-010')
            if variant == 'missing':
                task['check_contracts'].pop()
            elif variant == 'duplicate':
                task['check_contracts'].append(copy.deepcopy(task['check_contracts'][0]))
            else:
                task['check_contracts'][0]['command'] = 'TODO placeholder'
            dump(backlog_path, backlog)
            self.check(1, key)
        dump(backlog_path, original)

    def test_m2_wrong_or_escaping_evidence_path_rejected(self):
        backlog_path = self.root / v.BACKLOG
        original = json.loads(backlog_path.read_text())
        for evidence_path in ('docs/exec-plans/evidence/KL-011/**', '../escape/**'):
            backlog = copy.deepcopy(original)
            task = next(item for item in backlog['tasks'] if item['id'] == 'KL-010')
            task['evidence_paths'] = [evidence_path]
            dump(backlog_path, backlog)
            self.check(1, 'evidence-path:KL-010')
        dump(backlog_path, original)

    def test_m2_required_security_contracts_cannot_be_removed(self):
        backlog_path = self.root / v.BACKLOG
        original = json.loads(backlog_path.read_text())

        backlog = copy.deepcopy(original)
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-055')
        removed = {
            'provider_contract_is_hermetic',
            'provider_fixtures_pass_hardened_synthetic_guard',
        }
        task['checks_required_for_this_task'] = [
            check_id for check_id in task['checks_required_for_this_task']
            if check_id not in removed
        ]
        task['check_contracts'] = [
            contract for contract in task['check_contracts']
            if contract['check_id'] not in removed
        ]
        dump(backlog_path, backlog)
        self.check(1, 'm2-required-semantic-checks:KL-055')

        backlog = copy.deepcopy(original)
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-018')
        removed = {
            'artifact_dependencies_must_be_pre_registered',
            'artifact_dependency_graph_is_acyclic',
            'artifact_dependency_closure_is_bounded',
        }
        task['checks_required_for_this_task'] = [
            check_id for check_id in task['checks_required_for_this_task']
            if check_id not in removed
        ]
        task['check_contracts'] = [
            contract for contract in task['check_contracts']
            if contract['check_id'] not in removed
        ]
        dump(backlog_path, backlog)
        self.check(1, 'm2-required-semantic-checks:KL-018')

        backlog = copy.deepcopy(original)
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-015')
        removed = {
            'factset_build_stays_outside_subject_coordination',
            't6_ack_loss_replay_returns_same_issuance',
        }
        task['checks_required_for_this_task'] = [
            check_id for check_id in task['checks_required_for_this_task']
            if check_id not in removed
        ]
        task['check_contracts'] = [
            contract for contract in task['check_contracts']
            if contract['check_id'] not in removed
        ]
        dump(backlog_path, backlog)
        self.check(1, 'm2-required-semantic-checks:KL-015')

        backlog = copy.deepcopy(original)
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-017')
        removed = {'cross_subject_denial_is_non_enumerating'}
        task['checks_required_for_this_task'] = [
            check_id for check_id in task['checks_required_for_this_task']
            if check_id not in removed
        ]
        task['check_contracts'] = [
            contract for contract in task['check_contracts']
            if contract['check_id'] not in removed
        ]
        dump(backlog_path, backlog)
        self.check(1, 'm2-required-semantic-checks:KL-017')

        backlog = copy.deepcopy(original)
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-055')
        removed = {
            'provider_subject_source_binding_is_trusted',
            'evidence_envelope_closed_s09_schema',
            'provider_credentials_do_not_cross_evidence_or_diagnostic_boundary',
        }
        task['checks_required_for_this_task'] = [
            check_id for check_id in task['checks_required_for_this_task']
            if check_id not in removed
        ]
        task['check_contracts'] = [
            contract for contract in task['check_contracts']
            if contract['check_id'] not in removed
        ]
        dump(backlog_path, backlog)
        self.check(1, 'm2-required-semantic-checks:KL-055')

        backlog = copy.deepcopy(original)
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-014')
        removed = {'preparation_and_registry_management_stay_outside_atomic_boundaries'}
        task['checks_required_for_this_task'] = [
            check_id for check_id in task['checks_required_for_this_task']
            if check_id not in removed
        ]
        task['check_contracts'] = [
            contract for contract in task['check_contracts']
            if contract['check_id'] not in removed
        ]
        dump(backlog_path, backlog)
        self.check(1, 'm2-required-semantic-checks:KL-014')

        backlog = copy.deepcopy(original)
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-018')
        task['review_requirements'].remove('SECURITY_DATA_BOUNDARY')
        dump(backlog_path, backlog)
        self.check(1, 'm2-security-review-required:KL-018')

        backlog = copy.deepcopy(original)
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-014')
        task['review_requirements'].remove('DB_CONCURRENCY')
        dump(backlog_path, backlog)
        self.check(1, 'm2-db-review-required:KL-014')
        dump(backlog_path, original)

    def test_kl014_preparation_cannot_be_reclassified_into_atomic_boundaries(self):
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-014')
        task['commands'][0] = 'T1: ReceiveEvidence, RecordCandidate'
        dump(backlog_path, backlog)
        self.check(1, 'm2-kl014-command-surface')

    def test_m2_packet_check_contract_drift_rejected(self):
        packet = self.root / 'docs/exec-plans/active/KL-010.md'
        packet.write_text(packet.read_text().replace(
            'Command exits 0 and prints HARNESS_CHECK_PASS.',
            'Command merely exits 0.', 1))
        self.check(1, 'packet-check-contract:KL-010')

    def test_m2_result_requires_exact_command_and_task_owned_evidence(self):
        backlog = json.loads((self.root / v.BACKLOG).read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-010')
        evidence = 'docs/exec-plans/evidence/KL-010/checks.log'
        self.put(evidence, 'exact KL-010 checks\n')
        result = {
            'task_identity': task['task_identity'],
            'display_task_id': task['id'],
            'task_status': 'PASS',
            'task_checks_status': 'PASS',
            'tested_commit': self.base,
            'requirements_covered': [],
            'commands_run': [
                {
                    'check_id': contract['check_id'],
                    'command': contract['command'],
                    'result': 'PASS',
                    'evidence_ref': evidence,
                }
                for contract in task['check_contracts']
            ],
        }
        self.assertEqual([], v.semantic_result_errors(result, task, self.root))
        wrong_command = copy.deepcopy(result)
        wrong_command['commands_run'][0]['command'] = 'true'
        self.assertIn(
            'command-contract-command:' + wrong_command['commands_run'][0]['check_id'],
            v.semantic_result_errors(wrong_command, task, self.root),
        )
        wrong_evidence = copy.deepcopy(result)
        wrong_evidence['commands_run'][0]['evidence_ref'] = v.INDEX
        self.assertIn(
            'command-evidence-scope:' + wrong_evidence['commands_run'][0]['check_id'],
            v.semantic_result_errors(wrong_evidence, task, self.root),
        )

    def test_m2_packet_material_contract_drift_rejected(self):
        packet = self.root / 'docs/exec-plans/active/KL-010.md'
        original = packet.read_text()
        variants = (
            ('- 04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
             '- 12_KineticLoop_Integration_Spec_v0.1.md',
             'packet-context-files:KL-010'),
            ('FK/reference-root migration plan', 'wrong deliverable',
             'packet-deliverables:KL-010'),
            ('DDL ordering follows references, not logical table numbers', 'wrong DoD',
             'packet-definition-of-done:KL-010'),
            ('Environment requirements:\n- none',
             'Environment requirements:\n- ISOLATED_POSTGRESQL_NAMESPACE',
             'packet-environment:KL-010'),
            ('Parallel write policy: **PARALLEL_IF_DEPENDENCIES_MET**',
             'Parallel write policy: **SERIALIZE_WITH_OTHER_HOTSPOT_TASKS**',
             'packet-parallel-policy:KL-010'),
            ('- Logical tables: S01-S51', '- Logical tables: S01-S50',
             'packet-impact-map:KL-010:logical-tables'),
        )
        for old, new, expected in variants:
            packet.write_text(original.replace(old, new, 1))
            self.check(1, expected)
        packet.write_text(original)

    def test_m2_kl015_synchronized_frozen_impact_underdeclaration_rejected(self):
        backlog_path = self.root / v.BACKLOG
        traceability_path = self.root / v.TRACEABILITY
        packet_path = self.root / 'docs/exec-plans/active/KL-015.md'
        original_backlog = json.loads(backlog_path.read_text())
        original_traceability = json.loads(traceability_path.read_text())
        original_packet = packet_path.read_text()

        for field, omitted, packet_token, expected in (
                ('invariant_ids', 'INV-11', ', INV-11',
                 'm2-kl015-frozen-impact:invariants'),
                ('transaction_boundaries', 'T1-T8', '- Transactions: T1-T8',
                 'm2-kl015-frozen-impact:transactions'),
                ('table_ids', 'S19', ', S19',
                 'm2-kl015-frozen-impact:tables'),
                ('table_ids', 'S42', ', S42',
                 'm2-kl015-frozen-impact:tables'),
                ('table_ids', 'S48', ', S48',
                 'm2-kl015-frozen-impact:tables')):
            backlog = copy.deepcopy(original_backlog)
            task = next(item for item in backlog['tasks'] if item['id'] == 'KL-015')
            task[field].remove(omitted)
            dump(backlog_path, backlog)

            traceability = copy.deepcopy(original_traceability)
            trace = next(item for item in traceability['tasks'] if item['id'] == 'KL-015')
            trace[field].remove(omitted)
            dump(traceability_path, traceability)

            packet_path.write_text(original_packet.replace(packet_token, '', 1))
            refresh(self.root)
            self.check(1, expected)

        dump(backlog_path, original_backlog)
        dump(traceability_path, original_traceability)
        packet_path.write_text(original_packet)
        refresh(self.root)

    def test_m2_security_contracts_reject_removal_substitution_and_weakening(self):
        backlog_path = self.root / v.BACKLOG
        traceability_path = self.root / v.TRACEABILITY
        original_backlog = json.loads(backlog_path.read_text())
        original_traceability = json.loads(traceability_path.read_text())
        selected = [
            ('KL-014', 'identity_idempotency_and_basis_fields'),
            ('KL-015', 'catalog_mapping_and_release_owner_boundaries_complete'),
            ('KL-016', 'shared_gate_command_matrix_fails_closed'),
            ('KL-016', 'revoke_artifact_atomic_linearization_and_idempotency'),
            ('KL-072', 'successor_migration_contains_no_cluster_role_ddl'),
            ('KL-072', 'safety_registry_role_preflight_fails_before_object_changes'),
            ('KL-072', 'safety_registry_object_ownership_enforced'),
            ('KL-072', 'safety_registry_command_routine_privileges_enforced'),
            ('KL-072', 'safety_registry_definer_search_path_and_schema_acl_enforced'),
            ('KL-072', 'safety_registry_runtime_login_boundary_enforced'),
            ('KL-017', 'cross_subject_denial_is_non_enumerating'),
            ('KL-017', 'complete_db_suite_passes'),
            ('KL-018', 'artifact_registry_successor_migration_chain'),
            ('KL-018', 'artifact_registration_command_routine_privileges_enforced'),
            ('KL-018', 'artifact_registration_session_authority_enforced'),
            ('KL-018', 'artifact_identity_is_immutable'),
            ('KL-018', 'artifact_validity_is_null_total'),
            ('KL-018', 'artifact_timeless_policy_is_registered_dependency'),
            ('KL-018', 'artifact_persistence_denials_are_stable'),
            ('KL-018', 'artifact_dependency_dense_graph_is_bounded'),
            ('KL-018', 'artifact_registration_lock_timeout_is_atomic'),
            ('KL-018', 'artifact_registration_post_write_failure_is_atomic'),
            ('KL-018', 'artifact_registration_safety_registry_privilege_regression'),
            ('KL-018', 'complete_db_suite_passes'),
            ('KL-055', 'provider_subject_source_binding_is_trusted'),
        ]
        original_packets = {
            task_id: (self.root / f'docs/exec-plans/active/{task_id}.md').read_text()
            for task_id, _ in selected
        }

        for task_id, check_id in selected:
            expected = f'm2-security-contract:{task_id}:{check_id}'
            source_task = next(
                item for item in original_backlog['tasks'] if item['id'] == task_id)
            source_contract = next(
                item for item in source_task['check_contracts']
                if item['check_id'] == check_id)
            for variant in ('remove', 'command', 'oracle', 'coordinated'):
                backlog = copy.deepcopy(original_backlog)
                task = next(item for item in backlog['tasks'] if item['id'] == task_id)
                contract = next(
                    item for item in task['check_contracts'] if item['check_id'] == check_id)
                if variant == 'remove':
                    task['checks_required_for_this_task'].remove(check_id)
                    task['check_contracts'].remove(contract)
                elif variant == 'command':
                    contract['command'] = 'true'
                else:
                    contract['pass_oracle'] = 'Command exits 0.'
                dump(backlog_path, backlog)

                if variant == 'coordinated':
                    traceability = copy.deepcopy(original_traceability)
                    trace = next(
                        item for item in traceability['tasks'] if item['id'] == task_id)
                    trace_contract = next(
                        item for item in trace['check_contracts']
                        if item['check_id'] == check_id)
                    trace_contract['pass_oracle'] = 'Command exits 0.'
                    dump(traceability_path, traceability)
                    packet_path = self.root / f'docs/exec-plans/active/{task_id}.md'
                    packet_path.write_text(original_packets[task_id].replace(
                        source_contract['pass_oracle'], 'Command exits 0.', 1))
                    refresh(self.root)

                self.check(1, expected)

                dump(backlog_path, original_backlog)
                dump(traceability_path, original_traceability)
                for packet_task_id, packet_text in original_packets.items():
                    (self.root / f'docs/exec-plans/active/{packet_task_id}.md').write_text(
                        packet_text)
                refresh(self.root)

    def test_m2_kl016_synchronized_registry_command_omission_rejected(self):
        backlog_path = self.root / v.BACKLOG
        traceability_path = self.root / v.TRACEABILITY
        packet_path = self.root / 'docs/exec-plans/active/KL-016.md'
        backlog = json.loads(backlog_path.read_text())
        traceability = json.loads(traceability_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == 'KL-016')
        trace = next(item for item in traceability['tasks'] if item['id'] == 'KL-016')
        task['commands'].remove('Reauthorize')
        trace['commands'].remove('Reauthorize')
        dump(backlog_path, backlog)
        dump(traceability_path, traceability)
        packet_path.write_text(packet_path.read_text().replace('- Reauthorize\n', '', 1))
        refresh(self.root)
        self.check(1, 'm2-kl016-command-surface')


    def test_m2_kl018_registry_migration_scope_cannot_be_removed(self):
        backlog_path = self.root / v.BACKLOG
        original = json.loads(backlog_path.read_text())
        for field, value in (
                ('resource_keys', 'migration_chain'),
                ('resource_keys', 'persistence_permissions'),
                ('write_paths', 'migrations/versions/*_artifact_registry.py'),
                ('write_paths', 'tests/db/test_migrations.py'),
                ('write_paths', 'tests/db/test_safety_registry.py')):
            backlog = copy.deepcopy(original)
            task = next(item for item in backlog['tasks'] if item['id'] == 'KL-018')
            task[field].remove(value)
            dump(backlog_path, backlog)
            self.check(1, 'm2-kl018-registry-migration-scope')
        dump(backlog_path, original)

    def test_m2_kl017_successor_migration_scope_cannot_be_removed(self):
        backlog_path = self.root / v.BACKLOG
        original = json.loads(backlog_path.read_text())
        for field, value in (
                ('depends_on', 'KL-018'),
                ('resource_keys', 'registry_coordination'),
                ('write_paths', 'tests/db/test_migrations.py'),
                ('write_paths', 'tests/db/test_safety_registry.py')):
            backlog = copy.deepcopy(original)
            task = next(item for item in backlog['tasks'] if item['id'] == 'KL-017')
            task[field].remove(value)
            dump(backlog_path, backlog)
            self.check(1, 'm2-kl017-successor-migration-scope')
        dump(backlog_path, original)

    def test_manifest_claimed_m1_closure_cannot_be_missing(self):
        manifest_path = self.root / v.MANIFEST
        manifest = json.loads(manifest_path.read_text())
        source_manifest = json.loads((ROOT / v.MANIFEST).read_text())
        closure_entry = next(
            entry for entry in source_manifest['files']
            if entry['path'] == 'docs/exec-plans/milestones/M1.json')
        manifest['files'].append(closure_entry)
        dump(manifest_path, manifest)
        self.check(1, 'manifest-missing:docs/exec-plans/milestones/M1.json')

    def test_malformed_m1_closure_discovery_rejected(self):
        dump(self.root / 'docs/exec-plans/milestones/M1.json', {
            'display_milestone_id': 'M1',
        })
        self.check(1, 'milestone-schema:M1.json:')

    def test_unlocked_m2_write_overlap_rejected(self):
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        left = next(item for item in backlog['tasks'] if item['id'] == 'KL-010')
        right = next(item for item in backlog['tasks'] if item['id'] == 'KL-011')
        left['write_paths'] = ['src/shared.py']
        right['write_paths'] = ['src/shared.py']
        left['resource_keys'] = ['schema_topology']
        right['resource_keys'] = ['canonical_fact_schema']
        dump(backlog_path, backlog)
        self.check(1, 'unlocked-write-path-overlap:KL-010:KL-011')

    def closure_errors(self, closure):
        from jsonschema import Draft202012Validator

        backlog = v.load_artifact(ROOT / v.BACKLOG)
        _, tasks = v.task_definition_errors(ROOT, backlog)
        return v.milestone_closure_errors(
            ROOT,
            closure,
            Draft202012Validator(v.load_artifact(ROOT / v.MILESTONE_CLOSURE_SCHEMA)),
            Draft202012Validator(v.load_artifact(ROOT / v.INTEGRATION_SCHEMA)),
            Draft202012Validator(v.load_artifact(ROOT / 'THREAD_RESULT.schema.json')),
            Draft202012Validator(v.load_artifact(ROOT / 'THREAD_REVIEW.schema.json')),
            backlog,
            tasks,
        )

    def test_m1_closure_rejects_missing_extra_and_mismatched_tasks(self):
        original = v.load_artifact(ROOT / 'docs/exec-plans/milestones/M1.json')
        missing = copy.deepcopy(original)
        missing['integrations'].pop()
        self.assertTrue(self.closure_errors(missing))
        extra = copy.deepcopy(original)
        extra['integrations'].append(copy.deepcopy(extra['integrations'][0]))
        self.assertTrue(self.closure_errors(extra))
        mismatch = copy.deepcopy(original)
        mismatch['integrations'][0]['task_identity'] = 'harness-backlog-v0.2/KL-002'
        self.assertIn('milestone-integration-binding:KL-001', self.closure_errors(mismatch))

    def test_m1_closure_rejects_model_overclaim_and_exit_evidence_failures(self):
        original = v.load_artifact(ROOT / 'docs/exec-plans/milestones/M1.json')
        overclaim = copy.deepcopy(original)
        overclaim['historical_model_evidence'][
            'independently_reproducible_protocol_model'] = True
        self.assertTrue(self.closure_errors(overclaim))
        failed = copy.deepcopy(original)
        failed['exit_checks'][0]['result'] = 'FAIL'
        self.assertTrue(self.closure_errors(failed))
        missing = copy.deepcopy(original)
        missing['exit_checks'][0]['evidence'] = []
        self.assertTrue(self.closure_errors(missing))
        bad_hash = copy.deepcopy(original)
        bad_hash['exit_checks'][0]['evidence'][0]['sha256'] = '0' * 64
        self.assertIn(
            'milestone-exit-evidence-hash:clean_checkout_starts_test_environment',
            self.closure_errors(bad_hash),
        )
        semantic_substitution = copy.deepcopy(original)
        semantic_substitution['exit_checks'][0]['evidence'] = [
            item for item in semantic_substitution['exit_checks'][0]['evidence']
            if '/postgres_ready-' not in item['path']
        ]
        self.assertIn(
            'milestone-exit-evidence-semantic:clean_checkout_starts_test_environment',
            self.closure_errors(semantic_substitution),
        )

    def test_m1_clean_start_evidence_requires_fresh_pass_oracle(self):
        original = v.load_artifact(ROOT / 'docs/exec-plans/milestones/M1.json')
        clean = next(item for item in original['exit_checks']
                     if item['check_id'] == 'clean_checkout_starts_test_environment')

        stale = copy.deepcopy(original)
        stale_clean = next(item for item in stale['exit_checks']
                           if item['check_id'] == 'clean_checkout_starts_test_environment')
        stale_clean['evidence'][0]['revision'] = v.resolve(
            ROOT, original['evaluated_commit'] + '^')
        self.assertIn(
            'milestone-exit-evidence-stale:compose_config_valid',
            self.closure_errors(stale),
        )

        target = clean['evidence'][0]['path']
        real_loader = v.load_artifact_at_revision

        def failing_loader(root, path, revision):
            payload = real_loader(root, path, revision)
            if path == target:
                payload = copy.deepcopy(payload)
                payload['status'] = 'FAIL'
            return payload

        with mock.patch.object(v, 'load_artifact_at_revision', side_effect=failing_loader):
            self.assertIn(
                'milestone-exit-evidence-oracle:compose_config_valid',
                self.closure_errors(original),
            )

    def test_m1_closure_rejects_missing_unmerged_and_unreachable_integration(self):
        original = v.load_artifact(ROOT / 'docs/exec-plans/milestones/M1.json')
        real_loader = v.load_artifact_at_revision
        target = original['integrations'][0]['integration_record']

        def missing_loader(root, path, revision):
            if path == target:
                raise ValueError('fixture-missing')
            return real_loader(root, path, revision)

        with mock.patch.object(v, 'load_artifact_at_revision', side_effect=missing_loader):
            self.assertTrue(any(
                issue.startswith('milestone-integration-invalid:KL-001:')
                for issue in self.closure_errors(original)))

        def changed_loader(root, path, revision, *, unreachable=False):
            record = real_loader(root, path, revision)
            if path == target:
                record = copy.deepcopy(record)
                if unreachable:
                    record['merge_commit'] = v.resolve(ROOT, 'HEAD')
                else:
                    record['integration_status'] = 'UNMERGED'
            return record

        with mock.patch.object(
                v, 'load_artifact_at_revision',
                side_effect=lambda root, path, revision: changed_loader(root, path, revision)):
            self.assertTrue(any(
                'milestone-integration-unmerged:KL-001' in issue
                or 'milestone-integration-invalid:KL-001:' in issue
                for issue in self.closure_errors(original)))
        with mock.patch.object(
                v, 'load_artifact_at_revision',
                side_effect=lambda root, path, revision: changed_loader(
                    root, path, revision, unreachable=True)):
            earlier = copy.deepcopy(original)
            earlier['evaluated_commit'] = v.resolve(
                ROOT, original['evaluated_commit'] + '^')
            self.assertIn(
                'milestone-integration-unreachable:KL-001',
                self.closure_errors(earlier),
            )

    def test_m1_closure_propagates_historical_review_validation_errors(self):
        original = v.load_artifact(ROOT / 'docs/exec-plans/milestones/M1.json')
        with mock.patch.object(
                v, 'integration_record_errors',
                return_value=['integration-review-identity:KL-001:GENERAL']):
            self.assertIn(
                'milestone-integration-invalid:KL-001:'
                'integration-review-identity:KL-001:GENERAL',
                self.closure_errors(original),
            )

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

    def test_emergency_governance_task_pair_is_identity_exact(self):
        self.assertEqual(
            v.emergency_governance_task_pair({'KL-073'}, {'HG-024'}),
            ('HG-024', 'KL-073'),
        )
        for tasks, changes in (
                ({'KL-072'}, {'HG-024'}),
                ({'KL-073'}, {'HG-023'}),
                ({'KL-073', 'KL-072'}, {'HG-024'}),
                ({'KL-073'}, {'HG-024', 'HG-023'}),
                (set(), {'HG-024'}),
                ({'KL-073'}, set())):
            self.assertIsNone(v.emergency_governance_task_pair(tasks, changes))

    def test_hg024_emergency_scope_is_closed_and_non_generalizable(self):
        allowed = set(v.governance_allowed_patterns('HG-024'))
        self.assertIn('tests/db/test_transaction_interfaces.py', allowed)
        self.assertIn('docs/exec-plans/completed/KL-073_RESULT.yaml', allowed)
        self.assertIn('docs/exec-plans/evidence/KL-073/**', allowed)
        self.assertIn('docs/exec-plans/reviews/KL-073/**', allowed)
        self.assertNotIn('tests/db/**', allowed)
        self.assertNotIn('docs/exec-plans/completed/**', allowed)
        self.assertNotIn('docs/exec-plans/evidence/KL-*/**', allowed)
        self.assertNotIn('src/**', allowed)
        self.assertNotEqual(
            v.governance_allowed_patterns('HG-025'),
            v.governance_allowed_patterns('HG-024'),
        )

    def test_ci_hg024_implementation_scope_requires_exact_mixed_pair(self):
        self.put('tests/db/test_transaction_interfaces.py', '# emergency fixture\n')
        record_path = self.root / 'docs/exec-plans/governance/HG-024.yaml'
        record = yaml.safe_load((ROOT / 'docs/exec-plans/governance/HG-024.yaml').read_text())
        record['summary'] += ' governance-only escape fixture'
        self.save_result(record_path, record)
        self.commit('attempt HG-024 implementation without KL-073 result')
        self.check(
            1,
            'ci-emergency-pair-required:HG-024:KL-073',
            '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD',
        )

    def test_ci_future_task_can_modify_transaction_test_without_hg024_candidate(self):
        self.put('tests/db/test_transaction_interfaces.py', '# future task fixture\n')
        tested = self.commit('future task changes transaction test')
        self.result(tested=tested)
        reviewed = self.commit('record future task result')
        self.review(reviewed)
        args = SimpleNamespace(ci_pr_base=self.base, ci_pr_head='HEAD')
        v.configure_ci_merge_gate(self.root, args)
        self.assertEqual(args.task_id, 'KL-001')
        self.assertEqual(args.reviewed_head, reviewed)

    def test_ci_hg024_emergency_pair_is_one_time_at_protected_base(self):
        self.emergency_candidate()
        self.check(
            1,
            'ci-emergency-already-consumed:docs/exec-plans/active/KL-073.md',
            '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD',
        )

    def test_ci_hg024_exact_pair_binds_both_general_reviews_to_one_head(self):
        reviewed = self.emergency_candidate()
        args = SimpleNamespace(ci_pr_base=self.base, ci_pr_head='HEAD')
        with mock.patch.object(v, 'HG024_ONE_TIME_BASE_ABSENT_PATHS', []):
            v.configure_ci_merge_gate(self.root, args)
        self.assertEqual(args.governance_change_id, 'HG-024')
        self.assertEqual(args.emergency_task_id, 'KL-073')
        self.assertEqual(args.governance_reviewed_head, reviewed)

    def test_ci_hg024_exact_pair_rejects_missing_or_stale_task_review(self):
        self.emergency_candidate(include_task_review=False)
        args = SimpleNamespace(ci_pr_base=self.base, ci_pr_head='HEAD')
        with mock.patch.object(v, 'HG024_ONE_TIME_BASE_ABSENT_PATHS', []):
            with self.assertRaisesRegex(ValueError, 'ci-general-review-missing:KL-073'):
                v.configure_ci_merge_gate(self.root, args)

        self.git('reset', '--hard', self.base)
        self.emergency_candidate(task_reviewed_head=self.base)
        args = SimpleNamespace(ci_pr_base=self.base, ci_pr_head='HEAD')
        with mock.patch.object(v, 'HG024_ONE_TIME_BASE_ABSENT_PATHS', []):
            with self.assertRaisesRegex(ValueError, 'ci-emergency-reviewed-head-mismatch:HG-024'):
                v.configure_ci_merge_gate(self.root, args)


    def test_ci_governance_allows_new_follow_up_task_identity(self):
        task = self.add_governance_task()
        tested = self.commit('add explicit follow-up task')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_new_task_must_start_not_started(self):
        task = self.add_governance_task(status='READY')
        tested = self.commit('add already-ready follow-up task')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'governance-new-task-status:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_new_task_cannot_arrive_with_review_artifact(self):
        task = self.add_governance_task(add_review_artifact=True)
        tested = self.commit('add follow-up task with fabricated review')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'governance-new-task-artifact:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_rejects_retroactive_completed_task_refinement(self):
        for relative in (
                'docs/exec-plans/completed/KL-013_RESULT.yaml',
                'docs/exec-plans/evidence/KL-013/checks-f2416f1.log',
                'docs/exec-plans/evidence/KL-013/checks-d9085e7.log',
                'docs/exec-plans/evidence/KL-013/checks-b0c5d4a.log'):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.base = self.commit('record completed KL-013 fixture')

        task_id = 'KL-013'
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        old_dod = task['definition_of_done']
        task['definition_of_done'] = old_dod + '; retroactive obligation'
        dump(backlog_path, backlog)
        packet = self.root / f'docs/exec-plans/active/{task_id}.md'
        packet.write_text(packet.read_text().replace(
            old_dod, task['definition_of_done']))
        trace_path = self.root / v.TRACEABILITY
        traceability = json.loads(trace_path.read_text())
        trace = next(item for item in traceability['tasks'] if item['id'] == task_id)
        for field in v.TRACEABILITY_TASK_FIELDS:
            trace[field] = task.get(field)
        dump(trace_path, traceability)
        refresh(self.root)
        tested = self.commit('impose obligation on completed task')
        self.persist_governance_change(
            'HG-999', tested, [task_id], task['review_requirements'])
        self.check(1, 'governance-refine-completed-task:' + task_id,
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_allows_refined_traceability_metadata(self):
        task_id = 'KL-008'
        task = self.refine_task(task_id)
        refresh(self.root)
        tested = self.commit('refine packet and derived traceability metadata')
        self.persist_governance_change(
            'HG-999', tested, [task_id], task['review_requirements'])
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_allows_explicit_unstarted_task_retirement(self):
        task = self.retire_task()
        refresh(self.root)
        tested = self.commit('retire unneeded Google Sheet migration task')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_requires_updated_active_count(self):
        task = self.retire_task(update_active_count=False)
        refresh(self.root)
        tested = self.commit('retire task with stale active count')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'backlog-active-task-count',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_preserves_requirement_mapping(self):
        task = self.retire_task(preserve_requirement_mapping=False)
        refresh(self.root)
        tested = self.commit('retire task while changing requirement mapping')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'governance-retirement-definition-scope:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_requires_schedule_barrier(self):
        task = self.retire_task(include_schedule_barrier=False)
        refresh(self.root)
        tested = self.commit('retire task without schedule barrier')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'packet-superseded-schedulable:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_rejects_negated_schedule_barrier(self):
        task = self.retire_task(schedule_barrier_text=(
            'Scheduling note: This packet does not claim it MUST NOT be scheduled.'
        ))
        refresh(self.root)
        tested = self.commit('retire task with negated schedule barrier')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'packet-superseded-schedulable:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_requires_durable_reason(self):
        task = self.retire_task(include_reason=False)
        refresh(self.root)
        tested = self.commit('retire task without durable reason')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'governance-retirement-reason:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_rejects_altered_packet_reason(self):
        task = self.retire_task(packet_reason='A different retirement reason.')
        refresh(self.root)
        tested = self.commit('retire task with altered packet reason')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'packet-superseded-reason:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_rejects_extended_packet_reason(self):
        task = self.retire_task(packet_reason=(
            'The user approved this fixture retirement because replacement work exists. '
            'Conflicting extension.'
        ))
        refresh(self.root)
        tested = self.commit('retire task with extended packet reason')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'packet-superseded-reason:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_rejects_duplicate_packet_reason(self):
        task = self.retire_task(duplicate_reason='A contradictory second reason.')
        refresh(self.root)
        tested = self.commit('retire task with duplicate packet reason')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'packet-superseded-reason:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_requires_nonempty_replacement(self):
        task = self.retire_task(replacement_mode='empty', packet_replacement=None)
        refresh(self.root)
        tested = self.commit('retire task without replacement')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'governance-retirement-replacement:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_requires_changed_replacement(self):
        task = self.retire_task(replacement_mode='unchanged')
        refresh(self.root)
        tested = self.commit('retire task with unchanged dependencies')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'governance-retirement-replacement:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_rejects_unknown_replacement(self):
        task = self.retire_task(replacement_mode='unknown', packet_replacement='KL-999')
        refresh(self.root)
        tested = self.commit('retire task with unknown replacement')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'unknown-dep:' + task['id'] + '->KL-999',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_rejects_packet_replacement_mismatch(self):
        task = self.retire_task(packet_replacement='KL-002')
        refresh(self.root)
        tested = self.commit('retire task with mismatched packet replacement')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'packet-superseded-replacements:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_rejects_duplicate_packet_replacement(self):
        task = self.retire_task(packet_replacement=['KL-001', 'KL-001'])
        refresh(self.root)
        tested = self.commit('retire task with duplicate packet replacement')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'packet-superseded-replacements:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_rejects_structured_dependency_mismatch(self):
        task = self.retire_task(
            metadata_replacements=['KL-002'], packet_replacement='KL-002')
        refresh(self.root)
        tested = self.commit('retire task with mismatched structured replacement')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'governance-retirement-replacement:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_retirement_rejects_reordered_old_dependencies(self):
        task_id = 'KL-008'
        backlog = json.loads((self.root / v.BACKLOG).read_text())
        old_task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        self.assertGreater(len(old_task['depends_on']), 1)
        reordered = list(reversed(old_task['depends_on']))
        task = self.retire_task(
            replacement_mode='unchanged',
            metadata_replacements=reordered,
            packet_replacement=reordered,
        )
        backlog_path = self.root / v.BACKLOG
        updated = json.loads(backlog_path.read_text())
        updated_task = next(item for item in updated['tasks'] if item['id'] == task_id)
        updated_task['depends_on'] = reordered
        dump(backlog_path, updated)
        refresh(self.root)
        tested = self.commit('retire task with reordered old dependencies')
        self.persist_governance_change(
            'HG-999', tested, [task['id']], task['review_requirements'])
        self.check(1, 'governance-retirement-replacement:' + task['id'],
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_superseded_task_cannot_have_yaml_or_json_result(self):
        task_id = 'KL-053'
        backlog = json.loads((self.root / v.BACKLOG).read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        evidence = f'docs/exec-plans/evidence/{task_id}/checks.log'
        self.put(evidence, 'fabricated superseded result evidence\n')
        result = {
            'task_identity': task['task_identity'],
            'display_task_id': task_id,
            'base_commit': self.base,
            'tested_commit': self.base,
            'task_status': 'PASS',
            'task_checks_status': 'PASS',
            'integration_status': 'UNMERGED',
            'summary': 'A superseded task must never pass.',
            'files_changed': [],
            'requirements_covered': [],
            'commands_run': [{
                'check_id': check_id,
                'command': 'fabricated-check ' + check_id,
                'result': 'PASS',
                'evidence_ref': evidence,
            } for check_id in task['checks_required_for_this_task']],
        }
        for extension in ('yaml', 'json'):
            path = self.root / f'docs/exec-plans/completed/{task_id}_RESULT.{extension}'
            self.save_result(path, result)
            self.check(1, path.name + ':result-for-superseded-task')
            path.unlink()

    def test_ci_governance_rejects_superseded_task_reactivation(self):
        task_id = 'KL-053'
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        task['status'] = 'NOT_STARTED'
        task['packet_refinement'] = 'ENFORCEABLE'
        task['write_paths_status'] = 'ENFORCEABLE'
        backlog['active_task_count'] += 1
        dump(backlog_path, backlog)
        packet = self.root / f'docs/exec-plans/active/{task_id}.md'
        packet.write_text(packet.read_text() + '\nReactivation fixture.\n')
        traceability_path = self.root / v.TRACEABILITY
        traceability = json.loads(traceability_path.read_text())
        trace = next(item for item in traceability['tasks'] if item['id'] == task_id)
        for field in v.TRACEABILITY_TASK_FIELDS:
            trace[field] = task.get(field)
        dump(traceability_path, traceability)
        refresh(self.root)
        tested = self.commit('attempt superseded task reactivation')
        self.persist_governance_change(
            'HG-999', tested, [task_id], task['review_requirements'])
        self.check(1, 'governance-reactivate-superseded-task:' + task_id,
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_rejects_same_status_superseded_refinement(self):
        task_id = 'KL-053'
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        task['packet_refinement'] = 'ENFORCEABLE'
        task['write_paths_status'] = 'ENFORCEABLE'
        dump(backlog_path, backlog)
        packet = self.root / f'docs/exec-plans/active/{task_id}.md'
        packet.write_text(packet.read_text() + '\nSame-status refinement fixture.\n')
        traceability_path = self.root / v.TRACEABILITY
        traceability = json.loads(traceability_path.read_text())
        trace = next(item for item in traceability['tasks'] if item['id'] == task_id)
        for field in v.TRACEABILITY_TASK_FIELDS:
            trace[field] = task.get(field)
        dump(traceability_path, traceability)
        refresh(self.root)
        tested = self.commit('attempt same-status superseded refinement')
        self.persist_governance_change(
            'HG-999', tested, [task_id], task['review_requirements'])
        self.check(1, 'governance-modify-superseded-task:' + task_id,
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_rejects_packet_only_superseded_refinement(self):
        task_id = 'KL-053'
        backlog = json.loads((self.root / v.BACKLOG).read_text())
        task = next(item for item in backlog['tasks'] if item['id'] == task_id)
        packet = self.root / f'docs/exec-plans/active/{task_id}.md'
        packet.write_text(packet.read_text() + '\nFabricated task PASS and implementation evidence.\n')
        refresh(self.root)
        tested = self.commit('attempt packet-only superseded refinement')
        self.persist_governance_change(
            'HG-999', tested, [task_id], task['review_requirements'])
        self.check(1, 'governance-modify-superseded-task:' + task_id,
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_rejects_wrong_target_backlog_edit(self):
        task_id = 'KL-008'
        task = self.refine_task(task_id)
        backlog_path = self.root / v.BACKLOG
        backlog = json.loads(backlog_path.read_text())
        wrong = next(item for item in backlog['tasks'] if item['id'] == 'KL-001')
        wrong['commands'] = ['wrong-target governance edit']
        dump(backlog_path, backlog)
        refresh(self.root)
        tested = self.commit('misapply refinement to unrelated backlog task')
        self.persist_governance_change(
            'HG-999', tested, [task_id], task['review_requirements'])
        self.check(1, 'governance-task-definition-scope:HG-999:KL-001',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_governance_rejects_wrong_target_traceability_edit(self):
        task_id = 'KL-008'
        task = self.refine_task(task_id)
        traceability_path = self.root / v.TRACEABILITY
        traceability = json.loads(traceability_path.read_text())
        wrong = next(item for item in traceability['tasks'] if item['id'] == 'KL-003')
        wrong['checks_required_for_this_task'] = task['checks_required_for_this_task']
        dump(traceability_path, traceability)
        refresh(self.root)
        tested = self.commit('misapply refinement to unrelated traceability task')
        self.persist_governance_change(
            'HG-999', tested, [task_id], task['review_requirements'])
        self.check(
            1,
            'governance-traceability-scope:HG-999:harness-backlog-v0.2/KL-003',
            '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_duplicate_traceability_identity_and_id_rejected(self):
        traceability_path = self.root / v.TRACEABILITY
        traceability = json.loads(traceability_path.read_text())
        duplicate = copy.deepcopy(traceability['tasks'][2])
        traceability['tasks'].append(duplicate)
        dump(traceability_path, traceability)
        refresh(self.root)
        self.check(1, 'traceability-duplicate-task-identity:' + duplicate['task_identity'])
        self.check(1, 'traceability-duplicate-task-id:' + duplicate['id'])

    def test_invalid_traceability_identity_and_id_rejected(self):
        traceability_path = self.root / v.TRACEABILITY
        original = json.loads(traceability_path.read_text())
        cases = [
            ('missing', None, 'traceability-task-identity:0'),
            ('non-string', 7, 'traceability-task-identity:0'),
            ('mismatched', 'harness-backlog-v0.2/KL-999',
             'traceability-task-identity-mismatch:harness-backlog-v0.2/KL-999'),
            ('bad-id', 'KL-nine',
             'traceability-task-id:harness-backlog-v0.2/KL-001'),
        ]
        for kind, value, diagnostic in cases:
            traceability = copy.deepcopy(original)
            if kind in ('missing', 'non-string'):
                if kind == 'missing':
                    traceability['tasks'][0].pop('task_identity')
                else:
                    traceability['tasks'][0]['task_identity'] = value
            elif kind == 'mismatched':
                traceability['tasks'][0]['task_identity'] = value
            else:
                traceability['tasks'][0]['id'] = value
            dump(traceability_path, traceability)
            refresh(self.root)
            self.check(1, diagnostic)

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

    def test_hg051_all_four_review_types_are_mandatory(self):
        self.put('docs/exec-plans/evidence/HG-051/scope.md', 'fixture scope')
        tested = self.commit('HG051 governance implementation')
        _, reviewed = self.persist_governance_change(
            'HG-051', tested, [], ['GENERAL', 'PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'])
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')
        for review_type in ('PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'):
            path = self.root / f'docs/exec-plans/reviews/HG-051/{review_type}.json'
            original = path.read_bytes()
            path.unlink()
            self.commit('missing ' + review_type)
            self.check(1, 'governance-required-reviews-not-pass:HG-051',
                       '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')
            path.write_bytes(original)
            self.commit('restore ' + review_type)
        self.assertEqual(self.git('rev-parse', reviewed), reviewed)

    def test_hg051_cannot_write_actual_historical_artifacts(self):
        self.put('docs/exec-plans/evidence/HG-051/scope.md', 'fixture scope')
        tested = self.commit('HG051 governance implementation')
        self.persist_governance_change(
            'HG-051', tested, [], ['GENERAL', 'PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'])
        path = 'docs/exec-plans/evidence/KL-080/unauthorized.log'
        self.put(path)
        self.commit('forbidden actual migration')
        self.check(1, 'governance-write-scope:HG-051:' + path,
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_hg060_security_review_is_mandatory(self):
        self.put('docs/exec-plans/evidence/HG-060/scope.md', 'fixture scope')
        tested = self.commit('HG060 governance definitions')
        self.persist_governance_change('HG-060', tested, [], ['GENERAL'])
        self.check(1, 'governance-required-reviews-not-pass:HG-060',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_hg059_security_review_is_mandatory(self):
        self.put('docs/exec-plans/evidence/HG-059/scope.md', 'fixture scope')
        tested = self.commit('HG059 governance implementation')
        self.persist_governance_change('HG-059', tested, [], ['GENERAL'])
        self.check(1, 'governance-required-reviews-not-pass:HG-059',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_hg058_security_review_is_mandatory(self):
        self.put('docs/exec-plans/evidence/HG-058/scope.md', 'fixture scope')
        tested = self.commit('HG058 governance implementation')
        self.persist_governance_change(
            'HG-058', tested, [], ['GENERAL', 'SECURITY_DATA_BOUNDARY'])
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')
        (self.root / 'docs/exec-plans/reviews/HG-058/SECURITY_DATA_BOUNDARY.json').unlink()
        self.commit('missing HG058 security review')
        self.check(1, 'governance-required-reviews-not-pass:HG-058',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_hg054_all_four_review_types_are_mandatory(self):
        self.put('docs/exec-plans/evidence/HG-054/scope.md', 'fixture scope')
        tested = self.commit('HG054 governance implementation')
        _, reviewed = self.persist_governance_change(
            'HG-054', tested, [], ['GENERAL', 'PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'])
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')
        for review_type in ('PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'):
            path = self.root / f'docs/exec-plans/reviews/HG-054/{review_type}.json'
            original = path.read_bytes()
            path.unlink()
            self.commit('missing ' + review_type)
            self.check(1, 'governance-required-reviews-not-pass:HG-054',
                       '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')
            path.write_bytes(original)
            self.commit('restore ' + review_type)
        self.assertEqual(self.git('rev-parse', reviewed), reviewed)

    def test_hg054_cannot_write_actual_historical_artifacts(self):
        self.put('docs/exec-plans/evidence/HG-054/scope.md', 'fixture scope')
        tested = self.commit('HG054 governance implementation')
        self.persist_governance_change(
            'HG-054', tested, [], ['GENERAL', 'PROTOCOL', 'DB_CONCURRENCY', 'SECURITY_DATA_BOUNDARY'])
        path = 'docs/exec-plans/evidence/KL-036/unauthorized.log'
        self.put(path)
        self.commit('forbidden actual migration')
        self.check(1, 'governance-write-scope:HG-054:' + path,
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

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

    def test_ci_governance_allows_current_project_plan_refinement(self):
        plan = self.root / v.PROJECT_PLAN
        plan.write_text(plan.read_text() + '\nGovernance fixture refinement.\n')
        self.governance_change()
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

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

    def test_integration_rejects_invalid_historical_review_schema(self):
        self.result(tested=self.base)
        result_commit = self.commit('persist result')
        dump(self.root / 'docs/exec-plans/reviews/KL-001/GENERAL.json', {
            'task_identity': self.task['task_identity'],
            'reviewed_head_sha': result_commit,
            'review_type': 'GENERAL',
            'status': 'PASS',
            'findings': [],
        })
        review_commit = self.commit('persist schema-invalid review')
        self.integration_record(result_commit, result_commit, review_commit, review_commit)
        self.check(1, 'integration-review-schema:KL-001:GENERAL:')

    def test_integration_rejects_historical_review_task_identity_mismatch(self):
        self.result(tested=self.base)
        result_commit = self.commit('persist result')
        review_commit = self.review(result_commit)
        review_path = self.root / 'docs/exec-plans/reviews/KL-001/GENERAL.json'
        review = json.loads(review_path.read_text())
        review['task_identity'] = 'harness-backlog-v0.2/KL-002'
        dump(review_path, review)
        review_commit = self.commit('persist mismatched review identity')
        self.integration_record(result_commit, result_commit, review_commit, review_commit)
        self.check(1, 'integration-review-identity:KL-001:GENERAL')

    def test_integration_rejects_missing_historical_review_evidence(self):
        self.result(tested=self.base)
        result_commit = self.commit('persist result')
        review_commit = self.review(result_commit)
        review_path = self.root / 'docs/exec-plans/reviews/KL-001/GENERAL.json'
        review = json.loads(review_path.read_text())
        review['evidence_refs'] = ['docs/exec-plans/evidence/KL-001/missing.log']
        dump(review_path, review)
        review_commit = self.commit('persist review with missing evidence')
        self.integration_record(result_commit, result_commit, review_commit, review_commit)
        self.check(1, 'integration-review-evidence:KL-001:GENERAL:')

    def test_integration_rejects_implementation_after_historical_tested_commit(self):
        self.put('src/kineticloop/post_test_change.py')
        self.commit('change implementation after claimed tested revision')
        self.result(tested=self.base)
        reviewed = self.commit('persist result after stale implementation change')
        review_commit = self.review(reviewed)
        self.integration_record(reviewed, reviewed, review_commit, review_commit)
        self.check(1, 'integration-tested-stale-change:src/kineticloop/post_test_change.py')

    def test_integration_allows_unrelated_task_bookkeeping_after_tested_commit(self):
        self.put('docs/exec-plans/evidence/KL-002/unrelated.log')
        self.commit('persist unrelated task bookkeeping')
        self.result(tested=self.base)
        reviewed = self.commit('persist result after unrelated bookkeeping')
        review_commit = self.review(reviewed)
        self.integration_record(reviewed, reviewed, review_commit, review_commit)
        self.check()

    def test_integration_rejects_implementation_after_historical_reviewed_head(self):
        self.result(tested=self.base)
        reviewed = self.commit('persist reviewed result')
        self.put('src/kineticloop/post_review_change.py')
        self.commit('change implementation after reviewed head')
        review_commit = self.review(reviewed)
        self.integration_record(reviewed, reviewed, review_commit, review_commit)
        self.check(1, 'integration-review-stale-change:src/kineticloop/post_review_change.py')

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

    def test_delayed_review_rejects_task_change_after_merge(self):
        self.result(tested=self.base)
        merge_commit = self.commit('merge result before delayed review')
        self.put('src/kineticloop/delayed_review_change.py')
        self.commit('change reviewed task after merge')
        review_commit = self.review(merge_commit)
        self.integration_record(merge_commit, merge_commit, review_commit, merge_commit)
        self.check(
            1,
            'integration-delayed-review-stale-change:'
            'src/kineticloop/delayed_review_change.py',
        )

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

    def test_ci_prospective_evidence_budget_includes_review_suffix(self):
        self.result()
        reviewed = self.commit('fixture result and evidence')
        self.review(reviewed)
        self.check(0, '', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')
        self.put('docs/exec-plans/reviews/KL-001/huge.log',
                 'x' * (v.compact_evidence.PLAIN_LIMIT + 1))
        self.commit('oversized review-created artifact')
        self.check(1, 'evidence-budget:', '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

    def test_ci_review_cannot_repair_preexisting_manifest_in_suffix(self):
        self.result()
        ref = 'docs/exec-plans/reviews/KL-001/raw/preexisting.json'
        record = v.compact_evidence.capture(
            self.root, ref, b'1 passed in 0.1s\n', self.base, 'fixture review', 0)
        self.put(ref, json.dumps(dict(record, raw_sha256='0' * 64)))
        reviewed = self.commit('result and invalid ordinary review envelope')
        self.review(reviewed)
        # A valid later envelope cannot repair an ordinary reference at reviewed.
        self.put(ref, json.dumps(record))
        review_path = self.root / 'docs/exec-plans/reviews/KL-001/GENERAL.json'
        review = json.loads(review_path.read_text())
        review['evidence_refs'] = [ref]
        dump(review_path, review)
        self.commit('repair same-path envelope in allowed review suffix')
        self.check(1, 'review-evidence-revision:',
                   '--ci-pr-base', self.base, '--ci-pr-head', 'HEAD')

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


class CleanRecoveryTests(unittest.TestCase):
    def setUp(self):
        tasks = json.loads((ROOT / v.BACKLOG).read_text())['tasks']
        self.after = {task['id']: copy.deepcopy(task) for task in tasks}
        self.before = copy.deepcopy(self.after)
        successor = self.before.pop('KL-081')
        source = json.loads(json.dumps(successor).replace('KL-081', 'KL-036'))
        source['entry_conditions'] = source['entry_conditions'][:-4]
        self.before['KL-036'] = source
        for task_id in v.HG057_REDIRECT_IDS:
            task = self.before[task_id]
            task['depends_on'] = [
                'KL-036' if dependency == 'KL-081' else dependency
                for dependency in task['depends_on']]

    def test_clean_recovery_preserves_complete_functional_projection(self):
        self.assertEqual(v.clean_recovery_projection_errors(self.before, self.after), [])

    def test_clean_recovery_rejects_changed_frozen_paths_oracles_reviews_and_requirements(self):
        for field in ('write_paths', 'check_contracts', 'checks_required_for_this_task',
                      'review_requirements', 'requirements_covered', 'invariant_ids',
                      'transaction_boundaries', 'depends_on', 'table_ids', 'resource_keys'):
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.after)
                mutated['KL-081'][field] = []
                if mutated['KL-081'][field] == self.after['KL-081'][field]:
                    mutated['KL-081'][field] = ['invented-requirement']
                self.assertIn('clean-recovery-functional-projection:KL-081',
                              v.clean_recovery_projection_errors(self.before, mutated))

    def test_clean_recovery_rejects_weakened_installed_readiness(self):
        mutated = copy.deepcopy(self.after)
        mutated['KL-081']['entry_conditions'][-3] = 'HG-058 governance PASS is sufficient'
        self.assertIn('clean-recovery-readiness:KL-081',
                      v.clean_recovery_projection_errors(self.before, mutated))

    def test_clean_recovery_rejects_non_dependency_changes_and_partial_redirect(self):
        for task_id in sorted(v.HG057_REDIRECT_IDS):
            with self.subTest(task_id=task_id):
                mutated = copy.deepcopy(self.after)
                mutated[task_id]['depends_on'] = self.before[task_id]['depends_on']
                self.assertIn('clean-recovery-dependency-projection:' + task_id,
                              v.clean_recovery_projection_errors(self.before, mutated))
                mutated[task_id]['depends_on'] = self.after[task_id]['depends_on']
                mutated[task_id]['definition_of_done'] += '; new concern'
                self.assertIn('clean-recovery-dependency-projection:' + task_id,
                              v.clean_recovery_projection_errors(self.before, mutated))

    def test_clean_recovery_rejects_extra_task_and_pass_disposition(self):
        mutated = copy.deepcopy(self.after)
        mutated['KL-036']['status'] = 'PASS'
        mutated['KL-039']['requirements_covered'] = ['W01@PU']
        mutated['KL-082'] = copy.deepcopy(mutated['KL-081'])
        errors = v.clean_recovery_projection_errors(self.before, mutated)
        self.assertIn('clean-recovery-task-set', errors)
        self.assertIn('clean-recovery-disposition:KL-036', errors)

    def test_hg057_scope_rejects_successor_implementation_and_original_artifacts(self):
        patterns = v.governance_allowed_patterns('HG-057')
        for path in ('tools/harness/compact_evidence.py', 'src/kineticloop/workflow/worker_reaper.py',
                     'docs/harness/THREAD_REVIEW_CONTRACT.md', '.github/workflows/ci.yml',
                     'docs/exec-plans/evidence/KL-036/probe.py',
                     'docs/exec-plans/evidence/HG-056/probe.py',
                     'docs/exec-plans/completed/KL-081_RESULT.yaml'):
            with self.subTest(path=path):
                self.assertFalse(v.matches(path, patterns))
        self.assertTrue(v.matches('docs/exec-plans/active/HG-058.md', patterns))

    def test_hg058_scope_is_literal_and_rejects_schema_or_installer_expansion(self):
        patterns = v.governance_allowed_patterns('HG-058')
        for path in ('THREAD_REVIEW.schema.json', 'tools/harness/local_gate.py',
                     'docs/exec-plans/active/KL-081.md', 'tests/db/test_worker_reaper.py',
                     'docs/exec-plans/evidence/HG-056/check.log'):
            with self.subTest(path=path):
                self.assertFalse(v.matches(path, patterns))
        self.assertTrue(v.matches('docs/harness/THREAD_REVIEW_CONTRACT.md', patterns))

    def test_kl081_packet_projects_entry_conditions_oracles_and_frozen_boundaries(self):
        task = self.after['KL-081']
        text = (ROOT / 'docs/exec-plans/active/KL-081.md').read_text()
        self.assertEqual(v.packet_errors(task, text), [])
        changed = text.replace(task['entry_conditions'][-3], 'HG058 PASS alone')
        self.assertIn('packet-entry-condition:KL-081', v.packet_errors(task, changed))

    def test_kl081_packet_rejects_old_or_malformed_owned_namespaces(self):
        task = self.after['KL-081']
        text = (ROOT / 'docs/exec-plans/active/KL-081.md').read_text()
        for old, new in (('kineticloop_kl081_', 'kineticloop_kl036_'),
                         ('kineticloop-kl081-', 'kineticloop-kl036-'),
                         ('<ROOT12>', '<ROOT7>')):
            with self.subTest(namespace=new):
                changed = text.replace(old, new)
                self.assertIn('packet-recovery-namespace:KL-081',
                              v.packet_errors(task, changed))


class SourceLineageDefinitionTests(unittest.TestCase):
    def test_hg059_literal_scope_and_hg058_read_only_authority(self):
        patterns = v.governance_allowed_patterns('HG-059')
        for path in ('REVIEW_SOURCE_DECLARATIONS.schema.json',
                     'docs/harness/REVIEW_SOURCE_DECLARATIONS.json',
                     'docs/exec-plans/active/HG-058.md',
                     'docs/exec-plans/evidence/HG-059/check.json',
                     'docs/exec-plans/reviews/HG-059/GENERAL.json'):
            with self.subTest(path=path):
                self.assertTrue(v.matches(path, patterns))
        for path in ('tools/harness/compact_evidence.py', 'tools/harness/local_gate.py',
                     'THREAD_REVIEW.schema.json', 'FROZEN_BASELINE.json',
                     'CURRENT_REQUIREMENT_SET.json', 'docs/exec-plans/active/KL-081.md',
                     'docs/exec-plans/evidence/HG-058/check.json',
                     'docs/exec-plans/evidence/HG-059A/check.json',
                     'docs/exec-plans/reviews/HG-047/GENERAL.json'):
            with self.subTest(path=path):
                self.assertFalse(v.matches(path, patterns))
        for path in ('REVIEW_SOURCE_DECLARATIONS.schema.json',
                     'docs/harness/REVIEW_SOURCE_DECLARATIONS.json'):
            self.assertFalse(v.matches(path, v.governance_allowed_patterns('HG-058')))

    def test_hg059_exact_checks_authorities_and_no_product_definition_projection(self):
        record: dict[str, list] = {
            'checks_run': [{'check_id': name} for name in v.HG059_REQUIRED_CHECKS],
                  'authority_entries_added': ['REVIEW_SOURCE_DECLARATIONS.schema.json',
                                             'docs/harness/REVIEW_SOURCE_DECLARATIONS.json'],
                  'packets_refined': []}
        self.assertEqual(v.source_lineage_projection_errors(record, set()), [])
        for change in ('missing', 'duplicate', 'foreign'):
            mutated = copy.deepcopy(record)
            if change == 'missing':
                mutated['checks_run'].pop()
            elif change == 'duplicate':
                mutated['checks_run'].append(mutated['checks_run'][0])
            else:
                mutated['checks_run'][0] = {'check_id': 'invented-check'}
            self.assertIn('source-lineage-required-checks',
                          v.source_lineage_projection_errors(mutated, set()))
        for additions in ([], ['THREAD_REVIEW.schema.json']):
            mutated = dict(record, authority_entries_added=additions)
            self.assertIn('source-lineage-authority-projection',
                          v.source_lineage_projection_errors(mutated, set()))
        self.assertIn('source-lineage-task-projection',
                      v.source_lineage_projection_errors(record, {'KL-081'}))
        self.assertIn('source-lineage-task-projection', v.source_lineage_projection_errors(
            dict(record, packets_refined=['KL-081']), set()))


class BoundedRecoveryDefinitionTests(unittest.TestCase):
    def test_hg060_exact_literal_scope(self):
        allowed = {
            'docs/harness/REVIEW_SOURCE_DECLARATIONS.json',
            'docs/harness/THREAD_REVIEW_CONTRACT.md', 'docs/harness/EVIDENCE_STORAGE_POLICY.md',
            'docs/harness/HARNESS_GOVERNANCE_CONTRACT.md', 'docs/exec-plans/active/HG-058.md',
            'tools/harness/validate_harness.py', 'tests/harness/test_validator.py',
            'CURRENT_DOCUMENT_INDEX.json', 'HARNESS_DOCUMENT_MANIFEST.json',
            'docs/exec-plans/governance/HG-060.yaml',
            'docs/exec-plans/evidence/HG-060/**', 'docs/exec-plans/reviews/HG-060/**'}
        self.assertEqual(set(v.governance_allowed_patterns('HG-060')), allowed)
        for path in ('REVIEW_SOURCE_DECLARATIONS.schema.json', 'HARNESS_CHANGE.schema.json',
                     'tools/harness/compact_evidence.py', 'tools/harness/local_gate.py',
                     'tools/harness/local_ci_controller.py', '.github/workflows/ci.yml',
                     'tests/harness/test_planning_fixture_scope.py', 'CURRENT_REQUIREMENT_SET.json',
                     'FROZEN_BASELINE.json', 'docs/exec-plans/governance/HG-058.yaml',
                     'docs/exec-plans/evidence/HG-058/probe.json',
                     'docs/exec-plans/reviews/HG-058/preserved-metadata/REVIEW_APPEND_INDEX.json',
                     'docs/exec-plans/evidence/HG-060A/probe.json',
                     'docs/exec-plans/active/KL-081.md'):
            with self.subTest(path=path):
                self.assertFalse(v.matches(path, list(allowed)))

    def test_hg060_exact_checks_and_unchanged_authority_product_projection(self):
        record: dict[str, list] = {
            'checks_run': [{'check_id': name} for name in v.HG060_REQUIRED_CHECKS],
            'authority_entries_added': [], 'packets_refined': []}
        self.assertEqual(v.bounded_recovery_projection_errors(record, set()), [])
        for variant in ('missing', 'duplicate', 'foreign'):
            bad = copy.deepcopy(record)
            if variant == 'missing':
                bad['checks_run'].pop()
            elif variant == 'duplicate':
                bad['checks_run'].append(bad['checks_run'][0])
            else:
                bad['checks_run'][0] = {'check_id': 'invented'}
            self.assertIn('bounded-recovery-required-checks',
                          v.bounded_recovery_projection_errors(bad, set()))
        self.assertIn('bounded-recovery-authority-projection',
                      v.bounded_recovery_projection_errors(
                          dict(record, authority_entries_added=['HARNESS_CHANGE.schema.json']), set()))
        self.assertIn('bounded-recovery-task-projection',
                      v.bounded_recovery_projection_errors(record, {'KL-081'}))
        self.assertIn('bounded-recovery-task-projection',
                      v.bounded_recovery_projection_errors(
                          dict(record, packets_refined=['KL-081']), set()))
