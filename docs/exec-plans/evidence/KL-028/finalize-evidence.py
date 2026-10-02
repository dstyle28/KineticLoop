"""Verify exact packet outputs and write the pre-review result/layer ledger."""
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import jsonschema
import yaml

root = Path(__file__).resolve().parents[4]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
base = "9268fc8dd8c071c02dc5c698274dbf6fcd112776"
directory = Path(__file__).resolve().parent / ("checks-" + head[:7])
checks = json.loads((directory / "checks.json").read_text())
packet = (root / "docs/exec-plans/active/KL-028.md").read_text()
blocks = re.findall(r"```json\n(.*?)\n```", packet, re.S)
contracts = json.loads(blocks[0])["check_contracts"]
layers = json.loads(blocks[-1])
assert checks["tested_commit"] == head and len(checks["checks"]) == 29
assert [r["check_id"] for r in checks["checks"]] == [r["check_id"] for r in contracts]
witness_counts = {}
for record, contract in zip(checks["checks"], contracts, strict=True):
    assert record["command"] == contract["command"] and record["result"] == "PASS" and record["exit_code"] == 0
    log = root / record["evidence_ref"]
    assert hashlib.sha256(log.read_bytes()).hexdigest() == record["log_sha256"]
    lines = log.read_text().splitlines()
    header = json.loads(lines[0])
    assert header["tested_commit"] == head and header["command"] == record["command"] and header["oracle"] == contract["pass_oracle"]
    if record["junit_ref"]:
        suites = list(ET.parse(root / record["junit_ref"]).getroot().iter("testsuite"))
        counts = {k: sum(int(s.get(k, "0")) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
        assert counts == record["counts"] and counts["tests"] > 0 and not any(counts[k] for k in ("failures", "errors", "skipped"))
    witnesses = [json.loads(line.split(" ", 1)[1]) for line in lines if line.startswith("FIXTURE_EVIDENCE ")]
    kinds = Counter(w["kind"] for w in witnesses)
    witness_counts[record["check_id"]] = dict(kinds)
    if "tests/db/test_boundary_acceptance.py" in record["command"]:
        assert kinds["owned_namespace"] == kinds["exact_owned_cleanup"] == record["counts"]["tests"]
        for w in witnesses:
            if w["kind"] in ("owned_namespace", "exact_owned_cleanup"):
                assert w["tested_commit"] == head and w["compose"] == checks["compose"] and w["database"] == checks["database"]
            if w["kind"] == "owned_namespace":
                assert w["migration"] == "e8c2f1a6b904" and w["root"] == str(root)
            if w["kind"] == "exact_owned_cleanup":
                assert w["remaining"] == {"container": "", "volume": "", "network": ""}
assert next(r for r in checks["checks"] if r["check_id"] == "boundary_full_db_suite")["counts"]["tests"] == 64
assert next(r for r in checks["checks"] if r["check_id"] == "boundary_full_unit_suite")["counts"]["tests"] == 7
lookup = {r["check_id"]: r for r in checks["checks"]}
requirements = []
for layer in layers:
    name = layer["requirement_id"] + "@" + layer["layer"]
    item = {"requirement_id": name, "status": "NOT_RUN", "tested_commit": head}
    if layer["disposition"] == "KL028_PLANNED_EXECUTABLE":
        item.update(status="PASS", evidence_ref=lookup[layer["check_id"]]["evidence_ref"], owner=layer["owner"], pass_oracle=layer["pass_oracle"])
    else:
        item.update(reason=layer["reason"], required_future_owner=layer["required_future_owner"])
    requirements.append(item)
assert len(requirements) == 31 and Counter(r["status"] for r in requirements) == {"PASS": 19, "NOT_RUN": 12}
ledger_ref = str((directory / "layer-ledger.json").relative_to(root))
(root / ledger_ref).write_text(json.dumps({"task_identity": "harness-backlog-v0.2/KL-028", "tested_commit": head, "requirements": requirements, "aggregate_product_pass": False, "m3_release_shadow_closure": False}, indent=2) + "\n")
(directory / "oracle-audit.json").write_text(json.dumps({"tested_commit": head, "check_count": 29, "log_hashes_verified": True, "exact_packet_commands_and_oracles_verified": True, "junit_counts_verified": True, "full_db_cases": 64, "full_pu_cases": 7, "zero_skips_failures_errors": True, "exact_owned_migration_namespace_and_empty_cleanup_verified": True, "witness_counts": witness_counts, "layer_status_counts": {"PASS": 19, "NOT_RUN": 12}, "layer_ledger_ref": ledger_ref}, indent=2) + "\n")
result_path = root / "docs/exec-plans/completed/KL-028_RESULT.yaml"
result = {
    "task_identity": "harness-backlog-v0.2/KL-028", "display_task_id": "KL-028", "task_definition_version": "v0.2",
    "base_commit": base, "tested_commit": head, "merge_commit": None, "task_status": "PASS", "task_checks_status": "PASS", "integration_status": "UNMERGED",
    "summary": "Bounded tests-only boundary suite: all 29 exact packet checks pass on tested_commit, including 7 PU and 64 isolated real-PostgreSQL cases with zero skips. All 31 B-layer obligations are explicit: 19 mechanical layers PASS and 12 deferred NOT_RUN. B04 full issuance/registry-guard and B14 fault/STOP checks are support only; no product aggregate, M3, release or shadow-usability closure is inferred.",
    "commands_run": [{k: r[k] for k in ("check_id", "command", "result", "evidence_ref")} for r in checks["checks"]],
    "requirements_covered": requirements,
    "files_changed": [],
    "decisions": [
        "Protected base, normally merged prerequisite ancestry/results/reviews, authority hashes and M2 PASS verified before execution; entry-audit.json is the durable entry witness.",
        "Only three declared implementation paths plus task-owned result/evidence/review records change. Production sources, grants, migrations, lifecycle, shared fixtures, CI and frozen baselines are unchanged.",
        "Every lifecycle and nested bootstrap/cleanup route validates exact KL028 boundary label, runtime HEAD and resolved-root digest before runner calls. Explicit owned URLs, verified current_database/migration head and finite connection/SQL/lock/idle deadlines protect each connection. Every DB case records empty exact-label cleanup inventories.",
        "Merged owners produce every tested seal, projection/build, manifest, full TEST snapshot/F/D/N/resolution/validation, bundle/issuance and execution binding. RegisterArtifact produces A/B/C transitive graph; RevokeArtifact performs actual trusted management writes. No target output seeds, terminal reopening or timestamp overwrite substitutes.",
        "Race evidence observes actual pg_blocking_pids and trusted time using bounded barriers after real owner writes and before commit, in both serial orders. S51 precedes S01. Exact guard causes and complete user/global before/after history establish denial and rollback zero effects.",
        "Owner-issued validity certificates are checked against actual source IDs, revisions and windows, exact server minimum, deterministic dependency order/hash/method and materialized S49 closure. Client extension cannot lengthen authority; half-open equality is separately PU.",
        "B04 existing Reauthorize guard probe intentionally aborts after the actual gate and is never labeled full reauthorization PASS. B14 registry query fault/shared-gate timeout plus independent S01 STOP is DC support only, never WF/E2E PASS.",
        "Exploratory logs preserve task-local assertion/signature corrections and are explicitly non-final evidence. All final task checks ran on the committed implementation tested SHA; result/evidence append precedes fresh independent GENERAL/PROTOCOL/DB_CONCURRENCY reviews. Only own REVIEW_RECORD_ONLY suffix may follow.",
    ],
    "known_limitations": [
        "Twelve exact deferred obligations remain NOT_RUN with owner gaps recorded individually. Task PASS is separate from review PASS, requirement/product PASS and MERGED.",
        "No public API/rendering E2E, pure registry commit-state evaluator, independent worker STOP lane/fault infrastructure or complete full TEST Reauthorize owner is supplied by this tests-only task.",
        "Inherited KL-077 management audit metadata follow-up remains separate; no source or management contract repair is included.",
        "Production auto-activation remains disabled; real-data shadow remains non-executable; planned values never populate actual execution.",
        "Normal merge remains conditional on independent reviews and unchanged final-head hosted quality, merge-gate and PostgreSQL checks; integration is UNMERGED here.",
    ],
    "follow_up_tasks": [{"obligation": r["requirement_id"], "required_future_owner": r["required_future_owner"], "reason": r["reason"]} for r in requirements if r["status"] == "NOT_RUN"],
    "spec_change_request": None,
}
changed = subprocess.check_output(["git", "diff", "--name-only", base], cwd=root, text=True).splitlines()
untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=root, text=True).splitlines()
result["files_changed"] = sorted(set(changed + untracked + [str(result_path.relative_to(root))]))
jsonschema.validate(result, json.loads((root / "THREAD_RESULT.schema.json").read_text()))
result_path.write_text(yaml.safe_dump(result, sort_keys=False, width=110))
print(json.dumps({"tested_commit": head, "checks": 29, "layers": {"PASS": 19, "NOT_RUN": 12}, "result": str(result_path.relative_to(root))}))
