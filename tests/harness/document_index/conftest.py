"""Fixtures for document handoff validation."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@pytest.fixture
def indexed_root(tmp_path: Path) -> Path:
    index = json.loads((ROOT / "CURRENT_DOCUMENT_INDEX.json").read_text())
    paths = ["CURRENT_DOCUMENT_INDEX.json"]
    paths.extend(entry["path"] for entry in index["documents"])
    paths.extend(entry["path"] for entry in index["machine_readable"])
    manifest = json.loads((ROOT / "KineticLoop_Evidence_Manifest_v0.1.json").read_text())
    paths.extend(entry["path"] for entry in manifest["available_evidence"])
    for relative in dict.fromkeys(paths):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return tmp_path


@pytest.fixture
def historical_root(tmp_path: Path) -> Path:
    mapping = json.loads((ROOT / "HISTORICAL_TASK_ID_MAP.json").read_text())
    write_json(tmp_path / "HISTORICAL_TASK_ID_MAP.json", mapping)
    for source in mapping["namespace_sources"]:
        destination = tmp_path / source["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source["path"], destination)
    return tmp_path
