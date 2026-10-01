"""Observe and reject candidate lifecycle targets before real operations."""
import os
import subprocess
from collections import Counter
from pathlib import Path

from kineticloop.db.lifecycle import DatabaseLifecycle
from namespace_probe import derived, validate_tx_launch

ROOT = Path.cwd()
SHORT = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
ALLOWED = {derived(ROOT, SHORT, label) for label in ['tx', 'plan', 'ledger']}
RESETS = []
DESTROYS = []
RESET = DatabaseLifecycle.reset
DESTROY = DatabaseLifecycle.destroy


def reset(lifecycle):
    assert lifecycle.namespace in ALLOWED, 'unexpected candidate reset namespace'
    assert lifecycle.environment['COMPOSE_PROJECT_NAME'] == lifecycle.namespace.project_name
    assert lifecycle.environment['KINETICLOOP_DB_NAME'] == lifecycle.namespace.database_name
    RESETS.append(lifecycle.namespace)
    print('OWNED_RESET', lifecycle.namespace, flush=True)
    return RESET(lifecycle)


def destroy(lifecycle):
    assert lifecycle.namespace in ALLOWED, 'unexpected candidate cleanup namespace'
    DESTROYS.append(lifecycle.namespace)
    print('OWNED_DESTROY', lifecycle.namespace, flush=True)
    return DESTROY(lifecycle)


def pytest_configure(config):
    assert os.environ['KINETICLOOP_KL024_FIXTURE_OWNER'] == 'KL-019'
    assert os.environ['KINETICLOOP_KL025_FIXTURE_OWNER'] == 'KL-019'
    validate_tx_launch(ROOT, SHORT, os.environ)
    DatabaseLifecycle.reset = reset
    DatabaseLifecycle.destroy = destroy


def pytest_sessionfinish(session, exitstatus):
    DatabaseLifecycle.reset = RESET
    DatabaseLifecycle.destroy = DESTROY
    assert set(RESETS) == ALLOWED
    assert Counter(RESETS) == Counter(DESTROYS)
    print('PASS all real reset/destroy calls confined to three derived owned namespaces', flush=True)
