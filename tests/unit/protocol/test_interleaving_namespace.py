"""KL026 lifecycle isolation and exact half-open predicate evidence (PU)."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace
from kineticloop.protocol.authorization import (
    AuthorizationEvaluationError,
    ExecutabilityBasis,
    ValidityDependency,
    evaluate_executability,
    evaluate_validity_closure,
)
from kineticloop.workflow.planning import PlanningDenied, require_live

ROOT = Path(__file__).resolve().parents[3]
AMBIENT_TARGETS = (
    "COMPOSE_PROJECT_NAME",
    "KINETICLOOP_DB_NAME",
    "DATABASE_URL",
    "KINETICLOOP_KL022_COMPOSE_PROJECT",
    "KINETICLOOP_KL022_DATABASE",
    "KINETICLOOP_KL024_FIXTURE_OWNER",
    "KINETICLOOP_KL025_FIXTURE_OWNER",
)


def interleaving_namespace(
    root: Path, sha: str, label: str = "interleave", *, worktree_digest: str | None = None
) -> DatabaseNamespace:
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None or label != "interleave":
        raise ValueError("KL026 requires full tested SHA and fixed interleave label")
    actual = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    if worktree_digest is not None and worktree_digest != actual:
        raise ValueError("KL026 resolved worktree digest mismatch")
    return DatabaseNamespace(
        f"kineticloop-kl026-{label}-{sha[:7]}-{actual}",
        f"kineticloop_kl026_{label}_{sha[:7]}_{actual}",
    )


class OwnedLifecycle(DatabaseLifecycle):
    """Recheck ownership before every nested Docker/SQL/reset/cleanup operation."""

    def __init__(
        self,
        root: Path,
        sha: str,
        *,
        runner: Any = subprocess.run,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        selected = interleaving_namespace(root, sha)
        ambient = dict(os.environ if environ is None else environ)
        if any(key in ambient for key in AMBIENT_TARGETS):
            raise ValueError("ambient/default/foreign lifecycle target denied")
        super().__init__(root, runner=runner, environ=ambient)
        self.namespace = selected
        self.owned_root, self.owned_sha = root.resolve(), sha
        self.inventory: list[list[str]] = []

    def validate_owner(self) -> None:
        if self.root != self.owned_root or self.namespace != interleaving_namespace(
            self.owned_root, self.owned_sha
        ):
            raise ValueError("KL026 lifecycle root/namespace drift")
        if any(key in self._base_environ for key in AMBIENT_TARGETS):
            raise ValueError("ambient lifecycle target denied")

    def _run(
        self, command: Sequence[str], *, check: bool = True, timeout_seconds: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        self.validate_owner()
        if list(command[:6]) != self.compose_command() or (
            "psql" in command
            and command[command.index("--dbname") + 1]
            not in {"postgres", self.namespace.database_name}
        ):
            raise ValueError("foreign nested command target")
        self.inventory.append(list(command))
        return super()._run(command, check=check, timeout_seconds=timeout_seconds)


def namespace_core(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sha = "abcdef1" + "0" * 33
    selected = interleaving_namespace(ROOT, sha)
    assert interleaving_namespace(tmp_path, sha) != selected
    assert interleaving_namespace(ROOT / ".." / ROOT.name, sha) == selected
    for bad in ("", "abcdef1", "A" * 40, "f" * 41, "../" + "0" * 37):
        with pytest.raises(ValueError):
            interleaving_namespace(ROOT, bad)
    for label in ("", "exec", "ledger", "plan", "../interleave", "INTERLEAVE"):
        with pytest.raises(ValueError):
            interleaving_namespace(ROOT, sha, label)
    for digest in ("", "a" * 12, "A" * 12, "0" * 11):
        with pytest.raises(ValueError):
            interleaving_namespace(ROOT, sha, worktree_digest=digest)
    calls: list[Any] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, "127.0.0.1:5432\n", "")

    for key in AMBIENT_TARGETS:
        for value in ("", "foreign", selected.database_name, selected.project_name):
            with pytest.raises(ValueError):
                OwnedLifecycle(ROOT, sha, runner=runner, environ={key: value})
            assert calls == []
    lifecycle = OwnedLifecycle(ROOT, sha, runner=runner, environ={})
    for namespace in (
        DatabaseNamespace.for_worktree(ROOT),
        interleaving_namespace(tmp_path, sha),
        DatabaseNamespace(selected.project_name, "foreign"),
    ):
        lifecycle.namespace = namespace
        for action in (
            lifecycle.reset,
            lifecycle.destroy,
            lambda: lifecycle.execute_sql("SELECT 1"),
            lifecycle.connection,
        ):
            with pytest.raises(ValueError):
                action()
            assert calls == []
    lifecycle.namespace = selected
    lifecycle.root = tmp_path
    with pytest.raises(ValueError):
        lifecycle.destroy()
    assert calls == []
    lifecycle.root = ROOT
    assert lifecycle.reset().database_name == selected.database_name
    lifecycle.execute_sql("SELECT 1")
    lifecycle.destroy()
    assert all(
        command[3] == selected.project_name and env["KINETICLOOP_DB_NAME"] == selected.database_name
        for command, env in calls
    )
    sqls = [cmd[-1] for cmd, _ in calls if "psql" in cmd]
    assert sqls[:2] == [
        f'DROP DATABASE IF EXISTS "{selected.database_name}" WITH (FORCE);',
        f'CREATE DATABASE "{selected.database_name}" OWNER "kineticloop";',
    ]
    assert calls[-1][0][-3:] == ["down", "--volumes", "--remove-orphans"]


def test_time_boundaries() -> None:
    """Actual pure predicates; equality is PU, never a real-PG equality claim."""
    end = datetime(2026, 9, 30, 12, tzinfo=UTC)
    basis = ExecutabilityBasis(
        authoritative_now=end,
        requested_subject_id="test",
        authorization_subject_id="test",
        prescription_content_hash="hash",
        authorization_content_hash="hash",
        requested_scope="TEST_ONLY",
        authorization_scope="TEST_ONLY",
        current_epoch=0,
        authorization_epoch=0,
        valid_from=end - timedelta(minutes=1),
        valid_until=end,
        target_state="ACTIVE",
        controls_proven=True,
        applicable_control_states=(),
        policy_admissible=True,
        session_relation_current=True,
        dependency_eligible=True,
    )
    for offset in (-1, 0, 1):
        now = end + timedelta(microseconds=offset)
        assert evaluate_executability(replace(basis, authoritative_now=now)).is_executable == (
            offset < 0
        )
        dep = ValidityDependency("ARTIFACT", "test", 1, end - timedelta(minutes=1), end)
        if offset < 0:
            assert (
                evaluate_validity_closure(authoritative_now=now, dependencies=[dep]).valid_until
                == end
            )
        else:
            with pytest.raises(AuthorizationEvaluationError):
                evaluate_validity_closure(authoritative_now=now, dependencies=[dep])
        for boundary in ("lease", "deadline"):
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
                now=now,
                expiry=end if boundary == "lease" else end + timedelta(minutes=1),
                deadline=end if boundary == "deadline" else end + timedelta(minutes=1),
            )
            if offset < 0:
                require_live(**args)
            else:
                with pytest.raises(PlanningDenied):
                    require_live(**args)


def test_namespace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    namespace_core(monkeypatch, tmp_path)
    import ast
    import importlib.util
    import sys

    path = ROOT / "tests/db/test_protocol_interleavings.py"
    source = path.read_text()
    tree = ast.parse(source)
    names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
    assert names == {
        "test_publish_vs_user_revoke",
        "test_start_vs_user_revoke",
        "test_cancel_vs_dispatch",
        "test_takeover_vs_commit",
        "test_artifact_revoke_vs_issue",
        "test_artifact_revoke_vs_start",
        "test_artifact_revoke_vs_publish",
        "test_seal_vs_input_update",
        "test_expiry_vs_start",
    }
    # No foreign fixture or seed-builder import is evaluated. Only migrations supply
    # immutable bootstrap helpers and receive the explicitly selected lifecycle.
    assert 'load("tests/db/test_migrations.py")' in source
    assert 'load("tests/db/test_protocol_execution.py")' not in source
    assert "bootstrap_two_phase(lifecycle)" in source
    spec = importlib.util.spec_from_file_location("kl026_namespace_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    calls: list[Any] = []
    sha = "abcdef1" + "0" * 33

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs["env"]))
        return subprocess.CompletedProcess(command, 0, "127.0.0.1:5432\n", "")

    owned_class = module._NAMESPACE.OwnedLifecycle

    class Stop(RuntimeError):
        pass

    def selected(root: Path, revision: str, **kwargs: Any) -> Any:
        return owned_class(root, revision, runner=runner, environ={})

    def bootstrap(lifecycle: Any) -> None:
        assert lifecycle.namespace == interleaving_namespace(ROOT, sha)
        lifecycle.reset()
        raise Stop("nested bootstrap failure")

    with monkeypatch.context() as patch:
        patch.setattr(module._NAMESPACE, "namespace_core", lambda *a: None)
        patch.setattr(module._NAMESPACE, "OwnedLifecycle", selected)
        patch.setattr(module._MIGRATIONS, "bootstrap_two_phase", bootstrap)
        for bad in ("", "abc123", "ABCDEF1" + "0" * 33):
            patch.setattr(module.subprocess, "check_output", lambda *a, value=bad, **kw: value)
            with pytest.raises(ValueError):
                next(module.database_urls.__wrapped__())
            assert calls == []
        patch.setattr(module.subprocess, "check_output", lambda *a, **kw: sha)
        for name in (
            "postgres",
            "kineticloop_kl019_exec_abcdef1_foreign",
            DatabaseNamespace.for_worktree(ROOT).database_name,
        ):
            with pytest.raises(ValueError):
                module.connect("postgresql://localhost/" + name)
            assert calls == []
        with pytest.raises(Stop):
            next(module.database_urls.__wrapped__())
    expected = interleaving_namespace(ROOT, sha)
    assert all(
        cmd[3] == expected.project_name and env["KINETICLOOP_DB_NAME"] == expected.database_name
        for cmd, env in calls
    )
    assert calls[-1][0][-3:] == ["down", "--volumes", "--remove-orphans"]


def test_cancellation_identity() -> None:
    """Installed HG039 candidate: strict payload, trusted identity, basis and history PU."""
    import importlib.util
    import json
    import sys
    from dataclasses import replace
    from uuid import uuid4

    from pydantic import ValidationError

    from kineticloop.contracts.commands import PUBLIC_COMMAND_MODELS, CancelIntent, SubjectCommand
    from kineticloop.identity import ActorRole, RoleIdentity
    from kineticloop.persistence.planning import PlanningIdentity
    from kineticloop.persistence.transactions import GuardRequired, IdempotencyConflict

    spec = importlib.util.spec_from_file_location(
        "kl026_cancel_pu", ROOT / "tests/db/test_protocol_interleavings.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    cls = module.TestCancelIntentRequest
    assert not issubclass(cls, SubjectCommand) and cls not in PUBLIC_COMMAND_MODELS
    assert len(PUBLIC_COMMAND_MODELS) == 39 and CancelIntent in PUBLIC_COMMAND_MODELS
    assert {"actor", "request_hash", "authorization_scope"}.isdisjoint(cls.model_fields)
    root, attempt, reservation = uuid4(), uuid4(), uuid4()
    request = module.cancel_request(root, attempt, reservation)
    payload = request.model_dump(mode="python")
    identity = PlanningIdentity(module.IDENTITY.actor, module.SUBJECT)
    registration = ("TEST", module.POLICY, module.ENVIRONMENT, module.IDENTITY.principal)

    def bind(
        candidate: Any = request, actor: Any = identity, registered: Any = registration
    ) -> Any:
        return module.bind(
            candidate,
            actor,
            module.POLICY,
            module.ENVIRONMENT,
            module.IDENTITY.principal,
            registered,
        )

    scope, key, request_hash = bind()
    assert scope == identity.key and key == request.key and len(request_hash) == 64
    assert bind(cls.model_validate(dict(reversed(list(payload.items())))))[2] == request_hash
    assert bind(cls.model_validate({**payload, "expected_fence": 2}))[2] != request_hash
    with pytest.raises(ValidationError):
        request.expected_fence = 2
    with pytest.raises(ValidationError):
        bind(request.model_copy(update={"expected_fence": True}))
    malformed = [
        ("subject_id", "invalid"),
        ("policy_id", 2),
        ("environment_id", None),
        ("key", ""),
        ("key", " "),
        ("key", " cancel"),
        ("key", "x" * 513),
        ("principal", ""),
        ("intent_id", root),
        ("attempt_id", "foreign"),
        ("reservation_id", False),
        ("expected_request_revision", True),
        ("expected_request_revision", 0),
        ("expected_request_revision", "1"),
        ("expected_fence", False),
        ("expected_fence", -1),
        ("expected_fence", "1"),
        ("boundary", "T4"),
        ("command_kind", "CommitBundle"),
        ("actor", {}),
        ("request_hash", "0" * 64),
        ("authorization_scope", "production"),
    ]
    for field, value in malformed:
        with pytest.raises(ValidationError):
            cls.model_validate({**payload, field: value})
    for field in ("subject_id", "policy_id", "environment_id", "principal"):
        value = "kl_test_subject_2_login" if field == "principal" else str(uuid4())
        with pytest.raises(GuardRequired):
            bind(cls.model_validate({**payload, field: value}))
    for actor in (
        object(),
        PlanningIdentity(RoleIdentity(str(uuid4()), ActorRole.SUBJECT), module.SUBJECT),
        replace(identity, subject_id=uuid4()),
        replace(identity, subject_id=cast(Any, str(module.SUBJECT))),
    ):
        with pytest.raises(GuardRequired):
            bind(actor=actor)
    for registered in (
        None,
        ("PRODUCTION", *registration[1:]),
        ("TEST", uuid4(), *registration[2:]),
        ("TEST", module.POLICY, uuid4(), module.IDENTITY.principal),
        ("TEST", module.POLICY, module.ENVIRONMENT, "kl_test_subject_2_login"),
    ):
        with pytest.raises(GuardRequired):
            bind(registered=registered)
    for field in ("policy", "environment"):
        args = dict(
            identity=identity,
            policy=module.POLICY,
            environment=module.ENVIRONMENT,
            principal=module.IDENTITY.principal,
            registration=registration,
        )
        args[field] = str(args[field])
        with pytest.raises(GuardRequired):
            module.bind(request, **args)
    foreign = cls.model_validate({**payload, "principal": "foreign_login"})
    with pytest.raises(GuardRequired):
        module.bind(
            foreign,
            identity,
            module.POLICY,
            module.ENVIRONMENT,
            "foreign_login",
            ("TEST", module.POLICY, module.ENVIRONMENT, "foreign_login"),
        )
    basis = dict(
        subject_id=module.SUBJECT,
        intent_id=root,
        attempt_id=attempt,
        reservation_id=reservation,
        reservation_root=root,
        reservation_attempt=attempt,
        status="RUNNING",
        request_revision=1,
        fence=1,
        reservation_status="RESERVED",
    )
    assert module.locked_basis(request, basis) == "CANCELLED"
    assert (
        module.locked_basis(request, {**basis, "reservation_status": "DISPATCH_INTENT"})
        == "CANCELLED"
    )
    assert module.locked_basis(request, {**basis, "status": "FOUND_VALID_PLAN"}) == "COMPLETED_FACT"
    bad_basis: list[tuple[str, Any]] = [
        (field, uuid4())
        for field in (
            "subject_id",
            "intent_id",
            "attempt_id",
            "reservation_id",
            "reservation_root",
            "reservation_attempt",
        )
    ]
    bad_basis += [
        ("status", "CANCELLED"),
        ("status", "DEADLINE_EXCEEDED"),
        ("request_revision", 2),
        ("fence", 2),
        ("reservation_status", "UNKNOWN"),
    ]
    for field, value in bad_basis:
        with pytest.raises(GuardRequired):
            module.locked_basis(request, {**basis, field: value})
    receipt = (
        request_hash,
        "SUCCEEDED",
        {"outcome": {"intent_id": str(root), "status": "CANCELLED"}},
    )
    assert module.historical(request, None) is None
    assert module.historical(request, receipt) == {
        **receipt[2]["outcome"],
        "replayed": True,
        "executable": False,
    }
    for receipt_bad in (
        ("0" * 64, *receipt[1:]),
        (request_hash, "FAILED", receipt[2]),
        (request_hash, "SUCCEEDED", {}),
    ):
        with pytest.raises(IdempotencyConflict):
            module.historical(request, receipt_bad)
    with pytest.raises(IdempotencyConflict):
        module.historical(cls.model_validate({**payload, "expected_fence": 2}), receipt)
    for boundary in ("T4", "T8"):
        with pytest.raises(ValidationError, match="TEST_ONLY is admitted only at T6/T7"):
            CancelIntent.model_validate_json(
                json.dumps({
                    **module.wire("CancelIntent"),
                    "boundary": boundary,
                    "intent_id": str(root),
                    "expected_request_revision": 1,
                    "expected_fence": 1,
                })
            )
    # Public validator/registry bytes remain those of the actual merged authority.
    source = "src/kineticloop/contracts/commands.py"
    assert (ROOT / source).read_bytes() == subprocess.check_output(
        ["git", "show", "37de321:" + source], cwd=ROOT
    )
    print(
        "KL026_PU "
        + json.dumps(
            {
                "check": "cancellation_identity_pu",
                "strict_negative_cases": len(malformed),
                "basis_negative_cases": len(bad_basis),
                "installed_candidate": True,
                "public_commands": len(PUBLIC_COMMAND_MODELS),
                "layer": "PU",
            }
        )
    )
