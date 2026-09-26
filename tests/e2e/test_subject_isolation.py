from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from kineticloop.db.lifecycle import DatabaseLifecycle
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.subject_scope import (
    TEST_SUBJECT_LOGINS,
    ScopedObjectKind,
    SubjectScopeDenied,
    read_scoped_object,
)

ROOT = Path(__file__).parents[2]
_SPEC = spec_from_file_location("kl017_e2e_migrations", ROOT / "tests/db/test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_MIGRATIONS = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATIONS)
bootstrap_two_phase: Any = _MIGRATIONS.bootstrap_two_phase

_SAFETY_SPEC = spec_from_file_location(
    "kl017_e2e_safety_seed", ROOT / "tests/db/test_safety_registry.py"
)
assert _SAFETY_SPEC is not None and _SAFETY_SPEC.loader is not None
_SAFETY = module_from_spec(_SAFETY_SPEC)
_SAFETY_SPEC.loader.exec_module(_SAFETY)


def test_test_actor_cannot_observe_production_authorization_end_to_end() -> None:
    urls = bootstrap_two_phase(DatabaseLifecycle(ROOT))
    _SAFETY.seed(urls["admin"])
    production_subject = UUID(_SAFETY.SUBJECT_ID)
    authorization_id = UUID(_SAFETY.AUTHORIZATION_ID)
    test_subject = "00000000-0000-8000-8000-000000000303"
    policy_id = UUID("00000000-0000-8000-8000-000000000304")
    environment_id = UUID("00000000-0000-8000-8000-000000000305")
    with psycopg.connect(urls["admin"], autocommit=True) as admin:
        admin.execute(
            "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash) "
            "VALUES (%s,%s,'test:e2e','1','test-policy')",
            (policy_id, UUID(test_subject)),
        )
    with psycopg.connect(urls["trusted_admin"], autocommit=True) as trusted:
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
            (UUID(test_subject), policy_id, environment_id, TEST_SUBJECT_LOGINS[0]),
        )

    actor = RoleIdentity(
        identity_id="00000000-0000-8000-8000-000000000306", role=ActorRole.TEST
    )
    denials = []
    with psycopg.connect(urls["test"]) as scoped:
        assert [
            scoped.execute(
                "SELECT kineticloop.subject_scope_lookup('S42',%s)",
                (object_id,),
            ).fetchone()
            for object_id in (
                authorization_id,
                UUID("00000000-0000-8000-8000-000000000308"),
            )
        ] == [(None,), (None,)]
        for subject_id, object_id in (
            (str(production_subject), str(authorization_id)),
            (
                "00000000-0000-8000-8000-000000000307",
                "00000000-0000-8000-8000-000000000308",
            ),
        ):
            try:
                read_scoped_object(
                    scoped,
                    actor=actor,
                    actor_subject_id=test_subject,
                    target_subject_id=subject_id,
                    object_kind=ScopedObjectKind.AUTHORIZATION_ISSUANCE,
                    object_id=object_id,
                )
            except SubjectScopeDenied as error:
                denials.append(error.denial)
    assert len(denials) == 2
    assert denials[0] == denials[1]
    assert dict(denials[0].payload) == {"error": "subject_scope_denied"}
