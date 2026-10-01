"""Strict immutable canonical evidence; synthetic success never admits a release."""

from typing import Literal, Self, cast

from pydantic import model_validator

from kineticloop.primitives import canonical_sha256

from .manifest import FrozenValue, Manifest, Source, timestamp
from .scorer import Observation, classify


class Predicates(FrozenValue):
    complete_correspondence: bool
    format_or_failure_captured: bool
    non_executable: bool
    cutoff_adherent: bool
    input_immutable: bool


class MetricCount(FrozenValue):
    predicate: str
    passed: int
    denominator: int


class Row(FrozenValue):
    case_id: str
    category: str
    expected: str
    actual: str
    mechanical_pass: bool
    predicates: Predicates
    source_refs: tuple[Source, ...]
    observation: Observation


class Counts(FrozenValue):
    observed: int
    denominator: int
    passed: int
    metrics: tuple[MetricCount, ...]


class Statuses(FrozenValue):
    model_evaluation: Literal["NOT_RUN"]
    fitness_quality: Literal["NOT_RUN"]
    product_requirements: Literal["NOT_RUN"]
    remote_ai_gate: Literal["NOT_RUN"]
    m7: Literal["NOT_RUN"]
    release_admission: Literal["NOT_RUN"]


class LiveTargets(FrozenValue):
    s38: None
    s42: None
    s45: None
    live_success: None


LIMITATIONS = (
    "Declared synthetic freeze times are metadata, not historical custody proof.",
    "Current-algorithm derivations are counterfactual, never historically known facts.",
    "Current model broad training knowledge cannot reconstruct past model knowledge.",
    "No recommendation quality, independent tuned-model validation or causal effects measured.",
)


class Report(FrozenValue):
    wire_schema: Literal["kineticloop-synthetic-report-v1"]
    manifest: Manifest
    rows: tuple[Row, ...]
    counts: Counts
    mechanical_status: Literal["PASS", "FAIL"]
    provenance: Literal["SYNTHETIC_LOCAL_COUNTERFACTUAL"]
    execution_disposition: Literal["NOT_EXECUTABLE"]
    live_targets: LiveTargets
    statuses: Statuses
    measured_model_result: None
    rollout_decision: Literal["NO_ROLLOUT_DECISION"]
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def valid(self) -> Self:
        if (
            tuple(r.case_id for r in self.rows) != self.manifest.test
            or self.limitations != LIMITATIONS
        ):
            raise ValueError("complete ordered report and explicit limitations required")
        for case, row in zip(self.manifest.cases, self.rows, strict=True):
            o = row.observation
            if (
                row.category != case.category
                or row.expected != case.expected
                or row.source_refs != case.sources
                or o.case_id != case.case_id
                or o.dataset_id != self.manifest.dataset_id
                or o.split_id != self.manifest.split_id
                or o.evaluation_id != self.manifest.evaluation_id
                or o.release_id != self.manifest.release_id
                or o.artifacts != self.manifest.artifacts
                or o.input_json != case.input_json
                or o.input_hash != case.input_hash
                or timestamp(o.observed_at) < timestamp(self.manifest.outputs_not_before)
                or row.actual != classify(o, case)
                or row.mechanical_pass != (row.actual == case.expected)
                or row.predicates
                != Predicates(
                    complete_correspondence=True,
                    format_or_failure_captured=row.actual == case.expected,
                    non_executable=True,
                    cutoff_adherent=(
                        row.actual != "REJECT_KNOWLEDGE_BOUNDARY"
                        or case.expected == "REJECT_KNOWLEDGE_BOUNDARY"
                    ),
                    input_immutable=True,
                )
            ):
                raise ValueError("report evidence binding or mechanical result mismatch")
        passed = sum(r.mechanical_pass for r in self.rows)
        if self.counts != Counts(
            observed=len(self.rows),
            denominator=len(self.manifest.test),
            passed=passed,
            metrics=tuple(
                MetricCount(
                    predicate=name,
                    passed=sum(r.predicates.model_dump()[name] for r in self.rows),
                    denominator=len(self.rows),
                )
                for name in self.manifest.metrics.predicates
            ),
        ) or self.mechanical_status != ("PASS" if passed == len(self.rows) else "FAIL"):
            raise ValueError("report counts/status mismatch")
        return self

    @classmethod
    def build(cls, manifest: Manifest, rows: list[dict[str, object]]) -> Self:
        # JSON parsing gives tuples for strict immutable sequence fields.
        from kineticloop.primitives import canonical_json

        rows = [dict(row) for row in rows]
        passed = sum(row["mechanical_pass"] is True for row in rows)
        for row in rows:
            row["predicates"] = {
                "complete_correspondence": True,
                "format_or_failure_captured": row["mechanical_pass"],
                "non_executable": True,
                "cutoff_adherent": row["actual"] != "REJECT_KNOWLEDGE_BOUNDARY"
                or row["expected"] == "REJECT_KNOWLEDGE_BOUNDARY",
                "input_immutable": True,
            }
        metric_counts = [
            {
                "predicate": name,
                "passed": sum(
                    cast(dict[str, object], row["predicates"])[name] is True for row in rows
                ),
                "denominator": len(rows),
            }
            for name in manifest.metrics.predicates
        ]
        return cls.from_json(
            canonical_json(
                {
                    "wire_schema": "kineticloop-synthetic-report-v1",
                    "manifest": manifest.model_dump(mode="json"),
                    "rows": rows,
                    "counts": {
                        "observed": len(rows),
                        "denominator": len(manifest.test),
                        "passed": passed,
                        "metrics": metric_counts,
                    },
                    "mechanical_status": "PASS" if passed == len(manifest.test) else "FAIL",
                    "provenance": "SYNTHETIC_LOCAL_COUNTERFACTUAL",
                    "execution_disposition": "NOT_EXECUTABLE",
                    "live_targets": dict.fromkeys(("s38", "s42", "s45", "live_success")),
                    "statuses": dict.fromkeys(
                        (
                            "model_evaluation",
                            "fitness_quality",
                            "product_requirements",
                            "remote_ai_gate",
                            "m7",
                            "release_admission",
                        ),
                        "NOT_RUN",
                    ),
                    "measured_model_result": None,
                    "rollout_decision": "NO_ROLLOUT_DECISION",
                    "limitations": list(LIMITATIONS),
                }
            )
        )

    def to_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json")

    @property
    def content_hash(self) -> str:
        return canonical_sha256(self.to_payload())
