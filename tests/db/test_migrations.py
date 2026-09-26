from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql

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
from kineticloop.persistence.subject_scope import (
    EVALUATION_SUBJECT_LOGINS,
    PRODUCTION_SUBJECT_LOGIN,
    SUBJECT_SCOPE_DATABASE_ROLES,
    SUBJECT_SCOPE_LOGIN_ROLES,
    TEST_SUBJECT_LOGINS,
)

ROOT = Path(__file__).parents[2]
BASELINE_REVISION = "76fd67f76bd4"
SAFETY_REGISTRY_REVISION = "a3f91c7d2e10"
ARTIFACT_REGISTRY_REVISION = "b6e4d8a1c927"
REVISION = "d4c1a9e7b203"
MIGRATION = ROOT / "migrations/versions/76fd67f76bd4_frozen_s01_s51_baseline.py"
SUCCESSOR = ROOT / "migrations/versions/a3f91c7d2e10_safety_registry_integration.py"
ARTIFACT_REGISTRY_SUCCESSOR = ROOT / "migrations/versions/b6e4d8a1c927_artifact_registry.py"
SUBJECT_SCOPE_SUCCESSOR = ROOT / "migrations/versions/d4c1a9e7b203_subject_scope.py"

ROLE_PASSWORD = "kl072-local-only"
PROTECTED_ROLES = (
    "kl_migration_owner",
    "kl_writer_safety_registry",
    "kl_application",
    "kl_auditor",
    "kl_trusted_admin",
)


def role_url(admin_url: str, role: str) -> str:
    parsed = urlsplit(admin_url)
    hostname = parsed.hostname or "127.0.0.1"
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    netloc = f"{quote(role)}:{quote(ROLE_PASSWORD)}@{hostname}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def run_alembic(database_url: str, revision: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(Config(ROOT / "alembic.ini"), revision)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def run_alembic_downgrade(database_url: str, revision: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.downgrade(Config(ROOT / "alembic.ini"), revision)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def provision_external_roles(admin_url: str) -> None:
    role_names = sorted(
        RUNTIME_ROLE_NAMES
        | SUBJECT_SCOPE_DATABASE_ROLES
        | SUBJECT_SCOPE_LOGIN_ROLES
        | {
            "kl_cluster_bootstrap",
            "kl_migration_deployer",
            "kl_migration_owner",
            "kl_trusted_admin",
            "kl_application_login",
            "kl_auditor_login",
            "kl_stop_login",
            "kl_trusted_admin_login",
            "kl_user_login",
            "kl_agent_login",
        }
    )
    with psycopg.connect(admin_url, autocommit=True) as connection:
        for role in PROTECTED_ROLES:
            connection.execute(f"DROP ROLE IF EXISTS {role}_missing_test")
        for role in role_names:
            connection.execute(
                f"DO $role$ BEGIN CREATE ROLE {role}; "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $role$"
            )
        memberships = connection.execute(
            "SELECT parent.rolname parent_name, member.rolname member_name "
            "FROM pg_auth_members membership "
            "JOIN pg_roles parent ON parent.oid=membership.roleid "
            "JOIN pg_roles member ON member.oid=membership.member "
            "WHERE parent.rolname = ANY(%s::text[]) OR member.rolname = ANY(%s::text[])",
            (role_names, role_names),
        ).fetchall()
        for parent, member in memberships:
            connection.execute(
                sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(parent), sql.Identifier(member))
            )
        for role in sorted(
            RUNTIME_ROLE_NAMES
            | SUBJECT_SCOPE_DATABASE_ROLES
            | {"kl_migration_owner", "kl_trusted_admin"}
        ):
            connection.execute(
                f"ALTER ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOINHERIT NOREPLICATION NOBYPASSRLS"
            )
        connection.execute(
            f"ALTER ROLE kl_cluster_bootstrap LOGIN PASSWORD '{ROLE_PASSWORD}' "
            "SUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        for role in (
            "kl_migration_deployer",
            "kl_application_login",
            "kl_auditor_login",
            "kl_stop_login",
            "kl_trusted_admin_login",
            "kl_user_login",
            "kl_agent_login",
            *sorted(SUBJECT_SCOPE_LOGIN_ROLES),
        ):
            connection.execute(
                f"ALTER ROLE {role} LOGIN PASSWORD '{ROLE_PASSWORD}' "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
            )
        for role in (
            "kl_application_login",
            "kl_auditor_login",
            "kl_trusted_admin_login",
            "kl_user_login",
            "kl_agent_login",
            *sorted(SUBJECT_SCOPE_LOGIN_ROLES),
        ):
            connection.execute(f"ALTER ROLE {role} INHERIT")


def external_ownership_handoff(admin_url: str, database_name: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("REASSIGN OWNED BY kl_cluster_bootstrap TO kl_migration_owner")
        connection.execute(f'ALTER DATABASE "{database_name}" OWNER TO kl_migration_owner')
        connection.execute(
            "ALTER ROLE kl_cluster_bootstrap NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        connection.execute(
            "GRANT kl_migration_owner, kl_writer_safety_registry "
            "TO kl_migration_deployer WITH INHERIT FALSE, SET TRUE"
        )
        connection.execute(
            "GRANT kl_application TO kl_application_login WITH INHERIT TRUE, SET FALSE"
        )
        connection.execute(
            "GRANT kl_application TO kl_user_login, kl_agent_login "
            "WITH INHERIT TRUE, SET FALSE"
        )
        connection.execute(
            f"GRANT kl_application TO {PRODUCTION_SUBJECT_LOGIN} "
            "WITH INHERIT TRUE, SET FALSE"
        )
        for login in TEST_SUBJECT_LOGINS:
            connection.execute(
                f"GRANT kl_subject_test TO {login} WITH INHERIT TRUE, SET FALSE"
            )
        for login in EVALUATION_SUBJECT_LOGINS:
            connection.execute(
                f"GRANT kl_subject_evaluation TO {login} WITH INHERIT TRUE, SET FALSE"
            )
        connection.execute(
            "GRANT kl_auditor TO kl_auditor_login WITH INHERIT TRUE, SET FALSE"
        )
        connection.execute(
            "GRANT kl_trusted_admin TO kl_trusted_admin_login WITH INHERIT TRUE, SET FALSE"
        )
        connection.execute(
            "GRANT kl_writer_decision_state_coordinator TO kl_stop_login "
            "WITH INHERIT TRUE, SET FALSE"
        )
        connection.execute(
            "GRANT CONNECT ON DATABASE " + f'"{database_name}"' + " TO "
            "kl_migration_deployer, kl_application_login, kl_stop_login, "
            "kl_trusted_admin_login, kl_auditor_login, kl_user_login, kl_agent_login, "
            + ", ".join(sorted(SUBJECT_SCOPE_LOGIN_ROLES))
        )
        connection.execute("GRANT SELECT ON public.alembic_version TO kl_migration_deployer")


def bootstrap_two_phase(lifecycle: DatabaseLifecycle, *, head: bool = True) -> dict[str, str]:
    database = lifecycle.reset()
    admin_url = database.url
    provision_external_roles(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            f'ALTER DATABASE "{database.database_name}" OWNER TO kl_cluster_bootstrap'
        )
    bootstrap_url = role_url(admin_url, "kl_cluster_bootstrap")
    run_alembic(bootstrap_url, BASELINE_REVISION)
    external_ownership_handoff(admin_url, database.database_name)
    deployer_url = role_url(admin_url, "kl_migration_deployer")
    if head:
        run_alembic(deployer_url, "head")
    return {
        "admin": admin_url,
        "bootstrap": bootstrap_url,
        "deployer": deployer_url,
        "application": role_url(admin_url, "kl_application_login"),
        "auditor": role_url(admin_url, "kl_auditor_login"),
        "stop": role_url(admin_url, "kl_stop_login"),
        "trusted_admin": role_url(admin_url, "kl_trusted_admin_login"),
        "user": role_url(admin_url, "kl_user_login"),
        "agent": role_url(admin_url, "kl_agent_login"),
        "production_subject": role_url(admin_url, PRODUCTION_SUBJECT_LOGIN),
        "test": role_url(admin_url, TEST_SUBJECT_LOGINS[0]),
        "test_2": role_url(admin_url, TEST_SUBJECT_LOGINS[1]),
        "evaluation": role_url(admin_url, EVALUATION_SUBJECT_LOGINS[0]),
        "evaluation_2": role_url(admin_url, EVALUATION_SUBJECT_LOGINS[1]),
    }


def upgrade_empty(lifecycle: DatabaseLifecycle) -> None:
    bootstrap_two_phase(lifecycle)


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
    ) == str(len(LOGICAL_RELATIONS) + len(FACT_CHILD_PLANS) + 12)
    assert (
        migrated_database.execute_sql(
            "SELECT registry_revision FROM kineticloop.safety_registry_state WHERE id=1;"
        )
        == "0"
    )


def test_safety_registry_successor_migration_chain() -> None:
    config = Config(ROOT / "alembic.ini")
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())
    assert [revision.revision for revision in revisions] == [
        REVISION,
        ARTIFACT_REGISTRY_REVISION,
        SAFETY_REGISTRY_REVISION,
        BASELINE_REVISION,
    ]
    assert revisions[0].down_revision == ARTIFACT_REGISTRY_REVISION
    assert revisions[1].down_revision == SAFETY_REGISTRY_REVISION
    assert revisions[2].down_revision == BASELINE_REVISION
    assert revisions[3].down_revision is None
    assert (
        MIGRATION.read_bytes()
        == (ROOT / "migrations/versions/76fd67f76bd4_frozen_s01_s51_baseline.py").read_bytes()
    )


def test_artifact_registry_successor_migration_chain() -> None:
    config = Config(ROOT / "alembic.ini")
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())
    assert [revision.revision for revision in revisions] == [
        REVISION,
        ARTIFACT_REGISTRY_REVISION,
        SAFETY_REGISTRY_REVISION,
        BASELINE_REVISION,
    ]
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1
    assert revisions[0].down_revision == ARTIFACT_REGISTRY_REVISION
    assert revisions[1].down_revision == SAFETY_REGISTRY_REVISION

    spec = spec_from_file_location("kl018_migration", ARTIFACT_REGISTRY_SUCCESSOR)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    statements: list[str] = []
    with patch.object(migration.op, "execute", side_effect=lambda sql: statements.append(str(sql))):
        migration.upgrade()
        migration.downgrade()
    emitted = "\n".join(statements)
    forbidden = (
        r"\bCREATE\s+(?:ROLE|USER)\b",
        r"\bALTER\s+(?:ROLE|USER)\b",
        r"\bDROP\s+(?:ROLE|USER)\b",
        r"\bREASSIGN\s+OWNED\b",
        r"\bGRANT\s+\w+\s+TO\s+\w+\s+WITH\s+(?:ADMIN|SET|INHERIT)\b",
        r"\bREVOKE\s+\w+\s+FROM\s+\w+\b",
    )
    assert statements[0].strip().startswith("DO $preflight$")
    for pattern in forbidden:
        assert re.search(pattern, emitted, flags=re.IGNORECASE) is None

    lifecycle = DatabaseLifecycle(ROOT)
    urls = bootstrap_two_phase(lifecycle)
    with psycopg.connect(urls["deployer"]) as connection:
        assert connection.execute(
            "SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname=session_user"
        ).fetchone() == (False, False)


def test_artifact_registry_upgrade_rejects_malformed_legacy_timeless_row() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    urls = bootstrap_two_phase(lifecycle, head=False)
    run_alembic(urls["deployer"], SAFETY_REGISTRY_REVISION)
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        policy_id = admin.execute(
            "INSERT INTO kineticloop.policy_bundles("
            "subject_id,policy_namespace,policy_version,content_hash) "
            "VALUES (%s,'legacy-timeless','1','legacy-policy') RETURNING id",
            (UUID("00000000-0000-8000-8000-000000000190"),),
        ).fetchone()
        assert policy_id is not None
        admin.execute(
            "INSERT INTO kineticloop.safety_artifacts("
            "id,artifact_kind,artifact_identity,artifact_version,content_hash,"
            "validity_kind,valid_from,valid_until,timeless_approval_policy,"
            "timeless_approval_reason,ref_s05_id) VALUES ("
            "%s,'POLICY_BUNDLE','legacy-malformed','1',%s,'TIMELESS',"
            "clock_timestamp(),NULL,'legacy-noncanonical-policy','legacy reason',%s)",
            (
                UUID("00000000-0000-8000-8000-000000000191"),
                "9" * 64,
                policy_id[0],
            ),
        )

    for _attempt in range(2):
        with pytest.raises(
            Exception,
            match="KL_ARTIFACT_REGISTRY_LEGACY_TIMELESS_INVALID",
        ):
            run_alembic(urls["deployer"], "head")
        with psycopg.connect(urls["admin"]) as admin:
            assert admin.execute("SELECT version_num FROM alembic_version").fetchone() == (
                SAFETY_REGISTRY_REVISION,
            )
            assert admin.execute(
                "SELECT count(*) FROM kineticloop.safety_artifacts "
                "WHERE artifact_identity='legacy-malformed'"
            ).fetchone() == (1,)


def assert_subject_scope_preflight_failure(urls: dict[str, str]) -> None:
    with psycopg.connect(urls["admin"]) as admin:
        before = admin.execute(
            "SELECT version_num,(SELECT count(*) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='kineticloop') FROM alembic_version"
        ).fetchone()
        assert before is not None
    with pytest.raises(Exception, match="KL_SUBJECT_SCOPE_"):
        run_alembic(urls["deployer"], "head")
    with psycopg.connect(urls["admin"]) as admin:
        assert admin.execute(
            "SELECT version_num,(SELECT count(*) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='kineticloop') FROM alembic_version"
        ).fetchone() == before
        assert admin.execute(
            "SELECT to_regclass('kineticloop.subject_scopes'),"
            "has_table_privilege('kl_application',"
            "'kineticloop.authorization_issuances','SELECT')"
        ).fetchone() == (None, True)


def test_subject_scope_preflight_rejects_writer_assumption_paths() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    urls = bootstrap_two_phase(lifecycle, head=False)
    run_alembic(urls["deployer"], ARTIFACT_REGISTRY_REVISION)
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        admin.execute(
            "GRANT kl_writer_authorization_service TO kl_test_subject_1_login "
            "WITH INHERIT FALSE, SET TRUE"
        )
        assert_subject_scope_preflight_failure(urls)
        admin.execute(
            "REVOKE kl_writer_authorization_service FROM kl_test_subject_1_login"
        )

        admin.execute(
            "GRANT kl_writer_replay_service TO kl_subject_evaluation "
            "WITH INHERIT FALSE, SET TRUE"
        )
        assert_subject_scope_preflight_failure(urls)
        admin.execute("REVOKE kl_writer_replay_service FROM kl_subject_evaluation")

    run_alembic(urls["deployer"], "head")
    with psycopg.connect(urls["admin"]) as admin:
        assert admin.execute("SELECT version_num FROM alembic_version").fetchone() == (
            REVISION,
        )


def test_subject_scope_preflight_rejects_principal_object_bypasses() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    urls = bootstrap_two_phase(lifecycle, head=False)
    run_alembic(urls["deployer"], ARTIFACT_REGISTRY_REVISION)
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        admin.execute(
            "GRANT SELECT ON kineticloop.authorization_issuances "
            "TO kl_test_subject_1_login"
        )
        assert_subject_scope_preflight_failure(urls)
        admin.execute(
            "REVOKE SELECT ON kineticloop.authorization_issuances "
            "FROM kl_test_subject_1_login"
        )

        admin.execute("GRANT CREATE ON SCHEMA kineticloop TO kl_evaluation_subject_1_login")
        assert_subject_scope_preflight_failure(urls)
        admin.execute(
            "REVOKE CREATE ON SCHEMA kineticloop FROM kl_evaluation_subject_1_login"
        )

        admin.execute(
            "ALTER TABLE kineticloop.daily_plan_heads "
            "OWNER TO kl_test_subject_1_login"
        )
        assert_subject_scope_preflight_failure(urls)
        admin.execute(
            "ALTER TABLE kineticloop.daily_plan_heads OWNER TO kl_migration_owner"
        )

    run_alembic(urls["deployer"], "head")
    with psycopg.connect(urls["admin"]) as admin:
        assert admin.execute("SELECT version_num FROM alembic_version").fetchone() == (
            REVISION,
        )
        assert admin.execute(
            "SELECT has_table_privilege('kl_test_subject_1_login',"
            "'kineticloop.authorization_issuances','SELECT'),"
            "has_schema_privilege('kl_evaluation_subject_1_login',"
            "'kineticloop','CREATE'),"
            "pg_get_userbyid(c.relowner) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='kineticloop' AND c.relname='daily_plan_heads'"
        ).fetchone() == (False, False, "kl_migration_owner")


def test_subject_scope_downgrade_locks_serialize_registration_and_writes() -> None:
    lifecycle = DatabaseLifecycle(ROOT)

    def assert_downgrade_waits_and_fails(
        urls: dict[str, str], blocking_connection: psycopg.Connection[Any]
    ) -> None:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                run_alembic_downgrade, urls["deployer"], ARTIFACT_REGISTRY_REVISION
            )
            with pytest.raises(TimeoutError):
                future.result(timeout=0.3)
            blocking_connection.commit()
            with pytest.raises(Exception, match="KL_SUBJECT_SCOPE_DOWNGRADE_SCOPED_STATE"):
                future.result(timeout=10)
        with psycopg.connect(urls["admin"]) as admin:
            assert admin.execute("SELECT version_num FROM alembic_version").fetchone() == (
                REVISION,
            )
            assert admin.execute(
                "SELECT count(*) FROM pg_trigger trigger "
                "JOIN pg_class relation ON relation.oid=trigger.tgrelid "
                "JOIN pg_namespace schema ON schema.oid=relation.relnamespace "
                "WHERE schema.nspname='kineticloop' "
                "AND trigger.tgname IN "
                "('subject_storage_scope','subject_storage_truncate') "
                "AND NOT trigger.tgisinternal"
            ).fetchone() == (10,)
            assert admin.execute(
                "SELECT count(*) FROM pg_class relation "
                "JOIN pg_namespace schema ON schema.oid=relation.relnamespace "
                "WHERE schema.nspname='kineticloop' "
                "AND relation.relname=ANY(%s) "
                "AND relation.relrowsecurity AND relation.relforcerowsecurity",
                ([
                    "daily_plan_heads",
                    "authorization_issuances",
                    "execution_bindings",
                    "replay_runs",
                    "replay_artifacts",
                ],),
            ).fetchone() == (5,)

    urls = bootstrap_two_phase(lifecycle)
    registration = psycopg.connect(urls["trusted_admin"])
    try:
        registration.execute(
            "SELECT kineticloop.subject_scope_register("
            "%s,'PRODUCTION',NULL,NULL,%s)",
            (
                UUID("00000000-0000-8000-8000-000000000280"),
                PRODUCTION_SUBJECT_LOGIN,
            ),
        )
        assert_downgrade_waits_and_fails(urls, registration)
    finally:
        registration.close()

    urls = bootstrap_two_phase(lifecycle)
    write_subject = UUID("00000000-0000-8000-8000-000000000281")
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        admin.execute(
            "INSERT INTO kineticloop.user_decision_state(subject_id,authorization_epoch) "
            "VALUES (%s,0)",
            (write_subject,),
        )
    writing = psycopg.connect(urls["admin"])
    try:
        writing.execute("SET ROLE kl_writer_prescription_commit_service")
        writing.execute(
            "INSERT INTO kineticloop.daily_plan_heads(subject_id,local_date) "
            "VALUES (%s,DATE '2026-09-28')",
            (write_subject,),
        )
        assert_downgrade_waits_and_fails(urls, writing)
    finally:
        writing.close()


def test_safety_registry_successor_contains_no_cluster_role_ddl() -> None:
    spec = spec_from_file_location("kl072_migration", SUCCESSOR)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    statements: list[str] = []
    with patch.object(migration.op, "execute", side_effect=lambda sql: statements.append(str(sql))):
        migration.upgrade()
        migration.downgrade()
    emitted = "\n".join(statements)
    forbidden = (
        r"\bCREATE\s+(?:ROLE|USER)\b",
        r"\bALTER\s+(?:ROLE|USER)\b",
        r"\bDROP\s+(?:ROLE|USER)\b",
        r"\bREASSIGN\s+OWNED\b",
        r"\bGRANT\s+\w+\s+TO\s+\w+\s+WITH\s+(?:ADMIN|SET|INHERIT)\b",
        r"\bREVOKE\s+\w+\s+FROM\s+\w+\b",
    )
    assert statements[0].strip().startswith("DO $preflight$")
    for pattern in forbidden:
        assert re.search(pattern, emitted, flags=re.IGNORECASE) is None

    lifecycle = DatabaseLifecycle(ROOT)
    urls = bootstrap_two_phase(lifecycle)
    with psycopg.connect(urls["deployer"]) as connection:
        row = connection.execute(
            "SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname=session_user"
        ).fetchone()
        assert row == (False, False)


def test_two_phase_empty_db_upgrade_head() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    urls = bootstrap_two_phase(lifecycle)
    assert lifecycle.execute_sql("SELECT version_num FROM alembic_version") == REVISION
    with psycopg.connect(urls["admin"]) as connection:
        row = connection.execute(
            "SELECT rolcanlogin,rolsuper,rolcreaterole FROM pg_roles "
            "WHERE rolname='kl_cluster_bootstrap'"
        ).fetchone()
        assert row == (False, False, False)
    with psycopg.connect(urls["deployer"]) as connection:
        row = connection.execute(
            "SELECT rolsuper, rolcreaterole, "
            "pg_has_role(session_user,'kl_migration_owner','SET'), "
            "pg_has_role(session_user,'kl_writer_safety_registry','SET') "
            "FROM pg_roles WHERE rolname=session_user"
        ).fetchone()
        assert row == (False, False, True, True)


def catalog_fingerprint(admin_url: str) -> str:
    with psycopg.connect(admin_url) as connection:
        row = connection.execute(
            """
            WITH catalog_rows AS (
              SELECT 'version:' || version_num AS value FROM alembic_version
              UNION ALL
              SELECT 'class:' || c.oid::regclass::text || ':' || c.relkind::text || ':' ||
                     pg_get_userbyid(c.relowner) || ':' || coalesce(c.relacl::text, '')
              FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
              WHERE n.nspname='kineticloop'
              UNION ALL
              SELECT 'proc:' || p.oid::regprocedure::text || ':' ||
                     pg_get_userbyid(p.proowner) || ':' || coalesce(p.proacl::text, '')
              FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='kineticloop'
              UNION ALL
              SELECT 'role:' || rolname || ':' || rolcanlogin::text || ':' || rolsuper::text || ':' ||
                     rolcreatedb::text || ':' || rolcreaterole::text || ':' || rolinherit::text || ':' ||
                     rolreplication::text || ':' || rolbypassrls::text
              FROM pg_roles WHERE rolname = ANY(%s::text[])
              UNION ALL
              SELECT 'membership:' || parent.rolname || ':' || member.rolname || ':' ||
                     membership.set_option::text || ':' || membership.inherit_option::text || ':' ||
                     membership.admin_option::text
              FROM pg_auth_members membership
              JOIN pg_roles parent ON parent.oid=membership.roleid
              JOIN pg_roles member ON member.oid=membership.member
              WHERE parent.rolname = ANY(%s::text[]) OR member.rolname = ANY(%s::text[])
            ) SELECT md5(string_agg(value, E'\n' ORDER BY value)) FROM catalog_rows
            """,
            (list(PROTECTED_ROLES), list(PROTECTED_ROLES), list(PROTECTED_ROLES)),
        ).fetchone()
        assert row is not None
        return str(row[0])


def assert_preflight_failure(urls: dict[str, str]) -> None:
    before = catalog_fingerprint(urls["admin"])
    with pytest.raises(Exception, match="KL_SAFETY_REGISTRY_ROLE_PREFLIGHT"):
        run_alembic(urls["deployer"], "head")
    assert catalog_fingerprint(urls["admin"]) == before
    with psycopg.connect(urls["admin"]) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            BASELINE_REVISION,
        )


def test_safety_registry_role_preflight_fails_before_object_changes() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    urls = bootstrap_two_phase(lifecycle, head=False)
    admin_url = urls["admin"]
    with psycopg.connect(admin_url, autocommit=True) as admin:
        for role in PROTECTED_ROLES:
            renamed = role + "_missing_test"
            admin.execute(f"ALTER ROLE {role} RENAME TO {renamed}")
            assert_preflight_failure(urls)
            admin.execute(f"ALTER ROLE {renamed} RENAME TO {role}")

        attributes = (
            ("LOGIN", "NOLOGIN"),
            ("SUPERUSER", "NOSUPERUSER"),
            ("CREATEDB", "NOCREATEDB"),
            ("CREATEROLE", "NOCREATEROLE"),
            ("INHERIT", "NOINHERIT"),
            ("REPLICATION", "NOREPLICATION"),
            ("BYPASSRLS", "NOBYPASSRLS"),
        )
        for role in PROTECTED_ROLES:
            for unsafe, safe in attributes:
                admin.execute(f"ALTER ROLE {role} {unsafe}")
                assert_preflight_failure(urls)
                admin.execute(f"ALTER ROLE {role} {safe}")

        admin.execute("GRANT kl_application TO kl_auditor")
        assert_preflight_failure(urls)
        admin.execute("REVOKE kl_application FROM kl_auditor")

        admin.execute(
            "CREATE ROLE kl072_membership_bridge NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        admin.execute(
            "GRANT kl_application TO kl072_membership_bridge "
            "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE"
        )
        admin.execute(
            "GRANT kl072_membership_bridge TO kl_auditor "
            "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE"
        )
        assert_preflight_failure(urls)
        admin.execute("REVOKE kl072_membership_bridge FROM kl_auditor")
        admin.execute("REVOKE kl_application FROM kl072_membership_bridge")

        admin.execute(
            "GRANT kl072_membership_bridge TO kl_migration_owner "
            "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE"
        )
        assert_preflight_failure(urls)
        admin.execute("REVOKE kl072_membership_bridge FROM kl_migration_owner")
        admin.execute("DROP ROLE kl072_membership_bridge")

        for owner in ("kl_migration_owner", "kl_writer_safety_registry"):
            admin.execute(f"REVOKE {owner} FROM kl_migration_deployer")
            assert_preflight_failure(urls)
            admin.execute(f"GRANT {owner} TO kl_migration_deployer WITH INHERIT FALSE, SET TRUE")

            for options in (
                "ADMIN TRUE, INHERIT FALSE, SET TRUE",
                "ADMIN FALSE, INHERIT TRUE, SET TRUE",
                "ADMIN FALSE, INHERIT FALSE, SET FALSE",
            ):
                admin.execute(f"REVOKE {owner} FROM kl_migration_deployer")
                admin.execute(
                    f"GRANT {owner} TO kl_migration_deployer WITH {options}"
                )
                assert_preflight_failure(urls)
                admin.execute(f"REVOKE {owner} FROM kl_migration_deployer")
                admin.execute(
                    f"GRANT {owner} TO kl_migration_deployer "
                    "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE"
                )

        admin.execute(
            "GRANT kl_auditor TO kl_migration_deployer "
            "WITH ADMIN FALSE, INHERIT FALSE, SET FALSE"
        )
        assert_preflight_failure(urls)
        admin.execute("REVOKE kl_auditor FROM kl_migration_deployer")

    run_alembic(urls["deployer"], "head")


def test_safety_registry_migrated_object_ownership() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    bootstrap_two_phase(lifecycle)
    wrong_owners = lifecycle.execute_sql(
        """
        SELECT c.oid::regclass::text || ':' || pg_get_userbyid(c.relowner)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='kineticloop' AND c.relkind IN ('r','S')
          AND pg_get_userbyid(c.relowner) <> 'kl_migration_owner'
        ORDER BY 1
        """
    )
    assert wrong_owners == ""
    wrong_functions = lifecycle.execute_sql(
        """
        SELECT p.oid::regprocedure::text || ':' || pg_get_userbyid(p.proowner)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='kineticloop'
          AND p.proname NOT LIKE 'registry_guard_%'
          AND p.proname <> 'registry_revoke_artifact'
          AND p.proname <> 'registry_register_artifact'
          AND pg_get_userbyid(p.proowner) <> 'kl_migration_owner'
        ORDER BY 1
        """
    )
    assert wrong_functions == ""
    assert (
        lifecycle.execute_sql(
            "SELECT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit "
            "OR rolreplication OR rolbypassrls FROM pg_roles "
            "WHERE rolname='kl_migration_owner'"
        )
        == "f"
    )


def test_safety_registry_repository_integrates_with_migrated_schema() -> None:
    support_spec = spec_from_file_location(
        "kl072_safety_test_support", ROOT / "tests/db/test_safety_registry.py"
    )
    assert support_spec is not None and support_spec.loader is not None
    support = module_from_spec(support_spec)
    support_spec.loader.exec_module(support)

    lifecycle = DatabaseLifecycle(ROOT)
    urls = bootstrap_two_phase(lifecycle)
    support.seed(urls["admin"])
    with psycopg.connect(urls["application"]) as application:
        assert (
            support.execute_shared_registry_command(
                application,
                support.eligibility(support.RegistryCommand.START_SESSION),
                support.mutate(support.RegistryCommand.START_SESSION),
            )
            == 1
        )
    with psycopg.connect(urls["trusted_admin"]) as trusted_admin:
        first = support.revoke_artifact(
            trusted_admin,
            support.revoke_command(),
            effective_at=support.NOW,
            reason_code="EMERGENCY",
        )
    with psycopg.connect(urls["trusted_admin"]) as trusted_admin:
        replay = support.revoke_artifact(
            trusted_admin,
            support.revoke_command(),
            effective_at=support.NOW,
            reason_code="EMERGENCY",
        )
    assert replay == first
    with psycopg.connect(urls["trusted_admin"]) as trusted_admin:
        with pytest.raises(support.RegistryDenied) as denial:
            support.revoke_artifact(
                trusted_admin,
                support.revoke_command(request_hash="f" * 64),
                effective_at=support.NOW,
                reason_code="EMERGENCY",
            )
    assert denial.value.code is support.RegistryDenialCode.IDEMPOTENCY_CONFLICT
    with psycopg.connect(urls["admin"]) as admin:
        row = admin.execute(
            "SELECT s.registry_revision, r.operator_identity, r.command_key, "
            "r.request_hash, r.causation_incident_id, r.outbox_delivery_id "
            "FROM kineticloop.safety_registry_state s "
            "JOIN kineticloop.artifact_revocation_events r "
            "ON r.id=s.last_revocation_id WHERE s.id=1"
        ).fetchone()
        assert row is not None
        assert row[:5] == (
            1,
            "kl_trusted_admin_login",
            "revoke-1",
            "d" * 64,
            UUID(support.INCIDENT_ID),
        )
        assert row[5] is not None
        migrated_rows = admin.execute(
            "SELECT "
            "(SELECT count(*) FROM kineticloop.user_decision_state),"
            "(SELECT count(*) FROM kineticloop.command_receipts),"
            "(SELECT count(*) FROM kineticloop.domain_events),"
            "(SELECT count(*) FROM kineticloop.outbox_deliveries),"
            "(SELECT count(*) FROM kineticloop.safety_artifacts),"
            "(SELECT count(*) FROM kineticloop.artifact_revocation_events),"
            "(SELECT registry_revision FROM kineticloop.safety_registry_state WHERE id=1)"
        ).fetchone()
        assert migrated_rows == (1, 1, 1, 1, 2, 1, 1)


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
        assert (
            migrated_database.execute_sql(
                "SELECT to_regclass('kineticloop." + plan.table_name + "') IS NOT NULL;"
            )
            == "t"
        )
    assert (
        migrated_database.execute_sql(
            "SELECT count(*) FROM pg_constraint con JOIN pg_namespace n ON n.oid=con.connamespace "
            "WHERE n.nspname='kineticloop' AND con.contype='f' "
            "AND con.conrelid IN ('kineticloop.replay_artifact_fact_revision_sources'::regclass, "
            "'kineticloop.replay_artifact_mapping_revision_sources'::regclass);"
        )
        == "4"
    )


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
        "fk_subject_scope_test_policy",
        "fk_subject_principal_scope",
    }
    assert actual_names == base_names | deferred_names | supplemental_names

    for reference in DEFERRED_REFERENCES:
        assert reference.target in RELATION_BY_ID


def test_immutable_history_materialized(migrated_database: DatabaseLifecycle) -> None:
    immutable_tables = (
        {
            protection.table_name
            for protection in PROTECTION_BY_ID.values()
            if protection.storage_class is StorageClass.IMMUTABLE
        }
        | {plan.table_name for plan in FACT_CHILD_PLANS.values()}
        | {
            "replay_artifact_fact_revision_sources",
            "replay_artifact_mapping_revision_sources",
            "safety_artifact_dependencies",
            "authorization_artifact_closure",
            "registry_management_receipts",
            "registry_audit_events",
            "registry_outbox",
            "registry_artifact_receipts",
            "artifact_registration_events",
            "artifact_registration_outbox",
        }
    )
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
        migrated_database.execute_sql("UPDATE kineticloop.policy_bundles SET policy_version='2';")
    policy_writer = role_name_for(PROTECTION_BY_ID["S05"].writers[0].principal)
    assert (
        migrated_database.execute_sql(
            f"SELECT has_table_privilege('{policy_writer}', 'kineticloop.policy_bundles', 'INSERT') "
            f"AND NOT has_table_privilege('{policy_writer}', 'kineticloop.policy_bundles', 'UPDATE') "
            f"AND NOT pg_has_role('{DatabaseRole.APPLICATION.value}', '{policy_writer}', 'MEMBER');"
        )
        == "t"
    )


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
    assert (
        migrated_database.execute_sql(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema='kineticloop' "
            "AND table_name IN ('safety_artifacts','artifact_revocation_events') "
            "AND column_name='subject_id';"
        )
        == "0"
    )


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
    assert (
        migrated_database.execute_sql(
            "SELECT count(*) FROM pg_constraint WHERE connamespace='kineticloop'::regnamespace "
            "AND conname IN ('uq_s39_commit_receipt','uq_authorization_events_natural',"
            "'ck_s43_target_xor','ck_s43_cause_present');"
        )
        == "4"
    )


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
    urls = bootstrap_two_phase(lifecycle)

    role_list = ",".join(f"'{role}'" for role in sorted(RUNTIME_ROLE_NAMES))
    assert (
        lifecycle.execute_sql(
            "SELECT count(*) FROM pg_roles WHERE rolname IN (" + role_list + ") "
            "AND (rolcanlogin OR rolsuper OR rolinherit OR rolcreaterole OR rolcreatedb "
            "OR rolreplication OR rolbypassrls);"
        )
        == "0"
    )
    assert (
        lifecycle.execute_sql(
                "SELECT count(*) FROM pg_auth_members memberships "
                "JOIN pg_roles parent ON parent.oid=memberships.roleid "
                "JOIN pg_roles member ON member.oid=memberships.member "
                "WHERE parent.rolname IN (" + role_list + ") AND member.rolname IN (" + role_list + ");"
        )
        == "0"
    )
    assert (
        lifecycle.execute_sql(
            "SELECT to_regprocedure('kineticloop.publish_policy_bundle(uuid,text,text,text,jsonb)') IS NULL;"
        )
        == "t"
    )
    with psycopg.connect(urls["application"]) as application:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            application.execute(
                "INSERT INTO kineticloop.policy_bundles"
                "(subject_id,policy_namespace,policy_version,content_hash) VALUES "
                "('00000000-0000-0000-0000-000000000020','bypass','1','hash-2')"
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
    assert (
        migrated_database.execute_sql(
            f"SELECT status||':'||(SELECT count(*) FROM kineticloop.factset_members "
            f"WHERE ref_s15_id='{parent}') FROM kineticloop.factset_revisions WHERE id='{parent}';"
        )
        == "READY:1"
    )

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
    urls = bootstrap_two_phase(lifecycle)
    run_alembic_downgrade(urls["deployer"], BASELINE_REVISION)
    assert lifecycle.execute_sql("SELECT version_num FROM alembic_version") == BASELINE_REVISION
    assert (
        lifecycle.execute_sql(
            "SELECT to_regclass('kineticloop.registry_management_receipts') IS NULL"
        )
        == "t"
    )
    run_alembic(urls["deployer"], "head")
    assert lifecycle.execute_sql("SELECT version_num FROM alembic_version") == REVISION


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
