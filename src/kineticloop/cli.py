"""Stable engineering commands, run from a KineticLoop checkout."""

import argparse
import subprocess
import sys
from pathlib import Path


def repository_root() -> Path:
    for root in (Path.cwd(), *Path.cwd().parents):
        if (root / "CURRENT_DOCUMENT_INDEX.json").is_file():
            return root
    raise ValueError("Run kl from a KineticLoop checkout.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=[
        "check-harness", "lint", "typecheck", "test-unit", "test-harness", "test-protocol-model"
    ])
    args, extra = parser.parse_known_args(argv)
    if args.command == "test-protocol-model":
        print("PROTOCOL_MODEL_NOT_RUN: model source is unavailable; no protocol evidence claimed.")
        return 2
    try:
        root = repository_root()
    except ValueError as error:
        parser.error(str(error))
    commands = {
        "check-harness": [str(root / "tools/harness/validate_harness.py")],
        "lint": ["-m", "ruff", "check", "."],
        "typecheck": ["-m", "mypy"],
        "test-unit": ["-m", "pytest", "tests/unit"],
        "test-harness": [str(root / "tools/harness/run_harness_tests.py")],
    }
    return subprocess.call([sys.executable, *commands[args.command], *extra], cwd=root)


if __name__ == "__main__":
    sys.exit(main())
