#!/usr/bin/env python3
"""Run the bounded, offline protocol model and write reviewable evidence."""
import hashlib
import json
import platform
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kineticloop_model.interleavings import run_all
from tests.test_acceptance import AcceptanceTests, BoundaryTests
from tests.test_mutations import evaluate_mutants

ROOT = Path(__file__).resolve().parent


def run_case(case):
    result = unittest.TestResult()
    case.run(result)
    return {"test": case.id(), "status": "PASS" if result.wasSuccessful() else "FAIL",
            "failures": [detail for _, detail in result.failures + result.errors]}


def main():
    fixture_doc = json.loads((ROOT / "fixtures.json").read_text())
    fixtures = fixture_doc["acceptance_fixtures"]
    expected = {"E%02d" % n for n in range(1, 9)} | {"D%02d" % n for n in range(1, 6)}
    expected |= {"A%02d" % n for n in range(1, 9)} | {"W%02d" % n for n in range(1, 10)}
    expected |= {"R%02d" % n for n in range(1, 5)}
    assert len(fixtures) == 34 and {f["test_id"] for f in fixtures} == expected
    assert set(unittest.defaultTestLoader.getTestCaseNames(AcceptanceTests)) == {"test_" + i for i in expected}
    acceptance = []
    for fixture in fixtures:
        handler = "tests.test_acceptance.AcceptanceTests.test_" + fixture["test_id"]
        assert fixture["handler"] == handler
        assert all(fixture[k] for k in ("given", "when", "then", "layers"))
        result = run_case(AcceptanceTests("test_" + fixture["test_id"]))
        acceptance.append({**fixture, "model_result": result,
                           "production_layer_results": {layer: "NOT_RUN" for layer in fixture["layers"]}})
    boundaries = [run_case(BoundaryTests(name)) for name in
                  unittest.defaultTestLoader.getTestCaseNames(BoundaryTests)]
    interleavings = run_all()
    mutations = evaluate_mutants()
    success = (all(f["model_result"]["status"] == "PASS" for f in acceptance)
               and all(f["status"] == "PASS" for f in boundaries)
               and len(interleavings) == 9
               and all(not s["violations"] and not s["deadlocks"] and len(s["outcomes"]) > 1 for s in interleavings)
               and all(m["detected"] for m in mutations))
    sources = sorted(p for p in ROOT.rglob("*") if p.is_file() and
                     p.suffix in {".py", ".json"} and "reports" not in p.parts)
    report = {
        "status": "PASS" if success else "FAIL", "protocol_status": "FREEZE_CANDIDATE_NOT_FROZEN",
        "generated_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "scope": "Bounded atomic transition model; synthetic single-subject data; no real database, provider or processes.",
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "baseline": fixture_doc["baseline"], "acceptance": acceptance, "boundaries": boundaries,
        "interleavings": interleavings, "negative_controls": mutations,
        "totals": {"acceptance_cases": len(acceptance), "boundary_cases": len(boundaries),
                   "interleaving_scenarios": len(interleavings),
                   "complete_schedules": sum(s["complete_schedules"] for s in interleavings),
                   "visited_prefixes": sum(s["visited_prefixes"] for s in interleavings),
                   "mutants_detected": sum(m["detected"] for m in mutations),
                   "real_postgres_tests": 0, "real_process_fault_tests": 0, "live_llm_calls": 0},
        "unverified": ["PostgreSQL constraints, isolation, statement interleavings and rollback",
                       "Actual crash recovery, provider billing, SDK retries and transport fencing",
                       "Multiple subjects, permissions, replay storage isolation and timezones",
                       "Production medical/training policy and complete event/exposure reconciliation",
                       "Registry outage, lock fairness, fleet fanout and load/latency limits"]}
    destination = ROOT / "reports"
    destination.mkdir(exist_ok=True)
    (destination / "model_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    rows = ["# Pre-freeze executable model report", "", "状态：**%s；NOT FROZEN**。" % report["status"], "",
            "模型验收 %d；新增边界 %d；交错场景 %d；完整调度 %d；负向故障检出 %d/%d。" % (
                len(acceptance), len(boundaries), len(interleavings), report["totals"]["complete_schedules"],
                report["totals"]["mutants_detected"], len(mutations)), "",
            "所有数字仅指有限状态模型；真实 PostgreSQL / 进程故障 / LLM 调用均为 0。",
            "原验收的生产 PU/DC/WF/E2E 标签保留为 NOT_RUN，不由模拟结果替代。", "",
            "| 场景 | 完整调度 | 访问前缀 | 死锁 | 违例 |", "|---|---:|---:|---:|---:|"]
    rows += ["| %s | %d | %d | %d | %d |" % (s["scenario"], s["complete_schedules"],
             s["visited_prefixes"], s["deadlocks"], len(s["violations"])) for s in interleavings]
    rows += ["", "穷举边界：每场景固定 2–3 个 actor、一次命令，guard 与 mutation 合并为原子 APPLY。",
             "不证明任意长度执行、公平性、数据库锁实现或进程崩溃恢复。", "",
             "详细 Given/When/Then、逐例结果、故障检出、源码 SHA-256 见同目录 model_report.json。", "",
             "复跑：在 protocol_model 目录执行 `python3 run_model.py`（Python 3.9+，仅标准库）。", ""]
    (destination / "model_report.md").write_text("\n".join(rows))
    print(json.dumps({"status": report["status"], **report["totals"]}, ensure_ascii=False, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
