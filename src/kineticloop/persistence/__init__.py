"""Persistence contracts shared by schema and migration implementations."""

from kineticloop.persistence.schema_topology import (
    AUTHORITY_ROOT_CONSTRAINTS,
    DEFERRED_REFERENCES,
    LOGICAL_RELATIONS,
    POST_BASE_REFERENCE_PLANS,
    RELATION_BY_ID,
    DeferredReference,
    LogicalRelation,
    NormalizedReferencePlan,
    SchemaTopologyError,
    topological_order,
)

__all__ = [
    "AUTHORITY_ROOT_CONSTRAINTS",
    "DEFERRED_REFERENCES",
    "LOGICAL_RELATIONS",
    "POST_BASE_REFERENCE_PLANS",
    "RELATION_BY_ID",
    "DeferredReference",
    "LogicalRelation",
    "NormalizedReferencePlan",
    "SchemaTopologyError",
    "topological_order",
]
