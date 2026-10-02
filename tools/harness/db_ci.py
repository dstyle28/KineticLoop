#!/usr/bin/env python3
"""Run full database CI in an owned local daemon or an explicit hosted job.

The local command owns one disposable privileged Linux container. It copies a Git
bundle, never mounts host paths/sockets or passes credentials into the container.
Use only a trusted reviewed commit: this is environment isolation, not a sandbox
for hostile code. The run command refuses a populated or remote Docker daemon.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

FORMAT = "kineticloop-db-ci-v1"
REVISION = re.compile(r"[0-9a-f]{40}")
ROOT = Path(__file__).resolve().parents[2]


def output(argv: list[str], *, cwd: Path = ROOT) -> str:
    return subprocess.check_output(argv, cwd=cwd, text=True, timeout=120).strip()


def resolve_revision(value: str, root: Path = ROOT) -> str:
    sha = output(["git", "rev-parse", "--verify", "--end-of-options", value + "^{commit}"], cwd=root)
    if not REVISION.fullmatch(sha):
        raise ValueError("a full SHA-1 commit is required")
    return sha


def file_record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run_capture(argv: list[str], directory: Path, name: str, *, timeout: int = 6600,
                cwd: Path = ROOT, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Retain raw combined output on success, failure, timeout and interruption."""
    path = directory / (name + ".log")
    start = time.monotonic()
    code = 125
    interrupted = False
    with path.open("wb") as log:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            interrupted = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = 124
    result = {"check_id": name, "argv": argv, "exit_code": code,
              "interrupted": interrupted, "duration_seconds": round(time.monotonic() - start, 3),
              "stdout": file_record(path)}
    print(f"{name}: {'PASS' if code == 0 else 'FAIL'} ({result['duration_seconds']}s)", flush=True)
    return result


def environment_preflight(environment: str, revision: str) -> dict[str, Any]:
    if platform.system() != "Linux":
        raise ValueError("run requires Linux; use local on macOS")
    if resolve_revision("HEAD") != revision:
        raise ValueError("checkout HEAD differs from tested revision")
    if output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise ValueError("run requires a clean committed checkout")
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        raise ValueError("ambient/remote Docker overrides are forbidden")
    if output(["docker", "context", "show"]) != "default":
        raise ValueError("a dedicated default Docker context is required")
    endpoint = output(["docker", "context", "inspect", "default", "--format",
                       "{{.Endpoints.docker.Host}}"])
    if endpoint != "unix:///var/run/docker.sock":
        raise ValueError("a dedicated local Unix Docker socket is required")
    if environment == "local-isolated":
        marker = Path("/run/kineticloop-local-db/owner")
        if not marker.is_file() or marker.read_text().strip() != "dedicated-container-daemon-v1":
            raise ValueError("local run must be launched by the owned container entrypoint")
    elif not (os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
              and os.environ.get("RUNNER_OS") == "Linux"):
        raise ValueError("hosted provenance is unavailable")
    if output(["docker", "ps", "--all", "--quiet"]) or output(["docker", "volume", "ls", "--quiet"]):
        raise ValueError("refusing a populated Docker daemon before any lifecycle action")
    return {"environment": environment, "os": platform.system(), "architecture": platform.machine(),
            "python": platform.python_version(), "uv": output(["uv", "--version"]),
            "docker": json.loads(output(["docker", "version", "--format", "{{json .Server}}"])),
            "docker_endpoint": endpoint, "initial_containers": [], "initial_volumes": [],
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}


def junit_counts(path: Path) -> dict[str, int]:
    tree = ET.parse(path)
    cases = tree.findall(".//testcase")
    return {"tests": len(cases), "failures": len(tree.findall(".//failure")),
            "errors": len(tree.findall(".//error")), "skipped": len(tree.findall(".//skipped"))}


def command_plan(directory: Path, revision: str) -> list[tuple[str, list[str]]]:
    peer = directory.parent / (directory.name + "-peer")
    return [
        ("lint", ["uv", "run", "kl", "lint"]),
        ("typecheck", ["uv", "run", "kl", "typecheck"]),
        ("collection", ["uv", "run", "python", "-m", "pytest", "--collect-only", "-q",
                        "-p", "tools.harness.db_ci_pytest", "-o", "xfail_strict=true", "tests/db"]),
        ("full_database", ["uv", "run", "python", "-m", "pytest", "-q",
                           "-p", "tools.harness.db_ci_pytest", "-o", "xfail_strict=true", "tests/db",
                           "--junitxml=" + str(directory / "database.xml")]),
        ("compose_config_valid", ["uv", "run", "python", "tools/db/verify.py", "compose-config-valid"]),
        ("postgres_ready", ["uv", "run", "python", "tools/db/verify.py", "postgres-ready"]),
        ("reset_idempotent", ["uv", "run", "python", "tools/db/verify.py", "reset-idempotent"]),
        ("peer_checkout", ["git", "worktree", "add", "--detach", str(peer), revision]),
        ("worktree_db_isolated", ["uv", "run", "python", "tools/db/verify.py",
                                 "worktree-db-isolated", "--peer-root", str(peer)]),
    ]


def validate_evidence(directory: Path, revision: str) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text())
    if (manifest.get("format") != FORMAT or manifest.get("tested_commit") != revision
            or manifest.get("status") != "PASS"):
        raise ValueError("evidence identity, revision or status mismatch")
    required = ["lint", "typecheck", "collection", "full_database", "compose_config_valid",
                "postgres_ready", "reset_idempotent", "peer_checkout", "worktree_db_isolated",
                "destroy", "peer_remove"]
    checks = manifest.get("checks", [])
    if [entry["check_id"] for entry in checks] != required:
        raise ValueError("incomplete or reordered full database check set")
    for entry in checks:
        if type(entry.get("exit_code")) is not int or entry["exit_code"] != 0 or entry["interrupted"]:
            raise ValueError("failed/interrupted check cannot pass")
    if (not checks[3]["argv"] or not checks[3]["argv"][-1].startswith("--junitxml=/")
            or not checks[3]["argv"][-1].endswith("/database.xml")):
        raise ValueError("missing exact JUnit output argument")
    if [entry["stdout"]["path"] for entry in checks] != [name + ".log" for name in required]:
        raise ValueError("each check requires its own raw log")
    # Commands, including selectors, cannot be replaced by a shorter passing run.
    expected = dict(command_plan(Path(checks[3]["argv"][-1].split("=", 1)[1]).parent, revision))
    evidence_root = Path(checks[3]["argv"][-1].split("=", 1)[1]).parent
    peer = evidence_root.parent / (evidence_root.name + "-peer")
    expected["destroy"] = ["uv", "run", "python", "tools/db/verify.py", "destroy"]
    expected["peer_remove"] = ["git", "worktree", "remove", "--force", str(peer)]
    if any(entry["argv"] != expected[entry["check_id"]] for entry in checks):
        raise ValueError("full DB command/selector drift")
    if [item["path"] for item in manifest["artifacts"]] != [
            "collection.json", "execution.json", "database.xml"]:
        raise ValueError("missing exact hashed collection/execution/JUnit artifacts")
    provenance = manifest["provenance"]
    if (provenance["environment"] not in ("local-isolated", "github-hosted")
            or provenance["os"] != "Linux"
            or provenance["docker_endpoint"] != "unix:///var/run/docker.sock"
            or provenance["initial_containers"] or provenance["initial_volumes"]):
        raise ValueError("unsupported DB execution environment")
    records = [entry["stdout"] for entry in checks] + manifest["artifacts"]
    for record in records:
        name = record["path"]
        if Path(name).name != name or name in ("", ".", ".."):
            raise ValueError("evidence path must be a sibling regular file")
        path = directory / name
        if path.is_symlink() or not path.is_file() or file_record(path) != record:
            raise ValueError("evidence blob/hash mismatch: " + name)
    collection = json.loads((directory / "collection.json").read_text())
    execution = json.loads((directory / "execution.json").read_text())
    if (not collection["nodeids"] or len(set(collection["nodeids"])) != len(collection["nodeids"])
            or collection["nodeids"] != execution["nodeids"]
            or collection["exit_code"] != 0 or execution["exit_code"] != 0):
        raise ValueError("collection/execution identities or counts differ")
    cases = ET.parse(directory / "database.xml").findall(".//testcase")
    expected_cases = []
    for nodeid in collection["nodeids"]:
        base, separator, parameters = nodeid.partition("[")
        pieces = base.split("::")
        filename = pieces[0]
        if not filename.startswith("tests/db/") or not filename.endswith(".py"):
            raise ValueError("non-DB collected node")
        classname = ".".join([filename[:-3].replace("/", "."), *pieces[1:-1]])
        expected_cases.append((classname, pieces[-1] + separator + parameters))
    if Counter(expected_cases) != Counter((case.get("classname"), case.get("name")) for case in cases):
        raise ValueError("JUnit identities differ from actual collection")
    counts = junit_counts(directory / "database.xml")
    if (counts["tests"] != len(collection["nodeids"]) or counts["failures"]
            or counts["errors"] or counts["skipped"]):
        raise ValueError("JUnit must execute every collected case without failure/skip")
    if counts != manifest["junit"]:
        raise ValueError("JUnit summary mismatch")
    return manifest


def execute(args: argparse.Namespace) -> int:
    revision = args.revision
    if not REVISION.fullmatch(revision):
        raise ValueError("--revision must be a full immutable SHA")
    directory = args.evidence_dir.resolve()
    if directory.exists():
        raise ValueError("evidence directory already exists; never overwrite a run")
    if directory.is_relative_to(ROOT):
        raise ValueError("run evidence must be outside the checkout")
    directory.mkdir(parents=True)
    manifest: dict[str, Any] = {"format": FORMAT, "tested_commit": revision, "status": "FAIL",
                                "checks": [], "artifacts": []}
    try:
        manifest["provenance"] = environment_preflight(args.environment, revision)
        peer = directory.parent / (directory.name + "-peer")
        commands = command_plan(directory, revision)
        try:
            for name, command in commands:
                env = os.environ.copy()
                env["KINETICLOOP_DB_CI_NODEIDS"] = str(directory / (
                    "collection.json" if name == "collection" else "execution.json"))
                result = run_capture(command, directory, name, env=env)
                manifest["checks"].append(result)
                if result["exit_code"] != 0:
                    raise ValueError("check failed: " + name)
        finally:
            manifest["checks"].append(run_capture(
                ["uv", "run", "python", "tools/db/verify.py", "destroy"], directory, "destroy", timeout=120))
            if peer.exists():
                manifest["checks"].append(run_capture(
                    ["git", "worktree", "remove", "--force", str(peer)], directory, "peer_remove", timeout=120))
            manifest["remaining_containers"] = output(["docker", "ps", "--all", "--format", "{{.Names}}"])
            manifest["remaining_volumes"] = output(["docker", "volume", "ls", "--format", "{{.Name}}"])
        for name in ["collection.json", "execution.json", "database.xml"]:
            manifest["artifacts"].append(file_record(directory / name))
        manifest["junit"] = junit_counts(directory / "database.xml")
        manifest["status"] = "PASS"
        write_json(directory / "manifest.json", manifest)
        validate_evidence(directory, revision)
    except (ValueError, OSError, subprocess.SubprocessError, ET.ParseError, KeyError) as error:
        manifest["status"] = "FAIL"
        manifest["error"] = str(error)
    finally:
        write_json(directory / "manifest.json", manifest)
    print(f"DB_CI_{manifest['status']} tested_commit={revision} evidence={directory}", flush=True)
    return 0 if manifest["status"] == "PASS" else 1


def owned_mounts(inspect: dict[str, Any], volume: str) -> list[dict[str, str]]:
    mounts = inspect["Mounts"]
    if (len(mounts) != 1 or mounts[0]["Type"] != "volume"
            or mounts[0]["Name"] != volume or mounts[0]["Destination"] != "/var/lib/docker"
            or inspect["HostConfig"]["NetworkMode"] == "host"):
        raise ValueError("unexpected shared container resources")
    return [{key: mounts[0][key] for key in ("Type", "Name", "Destination")}]


def local(args: argparse.Namespace) -> int:
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        raise ValueError("local executor rejects ambient Docker overrides")
    context = output(["docker", "context", "show"])
    endpoint = output(["docker", "context", "inspect", context, "--format",
                       "{{.Endpoints.docker.Host}}"])
    if not endpoint.startswith("unix:///"):
        raise ValueError("local executor requires a local Unix Docker endpoint")
    revision = resolve_revision(args.revision)
    if resolve_revision("HEAD") != revision or output(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise ValueError("local requires clean HEAD at the selected commit; use a separate checkout")
    destination = args.evidence_dir.resolve()
    if destination.exists() or destination.is_relative_to(ROOT):
        raise ValueError("choose a new evidence directory outside the checkout")
    destination.mkdir(parents=True)
    name = "kineticloop-db-ci-" + revision[:7] + "-" + uuid.uuid4().hex[:12]
    image = "kineticloop-local-db:" + revision[:12]
    volume = name + "-data"
    volume_created = False
    container_created = False
    envelope: dict[str, Any] = {"tested_commit": revision, "container": name, "status": "FAIL"}
    try:
        build = run_capture(["docker", "build", "--tag", image, "tools/harness/local_db"],
                            destination, "image_build", timeout=1200)
        if build["exit_code"]:
            raise ValueError("image build failed; see image_build.log")
        envelope["image"] = json.loads(output(["docker", "image", "inspect", image]))[0]["Id"]
        # Fresh owned data volume supports overlay2; never reuse another run's data.
        if subprocess.run(["docker", "volume", "inspect", volume], capture_output=True).returncode == 0:
            raise ValueError("refusing a pre-existing executor data volume")
        output(["docker", "volume", "create", "--label", "kineticloop.owner=" + name, volume])
        volume_created = True
        # No bind mounts, host socket/network/PID namespace or environment credentials.
        output(["docker", "run", "--detach", "--privileged", "--name", name,
                "--mount", "type=volume,source=" + volume + ",target=/var/lib/docker",
                "--label", "kineticloop.owner=local-db-ci", image])
        container_created = True
        inspect = json.loads(output(["docker", "inspect", name]))[0]
        envelope["mounts"] = owned_mounts(inspect, volume)
        envelope["owned_volume"] = volume
        for _ in range(60):
            check = subprocess.run(["docker", "exec", name, "docker", "info"], capture_output=True)
            if check.returncode == 0:
                break
            if output(["docker", "inspect", "--format", "{{.State.Running}}", name]) != "true":
                raise ValueError("owned daemon exited; see daemon.log")
            time.sleep(1)
        else:
            raise ValueError("owned daemon failed to become ready")
        with tempfile.TemporaryDirectory(prefix="kineticloop-db-ci-") as temp:
            bundle = Path(temp) / "source.bundle"
            output(["git", "bundle", "create", str(bundle), "HEAD"])
            output(["docker", "cp", str(bundle), name + ":/source.bundle"])
        output(["docker", "exec", name, "git", "clone", "/source.bundle", "/workspace/KineticLoop"])
        output(["docker", "exec", "--workdir", "/workspace/KineticLoop", name,
                "git", "checkout", "--detach", revision])
        sync = run_capture(["docker", "exec", "--workdir", "/workspace/KineticLoop", name,
                            "uv", "sync", "--locked"], destination, "dependency_sync", timeout=1200)
        if sync["exit_code"]:
            raise ValueError("dependency sync failed")
        run = run_capture(["docker", "exec", "--workdir", "/workspace/KineticLoop", name,
                           "uv", "run", "python", "tools/harness/db_ci.py", "run",
                           "--revision", revision, "--environment", "local-isolated",
                           "--evidence-dir", "/evidence/run"], destination, "executor", timeout=7000)
        output(["docker", "cp", name + ":/evidence/run", str(destination / "run")])
        if run["exit_code"]:
            raise ValueError("local DB regression failed; raw evidence retained")
        validate_evidence(destination / "run", revision)
        envelope["status"] = "PASS"
    except (ValueError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        envelope["error"] = str(error)
    finally:
        # Preserve daemon failures and partial evidence before own-resource cleanup.
        if container_created:
            with (destination / "daemon.log").open("wb") as log:
                subprocess.run(["docker", "logs", name], stdout=log, stderr=subprocess.STDOUT)
            if not (destination / "run").exists():
                subprocess.run(["docker", "cp", name + ":/evidence/run", str(destination / "run")],
                               capture_output=True)
            cleanup = subprocess.run(["docker", "rm", "--force", "--volumes", name], capture_output=True)
            envelope["container_removed"] = cleanup.returncode == 0
        else:
            envelope["container_removed"] = True
        if volume_created:
            removed = subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
            envelope["volume_removed"] = removed.returncode == 0
        else:
            envelope["volume_removed"] = True
        if not envelope["container_removed"] or not envelope["volume_removed"]:
            envelope["status"] = "FAIL"
        write_json(destination / "local-executor.json", envelope)
    print(f"LOCAL_DB_CI_{envelope['status']} evidence={destination}", flush=True)
    return 0 if envelope["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("local", "run", "verify"):
        child = sub.add_parser(command)
        child.add_argument("--revision", required=True)
        child.add_argument("--evidence-dir", type=Path, required=True)
        if command == "run":
            child.add_argument("--environment", choices=("local-isolated", "github-hosted"), required=True)
    args = parser.parse_args()
    try:
        if args.command == "local":
            return local(args)
        if args.command == "run":
            return execute(args)
        validate_evidence(args.evidence_dir, args.revision)
        print("DB_CI_EVIDENCE_PASS")
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, ET.ParseError) as error:
        parser.exit(1, f"db-ci: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
