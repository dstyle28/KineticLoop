from __future__ import annotations

import json
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

import kineticloop.db.lifecycle as lifecycle_module
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


def test_destroy_reports_compose_cleanup_failure(tmp_path: Path) -> None:
    root = tmp_path / "abc123" / "KineticLoop"
    failure = subprocess.CalledProcessError(
        1,
        ["docker", "compose", "down"],
        stderr="volume is still in use",
    )
    lifecycle = DatabaseLifecycle(root, runner=Mock(side_effect=failure), environ={})

    with pytest.raises(DatabaseLifecycleError, match="volume is still in use"):
        lifecycle.destroy()


def test_missing_docker_has_actionable_error(tmp_path: Path) -> None:
    root = tmp_path / "abc123" / "KineticLoop"
    root.mkdir(parents=True)
    (root / "compose.yaml").write_text("services: {}\n")
    runner = Mock(side_effect=FileNotFoundError)
    lifecycle = DatabaseLifecycle(root, runner=runner, environ={})

    with pytest.raises(DatabaseLifecycleError, match="Docker with the Compose plugin"):
        lifecycle.validate_compose()


class ReadinessScenario:
    """Virtual clock: socket init accepts, then disappears, then final TCP starts."""

    def __init__(self, *, failures: int | None = 3, hung: bool = False) -> None:
        self.now = 0.0
        self.failures = failures
        self.hung = hung
        self.probes: list[tuple[list[str], float | None]] = []
        self.sql: list[str] = []
        self.premature_sql: list[str] = []
        self.final_ready = False
        self.sleeps: list[float] = []

    def sleep(self, duration: float) -> None:
        self.sleeps.append(duration)
        self.now += duration

    def run(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "pg_isready" in command:
            timeout = kwargs.get("timeout")
            assert timeout is None or isinstance(timeout, (float, int))
            self.probes.append((command, timeout))
            if "--host" not in command:
                return completed("socket init accepts connections")
            assert command[command.index("--host") + 1] == "127.0.0.1"
            assert command[command.index("--port") + 1] == "5432"
            if self.hung:
                assert timeout is not None and timeout > 0
                self.now += timeout
                raise subprocess.TimeoutExpired(command, timeout, output="secret-untrusted-output")
            if timeout is not None and timeout < 0.1:
                self.now += timeout
                raise subprocess.TimeoutExpired(command, timeout)
            self.now += 0.1
            if self.failures is None or len(self.probes) <= self.failures:
                return completed("TCP unavailable during init/stop", returncode=1)
            self.final_ready = True
            return completed("final TCP accepts connections")
        if "psql" in command:
            statement = command[-1]
            self.sql.append(statement)
            assert "--host" not in command and "--port" not in command
            if not self.final_ready:
                self.premature_sql.append(statement)
                raise subprocess.CalledProcessError(
                    2, command, stderr="init stopped: socket .s.PGSQL.5432 missing"
                )
        if command[-3:] == ["port", "postgres", "5432"]:
            return completed("127.0.0.1:49152\n")
        return completed()


def scenario_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: ReadinessScenario,
    module: ModuleType = lifecycle_module,
) -> DatabaseLifecycle:
    root = tmp_path / "owned" / "KineticLoop"
    root.mkdir(parents=True, exist_ok=True)
    (root / "compose.yaml").write_text("services: {}\n")
    monkeypatch.setattr(
        module, "time", SimpleNamespace(monotonic=lambda: scenario.now, sleep=scenario.sleep)
    )
    return module.DatabaseLifecycle(root, runner=scenario.run, environ={
        "COMPOSE_PROJECT_NAME": "foreign", "KINETICLOOP_DB_NAME": "postgres",
    })


def protected_baseline_module() -> ModuleType:
    root = Path(__file__).parents[2]
    spec = spec_from_file_location("readiness_guard", root / "tools/harness/validate_harness.py")
    assert spec is not None and spec.loader is not None
    guard = module_from_spec(spec)
    spec.loader.exec_module(guard)
    source = (root / "src/kineticloop/db/lifecycle.py").read_text()
    for before, after in guard.READINESS_LIFECYCLE_REPLACEMENTS:
        assert source.count(after) == 1
        source = source.replace(after, before, 1)
    import hashlib
    assert hashlib.sha256(source.encode()).hexdigest() == guard.READINESS_LIFECYCLE_BASE_SHA256
    module = ModuleType("kl074_protected_baseline")
    sys.modules[module.__name__] = module
    exec(compile(source, "protected-base/lifecycle.py", "exec"), module.__dict__)
    return module


def test_temporary_socket_old_code_fails_repaired_code_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = protected_baseline_module()
    old = ReadinessScenario()
    lifecycle = scenario_lifecycle(tmp_path, monkeypatch, old, baseline)
    with pytest.raises(baseline.DatabaseLifecycleError, match="socket .* missing"):
        lifecycle.reset(timeout_seconds=3)
    assert len(old.premature_sql) == 1 and not old.final_ready
    assert len(old.probes) == 1 and "--host" not in old.probes[0][0]

    repaired = ReadinessScenario()
    lifecycle = scenario_lifecycle(tmp_path, monkeypatch, repaired)
    lifecycle.reset(timeout_seconds=3)
    assert repaired.final_ready and not repaired.premature_sql
    assert len(repaired.sql) == 2 and len(repaired.probes) == 5


@pytest.mark.parametrize("hung", [False, True])
def test_permanent_tcp_unready_is_bounded_and_executes_zero_sql(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hung: bool,
) -> None:
    scenario = ReadinessScenario(failures=None, hung=hung)
    lifecycle = scenario_lifecycle(tmp_path, monkeypatch, scenario)
    with pytest.raises(DatabaseLifecycleError, match="did not become ready|command timed out") as error:
        lifecycle.reset(timeout_seconds=1.25)
    assert scenario.now == pytest.approx(1.25)
    assert scenario.sql == []
    assert "secret-untrusted-output" not in str(error.value)
    assert all(timeout is not None and 0 < timeout <= 1.25 for _, timeout in scenario.probes)
    assert all(0 <= duration <= 0.5 for duration in scenario.sleeps)


def test_delayed_final_ready_exact_reset_and_socket_sql(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = ReadinessScenario()
    lifecycle = scenario_lifecycle(tmp_path, monkeypatch, scenario)
    connection = lifecycle.reset(timeout_seconds=3)
    name = DatabaseNamespace.for_worktree(lifecycle.root).database_name
    assert scenario.sql == [
        f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE);',
        f'CREATE DATABASE "{name}" OWNER "kineticloop";',
    ]
    assert connection.database_name == name
    assert scenario.probes[-1][0][-1] == name
    assert [timeout for _, timeout in scenario.probes[:-1]] == pytest.approx([3, 2.4, 1.8, 1.2])
    assert not scenario.premature_sql


@pytest.mark.parametrize("statement", ["DROP", "CREATE"])
def test_sql_failure_preserves_redacted_error_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, statement: str,
) -> None:
    scenario = ReadinessScenario(failures=0)
    lifecycle = scenario_lifecycle(tmp_path, monkeypatch, scenario)
    original = scenario.run

    def fail(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        result = original(command, **kwargs)
        if "psql" in command and command[-1].startswith(statement):
            raise subprocess.CalledProcessError(
                2, command, stderr=f"{statement} failed: permission denied kineticloop-local-only"
            )
        return result

    lifecycle._runner = fail
    with pytest.raises(DatabaseLifecycleError, match=f"{statement} failed: permission denied") as error:
        lifecycle.reset(timeout_seconds=3)
    assert "kineticloop-local-only" not in str(error.value)
    assert len(scenario.sql) == (1 if statement == "DROP" else 2)
    assert sum(sql.startswith(statement) for sql in scenario.sql) == 1
