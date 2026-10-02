"""Independent GENERAL audit: Git and committed raw files only; no DB lifecycle."""
import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[5]
BASE = "6d1348c5a731afb74fdf6f2345109a446cdb597c"
TESTED = "72a9a5f3f9529028708f64ece3bbec6d791413a7"
REVIEWED = "ff93c08c7c32fba9e8dede0c161bb4f97bc98259"
TASK = "harness-backlog-v0.2/KL-027"
OUT = Path(__file__).parent


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def exists(revision, path):
    return subprocess.run(["git", "cat-file", "-e", revision + ":" + path], cwd=ROOT,
                          capture_output=True).returncode == 0


def ancestor(before, after):
    assert subprocess.run(["git", "merge-base", "--is-ancestor", before, after], cwd=ROOT).returncode == 0


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def suffix(start, end, task, mode):
    ancestor(start, end)
    rows = []
    for commit in git("rev-list", "--reverse", start + ".." + end).splitlines():
        parents = git("show", "-s", "--format=%P", commit).split()
        assert len(parents) == 1, (commit, parents)
        changed = git("diff", "--name-status", parents[0], commit).splitlines()
        for line in changed:
            status, path = line.split("\t")
            if mode == "review":
                assert path.startswith("docs/exec-plans/reviews/" + task + "/"), line
            else:
                assert path in ["docs/exec-plans/completed/" + task + "_RESULT.yaml", "docs/exec-plans/completed/" + task + "_RESULT.json"] or (
                    path.startswith("docs/exec-plans/evidence/" + task + "/") and status == "A"
                    and not exists(parents[0], path)
                ), line
        rows.append({"commit": commit, "changes": changed})
    return rows


assert git("rev-parse", "HEAD") == REVIEWED
ancestor(BASE, TESTED)
ancestor(TESTED, REVIEWED)
report = {"task_identity": TASK, "base_commit": BASE, "tested_commit": TESTED,
          "reviewed_head_sha": REVIEWED, "database_lifecycle_invocations": 0}
index = json.loads((ROOT / "CURRENT_DOCUMENT_INDEX.json").read_text())
report["indexed_hashes"] = []
for item in index["documents"] + index["machine_readable"]:
    actual = sha(item["path"])
    assert actual == item["sha256"], item["path"]
    report["indexed_hashes"].append({"path": item["path"], "sha256": actual})
backlog = json.loads((ROOT / "KineticLoop_Harness_Backlog_v0.2.json").read_text())
tasks = {t["id"]: t for t in backlog["tasks"]}
spec = importlib.util.spec_from_file_location("kl027_independent_validator", ROOT / "tools/harness/validate_harness.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
result_schema = json.loads((ROOT / "THREAD_RESULT.schema.json").read_text())
review_schema = json.loads((ROOT / "THREAD_REVIEW.schema.json").read_text())
entry = json.loads((ROOT / "docs/exec-plans/evidence/KL-027/entry-audit.json").read_text())
assert entry["base_commit"] == BASE
entry_by_task = {p["task"]: p for p in entry["prerequisites"]}
merges = git("log", "--first-parent", "--merges", "--reverse", "--format=%H %s", BASE).splitlines()
report["prerequisites"] = []
for task in ["KL-017", "KL-019", "KL-022", "KL-023", "KL-024", "KL-025", "KL-074", "KL-075", "KL-076", "KL-077", "KL-078", "KL-079"]:
    path = "docs/exec-plans/completed/" + task + "_RESULT.yaml"
    result = yaml.safe_load(git("show", BASE + ":" + path))
    jsonschema.validate(result, result_schema)
    assert result["task_identity"] == "harness-backlog-v0.2/" + task
    assert result["task_status"] == result["task_checks_status"] == "PASS"
    assert not validator.semantic_result_errors(result, tasks[task], ROOT, BASE)
    ancestor(result["tested_commit"], BASE)
    assert sha(path) == entry_by_task[task]["result_sha256"]
    required = set(tasks[task]["review_requirements"])
    review_rows = []
    for kind in required:
        rp = "docs/exec-plans/reviews/" + task + "/" + kind + ".json"
        review = json.loads(git("show", BASE + ":" + rp))
        jsonschema.validate(review, review_schema)
        assert review["status"] == "PASS" and review["task_identity"] == result["task_identity"]
        assert review["review_type"] == kind
        ancestor(result["tested_commit"], review["reviewed_head_sha"])
        suffix(result["tested_commit"], review["reviewed_head_sha"], task, "tested")
        merge = entry_by_task[task]["normal_merge"]
        assert merge in merges and "Merge pull request #" in merge
        parents = git("show", "-s", "--format=%P", merge[:40]).split()
        assert len(parents) == 2
        source = parents[1]
        ancestor(review["reviewed_head_sha"], source)
        assert subprocess.run(["git", "merge-base", "--is-ancestor", review["reviewed_head_sha"], parents[0]], cwd=ROOT).returncode != 0
        review_suffix = suffix(review["reviewed_head_sha"], source, task, "review")
        assert git("show", source + ":" + path) == git("show", review["reviewed_head_sha"] + ":" + path)
        review_rows.append({"path": rp, "sha256": sha(rp), "reviewed_head_sha": review["reviewed_head_sha"],
                            "normal_merge": merge, "source_head": source, "review_suffix": review_suffix})
    report["prerequisites"].append({"task_identity": result["task_identity"], "tested_commit": result["tested_commit"],
        "summary": result["summary"], "requirements_covered": result["requirements_covered"],
        "checks": len(result["commands_run"]), "reviews": review_rows,
        "integration_record_present": exists(BASE, "docs/exec-plans/integrations/" + task + ".json")})
for path in ["docs/exec-plans/completed/KL-027_RESULT.yaml", "docs/exec-plans/completed/KL-027_RESULT.json", "docs/exec-plans/integrations/KL-027.json"]:
    assert not exists(BASE, path)
assert not git("ls-tree", "-r", "--name-only", BASE, "docs/exec-plans/reviews/KL-027")
m2 = json.loads(git("show", BASE + ":docs/exec-plans/milestones/M2.json"))
assert m2["closure_status"] == "PASS" and m2["milestone_identity"] == "harness-backlog-v0.2/M2"
ancestor(m2["evaluated_commit"], BASE)
for row in m2["integrations"]:
    assert sha(row["integration_record"]) == row["sha256"]
report["m2"] = {"closure_status": "PASS", "evaluated_commit": m2["evaluated_commit"], "integration_hashes_verified": len(m2["integrations"])}
result = yaml.safe_load((ROOT / "docs/exec-plans/completed/KL-027_RESULT.yaml").read_text())
jsonschema.validate(result, result_schema)
assert not validator.semantic_result_errors(result, tasks["KL-027"], ROOT, REVIEWED)
assert result["base_commit"] == BASE and result["tested_commit"] == TESTED
assert result["requirements_covered"] == [] and result["integration_status"] == "UNMERGED"
report["tested_suffix"] = suffix(TESTED, REVIEWED, "KL-027", "tested")
scope = {"tests/db/test_test_only_demo.py", "tests/unit/protocol/test_test_only_demo.py", "docs/contracts/test_only_demo.md"}
changed = git("diff", "--name-only", BASE, REVIEWED).splitlines()
assert set(changed) == set(result["files_changed"])
for path in changed:
    assert path in scope or path == "docs/exec-plans/completed/KL-027_RESULT.yaml" or path.startswith(("docs/exec-plans/evidence/KL-027/", "docs/exec-plans/reviews/KL-027/")), path
for path in scope:
    assert git("rev-parse", TESTED + ":" + path) == git("rev-parse", REVIEWED + ":" + path)
whitespace = subprocess.run(["git", "diff", "--check", BASE, REVIEWED], cwd=ROOT, capture_output=True, text=True)
report["full_diff_whitespace_observations"] = whitespace.stdout.splitlines()
assert all(line.startswith("docs/exec-plans/evidence/KL-027/checks-e78a59b/demo_suite_e2e.") for line in whitespace.stdout.splitlines() if not line.startswith("+"))
assert not git("diff", "--check", BASE, REVIEWED, "--", *sorted(scope))
report["changed_paths"] = changed
packet = (ROOT / "docs/exec-plans/active/KL-027.md").read_text()
contracts = json.loads(re.search(r"```json\n(.*?)\n```", packet, re.S).group(1))["check_contracts"]
expected = {c["check_id"]: c for c in contracts}
checks = json.loads((ROOT / "docs/exec-plans/evidence/KL-027/checks-72a9a5f/checks.json").read_text())
assert checks["tested_commit"] == TESTED and checks["root"] == str(ROOT)
root_hash = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
compose = "kineticloop-kl027-demo-" + TESTED[:7] + "-" + root_hash
database = compose.replace("-", "_")
assert checks["compose"] == compose and checks["database"] == database
assert len(checks["checks"]) == len(expected) == 12
report["checks"] = []
witness_by_check = {}
for check in checks["checks"]:
    assert check["command"] == expected[check["check_id"]]["command"]
    assert check["result"] == "PASS" and check["exit_code"] == 0
    assert sha(check["evidence_ref"]) == check["log_sha256"]
    log = (ROOT / check["evidence_ref"]).read_text()
    header = json.loads(log.splitlines()[0])
    assert header["tested_commit"] == TESTED and header["command"] == check["command"]
    assert header["resolved_root"] == str(ROOT) and header["oracle"] == expected[check["check_id"]]["pass_oracle"]
    witnesses = [json.loads(s.split("FIXTURE_EVIDENCE ", 1)[1]) for s in log.splitlines() if "FIXTURE_EVIDENCE " in s]
    witness_by_check[check["check_id"]] = witnesses
    parsed_counts = None
    if check["junit_ref"]:
        xml = ET.parse(ROOT / check["junit_ref"])
        suites = list(xml.getroot().iter("testsuite"))
        parsed_counts = {k: sum(int(s.get(k, "0")) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
        assert parsed_counts == check["counts"] and parsed_counts["tests"] > 0
        assert all(parsed_counts[k] == 0 for k in ("failures", "errors", "skipped"))
        assert len(list(xml.getroot().iter("testcase"))) == parsed_counts["tests"]
        assert re.search(r"\b" + str(parsed_counts["tests"]) + r" passed\b", log)
    report["checks"].append({"check_id": check["check_id"], "command": check["command"], "log_sha256": sha(check["evidence_ref"]),
        "junit_sha256": sha(check["junit_ref"]) if check["junit_ref"] else None, "counts": parsed_counts,
        "witness_counts": dict(Counter(w["kind"] for w in witnesses))})
for name, marker in [("harness_validation_passes", "HARNESS_CHECK_PASS"), ("lint_passes", "All checks passed!"), ("typecheck_passes", "Success: no issues found")]:
    assert marker in (ROOT / ("docs/exec-plans/evidence/KL-027/checks-72a9a5f/" + name + ".log")).read_text()
witnesses = witness_by_check["demo_suite_e2e"]
counts = Counter(w["kind"] for w in witnesses)
assert counts["namespace"] == counts["cleanup"] == 61
assert counts["trusted_post_lock_expiry_DC"] == counts["blocked"] == 4
report["suite_witness_counts"] = dict(counts)
timing = []
audited_persisted = 0
certificates = 0
inherited_audit_attributes = []
for w in witnesses:
    if w["kind"] == "namespace":
        assert w["tested_commit"] == TESTED and w["compose"] == compose and w["database"] == database
        assert w["resolved_root"] == str(ROOT) and w["migration"] == "e8c2f1a6b904"
    if w["kind"] == "cleanup":
        assert w["compose"] == compose and w["database"] == database
        assert w["inventory"] == ["bootstrap_two_phase(selected_lifecycle)", "reset", "start", "destroy"]
        assert not any(w["remaining"].values()) and w["elapsed"] < 120
    if w["kind"] == "trusted_post_lock_expiry_DC":
        times = [datetime.fromisoformat(w[k]) for k in ("trusted_before_wait", "trusted_blocked_at", "source_end", "trusted_after")]
        assert times[0] <= times[1] < times[2] < times[3]
        assert w["observed_lock"][1] and w["observed_lock"][3] == w["trusted_blocked_at"] and w["zero_effects"]
        assert "expired" in w["actual_guard"] if w["operation"] == "T6" else "TIME_INELIGIBLE" in w["actual_guard"]
        timing.append(w)
    if w["kind"] == "exact_zero_effect_denial":
        assert w["intended_cause"] and w["intended_cause"] in w["actual_cause"]
    if w["kind"] == "historical_identity_only":
        assert w["zero_effects"] and w["start"]["replayed"] and not w["start"]["executable"]
        assert w["bundle"]["replayed"] and not w["bundle"]["executable"]
    if w["kind"] in ("output", "full_output"):
        assert digest(w["payload"]) == w["hash"]
    persisted = w.get("persisted")
    if not isinstance(persisted, dict) or "command_receipts" not in persisted:
        continue
    audited_persisted += 1
    receipts, events, outbox = [[r[0] for r in persisted[k]] for k in ("command_receipts", "domain_events", "outbox_deliveries")]
    assert len(receipts) == len(events) == len(outbox)
    for r in receipts:
        assert r["status"] == "SUCCEEDED"
        linked = [e for e in events if e["ref_s02_id"] == r["id"]]
        assert len(linked) == 1 and len([o for o in outbox if o["ref_s03_id"] == linked[0]["id"]]) == 1
    frows = {r[0]["id"]: r[0] for r in persisted["proposal_revisions"]}
    for item in persisted["prescription_demand_features"]:
        d = item[0]
        assert d["ref_s34_id"] in frows and d["basis_hash"] == frows[d["ref_s34_id"]]["content_hash"]
        assert d["feature_hash"] == d["content_hash"] == digest(d["typed_payload"])
    drows = {r[0]["id"]: r[0] for r in persisted["prescription_demand_features"]}
    for n in frows.values():
        if n["proposal_kind"] != "NUTRITION":
            continue
        body = n["typed_payload"]
        assert n["demand_feature_id"] == body["demand_id"] and body["demand_id"] in drows
        assert body["fitness_id"] in frows
        assert body["fitness_hash"] == frows[body["fitness_id"]]["content_hash"]
        assert body["demand_hash"] == drows[body["demand_id"]]["content_hash"]
        assert drows[body["demand_id"]]["ref_s34_id"] == body["fitness_id"]
        assert n["content_hash"] == digest(body)
    resolutions = {r[0]["id"]: r[0] for r in persisted["evidence_resolutions"]}
    validations = {r[0]["id"]: r[0] for r in persisted["validation_results"]}
    prescriptions = {r[0]["id"]: r[0] for r in persisted["prescription_revisions"]}
    for item in persisted["authorization_issuances"]:
        a = item[0]
        c = a["validity_certificate"]
        assert c["closure_digest"] == digest(c["dependencies"])
        assert datetime.fromisoformat(a["valid_until"]) == min(datetime.fromisoformat(d["valid_until"]) for d in c["dependencies"] if d.get("valid_until"))
        p = prescriptions[a["ref_s40_id"]]
        r = resolutions[a["ref_s36_id"]]
        v = validations[a["ref_s37_id"]]
        assert p["content_hash"] == digest(p["typed_payload"]) == a["bound_content_hash"]
        assert r["action_type"] == p["prescription_kind"]
        assert r["action_parameters_hash"] == digest(p["typed_payload"])
        bindings = v["typed_payload"]["action_bindings"]
        assert [b["action_type"] for b in bindings] == ["TRAINING", "NUTRITION"]
        action_binding = next(b for b in bindings if b["action_type"] == p["prescription_kind"])
        assert action_binding["resolution_id"] == r["id"] and action_binding["resolution_hash"] == r["content_hash"]
        assert action_binding["proposal_id"] == p["ref_s34_id"] and action_binding["proposal_hash"] == frows[p["ref_s34_id"]]["content_hash"]
        assert {d["identity"] for d in c["dependencies"] if d["dependency_kind"] == "EVIDENCE_RESOLUTION"} == {b["resolution_id"] for b in bindings}
        demand_dependency = next(d for d in c["dependencies"] if d["dependency_kind"] == "DEMAND_FEATURE")
        d = drows[demand_dependency["identity"]]
        if demand_dependency["proposal_id"] != d["ref_s34_id"]:
            inherited_audit_attributes.append({"authorization": a["id"], "demand": d["id"],
                "physical_fitness": d["ref_s34_id"], "audit_proposal": demand_dependency["proposal_id"],
                "validation_nutrition_anchor": v["ref_s34_id"]})
            assert demand_dependency["proposal_id"] == v["ref_s34_id"]
        certificates += 1
assert {w["operation"] for w in timing} == {"T6", "START", "CONTINUE", "RESUME"}
report["temporal_witnesses"] = timing
report["persisted_snapshots_independently_audited"] = audited_persisted
report["certificate_instances_independently_audited"] = certificates
report["inherited_demand_audit_attribute_instances"] = inherited_audit_attributes
report["namespace"] = {"compose": compose, "database": database, "resolved_root_digest": root_hash}
tree = ast.parse((ROOT / "tests/db/test_test_only_demo.py").read_text())
report["dynamic_imports"] = [ast.unparse(n) for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == "load"]
assert len(report["dynamic_imports"]) == 2
report["status"] = "PASS"
(OUT / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"status": "PASS", "reviewed_head_sha": REVIEWED, "prerequisites": len(report["prerequisites"]),
    "raw_checks": len(report["checks"]), "suite_witness_counts": dict(counts),
    "persisted_snapshots": audited_persisted, "certificates": certificates, "namespace": report["namespace"]}, indent=2))
