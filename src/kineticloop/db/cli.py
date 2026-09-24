"""Add local database lifecycle commands to the stable ``kl`` entrypoint."""

from __future__ import annotations

import argparse

from kineticloop import cli as engineering_cli
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError
from kineticloop.security.redaction import REDACTED, Redactor


def _db_reset(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kl db-reset")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--json", action="store_true")
    redacted_argv = Redactor().redact(argv)
    assert isinstance(redacted_argv, list)
    args = parser.parse_args(
        [item if isinstance(item, str) else REDACTED for item in redacted_argv]
    )
    try:
        lifecycle = DatabaseLifecycle(engineering_cli.repository_root())
        connection = lifecycle.reset(timeout_seconds=args.timeout)
    except DatabaseLifecycleError as error:
        parser.exit(1, f"db-reset: {error}\n")
    if args.json:
        print(connection.as_json())
    else:
        diagnostic = connection.diagnostic_mapping()
        print(f"PostgreSQL reset for Compose project {diagnostic['project_name']}.")
        print(f"Database: {diagnostic['database_name']}")
        print(f"Host: {diagnostic['host']}:{diagnostic['port']}")
        print(f"DATABASE_URL={diagnostic['url']}")
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
