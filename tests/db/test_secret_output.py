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
        stderr=f"nested password={PASSWORD}",
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
    assert "database command failed" in rendered_error

    with patch("kineticloop.db.cli.DatabaseLifecycle", return_value=lifecycle):
        with pytest.raises(SystemExit) as exit_info:
            main(["db-reset"])
    assert exit_info.value.code == 1
    cli_error = capsys.readouterr().err
    assert USER not in cli_error
    assert PASSWORD not in cli_error
    assert encoded not in cli_error
    assert "db-reset: database command failed" in cli_error
