from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


def test_result_writer_binds_exact_tested_commit(tmp_path: Path) -> None:
    output_dir = tmp_path / "docs/exec-plans/completed"
    output_dir.mkdir(parents=True)
    tested_commit = "a" * 40
    script = Path(__file__).parents[2] / "tools/db/write_result.py"

    subprocess.run(
        [sys.executable, str(script), "--tested-commit", tested_commit],
        cwd=tmp_path,
        check=True,
    )

    result = yaml.safe_load((output_dir / "KL-002_RESULT.yaml").read_text())
    assert result["tested_commit"] == tested_commit
    assert result["task_status"] == "PASS"
    assert result["requirements_covered"] == []
    assert {item["check_id"] for item in result["commands_run"]} == {
        "compose_config_valid",
        "postgres_ready",
        "reset_idempotent",
        "worktree_db_isolated",
    }
