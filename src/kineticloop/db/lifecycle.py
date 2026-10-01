"""Worktree-isolated PostgreSQL lifecycle driven through Docker Compose."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

from kineticloop.config.secrets import SecretValue
from kineticloop.security.redaction import REDACTED, Redactor

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_SAFE_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


class DatabaseLifecycleError(RuntimeError):
    """Raised when the local database lifecycle cannot complete safely."""


@dataclass(frozen=True)
class DatabaseNamespace:
    """Names derived from a physical worktree path."""

    project_name: str
    database_name: str

    @classmethod
    def for_worktree(cls, worktree_root: Path) -> DatabaseNamespace:
        resolved = worktree_root.resolve()
        digest = hashlib.sha256(os.fsencode(resolved)).hexdigest()[:12]
        parent = re.sub(r"[^a-z0-9]+", "_", resolved.parent.name.lower()).strip("_")
        label = parent[:20] or "worktree"
        project_name = f"kl_{label}_{digest}"
        database_name = f"{project_name}_test"
        if not _SAFE_IDENTIFIER.fullmatch(project_name):
            raise DatabaseLifecycleError(f"unsafe Compose project name: {project_name}")
        if not _SAFE_IDENTIFIER.fullmatch(database_name):
            raise DatabaseLifecycleError(f"unsafe PostgreSQL database name: {database_name}")
        return cls(project_name=project_name, database_name=database_name)


@dataclass(frozen=True)
class DatabaseConnection:
    """Connection details for the reset worktree database."""

    project_name: str
    database_name: str
    host: str
    port: int
    user: str
    password: SecretValue | str

    def __post_init__(self) -> None:
        if type(self.host) is not str:
            raise TypeError("database host must be a string")
        decoded_host = unquote(self.host)
        if decoded_host != self.host:
            raise ValueError("database host must not be percent-encoded")
        if not self.host or any(character.isspace() for character in self.host):
            raise ValueError("database host must be host-only")
        if any(character in self.host for character in "@/?#[]"):
            raise ValueError("database host must be host-only")
        if ":" in self.host:
            try:
                ipaddress.ip_address(self.host)
            except ValueError as error:
                raise ValueError("database host must be host-only") from error
        elif _SAFE_HOSTNAME.fullmatch(self.host) is None:
            raise ValueError("database host must be host-only")
        if type(self.port) is not int:
            raise TypeError("database port must be an integer")
        if not 1 <= self.port <= 65535:
            raise ValueError("database port must be between 1 and 65535")
        if isinstance(self.password, str):
            object.__setattr__(self, "password", SecretValue(self.password))

    @property
    def url(self) -> str:
        encoded_user = quote(self.user, safe="")
        password = self.password
        assert isinstance(password, SecretValue)
        encoded_password = quote(password.reveal(), safe="")
        url_host = f"[{self.host}]" if ":" in self.host else self.host
        return (
            f"postgresql://{encoded_user}:{encoded_password}@{url_host}:{self.port}/"
            f"{self.database_name}"
        )

    @property
    def redacted_url(self) -> str:
        password = self.password
        assert isinstance(password, SecretValue)
        redactor = Redactor((self.user, password))
        host = redactor.redact(self.host)
        database_name = redactor.redact(self.database_name)
        url_host = f"[{host}]" if ":" in str(host) else host
        return f"postgresql://{REDACTED}@{url_host}:{self.port}/{database_name}"

    def diagnostic_mapping(self) -> dict[str, str | int]:
        password = self.password
        assert isinstance(password, SecretValue)
        redactor = Redactor((self.user, password))
        return {
            "project_name": str(redactor.redact(self.project_name)),
            "database_name": str(redactor.redact(self.database_name)),
            "host": str(redactor.redact(self.host)),
            "port": self.port,
            "url": self.redacted_url,
        }

    def as_json(self) -> str:
        return json.dumps(self.diagnostic_mapping(), sort_keys=True)

    def __str__(self) -> str:
        return self.as_json()

    def __repr__(self) -> str:
        return f"DatabaseConnection({self.as_json()})"


class DatabaseLifecycle:
    """Manage only the PostgreSQL instance assigned to one worktree."""

    def __init__(
        self,
        worktree_root: Path,
        *,
        runner: CommandRunner = subprocess.run,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.root = worktree_root.resolve()
        self.compose_file = self.root / "compose.yaml"
        self.namespace = DatabaseNamespace.for_worktree(self.root)
        self._runner = runner
        self._base_environ = dict(os.environ if environ is None else environ)
        self.user = self._base_environ.get("KINETICLOOP_DB_USER", "kineticloop")
        self.password = SecretValue(
            self._base_environ.get("KINETICLOOP_DB_PASSWORD", "kineticloop-local-only")
        )
        if not _SAFE_IDENTIFIER.fullmatch(self.user):
            raise DatabaseLifecycleError("KINETICLOOP_DB_USER must be a safe SQL identifier")

    @property
    def environment(self) -> dict[str, str]:
        env = dict(self._base_environ)
        env.update(
            {
                "COMPOSE_PROJECT_NAME": self.namespace.project_name,
                "KINETICLOOP_DB_NAME": self.namespace.database_name,
                "KINETICLOOP_DB_USER": self.user,
                "KINETICLOOP_DB_PASSWORD": self.password.reveal(),
            }
        )
        return env

    def compose_command(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--project-name",
            self.namespace.project_name,
            "--file",
            str(self.compose_file),
            *args,
        ]

    def _run(
        self,
        command: Sequence[str],
        *,
        check: bool = True,
        timeout_seconds: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(
                list(command),
                cwd=self.root,
                env=self.environment,
                check=check,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            raise DatabaseLifecycleError("database readiness command timed out") from None
        except FileNotFoundError as error:
            raise DatabaseLifecycleError(
                "Docker with the Compose plugin is required for the local test database."
            ) from error
        except subprocess.CalledProcessError as error:
            details = Redactor((self.user, self.password)).exception_diagnostic(error)
            raise DatabaseLifecycleError(f"database command failed: {details}") from None

    def validate_compose(self) -> None:
        if not self.compose_file.is_file():
            raise DatabaseLifecycleError(f"missing Compose file: {self.compose_file}")
        self._run(self.compose_command("config", "--quiet"))

    def start(self, *, timeout_seconds: float = 60.0) -> None:
        self.validate_compose()
        self._run(self.compose_command("up", "--detach", "postgres"))
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            result = self._run(
                self.compose_command(
                    "exec",
                    "--no-TTY",
                    "postgres",
                    "pg_isready",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5432",
                    "--username",
                    self.user,
                    "--dbname",
                    "postgres",
                ),
                check=False,
                timeout_seconds=remaining,
            )
            if result.returncode == 0:
                return
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
        raise DatabaseLifecycleError(
            f"PostgreSQL did not become ready within {timeout_seconds:g} seconds"
        )

    def _psql(self, database: str, sql: str) -> subprocess.CompletedProcess[str]:
        if not _SAFE_IDENTIFIER.fullmatch(database):
            raise DatabaseLifecycleError(f"unsafe PostgreSQL database name: {database}")
        return self._run(
            self.compose_command(
                "exec",
                "--no-TTY",
                "postgres",
                "psql",
                "--username",
                self.user,
                "--dbname",
                database,
                "--set",
                "ON_ERROR_STOP=1",
                "--tuples-only",
                "--no-align",
                "--command",
                sql,
            )
        )

    def execute_sql(self, sql: str) -> str:
        return self._psql(self.namespace.database_name, sql).stdout.strip()

    def reset(self, *, timeout_seconds: float = 60.0) -> DatabaseConnection:
        self.start(timeout_seconds=timeout_seconds)
        quoted_database = f'"{self.namespace.database_name}"'
        quoted_user = f'"{self.user}"'
        self._psql(
            "postgres",
            f"DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE);",
        )
        self._psql(
            "postgres",
            f"CREATE DATABASE {quoted_database} OWNER {quoted_user};",
        )
        ready = self._run(
            self.compose_command(
                "exec",
                "--no-TTY",
                "postgres",
                "pg_isready",
                "--host",
                "127.0.0.1",
                "--port",
                "5432",
                "--username",
                self.user,
                "--dbname",
                self.namespace.database_name,
            ),
            check=False,
            timeout_seconds=timeout_seconds,
        )
        if ready.returncode != 0:
            raise DatabaseLifecycleError("reset database failed its readiness probe")
        return self.connection()

    def connection(self) -> DatabaseConnection:
        result = self._run(self.compose_command("port", "postgres", "5432"))
        endpoint = result.stdout.strip().rsplit("\n", maxsplit=1)[-1]
        host, separator, raw_port = endpoint.rpartition(":")
        if not separator or not raw_port.isdigit():
            safe_endpoint = Redactor((self.user, self.password)).redact(endpoint)
            raise DatabaseLifecycleError(f"unexpected Docker port output: {safe_endpoint!r}")
        try:
            return DatabaseConnection(
                project_name=self.namespace.project_name,
                database_name=self.namespace.database_name,
                host=host.strip("[]") or "127.0.0.1",
                port=int(raw_port),
                user=self.user,
                password=self.password,
            )
        except (TypeError, ValueError):
            safe_endpoint = Redactor((self.user, self.password)).redact(endpoint)
            raise DatabaseLifecycleError(
                f"unexpected Docker port output: {safe_endpoint!r}"
            ) from None

    def destroy(self) -> None:
        """Remove only this worktree's containers, network, and named volume."""
        self._run(self.compose_command("down", "--volumes", "--remove-orphans"))
