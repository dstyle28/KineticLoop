"""Replay HG031's exact five-task integration audit using immutable Git evidence."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.harness.validate_harness import integration_record_errors  # noqa: E402

BASE = "a8e243f043ad828717b667a222c695e2500ac1a0"
TASK_PRS = {"KL-020": 52, "KL-021": 54, "KL-022": 56, "KL-023": 59, "KL-050": 58}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


tasks = {t["id"]: t for t in json.loads((ROOT / "KineticLoop_Harness_Backlog_v0.2.json").read_text())["tasks"]}
schemas = [Draft202012Validator(json.loads((ROOT / p).read_text())) for p in
           ("INTEGRATION_RECORD.schema.json", "THREAD_RESULT.schema.json", "THREAD_REVIEW.schema.json")]
print("audited_head=" + git("rev-parse", "HEAD").decode().strip())
print("protected_base=" + BASE)
for task, pr_number in TASK_PRS.items():
    path = ROOT / f"docs/exec-plans/integrations/{task}.json"
    record = json.loads(path.read_text())
    pr = json.loads((ROOT / f"docs/exec-plans/evidence/HG-031/pr-{pr_number}.json").read_text())
    assert pr["state"] == "MERGED" and pr["baseRefName"] == "master"
    assert pr["mergeCommit"]["oid"] == record["merge_commit"]
    assert pr["headRefOid"] == record["review_record_commit"]
    assert record["result_commit"] in {c["oid"] for c in pr["commits"]}
    assert git("show", "-s", "--format=%B", record["merge_commit"]).decode().startswith(
        f"Merge pull request #{pr_number} ")
    issues = integration_record_errors(ROOT, path, record, *schemas, tasks)
    assert not issues, issues
    result_path = f"docs/exec-plans/completed/{task}_RESULT.yaml"
    result = git("show", record["result_commit"] + ":" + result_path)
    for revision in (record["reviewed_head_sha"], record["merge_commit"], BASE, "HEAD"):
        assert result == git("show", revision + ":" + result_path)
    reviews = {}
    for review_type in tasks[task]["review_requirements"]:
        review_path = f"docs/exec-plans/reviews/{task}/{review_type}.json"
        content = git("show", record["review_record_commit"] + ":" + review_path)
        assert content == git("show", BASE + ":" + review_path)
        assert content == git("show", "HEAD:" + review_path)
        reviews[review_type] = hashlib.sha256(content).hexdigest()
    print(json.dumps({"task": task, "pr": pr["url"], "record": record,
                      "result_sha256": hashlib.sha256(result).hexdigest(),
                      "review_sha256": reviews, "semantic_integration_errors": issues}, sort_keys=True))

allowed = {f"docs/exec-plans/integrations/{task}.json" for task in TASK_PRS}
for changed in git("diff", "--name-only", BASE, "HEAD").decode().splitlines():
    assert (changed in allowed or changed == "docs/exec-plans/governance/HG-031.yaml"
            or changed.startswith("docs/exec-plans/evidence/HG-031/")
            or changed.startswith("docs/exec-plans/reviews/HG-031/")), changed
print("HG031_AUDIT_PASS coverage=KL-020,KL-021,KL-022,KL-023,KL-050; immutable results/reviews; no requirement or milestone promotion")
