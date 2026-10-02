"""Independent GENERAL review audit. Reads Git-bound task evidence; no DB lifecycle."""
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
import jsonschema

ROOT = Path(__file__).resolve().parents[5]
BASE = "9268fc8dd8c071c02dc5c698274dbf6fcd112776"
TESTED = "debd5e58f98b4b20a2dd1ae132799d2373797622"
REVIEWED = "994cf425360c75a366f186e91857a5d75ed02ebe"
OUT = Path(__file__).parent

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)

def blob(path, rev=REVIEWED):
    entry = git("ls-tree", rev, "--", path).decode().split()
    assert entry and entry[0] in ("100644", "100755") and entry[1] == "blob", path
    return git("show", rev + ":" + path)

def document(path, rev=REVIEWED):
    return json.loads(blob(path, rev))

def ancestor(a, b):
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=ROOT).returncode == 0

assert git("rev-parse", "HEAD").decode().strip() == REVIEWED
assert ancestor(BASE, TESTED) and ancestor(TESTED, REVIEWED)
for path in ("docs/exec-plans/completed/KL-028_RESULT.yaml", "docs/exec-plans/reviews/KL-028", "docs/exec-plans/integrations/KL-028.json"):
    assert not git("ls-tree", BASE, "--", path).strip(), path
implementation = ["tests/db/test_boundary_acceptance.py", "tests/unit/protocol/test_boundary_acceptance.py", "docs/contracts/boundary_acceptance.md"]
assert all(blob(p, TESTED) == blob(p) for p in implementation)
changes = git("diff", "--name-status", TESTED, REVIEWED).decode().splitlines()
assert changes and all(x.startswith("A\tdocs/exec-plans/evidence/KL-028/") or x == "A\tdocs/exec-plans/completed/KL-028_RESULT.yaml" for x in changes)
for c in git("rev-list", TESTED + ".." + REVIEWED).decode().splitlines():
    assert len(git("show", "-s", "--format=%P", c).decode().split()) == 1
changed_paths = git("diff", "--name-only", BASE, REVIEWED).decode().splitlines()
assert all(p in implementation or p.startswith("docs/exec-plans/evidence/KL-028/") or p == "docs/exec-plans/completed/KL-028_RESULT.yaml" for p in changed_paths)
index = document("CURRENT_DOCUMENT_INDEX.json")
authority = []
for item in index["documents"] + index["machine_readable"]:
    assert hashlib.sha256(blob(item["path"])).hexdigest() == item["sha256"], item["path"]
    assert blob(item["path"], BASE) == blob(item["path"]), item["path"]
    authority.append(item["path"])
assert document("docs/exec-plans/milestones/M2.json")["closure_status"] == "PASS"
prerequisites = []
for task in ("KL-021", "KL-022", "KL-023", "KL-027"):
    integration = document(f"docs/exec-plans/integrations/{task}.json", BASE)
    assert integration["integration_status"] == "MERGED"
    assert integration["task_identity"] == "harness-backlog-v0.2/" + task
    merge = integration["merge_commit"]
    assert ancestor(merge, BASE)
    parents = git("show", "-s", "--format=%P", merge).decode().split()
    assert len(parents) == 2 and integration["review_record_commit"] in parents
    result = yaml.safe_load(blob(f"docs/exec-plans/completed/{task}_RESULT.yaml", integration["result_commit"]))
    assert result["task_identity"] == integration["task_identity"] and result["task_status"] == result["task_checks_status"] == "PASS"
    assert ancestor(result["tested_commit"], integration["result_commit"])
    suffix_paths = git("diff", "--name-only", integration["reviewed_head_sha"], integration["review_record_commit"]).decode().splitlines()
    assert suffix_paths and all(p.startswith(f"docs/exec-plans/reviews/{task}/") for p in suffix_paths)
    assert ancestor(integration["reviewed_head_sha"], integration["review_record_commit"])
    for typ in ("GENERAL", "PROTOCOL", "DB_CONCURRENCY"):
        review = document(f"docs/exec-plans/reviews/{task}/{typ}.json", integration["review_record_commit"])
        assert review.get("status", review.get("review_status")) == "PASS"
        assert review["reviewed_head_sha"] == integration["reviewed_head_sha"]
    prerequisites.append({"task":task,"merge":merge,"result_tested_commit":result["tested_commit"],"normal_merge_ancestor":True,"sha_bound_reviews_pass":True})
packet = blob("docs/exec-plans/active/KL-028.md").decode()
blocks = re.findall(r"```json\n(.*?)\n```", packet, re.S)
contracts = json.loads(blocks[0])["check_contracts"]
layers = json.loads(blocks[-1])
acceptance = document("KineticLoop_Acceptance_Spec_v1.2.2.json")["supplemental_boundary_requirements"]
acceptance_layers = {(r["requirement_id"], layer) for r in acceptance for layer in r["layers"]}
assert acceptance_layers == {(r["requirement_id"],r["layer"]) for r in layers}
for layer in layers:
    specification = next(r for r in acceptance if r["requirement_id"] == layer["requirement_id"])
    assert all(layer[k] == specification[k] for k in ("given","when","then"))
result = yaml.safe_load(blob("docs/exec-plans/completed/KL-028_RESULT.yaml"))
jsonschema.validate(result, document("THREAD_RESULT.schema.json"))
assert result["base_commit"] == BASE and result["tested_commit"] == TESTED
assert result["task_status"] == result["task_checks_status"] == "PASS" and result["integration_status"] == "UNMERGED"
assert sorted(result["files_changed"]) == sorted(changed_paths)
directory = "docs/exec-plans/evidence/KL-028/checks-debd5e5/"
checks = document(directory + "checks.json")
assert checks["tested_commit"] == TESTED and len(checks["checks"]) == len(contracts) == 29
root_digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
assert checks["compose"] == "kineticloop-kl028-boundary-debd5e5-" + root_digest
assert checks["database"] == "kineticloop_kl028_boundary_debd5e5_" + root_digest
checked = []
all_witnesses = {}
for record, contract, command in zip(checks["checks"], contracts, result["commands_run"], strict=True):
    assert record["check_id"] == contract["check_id"] == command["check_id"]
    assert record["command"] == contract["command"] == command["command"]
    assert record["result"] == command["result"] == "PASS" and record["exit_code"] == 0
    assert command["evidence_ref"] == record["evidence_ref"]
    raw = blob(record["evidence_ref"])
    assert hashlib.sha256(raw).hexdigest() == record["log_sha256"]
    lines = raw.decode().splitlines()
    header = json.loads(lines[0])
    assert header["tested_commit"] == TESTED and header["oracle"] == contract["pass_oracle"] and header["command"] == contract["command"]
    if record["junit_ref"]:
        suites = list(ET.fromstring(blob(record["junit_ref"])).iter("testsuite"))
        counts = {k:sum(int(x.get(k,"0")) for x in suites) for k in ("tests","failures","errors","skipped")}
        assert counts == record["counts"] and counts["tests"] > 0 and not any(counts[k] for k in ("failures","errors","skipped"))
        cases = [x for s in suites for x in s.findall("testcase")]
        if "::" in contract["command"]:
            selector = contract["command"].split("::")[-1]
            assert all(x.get("name","").split("[")[0] == selector for x in cases)
    witnesses = [json.loads(x.split(" ",1)[1]) for x in lines if x.startswith("FIXTURE_EVIDENCE ") or x.startswith("BOUNDARY_PU ")]
    all_witnesses[record["check_id"]] = witnesses
    labels = Counter(w.get("kind",w.get("label")) for w in witnesses)
    for w in witnesses:
        if w.get("kind") == "exact_guard_zero_effect":
            assert w["intended"] in w["cause"] and w["before"] == w["after"] and w["global_before"] == w["global_after"]
        if w.get("kind") == "observed_real_race":
            assert w["winner"] in w["blocked"][0]
            if w["zero_effects_after_winner"]:
                assert w["winner_uncommitted_history"] == w["after_loser"]
            for trace in w["traces"]:
                if trace["command"] in ("PublishManifest","CommitBundle","StartSession"):
                    assert [x[1] for x in trace["trace"][:2]] == ["S51","S01"]
        if w.get("kind") == "exact_owned_cleanup":
            assert w["remaining"] == {"container":"","volume":"","network":""}
            assert w["tested_commit"] == TESTED and w["compose"] == checks["compose"] and w["database"] == checks["database"]
        if w.get("kind") == "owned_namespace":
            assert w["migration"] == "e8c2f1a6b904" and w["tested_commit"] == TESTED and w["compose"] == checks["compose"] and w["database"] == checks["database"]
        if w.get("kind") == "effective_at_audit_only":
            assert w["history"] == w["after"]
            assert (datetime.fromisoformat(w["result"]["effective_at"]) > datetime.fromisoformat(w["result"]["recorded_at"])) == w["future"]
        if w.get("kind") == "actual_gate_timeout_STOP_support":
            assert w["before"] == w["after"]
        if w.get("kind") == "DC_support_only_registry_fault_STOP":
            assert w["global_before"] == w["global_after"] and w["B14_WF"] == w["B14_E2E"] == "NOT_RUN"
    if "tests/db/test_boundary_acceptance.py" in record["command"]:
        assert labels["owned_namespace"] == labels["exact_owned_cleanup"] == record["counts"]["tests"]
    checked.append({"check_id":record["check_id"],"counts":record["counts"],"hash_header_selector_verified":True,"witness_counts":dict(labels)})
assert checks["checks"][23]["counts"]["tests"] == 64
requirements = result["requirements_covered"]
assert len(requirements) == len(layers) == 31
assert len({x["requirement_id"] for x in requirements}) == 31
for r,l in zip(requirements,layers,strict=True):
    assert r["requirement_id"] == l["requirement_id"] + "@" + l["layer"] and r["tested_commit"] == TESTED
    if l["disposition"] == "KL028_PLANNED_EXECUTABLE":
        assert r["status"] == "PASS" and r["pass_oracle"] == l["pass_oracle"]
    else:
        assert r["status"] == "NOT_RUN" and r["reason"] == l.get("reason",l.get("qualification")) and r["required_future_owner"] == l.get("required_future_owner",l.get("future_owner"))
assert Counter(x["status"] for x in requirements) == {"PASS":19,"NOT_RUN":12}
assert document(directory+"layer-ledger.json")["requirements"] == requirements
snapshot_count = 0
certificate_count = 0
history_loss_count = 0
def dt(x):
    return datetime.fromisoformat(x)
for check_id, witnesses in all_witnesses.items():
    for w in witnesses:
        for value in w.values():
            if not isinstance(value, dict) or "command_receipts" not in value:
                continue
            receipts = [x[0] for x in value["command_receipts"]]
            events = [x[0] for x in value["domain_events"]]
            outbox = [x[0] for x in value["outbox_deliveries"]]
            assert len(receipts) == len(events) == len(outbox)
            for receipt in receipts:
                assert receipt["status"] == "SUCCEEDED"
                linked = [x for x in events if x["ref_s02_id"] == receipt["id"]]
                assert len(linked) == 1
                assert len([x for x in outbox if x["ref_s03_id"] == linked[0]["id"]]) == 1
            snapshot_count += 1
        if w.get("kind") == "registered_transitive_graph":
            g = w["graph"]
            edges = w["actual_edges"]
            assert [g["a"],g["b"]] in edges and [g["b"],g["c"]] in edges and [g["a"],g["c"]] in edges
        if w.get("kind") == "rollback_complete_global_zero_effect_positive_owner":
            assert w["before"] == w["after"] and w["result"]["replayed"] is False
        if w.get("kind") == "lifecycle_valid_fresh_authority_loss":
            assert w["positive"]["executable"] is True and w["positive"]["replayed"] is False
            assert w["non_bearer"]["is_executable"] is True and w["non_bearer"]["non_bearer"] is True
            for table in ("factset_revisions","factset_members","decision_manifests","proposal_revisions","prescription_demand_features","evidence_resolutions","validation_results","daily_bundle_revisions","prescription_revisions","authorization_issuances","authorization_artifact_closure","execution_bindings","workout_sessions"):
                assert w["before"][table] == w["after"][table], table
            assert any(x[0]["binding_kind"] == "START" for x in w["after"]["execution_bindings"])
            history_loss_count += 1
        if w.get("kind") == "server_exact_minimum_full_certificate":
            state = w["persisted"]
            assert len(state["authorization_issuances"]) == 2
            assert {x[0]["action_type"] for x in state["evidence_resolutions"]} == {"TRAINING","NUTRITION"}
            assert len(state["proposal_revisions"]) == 2 and len(state["prescription_demand_features"]) == 1
            assert state["planning_intents"][0][0]["status"] == "FOUND_VALID_PLAN"
            assert state["planning_attempts"][0][0]["status"] == "COMMITTED"
            for row in state["authorization_issuances"]:
                issuance = row[0]
                certificate = issuance["validity_certificate"]
                entries = certificate["dependencies"]
                assert entries == sorted(entries,key=lambda e:(e["dependency_kind"],e["identity"],str(e["revision"])))
                assert certificate["method_version"] == "kl022-v1"
                assert hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(",",":")).encode()).hexdigest() == certificate["closure_digest"]
                assert dt(w["trusted_before"]) <= dt(issuance["valid_from"]) < dt(w["trusted_after"])
                assert dt(issuance["valid_until"]) == min(dt(e["valid_until"]) for e in entries if e.get("valid_until"))
                assert dt(issuance["valid_until"]) <= dt(w["client"])
                by_key = {(e["dependency_kind"],e["identity"]):e for e in entries}
                for table,kind,endfield in (("decision_manifests","MANIFEST","valid_until"),("projection_versions","PROJECTION","valid_until"),("evidence_resolutions","EVIDENCE_RESOLUTION","resolution_expires_at"),("validation_results","VALIDATION_ADMISSION_FRESHNESS","valid_until")):
                    for source_row in state[table]:
                        source = source_row[0]
                        entry = by_key[(kind,source["id"])]
                        assert entry["revision"] == source["revision"] and dt(entry["valid_until"]) == dt(source[endfield])
                        assert dt(entry["valid_from"]) == max(dt(source[k]) for k in ("recorded_at","effective_at","computed_at") if source.get(k))
                assert issuance["ref_s37_id"] == state["validation_results"][0][0]["id"]
                assert issuance["ref_s36_id"] in {x[0]["id"] for x in state["evidence_resolutions"]}
                artifacts = {e["identity"]:e for e in entries if e["dependency_kind"] == "ARTIFACT"}
                closure = [x[0] for x in state["authorization_artifact_closure"] if x[0]["authorization_id"] == issuance["id"]]
                assert {x["artifact_id"] for x in closure} == set(artifacts) == set(state["decision_manifests"][0][0]["typed_payload"]["artifact_closure_ids"])
                for member in closure:
                    e = artifacts[member["artifact_id"]]
                    assert member["artifact_revision"] == e["revision"]
                    assert dt(member["valid_from"]) == dt(e["valid_from"]) and dt(member["valid_until"]) == dt(e["valid_until"])
                certificate_count += 1
assert certificate_count == 48 and history_loss_count == 14  # Individual and full-suite execution records.
summary = {"reviewed_head_sha":REVIEWED,"tested_commit":TESTED,"base_commit":BASE,"implementation_blobs_equal":True,"tested_to_reviewed_new_evidence_result_only":True,"scope_paths_checked":len(changed_paths),"current_authority_hashes_verified":authority,"prerequisites":prerequisites,"all_29_records":checked,"all_31_layers":[{"requirement_id":x["requirement_id"],"status":x["status"]} for x in requirements],"layer_counts":{"PASS":19,"NOT_RUN":12},"db_rerun":False,"audit_status":"PASS"}
summary["independent_persisted_oracles"] = {"receipt_event_outbox_snapshots":snapshot_count,"exact_minimum_full_certificates":certificate_count,"lifecycle_valid_history_loss_records":history_loss_count}
summary["merged_helper_blobs"] = {p:hashlib.sha256(blob(p)).hexdigest() for p in ("tests/db/test_test_only_demo.py","tests/db/test_migrations.py","tests/db/test_full_test_execution.py","tests/db/test_protocol_interleavings.py") if blob(p,BASE) == blob(p)}
assert len(summary["merged_helper_blobs"]) == 4
(OUT / "audit.json").write_text(json.dumps(summary,indent=2)+"\n")
print(json.dumps({"audit_status":"PASS","checks":29,"layers":31,"db_cases":64,"pu_cases":7,"reviewed_head_sha":REVIEWED}))
