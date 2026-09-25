"""Immutable-history permissions derived from the frozen S01-S51 inventory.

This module is a physical-enforcement contract, not a replacement for command
authorization.  A command-specific database role receives only the mutation
rights declared for its relation; the ordinary application role is read-only.
Database object owners and migration credentials must never be runtime roles.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from kineticloop.persistence.schema_topology import LOGICAL_RELATIONS


class StorageClass(StrEnum):
    """Frozen persistence behavior for one logical relation."""

    IMMUTABLE = "immutable"
    MUTABLE = "mutable"
    BUILD = "build"
    BUILD_TO_IMMUTABLE = "build_to_immutable"


class DatabaseRole(StrEnum):
    """Role categories used in every relation permission cell."""

    APPLICATION = "application"
    AUDITOR = "auditor"
    COMMAND_OWNER = "command_owner"


class SqlPermission(StrEnum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


@dataclass(frozen=True, slots=True)
class RelationProtection:
    """Write owner and lifecycle class for one frozen logical relation."""

    logical_id: str
    table_name: str
    storage_class: StorageClass
    command_owner: str


READ_ONLY: Final[frozenset[SqlPermission]] = frozenset({SqlPermission.SELECT})
INSERT_ONLY: Final[frozenset[SqlPermission]] = frozenset(
    {SqlPermission.SELECT, SqlPermission.INSERT}
)
OWNED_TRANSITION: Final[frozenset[SqlPermission]] = frozenset(
    {SqlPermission.SELECT, SqlPermission.INSERT, SqlPermission.UPDATE}
)


def _protection(
    logical_id: str,
    storage_class: StorageClass,
    command_owner: str,
) -> RelationProtection:
    table_name = next(
        relation.table_name
        for relation in LOGICAL_RELATIONS
        if relation.logical_id == logical_id
    )
    return RelationProtection(logical_id, table_name, storage_class, command_owner)


# Owner names preserve the frozen unique-writer boundary.  They are logical service
# roles: deployments may map several to one process credential only if SET ROLE (or
# an equivalent non-forgeable binding) still selects exactly one command owner.
RELATION_PROTECTIONS: Final[tuple[RelationProtection, ...]] = (
    _protection("S01", StorageClass.MUTABLE, "decision_state_coordinator"),
    _protection("S02", StorageClass.MUTABLE, "command_gateway"),
    _protection("S03", StorageClass.IMMUTABLE, "domain_command_event_writer"),
    _protection("S04", StorageClass.MUTABLE, "outbox_dispatcher"),
    _protection("S05", StorageClass.IMMUTABLE, "policy_registry"),
    _protection("S06", StorageClass.IMMUTABLE, "program_service"),
    _protection("S07", StorageClass.IMMUTABLE, "program_review_service"),
    _protection("S08", StorageClass.IMMUTABLE, "approval_service"),
    _protection("S09", StorageClass.IMMUTABLE, "evidence_service"),
    _protection("S10", StorageClass.IMMUTABLE, "extraction_service"),
    _protection("S11", StorageClass.IMMUTABLE, "evidence_association_service"),
    _protection("S12", StorageClass.IMMUTABLE, "evidence_association_service"),
    _protection("S13", StorageClass.IMMUTABLE, "admission_service"),
    _protection("S14", StorageClass.IMMUTABLE, "canonical_fact_service"),
    _protection("S15", StorageClass.BUILD_TO_IMMUTABLE, "canonical_view_service"),
    _protection("S16", StorageClass.BUILD_TO_IMMUTABLE, "canonical_view_service"),
    _protection("S17", StorageClass.IMMUTABLE, "control_service"),
    _protection("S18", StorageClass.MUTABLE, "control_service"),
    _protection("S19", StorageClass.IMMUTABLE, "exercise_catalog_service"),
    _protection("S20", StorageClass.IMMUTABLE, "exercise_mapping_service"),
    _protection("S21", StorageClass.IMMUTABLE, "projection_service"),
    _protection("S22", StorageClass.IMMUTABLE, "projection_service"),
    _protection("S23", StorageClass.BUILD, "decision_publication_service"),
    _protection("S24", StorageClass.IMMUTABLE, "decision_publication_service"),
    _protection("S25", StorageClass.IMMUTABLE, "decision_publication_service"),
    _protection("S26", StorageClass.IMMUTABLE, "context_service"),
    _protection("S27", StorageClass.MUTABLE, "planning_workflow_service"),
    _protection("S28", StorageClass.IMMUTABLE, "planning_workflow_service"),
    _protection("S29", StorageClass.MUTABLE, "planning_workflow_service"),
    _protection("S30", StorageClass.MUTABLE, "planning_workflow_service"),
    _protection("S31", StorageClass.MUTABLE, "call_ledger_service"),
    _protection("S32", StorageClass.IMMUTABLE, "call_ledger_service"),
    _protection("S33", StorageClass.IMMUTABLE, "context_tool_gateway"),
    _protection("S34", StorageClass.IMMUTABLE, "proposal_service"),
    _protection("S35", StorageClass.IMMUTABLE, "demand_feature_service"),
    _protection("S36", StorageClass.IMMUTABLE, "evidence_resolver"),
    _protection("S37", StorageClass.IMMUTABLE, "validation_service"),
    _protection("S38", StorageClass.MUTABLE, "prescription_commit_service"),
    _protection("S39", StorageClass.IMMUTABLE, "prescription_commit_service"),
    _protection("S40", StorageClass.IMMUTABLE, "prescription_commit_service"),
    _protection("S41", StorageClass.IMMUTABLE, "prescription_commit_service"),
    _protection("S42", StorageClass.IMMUTABLE, "authorization_service"),
    _protection("S43", StorageClass.IMMUTABLE, "authorization_service"),
    _protection("S44", StorageClass.MUTABLE, "execution_service"),
    _protection("S45", StorageClass.IMMUTABLE, "execution_service"),
    _protection("S46", StorageClass.MUTABLE, "replay_service"),
    _protection("S47", StorageClass.IMMUTABLE, "replay_service"),
    _protection("S48", StorageClass.IMMUTABLE, "release_evaluation_service"),
    _protection("S49", StorageClass.IMMUTABLE, "safety_registry"),
    _protection("S50", StorageClass.IMMUTABLE, "safety_registry"),
    _protection("S51", StorageClass.MUTABLE, "safety_registry"),
)

PROTECTION_BY_ID: Final[Mapping[str, RelationProtection]] = MappingProxyType(
    {protection.logical_id: protection for protection in RELATION_PROTECTIONS}
)


def permissions_for(
    protection: RelationProtection,
    role: DatabaseRole,
) -> frozenset[SqlPermission]:
    """Return the closed SQL permission cell for a role and relation.

    UPDATE on build-to-immutable relations is necessary only for guarded build
    lifecycle transitions.  A trigger/repository guard must reject changes after
    READY (S15) or after the parent is READY/SEALED (S16).  DELETE is intentionally
    absent from every runtime cell; privacy erasure uses a separately reviewed
    maintenance mechanism and tombstone semantics.
    """

    if type(protection) is not RelationProtection:
        raise TypeError("protection must be a RelationProtection")
    if type(role) is not DatabaseRole:
        raise TypeError("role must be a DatabaseRole")
    if role in {DatabaseRole.APPLICATION, DatabaseRole.AUDITOR}:
        return READ_ONLY
    if protection.storage_class is StorageClass.IMMUTABLE:
        return INSERT_ONLY
    return OWNED_TRANSITION


def role_name_for(protection: RelationProtection) -> str:
    """Return a stable, identifier-safe PostgreSQL role for the unique writer."""

    return f"kl_owner_{protection.logical_id.lower()}_{protection.command_owner}"


def render_permission_sql(
    protection: RelationProtection,
    *,
    schema: str,
    application_role: str,
    auditor_role: str,
) -> str:
    """Render deny-by-default grants for an already-created physical table.

    Inputs must be trusted migration constants.  This function deliberately does
    not accept runtime values and does not quote arbitrary identifiers.
    """

    identifiers = (schema, application_role, auditor_role, role_name_for(protection))
    if any(not value.replace("_", "a").isalnum() or not value for value in identifiers):
        raise ValueError("SQL identifiers must contain only letters, digits, and underscores")
    table = f"{schema}.{protection.table_name}"
    owner_role = role_name_for(protection)
    owner_permissions = ", ".join(
        permission.value
        for permission in SqlPermission
        if permission in permissions_for(protection, DatabaseRole.COMMAND_OWNER)
    )
    return "\n".join(
        (
            f"REVOKE ALL ON TABLE {table} FROM PUBLIC;",
            f"REVOKE ALL ON TABLE {table} FROM {application_role};",
            f"REVOKE ALL ON TABLE {table} FROM {auditor_role};",
            f"REVOKE ALL ON TABLE {table} FROM {owner_role};",
            f"GRANT SELECT ON TABLE {table} TO {application_role}, {auditor_role};",
            f"GRANT {owner_permissions} ON TABLE {table} TO {owner_role};",
        )
    )
