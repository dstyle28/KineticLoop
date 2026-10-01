#!/usr/bin/env python3
"""KL074 exact-head, dedicated hosted VM coldstart evidence and owned cleanup."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing
import os
import re
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError, DatabaseNamespace
from kineticloop.security.redaction import Redactor

ROOT = Path(__file__).resolve().parents[2]
COMMIT = re.compile(r"[0-9a-f]{40}")
NAMESPACE_KEYS = ("COMPOSE_PROJECT_NAME", "KINETICLOOP_DB_NAME", "COMPOSE_FILE")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DatabaseLifecycleError(message)


def owned_namespace(root: Path, tested_commit: str) -> DatabaseNamespace:
    require(COMMIT.fullmatch(tested_commit) is not None, "invalid tested commit")
    digest = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    suffix = f"{tested_commit[:7]}-{digest}"
    return DatabaseNamespace(
        f"kineticloop-kl074-cold-{suffix}",
        f"kineticloop_kl074_cold_{suffix.replace('-', '_')}",
    )


def validate_owned(lifecycle: DatabaseLifecycle, tested_commit: str) -> None:
    require(lifecycle.namespace == owned_namespace(lifecycle.root, tested_commit),
            "refusing mismatched/default/foreign lifecycle namespace")
    require(not any(lifecycle._base_environ.get(key) for key in NAMESPACE_KEYS),
            "refusing ambient namespace override")
    require(lifecycle.compose_file == lifecycle.root / "compose.yaml",
            "refusing foreign Compose file")
    require(lifecycle.compose_file.read_bytes() == (ROOT / "compose.yaml").read_bytes(),
            "temporary worktree Compose bytes differ")


def bounded_run(command: list[str], deadline: float, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    remaining = deadline - time.monotonic()
    require(remaining > 0, "coldstart total deadline expired")
    requested = kwargs.pop("timeout", None)
    timeout = min(remaining, 30.0, requested) if requested is not None else min(remaining, 30.0)
    return subprocess.run(command, timeout=timeout, **kwargs)


def command_output(command: list[str], deadline: float) -> str:
    return bounded_run(command, deadline, check=True, capture_output=True, text=True).stdout.strip()


def validate_environment(environ: dict[str, str], head: str) -> Path:
    require(COMMIT.fullmatch(head) is not None, "invalid git HEAD")
    require(environ.get("KINETICLOOP_KL074_TESTED_COMMIT") == head,
            "tested commit must equal git HEAD")
    expected = ROOT / "docs/exec-plans/evidence/KL-074" / f"hosted-{head}"
    raw = environ.get("KINETICLOOP_KL074_EVIDENCE_DIR", "")
    require(bool(raw) and Path(raw).resolve() == expected.resolve(),
            "evidence directory must equal the exact checkout/head directory")
    require(expected.resolve().is_relative_to(ROOT), "evidence directory escaped checkout")
    require(environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and environ.get("RUNNER_OS") == "Linux", "dedicated GitHub-hosted Linux VM required")
    require(not any(environ.get(key) for key in (*NAMESPACE_KEYS, "DOCKER_HOST", "DOCKER_CONTEXT")),
            "ambient namespace or Docker endpoint override rejected")
    require(not any(environ.get(key) for key in ("KINETICLOOP_DB_USER", "KINETICLOOP_DB_PASSWORD")),
            "coldstart requires unchanged local-only Compose credentials")
    return expected


def resources(namespace: DatabaseNamespace, deadline: float) -> dict[str, list[str]]:
    label = f"label=com.docker.compose.project={namespace.project_name}"
    found = {
        "containers": command_output(["docker", "ps", "--all", "--filter", label, "--quiet"], deadline).splitlines(),
        "networks": command_output(["docker", "network", "ls", "--filter", label, "--quiet"], deadline).splitlines(),
        "volumes": command_output(["docker", "volume", "ls", "--filter", label, "--quiet"], deadline).splitlines(),
    }
    all_volumes = command_output(["docker", "volume", "ls", "--format", "{{.Name}}"], deadline).splitlines()
    exact = f"{namespace.project_name}_postgres-data"
    if exact in all_volumes and exact not in found["volumes"]:
        found["volumes"].append(exact)
    return found


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


class MeasuredRunner:
    def __init__(self, evidence: Path, deadline: float) -> None:
        self.evidence = evidence
        self.deadline = deadline
        self.redactor = Redactor(("kineticloop-local-only", "kl072-local-only"))

    def event(self, **values: object) -> None:
        record = {"utc": datetime.now(UTC).isoformat(), "monotonic": time.monotonic(), **values}
        with (self.evidence / "events.jsonl").open("a") as output:
            output.write(json.dumps(record, sort_keys=True) + "\n")

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        category = "compose"
        if "pg_isready" in command:
            category = "tcp_probe"
            # Observe the actual init socket immediately before each measured TCP probe.
            socket_command = list(command)
            index = socket_command.index("--host")
            del socket_command[index:index + 4]
            observed = bounded_run(socket_command, self.deadline, **kwargs)
            self.event(kind="socket_probe", returncode=observed.returncode,
                       stdout=self.redactor.text(observed.stdout))
        elif "psql" in command:
            category = "sql"
        safe_command = [self.redactor.text(part) for part in command]
        self.event(kind=f"{category}_begin", command=safe_command,
                   requested_timeout=kwargs.get("timeout"))
        try:
            result = bounded_run(command, self.deadline, **kwargs)
        except Exception as error:
            self.event(kind=f"{category}_error",
                       diagnostic=str(self.redactor.exception_diagnostic(error)))
            raise
        self.event(kind=f"{category}_end", returncode=result.returncode,
                   stdout=self.redactor.text(result.stdout), stderr=self.redactor.text(result.stderr))
        return result


def bootstrap_module() -> Any:
    spec = spec_from_file_location("kl074_existing_migrations", ROOT / "tests/db/test_migrations.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker(root: Path, tested_commit: str, evidence: Path, deadline: float, startup: float) -> None:
    runner = MeasuredRunner(evidence, deadline)
    lifecycle = DatabaseLifecycle(root, runner=runner)
    lifecycle.namespace = owned_namespace(root, tested_commit)
    try:
        validate_owned(lifecycle, tested_commit)
        lifecycle.reset(timeout_seconds=startup)
        require(lifecycle.execute_sql("SELECT current_database();") == lifecycle.namespace.database_name,
                "reset reached foreign database")
        migrations = bootstrap_module()
        migrations.bootstrap_two_phase(lifecycle)
        revision = lifecycle.execute_sql("SELECT version_num FROM alembic_version;")
        require(revision == migrations.HEAD_REVISION, "migrated head mismatch")
        lifecycle.execute_sql("CREATE TABLE public.kl074_reset_sentinel (value integer);")
        lifecycle.execute_sql("INSERT INTO public.kl074_reset_sentinel VALUES (74);")
        lifecycle.reset(timeout_seconds=startup)
        require(lifecycle.execute_sql("SELECT to_regclass('public.kl074_reset_sentinel') IS NULL;") == "t",
                "repeated reset retained sentinel")
        require(lifecycle.execute_sql("SELECT current_database();") == lifecycle.namespace.database_name,
                "repeated reset reached foreign database")
        save_json(evidence / "assertions.json", {
            "tested_commit": tested_commit, "root": str(root),
            "project_name": lifecycle.namespace.project_name,
            "database_name": lifecycle.namespace.database_name,
            "migrated_revision": revision, "expected_revision": migrations.HEAD_REVISION,
            "sentinel_removed": True, "current_database_verified_twice": True,
            "status": "PASS",
        })
    except Exception as error:
        save_json(evidence / "worker-failure.json", {
            "status": "FAIL", "diagnostic": str(runner.redactor.exception_diagnostic(error)),
        })
        raise SystemExit(1) from None


def verify_ordering(logs: str, events: list[dict[str, Any]]) -> dict[str, object]:
    lines = logs.splitlines()
    def position(fragment: str, start: int = 0) -> int:
        return next((i for i in range(start, len(lines)) if fragment in lines[i]), -1)
    socket = position('listening on Unix socket')
    init_ready = position('database system is ready to accept connections', socket + 1)
    stop = position('received fast shutdown request', init_ready + 1)
    stopped = position('database system is shut down', stop + 1)
    final_tcp = position('listening on IPv4 address "0.0.0.0", port 5432', stopped + 1)
    final_ready = position('database system is ready to accept connections', final_tcp + 1)
    require(0 <= socket < init_ready < stop < stopped < final_tcp < final_ready,
            "actual image init-stop-final log ordering unavailable")
    require(not any('listening on IPv4' in line or 'listening on IPv6' in line
                    for line in lines[:stop]), "initialization server was not socket-only")
    # Docker timestamps establish actual-server ordering; events establish lifecycle SQL gating.
    require(all(re.match(r"\d{4}-\d\d-\d\dT", lines[index])
                for index in (socket, init_ready, stop, stopped, final_tcp, final_ready)),
            "missing timestamped actual container logs")
    first_ready = next((i for i, event in enumerate(events)
                        if event['kind'] == 'tcp_probe_end' and event['returncode'] == 0), -1)
    first_sql = next((i for i, event in enumerate(events) if event['kind'] == 'sql_begin'), -1)
    require(0 <= first_ready < first_sql, "SQL occurred before measured final TCP readiness")
    socket_only = any(
        event['kind'] == 'socket_probe' and event['returncode'] == 0
        and any(item['kind'] == 'tcp_probe_end' and item['returncode'] != 0
                for item in events[i + 1:i + 3])
        for i, event in enumerate(events[:first_ready])
    )
    require(socket_only, "actual socket-ready/TCP-unready measurement unavailable")
    require(datetime.fromisoformat(events[first_sql]['utc'])
            > datetime.fromisoformat(lines[final_ready].split(' ', 1)[0]),
            "SQL timestamp did not follow final-server log readiness")
    return {"init_socket_line": socket + 1, "init_ready_line": init_ready + 1,
            "init_stop_line": stop + 1, "init_stopped_line": stopped + 1,
            "final_tcp_line": final_tcp + 1, "final_ready_line": final_ready + 1,
            "socket_only_measured": True, "sql_before_final_readiness": 0, "status": "PASS"}


def capture(lifecycle: DatabaseLifecycle, evidence: Path, deadline: float) -> None:
    containers = resources(lifecycle.namespace, deadline)["containers"]
    require(len(containers) == 1, "expected exactly one owned postgres container")
    container = containers[0]
    topology = json.loads(command_output([
        "docker", "inspect", "--format",
        '{"project":{{json (index .Config.Labels "com.docker.compose.project")}},"mounts":{{json .Mounts}},"networks":{{json .NetworkSettings.Networks}}}',
        container,
    ], deadline))
    require(topology['project'] == lifecycle.namespace.project_name,
            "container project label mismatch")
    require(any(mount.get('Name') == f"{lifecycle.namespace.project_name}_postgres-data"
                and mount['Destination'] == '/var/lib/postgresql/data'
                for mount in topology['mounts']), "actual owned volume mismatch")
    require(set(topology['networks']) == {f"{lifecycle.namespace.project_name}_default"},
            "actual owned network mismatch")
    save_json(evidence / "actual-topology.json", topology)
    image_id = command_output(["docker", "inspect", "--format", "{{.Image}}", container], deadline)
    image = json.loads(command_output([
        "docker", "image", "inspect", "--format",
        '{"id":{{json .Id}},"digests":{{json .RepoDigests}},"entrypoint":{{json .Config.Entrypoint}}}',
        image_id,
    ], deadline))
    configured = command_output(["docker", "inspect", "--format", "{{.Config.Image}}", container], deadline)
    require(configured == "postgres:16.10-alpine" and image['id'] == image_id and bool(image['digests']),
            "actual configured/resolved image provenance mismatch")
    source = bounded_run(["docker", "exec", container, "cat", "/usr/local/bin/docker-entrypoint.sh"],
                         deadline, check=True, capture_output=True, text=True).stdout
    actual_hash = command_output(["docker", "exec", container, "sha256sum", "/usr/local/bin/docker-entrypoint.sh"], deadline).split()[0]
    require(hashlib.sha256(source.encode()).hexdigest() == actual_hash, "entrypoint source/hash mismatch")
    (evidence / "docker-entrypoint.sh.txt").write_text(source)
    # PostgreSQL writes to stderr; capture both streams without losing timestamped lines.
    raw = bounded_run(["docker", "logs", "--timestamps", container], deadline,
                      check=True, capture_output=True, text=True)
    save_json(evidence / "container-raw-log.json", {
        "stdout": raw.stdout, "stderr": raw.stderr,
        "stdout_sha256": hashlib.sha256(raw.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(raw.stderr.encode()).hexdigest(),
    })
    logs = "\n".join(sorted((raw.stdout + raw.stderr).splitlines())) + "\n"
    (evidence / "container.log").write_text(logs)
    save_json(evidence / "image-provenance.json", {
        "configured_image": configured, "resolved_image": image,
        "entrypoint_sha256": actual_hash, "container": container,
        "docker_version": command_output(["docker", "version", "--format", "{{.Server.Version}}"], deadline),
        "compose_version": command_output(["docker", "compose", "version", "--short"], deadline),
        "postgres_version": command_output(["docker", "exec", container, "postgres", "--version"], deadline),
    })
    events = [json.loads(line) for line in (evidence / "events.jsonl").read_text().splitlines()]
    save_json(evidence / "ordering.json", verify_ordering(logs, events))


def iteration(index: int, tested_commit: str, evidence: Path, deadline: float, startup: float) -> dict[str, str]:
    evidence.mkdir()
    with tempfile.TemporaryDirectory(prefix="kineticloop-kl074-cold-") as temporary:
        root = (Path(temporary) / "KineticLoop").resolve()
        namespace = owned_namespace(root, tested_commit)
        require(not any(resources(namespace, deadline).values()), "preexisting owned resources rejected")
        command_output(["git", "worktree", "add", "--detach", str(root), tested_commit], deadline)
        require(command_output(["git", "-C", str(root), "rev-parse", "HEAD"], deadline) == tested_commit,
                "temporary worktree head mismatch")
        lifecycle = DatabaseLifecycle(root, runner=lambda command, **kwargs: bounded_run(command, deadline, **kwargs))
        lifecycle.namespace = namespace
        validate_owned(lifecycle, tested_commit)
        save_json(evidence / "ownership-before.json", {
            "tested_commit": tested_commit, "root": str(root),
            "project_name": namespace.project_name, "database_name": namespace.database_name,
            "preexisting_resources": resources(namespace, deadline),
            "compose_sha256": hashlib.sha256(lifecycle.compose_file.read_bytes()).hexdigest(),
        })
        process = multiprocessing.get_context("fork").Process(
            target=worker, args=(root, tested_commit, evidence, deadline - 20, startup))
        try:
            process.start()
            process.join(max(0, deadline - 25 - time.monotonic()))
            if process.is_alive():
                process.terminate()
                process.join(2)
                if process.is_alive():
                    process.kill()
                    process.join(2)
                raise DatabaseLifecycleError("bounded coldstart worker deadline expired")
            require(process.exitcode == 0, "coldstart worker failed; retained raw diagnostics")
        finally:
            # Only a namespace validated before first mutation can reach destructive cleanup.
            validate_owned(lifecycle, tested_commit)
            errors: list[str] = []
            redactor = Redactor(("kineticloop-local-only", "kl072-local-only"))
            try:
                capture(lifecycle, evidence, deadline - 10)
            except Exception as error:
                errors.append(str(redactor.exception_diagnostic(error)))
                save_json(evidence / "capture-failure.json", {"diagnostic": errors[-1]})
            try:
                lifecycle.destroy()
            except Exception as error:
                errors.append(str(redactor.exception_diagnostic(error)))
            remaining: dict[str, list[str]] | None = None
            try:
                remaining = resources(namespace, deadline)
            except Exception as error:
                errors.append(str(redactor.exception_diagnostic(error)))
            save_json(evidence / "cleanup.json", {
                "project_name": namespace.project_name, "remaining_resources": remaining,
                "errors": errors,
                "status": "PASS" if not errors and remaining is not None and not any(remaining.values()) else "FAIL",
            })
            try:
                command_output(["git", "worktree", "remove", "--force", str(root)], deadline)
            except Exception as error:
                errors.append(str(redactor.exception_diagnostic(error)))
                save_json(evidence / "worktree-cleanup-failure.json", {"diagnostic": errors[-1]})
            require(not errors and remaining is not None and not any(remaining.values()),
                    "owned capture/cleanup failed; retained diagnostics")
    return {"project_name": namespace.project_name, "database_name": namespace.database_name}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--startup-timeout", type=float, default=60)
    parser.add_argument("--total-timeout", type=float, default=300)
    args = parser.parse_args()
    require(args.iterations == 3, "exactly three coldstarts required")
    require(math.isfinite(args.startup_timeout) and 0 < args.startup_timeout <= 60,
            "startup timeout must be positive and at most 60 seconds")
    require(math.isfinite(args.total_timeout) and 30 < args.total_timeout <= 300,
            "total timeout must reserve cleanup and be at most 300 seconds")
    started = time.monotonic()
    deadline = started + args.total_timeout
    head = command_output(["git", "rev-parse", "HEAD"], deadline)
    evidence = validate_environment(dict(os.environ), head)
    require(command_output(["docker", "context", "show"], deadline) == "default", "nondefault Docker context")
    require(command_output(["docker", "context", "inspect", "default", "--format",
                            "{{.Endpoints.docker.Host}}"], deadline) == "unix:///var/run/docker.sock",
            "nonlocal Docker endpoint")
    evidence.mkdir(parents=True, exist_ok=True)
    require(not any(evidence.glob("iteration-*")), "coldstart evidence cannot be overwritten")
    try:
        namespaces = [iteration(i, head, evidence / f"iteration-{i}", deadline, args.startup_timeout)
                      for i in range(1, 4)]
        require(len({item['project_name'] for item in namespaces}) == 3
                and len({item['database_name'] for item in namespaces}) == 3,
                "cross-root namespaces collided")
        summary = {"status": "PASS", "tested_commit": head, "iterations": namespaces,
                   "cross_root_separation": True, "elapsed_seconds": time.monotonic() - started}
        save_json(evidence / "coldstart-summary.json", summary)
        print(json.dumps(summary, sort_keys=True))
    except Exception as error:
        summary = {"status": "FAIL", "tested_commit": head,
                   "diagnostic": str(Redactor(("kineticloop-local-only", "kl072-local-only")).exception_diagnostic(error)),
                   "elapsed_seconds": time.monotonic() - started}
        save_json(evidence / "coldstart-summary.json", summary)
        print(json.dumps(summary, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
