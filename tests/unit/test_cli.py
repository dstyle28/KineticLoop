"""Exercise the installed entrypoint and its exit status contract."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KL = Path(sys.executable).with_name("kl")


def test_harness_entrypoint_from_subdirectory():
    result = subprocess.run([KL, "check-harness"], cwd=ROOT / "src", capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HARNESS_CHECK_PASS" in result.stdout


def test_protocol_model_is_explicitly_not_run():
    result = subprocess.run([KL, "test-protocol-model"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "PROTOCOL_MODEL_NOT_RUN" in result.stdout


def test_invalid_harness_argument_propagates_failure():
    result = subprocess.run([KL, "check-harness", "--invalid"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
