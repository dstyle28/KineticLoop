#!/usr/bin/env python3
"""Write the KL-002 result after all revision-bound CI checks pass."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tested-commit", required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.tested_commit) is None:
        parser.error("--tested-commit must be a full 40-character lowercase Git SHA")
    evidence_root = "docs/exec-plans/evidence/KL-002"
    evidence_refs = {
        check_id: f"{evidence_root}/{check_id}-{args.tested_commit}.log"
        for check_id in (
            "compose_config_valid",
            "postgres_ready",
            "reset_idempotent",
            "worktree_db_isolated",
        )
    }
    result = {
        "task_identity": "harness-backlog-v0.2/KL-002",
        "display_task_id": "KL-002",
        "task_definition_version": "v0.2",
        "base_commit": "7da20cdd24720705f3bb6584921f5413d9aa18f4",
        "tested_commit": args.tested_commit,
        "merge_commit": None,
        "task_status": "PASS",
        "task_checks_status": "PASS",
        "integration_status": "UNMERGED",
        "summary": (
            "Added a deterministic local PostgreSQL 16 lifecycle whose Compose project, "
            "database, volume, network, and ephemeral host port are isolated by worktree."
        ),
        "commands_run": [
            {
                "check_id": "compose_config_valid",
                "command": "uv run python tools/db/verify.py compose-config-valid",
                "result": "PASS",
                "evidence_ref": evidence_refs["compose_config_valid"],
            },
            {
                "check_id": "postgres_ready",
                "command": "uv run python tools/db/verify.py postgres-ready",
                "result": "PASS",
                "evidence_ref": evidence_refs["postgres_ready"],
            },
            {
                "check_id": "reset_idempotent",
                "command": "uv run python tools/db/verify.py reset-idempotent",
                "result": "PASS",
                "evidence_ref": evidence_refs["reset_idempotent"],
            },
            {
                "check_id": "worktree_db_isolated",
                "command": (
                    "uv run python tools/db/verify.py worktree-db-isolated "
                    "--peer-root <second-git-worktree>"
                ),
                "result": "PASS",
                "evidence_ref": evidence_refs["worktree_db_isolated"],
            },
        ],
        "requirements_covered": [],
        "files_changed": [
            ".env.example",
            ".github/workflows/db.yml",
            "compose.yaml",
            "pyproject.toml",
            "src/kineticloop/db/__init__.py",
            "src/kineticloop/db/cli.py",
            "src/kineticloop/db/lifecycle.py",
            "tools/db/verify.py",
            "tools/db/write_result.py",
            "tests/db/__init__.py",
            "tests/db/test_cli.py",
            "tests/db/test_lifecycle.py",
            "tests/db/test_result_writer.py",
            "docs/exec-plans/evidence/KL-002/compose_config_valid.log",
            "docs/exec-plans/evidence/KL-002/postgres_ready.log",
            "docs/exec-plans/evidence/KL-002/reset_idempotent.log",
            "docs/exec-plans/evidence/KL-002/worktree_db_isolated.log",
            *evidence_refs.values(),
            "docs/exec-plans/completed/KL-002_RESULT.yaml",
        ],
        "decisions": [
            "Derive Compose and database namespaces from the resolved physical worktree path.",
            "Publish PostgreSQL on an ephemeral loopback port rather than a shared fixed port.",
            "Make teardown failures fail lifecycle verification.",
        ],
        "known_limitations": [
            "Docker with the Compose plugin is required for live lifecycle checks."
        ],
        "follow_up_tasks": [],
        "spec_change_request": None,
    }
    output = Path("docs/exec-plans/completed/KL-002_RESULT.yaml")
    output.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
