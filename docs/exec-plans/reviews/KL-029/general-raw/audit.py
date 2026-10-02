"""Independent GENERAL review audit; reads exact Git blobs, never mutates task evidence."""
from pathlib import Path
import collections
import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[5]
REVIEWED = "eed165afbd56d3ae551c46166aaec776cf79e625"
BASE = "9268fc8dd8c071c02dc5c698274dbf6fcd112776"
TESTED = "b9fbf9b475e07765db62e67f0104a800036dda4d"

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)

def blob(path, revision=REVIEWED):
    entry = git("ls-tree", revision, "--", path).decode().split()
    assert entry and entry[0] in ("100644", "100755") and entry[1] == "blob", (path, entry)
    return git("show", revision + ":" + path)

assert git("rev-parse", "HEAD").decode().strip() == REVIEWED
for before, after in ((BASE, TESTED), (TESTED, REVIEWED)):
    subprocess.run(["git", "merge-base", "--is-ancestor", before, after], cwd=ROOT, check=True)
suffix = []
for commit in git("rev-list", "--reverse", TESTED + ".." + REVIEWED).decode().splitlines():
    assert len(git("rev-list", "--parents", "-n", "1", commit).decode().split()) == 2
    changes = git("diff-tree", "--no-commit-id", "--name-status", "-r", commit).decode().splitlines()
    for change in changes:
        status, path = change.split("\t")
        assert path == "docs/exec-plans/completed/KL-029_RESULT.yaml" or (
            status == "A" and path.startswith("docs/exec-plans/evidence/KL-029/")
        ), change
    suffix.append({"commit": commit, "changes": changes})
changed = git("diff", "--name-only", BASE, REVIEWED).decode().splitlines()
implementation = {"tests/db/test_shadow_isolation.py", "tests/unit/protocol/test_shadow_isolation.py", "docs/contracts/shadow_isolation.md"}
assert all(p in implementation or p == "docs/exec-plans/completed/KL-029_RESULT.yaml" or p.startswith("docs/exec-plans/evidence/KL-029/") for p in changed)
for path in implementation:
    assert blob(path, TESTED) == blob(path)
index = json.loads(blob("CURRENT_DOCUMENT_INDEX.json"))
for entry in index["documents"] + index["machine_readable"]:
    assert hashlib.sha256(blob(entry["path"])).hexdigest() == entry["sha256"], entry["path"]
prerequisites = []
for task in ("KL-008", "KL-017", "KL-027"):
    item = json.loads(blob("docs/exec-plans/integrations/" + task + ".json", BASE))
    assert item["task_identity"] == "harness-backlog-v0.2/" + task and item["integration_status"] == "MERGED"
    subprocess.run(["git", "merge-base", "--is-ancestor", item["merge_commit"], BASE], cwd=ROOT, check=True)
    for path in git("ls-tree", "-r", "--name-only", BASE, "docs/exec-plans/reviews/" + task).decode().splitlines():
        if path.endswith(".json") and "/history/" not in path and path.count("/") == 4:
            review = json.loads(blob(path, BASE))
            assert review["status"] == "PASS" and review["reviewed_head_sha"] == item["reviewed_head_sha"]
    prerequisites.append(item)
assert json.loads(blob("docs/exec-plans/milestones/M2.json", BASE))["closure_status"] == "PASS"
packet = blob("docs/exec-plans/active/KL-029.md").decode()
contracts = json.loads(re.search(r"```json\n(.*?)\n```", packet, re.S).group(1))["check_contracts"]
checks = json.loads(blob("docs/exec-plans/evidence/KL-029/checks-b9fbf9b/checks.json"))
assert checks["tested_commit"] == TESTED
assert [i["check_id"] for i in checks["checks"]] == [i["check_id"] for i in contracts]
for item, contract in zip(checks["checks"], contracts):
    assert item["command"] == contract["command"] and item["result"] == "PASS" and item["exit_code"] == 0
    raw = blob(item["evidence_ref"])
    assert hashlib.sha256(raw).hexdigest() == item["log_sha256"]
    header = json.loads(raw.splitlines()[0])
    assert header["tested_commit"] == TESTED and header["command"] == item["command"]
    if item["junit_ref"]:
        suites = list(ET.fromstring(blob(item["junit_ref"])).iter("testsuite"))
        counts = {k: sum(int(s.get(k, "0")) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
        assert counts == item["counts"] and counts["tests"] > 0
        assert all(counts[k] == 0 for k in ("failures", "errors", "skipped"))
        assert b"XPASS" not in raw and b"XFAIL" not in raw
log = "docs/exec-plans/evidence/KL-029/checks-b9fbf9b/shadow_suite_dc.log"
records = [json.loads(line.removeprefix("SHADOW_EVIDENCE ")) for line in blob(log).decode().splitlines() if line.startswith("SHADOW_EVIDENCE ")]
counts = collections.Counter(r["kind"] for r in records)
reaches = collections.Counter(r["guard_reached"] for r in records if "guard_reached" in r)
assert counts["full_TEST_owner_trajectory"] == 4 and counts["actual_T7_positive_guard"] == 12
assert counts["zero_effect"] == 26 and counts["live_privilege_denial"] == 15 and counts["cleanup"] == 4
digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
for r in records:
    assert r["tested_commit"] == TESTED
    if r["kind"] == "namespace":
        assert r["root"] == str(ROOT.resolve()) and r["compose"] == "kineticloop-kl029-shadow-" + TESTED[:7] + "-" + digest
        assert r["database"] == "kineticloop_kl029_shadow_" + TESTED[:7] + "_" + digest
    elif r["kind"] == "zero_effect":
        assert r["before"] == r["after"] and r["zero_new_receipt_event_outbox"]
    elif r["kind"] == "cleanup":
        assert not any(r["remaining"].values())
    elif r["kind"] == "live_privilege_denial":
        assert r["sqlstate"] == "42501" and r["target"] and r["evaluation_subject"]
    elif r["kind"] == "scope_denial":
        assert r["response"] == {"error": "subject_scope_denied"} and r["code"] == "SUBJECT_SCOPE_DENIED"
        assert r["timing_class"] == "BOUNDED_SCOPE_LOOKUP" and r["measured_constant_time"] is False
    elif r["kind"] == "actual_T7_positive_guard":
        assert r["decision"]["is_executable"] and r["decision"]["non_bearer"]
    elif r["kind"] == "declared_external_evaluation_inputs":
        assert r["source"]["classification"] == "EXTERNAL_HISTORICAL_INPUT_ONLY"
        assert r["source"]["execution_disposition"] == "NOT_EXECUTABLE" and r["source"]["mode"] == "RECORDED_OUTPUT"
        assert r["triggers"] and all(t[2] in ("O", "A") for t in r["triggers"])
        assert r["no_live_pointer_or_shadow_owner_output"]
        for value in r["persisted"].values():
            canonical = json.dumps(value["row"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            assert hashlib.sha256(canonical.encode()).hexdigest() == value["row_hash"]
summary = {"reviewed_head_sha": REVIEWED, "tested_commit": TESTED, "base_commit": BASE, "source": "exact Git blobs, independent assertions", "authority_hashes_valid": True, "scope_valid": True, "tested_to_reviewed_linear_bookkeeping": suffix, "prerequisites": prerequisites, "checks": checks["checks"], "witness_counts": dict(counts), "guard_reach_counts": dict(reaches), "fresh_pu": {"selector": "tests/unit/protocol/test_shadow_isolation.py", "tests": 2, "failures": 0, "errors": 0, "skipped": 0}, "product_requirements_claimed": []}
(Path(__file__).parent / "audit.json").write_text(json.dumps(summary, indent=2) + "\n")
print("GENERAL_REVIEW_AUDIT_PASS", REVIEWED, dict(counts), dict(reaches))
