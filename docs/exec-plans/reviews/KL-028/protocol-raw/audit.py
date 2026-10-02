"""Independent read-only verification of the exact KL028 protocol evidence."""
import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]
BASE = "9268fc8dd8c071c02dc5c698274dbf6fcd112776"
TESTED = "debd5e58f98b4b20a2dd1ae132799d2373797622"
REVIEWED = "994cf425360c75a366f186e91857a5d75ed02ebe"
def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
def read(path):
    return (ROOT / path).read_text()
def rows(state, name):
    return [r[0] for r in state[name]]
assert git("rev-parse", "HEAD") == REVIEWED
assert git("merge-base", BASE, REVIEWED) == BASE
assert git("merge-base", TESTED, REVIEWED) == TESTED
changed = git("diff", "--name-only", BASE, REVIEWED).splitlines()
allowed = {"tests/db/test_boundary_acceptance.py", "tests/unit/protocol/test_boundary_acceptance.py", "docs/contracts/boundary_acceptance.md", "docs/exec-plans/completed/KL-028_RESULT.yaml"}
assert all(p in allowed or p.startswith("docs/exec-plans/evidence/KL-028/") for p in changed)
after_tested = git("diff", "--name-only", TESTED, REVIEWED).splitlines()
assert all(p == "docs/exec-plans/completed/KL-028_RESULT.yaml" or p.startswith("docs/exec-plans/evidence/KL-028/") for p in after_tested)
prerequisites = []
for task in ("KL-021", "KL-022", "KL-023", "KL-027"):
    integration = json.loads(git("show", BASE + ":docs/exec-plans/integrations/" + task + ".json"))
    merge = integration["merge_commit"]
    assert integration["task_identity"] == "harness-backlog-v0.2/" + task
    assert integration["integration_status"] == "MERGED"
    assert git("merge-base", merge, BASE) == merge
    assert len(git("rev-list", "--parents", "-n", "1", merge).split()) == 3
    implementation = integration["reviewed_head_sha"]
    record = integration["review_record_commit"]
    assert git("merge-base", implementation, record) == implementation
    suffix = git("diff", "--name-only", implementation, record).splitlines()
    assert all(p.startswith("docs/exec-plans/reviews/" + task + "/") for p in suffix)
    reviews = []
    for kind in ("GENERAL", "PROTOCOL", "DB_CONCURRENCY"):
        review = json.loads(git("show", record + ":docs/exec-plans/reviews/" + task + "/" + kind + ".json"))
        assert review["status"] == "PASS" and review["reviewed_head_sha"] == implementation
        reviews.append(kind)
    prerequisites.append({"task": task, "normal_merge": merge, "ancestor_of_base": True, "reviews": reviews})
index = json.loads(read("CURRENT_DOCUMENT_INDEX.json"))
for row in index["documents"] + index["machine_readable"]:
    assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row["sha256"]
packet = read("docs/exec-plans/active/KL-028.md")
blocks = re.findall(r"```json\n(.*?)\n```", packet, re.S)
contracts = json.loads(blocks[0])["check_contracts"]
layers = json.loads(blocks[-1])
result = yaml.safe_load(read("docs/exec-plans/completed/KL-028_RESULT.yaml"))
assert result["base_commit"] == BASE and result["tested_commit"] == TESTED
obligations = {f"{b['requirement_id']}@{layer}" for b in json.loads(read("KineticLoop_Acceptance_Spec_v1.2.2.json"))["supplemental_boundary_requirements"] for layer in b["layers"]}
assert len(obligations) == 31 == len(result["requirements_covered"]) == len(layers)
assert obligations == {r["requirement_id"] for r in result["requirements_covered"]}
for layer, actual in zip(layers, result["requirements_covered"], strict=True):
    assert actual["requirement_id"] == layer["requirement_id"] + "@" + layer["layer"]
    assert actual["status"] == ("PASS" if layer["disposition"] == "KL028_PLANNED_EXECUTABLE" else "NOT_RUN")
    if actual["status"] == "NOT_RUN":
        assert actual["reason"] and actual["required_future_owner"]
checks = json.loads(read("docs/exec-plans/evidence/KL-028/checks-debd5e5/checks.json"))
assert checks["tested_commit"] == TESTED
digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
assert checks["database"] == "kineticloop_kl028_boundary_debd5e5_" + digest
assert checks["compose"] == "kineticloop-kl028-boundary-debd5e5-" + digest
check_report = []
for contract, check, command in zip(contracts, checks["checks"], result["commands_run"], strict=True):
    assert check["check_id"] == contract["check_id"] == command["check_id"]
    assert check["command"] == contract["command"] == command["command"]
    assert check["exit_code"] == 0 and check["result"] == command["result"] == "PASS"
    log = read(check["evidence_ref"])
    assert hashlib.sha256(log.encode()).hexdigest() == check["log_sha256"]
    header = json.loads(log.splitlines()[0])
    assert header["tested_commit"] == TESTED and header["oracle"] == contract["pass_oracle"]
    assert header["command"] == contract["command"]
    if check["junit_ref"]:
        suites = list(ET.fromstring(read(check["junit_ref"])).iter("testsuite"))
        counts = {k: sum(int(s.get(k, "0")) for s in suites) for k in ("tests", "errors", "failures", "skipped")}
        assert counts == check["counts"] and counts["tests"] > 0
        assert counts["errors"] == counts["failures"] == counts["skipped"] == 0
    evidence = [json.loads(l.split(" ", 1)[1]) for l in log.splitlines() if l.startswith("FIXTURE_EVIDENCE ")]
    kinds = Counter(w["kind"] for w in evidence)
    for w in evidence:
        kind = w["kind"]
        if kind in {"owned_namespace", "exact_owned_cleanup"}:
            assert w["tested_commit"] == TESTED and w["database"] == checks["database"] and w["compose"] == checks["compose"]
        if kind == "exact_owned_cleanup":
            assert w["remaining"] == {"container": "", "volume": "", "network": ""}
        if kind == "exact_guard_zero_effect":
            assert w["intended"] in w["cause"] and w["before"] == w["after"] and w["global_before"] == w["global_after"]
        if kind == "observed_real_race":
            assert w["winner"] in w["blocked"][0]
            if w["zero_effects_after_winner"]:
                assert w["winner_uncommitted_history"] == w["after_loser"]
            for trace in w["traces"]:
                if trace["command"] in {"PublishManifest", "CommitBundle", "StartSession"}:
                    assert [t[1] for t in trace["trace"][:2]] == ["S51", "S01"]
        if kind == "registered_transitive_graph":
            graph = w["graph"]
            assert [graph["a"], graph["b"]] in w["actual_edges"] and [graph["b"], graph["c"]] in w["actual_edges"]
        if kind == "Reauthorize_registry_guard_support_only":
            assert w["full_B04_DC"] == "NOT_RUN"
        if kind == "DC_support_only_registry_fault_STOP":
            assert w["B14_WF"] == w["B14_E2E"] == "NOT_RUN" and w["global_before"] == w["global_after"]
        if kind == "actual_gate_timeout_STOP_support":
            assert w["before"] == w["after"]
        if kind == "effective_at_audit_only":
            assert w["history"] == w["after"]
            assert (datetime.fromisoformat(w["result"]["effective_at"]) > datetime.fromisoformat(w["result"]["recorded_at"])) == w["future"]
        if kind == "rollback_complete_global_zero_effect_positive_owner":
            assert w["before"] == w["after"]
        if kind == "server_exact_minimum_full_certificate":
            for issuance in rows(w["persisted"], "authorization_issuances"):
                entries = issuance["validity_certificate"]["dependencies"]
                end = datetime.fromisoformat(issuance["valid_until"])
                assert end == min(datetime.fromisoformat(e["valid_until"]) for e in entries if e.get("valid_until"))
                assert datetime.fromisoformat(w["trusted_before"]) <= datetime.fromisoformat(issuance["valid_from"]) < datetime.fromisoformat(w["trusted_after"])
                assert hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(",",":")).encode()).hexdigest() == issuance["validity_certificate"]["closure_digest"]
                closure = {e["identity"] for e in entries if e["dependency_kind"] == "ARTIFACT"}
                assert closure == {e["artifact_id"] for e in rows(w["persisted"], "authorization_artifact_closure") if e["authorization_id"] == issuance["id"]}
    if "tests/db/test_boundary_acceptance.py" in check["command"]:
        assert kinds["owned_namespace"] == kinds["exact_owned_cleanup"] == check["counts"]["tests"]
    check_report.append({"check_id": check["check_id"], "counts": check["counts"], "raw_sha256": check["log_sha256"], "witness_counts": dict(kinds)})
report = {"reviewed_head_sha": REVIEWED, "tested_commit": TESTED, "base_commit": BASE, "source_tree_unchanged_after_tested": True, "authority_hashes_verified": True, "prerequisites": prerequisites, "all_29_packet_commands_oracles_hashes_counts_verified": True, "layers": [{"obligation": r["requirement_id"], "status": r["status"]} for r in result["requirements_covered"]], "layer_counts": dict(Counter(r["status"] for r in result["requirements_covered"])), "checks": check_report, "limitations": ["Read-only inspection of submitted DC raw evidence; no DB lifecycle or foreign fixture executed.", "Independent pure suite rerun runs at reviewed HEAD; it is review evidence, not replacement task evidence."]}
(Path(__file__).parent / "audit.json").write_text(json.dumps(report,indent=2) + "\n")
print(json.dumps({"status": "PASS", "checks": len(check_report), "layers": report["layer_counts"], "reviewed_head_sha": REVIEWED}))
