"""Persistence contracts shared by schema and migration implementations."""

from kineticloop.persistence.immutability import (
    PROTECTION_BY_ID,
    RELATION_PROTECTIONS,
    DatabaseRole,
    RelationProtection,
    SqlPermission,
    StorageClass,
    permissions_for,
    render_permission_sql,
    role_name_for,
)
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
    "DatabaseRole",
    "DEFERRED_REFERENCES",
    "LOGICAL_RELATIONS",
    "POST_BASE_REFERENCE_PLANS",
    "PROTECTION_BY_ID",
    "RELATION_BY_ID",
    "RELATION_PROTECTIONS",
    "DeferredReference",
    "LogicalRelation",
    "NormalizedReferencePlan",
    "RelationProtection",
    "SchemaTopologyError",
    "SqlPermission",
    "StorageClass",
    "permissions_for",
    "render_permission_sql",
    "role_name_for",
    "topological_order",
]
