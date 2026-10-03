"""Run independent harness tests with at most four local process workers.

This is developer evidence, not the trusted App-bound local database gate.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

MAX_WORKERS = 4
DEFAULT_WORKERS = 2
ROOT = Path(__file__).resolve().parents[2]


def file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def evidence_errors(record: dict[str, Any], workers: int, collect_only: bool) -> list[str]:
    errors = list(record["errors"])
    collections = list(record["collections"].values())
    if len(collections) != (workers if workers > 1 else 1):
        errors.append("missing-worker-collection")
    nodes = collections[0] if collections else []
    if any(collected != nodes for collected in collections):
        errors.append("worker-collection-mismatch")
    if not nodes or len(nodes) != len(set(nodes)):
        errors.append("empty-or-duplicate-collection")
    if collect_only:
        return errors
    started = record["started"]
    if len(started) != len(set(started)) or sorted(started) != sorted(nodes):
        errors.append("execution-collection-mismatch")
    for phase in ("setup", "call", "teardown"):
        reports = [report for report in record["reports"] if report["phase"] == phase]
        if sorted(report["nodeid"] for report in reports) != sorted(nodes):
            errors.append("missing-or-duplicate-" + phase)
        if any(report["outcome"] != "passed" for report in reports):
            errors.append("failed-or-skipped-" + phase)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--workers", type=int, choices=range(1, MAX_WORKERS + 1),
                        default=DEFAULT_WORKERS)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--junitxml", "--junit-xml", type=Path)
    args, extra = parser.parse_known_args(argv)
    if args.evidence_dir and args.evidence_dir.resolve().is_relative_to(ROOT):
        parser.error("Record evidence outside the source checkout, then commit it after execution")
    # One entrypoint owns process topology; arbitrary pytest selectors/options remain available.
    controlled = ("-n", "-d", "--numprocesses", "--dist", "--tx", "--px", "--maxprocesses",
                  "--max-worker-restart", "--maxschedchunk")
    if any(arg == "-d" or arg.startswith("-n") or
           any(arg == name or arg.startswith(name + "=") for name in controlled[2:])
           for arg in extra):
        parser.error("Use --workers to configure local concurrency")
    if args.workers > 1 and "-s" in extra:
        parser.error("xdist does not support -s; use --workers 1")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    if args.evidence_dir and dirty:
        parser.error("Commit source before recording revision-bound evidence")
    if args.evidence_dir:
        directory = args.evidence_dir.resolve()
        directory.mkdir(parents=True, exist_ok=False)
        temporary = None
    else:
        temporary = tempfile.TemporaryDirectory(prefix="kl-harness-run-")
        directory = Path(temporary.name)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "src"), env.get("PYTHONPATH", "")])
    env["KINETICLOOP_HARNESS_ROOT"] = str(ROOT)
    env["KINETICLOOP_HARNESS_WORKERS"] = str(args.workers)
    env["KINETICLOOP_HARNESS_OBSERVER"] = str(directory / "execution.json")
    command = [sys.executable, "-m", "pytest", "-p", "tools.harness.parallel_observer",
               "tests/harness", *extra, "-n", str(args.workers if args.workers > 1 else 0),
               "--dist", "load", "--maxprocesses", str(MAX_WORKERS),
               "--max-worker-restart", "0", "--maxschedchunk", "1",
               "--junitxml=" + str(directory / "junit.xml")]
    collect_only = "--collect-only" in extra or "--co" in extra
    if collect_only:
        command[command.index("-n") + 1] = "0"
    collection_command = command[:command.index("-n")] + ["--collect-only", "-q", "-n", "0"]
    started = time.monotonic()
    status = 2
    errors: list[str] = []
    observer: dict[str, Any] = {}
    process: subprocess.Popen[bytes] | None = None
    try:
        collection_env = {**env, "KINETICLOOP_HARNESS_OBSERVER": str(directory / "collection.json")}
        with (directory / "collection.log").open("wb") as collected_log:
            collection_process = subprocess.run(collection_command, cwd=ROOT, env=collection_env,
                                                stdout=collected_log, stderr=subprocess.STDOUT)
        if collection_process.returncode != 0:
            sys.stdout.buffer.write((directory / "collection.log").read_bytes())
            status = collection_process.returncode
            errors.append("preflight-collection-failed")
            (directory / "manifest.json").write_text(json.dumps({
                "format": "kineticloop-developer-harness-run-v1", "tested_commit": revision,
                "workers": args.workers, "command": collection_command,
                "dirty_source": dirty, "wall_seconds": time.monotonic() - started,
                "exit_code": status, "errors": errors,
                "files": [file_record(path) for path in sorted(directory.iterdir()) if path.is_file()],
            }, indent=2) + "\n")
            return status
        collection_wall = time.monotonic() - started
        collection = json.loads((directory / "collection.json").read_text())
        errors.extend(evidence_errors(collection, 1, True))
        with (directory / "pytest.log").open("wb") as raw:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    raw.write(line)
                    raw.flush()
                    sys.stdout.buffer.write(line)
                    sys.stdout.buffer.flush()
                status = process.wait()
            except KeyboardInterrupt:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                status = 130
                errors.append("interrupted")
        try:
            observer = json.loads((directory / "execution.json").read_text())
            if observer["exit_code"] != process.returncode:
                errors.append("observer-exit-mismatch")
            errors.extend(evidence_errors(observer, 1 if collect_only else args.workers, collect_only))
            expected = collection["collections"]["serial"]
            if any(nodes != expected for nodes in observer["collections"].values()):
                errors.append("preflight-execution-collection-mismatch")
            if not collect_only:
                cases = list(ET.parse(directory / "junit.xml").iter("testcase"))
                expected_cases = []
                for node in observer["started"]:
                    address, separator, parameters = node.partition("[")
                    pieces = address.split("::")
                    classname = ".".join([pieces[0][:-3].replace("/", "."), *pieces[1:-1]])
                    expected_cases.append((classname, pieces[-1] + separator + parameters))
                if Counter(expected_cases) != Counter(
                        (case.get("classname"), case.get("name")) for case in cases):
                    errors.append("junit-execution-identity-mismatch")
        except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
            errors.append("missing-or-invalid-evidence: " + str(error))
        current_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        current_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
        if current_revision != revision or (not dirty and current_dirty):
            errors.append("source-changed-during-execution")
        if args.junitxml and args.junitxml.resolve() != (directory / "junit.xml").resolve():
            try:
                args.junitxml.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(directory / "junit.xml", args.junitxml)
            except OSError as error:
                errors.append("junit-export-failed: " + str(error))
        # Preserve pytest's failure code; missing/partial evidence cannot create success.
        result = status if status != 0 else 1 if errors else 0
        files = [file_record(path) for path in sorted(directory.iterdir()) if path.is_file()]
        (directory / "manifest.json").write_text(json.dumps({
            "format": "kineticloop-developer-harness-run-v1", "tested_commit": revision,
            "dirty_source": dirty, "workers": args.workers, "command": command,
            "python": sys.version, "platform": platform.platform(),
            "versions": {name: importlib.metadata.version(name)
                         for name in ("pytest", "pytest-xdist", "execnet")},
            "collection_command": collection_command,
            "collection_wall_seconds": collection_wall,
            "wall_seconds": time.monotonic() - started, "pytest_exit_code": process.returncode,
            "mode": "COLLECTION_ONLY" if collect_only else "EXECUTION",
            "execution_complete": not collect_only and result == 0,
            "requested_junitxml": str(args.junitxml) if args.junitxml else None,
            "exit_code": result, "errors": errors, "files": files,
            "evidence_scope": "developer-harness; App-bound local-db-gate still required",
        }, indent=2) + "\n")
        for issue in errors:
            print("HARNESS_EVIDENCE_ERROR: " + issue, file=sys.stderr)
        return result
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    sys.exit(main())
