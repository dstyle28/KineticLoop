#!/usr/bin/env python3
"""Generate or verify the committed acceptance requirement registry fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kineticloop.acceptance import RegistryValidationError, build_registry


def _repository_root() -> Path:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "CURRENT_REQUIREMENT_SET.json").is_file():
            return candidate
    raise RegistryValidationError("run the fixture generator from a KineticLoop checkout")


def _render(root: Path) -> str:
    registry = build_registry(root)
    return json.dumps(registry.to_dict(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the committed fixture differs from the current indexed sources",
    )
    args = parser.parse_args(argv)
    try:
        root = _repository_root()
        output = root / "tests/fixtures/acceptance/requirement_registry.json"
        rendered = _render(root)
        if args.check:
            if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
                print(f"STALE: {output.relative_to(root)}", file=sys.stderr)
                return 1
            print(f"CURRENT: {output.relative_to(root)}")
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"WROTE: {output.relative_to(root)}")
        return 0
    except RegistryValidationError as error:
        print(f"INVALID_REQUIREMENT_REGISTRY: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
