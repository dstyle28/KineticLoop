"""Deterministic mechanical checks over complete captured synthetic observations."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, Self

from pydantic import model_validator

from kineticloop.contracts.shadow import ShadowContractError, ShadowEvaluationArtifact
from kineticloop.primitives import canonical_sha256

from .manifest import Artifact, Case, FrozenValue, Manifest, digest, snapshot, timestamp

if TYPE_CHECKING:
    from .report import Report


class Observation(FrozenValue):
    case_id: str
    dataset_id: str
    split_id: str
    evaluation_id: str
    release_id: str
    artifacts: tuple[Artifact, ...]
    provenance: Literal["SYNTHETIC_LOCAL_COUNTERFACTUAL"]
    execution_disposition: Literal["NOT_EXECUTABLE"]
    execution: Literal["EXECUTED"]
    observed_at: str
    outcome: Literal[
        "output",
        "refusal",
        "timeout",
        "tool_failure",
        "budget_exhaustion",
    ]
    input_json: str
    input_hash: str
    output_json: str | None
    output_hash: str
    absent_reason: str | None
    elapsed_ms: int
    timeout_ms: int
    timed_out: bool
    evidence_refs: tuple[str, ...]

    @model_validator(mode="after")
    def valid(self) -> Self:
        for value in (
            self.case_id,
            self.dataset_id,
            self.split_id,
            self.evaluation_id,
            self.release_id,
            self.input_hash,
            self.output_hash,
        ):
            digest(value)
        timestamp(self.observed_at)
        if canonical_sha256(snapshot(self.input_json)) != self.input_hash:
            raise ValueError("captured input hash mismatch")
        output = snapshot(self.output_json) if self.output_json is not None else None
        if canonical_sha256(output) != self.output_hash:
            raise ValueError("captured output hash mismatch")
        if self.outcome == "output":
            if self.output_json is None or self.absent_reason is not None or self.timed_out:
                raise ValueError("output requires present output, no absent reason, no timeout")
        elif self.output_json is not None or self.absent_reason != self.outcome:
            raise ValueError("failure/refusal requires explicit absent output and matching reason")
        if (
            self.elapsed_ms < 0
            or self.timeout_ms <= 0
            or self.timed_out != (self.outcome == "timeout")
            or self.timed_out != (self.elapsed_ms >= self.timeout_ms)
        ):
            raise ValueError("inconsistent observed timeout evidence")
        if not self.evidence_refs or any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("captured observation evidence required")
        return self


def classify(observation: Observation, case: Case) -> str:
    if observation.outcome != "output":
        return {
            "refusal": "CAPTURE_REFUSAL",
            "timeout": "CAPTURE_TIMEOUT",
            "tool_failure": "CAPTURE_TOOL_FAILURE",
            "budget_exhaustion": "CAPTURE_BUDGET_EXHAUSTION",
        }[observation.outcome]
    assert observation.output_json is not None
    output = snapshot(observation.output_json)
    if type(output) is not dict or set(output) != {"artifact", "proposal_json", "used_data"}:
        return "REJECT_FORMAT"
    artifact = output["artifact"]
    try:
        ShadowEvaluationArtifact.from_payload(artifact)
    except (ShadowContractError, ValueError, TypeError):
        # Unknown capabilities/targets are rejected with the same non-executable oracle.
        return "REJECT_EXECUTION"
    try:
        if type(output["proposal_json"]) is not str:
            return "REJECT_FORMAT"
        snapshot(output["proposal_json"])
        data = output["used_data"]
        if type(data) is not list:
            return "REJECT_FORMAT"
        for member in data:
            if type(member) is not dict or set(member) != {"available_at", "known_at", "kind"}:
                return "REJECT_FORMAT"
            if (
                member["kind"] != "synthetic_input"
                or timestamp(member["known_at"]) > timestamp(case.cutoff)
                or timestamp(member["available_at"]) > timestamp(case.cutoff)
            ):
                return "REJECT_KNOWLEDGE_BOUNDARY"
    except (ValueError, TypeError):
        return "REJECT_FORMAT"
    captured = snapshot(case.input_json)
    assert type(captured) is dict
    if output["used_data"] != captured["available_data"]:
        return "REJECT_KNOWLEDGE_BOUNDARY"
    return "ACCEPT_NON_EXECUTABLE"


def score(
    manifest: Manifest,
    observations: tuple[Observation, ...],
    *,
    source_bytes: Mapping[str, bytes],
    scorer_bytes: bytes,
) -> "Report":
    """Require exact predeclared evidence; success denotes only mechanical fixture handling."""
    from .report import Report

    manifest.verify_sources(source_bytes, scorer_bytes)
    # Revalidate instead of trusting model_copy/model_construct bypasses from external callers.
    manifest = Manifest.from_json(manifest.to_json())
    observations = tuple(Observation.from_json(o.to_json()) for o in observations)
    by_case = {o.case_id: o for o in observations}
    if len(by_case) != len(observations) or set(by_case) != set(manifest.test):
        raise ValueError("missing/duplicate/extra or unexecuted observations")
    rows = []
    for case in manifest.cases:
        observation = by_case[case.case_id]
        if (
            observation.dataset_id != manifest.dataset_id
            or observation.split_id != manifest.split_id
            or observation.evaluation_id != manifest.evaluation_id
            or observation.release_id != manifest.release_id
            or observation.artifacts != manifest.artifacts
            or observation.input_json != case.input_json
            or observation.input_hash != case.input_hash
            or timestamp(observation.observed_at) < timestamp(manifest.outputs_not_before)
        ):
            raise ValueError("stale binding, altered input or prefreeze observation")
        actual = classify(observation, case)
        rows.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "expected": case.expected,
                "actual": actual,
                "mechanical_pass": actual == case.expected,
                "source_refs": [s.model_dump(mode="json") for s in case.sources],
                "observation": observation.model_dump(mode="json"),
            }
        )
    return Report.build(manifest, rows)
