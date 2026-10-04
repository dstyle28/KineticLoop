"""HG053 prospective packet/projection/admission audit; no runtime/task PASS."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = "c82e50aefad5c4d9e325d4928a8f96032b81192d"
TARGETS = ("KL-036", "KL-037")
# Hashes bind only these complete prospective definitions; not shared enforcement.
EXPECTED = {'KL-036': 'd11c4357f4a726d42dc89b5af1bffae97508fcf3ab18d1ad6968a06bfffe8fe7', 'KL-037': 'a71a1fdadc0d40821c28f800297beb3d8f2f4789002db6fe90462d24065587c6'}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def main() -> None:
    spec = importlib.util.spec_from_file_location("hg053_harness", ROOT / "tools/harness/validate_harness.py")
    assert spec and spec.loader
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    assert not harness.revision_git_entry(ROOT, "docs/exec-plans/governance/HG-053.yaml", BASE)
    assert not git("ls-tree", "-r", "--name-only", BASE, "docs/exec-plans/evidence/HG-053", "docs/exec-plans/reviews/HG-053")
    backlog_path = harness.BACKLOG
    old = json.loads(git("show", BASE + ":" + backlog_path))
    new = load(backlog_path)
    before = {t["id"]: t for t in old["tasks"]}
    after = {t["id"]: t for t in new["tasks"]}
    assert set(before) == set(after)
    assert {k: v for k, v in old.items() if k != "tasks"} == {k: v for k, v in new.items() if k != "tasks"}
    assert [t["id"] for t in old["tasks"]] == [t["id"] for t in new["tasks"]]
    assert [k for k in before if before[k] != after[k]] == list(TARGETS)
    trace_before = json.loads(git("show", BASE + ":" + harness.TRACEABILITY))
    trace_after = load(harness.TRACEABILITY)
    assert {k: v for k, v in trace_before.items() if k != "tasks"} == {k: v for k, v in trace_after.items() if k != "tasks"}
    assert [t["id"] for t in trace_before["tasks"]] == [t["id"] for t in trace_after["tasks"]]
    for a, b in zip(trace_before["tasks"], trace_after["tasks"], strict=True):
        assert a == b or a["id"] in TARGETS
    traced = {t["id"]: t for t in trace_after["tasks"]}
    observations = []
    for name in TARGETS:
        task = after[name]
        canonical = json.dumps(task, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        assert hashlib.sha256(canonical).hexdigest() == EXPECTED[name], name
        assert traced[name] == harness.traceability_projection(task)
        assert task["status"] == "NOT_STARTED" and task["evidence_refs"] == []
        assert task["requirements_covered"] == []
        assert task["packet_refinement"] == task["write_paths_status"] == "ENFORCEABLE"
        assert task["review_requirements"] == ["DB_CONCURRENCY", "GENERAL", "PROTOCOL", "SECURITY_DATA_BOUNDARY"]
        assert task["parallel_write_policy"] == "SERIALIZE_WITH_OTHER_HOTSPOT_TASKS" and task["shared_hotspot"]
        assert task["resource_keys"] == ["transaction_interfaces", "user_coordination", "planning_ledger"]
        assert all("*" not in p for p in task["write_paths"])
        contracts = task["check_contracts"]
        assert [c["check_id"] for c in contracts] == task["checks_required_for_this_task"]
        assert len({c["check_id"] for c in contracts}) == len(contracts) == (16 if name == "KL-036" else 15)
        assert all(set(c) == {"check_id", "command", "pass_oracle"} and all(c.values()) for c in contracts)
        assert not any(re.search("task_scope_|TODO|TBD|placeholder", json.dumps(c), re.I) for c in contracts)
        packet = (ROOT / f"docs/exec-plans/active/{name}.md").read_text()
        assert not harness.packet_errors(task, packet)
        contract = json.loads(re.search(r"```json\s*(\{.*?\})\s*```", harness.section(packet, "Machine-readable check contract"), re.S)[1])
        assert contract == {"check_contracts": contracts, "evidence_paths": task["evidence_paths"]}
        assert harness.bullets(harness.section(packet, "Read first")) == task["context_files"]
        assert harness.bullets(harness.section(packet, "Entry conditions")) == task["entry_conditions"]
        assert harness.bullets(harness.section(packet, "Deliverables")) == task["deliverables"]
        assert harness.section(packet, "Definition of Done").strip() == task["definition_of_done"]
        assert harness.bullets(harness.section(packet, "Review requirements")) == task["review_requirements"]
        for path in (f"docs/exec-plans/completed/{name}_RESULT.yaml", f"docs/exec-plans/completed/{name}_RESULT.json", f"docs/exec-plans/integrations/{name}.json"):
            assert not harness.revision_git_entry(ROOT, path, BASE)
            assert not (ROOT / path).exists()
        assert not git("ls-tree", "-r", "--name-only", BASE, f"docs/exec-plans/reviews/{name}")
        for dep in task["depends_on"]:
            result = harness.load_artifact(ROOT / f"docs/exec-plans/completed/{dep}_RESULT.yaml")
            record = load(f"docs/exec-plans/integrations/{dep}.json")
            assert result["task_status"] == result["task_checks_status"] == "PASS"
            assert record["task_identity"] == "harness-backlog-v0.2/" + dep
            subprocess.run(["git", "merge-base", "--is-ancestor", record["merge_commit"], BASE], cwd=ROOT, check=True)
        # Exercise existing generic result command/scope machinery, without adding
        # task artifacts or treating synthetic fixtures as real executed evidence.
        with tempfile.TemporaryDirectory(prefix="hg053-contract-") as temp:
            tmp = Path(temp)
            ref = f"docs/exec-plans/evidence/{name}/synthetic.log"
            (tmp / ref).parent.mkdir(parents=True)
            (tmp / ref).write_text("SYNTHETIC CONTRACT TEST ONLY\n")
            obj = {"task_identity": task["task_identity"], "display_task_id": name,
                   "task_status": "PASS", "task_checks_status": "PASS", "tested_commit": git("rev-parse", "HEAD"),
                   "requirements_covered": [], "commands_run": [{"check_id": c["check_id"], "command": c["command"], "result": "PASS", "evidence_ref": ref} for c in contracts]}
            assert harness.semantic_result_errors(obj, task, tmp) == []
            bad = copy.deepcopy(obj); bad["commands_run"].pop()
            assert "required-checks-not-pass" in harness.semantic_result_errors(bad, task, tmp)
            bad = copy.deepcopy(obj); bad["commands_run"][0]["command"] = "uv run pytest -q tests/unit"
            assert "command-contract-command:" + contracts[0]["check_id"] in harness.semantic_result_errors(bad, task, tmp)
            bad = copy.deepcopy(obj); bad["commands_run"][0]["evidence_ref"] = "docs/exec-plans/evidence/OTHER/borrowed.log"
            assert "command-evidence-scope:" + contracts[0]["check_id"] in harness.semantic_result_errors(bad, task, tmp)
            bad = copy.deepcopy(obj); bad["commands_run"][0]["result"] = "NOT_RUN"
            assert "required-checks-not-pass" in harness.semantic_result_errors(bad, task, tmp)
        observations.append({"task_identity": task["task_identity"], "initial_check_statuses": {c["check_id"]: "NOT_RUN" for c in contracts}, "definition_sha256": EXPECTED[name], "prospective_checks": len(contracts), "prerequisites": task["depends_on"]})
    closure = load("docs/exec-plans/milestones/M3.json")
    assert closure["closure_status"] == "PASS" and closure["production_auto_activation"] is False and closure["shadow_executable"] is False and closure["product_requirement_pass_claims"] == []
    changed = git("diff", "--name-only", BASE).splitlines()
    allowed = {backlog_path, harness.TRACEABILITY, harness.INDEX, harness.MANIFEST, *(f"docs/exec-plans/active/{n}.md" for n in TARGETS), "docs/exec-plans/governance/HG-053.yaml"}
    assert all(p in allowed or p.startswith("docs/exec-plans/evidence/HG-053/") or p.startswith("docs/exec-plans/reviews/HG-053/") for p in changed)
    shared = set(after[TARGETS[0]]["write_paths"]) & set(after[TARGETS[1]]["write_paths"])
    assert shared == {"src/kineticloop/persistence/transactions.py"}
    print(json.dumps({"governance_audit": "PASS", "base_commit": BASE, "audited_head": git("rev-parse", "HEAD"), "definitions": observations, "shared_path": sorted(shared), "scheduling": "SERIALIZED", "runtime_task_checks": "NOT_RUN", "product_claims": [], "generic_enforcement": "required IDs, exact commands, owner evidence scope and bound revisions; semantic/skip oracles require actual tests and independent review", "packet_projection_audit": "task-owned governance verifier supplements generic packet mirrors without shared validator edits"}, indent=2))


if __name__ == "__main__":
    main()
