from __future__ import annotations

import pytest

from kineticloop.persistence.schema_topology import (
    AUTHORITY_ROOT_CONSTRAINTS,
    DEFERRED_REFERENCES,
    LOGICAL_RELATIONS,
    LogicalRelation,
    SchemaTopologyError,
    topological_order,
)


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


def test_topological_order_rejects_unknown_and_cyclic_dependencies() -> None:
    with pytest.raises(SchemaTopologyError, match="unknown relation dependencies"):
        topological_order((LogicalRelation("S01", "one", ("S02",)),))

    cyclic = (
        LogicalRelation("S01", "one", ("S02",)),
        LogicalRelation("S02", "two", ("S01",)),
    )
    with pytest.raises(SchemaTopologyError, match="cyclic relation dependencies"):
        topological_order(cyclic)
