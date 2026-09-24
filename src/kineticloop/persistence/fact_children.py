"""Closed physical child-table contract for S14 canonical fact revisions.

The contract is intentionally a schema plan rather than a persistence writer.  KL-013
owns PostgreSQL DDL and KL-031 owns the workout-actual command implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum, unique
from types import MappingProxyType
from typing import TypeAlias


class FactChildContractError(ValueError):
    """Raised when a fact child would weaken the frozen S14 contract."""


@unique
class FactChildKind(StrEnum):
    """The complete set of typed child relations introduced by this plan."""

    STRENGTH_SET = "STRENGTH_SET"
    CARDIO_BOUT = "CARDIO_BOUT"
    HEALTH_OBSERVATION = "HEALTH_OBSERVATION"
    NUTRITION_INTAKE = "NUTRITION_INTAKE"


@unique
class FactKind(StrEnum):
    """S14 fact kinds used by the declared child relations."""

    WORKOUT_ACTUAL = "WORKOUT_ACTUAL"
    HEALTH_OBSERVATION = "HEALTH_OBSERVATION"
    NUTRITION_INTAKE = "NUTRITION_INTAKE"


@unique
class FactValueState(StrEnum):
    """Explicit states which must never be collapsed to SQL NULL or numeric zero."""

    ACTUAL = "ACTUAL"
    UNKNOWN = "UNKNOWN"
    NOT_MEASURED = "NOT_MEASURED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PARSE_FAILED = "PARSE_FAILED"


ScalarValue: TypeAlias = Decimal | str | bool


def _required_text(value: str, name: str) -> None:
    if not value.strip():
        raise FactChildContractError(f"{name} must be non-blank")


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    """Field-level lineage required by the Evidence Admission Protocol."""

    evidence_revision_id: str
    assertion_id: str
    admission_decision_id: str
    source_locator: str

    def __post_init__(self) -> None:
        for name in (
            "evidence_revision_id",
            "assertion_id",
            "admission_decision_id",
            "source_locator",
        ):
            _required_text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ProvenancedFactValue:
    """One typed value together with its state and mandatory source lineage."""

    state: FactValueState
    value: ScalarValue | None
    provenance: FieldProvenance
    unit: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, FieldProvenance):
            raise FactChildContractError("provenance is mandatory")
        if self.state is FactValueState.ACTUAL and self.value is None:
            raise FactChildContractError("ACTUAL requires a value")
        if self.state is not FactValueState.ACTUAL and self.value is not None:
            raise FactChildContractError(f"{self.state.value} must not carry a value")
        if self.unit is not None:
            _required_text(self.unit, "unit")

    @classmethod
    def actual(
        cls,
        value: ScalarValue,
        provenance: FieldProvenance,
        *,
        unit: str | None = None,
    ) -> ProvenancedFactValue:
        """Create an observed value; Decimal(0) remains an actual numeric zero."""

        return cls(FactValueState.ACTUAL, value, provenance, unit)

    @classmethod
    def unknown(
        cls,
        provenance: FieldProvenance,
        *,
        state: FactValueState = FactValueState.UNKNOWN,
        unit: str | None = None,
    ) -> ProvenancedFactValue:
        """Create an explicit non-value state without substituting zero or a plan value."""

        if state is FactValueState.ACTUAL:
            raise FactChildContractError("unknown() requires a non-ACTUAL state")
        return cls(state, None, provenance, unit)


@dataclass(frozen=True, slots=True)
class FactChildPlan:
    """Physical relation shape consumed later by the DDL task."""

    kind: FactChildKind
    table_name: str
    parent_relation: str
    fact_kind: FactKind
    child_identity_field: str
    typed_fields: tuple[str, ...]
    parent_key: tuple[str, str]
    provenance_roots: tuple[str, ...]
    writer: str
    transaction: str

    def __post_init__(self) -> None:
        if self.parent_relation != "S14":
            raise FactChildContractError("fact children must be owned by S14")
        if self.parent_key != ("subject_id", "fact_revision_id"):
            raise FactChildContractError("fact children require a same-subject S14 parent key")
        if not self.typed_fields or len(set(self.typed_fields)) != len(self.typed_fields):
            raise FactChildContractError("typed fields must be non-empty and unique")
        if self.provenance_roots != ("S09", "S10", "S13"):
            raise FactChildContractError("field provenance must bind evidence, assertion, and admission")
        if self.writer != "CanonicalFactService.AcceptFactRevision" or self.transaction != "T2-IN":
            raise FactChildContractError("fact children must remain inside the S14 T2-IN writer")


FACT_CHILD_PLANS = MappingProxyType(
    {
        FactChildKind.STRENGTH_SET: FactChildPlan(
            kind=FactChildKind.STRENGTH_SET,
            table_name="canonical_fact_strength_sets",
            parent_relation="S14",
            fact_kind=FactKind.WORKOUT_ACTUAL,
            child_identity_field="set_id",
            typed_fields=("exercise_identity", "repetitions", "load"),
            parent_key=("subject_id", "fact_revision_id"),
            provenance_roots=("S09", "S10", "S13"),
            writer="CanonicalFactService.AcceptFactRevision",
            transaction="T2-IN",
        ),
        FactChildKind.CARDIO_BOUT: FactChildPlan(
            kind=FactChildKind.CARDIO_BOUT,
            table_name="canonical_fact_cardio_bouts",
            parent_relation="S14",
            fact_kind=FactKind.WORKOUT_ACTUAL,
            child_identity_field="bout_id",
            typed_fields=("activity_identity", "duration", "distance"),
            parent_key=("subject_id", "fact_revision_id"),
            provenance_roots=("S09", "S10", "S13"),
            writer="CanonicalFactService.AcceptFactRevision",
            transaction="T2-IN",
        ),
        FactChildKind.HEALTH_OBSERVATION: FactChildPlan(
            kind=FactChildKind.HEALTH_OBSERVATION,
            table_name="canonical_fact_health_observations",
            parent_relation="S14",
            fact_kind=FactKind.HEALTH_OBSERVATION,
            child_identity_field="observation_id",
            typed_fields=("metric_identity", "observed_value"),
            parent_key=("subject_id", "fact_revision_id"),
            provenance_roots=("S09", "S10", "S13"),
            writer="CanonicalFactService.AcceptFactRevision",
            transaction="T2-IN",
        ),
        FactChildKind.NUTRITION_INTAKE: FactChildPlan(
            kind=FactChildKind.NUTRITION_INTAKE,
            table_name="canonical_fact_nutrition_intakes",
            parent_relation="S14",
            fact_kind=FactKind.NUTRITION_INTAKE,
            child_identity_field="intake_item_id",
            typed_fields=("nutrient_identity", "consumed_amount"),
            parent_key=("subject_id", "fact_revision_id"),
            provenance_roots=("S09", "S10", "S13"),
            writer="CanonicalFactService.AcceptFactRevision",
            transaction="T2-IN",
        ),
    }
)


def fact_child_plan(kind: FactChildKind | str) -> FactChildPlan:
    """Return a declared plan and reject undeclared or open-ended variants."""

    try:
        closed_kind = kind if isinstance(kind, FactChildKind) else FactChildKind(kind)
    except (TypeError, ValueError) as error:
        raise FactChildContractError(f"undeclared fact child kind: {kind!r}") from error
    return FACT_CHILD_PLANS[closed_kind]
