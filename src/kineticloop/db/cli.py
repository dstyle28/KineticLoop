"""Add local database lifecycle commands to the stable ``kl`` entrypoint."""

from __future__ import annotations

import argparse

from kineticloop import cli as engineering_cli
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError


def _db_reset(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kl db-reset")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        lifecycle = DatabaseLifecycle(engineering_cli.repository_root())
        connection = lifecycle.reset(timeout_seconds=args.timeout)
    except DatabaseLifecycleError as error:
        parser.exit(1, f"db-reset: {error}\n")
    if args.json:
        print(connection.as_json())
    else:
        print(f"PostgreSQL reset for Compose project {connection.project_name}.")
        print(f"Database: {connection.database_name}")
        print(f"DATABASE_URL={connection.url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else None
    if arguments is None:
        import sys

        arguments = sys.argv[1:]
    if arguments[:1] == ["db-reset"]:
        return _db_reset(arguments[1:])
    return engineering_cli.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
