from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from kineticloop.contracts.artifacts import (
    ArtifactBindingKind,
    ArtifactRegistration,
    ArtifactValiditySpec,
)
from kineticloop.contracts.commands import RegisterArtifact, TransactionBoundary
from kineticloop.contracts.safety_registry import (
    RegistryDenialCode,
    RegistryDenied,
    revocation_payload_hash,
)
from kineticloop.db.lifecycle import DatabaseLifecycle
from kineticloop.identity import ActorRole
from kineticloop.persistence.artifact_registry import (
    ArtifactRegistryDenialCode,
    register_artifact,
)
from kineticloop.primitives import canonical_sha256

ROOT = Path(__file__).parents[2]

_MIGRATION_SPEC = spec_from_file_location("kl018_test_migrations", ROOT / "tests/db/test_migrations.py")
assert _MIGRATION_SPEC is not None and _MIGRATION_SPEC.loader is not None
_MIGRATIONS = module_from_spec(_MIGRATION_SPEC)
_MIGRATION_SPEC.loader.exec_module(_MIGRATIONS)
bootstrap_two_phase: Any = _MIGRATIONS.bootstrap_two_phase

_SAFETY_SPEC = spec_from_file_location("kl018_safety_support", ROOT / "tests/db/test_safety_registry.py")
assert _SAFETY_SPEC is not None and _SAFETY_SPEC.loader is not None
_SAFETY = module_from_spec(_SAFETY_SPEC)
_SAFETY_SPEC.loader.exec_module(_SAFETY)

NEW_ARTIFACT_ID = "00000000-0000-8000-8000-000000000101"
SECOND_ARTIFACT_ID = "00000000-0000-8000-8000-000000000102"
VALIDITY_NOW = datetime(2026, 9, 26, tzinfo=UTC)


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    lifecycle = DatabaseLifecycle(ROOT)
    yield bootstrap_two_phase(lifecycle)


@pytest.fixture
def db_urls(database_urls: dict[str, str]) -> dict[str, str]:
    _SAFETY.seed(database_urls["admin"])
    return database_urls


def connect(url: str, *, name: str = "kl018-test") -> psycopg.Connection[Any]:
    return psycopg.connect(url, application_name=name)


def validity_spec(*, closure_complete: bool = True) -> str:
    return json.dumps(
        {
            "binding_id": _SAFETY.RELEASE_ID,
            "binding_kind": "EVALUATION_RELEASE",
            "closure_complete": closure_complete,
            "timeless_approval_policy": None,
            "timeless_approval_reason": None,
            "valid_from": (VALIDITY_NOW - timedelta(days=1)).isoformat(),
            "valid_until": (VALIDITY_NOW + timedelta(days=30)).isoformat(),
            "validity_kind": "BOUNDED",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def timeless_validity_spec(
    policy_id: str = _SAFETY.ARTIFACT_ID,
    *,
    reason: str | None = "static release approved",
) -> str:
    return json.dumps(
        {
            "binding_id": _SAFETY.RELEASE_ID,
            "binding_kind": "EVALUATION_RELEASE",
            "closure_complete": True,
            "timeless_approval_policy": policy_id,
            "timeless_approval_reason": reason,
            "valid_from": (VALIDITY_NOW - timedelta(days=1)).isoformat(),
            "valid_until": None,
            "validity_kind": "TIMELESS",
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def registration_contract(
    *,
    artifact_id: str = NEW_ARTIFACT_ID,
    content_hash: str = "c" * 64,
    dependencies: tuple[str, ...] = (_SAFETY.ARTIFACT_ID, _SAFETY.DEPENDENCY_ID),
    identity: str = "planner-model",
    version: str = "1",
    binding_id: str = _SAFETY.RELEASE_ID,
) -> ArtifactRegistration:
    validity = ArtifactValiditySpec(
        validity_kind="BOUNDED",
        valid_from=VALIDITY_NOW - timedelta(days=1),
        valid_until=VALIDITY_NOW + timedelta(days=30),
        binding_kind=ArtifactBindingKind.EVALUATION_RELEASE,
        binding_id=binding_id,
    )
    command = RegisterArtifact.model_validate(
        {
            "schema_version": "kineticloop-command-v1",
            "command_kind": "RegisterArtifact",
            "boundary": TransactionBoundary.REGISTRY_MANAGEMENT,
            "command_id": "00000000-0000-8000-8000-000000000106",
            "actor": {
                "schema": "kineticloop-role-identity-v1",
                "identity_id": "00000000-0000-8000-8000-000000000107",
                "role": ActorRole.ADMIN,
            },
            "idempotency_key": f"register-{artifact_id}",
            "request_hash": canonical_sha256(
                {"artifact_id": artifact_id, "content_hash": content_hash}
            ),
            "subject_id": None,
            "explicit_scope": "global:safety-registry",
            "artifact_id": artifact_id,
            "artifact_kind": "MODEL",
            "content_hash": content_hash,
            "dependency_ids": dependencies,
            "validity_spec_hash": validity.sha256(),
        }
    )
    return ArtifactRegistration(
        command=command,
        artifact_identity=identity,
        artifact_version=version,
        validity=validity,
    )


def invoke_register(
    connection: psycopg.Connection[Any],
    *,
    artifact_id: str = NEW_ARTIFACT_ID,
    content_hash: str = "c" * 64,
    dependencies: tuple[str, ...] = (_SAFETY.ARTIFACT_ID, _SAFETY.DEPENDENCY_ID),
    spec: str | None = None,
    artifact_kind: str = "MODEL",
) -> tuple[Any, ...] | None:
    return connection.execute(
        "SELECT * FROM kineticloop.registry_register_artifact(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            UUID(artifact_id),
            artifact_kind,
            content_hash,
            [UUID(value) for value in dependencies],
            "planner-model",
            "1",
            spec or validity_spec(),
            5_000,
        ),
    ).fetchone()


def registration_counts(admin_url: str) -> tuple[int, int, int, int]:
    with connect(admin_url) as connection:
        row = connection.execute(
            "SELECT "
            "(SELECT count(*) FROM kineticloop.safety_artifacts WHERE id=%s),"
            "(SELECT count(*) FROM kineticloop.registry_artifact_receipts),"
            "(SELECT count(*) FROM kineticloop.artifact_registration_events),"
            "(SELECT count(*) FROM kineticloop.artifact_registration_outbox)",
            (UUID(NEW_ARTIFACT_ID),),
        ).fetchone()
        assert row is not None
        return tuple(int(value) for value in row)  # type: ignore[return-value]


def registry_snapshot(admin_url: str) -> tuple[Any, ...]:
    with connect(admin_url) as connection:
        row = connection.execute(
            "SELECT registry_revision,last_revocation_id,"
            "(SELECT count(*) FROM kineticloop.safety_artifacts),"
            "(SELECT count(*) FROM kineticloop.safety_artifact_dependencies),"
            "(SELECT count(*) FROM kineticloop.registry_artifact_receipts),"
            "(SELECT count(*) FROM kineticloop.artifact_registration_events),"
            "(SELECT count(*) FROM kineticloop.artifact_registration_outbox),"
            "(SELECT count(*) FROM kineticloop.registry_management_receipts),"
            "(SELECT count(*) FROM kineticloop.registry_audit_events),"
            "(SELECT count(*) FROM kineticloop.registry_outbox) "
            "FROM kineticloop.safety_registry_state WHERE id=1"
        ).fetchone()
        assert row is not None
        return tuple(row)


def closure_hash(*artifact_ids: str) -> str:
    return hashlib.sha256(",".join(sorted(artifact_ids)).encode()).hexdigest()


def test_artifact_identity_is_immutable(db_urls: dict[str, str]) -> None:
    with connect(db_urls["trusted_admin"]) as trusted:
        first = invoke_register(trusted)
        trusted.commit()
    assert first is not None and first[2] == "kl_trusted_admin_login" and first[3] is False

    with connect(db_urls["trusted_admin"]) as trusted:
        replay = invoke_register(trusted)
        trusted.commit()
    assert replay is not None and replay[:3] == first[:3] and replay[3] is True

    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_IMMUTABLE_ARTIFACT"):
            invoke_register(trusted, content_hash="d" * 64)
        trusted.rollback()
    with connect(db_urls["admin"]) as admin:
        with pytest.raises(psycopg.Error, match="KL_IMMUTABLE_HISTORY_MUTATION_REJECTED"):
            admin.execute(
                "UPDATE kineticloop.safety_artifacts SET content_hash=%s WHERE id=%s",
                ("e" * 64, UUID(NEW_ARTIFACT_ID)),
            )
        admin.rollback()
    assert registration_counts(db_urls["admin"]) == (1, 1, 1, 1)


def test_artifact_dependencies_must_be_pre_registered(db_urls: dict[str, str]) -> None:
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_ARTIFACT_UNKNOWN"):
            invoke_register(
                trusted,
                dependencies=(_SAFETY.ARTIFACT_ID, "00000000-0000-8000-8000-00000000ffff"),
            )
        trusted.rollback()
    assert registration_counts(db_urls["admin"]) == (0, 0, 0, 0)


def test_artifact_dependency_graph_is_acyclic(db_urls: dict[str, str]) -> None:
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(
            psycopg.errors.RaiseException, match="KL_REGISTRY_VALIDITY_UNDEFINED"
        ):
            invoke_register(trusted, dependencies=(NEW_ARTIFACT_ID,))
        trusted.rollback()

    with connect(db_urls["admin"]) as admin:
        admin.execute(
            "INSERT INTO kineticloop.safety_artifact_dependencies"
            "(artifact_id,dependency_artifact_id) VALUES (%s,%s)",
            (UUID(_SAFETY.DEPENDENCY_ID), UUID(_SAFETY.ARTIFACT_ID)),
        )
        admin.commit()
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(
            psycopg.errors.RaiseException, match="KL_REGISTRY_VALIDITY_UNDEFINED"
        ):
            invoke_register(trusted)
        trusted.rollback()
    assert registration_counts(db_urls["admin"]) == (0, 0, 0, 0)


def _insert_registered_artifacts(
    admin_url: str, artifact_ids: list[UUID], *, chained: bool
) -> None:
    now = datetime.now(UTC)
    with connect(admin_url) as admin:
        admin.cursor().executemany(
            "INSERT INTO kineticloop.safety_artifacts("
            "id,artifact_kind,artifact_identity,artifact_version,content_hash,"
            "validity_kind,valid_from,valid_until,ref_s48_id) "
            "VALUES (%s,'EVALUATION_RELEASE',%s,'1',%s,'BOUNDED',%s,%s,%s)",
            [
                (
                    artifact_id,
                    f"bound-{index}",
                    f"{index + 1000:064x}",
                    now - timedelta(days=1),
                    now + timedelta(days=30),
                    UUID(_SAFETY.RELEASE_ID),
                )
                for index, artifact_id in enumerate(artifact_ids)
            ],
        )
        if chained:
            admin.cursor().executemany(
                "INSERT INTO kineticloop.safety_artifact_dependencies"
                "(artifact_id,dependency_artifact_id) VALUES (%s,%s)",
                list(zip(artifact_ids[:-1], artifact_ids[1:], strict=True)),
            )
        admin.commit()


def test_artifact_dependency_closure_is_bounded(db_urls: dict[str, str]) -> None:
    deep_ids = [UUID(f"00000000-0000-8000-8000-{index:012x}") for index in range(0x200, 0x212)]
    _insert_registered_artifacts(db_urls["admin"], deep_ids, chained=True)
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_VALIDITY_UNDEFINED"):
            invoke_register(trusted, dependencies=tuple(str(value) for value in deep_ids))
        trusted.rollback()

    _SAFETY.seed(db_urls["admin"])
    wide_ids = [UUID(f"00000000-0000-8000-8000-{index:012x}") for index in range(0x300, 0x381)]
    _insert_registered_artifacts(db_urls["admin"], wide_ids, chained=False)
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_VALIDITY_UNDEFINED"):
            invoke_register(trusted, dependencies=tuple(str(value) for value in wide_ids))
        trusted.rollback()
    assert registration_counts(db_urls["admin"]) == (0, 0, 0, 0)


def test_artifact_registration_command_routine_privileges(db_urls: dict[str, str]) -> None:
    signature = (
        "kineticloop.registry_register_artifact("
        "uuid,text,text,uuid[],text,text,text,integer)"
    )
    with connect(db_urls["admin"]) as admin:
        rows = admin.execute(
            "SELECT p.oid::regprocedure::text, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='kineticloop' AND p.proname='registry_register_artifact'"
        ).fetchall()
        assert rows == [
            (
                signature.removeprefix("kineticloop."),
                "kl_writer_safety_registry",
                True,
                ["search_path=pg_catalog, kineticloop, pg_temp"],
            )
        ]
        for role in (
                "kl_application",
            "kl_auditor",
            "kl_user_login",
            "kl_agent_login",
        ):
            assert admin.execute(
                "SELECT has_function_privilege(%s,%s,'EXECUTE')", (role, signature)
            ).fetchone() == (False,)
        assert admin.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM pg_proc p, LATERAL aclexplode(p.proacl) acl "
            "WHERE p.oid=%s::regprocedure AND acl.grantee=0 AND acl.privilege_type='EXECUTE')",
            (signature,),
        ).fetchone() == (True,)
        assert admin.execute(
            "SELECT has_function_privilege('kl_trusted_admin',%s,'EXECUTE')", (signature,)
        ).fetchone() == (True,)


def test_artifact_registration_session_authority_enforced(db_urls: dict[str, str]) -> None:
    for url_key in ("user", "agent", "application", "auditor"):
        with connect(db_urls[url_key]) as runtime:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                invoke_register(runtime)
            runtime.rollback()
        assert registration_counts(db_urls["admin"]) == (0, 0, 0, 0)
        with connect(db_urls["admin"]) as admin:
            assert admin.execute(
                "SELECT registry_revision,last_revocation_id FROM "
                "kineticloop.safety_registry_state WHERE id=1"
            ).fetchone() == (0, None)

    with connect(db_urls["trusted_admin"]) as trusted:
        result = invoke_register(trusted)
        trusted.commit()
    assert result is not None and result[2] == "kl_trusted_admin_login"
    with connect(db_urls["admin"]) as admin:
        assert admin.execute(
            "SELECT operator_identity FROM kineticloop.registry_artifact_receipts "
            "WHERE artifact_id=%s", (UUID(NEW_ARTIFACT_ID),)
        ).fetchone() == ("kl_trusted_admin_login",)


def _wait_until_blocked(admin_url: str, application_name: str) -> None:
    deadline = time.monotonic() + 5
    with connect(admin_url) as observer:
        while time.monotonic() < deadline:
            row = observer.execute(
                "SELECT cardinality(pg_blocking_pids(pid)) FROM pg_stat_activity "
                "WHERE application_name=%s AND state<>'idle'", (application_name,)
            ).fetchone()
            observer.rollback()
            if row is not None and row[0] > 0:
                return
            time.sleep(0.02)
    raise AssertionError("shared registry command did not block behind registration")


def test_artifact_registration_uses_exclusive_registry_gate(db_urls: dict[str, str]) -> None:
    blocker = connect(db_urls["trusted_admin"], name="register-exclusive")
    assert invoke_register(blocker) is not None
    assert registration_counts(db_urls["admin"]) == (0, 0, 0, 0)

    with connect(db_urls["admin"]) as observer:
        observer.execute("SET LOCAL lock_timeout='100ms'")
        assert observer.execute(
            "SELECT subject_id FROM kineticloop.user_decision_state "
            "WHERE subject_id=%s FOR UPDATE", (UUID(_SAFETY.SUBJECT_ID),)
        ).fetchone() == (UUID(_SAFETY.SUBJECT_ID),)
        observer.rollback()

    outcome: dict[str, object] = {}

    def shared_worker() -> None:
        try:
            with connect(db_urls["application"], name="shared-behind-register") as application:
                application.execute(
                    "SELECT kineticloop.registry_guard_publish_manifest(%s,%s,0,5000)",
                    (
                        UUID(_SAFETY.SUBJECT_ID),
                        [UUID(_SAFETY.ARTIFACT_ID), UUID(_SAFETY.DEPENDENCY_ID)],
                    ),
                ).fetchone()
                application.commit()
                outcome["ok"] = True
        except BaseException as error:
            outcome["error"] = error

    worker = threading.Thread(target=shared_worker)
    worker.start()
    _wait_until_blocked(db_urls["admin"], "shared-behind-register")
    blocker.commit()
    blocker.close()
    worker.join(timeout=5)
    assert not worker.is_alive() and outcome == {"ok": True}
    assert registration_counts(db_urls["admin"]) == (1, 1, 1, 1)


def test_artifact_registration_direct_write_rejected(db_urls: dict[str, str]) -> None:
    for url_key in ("user", "agent", "application", "auditor", "trusted_admin"):
        with connect(db_urls[url_key]) as runtime:
            statements = (
                "UPDATE kineticloop.safety_registry_state SET registry_revision=99 WHERE id=1",
                "INSERT INTO kineticloop.safety_artifacts("
                "id,artifact_kind,artifact_identity,artifact_version,content_hash,"
                "validity_kind,valid_from,valid_until,ref_s48_id) VALUES ("
                f"'{NEW_ARTIFACT_ID}','MODEL','forged','1','{'f' * 64}',"
                f"'BOUNDED',clock_timestamp(),clock_timestamp()+interval '1 day','{_SAFETY.RELEASE_ID}')",
                "SET ROLE kl_writer_safety_registry",
            )
            for statement in statements:
                with pytest.raises(psycopg.Error):
                    runtime.execute(statement)
                runtime.rollback()
    assert registration_counts(db_urls["admin"]) == (0, 0, 0, 0)

    with connect(db_urls["trusted_admin"]) as trusted:
        assert invoke_register(trusted) is not None
        trusted.commit()
    assert registration_counts(db_urls["admin"]) == (1, 1, 1, 1)


def test_unregistered_or_revoked_artifact_denied(db_urls: dict[str, str]) -> None:
    with connect(db_urls["application"]) as application:
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_ARTIFACT_UNKNOWN"):
            application.execute(
                "SELECT kineticloop.registry_guard_publish_manifest(%s,%s,0,1000)",
                (UUID(_SAFETY.SUBJECT_ID), [UUID(NEW_ARTIFACT_ID)]),
            )
        application.rollback()

    with connect(db_urls["trusted_admin"]) as trusted:
        assert _SAFETY.invoke_revoke_sql(trusted, key="kl018-revoke") is not None
        trusted.commit()
    with connect(db_urls["application"]) as application:
        with pytest.raises(psycopg.errors.RaiseException, match="KL_REGISTRY_ARTIFACT_REVOKED"):
            application.execute(
                "SELECT kineticloop.registry_guard_publish_manifest(%s,%s,0,1000)",
                (
                    UUID(_SAFETY.SUBJECT_ID),
                    [UUID(_SAFETY.ARTIFACT_ID), UUID(_SAFETY.DEPENDENCY_ID)],
                ),
            )
        application.rollback()


def test_artifact_validity_is_null_total(db_urls: dict[str, str]) -> None:
    base = json.loads(validity_spec())
    malformed_specs: list[dict[str, object]] = []
    for key in (
        "validity_kind",
        "valid_from",
        "binding_kind",
        "binding_id",
        "closure_complete",
    ):
        missing = dict(base)
        missing.pop(key)
        malformed_specs.append(missing)
        explicit_null = dict(base)
        explicit_null[key] = None
        malformed_specs.append(explicit_null)
    for key in ("validity_kind", "valid_from", "binding_kind", "binding_id"):
        blank = dict(base)
        blank[key] = ""
        malformed_specs.append(blank)
    missing_until = dict(base)
    missing_until["valid_until"] = None
    malformed_specs.append(missing_until)
    non_increasing = dict(base)
    non_increasing["valid_until"] = non_increasing["valid_from"]
    malformed_specs.append(non_increasing)
    for policy, reason in ((None, "reason"), (_SAFETY.ARTIFACT_ID, None), ("", "reason"), (_SAFETY.ARTIFACT_ID, "")):
        timeless = json.loads(timeless_validity_spec())
        timeless["timeless_approval_policy"] = policy
        timeless["timeless_approval_reason"] = reason
        malformed_specs.append(timeless)

    initial = registry_snapshot(db_urls["admin"])
    for malformed in malformed_specs:
        with connect(db_urls["trusted_admin"]) as trusted:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_REGISTRY_VALIDITY_UNDEFINED",
            ):
                invoke_register(trusted, spec=json.dumps(malformed))
            trusted.rollback()
        assert registry_snapshot(db_urls["admin"]) == initial

    with connect(db_urls["admin"]) as admin:
        definition = admin.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='ck_s49_validity_spec'"
        ).fetchone()
        assert definition is not None and "IS TRUE" in definition[0]

    with connect(db_urls["trusted_admin"]) as trusted:
        assert invoke_register(trusted) is not None
        trusted.commit()
    _SAFETY.seed(db_urls["admin"])
    with connect(db_urls["trusted_admin"]) as trusted:
        assert invoke_register(trusted, spec=timeless_validity_spec()) is not None
        trusted.commit()


def test_artifact_timeless_policy_is_registered_dependency(
    db_urls: dict[str, str],
) -> None:
    cases = (
        (
            timeless_validity_spec("not-a-uuid"),
            (_SAFETY.ARTIFACT_ID, _SAFETY.DEPENDENCY_ID),
            "KL_REGISTRY_VALIDITY_UNDEFINED",
        ),
        (
            timeless_validity_spec("00000000-0000-8000-8000-00000000ffff"),
            (_SAFETY.ARTIFACT_ID, _SAFETY.DEPENDENCY_ID),
            "KL_REGISTRY_ARTIFACT_UNKNOWN",
        ),
        (
            timeless_validity_spec(),
            (_SAFETY.DEPENDENCY_ID,),
            "KL_REGISTRY_VALIDITY_UNDEFINED",
        ),
        (
            timeless_validity_spec(_SAFETY.DEPENDENCY_ID),
            (_SAFETY.ARTIFACT_ID, _SAFETY.DEPENDENCY_ID),
            "KL_REGISTRY_VALIDITY_UNDEFINED",
        ),
    )
    initial = registry_snapshot(db_urls["admin"])
    for spec, dependencies, marker in cases:
        with connect(db_urls["trusted_admin"]) as trusted:
            with pytest.raises(psycopg.errors.RaiseException, match=marker):
                invoke_register(trusted, dependencies=dependencies, spec=spec)
            trusted.rollback()
        assert registry_snapshot(db_urls["admin"]) == initial

    with connect(db_urls["trusted_admin"]) as trusted:
        assert invoke_register(trusted, spec=timeless_validity_spec()) is not None
        trusted.commit()
        with connect(db_urls["admin"]) as admin:
            admin.execute("SET LOCAL session_replication_role=replica")
            admin.execute(
                "UPDATE kineticloop.decision_manifests "
                "SET ref_s49_id=%s,dependency_closure_hash=%s WHERE id=%s",
                (
                    UUID(NEW_ARTIFACT_ID),
                    closure_hash(
                        NEW_ARTIFACT_ID,
                        _SAFETY.ARTIFACT_ID,
                        _SAFETY.DEPENDENCY_ID,
                    ),
                    UUID(_SAFETY.MANIFEST_ID),
                ),
            )
            admin.commit()
        revoke_at = datetime.now(UTC)
        assert trusted.execute(
            "SELECT * FROM kineticloop.registry_revoke_artifact("
            "%s,%s,%s,%s,%s,%s,%s,%s,5000)",
            (
                UUID(_SAFETY.ARTIFACT_ID),
                _SAFETY.CONTENT_HASH,
                revoke_at,
                "TIMELESS_POLICY_REVOKED",
                revocation_payload_hash(
                    effective_at=revoke_at,
                    reason_code="TIMELESS_POLICY_REVOKED",
                ),
                "kl018-timeless-policy-revoke",
                "e" * 64,
                UUID(_SAFETY.INCIDENT_ID),
            ),
        ).fetchone() is not None
        trusted.commit()

    before_denials = registry_snapshot(db_urls["admin"])
    artifact_closure = [
        UUID(NEW_ARTIFACT_ID),
        UUID(_SAFETY.ARTIFACT_ID),
        UUID(_SAFETY.DEPENDENCY_ID),
    ]
    with connect(db_urls["application"]) as application:
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="KL_REGISTRY_DEPENDENCY_INCOMPLETE",
        ):
            application.execute(
                "SELECT kineticloop.registry_guard_publish_manifest(%s,%s,0,1000)",
                (
                    UUID(_SAFETY.SUBJECT_ID),
                    [UUID(_SAFETY.DEPENDENCY_ID)],
                ),
            )
        application.rollback()
    assert registry_snapshot(db_urls["admin"]) == before_denials

    for routine in (
        "registry_guard_publish_manifest",
        "registry_guard_commit_bundle",
        "registry_guard_reauthorize",
        "registry_guard_start_session",
        "registry_guard_resume_session",
        "registry_guard_continue_session",
    ):
        with connect(db_urls["application"]) as application:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_REGISTRY_ARTIFACT_REVOKED",
            ):
                application.execute(
                    f"SELECT kineticloop.{routine}(%s,%s,0,1000)",
                    (UUID(_SAFETY.SUBJECT_ID), artifact_closure),
                )
            application.rollback()
        assert registry_snapshot(db_urls["admin"]) == before_denials


def test_artifact_repository_maps_immutable_and_natural_identity_conflicts(
    db_urls: dict[str, str],
) -> None:
    with connect(db_urls["trusted_admin"]) as trusted:
        first = register_artifact(trusted, registration_contract())
    assert first.replayed is False
    expected = registry_snapshot(db_urls["admin"])

    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(RegistryDenied) as immutable:
            register_artifact(
                trusted,
                registration_contract(content_hash="d" * 64),
            )
    assert immutable.value.code is ArtifactRegistryDenialCode.IMMUTABLE_ARTIFACT
    assert registry_snapshot(db_urls["admin"]) == expected

    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(RegistryDenied) as natural_conflict:
            register_artifact(
                trusted,
                registration_contract(
                    artifact_id=SECOND_ARTIFACT_ID,
                    content_hash="e" * 64,
                ),
            )
    assert natural_conflict.value.code is ArtifactRegistryDenialCode.IMMUTABLE_ARTIFACT
    assert registry_snapshot(db_urls["admin"]) == expected


def test_artifact_repository_normalizes_public_input_denials(
    db_urls: dict[str, str],
) -> None:
    initial = registry_snapshot(db_urls["admin"])
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(RegistryDenied) as unknown_root:
            register_artifact(
                trusted,
                registration_contract(
                    binding_id="00000000-0000-8000-8000-00000000ffff"
                ),
            )
    assert unknown_root.value.code is RegistryDenialCode.ARTIFACT_UNKNOWN
    assert registry_snapshot(db_urls["admin"]) == initial

    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(RegistryDenied) as incomplete:
            register_artifact(
                trusted,
                registration_contract(dependencies=(_SAFETY.ARTIFACT_ID,)),
            )
    assert incomplete.value.code is RegistryDenialCode.VALIDITY_UNDEFINED
    assert registry_snapshot(db_urls["admin"]) == initial

    with connect(db_urls["admin"]) as admin:
        admin.execute(
            "INSERT INTO kineticloop.safety_artifact_dependencies"
            "(artifact_id,dependency_artifact_id) VALUES (%s,%s)",
            (UUID(_SAFETY.DEPENDENCY_ID), UUID(_SAFETY.ARTIFACT_ID)),
        )
        admin.commit()
    cycle_state = registry_snapshot(db_urls["admin"])
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(RegistryDenied) as cycle:
            register_artifact(trusted, registration_contract())
    assert cycle.value.code is RegistryDenialCode.VALIDITY_UNDEFINED
    assert registry_snapshot(db_urls["admin"]) == cycle_state

    _SAFETY.seed(db_urls["admin"])
    direct_state = registry_snapshot(db_urls["admin"])
    direct_cases: tuple[tuple[tuple[str, ...], str], ...] = (
        ((NEW_ARTIFACT_ID,), "MODEL"),
        ((_SAFETY.ARTIFACT_ID, _SAFETY.ARTIFACT_ID), "MODEL"),
        ((_SAFETY.ARTIFACT_ID, _SAFETY.DEPENDENCY_ID), "POLICY"),
    )
    for dependencies, artifact_kind in direct_cases:
        with connect(db_urls["trusted_admin"]) as trusted:
            with pytest.raises(
                psycopg.errors.RaiseException,
                match="KL_REGISTRY_VALIDITY_UNDEFINED",
            ):
                invoke_register(
                    trusted,
                    dependencies=dependencies,
                    artifact_kind=artifact_kind,
                )
            trusted.rollback()
        assert registry_snapshot(db_urls["admin"]) == direct_state


def test_artifact_dependency_dense_graph_is_bounded(db_urls: dict[str, str]) -> None:
    dense_ids = [
        UUID(f"00000000-0000-8000-8001-{index:012x}") for index in range(128)
    ]
    _insert_registered_artifacts(db_urls["admin"], dense_ids, chained=False)
    levels = [dense_ids[index : index + 8] for index in range(0, 128, 8)]
    edges = [
        (parent, child)
        for left, right in zip(levels[:-1], levels[1:], strict=True)
        for parent in left
        for child in right
    ]
    with connect(db_urls["admin"]) as admin:
        admin.cursor().executemany(
            "INSERT INTO kineticloop.safety_artifact_dependencies"
            "(artifact_id,dependency_artifact_id) VALUES (%s,%s)",
            edges,
        )
        admin.commit()
    with connect(db_urls["trusted_admin"]) as trusted:
        trusted.execute("SET statement_timeout='2s'")
        assert invoke_register(
            trusted,
            dependencies=tuple(str(value) for value in dense_ids),
        ) is not None
        trusted.commit()

    _SAFETY.seed(db_urls["admin"])
    wide_ids = [
        UUID(f"00000000-0000-8000-8002-{index:012x}") for index in range(129)
    ]
    _insert_registered_artifacts(db_urls["admin"], wide_ids, chained=False)
    initial = registry_snapshot(db_urls["admin"])
    with connect(db_urls["trusted_admin"]) as trusted:
        trusted.execute("SET statement_timeout='2s'")
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="KL_REGISTRY_VALIDITY_UNDEFINED",
        ):
            invoke_register(
                trusted,
                dependencies=tuple(str(value) for value in wide_ids),
            )
        trusted.rollback()
    assert registry_snapshot(db_urls["admin"]) == initial


def test_artifact_registration_lock_timeout_is_atomic(
    db_urls: dict[str, str],
) -> None:
    initial = registry_snapshot(db_urls["admin"])
    blocker = connect(db_urls["admin"], name="kl018-held-exclusive-gate")
    blocker.execute(
        "SELECT registry_revision FROM kineticloop.safety_registry_state "
        "WHERE id=1 FOR UPDATE"
    )
    try:
        with connect(db_urls["trusted_admin"]) as trusted:
            with pytest.raises(RegistryDenied) as denial:
                register_artifact(
                    trusted,
                    registration_contract(),
                    lock_timeout_ms=100,
                )
        assert denial.value.code is RegistryDenialCode.REGISTRY_TIMEOUT
    finally:
        blocker.rollback()
        blocker.close()
    assert registry_snapshot(db_urls["admin"]) == initial


def test_artifact_registration_post_write_failure_is_atomic(
    db_urls: dict[str, str],
) -> None:
    with connect(db_urls["admin"]) as admin:
        admin.execute(
            "CREATE OR REPLACE FUNCTION public.kl018_fail_after_s49() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'KL018_TEST_FAILURE_AFTER_S49'; END $$"
        )
        admin.execute(
            "CREATE TRIGGER kl018_injected_failure BEFORE INSERT ON "
            "kineticloop.registry_artifact_receipts FOR EACH ROW "
            "EXECUTE FUNCTION public.kl018_fail_after_s49()"
        )
        admin.commit()
    initial = registry_snapshot(db_urls["admin"])
    with connect(db_urls["trusted_admin"]) as trusted:
        with pytest.raises(psycopg.Error, match="KL018_TEST_FAILURE_AFTER_S49"):
            register_artifact(trusted, registration_contract())
    assert registry_snapshot(db_urls["admin"]) == initial
