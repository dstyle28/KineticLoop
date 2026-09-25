from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError
from kineticloop.persistence.fact_children import FACT_CHILD_PLANS
from kineticloop.persistence.immutability import (
    PROTECTION_BY_ID,
    DatabaseRole,
    StorageClass,
    role_name_for,
)
from kineticloop.persistence.schema_topology import (
    DEFERRED_REFERENCES,
    LOGICAL_RELATIONS,
    RELATION_BY_ID,
    topological_order,
)

ROOT = Path(__file__).parents[2]
REVISION = "76fd67f76bd4"
MIGRATION = ROOT / "migrations/versions/76fd67f76bd4_frozen_s01_s51_baseline.py"


def upgrade_empty(lifecycle: DatabaseLifecycle) -> None:
    connection = lifecycle.reset()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = connection.url
    try:
        command.upgrade(Config(ROOT / "alembic.ini"), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture()
def migrated_database() -> DatabaseLifecycle:
    lifecycle = DatabaseLifecycle(ROOT)
    upgrade_empty(lifecycle)
    return lifecycle


def test_empty_db_upgrade_head(migrated_database: DatabaseLifecycle) -> None:
    assert migrated_database.execute_sql("SELECT version_num FROM alembic_version;") == REVISION
    assert migrated_database.execute_sql(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='kineticloop' AND c.relkind='r';"
    ) == str(len(LOGICAL_RELATIONS) + len(FACT_CHILD_PLANS) + 2)
    assert migrated_database.execute_sql(
        "SELECT registry_revision FROM kineticloop.safety_registry_state WHERE id=1;"
    ) == "0"


def test_logical_inventory_complete(migrated_database: DatabaseLifecycle) -> None:
    rows = migrated_database.execute_sql(
        "SELECT obj_description(c.oid, 'pg_class') FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='kineticloop' AND obj_description(c.oid, 'pg_class') "
        "LIKE 'S__ frozen logical relation' ORDER BY 1;"
    ).splitlines()
    assert {row.split()[0] for row in rows} == {f"S{number:02d}" for number in range(1, 52)}
    assert len(rows) == 51
    for plan in FACT_CHILD_PLANS.values():
        assert migrated_database.execute_sql(
            "SELECT to_regclass('kineticloop." + plan.table_name + "') IS NOT NULL;"
        ) == "t"
    assert migrated_database.execute_sql(
        "SELECT count(*) FROM pg_constraint con JOIN pg_namespace n ON n.oid=con.connamespace "
        "WHERE n.nspname='kineticloop' AND con.contype='f' "
        "AND con.conrelid IN ('kineticloop.replay_artifact_fact_revision_sources'::regclass, "
        "'kineticloop.replay_artifact_mapping_revision_sources'::regclass);"
    ) == "4"


def test_fk_order_matches_topology(migrated_database: DatabaseLifecycle) -> None:
    migration_text = MIGRATION.read_text(encoding="utf-8")
    positions = {
        relation.logical_id: migration_text.index(f"op.create_table('{relation.table_name}'")
        for relation in LOGICAL_RELATIONS
    }
    assert set(positions) == set(topological_order())
    for relation in LOGICAL_RELATIONS:
        for dependency in relation.dependencies:
            assert positions[dependency] < positions[relation.logical_id]

    actual_names = set(
        migrated_database.execute_sql(
            "SELECT conname FROM pg_constraint con JOIN pg_namespace n ON n.oid=con.connamespace "
            "WHERE n.nspname='kineticloop' AND con.contype='f' AND conname LIKE 'fk_s%' "
            "ORDER BY conname;"
        ).splitlines()
    )
    base_names = {
        f"fk_{relation.logical_id.lower()}_{dependency.lower()}"
        for relation in LOGICAL_RELATIONS
        for dependency in relation.dependencies
    }
    deferred_names = {
        f"fk_{reference.source.lower()}_{reference.target.lower()}_{reference.field}"
        for reference in DEFERRED_REFERENCES
    }
    assert actual_names == base_names | deferred_names

    for reference in DEFERRED_REFERENCES:
        assert reference.target in RELATION_BY_ID


def test_immutable_history_materialized(migrated_database: DatabaseLifecycle) -> None:
    immutable_tables = {
        protection.table_name
        for protection in PROTECTION_BY_ID.values()
        if protection.storage_class is StorageClass.IMMUTABLE
    } | {plan.table_name for plan in FACT_CHILD_PLANS.values()} | {
        "replay_artifact_fact_revision_sources",
        "replay_artifact_mapping_revision_sources",
    }
    guarded = set(
        migrated_database.execute_sql(
            "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='kineticloop' AND NOT t.tgisinternal "
            "AND t.tgname LIKE '%_immutable' ORDER BY c.relname;"
        ).splitlines()
    )
    assert guarded == immutable_tables

    migrated_database.execute_sql(
        "INSERT INTO kineticloop.policy_bundles(subject_id, policy_namespace, policy_version) "
        "VALUES ('00000000-0000-0000-0000-000000000001', 'test', '1');"
    )
    with pytest.raises(DatabaseLifecycleError, match="permission denied"):
        migrated_database.execute_sql(
            f"SET ROLE {DatabaseRole.APPLICATION.value}; "
            "UPDATE kineticloop.policy_bundles SET policy_version='2';"
        )
    with pytest.raises(DatabaseLifecycleError, match="KL_IMMUTABLE_HISTORY_MUTATION_REJECTED"):
        migrated_database.execute_sql(
            "UPDATE kineticloop.policy_bundles SET policy_version='2';"
        )
    policy_writer = role_name_for(PROTECTION_BY_ID["S05"].writers[0].principal)
    assert migrated_database.execute_sql(
        f"SELECT has_table_privilege('{policy_writer}', 'kineticloop.policy_bundles', 'INSERT') "
        f"AND NOT has_table_privilege('{policy_writer}', 'kineticloop.policy_bundles', 'UPDATE') "
        f"AND NOT pg_has_role('{DatabaseRole.APPLICATION.value}', '{policy_writer}', 'MEMBER');"
    ) == "t"


def schema_signature(lifecycle: DatabaseLifecycle) -> str:
    return lifecycle.execute_sql(
        "WITH objects AS ("
        " SELECT 'C:'||c.relname||':'||a.attnum||':'||a.attname||':'||pg_catalog.format_type(a.atttypid,a.atttypmod)||':'||a.attnotnull AS value"
        " FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace"
        " JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped"
        " WHERE n.nspname='kineticloop' AND c.relkind='r'"
        " UNION ALL SELECT 'K:'||conrelid::regclass::text||':'||conname||':'||pg_get_constraintdef(oid)"
        " FROM pg_constraint WHERE connamespace='kineticloop'::regnamespace"
        " UNION ALL SELECT 'T:'||tgrelid::regclass::text||':'||tgname||':'||pg_get_triggerdef(oid)"
        " FROM pg_trigger WHERE tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace='kineticloop'::regnamespace) AND NOT tgisinternal"
        ") SELECT md5(string_agg(value, E'\\n' ORDER BY value)) FROM objects;"
    )


def test_database_rebuild_is_deterministic() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    upgrade_empty(lifecycle)
    first = schema_signature(lifecycle)
    upgrade_empty(lifecycle)
    second = schema_signature(lifecycle)
    assert first == second
