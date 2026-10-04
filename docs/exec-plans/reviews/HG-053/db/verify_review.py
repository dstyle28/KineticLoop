"""Independent HG053 DB review: recover evidence only from exact Git revision."""
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[5]
B = "c82e50aefad5c4d9e325d4928a8f96032b81192d"
C = "a75a41edfb1b58828b81053b4ac3afa51457a279"
R = "2936848abed73320db56f71a649e86eca1497502"
PREFIX = "docs/exec-plans/evidence/HG-053/checks-" + C + "/"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def blob(path: str) -> bytes:
    entry = git("ls-tree", R, "--", path).decode().strip()
    assert entry.startswith("100644 blob "), (path, entry)
    return git("show", R + ":" + path)


def recover(path: str, command: str | None = None) -> bytes:
    envelope = json.loads(blob(path))
    stored = blob(envelope["payload"])
    assert len(stored) == envelope["stored_bytes"]
    assert hashlib.sha256(stored).hexdigest() == envelope["stored_sha256"]
    raw = gzip.decompress(stored)
    assert len(raw) == envelope["raw_bytes"]
    assert hashlib.sha256(raw).hexdigest() == envelope["raw_sha256"]
    assert len(stored) <= 8388608 and len(raw) <= 67108864
    if command is not None:
        assert envelope["tested_commit"] == C
        assert envelope["command"] == command and envelope["exit_code"] == 0
    return raw


def junit(raw: bytes, expected: int) -> list[str]:
    root = ET.fromstring(raw)
    suites = root.findall("testsuite")
    assert sum(int(s.attrib["tests"]) for s in suites) == expected
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ("errors", "failures", "skipped"))
    cases = root.findall(".//testcase")
    assert len(cases) == expected
    assert all(not list(case) for case in cases)
    return [case.attrib["classname"] + "::" + case.attrib["name"] for case in cases]


def main() -> None:
    record = yaml.safe_load(blob("docs/exec-plans/governance/HG-053.yaml"))
    changed = git("diff", "--name-only", B, R).decode().splitlines()
    assert sorted(changed) == sorted(record["files_changed"])
    assert record["base_commit"] == B and record["tested_commit"] == C
    assert record["change_status"] == "PASS" and record["frozen_impact"] == "NONE"
    documents = {"CURRENT_DOCUMENT_INDEX.json", "HARNESS_DOCUMENT_MANIFEST.json",
                 "KineticLoop_Harness_Backlog_v0.2.json", "KineticLoop_Harness_Traceability_v0.3.json",
                 "docs/exec-plans/active/KL-036.md", "docs/exec-plans/active/KL-037.md"}
    assert all(p in documents or p.startswith("docs/exec-plans/evidence/HG-053/")
               or p == "docs/exec-plans/governance/HG-053.yaml" for p in changed)
    suffix = git("diff", "--name-only", C, R).decode().splitlines()
    assert all(p.startswith("docs/exec-plans/evidence/HG-053/")
               or p == "docs/exec-plans/governance/HG-053.yaml" for p in suffix)
    subprocess.run(["git", "merge-base", "--is-ancestor", C, R], cwd=ROOT, check=True)
    index = json.loads(blob(PREFIX + "CHECK_INDEX.json"))
    assert index["tested_commit"] == C and index["runtime_checks"] == "NOT_RUN"
    assert index["product_claims"] == [] and len(index["checks"]) == 7
    assert record["checks_run"] == [{k: c[k] for k in ("check_id", "command", "result", "evidence_ref")}
                                     for c in index["checks"]]
    recovered = {}
    checks = []
    for check in index["checks"]:
        assert check["exit_code"] == 0 and check["result"] == "PASS"
        raw = recover(check["evidence_ref"], check["command"])
        checks.append({"check_id": check["check_id"], "raw_bytes": len(raw),
                       "raw_sha256": hashlib.sha256(raw).hexdigest(), "exit_code": 0})
        for path in check.get("ancillary_refs", []):
            recovered[path.rsplit("/", 1)[-1]] = recover(path, check["command"])
    assert len(set(junit(recovered["unit-unit.xml.json"], 247))) == 247
    harness_ids = junit(recovered["harness-junit.xml.json"], 1492)
    assert len(set(harness_ids)) == 1492
    execution = json.loads(recovered["harness-execution.json.json"])
    serial = json.loads(recovered[C + "-harness-collection.json.json"])
    collections = list(serial["collections"].values())
    assert collections and len(collections[0]) == len(set(collections[0])) == 1492
    expected = set(collections[0])
    assert all(set(ids) == expected and len(ids) == 1492 for ids in collections)
    assert execution["exit_code"] == 0 and execution["errors"] == []
    assert len(execution["started"]) == len(set(execution["started"])) == 1492
    assert set(execution["started"]) == expected
    assert all(set(ids) == expected and len(ids) == 1492 for ids in execution["collections"].values())
    assert len(execution["reports"]) == 1492 * 3
    counts = Counter((r["nodeid"], r["phase"]) for r in execution["reports"])
    assert all(r["outcome"] == "passed" for r in execution["reports"])
    assert set(counts) == {(node, phase) for node in expected for phase in ("setup", "call", "teardown")}
    assert all(count == 1 for count in counts.values())
    normalized = {".".join([parts[0][:-3].replace("/", "."), *parts[1:-1]]) + "::" + parts[-1]
                  + ("[" + parameter if separator else "")
                  for node in expected for stem, separator, parameter in [node.partition("[")]
                  for parts in [stem.split("::")]}
    assert normalized == set(harness_ids)
    manifest = json.loads(recovered["harness-manifest.json.json"])
    assert manifest["tested_commit"] == C and not manifest["dirty_source"]
    assert manifest["execution_complete"] and manifest["exit_code"] == manifest["pytest_exit_code"] == 0
    assert manifest["errors"] == []
    backlog = json.loads(blob("KineticLoop_Harness_Backlog_v0.2.json"))
    targets = [t for t in backlog["tasks"] if t["id"] in {"KL-036", "KL-037"}]
    assert len(targets) == 2
    for task in targets:
        assert task["status"] == "NOT_STARTED" and task["requirements_covered"] == []
        assert task["resource_keys"] == ["transaction_interfaces", "user_coordination", "planning_ledger"]
        assert task["parallel_write_policy"] == "SERIALIZE_WITH_OTHER_HOTSPOT_TASKS"
        for dep in task["depends_on"]:
            integration = json.loads(blob("docs/exec-plans/integrations/" + dep + ".json"))
            result = yaml.safe_load(blob("docs/exec-plans/completed/" + dep + "_RESULT.yaml"))
            assert result["task_status"] == result["task_checks_status"] == "PASS"
            subprocess.run(["git", "merge-base", "--is-ancestor", integration["merge_commit"], B], cwd=ROOT, check=True)
    output = {"reviewed_head_sha": R, "base_commit": B, "tested_commit": C,
              "declared_files_match_diff": True, "post_test_suffix_own_bookkeeping_only": True,
              "all_seven_exact_C_captures_recovered": True, "checks": checks,
              "unit_junit_cases": 247, "harness_collection_started_junit_cases": 1492,
              "harness_passing_phase_reports": 4476, "failed": 0, "skipped": 0,
              "prospective_runtime_checks": "NOT_RUN", "product_claims": []}
    target = ROOT / "docs/exec-plans/reviews/HG-053/db/VERIFICATION.json"
    target.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
