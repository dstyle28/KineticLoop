"""Canonical reporting preserves synthetic limitations and prevents admission claims."""

import ast
import json

import pytest
from test_manifest import ROOT, evaluate, fixture
from test_scorer import changed

from kineticloop.evaluation import Report
from kineticloop.primitives import canonical_json, canonical_sha256


def test_deterministic_report():
    manifest, observations, _, _ = fixture()
    first = evaluate()
    second = evaluate(observations=tuple(reversed(observations)))
    assert first.to_json().encode() == second.to_json().encode()
    assert first.content_hash == canonical_sha256(second.to_payload())
    assert Report.from_json(first.to_json()) == first
    caller = first.to_payload()
    caller["rows"][0]["observation"]["input_json"] = "mutated"
    caller["manifest"]["cases"].clear()
    assert first.counts.observed == len(first.rows) == len(manifest.cases) == 8
    for row, observation in zip(first.rows, observations, strict=True):
        assert row.observation == observation
        assert row.source_refs
        assert row.observation.input_hash == canonical_sha256(
            json.loads(row.observation.input_json)
        )
        output = json.loads(row.observation.output_json) if row.observation.output_json else None
        assert row.observation.output_hash == canonical_sha256(output)
    with pytest.raises(ValueError):
        first.mechanical_status = "FAIL"
    for key in ("extra", "missing", "duplicate", "counts", "forged_actual"):
        raw = first.to_payload()
        if key == "extra":
            raw["quality_weight"] = 1
        if key == "missing":
            del raw["provenance"]
        if key == "counts":
            raw["counts"]["passed"] = 0
        if key == "forged_actual":
            raw["rows"][0]["actual"] = "QUALITY_PASS"
        serialized = canonical_json(raw)
        if key == "duplicate":
            serialized = serialized[:-1] + ',"rows":[]}'
        with pytest.raises(ValueError):
            Report.from_json(serialized)
    raw = observations[0].model_dump(mode="json")
    raw["input_json"] = canonical_json({"changed": True})
    raw["input_hash"] = canonical_sha256({"changed": True})
    with pytest.raises(ValueError):
        evaluate(observations=(changed(observations[0], **raw),) + observations[1:])


def test_no_release_or_execution_claim():
    report = evaluate()
    assert report.mechanical_status == "PASS"
    assert report.execution_disposition == "NOT_EXECUTABLE"
    assert set(report.statuses.model_dump().values()) == {"NOT_RUN"}
    assert report.measured_model_result is None
    assert report.rollout_decision == "NO_ROLLOUT_DECISION"
    assert all(value is None for value in report.live_targets.model_dump().values())
    assert all(a.registration == "LOCAL_UNREGISTERED_FIXTURE" for a in report.manifest.artifacts)
    assert "counterfactual" in report.to_json()
    assert "past model knowledge" in report.to_json()
    for field in report.statuses.model_dump():
        raw = report.to_payload()
        raw["statuses"][field] = "PASS"
        with pytest.raises(ValueError):
            Report.from_json(canonical_json(raw))
    for field in report.live_targets.model_dump():
        raw = report.to_payload()
        raw["live_targets"][field] = "live-target"
        with pytest.raises(ValueError):
            Report.from_json(canonical_json(raw))
    for captured in ((), fixture()[1][:-1]):
        with pytest.raises(ValueError):
            evaluate(observations=captured)
    # A source audit guards the local package's intentionally tiny, IO-free dependency surface.
    forbidden = (
        "socket",
        "requests",
        "httpx",
        "psycopg",
        "sqlalchemy",
        "subprocess",
        "kineticloop.persistence",
        "kineticloop.agents",
        "kineticloop.providers",
    )
    for path in (ROOT / "src/kineticloop/evaluation").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(name.startswith(forbidden) for name in names)
            assert not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "open"
            )


def test_metric_counts_and_report_build_copy():
    report = evaluate()
    assert [m.predicate for m in report.counts.metrics] == list(report.manifest.metrics.predicates)
    assert all(m.denominator == m.passed == 8 for m in report.counts.metrics)
    rows = [row.model_dump(mode="json") for row in report.rows]
    before = canonical_json(rows)
    rebuilt = Report.build(report.manifest, rows)
    assert canonical_json(rows) == before
    assert rebuilt.content_hash == report.content_hash
    for field in report.to_payload():
        raw = report.to_payload()
        del raw[field]
        with pytest.raises(ValueError):
            Report.from_json(canonical_json(raw))
    raw = report.to_payload()
    raw["counts"]["metrics"][0]["passed"] = 0
    with pytest.raises(ValueError):
        Report.from_json(canonical_json(raw))
