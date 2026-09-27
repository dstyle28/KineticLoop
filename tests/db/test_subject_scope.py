from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import psycopg
import pytest
from psycopg import sql

from kineticloop.db.lifecycle import DatabaseLifecycle
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.subject_scope import (
    EVALUATION_SUBJECT_LOGINS,
    PRODUCTION_SUBJECT_LOGIN,
    TEST_SUBJECT_LOGINS,
    ScopedObjectKind,
    SubjectScopeDenied,
    namespace_for_actor,
    read_scoped_object,
)

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "migrations/versions/d4c1a9e7b203_subject_scope.py"
_SPEC = spec_from_file_location("kl017_test_migrations", ROOT / "tests/db/test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_MIGRATIONS = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATIONS)
bootstrap_two_phase: Any = _MIGRATIONS.bootstrap_two_phase
run_alembic_downgrade: Any = _MIGRATIONS.run_alembic_downgrade
ARTIFACT_REGISTRY_REVISION: str = _MIGRATIONS.ARTIFACT_REGISTRY_REVISION
REVISION: str = _MIGRATIONS.REVISION

_SAFETY_SPEC = spec_from_file_location(
    "kl017_safety_seed", ROOT / "tests/db/test_safety_registry.py"
)
assert _SAFETY_SPEC is not None and _SAFETY_SPEC.loader is not None
_SAFETY: Any = module_from_spec(_SAFETY_SPEC)
_SAFETY_SPEC.loader.exec_module(_SAFETY)

PRODUCTION_SUBJECT = _SAFETY.SUBJECT_ID
TEST_SUBJECT = "00000000-0000-8000-8000-000000000202"
EVALUATION_SUBJECT = "00000000-0000-8000-8000-000000000203"
TEST_SUBJECT_2 = "00000000-0000-8000-8000-000000000402"
EVALUATION_SUBJECT_2 = "00000000-0000-8000-8000-000000000403"
UNKNOWN_SUBJECT = "00000000-0000-8000-8000-000000000204"
PRODUCTION_AUTHORIZATION = _SAFETY.AUTHORIZATION_ID
TEST_AUTHORIZATION = "00000000-0000-8000-8000-000000000212"
EVALUATION_RUN = "00000000-0000-8000-8000-000000000213"
EVALUATION_ARTIFACT = "00000000-0000-8000-8000-000000000214"
TEST_AUTHORIZATION_2 = "00000000-0000-8000-8000-000000000412"
EVALUATION_RUN_2 = "00000000-0000-8000-8000-000000000413"
EVALUATION_ARTIFACT_2 = "00000000-0000-8000-8000-000000000414"
TEST_POLICY = "00000000-0000-8000-8000-000000000215"
OTHER_TEST_POLICY = "00000000-0000-8000-8000-000000000216"
TEST_POLICY_2 = "00000000-0000-8000-8000-000000000415"
TEST_ENVIRONMENT = "00000000-0000-8000-8000-000000000217"
EVALUATION_ENVIRONMENT = "00000000-0000-8000-8000-000000000218"
TEST_ENVIRONMENT_2 = "00000000-0000-8000-8000-000000000417"
EVALUATION_ENVIRONMENT_2 = "00000000-0000-8000-8000-000000000418"
EVALUATION_MANIFEST = "00000000-0000-8000-8000-000000000231"
EVALUATION_RELEASE = "00000000-0000-8000-8000-000000000232"
EVALUATION_MANIFEST_2 = "00000000-0000-8000-8000-000000000431"
EVALUATION_RELEASE_2 = "00000000-0000-8000-8000-000000000432"
TEST_PLAN = "00000000-0000-8000-8000-000000000433"
TEST_PLAN_2 = "00000000-0000-8000-8000-000000000434"


def configure_seed_ids(
    *,
    subject_id: str,
    authorization_id: str,
    policy_id: str,
    start: int,
) -> None:
    values = {
        "SUBJECT_ID": subject_id,
        "AUTHORIZATION_ID": authorization_id,
        "POLICY_ID": policy_id,
        "CALLER_ADMIN_ID": f"00000000-0000-8000-8000-{start:012x}",
        "ARTIFACT_ID": f"00000000-0000-8000-8000-{start + 1:012x}",
        "DEPENDENCY_ID": f"00000000-0000-8000-8000-{start + 2:012x}",
        "INCIDENT_ID": f"00000000-0000-8000-8000-{start + 3:012x}",
        "MISSING_ID": f"00000000-0000-8000-8000-{start + 4:012x}",
        "RELEASE_ID": f"00000000-0000-8000-8000-{start + 5:012x}",
        "MANIFEST_ID": f"00000000-0000-8000-8000-{start + 6:012x}",
        "RECEIPT_ID": f"00000000-0000-8000-8000-{start + 7:012x}",
        "EVENT_ID": f"00000000-0000-8000-8000-{start + 8:012x}",
        "OUTBOX_ID": f"00000000-0000-8000-8000-{start + 9:012x}",
    }
    for name, value in values.items():
        setattr(_SAFETY, name, value)
    _SAFETY.ARTIFACT_CLOSURE_HASH = hashlib.sha256(
        ",".join(sorted((values["ARTIFACT_ID"], values["DEPENDENCY_ID"]))).encode()
    ).hexdigest()


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    urls = bootstrap_two_phase(DatabaseLifecycle(ROOT))
    seed(urls)
    yield urls


def seed(urls: dict[str, str]) -> None:
    _SAFETY.seed(urls["admin"])
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        admin.execute(
            "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash) VALUES "
            "(%s,%s,'test:isolated','1','test-policy'),"
            "(%s,%s,'test:other','1','other-policy'),"
            "(%s,%s,'test:isolated-2','1','test-policy-2')",
            (
                UUID(TEST_POLICY),
                UUID(TEST_SUBJECT),
                UUID(OTHER_TEST_POLICY),
                UUID(TEST_SUBJECT),
                UUID(TEST_POLICY_2),
                UUID(TEST_SUBJECT_2),
            ),
        )
    with psycopg.connect(urls["trusted_admin"], autocommit=True) as trusted:
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,'PRODUCTION',NULL,NULL,%s)",
            (UUID(PRODUCTION_SUBJECT), PRODUCTION_SUBJECT_LOGIN),
        )
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
            (
                UUID(TEST_SUBJECT),
                UUID(TEST_POLICY),
                UUID(TEST_ENVIRONMENT),
                TEST_SUBJECT_LOGINS[0],
            ),
        )
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
            (
                UUID(TEST_SUBJECT_2),
                UUID(TEST_POLICY_2),
                UUID(TEST_ENVIRONMENT_2),
                TEST_SUBJECT_LOGINS[1],
            ),
        )
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,'EVALUATION',NULL,%s,%s)",
            (
                UUID(EVALUATION_SUBJECT),
                UUID(EVALUATION_ENVIRONMENT),
                EVALUATION_SUBJECT_LOGINS[0],
            ),
        )
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,'EVALUATION',NULL,%s,%s)",
            (
                UUID(EVALUATION_SUBJECT_2),
                UUID(EVALUATION_ENVIRONMENT_2),
                EVALUATION_SUBJECT_LOGINS[1],
            ),
        )
    configure_seed_ids(
        subject_id=TEST_SUBJECT,
        authorization_id=TEST_AUTHORIZATION,
        policy_id=TEST_POLICY,
        start=0x260,
    )
    _SAFETY.seed(
        urls["admin"],
        reset=False,
        policy_namespace="test:isolated",
        authorization_scope="TEST_ONLY",
        artifact_identity_suffix="-test",
        include_policy=False,
    )
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        admin.execute(
            "INSERT INTO kineticloop.daily_plan_heads(id,subject_id,local_date) "
            "VALUES (%s,%s,DATE '2026-09-26')",
            (UUID(TEST_PLAN), UUID(TEST_SUBJECT)),
        )
    configure_seed_ids(
        subject_id=TEST_SUBJECT_2,
        authorization_id=TEST_AUTHORIZATION_2,
        policy_id=TEST_POLICY_2,
        start=0x460,
    )
    _SAFETY.seed(
        urls["admin"],
        reset=False,
        policy_namespace="test:isolated-2",
        authorization_scope="TEST_ONLY",
        artifact_identity_suffix="-test-2",
        include_policy=False,
    )
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        admin.execute(
            "INSERT INTO kineticloop.daily_plan_heads(id,subject_id,local_date) "
            "VALUES (%s,%s,DATE '2026-09-27')",
            (UUID(TEST_PLAN_2), UUID(TEST_SUBJECT_2)),
        )
    configure_seed_ids(
        subject_id=EVALUATION_SUBJECT,
        authorization_id="00000000-0000-8000-8000-000000000230",
        policy_id="00000000-0000-8000-8000-000000000239",
        start=0x22B,
    )
    _SAFETY.MANIFEST_ID = EVALUATION_MANIFEST
    _SAFETY.RELEASE_ID = EVALUATION_RELEASE
    _SAFETY.seed(
        urls["admin"],
        reset=False,
        policy_namespace="evaluation:isolated",
        artifact_identity_suffix="-evaluation",
        include_authorization=False,
    )
    configure_seed_ids(
        subject_id=EVALUATION_SUBJECT_2,
        authorization_id="00000000-0000-8000-8000-000000000430",
        policy_id="00000000-0000-8000-8000-000000000439",
        start=0x42B,
    )
    _SAFETY.MANIFEST_ID = EVALUATION_MANIFEST_2
    _SAFETY.RELEASE_ID = EVALUATION_RELEASE_2
    _SAFETY.seed(
        urls["admin"],
        reset=False,
        policy_namespace="evaluation:isolated-2",
        artifact_identity_suffix="-evaluation-2",
        include_authorization=False,
    )
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        admin.execute(
            "INSERT INTO kineticloop.replay_runs("
            "id,subject_id,replay_mode,input_selection_hash,knowledge_cutoff,status,"
            "ref_s24_id,ref_s48_id) VALUES ("
            "%s,%s,'RECORDED_OUTPUT','input',clock_timestamp(),'SUCCEEDED',%s,%s)",
            (
                UUID(EVALUATION_RUN),
                UUID(EVALUATION_SUBJECT),
                UUID(EVALUATION_MANIFEST),
                UUID(EVALUATION_RELEASE),
            ),
        )
        admin.execute(
            "INSERT INTO kineticloop.replay_artifacts(id,subject_id,artifact_kind,artifact_hash,knowledge_cutoff,ref_s46_id) "
            "VALUES (%s,%s,'RECORDED_OUTPUT','artifact',clock_timestamp(),%s)",
            (UUID(EVALUATION_ARTIFACT), UUID(EVALUATION_SUBJECT), UUID(EVALUATION_RUN)),
        )
        admin.execute(
            "INSERT INTO kineticloop.replay_runs("
            "id,subject_id,replay_mode,input_selection_hash,knowledge_cutoff,status,"
            "ref_s24_id,ref_s48_id) VALUES ("
            "%s,%s,'RECORDED_OUTPUT','input-2',clock_timestamp(),'SUCCEEDED',%s,%s)",
            (
                UUID(EVALUATION_RUN_2),
                UUID(EVALUATION_SUBJECT_2),
                UUID(EVALUATION_MANIFEST_2),
                UUID(EVALUATION_RELEASE_2),
            ),
        )
        admin.execute(
            "INSERT INTO kineticloop.replay_artifacts(id,subject_id,artifact_kind,artifact_hash,knowledge_cutoff,ref_s46_id) "
            "VALUES (%s,%s,'RECORDED_OUTPUT','artifact-2',clock_timestamp(),%s)",
            (
                UUID(EVALUATION_ARTIFACT_2),
                UUID(EVALUATION_SUBJECT_2),
                UUID(EVALUATION_RUN_2),
            ),
        )


def test_subject_namespace_isolation(database_urls: dict[str, str]) -> None:
    for url_key in ("test", "test_2", "evaluation", "evaluation_2"):
        with psycopg.connect(database_urls[url_key]) as scoped:
            assert scoped.execute(
                "SELECT kineticloop.subject_scope_lookup('S42',%s)",
                (UUID(PRODUCTION_AUTHORIZATION),),
            ).fetchone() == (None,)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                scoped.execute("SELECT id FROM kineticloop.authorization_issuances")
            scoped.rollback()


def test_cross_subject_denial_is_non_enumerating(database_urls: dict[str, str]) -> None:
    denials = []
    for url_key, role, actor_subject, foreign_subject, foreign_object, object_kind in (
        (
            "test",
            ActorRole.TEST,
            TEST_SUBJECT,
            TEST_SUBJECT_2,
            TEST_AUTHORIZATION_2,
            ScopedObjectKind.AUTHORIZATION_ISSUANCE,
        ),
        (
            "test_2",
            ActorRole.TEST,
            TEST_SUBJECT_2,
            TEST_SUBJECT,
            TEST_AUTHORIZATION,
            ScopedObjectKind.AUTHORIZATION_ISSUANCE,
        ),
        (
            "evaluation",
            ActorRole.EVALUATION,
            EVALUATION_SUBJECT,
            EVALUATION_SUBJECT_2,
            EVALUATION_ARTIFACT_2,
            ScopedObjectKind.REPLAY_ARTIFACT,
        ),
        (
            "evaluation_2",
            ActorRole.EVALUATION,
            EVALUATION_SUBJECT_2,
            EVALUATION_SUBJECT,
            EVALUATION_ARTIFACT,
            ScopedObjectKind.REPLAY_ARTIFACT,
        ),
    ):
        actor = RoleIdentity(
            identity_id="00000000-0000-8000-8000-000000000220", role=role
        )
        with psycopg.connect(database_urls[url_key]) as scoped:
            database_results = [
                scoped.execute(
                    "SELECT kineticloop.subject_scope_lookup(%s,%s)",
                    (object_kind.value, UUID(object_id)),
                ).fetchone()
                for object_id in (
                    foreign_object,
                    "00000000-0000-8000-8000-000000000299",
                )
            ]
            assert database_results == [(None,), (None,)]
            for subject_id, object_id in (
                (foreign_subject, foreign_object),
                (UNKNOWN_SUBJECT, "00000000-0000-8000-8000-000000000299"),
            ):
                with pytest.raises(SubjectScopeDenied) as caught:
                    read_scoped_object(
                        scoped,
                        actor=actor,
                        actor_subject_id=actor_subject,
                        target_subject_id=subject_id,
                        object_kind=object_kind,
                        object_id=object_id,
                    )
                denials.append(caught.value.denial)
            production_results = [
                scoped.execute(
                    "SELECT kineticloop.subject_scope_lookup('S42',%s)",
                    (UUID(object_id),),
                ).fetchone()
                for object_id in (
                    PRODUCTION_AUTHORIZATION,
                    "00000000-0000-8000-8000-000000000299",
                )
            ]
            assert production_results == [(None,), (None,)]
            for subject_id, object_id in (
                (PRODUCTION_SUBJECT, PRODUCTION_AUTHORIZATION),
                (UNKNOWN_SUBJECT, "00000000-0000-8000-8000-000000000299"),
            ):
                with pytest.raises(SubjectScopeDenied) as caught:
                    read_scoped_object(
                        scoped,
                        actor=actor,
                        actor_subject_id=actor_subject,
                        target_subject_id=subject_id,
                        object_kind=ScopedObjectKind.AUTHORIZATION_ISSUANCE,
                        object_id=object_id,
                    )
                denials.append(caught.value.denial)
    assert all(denial == denials[0] for denial in denials)
    assert denials[0].code == "SUBJECT_SCOPE_DENIED"
    assert denials[0].timing_class == "BOUNDED_SCOPE_LOOKUP"
    assert dict(denials[0].payload) == {"error": "subject_scope_denied"}
    serialized = repr(denials)
    for forbidden in (
        TEST_SUBJECT,
        TEST_SUBJECT_2,
        EVALUATION_SUBJECT,
        EVALUATION_SUBJECT_2,
        TEST_AUTHORIZATION,
        TEST_AUTHORIZATION_2,
        EVALUATION_ARTIFACT,
        EVALUATION_ARTIFACT_2,
        PRODUCTION_SUBJECT,
        PRODUCTION_AUTHORIZATION,
    ):
        assert forbidden not in serialized


def test_test_authorization_is_isolated(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["test"]) as scoped:
        row = scoped.execute(
            "SELECT kineticloop.subject_scope_lookup('S42',%s)",
            (UUID(TEST_AUTHORIZATION),),
        ).fetchone()
        assert row is not None and row[0]["subject_id"] == TEST_SUBJECT
    with psycopg.connect(database_urls["test_2"]) as other_test:
        assert other_test.execute(
            "SELECT kineticloop.subject_scope_lookup('S42',%s)",
            (UUID(TEST_AUTHORIZATION),),
        ).fetchone() == (None,)
    with psycopg.connect(database_urls["production_subject"]) as production:
        assert production.execute(
            "SELECT kineticloop.subject_scope_lookup('S42',%s)",
            (UUID(TEST_AUTHORIZATION),),
        ).fetchone() == (None,)
    with psycopg.connect(database_urls["admin"]) as admin:
        for scope, policy in (("PRODUCTION", TEST_POLICY), ("TEST_ONLY", OTHER_TEST_POLICY)):
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_TEST_AUTHORIZATION_DENIED",
            ):
                admin.execute(
                    "INSERT INTO kineticloop.authorization_issuances(subject_id,bound_content_hash,scope,valid_from,valid_until,ref_s05_id) "
                    "VALUES (%s,'denied',%s,clock_timestamp(),clock_timestamp()+interval '1 day',%s)",
                    (UUID(TEST_SUBJECT), scope, UUID(policy)),
                )
            admin.rollback()


def test_evaluation_storage_is_isolated(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["evaluation"]) as scoped:
        row = scoped.execute(
            "SELECT kineticloop.subject_scope_lookup('S47',%s)",
            (UUID(EVALUATION_ARTIFACT),),
        ).fetchone()
        assert row is not None and row[0]["kind"] == "S47"
    with psycopg.connect(database_urls["evaluation_2"]) as other_evaluation:
        assert other_evaluation.execute(
            "SELECT kineticloop.subject_scope_lookup('S47',%s)",
            (UUID(EVALUATION_ARTIFACT),),
        ).fetchone() == (None,)
    with psycopg.connect(database_urls["production_subject"]) as production:
        assert production.execute(
            "SELECT kineticloop.subject_scope_lookup('S47',%s)",
            (UUID(EVALUATION_ARTIFACT),),
        ).fetchone() == (None,)
    with psycopg.connect(database_urls["admin"]) as admin:
        with pytest.raises(
            psycopg.errors.RaiseException, match="KL_SUBJECT_SCOPE_LIVE_STORAGE_DENIED"
        ):
            admin.execute(
                "INSERT INTO kineticloop.authorization_issuances(subject_id,bound_content_hash,scope,valid_from,valid_until) "
                "VALUES (%s,'eval-live','TEST_ONLY',clock_timestamp(),clock_timestamp()+interval '1 day')",
                (UUID(EVALUATION_SUBJECT),),
            )
        admin.rollback()
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="KL_SUBJECT_SCOPE_EVALUATION_STORAGE_DENIED",
        ):
            admin.execute(
                "INSERT INTO kineticloop.replay_runs(subject_id,replay_mode,input_selection_hash,knowledge_cutoff) "
                "VALUES (%s,'RECORDED_OUTPUT','production-replay',clock_timestamp())",
                (UUID(PRODUCTION_SUBJECT),),
            )
        admin.rollback()


def test_application_role_scope_enforced(database_urls: dict[str, str]) -> None:
    for url_key, role, subject_id, object_id in (
        (
            "production_subject",
            ActorRole.SUBJECT,
            PRODUCTION_SUBJECT,
            PRODUCTION_AUTHORIZATION,
        ),
        ("test", ActorRole.TEST, TEST_SUBJECT, TEST_AUTHORIZATION),
        ("test_2", ActorRole.TEST, TEST_SUBJECT_2, TEST_AUTHORIZATION_2),
        (
            "evaluation",
            ActorRole.EVALUATION,
            EVALUATION_SUBJECT,
            EVALUATION_ARTIFACT,
        ),
        (
            "evaluation_2",
            ActorRole.EVALUATION,
            EVALUATION_SUBJECT_2,
            EVALUATION_ARTIFACT_2,
        ),
    ):
        actor = RoleIdentity(
            identity_id="00000000-0000-8000-8000-000000000221", role=role
        )
        with psycopg.connect(database_urls[url_key]) as scoped:
            result = read_scoped_object(
                scoped,
                actor=actor,
                actor_subject_id=subject_id,
                target_subject_id=subject_id,
                object_kind=(
                    ScopedObjectKind.REPLAY_ARTIFACT
                    if role is ActorRole.EVALUATION
                    else ScopedObjectKind.AUTHORIZATION_ISSUANCE
                ),
                object_id=object_id,
            )
            assert result.subject_id == subject_id
            assert result.namespace.value == namespace_for_actor(actor).value
            assert namespace_for_actor(actor).value in {
                "PRODUCTION",
                "TEST",
                "EVALUATION",
            }

    test_actor = RoleIdentity(
        identity_id="00000000-0000-8000-8000-000000000222", role=ActorRole.TEST
    )
    with psycopg.connect(database_urls["application"]) as production_connection:
        with pytest.raises(SubjectScopeDenied):
            read_scoped_object(
                production_connection,
                actor=test_actor,
                actor_subject_id=TEST_SUBJECT,
                target_subject_id=TEST_SUBJECT,
                object_kind=ScopedObjectKind.AUTHORIZATION_ISSUANCE,
                object_id=TEST_AUTHORIZATION,
            )

    with psycopg.connect(database_urls["test_2"]) as wrong_subject_connection:
        with pytest.raises(SubjectScopeDenied) as mismatch:
            read_scoped_object(
                wrong_subject_connection,
                actor=test_actor,
                actor_subject_id=TEST_SUBJECT,
                target_subject_id=TEST_SUBJECT,
                object_kind=ScopedObjectKind.AUTHORIZATION_ISSUANCE,
                object_id=TEST_AUTHORIZATION,
            )
        assert dict(mismatch.value.denial.payload) == {"error": "subject_scope_denied"}


def test_application_wrapper_rejects_forged_database_identity() -> None:
    actor = RoleIdentity(
        identity_id="00000000-0000-8000-8000-000000000224", role=ActorRole.TEST
    )
    base_payload = {
        "kind": "S42",
        "object_id": TEST_AUTHORIZATION,
        "subject_id": TEST_SUBJECT,
        "namespace": "TEST",
    }
    for field, forged_value in (
        ("kind", "S38"),
        ("object_id", PRODUCTION_AUTHORIZATION),
        ("subject_id", TEST_SUBJECT_2),
        ("namespace", "PRODUCTION"),
    ):
        connection: Any = MagicMock()
        connection.execute.return_value.fetchone.return_value = (
            {**base_payload, field: forged_value},
        )
        with pytest.raises(SubjectScopeDenied) as denied:
            read_scoped_object(
                connection,
                actor=actor,
                actor_subject_id=TEST_SUBJECT,
                target_subject_id=TEST_SUBJECT,
                object_kind=ScopedObjectKind.AUTHORIZATION_ISSUANCE,
                object_id=TEST_AUTHORIZATION,
            )
        assert dict(denied.value.denial.payload) == {"error": "subject_scope_denied"}


def test_runtime_writer_membership_drift_is_denied(
    database_urls: dict[str, str],
) -> None:
    actor = RoleIdentity(
        identity_id="00000000-0000-8000-8000-000000000223", role=ActorRole.TEST
    )
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "GRANT kl_writer_authorization_service TO kl_test_subject_1_login "
            "WITH INHERIT FALSE, SET TRUE"
        )
    try:
        with psycopg.connect(database_urls["test"]) as scoped:
            with pytest.raises(SubjectScopeDenied) as denied:
                read_scoped_object(
                    scoped,
                    actor=actor,
                    actor_subject_id=TEST_SUBJECT,
                    target_subject_id=TEST_SUBJECT,
                    object_kind=ScopedObjectKind.AUTHORIZATION_ISSUANCE,
                    object_id=TEST_AUTHORIZATION,
                )
            assert dict(denied.value.denial.payload) == {
                "error": "subject_scope_denied"
            }
            scoped.rollback()
            scoped.execute("SET ROLE kl_writer_authorization_service")
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_DIRECT_DML_DENIED",
            ):
                scoped.execute(
                    "INSERT INTO kineticloop.authorization_issuances("
                    "subject_id,bound_content_hash,scope,valid_from,valid_until) "
                    "VALUES (%s,'direct-bypass','TEST_ONLY',clock_timestamp(),"
                    "clock_timestamp()+interval '1 day')",
                    (UUID(TEST_SUBJECT),),
                )
            scoped.rollback()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(
                "REVOKE kl_writer_authorization_service FROM kl_test_subject_1_login"
            )

    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "GRANT kl_writer_replay_service TO kl_subject_evaluation "
            "WITH INHERIT TRUE, SET TRUE"
        )
    try:
        with psycopg.connect(database_urls["evaluation"]) as scoped:
            updated = scoped.execute(
                "UPDATE kineticloop.replay_runs SET status='BYPASSED' WHERE id=%s",
                (UUID(EVALUATION_RUN),),
            )
            assert updated.rowcount == 0
            scoped.rollback()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute("REVOKE kl_writer_replay_service FROM kl_subject_evaluation")


def _assert_s42_drift_access_is_closed(url: str, *, set_role: str | None = None) -> None:
    with psycopg.connect(url) as scoped:
        if set_role is not None:
            scoped.execute(f"SET ROLE {set_role}")
        assert scoped.execute(
            "SELECT id FROM kineticloop.authorization_issuances "
            "WHERE id IN (%s,%s,%s)",
            (
                UUID(TEST_AUTHORIZATION),
                UUID(TEST_AUTHORIZATION_2),
                UUID(PRODUCTION_AUTHORIZATION),
            ),
        ).fetchall() == []
        assert scoped.execute(
            "UPDATE kineticloop.authorization_issuances "
            "SET bound_content_hash='drift-update' WHERE id IN (%s,%s,%s)",
            (
                UUID(TEST_AUTHORIZATION),
                UUID(TEST_AUTHORIZATION_2),
                UUID(PRODUCTION_AUTHORIZATION),
            ),
        ).rowcount == 0
        assert scoped.execute(
            "DELETE FROM kineticloop.authorization_issuances "
            "WHERE id IN (%s,%s,%s)",
            (
                UUID(TEST_AUTHORIZATION),
                UUID(TEST_AUTHORIZATION_2),
                UUID(PRODUCTION_AUTHORIZATION),
            ),
        ).rowcount == 0
        scoped.rollback()

    for day, subject_id in (
        ("2026-10-01", TEST_SUBJECT),
        ("2026-10-02", TEST_SUBJECT_2),
        ("2026-10-03", PRODUCTION_SUBJECT),
    ):
        with psycopg.connect(url) as scoped:
            if set_role is not None:
                scoped.execute(f"SET ROLE {set_role}")
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_DIRECT_DML_DENIED",
            ):
                scoped.execute(
                    "INSERT INTO kineticloop.daily_plan_heads(subject_id,local_date) "
                    "VALUES (%s,%s)",
                    (UUID(subject_id), day),
                )

    with psycopg.connect(url) as scoped:
        if set_role is not None:
            scoped.execute(f"SET ROLE {set_role}")
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="KL_SUBJECT_SCOPE_DIRECT_DML_DENIED",
        ):
            scoped.execute("TRUNCATE kineticloop.execution_bindings")


def test_force_rls_blocks_post_registration_privilege_drift(
    database_urls: dict[str, str],
) -> None:
    privileges = "SELECT,INSERT,UPDATE,DELETE,TRUNCATE"

    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            f"GRANT {privileges} ON kineticloop.authorization_issuances "
            "TO kl_test_subject_1_login"
        )
        admin.execute(
            "GRANT TRUNCATE ON kineticloop.execution_bindings "
            "TO kl_test_subject_1_login"
        )
        admin.execute(
            "GRANT INSERT ON kineticloop.daily_plan_heads "
            "TO kl_test_subject_1_login"
        )
    try:
        _assert_s42_drift_access_is_closed(database_urls["test"])
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(
                f"REVOKE {privileges} ON kineticloop.authorization_issuances "
                "FROM kl_test_subject_1_login"
            )
            admin.execute(
                "REVOKE TRUNCATE ON kineticloop.execution_bindings "
                "FROM kl_test_subject_1_login"
            )
            admin.execute(
                "REVOKE INSERT ON kineticloop.daily_plan_heads "
                "FROM kl_test_subject_1_login"
            )

    bridge = "kl_subject_scope_acl_bridge"
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            f"CREATE ROLE {bridge} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        admin.execute(
            f"GRANT {privileges} ON kineticloop.authorization_issuances TO {bridge}"
        )
        admin.execute(f"GRANT USAGE ON SCHEMA kineticloop TO {bridge}")
        admin.execute(
            "GRANT EXECUTE ON FUNCTION "
            "kineticloop.subject_scope_rls_allows(uuid,text,text,text) "
            f"TO {bridge}"
        )
        admin.execute(
            f"GRANT TRUNCATE ON kineticloop.execution_bindings TO {bridge}"
        )
        admin.execute(f"GRANT INSERT ON kineticloop.daily_plan_heads TO {bridge}")
        admin.execute(
            f"GRANT {bridge} TO kl_test_subject_1_login "
            "WITH INHERIT TRUE, SET TRUE"
        )
    try:
        _assert_s42_drift_access_is_closed(database_urls["test"])
        _assert_s42_drift_access_is_closed(database_urls["test"], set_role=bridge)
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(f"REVOKE {bridge} FROM kl_test_subject_1_login")
            admin.execute(
                f"REVOKE {privileges} ON kineticloop.authorization_issuances "
                f"FROM {bridge}"
            )
            admin.execute(
                f"REVOKE TRUNCATE ON kineticloop.execution_bindings FROM {bridge}"
            )
            admin.execute(
                f"REVOKE INSERT ON kineticloop.daily_plan_heads FROM {bridge}"
            )
            admin.execute(
                "REVOKE EXECUTE ON FUNCTION "
                "kineticloop.subject_scope_rls_allows(uuid,text,text,text) "
                f"FROM {bridge}"
            )
            admin.execute(f"REVOKE USAGE ON SCHEMA kineticloop FROM {bridge}")
            admin.execute(f"DROP ROLE {bridge}")

    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "ALTER TABLE kineticloop.authorization_issuances "
            "OWNER TO kl_test_subject_1_login"
        )
        admin.execute(
            "ALTER TABLE kineticloop.execution_bindings "
            "OWNER TO kl_test_subject_1_login"
        )
        admin.execute(
            "ALTER TABLE kineticloop.daily_plan_heads "
            "OWNER TO kl_test_subject_1_login"
        )
    try:
        _assert_s42_drift_access_is_closed(database_urls["test"])
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(
                "ALTER TABLE kineticloop.authorization_issuances "
                "OWNER TO kl_migration_owner"
            )
            admin.execute(
                "ALTER TABLE kineticloop.execution_bindings "
                "OWNER TO kl_migration_owner"
            )
            admin.execute(
                "ALTER TABLE kineticloop.daily_plan_heads "
                "OWNER TO kl_migration_owner"
            )

    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "GRANT kl_migration_owner TO kl_test_subject_1_login "
            "WITH INHERIT FALSE, SET TRUE"
        )
    try:
        _assert_s42_drift_access_is_closed(
            database_urls["test"], set_role="kl_migration_owner"
        )
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute("REVOKE kl_migration_owner FROM kl_test_subject_1_login")

    with psycopg.connect(database_urls["admin"]) as admin:
        assert admin.execute(
            "SELECT count(*) FROM kineticloop.authorization_issuances "
            "WHERE id IN (%s,%s,%s)",
            (
                UUID(TEST_AUTHORIZATION),
                UUID(TEST_AUTHORIZATION_2),
                UUID(PRODUCTION_AUTHORIZATION),
            ),
        ).fetchone() == (3,)
        assert admin.execute(
            "SELECT count(*) FROM kineticloop.daily_plan_heads "
            "WHERE local_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-03'"
        ).fetchone() == (0,)


def test_force_rls_preserves_security_definer_command_owner(
    database_urls: dict[str, str],
) -> None:
    function_signature = "kineticloop.kl017_test_update_plan(uuid,text)"
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "GRANT CREATE ON SCHEMA kineticloop "
            "TO kl_writer_prescription_commit_service"
        )
        admin.execute("SET ROLE kl_writer_prescription_commit_service")
        admin.execute(
            "CREATE FUNCTION kineticloop.kl017_test_update_plan("
            "p_plan_id uuid,p_status text) RETURNS bigint "
            "LANGUAGE plpgsql SECURITY DEFINER "
            "SET search_path=pg_catalog,kineticloop,pg_temp AS $routine$ "
            "DECLARE affected bigint; BEGIN "
            "UPDATE kineticloop.daily_plan_heads SET status=p_status "
            "WHERE id=p_plan_id; GET DIAGNOSTICS affected=ROW_COUNT; "
            "RETURN affected; END $routine$"
        )
        admin.execute("RESET ROLE")
        admin.execute(
            "REVOKE CREATE ON SCHEMA kineticloop "
            "FROM kl_writer_prescription_commit_service"
        )
        admin.execute(f"REVOKE ALL ON FUNCTION {function_signature} FROM PUBLIC")
        admin.execute(
            f"GRANT EXECUTE ON FUNCTION {function_signature} TO kl_subject_test"
        )
    try:
        with psycopg.connect(database_urls["test"]) as scoped:
            assert scoped.execute(
                "SELECT kineticloop.kl017_test_update_plan(%s,'RLS_OWNER_OK')",
                (UUID(TEST_PLAN),),
            ).fetchone() == (1,)
            assert scoped.execute(
                "SELECT kineticloop.kl017_test_update_plan(%s,'RLS_CROSS_SUBJECT')",
                (UUID(TEST_PLAN_2),),
            ).fetchone() == (0,)
            scoped.commit()
        with psycopg.connect(database_urls["admin"]) as admin:
            assert admin.execute(
                "SELECT status FROM kineticloop.daily_plan_heads WHERE id=%s",
                (UUID(TEST_PLAN),),
            ).fetchone() == ("RLS_OWNER_OK",)
            assert admin.execute(
                "SELECT status FROM kineticloop.daily_plan_heads WHERE id=%s",
                (UUID(TEST_PLAN_2),),
            ).fetchone() == (None,)
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(f"DROP FUNCTION {function_signature}")


def test_force_rls_inventory_covers_all_protected_tables(
    database_urls: dict[str, str],
) -> None:
    with psycopg.connect(database_urls["admin"]) as admin:
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


def test_bound_subject_cannot_remove_ddl_guards_after_set_role(
    database_urls: dict[str, str],
) -> None:
    ddl_attempts = (
        "ALTER TABLE kineticloop.daily_plan_heads DISABLE ROW LEVEL SECURITY",
        "ALTER TABLE kineticloop.daily_plan_heads DISABLE TRIGGER subject_storage_scope",
        "DROP POLICY subject_scope_select ON kineticloop.daily_plan_heads",
        "DROP TRIGGER subject_storage_scope ON kineticloop.daily_plan_heads",
        "DROP FUNCTION kineticloop.subject_scope_rls_allows(uuid,text,text,text)",
        "DROP TABLE kineticloop.daily_plan_heads",
    )
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "GRANT kl_migration_owner TO kl_test_subject_1_login "
            "WITH INHERIT FALSE, SET TRUE"
        )
    try:
        with psycopg.connect(database_urls["test"]) as scoped:
            scoped.execute("SET ROLE kl_migration_owner")
            assert scoped.execute(
                "DELETE FROM kineticloop.subject_principal_bindings "
                "WHERE principal_name=session_user"
            ).rowcount == 0
        with psycopg.connect(database_urls["test"]) as scoped:
            scoped.execute("SET ROLE kl_migration_owner")
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_DDL_DENIED",
            ):
                scoped.execute(
                    "ALTER TABLE kineticloop.daily_plan_heads "
                    "DISABLE ROW LEVEL SECURITY"
                )

        for statement in ddl_attempts:
            with psycopg.connect(database_urls["test"]) as scoped:
                scoped.execute("SET ROLE kl_migration_owner")
                with pytest.raises(
                    psycopg.errors.RaiseException,
                    match="KL_SUBJECT_SCOPE_DDL_DENIED",
                ):
                    scoped.execute(statement)

        for statement in (
            "ALTER EVENT TRIGGER kl_subject_scope_ddl_guard DISABLE",
            "DROP EVENT TRIGGER kl_subject_scope_ddl_guard",
        ):
            with psycopg.connect(database_urls["test"]) as scoped:
                scoped.execute("SET ROLE kl_migration_owner")
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    scoped.execute(statement)

        with psycopg.connect(database_urls["test"]) as scoped:
            scoped.execute("SET ROLE kl_migration_owner")
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_DIRECT_DML_DENIED",
            ):
                scoped.execute(
                    "INSERT INTO kineticloop.daily_plan_heads(subject_id,local_date) "
                    "VALUES (%s,DATE '2026-10-04')",
                    (UUID(PRODUCTION_SUBJECT),),
                )

        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(
                "ALTER TABLE kineticloop.daily_plan_heads "
                "OWNER TO kl_test_subject_1_login"
            )
        try:
            with psycopg.connect(database_urls["test"]) as scoped:
                with pytest.raises(
                    psycopg.errors.RaiseException,
                    match="KL_SUBJECT_SCOPE_DDL_DENIED",
                ):
                    scoped.execute(
                        "ALTER TABLE kineticloop.daily_plan_heads "
                        "DISABLE ROW LEVEL SECURITY"
                    )
        finally:
            with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
                admin.execute(
                    "ALTER TABLE kineticloop.daily_plan_heads "
                    "OWNER TO kl_migration_owner"
                )
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute("REVOKE kl_migration_owner FROM kl_test_subject_1_login")

    with psycopg.connect(database_urls["admin"]) as admin:
        assert admin.execute(
            "SELECT subject_id FROM kineticloop.subject_principal_bindings "
            "WHERE principal_name='kl_test_subject_1_login'"
        ).fetchone() == (UUID(TEST_SUBJECT),)
        assert admin.execute(
            "SELECT relrowsecurity,relforcerowsecurity FROM pg_class relation "
            "JOIN pg_namespace schema ON schema.oid=relation.relnamespace "
            "WHERE schema.nspname='kineticloop' "
            "AND relation.relname='daily_plan_heads'"
        ).fetchone() == (True, True)
        assert admin.execute(
            "SELECT count(*) FROM kineticloop.daily_plan_heads "
            "WHERE local_date=DATE '2026-10-04'"
        ).fetchone() == (0,)
        assert admin.execute(
            "SELECT count(*) FROM pg_policy policy "
            "JOIN pg_class relation ON relation.oid=policy.polrelid "
            "JOIN pg_namespace schema ON schema.oid=relation.relnamespace "
            "WHERE schema.nspname='kineticloop' "
            "AND policy.polname LIKE 'subject_scope_%'"
        ).fetchone() == (20,)
        assert admin.execute(
            "SELECT count(*) FROM pg_trigger trigger "
            "JOIN pg_class relation ON relation.oid=trigger.tgrelid "
            "JOIN pg_namespace schema ON schema.oid=relation.relnamespace "
            "WHERE schema.nspname='kineticloop' "
            "AND trigger.tgname='subject_storage_truncate' "
            "AND NOT trigger.tgisinternal"
        ).fetchone() == (5,)


def test_bound_subject_ddl_guard_blocks_references_existence_oracles(
    database_urls: dict[str, str],
) -> None:
    probe_table = "kl017_fk_probe"
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        database_row = admin.execute("SELECT current_database()").fetchone()
        assert database_row is not None
        database_name = database_row[0]
        admin.execute(
            "GRANT REFERENCES ON kineticloop.daily_plan_heads "
            "TO kl_test_subject_1_login"
        )
        admin.execute(
            sql.SQL("GRANT TEMPORARY ON DATABASE {} TO kl_test_subject_1_login").format(
                sql.Identifier(database_name)
            )
        )
        admin.execute(
            "GRANT kl_migration_owner TO kl_test_subject_1_login "
            "WITH INHERIT FALSE, SET TRUE"
        )
        admin.execute(f"CREATE TABLE kineticloop.{probe_table}(ref_s38 uuid)")
        admin.execute(
            f"ALTER TABLE kineticloop.{probe_table} OWNER TO kl_migration_owner"
        )
    try:
        with psycopg.connect(database_urls["test"]) as scoped:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_DDL_DENIED",
            ):
                scoped.execute(
                    "CREATE TEMP TABLE kl017_fk_temp_probe("
                    "ref_s38 uuid REFERENCES kineticloop.daily_plan_heads(id))"
                )
        with psycopg.connect(database_urls["test"]) as scoped:
            scoped.execute("SET ROLE kl_migration_owner")
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_DDL_DENIED",
            ):
                scoped.execute(
                    f"ALTER TABLE kineticloop.{probe_table} "
                    "ADD CONSTRAINT fk_kl017_probe FOREIGN KEY(ref_s38) "
                    "REFERENCES kineticloop.daily_plan_heads(id)"
                )
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(f"DROP TABLE IF EXISTS kineticloop.{probe_table}")
            admin.execute("REVOKE kl_migration_owner FROM kl_test_subject_1_login")
            admin.execute(
                "REVOKE REFERENCES ON kineticloop.daily_plan_heads "
                "FROM kl_test_subject_1_login"
            )
            admin.execute(
                sql.SQL(
                    "REVOKE TEMPORARY ON DATABASE {} FROM kl_test_subject_1_login"
                ).format(sql.Identifier(database_name))
            )


def test_bound_subject_bypassrls_drift_cannot_write_protected_rows(
    database_urls: dict[str, str],
) -> None:
    privileges = "SELECT,INSERT,UPDATE,DELETE"
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        original_status = admin.execute(
            "SELECT status FROM kineticloop.daily_plan_heads WHERE id=%s",
            (UUID(TEST_PLAN),),
        ).fetchone()
        assert original_status is not None
        admin.execute("ALTER ROLE kl_test_subject_1_login BYPASSRLS")
        admin.execute(
            f"GRANT {privileges} ON kineticloop.daily_plan_heads "
            "TO kl_test_subject_1_login"
        )
    try:
        attempts = (
            (
                "INSERT INTO kineticloop.daily_plan_heads(subject_id,local_date) "
                "VALUES (%s,DATE '2026-10-05')",
                (UUID(PRODUCTION_SUBJECT),),
            ),
            (
                "UPDATE kineticloop.daily_plan_heads SET status='BYPASS' "
                "WHERE id=%s",
                (UUID(TEST_PLAN),),
            ),
            (
                "DELETE FROM kineticloop.daily_plan_heads WHERE id=%s",
                (UUID(TEST_PLAN),),
            ),
        )
        for statement, parameters in attempts:
            with psycopg.connect(database_urls["test"]) as scoped:
                with pytest.raises(
                    psycopg.errors.RaiseException,
                    match="KL_SUBJECT_SCOPE_DIRECT_DML_DENIED",
                ):
                    scoped.execute(statement, parameters)
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(
                f"REVOKE {privileges} ON kineticloop.daily_plan_heads "
                "FROM kl_test_subject_1_login"
            )
            admin.execute("ALTER ROLE kl_test_subject_1_login NOBYPASSRLS")

    with psycopg.connect(database_urls["admin"]) as admin:
        assert admin.execute(
            "SELECT count(*) FROM kineticloop.daily_plan_heads "
            "WHERE local_date=DATE '2026-10-05'"
        ).fetchone() == (0,)
        assert admin.execute(
            "SELECT status FROM kineticloop.daily_plan_heads WHERE id=%s",
            (UUID(TEST_PLAN),),
        ).fetchone() == original_status


def test_authority_metadata_acl_membership_and_owner_drift_fail_closed(
    database_urls: dict[str, str],
) -> None:
    metadata_tables = "kineticloop.subject_scopes,kineticloop.subject_principal_bindings"
    privileges = "SELECT,INSERT,UPDATE,DELETE,TRUNCATE"
    test_actor = RoleIdentity(
        identity_id="00000000-0000-8000-8000-000000000225",
        role=ActorRole.TEST,
    )

    def assert_lookup_is_non_enumerating() -> None:
        denials = []
        for object_id in (
            TEST_AUTHORIZATION_2,
            "00000000-0000-8000-8000-000000000299",
        ):
            with psycopg.connect(database_urls["test"]) as scoped:
                with pytest.raises(SubjectScopeDenied) as caught:
                    read_scoped_object(
                        scoped,
                        actor=test_actor,
                        actor_subject_id=TEST_SUBJECT,
                        target_subject_id=TEST_SUBJECT,
                        object_kind=ScopedObjectKind.AUTHORIZATION_ISSUANCE,
                        object_id=object_id,
                    )
                denials.append(caught.value.denial)
        assert denials[0] == denials[1]
        assert denials[0].code == "SUBJECT_SCOPE_DENIED"
        assert denials[0].timing_class == "BOUNDED_SCOPE_LOOKUP"
        assert dict(denials[0].payload) == {"error": "subject_scope_denied"}

    def assert_registration_rejects_principal_drift() -> None:
        with psycopg.connect(database_urls["trusted_admin"]) as trusted:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_PRINCIPAL_INVALID",
            ):
                trusted.execute(
                    "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
                    (
                        UUID(TEST_SUBJECT),
                        UUID(TEST_POLICY),
                        UUID(TEST_ENVIRONMENT),
                        TEST_SUBJECT_LOGINS[0],
                    ),
                )

    def assert_metadata_mutations_are_denied(*, set_role: str | None = None) -> None:
        filtered_attempts = (
            (
                "DELETE FROM kineticloop.subject_principal_bindings "
                "WHERE principal_name=%s",
                (TEST_SUBJECT_LOGINS[1],),
            ),
            (
                "UPDATE kineticloop.subject_principal_bindings SET subject_id=%s "
                "WHERE principal_name=%s",
                (UUID(TEST_SUBJECT_2), TEST_SUBJECT_LOGINS[0]),
            ),
            (
                "UPDATE kineticloop.subject_scopes SET policy_id=%s "
                "WHERE subject_id=%s",
                (UUID(TEST_POLICY_2), UUID(TEST_SUBJECT)),
            ),
        )
        for statement, parameters in filtered_attempts:
            with psycopg.connect(database_urls["test"]) as scoped:
                if set_role is not None:
                    scoped.execute(f"SET ROLE {set_role}")
                assert scoped.execute(statement, parameters).rowcount == 0
        with psycopg.connect(database_urls["test"]) as scoped:
            if set_role is not None:
                scoped.execute(f"SET ROLE {set_role}")
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_METADATA_DML_DENIED",
            ):
                scoped.execute("TRUNCATE kineticloop.subject_principal_bindings")

    def assert_metadata_reads_are_denied(*, set_role: str | None = None) -> None:
        with psycopg.connect(database_urls["test"]) as scoped:
            if set_role is not None:
                scoped.execute(f"SET ROLE {set_role}")
            assert scoped.execute(
                "SELECT subject_id,namespace FROM kineticloop.subject_scopes"
            ).fetchall() == []
            assert scoped.execute(
                "SELECT principal_name,subject_id,namespace "
                "FROM kineticloop.subject_principal_bindings"
            ).fetchall() == []

    def assert_metadata_insert_is_denied(*, set_role: str | None = None) -> None:
        with psycopg.connect(database_urls["test"]) as scoped:
            if set_role is not None:
                scoped.execute(f"SET ROLE {set_role}")
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_METADATA_DML_DENIED",
            ):
                scoped.execute(
                    "INSERT INTO kineticloop.subject_scopes("
                    "subject_id,namespace,policy_id,environment_id) "
                    "VALUES (%s,'PRODUCTION',NULL,NULL)",
                    (UUID("00000000-0000-8000-8000-000000000298"),),
                )

    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            f"GRANT {privileges} ON {metadata_tables} TO kl_test_subject_1_login"
        )
    try:
        assert_metadata_reads_are_denied()
        assert_metadata_mutations_are_denied()
        assert_metadata_insert_is_denied()
        assert_lookup_is_non_enumerating()
        assert_registration_rejects_principal_drift()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(
                f"REVOKE {privileges} ON {metadata_tables} "
                "FROM kl_test_subject_1_login"
            )

    bridge = "kl_subject_authority_acl_bridge"
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            f"CREATE ROLE {bridge} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        admin.execute(f"GRANT USAGE ON SCHEMA kineticloop TO {bridge}")
        admin.execute(f"GRANT {privileges} ON {metadata_tables} TO {bridge}")
        admin.execute(
            "GRANT EXECUTE ON FUNCTION "
            "kineticloop.subject_authority_metadata_allows(text,text,text) "
            f"TO {bridge}"
        )
        admin.execute(
            f"GRANT {bridge} TO kl_test_subject_1_login "
            "WITH INHERIT TRUE, SET TRUE"
        )
    try:
        assert_metadata_reads_are_denied()
        assert_metadata_reads_are_denied(set_role=bridge)
        assert_metadata_mutations_are_denied()
        assert_metadata_mutations_are_denied(set_role=bridge)
        assert_metadata_insert_is_denied()
        assert_metadata_insert_is_denied(set_role=bridge)
        assert_lookup_is_non_enumerating()
        assert_registration_rejects_principal_drift()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(f"REVOKE {bridge} FROM kl_test_subject_1_login")
            admin.execute(
                "REVOKE EXECUTE ON FUNCTION "
                "kineticloop.subject_authority_metadata_allows(text,text,text) "
                f"FROM {bridge}"
            )
            admin.execute(f"REVOKE {privileges} ON {metadata_tables} FROM {bridge}")
            admin.execute(f"REVOKE USAGE ON SCHEMA kineticloop FROM {bridge}")
            admin.execute(f"DROP ROLE {bridge}")

    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "ALTER TABLE kineticloop.subject_scopes "
            "OWNER TO kl_test_subject_1_login"
        )
        admin.execute(
            "ALTER TABLE kineticloop.subject_principal_bindings "
            "OWNER TO kl_test_subject_1_login"
        )
    try:
        assert_metadata_reads_are_denied()
        assert_metadata_mutations_are_denied()
        assert_metadata_insert_is_denied()
        assert_lookup_is_non_enumerating()
        assert_registration_rejects_principal_drift()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(
                "ALTER TABLE kineticloop.subject_principal_bindings "
                "OWNER TO kl_migration_owner"
            )
            admin.execute(
                "ALTER TABLE kineticloop.subject_scopes OWNER TO kl_migration_owner"
            )

    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "GRANT kl_trusted_admin TO kl_test_subject_1_login "
            "WITH INHERIT TRUE, SET TRUE"
        )
    try:
        with psycopg.connect(database_urls["test"]) as scoped:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_REGISTRATION_DENIED",
            ):
                scoped.execute(
                    "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
                    (
                        UUID(TEST_SUBJECT),
                        UUID(TEST_POLICY),
                        UUID(TEST_ENVIRONMENT),
                        TEST_SUBJECT_LOGINS[0],
                    ),
                )
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute("REVOKE kl_trusted_admin FROM kl_test_subject_1_login")

    trusted_bridge = "kl_subject_registration_drift_bridge"
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            f"CREATE ROLE {trusted_bridge} NOLOGIN NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
        admin.execute(
            f"GRANT {trusted_bridge} TO kl_trusted_admin_login "
            "WITH INHERIT TRUE, SET TRUE"
        )
    try:
        with psycopg.connect(database_urls["trusted_admin"]) as trusted:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_REGISTRATION_DENIED",
            ):
                trusted.execute(
                    "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
                    (
                        UUID(TEST_SUBJECT),
                        UUID(TEST_POLICY),
                        UUID(TEST_ENVIRONMENT),
                        TEST_SUBJECT_LOGINS[0],
                    ),
                )
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(f"REVOKE {trusted_bridge} FROM kl_trusted_admin_login")
            admin.execute(f"DROP ROLE {trusted_bridge}")

    with psycopg.connect(database_urls["admin"]) as admin:
        assert admin.execute(
            "SELECT principal_name,subject_id,namespace "
            "FROM kineticloop.subject_principal_bindings "
            "WHERE principal_name IN (%s,%s) ORDER BY principal_name",
            (TEST_SUBJECT_LOGINS[0], TEST_SUBJECT_LOGINS[1]),
        ).fetchall() == [
            (TEST_SUBJECT_LOGINS[0], UUID(TEST_SUBJECT), "TEST"),
            (TEST_SUBJECT_LOGINS[1], UUID(TEST_SUBJECT_2), "TEST"),
        ]


def test_noncanonical_inbound_fk_fails_registration_lookup_and_rls(
    database_urls: dict[str, str],
) -> None:
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute("CREATE SCHEMA kl017_legacy_probe")
        admin.execute(
            "CREATE TABLE kl017_legacy_probe.s42_probe("
            "subject_id uuid,authorization_id uuid,"
            "CONSTRAINT fk_kl017_noncanonical_s42 FOREIGN KEY("
            "subject_id,authorization_id) REFERENCES "
            "kineticloop.authorization_issuances(subject_id,id))"
        )
        admin.execute(
            "ALTER TABLE kl017_legacy_probe.s42_probe "
            "OWNER TO kl_test_subject_1_login"
        )
    try:
        with psycopg.connect(database_urls["trusted_admin"]) as trusted:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_NONCANONICAL_INBOUND_FK",
            ):
                trusted.execute(
                    "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
                    (
                        UUID(TEST_SUBJECT),
                        UUID(TEST_POLICY),
                        UUID(TEST_ENVIRONMENT),
                        TEST_SUBJECT_LOGINS[0],
                    ),
                )
        with psycopg.connect(database_urls["test"]) as scoped:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_ROLE_DENIED",
            ):
                scoped.execute(
                    "SELECT kineticloop.subject_scope_lookup('S42',%s)",
                    (UUID(TEST_AUTHORIZATION_2),),
                )
        with psycopg.connect(database_urls["test"]) as scoped:
            assert scoped.execute(
                "SELECT kineticloop.subject_scope_rls_allows("
                "%s,'authorization_issuances','SELECT',current_user::text)",
                (UUID(TEST_SUBJECT),),
            ).fetchone() == (False,)
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute("DROP SCHEMA kl017_legacy_probe CASCADE")

    with psycopg.connect(database_urls["test"]) as scoped:
        restored_lookup = scoped.execute(
            "SELECT kineticloop.subject_scope_lookup('S42',%s)",
            (UUID(TEST_AUTHORIZATION),),
        ).fetchone()
        assert restored_lookup is not None
        assert restored_lookup[0]["subject_id"] == TEST_SUBJECT


def test_subject_id_is_immutable_on_protected_updates(
    database_urls: dict[str, str],
) -> None:
    attempts = (
        ("daily_plan_heads", TEST_PLAN, TEST_SUBJECT_2),
        ("daily_plan_heads", TEST_PLAN, PRODUCTION_SUBJECT),
        ("replay_runs", EVALUATION_RUN, EVALUATION_SUBJECT_2),
        ("replay_runs", EVALUATION_RUN, PRODUCTION_SUBJECT),
    )
    with psycopg.connect(database_urls["admin"]) as admin:
        for table, object_id, replacement_subject in attempts:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_SUBJECT_IMMUTABLE",
            ):
                admin.execute(
                    f"UPDATE kineticloop.{table} SET subject_id=%s WHERE id=%s",
                    (UUID(replacement_subject), UUID(object_id)),
                )
            admin.rollback()
        assert admin.execute(
            "SELECT subject_id FROM kineticloop.daily_plan_heads WHERE id=%s",
            (UUID(TEST_PLAN),),
        ).fetchone() == (UUID(TEST_SUBJECT),)
        assert admin.execute(
            "SELECT subject_id FROM kineticloop.replay_runs WHERE id=%s",
            (UUID(EVALUATION_RUN),),
        ).fetchone() == (UUID(EVALUATION_SUBJECT),)


def test_shared_namespace_login_cannot_become_subject_principal(
    database_urls: dict[str, str],
) -> None:
    subject_id = UUID("00000000-0000-8000-8000-000000000252")
    with psycopg.connect(database_urls["trusted_admin"]) as trusted:
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="KL_SUBJECT_SCOPE_PRINCIPAL_INVALID",
        ):
            trusted.execute(
                "SELECT kineticloop.subject_scope_register("
                "%s,'PRODUCTION',NULL,NULL,'kl_application_login')",
                (subject_id,),
            )
        trusted.rollback()
    with psycopg.connect(database_urls["admin"]) as admin:
        assert admin.execute(
            "SELECT count(*) FROM kineticloop.subject_scopes WHERE subject_id=%s",
            (subject_id,),
        ).fetchone() == (0,)


def test_principal_with_protected_object_bypass_cannot_register(
    database_urls: dict[str, str],
) -> None:
    with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
        admin.execute(
            "GRANT SELECT ON kineticloop.authorization_issuances "
            "TO kl_test_subject_1_login"
        )
    try:
        with psycopg.connect(database_urls["trusted_admin"]) as trusted:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_SUBJECT_SCOPE_PRINCIPAL_INVALID",
            ):
                trusted.execute(
                    "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
                    (
                        UUID(TEST_SUBJECT),
                        UUID(TEST_POLICY),
                        UUID(TEST_ENVIRONMENT),
                        TEST_SUBJECT_LOGINS[0],
                    ),
                )
            trusted.rollback()
    finally:
        with psycopg.connect(database_urls["admin"], autocommit=True) as admin:
            admin.execute(
                "REVOKE SELECT ON kineticloop.authorization_issuances "
                "FROM kl_test_subject_1_login"
            )

    with psycopg.connect(database_urls["trusted_admin"]) as trusted:
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
            (
                UUID(TEST_SUBJECT),
                UUID(TEST_POLICY),
                UUID(TEST_ENVIRONMENT),
                TEST_SUBJECT_LOGINS[0],
            ),
        )


def test_subject_registration_serializes_with_first_storage_write(
    database_urls: dict[str, str],
) -> None:
    subject_id = UUID(EVALUATION_SUBJECT)
    environment_id = UUID(EVALUATION_ENVIRONMENT)
    with (
        psycopg.connect(database_urls["trusted_admin"]) as registering,
        psycopg.connect(database_urls["admin"]) as writing,
    ):
        registering.execute(
            "SELECT kineticloop.subject_scope_register(%s,'EVALUATION',NULL,%s,%s)",
            (subject_id, environment_id, EVALUATION_SUBJECT_LOGINS[0]),
        )
        writing.execute("SET LOCAL statement_timeout = '150ms'")
        with pytest.raises(psycopg.errors.QueryCanceled):
            writing.execute(
                "INSERT INTO kineticloop.replay_runs("
                "subject_id,replay_mode,input_selection_hash,knowledge_cutoff,status) "
                "VALUES (%s,'RECORDED_OUTPUT','blocked',clock_timestamp(),'PENDING')",
                (subject_id,),
            )
        writing.rollback()
        registering.rollback()


def test_populated_downgrade_fails_before_guard_or_acl_changes(
    database_urls: dict[str, str],
) -> None:
    def assert_failed_without_changes(urls: dict[str, str]) -> None:
        with pytest.raises(
            Exception, match="KL_SUBJECT_SCOPE_DOWNGRADE_SCOPED_STATE"
        ):
            run_alembic_downgrade(urls["deployer"], ARTIFACT_REGISTRY_REVISION)
        with psycopg.connect(urls["admin"]) as admin:
            assert admin.execute("SELECT version_num FROM alembic_version").fetchone() == (
                REVISION,
            )
            assert admin.execute(
                "SELECT count(*) FROM pg_trigger trigger "
                "JOIN pg_class relation ON relation.oid=trigger.tgrelid "
                "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
                "WHERE namespace.nspname='kineticloop' "
                "AND trigger.tgname='subject_storage_scope' "
                "AND NOT trigger.tgisinternal"
            ).fetchone() == (5,)
            assert admin.execute(
                "SELECT to_regprocedure("
                "'kineticloop.subject_scope_lookup(text,uuid)') IS NOT NULL"
            ).fetchone() == (True,)
            assert admin.execute(
                "SELECT has_table_privilege('kl_application',"
                "'kineticloop.authorization_issuances','SELECT')"
            ).fetchone() == (False,)

    # Non-production classifications and rows are never silently declassified.
    assert_failed_without_changes(database_urls)
    with psycopg.connect(database_urls["admin"]) as admin:
        assert admin.execute("SELECT version_num FROM alembic_version").fetchone() == (
            REVISION,
        )
        assert admin.execute(
            "SELECT count(*) FROM kineticloop.subject_scopes "
            "WHERE namespace IN ('TEST','EVALUATION')"
        ).fetchone() == (4,)
        assert admin.execute(
            "SELECT count(*) FROM kineticloop.subject_principal_bindings "
            "WHERE namespace IN ('TEST','EVALUATION')"
        ).fetchone() == (4,)
    with psycopg.connect(database_urls["test"]) as scoped:
        row = scoped.execute(
            "SELECT kineticloop.subject_scope_lookup('S42',%s)",
            (UUID(TEST_AUTHORIZATION),),
        ).fetchone()
        assert row is not None and row[0]["subject_id"] == TEST_SUBJECT

    # A production binding alone also prevents the SELECT grant from returning.
    urls = bootstrap_two_phase(DatabaseLifecycle(ROOT))
    production_only_subject = UUID("00000000-0000-8000-8000-000000000270")
    with psycopg.connect(urls["trusted_admin"]) as trusted:
        trusted.execute(
            "SELECT kineticloop.subject_scope_register("
            "%s,'PRODUCTION',NULL,NULL,%s)",
            (production_only_subject, PRODUCTION_SUBJECT_LOGIN),
        )
        trusted.commit()
    assert_failed_without_changes(urls)
    with psycopg.connect(urls["admin"]) as admin:
        assert admin.execute(
            "SELECT namespace FROM kineticloop.subject_scopes WHERE subject_id=%s",
            (production_only_subject,),
        ).fetchone() == ("PRODUCTION",)
        assert admin.execute(
            "SELECT subject_id FROM kineticloop.subject_principal_bindings "
            "WHERE principal_name=%s",
            (PRODUCTION_SUBJECT_LOGIN,),
        ).fetchone() == (production_only_subject,)

    # Deleting classification metadata cannot make retained production data safe.
    urls = bootstrap_two_phase(DatabaseLifecycle(ROOT))
    configure_seed_ids(
        subject_id=PRODUCTION_SUBJECT,
        authorization_id=PRODUCTION_AUTHORIZATION,
        policy_id=_SAFETY.POLICY_ID,
        start=0x560,
    )
    _SAFETY.seed(urls["admin"])
    with psycopg.connect(urls["trusted_admin"]) as trusted:
        trusted.execute(
            "SELECT kineticloop.subject_scope_register("
            "%s,'PRODUCTION',NULL,NULL,%s)",
            (UUID(PRODUCTION_SUBJECT), PRODUCTION_SUBJECT_LOGIN),
        )
        trusted.commit()
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        admin.execute("DELETE FROM kineticloop.subject_principal_bindings")
        admin.execute("DELETE FROM kineticloop.subject_scopes")
        assert admin.execute(
            "SELECT (SELECT count(*) FROM kineticloop.subject_scopes),"
            "(SELECT count(*) FROM kineticloop.subject_principal_bindings),"
            "(SELECT count(*) FROM kineticloop.authorization_issuances)"
        ).fetchone() == (0, 0, 1)
    assert_failed_without_changes(urls)
    with psycopg.connect(urls["admin"]) as admin:
        assert admin.execute(
            "SELECT count(*) FROM kineticloop.authorization_issuances"
        ).fetchone() == (1,)


def test_subject_scope_successor_is_cluster_role_ddl_free() -> None:
    spec = spec_from_file_location("kl017_subject_scope_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    statements: list[str] = []
    with patch.object(migration.op, "execute", side_effect=lambda sql: statements.append(str(sql))):
        migration.upgrade()
        migration.downgrade()
    emitted = "\n".join(statements)
    assert statements[0].strip().startswith("DO $preflight$")
    for pattern in (
        r"\bCREATE\s+(?:ROLE|USER)\b",
        r"\bALTER\s+(?:ROLE|USER)\b",
        r"\bDROP\s+(?:ROLE|USER)\b",
        r"\bREASSIGN\s+OWNED\b",
    ):
        assert re.search(pattern, emitted, flags=re.IGNORECASE) is None
