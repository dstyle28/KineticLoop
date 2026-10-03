"""Parent-owned collection/execution evidence for developer harness parallelism."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

_collections: dict[str, list[str]] = {}
_started: list[str] = []
_reports: list[dict[str, Any]] = []
_errors: list[str] = []


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "harness_serial: requires an exclusive shared resource")
    expected = int(os.environ["KINETICLOOP_HARNESS_WORKERS"])
    actual = config.getoption("numprocesses", default=0) or 0
    if (not hasattr(config, "workerinput") and not config.getoption("collectonly")
            and actual != (expected if expected > 1 else 0)):
        raise pytest.UsageError("Harness worker configuration was overridden")
    if any(spec != "popen" for spec in config.getoption("tx", default=[])):
        raise pytest.UsageError("Harness workers must be local processes")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if int(os.environ["KINETICLOOP_HARNESS_WORKERS"]) == 1:
        return
    scope = Path(os.environ["KINETICLOOP_HARNESS_ROOT"]).resolve() / "tests/harness"
    for item in items:
        if not item.path.resolve().is_relative_to(scope):
            raise pytest.UsageError("Parallel harness scope violation: " + item.nodeid)
        if item.get_closest_marker("harness_serial"):
            raise pytest.UsageError("Exclusive resource requires --workers 1: " + item.nodeid)


def pytest_collection_finish(session: pytest.Session) -> None:
    if not hasattr(session.config, "workerinput"):
        _collections["serial"] = [item.nodeid for item in session.items]


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node: Any, ids: list[str]) -> None:
    _collections.pop("serial", None)
    _collections[node.gateway.id] = list(ids)


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node: Any, error: Any) -> None:
    if error is not None:
        _errors.append(str(node.gateway.id) + ": " + str(error))


def pytest_collectreport(report: Any) -> None:
    if report.failed:
        _errors.append(str(report.longrepr))


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int, str]) -> None:
    _started.append(nodeid)


def pytest_runtest_logreport(report: Any) -> None:
    _reports.append({"nodeid": report.nodeid, "phase": report.when,
                     "outcome": report.outcome, "duration": report.duration,
                     "worker": getattr(report, "worker_id", "serial")})


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    # Workers never write a shared file. xdist forwards their reports to this parent.
    if hasattr(session.config, "workerinput"):
        return
    target = Path(os.environ["KINETICLOOP_HARNESS_OBSERVER"])
    target.write_text(json.dumps({"collections": _collections, "started": _started,
                                  "reports": _reports, "errors": _errors,
                                  "exit_code": int(exitstatus)}, indent=2) + "\n")
