"""Exercise real child processes, worker evidence and serial resource admission."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("parallel_runner", ROOT / "tools/harness/run_harness_tests.py")
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def repository(tmp_path: Path, source: str) -> Path:
    root = tmp_path / "repo"
    (root / "tools/harness").mkdir(parents=True)
    (root / "tests/harness").mkdir(parents=True)
    for name in ("run_harness_tests.py", "parallel_observer.py"):
        shutil.copyfile(ROOT / "tools/harness" / name, root / "tools/harness" / name)
    (root / "tests/harness/test_example.py").write_text(source)
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\naddopts = "-ra"\n')
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    commit(root)
    return root


def commit(root: Path) -> None:
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "commit", "-qm", "fixture"], cwd=root, check=True)


def run(root: Path, workers: int, directory: Path, *options: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    return subprocess.run([sys.executable, str(root / "tools/harness/run_harness_tests.py"),
                           "--workers", str(workers), "--evidence-dir", str(directory),
                           "-q", *options], cwd=root, env=env,
                          capture_output=True, text=True, timeout=90)


def test_same_nodes_actual_execution_and_junit_across_workers(tmp_path: Path) -> None:
    root = repository(tmp_path, """import os
import pytest
@pytest.mark.parametrize('value', range(8))
def test_case(value, tmp_path):
    (tmp_path / 'owner').write_text(str(os.getpid()))
    assert (tmp_path / 'owner').read_text() == str(os.getpid())
""")
    nodes = None
    for workers in (1, 2, 4):
        directory = tmp_path / str(workers)
        result = run(root, workers, directory)
        assert result.returncode == 0, result.stdout + result.stderr
        manifest = json.loads((directory / "manifest.json").read_text())
        record = json.loads((directory / "execution.json").read_text())
        assert manifest["workers"] == workers and manifest["errors"] == []
        assert manifest["dirty_source"] is False
        assert len(record["collections"]) == (workers if workers > 1 else 1)
        collected = next(iter(record["collections"].values()))
        if nodes is None:
            nodes = collected
        assert nodes == collected
        assert sorted(record["started"]) == sorted(nodes)
        assert len(record["started"]) == 8
        assert len(record["reports"]) == 24
        assert all(item["outcome"] == "passed" for item in record["reports"])
        for item in manifest["files"]:
            assert runner.file_record(directory / item["path"]) == item
        assert manifest["tested_commit"] == subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        assert "8 passed" in (directory / "pytest.log").read_text()
        assert (directory / "junit.xml").is_file()


@pytest.mark.parametrize("source", [
    "def test_case():\n    assert False, 'failure detail'\n",
    "import pytest\n@pytest.fixture\ndef bad():\n    raise RuntimeError('setup detail')\n"
    "def test_case(bad):\n    pass\n",
    "import pytest\n@pytest.mark.skip(reason='skip detail')\ndef test_case():\n    pass\n",
])
def test_failures_and_skips_cannot_create_success(tmp_path: Path, source: str) -> None:
    root = repository(tmp_path, source)
    result = run(root, 2, tmp_path / "evidence")
    assert result.returncode == 1, result.stdout + result.stderr
    manifest = json.loads((tmp_path / "evidence/manifest.json").read_text())
    assert manifest["exit_code"] == 1 and manifest["errors"]
    assert (tmp_path / "evidence/pytest.log").read_text()


def test_parallel_scope_exclusive_resources_and_serial_support(tmp_path: Path) -> None:
    root = repository(tmp_path, """import pytest
@pytest.mark.harness_serial
def test_case():
    pass
""")
    parallel = run(root, 2, tmp_path / "parallel")
    assert parallel.returncode != 0
    assert "Exclusive resource requires --workers 1" in parallel.stdout
    serial = run(root, 1, tmp_path / "serial")
    assert serial.returncode == 0, serial.stdout + serial.stderr
    (root / "tests/harness/test_example.py").write_text("def test_case():\n    pass\n")
    (root / "tests/db").mkdir()
    (root / "tests/db/test_forbidden.py").write_text(
        "def test_db():\n    raise AssertionError('DB EXECUTED')\n")
    commit(root)
    foreign = run(root, 2, tmp_path / "foreign", "tests/db")
    assert foreign.returncode != 0
    assert "Parallel harness scope violation" in foreign.stdout
    assert "DB EXECUTED" not in foreign.stdout


@pytest.mark.parametrize("options", [
    ("--workers", "0"), ("--workers", "5"), ("--workers", "auto"),
    ("-n", "8"), ("-n8",), ("--numprocesses=8",), ("--dist=each",),
    ("--tx=popen",), ("--max-worker-restart=10",),
])
def test_unbounded_or_duplicate_topology_rejected(tmp_path: Path, options: tuple[str, ...]) -> None:
    root = repository(tmp_path, "def test_case():\n    pass\n")
    result = run(root, 2, tmp_path / "evidence", *options)
    assert result.returncode == 2
    assert not (tmp_path / "evidence").exists()


def test_dirty_source_and_reused_evidence_rejected(tmp_path: Path) -> None:
    root = repository(tmp_path, "def test_case():\n    pass\n")
    (root / "dirty").write_text("uncommitted")
    result = run(root, 1, tmp_path / "evidence")
    assert result.returncode == 2 and "Commit source" in result.stderr
    commit(root)
    (tmp_path / "evidence").mkdir()
    sentinel = tmp_path / "evidence/sentinel"
    sentinel.write_text("preserved")
    result = run(root, 1, tmp_path / "evidence")
    assert result.returncode != 0
    assert sentinel.read_text() == "preserved"


def test_worker_crash_does_not_restart_or_claim_complete_execution(tmp_path: Path) -> None:
    root = repository(tmp_path, "import os\ndef test_crash():\n    os._exit(23)\n")
    result = run(root, 2, tmp_path / "crash")
    assert result.returncode != 0
    manifest = json.loads((tmp_path / "crash/manifest.json").read_text())
    assert manifest["errors"] and manifest["exit_code"] != 0
    assert "--max-worker-restart" in manifest["command"]


def test_aggregation_rejects_partial_or_mismatched_worker_evidence() -> None:
    record = {"collections": {"gw0": ["a"], "gw1": ["b"]}, "started": ["a", "a"],
              "reports": [], "errors": []}
    errors = runner.evidence_errors(record, 2, False)
    assert "worker-collection-mismatch" in errors
    assert "execution-collection-mismatch" in errors
    assert "missing-or-duplicate-call" in errors
    assert "missing-worker-collection" in runner.evidence_errors(record, 4, False)


def test_legacy_junit_export_and_collection_only_mode(tmp_path: Path) -> None:
    root = repository(tmp_path, "def test_case():\n    pass\n")
    for workers in (1, 2):
        directory = tmp_path / ("run-" + str(workers))
        exported = tmp_path / ("legacy-" + str(workers) + ".xml")
        result = run(root, workers, directory, "--junitxml", str(exported))
        assert result.returncode == 0, result.stdout + result.stderr
        assert exported.read_bytes() == (directory / "junit.xml").read_bytes()
        manifest = json.loads((directory / "manifest.json").read_text())
        assert manifest["mode"] == "EXECUTION" and manifest["execution_complete"] is True
    collection = run(root, 2, tmp_path / "collection", "--collect-only")
    assert collection.returncode == 0, collection.stdout + collection.stderr
    manifest = json.loads((tmp_path / "collection/manifest.json").read_text())
    assert manifest["mode"] == "COLLECTION_ONLY" and manifest["execution_complete"] is False
    inside = run(root, 2, root / "new-evidence")
    assert inside.returncode == 2 and "outside the source checkout" in inside.stderr
    assert not (root / "new-evidence").exists()
