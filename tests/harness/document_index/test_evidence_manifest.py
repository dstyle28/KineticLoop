"""Evidence handoff path and missing-source checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from conftest import write_json

from kineticloop.harness.documents import ValidationError, validate_evidence_manifest


def test_manifest_verifies_paths_and_reports_every_missing_model_input(
    indexed_root: Path,
) -> None:
    report = validate_evidence_manifest(indexed_root)

    assert "05_KineticLoop_Protocol_v1.2_FROZEN.md" in report.verified_paths
    assert "04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md" in report.verified_paths
    assert any(path.endswith("protocol_model_report.md") for path in report.verified_paths)
    assert {finding.artifact_kind for finding in report.missing} == {
        "MODEL_SOURCE",
        "MODEL_REPORT",
        "POLICY_FIXTURE",
        "SOURCE_REVISION",
    }
    assert {finding.path for finding in report.missing if finding.path} == {
        "protocol_model/run_model.py",
        "protocol_model/reports/model_report.json",
        "protocol_model/fixtures.json",
        "protocol_model/policies.json",
    }
    assert report.historical_claims_status == "UNVERIFIED_HISTORICAL_DECLARATION"


def test_available_evidence_must_exist_and_match_hash(indexed_root: Path) -> None:
    manifest_path = indexed_root / "KineticLoop_Evidence_Manifest_v0.1.json"
    manifest = json.loads(manifest_path.read_text())
    available_path = indexed_root / manifest["available_evidence"][0]["path"]
    available_path.unlink()

    with pytest.raises(ValidationError, match="evidence-missing"):
        validate_evidence_manifest(indexed_root)


def test_unbound_source_copy_cannot_silently_close_handoff_gap(indexed_root: Path) -> None:
    unexpected = indexed_root / "protocol_model/run_model.py"
    unexpected.parent.mkdir(parents=True)
    unexpected.write_text("# unbound source copy\n")

    with pytest.raises(ValidationError, match="evidence-unresolved-path-present"):
        validate_evidence_manifest(indexed_root)


def test_authority_binding_cannot_drift_from_document_index(indexed_root: Path) -> None:
    path = indexed_root / "KineticLoop_Evidence_Manifest_v0.1.json"
    manifest = json.loads(path.read_text())
    manifest["protocol_sha256"] = "0" * 64
    write_json(path, manifest)
    index_path = indexed_root / "CURRENT_DOCUMENT_INDEX.json"
    index = json.loads(index_path.read_text())
    indexed_manifest = next(
        entry
        for entry in index["machine_readable"]
        if entry["path"] == "KineticLoop_Evidence_Manifest_v0.1.json"
    )
    indexed_manifest["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(index_path, index)

    with pytest.raises(ValidationError, match="evidence-authority-binding:DOC-PROTOCOL-V1.2"):
        validate_evidence_manifest(indexed_root)


@pytest.mark.parametrize(
    "field,value,diagnostic",
    [
        ("freeze_evidence_status", "FULLY_REPRODUCIBLE_AND_APPROVED", "evidence-freeze-status"),
        (
            "historical_declared_results_status",
            "VERIFIED",
            "evidence-historical-results-status",
        ),
        (
            "historical_declared_results",
            {"original_model_cases": "999/999"},
            "evidence-historical-results-declaration",
        ),
    ],
)
def test_historical_evidence_claims_cannot_be_promoted_or_rewritten(
    indexed_root: Path, field: str, value: object, diagnostic: str
) -> None:
    path = indexed_root / "KineticLoop_Evidence_Manifest_v0.1.json"
    manifest = json.loads(path.read_text())
    manifest[field] = value
    write_json(path, manifest)
    index_path = indexed_root / "CURRENT_DOCUMENT_INDEX.json"
    index = json.loads(index_path.read_text())
    indexed_manifest = next(
        entry
        for entry in index["machine_readable"]
        if entry["path"] == "KineticLoop_Evidence_Manifest_v0.1.json"
    )
    indexed_manifest["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(index_path, index)

    with pytest.raises(ValidationError, match=diagnostic):
        validate_evidence_manifest(indexed_root)
