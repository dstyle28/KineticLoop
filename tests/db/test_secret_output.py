from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import quote

import pytest

from kineticloop.db.cli import main
from kineticloop.db.lifecycle import DatabaseConnection, DatabaseLifecycle, DatabaseLifecycleError

USER = "synthetic_db_user"
PASSWORD = "SYNTHETIC db:p@ss/word? NOT A CREDENTIAL"


class UnsafePort(int):
    def __format__(self, format_spec: str) -> str:
        del format_spec
        return "5432?token=PORT_FORMAT_SECRET"


def _connection() -> DatabaseConnection:
    return DatabaseConnection(
        project_name="kl_synthetic_deadbeef0000",
        database_name="kl_synthetic_deadbeef0000_test",
        host="127.0.0.1",
        port=49152,
        user=USER,
        password=PASSWORD,
    )


def _assert_credential_free(rendered: str) -> None:
    assert USER not in rendered
    assert PASSWORD not in rendered
    assert quote(USER, safe="") not in rendered
    assert quote(PASSWORD, safe="") not in rendered
    assert "127.0.0.1" in rendered
    assert "49152" in rendered
    assert "kl_synthetic_deadbeef0000_test" in rendered


def test_connection_default_diagnostics_are_credential_free() -> None:
    connection = _connection()
    for rendered in (str(connection), repr(connection), connection.as_json()):
        _assert_credential_free(rendered)
    assert quote(PASSWORD, safe="") in connection.url
    assert USER in connection.url
    assert json.loads(connection.as_json())["url"].startswith("postgresql://[REDACTED]@")

    with pytest.raises(TypeError, match="port must be an integer"):
        DatabaseConnection(
            project_name=connection.project_name,
            database_name=connection.database_name,
            host=connection.host,
            port="5432?token=PORT_STRING_SECRET",  # type: ignore[arg-type]
            user=USER,
            password=PASSWORD,
        )
    for unsafe_host in (
        "alice:hunter2@db.invalid",
        "alice%3Ahunter2%40db.invalid",
    ):
        with pytest.raises(ValueError, match="database host") as caught:
            DatabaseConnection(
                project_name=connection.project_name,
                database_name=connection.database_name,
                host=unsafe_host,
                port=5432,
                user=USER,
                password=PASSWORD,
            )
        assert "alice" not in str(caught.value)
        assert "hunter2" not in str(caught.value)

    ipv6_connection = DatabaseConnection(
        project_name=connection.project_name,
        database_name=connection.database_name,
        host="::1",
        port=5432,
        user=USER,
        password=PASSWORD,
    )
    assert "@[::1]:5432/" in ipv6_connection.url
    assert "@[::1]:5432/" in ipv6_connection.redacted_url
    with pytest.raises(TypeError, match="port must be an integer"):
        DatabaseConnection(
            project_name=connection.project_name,
            database_name=connection.database_name,
            host=connection.host,
            port=UnsafePort(5432),
            user=USER,
            password=PASSWORD,
        )


@pytest.mark.parametrize("as_json", [False, True])
def test_db_reset_cli_outputs_credential_free_diagnostics(
    as_json: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lifecycle = Mock()
    lifecycle.reset.return_value = _connection()
    arguments = ["db-reset", *(["--json"] if as_json else [])]

    with patch("kineticloop.db.cli.DatabaseLifecycle", return_value=lifecycle):
        assert main(arguments) == 0

    _assert_credential_free(capsys.readouterr().out)


def test_lifecycle_subprocess_and_cli_errors_are_redacted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "synthetic" / "KineticLoop"
    root.mkdir(parents=True)
    (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    encoded = quote(PASSWORD, safe="")
    failure = subprocess.CalledProcessError(
        1,
        ["docker", "compose", f"--username={USER}", f"--password={PASSWORD}"],
        output=f"DATABASE_URL=postgresql://{USER}:{encoded}@db.invalid/test?token={PASSWORD}",
        stderr=(
            f'nested password=[["first"],"{PASSWORD}"]\n'
            "cookie=session-value; SYNTHETIC_COOKIE_TAIL_NOT_A_CREDENTIAL"
        ),
    )
    lifecycle = DatabaseLifecycle(
        root,
        runner=Mock(side_effect=failure),
        environ={"KINETICLOOP_DB_USER": USER, "KINETICLOOP_DB_PASSWORD": PASSWORD},
    )

    with pytest.raises(DatabaseLifecycleError) as caught:
        lifecycle.validate_compose()
    rendered_error = str(caught.value)
    assert USER not in rendered_error
    assert PASSWORD not in rendered_error
    assert encoded not in rendered_error
    assert "SYNTHETIC_COOKIE_TAIL_NOT_A_CREDENTIAL" not in rendered_error
    assert "database command failed" in rendered_error

    with patch("kineticloop.db.cli.DatabaseLifecycle", return_value=lifecycle):
        with pytest.raises(SystemExit) as exit_info:
            main(["db-reset"])
    assert exit_info.value.code == 1
    cli_error = capsys.readouterr().err
    assert USER not in cli_error
    assert PASSWORD not in cli_error
    assert encoded not in cli_error
    assert "SYNTHETIC_COOKIE_TAIL_NOT_A_CREDENTIAL" not in cli_error
    assert "db-reset: database command failed" in cli_error


@pytest.mark.parametrize(
    "argument,secret",
    [
        ("--password=SYNTHETIC_CLI_RAW_NOT_A_CREDENTIAL", "SYNTHETIC_CLI_RAW_NOT_A_CREDENTIAL"),
        (
            "--database-url=postgresql%3A%2F%2Falice%3Ahunter2%40db.invalid%2Fdb",
            "alice%3Ahunter2",
        ),
        ("--timeout=password=SYNTHETIC_TIMEOUT_SECRET", "SYNTHETIC_TIMEOUT_SECRET"),
        ("--timeout=password%3DSYNTHETIC_TIMEOUT_ENCODED", "SYNTHETIC_TIMEOUT_ENCODED"),
        ("--timeout=token%253DSYNTHETIC_TIMEOUT_DOUBLE", "SYNTHETIC_TIMEOUT_DOUBLE"),
        (
            "--timeout=https%3A%2F%2Falice%3Ahunter2%40db.invalid%2Fdb%3Ftoken%3Dquerysecret",
            "hunter2",
        ),
        ("--pass%77ord=ENCODED_KEY_SECRET", "ENCODED_KEY_SECRET"),
        (
            "--timeout=%70%61%73%73%77%6F%72%64%3D%53%59%4E%54%48%45%54%49%43",
            "%53%59%4E%54%48%45%54%49%43",
        ),
        (
            "--password=FIRST%0AENCODED_ARGPARSE_TAIL",
            "ENCODED_ARGPARSE_TAIL",
        ),
        ("--password;ARGPARSE_SEMICOLON_VALUE", "ARGPARSE_SEMICOLON_VALUE"),
        (
            "--password%3BARGPARSE_ENCODED_SEMICOLON_VALUE",
            "ARGPARSE_ENCODED_SEMICOLON_VALUE",
        ),
        (
            "--authorization;AWS4-HMAC-SHA256;Signature=ARGPARSE_AUTH_SEMICOLON_VALUE",
            "ARGPARSE_AUTH_SEMICOLON_VALUE",
        ),
    ],
)
def test_db_reset_argument_errors_are_credential_free(
    argument: str,
    secret: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["db-reset", argument])
    assert exit_info.value.code == 2
    stderr = capsys.readouterr().err
    assert secret not in stderr
    assert "[REDACTED]" in stderr


@pytest.mark.parametrize(
    "arguments,secret",
    [
        (["--pass%77ord", "SYNTHETIC_SEPARATE_SECRET"], "SYNTHETIC_SEPARATE_SECRET"),
        (
            ["--authorization", "B%65arer", "SYNTHETIC_AUTH_SECRET"],
            "SYNTHETIC_AUTH_SECRET",
        ),
    ],
)
def test_db_reset_split_argument_errors_are_credential_free(
    arguments: list[str],
    secret: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["db-reset", *arguments])
    assert exit_info.value.code == 2
    stderr = capsys.readouterr().err
    assert secret not in stderr
    assert "[REDACTED]" in stderr


@pytest.mark.parametrize("argument", ["--timeout=%36%30", "--j%73on"])
def test_db_reset_never_executes_percent_decoded_parser_input(
    argument: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch("kineticloop.db.cli.DatabaseLifecycle") as lifecycle_type:
        with pytest.raises(SystemExit) as exit_info:
            main(["db-reset", argument])

    assert exit_info.value.code == 2
    lifecycle_type.assert_not_called()
    assert "error:" in capsys.readouterr().err


def test_db_reset_arbitrary_authorization_diagnostic_is_credential_free(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "ARGPARSE_NEGOTIATE_VALUE"

    with pytest.raises(SystemExit) as exit_info:
        main(["db-reset", "Authorization", "Negotiate", secret])

    assert exit_info.value.code == 2
    stderr = capsys.readouterr().err
    assert secret not in stderr
    assert "[REDACTED]" in stderr


@pytest.mark.parametrize(
    "endpoint,secret",
    [
        ("alice:hunter2@db.invalid:notaport", "hunter2"),
        ("alice%3Ahunter2%40db.invalid:notaport", "hunter2"),
        ("alice:hunter2@db.invalid:5432", "hunter2"),
        ("alice%3Ahunter2%40db.invalid:5432", "hunter2"),
        ("alice:alpha/bravo@db.invalid:notaport", "alpha"),
        ("alice:alpha bravo@db.invalid:notaport", "alpha"),
        ("notice@example.com alice:hunter2@db.invalid:notaport", "hunter2"),
        ("notice@example.com,alice:hunter2@db.invalid:notaport", "hunter2"),
        ("notice@example.com;alice:hunter2@db.invalid:notaport", "hunter2"),
        ("notice@example.com/alice:hunter2@db.invalid:notaport", "hunter2"),
    ],
)
def test_malformed_docker_endpoints_redact_scheme_less_userinfo(
    endpoint: str,
    secret: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "synthetic" / "KineticLoop"
    root.mkdir(parents=True)
    result = subprocess.CompletedProcess(
        ["docker", "compose", "port"],
        0,
        stdout=f"{endpoint}\n",
        stderr="",
    )
    lifecycle = DatabaseLifecycle(root, runner=Mock(return_value=result), environ={})

    with pytest.raises(DatabaseLifecycleError) as caught:
        lifecycle.connection()

    rendered = str(caught.value)
    assert "alice" not in rendered
    assert secret not in rendered
    assert "%3A" not in rendered
    assert "[REDACTED]" in rendered
