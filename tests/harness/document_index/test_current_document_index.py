"""Stable-ID document index checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from conftest import write_json

from kineticloop.harness.documents import DocumentIndex, ValidationError


def test_every_canonical_document_resolves_by_stable_id(indexed_root: Path) -> None:
    raw = json.loads((indexed_root / "CURRENT_DOCUMENT_INDEX.json").read_text())
    index = DocumentIndex.load(indexed_root)

    assert index.document_ids == tuple(entry["document_id"] for entry in raw["documents"])
    for expected in raw["documents"]:
        resolved = index.resolve(expected["document_id"])
        assert resolved.path == expected["path"]
        assert resolved.absolute_path.is_file()
        assert hashlib.sha256(resolved.absolute_path.read_bytes()).hexdigest() == expected["sha256"]


def test_filename_is_not_an_authority_alias(indexed_root: Path) -> None:
    index = DocumentIndex.load(indexed_root)

    with pytest.raises(ValidationError, match="unknown-document-id"):
        index.resolve("05_KineticLoop_Protocol_v1.2_FROZEN.md")


@pytest.mark.parametrize("mutation,diagnostic", [
    ("duplicate-id", "document-index-duplicate-id:DOC-PROTOCOL-V1.2"),
    ("bad-hash", "document-index-hash:05_KineticLoop_Protocol_v1.2_FROZEN.md"),
    ("history-authority", "document-index-current-points-to-history"),
])
def test_invalid_current_index_is_rejected(
    indexed_root: Path, mutation: str, diagnostic: str
) -> None:
    path = indexed_root / "CURRENT_DOCUMENT_INDEX.json"
    index = json.loads(path.read_text())
    if mutation == "duplicate-id":
        duplicate = dict(index["documents"][0])
        duplicate["path"] = index["documents"][1]["path"]
        index["documents"].append(duplicate)
    elif mutation == "bad-hash":
        index["documents"][0]["sha256"] = "0" * 64
    else:
        source = indexed_root / index["documents"][0]["path"]
        historical = indexed_root / "docs/history/v1.2.2/protocol.md"
        historical.parent.mkdir(parents=True)
        historical.write_bytes(source.read_bytes())
        index["documents"][0]["path"] = "docs/history/v1.2.2/protocol.md"
    write_json(path, index)

    with pytest.raises(ValidationError, match=diagnostic):
        DocumentIndex.load(indexed_root)
