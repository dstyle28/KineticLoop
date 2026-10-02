"""Read-only independent GENERAL review provenance and raw-evidence audit."""
import ast
import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path.cwd().resolve()
BASE = "6d1348c5a731afb74fdf6f2345109a446cdb597c"
HEAD = "1df15275291ee99b98bd063e856d45c83ccc6f81"
TESTED = "8b446eda05bfb8201fb48c89fda5d03eb40c2218"


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def ancestor(old, new):
    assert subprocess.run(["git", "merge-base", "--is-ancestor", old, new]).returncode == 0


ancestor(BASE, TESTED)
ancestor(TESTED, HEAD)
assert git("rev-parse", "HEAD") == HEAD
changed = git("diff", "--name-only", BASE, HEAD).splitlines()
allowed = ["tests/db/test_test_only_demo.py", "tests/unit/protocol/test_test_only_demo.py", "docs/contracts/test_only_demo.md", "docs/exec-plans/completed/KL-027_RESULT.yaml"]
assert all(p in allowed or p.startswith("docs/exec-plans/evidence/KL-027/") for p in changed)
post_test = git("diff", "--name-only", TESTED, HEAD).splitlines()
assert all(p == "docs/exec-plans/completed/KL-027_RESULT.yaml" or p.startswith("docs/exec-plans/evidence/KL-027/") for p in post_test)
assert git("diff", TESTED, HEAD, "--", "tests", "src", "docs/contracts") == ""
authority = json.loads(Path("CURRENT_DOCUMENT_INDEX.json").read_text())
hashes = {}
for item in authority["documents"] + authority["machine_readable"]:
    p = Path(item["path"])
    actual = hashlib.sha256(p.read_bytes()).hexdigest()
    assert actual == item["sha256"], p
    assert git("diff", BASE, HEAD, "--", str(p)) == ""
    hashes[str(p)] = actual
merges = git("log", "--first-parent", "--merges", "--format=%H", BASE).splitlines()
prereqs = []
for number in ["017", "019", "022", "023", "024", "025", "074", "075", "076", "077", "078", "079"]:
    task = "KL-" + number
    p = Path("docs/exec-plans/completed") / (task + "_RESULT.yaml")
    result = yaml.safe_load(p.read_text())
    assert result["task_identity"] == "harness-backlog-v0.2/" + task
    assert result["task_status"] == result["task_checks_status"] == "PASS"
    ancestor(result["tested_commit"], BASE)
    reviews = []
    review_shas = []
    for path in Path("docs/exec-plans/reviews", task).glob("*.json"):
        review = json.loads(path.read_text())
        assert review["status"] == "PASS"
        ancestor(review["reviewed_head_sha"], BASE)
        review_shas.append(review["reviewed_head_sha"])
        reviews.append({"path": str(path), "sha": review["reviewed_head_sha"], "findings": review["findings"]})
    assert {r["path"].split("/")[-1] for r in reviews} >= {"GENERAL.json", "DB_CONCURRENCY.json"}
    if task != "KL-074":
        assert "PROTOCOL.json" in {r["path"].split("/")[-1] for r in reviews}
    # Find an actual protected first-parent two-parent normal PR merge whose source
    # includes this reviewed result, then validate its task-only linear suffix.
    matches = []
    for merge in reversed(merges):
        parents = git("show", "-s", "--format=%P", merge).split()
        if len(parents) != 2 or not git("show", "-s", "--format=%s", merge).startswith("Merge pull request #"):
            continue
        if not all(subprocess.run(["git", "merge-base", "--is-ancestor", sha, parents[1]]).returncode == 0 for sha in review_shas):
            continue
        if not all(git("show", f"{parents[1]}:{r['path']}") == Path(r["path"]).read_text().strip() for r in reviews):
            continue
        paths = git("diff", "--name-only", review_shas[0], parents[1]).splitlines()
        if all(p.startswith("docs/exec-plans/reviews/" + task + "/") for p in paths):
            assert git("rev-list", "--merges", review_shas[0] + ".." + parents[1]) == ""
            matches.append({"merge": merge, "source": parents[1], "review_only_paths": paths})
            break
    assert matches, task
    prereqs.append({"task_identity": result["task_identity"], "tested_commit": result["tested_commit"], "result_sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "reviews": reviews, "normal_merge": matches[0]})
m2 = json.loads(Path("docs/exec-plans/milestones/M2.json").read_text())
assert m2["closure_status"] == "PASS"
ancestor(m2["evaluated_commit"], BASE)
for p in ["docs/exec-plans/completed/KL-027_RESULT.yaml", "docs/exec-plans/integrations/KL-027.json", "docs/exec-plans/reviews/KL-027/GENERAL.json"]:
    assert subprocess.run(["git", "cat-file", "-e", BASE + ":" + p], capture_output=True).returncode != 0
packet = Path("docs/exec-plans/active/KL-027.md").read_text()
contracts = json.loads(re.search(r"```json\n(.*?)\n```", packet, re.S).group(1))["check_contracts"]
records = json.loads(Path("docs/exec-plans/evidence/KL-027/checks-8b446ed/checks.json").read_text())
assert records["tested_commit"] == TESTED
digest = hashlib.sha256(os.fsencode(ROOT)).hexdigest()[:12]
assert records["compose"] == f"kineticloop-kl027-demo-{TESTED[:7]}-{digest}"
assert records["database"] == f"kineticloop_kl027_demo_{TESTED[:7]}_{digest}"
assert len(contracts) == len(records["checks"]) == 12
checks = []
for spec, record in zip(contracts, records["checks"], strict=True):
    assert record["check_id"] == spec["check_id"] and record["command"] == spec["command"]
    assert record["exit_code"] == 0 and record["result"] == "PASS"
    raw = Path(record["evidence_ref"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == record["log_sha256"]
    header = json.loads(raw.splitlines()[0])
    assert header["tested_commit"] == TESTED and header["command"] == spec["command"]
    assert header["oracle"] == spec["pass_oracle"]
    if record["junit_ref"]:
        suites = list(ET.parse(record["junit_ref"]).getroot().iter("testsuite"))
        counts = {k: sum(int(s.get(k, "0")) for s in suites) for k in ["tests", "failures", "errors", "skipped"]}
        assert counts == record["counts"] and counts["tests"] > 0
        assert counts["failures"] == counts["errors"] == counts["skipped"] == 0
    witnesses = []
    for line in raw.decode().splitlines():
        if line.startswith("FIXTURE_EVIDENCE "):
            witnesses.append(json.loads(line.removeprefix("FIXTURE_EVIDENCE ")))
    inventory = Counter(w["kind"] for w in witnesses)
    for w in witnesses:
        if w["kind"] == "namespace":
            assert w["tested_commit"] == TESTED and w["compose"] == records["compose"] and w["database"] == records["database"]
            assert w["migration"] == "e8c2f1a6b904"
        if w["kind"] == "cleanup":
            assert not any(w["remaining"].values())
        if w["kind"] == "exact_zero_effect_denial":
            assert w["intended_cause"] and w["intended_cause"] in w["actual_cause"]
    checks.append({"check_id": record["check_id"], "counts": record["counts"], "log_sha256": record["log_sha256"], "witness_counts": dict(inventory)})
result = yaml.safe_load(Path("docs/exec-plans/completed/KL-027_RESULT.yaml").read_text())
assert result["tested_commit"] == TESTED and result["requirements_covered"] == []
assert result["base_commit"] == BASE and result["integration_status"] == "UNMERGED"
assert [c["check_id"] for c in result["commands_run"]] == [c["check_id"] for c in contracts]
print(json.dumps({"reviewed_head_sha": HEAD, "tested_commit": TESTED, "base_commit": BASE, "changed_paths": changed, "post_test_paths": post_test, "authority_hashes": hashes, "prerequisites": prereqs, "m2_closure": "PASS_ANCESTOR", "twelve_checks": checks, "product_requirement_claims": [], "status": "AUDIT_PASS"}, indent=2))
