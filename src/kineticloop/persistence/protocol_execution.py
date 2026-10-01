"""Internal typed TEST adapters over the existing T3/T6/T7 transaction owners."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg import Error as PsycopgError
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.contracts.commands import (
    CommitBundle,
    ContinueSession,
    ResumeSession,
    StartSession,
)
from kineticloop.persistence.transactions import (
    ArtifactIdentity,
    EventWrite,
    GuardRequired,
    ReplayNotFound,
    RepositoryTransaction,
    RepositoryTransactionError,
    RestrictedSqlSession,
    TransactionStateError,
    execute_command,
    replay_outcome,
)
from kineticloop.protocol.authorization import AUTHORIZATION_METHOD_VERSION
from kineticloop.protocol.execution import (
    ExecutionIdentity,
    FullCommitRequest,
    OrdinaryPause,
    PublishReady,
    digest,
)


def _json(value: Any) -> Any:
    if isinstance(value, (UUID, date, datetime)):
        return str(value)
    if isinstance(value, Mapping):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


class ProtocolExecutionService:
    """Constructed by trusted ingress with an idle internal owner connection."""

    def __init__(self, connection: Connection[Any], identity: ExecutionIdentity) -> None:
        if type(identity) is not ExecutionIdentity:
            raise GuardRequired("separately authenticated execution identity required")
        identity.__post_init__()
        self._connection, self._identity = connection, identity

    def _guard(self, subject: UUID) -> None:
        if subject != self._identity.subject_id:
            raise GuardRequired("authenticated subject mismatch")
        if self._connection.info.transaction_status != TransactionStatus.IDLE:
            raise TransactionStateError("execution service requires idle owner connection")
        with self._connection.transaction():
            row = self._connection.execute(
                "SELECT scope.namespace,scope.policy_id,scope.environment_id,"
                "binding.principal_name FROM kineticloop.subject_scopes scope JOIN kineticloop.subject_principal_bindings binding "
                "ON binding.subject_id=scope.subject_id AND binding.namespace=scope.namespace WHERE scope.subject_id=%s",
                (subject,),
            ).fetchone()
        if row != (
            "TEST",
            self._identity.policy_id,
            self._identity.environment_id,
            self._identity.principal,
        ):
            raise GuardRequired("authenticated TEST registration mismatch")

    def _ingress(self, tx: RepositoryTransaction) -> None:
        tx.require_test_execution_ingress(
            policy_id=self._identity.policy_id,
            environment_id=self._identity.environment_id,
            principal=self._identity.principal,
        )

    def _replay(self, kind: str, key: str, request_hash: str) -> Mapping[str, Any] | None:
        try:
            outcome = replay_outcome(
                self._connection,
                kind,
                self._identity.subject_id,
                actor_scope=self._identity.key,
                client_key=key,
                request_hash=request_hash,
            )
            return {**outcome, "replayed": True, "executable": False}
        except ReplayNotFound:
            return None

    def _fresh_or_historical(
        self,
        kind: str,
        key: str,
        request_hash: str,
        operation: Callable[[], Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        try:
            return operation()
        except (RepositoryTransactionError, PsycopgError, ValueError):
            # A preflight miss can race a committed original and later authority loss.
            # Only after the failed fresh transaction has rolled back may the existing
            # receipt-only owner return history. No current action bypasses its guards.
            if self._connection.info.transaction_status != TransactionStatus.IDLE:
                raise
            self._guard(self._identity.subject_id)
            prior = self._replay(kind, key, request_hash)
            if prior is not None:
                return prior
            raise

    def _artifacts(self, ids: list[str]) -> tuple[ArtifactIdentity, ...]:
        # Immutable bounded inputs read outside coordination; exact owner rechecks follow.
        if not ids or len(ids) > 64 or len(ids) != len(set(ids)):
            raise GuardRequired("bounded exact artifact closure required")
        with self._connection.transaction():
            rows = self._connection.execute(
                "SELECT id,artifact_kind,artifact_identity,artifact_version,content_hash "
                "FROM kineticloop.safety_artifacts WHERE id=ANY(%s) ORDER BY id",
                ([UUID(item) for item in ids],),
            ).fetchall()
        if len(rows) != len(ids):
            raise GuardRequired("unknown artifact in immutable closure")
        return tuple(ArtifactIdentity(*row) for row in rows)

    def _registry(self, tx: RepositoryTransaction, artifacts: tuple[ArtifactIdentity, ...]) -> None:
        tx.acquire_registry_lease([item.artifact_id for item in artifacts])
        for item in artifacts:
            tx.require_artifact(item)
        self._ingress(tx)

    def publish(self, request: PublishReady) -> Mapping[str, Any]:
        if type(request) is not PublishReady:
            raise GuardRequired("typed publication request required")
        request.__post_init__()
        self._guard(request.subject_id)
        payload_hash = digest(_json(asdict(request)))
        prior = self._replay("PublishManifest", request.key, payload_hash)
        if prior is not None:
            return prior

        def fresh() -> Mapping[str, Any]:
            with self._connection.transaction():
                row = self._connection.execute(
                    "SELECT typed_payload FROM kineticloop.manifest_builds "
                    "WHERE subject_id=%s AND id=%s",
                    (request.subject_id, request.build_id),
                ).fetchone()
            if row is None:
                raise GuardRequired("READY publication input missing")
            artifacts = self._artifacts(row[0].get("artifact_closure_ids", []))

            def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
                self._registry(tx, artifacts)
                historical = tx.execution_historical_outcome(
                    actor_scope=self._identity.key,
                    client_key=request.key,
                    request_hash=payload_hash,
                )
                if historical is not None:
                    return historical
                manifest, receipt, event_id = uuid4(), uuid4(), uuid4()

                def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                    basis = session.prepared_publication()
                    session.insert(
                        "S24", {"id": manifest, "subject_id": request.subject_id, **basis}
                    )
                    for binding in session.prepared_projection_bindings():
                        session.insert(
                            "S25",
                            {
                                "id": uuid4(),
                                "subject_id": request.subject_id,
                                "ref_s24_id": manifest,
                                **binding,
                            },
                        )
                    session.update(
                        "S23",
                        {"status": "PUBLISHED"},
                        {"id": request.build_id, "subject_id": request.subject_id},
                    )
                    session.update(
                        "S01",
                        {
                            "current_manifest_id": manifest,
                            "decision_generation": basis["generation"],
                        },
                        {"subject_id": request.subject_id},
                    )
                    return {
                        "manifest_id": str(manifest),
                        "generation": basis["generation"],
                        "receipt_id": str(receipt),
                        "event_id": str(event_id),
                        "executable": False,
                    }

                outcome, replayed = tx.idempotent_outcome(
                    receipt_id=receipt,
                    actor_scope=self._identity.key,
                    client_key=request.key,
                    request_hash=payload_hash,
                    mutation=mutation,
                    event=EventWrite(
                        event_id,
                        "MANIFEST",
                        str(request.build_id),
                        1,
                        "MANIFEST_PUBLISHED",
                        "execution",
                        uuid4(),
                    ),
                    aggregate_locks={"manifest_builds": (request.build_id,)},
                    execution_request=request,
                )
                return {**outcome, "replayed": replayed}

            return execute_command(
                self._connection, "PublishManifest", request.subject_id, operation
            )

        return self._fresh_or_historical("PublishManifest", request.key, payload_hash, fresh)

    def commit(
        self, command: CommitBundle, *, requested_valid_until: datetime | None = None
    ) -> Mapping[str, Any]:
        return self._commit(command, requested_valid_until=requested_valid_until)

    def commit_full(
        self, request: FullCommitRequest, *, requested_valid_until: datetime | None = None
    ) -> Mapping[str, Any]:
        if type(request) is not FullCommitRequest:
            raise GuardRequired("closed full commit request required")
        request.__post_init__()
        return self._commit(
            request.command, requested_valid_until=requested_valid_until, full_request=request
        )

    def _commit(
        self,
        command: CommitBundle,
        *,
        requested_valid_until: datetime | None = None,
        full_request: FullCommitRequest | None = None,
    ) -> Mapping[str, Any]:
        if type(command) is not CommitBundle:
            raise GuardRequired("strict CommitBundle required")
        self._identity.require_wire(command)
        self._guard(UUID(command.subject_id))
        if requested_valid_until is not None and (
            type(requested_valid_until) is not datetime or requested_valid_until.tzinfo is None
        ):
            raise GuardRequired("requested shortening requires an absolute timezone")
        request_hash = digest(
            {
                "wire": command.model_dump(mode="json"),
                "requested_valid_until": _json(requested_valid_until),
                **(
                    {"full_sources": dict(full_request.sources)} if full_request is not None else {}
                ),
            }
        )
        prior = self._replay("CommitBundle", command.idempotency_key, request_hash)
        if prior is not None:
            return prior

        def fresh() -> Mapping[str, Any]:
            with self._connection.transaction():
                manifest = self._connection.execute(
                    "SELECT typed_payload FROM kineticloop.decision_manifests "
                    "WHERE subject_id=%s AND id=%s",
                    (self._identity.subject_id, UUID(command.manifest_id)),
                ).fetchone()
                inputs = self._connection.execute(
                    "SELECT intent.local_date,validation.ref_s36_id "
                    "FROM kineticloop.planning_intents intent JOIN kineticloop.validation_results validation "
                    "ON validation.subject_id=intent.subject_id WHERE intent.subject_id=%s AND intent.id=%s AND validation.id=%s",
                    (
                        self._identity.subject_id,
                        UUID(command.intent_id),
                        UUID(command.validation_id),
                    ),
                ).fetchone()
            if manifest is None or inputs is None:
                raise GuardRequired("current immutable commit inputs missing")
            artifacts = self._artifacts(manifest[0].get("artifact_closure_ids", []))
            subject, intent, attempt, validation = (
                UUID(command.subject_id),
                UUID(command.intent_id),
                UUID(command.attempt_id),
                UUID(command.validation_id),
            )

            def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
                self._registry(tx, artifacts)
                historical = tx.execution_historical_outcome(
                    actor_scope=self._identity.key,
                    client_key=command.idempotency_key,
                    request_hash=request_hash,
                )
                if historical is not None:
                    return historical
                tx.lock_intents((intent,))
                tx.require_current_fence(
                    intent,
                    owner_id=self._identity.key,
                    fence=command.expected_fence,
                    expected_request_revision=command.expected_request_revision,
                    expected_attempt_id=attempt,
                )
                tx.lock_daily_head(inputs[0], create_first=True)
                head = tx.execution_daily_head_id()
                bundle, prescription, issuance, receipt, event_id = (uuid4() for _ in range(5))

                def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                    nonlocal prescription, issuance
                    basis = session.prepared_commit()
                    session.insert(
                        "S39",
                        {
                            "id": bundle,
                            "subject_id": subject,
                            "ref_s38_id": head,
                            "local_date": basis["local_date"],
                            "revision_no": basis["revision_no"],
                            "parent_revision_id": basis["parent_revision_id"],
                            "generation_mode": "AI_GENERATED_CURRENT",
                            "ref_s02_id": receipt,
                            "ref_s24_id": basis["manifest_id"],
                            "ref_s27_id": intent,
                            "ref_s29_id": attempt,
                            "ref_s37_id": validation,
                        },
                    )
                    committed_members = []
                    members = basis.get("members", (basis,))
                    primary_prescription, primary_issuance = prescription, issuance
                    for index, member in enumerate(members):
                        if index:
                            prescription, issuance = uuid4(), uuid4()
                        session.insert(
                            "S40",
                            {
                                "id": prescription,
                                "subject_id": subject,
                                "prescription_identity": str(command.commit_identity)
                                + (":" + member["action_type"] if full_request is not None else ""),
                                "prescription_kind": member.get("action_type", "TRAINING"),
                                "prescription_revision": 1,
                                "ref_s34_id": member["proposal_id"],
                                "ref_s49_id": member["artifact_id"],
                                "content_hash": member["content_hash"],
                                "typed_payload": Jsonb(member["content"]),
                            },
                        )
                        membership = uuid4()
                        session.insert(
                            "S41",
                            {
                                "id": membership,
                                "subject_id": subject,
                                "member_kind": member.get("action_type", "TRAINING"),
                                "session_slot": member.get("session_slot", "TRAINING_1"),
                                "member_order": member.get("member_order", 1),
                                "ref_s39_id": bundle,
                                "ref_s40_id": prescription,
                            },
                        )
                        certificate = {
                            "authorization_epoch": basis["epoch"],
                            "method_version": AUTHORIZATION_METHOD_VERSION,
                            "closure_digest": session.authorization_closure_digest(),
                            "dependencies": list(session.authorization_certificate_dependencies()),
                        }
                        session.insert(
                            "S42",
                            {
                                "id": issuance,
                                "subject_id": subject,
                                "scope": basis["scope"],
                                "issuance_reason": "AI_PLAN",
                                "bound_content_hash": member["content_hash"],
                                "ref_s40_id": prescription,
                                "ref_s02_id": receipt,
                                "ref_s05_id": basis["policy_id"],
                                "ref_s24_id": basis["manifest_id"],
                                "ref_s36_id": member.get("resolution_id", inputs[1]),
                                "ref_s37_id": validation,
                                "ref_s49_id": member["artifact_id"],
                                "registry_state_id": 1,
                                "registry_revision_at_issue": basis["registry_revision"],
                                "valid_from": session.authorization_valid_from(),
                                "valid_until": session.authorization_valid_until(),
                                "validity_certificate": Jsonb(certificate),
                                "artifact_dependency_closure_hash": session.authorization_closure_digest(),
                            },
                        )
                        session.insert_authorization_artifact_closure(
                            issuance, artifact_ids=[item.artifact_id for item in artifacts]
                        )
                        committed_members.append(
                            {
                                "action_type": member.get("action_type", "TRAINING"),
                                "member_id": str(membership),
                                "prescription_id": str(prescription),
                                "authorization_id": str(issuance),
                                "content_hash": member["content_hash"],
                                "resolution_id": str(member.get("resolution_id", inputs[1])),
                                "validation_id": str(validation),
                                "member_order": index + 1,
                                "session_slot": member.get("session_slot", "TRAINING_1"),
                            }
                        )
                    prescription, issuance = primary_prescription, primary_issuance
                    # This bounded slice accepts only a first head, preserving existing update/reauthorize semantics.
                    if basis["parent_revision_id"] is not None:
                        raise GuardRequired(
                            "first-day execution adapter requires absent prior bundle"
                        )
                    session.update(
                        "S38",
                        {
                            "current_bundle_revision_id": bundle,
                            "head_revision": basis["revision_no"],
                        },
                        {"subject_id": subject, "id": head},
                    )
                    session.update(
                        "S27",
                        {
                            "status": "FOUND_VALID_PLAN",
                            "result_bundle_revision_id": bundle,
                            "result_authorization_id": issuance,
                        },
                        {"subject_id": subject, "id": intent},
                    )
                    session.update(
                        "S29", {"status": "COMMITTED"}, {"subject_id": subject, "id": attempt}
                    )
                    session.update(
                        "S01", {"execution_basis_event_id": event_id}, {"subject_id": subject}
                    )
                    return {
                        "bundle_id": str(bundle),
                        "prescription_id": str(prescription),
                        "authorization_id": str(issuance),
                        "head_id": str(head),
                        "content_hash": committed_members[0]["content_hash"],
                        **({"members": committed_members} if full_request is not None else {}),
                        "artifact_dependency_closure_hash": session.authorization_closure_digest(),
                        "valid_until": session.authorization_valid_until().isoformat(),
                        "receipt_id": str(receipt),
                        "event_id": str(event_id),
                        "executable": False,
                    }

                outcome, replayed = tx.idempotent_outcome(
                    receipt_id=receipt,
                    actor_scope=self._identity.key,
                    client_key=command.idempotency_key,
                    request_hash=request_hash,
                    mutation=mutation,
                    event=EventWrite(
                        event_id,
                        "BUNDLE",
                        command.commit_identity,
                        1,
                        "BUNDLE_COMMITTED",
                        "execution",
                        uuid4(),
                    ),
                    aggregate_locks={
                        "planning_attempts": (attempt,),
                        "validation_results": (validation,),
                    },
                    authorization_basis={
                        "validation_id": validation,
                        "resolution_id": inputs[1],
                        "intent_id": intent,
                        "head_id": head,
                        "requested_valid_until": requested_valid_until,
                    },
                    execution_request=command,
                    full_request=full_request,
                    execution_identity=self._identity,
                )
                return {**outcome, "replayed": replayed}

            return execute_command(self._connection, "CommitBundle", subject, operation)

        return self._fresh_or_historical(
            "CommitBundle", command.idempotency_key, request_hash, fresh
        )

    def start(self, command: StartSession) -> Mapping[str, Any]:
        if type(command) is not StartSession:
            raise GuardRequired("strict StartSession required")
        return self._execute_session(command)

    def continue_session(self, command: ContinueSession) -> Mapping[str, Any]:
        if type(command) is not ContinueSession:
            raise GuardRequired("strict ContinueSession required")
        return self._execute_session(command)

    def resume(self, command: ResumeSession) -> Mapping[str, Any]:
        if type(command) is not ResumeSession:
            raise GuardRequired("strict ResumeSession required")
        return self._execute_session(command)

    def _execute_session(
        self, command: StartSession | ContinueSession | ResumeSession
    ) -> Mapping[str, Any]:
        self._identity.require_wire(command)
        self._guard(UUID(command.subject_id))
        prior = self._replay(command.command_kind, command.idempotency_key, command.request_hash)
        if prior is not None:
            return prior

        def fresh() -> Mapping[str, Any]:
            subject, session_id = UUID(command.subject_id), UUID(command.session_id)
            with self._connection.transaction():
                row = self._connection.execute(
                    "SELECT head.local_date,manifest.typed_payload "
                    "FROM kineticloop.authorization_issuances issuance JOIN kineticloop.decision_manifests manifest "
                    "ON manifest.subject_id=issuance.subject_id AND manifest.id=issuance.ref_s24_id "
                    "JOIN kineticloop.bundle_prescription_members member ON member.subject_id=issuance.subject_id AND member.ref_s40_id=issuance.ref_s40_id "
                    "JOIN kineticloop.daily_plan_heads head ON head.subject_id=member.subject_id AND head.current_bundle_revision_id=member.ref_s39_id "
                    "WHERE issuance.subject_id=%s AND issuance.id=%s",
                    (subject, UUID(command.authorization_id)),
                ).fetchone()
            if row is None:
                raise GuardRequired("exact current bundle membership missing")
            artifacts = self._artifacts(row[1].get("artifact_closure_ids", []))

            def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
                self._registry(tx, artifacts)
                historical = tx.execution_historical_outcome(
                    actor_scope=self._identity.key,
                    client_key=command.idempotency_key,
                    request_hash=command.request_hash,
                )
                if historical is not None:
                    return historical
                tx.lock_daily_head(row[0])
                tx.lock_execution((session_id,), create_first=isinstance(command, StartSession))
                receipt, event_id = uuid4(), uuid4()

                def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                    accepted = session.execution_binding_accepted_at()
                    binding_id = (
                        uuid4()
                        if not isinstance(command, ContinueSession)
                        else UUID(command.current_binding_id)
                    )
                    if not isinstance(command, ContinueSession):
                        session.insert(
                            "S45",
                            {
                                "id": binding_id,
                                "subject_id": subject,
                                "binding_kind": "START"
                                if isinstance(command, StartSession)
                                else "RESUME",
                                "binding_revision": session.execution_binding_revision(),
                                "accepted_at": accepted,
                                "execution_scope": "TEST_ONLY",
                                "ref_s02_id": receipt,
                                "ref_s40_id": UUID(command.prescription_id),
                                "ref_s42_id": UUID(command.authorization_id),
                                "ref_s44_id": session_id,
                            },
                        )
                    session.update(
                        "S44",
                        {
                            "lifecycle": "IN_PROGRESS",
                            "execution_revision": 1
                            if isinstance(command, StartSession)
                            else session.execution_revision(),
                        },
                        {"subject_id": subject, "id": session_id},
                    )
                    session.update(
                        "S01", {"execution_basis_event_id": event_id}, {"subject_id": subject}
                    )
                    return {
                        "session_id": str(session_id),
                        "binding_id": str(binding_id),
                        "binding_revision": command.binding_revision,
                        "execution_revision": 1
                        if isinstance(command, StartSession)
                        else session.execution_revision(),
                        "prescription_id": command.prescription_id,
                        "authorization_id": command.authorization_id,
                        "accepted_at": accepted.isoformat(),
                        "receipt_id": str(receipt),
                        "event_id": str(event_id),
                        "executable": True,
                    }

                outcome, replayed = tx.idempotent_outcome(
                    receipt_id=receipt,
                    actor_scope=self._identity.key,
                    client_key=command.idempotency_key,
                    request_hash=command.request_hash,
                    mutation=mutation,
                    event=EventWrite(
                        event_id,
                        "SESSION",
                        command.session_id,
                        tx.execution_next_revision(),
                        {
                            "StartSession": "SESSION_STARTED",
                            "ResumeSession": "SESSION_RESUMED",
                            "ContinueSession": "SESSION_CONTINUED",
                        }[command.command_kind],
                        "execution",
                        uuid4(),
                    ),
                    execution_request=command,
                )
                return {**outcome, "replayed": replayed, "executable": not replayed}

            return execute_command(self._connection, command.command_kind, subject, operation)

        return self._fresh_or_historical(
            command.command_kind, command.idempotency_key, command.request_hash, fresh
        )

    def pause(self, request: OrdinaryPause) -> Mapping[str, Any]:
        if type(request) is not OrdinaryPause:
            raise GuardRequired("strict ordinary lifecycle pause required")
        request.__post_init__()
        if request.identity != self._identity:
            raise GuardRequired("separately authenticated ordinary pause identity mismatch")
        self._guard(self._identity.subject_id)
        request_hash = digest(_json(asdict(request)))
        prior = self._replay("OrdinaryPause", request.key, request_hash)
        if prior is not None:
            return prior

        def fresh() -> Mapping[str, Any]:
            def operation(tx: RepositoryTransaction) -> Mapping[str, Any]:
                tx.lock_subject()
                self._ingress(tx)
                historical = tx.execution_historical_outcome(
                    actor_scope=self._identity.key,
                    client_key=request.key,
                    request_hash=request_hash,
                )
                if historical is not None:
                    return historical
                tx.lock_execution((request.session_id,))
                receipt, event_id = uuid4(), uuid4()

                def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
                    revision = request.expected_execution_revision + 1
                    session.update(
                        "S44",
                        {"lifecycle": "PAUSED", "execution_revision": revision},
                        {"subject_id": self._identity.subject_id, "id": request.session_id},
                    )
                    session.update(
                        "S01",
                        {"execution_basis_event_id": event_id},
                        {"subject_id": self._identity.subject_id},
                    )
                    return {
                        "session_id": str(request.session_id),
                        "binding_id": str(request.binding_id),
                        "execution_revision": revision,
                        "reason": request.reason,
                        "receipt_id": str(receipt),
                        "event_id": str(event_id),
                        "executable": False,
                    }

                outcome, replayed = tx.idempotent_outcome(
                    receipt_id=receipt,
                    actor_scope=self._identity.key,
                    client_key=request.key,
                    request_hash=request_hash,
                    mutation=mutation,
                    event=EventWrite(
                        event_id,
                        "SESSION",
                        str(request.session_id),
                        request.expected_execution_revision + 1,
                        "SESSION_PAUSED",
                        "execution",
                        uuid4(),
                    ),
                    execution_request=request,
                )
                return {**outcome, "replayed": replayed}

            return execute_command(
                self._connection, "OrdinaryPause", self._identity.subject_id, operation
            )

        return self._fresh_or_historical("OrdinaryPause", request.key, request_hash, fresh)
