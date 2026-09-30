"""Candidate-only probe; never a passing CI/task result or an applied scope waiver.

For the sole selected negative downgrade test, REVISION occurs only in its two
expected-version assertions. Temporarily binding that module global to current
HEAD models the proposed two-expression repair without editing the excluded file.
"""
from __future__ import annotations

import inspect


def pytest_collection_modifyitems(items):
    assert len(items) == 1
    item = items[0]
    assert item.name == "test_populated_downgrade_fails_before_guard_or_acl_changes"
    assert inspect.getsource(item.obj).count("REVISION,") == 2
    module = item.module
    assert module.REVISION == module._MIGRATIONS.REVISION == "d4c1a9e7b203"
    assert module._MIGRATIONS.HEAD_REVISION == "e8c2f1a6b904"
    module.REVISION = module._MIGRATIONS.HEAD_REVISION
