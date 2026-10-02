"""Independent read-only protocol evidence audit; never opens a database."""
import collections
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import yaml

from kineticloop.protocol.execution import digest

ROOT = Path(__file__).resolve().parents[5]
BASE = "6d1348c5a731afb74fdf6f2345109a446cdb597c"
HEAD = "1df15275291ee99b98bd063e856d45c83ccc6f81"
TESTED = "8b446eda05bfb8201fb48c89fda5d03eb40c2218"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def ancestor(a, b):
    subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=ROOT, check=True)


def read(path):
    return (ROOT / path).read_text()


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


ancestor(BASE, TESTED)
ancestor(TESTED, HEAD)
scope = git("diff", "--name-only", BASE, HEAD).splitlines()
allowed = {"tests/db/test_test_only_demo.py", "tests/unit/protocol/test_test_only_demo.py", "docs/contracts/test_only_demo.md", "docs/exec-plans/completed/KL-027_RESULT.yaml"}
assert all(p in allowed or p.startswith("docs/exec-plans/evidence/KL-027/") for p in scope)
for p in list(allowed)[:]:
    if p != "docs/exec-plans/completed/KL-027_RESULT.yaml":
        assert git("rev-parse", TESTED + ":" + p) == git("rev-parse", HEAD + ":" + p)
suffix = git("diff", "--name-only", TESTED, HEAD).splitlines()
assert all(p == "docs/exec-plans/completed/KL-027_RESULT.yaml" or p.startswith("docs/exec-plans/evidence/KL-027/") for p in suffix)
subprocess.run(["git", "diff", "--check", BASE, HEAD], cwd=ROOT, check=True)
index = json.loads(read("CURRENT_DOCUMENT_INDEX.json"))
indexed = index["documents"] + index["machine_readable"]
for item in indexed:
    assert sha(item["path"]) == item["sha256"], item["path"]

entry = json.loads(read("docs/exec-plans/evidence/KL-027/entry-audit.json"))
prerequisites = []
for p in entry["prerequisites"]:
    task = p["task"]
    result_path = f"docs/exec-plans/completed/{task}_RESULT.yaml"
    result = yaml.safe_load(read(result_path))
    assert result["task_identity"] == "harness-backlog-v0.2/" + task
    assert result["task_status"] == result["task_checks_status"] == "PASS"
    merge = p["normal_merge"].split()[0]
    parents = git("show", "-s", "--format=%P", merge).split()
    assert len(parents) == 2
    ancestor(merge, BASE)
    ancestor(result["tested_commit"], parents[1])
    reviewed = []
    for rp in p["reviews"]:
        review = json.loads(read(rp["path"]))
        assert review["task_identity"] == result["task_identity"] and review["status"] == "PASS"
        ancestor(review["reviewed_head_sha"], parents[1])
        delta = git("diff", "--name-only", review["reviewed_head_sha"], parents[1]).splitlines()
        assert all(x.startswith(f"docs/exec-plans/reviews/{task}/") for x in delta)
        assert not git("rev-list", "--merges", review["reviewed_head_sha"] + ".." + parents[1])
        reviewed.append({"path": rp["path"], "reviewed_head_sha": review["reviewed_head_sha"], "sha256": sha(rp["path"]), "findings": review["findings"]})
    prerequisites.append({"task": task, "normal_merge": merge, "source_head": parents[1], "result_sha256": sha(result_path), "reviews": reviewed, "known_limitations": result.get("known_limitations", [])})
assert len(prerequisites) == 12
m2 = json.loads(read("docs/exec-plans/milestones/M2.json"))
assert m2["closure_status"] == "PASS"
ancestor(m2["evaluated_commit"], BASE)

directory = "docs/exec-plans/evidence/KL-027/checks-8b446ed/"
checks = json.loads(read(directory + "checks.json"))
assert checks["tested_commit"] == TESTED
inventory = []
for check in checks["checks"]:
    assert check["exit_code"] == 0 and check["result"] == "PASS"
    assert sha(check["evidence_ref"]) == check["log_sha256"]
    log = read(check["evidence_ref"])
    header = json.loads(log.splitlines()[0])
    assert header["tested_commit"] == TESTED and header["command"] == check["command"]
    if check["junit_ref"]:
        suites = list(ET.fromstring(read(check["junit_ref"])).iter("testsuite"))
        counts = {k: sum(int(s.get(k, "0")) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
        assert counts == check["counts"] and counts["tests"] > 0
        assert counts["failures"] == counts["errors"] == counts["skipped"] == 0
    inventory.append({"check_id": check["check_id"], "counts": check["counts"], "verified_log_sha256": sha(check["evidence_ref"])})
assert len(inventory) == 12
log = read(directory + "demo_suite_e2e.log")
rows = [json.loads(s.split("FIXTURE_EVIDENCE ", 1)[1]) for s in log.splitlines() if "FIXTURE_EVIDENCE " in s]
counts = dict(collections.Counter(r["kind"] for r in rows))
root_digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
for r in rows:
    if r["kind"] == "namespace":
        assert r["tested_commit"] == TESTED
        assert r["compose"] == f"kineticloop-kl027-demo-{TESTED[:7]}-{root_digest}"
        assert r["database"] == f"kineticloop_kl027_demo_{TESTED[:7]}_{root_digest}"
        assert r["migration"] == "e8c2f1a6b904"
    if r["kind"] == "cleanup":
        assert not any(r["remaining"].values())
        assert r["inventory"] == ["bootstrap_two_phase(selected_lifecycle)", "reset", "start", "destroy"]
    if r["kind"] == "forward_stage":
        order = ["CREATED", "LEASED", "BUILDING_CONTEXT", "FITNESS", "DEMAND_FEATURES", "NUTRITION", "VALIDATING", "COMMIT_READY"]
        assert order.index(r["target"]) == order.index(r["basis"]["source_state"]) + 1
        assert r["result"]["state"] == r["target"]
    if r["kind"] in {"output", "full_output"}:
        assert digest(r["payload"]) == r["hash"]
    if r["kind"] == "exact_zero_effect_denial":
        assert r["intended_cause"] and r["intended_cause"] in r["actual_cause"]
    if r["kind"] == "lifecycle_current_preconditions":
        assert r["lifecycle"] == ("PAUSED" if r["mode"] == "RESUME" else "IN_PROGRESS")
        assert r["non_bearer"] and r["distinct_absent_start"] == (r["mode"] == "START")
    if r["kind"] == "historical_identity_only":
        assert r["zero_effects"] and r["start"]["replayed"] and r["bundle"]["replayed"]
        assert r["start"]["executable"] is r["bundle"]["executable"] is False
    if r["kind"] == "trusted_post_lock_expiry_DC":
        assert datetime.fromisoformat(r["trusted_before_wait"]) < datetime.fromisoformat(r["source_end"]) < datetime.fromisoformat(r["trusted_after"])
        assert r["observed_lock"][1] and r["zero_effects"]
        assert ("expired" if r["operation"] == "T6" else "TIME_INELIGIBLE") in r["actual_guard"]
assert counts["namespace"] == counts["cleanup"] == 61
assert counts["historical_identity_only"] == 9 and counts["trusted_post_lock_expiry_DC"] == 4
full = next(r for r in rows if r["kind"] == "full_commit")
state = {k: [r[0] for r in v] for k, v in full["persisted"].items()}
assert [m["action_type"] for m in full["result"]["members"]] == ["TRAINING", "NUTRITION"]
certificates = []
for issuance in state["authorization_issuances"]:
    certificate = issuance["validity_certificate"]
    assert digest(certificate["dependencies"]) == certificate["closure_digest"] == issuance["artifact_dependency_closure_hash"]
    assert datetime.fromisoformat(issuance["valid_until"]) == min(datetime.fromisoformat(d["valid_until"]) for d in certificate["dependencies"] if d.get("valid_until"))
    cert_resolutions = {d["identity"] for d in certificate["dependencies"] if d["dependency_kind"] == "EVIDENCE_RESOLUTION"}
    assert cert_resolutions == {m["resolution_id"] for m in full["result"]["members"]}
    prescription = next(p for p in state["prescription_revisions"] if p["id"] == issuance["ref_s40_id"])
    assert digest(prescription["typed_payload"]) == prescription["content_hash"] == issuance["bound_content_hash"]
    demand = state["prescription_demand_features"][0]
    demand_dependency = next(d for d in certificate["dependencies"] if d["dependency_kind"] == "DEMAND_FEATURE")
    assert demand_dependency["identity"] == demand["id"]
    certificates.append({"issuance_id": issuance["id"], "prescription_id": prescription["id"], "action_type": prescription["prescription_kind"], "resolution_id": issuance["ref_s36_id"], "validation_id": issuance["ref_s37_id"], "closure_digest": certificate["closure_digest"], "valid_until": issuance["valid_until"], "demand_physical_fitness_id": demand["ref_s34_id"], "demand_audit_proposal_id": demand_dependency["proposal_id"]})
summary = {"reviewed_head_sha": HEAD, "tested_commit": TESTED, "base_commit": BASE, "indexed_hashes_verified": len(indexed), "scope": scope, "tested_to_reviewed_suffix": suffix, "prerequisites": prerequisites, "checks": inventory, "witness_counts": counts, "certificate_independent_recomputations": certificates, "denial_causes": [{k: r[k] for k in ("label", "intended_cause", "actual_cause")} for r in rows if r["kind"] == "exact_zero_effect_denial"], "expiry_waits": [r for r in rows if r["kind"] == "trusted_post_lock_expiry_DC"], "no_database_lifecycle_or_connections": True}
target = Path(__file__).with_name("audit.json")
target.write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({"status": "PASS", "reviewed_head_sha": HEAD, "indexed_hashes_verified": len(indexed), "prerequisites_verified": len(prerequisites), "checks": inventory, "witness_counts": counts, "certificates": certificates}, indent=2))
