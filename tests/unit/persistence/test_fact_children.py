from __future__ import annotations

from decimal import Decimal

import pytest

from kineticloop.persistence.fact_children import (
    FACT_CHILD_PLANS,
    FactChildContractError,
    FactChildKind,
    FactFieldSpec,
    FactFieldType,
    FactKind,
    FactValueState,
    FieldProvenance,
    ProvenancedFactValue,
    UnitPolicy,
    fact_child_plan,
)


def provenance() -> FieldProvenance:
    return FieldProvenance(
        evidence_revision_id="evidence-revision-1",
        assertion_id="assertion-1",
        admission_decision_id="admission-1",
        source_locator="provider-payload:sets/0/repetitions",
    )


def test_typed_fact_children_are_closed() -> None:
    assert set(FACT_CHILD_PLANS) == set(FactChildKind) == {
        FactChildKind.STRENGTH_SET,
        FactChildKind.CARDIO_BOUT,
        FactChildKind.HEALTH_OBSERVATION,
        FactChildKind.NUTRITION_INTAKE,
    }
    assert {plan.table_name for plan in FACT_CHILD_PLANS.values()} == {
        "canonical_fact_strength_sets",
        "canonical_fact_cardio_bouts",
        "canonical_fact_health_observations",
        "canonical_fact_nutrition_intakes",
    }
    assert FACT_CHILD_PLANS[FactChildKind.STRENGTH_SET].fact_kind is FactKind.WORKOUT_ACTUAL
    assert FACT_CHILD_PLANS[FactChildKind.CARDIO_BOUT].fact_kind is FactKind.WORKOUT_ACTUAL
    assert all(plan.parent_relation == "S14" for plan in FACT_CHILD_PLANS.values())
    assert all(
        plan.parent_key == ("subject_id", "fact_revision_id")
        for plan in FACT_CHILD_PLANS.values()
    )
    assert all(plan.transaction == "T2-IN" for plan in FACT_CHILD_PLANS.values())
    expected_fields = {
        FactChildKind.STRENGTH_SET: (
            ("exercise_identity", FactFieldType.TEXT, UnitPolicy.FORBIDDEN, False),
            ("repetitions", FactFieldType.NONNEGATIVE_INTEGER, UnitPolicy.FORBIDDEN, True),
            (
                "load",
                FactFieldType.NONNEGATIVE_DECIMAL,
                UnitPolicy.REQUIRED_WHEN_ACTUAL,
                True,
            ),
        ),
        FactChildKind.CARDIO_BOUT: (
            ("activity_identity", FactFieldType.TEXT, UnitPolicy.FORBIDDEN, False),
            (
                "duration",
                FactFieldType.NONNEGATIVE_DECIMAL,
                UnitPolicy.REQUIRED_WHEN_ACTUAL,
                True,
            ),
            (
                "distance",
                FactFieldType.NONNEGATIVE_DECIMAL,
                UnitPolicy.REQUIRED_WHEN_ACTUAL,
                True,
            ),
        ),
        FactChildKind.HEALTH_OBSERVATION: (
            ("metric_identity", FactFieldType.TEXT, UnitPolicy.FORBIDDEN, False),
            (
                "observed_value",
                FactFieldType.NONNEGATIVE_DECIMAL,
                UnitPolicy.REQUIRED_WHEN_ACTUAL,
                True,
            ),
        ),
        FactChildKind.NUTRITION_INTAKE: (
            ("nutrient_identity", FactFieldType.TEXT, UnitPolicy.FORBIDDEN, False),
            (
                "consumed_amount",
                FactFieldType.NONNEGATIVE_DECIMAL,
                UnitPolicy.REQUIRED_WHEN_ACTUAL,
                True,
            ),
        ),
    }
    actual_fields = {
        kind: tuple(
            (field.name, field.value_type, field.unit_policy, field.value_nullable)
            for field in plan.fields
        )
        for kind, plan in FACT_CHILD_PLANS.items()
    }
    assert actual_fields == expected_fields
    for plan in FACT_CHILD_PLANS.values():
        assert plan.revision_unique_key == (
            "subject_id",
            "fact_revision_id",
            plan.child_identity_field,
        )
        assert plan.correction_identity_key == (
            "subject_id",
            "stable_fact_id",
            plan.child_identity_field,
        )

    with pytest.raises(FactChildContractError, match="undeclared fact child kind"):
        fact_child_plan("BODY_MEASUREMENT")
    with pytest.raises(FactChildContractError, match="undeclared fact child kind"):
        fact_child_plan("GENERIC_JSON")


def test_actual_unknown_zero_are_distinct() -> None:
    source = provenance()
    actual = ProvenancedFactValue.actual(Decimal("7.5"), source, unit="kg")
    zero = ProvenancedFactValue.actual(Decimal("0"), source, unit="kg")
    unknown = ProvenancedFactValue.unknown(source, unit="kg")
    not_measured = ProvenancedFactValue.unknown(
        source, state=FactValueState.NOT_MEASURED, unit="kg"
    )

    assert actual.state is zero.state is FactValueState.ACTUAL
    assert actual.value == Decimal("7.5")
    assert zero.value == Decimal("0")
    assert unknown.state is FactValueState.UNKNOWN and unknown.value is None
    assert not_measured.state is FactValueState.NOT_MEASURED
    assert len({actual, zero, unknown, not_measured}) == 4

    with pytest.raises(FactChildContractError, match="ACTUAL requires a value"):
        ProvenancedFactValue(FactValueState.ACTUAL, None, source)
    with pytest.raises(FactChildContractError, match="must not carry a value"):
        ProvenancedFactValue(FactValueState.UNKNOWN, Decimal("0"), source)


def test_fact_child_provenance_is_mandatory() -> None:
    value = ProvenancedFactValue.actual(Decimal("3"), provenance(), unit="repetition")

    assert value.provenance.evidence_revision_id == "evidence-revision-1"
    assert value.provenance.assertion_id == "assertion-1"
    assert value.provenance.admission_decision_id == "admission-1"
    assert all(
        plan.provenance_roots == ("S09", "S10", "S13")
        for plan in FACT_CHILD_PLANS.values()
    )
    assert all(
        field.provenance_required
        for plan in FACT_CHILD_PLANS.values()
        for field in plan.fields
    )

    with pytest.raises(TypeError, match="provenance"):
        ProvenancedFactValue(FactValueState.ACTUAL, Decimal("3"))  # type: ignore[call-arg]
    with pytest.raises(FactChildContractError, match="provenance is mandatory"):
        ProvenancedFactValue(
            FactValueState.ACTUAL, Decimal("3"), None  # type: ignore[arg-type]
        )
    with pytest.raises(FactChildContractError, match="evidence_revision_id"):
        FieldProvenance("", "assertion-1", "admission-1", "payload:field")
    with pytest.raises(FactChildContractError, match="source_locator"):
        FieldProvenance("evidence-1", "assertion-1", "admission-1", " ")
    with pytest.raises(FactChildContractError, match="every declared fact child field"):
        FactFieldSpec(
            name="unprovenanced_value",
            value_type=FactFieldType.NONNEGATIVE_DECIMAL,
            allowed_states=(FactValueState.ACTUAL,),
            value_nullable=False,
            unit_policy=UnitPolicy.REQUIRED_WHEN_ACTUAL,
            provenance_required=False,
        )
