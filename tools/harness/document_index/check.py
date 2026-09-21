#!/usr/bin/env python3
"""Run one KL-006 document/evidence handoff check."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from kineticloop.harness.documents import (  # noqa: E402
    DocumentIndex,
    HistoricalTaskMap,
    ValidationError,
    validate_evidence_manifest,
)

CHECKS = (
    "current_document_index_resolves",
    "evidence_manifest_paths_resolve",
    "historical_task_id_map_valid",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("check", choices=CHECKS)
    args = parser.parse_args(argv)
    try:
        if args.check == "current_document_index_resolves":
            index = DocumentIndex.load(ROOT)
            for document_id in index.document_ids:
                index.resolve(document_id)
            print(f"CURRENT_DOCUMENT_INDEX_PASS resolved={len(index.document_ids)}")
        elif args.check == "evidence_manifest_paths_resolve":
            report = validate_evidence_manifest(ROOT)
            print(f"EVIDENCE_MANIFEST_PASS verified_paths={len(report.verified_paths)}")
            for finding in report.missing:
                location = finding.path or "<no-bound-revision>"
                print(f"MISSING_{finding.artifact_kind} {finding.artifact_id} path={location}")
        else:
            count = HistoricalTaskMap.validate(ROOT)
            print(f"HISTORICAL_TASK_ID_MAP_PASS mappings={count}")
    except ValidationError as error:
        print("DOCUMENT_HANDOFF_CHECK_FAIL")
        print("\n".join(error.errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
