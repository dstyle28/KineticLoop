"""Read-only, revision-bound security review; never opens a database or network."""
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[5]
BASE = "034d6301316d0dade784a61b159c027b83fbce3a"
TESTED = "f85277e27ab5393b7f77b6fea25d4197294d3153"
REVIEWED = "275d7f849b31c9fe123c8d8594b88a85d1c25355"
PREFIX = f"docs/exec-plans/evidence/KL-080/HG049-{TESTED}/"
sys.path[:0] = [str(ROOT / "tools/harness"), str(ROOT / "src")]
import compact_evidence as ce
from kineticloop.contracts.commands import CommitBundle
from kineticloop.protocol.execution import command_digest, digest


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def rows(snapshot, table):
    return [x[0] for x in snapshot[table]]


def one(snapshot, table):
    result = rows(snapshot, table)
    assert len(result) == 1
    return result[0]


for older, newer in [(BASE, TESTED), (TESTED, REVIEWED)]:
    git("merge-base", "--is-ancestor", older, newer)
suffix = git("diff", "--name-only", TESTED, REVIEWED).decode().splitlines()
assert all(x == "docs/exec-plans/completed/KL-080_RESULT.yaml" or x.startswith(PREFIX) for x in suffix)
paths = git("ls-tree", "-r", "--name-only", REVIEWED, "--", PREFIX).decode().splitlines()
captures = {p: ce.read(ROOT, p, REVIEWED, tested=TESTED) for p in paths if p.endswith(".capture.json")}
checks = json.loads(ce.blob(ROOT, PREFIX + "final-checks.json", REVIEWED))
counts = {}
for check in checks["executions"]:
    raw = ce.read(ROOT, check["stdout"]["path"], REVIEWED, tested=TESTED,
                  command=check["command"], exit_code=0)
    assert b"EXIT_CODE=0" in raw
    if "junit" in check:
        xml = ET.fromstring(captures[check["junit"]["path"]])
        cases = xml.findall(".//testcase")
        assert len(cases) == check["counts"]["executed"] > 0
        assert not any(case.find(k) is not None for case in cases for k in ("failure", "error", "skipped"))
        counts[check["check_id"]] = len(cases)
assert len(checks["executions"]) == 17
witnesses = []
for n, line in enumerate(captures[PREFIX + "source_suite_dc.stdout.capture.json"].decode().splitlines(), 1):
    if "SOURCE_EVIDENCE " in line:
        witnesses.append((n, json.loads(line.split("SOURCE_EVIDENCE ", 1)[1])))
kind_counts = dict(collections.Counter(x["kind"] for _, x in witnesses))
assert kind_counts["kl080_namespace"] == kind_counts["kl080_cleanup"] == 106
for _, x in witnesses:
    if x["kind"] == "kl080_cleanup":
        assert not any(x["remaining"].values())

line, mechanical = next((n, x) for n, x in witnesses if x["kind"] == "kl080_mechanical_s37_legacy_consumer_denial")
b = mechanical["before"]
assert b == mechanical["after"]
command = CommitBundle.model_validate_json(json.dumps(mechanical["command"]))
assert command.request_hash == command_digest(command)
state, intent, request, validation = [one(b, t) for t in
    ("user_decision_state", "planning_intents", "planning_request_revisions", "validation_results")]
assert command.subject_id == state["subject_id"] == intent["subject_id"]
assert command.manifest_id == state["current_manifest_id"]
assert command.policy_id == state["active_policy_bundle_id"]
assert command.expected_generation == state["decision_generation"]
assert command.expected_authorization_epoch == state["authorization_epoch"]
assert command.execution_basis_event_id == state["execution_basis_event_id"]
assert command.intent_id == intent["id"] and command.attempt_id == intent["current_attempt_id"]
assert command.expected_owner_id == command.actor.identity_id
assert f"{command.actor.role}:{command.expected_owner_id}" == intent["lease_owner"]
assert command.expected_fence == intent["fence_token"]
assert command.expected_request_revision == request["request_revision"]
assert command.validation_id == validation["id"] and validation["result"] == "PASS"
assert digest(validation["typed_payload"]) == validation["content_hash"]
nutrition = next(r for r in rows(b, "proposal_revisions") if r["id"] == validation["ref_s34_id"])
assert command.result_fingerprint == digest({"proposal_id": nutrition["id"], "proposal_hash": nutrition["content_hash"], "validation_id": validation["id"]})
assert command.artifact_dependency_closure_hash == one(b, "decision_manifests")["typed_payload"]["artifact_dependency_closure_hash"]
assert mechanical["reached"][0]["first_use_head"]["head_revision"] == 0
assert mechanical["reached"][0]["first_use_head"]["current_bundle_revision_id"] is None
for table in ("daily_plan_heads", "daily_bundle_revisions", "prescription_revisions", "authorization_issuances", "execution_bindings", "workout_sessions"):
    assert not b[table]
trace = [x for x in mechanical["guard_trace"] if x["command"] == "CommitBundle"]
for guard in ("require_test_execution_ingress", "require_current_fence", "lock_daily_head"):
    assert any(x["guard"] == guard and x["status"] == "PASSED" for x in trace)
assert mechanical["actual_cause"] == "policy, demand, and calendar authorization bounds must exist"
assert trace[-1]["guard"] == "prepare_authorization_basis" and trace[-1]["status"] == "DENIED"

prior_line, prior = next((n, x) for n, x in witnesses if x["kind"] == "kl080_prior_deployment_earlier_denial")
assert prior["protected_revision"] == BASE
for path, sha in prior["verified_blobs"].items():
    assert hashlib.sha256(git("show", BASE + ":" + path)).hexdigest() == sha
assert prior["reached"] == ["_progress_sources -> _verify_full_progress"]
assert prior["no_later_freshness_claim"]
assert one(prior["immutable_rows"], "admission_decisions")["decision"] == "ADMITTED"
assert one(prior["immutable_rows"], "event_association_decisions")["association_state"] == "CONFIRMED"
assert any(x["guard"] == "require_test_execution_ingress" and x["status"] == "PASSED" for x in prior["guard_trace"])
assert any(x["guard"] == "require_current_fence" and x["status"] == "PASSED" for x in prior["guard_trace"])

full_line, full = next((n, x) for n, x in witnesses if x["kind"] == "kl080_owner_trajectory")
s = full["persisted"]
assert len(s["authorization_issuances"]) == len(s["prescription_revisions"]) == 2
assert len(s["execution_bindings"]) == 4
assert len(s["workout_sessions"]) == 2
assert {m["action_type"] for m in full["result"]["members"]} == {"TRAINING", "NUTRITION"}
assert len({m["resolution_id"] for m in full["result"]["members"]}) == 2
assert len({m["validation_id"] for m in full["result"]["members"]}) == 1
for member in full["result"]["members"]:
    authorization = next(a for a in rows(s, "authorization_issuances") if a["id"] == member["authorization_id"])
    prescription = next(a for a in rows(s, "prescription_revisions") if a["id"] == member["prescription_id"])
    assert authorization["ref_s40_id"] == prescription["id"]
    assert authorization["ref_s36_id"] == member["resolution_id"]
    assert authorization["ref_s37_id"] == member["validation_id"]
    assert prescription["content_hash"] == digest(prescription["typed_payload"]) == member["content_hash"]
    bindings = [a for a in rows(s, "execution_bindings") if a["ref_s40_id"] == prescription["id"]]
    assert {(a["binding_kind"], a["binding_revision"]) for a in bindings} == {("START", 1), ("RESUME", 2)}
    assert len({a["ref_s44_id"] for a in bindings}) == 1
    assert all(a["execution_scope"] == "TEST_ONLY" and a["ref_s42_id"] == authorization["id"] for a in bindings)
assert collections.Counter(a["command_kind"] for a in rows(s, "command_receipts"))["ContinueSession"] == 2
for table in ("command_receipts", "domain_events", "outbox_deliveries"):
    assert len(s[table]) == 28

hosted = json.loads(captures[PREFIX + "hosted.manifest.json.capture.json"])
assert hosted["tested_commit"] == TESTED and hosted["status"] == "PASS"
assert hosted["junit"] == {"tests": 780, "errors": 0, "failures": 0, "skipped": 0}
assert not hosted["remaining_containers"] and not hosted["remaining_volumes"]
assert len(ET.fromstring(captures[PREFIX + "hosted.database.xml.capture.json"]).findall(".//testcase")) == 780

patterns = {
    "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "openai_key": r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}",
    "github_token": r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})",
    "bearer": r"Bearer [A-Za-z0-9._-]{15,}",
    "credential_postgres_url": r"postgres(?:ql)?://[^\s/]+:[^\s@]+@",
}
scan = {name: sum(len(re.findall(expr, data.decode(errors="replace"))) for data in captures.values()) for name, expr in patterns.items()}
assert not any(scan.values())
verification = {
    "task_identity": "harness-backlog-v0.2/KL-080", "reviewed_head_sha": REVIEWED,
    "tested_commit": TESTED, "protected_base": BASE, "read_only_no_database_or_network": True,
    "capture_count": len(captures), "referenced_raw_bytes": sum(map(len, captures.values())),
    "raw_testcase_counts": counts, "witness_counts": kind_counts,
    "mechanical_raw_line": line, "mechanical_request_digest_hash_bindings_zero_effects": "PASS",
    "prior_deployment_raw_line": prior_line, "verified_prior_blobs": len(prior["verified_blobs"]),
    "prior_deployment_earlier_guard": "PASS", "full_owner_raw_line": full_line,
    "full_exact_members_test_bindings_bookkeeping": "PASS", "hosted_cases": 780,
    "secret_pattern_matches": scan,
    "sensitive_content_classification": "No actual provider/health-person records or non-test credentials identified. Test-redaction strings/node IDs and fixture source snippets are present; incidental workspace login/path, repo/CI and runner metadata are present. Pattern scanning is supplementary, not a complete DLP guarantee or external-write authorization.",
}
output = Path(__file__).with_name("verification.json")
output.write_text(json.dumps(verification, indent=2) + "\n")
print(json.dumps(verification, indent=2))
