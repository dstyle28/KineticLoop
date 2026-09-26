from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

import psycopg
import pytest

from kineticloop.db.lifecycle import DatabaseLifecycle
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.subject_scope import (
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

_SAFETY_SPEC = spec_from_file_location(
    "kl017_safety_seed", ROOT / "tests/db/test_safety_registry.py"
)
assert _SAFETY_SPEC is not None and _SAFETY_SPEC.loader is not None
_SAFETY: Any = module_from_spec(_SAFETY_SPEC)
_SAFETY_SPEC.loader.exec_module(_SAFETY)

PRODUCTION_SUBJECT = _SAFETY.SUBJECT_ID
TEST_SUBJECT = "00000000-0000-8000-8000-000000000202"
EVALUATION_SUBJECT = "00000000-0000-8000-8000-000000000203"
UNKNOWN_SUBJECT = "00000000-0000-8000-8000-000000000204"
PRODUCTION_AUTHORIZATION = _SAFETY.AUTHORIZATION_ID
TEST_AUTHORIZATION = "00000000-0000-8000-8000-000000000212"
EVALUATION_RUN = "00000000-0000-8000-8000-000000000213"
EVALUATION_ARTIFACT = "00000000-0000-8000-8000-000000000214"
TEST_POLICY = "00000000-0000-8000-8000-000000000215"
OTHER_TEST_POLICY = "00000000-0000-8000-8000-000000000216"
TEST_ENVIRONMENT = "00000000-0000-8000-8000-000000000217"
EVALUATION_ENVIRONMENT = "00000000-0000-8000-8000-000000000218"
EVALUATION_MANIFEST = "00000000-0000-8000-8000-000000000231"
EVALUATION_RELEASE = "00000000-0000-8000-8000-000000000232"


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
            "(%s,%s,'test:isolated','1','test-policy'),(%s,%s,'test:other','1','other-policy')",
            (UUID(TEST_POLICY), UUID(TEST_SUBJECT), UUID(OTHER_TEST_POLICY), UUID(TEST_SUBJECT)),
        )
    with psycopg.connect(urls["trusted_admin"], autocommit=True) as trusted:
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s)",
            (UUID(TEST_SUBJECT), UUID(TEST_POLICY), UUID(TEST_ENVIRONMENT)),
        )
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,'EVALUATION',NULL,%s)",
            (UUID(EVALUATION_SUBJECT), UUID(EVALUATION_ENVIRONMENT)),
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


def test_subject_namespace_isolation(database_urls: dict[str, str]) -> None:
    for url_key, namespace in (("test", "TEST"), ("evaluation", "EVALUATION")):
        with psycopg.connect(database_urls[url_key]) as scoped:
            assert scoped.execute(
                "SELECT kineticloop.subject_scope_lookup(%s,%s,'S42',%s)",
                (namespace, UUID(PRODUCTION_SUBJECT), UUID(PRODUCTION_AUTHORIZATION)),
            ).fetchone() == (None,)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                scoped.execute("SELECT id FROM kineticloop.authorization_issuances")
            scoped.rollback()


def test_cross_subject_denial_is_non_enumerating(database_urls: dict[str, str]) -> None:
    denials = []
    for url_key, namespace, role, actor_subject in (
        ("test", "TEST", ActorRole.TEST, TEST_SUBJECT),
        ("evaluation", "EVALUATION", ActorRole.EVALUATION, EVALUATION_SUBJECT),
    ):
        actor = RoleIdentity(
            identity_id="00000000-0000-8000-8000-000000000220", role=role
        )
        with psycopg.connect(database_urls[url_key]) as scoped:
            database_results = [
                scoped.execute(
                    "SELECT kineticloop.subject_scope_lookup(%s,%s,'S42',%s)",
                    (namespace, UUID(subject_id), UUID(object_id)),
                ).fetchone()
                for subject_id, object_id in (
                    (PRODUCTION_SUBJECT, PRODUCTION_AUTHORIZATION),
                    (UNKNOWN_SUBJECT, "00000000-0000-8000-8000-000000000299"),
                )
            ]
            assert database_results == [(None,), (None,)]
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
    for forbidden in (PRODUCTION_SUBJECT, PRODUCTION_AUTHORIZATION, "prod-content", "PRODUCTION"):
        assert forbidden not in serialized


def test_test_authorization_is_isolated(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["test"]) as scoped:
        row = scoped.execute(
            "SELECT kineticloop.subject_scope_lookup('TEST',%s,'S42',%s)",
            (UUID(TEST_SUBJECT), UUID(TEST_AUTHORIZATION)),
        ).fetchone()
        assert row is not None and row[0]["subject_id"] == TEST_SUBJECT
    with psycopg.connect(database_urls["application"]) as production:
        assert production.execute(
            "SELECT kineticloop.subject_scope_lookup('PRODUCTION',%s,'S42',%s)",
            (UUID(TEST_SUBJECT), UUID(TEST_AUTHORIZATION)),
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
            "SELECT kineticloop.subject_scope_lookup('EVALUATION',%s,'S47',%s)",
            (UUID(EVALUATION_SUBJECT), UUID(EVALUATION_ARTIFACT)),
        ).fetchone()
        assert row is not None and row[0]["kind"] == "S47"
    with psycopg.connect(database_urls["application"]) as production:
        assert production.execute(
            "SELECT kineticloop.subject_scope_lookup('PRODUCTION',%s,'S47',%s)",
            (UUID(EVALUATION_SUBJECT), UUID(EVALUATION_ARTIFACT)),
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
        ("application", ActorRole.SUBJECT, PRODUCTION_SUBJECT, PRODUCTION_AUTHORIZATION),
        ("test", ActorRole.TEST, TEST_SUBJECT, TEST_AUTHORIZATION),
        (
            "evaluation",
            ActorRole.EVALUATION,
            EVALUATION_SUBJECT,
            EVALUATION_ARTIFACT,
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


def test_subject_registration_serializes_with_first_storage_write(
    database_urls: dict[str, str],
) -> None:
    subject_id = UUID("00000000-0000-8000-8000-000000000250")
    environment_id = UUID("00000000-0000-8000-8000-000000000251")
    with (
        psycopg.connect(database_urls["trusted_admin"]) as registering,
        psycopg.connect(database_urls["admin"]) as writing,
    ):
        registering.execute(
            "SELECT kineticloop.subject_scope_register(%s,'EVALUATION',NULL,%s)",
            (subject_id, environment_id),
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
