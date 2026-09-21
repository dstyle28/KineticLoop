#!/usr/bin/env python3
"""Executable verification for the KL-002 PostgreSQL lifecycle checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kineticloop.cli import repository_root
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError


def _lifecycle(root: Path | None = None) -> DatabaseLifecycle:
    return DatabaseLifecycle(repository_root() if root is None else root)


def compose_config_valid(_: argparse.Namespace) -> None:
    lifecycle = _lifecycle()
    lifecycle.validate_compose()
    print(json.dumps({"project_name": lifecycle.namespace.project_name, "status": "PASS"}))


def postgres_ready(args: argparse.Namespace) -> None:
    lifecycle = _lifecycle()
    connection = lifecycle.reset(timeout_seconds=args.timeout)
    current_database = lifecycle.execute_sql("SELECT current_database();")
    if current_database != lifecycle.namespace.database_name:
        raise DatabaseLifecycleError(
            f"readiness query reached {current_database!r}, expected "
            f"{lifecycle.namespace.database_name!r}"
        )
    print(connection.as_json())


def reset_idempotent(args: argparse.Namespace) -> None:
    lifecycle = _lifecycle()
    lifecycle.reset(timeout_seconds=args.timeout)
    lifecycle.execute_sql("CREATE TABLE kl_reset_probe (value integer NOT NULL);")
    lifecycle.execute_sql("INSERT INTO kl_reset_probe (value) VALUES (1);")
    lifecycle.reset(timeout_seconds=args.timeout)
    lifecycle.reset(timeout_seconds=args.timeout)
    probe_absent = lifecycle.execute_sql(
        "SELECT to_regclass('public.kl_reset_probe') IS NULL;"
    )
    if probe_absent != "t":
        raise DatabaseLifecycleError("reset left data from the preceding database generation")
    print(
        json.dumps(
            {
                "database_name": lifecycle.namespace.database_name,
                "resets": 3,
                "sentinel_removed": True,
                "status": "PASS",
            },
            sort_keys=True,
        )
    )


def worktree_db_isolated(args: argparse.Namespace) -> None:
    primary = _lifecycle()
    peer = _lifecycle(args.peer_root)
    check_error: Exception | None = None
    try:
        if primary.namespace == peer.namespace:
            raise DatabaseLifecycleError("distinct worktrees resolved to the same database namespace")
        primary.reset(timeout_seconds=args.timeout)
        peer.reset(timeout_seconds=args.timeout)
        primary.execute_sql("CREATE TABLE kl_worktree_probe (owner text NOT NULL);")
        primary.execute_sql("INSERT INTO kl_worktree_probe (owner) VALUES ('primary');")
        peer_probe_absent = peer.execute_sql(
            "SELECT to_regclass('public.kl_worktree_probe') IS NULL;"
        )
        if peer_probe_absent != "t":
            raise DatabaseLifecycleError("primary worktree data was visible in the peer database")
        print(
            json.dumps(
                {
                    "primary": {
                        "root": str(primary.root),
                        "project_name": primary.namespace.project_name,
                        "database_name": primary.namespace.database_name,
                    },
                    "peer": {
                        "root": str(peer.root),
                        "project_name": peer.namespace.project_name,
                        "database_name": peer.namespace.database_name,
                    },
                    "peer_cannot_see_primary_probe": True,
                    "status": "PASS",
                },
                sort_keys=True,
            )
        )
    except Exception as error:
        check_error = error
    finally:
        cleanup_errors: list[str] = []
        for label, lifecycle in (("primary", primary), ("peer", peer)):
            try:
                lifecycle.destroy()
            except DatabaseLifecycleError as error:
                cleanup_errors.append(f"{label}: {error}")
        if cleanup_errors:
            detail = "; ".join(cleanup_errors)
            raise DatabaseLifecycleError(f"worktree cleanup failed: {detail}") from check_error
    if check_error is not None:
        raise check_error


def destroy(_: argparse.Namespace) -> None:
    lifecycle = _lifecycle()
    lifecycle.destroy()
    print(json.dumps({"project_name": lifecycle.namespace.project_name, "status": "REMOVED"}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=60.0)
    subparsers = parser.add_subparsers(dest="check", required=True)
    subparsers.add_parser("compose-config-valid").set_defaults(handler=compose_config_valid)
    subparsers.add_parser("postgres-ready").set_defaults(handler=postgres_ready)
    subparsers.add_parser("reset-idempotent").set_defaults(handler=reset_idempotent)
    isolation = subparsers.add_parser("worktree-db-isolated")
    isolation.add_argument("--peer-root", type=Path, required=True)
    isolation.set_defaults(handler=worktree_db_isolated)
    subparsers.add_parser("destroy").set_defaults(handler=destroy)
    args = parser.parse_args()
    try:
        args.handler(args)
    except DatabaseLifecycleError as error:
        parser.exit(1, f"{args.check}: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
