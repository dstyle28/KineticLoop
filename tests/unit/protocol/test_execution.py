from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import fields, replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from kineticloop.contracts.commands import CommitBundle, PublishManifest, StartSession
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.protocol.execution import ExecutionIdentity, PublishReady, command_digest

ROOT = Path(__file__).resolve().parents[3]
TX_COMMAND = [
    "uv",
    "run",
    "pytest",
    "-q",
    "tests/db/test_transaction_interfaces.py",
    "tests/unit/persistence/test_transactions.py",
]


def execution_namespace(
    root: Path, short: str, label: str, *, worktree_digest: str | None = None
) -> DatabaseNamespace:
    if (
        label not in {"exec", "tx", "plan", "ledger"}
        or re.fullmatch(r"[0-9a-f]{7,12}", short) is None
    ):
        raise ValueError("invalid execution namespace SHA/suite")
    actual = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    if worktree_digest is not None and (
        re.fullmatch(r"[0-9a-f]{12}", worktree_digest) is None or worktree_digest != actual
    ):
        raise ValueError("invalid execution worktree digest")
    return DatabaseNamespace(
        f"kineticloop-kl019-{label}-{short}-{actual}", f"kineticloop_kl019_{label}_{short}_{actual}"
    )


def run_transaction_regressions(root: Path = ROOT) -> int:
    short = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True
    ).strip()
    namespace = execution_namespace(root, short, "tx")
    if (
        os.environ.get("KINETICLOOP_KL022_COMPOSE_PROJECT") != namespace.project_name
        or os.environ.get("KINETICLOOP_KL022_DATABASE") != namespace.database_name
    ):
        raise ValueError("transaction fixture target does not equal tested SHA/worktree namespace")
    return subprocess.run(TX_COMMAND, cwd=root, check=False).returncode


def load(path: str) -> Any:
    spec = spec_from_file_location("kl019_probe_" + Path(path).stem, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_identity_and_wire_scope() -> None:
    subject, policy, environment = uuid4(), uuid4(), uuid4()
    actor = RoleIdentity(str(uuid4()), ActorRole.TEST)
    identity = ExecutionIdentity(actor, subject, policy, environment, "kl_test_subject_1_login")
    assert identity.key.startswith("test:")
    for role in (ActorRole.SUBJECT, ActorRole.ADMIN, ActorRole.EVALUATION):
        with pytest.raises(ValueError):
            replace(identity, actor=RoleIdentity(str(uuid4()), role))
    with pytest.raises(ValueError):
        replace(identity, principal="kl_evaluation_subject_1_login")
    assert "authorization_scope" not in {f.name for f in fields(PublishReady)}
    # Frozen T3 wire still cannot accept TEST_ONLY, even with a valid TEST actor.
    payload = {
        "schema_version": "kineticloop-command-v1",
        "command_kind": "PublishManifest",
        "boundary": "T3",
        "command_id": str(uuid4()),
        "actor": {
            "schema": "kineticloop-role-identity-v1",
            "identity_id": actor.identity_id,
            "role": "test",
        },
        "idempotency_key": "publish",
        "request_hash": "a" * 64,
        "subject_id": str(subject),
        "explicit_scope": None,
        "authorization_scope": {
            "scope": "test_only",
            "subject_id": str(subject),
            "policy_id": str(policy),
            "environment_id": str(environment),
            "subject_boundary": "isolated_non_production",
            "policy_boundary": "isolated_non_production",
            "environment_boundary": "isolated_non_production",
            "direct_write_allowed": False,
            "command_owner_guard_required": True,
        },
        "build_id": str(uuid4()),
        "sealed_factset_id": str(uuid4()),
        "expected_input_frontier_hash": "a" * 64,
        "expected_authorization_epoch": 0,
        "program_revision_id": str(uuid4()),
        "policy_id": str(policy),
        "dependency_basis_hash": "a" * 64,
        "artifact_dependency_closure_hash": "a" * 64,
    }
    with pytest.raises(ValidationError, match="TEST_ONLY is admitted only"):
        PublishManifest.model_validate_json(json.dumps(payload))
    for model, kind, extra in (
        (
            CommitBundle,
            "CommitBundle",
            {
                **{
                    name: str(uuid4())
                    for name in (
                        "intent_id",
                        "attempt_id",
                        "manifest_id",
                        "validation_id",
                        "execution_basis_event_id",
                        "commit_identity",
                    )
                },
                "expected_generation": 1,
                "expected_authorization_epoch": 0,
                "expected_request_revision": 1,
                "expected_owner_id": actor.identity_id,
                "expected_fence": 1,
                "policy_id": str(policy),
                "artifact_dependency_closure_hash": "a" * 64,
                "result_fingerprint": "b" * 64,
            },
        ),
        (
            StartSession,
            "StartSession",
            {
                **{
                    name: str(uuid4())
                    for name in ("session_id", "prescription_id", "authorization_id")
                },
                "action_key": "start",
                "binding_revision": 1,
                "expected_authorization_epoch": 0,
                "content_hash": "a" * 64,
                "artifact_dependency_closure_hash": "b" * 64,
            },
        ),
    ):
        body: dict[str, Any] = {
            key: value
            for key, value in payload.items()
            if key
            in {
                "schema_version",
                "command_id",
                "actor",
                "idempotency_key",
                "request_hash",
                "subject_id",
                "explicit_scope",
                "authorization_scope",
            }
        }
        body.update(command_kind=kind, boundary="T6" if kind == "CommitBundle" else "T7", **extra)

        def signed(value: dict[str, Any]) -> Any:
            parsed = model.model_validate_json(json.dumps(value))
            value["request_hash"] = command_digest(parsed)
            return model.model_validate_json(json.dumps(value))

        valid = signed(body)
        identity.require_wire(valid)
        for mismatch in (
            "actor",
            "subject",
            "policy",
            "environment",
            "hash",
            "extra",
            "evaluation",
            "execution",
            "shadow",
        ):
            wrong = json.loads(json.dumps(body))
            if mismatch == "actor":
                wrong["actor"]["identity_id"] = str(uuid4())
            elif mismatch == "subject":
                wrong["subject_id"] = wrong["authorization_scope"]["subject_id"] = str(uuid4())
            elif mismatch in {"policy", "environment"}:
                wrong["authorization_scope"][mismatch + "_id"] = str(uuid4())
                if mismatch == "policy" and kind == "CommitBundle":
                    wrong["policy_id"] = wrong["authorization_scope"]["policy_id"]
            elif mismatch == "hash":
                wrong["request_hash"] = "f" * 64
            elif mismatch == "extra":
                wrong["mutation"] = "arbitrary authority"
            elif mismatch == "evaluation":
                wrong["actor"]["role"] = "evaluation"
            else:
                wrong["authorization_scope"]["scope"] = mismatch
            with pytest.raises((ValueError, ValidationError)):
                identity.require_wire(
                    model.model_validate_json(json.dumps(wrong))
                    if mismatch == "hash"
                    else signed(wrong)
                )
    # Public methods contain no mutation, SQL, aggregate-lock or owner arguments.
    import inspect

    from kineticloop.persistence.protocol_execution import ProtocolExecutionService

    assert list(inspect.signature(ProtocolExecutionService.publish).parameters) == [
        "self",
        "request",
    ]
    assert list(inspect.signature(ProtocolExecutionService.start).parameters) == ["self", "command"]
    assert list(inspect.signature(ProtocolExecutionService.commit).parameters) == [
        "self",
        "command",
        "requested_valid_until",
    ]


def test_all_fixture_namespaces_fail_before_reset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    short = "abcdef1"
    targets = [
        execution_namespace(ROOT, short, label) for label in ("exec", "tx", "plan", "ledger")
    ]
    assert len(set(targets)) == 4
    assert execution_namespace(tmp_path, short, "tx") != targets[1]
    for bad in ("", "abc123", "abcdef1234567", "ABCDEF1", "../foo1"):
        with pytest.raises(ValueError):
            execution_namespace(ROOT, bad, "exec")
    for bad in ("", "abcd", "A" * 12, "a" * 12):
        with pytest.raises(ValueError):
            execution_namespace(ROOT, short, "tx", worktree_digest=bad)
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: short)

    def launched(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", launched)
    tx = targets[1]
    for var, value in (
        ("KINETICLOOP_KL022_COMPOSE_PROJECT", tx.project_name),
        ("KINETICLOOP_KL022_DATABASE", tx.database_name),
    ):
        monkeypatch.setenv(var, value)
    for var in ("KINETICLOOP_KL022_COMPOSE_PROJECT", "KINETICLOOP_KL022_DATABASE"):
        valid = os.environ[var]
        for bad in ("", "arbitrary", "kineticloop-kl022-08e743c", valid + "x"):
            monkeypatch.setenv(var, bad)
            with pytest.raises(ValueError):
                run_transaction_regressions()
            assert calls == []
        monkeypatch.setenv(var, valid)
    assert run_transaction_regressions() == 0
    assert calls[0][0][0] == TX_COMMAND
    calls.clear()

    # Actual fixture and actual lifecycle reset/destroy use only the selected names.
    # This runner proof is deliberately separate from all real required regressions.
    class Stop(RuntimeError):
        pass

    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kw["env"]["KINETICLOOP_DB_NAME"]))
        return subprocess.CompletedProcess(cmd, 0, "127.0.0.1:5432\n", "")

    class InstrumentedLifecycle(DatabaseLifecycle):
        def __init__(self, root: Path) -> None:
            super().__init__(root, runner=runner)

    def bootstrap(lifecycle: DatabaseLifecycle) -> None:
        actual = lifecycle.reset()
        assert actual.database_name == lifecycle.namespace.database_name
        raise Stop

    for path, selector, helper, label in (
        ("tests/db/test_protocol_execution.py", None, "execution_namespace", "exec"),
        (
            "tests/db/test_planning.py",
            "KINETICLOOP_KL024_FIXTURE_OWNER",
            "_planning_namespace",
            "plan",
        ),
        (
            "tests/db/test_call_ledger.py",
            "KINETICLOOP_KL025_FIXTURE_OWNER",
            "_ledger_namespace",
            "ledger",
        ),
        ("tests/db/test_transaction_interfaces.py", None, None, "tx"),
    ):
        module = load(path)
        with monkeypatch.context() as patch:
            patch.setattr(module, "DatabaseLifecycle", InstrumentedLifecycle)
            patch.setattr(module._MIGRATIONS, "bootstrap_two_phase", bootstrap)
            if selector:
                for bad in ("", "KL-024", "KL-055", "kl-019", "KL-019 ", "../KL-019"):
                    patch.setenv(selector, bad)
                    with pytest.raises(ValueError):
                        next(module.database_urls.__wrapped__())
                    assert calls == []
                patch.setenv(selector, "KL-019")
                for bad in ("", "ABCDEF1", "abcdef", "abcdef1234567"):
                    patch.setattr(
                        module.subprocess, "check_output", lambda *a, value=bad, **kw: value
                    )
                    with pytest.raises(ValueError):
                        next(module.database_urls.__wrapped__())
                    assert calls == []
                patch.setattr(module.subprocess, "check_output", lambda *a, **kw: short)
                assert helper is not None
                assert getattr(module, helper)(short) == execution_namespace(ROOT, short, label)
            with pytest.raises(Stop):
                next(module.database_urls.__wrapped__())
            expected = execution_namespace(ROOT, short, label)
            assert calls
            assert all(
                cmd[cmd.index("--project-name") + 1] == expected.project_name
                and db == expected.database_name
                for cmd, db in calls
            )
            sqls = [cmd[-1] for cmd, db in calls if "psql" in cmd]
            assert any(
                f'"{expected.database_name}"' in sql and sql.startswith("DROP DATABASE")
                for sql in sqls
            )
            assert calls[-1][0][-3:] == ["down", "--volumes", "--remove-orphans"]
            calls.clear()


if __name__ == "__main__":
    if sys.argv[1:] != ["--run-transaction-owner-regressions"]:
        raise SystemExit("only the exact owned transaction regression launcher is supported")
    raise SystemExit(run_transaction_regressions())
