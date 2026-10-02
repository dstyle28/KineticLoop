from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_spec = importlib.util.spec_from_file_location(
    "db_ci", Path(__file__).parents[2] / "tools/harness/db_ci.py")
assert _spec is not None and _spec.loader is not None
db_ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db_ci)

SHA = "a" * 40


@pytest.fixture
def evidence(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    directory = tmp_path / "evidence"
    directory.mkdir()
    original = Path("/evidence/run")
    commands = db_ci.command_plan(original, SHA) + [
        ("destroy", ["uv", "run", "python", "tools/db/verify.py", "destroy"]),
        ("peer_remove", ["git", "worktree", "remove", "--force", "/evidence/run-peer"]),
    ]
    checks = []
    for name, command in commands:
        path = directory / (name + ".log")
        path.write_text("raw output\n")
        checks.append({"check_id": name, "argv": command, "exit_code": 0,
                       "interrupted": False, "stdout": db_ci.file_record(path)})
    nodeids = ["tests/db/test_example.py::test_case[parameter::with::colons]"]
    for name in ("collection.json", "execution.json"):
        db_ci.write_json(directory / name, {"nodeids": nodeids, "exit_code": 0})
    (directory / "database.xml").write_text(
        '<testsuites><testsuite><testcase classname="tests.db.test_example" '
        'name="test_case[parameter::with::colons]"/></testsuite></testsuites>')
    manifest = {"format": db_ci.FORMAT, "tested_commit": SHA, "status": "PASS",
                "checks": checks, "provenance": {
                    "environment": "local-isolated", "os": "Linux",
                    "docker_endpoint": "unix:///var/run/docker.sock",
                    "initial_containers": [], "initial_volumes": []},
                "artifacts": [db_ci.file_record(directory / name) for name in
                              ("collection.json", "execution.json", "database.xml")],
                "junit": {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}}
    db_ci.write_json(directory / "manifest.json", manifest)
    return directory, manifest


def test_evidence_accepts_exact_commands_and_parameterized_identity(evidence):
    directory, manifest = evidence
    assert db_ci.validate_evidence(directory, SHA) == manifest


@pytest.mark.parametrize("mutation", [
    "sha", "missing_check", "failure", "bool_exit", "interrupted", "selector", "hash",
    "missing_hash", "path", "symlink", "collection", "junit_identity", "skipped", "zero",
    "environment", "populated",
])
def test_evidence_rejects_false_pass(evidence, mutation):
    directory, manifest = evidence
    if mutation == "sha":
        manifest["tested_commit"] = "b" * 40
    elif mutation == "missing_check":
        manifest["checks"].pop()
    elif mutation == "failure":
        manifest["checks"][0]["exit_code"] = 1
    elif mutation == "bool_exit":
        manifest["checks"][0]["exit_code"] = False
    elif mutation == "interrupted":
        manifest["checks"][0]["interrupted"] = True
    elif mutation == "selector":
        manifest["checks"][3]["argv"][-2] = "tests/db/test_lifecycle.py"
    elif mutation == "hash":
        (directory / "lint.log").write_text("rewritten")
    elif mutation == "missing_hash":
        manifest["artifacts"].pop()
    elif mutation == "path":
        manifest["checks"][0]["stdout"]["path"] = "../lint.log"
    elif mutation == "symlink":
        source = directory / "lint.log"
        source.unlink()
        source.symlink_to(directory / "typecheck.log")
    elif mutation == "collection":
        db_ci.write_json(directory / "execution.json", {"nodeids": ["tests/db/test_other.py::test_other"], "exit_code": 0})
    elif mutation == "junit_identity":
        path = directory / "database.xml"
        path.write_text(path.read_text().replace("test_case[", "different_test["))
    elif mutation == "skipped":
        path = directory / "database.xml"
        path.write_text(path.read_text().replace('/>', '><skipped/></testcase>'))
        manifest["junit"]["skipped"] = 1
    elif mutation == "zero":
        for name in ("collection.json", "execution.json"):
            db_ci.write_json(directory / name, {"nodeids": [], "exit_code": 0})
        (directory / "database.xml").write_text("<testsuites/>")
        manifest["junit"]["tests"] = 0
    elif mutation == "environment":
        manifest["provenance"]["environment"] = "unknown"
    elif mutation == "populated":
        manifest["provenance"]["initial_containers"] = ["foreign"]
    # Even honestly rehashed invalid semantics must be rejected.
    if mutation in ("collection", "junit_identity", "skipped", "zero"):
        manifest["artifacts"] = [db_ci.file_record(directory / name) for name in
                                 ("collection.json", "execution.json", "database.xml")]
    db_ci.write_json(directory / "manifest.json", manifest)
    with pytest.raises(ValueError):
        db_ci.validate_evidence(directory, SHA)


def test_failed_process_raw_output_is_preserved(tmp_path):
    result = db_ci.run_capture([sys.executable, "-c", "print('failure detail'); raise SystemExit(7)"],
                              tmp_path, "failure", timeout=5)
    assert result["exit_code"] == 7
    assert (tmp_path / "failure.log").read_bytes() == b"failure detail\n"
    assert result["stdout"] == db_ci.file_record(tmp_path / "failure.log")


def test_timeout_is_never_pass(tmp_path):
    result = db_ci.run_capture([sys.executable, "-u", "-c", "import time; print('started'); time.sleep(30)"],
                              tmp_path, "timeout", timeout=1)
    assert result["exit_code"] == 124 and result["interrupted"]
    assert (tmp_path / "timeout.log").read_bytes() == b"started\n"


@pytest.mark.parametrize("reason", ["dirty", "remote", "context", "socket", "containers", "volumes", "not_hosted"])
def test_preflight_denies_shared_or_wrong_environment_before_lifecycle(monkeypatch, reason):
    monkeypatch.setattr(db_ci.platform, "system", lambda: "Linux")
    monkeypatch.setattr(db_ci, "resolve_revision", lambda _: SHA)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setenv("RUNNER_OS", "Linux")
    if reason == "remote":
        monkeypatch.setenv("DOCKER_HOST", "tcp://foreign:2375")
    if reason == "not_hosted":
        monkeypatch.setenv("RUNNER_ENVIRONMENT", "self-hosted")
    calls = []

    def output(argv):
        calls.append(argv)
        if argv[:2] == ["git", "status"]:
            return " M changed.py" if reason == "dirty" else ""
        if argv[:3] == ["docker", "context", "show"]:
            return "foreign" if reason == "context" else "default"
        if argv[:3] == ["docker", "context", "inspect"]:
            return "tcp://foreign:2375" if reason == "socket" else "unix:///var/run/docker.sock"
        if argv[:2] == ["docker", "ps"]:
            return "foreign" if reason == "containers" else ""
        if argv[:3] == ["docker", "volume", "ls"]:
            return "foreign" if reason == "volumes" else ""
        raise AssertionError(argv)

    monkeypatch.setattr(db_ci, "output", output)
    with pytest.raises(ValueError):
        db_ci.environment_preflight("github-hosted", SHA)
    assert not any("compose" in command or "destroy" in command for command in calls)


def test_failed_preflight_never_runs_cleanup_on_foreign_daemon(monkeypatch, tmp_path):
    def reject(*args):
        raise ValueError("foreign daemon")
    monkeypatch.setattr(db_ci, "environment_preflight", reject)
    monkeypatch.setattr(db_ci, "run_capture", lambda *a, **kw: pytest.fail("lifecycle called"))
    args = argparse.Namespace(revision=SHA, environment="local-isolated", evidence_dir=tmp_path / "run")
    assert db_ci.execute(args) == 1
    assert json.loads((args.evidence_dir / "manifest.json").read_text())["status"] == "FAIL"


def test_workflows_local_default_and_explicit_hosted_fallback():
    root = Path(__file__).parents[2]
    ci = yaml.load((root / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    db = yaml.load((root / ".github/workflows/db.yml").read_text(), Loader=yaml.BaseLoader)
    assert ci["on"]["push"]["branches"] == ["master"]
    assert "pull_request" in ci["on"]
    assert ci["concurrency"]["cancel-in-progress"] == "true"
    assert set(db["on"]) == {"workflow_dispatch"}
    assert db["on"]["workflow_dispatch"]["inputs"]["revision"]["required"] == "true"
    assert "record-evidence" not in db["jobs"]
    steps = db["jobs"]["kl-002-database"]["steps"]
    assert any("tools/harness/db_ci.py run" in step.get("run", "") for step in steps)
    assert steps[-1]["if"] == "always()"


@pytest.mark.parametrize("change", ["bind", "extra", "foreign", "socket", "host_network"])
def test_mount_guard_rejects_shared_resources(change):
    inspect: dict[str, Any] = {"Mounts": [{"Type": "volume", "Name": "owned", "Destination": "/var/lib/docker"}],
               "HostConfig": {"NetworkMode": "default"}}
    if change == "bind":
        inspect["Mounts"][0]["Type"] = "bind"
    elif change == "extra":
        inspect["Mounts"].append({"Type": "bind", "Name": "", "Destination": "/host"})
    elif change == "foreign":
        inspect["Mounts"][0]["Name"] = "another-task"
    elif change == "socket":
        inspect["Mounts"][0]["Destination"] = "/var/run/docker.sock"
    else:
        inspect["HostConfig"]["NetworkMode"] = "host"
    with pytest.raises(ValueError):
        db_ci.owned_mounts(inspect, "owned")


def test_mount_guard_accepts_only_own_data_volume():
    inspect: dict[str, Any] = {"Mounts": [{"Type": "volume", "Name": "owned", "Destination": "/var/lib/docker"}],
               "HostConfig": {"NetworkMode": "default"}}
    assert db_ci.owned_mounts(inspect, "owned") == inspect["Mounts"]


def test_git_bound_evidence_ignores_ambient_edits_and_rejects_committed_symlink(evidence, tmp_path):
    import subprocess
    directory, _ = evidence
    repo = tmp_path / "repo"
    target = repo / "docs/exec-plans/evidence/HG-046/db"
    target.parent.mkdir(parents=True)
    import shutil
    shutil.copytree(directory, target)
    (repo / "tools/harness").mkdir(parents=True)
    assert db_ci.__file__ is not None
    shutil.copyfile(Path(db_ci.__file__), repo / "tools/harness/db_ci.py")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    def commit():
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "evidence"], cwd=repo, check=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    reviewed = commit()
    spec = importlib.util.spec_from_file_location(
        "review_guard", Path(__file__).parents[2] / "tools/harness/validate_harness.py")
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    ref = "docs/exec-plans/evidence/HG-046/db/manifest.json"
    assert guard.full_database_evidence_errors(repo, reviewed, SHA, ref) == []
    (target / "lint.log").write_text("ambient edited bytes")
    assert guard.full_database_evidence_errors(repo, reviewed, SHA, ref) == []
    (target / "lint.log").unlink()
    (target / "lint.log").symlink_to("typecheck.log")
    symlink_head = commit()
    assert any("raw-not-regular-reviewed-blob" in error for error in
               guard.full_database_evidence_errors(repo, symlink_head, SHA, ref))


@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("config", ['{"proxies":{"default":{"httpProxy":"secret-placeholder"}}}',
                                    '{"proxies":[]}', '{"proxies":null}', '[]', '{invalid'])
def test_local_rejects_implicit_proxy_config_before_docker(monkeypatch, tmp_path, override, config):
    monkeypatch.delenv("BUILDX_BUILDER", raising=False)
    monkeypatch.delenv("BUILDKIT_HOST", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    directory = tmp_path / ("custom" if override else ".docker")
    directory.mkdir()
    if override:
        monkeypatch.setenv("DOCKER_CONFIG", str(directory))
    else:
        monkeypatch.delenv("DOCKER_CONFIG", raising=False)
    (directory / "config.json").write_text(config)
    monkeypatch.setattr(db_ci, "output", lambda *a, **kw: pytest.fail("Docker called"))
    monkeypatch.setattr(db_ci, "run_capture", lambda *a, **kw: pytest.fail("build/run called"))
    with pytest.raises(ValueError, match="without proxy forwarding") as error:
        db_ci.local(argparse.Namespace())
    assert "secret-placeholder" not in str(error.value)


@pytest.mark.parametrize("override", ["BUILDX_BUILDER", "BUILDKIT_HOST"])
def test_local_rejects_ambient_builder_before_docker(monkeypatch, override):
    monkeypatch.setenv(override, "remote-placeholder")
    monkeypatch.setattr(db_ci, "output", lambda *a, **kw: pytest.fail("Docker called"))
    with pytest.raises(ValueError, match="builder overrides"):
        db_ci.local(argparse.Namespace())


@pytest.mark.parametrize("config", [None, '{}', '{"proxies":{}}', '{"credsStore":"desktop"}'])
def test_local_client_accepts_no_proxy_forwarding(monkeypatch, tmp_path, config):
    monkeypatch.delenv("BUILDX_BUILDER", raising=False)
    monkeypatch.delenv("BUILDKIT_HOST", raising=False)
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    if config is not None:
        (tmp_path / "config.json").write_text(config)
    db_ci.local_client_preflight()


def test_hg046_scope_admits_only_named_workflow_compatibility_tests():
    spec = importlib.util.spec_from_file_location(
        "scope_guard", Path(__file__).parents[2] / "tools/harness/validate_harness.py")
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    allowed = guard.governance_allowed_patterns("HG-046")
    assert guard.matches("tests/db/test_startup_readiness.py", allowed)
    assert guard.matches("tests/db/test_workflow.py", allowed)
    for path in ("tests/db/conftest.py", "tests/db/test_other.py", "src/kineticloop/db/lifecycle.py",
                 "docs/exec-plans/completed/KL-074_RESULT.yaml", ".github/workflows/kl074-readiness.yml"):
        assert not guard.matches(path, allowed)
    assert not guard.matches("tests/db/test_startup_readiness.py", guard.governance_allowed_patterns("HG-047"))
    assert not guard.matches("tests/db/test_workflow.py", guard.governance_allowed_patterns("HG-047"))
