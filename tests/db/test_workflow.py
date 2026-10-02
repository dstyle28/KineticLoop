from pathlib import Path

import yaml


def test_review_record_only_push_does_not_rerun_database_evidence() -> None:
    workflow = Path(__file__).parents[2] / ".github/workflows/db.yml"
    config = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    # HG-046 removes all automatic full-DB triggers, including review-only pushes.
    assert set(config["on"]) == {"workflow_dispatch"}
    assert "record-evidence" not in config["jobs"]
