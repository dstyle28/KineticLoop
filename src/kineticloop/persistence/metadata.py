"""SQLAlchemy metadata for the frozen S01-S51 PostgreSQL baseline.

The logical inventory and dependency order remain owned by ``schema_topology``.
This module gives that contract a deterministic physical shape consumed by the
initial Alembic revision and by schema inventory tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from kineticloop.persistence.fact_children import (
    FACT_CHILD_PLANS,
    FactFieldType,
    UnitPolicy,
)
from kineticloop.persistence.immutability import (
    PROTECTION_BY_ID,
    RUNTIME_ROLE_NAMES,
    DatabaseRole,
    StorageClass,
    permissions_for_role,
)
from kineticloop.persistence.schema_topology import (
    DEFERRED_REFERENCES,
    LOGICAL_RELATIONS,
    RELATION_BY_ID,
    topological_order,
)

NAMING_CONVENTION: Final = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SCHEMA: Final = "public"


@dataclass(frozen=True, slots=True)
class PhysicalRelation:
    logical_id: str
    table_name: str
    identity_column: str


IDENTITY_COLUMN_OVERRIDES: Final = MappingProxyType(
    {
        "S01": "subject_state_id",
        "S02": "command_receipt_id",
        "S14": "fact_revision_id",
        "S15": "factset_id",
        "S23": "build_id",
        "S24": "manifest_id",
        "S27": "intent_id",
        "S29": "attempt_id",
        "S34": "proposal_revision_id",
        "S38": "daily_plan_head_id",
        "S39": "bundle_revision_id",
        "S42": "authorization_id",
        "S44": "session_id",
        "S46": "replay_run_id",
        "S47": "replay_artifact_id",
        "S49": "artifact_id",
        "S50": "revocation_id",
        "S51": "registry_state_id",
    }
)

PHYSICAL_RELATIONS: Final = tuple(
    PhysicalRelation(
        relation.logical_id,
        relation.table_name,
        IDENTITY_COLUMN_OVERRIDES.get(relation.logical_id, "record_id"),
    )
    for relation in LOGICAL_RELATIONS
)
PHYSICAL_BY_ID: Final = MappingProxyType(
    {relation.logical_id: relation for relation in PHYSICAL_RELATIONS}
)


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _common_columns(logical_id: str) -> list[sa.Column[Any]]:
    identity = PHYSICAL_BY_ID[logical_id].identity_column
    columns: list[sa.Column[Any]] = [
        _uuid("subject_id"),
        _uuid(identity),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
    ]
    if logical_id not in {
        "S01",
        "S02",
        "S18",
        "S23",
        "S27",
        "S29",
        "S30",
        "S31",
        "S38",
        "S44",
        "S51",
    }:
        columns.append(sa.Column("effective_at", sa.DateTime(timezone=True)))
    return columns


def _special_columns(logical_id: str) -> list[sa.Column[Any]]:
    if logical_id == "S01":
        return [
            sa.Column("decision_generation", sa.BigInteger, nullable=False, server_default="0"),
            sa.Column("authorization_epoch", sa.BigInteger, nullable=False, server_default="0"),
            sa.Column("input_frontier_hash", sa.String(64)),
        ]
    if logical_id == "S02":
        return [
            sa.Column("command_kind", sa.Text, nullable=False),
            sa.Column("client_key", sa.Text, nullable=False),
            sa.Column("actor_scope", sa.Text, nullable=False),
            sa.Column("request_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.Text, nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
        ]
    if logical_id == "S14":
        return [
            _uuid("stable_fact_id"),
            sa.Column("revision", sa.Integer, nullable=False),
            sa.Column("fact_kind", sa.Text, nullable=False),
        ]
    if logical_id == "S15":
        return [
            sa.Column("lifecycle_state", sa.Text, nullable=False, server_default="BUILDING"),
            sa.Column("member_revision", sa.BigInteger, nullable=False, server_default="0"),
            sa.Column("completed_member_revision", sa.BigInteger),
            sa.Column("membership_digest", sa.String(64)),
            sa.Column("sealed_at", sa.DateTime(timezone=True)),
        ]
    if logical_id == "S16":
        return [
            sa.Column("member_operation", sa.Text, nullable=False),
            sa.Column("member_kind", sa.Text, nullable=False),
            sa.Column("logical_member_key", sa.Text, nullable=False),
            sa.Column("action_scope", sa.Text, nullable=False),
        ]
    if logical_id == "S23":
        return [sa.Column("lifecycle_state", sa.Text, nullable=False, server_default="BUILDING")]
    if logical_id == "S51":
        return [
            sa.Column("registry_scope", sa.Text, nullable=False),
            sa.Column("registry_revision", sa.BigInteger, nullable=False, server_default="0"),
        ]
    return []


def _special_constraints(logical_id: str) -> list[sa.Constraint]:
    constraints: list[sa.Constraint] = []
    if logical_id == "S01":
        constraints.extend(
            [
                sa.CheckConstraint(
                    "decision_generation >= 0", name="decision_generation_nonnegative"
                ),
                sa.CheckConstraint(
                    "authorization_epoch >= 0", name="authorization_epoch_nonnegative"
                ),
            ]
        )
    elif logical_id == "S02":
        constraints.append(
            sa.UniqueConstraint(
                "subject_id",
                "actor_scope",
                "command_kind",
                "client_key",
                name="uq_command_receipts_idempotency",
            )
        )
    elif logical_id == "S14":
        constraints.extend(
            [
                sa.UniqueConstraint(
                    "subject_id", "stable_fact_id", "revision", name="uq_fact_revision"
                ),
                sa.UniqueConstraint(
                    "subject_id", "fact_revision_id", "fact_kind", name="uq_fact_kind_parent"
                ),
                sa.CheckConstraint("revision >= 1", name="fact_revision_positive"),
                sa.CheckConstraint(
                    "fact_kind IN ('WORKOUT_ACTUAL','HEALTH_OBSERVATION','NUTRITION_INTAKE','BODY_MEASUREMENT','OUTCOME_OBSERVATION')",
                    name="fact_kind_closed",
                ),
            ]
        )
    elif logical_id == "S15":
        constraints.extend(
            [
                sa.CheckConstraint(
                    "lifecycle_state IN ('BUILDING','READY','SEALED','STALE','ABANDONED')",
                    name="factset_state_closed",
                ),
                sa.CheckConstraint("member_revision >= 0", name="member_revision_nonnegative"),
            ]
        )
    elif logical_id == "S16":
        constraints.extend(
            [
                sa.CheckConstraint(
                    "member_operation IN ('SET','REMOVE')", name="member_operation_closed"
                ),
                sa.UniqueConstraint(
                    "subject_id",
                    "ref_s15_id",
                    "member_kind",
                    "logical_member_key",
                    "action_scope",
                    name="uq_factset_member_semantic_key",
                ),
            ]
        )
    elif logical_id == "S23":
        constraints.append(
            sa.CheckConstraint(
                "lifecycle_state IN ('BUILDING','READY','STALE','FAILED','PUBLISHED')",
                name="manifest_build_state_closed",
            )
        )
    elif logical_id == "S51":
        constraints.extend(
            [
                sa.UniqueConstraint("registry_scope", name="uq_registry_scope"),
                sa.CheckConstraint("registry_revision >= 0", name="registry_revision_nonnegative"),
            ]
        )
    return constraints


def _create_logical_table(metadata: sa.MetaData, logical_id: str) -> sa.Table:
    relation = RELATION_BY_ID[logical_id]
    physical = PHYSICAL_BY_ID[logical_id]
    columns = _common_columns(logical_id) + _special_columns(logical_id)
    constraints: list[sa.Constraint] = [
        sa.PrimaryKeyConstraint("subject_id", physical.identity_column),
        sa.CheckConstraint("length(content_hash) = 64", name="content_hash_length"),
        *_special_constraints(logical_id),
    ]

    for dependency in relation.dependencies:
        ref_name = f"ref_{dependency.lower()}_id"
        columns.append(_uuid(ref_name))
        target = PHYSICAL_BY_ID[dependency]
        constraints.append(
            sa.ForeignKeyConstraint(
                ["subject_id", ref_name],
                [
                    f"{target.table_name}.subject_id",
                    f"{target.table_name}.{target.identity_column}",
                ],
                name=f"fk_{relation.table_name}_{dependency.lower()}",
            )
        )

    for reference in DEFERRED_REFERENCES:
        if reference.source == logical_id:
            columns.append(_uuid(reference.field, nullable=True))

    return sa.Table(
        relation.table_name,
        metadata,
        *columns,
        *constraints,
        comment=f"{logical_id} frozen logical relation",
    )


def _add_deferred_foreign_keys(metadata: sa.MetaData) -> None:
    for reference in DEFERRED_REFERENCES:
        source = PHYSICAL_BY_ID[reference.source]
        target = PHYSICAL_BY_ID[reference.target]
        source_table = metadata.tables[source.table_name]
        source_table.append_constraint(
            sa.ForeignKeyConstraint(
                ["subject_id", reference.field],
                [
                    f"{target.table_name}.subject_id",
                    f"{target.table_name}.{target.identity_column}",
                ],
                name=f"fk_{source.table_name}_{reference.field}",
            )
        )


def _value_columns(
    field_name: str,
    field_type: FactFieldType,
    unit_policy: UnitPolicy,
) -> tuple[list[sa.Column[Any]], list[sa.Constraint]]:
    if field_type is FactFieldType.TEXT:
        value_type: sa.types.TypeEngine[Any] = sa.Text()
    elif field_type is FactFieldType.NONNEGATIVE_INTEGER:
        value_type = sa.BigInteger()
    else:
        value_type = sa.Numeric(20, 6)
    columns = [
        sa.Column(f"{field_name}_state", sa.Text, nullable=False),
        sa.Column(f"{field_name}_value", value_type),
        sa.Column(f"{field_name}_unit", sa.Text),
        _uuid(f"{field_name}_evidence_revision_id"),
        _uuid(f"{field_name}_assertion_id"),
        _uuid(f"{field_name}_admission_decision_id"),
        sa.Column(f"{field_name}_source_locator", sa.Text, nullable=False),
    ]
    constraints: list[sa.Constraint] = [
        sa.CheckConstraint(
            f"{field_name}_state IN ('ACTUAL','UNKNOWN','NOT_MEASURED','NOT_APPLICABLE','PARSE_FAILED')",
            name=f"{field_name}_state_closed",
        ),
        sa.CheckConstraint(
            f"(({field_name}_state = 'ACTUAL') = ({field_name}_value IS NOT NULL))",
            name=f"{field_name}_state_value_consistent",
        ),
        sa.CheckConstraint(
            f"length(btrim({field_name}_source_locator)) > 0",
            name=f"{field_name}_source_locator_nonblank",
        ),
    ]
    if field_type in {FactFieldType.NONNEGATIVE_INTEGER, FactFieldType.NONNEGATIVE_DECIMAL}:
        constraints.append(
            sa.CheckConstraint(
                f"{field_name}_value IS NULL OR {field_name}_value >= 0",
                name=f"{field_name}_nonnegative",
            )
        )
    if field_type is FactFieldType.TEXT:
        constraints.extend(
            [
                sa.CheckConstraint(
                    f"{field_name}_state = 'ACTUAL'", name=f"{field_name}_actual_only"
                ),
                sa.CheckConstraint(
                    f"length(btrim({field_name}_value)) > 0", name=f"{field_name}_nonblank"
                ),
            ]
        )
    if unit_policy is UnitPolicy.REQUIRED_WHEN_ACTUAL:
        constraints.append(
            sa.CheckConstraint(
                f"(({field_name}_state = 'ACTUAL') = ({field_name}_unit IS NOT NULL AND length(btrim({field_name}_unit)) > 0))",
                name=f"{field_name}_unit_consistent",
            )
        )
    else:
        constraints.append(
            sa.CheckConstraint(f"{field_name}_unit IS NULL", name=f"{field_name}_unit_forbidden")
        )
    return columns, constraints


def _create_fact_child_tables(metadata: sa.MetaData) -> None:
    provenance_targets = {
        "evidence_revision_id": PHYSICAL_BY_ID["S09"],
        "assertion_id": PHYSICAL_BY_ID["S10"],
        "admission_decision_id": PHYSICAL_BY_ID["S13"],
    }
    for plan in FACT_CHILD_PLANS.values():
        columns: list[sa.Column[Any]] = [
            _uuid("subject_id"),
            _uuid("fact_revision_id"),
            _uuid("stable_fact_id"),
            _uuid(plan.child_identity_field),
            sa.Column(
                "fact_kind",
                sa.Text,
                nullable=False,
                server_default=sa.text(f"'{plan.fact_kind.value}'"),
            ),
        ]
        constraints: list[sa.Constraint] = [
            sa.PrimaryKeyConstraint("subject_id", "fact_revision_id", plan.child_identity_field),
            sa.ForeignKeyConstraint(
                ["subject_id", "fact_revision_id", "fact_kind"],
                [
                    "canonical_fact_revisions.subject_id",
                    "canonical_fact_revisions.fact_revision_id",
                    "canonical_fact_revisions.fact_kind",
                ],
                name=f"fk_{plan.table_name}_fact_revision_kind",
            ),
            sa.CheckConstraint(
                f"fact_kind = '{plan.fact_kind.value}'", name="fact_kind_matches_child"
            ),
        ]
        for field in plan.fields:
            value_columns, value_constraints = _value_columns(
                field.name, field.value_type, field.unit_policy
            )
            columns.extend(value_columns)
            constraints.extend(value_constraints)
            for suffix, target in provenance_targets.items():
                ref_name = f"{field.name}_{suffix}"
                suffix_tag = {
                    "evidence_revision_id": "evidence",
                    "assertion_id": "assertion",
                    "admission_decision_id": "admission",
                }[suffix]
                constraints.append(
                    sa.ForeignKeyConstraint(
                        ["subject_id", ref_name],
                        [
                            f"{target.table_name}.subject_id",
                            f"{target.table_name}.{target.identity_column}",
                        ],
                        name=f"fk_{plan.kind.value.lower()}_{field.name}_{suffix_tag}",
                    )
                )
        sa.Table(
            plan.table_name, metadata, *columns, *constraints, comment="S14 typed child relation"
        )
        sa.Index(
            f"ix_{plan.table_name}_correction_identity",
            metadata.tables[plan.table_name].c.subject_id,
            metadata.tables[plan.table_name].c.stable_fact_id,
            metadata.tables[plan.table_name].c[plan.child_identity_field],
        )


def _create_replay_source_edges(metadata: sa.MetaData) -> None:
    replay = PHYSICAL_BY_ID["S47"]
    for target_id, suffix in (("S14", "fact_revision"), ("S20", "mapping_decision")):
        target = PHYSICAL_BY_ID[target_id]
        table_name = f"replay_artifact_source_{suffix}s"
        target_column = f"source_{suffix}_id"
        sa.Table(
            table_name,
            metadata,
            _uuid("subject_id"),
            _uuid("replay_artifact_id"),
            _uuid(target_column),
            sa.PrimaryKeyConstraint("subject_id", "replay_artifact_id", target_column),
            sa.ForeignKeyConstraint(
                ["subject_id", "replay_artifact_id"],
                [
                    f"{replay.table_name}.subject_id",
                    f"{replay.table_name}.{replay.identity_column}",
                ],
            ),
            sa.ForeignKeyConstraint(
                ["subject_id", target_column],
                [
                    f"{target.table_name}.subject_id",
                    f"{target.table_name}.{target.identity_column}",
                ],
            ),
            comment="Closed typed S47 source revision edge",
        )


def build_metadata() -> sa.MetaData:
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)
    for logical_id in topological_order():
        _create_logical_table(metadata, logical_id)
    _add_deferred_foreign_keys(metadata)
    _create_fact_child_tables(metadata)
    _create_replay_source_edges(metadata)
    return metadata


metadata: Final = build_metadata()
LOGICAL_TABLE_NAMES: Final = frozenset(row.table_name for row in PHYSICAL_RELATIONS)
TYPED_CHILD_TABLE_NAMES: Final = frozenset(plan.table_name for plan in FACT_CHILD_PLANS.values())
REPLAY_EDGE_TABLE_NAMES: Final = frozenset(
    {"replay_artifact_source_fact_revisions", "replay_artifact_source_mapping_decisions"}
)

# Stable names consumed by Alembic and migration tests.
BASELINE_METADATA: Final = metadata
FACT_CHILD_TABLE_NAMES: Final = tuple(sorted(TYPED_CHILD_TABLE_NAMES))
REPLAY_REFERENCE_TABLE_NAMES: Final = tuple(sorted(REPLAY_EDGE_TABLE_NAMES))


def _execute_many(connection: sa.Connection, statements: list[str]) -> None:
    for statement in statements:
        connection.exec_driver_sql(statement)


def install_baseline_protections(connection: sa.Connection) -> None:
    """Install the KL-012 deny-by-default ACL and immutable-history contract."""

    roles = sorted(RUNTIME_ROLE_NAMES)
    for role in roles:
        connection.exec_driver_sql(
            f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )

    connection.exec_driver_sql(
        """CREATE FUNCTION reject_immutable_history_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'KL_IMMUTABLE_HISTORY_MUTATION_REJECTED'; END $$"""
    )
    immutable_tables = [
        protection.table_name
        for protection in PROTECTION_BY_ID.values()
        if protection.storage_class is StorageClass.IMMUTABLE
    ]
    immutable_tables.extend(FACT_CHILD_TABLE_NAMES)
    immutable_tables.extend(REPLAY_REFERENCE_TABLE_NAMES)
    for table_name in immutable_tables:
        connection.exec_driver_sql(
            f"CREATE TRIGGER {table_name}_immutable BEFORE UPDATE OR DELETE "
            f"ON {table_name} FOR EACH ROW EXECUTE FUNCTION "
            "reject_immutable_history_mutation()"
        )

    connection.exec_driver_sql(
        """CREATE FUNCTION guard_factset_revision_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.lifecycle_state IN ('READY', 'SEALED') THEN
            RAISE EXCEPTION 'KL_FACTSET_IMMUTABLE_AFTER_READY';
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END $$"""
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER factset_revisions_write_gate BEFORE UPDATE OR DELETE "
        "ON factset_revisions FOR EACH ROW EXECUTE FUNCTION "
        "guard_factset_revision_mutation()"
    )
    connection.exec_driver_sql(
        """CREATE FUNCTION guard_factset_member_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE owner_state text;
        BEGIN
          SELECT lifecycle_state INTO owner_state FROM factset_revisions
          WHERE subject_id = COALESCE(NEW.subject_id, OLD.subject_id)
            AND factset_id = COALESCE(NEW.ref_s15_id, OLD.ref_s15_id);
          IF owner_state IS DISTINCT FROM 'BUILDING' THEN
            RAISE EXCEPTION 'KL_FACTSET_MEMBER_PARENT_NOT_BUILDING';
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END $$"""
    )
    connection.exec_driver_sql(
        "CREATE TRIGGER factset_members_parent_write_gate "
        "BEFORE INSERT OR UPDATE OR DELETE ON factset_members FOR EACH ROW "
        "EXECUTE FUNCTION guard_factset_member_mutation()"
    )

    for protection in PROTECTION_BY_ID.values():
        table = protection.table_name
        _execute_many(
            connection,
            [
                f"REVOKE ALL ON TABLE {table} FROM PUBLIC",
                *(f"REVOKE ALL ON TABLE {table} FROM {role}" for role in roles),
            ],
        )
        for role in roles:
            permissions = permissions_for_role(protection, role)
            if permissions:
                rendered = ", ".join(sorted(permission.value for permission in permissions))
                connection.exec_driver_sql(f"GRANT {rendered} ON TABLE {table} TO {role}")

    application = DatabaseRole.APPLICATION.value
    auditor = DatabaseRole.AUDITOR.value
    child_roles = {
        **{name: "kl_writer_canonical_fact_service" for name in FACT_CHILD_TABLE_NAMES},
        **{name: "kl_writer_replay_service" for name in REPLAY_REFERENCE_TABLE_NAMES},
    }
    for table, writer in child_roles.items():
        _execute_many(
            connection,
            [
                f"REVOKE ALL ON TABLE {table} FROM PUBLIC",
                *(f"REVOKE ALL ON TABLE {table} FROM {role}" for role in roles),
                f"GRANT SELECT ON TABLE {table} TO {application}, {auditor}",
                f"GRANT SELECT, INSERT ON TABLE {table} TO {writer}",
            ],
        )
