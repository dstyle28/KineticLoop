"""HG-055: retain each regression owner and reject missing coverage."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parents[2]
PR_ONLY_OMISSION = "github.event_name != 'pull_request'"


def workflow(name: str) -> dict[str, Any]:
    return yaml.load((ROOT / '.github/workflows' / name).read_text(), Loader=yaml.BaseLoader)


def controller_plan() -> list[tuple[str, list[str]]]:
    spec = importlib.util.spec_from_file_location('hg055_local_gate',
                                                ROOT / 'tools/harness/local_gate.py')
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return gate.gate_plan('a' * 40, 'b' * 40, True, False)


def assert_coverage(ci: dict[str, Any], plan: list[tuple[str, list[str]]],
                    db: dict[str, Any], readiness: dict[str, Any]) -> None:
    assert set(ci['on']) == {'push', 'pull_request', 'workflow_dispatch'}
    assert ci['on']['push']['branches'] == ['master']
    assert ci['permissions'] == {'contents': 'read'}
    assert ci['concurrency']['cancel-in-progress'] == 'true'
    assert set(ci['jobs']) == {'quality', 'merge-gate'}
    quality = ci['jobs']['quality']
    assert 'if' not in quality
    steps = {step['run']: step for step in quality['steps'] if 'run' in step}
    for command in ('uv sync --locked', 'uv run kl lint', 'uv run kl typecheck',
                    'uv run kl check-harness'):
        assert command in steps and 'if' not in steps[command]
    for suite in ('unit', 'harness'):
        assert steps['uv run kl test-' + suite]['if'] == PR_ONLY_OMISSION

    merge = ci['jobs']['merge-gate']
    assert merge['if'] == "github.event_name == 'pull_request'"
    checkout = next(step for step in merge['steps']
                    if step.get('uses', '').startswith('actions/checkout@'))
    assert checkout['with']['ref'] == '${{ github.event.pull_request.head.sha }}'
    merge_command = next(step['run'] for step in merge['steps']
                         if 'uv run kl check-harness' in step.get('run', ''))
    assert '--ci-pr-base "${{ github.event.pull_request.base.sha }}"' in merge_command
    assert '--ci-pr-head "${{ github.event.pull_request.head.sha }}"' in merge_command

    commands = dict(plan)
    for suite in ('unit', 'harness'):
        argv = commands[suite]
        assert '/gate/tools/harness/gate_pytest.py' in argv and '-I' in argv
        assert [arg for arg in argv if arg.startswith('tests/')] == ['tests/' + suite]
        assert 'xfail_strict=true' in argv
        assert '--junitxml=/evidence/' + suite + '.xml' in argv
        assert not any(arg in ('-k', '-m', '--collect-only')
                       or arg.startswith(('--ignore', '--deselect')) for arg in argv)
    assert commands['merge_gate'][-4:] == ['--ci-pr-base', 'a' * 40,
                                         '--ci-pr-head', 'b' * 40]
    assert {'collection', 'full_database', 'destroy', 'peer_remove'} <= commands.keys()
    assert set(db['on']) == {'workflow_dispatch'}
    assert db['on']['workflow_dispatch']['inputs']['revision']['required'] == 'true'
    assert set(readiness['on']) == {'pull_request'}
    assert '.github/workflows/kl074-readiness.yml' in readiness['on']['pull_request']['paths']
    readiness_job = readiness['jobs']['kl074-readiness']
    assert 'github.event.pull_request.head.repo.full_name == github.repository' in readiness_job['if']
    assert "startsWith(github.head_ref, 'codex/kl074-')" in readiness_job['if']
    assert readiness_job['env']['KINETICLOOP_KL074_TESTED_COMMIT'] == (
        '${{ github.event.pull_request.head.sha }}')


def inputs() -> tuple[dict[str, Any], list[tuple[str, list[str]]],
                      dict[str, Any], dict[str, Any]]:
    return (workflow('ci.yml'), controller_plan(), workflow('db.yml'),
            workflow('kl074-readiness.yml'))


def test_pr_omits_only_duplicate_regressions_and_retains_other_execution_owners() -> None:
    assert_coverage(*inputs())


@pytest.mark.parametrize('mutation', ['unconditional_pr_suite', 'no_manual_suite',
                                     'conditional_static', 'missing_merge_gate',
                                     'missing_controller_suite', 'partial_controller_suite',
                                     'missing_full_db', 'automatic_db', 'unguarded_readiness'])
def test_missing_or_partial_execution_owner_is_rejected(mutation: str) -> None:
    ci, plan, db, readiness = copy.deepcopy(inputs())
    steps = {step['run']: step for step in ci['jobs']['quality']['steps'] if 'run' in step}
    if mutation == 'unconditional_pr_suite':
        del steps['uv run kl test-unit']['if']
    elif mutation == 'no_manual_suite':
        steps['uv run kl test-harness']['if'] = "github.event_name == 'push'"
    elif mutation == 'conditional_static':
        steps['uv run kl lint']['if'] = PR_ONLY_OMISSION
    elif mutation == 'missing_merge_gate':
        del ci['jobs']['merge-gate']
    elif mutation == 'missing_controller_suite':
        plan = [(label, argv) for label, argv in plan if label != 'unit']
    elif mutation == 'partial_controller_suite':
        dict(plan)['harness'].append('-k')
        dict(plan)['harness'].append('only_one')
    elif mutation == 'missing_full_db':
        plan = [(label, argv) for label, argv in plan if label != 'full_database']
    elif mutation == 'automatic_db':
        db['on']['pull_request'] = {}
    else:
        del readiness['jobs']['kl074-readiness']['if']
    with pytest.raises((AssertionError, KeyError)):
        assert_coverage(ci, plan, db, readiness)
