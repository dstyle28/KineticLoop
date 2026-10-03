"""Launch pytest with the installed observer loaded by absolute file identity."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def main(argv: list[str]) -> int:
    path = Path(__file__).resolve().with_name('db_ci_pytest.py')
    spec = importlib.util.spec_from_file_location('kineticloop_trusted_observer', path)
    assert spec is not None and spec.loader is not None
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    # Candidate imports are needed by tests, after the observer is already loaded.
    sys.path.append(str(Path.cwd()))
    return int(pytest.main(argv, plugins=[observer]))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
