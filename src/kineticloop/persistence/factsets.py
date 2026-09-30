"""CanonicalViewService over the single repository transaction owner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast
from uuid import UUID, uuid4, uuid5

from psycopg import Connection, sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.transactions import (
    EventWrite,
    GuardRequired,
    ReplayNotFound,
    RepositoryTransaction,
    RestrictedSqlSession,
    TransactionStateError,
    execute_command,
    execute_factset_build,
    replay_outcome,
)
from kineticloop.protocol.factsets import (
    EvidenceBasis,
    Factset,
    FactsetError,
    Member,
    Reconstruction,
    certificate_basis,
    completion_certificate,
    digest,
    reconstruct,
    storage_plan,
)

_ID_NAMESPACE = UUID("b8d52eee-1349-4522-a0af-a62c60ca43c4")
_REFERENCE_TABLES = {
    "FACT": ("canonical_fact_revisions", "ref_s14_id"),
    "ADMISSION": ("admission_decisions", "ref_s13_id"),
    "ASSOCIATION": ("event_association_decisions", "ref_s12_id"),
    "MAPPING": ("exercise_mapping_decisions", "ref_s20_id"),
}


@dataclass(frozen=True)
class BuilderIdentity:
    """Trusted ingress binding, never parsed from a build command payload."""

    actor: RoleIdentity
    subject_id: UUID

    def __post_init__(self) -> None:
        if (
            type(self.actor) is not RoleIdentity
            or self.actor.role not in {ActorRole.SUBJECT, ActorRole.TEST}
            or not isinstance(self.subject_id, UUID)
        ):
            raise GuardRequired("authenticated subject builder required")

    @property
    def key(self) -> str:
        return f"{self.actor.role}:{self.actor.identity_id}"


@dataclass(frozen=True)
class BeginBuild:
    subject_id: UUID
    key: str
    captured_input_frontier: str
    captured_epoch: int
    program_revision_id: UUID
    policy_id: UUID
    basis: EvidenceBasis
    mapping_revision_id: UUID | None = None
    parent_id: UUID | None = None
    max_delta_depth: int = 8


@dataclass(frozen=True)
class WriteCandidate:
    subject_id: UUID
    key: str
    build_id: UUID
    expected_member_revision: int
    member: Member


@dataclass(frozen=True)
class CompleteFactset:
    subject_id: UUID
    key: str
    build_id: UUID
    expected_member_revision: int


@dataclass(frozen=True)
class SealFactset:
    subject_id: UUID
    key: str
    build_id: UUID
    completion: Mapping[str, Any]


def _wire(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(v) for v in value]
    return value


class CanonicalViewService:
    def __init__(self, connection: Connection[Any], builder: BuilderIdentity) -> None:
        if type(builder) is not BuilderIdentity:
            raise GuardRequired("trusted builder binding required")
        self.connection = connection
        self.builder = builder

    def _guard(self, subject_id: UUID, key: str = "read") -> None:
        if subject_id != self.builder.subject_id:
            raise GuardRequired("authenticated subject mismatch")
        if not isinstance(key, str) or not key.strip():
            raise FactsetError("command key required")
        if self.connection.info.transaction_status is not TransactionStatus.IDLE:
            raise TransactionStateError("factset service requires idle connection")
        with self.connection.transaction():
            scope = self.connection.execute(
                "SELECT namespace FROM kineticloop.subject_scopes WHERE subject_id=%s",
                (subject_id,),
            ).fetchone()
        namespace = {
            ActorRole.SUBJECT: "PRODUCTION",
            ActorRole.TEST: "TEST",
        }[self.builder.actor.role]
        if scope is None or scope[0] != namespace:
            raise GuardRequired("authenticated subject namespace mismatch")

    def _replay_basis(self, command: Any, outcome: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "command_key": command.key,
            "builder_identity": self.builder.key,
            "request_hash": digest(_wire(asdict(command))),
            "durable_outcome": dict(outcome),
        }

    def begin_build(self, command: BeginBuild) -> Mapping[str, Any]:
        self._guard(command.subject_id, command.key)
        if type(command.captured_epoch) is not int or command.captured_epoch < 0:
            raise FactsetError("invalid captured epoch")
        build_id = uuid5(_ID_NAMESPACE, f"{command.subject_id}:begin:{command.key}")
        parent = None
        checkpoint: tuple[Member, ...] = ()
        if command.parent_id is not None:
            parent, ancestors, _ = self._load_chain(command.parent_id, command.max_delta_depth)
            inherited = reconstruct(
                parent, ancestors, max_depth=command.max_delta_depth, canonical=True
            )
            if parent.subject_id != command.subject_id:
                raise FactsetError("foreign parent")
        mode, parent_id, depth = storage_plan(parent, command.max_delta_depth)
        if parent is not None and mode == "FULL":
            checkpoint = inherited.members
        with self.connection.transaction():
            self._validate_references(command.subject_id, command.basis, ())
            for member in checkpoint:
                self._validate_member(command.subject_id, member)
            policy = self.connection.execute(
                "SELECT typed_payload->'factset_max_delta_depth' FROM kineticloop.policy_bundles "
                "WHERE subject_id=%s AND id=%s",
                (command.subject_id, command.policy_id),
            ).fetchone()
            if policy is None or type(policy[0]) is not int or policy[0] != command.max_delta_depth:
                raise FactsetError("maximum DELTA depth must match selected immutable policy")
            if command.mapping_revision_id not in (*command.basis.mappings, None):
                raise FactsetError("mapping must be in complete selected basis")
        outcome = {
            "build_id": str(build_id),
            "member_revision": 0,
            "storage_mode": mode,
            "delta_depth": depth,
        }
        basis = self._replay_basis(command, outcome) | {
            "build_identity": f"kl023:{command.key}",
            "storage_mode": mode,
            "captured_input_frontier": command.captured_input_frontier,
            "captured_epoch": command.captured_epoch,
            "program_revision_id": command.program_revision_id,
            "policy_id": command.policy_id,
            "mapping_revision_id": command.mapping_revision_id,
            "domain_basis": command.basis.payload(),
            "domain_basis_digest": digest(command.basis.payload()),
            "parent_factset_id": str(parent_id) if parent_id else None,
            "max_delta_depth": command.max_delta_depth,
            "checkpoint": [m.payload() for m in checkpoint],
        }

        def create(session: RestrictedSqlSession) -> Mapping[str, Any]:
            session.insert(
                "S15",
                {
                    "id": build_id,
                    "subject_id": command.subject_id,
                    "factset_identity": basis["build_identity"],
                    "status": "BUILDING",
                    "storage_mode": mode,
                    "delta_depth": depth,
                    "member_revision": 0,
                    "completed_member_revision": None,
                    "membership_digest": None,
                    "ref_s20_id": command.mapping_revision_id,
                    "typed_payload": Jsonb(session.factset_build_payload()),
                },
            )
            return outcome

        return execute_factset_build(
            self.connection,
            "BeginBuild",
            command.subject_id,
            build_id,
            create,
            factset_build_basis=basis,
        )

    def write_candidate(self, command: WriteCandidate) -> Mapping[str, Any]:
        self._guard(command.subject_id, command.key)
        if (
            type(command.expected_member_revision) is not int
            or command.expected_member_revision < 0
        ):
            raise FactsetError("invalid member revision")
        with self.connection.transaction():
            self._validate_member(command.subject_id, command.member)
        member_id = uuid5(command.build_id, f"member:{command.key}")
        outcome = {
            "build_id": str(command.build_id),
            "member_id": str(member_id),
            "member_revision": command.expected_member_revision + 1,
        }
        basis = self._replay_basis(command, outcome) | {
            "expected_member_revision": command.expected_member_revision
        }

        def write(session: RestrictedSqlSession) -> Mapping[str, Any]:
            member = command.member
            session.insert(
                "S16",
                {
                    "id": member_id,
                    "subject_id": command.subject_id,
                    "ref_s15_id": command.build_id,
                    "member_kind": member.kind,
                    "logical_member_key": member.key,
                    "action_scope": member.scope,
                    "member_operation": member.operation,
                    _REFERENCE_TABLES[member.kind][1]: member.revision_id,
                },
            )
            session.update(
                "S15",
                {"member_revision": command.expected_member_revision + 1},
                {"id": command.build_id, "subject_id": command.subject_id},
            )
            return outcome

        return execute_factset_build(
            self.connection,
            "WriteCandidate",
            command.subject_id,
            command.build_id,
            write,
            factset_build_basis=basis,
        )

    def complete_factset(self, command: CompleteFactset) -> Mapping[str, Any]:
        self._guard(command.subject_id, command.key)
        if (
            type(command.expected_member_revision) is not int
            or command.expected_member_revision < 0
        ):
            raise FactsetError("invalid member revision")
        root, ancestors, payload = self._load_chain(command.build_id)
        # Read a consistent candidate snapshot without S01/S15 locks, then close by CAS.
        result = reconstruct(root, ancestors, max_depth=payload["max_delta_depth"])
        with self.connection.transaction():
            self._validate_references(command.subject_id, root.basis, result.members)
        identity = digest(
            {
                "build_id": str(command.build_id),
                "revision": command.expected_member_revision,
                "digest": result.membership_digest,
            }
        )
        cert = completion_certificate(
            subject_id=command.subject_id,
            build_id=command.build_id,
            member_revision=command.expected_member_revision,
            membership_digest=result.membership_digest,
            member_count=result.member_count,
            payload=payload,
        )
        outcome = {
            "build_id": str(command.build_id),
            "completed_member_revision": command.expected_member_revision,
            "membership_digest": result.membership_digest,
            "member_count": result.member_count,
            "completion_identity": identity,
            "completion_certificate": cert,
            "captured_input_frontier": payload["captured_input_frontier"],
            "captured_epoch": payload["captured_epoch"],
        } | certificate_basis(payload)
        basis = self._replay_basis(command, outcome) | {
            "expected_member_revision": command.expected_member_revision,
            "membership_digest": result.membership_digest,
            "member_count": result.member_count,
            "completion_identity": identity,
        }
        if root.member_revision != command.expected_member_revision:
            raise GuardRequired("candidate revision changed before completion")

        def complete(session: RestrictedSqlSession) -> Mapping[str, Any]:
            session.update(
                "S15",
                {
                    "status": "READY",
                    "member_revision": root.member_revision,
                    "completed_member_revision": root.member_revision,
                    "membership_digest": result.membership_digest,
                    "typed_payload": Jsonb(session.factset_completion_payload()),
                },
                {"id": command.build_id, "subject_id": command.subject_id},
            )
            return outcome

        return execute_factset_build(
            self.connection,
            "CompleteFactset",
            command.subject_id,
            command.build_id,
            complete,
            factset_build_basis=basis,
        )

    def seal_factset(self, command: SealFactset) -> Mapping[str, Any]:
        self._guard(command.subject_id, command.key)
        request_hash = digest(_wire(asdict(command)))
        actor_scope = self.builder.key
        # Historical receipt replay needs neither members nor a current READY artifact.
        try:
            return replay_outcome(
                self.connection,
                "SealFactset",
                command.subject_id,
                actor_scope=actor_scope,
                client_key=command.key,
                request_hash=request_hash,
            )
        except ReplayNotFound:
            pass
        completion = dict(command.completion)
        if completion.get("build_id") != str(command.build_id):
            raise GuardRequired("completion belongs to a different build")
        if completion.get("builder_identity") != self.builder.key:
            raise GuardRequired("factset builder ownership mismatch")

        def seal(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
            tx.lock_subject()

            def mutate(session: RestrictedSqlSession) -> Mapping[str, Any]:
                session.update(
                    "S15",
                    {"status": "SEALED", "sealed_at": session.factset_sealed_at()},
                    {"id": command.build_id, "subject_id": command.subject_id},
                )
                session.update(
                    "S01",
                    {"current_factset_id": command.build_id},
                    {"subject_id": command.subject_id},
                )
                return {
                    "factset_id": str(command.build_id),
                    "completion_identity": completion["completion_identity"],
                    "completion": completion,
                }

            return tx.idempotent_outcome(
                receipt_id=uuid4(),
                actor_scope=actor_scope,
                client_key=command.key,
                request_hash=request_hash,
                mutation=mutate,
                event=EventWrite(
                    uuid4(),
                    "FACTSET",
                    str(command.build_id),
                    1,
                    "FACTSET_SEALED",
                    "canonical",
                    uuid4(),
                ),
                aggregate_locks={"factset_revisions": (command.build_id,)},
                factset_seal_basis=completion | {"factset_id": command.build_id},
            )

        return execute_command(self.connection, "SealFactset", command.subject_id, seal)[0]

    def read_canonical(self, subject_id: UUID, factset_id: UUID) -> Reconstruction:
        self._guard(subject_id)
        root, ancestors, payload = self._load_chain(factset_id)
        return reconstruct(root, ancestors, max_depth=payload["max_delta_depth"], canonical=True)

    def _load_chain(
        self, factset_id: UUID, limit: int | None = None
    ) -> tuple[Factset, Mapping[UUID, Factset], Mapping[str, Any]]:
        self._guard(self.builder.subject_id)
        with self.connection.transaction():
            # One snapshot pairs each S15 member_revision with its S16 membership.
            self.connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            nodes: dict[UUID, Factset] = {}
            current: UUID | None = factset_id
            root_payload: Mapping[str, Any] = {}
            while current is not None:
                if current in nodes:
                    raise FactsetError("cyclic chain")
                row = self.connection.execute(
                    "SELECT id,status,storage_mode,delta_depth,"
                    "member_revision,membership_digest,typed_payload,completed_member_revision,ref_s20_id "
                    "FROM kineticloop.factset_revisions "
                    "WHERE subject_id=%s AND id=%s",
                    (self.builder.subject_id, current),
                ).fetchone()
                if row is None:
                    raise FactsetError("missing or foreign parent/build")
                payload = row[6]
                if digest(payload["domain_basis"]) != payload.get("domain_basis_digest"):
                    raise FactsetError("selected basis digest mismatch")
                if row[1] in {"READY", "SEALED"}:
                    expected_certificate = completion_certificate(
                        subject_id=self.builder.subject_id,
                        build_id=current,
                        member_revision=row[7],
                        membership_digest=row[5],
                        member_count=payload.get("member_count"),
                        payload=payload,
                    )
                    if (
                        row[4] != row[7]
                        or not payload.get("completion_identity")
                        or payload.get("completion_certificate") != expected_certificate
                        or payload.get("mapping_revision_id") != (str(row[8]) if row[8] else None)
                    ):
                        raise FactsetError("closed completion certificate mismatch")

                if not nodes:
                    root_payload = payload
                    if limit is None:
                        limit = payload.get("max_delta_depth")
                    if type(limit) is not int or limit < 0:
                        raise FactsetError("missing chain bound")
                assert limit is not None
                if len(nodes) > limit:
                    raise FactsetError("chain exceeds bound")
                members = tuple(
                    Member(r[0], r[1], r[2], r[3] or r[4] or r[5] or r[6], r[7])
                    for r in self.connection.execute(
                        "SELECT member_kind,logical_member_key,"
                        "action_scope,ref_s14_id,ref_s13_id,ref_s12_id,ref_s20_id,member_operation "
                        "FROM kineticloop.factset_members WHERE subject_id=%s AND ref_s15_id=%s",
                        (self.builder.subject_id, current),
                    ).fetchall()
                )
                parent = (
                    UUID(payload["parent_factset_id"]) if payload.get("parent_factset_id") else None
                )
                nodes[current] = Factset(
                    row[0],
                    self.builder.subject_id,
                    row[1],
                    row[2],
                    parent,
                    row[3],
                    row[4],
                    members,
                    EvidenceBasis.from_payload(payload["domain_basis"]),
                    tuple(Member.from_payload(x) for x in payload.get("checkpoint", [])),
                    row[5],
                    payload.get("member_count"),
                )
                current = parent
            return nodes[factset_id], nodes, root_payload

    def _validate_member(self, subject_id: UUID, member: Member) -> None:
        if member.operation == "REMOVE":
            return
        table = _REFERENCE_TABLES[member.kind][0]
        row = self.connection.execute(
            sql.SQL("SELECT 1 FROM kineticloop.{} WHERE subject_id=%s AND id=%s").format(
                sql.Identifier(table)
            ),
            (subject_id, member.revision_id),
        ).fetchone()
        if row is None:
            raise FactsetError("missing or foreign typed member revision")

    def _validate_references(
        self, subject_id: UUID, basis: EvidenceBasis, members: tuple[Member, ...]
    ) -> None:
        for kind, ids in (
            ("ASSOCIATION", basis.associations),
            ("ADMISSION", basis.admissions),
            ("MAPPING", basis.mappings),
        ):
            for revision in ids:
                self._validate_member(
                    subject_id,
                    Member(
                        cast(Literal["FACT", "ADMISSION", "ASSOCIATION", "MAPPING"], kind),
                        str(revision),
                        "BASIS",
                        revision,
                    ),
                )
        for member in members:
            self._validate_member(subject_id, member)
            if member.kind == "FACT" and member.operation == "SET":
                admission = self.connection.execute(
                    "SELECT ref_s13_id FROM kineticloop.canonical_fact_revisions "
                    "WHERE subject_id=%s AND id=%s",
                    (subject_id, member.revision_id),
                ).fetchone()
                if admission is None or admission[0] not in basis.admissions:
                    raise FactsetError("fact admission missing from selected complete basis")
