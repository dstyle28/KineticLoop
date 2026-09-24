from __future__ import annotations

import pytest

from kineticloop.persistence.schema_topology import (
    AUTHORITY_ROOT_CONSTRAINTS,
    DEFERRED_REFERENCES,
    LOGICAL_RELATIONS,
    POST_BASE_REFERENCE_PLANS,
    RELATION_BY_ID,
    LogicalRelation,
    NormalizedReferencePlan,
    SchemaTopologyError,
    topological_order,
)

EXPECTED_CREATE_DEPENDENCIES = {
    **{f"S{number:02d}": frozenset() for number in range(1, 52)},
    "S03": frozenset({"S02"}),
    "S04": frozenset({"S03"}),
    "S07": frozenset({"S06"}),
    "S08": frozenset({"S02", "S05", "S06", "S07"}),
    "S10": frozenset({"S09"}),
    "S12": frozenset({"S09", "S11"}),
    "S13": frozenset({"S05", "S09", "S10"}),
    "S14": frozenset({"S10", "S11", "S13"}),
    "S15": frozenset({"S12", "S13", "S20"}),
    "S16": frozenset({"S12", "S13", "S14", "S15", "S20"}),
    "S17": frozenset({"S02", "S05", "S09", "S13"}),
    "S18": frozenset({"S17"}),
    "S20": frozenset({"S08", "S19"}),
    "S22": frozenset({"S05", "S06", "S14", "S15", "S19", "S20", "S21"}),
    "S23": frozenset({"S05", "S06", "S15", "S21"}),
    "S24": frozenset({"S05", "S06", "S15", "S19", "S20", "S23", "S49", "S51"}),
    "S25": frozenset({"S21", "S24"}),
    "S26": frozenset({"S24", "S28", "S29"}),
    "S27": frozenset({"S01"}),
    "S28": frozenset({"S02", "S27"}),
    "S29": frozenset({"S24", "S27", "S28"}),
    "S30": frozenset({"S05"}),
    "S31": frozenset({"S27", "S29"}),
    "S32": frozenset({"S31"}),
    "S33": frozenset({"S26", "S29"}),
    "S34": frozenset({"S26", "S29"}),
    "S35": frozenset({"S34"}),
    "S36": frozenset({"S05", "S09", "S12", "S14", "S24"}),
    "S37": frozenset({"S03", "S05", "S24", "S28", "S29", "S34", "S35", "S36"}),
    "S38": frozenset({"S01"}),
    "S39": frozenset({"S02", "S24", "S27", "S29", "S37", "S38"}),
    "S40": frozenset({"S34", "S49"}),
    "S41": frozenset({"S39", "S40"}),
    "S42": frozenset({"S02", "S05", "S24", "S36", "S37", "S40", "S49", "S51"}),
    "S43": frozenset({"S02", "S13", "S17", "S42"}),
    "S44": frozenset({"S01", "S11", "S14"}),
    "S45": frozenset({"S02", "S40", "S42", "S44"}),
    "S46": frozenset({"S24", "S48"}),
    "S47": frozenset({"S46"}),
    "S49": frozenset({"S05", "S19", "S48"}),
    "S50": frozenset({"S49", "S51"}),
}


def test_all_logical_relations_mapped_once() -> None:
    expected = {f"S{number:02d}" for number in range(1, 52)}
    logical_ids = [relation.logical_id for relation in LOGICAL_RELATIONS]
    table_names = [relation.table_name for relation in LOGICAL_RELATIONS]

    assert set(logical_ids) == expected
    assert len(logical_ids) == len(set(logical_ids)) == 51
    assert len(table_names) == len(set(table_names)) == 51


def test_fk_dependency_graph_is_acyclic() -> None:
    order = topological_order()
    positions = {logical_id: index for index, logical_id in enumerate(order)}

    assert len(order) == len(LOGICAL_RELATIONS) == 51
    assert set(order) == {relation.logical_id for relation in LOGICAL_RELATIONS}
    for relation in LOGICAL_RELATIONS:
        assert all(positions[dependency] < positions[relation.logical_id] for dependency in relation.dependencies)

    actual = {
        relation.logical_id: frozenset(relation.dependencies)
        for relation in LOGICAL_RELATIONS
    }
    assert actual == EXPECTED_CREATE_DEPENDENCIES


def test_authority_roots_precede_dependents() -> None:
    positions = {logical_id: index for index, logical_id in enumerate(topological_order())}

    for root, dependents in AUTHORITY_ROOT_CONSTRAINTS.items():
        assert dependents
        assert all(positions[root] < positions[dependent] for dependent in dependents)


def test_creation_order_follows_references_not_logical_numbers() -> None:
    order = topological_order()

    assert order.index("S48") < order.index("S03")
    assert order.index("S51") < order.index("S50")
    assert order.index("S21") < order.index("S22")
    assert order.index("S27") < order.index("S26")


def test_deferred_authority_references_form_a_valid_second_phase() -> None:
    logical_ids = {relation.logical_id for relation in LOGICAL_RELATIONS}
    reference_keys = [(reference.source, reference.field) for reference in DEFERRED_REFERENCES]

    assert len(reference_keys) == len(set(reference_keys))
    assert all(reference.source in logical_ids for reference in DEFERRED_REFERENCES)
    assert all(reference.target in logical_ids for reference in DEFERRED_REFERENCES)
    assert all(reference.source != reference.target for reference in DEFERRED_REFERENCES)
    assert all(reference.reason for reference in DEFERRED_REFERENCES)


def test_post_base_reference_plans_are_typed_and_closed() -> None:
    expected_relations = frozenset(f"S{number:02d}" for number in range(1, 52))
    assert POST_BASE_REFERENCE_PLANS == (
        NormalizedReferencePlan(
            owner="S47",
            field="source_revision_refs",
            phase="POST_BASE_RELATIONS",
            materialization="TARGET_TYPED_CHILD_EDGES",
            after_relations=expected_relations,
            required_target_roots=frozenset({"S14", "S20"}),
            requires_same_subject=True,
        ),
    )

    plan_keys = [(plan.owner, plan.field) for plan in POST_BASE_REFERENCE_PLANS]
    assert len(plan_keys) == len(set(plan_keys))
    for plan in POST_BASE_REFERENCE_PLANS:
        assert plan.owner in RELATION_BY_ID
        assert plan.after_relations == expected_relations
        assert plan.required_target_roots <= plan.after_relations
        assert plan.requires_same_subject is True
        assert plan.materialization == "TARGET_TYPED_CHILD_EDGES"
        assert "POLYMORPHIC" not in plan.materialization
        assert "TEXT" not in plan.materialization

    assert set(RELATION_BY_ID["S42"].dependencies) == {
        "S02", "S05", "S24", "S36", "S37", "S40", "S49", "S51"
    }
    assert set(RELATION_BY_ID["S47"].dependencies) == {"S46"}


def test_topological_order_rejects_unknown_and_cyclic_dependencies() -> None:
    with pytest.raises(SchemaTopologyError, match="unknown relation dependencies"):
        topological_order((LogicalRelation("S01", "one", ("S02",)),))

    cyclic = (
        LogicalRelation("S01", "one", ("S02",)),
        LogicalRelation("S02", "two", ("S01",)),
    )
    with pytest.raises(SchemaTopologyError, match="cyclic relation dependencies"):
        topological_order(cyclic)
