"""Trusted worker entrypoint; invoke by absolute path with Python -I."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_harness  # noqa: E402

if __name__ == '__main__':
    sys.exit(validate_harness.main(sys.argv[1:], root=Path('/workspace/KineticLoop')))
