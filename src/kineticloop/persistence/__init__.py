"""Persistence contracts shared by schema and migration implementations."""

from kineticloop.persistence.schema_topology import (
    AUTHORITY_ROOT_CONSTRAINTS,
    DEFERRED_REFERENCES,
    LOGICAL_RELATIONS,
    RELATION_BY_ID,
    DeferredReference,
    LogicalRelation,
    SchemaTopologyError,
    topological_order,
)

__all__ = [
    "AUTHORITY_ROOT_CONSTRAINTS",
    "DEFERRED_REFERENCES",
    "LOGICAL_RELATIONS",
    "RELATION_BY_ID",
    "DeferredReference",
    "LogicalRelation",
    "SchemaTopologyError",
    "topological_order",
]
