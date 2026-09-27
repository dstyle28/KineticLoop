"""Application boundary for production, test, and evaluation subject storage."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Mapping
from uuid import UUID

import psycopg
from psycopg import Connection

from kineticloop.identity import ActorRole, RoleIdentity

TEST_DATABASE_ROLE: Final = "kl_subject_test"
EVALUATION_DATABASE_ROLE: Final = "kl_subject_evaluation"
SUBJECT_SCOPE_DATABASE_ROLES: Final = frozenset(
    {TEST_DATABASE_ROLE, EVALUATION_DATABASE_ROLE}
)
PRODUCTION_SUBJECT_LOGIN: Final = "kl_production_subject_1_login"
TEST_SUBJECT_LOGINS: Final = (
    "kl_test_subject_1_login",
    "kl_test_subject_2_login",
)
EVALUATION_SUBJECT_LOGINS: Final = (
    "kl_evaluation_subject_1_login",
    "kl_evaluation_subject_2_login",
)
SUBJECT_SCOPE_LOGIN_ROLES: Final = frozenset(
    {PRODUCTION_SUBJECT_LOGIN, *TEST_SUBJECT_LOGINS, *EVALUATION_SUBJECT_LOGINS}
)


class SubjectNamespace(StrEnum):
    PRODUCTION = "PRODUCTION"
    TEST = "TEST"
    EVALUATION = "EVALUATION"


class ScopedObjectKind(StrEnum):
    DAILY_PLAN_HEAD = "S38"
    AUTHORIZATION_ISSUANCE = "S42"
    EXECUTION_BINDING = "S45"
    REPLAY_RUN = "S46"
    REPLAY_ARTIFACT = "S47"


ROLE_NAMESPACE: Final[Mapping[ActorRole, SubjectNamespace]] = MappingProxyType(
    {
        ActorRole.SUBJECT: SubjectNamespace.PRODUCTION,
        ActorRole.ADMIN: SubjectNamespace.PRODUCTION,
        ActorRole.TEST: SubjectNamespace.TEST,
        ActorRole.EVALUATION: SubjectNamespace.EVALUATION,
    }
)

NAMESPACE_OBJECT_KINDS: Final[Mapping[SubjectNamespace, frozenset[ScopedObjectKind]]] = (
    MappingProxyType(
        {
            SubjectNamespace.PRODUCTION: frozenset(
                {
                    ScopedObjectKind.DAILY_PLAN_HEAD,
                    ScopedObjectKind.AUTHORIZATION_ISSUANCE,
                    ScopedObjectKind.EXECUTION_BINDING,
                }
            ),
            SubjectNamespace.TEST: frozenset(
                {
                    ScopedObjectKind.DAILY_PLAN_HEAD,
                    ScopedObjectKind.AUTHORIZATION_ISSUANCE,
                    ScopedObjectKind.EXECUTION_BINDING,
                }
            ),
            SubjectNamespace.EVALUATION: frozenset(
                {ScopedObjectKind.REPLAY_RUN, ScopedObjectKind.REPLAY_ARTIFACT}
            ),
        }
    )
)


@dataclass(frozen=True, slots=True)
class SubjectScopeDenial:
    """Stable non-enumerating response shared by every denied target."""

    code: str = "SUBJECT_SCOPE_DENIED"
    timing_class: str = "BOUNDED_SCOPE_LOOKUP"
    payload: Mapping[str, str] = MappingProxyType({"error": "subject_scope_denied"})


class SubjectScopeDenied(PermissionError):
    def __init__(self) -> None:
        self.denial = SubjectScopeDenial()
        super().__init__(self.denial.code)


@dataclass(frozen=True, slots=True)
class ScopedObject:
    kind: ScopedObjectKind
    object_id: str
    subject_id: str
    namespace: SubjectNamespace


def namespace_for_actor(actor: RoleIdentity) -> SubjectNamespace:
    if type(actor) is not RoleIdentity:
        raise TypeError("actor must be an exact RoleIdentity")
    return ROLE_NAMESPACE[actor.role]


def _canonical_uuid(value: str, field: str) -> UUID:
    if type(value) is not str:
        raise TypeError(f"{field} must be a UUID string")
    try:
        return UUID(value)
    except ValueError as error:
        raise ValueError(f"{field} must be a UUID string") from error


def read_scoped_object(
    connection: Connection[Any],
    *,
    actor: RoleIdentity,
    actor_subject_id: str,
    target_subject_id: str,
    object_kind: ScopedObjectKind,
    object_id: str,
) -> ScopedObject:
    """Read one object through both the application and database scope guards.

    All application denials use one response. The database routine independently
    derives its namespace from ``session_user`` and returns NULL for missing and
    out-of-scope targets, so row existence is never disclosed at this boundary.
    """

    if type(object_kind) is not ScopedObjectKind:
        raise TypeError("object_kind must be a ScopedObjectKind")
    namespace = namespace_for_actor(actor)
    actor_subject = _canonical_uuid(actor_subject_id, "actor_subject_id")
    target_subject = _canonical_uuid(target_subject_id, "target_subject_id")
    target_object = _canonical_uuid(object_id, "object_id")
    if actor_subject != target_subject or object_kind not in NAMESPACE_OBJECT_KINDS[namespace]:
        raise SubjectScopeDenied

    try:
        row = connection.execute(
            "SELECT kineticloop.subject_scope_lookup(%s,%s)",
            (object_kind.value, target_object),
        ).fetchone()
    except psycopg.Error as error:
        if "KL_SUBJECT_SCOPE_ROLE_DENIED" in str(error):
            raise SubjectScopeDenied from error
        raise
    if row is None or row[0] is None:
        raise SubjectScopeDenied
    payload = row[0]
    try:
        returned_kind = ScopedObjectKind(payload["kind"])
        returned_object = _canonical_uuid(payload["object_id"], "returned object_id")
        returned_subject = _canonical_uuid(payload["subject_id"], "returned subject_id")
        returned_namespace = SubjectNamespace(payload["namespace"])
    except (KeyError, TypeError, ValueError) as error:
        raise SubjectScopeDenied from error
    if (
        returned_kind is not object_kind
        or returned_object != target_object
        or returned_subject != actor_subject
        or returned_subject != target_subject
        or returned_namespace is not namespace
    ):
        raise SubjectScopeDenied
    return ScopedObject(
        kind=returned_kind,
        object_id=str(returned_object),
        subject_id=str(returned_subject),
        namespace=returned_namespace,
    )
