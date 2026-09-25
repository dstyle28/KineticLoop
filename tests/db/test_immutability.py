from __future__ import annotations

from pathlib import Path

import pytest

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests/fixtures/db/immutable_history/fixture.sql"


@pytest.fixture()
def database() -> DatabaseLifecycle:
    lifecycle = DatabaseLifecycle(ROOT)
    lifecycle.reset()
    lifecycle.execute_sql(FIXTURE.read_text(encoding="utf-8"))
    return lifecycle


def rejected(database: DatabaseLifecycle, sql: str, marker: str) -> None:
    with pytest.raises(DatabaseLifecycleError, match=marker):
        database.execute_sql(sql)


def test_update_delete_rejected(database: DatabaseLifecycle) -> None:
    database.execute_sql(
        "SET ROLE kl012_history_writer; "
        "INSERT INTO kl012_fixture.immutable_history(content) VALUES ('original');"
    )
    rejected(
        database,
        "SET ROLE kl012_history_writer; "
        "UPDATE kl012_fixture.immutable_history SET content = 'rewritten';",
        "permission denied",
    )
    rejected(
        database,
        "SET ROLE kl012_history_writer; DELETE FROM kl012_fixture.immutable_history;",
        "permission denied",
    )
    # Defense in depth: even an accidentally widened grant still reaches a trigger
    # that rejects semantic mutation. The fixture administrator exercises that path.
    rejected(
        database,
        "UPDATE kl012_fixture.immutable_history SET content = 'owner rewrite';",
        "KL_IMMUTABLE_HISTORY_MUTATION_REJECTED",
    )
    rejected(
        database,
        "DELETE FROM kl012_fixture.immutable_history;",
        "KL_IMMUTABLE_HISTORY_MUTATION_REJECTED",
    )
    assert database.execute_sql(
        "SELECT content FROM kl012_fixture.immutable_history ORDER BY history_id;"
    ) == "original"


def test_owned_transition_only(database: DatabaseLifecycle) -> None:
    database.execute_sql(
        "SET ROLE kl012_transition_owner; "
        "INSERT INTO kl012_fixture.owned_transitions(entity_id, state) VALUES (1, 'OPEN');"
    )
    rejected(
        database,
        "SET ROLE kl012_application; "
        "UPDATE kl012_fixture.owned_transitions SET state = 'SEALED', revision = 1 "
        "WHERE entity_id = 1;",
        "permission denied",
    )
    database.execute_sql(
        "SET ROLE kl012_transition_owner; "
        "UPDATE kl012_fixture.owned_transitions SET state = 'SEALED', revision = 1 "
        "WHERE entity_id = 1;"
    )
    rejected(
        database,
        "SET ROLE kl012_transition_owner; "
        "UPDATE kl012_fixture.owned_transitions SET state = 'OPEN', revision = 2 "
        "WHERE entity_id = 1;",
        "KL_INVALID_OWNED_TRANSITION",
    )
    assert database.execute_sql(
        "SELECT state || ':' || revision FROM kl012_fixture.owned_transitions WHERE entity_id = 1;"
    ) == "SEALED:1"

    database.execute_sql(
        "SET ROLE kl012_originating_command; "
        "INSERT INTO kl012_fixture.outbox_deliveries"
        "(event_id, destination, delivery_status) VALUES (1, 'audit', 'PENDING');"
    )
    rejected(
        database,
        "SET ROLE kl012_outbox_dispatcher; "
        "INSERT INTO kl012_fixture.outbox_deliveries"
        "(event_id, destination, delivery_status) VALUES (2, 'forged', 'PENDING');",
        "permission denied",
    )
    rejected(
        database,
        "SET ROLE kl012_originating_command; "
        "UPDATE kl012_fixture.outbox_deliveries "
        "SET delivery_status = 'DELIVERED', attempt_count = 1 WHERE event_id = 1;",
        "permission denied",
    )
    database.execute_sql(
        "SET ROLE kl012_outbox_dispatcher; "
        "UPDATE kl012_fixture.outbox_deliveries "
        "SET delivery_status = 'DELIVERED', attempt_count = 1 WHERE event_id = 1;"
    )
    assert database.execute_sql(
        "SELECT delivery_status || ':' || attempt_count "
        "FROM kl012_fixture.outbox_deliveries WHERE event_id = 1;"
    ) == "DELIVERED:1"


def test_direct_sql_bypass_rejected(database: DatabaseLifecycle) -> None:
    rejected(
        database,
        "SET ROLE kl012_application; "
        "INSERT INTO kl012_fixture.immutable_history(content) VALUES ('bypass');",
        "permission denied",
    )
    rejected(
        database,
        "SET ROLE kl012_application; "
        "ALTER TABLE kl012_fixture.immutable_history DISABLE TRIGGER ALL;",
        "must be owner",
    )
    assert database.execute_sql("SELECT count(*) FROM kl012_fixture.immutable_history;") == "0"

    assert database.execute_sql(
        "SELECT has_table_privilege('kl012_outbox_dispatcher', "
        "'kl012_fixture.outbox_deliveries', 'INSERT');"
    ) == "f"
    assert database.execute_sql(
        "SELECT has_column_privilege('kl012_outbox_dispatcher', "
        "'kl012_fixture.outbox_deliveries', 'delivery_status', 'UPDATE');"
    ) == "t"
    assert database.execute_sql(
        "SELECT has_table_privilege('kl012_originating_command', "
        "'kl012_fixture.outbox_deliveries', 'UPDATE');"
    ) == "f"
