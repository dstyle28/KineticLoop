"""Candidate-only namespace/unchanged-fixture launch proof, without PostgreSQL."""
import hashlib
import importlib.util
import os
import re
from pathlib import Path


def derived(root, short, label):
    if re.fullmatch(r'[0-9a-f]{7,12}', short) is None:
        raise ValueError('invalid commit suffix')
    digest = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    from kineticloop.db.lifecycle import DatabaseNamespace
    return DatabaseNamespace(f'kineticloop-kl019-{label}-{short}-{digest}',
                             f'kineticloop_kl019_{label}_{short}_{digest}')


def validate_tx_launch(root, short, environment):
    namespace = derived(root, short, 'tx')
    if (environment.get('KINETICLOOP_KL022_COMPOSE_PROJECT') != namespace.project_name
            or environment.get('KINETICLOOP_KL022_DATABASE') != namespace.database_name):
        raise ValueError('transaction launch target mismatch')
    return namespace


def load(root, path):
    spec = importlib.util.spec_from_file_location('probe_' + Path(path).stem, root / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prove(root):
    import pytest
    for path, variable, helper, label in [
        ('tests/db/test_planning.py', 'KINETICLOOP_KL024_FIXTURE_OWNER', '_planning_namespace', 'plan'),
        ('tests/db/test_call_ledger.py', 'KINETICLOOP_KL025_FIXTURE_OWNER', '_ledger_namespace', 'ledger'),
        ('tests/db/test_transaction_interfaces.py', None, None, 'tx')]:
        module = load(root, path)
        calls = []
        real = module.DatabaseLifecycle

        class ProbeStop(Exception):
            pass

        class Lifecycle(real):
            def __init__(self, path):
                super().__init__(path, runner=lambda *a, **k: calls.append(('runner', a)))

            def destroy(self):
                calls.append(('destroy', self.namespace))

        def stop(lifecycle):
            calls.append(('bootstrap/reset', lifecycle.namespace))
            raise ProbeStop

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(module, 'DatabaseLifecycle', Lifecycle)
            patch.setattr(module._MIGRATIONS, 'bootstrap_two_phase', stop)
            if helper:
                patch.setattr(module.subprocess, 'check_output', lambda *a, **k: 'abcdef1\n')
                patch.delenv(variable, raising=False)
                old = getattr(module, helper)('abcdef1')
                expected_project = ('kineticloop-kl024-abcdef1' if label == 'plan'
                                    else 'kineticloop-kl025-abcdef1')
                assert old.project_name == expected_project
                if label == 'plan':
                    patch.setenv(variable, 'KL-025')
                    old = module._planning_namespace('abcdef1')
                    assert old.project_name.startswith('kineticloop-kl025-plan-abcdef1-')
                patch.setenv(variable, 'KL-019')
                expected = derived(module.ROOT, 'abcdef1', label)
                assert getattr(module, helper)('abcdef1') == expected
                with patch.context() as different:
                    different.setattr(module, 'ROOT', root.parent / 'different-worktree')
                    assert getattr(module, helper)('abcdef1') != expected
                for invalid in ['', 'KL-024', 'KL-055', 'PRODUCTION', 'kl-019', 'KL-019 ', '../KL-019']:
                    patch.setenv(variable, invalid)
                    try:
                        next(module.database_urls.__wrapped__())
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('invalid selector accepted')
                    assert calls == []
                patch.setenv(variable, 'KL-019')
                for short in ['', 'abcdef', 'abcdef1234567', 'ABCDEF1', 'abcdex1', '../foo1']:
                    patch.setattr(module.subprocess, 'check_output', lambda *a, value=short, **k: value)
                    try:
                        next(module.database_urls.__wrapped__())
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('invalid SHA accepted')
                    assert calls == []
                patch.setattr(module.subprocess, 'check_output', lambda *a, **k: 'abcdef1\n')
            else:
                expected = derived(module.ROOT, 'abcdef1', 'tx')
                environment = dict(os.environ)
                environment.update(KINETICLOOP_KL022_COMPOSE_PROJECT=expected.project_name,
                                   KINETICLOOP_KL022_DATABASE=expected.database_name)
                assert validate_tx_launch(module.ROOT, 'abcdef1', environment) == expected
                assert derived(root.parent / 'different-worktree', 'abcdef1', 'tx') != expected
                for key in ['KINETICLOOP_KL022_COMPOSE_PROJECT', 'KINETICLOOP_KL022_DATABASE']:
                    for value in ['', 'arbitrary', 'kineticloop-kl022-08e743c', expected.project_name + 'x']:
                        wrong = {**environment, key: value}
                        try:
                            validate_tx_launch(module.ROOT, 'abcdef1', wrong)
                        except ValueError:
                            pass
                        else:
                            raise AssertionError('invalid launch target accepted')
                        assert calls == []
                for short in ['', 'abcdef', 'abcdef1234567', 'ABCDEF1', 'abcdex1']:
                    try:
                        validate_tx_launch(module.ROOT, short, environment)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('invalid launch SHA accepted')
                    assert calls == []
                for key, value in environment.items():
                    if key.startswith('KINETICLOOP_KL022_'):
                        patch.setenv(key, value)
            try:
                next(module.database_urls.__wrapped__())
            except ProbeStop:
                pass
            assert calls == [('bootstrap/reset', expected), ('destroy', expected)], calls
            print('PASS actual fixture consumes owned namespace/cleanup', path, expected)
    print('PASS exact selector/SHA/launch denial before runner/bootstrap/reset/cleanup; no PG contacted')
