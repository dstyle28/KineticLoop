"""Own lossless launcher; exact packet checks with collection/execution/JUnit proof."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.harness.compact_evidence import capture


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checks", nargs="*")
    args = parser.parse_args()
    tested = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise RuntimeError("commit coherent candidate before running revision-bound checks")
    packet = (ROOT / "docs/exec-plans/active/KL-036.md").read_text()
    contracts = json.loads(packet.split("```json", 1)[1].split("```", 1)[0])["check_contracts"]
    if args.checks:
        requested = set(args.checks)
        if requested - {c["check_id"] for c in contracts}:
            raise ValueError("unknown task check")
        contracts = [c for c in contracts if c["check_id"] in requested]
    # The unchanged harness runner requires a clean checkout to persist its manifest.
    contracts.sort(key=lambda c: c["check_id"] != "harness_regressions_pass")
    label = tested + "-" + uuid.uuid4().hex[:8]
    owned = Path("docs/exec-plans/evidence/KL-036") / ("checks-" + label)
    scratch = Path("/private/tmp" if sys.platform == "darwin" else "/tmp") / ("kl036-checks-" + label)
    scratch.mkdir()
    runs = []
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "src")])
    for contract in contracts:
        check, command = contract["check_id"], contract["command"]
        argv = shlex.split(command)
        folder = scratch / check
        folder.mkdir()
        run_env = dict(env)
        run_env.pop("PYTEST_ADDOPTS", None)
        run = {"check_id": check, "command": command, "tested_commit": tested, "status": "NOT_RUN"}
        print("CHECK_START " + check, flush=True)
        is_pytest = argv[2] == "pytest" or check == "unit_regressions_pass"
        if is_pytest:
            selectors = argv[4:] if argv[2] == "pytest" else ["tests/unit"]
            collect = ["uv", "run", "pytest", "--collect-only", "-q", *selectors]
            run_env.update(KINETICLOOP_HARNESS_ROOT=str(ROOT), KINETICLOOP_HARNESS_WORKERS="1",
                           KINETICLOOP_HARNESS_OBSERVER=str(folder / "collection.json"))
            run_env["PYTEST_ADDOPTS"] = "-p tools.harness.parallel_observer"
            with (folder / "collection.log").open("wb") as log:
                collected = subprocess.run(collect, cwd=ROOT, env=run_env, stdout=log, stderr=subprocess.STDOUT)
            run["collection_exit"] = collected.returncode
            run["collection_command"] = shlex.join(collect)
            run_env["KINETICLOOP_HARNESS_OBSERVER"] = str(folder / "execution.json")
            run_env["PYTEST_ADDOPTS"] = "-p tools.harness.parallel_observer -s --junitxml=" + str(folder / "junit.xml")
        if check == "harness_regressions_pass":
            argv += ["--evidence-dir", str(folder / "runner")]
        run["actual_argv"] = argv
        run["pytest_diagnostic_options"] = run_env.get("PYTEST_ADDOPTS")
        started = time.monotonic()
        with (folder / "execution.log").open("wb") as log:
            process = subprocess.run(argv, cwd=ROOT, env=run_env, stdout=log, stderr=subprocess.STDOUT)
        run["exit_code"], run["wall_seconds"] = process.returncode, time.monotonic() - started
        errors = []
        if process.returncode:
            errors.append("execution-failed")
        try:
            if is_pytest:
                collection = json.loads((folder / "collection.json").read_text())
                execution = json.loads((folder / "execution.json").read_text())
                nodes = collection["collections"]["serial"]
                if (not nodes or collection["errors"] or collection["exit_code"]
                    or run["collection_exit"] or execution["errors"] or execution["exit_code"]
                    or sorted(nodes) != sorted(execution["started"])):
                    errors.append("collection-execution-mismatch")
                for phase in ("setup", "call", "teardown"):
                    reports = [r for r in execution["reports"] if r["phase"] == phase]
                    if (sorted(r["nodeid"] for r in reports) != sorted(nodes)
                        or any(r["outcome"] != "passed" for r in reports)):
                        errors.append("incomplete-or-nonpassing-" + phase)
                xml = ET.parse(folder / "junit.xml")
                cases = xml.findall(".//testcase")
                expected_cases = []
                for node in nodes:
                    address, separator, parameters = node.partition("[")
                    parts = address.split("::")
                    classname = ".".join([parts[0][:-3].replace("/", "."), *parts[1:-1]])
                    expected_cases.append((classname, parts[-1] + separator + parameters))
                if (Counter(expected_cases) != Counter((c.get("classname"), c.get("name")) for c in cases)
                    or any(c.find("failure") is not None or c.find("error") is not None
                           or c.find("skipped") is not None for c in cases)):
                    errors.append("junit-mismatch")
                run["collected"] = run["executed"] = run["junit"] = len(nodes)
                run["nodeids"] = nodes
            elif check == "harness_regressions_pass":
                runner = folder / "runner"
                manifest = json.loads((runner / "manifest.json").read_text())
                execution = json.loads((runner / "execution.json").read_text())
                collections = list(execution["collections"].values())
                nodes = collections[0]
                cases = ET.parse(runner / "junit.xml").findall(".//testcase")
                if (not nodes or manifest["tested_commit"] != tested or manifest["dirty_source"]
                    or not manifest["execution_complete"] or manifest["errors"]
                    or any(c != nodes for c in collections) or sorted(execution["started"]) != sorted(nodes)
                    or len(cases) != len(nodes) or any(list(c) for c in cases)):
                    errors.append("harness-runner-incomplete")
                run["collected"] = run["executed"] = run["junit"] = len(nodes)
        except (OSError, ValueError, KeyError, IndexError) as error:
            errors.append(type(error).__name__)
        artifacts = {}
        for file in sorted(folder.rglob("*")):
            if not file.is_file():
                continue
            label = str(file.relative_to(folder)).replace("/", "-")
            path = str(owned / (check + "-" + label + ".json"))
            raw_command = run.get("collection_command", command) if file.name.startswith("collection.") else command
            code = run.get("collection_exit", 0) if file.name.startswith("collection.") else process.returncode
            raw = file.read_bytes()
            # This exact tracked harness case names a deliberately changed synthetic
            # password. Recognize only its canonical test identifier; retain raw bytes.
            inspected = raw.replace(
                b"test_compose_non_readiness_and_wrong_endpoint_rejected[kineticloop-local-only-changed]", b""
            )
            if (re.search(rb"postgres(?:ql)?://", inspected)
                or b"kineticloop-local-only" in inspected or b"kl072-local-only" in inspected):
                raise RuntimeError("credential-bearing diagnostic quarantined in local scratch; no Git capture")
            capture(ROOT, path, raw, tested, raw_command, code)
            artifacts[str(file.relative_to(folder))] = path
        run["artifacts"] = artifacts
        run["errors"] = errors
        run["status"] = "FAIL" if errors else "PASS"
        runs.append(run)
        (ROOT / owned / "CHECK_INDEX.json").write_text(json.dumps({
            "task_identity": "harness-backlog-v0.2/KL-036", "tested_commit": tested,
            "scratch": str(scratch), "runs": runs,
        }, indent=2) + "\n")
        print("CHECK_FINISH " + check + " " + run["status"], flush=True)
    return int(any(r["status"] != "PASS" for r in runs))


if __name__ == "__main__":
    raise SystemExit(main())
