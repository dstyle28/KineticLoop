from __future__ import annotations

from unittest.mock import Mock, patch

from kineticloop.db.cli import main
from kineticloop.db.lifecycle import DatabaseConnection


def test_db_reset_routes_through_worktree_lifecycle(capsys: object) -> None:
    connection = DatabaseConnection(
        project_name="kl_test_deadbeef0000",
        database_name="kl_test_deadbeef0000_test",
        host="127.0.0.1",
        port=49152,
        user="kineticloop",
        password="kineticloop-local-only",
    )
    lifecycle = Mock()
    lifecycle.reset.return_value = connection

    with patch("kineticloop.db.cli.DatabaseLifecycle", return_value=lifecycle):
        assert main(["db-reset", "--json"]) == 0

    lifecycle.reset.assert_called_once_with(timeout_seconds=60.0)
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert '"project_name": "kl_test_deadbeef0000"' in output


def test_existing_engineering_command_is_delegated() -> None:
    with patch("kineticloop.db.cli.engineering_cli.main", return_value=17) as legacy:
        assert main(["lint", "--fix"]) == 17
    legacy.assert_called_once_with(["lint", "--fix"])
