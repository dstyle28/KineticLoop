"""Strict immutable synthetic evaluation definitions; no storage or capabilities."""

import json
import re
from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from kineticloop.primitives import canonical_json, canonical_sha256

CATEGORIES = (
    "well_formed",
    "refusal",
    "malformed",
    "timeout",
    "tool_failure",
    "budget_exhaustion",
    "forbidden_target",
    "knowledge_cutoff",
)
Category = Literal[
    "well_formed",
    "refusal",
    "malformed",
    "timeout",
    "tool_failure",
    "budget_exhaustion",
    "forbidden_target",
    "knowledge_cutoff",
]
EXPECTATIONS = dict(
    zip(
        CATEGORIES,
        (
            "ACCEPT_NON_EXECUTABLE",
            "CAPTURE_REFUSAL",
            "REJECT_FORMAT",
            "CAPTURE_TIMEOUT",
            "CAPTURE_TOOL_FAILURE",
            "CAPTURE_BUDGET_EXHAUSTION",
            "REJECT_EXECUTION",
            "REJECT_KNOWLEDGE_BOUNDARY",
        ),
        strict=True,
    )
)
SOURCE_CLAUSES = {
    "well_formed": (
        "docs/contracts/shadow_test_semantics.md",
        "Real-data shadow evaluation artifact",
    ),
    "refusal": ("06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md", "G-REMOTE-AI"),
    "malformed": ("06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md", "G-REMOTE-AI"),
    "timeout": ("06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md", "G-REMOTE-AI"),
    "tool_failure": ("06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md", "M7"),
    "budget_exhaustion": ("06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md", "M7"),
    "forbidden_target": ("03_KineticLoop_Technical_Spec_v1.2.2_DEV_READY.md", "23.2"),
    "knowledge_cutoff": ("05_KineticLoop_Protocol_v1.2_FROZEN.md", "7.3"),
}


def digest(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("expected canonical SHA256 identity")
    return value


def snapshot(value: str) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, member in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = member
        return result

    parsed = json.loads(value, object_pairs_hook=unique)
    if canonical_json(parsed) != value:
        raise ValueError("captured JSON must be canonical")
    return parsed


def timestamp(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("timestamp must be canonical UTC seconds")
    return parsed


class FrozenValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    def to_json(self) -> str:
        return canonical_json(self.model_dump(mode="json"))

    @classmethod
    def from_json(cls, value: str) -> Self:
        # Duplicate detection precedes Pydantic's JSON parsing (which otherwise accepts duplicates).
        snapshot(value)
        return cls.model_validate_json(value)

    def identity(self, field: str) -> str:
        return canonical_sha256(self.model_dump(mode="json", exclude={field}))


class Source(FrozenValue):
    path: str
    sha256: str
    clause: str
    excerpt: str

    @model_validator(mode="after")
    def valid(self) -> Self:
        digest(self.sha256)
        if (
            not self.path
            or self.path.startswith("/")
            or ".." in self.path.split("/")
            or not self.clause
            or not self.excerpt
        ):
            raise ValueError("source path, clause and excerpt required")
        return self


class Case(FrozenValue):
    case_id: str
    category: Category
    expected: str
    provenance: Literal["SYNTHETIC_LOCAL_COUNTERFACTUAL"]
    input_json: str
    input_hash: str
    cutoff: str
    available_at: str
    known_at: str
    sources: tuple[Source, ...]

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.expected != EXPECTATIONS[self.category]:
            raise ValueError("only source-derived mechanical expectations allowed")
        if canonical_sha256(snapshot(self.input_json)) != digest(self.input_hash):
            raise ValueError("input hash mismatch")
        if self.identity("case_id") != digest(self.case_id):
            raise ValueError("case identity mismatch")
        cutoff = timestamp(self.cutoff)
        if timestamp(self.available_at) > cutoff or timestamp(self.known_at) > cutoff:
            raise ValueError("input unavailable at knowledge cutoff")
        captured = snapshot(self.input_json)
        if (
            type(captured) is not dict
            or set(captured) != {"synthetic_sample", "available_data"}
            or type(captured["synthetic_sample"]) is not str
            or not captured["synthetic_sample"].strip()
            or type(captured["available_data"]) is not list
        ):
            raise ValueError("strict synthetic input envelope required")
        for member in captured["available_data"]:
            if (
                type(member) is not dict
                or set(member) != {"available_at", "known_at", "kind"}
                or member["kind"] != "synthetic_input"
                or timestamp(member["available_at"]) > cutoff
                or timestamp(member["known_at"]) > cutoff
                or timestamp(member["available_at"]) > timestamp(self.available_at)
                or timestamp(member["known_at"]) > timestamp(self.known_at)
            ):
                raise ValueError("unavailable individual data or future outcome label")
        path, clause = SOURCE_CLAUSES[self.category]
        if not any(s.path == path and s.clause == clause for s in self.sources):
            raise ValueError("missing mandatory oracle source")
        return self


class Artifact(FrozenValue):
    kind: Literal["model", "prompt", "engine", "policy"]
    ref_id: str
    version: Literal["synthetic-fixture-v1"]
    content_json: str
    content_hash: str
    registration: Literal["LOCAL_UNREGISTERED_FIXTURE"]

    @model_validator(mode="after")
    def valid(self) -> Self:
        if canonical_sha256(snapshot(self.content_json)) != digest(self.content_hash):
            raise ValueError("artifact content mismatch")
        if self.identity("ref_id") != digest(self.ref_id):
            raise ValueError("artifact reference mismatch")
        return self


class Metrics(FrozenValue):
    predicates: tuple[
        Literal[
            "complete_correspondence",
            "format_or_failure_captured",
            "non_executable",
            "cutoff_adherent",
            "input_immutable",
        ],
        ...,
    ]
    threshold: Literal["ALL_SOURCE_DERIVED_BOOLEAN_PREDICATES"]

    @model_validator(mode="after")
    def valid(self) -> Self:
        if self.predicates != (
            "complete_correspondence",
            "format_or_failure_captured",
            "non_executable",
            "cutoff_adherent",
            "input_immutable",
        ):
            raise ValueError("exact mechanical predicates required")
        return self


class Manifest(FrozenValue):
    wire_schema: Literal["kineticloop-synthetic-eval-v1"]
    evaluation_id: str
    release_id: str
    dataset_id: str
    split_id: str
    cases: tuple[Case, ...]
    train: tuple[str, ...]
    tune: tuple[str, ...]
    test: tuple[str, ...]
    dataset_frozen_at: str
    splits_frozen_at: str
    outputs_not_before: str
    freeze_custody: Literal["DECLARED_SYNTHETIC_METADATA_ONLY"]
    available_data_rule: Literal["AVAILABLE_AND_KNOWN_AT_OR_BEFORE_CUTOFF_NO_OUTCOME_LABELS"]
    tuning: Literal["NO_TRAINING_OR_TUNING_NO_TEST_REUSE"]
    scorer_version: Literal["mechanical-v1"]
    scorer_hash: str
    metrics: Metrics
    config_hash: str
    artifacts: tuple[Artifact, ...]
    rollout_decision: Literal["NO_ROLLOUT_DECISION"]

    @model_validator(mode="after")
    def valid(self) -> Self:
        for value in (
            self.dataset_id,
            self.split_id,
            self.scorer_hash,
            self.config_hash,
            self.release_id,
            self.evaluation_id,
        ):
            digest(value)
        if not self.cases or {c.category for c in self.cases} != set(CATEGORIES):
            raise ValueError("all mandatory categories required")
        ids = [c.case_id for c in self.cases]
        inputs = [c.input_hash for c in self.cases]
        membership = self.train + self.tune + self.test
        if (
            len(set(ids)) != len(ids)
            or len(set(inputs)) != len(inputs)
            or len(set(membership)) != len(membership)
            or set(membership) != set(ids)
        ):
            raise ValueError("splits must be exhaustive and disjoint by case and underlying input")
        # This foundation makes no independent validation claim for trained/tuned models.
        if self.train or self.tune or self.test != tuple(ids):
            raise ValueError("mechanical foundation requires ordered test-only membership")
        if canonical_sha256([c.model_dump(mode="json") for c in self.cases]) != self.dataset_id:
            raise ValueError("dataset identity mismatch")
        if self.split_digest() != self.split_id:
            raise ValueError("split identity mismatch")
        if canonical_sha256(self.metrics.model_dump(mode="json")) != self.config_hash:
            raise ValueError("metric/config identity mismatch")
        if [a.kind for a in self.artifacts] != ["model", "prompt", "engine", "policy"]:
            raise ValueError("exact ordered artifact bundle required")
        if (
            timestamp(self.dataset_frozen_at) > timestamp(self.splits_frozen_at)
            or timestamp(self.splits_frozen_at) >= timestamp(self.outputs_not_before)
            or any(
                timestamp(c.known_at) > timestamp(self.dataset_frozen_at)
                or timestamp(c.available_at) > timestamp(self.dataset_frozen_at)
                for c in self.cases
            )
        ):
            raise ValueError("freeze must precede observations and follow available inputs")
        if self.release_digest() != self.release_id:
            raise ValueError("release identity mismatch")
        if self.identity("evaluation_id") != self.evaluation_id:
            raise ValueError("evaluation identity mismatch")
        return self

    def split_digest(self) -> str:
        return canonical_sha256(
            {
                "dataset_id": self.dataset_id,
                "train": list(self.train),
                "tune": list(self.tune),
                "test": list(self.test),
                "dataset_frozen_at": self.dataset_frozen_at,
                "splits_frozen_at": self.splits_frozen_at,
            }
        )

    def release_digest(self) -> str:
        return canonical_sha256(
            self.model_dump(mode="json", exclude={"evaluation_id", "release_id"})
        )

    def verify_sources(self, sources: Mapping[str, bytes], scorer_bytes: bytes) -> None:
        """Verify externally captured bytes without performing IO or trusting caller digests."""
        if sha256(scorer_bytes).hexdigest() != self.scorer_hash:
            raise ValueError("frozen scorer bytes mismatch")
        for case in self.cases:
            for source in case.sources:
                content = sources.get(source.path)
                if (
                    content is None
                    or sha256(content).hexdigest() != source.sha256
                    or source.excerpt not in content.decode("utf-8")
                ):
                    raise ValueError("source bytes/hash/excerpt mismatch")
