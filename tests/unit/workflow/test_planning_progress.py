from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from kineticloop.contracts.commands import INTERNAL_ONLY_OPERATIONS, PUBLIC_COMMAND_MODELS
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.planning_progress import ContextService, PlanningWorkflowService
from kineticloop.persistence.transactions import (
    _INTERNAL_OWNER_SPECS,
    _MUTATION_COLUMNS,
    TRANSACTION_OWNER_MATRIX,
    GuardRequired,
    TransactionStateError,
    execute_command,
    execute_preparation,
)
from kineticloop.workflow.planning import ATTEMPT_ACTIVE, PlanningDenied, require_live
from kineticloop.workflow.planning_progress import (
    EXITS,
    FORWARD,
    AdvanceAttempt,
    ProgressIdentity,
    eligible_at,
    require_transition,
)

ROOT = Path(__file__).resolve().parents[3]
LABELS = frozenset({"progress"})


def progress_namespace(
    root: Path, short: str, label: str, *, worktree_digest: str | None = None
) -> DatabaseNamespace:
    if label not in LABELS or re.fullmatch(r"[0-9a-f]{7}", short) is None:
        raise ValueError("exact progress SHA/label required")
    actual = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    if worktree_digest is not None and (
        re.fullmatch(r"[0-9a-f]{12}", worktree_digest) is None or worktree_digest != actual
    ):
        raise ValueError("exact progress root digest required")
    return DatabaseNamespace(
        f"kineticloop-kl075-{label}-{short}-{actual}", f"kineticloop_kl075_{label}_{short}_{actual}"
    )


class ProgressLifecycle(DatabaseLifecycle):
    """Task-test-only gate around every nested lifecycle route."""

    def __init__(self, root: Path, short: str, label: str, **kwargs: Any) -> None:
        selected = progress_namespace(root, short, label)
        self._progress_root, self._progress_short, self._progress_label = (
            root.resolve(),
            short,
            label,
        )
        super().__init__(root, **kwargs)
        self.namespace = selected
        self.validate_target()

    def validate_target(self) -> None:
        if self.root != self._progress_root or self.namespace != progress_namespace(
            self._progress_root, self._progress_short, self._progress_label
        ):
            raise ValueError("foreign progress lifecycle target")
        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True
        ).strip()
        if self._progress_short != current[:7]:
            raise ValueError("progress lifecycle SHA does not match tested HEAD")
        for name, target in (
            ("COMPOSE_PROJECT_NAME", self.namespace.project_name),
            ("KINETICLOOP_DB_NAME", self.namespace.database_name),
            ("KINETICLOOP_KL075_COMPOSE_PROJECT", self.namespace.project_name),
            ("KINETICLOOP_KL075_DATABASE", self.namespace.database_name),
        ):
            if name in self._base_environ and self._base_environ[name] != target:
                raise ValueError("ambient foreign progress target")
        if self._base_environ.get("DATABASE_URL"):
            raise ValueError("ambient database URL is not progress lifecycle authority")

    def _run(self, command: Any, **kwargs: Any) -> Any:
        self.validate_target()
        return super()._run(command, **kwargs)

    def reset(self, *, timeout_seconds: float = 60.0) -> Any:
        self.validate_target()
        return super().reset(timeout_seconds=timeout_seconds)

    def destroy(self) -> None:
        self.validate_target()
        super().destroy()

    def start(self, *, timeout_seconds: float = 60.0) -> None:
        self.validate_target()
        super().start(timeout_seconds=timeout_seconds)

    def connection(self) -> Any:
        self.validate_target()
        return super().connection()


def basis() -> dict[str, Any]:
    actor = RoleIdentity(str(uuid4()), ActorRole.TEST)
    identity = ProgressIdentity(actor, uuid4(), uuid4(), uuid4(), "kl_test_subject_1_login")
    return {
        "identity": identity,
        "subject_id": identity.subject_id,
        "key": "progress",
        "intent_id": uuid4(),
        "request_id": uuid4(),
        "request_revision": 1,
        "attempt_id": uuid4(),
        "expected_owner": identity.key,
        "fence": 1,
        "manifest_id": uuid4(),
        "epoch": 0,
        "source_state": "CREATED",
        "target_state": "LEASED",
        "sources": {},
    }


def test_internal_identity() -> None:
    assert {"RecordSnapshot", "AdvanceAttempt"} <= set(INTERNAL_ONLY_OPERATIONS)
    assert len(PUBLIC_COMMAND_MODELS) == len(TRANSACTION_OWNER_MATRIX) == 39
    assert not {"RecordSnapshot", "AdvanceAttempt"} & set(TRANSACTION_OWNER_MATRIX)
    original = {
        k: {
            "owner": v.owner,
            "boundary": v.boundary,
            "surfaces": v.mutation_surfaces,
            "registry": v.registry_required,
            "subject": v.subject_guard_required,
            "columns": {
                ":".join(key): sorted(value) for key, value in _MUTATION_COLUMNS[k].items()
            },
        }
        for k, v in TRANSACTION_OWNER_MATRIX.items()
    }
    assert (
        hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
        == "aec8554042a26955d805bca7048b16cde5f3af58b68cc23d25311f46d25b9844"
    )
    assert _INTERNAL_OWNER_SPECS["RecordSnapshot"].owner == "ContextService"
    assert _INTERNAL_OWNER_SPECS["AdvanceAttempt"].owner == "PlanningWorkflowService"
    args = basis()
    identity = args.pop("identity")
    request = AdvanceAttempt(**args)
    for role in (ActorRole.SUBJECT, ActorRole.ADMIN, ActorRole.EVALUATION):
        with pytest.raises(PlanningDenied):
            replace(identity, actor=RoleIdentity(str(uuid4()), role))
    with pytest.raises(PlanningDenied):
        replace(identity, principal="kl_evaluation_subject_1_login")
    with pytest.raises(GuardRequired):
        ContextService(Mock(), object())  # type: ignore[arg-type]
    db = Mock()
    from psycopg.pq import TransactionStatus

    db.info.transaction_status = TransactionStatus.INTRANS
    with pytest.raises(TransactionStateError):
        PlanningWorkflowService(db, identity).advance_attempt(request)
    db.info.transaction_status = TransactionStatus.IDLE
    for change in ({"subject_id": uuid4()}, {"expected_owner": "foreign"}):
        with pytest.raises(GuardRequired):
            PlanningWorkflowService(db, identity).advance_attempt(replace(request, **change))
    with pytest.raises(GuardRequired):
        PlanningWorkflowService(db, identity).advance_attempt(object())  # type: ignore[arg-type]
    for field, wrong in ((1, uuid4()), (2, uuid4()), (3, "kl_test_subject_2_login")):
        registered: list[Any] = [
            "TEST",
            identity.policy_id,
            identity.environment_id,
            identity.principal,
        ]
        registered[field] = wrong
        fake = MagicMock()
        fake.info.transaction_status = TransactionStatus.IDLE
        fake.execute.return_value.fetchone.return_value = tuple(registered)
        with pytest.raises(GuardRequired):
            PlanningWorkflowService(fake, identity).advance_attempt(request)
    for name in ("RecordSnapshot", "AdvanceAttempt"):
        with pytest.raises(GuardRequired):
            execute_preparation(db, name, identity.subject_id, lambda s: s.insert("S29", {}))
        with pytest.raises(GuardRequired):
            execute_command(db, name, identity.subject_id, lambda tx: None)


def test_frozen_transitions() -> None:
    all_states = ATTEMPT_ACTIVE | EXITS | {"COMMITTED", "FOUND_VALID_PLAN", "UNKNOWN"}
    for source in all_states:
        for target in all_states:
            if source in ATTEMPT_ACTIVE and (FORWARD.get(source) == target or target in EXITS):
                require_transition(source, target)
            else:
                with pytest.raises(PlanningDenied):
                    require_transition(source, target)
    args = basis()
    args.pop("identity")
    for change in (
        {"target_state": "FITNESS"},
        {"fence": True},
        {"fence": 0},
        {"sources": {"snapshot": {"id": str(uuid4()), "hash": "a" * 64}}},
    ):
        with pytest.raises(PlanningDenied):
            AdvanceAttempt(**{**args, **change})
    for exit_state in EXITS:
        AdvanceAttempt(**{**args, "target_state": exit_state, "failure_code": "TEST_REASON"})
        with pytest.raises(PlanningDenied):
            AdvanceAttempt(**{**args, "target_state": exit_state})


def test_time_boundaries() -> None:
    end = datetime(2026, 10, 1, tzinfo=timezone.utc)
    start = end - timedelta(seconds=10)
    for delta, allowed in ((-1, True), (0, False), (1, False)):
        now = end + timedelta(microseconds=delta)
        assert eligible_at(now, start, end) is allowed
        for deadline, expiry in ((end, end + timedelta(hours=1)), (end + timedelta(hours=1), end)):
            values: dict[str, Any] = dict(
                status="RUNNING",
                owner="worker",
                fence=1,
                request=1,
                attempt="a",
                expected_owner="worker",
                expected_fence=1,
                expected_request=1,
                expected_attempt="a",
                attempt_status="BUILDING_CONTEXT",
                now=now,
                expiry=expiry,
                deadline=deadline,
            )
            if allowed:
                require_live(**values)
            else:
                with pytest.raises(PlanningDenied):
                    require_live(**values)


def test_namespace(tmp_path: Path) -> None:
    short = "abcdef0"
    selected = progress_namespace(ROOT, short, "progress")
    assert selected != progress_namespace(tmp_path, short, "progress")
    for bad in ("ABCDEF0", "abcdef00", "abc", "../../x", "g" * 7):
        with pytest.raises(ValueError):
            progress_namespace(ROOT, bad, "progress")
    for label in ("exec", "plan", "default", "foreign", ""):
        with pytest.raises(ValueError):
            progress_namespace(ROOT, short, label)
    for bad in ("a" * 12, "A" * 12, "../x", ""):
        with pytest.raises(ValueError):
            progress_namespace(ROOT, short, "progress", worktree_digest=bad)
    calls = Mock()
    short = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()[:7]
    selected = progress_namespace(ROOT, short, "progress")
    with pytest.raises(ValueError):
        ProgressLifecycle(ROOT, "abcdef0", "progress", runner=calls, environ={})
    lifecycle = ProgressLifecycle(ROOT, short, "progress", runner=calls, environ={})
    for name in (
        "COMPOSE_PROJECT_NAME",
        "KINETICLOOP_DB_NAME",
        "KINETICLOOP_KL075_DATABASE",
        "KINETICLOOP_KL075_COMPOSE_PROJECT",
        "DATABASE_URL",
    ):
        with pytest.raises(ValueError):
            ProgressLifecycle(ROOT, short, "progress", runner=calls, environ={name: "foreign"})
    for route in (
        lifecycle.reset,
        lifecycle.destroy,
        lifecycle.start,
        lifecycle.connection,
        lambda: lifecycle.execute_sql("SELECT 1"),
        lifecycle.validate_compose,
    ):
        lifecycle.namespace = DatabaseNamespace.for_worktree(ROOT)
        with pytest.raises(ValueError):
            route()
    lifecycle.namespace = selected
    lifecycle.root = tmp_path
    with pytest.raises(ValueError):
        lifecycle.destroy()
    calls.assert_not_called()
