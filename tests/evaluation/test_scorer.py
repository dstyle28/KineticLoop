"""Source-derived mechanical categories and exhaustive captured-observation controls."""

import json
from hashlib import sha256

import pytest
from test_manifest import evaluate, fixture, parse_manifest, rebind

from kineticloop.evaluation import Observation, score
from kineticloop.evaluation.manifest import CATEGORIES, EXPECTATIONS
from kineticloop.primitives import canonical_json, canonical_sha256


def changed(observation, **fields):
    raw = observation.model_dump(mode="json")
    raw.update(fields)
    return Observation.from_json(canonical_json(raw))


def test_source_derived_cases():
    manifest, observations, sources, _ = fixture()
    report = evaluate()
    assert tuple(r.category for r in report.rows) == CATEGORIES
    assert report.counts.passed == report.counts.denominator == 8
    for case, row in zip(manifest.cases, report.rows, strict=True):
        assert row.actual == EXPECTATIONS[case.category]
        for source in case.sources:
            assert sha256(sources[source.path]).hexdigest() == source.sha256
            assert source.excerpt in sources[source.path].decode()
    # Every mandatory category has a negative control: wrong output/failure never passes its oracle.
    for index, observation in enumerate(observations):
        raw = observation.model_dump(mode="json")
        if observation.outcome == "output":
            raw.update(
                outcome="refusal",
                output_json=None,
                output_hash=canonical_sha256(None),
                absent_reason="refusal",
            )
        else:
            raw.update(
                outcome="output",
                output_json=canonical_json({"incomplete": True}),
                output_hash=canonical_sha256({"incomplete": True}),
                absent_reason=None,
                timed_out=False,
                elapsed_ms=1,
            )
        replacement = Observation.from_json(canonical_json(raw))
        mutant = observations[:index] + (replacement,) + observations[index + 1 :]
        result = evaluate(observations=mutant)
        assert result.mechanical_status == "FAIL"
        assert result.rows[index].mechanical_pass is False
    raw = manifest.model_dump(mode="json")
    raw["cases"][0]["sources"][0]["clause"] = "unrelated"
    with pytest.raises(ValueError):
        parse_manifest(rebind(raw))
    raw = manifest.model_dump(mode="json")
    raw["cases"][0]["expected"] = "EXPERT_FITNESS_QUALITY_PASS"
    with pytest.raises(ValueError):
        parse_manifest(rebind(raw))


def test_complete_observations():
    manifest, observations, sources, scorer_bytes = fixture()
    for captured in (
        (),
        observations[:-1],
        observations + (observations[0],),
        (observations[0],) + observations[:-1],
    ):
        with pytest.raises(ValueError):
            evaluate(observations=captured)
    foreign = changed(observations[0], case_id="0" * 64)
    with pytest.raises(ValueError):
        evaluate(observations=(foreign,) + observations[1:])
    for field in (
        "dataset_id",
        "split_id",
        "evaluation_id",
        "release_id",
        "input_hash",
        "output_hash",
    ):
        with pytest.raises(ValueError):
            evaluate(
                observations=(changed(observations[0], **{field: "0" * 64}),) + observations[1:]
            )
    for field, value in (
        ("execution", "UNEXECUTED"),
        ("observed_at", "2026-01-01T00:00:00Z"),
        ("evidence_refs", []),
        ("timed_out", True),
        ("elapsed_ms", -1),
        ("absent_reason", "timeout"),
        ("output_json", None),
        ("extra", "capability"),
    ):
        with pytest.raises(ValueError):
            evaluate(observations=(changed(observations[0], **{field: value}),) + observations[1:])
    for index in (1, 3, 4, 5):
        assert observations[index].output_json is None
        assert observations[index].absent_reason == observations[index].outcome
        with pytest.raises(ValueError):
            changed(observations[index], absent_reason=None)
    with pytest.raises(ValueError):
        changed(observations[3], elapsed_ms=1)
    for category in CATEGORIES:
        raw = manifest.model_dump(mode="json")
        raw["cases"] = [c for c in raw["cases"] if c["category"] != category]
        raw["test"] = [c["case_id"] for c in raw["cases"]]
        with pytest.raises(ValueError):
            parse_manifest(rebind(raw))
    # Even a recomputed scorer digest cannot retain the predeclared release/evaluation identity.
    raw = manifest.model_dump(mode="json")
    raw["scorer_hash"] = sha256(scorer_bytes + b"changed").hexdigest()
    with pytest.raises(ValueError):
        parse_manifest(raw)
    new = parse_manifest(rebind(raw))
    assert new.release_id != manifest.release_id
    with pytest.raises(ValueError):
        score(new, observations, source_bytes=sources, scorer_bytes=scorer_bytes + b"changed")
    for index in range(4):
        raw = manifest.model_dump(mode="json")
        artifact = raw["artifacts"][index]
        content = json.loads(artifact["content_json"])
        content["revision"] = "changed"
        artifact["content_json"] = canonical_json(content)
        artifact["content_hash"] = canonical_sha256(content)
        artifact["ref_id"] = canonical_sha256({k: v for k, v in artifact.items() if k != "ref_id"})
        new = parse_manifest(rebind(raw))
        assert new.release_id != manifest.release_id
        with pytest.raises(ValueError):
            evaluate(manifest=new)
    raw = manifest.model_dump(mode="json")
    raw["metrics"]["threshold"] = "INVENTED_QUALITY_THRESHOLD"
    with pytest.raises(ValueError):
        parse_manifest(rebind(raw))


def test_all_live_targets_capabilities_and_late_data_reject():
    _, observations, _, _ = fixture()
    original = observations[0]
    for field in (
        "s38_live_head_target",
        "s42_production_issuance_target",
        "s45_execution_binding_target",
        "live_planning_intent_success_target",
        "execution_capability",
    ):
        output = json.loads(original.output_json)
        output["artifact"][field] = "00000000-0000-4000-8000-000000000003"
        mutant = changed(
            original, output_json=canonical_json(output), output_hash=canonical_sha256(output)
        )
        result = evaluate(observations=(mutant,) + observations[1:])
        assert result.rows[0].actual == "REJECT_EXECUTION"
        assert result.mechanical_status == "FAIL"
    for field, value in (
        ("known_at", "2026-01-05T00:00:00Z"),
        ("available_at", "2026-01-05T00:00:00Z"),
        ("kind", "outcome_label"),
    ):
        output = json.loads(original.output_json)
        output["used_data"][0][field] = value
        mutant = changed(
            original, output_json=canonical_json(output), output_hash=canonical_sha256(output)
        )
        result = evaluate(observations=(mutant,) + observations[1:])
        assert result.rows[0].actual == "REJECT_KNOWLEDGE_BOUNDARY"
        assert result.rows[0].predicates.cutoff_adherent is False
        assert result.mechanical_status == "FAIL"
    for output in ("{not valid JSON", {"artifact": None}, None):
        # Malformed raw text is itself captured losslessly as a canonical JSON string.
        mutant = changed(
            original, output_json=canonical_json(output), output_hash=canonical_sha256(output)
        )
        assert evaluate(observations=(mutant,) + observations[1:]).rows[0].actual == "REJECT_FORMAT"
    serialized = original.to_json()
    with pytest.raises(ValueError):
        Observation.from_json(serialized[:-1] + ',"outcome":"output"}')
    for field in original.model_dump():
        raw = original.model_dump(mode="json")
        del raw[field]
        with pytest.raises(ValueError):
            Observation.from_json(canonical_json(raw))
