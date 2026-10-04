from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.transactions import GuardRequired
from kineticloop.persistence.worker_reaper import PlanningWorkflowService
from kineticloop.workflow.planning import PlanningDenied, renewal_expiry, require_live
from kineticloop.workflow.planning_progress import ProgressIdentity
from kineticloop.workflow.worker_reaper import (
    ReapIntent,
    TestWorker,
    WorkerSchedule,
    terminal_targets,
)

ROOT = Path(__file__).resolve().parents[3]
TASK = "harness-backlog-v0.2/KL-036"


def worker_namespace(root: Path, tested: str, task: str = TASK,
                     *, root_digest: str | None = None) -> DatabaseNamespace:
    if task != TASK or type(tested) is not str or re.fullmatch(r"[0-9a-f]{40}", tested) is None:
        raise ValueError("exact KL-036 identity and full tested SHA required")
    resolved = root.resolve()
    if not resolved.is_dir() or not (resolved / "compose.yaml").is_file():
        raise ValueError("resolved task worktree required")
    actual = hashlib.sha256(os.fsencode(resolved)).hexdigest()[:12]
    if root_digest is not None and root_digest != actual:
        raise ValueError("exact resolved-root SHA12 required")
    return DatabaseNamespace(f"kineticloop-kl036-{tested[:7]}-{actual}",
                             f"kineticloop_kl036_{tested[:7]}_{actual}")


class WorkerLifecycle(DatabaseLifecycle):
    """Own test constructor and all nested lifecycle gates; shared lifecycle untouched."""

    def __init__(self, root: Path, tested: str, task: str = TASK, **kwargs: Any) -> None:
        selected = worker_namespace(root, tested, task)
        self._owned_root, self._tested, self._task = root.resolve(), tested, task
        super().__init__(root, **kwargs)
        self.namespace = selected
        self.validate_target()

    def validate_target(self) -> None:
        if self.root != self._owned_root or self.namespace != worker_namespace(
            self._owned_root, self._tested, self._task
        ):
            raise ValueError("foreign worker lifecycle target")
        current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root,
                                          text=True).strip()
        if current != self._tested:
            raise ValueError("full tested HEAD mismatch")
        for key, target in (("COMPOSE_PROJECT_NAME", self.namespace.project_name),
                            ("KINETICLOOP_DB_NAME", self.namespace.database_name)):
            if key in self._base_environ and self._base_environ[key] != target:
                raise ValueError("ambient foreign lifecycle target")
        if self._base_environ.get("DATABASE_URL"):
            raise ValueError("ambient DSN cannot authorize a lifecycle")

    def _run(self, command: Any, **kwargs: Any) -> Any:
        self.validate_target()
        prefix = self.compose_command()
        if list(command)[:len(prefix)] != prefix or len(command) <= len(prefix):
            raise ValueError("nested lifecycle command must name exact owned Compose target")
        return super()._run(command, **kwargs)

    def _psql(self, database: str, sql: str) -> Any:
        self.validate_target()
        allowed = {
            f'DROP DATABASE IF EXISTS "{self.namespace.database_name}" WITH (FORCE);',
            f'CREATE DATABASE "{self.namespace.database_name}" OWNER TO "{self.user}";',
        }
        # Existing lifecycle uses OWNER (without TO).
        allowed.add(f'CREATE DATABASE "{self.namespace.database_name}" OWNER "{self.user}";')
        if database != self.namespace.database_name and not (database == "postgres" and sql in allowed):
            raise ValueError("foreign nested SQL lifecycle target")
        return super()._psql(database, sql)

    def reset(self, *, timeout_seconds: float = 60.0) -> Any:
        self.validate_target()
        return super().reset(timeout_seconds=timeout_seconds)

    def start(self, *, timeout_seconds: float = 60.0) -> None:
        self.validate_target()
        super().start(timeout_seconds=timeout_seconds)

    def connection(self) -> Any:
        self.validate_target()
        return super().connection()

    def destroy(self) -> None:
        self.validate_target()
        super().destroy()


def identity() -> ProgressIdentity:
    return ProgressIdentity(RoleIdentity(str(uuid4()), ActorRole.TEST), uuid4(), uuid4(),
                            uuid4(), "kl_test_subject_1_login")


def candidate() -> ReapIntent:
    return ReapIntent(subject_id=uuid4(), key="reap", intent_id=uuid4(), request_id=uuid4(),
                      request_revision=1, attempt_id=uuid4(), expected_owner=None, fence=0,
                      deadline=datetime.now(timezone.utc), lease_expires_at=None,
                      intent_status="ADMITTED", attempt_status="CREATED")


def test_identity_and_namespace() -> None:
    principal = identity()
    assert PlanningWorkflowService(Mock(), principal)
    assert TestWorker(Mock(), principal)
    bad_identities: list[tuple[str, Any]] = [("actor", RoleIdentity(str(uuid4()), ActorRole.SUBJECT)),
                         ("principal", ""), ("principal", "kl_application_login"),
                         ("environment_id", "foreign"), ("policy_id", None),
                         ("subject_id", "")]
    for field, value in bad_identities:
        with pytest.raises((PlanningDenied, GuardRequired, TypeError)):
            replace(principal, **{field: value})
    tested = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    root12 = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
    expected = worker_namespace(ROOT, tested)
    assert expected.database_name == f"kineticloop_kl036_{tested[:7]}_{root12}"
    assert expected.project_name == f"kineticloop-kl036-{tested[:7]}-{root12}"
    runner = Mock()
    lifecycle = WorkerLifecycle(ROOT, tested, runner=runner, environ={})
    for bad in ("", "a" * 7, "A" * 40, "x" * 40):
        with pytest.raises(ValueError):
            worker_namespace(ROOT, bad)
    for task in ("", "KL-036", "harness-backlog-v0.2/KL-037"):
        with pytest.raises(ValueError):
            worker_namespace(ROOT, tested, task)
    with pytest.raises(ValueError):
        worker_namespace(ROOT, tested, root_digest="0" * 12)
    for env in ({"COMPOSE_PROJECT_NAME": "foreign"}, {"KINETICLOOP_DB_NAME": ""},
                {"DATABASE_URL": "foreign"}):
        with pytest.raises(ValueError):
            WorkerLifecycle(ROOT, tested, runner=runner, environ=env)
    for method in (lifecycle.reset, lifecycle.start, lifecycle.connection, lifecycle.destroy):
        lifecycle.namespace = DatabaseNamespace("foreign", "foreign")
        with pytest.raises(ValueError):
            method()
        lifecycle.namespace = expected
    with pytest.raises(ValueError):
        lifecycle._run(["docker", "compose", "--project-name", "foreign", "up"])
    with pytest.raises(ValueError):
        lifecycle._psql("postgres", 'DROP DATABASE "foreign";')
    runner.assert_not_called()
    request = candidate()
    assert terminal_targets(request, request.deadline, cancel_expired_lease=False) == (
        "DEADLINE_EXCEEDED", "LEASE_LOST")
    for changes in ({"fence": 1}, {"intent_status": "RUNNING"},
                    {"attempt_status": "LEASED"}, {"lease_expires_at": request.deadline},
                    {"intent_status": "FAILED"}, {"request_revision": True}):
        with pytest.raises(PlanningDenied):
            replace(request, **changes)
    for authority in ("status", "sql", "callback", "now", "compatibility"):
        with pytest.raises(TypeError):
            ReapIntent(**{**{name: getattr(request, name) for name in request.__slots__},
                          authority: "caller"})


def test_lease_and_deadline_boundaries() -> None:
    now = datetime.now(timezone.utc)
    expiry, deadline = now + timedelta(seconds=5), now + timedelta(seconds=10)
    assert renewal_expiry(now, expiry, deadline, 6) == now + timedelta(seconds=6)
    assert renewal_expiry(now, expiry, deadline, 20) == deadline
    live: dict[str, Any] = dict(status="RUNNING", owner="test:worker", fence=2, request=1, attempt="a",
                expected_owner="test:worker", expected_fence=2, expected_request=1,
                expected_attempt="a", attempt_status="LEASED", now=now, expiry=expiry,
                deadline=deadline)
    require_live(**live)
    for changes in ({"now": expiry}, {"now": deadline}, {"owner": "old"},
                    {"fence": 1}, {"request": 2}, {"attempt": "old"},
                    {"status": "CANCELLED"}, {"attempt_status": "COMMITTED"}):
        with pytest.raises(PlanningDenied):
            require_live(**{**live, **changes})
    for at in (expiry, deadline):
        with pytest.raises(PlanningDenied):
            renewal_expiry(at, expiry, deadline, 6)
    request = replace(candidate(), expected_owner="test:worker", fence=2,
                      lease_expires_at=expiry, deadline=deadline, intent_status="RUNNING",
                      attempt_status="LEASED")
    with pytest.raises(PlanningDenied):
        terminal_targets(request, expiry - timedelta(microseconds=1), cancel_expired_lease=True)
    assert terminal_targets(request, expiry, cancel_expired_lease=True) == ("CANCELLED", "CANCELLED")
    with pytest.raises(PlanningDenied):
        terminal_targets(request, expiry, cancel_expired_lease=False)
    assert terminal_targets(request, deadline, cancel_expired_lease=False) == (
        "DEADLINE_EXCEEDED", "LEASE_LOST")
    assert WorkerSchedule()
    for kwargs in ({"lease_seconds": 0}, {"heartbeat_seconds": 5},
                   {"heartbeat_seconds": float("nan")}, {"max_heartbeats": 101}):
        with pytest.raises(PlanningDenied):
            WorkerSchedule(**kwargs)
