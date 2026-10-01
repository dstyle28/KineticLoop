"""Fail closed if candidate regressions reset/destroy any other namespace."""
from collections import Counter
from pathlib import Path
import os
import subprocess

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace

ROOT = Path.cwd()
SHORT = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
DIGEST = DatabaseNamespace.for_worktree(ROOT).project_name[-12:]
PLAN = DatabaseNamespace('kineticloop-kl025-plan-' + SHORT + '-' + DIGEST,
                         'kineticloop_kl025_plan_' + SHORT + '_' + DIGEST)
REG = DatabaseNamespace('kineticloop-kl025-reg-' + SHORT, 'kineticloop_kl025_reg_' + SHORT)
ALLOWED = {PLAN, REG}
RESETS = []
DESTROYS = []
RESET = DatabaseLifecycle.reset
DESTROY = DatabaseLifecycle.destroy


def reset(lifecycle):
    assert lifecycle.namespace in ALLOWED, 'unexpected regression reset namespace'
    assert lifecycle.environment['COMPOSE_PROJECT_NAME'] == lifecycle.namespace.project_name
    assert lifecycle.environment['KINETICLOOP_DB_NAME'] == lifecycle.namespace.database_name
    assert lifecycle.compose_command('ps')[3] == lifecycle.namespace.project_name
    RESETS.append(lifecycle.namespace)
    print('OWNED_RESET project=' + lifecycle.namespace.project_name +
          ' database=' + lifecycle.namespace.database_name, flush=True)
    return RESET(lifecycle)


def destroy(lifecycle):
    assert lifecycle.namespace in ALLOWED, 'unexpected regression teardown namespace'
    DESTROYS.append(lifecycle.namespace)
    print('OWNED_DESTROY project=' + lifecycle.namespace.project_name +
          ' database=' + lifecycle.namespace.database_name, flush=True)
    return DESTROY(lifecycle)


def pytest_configure(config):
    assert os.environ['KINETICLOOP_KL024_FIXTURE_OWNER'] == 'KL-025'
    assert os.environ['KINETICLOOP_KL022_COMPOSE_PROJECT'] == REG.project_name
    assert os.environ['KINETICLOOP_KL022_DATABASE'] == REG.database_name
    DatabaseLifecycle.reset = reset
    DatabaseLifecycle.destroy = destroy


def pytest_sessionfinish(session, exitstatus):
    DatabaseLifecycle.reset = RESET
    DatabaseLifecycle.destroy = DESTROY
    assert set(RESETS) == ALLOWED
    assert Counter(RESETS) == Counter(DESTROYS)
    print('PASS all called regression resets and cleanup confined to the two owned namespaces', flush=True)
