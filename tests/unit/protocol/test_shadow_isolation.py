from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
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
    "KINETICLOOP_KL029_DATABASE",
    "KINETICLOOP_KL027_COMPOSE_PROJECT",
    "KINETICLOOP_KL029_COMPOSE_PROJECT",
    "PGDATABASE",
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGOPTIONS",
    "KINETICLOOP_KL028_DATABASE",
    "KINETICLOOP_KL028_COMPOSE_PROJECT",
    "KINETICLOOP_DB_USER",
    "KINETICLOOP_DB_PASSWORD",
}


def fixture_namespace(
    root: Path, head: str, label: str = "shadow", *, worktree_digest: str | None = None
) -> DatabaseNamespace:
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if (
        root.resolve() != ROOT
        or not re.fullmatch(r"[0-9a-f]{40}", head)
        or head != actual
        or label != "shadow"
    ):
        raise DatabaseLifecycleError("exact KL029 task/SHA/resolved-root/label required")
    token = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    if worktree_digest is not None and (
        not re.fullmatch(r"[0-9a-f]{12}", worktree_digest) or token != worktree_digest
    ):
        raise DatabaseLifecycleError("exact resolved worktree digest required")
    return DatabaseNamespace(
        f"kineticloop-kl029-{label}-{head[:7]}-{token}",
        f"kineticloop_kl029_{label}_{head[:7]}_{token}",
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
            raise DatabaseLifecycleError("foreign KL029 lifecycle/ambient target")

    def _run(self, command: Any, **kwargs: Any) -> Any:
        self.validate_target()
        kwargs.setdefault("timeout_seconds", 60)
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
    assert selected.project_name == f"kineticloop-kl029-shadow-{head[:7]}-{expected_digest}"
    assert selected.database_name == f"kineticloop_kl029_shadow_{head[:7]}_{expected_digest}"
    for root, sha, label in (
        (tmp_path, head, "shadow"),
        (ROOT, head[:7], "shadow"),
        (ROOT, "G" * 40, "shadow"),
        (ROOT, "0" * 40, "shadow"),
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
        DatabaseNamespace.for_worktree(ROOT),
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
    original_root = own.root
    for changed_root, changed_head in ((tmp_path, head), (ROOT, "0" * 40), (ROOT, head[:7])):
        own.root, own.head = changed_root, changed_head
        for action in (
            own.reset,
            own.start,
            own.destroy,
            own.connection,
            lambda: own.bootstrap(lambda lifecycle: lifecycle.destroy()),
        ):
            with pytest.raises(DatabaseLifecycleError):
                action()
    own.root, own.head = original_root, head
    assert not calls
    own.bootstrap(lambda lifecycle: lifecycle._run(["docker", "version"]))
    own.destroy()
    assert len(calls) == 2
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


def start_wire(auth: ExecutionIdentity) -> Any:
    from kineticloop.contracts.commands import StartSession

    return wire(
        auth,
        StartSession,
        session_id=str(uuid4()),
        action_key=str(uuid4()),
        prescription_id=str(uuid4()),
        authorization_id=str(uuid4()),
        binding_revision=1,
        expected_authorization_epoch=0,
        content_hash="1" * 64,
        artifact_dependency_closure_hash="2" * 64,
    )


def test_strict_shadow_wire() -> None:
    from dataclasses import replace

    from kineticloop.contracts.commands import StartSession, parse_command
    from kineticloop.contracts.shadow import ShadowContractError, ShadowEvaluationArtifact
    from kineticloop.contracts.shadow import TestOnlyAuthorizationScope as Scope
    from kineticloop.protocol.execution import command_digest

    artifact = ShadowEvaluationArtifact(str(uuid4()), str(uuid4()))
    payload = artifact.to_payload()
    assert ShadowEvaluationArtifact.from_payload(payload) == artifact
    assert ShadowEvaluationArtifact.from_json(artifact.to_json()) == artifact
    assert payload["mode"] == "shadow_only" and payload["execution_disposition"] == "not_executable"
    for field in (
        "s38_live_head_target",
        "s42_production_issuance_target",
        "s45_execution_binding_target",
        "live_planning_intent_success_target",
    ):
        assert payload[field] is None
        with pytest.raises(TypeError):
            ShadowEvaluationArtifact(
                artifact.artifact_id, artifact.evaluation_run_id, **{field: str(uuid4())}
            )
        invalid_targets: tuple[Any, ...] = (str(uuid4()), False, 0, {}, [])
        for value in invalid_targets:
            bad = {**payload, field: value}
            target_parsers: tuple[tuple[Any, Any], ...] = (
                (ShadowEvaluationArtifact.from_payload, bad),
                (ShadowEvaluationArtifact.from_json, json.dumps(bad)),
            )
            for parse, source in target_parsers:
                with pytest.raises(ShadowContractError):
                    parse(source)
    for field in payload:
        bad = dict(payload)
        bad.pop(field)
        with pytest.raises(ShadowContractError):
            ShadowEvaluationArtifact.from_payload(bad)
        duplicate = (
            artifact.to_json()[:-1]
            + ","
            + json.dumps(field)
            + ":"
            + json.dumps(payload[field])
            + "}"
        )
        with pytest.raises(ShadowContractError, match="duplicate"):
            ShadowEvaluationArtifact.from_json(duplicate)
    for field in ("schema", "mode", "execution_disposition", "persistence_boundary", "extra"):
        constant_parsers: tuple[tuple[Any, Any], ...] = (
            (ShadowEvaluationArtifact.from_payload, {**payload, field: "unknown"}),
            (ShadowEvaluationArtifact.from_json, json.dumps({**payload, field: "unknown"})),
        )
        for parse, source in constant_parsers:
            with pytest.raises(ShadowContractError):
                parse(source)
    auth = identity()
    scope = Scope(auth.actor, str(auth.subject_id), str(auth.policy_id), str(auth.environment_id))
    assert Scope.from_json(scope.to_json()) == scope
    for role in (ActorRole.EVALUATION, ActorRole.SUBJECT, ActorRole.ADMIN):
        with pytest.raises(ValueError):
            replace(scope, actor=RoleIdentity(str(uuid4()), role))
        with pytest.raises(ValueError, match="authenticated TEST"):
            replace(auth, actor=RoleIdentity(str(uuid4()), role))
    with pytest.raises(ValueError, match="canonical TEST database principal"):
        replace(auth, principal="kl_evaluation_subject_1_login")
    for field in ("subject_boundary", "policy_boundary", "environment_boundary"):
        for value in ("production", "evaluation"):
            with pytest.raises(ShadowContractError):
                Scope.from_payload({**scope.to_payload(), field: value})
    for field, value in (
        ("direct_write_allowed", True),
        ("t6_command_owner_guard_required", False),
        ("t7_command_owner_guard_required", False),
    ):
        with pytest.raises(ShadowContractError):
            Scope.from_payload({**scope.to_payload(), field: value})
    command = start_wire(auth)
    auth.require_wire(command)
    for field in ("actor", "subject_id", "policy_id", "environment_id"):
        changes: dict[str, Any] = {
            field: RoleIdentity(str(uuid4()), ActorRole.TEST) if field == "actor" else uuid4()
        }
        altered = replace(auth, **changes)
        with pytest.raises(ValueError, match="authenticated TEST command binding mismatch"):
            altered.require_wire(command)
    raw = command.model_dump(mode="json")
    with pytest.raises(ValueError):
        parse_command(
            json.dumps(
                {
                    **raw,
                    "authorization_scope": {
                        "scope": "shadow_only",
                        "subject_id": raw["subject_id"],
                    },
                }
            )
        )
    with pytest.raises(ValueError, match="authenticated TEST command binding mismatch"):
        auth.require_wire(
            StartSession.model_validate_json(json.dumps({**raw, "request_hash": "f" * 64}))
        )
    production = {
        **raw,
        "actor": {**raw["actor"], "role": "subject", "identity_id": raw["subject_id"]},
        "authorization_scope": {"scope": "production", "subject_id": raw["subject_id"]},
    }
    first: Any = parse_command(json.dumps(production))
    valid: Any = parse_command(json.dumps({**production, "request_hash": command_digest(first)}))
    assert command_digest(valid) == valid.request_hash
    with pytest.raises(ValueError, match="authenticated TEST command binding mismatch"):
        auth.require_wire(valid)
    print(
        "STRICT_WIRE_PU canonical_shadow_hash",
        __import__("hashlib").sha256(artifact.to_json().encode()).hexdigest(),
        "guard_reached=strict_contract/require_wire; no_T7_claim",
    )
