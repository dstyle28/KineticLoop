"""Immutable-history permissions derived from the frozen S01-S51 inventory.

Privileges attach to logical command principals, not arbitrary table writers. A
principal may span several relations when one frozen command transaction must do
so (for example SafetyRegistry over S50/S51), while split ownership on one table
uses operation-specific grants (for example S04 insert versus delivery update).
The roles own SECURITY DEFINER command routines and remain NOLOGIN; runtime
application credentials do not receive direct DML privileges.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from kineticloop.persistence.schema_topology import LOGICAL_RELATIONS


class StorageClass(StrEnum):
    IMMUTABLE = "immutable"
    MUTABLE = "mutable"
    BUILD = "build"
    BUILD_TO_IMMUTABLE = "build_to_immutable"


class DatabaseRole(StrEnum):
    APPLICATION = "kl_application"
    AUDITOR = "kl_auditor"


class SqlPermission(StrEnum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class GuardRequirement(StrEnum):
    """Metadata that downstream DDL/repositories must materialize."""

    COMMAND_ENTRYPOINT = "command_entrypoint"
    IDEMPOTENCY = "idempotency"
    SAME_TRANSACTION = "same_transaction"
    USER_COORDINATION = "user_coordination"
    REGISTRY_GATE = "registry_gate"
    LOCK_ORDER = "lock_order"
    REVISION_OR_FENCE = "revision_or_fence"
    LIFECYCLE_TRANSITION = "lifecycle_transition"
    BUILD_WRITE_GATE = "build_write_gate"
    PARENT_BUILD_WRITE_GATE = "parent_build_write_gate"
    EVALUATION_ISOLATION = "evaluation_isolation"
    OUTBOX_DELIVERY_ONLY = "outbox_delivery_only"
    ACTUAL_FACT_ACCEPTANCE = "actual_fact_acceptance"
    CURRENT_AUTHORIZATION = "current_authorization"


class LockTarget(StrEnum):
    REGISTRY_SHARED = "registry_shared"
    REGISTRY_EXCLUSIVE = "registry_exclusive"
    USER = "user"
    BUILD = "build"
    EXECUTION = "execution"
    OUTBOX = "outbox"


@dataclass(frozen=True, slots=True)
class WriterGrant:
    principal: str
    permissions: frozenset[SqlPermission]


@dataclass(frozen=True, slots=True)
class RelationProtection:
    logical_id: str
    table_name: str
    storage_class: StorageClass
    writers: tuple[WriterGrant, ...]
    guards: frozenset[GuardRequirement]


@dataclass(frozen=True, slots=True)
class CommandMutation:
    logical_id: str
    permission: SqlPermission
    writer_principal: str


@dataclass(frozen=True, slots=True)
class CommandEntrypoint:
    """Authoritative path-specific transaction/lock contract."""

    command_id: str
    principal: str
    mutations: tuple[CommandMutation, ...]
    transaction_group: str
    lock_order: tuple[LockTarget, ...]
    guards: frozenset[GuardRequirement]


READ_ONLY: Final = frozenset({SqlPermission.SELECT})
INSERT_ONLY: Final = frozenset({SqlPermission.SELECT, SqlPermission.INSERT})
UPDATE_ONLY: Final = frozenset({SqlPermission.SELECT, SqlPermission.UPDATE})
OWNED_TRANSITION: Final = frozenset(
    {SqlPermission.SELECT, SqlPermission.INSERT, SqlPermission.UPDATE}
)


def _grant(principal: str, permissions: frozenset[SqlPermission]) -> WriterGrant:
    return WriterGrant(principal, permissions)


def _protection(
    logical_id: str,
    storage_class: StorageClass,
    principal: str,
    *guards: GuardRequirement,
    writers: tuple[WriterGrant, ...] | None = None,
) -> RelationProtection:
    table_name = next(
        relation.table_name
        for relation in LOGICAL_RELATIONS
        if relation.logical_id == logical_id
    )
    default = INSERT_ONLY if storage_class is StorageClass.IMMUTABLE else OWNED_TRANSITION
    return RelationProtection(
        logical_id=logical_id,
        table_name=table_name,
        storage_class=storage_class,
        writers=writers or (_grant(principal, default),),
        guards=frozenset({GuardRequirement.COMMAND_ENTRYPOINT, *guards}),
    )


RELATION_PROTECTIONS: Final[tuple[RelationProtection, ...]] = (
    _protection("S01", StorageClass.MUTABLE, "decision_state_coordinator", GuardRequirement.USER_COORDINATION, GuardRequirement.LOCK_ORDER, GuardRequirement.REVISION_OR_FENCE),
    _protection("S02", StorageClass.MUTABLE, "command_gateway", GuardRequirement.IDEMPOTENCY, GuardRequirement.SAME_TRANSACTION),
    _protection("S03", StorageClass.IMMUTABLE, "originating_domain_command", GuardRequirement.SAME_TRANSACTION),
    _protection("S04", StorageClass.MUTABLE, "originating_domain_command", GuardRequirement.SAME_TRANSACTION, GuardRequirement.OUTBOX_DELIVERY_ONLY, writers=(_grant("originating_domain_command", INSERT_ONLY), _grant("outbox_dispatcher", UPDATE_ONLY))),
    _protection("S05", StorageClass.IMMUTABLE, "policy_registry"),
    _protection("S06", StorageClass.IMMUTABLE, "program_service"),
    _protection("S07", StorageClass.IMMUTABLE, "program_review_service"),
    _protection("S08", StorageClass.IMMUTABLE, "approval_service"),
    _protection("S09", StorageClass.IMMUTABLE, "evidence_service"),
    _protection("S10", StorageClass.IMMUTABLE, "extraction_service"),
    _protection("S11", StorageClass.IMMUTABLE, "evidence_association_service"),
    _protection("S12", StorageClass.IMMUTABLE, "evidence_association_service"),
    _protection("S13", StorageClass.IMMUTABLE, "admission_service", GuardRequirement.USER_COORDINATION, GuardRequirement.SAME_TRANSACTION),
    _protection("S14", StorageClass.IMMUTABLE, "canonical_fact_service", GuardRequirement.USER_COORDINATION, GuardRequirement.SAME_TRANSACTION),
    _protection("S15", StorageClass.BUILD_TO_IMMUTABLE, "canonical_view_service", GuardRequirement.BUILD_WRITE_GATE, GuardRequirement.USER_COORDINATION, GuardRequirement.LOCK_ORDER),
    _protection("S16", StorageClass.BUILD_TO_IMMUTABLE, "canonical_view_service", GuardRequirement.PARENT_BUILD_WRITE_GATE),
    _protection("S17", StorageClass.IMMUTABLE, "control_service", GuardRequirement.USER_COORDINATION, GuardRequirement.SAME_TRANSACTION),
    _protection("S18", StorageClass.MUTABLE, "control_service", GuardRequirement.SAME_TRANSACTION, GuardRequirement.REVISION_OR_FENCE),
    _protection("S19", StorageClass.IMMUTABLE, "exercise_catalog_service"),
    _protection("S20", StorageClass.IMMUTABLE, "exercise_mapping_service"),
    _protection("S21", StorageClass.IMMUTABLE, "projection_service"),
    _protection("S22", StorageClass.IMMUTABLE, "projection_service", GuardRequirement.SAME_TRANSACTION),
    _protection("S23", StorageClass.BUILD, "decision_publication_service", GuardRequirement.BUILD_WRITE_GATE, GuardRequirement.REVISION_OR_FENCE),
    _protection("S24", StorageClass.IMMUTABLE, "decision_publication_service", GuardRequirement.REGISTRY_GATE, GuardRequirement.USER_COORDINATION, GuardRequirement.LOCK_ORDER, GuardRequirement.SAME_TRANSACTION),
    _protection("S25", StorageClass.IMMUTABLE, "decision_publication_service", GuardRequirement.SAME_TRANSACTION),
    _protection("S26", StorageClass.IMMUTABLE, "context_service", GuardRequirement.REVISION_OR_FENCE),
    _protection("S27", StorageClass.MUTABLE, "planning_workflow_service", GuardRequirement.USER_COORDINATION, GuardRequirement.REVISION_OR_FENCE, GuardRequirement.LOCK_ORDER),
    _protection("S28", StorageClass.IMMUTABLE, "planning_workflow_service", GuardRequirement.SAME_TRANSACTION, GuardRequirement.REVISION_OR_FENCE),
    _protection("S29", StorageClass.MUTABLE, "planning_workflow_service", GuardRequirement.LIFECYCLE_TRANSITION, GuardRequirement.REVISION_OR_FENCE),
    _protection("S30", StorageClass.MUTABLE, "planning_workflow_service", GuardRequirement.SAME_TRANSACTION, GuardRequirement.LOCK_ORDER),
    _protection("S31", StorageClass.MUTABLE, "call_ledger_service", GuardRequirement.LIFECYCLE_TRANSITION, GuardRequirement.REVISION_OR_FENCE, GuardRequirement.LOCK_ORDER),
    _protection("S32", StorageClass.IMMUTABLE, "call_ledger_service", GuardRequirement.SAME_TRANSACTION, GuardRequirement.IDEMPOTENCY),
    _protection("S33", StorageClass.IMMUTABLE, "context_tool_gateway", GuardRequirement.REVISION_OR_FENCE),
    _protection("S34", StorageClass.IMMUTABLE, "proposal_service", GuardRequirement.REVISION_OR_FENCE),
    _protection("S35", StorageClass.IMMUTABLE, "demand_feature_service"),
    _protection("S36", StorageClass.IMMUTABLE, "evidence_resolver", GuardRequirement.REVISION_OR_FENCE),
    _protection("S37", StorageClass.IMMUTABLE, "validation_service", GuardRequirement.REVISION_OR_FENCE),
    _protection("S38", StorageClass.MUTABLE, "prescription_commit_service", GuardRequirement.REGISTRY_GATE, GuardRequirement.USER_COORDINATION, GuardRequirement.LOCK_ORDER, GuardRequirement.SAME_TRANSACTION),
    _protection("S39", StorageClass.IMMUTABLE, "prescription_commit_service", GuardRequirement.SAME_TRANSACTION),
    _protection("S40", StorageClass.IMMUTABLE, "prescription_commit_service", GuardRequirement.SAME_TRANSACTION),
    _protection("S41", StorageClass.IMMUTABLE, "prescription_commit_service", GuardRequirement.SAME_TRANSACTION),
    _protection("S42", StorageClass.IMMUTABLE, "authorization_service", GuardRequirement.REGISTRY_GATE, GuardRequirement.USER_COORDINATION, GuardRequirement.LOCK_ORDER, GuardRequirement.SAME_TRANSACTION),
    _protection("S43", StorageClass.IMMUTABLE, "authorization_service", GuardRequirement.USER_COORDINATION, GuardRequirement.SAME_TRANSACTION),
    _protection("S44", StorageClass.MUTABLE, "execution_service", GuardRequirement.REGISTRY_GATE, GuardRequirement.USER_COORDINATION, GuardRequirement.LOCK_ORDER, GuardRequirement.LIFECYCLE_TRANSITION),
    _protection("S45", StorageClass.IMMUTABLE, "execution_service", GuardRequirement.REGISTRY_GATE, GuardRequirement.USER_COORDINATION, GuardRequirement.LOCK_ORDER, GuardRequirement.SAME_TRANSACTION),
    _protection("S46", StorageClass.MUTABLE, "replay_service", GuardRequirement.EVALUATION_ISOLATION, GuardRequirement.LIFECYCLE_TRANSITION),
    _protection("S47", StorageClass.IMMUTABLE, "replay_service", GuardRequirement.EVALUATION_ISOLATION),
    _protection("S48", StorageClass.IMMUTABLE, "release_evaluation_service", GuardRequirement.EVALUATION_ISOLATION),
    _protection("S49", StorageClass.IMMUTABLE, "safety_registry", GuardRequirement.REGISTRY_GATE),
    _protection("S50", StorageClass.IMMUTABLE, "safety_registry", GuardRequirement.REGISTRY_GATE, GuardRequirement.IDEMPOTENCY, GuardRequirement.SAME_TRANSACTION),
    _protection("S51", StorageClass.MUTABLE, "safety_registry", GuardRequirement.REGISTRY_GATE, GuardRequirement.LOCK_ORDER, GuardRequirement.SAME_TRANSACTION),
)


def _mutation(
    logical_id: str,
    permission: SqlPermission,
    writer_principal: str,
) -> CommandMutation:
    return CommandMutation(logical_id, permission, writer_principal)


# Relation ``guards`` above are an inventory aid only. These command-specific rows
# are authoritative wherever paths over the same relation diverge. Downstream DDL
# must never apply the union of relation guard tags to every command path.
COMMAND_ENTRYPOINTS: Final[tuple[CommandEntrypoint, ...]] = (

    CommandEntrypoint(
        command_id="record_domain_event_with_outbox",
        principal="originating_domain_command",
        mutations=(
            _mutation("S03", SqlPermission.INSERT, "originating_domain_command"),
            _mutation("S04", SqlPermission.INSERT, "originating_domain_command"),
        ),
        transaction_group="domain_event_outbox",
        lock_order=(),
        guards=frozenset(
            {GuardRequirement.COMMAND_ENTRYPOINT, GuardRequirement.SAME_TRANSACTION}
        ),
    ),
    CommandEntrypoint(
        command_id="dispatch_outbox_delivery",
        principal="outbox_dispatcher",
        mutations=(_mutation("S04", SqlPermission.UPDATE, "outbox_dispatcher"),),
        transaction_group="outbox_delivery",
        lock_order=(LockTarget.OUTBOX,),
        guards=frozenset(
            {
                GuardRequirement.COMMAND_ENTRYPOINT,
                GuardRequirement.OUTBOX_DELIVERY_ONLY,
            }
        ),
    ),
    CommandEntrypoint(
        command_id="build_factset",
        principal="canonical_view_service",
        mutations=(
            _mutation("S15", SqlPermission.INSERT, "canonical_view_service"),
            _mutation("S15", SqlPermission.UPDATE, "canonical_view_service"),
            _mutation("S16", SqlPermission.INSERT, "canonical_view_service"),
            _mutation("S16", SqlPermission.UPDATE, "canonical_view_service"),
        ),
        transaction_group="factset_build",
        lock_order=(LockTarget.BUILD,),
        guards=frozenset(
            {GuardRequirement.COMMAND_ENTRYPOINT, GuardRequirement.BUILD_WRITE_GATE}
        ),
    ),
    CommandEntrypoint(
        command_id="seal_factset",
        principal="canonical_view_service",
        mutations=(
            _mutation("S15", SqlPermission.UPDATE, "canonical_view_service"),
            _mutation("S01", SqlPermission.UPDATE, "decision_state_coordinator"),
            _mutation("S02", SqlPermission.INSERT, "command_gateway"),
            _mutation("S02", SqlPermission.UPDATE, "command_gateway"),
            _mutation("S03", SqlPermission.INSERT, "originating_domain_command"),
            _mutation("S04", SqlPermission.INSERT, "originating_domain_command"),
        ),
        transaction_group="t2_seal",
        lock_order=(LockTarget.USER, LockTarget.BUILD),
        guards=frozenset(
            {
                GuardRequirement.COMMAND_ENTRYPOINT,
                GuardRequirement.BUILD_WRITE_GATE,
                GuardRequirement.USER_COORDINATION,
                GuardRequirement.SAME_TRANSACTION,
            }
        ),
    ),
    CommandEntrypoint(
        command_id="accept_external_execution",
        principal="execution_service",
        mutations=(
            _mutation("S01", SqlPermission.UPDATE, "decision_state_coordinator"),
            _mutation("S02", SqlPermission.INSERT, "command_gateway"),
            _mutation("S02", SqlPermission.UPDATE, "command_gateway"),
            _mutation("S14", SqlPermission.INSERT, "canonical_fact_service"),
            _mutation("S44", SqlPermission.INSERT, "execution_service"),
            _mutation("S44", SqlPermission.UPDATE, "execution_service"),
            _mutation("S03", SqlPermission.INSERT, "originating_domain_command"),
            _mutation("S04", SqlPermission.INSERT, "originating_domain_command"),
        ),
        transaction_group="t2_external_execution",
        lock_order=(LockTarget.USER, LockTarget.EXECUTION),
        guards=frozenset(
            {
                GuardRequirement.COMMAND_ENTRYPOINT,
                GuardRequirement.ACTUAL_FACT_ACCEPTANCE,
                GuardRequirement.USER_COORDINATION,
                GuardRequirement.SAME_TRANSACTION,
            }
        ),
    ),
    CommandEntrypoint(
        command_id="start_or_resume_session",
        principal="execution_service",
        mutations=(
            _mutation("S01", SqlPermission.UPDATE, "decision_state_coordinator"),
            _mutation("S02", SqlPermission.INSERT, "command_gateway"),
            _mutation("S02", SqlPermission.UPDATE, "command_gateway"),
            _mutation("S44", SqlPermission.INSERT, "execution_service"),
            _mutation("S44", SqlPermission.UPDATE, "execution_service"),
            _mutation("S45", SqlPermission.INSERT, "execution_service"),
            _mutation("S03", SqlPermission.INSERT, "originating_domain_command"),
            _mutation("S04", SqlPermission.INSERT, "originating_domain_command"),
        ),
        transaction_group="t7_start_resume",
        lock_order=(
            LockTarget.REGISTRY_SHARED,
            LockTarget.USER,
            LockTarget.EXECUTION,
        ),
        guards=frozenset(
            {
                GuardRequirement.COMMAND_ENTRYPOINT,
                GuardRequirement.REGISTRY_GATE,
                GuardRequirement.CURRENT_AUTHORIZATION,
                GuardRequirement.USER_COORDINATION,
                GuardRequirement.SAME_TRANSACTION,
            }
        ),
    ),
    CommandEntrypoint(
        command_id="revoke_safety_artifact",
        principal="safety_registry",
        mutations=(
            _mutation("S50", SqlPermission.INSERT, "safety_registry"),
            _mutation("S51", SqlPermission.UPDATE, "safety_registry"),
        ),
        transaction_group="t2_global_revoke",
        lock_order=(LockTarget.REGISTRY_EXCLUSIVE,),
        guards=frozenset(
            {
                GuardRequirement.COMMAND_ENTRYPOINT,
                GuardRequirement.REGISTRY_GATE,
                GuardRequirement.IDEMPOTENCY,
                GuardRequirement.SAME_TRANSACTION,
            }
        ),
    ),
)

ENTRYPOINT_BY_ID: Final[Mapping[str, CommandEntrypoint]] = MappingProxyType(
    {entrypoint.command_id: entrypoint for entrypoint in COMMAND_ENTRYPOINTS}
)

PROTECTION_BY_ID: Final[Mapping[str, RelationProtection]] = MappingProxyType(
    {protection.logical_id: protection for protection in RELATION_PROTECTIONS}
)


def role_name_for(principal: str) -> str:
    """Return the shared non-login role for one logical command principal."""

    if not principal or not principal.replace("_", "a").isalnum():
        raise ValueError("principal must contain only letters, digits, and underscores")
    return f"kl_writer_{principal}"


WRITER_ROLE_NAMES: Final[frozenset[str]] = frozenset(
    role_name_for(writer.principal)
    for protection in RELATION_PROTECTIONS
    for writer in protection.writers
)
RUNTIME_ROLE_NAMES: Final[frozenset[str]] = frozenset(
    {DatabaseRole.APPLICATION.value, DatabaseRole.AUDITOR.value, *WRITER_ROLE_NAMES}
)


def permissions_for_role(
    protection: RelationProtection,
    role_name: str,
) -> frozenset[SqlPermission]:
    """Return one concrete role/table cell; unknown roles have no privileges."""

    if type(protection) is not RelationProtection:
        raise TypeError("protection must be a RelationProtection")
    if type(role_name) is not str:
        raise TypeError("role_name must be a string")
    if role_name in {DatabaseRole.APPLICATION.value, DatabaseRole.AUDITOR.value}:
        return READ_ONLY
    for writer in protection.writers:
        if role_name == role_name_for(writer.principal):
            return writer.permissions
    return frozenset()


def render_permission_sql(protection: RelationProtection, *, schema: str) -> str:
    """Render complete deny-by-default ACL reconciliation for one table."""

    if not schema or not schema.replace("_", "a").isalnum():
        raise ValueError("schema must contain only letters, digits, and underscores")
    table = f"{schema}.{protection.table_name}"
    statements = [f"REVOKE ALL ON TABLE {table} FROM PUBLIC;"]
    statements.extend(
        f"REVOKE ALL ON TABLE {table} FROM {role};"
        for role in sorted(RUNTIME_ROLE_NAMES)
    )
    for role in sorted(RUNTIME_ROLE_NAMES):
        permissions = permissions_for_role(protection, role)
        if permissions:
            rendered = ", ".join(
                permission.value
                for permission in SqlPermission
                if permission in permissions
            )
            statements.append(f"GRANT {rendered} ON TABLE {table} TO {role};")
    return "\n".join(statements)
