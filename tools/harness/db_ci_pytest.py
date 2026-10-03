"""Record actual pytest node IDs for full DB collection/execution comparison."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    target = os.environ.get("KINETICLOOP_DB_CI_NODEIDS")
    if target:
        Path(target).write_text(json.dumps({
            "nodeids": [item.nodeid for item in session.items],
            "exit_code": int(exitstatus),
        }, indent=2) + "\n")
