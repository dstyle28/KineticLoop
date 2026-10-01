"""Manifest identity, freeze, source custody and negative leakage controls."""

import json
from pathlib import Path

import pytest

from kineticloop.evaluation import Manifest, Observation, score
from kineticloop.evaluation.manifest import Case
from kineticloop.primitives import canonical_json, canonical_sha256

ROOT = Path(__file__).resolve().parents[2]


def fixture():
    manifest = Manifest.from_json(
        (ROOT / "tests/evaluation/predeclared_manifest.json").read_text().strip()
    )
    raw = json.loads((ROOT / "tests/evaluation/synthetic_cases.json").read_text())
    assert raw["cases"] == manifest.model_dump(mode="json")["cases"]
    observations = tuple(Observation.from_json(canonical_json(o)) for o in raw["observations"])
    sources = {s.path: (ROOT / s.path).read_bytes() for c in manifest.cases for s in c.sources}
    scorer_bytes = (ROOT / "src/kineticloop/evaluation/scorer.py").read_bytes()
    return manifest, observations, sources, scorer_bytes


def evaluate(manifest=None, observations=None):
    original, captured, sources, scorer_bytes = fixture()
    return score(
        original if manifest is None else manifest,
        captured if observations is None else observations,
        source_bytes=sources,
        scorer_bytes=scorer_bytes,
    )


def parse_manifest(payload):
    return Manifest.from_json(canonical_json(payload))


def rebind(payload):
    """Compute genuinely new identities for structural-negative tests, never mutate fixtures."""
    for case in payload["cases"]:
        case["case_id"] = canonical_sha256({k: v for k, v in case.items() if k != "case_id"})
    payload["dataset_id"] = canonical_sha256(payload["cases"])
    payload["split_id"] = canonical_sha256(
        {
            k: payload[k]
            for k in (
                "dataset_id",
                "train",
                "tune",
                "test",
                "dataset_frozen_at",
                "splits_frozen_at",
            )
        }
    )
    payload["config_hash"] = canonical_sha256(payload["metrics"])
    payload["release_id"] = canonical_sha256(
        {k: v for k, v in payload.items() if k not in {"release_id", "evaluation_id"}}
    )
    payload["evaluation_id"] = canonical_sha256(
        {k: v for k, v in payload.items() if k != "evaluation_id"}
    )
    return payload


def test_manifest_identity_and_freeze():
    manifest, _, sources, scorer_bytes = fixture()
    assert Manifest.from_json(manifest.to_json()) == manifest
    manifest.verify_sources(sources, scorer_bytes)
    for field in ("case_id", "input_hash"):
        case = manifest.cases[0].model_dump(mode="json")
        case[field] = "A" * 64
        with pytest.raises(ValueError):
            Case.from_json(canonical_json(case))
    for field in (
        "dataset_id",
        "split_id",
        "scorer_hash",
        "config_hash",
        "release_id",
        "evaluation_id",
        "dataset_frozen_at",
        "splits_frozen_at",
    ):
        raw = manifest.model_dump(mode="json")
        raw[field] = "0" * 64 if field.endswith(("id", "hash")) else "2026-01-05T00:00:00Z"
        with pytest.raises(ValueError):
            parse_manifest(raw)
    raw = manifest.model_dump(mode="json")
    raw["cases"][0]["input_json"] = canonical_json({"changed": True})
    with pytest.raises(ValueError):
        parse_manifest(raw)
    with pytest.raises(ValueError):
        manifest.verify_sources(sources, scorer_bytes + b"\n# changed")
    wrong_sources = dict(sources)
    wrong_sources[next(iter(sources))] += b"\n"
    with pytest.raises(ValueError):
        manifest.verify_sources(wrong_sources, scorer_bytes)
    for mutation in ("extra", "missing", "duplicate"):
        raw = manifest.model_dump(mode="json")
        if mutation == "extra":
            raw["expert_quality_score"] = 100
        if mutation == "missing":
            del raw["dataset_frozen_at"]
        serialized = canonical_json(raw)
        if mutation == "duplicate":
            serialized = serialized[:-1] + ',"test":[]}'
        with pytest.raises(ValueError):
            Manifest.from_json(serialized)
    with pytest.raises(ValueError):
        manifest.dataset_id = "0" * 64
    raw = manifest.model_dump(mode="json")
    raw["test"].clear()
    assert len(manifest.test) == 8


def test_split_and_knowledge_boundary():
    manifest, _, _, _ = fixture()
    for field in ("available_at", "known_at"):
        raw = manifest.model_dump(mode="json")
        raw["cases"][0][field] = "2026-01-05T00:00:00Z"
        with pytest.raises(ValueError):
            parse_manifest(rebind(raw))
    for key, value in (
        ("kind", "outcome_label"),
        ("known_at", "2026-01-05T00:00:00Z"),
        ("available_at", "2026-01-05T00:00:00Z"),
    ):
        raw = manifest.model_dump(mode="json")
        captured = json.loads(raw["cases"][0]["input_json"])
        captured["available_data"][0][key] = value
        raw["cases"][0]["input_json"] = canonical_json(captured)
        raw["cases"][0]["input_hash"] = canonical_sha256(captured)
        with pytest.raises(ValueError):
            parse_manifest(rebind(raw))
    for split in ("train", "tune", "test"):
        raw = manifest.model_dump(mode="json")
        raw[split].append(manifest.test[0])
        with pytest.raises(ValueError):
            parse_manifest(rebind(raw))
    raw = manifest.model_dump(mode="json")
    raw["test"].pop()
    with pytest.raises(ValueError):
        parse_manifest(rebind(raw))
    raw = manifest.model_dump(mode="json")
    raw["cases"][1]["input_json"] = raw["cases"][0]["input_json"]
    raw["cases"][1]["input_hash"] = raw["cases"][0]["input_hash"]
    rebind(raw)
    raw["test"] = [c["case_id"] for c in raw["cases"]]
    with pytest.raises(ValueError, match="underlying input"):
        parse_manifest(rebind(raw))
    raw = manifest.model_dump(mode="json")
    raw["tuning"] = "TUNED_ON_TEST_INDEPENDENT_VALIDATION"
    with pytest.raises(ValueError):
        parse_manifest(rebind(raw))
    raw = manifest.model_dump(mode="json")
    raw["splits_frozen_at"] = raw["outputs_not_before"]
    with pytest.raises(ValueError):
        parse_manifest(rebind(raw))
