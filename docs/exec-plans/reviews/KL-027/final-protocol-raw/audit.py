"""Independent final KL027 source/evidence/ancestry audit; never uses DB lifecycle."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path.cwd()
BASE = "6d1348c5a731afb74fdf6f2345109a446cdb597c"
TESTED = "72a9a5f3f9529028708f64ece3bbec6d791413a7"
REVIEWED = "ff93c08c7c32fba9e8dede0c161bb4f97bc98259"
OUT = ROOT / "docs/exec-plans/reviews/KL-027/final-protocol-raw"


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def show(sha, path):
    return subprocess.check_output(["git", "show", f"{sha}:{path}"])


def ancestor(left, right):
    assert subprocess.run(["git", "merge-base", "--is-ancestor", left, right]).returncode == 0


def sha256(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def witnesses(path):
    items = []
    for line in (ROOT / path).read_text().splitlines():
        if "FIXTURE_EVIDENCE " in line:
            items.append(json.loads(line.split("FIXTURE_EVIDENCE ", 1)[1]))
    return items


def instant(value):
    return datetime.fromisoformat(value)


assert git("rev-parse", "HEAD") == REVIEWED
ancestor(BASE, TESTED)
ancestor(TESTED, REVIEWED)
index = json.loads((ROOT / "CURRENT_DOCUMENT_INDEX.json").read_text())
authority = []
for item in index["documents"] + index["machine_readable"]:
    assert sha256(item["path"]) == item["sha256"], item["path"]
    assert show(BASE, item["path"]) == (ROOT / item["path"]).read_bytes(), item["path"]
    authority.append({"path": item["path"], "sha256": item["sha256"]})
scope = git("diff", "--name-only", BASE, REVIEWED).splitlines()
allowed = {"tests/db/test_test_only_demo.py", "tests/unit/protocol/test_test_only_demo.py", "docs/contracts/test_only_demo.md", "docs/exec-plans/completed/KL-027_RESULT.yaml"}
assert all(p in allowed or p.startswith(("docs/exec-plans/evidence/KL-027/", "docs/exec-plans/reviews/KL-027/")) for p in scope)
suffix = []
for commit in git("rev-list", "--reverse", f"{TESTED}..{REVIEWED}").splitlines():
    parents = git("show", "-s", "--format=%P", commit).split()
    assert len(parents) == 1
    paths = git("diff", "--name-only", parents[0], commit).splitlines()
    assert all(p == "docs/exec-plans/completed/KL-027_RESULT.yaml" or p.startswith(("docs/exec-plans/evidence/KL-027/", "docs/exec-plans/reviews/KL-027/")) for p in paths)
    suffix.append({"commit": commit, "paths": paths})
for p in allowed - {"docs/exec-plans/completed/KL-027_RESULT.yaml"}:
    assert show(TESTED, p) == show(REVIEWED, p)
for prefix in ["completed/KL-027_RESULT.yaml", "integrations/KL-027.json", "reviews/KL-027"]:
    assert not git("ls-tree", "-r", "--name-only", BASE, "docs/exec-plans/" + prefix)

prerequisites = []
merges = git("log", "--first-parent", "--merges", "--format=%H", BASE).splitlines()
for number in ["017", "019", "022", "023", "024", "025", "074", "075", "076", "077", "078", "079"]:
    task = "KL-" + number
    path = f"docs/exec-plans/completed/{task}_RESULT.yaml"
    result = yaml.safe_load(show(BASE, path))
    assert result["task_identity"] == "harness-backlog-v0.2/" + task
    assert result["task_status"] == result["task_checks_status"] == "PASS"
    ancestor(result["tested_commit"], BASE)
    required = ["GENERAL", "PROTOCOL", "DB_CONCURRENCY"]
    if task == "KL-017":
        required.append("SECURITY_DATA_BOUNDARY")
    if task == "KL-074":
        required = ["GENERAL", "DB_CONCURRENCY", "SECURITY_DATA_BOUNDARY"]
    reviews = [json.loads(show(BASE, f"docs/exec-plans/reviews/{task}/{kind}.json")) for kind in required]
    result_commits = git("log", BASE, "--format=%H", "--", path).splitlines()
    merged = None
    for candidate in reversed(merges):
        if all(subprocess.run(["git", "merge-base", "--is-ancestor", c, candidate]).returncode == 0 for c in result_commits):
            merged = candidate
            break
    assert merged and "Merge pull request #" in git("show", "-s", "--format=%s", merged)
    parents = git("show", "-s", "--format=%P", merged).split()
    assert len(parents) == 2
    ancestor(result["tested_commit"], parents[1])
    verified = []
    for review in reviews:
        assert review["status"] == "PASS" and review["task_identity"] == result["task_identity"]
        reviewed = review["reviewed_head_sha"]
        ancestor(reviewed, parents[1])
        for commit in git("rev-list", f"{reviewed}..{parents[1]}").splitlines():
            ps = git("show", "-s", "--format=%P", commit).split()
            assert len(ps) == 1
            assert all(p.startswith(f"docs/exec-plans/reviews/{task}/") for p in git("diff", "--name-only", ps[0], commit).splitlines())
        verified.append({"kind": review["review_type"], "status": review["status"], "reviewed_head_sha": reviewed})
    prerequisites.append({"task": task, "tested_commit": result["tested_commit"], "normal_merge": merged, "source_head": parents[1], "required_reviews": verified, "result_sha256": hashlib.sha256(show(BASE, path)).hexdigest()})
assert json.loads(show(BASE, "docs/exec-plans/milestones/M2.json"))["closure_status"] == "PASS"
result = yaml.safe_load((ROOT / "docs/exec-plans/completed/KL-027_RESULT.yaml").read_text())
assert result["tested_commit"] == TESTED and result["base_commit"] == BASE
assert result["requirements_covered"] == [] and result["integration_status"] == "UNMERGED"
checks = json.loads((ROOT / "docs/exec-plans/evidence/KL-027/checks-72a9a5f/checks.json").read_text())
assert checks["tested_commit"] == TESTED and len(checks["checks"]) == 12
verified_checks = []
for check in checks["checks"]:
    assert check["result"] == "PASS" and check["exit_code"] == 0
    assert sha256(check["evidence_ref"]) == check["log_sha256"]
    if check["junit_ref"]:
        suite = ET.parse(ROOT / check["junit_ref"]).getroot().find("testsuite")
        counts = {k: int(suite.attrib[k]) for k in ("tests", "failures", "errors", "skipped")}
        assert counts == check["counts"] and counts["tests"] > 0
        assert counts["failures"] == counts["errors"] == counts["skipped"] == 0
    verified_checks.append({"check_id": check["check_id"], "counts": check["counts"], "sha256": check["log_sha256"]})
items = witnesses("docs/exec-plans/evidence/KL-027/checks-72a9a5f/demo_suite_e2e.log")
counts = Counter(i["kind"] for i in items)
assert counts["namespace"] == counts["cleanup"] == 61
for item in items:
    if item["kind"] == "cleanup":
        assert all(not value for value in item["remaining"].values())
    if item["kind"] == "namespace":
        assert item["tested_commit"] == TESTED and item["compose"] == checks["compose"] and item["database"] == checks["database"]
timings = [i for i in items if i["kind"] == "trusted_post_lock_expiry_DC"]
assert {i["operation"] for i in timings} == {"T6", "START", "CONTINUE", "RESUME"}
for item in timings:
    assert instant(item["trusted_before_wait"]) <= instant(item["trusted_blocked_at"]) < instant(item["source_end"]) < instant(item["trusted_after"])
    assert item["observed_lock"][1] and item["trusted_blocked_at"] == item["observed_lock"][3]
    assert item["zero_effects"] is True
    assert ("expired" in item["actual_guard"]) if item["operation"] == "T6" else ("TIME_INELIGIBLE" in item["actual_guard"])
preloss = [i for i in items if i["kind"] == "lifecycle_current_preconditions"]
assert len(preloss) == 12
for item in preloss:
    assert item["non_bearer"] and item["fresh_key"]
    assert item["lifecycle"] == ("PAUSED" if item["mode"] == "RESUME" else "IN_PROGRESS")
    if item["mode"] == "START":
        assert item["distinct_absent_start"]
assert counts["historical_identity_only"] == 9
trajectory = next(i for i in items if i["kind"] == "full_commit")
persisted = trajectory["persisted"]
physical_d = persisted["prescription_demand_features"][0][0]
proposals = [i[0] for i in persisted["proposal_revisions"]]
f = next(i for i in proposals if i["proposal_kind"] == "FITNESS")
n = next(i for i in proposals if i["proposal_kind"] == "NUTRITION")
assert physical_d["ref_s34_id"] == f["id"]
assert n["demand_feature_id"] == physical_d["id"]
assert n["typed_payload"]["fitness_hash"] == f["content_hash"]
certificates = [i[0]["validity_certificate"] for i in persisted["authorization_issuances"]]
metadata = []
for certificate in certificates:
    dep = next(d for d in certificate["dependencies"] if d["dependency_kind"] == "DEMAND_FEATURE")
    assert dep["identity"] == physical_d["id"] and dep["proposal_id"] == n["id"]
    metadata.append({"demand_id": physical_d["id"], "physical_fitness_id": f["id"], "descriptive_proposal_id": dep["proposal_id"], "scope": "inherited descriptive metadata; authoritative full chain separately checked"})
audit = {"task_identity": "harness-backlog-v0.2/KL-027", "reviewed_head_sha": REVIEWED, "tested_commit": TESTED, "base_commit": BASE, "authority_hashes": authority, "allowed_scope": scope, "tested_to_reviewed_linear_result_evidence_suffix": suffix, "prerequisites": prerequisites, "m2": "PASS", "verified_checks": verified_checks, "suite_witness_counts": dict(counts), "trusted_post_lock_timings": timings, "inherited_demand_metadata": metadata, "reviewer_db_lifecycle": "separate final-db-raw; no DB lifecycle in this audit"}
(OUT / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
print(json.dumps({"status": "PASS", "prerequisites": len(prerequisites), "checks": len(verified_checks), "suite_cases": 61, "timing_witnesses": len(timings), "cleanup_witnesses": counts["cleanup"], "inherited_metadata": metadata}, indent=2))
