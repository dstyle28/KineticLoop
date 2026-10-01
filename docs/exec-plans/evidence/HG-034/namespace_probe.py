"""Candidate-only selector safety proof without contacting PostgreSQL."""
import importlib.util
import os
import re
from pathlib import Path


def prove(root: Path) -> None:
    spec = importlib.util.spec_from_file_location('candidate_planning', root / 'tests/db/test_planning.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    variable = 'KINETICLOOP_KL024_FIXTURE_OWNER'
    inherited = os.environ.get(variable)
    actual_root = module.ROOT
    real = module.DatabaseLifecycle
    bootstrap = module._MIGRATIONS.bootstrap_two_phase
    check_output = module.subprocess.check_output
    calls = []

    class ProbeStop(Exception):
        pass

    class Lifecycle(real):
        def __init__(self, path):
            super().__init__(path, runner=lambda *a, **k: calls.append(('runner', a)))

        def destroy(self):
            calls.append(('destroy', self.namespace))

    def stop(lifecycle):
        calls.append(('bootstrap', lifecycle.namespace))
        raise ProbeStop

    module.DatabaseLifecycle = Lifecycle
    module._MIGRATIONS.bootstrap_two_phase = stop
    module.subprocess.check_output = lambda *a, **k: 'abcdef0\n'
    try:
        os.environ.pop(variable, None)
        for sha in ['abcdef0', '0123456789ab']:
            namespace = module._planning_namespace(sha)
            assert namespace.project_name == 'kineticloop-kl024-' + sha
            assert namespace.database_name == 'kineticloop_kl024_' + sha
        try:
            next(module.database_urls.__wrapped__())
        except ProbeStop:
            pass
        assert [c[0] for c in calls] == ['bootstrap', 'destroy']
        assert calls[0][1] == calls[1][1]
        calls.clear()
        for selector in ['', 'KL-024', 'KL-055', 'PRODUCTION', 'KL-025 ', ' KL-025',
                         'kineticloop-kl025-any', 'kl-025']:
            os.environ[variable] = selector
            try:
                next(module.database_urls.__wrapped__())
            except ValueError:
                pass
            else:
                raise AssertionError('unsafe selector accepted')
            assert calls == [], calls
        os.environ[variable] = 'KL-025'
        for sha in ['', 'abcdef', '0123456789abc', 'ABCDEF0', 'abcdefg', 'abc def0',
                    '../foo0', 'abcdef\n']:
            module.subprocess.check_output = lambda *a, value=sha, **k: value
            try:
                next(module.database_urls.__wrapped__())
            except ValueError:
                pass
            else:
                raise AssertionError('unsafe commit suffix accepted')
            assert calls == [], calls
        module.subprocess.check_output = lambda *a, **k: 'abcdef0\n'
        first = module._planning_namespace('abcdef0')
        digest = module.DatabaseNamespace.for_worktree(actual_root).project_name[-12:]
        assert first.project_name == 'kineticloop-kl025-plan-abcdef0-' + digest
        assert first.database_name == 'kineticloop_kl025_plan_abcdef0_' + digest
        assert re.fullmatch(r'[a-z][a-z0-9_]{0,62}', first.database_name)
        assert re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', first.project_name)
        module.ROOT = actual_root.parent / 'different-worktree'
        second = module._planning_namespace('abcdef0')
        assert first.project_name != second.project_name
        assert first.database_name != second.database_name
        module.ROOT = actual_root
        try:
            next(module.database_urls.__wrapped__())
        except ProbeStop:
            pass
        assert [c[0] for c in calls] == ['bootstrap', 'destroy']
        assert calls[0][1] == calls[1][1] == first
        print('PASS defaults, 8 selector denials, 8 SHA denials before runner/bootstrap/teardown')
        print('PASS exact KL025 names, SQL/Compose bounds, distinct physical worktrees, selected cleanup')
    finally:
        module.ROOT = actual_root
        module.DatabaseLifecycle = real
        module._MIGRATIONS.bootstrap_two_phase = bootstrap
        module.subprocess.check_output = check_output
        if inherited is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = inherited
