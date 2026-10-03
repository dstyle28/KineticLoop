"""Read-only, exact-revision protocol evidence review; no DB lifecycle."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from tools.harness.compact_evidence import audit, blob, read  # noqa: E402

BASE = "034d6301316d0dade784a61b159c027b83fbce3a"
REVIEWED = "275d7f849b31c9fe123c8d8594b88a85d1c25355"
TESTED = "f85277e27ab5393b7f77b6fea25d4197294d3153"
PREFIX = "docs/exec-plans/evidence/KL-080/HG049-" + TESTED + "/"


def raw(name: str) -> bytes:
    return read(ROOT, PREFIX + name, REVIEWED, tested=TESTED, exit_code=0)


def rows(record: dict, table: str) -> list[dict]:
    return [r[0] for r in record[table]]


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> dict:
    summary = {"base_commit": BASE, "tested_commit": TESTED, "reviewed_head_sha": REVIEWED}
    final = json.loads(blob(ROOT, PREFIX + "final-checks.json", REVIEWED))
    checks = final["executions"]
    assert len(checks) == 17
    for check in checks:
        assert check["tested_commit"] == TESTED and check["result"] == "PASS"
        for key in ("stdout", "junit", "collection.log", "collection.json", "execution_record"):
            if key not in check:
                continue
            ref = check[key]
            data = read(ROOT, ref["path"], REVIEWED, tested=TESTED, exit_code=0)
            assert hashlib.sha256(data).hexdigest() == ref["raw_sha256"]
            assert len(data) == ref["raw_bytes"]
            if key == "junit":
                xml = ElementTree.fromstring(data)
                cases = xml.findall(".//testcase")
                assert cases and len(cases) == check["counts"]["executed"]
                assert not xml.findall(".//failure") + xml.findall(".//error") + xml.findall(".//skipped")
        assert all(check.get("counts", {}).get(k, 0) == 0 for k in ("failures", "errors", "skipped"))
    summary["task_command_counts"] = {c["check_id"]: c.get("counts", {}).get("executed") for c in checks}
    log = raw("source_suite_dc.stdout.capture.json")
    evidence = [json.loads(line.split("SOURCE_EVIDENCE ", 1)[1]) for line in log.decode().splitlines() if "SOURCE_EVIDENCE " in line]
    summary["raw_suite_sha256"] = hashlib.sha256(log).hexdigest()
    summary["witness_counts"] = dict(Counter(r["kind"] for r in evidence))
    namespaces = [r for r in evidence if r["kind"] == "kl080_namespace"]
    cleanups = [r for r in evidence if r["kind"] == "kl080_cleanup"]
    assert len(namespaces) == len(cleanups) == 106
    assert all(r["tested_commit"] == TESTED and r["migration"] == "e8c2f1a6b904" for r in namespaces)
    assert all(not any(r["remaining"].values()) for r in cleanups)
    trajectory = next(r for r in evidence if r["kind"] == "kl080_owner_trajectory")
    persisted = trajectory["persisted"]
    admission = rows(persisted, "admission_decisions")[0]
    association = rows(persisted, "event_association_decisions")[0]
    fact = rows(persisted, "canonical_fact_revisions")[0]
    assert admission["decision"] == "ELIGIBLE" and association["association_state"] == "MATCHED"
    assert fact["ref_s13_id"] == admission["id"] and fact["typed_payload"]["association_id"] == association["id"]
    assert all(r["command_authority"] == "NONE" and r["trust_class"] == "USER_REPORTED" for r in rows(persisted, "evidence_revisions"))
    proposals = {r["proposal_kind"]: r for r in rows(persisted, "proposal_revisions")}
    fitness, nutrition = proposals["FITNESS"], proposals["NUTRITION"]
    demand = rows(persisted, "prescription_demand_features")[0]
    assert demand["ref_s34_id"] == fitness["id"] and demand["basis_hash"] == fitness["content_hash"]
    assert nutrition["demand_feature_id"] == demand["id"]
    assert nutrition["typed_payload"]["semantic_class"] == "TARGET"
    resolutions = {r["action_type"]: r for r in rows(persisted, "evidence_resolutions")}
    assert set(resolutions) == {"TRAINING", "NUTRITION"}
    assert resolutions["TRAINING"]["id"] != resolutions["NUTRITION"]["id"]
    validation = rows(persisted, "validation_results")[0]
    assert validation["result"] == "PASS" and validation["ref_s34_id"] == nutrition["id"]
    assert validation["ref_s35_id"] == demand["id"]
    for r in [admission, association, fact, fitness, nutrition, demand, validation, *resolutions.values()]:
        assert digest(r["typed_payload"]) == r["content_hash"]
    for binding in validation["typed_payload"]["action_bindings"]:
        resolution = resolutions[binding["action_type"]]
        assert binding["resolution_id"] == resolution["id"]
        assert binding["resolution_hash"] == resolution["content_hash"]
        assert resolution["typed_payload"]["event_association_status"] == "CONFIRMED"
        source = resolution["typed_payload"]["facts"][0]
        assert source["admission_id"] == admission["id"] and source["admission_hash"] == admission["content_hash"]
        assert source["association_id"] == association["id"] and source["association_hash"] == association["content_hash"]
        assert source["fact_id"] == fact["id"] and source["fact_hash"] == fact["content_hash"]
        assert source["scope"] == "TEST_ONLY" and source["semantic_class"] == "ACTUAL_EXECUTION"
    bindings = rows(persisted, "execution_bindings")
    members = trajectory["result"]["members"]
    assert len(members) == 2 and len(bindings) == 4
    member_ids = []
    for member in members:
        issuance = next(r for r in rows(persisted, "authorization_issuances") if r["id"] == member["authorization_id"])
        assert issuance["ref_s40_id"] == member["prescription_id"]
        assert issuance["ref_s36_id"] == member["resolution_id"] == resolutions[member["action_type"]]["id"]
        assert issuance["ref_s37_id"] == member["validation_id"] == validation["id"]
        assert issuance["scope"] == "TEST_ONLY"
        deps = issuance["validity_certificate"]["dependencies"]
        fresh = [d for d in deps if d["dependency_kind"] == "EVIDENCE_ADMISSION_FRESHNESS"]
        assert len(fresh) == 1 and fresh[0]["identity"] == admission["id"] and fresh[0]["revision"] == admission["revision"]
        assert datetime.fromisoformat(issuance["valid_until"]) == min(datetime.fromisoformat(d["valid_until"]) for d in deps if d.get("valid_until"))
        own = [r for r in bindings if r["ref_s42_id"] == issuance["id"]]
        assert {(r["binding_kind"], r["binding_revision"]) for r in own} == {("START", 1), ("RESUME", 2)}
        assert all(r["ref_s40_id"] == member["prescription_id"] and r["execution_scope"] == "TEST_ONLY" for r in own)
        assert len({r["ref_s44_id"] for r in own}) == 1
        member_ids.append({**member, "session_id": own[0]["ref_s44_id"], "binding_ids": [r["id"] for r in own]})
    summary["full_identities"] = {"S13": admission["id"], "S13_revision": admission["revision"], "S12": association["id"], "F": fitness["id"], "D": demand["id"], "N": nutrition["id"], "S36": {a: r["id"] for a, r in resolutions.items()}, "S37": validation["id"], "members": member_ids}
    for command in ("StartSession", "ResumeSession", "ContinueSession"):
        assert sum(r["command"] == command and r["guard"] == "require_execution_authorization" and r["status"] == "PASSED" for r in trajectory["guard_trace"]) == 2
    mechanical = next(r for r in evidence if r["kind"] == "kl080_mechanical_s37_legacy_consumer_denial")
    assert mechanical["before"] == mechanical["after"]
    assert not mechanical["after"]["daily_plan_heads"]
    reached = mechanical["reached"][0]
    assert reached["guard"] == "prepare_authorization_basis" and reached["status"] == "DENIED"
    assert reached["first_use_head"]["current_bundle_revision_id"] is None
    assert reached["first_use_head"]["head_revision"] == 0
    assert reached["untouched_validation"] == rows(mechanical["before"], "validation_results")[0]
    trace = [r for r in mechanical["guard_trace"] if r["command"] == "CommitBundle"]
    for guard in ("require_test_execution_ingress", "require_current_fence", "lock_daily_head"):
        assert any(r["guard"] == guard and r["status"] == "PASSED" for r in trace)
    assert not any(r["guard"] == "require_execution_request" for r in trace)
    summary["mechanical"] = {"cause": reached["cause"], "validation_id": reached["untouched_validation"]["id"], "head_id_observed_then_rolled_back": reached["first_use_head"]["id"], "complete_snapshot_unchanged": True}
    prior = next(r for r in evidence if r["kind"] == "kl080_prior_deployment_earlier_denial")
    assert prior["protected_revision"] == BASE and prior["reached"] == ["_progress_sources -> _verify_full_progress"]
    assert rows(prior["immutable_rows"], "admission_decisions")[0]["decision"] == "ADMITTED"
    assert rows(prior["immutable_rows"], "event_association_decisions")[0]["association_state"] == "CONFIRMED"
    for path, expected in prior["verified_blobs"].items():
        assert hashlib.sha256(blob(ROOT, path, BASE)).hexdigest() == expected
    summary["verified_prior_deployment_blobs"] = len(prior["verified_blobs"])
    hosted = json.loads(raw("hosted.manifest.json.capture.json"))
    xml = ElementTree.fromstring(raw("hosted.database.xml.capture.json"))
    assert len(xml.findall(".//testcase")) == 780
    assert not xml.findall(".//failure") + xml.findall(".//error") + xml.findall(".//skipped")
    summary["hosted_db_cases"] = 780
    summary["hosted_provenance"] = hosted["provenance"]
    frozen = ["05_KineticLoop_Protocol_v1.2_FROZEN.md", "04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md", "FROZEN_BASELINE.json", "CURRENT_REQUIREMENT_SET.json"]
    for path in frozen:
        assert blob(ROOT, path, BASE) == blob(ROOT, path, REVIEWED)
    summary["protected_authorities_unchanged"] = frozen
    diffpaths = subprocess.check_output(["git", "diff", "--name-only", BASE, REVIEWED], cwd=ROOT, text=True).splitlines()
    assert not any(p.startswith(("migrations/", ".github/")) for p in diffpaths)
    summary["runtime_changed_paths"] = [p for p in diffpaths if p.startswith("src/")]
    summary["normal_evidence_budget"] = audit(ROOT, BASE, REVIEWED, "KL-080")
    assert summary["normal_evidence_budget"]["errors"]
    summary["verification_status"] = "PASS_PROTOCOL_CHECKS_NORMAL_GATE_BLOCKED"
    return summary


if __name__ == "__main__":
    result = main()
    (Path(__file__).parent / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("hosted_provenance",)}, indent=2))
