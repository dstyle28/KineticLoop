from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from kineticloop.db.lifecycle import DatabaseLifecycle
from kineticloop.persistence.fact_children import FACT_CHILD_PLANS
from kineticloop.persistence.immutability import (
    PROTECTION_BY_ID,
    StorageClass,
    role_name_for,
)
from kineticloop.persistence.metadata import (
    FACT_CHILD_TABLE_NAMES,
    REPLAY_REFERENCE_TABLE_NAMES,
    SCHEMA,
)
from kineticloop.persistence.schema_topology import (
    DEFERRED_REFERENCES,
    LOGICAL_RELATIONS,
    RELATION_BY_ID,
    topological_order,
)

ROOT = Path(__file__).parents[2]


def alembic_config(database_url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def rebuild(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


@pytest.fixture(scope="module")
def migrated_database() -> Iterator[tuple[DatabaseLifecycle, str]]:
    lifecycle = DatabaseLifecycle(ROOT)
    connection = lifecycle.reset(timeout_seconds=90)
    rebuild(connection.url)
    yield lifecycle, connection.url


def fetch_rows(database_url: str, query: str) -> list[tuple[object, ...]]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(query)
        return list(cursor.fetchall())


def test_empty_db_upgrade_head(
    migrated_database: tuple[DatabaseLifecycle, str],
) -> None:
    _, database_url = migrated_database
    assert fetch_rows(database_url, "SELECT version_num FROM alembic_version") == [
        ("20260924_0001",)
    ]
    logical_tables = fetch_rows(
        database_url,
        f"""SELECT table_name FROM information_schema.tables
        WHERE table_schema = '{SCHEMA}' AND table_type = 'BASE TABLE'
          AND table_name <> 'alembic_version'""",
    )
    assert len(logical_tables) == (
        len(LOGICAL_RELATIONS) + len(FACT_CHILD_TABLE_NAMES) + len(REPLAY_REFERENCE_TABLE_NAMES)
    )


def test_logical_inventory_complete(
    migrated_database: tuple[DatabaseLifecycle, str],
) -> None:
    _, database_url = migrated_database
    expected = {relation.table_name for relation in LOGICAL_RELATIONS}
    actual = {
        str(row[0])
        for row in fetch_rows(
            database_url,
            f"""SELECT table_name FROM information_schema.tables
            WHERE table_schema = '{SCHEMA}' AND table_name <> 'alembic_version'""",
        )
    }
    assert {relation.logical_id for relation in LOGICAL_RELATIONS} == {
        f"S{number:02d}" for number in range(1, 52)
    }
    assert expected <= actual
    assert actual == expected | set(FACT_CHILD_TABLE_NAMES) | set(REPLAY_REFERENCE_TABLE_NAMES)
    assert set(FACT_CHILD_TABLE_NAMES) == {plan.table_name for plan in FACT_CHILD_PLANS.values()}


def test_fk_order_matches_topology(
    migrated_database: tuple[DatabaseLifecycle, str],
) -> None:
    _, database_url = migrated_database
    fk_rows = fetch_rows(
        database_url,
        f"""SELECT source.relname, target.relname
        FROM pg_constraint constraint_row
        JOIN pg_class source ON source.oid = constraint_row.conrelid
        JOIN pg_class target ON target.oid = constraint_row.confrelid
        JOIN pg_namespace namespace ON namespace.oid = source.relnamespace
        WHERE constraint_row.contype = 'f' AND namespace.nspname = '{SCHEMA}'""",
    )
    actual = {(str(source), str(target)) for source, target in fk_rows}
    expected = {
        (relation.table_name, RELATION_BY_ID[dependency].table_name)
        for relation in LOGICAL_RELATIONS
        for dependency in relation.dependencies
    }
    expected.update(
        (
            RELATION_BY_ID[reference.source].table_name,
            RELATION_BY_ID[reference.target].table_name,
        )
        for reference in DEFERRED_REFERENCES
    )
    base_tables = {relation.table_name for relation in LOGICAL_RELATIONS}
    assert {(source, target) for source, target in actual if source in base_tables} == expected
    positions = {logical_id: index for index, logical_id in enumerate(topological_order())}
    assert all(
        positions[dependency] < positions[relation.logical_id]
        for relation in LOGICAL_RELATIONS
        for dependency in relation.dependencies
    )


def test_immutable_history_materialized(
    migrated_database: tuple[DatabaseLifecycle, str],
) -> None:
    _, database_url = migrated_database
    immutable_tables = (
        {
            protection.table_name
            for protection in PROTECTION_BY_ID.values()
            if protection.storage_class is StorageClass.IMMUTABLE
        }
        | set(FACT_CHILD_TABLE_NAMES)
        | set(REPLAY_REFERENCE_TABLE_NAMES)
    )
    trigger_tables = {
        str(row[0])
        for row in fetch_rows(
            database_url,
            f"""SELECT DISTINCT event_object_table FROM information_schema.triggers
            WHERE trigger_schema = '{SCHEMA}' AND action_statement LIKE '%reject_immutable_history_mutation%'""",
        )
    }
    assert trigger_tables == immutable_tables

    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE kl_writer_policy_registry")
            cursor.execute(
                f"""INSERT INTO {SCHEMA}.policy_bundles
                (subject_id, record_id, known_at, content_hash)
                VALUES ('00000000-0000-0000-0000-000000000001',
                        '00000000-0000-0000-0000-000000000002',
                        clock_timestamp(), repeat('a', 64))"""
            )
            cursor.execute("RESET ROLE")
            cursor.execute("SET ROLE kl_application")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cursor.execute(
                    f"UPDATE {SCHEMA}.policy_bundles SET content_hash = repeat('b', 64) "
                    "WHERE record_id = '00000000-0000-0000-0000-000000000002'"
                )
            cursor.execute("RESET ROLE")
            with pytest.raises(psycopg.errors.RaiseException, match="KL_IMMUTABLE"):
                cursor.execute(
                    f"UPDATE {SCHEMA}.policy_bundles SET content_hash = repeat('b', 64) "
                    "WHERE record_id = '00000000-0000-0000-0000-000000000002'"
                )

    for logical_id, protection in PROTECTION_BY_ID.items():
        if protection.storage_class is StorageClass.IMMUTABLE:
            writer = role_name_for(protection.writers[0].principal)
            privileges = fetch_rows(
                database_url,
                "SELECT "
                f"has_table_privilege('{writer}', '{SCHEMA}.{protection.table_name}', 'UPDATE'), "
                f"has_table_privilege('{writer}', '{SCHEMA}.{protection.table_name}', 'DELETE')",
            )
            assert privileges == [(False, False)], logical_id


def schema_fingerprint(database_url: str) -> list[tuple[object, ...]]:
    return fetch_rows(
        database_url,
        f"""SELECT 'column', table_name, column_name, ordinal_position::text,
                       data_type, is_nullable, COALESCE(column_default, '')
        FROM information_schema.columns WHERE table_schema = '{SCHEMA}'
        UNION ALL
        SELECT 'constraint', source.relname, constraint_row.conname,
               constraint_row.contype::text, pg_get_constraintdef(constraint_row.oid), '', ''
        FROM pg_constraint constraint_row
        JOIN pg_class source ON source.oid = constraint_row.conrelid
        JOIN pg_namespace namespace ON namespace.oid = source.relnamespace
        WHERE namespace.nspname = '{SCHEMA}'
        UNION ALL
        SELECT 'trigger', event_object_table, trigger_name, event_manipulation,
               action_statement, action_timing, ''
        FROM information_schema.triggers WHERE trigger_schema = '{SCHEMA}'
        ORDER BY 1, 2, 3, 4, 5, 6, 7""",
    )


def test_database_rebuild_is_deterministic(
    migrated_database: tuple[DatabaseLifecycle, str],
) -> None:
    lifecycle, database_url = migrated_database
    first = schema_fingerprint(database_url)
    connection = lifecycle.reset(timeout_seconds=90)
    assert connection.url == database_url
    rebuild(database_url)
    second = schema_fingerprint(database_url)
    assert first == second
