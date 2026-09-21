from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from kineticloop.db.lifecycle import (
    DatabaseLifecycle,
    DatabaseLifecycleError,
    DatabaseNamespace,
)


def completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_namespace_is_stable_and_worktree_specific(tmp_path: Path) -> None:
    first_root = tmp_path / "worktrees" / "one" / "KineticLoop"
    second_root = tmp_path / "worktrees" / "two" / "KineticLoop"

    first = DatabaseNamespace.for_worktree(first_root)
    repeated = DatabaseNamespace.for_worktree(first_root)
    second = DatabaseNamespace.for_worktree(second_root)

    assert first == repeated
    assert first != second
    assert first.project_name.startswith("kl_one_")
    assert first.database_name == f"{first.project_name}_test"
    assert len(first.database_name) <= 63


def test_compose_namespace_cannot_be_overridden_by_ambient_environment(tmp_path: Path) -> None:
    root = tmp_path / "isolated" / "KineticLoop"
    lifecycle = DatabaseLifecycle(
        root,
        runner=Mock(),
        environ={"COMPOSE_PROJECT_NAME": "shared", "KINETICLOOP_DB_NAME": "shared"},
    )

    assert lifecycle.environment["COMPOSE_PROJECT_NAME"] == lifecycle.namespace.project_name
    assert lifecycle.environment["KINETICLOOP_DB_NAME"] == lifecycle.namespace.database_name
    assert "shared" not in lifecycle.compose_command("config")
    assert lifecycle.namespace.project_name in lifecycle.compose_command("config")


def test_reset_is_repeatable_and_targets_only_derived_database(tmp_path: Path) -> None:
    root = tmp_path / "abc123" / "KineticLoop"
    root.mkdir(parents=True)
    (root / "compose.yaml").write_text("services: {}\n")
    runner = Mock()

    def respond(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command[-3:] == ["port", "postgres", "5432"]:
            return completed("127.0.0.1:49152\n")
        return completed()

    runner.side_effect = respond
    lifecycle = DatabaseLifecycle(root, runner=runner, environ={})

    first = lifecycle.reset(timeout_seconds=0.1)
    second = lifecycle.reset(timeout_seconds=0.1)

    assert first == second
    assert json.loads(first.as_json())["database_name"] == lifecycle.namespace.database_name
    commands = [call.args[0] for call in runner.call_args_list]
    sql = [command[-1] for command in commands if "--command" in command]
    assert sql.count(
        f'DROP DATABASE IF EXISTS "{lifecycle.namespace.database_name}" WITH (FORCE);'
    ) == 2
    assert sql.count(
        f'CREATE DATABASE "{lifecycle.namespace.database_name}" OWNER "kineticloop";'
    ) == 2
    assert all("shared" not in statement for statement in sql)


def test_destroy_is_scoped_to_the_derived_compose_project(tmp_path: Path) -> None:
    root = tmp_path / "abc123" / "KineticLoop"
    runner = Mock(return_value=completed())
    lifecycle = DatabaseLifecycle(root, runner=runner, environ={})

    lifecycle.destroy()

    command = runner.call_args.args[0]
    assert command == lifecycle.compose_command("down", "--volumes", "--remove-orphans")
    assert lifecycle.namespace.project_name in command


def test_missing_docker_has_actionable_error(tmp_path: Path) -> None:
    root = tmp_path / "abc123" / "KineticLoop"
    root.mkdir(parents=True)
    (root / "compose.yaml").write_text("services: {}\n")
    runner = Mock(side_effect=FileNotFoundError)
    lifecycle = DatabaseLifecycle(root, runner=runner, environ={})

    with pytest.raises(DatabaseLifecycleError, match="Docker with the Compose plugin"):
        lifecycle.validate_compose()
