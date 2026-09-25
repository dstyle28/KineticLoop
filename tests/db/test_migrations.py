from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError
from kineticloop.persistence.fact_children import FACT_CHILD_PLANS
from kineticloop.persistence.immutability import (
    PROTECTION_BY_ID,
    RUNTIME_ROLE_NAMES,
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
    ) == str(len(LOGICAL_RELATIONS) + len(FACT_CHILD_PLANS) + 4)
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
    supplemental_names = {
        "fk_s49_dependency_artifact",
        "fk_s49_dependency_target",
        "fk_s42_closure_authorization",
        "fk_s42_closure_artifact",
    }
    assert actual_names == base_names | deferred_names | supplemental_names

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
        "safety_artifact_dependencies",
        "authorization_artifact_closure",
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
        "INSERT INTO kineticloop.policy_bundles"
        "(subject_id, policy_namespace, policy_version, content_hash) "
        "VALUES ('00000000-0000-0000-0000-000000000001', 'test', '1', 'hash-1');"
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


def test_frozen_natural_keys_and_authorization_basis(
    migrated_database: DatabaseLifecycle,
) -> None:
    receipt = (
        "INSERT INTO kineticloop.command_receipts"
        "(subject_id, actor_scope, command_kind, client_key, request_hash, status) VALUES "
        "('00000000-0000-0000-0000-000000000010','USER','TEST','same-key','hash-1','SUCCESS')"
    )
    migrated_database.execute_sql(receipt)
    with pytest.raises(DatabaseLifecycleError, match="uq_command_receipts_natural"):
        migrated_database.execute_sql(receipt.replace("hash-1", "hash-2"))
    with pytest.raises(DatabaseLifecycleError, match="null value"):
        migrated_database.execute_sql(
            "INSERT INTO kineticloop.authorization_issuances"
            "(subject_id, bound_content_hash, scope, valid_from, valid_until, "
            "registry_revision_at_issue) VALUES "
            "('00000000-0000-0000-0000-000000000010','bound','START',"
            "transaction_timestamp(), transaction_timestamp() + interval '1 hour', 0);"
        )
    assert migrated_database.execute_sql(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema='kineticloop' "
        "AND table_name IN ('safety_artifacts','artifact_revocation_events') "
        "AND column_name='subject_id';"
    ) == "0"


def test_registry_and_authorization_authority_is_materialized(
    migrated_database: DatabaseLifecycle,
) -> None:
    subject = "00000000-0000-0000-0000-000000000040"
    policy = migrated_database.execute_sql(
        "INSERT INTO kineticloop.policy_bundles"
        "(subject_id,policy_namespace,policy_version,content_hash) VALUES "
        f"('{subject}','registry-test','1','policy-hash') RETURNING id;"
    ).splitlines()[0]
    release = migrated_database.execute_sql(
        "INSERT INTO kineticloop.evaluation_releases"
        "(subject_id,release_namespace,release_version) VALUES "
        f"('{subject}','registry-test','1') RETURNING id;"
    ).splitlines()[0]
    artifact = migrated_database.execute_sql(
        "INSERT INTO kineticloop.safety_artifacts"
        "(artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,ref_s05_id) VALUES "
        f"('POLICY_BUNDLE','policy-artifact','1','artifact-hash','BOUNDED',transaction_timestamp(),transaction_timestamp() + interval '1 day','{policy}') "
        "RETURNING id;"
    ).splitlines()[0]
    dependency = migrated_database.execute_sql(
        "INSERT INTO kineticloop.safety_artifacts"
        "(artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,ref_s48_id) VALUES "
        f"('EVALUATION_RELEASE','release-artifact','1','release-hash','BOUNDED',transaction_timestamp(),transaction_timestamp() + interval '1 day','{release}') "
        "RETURNING id;"
    ).splitlines()[0]
    migrated_database.execute_sql(
        "INSERT INTO kineticloop.safety_artifact_dependencies"
        f"(artifact_id,dependency_artifact_id) VALUES ('{artifact}','{dependency}');"
    )
    with pytest.raises(DatabaseLifecycleError, match="ck_s49_exact_typed_binding"):
        migrated_database.execute_sql(
            "INSERT INTO kineticloop.safety_artifacts"
            "(artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,ref_s48_id) VALUES "
            f"('POLICY_BUNDLE','wrong-binding','1','wrong-hash','BOUNDED',transaction_timestamp(),transaction_timestamp() + interval '1 day','{release}');"
        )
    migrated_database.execute_sql(
        "INSERT INTO kineticloop.artifact_revocation_events"
        "(management_command_identity,reason_code,revocation_payload_hash,effective_at,"
        "registry_revision,ref_s49_id,registry_state_id) VALUES "
        f"('revoke-1','TEST','payload-1',transaction_timestamp(),1,'{artifact}',1);"
    )
    with pytest.raises(DatabaseLifecycleError, match="uq_s50_registry_revision"):
        migrated_database.execute_sql(
            "INSERT INTO kineticloop.artifact_revocation_events"
            "(management_command_identity,reason_code,revocation_payload_hash,effective_at,"
            "registry_revision,ref_s49_id,registry_state_id) VALUES "
            f"('revoke-2','TEST','payload-2',transaction_timestamp(),1,'{dependency}',1);"
        )
    required_columns = {
        "artifact_dependency_closure_hash",
        "validity_certificate",
    }
    assert set(
        migrated_database.execute_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='kineticloop' AND table_name='authorization_issuances' "
            "AND is_nullable='NO' ORDER BY column_name;"
        ).splitlines()
    ).issuperset(required_columns)
    assert migrated_database.execute_sql(
        "SELECT count(*) FROM pg_constraint WHERE connamespace='kineticloop'::regnamespace "
        "AND conname IN ('uq_s39_commit_receipt','uq_authorization_events_natural',"
        "'ck_s43_target_xor','ck_s43_cause_present');"
    ) == "4"


def test_typed_fact_child_rejects_wrong_parent_kind(
    migrated_database: DatabaseLifecycle,
) -> None:
    subject = "00000000-0000-0000-0000-000000000050"
    evidence = migrated_database.execute_sql(
        "INSERT INTO kineticloop.evidence_revisions"
        "(subject_id,source_connection_identity,source_object_type,source_object_identity,"
        "source_revision,trust_class,source_class,command_authority) VALUES "
        f"('{subject}','source','record','object','1','TRUSTED','PROVIDER','NONE') RETURNING id;"
    ).splitlines()[0]
    assertion = migrated_database.execute_sql(
        "INSERT INTO kineticloop.candidate_assertions"
        "(subject_id,assertion_family_identity,ref_s09_id) VALUES "
        f"('{subject}','assertion-family','{evidence}') RETURNING id;"
    ).splitlines()[0]
    policy = migrated_database.execute_sql(
        "INSERT INTO kineticloop.policy_bundles"
        "(subject_id,policy_namespace,policy_version,content_hash) VALUES "
        f"('{subject}','fact-test','1','fact-policy') RETURNING id;"
    ).splitlines()[0]
    admission = migrated_database.execute_sql(
        "INSERT INTO kineticloop.admission_decisions"
        "(subject_id,action_scope,ref_s05_id,ref_s09_id,ref_s10_id) VALUES "
        f"('{subject}','FACT','{policy}','{evidence}','{assertion}') RETURNING id;"
    ).splitlines()[0]
    event = migrated_database.execute_sql(
        "INSERT INTO kineticloop.underlying_events(subject_id,event_identity) VALUES "
        f"('{subject}','event-1') RETURNING id;"
    ).splitlines()[0]
    fact = migrated_database.execute_sql(
        "INSERT INTO kineticloop.canonical_fact_revisions"
        "(subject_id,stable_fact_identity,fact_kind,fact_revision,ref_s10_id,ref_s11_id,ref_s13_id) VALUES "
        f"('{subject}','fact-1','WORKOUT_ACTUAL',1,'{assertion}','{event}','{admission}') RETURNING id;"
    ).splitlines()[0]
    with pytest.raises(DatabaseLifecycleError, match="KL_FACT_CHILD_PARENT_KIND_MISMATCH"):
        migrated_database.execute_sql(
            "INSERT INTO kineticloop.canonical_fact_nutrition_intakes("
            "subject_id,fact_revision_id,stable_fact_id,intake_item_id,"
            "nutrient_identity_state,nutrient_identity_value,"
            "nutrient_identity_evidence_revision_id,nutrient_identity_assertion_id,"
            "nutrient_identity_admission_decision_id,nutrient_identity_source_locator,"
            "consumed_amount_state,consumed_amount_evidence_revision_id,"
            "consumed_amount_assertion_id,consumed_amount_admission_decision_id,"
            "consumed_amount_source_locator) VALUES ("
            f"'{subject}','{fact}','00000000-0000-0000-0000-000000000051',"
            "'00000000-0000-0000-0000-000000000052','ACTUAL','protein',"
            f"'{evidence}','{assertion}','{admission}','source:nutrient','UNKNOWN',"
            f"'{evidence}','{assertion}','{admission}','source:amount');"
        )


def test_role_reconciliation_and_no_application_write_bypass() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    lifecycle.reset()
    lifecycle.execute_sql(
        "ALTER ROLE kl_writer_policy_registry LOGIN SUPERUSER INHERIT BYPASSRLS; "
        "GRANT kl_writer_policy_registry TO kl_application;"
    )
    connection = lifecycle.connection()
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = connection.url
    try:
        command.upgrade(Config(ROOT / "alembic.ini"), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

    role_list = ",".join(f"'{role}'" for role in sorted(RUNTIME_ROLE_NAMES))
    assert lifecycle.execute_sql(
        "SELECT count(*) FROM pg_roles WHERE rolname IN (" + role_list + ") "
        "AND (rolcanlogin OR rolsuper OR rolinherit OR rolcreaterole OR rolcreatedb "
        "OR rolreplication OR rolbypassrls);"
    ) == "0"
    assert lifecycle.execute_sql(
        "SELECT count(*) FROM pg_auth_members memberships "
        "JOIN pg_roles parent ON parent.oid=memberships.roleid "
        "JOIN pg_roles member ON member.oid=memberships.member "
        "WHERE parent.rolname IN (" + role_list + ") OR member.rolname IN (" + role_list + ");"
    ) == "0"
    assert lifecycle.execute_sql(
        "SELECT to_regprocedure('kineticloop.publish_policy_bundle(uuid,text,text,text,jsonb)') IS NULL;"
    ) == "t"
    with pytest.raises(DatabaseLifecycleError, match="permission denied"):
        lifecycle.execute_sql(
            "SET ROLE kl_application; INSERT INTO kineticloop.policy_bundles"
            "(subject_id,policy_namespace,policy_version,content_hash) VALUES "
            "('00000000-0000-0000-0000-000000000020','bypass','1','hash-2');"
        )


def test_factset_member_seal_serializes_and_old_parent_is_guarded(
    migrated_database: DatabaseLifecycle,
) -> None:
    subject = "00000000-0000-0000-0000-000000000030"
    parent = migrated_database.execute_sql(
        "INSERT INTO kineticloop.factset_revisions"
        "(subject_id,factset_identity,status,storage_mode) VALUES "
        f"('{subject}','00000000-0000-0000-0000-000000000031','BUILDING','FULL') "
        "RETURNING id;"
    ).splitlines()[0]
    connection_url = migrated_database.connection().url
    insert_connection = psycopg.connect(connection_url)
    insert_connection.execute("SET ROLE kl_writer_canonical_view_service")
    insert_connection.execute(
        "INSERT INTO kineticloop.factset_members"
        "(subject_id,ref_s15_id,member_operation,member_kind,logical_member_key,action_scope) "
        "VALUES (%s,%s,'SET','FACT','member-1','PLAN')",
        (subject, parent),
    )

    def seal() -> None:
        with psycopg.connect(connection_url) as seal_connection:
            seal_connection.execute("SET ROLE kl_writer_canonical_view_service")
            seal_connection.execute(
                "UPDATE kineticloop.factset_revisions SET status='READY' WHERE id=%s",
                (parent,),
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(seal)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.2)
        insert_connection.commit()
        future.result(timeout=5)
    insert_connection.close()
    assert migrated_database.execute_sql(
        f"SELECT status||':'||(SELECT count(*) FROM kineticloop.factset_members "
        f"WHERE ref_s15_id='{parent}') FROM kineticloop.factset_revisions WHERE id='{parent}';"
    ) == "READY:1"

    building_parent = migrated_database.execute_sql(
        "INSERT INTO kineticloop.factset_revisions"
        "(subject_id,factset_identity,status,storage_mode) VALUES "
        f"('{subject}','00000000-0000-0000-0000-000000000032','BUILDING','FULL') "
        "RETURNING id;"
    ).splitlines()[0]
    with pytest.raises(DatabaseLifecycleError, match="KL_FACTSET_MEMBER_WRITE_GATE_REJECTED"):
        migrated_database.execute_sql(
            "SET ROLE kl_writer_canonical_view_service; "
            f"UPDATE kineticloop.factset_members SET ref_s15_id='{building_parent}', "
            "logical_member_key='rewritten' "
            f"WHERE ref_s15_id='{parent}';"
        )


def test_upgrade_downgrade_roundtrip() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    upgrade_empty(lifecycle)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = lifecycle.connection().url
    try:
        config = Config(ROOT / "alembic.ini")
        command.downgrade(config, "base")
        assert lifecycle.execute_sql("SELECT to_regnamespace('kineticloop') IS NULL;") == "t"
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


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
