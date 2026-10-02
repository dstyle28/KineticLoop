from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError, DatabaseNamespace
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.protocol.execution import (
    ExecutionIdentity,
    command_digest,
)

ROOT = Path(__file__).resolve().parents[3]
AMBIENT = {
    "COMPOSE_PROJECT_NAME",
    "KINETICLOOP_DB_NAME",
    "COMPOSE_FILE",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DATABASE_URL",
    "KINETICLOOP_KL076_COMPOSE_PROJECT",
    "KINETICLOOP_KL076_DATABASE",
    "KINETICLOOP_KL027_DATABASE",
    "KINETICLOOP_KL027_COMPOSE_PROJECT",
    "PGDATABASE",
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "KINETICLOOP_DB_USER",
    "KINETICLOOP_DB_PASSWORD",
}


def fixture_namespace(
    root: Path, head: str, label: str = "demo", *, worktree_digest: str | None = None
) -> DatabaseNamespace:
    if root.resolve() != ROOT or not re.fullmatch(r"[0-9a-f]{40}", head) or label != "demo":
        raise DatabaseLifecycleError("exact KL027 task/SHA/resolved-root/label required")
    token = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    if worktree_digest is not None and (
        not re.fullmatch(r"[0-9a-f]{12}", worktree_digest) or token != worktree_digest
    ):
        raise DatabaseLifecycleError("exact resolved worktree digest required")
    return DatabaseNamespace(
        f"kineticloop-kl027-{label}-{head[:7]}-{token}",
        f"kineticloop_kl027_{label}_{head[:7]}_{token}",
    )


class OwnedLifecycle(DatabaseLifecycle):
    def __init__(
        self, root: Path, head: str, *, environ: Mapping[str, str] | None = None, **kwargs: Any
    ):
        selected = fixture_namespace(root, head)
        env = dict(os.environ if environ is None else environ)
        if AMBIENT & env.keys():
            raise DatabaseLifecycleError("ambient namespace/runtime override")
        self.head = head
        self.inventory: list[str] = []
        super().__init__(root, environ=env, **kwargs)
        self.namespace = selected
        self.validate_target()

    def validate_target(self) -> None:
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if (
            self.head != actual
            or self.namespace != fixture_namespace(self.root, self.head)
            or AMBIENT & self._base_environ.keys()
        ):
            raise DatabaseLifecycleError("foreign KL027 lifecycle/ambient target")

    def _run(self, command: Any, **kwargs: Any) -> Any:
        self.validate_target()
        return super()._run(command, **kwargs)

    def compose_command(self, *args: str) -> list[str]:
        self.validate_target()
        return super().compose_command(*args)

    def reset(self, *, timeout_seconds: float = 60) -> Any:
        self.validate_target()
        self.inventory.append("reset")
        return super().reset(timeout_seconds=timeout_seconds)

    def start(self, *, timeout_seconds: float = 60) -> None:
        self.validate_target()
        self.inventory.append("start")
        super().start(timeout_seconds=timeout_seconds)

    def connection(self) -> Any:
        self.validate_target()
        return super().connection()

    def destroy(self) -> None:
        self.validate_target()
        self.inventory.append("destroy")
        super().destroy()

    def bootstrap(self, selected_bootstrap: Callable[..., Any]) -> Any:
        self.validate_target()
        self.inventory.append("bootstrap_two_phase(selected_lifecycle)")
        return selected_bootstrap(self)


def test_namespace_and_boundary(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    selected = fixture_namespace(ROOT, head)
    expected_digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
    assert selected.project_name == f"kineticloop-kl027-demo-{head[:7]}-{expected_digest}"
    assert selected.database_name == f"kineticloop_kl027_demo_{head[:7]}_{expected_digest}"
    for root, sha, label in (
        (tmp_path, head, "demo"),
        (ROOT, head[:7], "demo"),
        (ROOT, "G" * 40, "demo"),
        (ROOT, head, "progress"),
    ):
        with pytest.raises(DatabaseLifecycleError):
            fixture_namespace(root, sha, label)
    for token in ("bad", "0" * 12, "G" * 12):
        with pytest.raises(DatabaseLifecycleError):
            fixture_namespace(ROOT, head, worktree_digest=token)
    calls: list[Any] = []

    def runner(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    own = OwnedLifecycle(ROOT, head, environ={}, runner=runner)
    for namespace in (
        DatabaseNamespace("foreign", "postgres"),
        DatabaseNamespace(selected.project_name, "postgres"),
    ):
        own.namespace = namespace
        for action in (
            own.reset,
            own.start,
            own.destroy,
            own.connection,
            lambda: own.bootstrap(lambda lifecycle: None),
            lambda: own._run(["docker", "version"]),
        ):
            with pytest.raises(DatabaseLifecycleError):
                action()
    own.namespace = selected
    for key in AMBIENT:
        with pytest.raises(DatabaseLifecycleError):
            OwnedLifecycle(ROOT, head, environ={key: "foreign"}, runner=runner)
        own._base_environ[key] = "foreign"
        for action in (own.reset, own.destroy, lambda: own.bootstrap(lambda lifecycle: None)):
            with pytest.raises(DatabaseLifecycleError):
                action()
        own._base_environ.pop(key)
    assert not calls
    own.bootstrap(lambda lifecycle: lifecycle._run(["docker", "version"]))
    own.destroy()
    assert len(calls) == 2
    import ast

    db_source = (ROOT / "tests/db/test_test_only_demo.py").read_text()
    tree = ast.parse(db_source)
    target_tables = {
        "factset_revisions",
        "factset_members",
        "projection_versions",
        "projection_dependencies",
        "manifest_builds",
        "decision_manifests",
        "manifest_projection_bindings",
        "decision_snapshots",
        "planning_intents",
        "planning_attempts",
        "proposal_revisions",
        "prescription_demand_features",
        "evidence_resolutions",
        "validation_results",
        "daily_plan_heads",
        "daily_bundle_revisions",
        "prescription_revisions",
        "bundle_prescription_members",
        "authorization_issuances",
        "execution_bindings",
        "workout_sessions",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            sql = node.value.lower()
            assert not any(
                "insert into kineticloop." + table in sql or "update kineticloop." + table in sql
                for table in target_tables
            )
            assert "tests/db/test_full_test_execution.py" not in sql
            assert "tests/db/test_full_action_preparation.py" not in sql
    test_half_open_equality()
    from dataclasses import replace

    for role in (ActorRole.SUBJECT, ActorRole.EVALUATION):
        with pytest.raises(ValueError):
            replace(identity(), actor=RoleIdentity(str(uuid4()), role))
    print(
        "NAMESPACE_PU",
        selected,
        "negative_controls=foreign_root,sha,digest,label,ambient,nested_cleanup",
        "nested_inventory",
        own.inventory,
    )


def identity() -> ExecutionIdentity:
    return ExecutionIdentity(
        RoleIdentity(str(uuid4()), ActorRole.TEST),
        uuid4(),
        uuid4(),
        uuid4(),
        "kl_test_subject_1_login",
    )


def wire(auth: ExecutionIdentity, model: Any, **extra: Any) -> Any:
    kind = model.__name__
    payload = {
        "schema_version": "kineticloop-command-v1",
        "command_kind": kind,
        "boundary": "T6" if kind == "CommitBundle" else "T7",
        "command_id": str(uuid4()),
        "actor": {
            "schema": "kineticloop-role-identity-v1",
            "identity_id": auth.actor.identity_id,
            "role": "test",
        },
        "idempotency_key": str(uuid4()),
        "request_hash": "0" * 64,
        "subject_id": str(auth.subject_id),
        "explicit_scope": None,
        "authorization_scope": {
            "scope": "test_only",
            "subject_id": str(auth.subject_id),
            "policy_id": str(auth.policy_id),
            "environment_id": str(auth.environment_id),
            "subject_boundary": "isolated_non_production",
            "policy_boundary": "isolated_non_production",
            "environment_boundary": "isolated_non_production",
            "direct_write_allowed": False,
            "command_owner_guard_required": True,
        },
        **extra,
    }
    first = model.model_validate_json(json.dumps(payload))
    return model.model_validate_json(json.dumps({**payload, "request_hash": command_digest(first)}))


def test_half_open_equality() -> None:
    from kineticloop.workflow.planning import PlanningDenied, require_live
    from kineticloop.workflow.planning_progress import eligible_at

    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = now + timedelta(seconds=1)
    assert eligible_at(now, now, end)
    for instant in (end, end + timedelta(microseconds=1)):
        assert not eligible_at(instant, now, end)
    from dataclasses import replace

    from kineticloop.protocol.authorization import ExecutabilityBasis, evaluate_executability

    basis = ExecutabilityBasis(
        now,
        "subject",
        "subject",
        "hash",
        "hash",
        "TEST_ONLY",
        "TEST_ONLY",
        1,
        1,
        now,
        end,
        "ACTIVE",
        True,
        (),
        True,
        True,
        True,
    )
    assert evaluate_executability(basis).is_executable
    for instant in (end, end + timedelta(microseconds=1)):
        decision = evaluate_executability(replace(basis, authoritative_now=instant))
        assert not decision.is_executable and decision.denial_reasons == ("TIME_INELIGIBLE",)
    for bound in ("lease", "deadline"):
        for delta in (-1, 0, 1):
            instant = end + timedelta(microseconds=delta)
            args: dict[str, Any] = dict(
                status="RUNNING",
                owner="test:owner",
                fence=1,
                request=1,
                attempt="attempt",
                expected_owner="test:owner",
                expected_fence=1,
                expected_request=1,
                expected_attempt="attempt",
                attempt_status="COMMIT_READY",
                now=instant,
                expiry=end if bound == "lease" else end + timedelta(seconds=1),
                deadline=end if bound == "deadline" else end + timedelta(seconds=1),
            )
            if delta < 0:
                require_live(**args)
            else:
                with pytest.raises(PlanningDenied):
                    require_live(**args)
    print(
        "HALF_OPEN_EQUALITY_PU actual eligibility/lease/deadline predicates; separately labeled, no DC equality claim"
    )
