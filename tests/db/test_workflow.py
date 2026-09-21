from pathlib import Path


def test_review_record_only_push_does_not_rerun_database_evidence() -> None:
    workflow = Path(__file__).parents[2] / ".github/workflows/db.yml"

    assert "- docs/exec-plans/reviews/KL-002/**" in workflow.read_text(encoding="utf-8")
