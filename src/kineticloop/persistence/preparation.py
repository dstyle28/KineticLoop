"""Source-bound, immutable TEST preparation; publication remains exclusively T3."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from psycopg import Connection, Cursor
from psycopg.types.json import Jsonb

from kineticloop.persistence.transactions import (
    ArtifactIdentity,
    GuardRequired,
    IdempotencyConflict,
    _execute_source_preparation,
    _source_preparation_session,
    artifact_bindings_match_activation,
)
from kineticloop.protocol.authorization import canonical_certificate_timestamp
from kineticloop.protocol.execution import ExecutionIdentity, digest

PreparationIdentity = ExecutionIdentity
_NAMESPACE = UUID("938f32ce-cfef-4c8a-8822-72c19ec5cffc")


def wire(value: Any) -> Any:
    if isinstance(value, (UUID, datetime)):
        return str(value)
    if isinstance(value, Mapping):
        return {key: wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [wire(item) for item in value]
    return value


@dataclass(frozen=True)
class SourceBasis:
    factset_id: UUID
    source_hash: str
    frontier: str
    epoch: int
    program_id: UUID
    policy_id: UUID
    mapping_id: UUID | None
    catalog_id: UUID | None


@dataclass(frozen=True)
class Dependency:
    kind: str
    key: str
    collection: str | None = None
    fact_id: UUID | None = None


@dataclass(frozen=True)
class RecordProjection:
    source: SourceBasis
    kind: str
    engine: ArtifactIdentity
    window: tuple[str, str]
    content: Mapping[str, Any]
    dependencies: tuple[Dependency, ...]
    valid_until: datetime


@dataclass(frozen=True)
class ProjectionBinding:
    role: str
    projection_id: UUID


@dataclass(frozen=True)
class BuildManifest:
    key: str
    source: SourceBasis
    bindings: tuple[ProjectionBinding, ...]
    artifact_roots: tuple[UUID, ...]


@dataclass(frozen=True)
class CompleteManifest:
    build_id: UUID


def _authenticate(cursor: Cursor[Any], identity: PreparationIdentity) -> None:
    if type(identity) is not PreparationIdentity:
        raise GuardRequired("separately authenticated TEST preparation identity required")
    identity.__post_init__()
    cursor.execute(
        "SELECT scope.namespace,scope.policy_id,scope.environment_id,binding.principal_name,"
        "current_user,session_user FROM kineticloop.subject_scopes scope "
        "JOIN kineticloop.subject_principal_bindings binding "
        "ON binding.subject_id=scope.subject_id AND binding.namespace=scope.namespace "
        "WHERE scope.subject_id=%s",
        (identity.subject_id,),
    )
    row = cursor.fetchone()
    if (
        row is None
        or row[:4] != ("TEST", identity.policy_id, identity.environment_id, identity.principal)
        or row[4] != row[5]
        or row[5] == identity.principal
    ):
        raise GuardRequired("authenticated TEST preparation registration/owner mismatch")


def _source(cursor: Cursor[Any], identity: PreparationIdentity, factset: UUID) -> SourceBasis:
    if type(factset) is not UUID:
        raise GuardRequired("exact factset identity required")
    cursor.execute(
        "SELECT f.status,f.membership_digest,f.typed_payload,f.ref_s20_id,m.ref_s19_id "
        "FROM kineticloop.factset_revisions f LEFT JOIN kineticloop.exercise_mapping_decisions m "
        "ON m.subject_id=f.subject_id AND m.id=f.ref_s20_id WHERE f.subject_id=%s AND f.id=%s",
        (identity.subject_id, factset),
    )
    row = cursor.fetchone()
    if row is None or row[0] != "SEALED":
        raise GuardRequired("exact same-subject SEALED factset required")
    payload = row[2]
    try:
        program, policy = UUID(payload["program_revision_id"]), UUID(payload["policy_id"])
        frontier, epoch = payload["captured_input_frontier"], payload["captured_epoch"]
        if (
            policy != identity.policy_id
            or not row[1]
            or not frontier
            or type(epoch) is not int
            or not payload["completion_certificate"]
            or not payload["domain_basis_digest"]
        ):
            raise ValueError("incomplete sealed source")
    except (KeyError, TypeError, ValueError) as error:
        raise GuardRequired("sealed source lacks exact immutable basis") from error
    cursor.execute(
        "SELECT 1 FROM kineticloop.program_versions WHERE subject_id=%s AND id=%s",
        (identity.subject_id, program),
    )
    if cursor.fetchone() is None:
        raise GuardRequired("sealed source program missing")
    return SourceBasis(
        factset,
        digest(wire([str(factset), *row])),
        frontier,
        epoch,
        program,
        policy,
        row[3],
        row[4],
    )


def _verify_source(cursor: Cursor[Any], identity: PreparationIdentity, source: SourceBasis) -> None:
    if type(source) is not SourceBasis or _source(cursor, identity, source.factset_id) != source:
        raise GuardRequired("exact source hash/basis conflict")


def _requirements(cursor: Cursor[Any], identity: PreparationIdentity, source: SourceBasis) -> dict[str, Any]:
    cursor.execute(
        "SELECT typed_payload FROM kineticloop.policy_bundles WHERE subject_id=%s AND id=%s",
        (identity.subject_id, identity.policy_id),
    )
    row = cursor.fetchone()
    try:
        requirements = row[0]["manifest_projection_requirements"] if row else None
        if not isinstance(requirements, dict) or not requirements:
            raise ValueError("missing role closure")
        mandatory = {"COLLECTION", "ENGINE", "FACTSET", "PROGRAM", "POLICY"}
        if source.mapping_id is not None:
            mandatory.add("MAPPING")
        if source.catalog_id is not None:
            mandatory.add("CATALOG")
        for role, item in requirements.items():
            deps = item["dependencies"]
            keys = [(d["kind"], d["key"], d.get("collection")) for d in deps]
            if (
                not role
                or not item["projection_kind"]
                or len(keys) != len(set(keys))
                or not mandatory <= {k[0] for k in keys}
                or not any(k[2] for k in keys)
                or any(k[0] == "COLLECTION" and not k[2] for k in keys)
            ):
                raise ValueError("incomplete dependency closure")
        return requirements
    except (KeyError, TypeError, ValueError) as error:
        raise GuardRequired("complete immutable policy role/dependency closure required") from error


def projection_identity(subject: UUID, request: RecordProjection) -> tuple[UUID, str, str]:
    basis_hash = digest(
        wire(
            {
                "source": asdict(request.source),
                "dependencies": [
                    asdict(d) for d in sorted(request.dependencies, key=lambda d: (d.kind, d.key))
                ],
            }
        )
    )
    projection = uuid5(_NAMESPACE, f"{subject}:{request.kind}:{basis_hash}")
    canonical = wire(asdict(request))
    canonical["dependencies"] = sorted(
        canonical["dependencies"], key=lambda dep: (dep["kind"], dep["key"])
    )
    return projection, basis_hash, digest(canonical)


def _artifacts(cursor: Cursor[Any], roots: tuple[UUID, ...]) -> tuple[list[dict[str, Any]], str]:
    if not roots or len(roots) != len(set(roots)) or any(type(r) is not UUID for r in roots):
        raise GuardRequired("exact nonduplicate artifact roots required")
    cursor.execute(
        "WITH RECURSIVE closure(id) AS (SELECT id FROM kineticloop.safety_artifacts WHERE id=ANY(%s) "
        "UNION SELECT e.dependency_artifact_id FROM closure c JOIN kineticloop.safety_artifact_dependencies e "
        "ON e.artifact_id=c.id) SELECT a.id,a.artifact_kind,a.artifact_identity,a.artifact_version,"
        "a.content_hash,a.revision,a.validity_kind,a.valid_from,a.valid_until,a.timeless_approval_policy,"
        "a.timeless_approval_reason,a.ref_s05_id,a.ref_s19_id,a.ref_s48_id "
        "FROM closure c JOIN kineticloop.safety_artifacts a ON a.id=c.id ORDER BY a.id",
        (list(roots),),
    )
    rows = cursor.fetchall()
    if not set(roots) <= {r[0] for r in rows} or len(rows) > 64:
        raise GuardRequired("missing/bounded artifact closure required")
    cursor.execute("SELECT clock_timestamp()")
    now = cursor.fetchone()[0]  # type: ignore[index]
    cursor.execute(
        "SELECT ref_s49_id FROM kineticloop.artifact_revocation_events WHERE ref_s49_id=ANY(%s)",
        ([r[0] for r in rows],),
    )
    if cursor.fetchone():
        raise GuardRequired("artifact closure revoked")
    proofs = []
    for row in rows:
        if (
            row[6] not in {"BOUNDED", "TIMELESS"}
            or row[7] is None
            or row[7] > now
            or (row[6] == "BOUNDED" and (row[8] is None or row[8] <= now))
        ):
            raise GuardRequired("artifact validity missing/expired")
        cursor.execute(
            "SELECT dependency_artifact_id FROM kineticloop.safety_artifact_dependencies "
            "WHERE artifact_id=%s ORDER BY dependency_artifact_id",
            (row[0],),
        )
        edges = [str(r[0]) for r in cursor.fetchall()]
        if row[6] == "TIMELESS" and (
            not row[9]
            or row[9] not in edges
            or not row[10]
            or not any(str(r[0]) == row[9] and r[1] in {"POLICY", "POLICY_BUNDLE"} for r in rows)
        ):
            raise GuardRequired("TIMELESS approval missing")
        proofs.append(
            dict(
                zip(
                    (
                        "artifact_id",
                        "artifact_kind",
                        "artifact_identity",
                        "artifact_version",
                        "content_hash",
                        "artifact_revision",
                        "validity_kind",
                        "valid_from",
                        "valid_until",
                        "timeless_approval_policy",
                        "timeless_approval_reason",
                    ),
                    (
                        str(row[0]),
                        *row[1:7],
                        canonical_certificate_timestamp(row[7], "from"),
                        canonical_certificate_timestamp(row[8], "until") if row[8] else None,
                        row[9],
                        row[10],
                    ),
                    strict=True,
                )
            )
            | {"dependency_ids": edges}
        )
    nonroots = {edge for proof in proofs for edge in proof["dependency_ids"]}
    if set(map(str, roots)) != {str(r[0]) for r in rows} - nonroots:
        raise GuardRequired("artifact roots do not equal complete closure roots")
    return proofs, digest(proofs)


def _artifact_bindings(
    cursor: Cursor[Any],
    source: SourceBasis,
    proofs: list[dict[str, Any]],
    roots: tuple[UUID, ...],
) -> None:
    ids = [UUID(proof["artifact_id"]) for proof in proofs]
    cursor.execute(
        "SELECT id,ref_s05_id,ref_s19_id,ref_s48_id FROM kineticloop.safety_artifacts WHERE id=ANY(%s)",
        (ids,),
    )
    bindings = cursor.fetchall()
    cursor.execute(
        "WITH RECURSIVE policy_closure(id) AS ("
        "SELECT id FROM kineticloop.safety_artifacts WHERE id=ANY(%s) AND ref_s05_id=%s "
        "UNION SELECT e.dependency_artifact_id FROM policy_closure c "
        "JOIN kineticloop.safety_artifact_dependencies e ON e.artifact_id=c.id) "
        "SELECT DISTINCT a.ref_s48_id FROM policy_closure c JOIN kineticloop.safety_artifacts a "
        "ON a.id=c.id WHERE a.ref_s48_id IS NOT NULL",
        (ids, source.policy_id),
    )
    releases = {r[0] for r in cursor.fetchall()}
    nonroots = {UUID(edge) for proof in proofs for edge in proof["dependency_ids"]}
    if not artifact_bindings_match_activation(
        bindings,
        root_ids=set(roots),
        expected_root_ids=set(ids) - nonroots,
        active_policy_id=source.policy_id,
        selected_catalog_id=source.catalog_id,
        active_release_ids=releases,
    ):
        raise GuardRequired(
            "artifact closure does not match exact sealed policy/catalog/release basis"
        )


def _record(
    cursor: Cursor[Any], identity: PreparationIdentity, request: RecordProjection
) -> Mapping[str, Any]:
    if (
        type(request.source) is not SourceBasis
        or type(request.engine) is not ArtifactIdentity
        or not request.kind
        or type(request.window) is not tuple
        or len(request.window) != 2
        or not all(isinstance(value, str) and value for value in request.window)
        or not isinstance(request.content, Mapping)
        or not request.content
        or set(request.content) & {"revision", "provenance", "preparation", "server_revision"}
        or type(request.valid_until) is not datetime
        or request.valid_until.tzinfo is None
        or any(type(dep) is not Dependency for dep in request.dependencies)
    ):
        raise GuardRequired("typed computation without caller revision/provenance required")
    signatures = [(d.kind, d.key, d.collection) for d in request.dependencies]
    if len(signatures) != len(set(signatures)) or len(
        {(d.kind, d.key) for d in request.dependencies}
    ) != len(signatures):
        raise GuardRequired("duplicate dependency semantic key")
    projection, basis_hash, request_hash = projection_identity(identity.subject_id, request)
    cursor.execute(
        "SELECT typed_payload FROM kineticloop.projection_versions WHERE subject_id=%s AND id=%s",
        (identity.subject_id, projection),
    )
    prior = cursor.fetchone()
    if prior:
        history = prior[0]["preparation"]
        if history["owner"] != identity.key or history["request_hash"] != request_hash:
            raise IdempotencyConflict("immutable computation identity conflict")
        return history["outcome"]
    _verify_source(cursor, identity, request.source)
    requirements = _requirements(cursor, identity, request.source)
    matching = [r for r in requirements.values() if r["projection_kind"] == request.kind]
    expected = [
        {(d["kind"], d["key"], d.get("collection")) for d in r["dependencies"]} for r in matching
    ]
    if not expected or set(signatures) not in expected:
        raise GuardRequired("projection dependency signature incomplete/foreign")
    proof, _ = _artifacts(cursor, (request.engine.artifact_id,))
    _artifact_bindings(cursor, request.source, proof, (request.engine.artifact_id,))
    engine = next(p for p in proof if p["artifact_id"] == str(request.engine.artifact_id))
    if (
        engine["artifact_kind"],
        engine["artifact_identity"],
        engine["artifact_version"],
        engine["content_hash"],
    ) != (
        request.engine.artifact_kind,
        request.engine.artifact_identity,
        request.engine.artifact_version,
        request.engine.content_hash,
    ):
        raise GuardRequired("exact engine identity/hash required")
    if not any(
        d.kind == "ENGINE"
        and d.key == f"{request.engine.artifact_identity}:{request.engine.artifact_version}"
        for d in request.dependencies
    ):
        raise GuardRequired("ENGINE dependency must name exact computation engine")
    source = request.source
    deps = {}
    refs = {
        "POLICY": ("ref_s05_id", source.policy_id),
        "PROGRAM": ("ref_s06_id", source.program_id),
        "FACTSET": ("ref_s15_id", source.factset_id),
        "COLLECTION": ("ref_s15_id", source.factset_id),
        "MAPPING": ("ref_s20_id", source.mapping_id),
        "CATALOG": ("ref_s19_id", source.catalog_id),
    }
    for dep in request.dependencies:
        values: dict[str, Any] = {
            "id": uuid5(projection, f"{dep.kind}:{dep.key}"),
            "subject_id": identity.subject_id,
            "ref_s21_id": projection,
            "dependency_kind": dep.kind,
            "dependency_semantic_key": dep.key,
            "collection_signature": dep.collection,
        }
        if dep.kind == "FACT":
            if type(dep.fact_id) is not UUID:
                raise GuardRequired("FACT requires exact admitted actual member")
            cursor.execute(
                "SELECT 1 FROM kineticloop.factset_members WHERE subject_id=%s AND ref_s15_id=%s "
                "AND ref_s14_id=%s AND member_operation='SET'",
                (identity.subject_id, source.factset_id, dep.fact_id),
            )
            if not cursor.fetchone():
                raise GuardRequired("FACT not in exact source")
            values["ref_s14_id"] = dep.fact_id
        elif dep.fact_id is not None:
            raise GuardRequired("foreign FACT reference")
        if dep.kind in refs:
            field, value = refs[dep.kind]
            if value is None:
                raise GuardRequired("missing exact dependency reference")
            values[field] = value
        elif dep.kind not in {"FACT", "ENGINE"}:
            raise GuardRequired("unknown dependency kind")
        values["typed_payload"] = Jsonb(
            {
                "source_hash": source.source_hash,
                "window": list(request.window),
                "collection_digest": source.source_hash if dep.collection else None,
            }
        )
        deps[values["id"]] = values
    outcome = {
        "projection_id": str(projection),
        "revision": 1,
        "input_basis_hash": basis_hash,
        "dependency_ids": sorted(str(i) for i in deps),
        "executable": False,
    }
    cursor.execute("SELECT clock_timestamp()")
    now = cursor.fetchone()[0]  # type: ignore[index]
    if request.valid_until <= now:
        raise GuardRequired("explicit live projection validity required")
    values = {
        "id": projection,
        "subject_id": identity.subject_id,
        "projection_kind": request.kind,
        "input_basis_hash": basis_hash,
        "computed_at": now,
        "valid_until": request.valid_until,
        "content_hash": digest(wire(request.content)),
        "typed_payload": Jsonb(
            {
                "result": wire(request.content),
                "preparation": {
                    "version": "kl078-v1",
                    "owner": identity.key,
                    "request_hash": request_hash,
                    "source": wire(asdict(source)),
                    "engine": wire(asdict(request.engine)),
                    "window": list(request.window),
                    "outcome": outcome,
                },
            }
        ),
    }
    session = _source_preparation_session(
        cursor, "RecordProjection", identity.subject_id, {"S21": {projection: values}, "S22": deps}
    )
    session.insert("S21", values)
    for dep_values in deps.values():
        session.insert("S22", dep_values)
    session.validate_completion()
    return outcome


def _candidate(
    cursor: Cursor[Any], identity: PreparationIdentity, request: BuildManifest
) -> dict[str, Any]:
    _verify_source(cursor, identity, request.source)
    requirements = _requirements(cursor, identity, request.source)
    if (
        any(type(b) is not ProjectionBinding for b in request.bindings)
        or len(request.bindings) != len(requirements)
        or {b.role for b in request.bindings} != set(requirements)
        or len({b.projection_id for b in request.bindings}) != len(request.bindings)
    ):
        raise GuardRequired("exact nonduplicate policy role closure required")
    bindings, projections = [], []
    engine_ids = set()
    for binding in sorted(request.bindings, key=lambda b: b.role):
        cursor.execute(
            "SELECT projection_kind,input_basis_hash,typed_payload FROM kineticloop.projection_versions "
            "WHERE subject_id=%s AND id=%s",
            (identity.subject_id, binding.projection_id),
        )
        row = cursor.fetchone()
        if (
            row is None
            or row[0] != requirements[binding.role]["projection_kind"]
            or row[2].get("preparation", {}).get("source") != wire(asdict(request.source))
        ):
            raise GuardRequired("exact source-bound projection parent required")
        engine_ids.add(row[2]["preparation"]["engine"]["artifact_id"])
        cursor.execute(
            "SELECT dependency_kind,dependency_semantic_key,collection_signature,ref_s05_id,ref_s06_id,"
            "ref_s14_id,ref_s15_id,ref_s19_id,ref_s20_id FROM kineticloop.projection_dependencies "
            "WHERE subject_id=%s AND ref_s21_id=%s ORDER BY dependency_kind,dependency_semantic_key,id",
            (identity.subject_id, binding.projection_id),
        )
        deps = [
            dict(
                zip(
                    (
                        "projection_id",
                        "kind",
                        "key",
                        "collection",
                        "policy",
                        "program",
                        "fact",
                        "factset",
                        "catalog",
                        "mapping",
                    ),
                    (str(binding.projection_id), *r[:3], *(str(v) if v else None for v in r[3:])),
                    strict=True,
                )
            )
            for r in cursor.fetchall()
        ]
        if {(d["kind"], d["key"], d["collection"]) for d in deps} != {
            (d["kind"], d["key"], d.get("collection"))
            for d in requirements[binding.role]["dependencies"]
        }:
            raise GuardRequired("projection dependencies do not close required role")
        bindings.append(
            {"id": str(binding.projection_id), "role": binding.role, "basis_hash": row[1]}
        )
        projections.append(
            {
                "id": str(binding.projection_id),
                "role": binding.role,
                "projection_kind": row[0],
                "validated_basis_hash": row[1],
                "dependencies": deps,
            }
        )
    artifacts, artifact_hash = _artifacts(cursor, request.artifact_roots)
    if not engine_ids <= {a["artifact_id"] for a in artifacts}:
        raise GuardRequired("computation engines missing from artifact closure")
    _artifact_bindings(cursor, request.source, artifacts, request.artifact_roots)
    dependency_hash = digest(
        {
            "projections": projections,
            "catalog_id": wire(request.source.catalog_id),
            "mapping_id": wire(request.source.mapping_id),
        }
    )
    candidate = {
        "projection_bindings": bindings,
        "dependency_basis_hash": dependency_hash,
        "artifact_dependency_closure_hash": artifact_hash,
        "artifact_closure_ids": [a["artifact_id"] for a in artifacts],
        "artifact_root_ids": sorted(map(str, request.artifact_roots)),
    }
    candidate["manifest_hash"] = digest(wire({"source": asdict(request.source), **candidate}))
    return candidate


def _build(
    cursor: Cursor[Any], identity: PreparationIdentity, request: BuildManifest
) -> Mapping[str, Any]:
    if (
        not isinstance(request.key, str)
        or not request.key.strip()
        or type(request.source) is not SourceBasis
    ):
        raise GuardRequired("typed immutable build identity required")
    build = uuid5(_NAMESPACE, f"{identity.subject_id}:build:{request.key}")
    request_hash = digest(wire(asdict(request)))
    cursor.execute(
        "SELECT typed_payload FROM kineticloop.manifest_builds WHERE subject_id=%s AND id=%s",
        (identity.subject_id, build),
    )
    prior = cursor.fetchone()
    if prior:
        history = prior[0]["preparation"]
        if history["owner"] != identity.key or history["request_hash"] != request_hash:
            raise IdempotencyConflict("immutable build identity conflict")
        return history["begin_outcome"]
    candidate = _candidate(cursor, identity, request)
    outcome = {"build_id": str(build), "status": "BUILDING", "executable": False}
    candidate["preparation"] = {
        "version": "kl078-v1",
        "owner": identity.key,
        "request_hash": request_hash,
        "request": wire(asdict(request)),
        "begin_outcome": outcome,
    }
    source = request.source
    values = {
        "id": build,
        "subject_id": identity.subject_id,
        "build_identity": f"kl078:{request.key}",
        "status": "BUILDING",
        "error_code": None,
        "captured_epoch": source.epoch,
        "captured_input_frontier": source.frontier,
        "ref_s05_id": source.policy_id,
        "ref_s06_id": source.program_id,
        "ref_s15_id": source.factset_id,
        "ref_s21_id": UUID(candidate["projection_bindings"][0]["id"]),
        "typed_payload": Jsonb(candidate),
    }
    session = _source_preparation_session(
        cursor, "BuildManifest", identity.subject_id, {"S23": {build: values}}
    )
    session.insert("S23", values)
    session.validate_completion()
    return outcome


def _complete(
    cursor: Cursor[Any], identity: PreparationIdentity, request: CompleteManifest
) -> Mapping[str, Any]:
    cursor.execute(
        "SELECT status,typed_payload FROM kineticloop.manifest_builds "
        "WHERE subject_id=%s AND id=%s FOR UPDATE",
        (identity.subject_id, request.build_id),
    )
    row = cursor.fetchone()
    if row is None or row[1].get("preparation", {}).get("owner") != identity.key:
        raise GuardRequired("exact local build ownership required")
    payload = row[1]
    if row[0] in {"READY", "PUBLISHED"}:
        return payload["preparation"]["complete_outcome"]
    if row[0] != "BUILDING":
        raise GuardRequired("terminal build cannot reopen")
    outcome = {
        "build_id": str(request.build_id),
        "status": "READY",
        "dependency_basis_hash": payload["dependency_basis_hash"],
        "artifact_dependency_closure_hash": payload["artifact_dependency_closure_hash"],
        "manifest_hash": payload["manifest_hash"],
        "executable": False,
    }
    payload["preparation"]["complete_outcome"] = outcome
    assignments = {"status": "READY", "typed_payload": Jsonb(payload)}
    where = {"id": request.build_id, "subject_id": identity.subject_id}
    session = _source_preparation_session(
        cursor, "BuildManifest", identity.subject_id, {}, (assignments, where)
    )
    session.update("S23", assignments, where)
    session.validate_completion()
    return outcome


def _persist(cursor: Cursor[Any], identity: PreparationIdentity, request: Any) -> Mapping[str, Any]:
    _authenticate(cursor, identity)
    operation: Callable[[Cursor[Any], PreparationIdentity, Any], Mapping[str, Any]]
    if type(request) is RecordProjection:
        if (
            type(request.source) is not SourceBasis
            or type(request.engine) is not ArtifactIdentity
            or type(request.dependencies) is not tuple
            or any(type(dep) is not Dependency for dep in request.dependencies)
            or not isinstance(request.content, Mapping)
        ):
            raise GuardRequired("typed source/computation/dependency basis required")
        request = replace(
            request,
            content=wire(request.content),
            dependencies=tuple(sorted(request.dependencies, key=lambda dep: (dep.kind, dep.key))),
        )
        projection = projection_identity(identity.subject_id, request)[0]
        key = f"projection:{identity.subject_id}:{projection}"
        operation = _record
    elif type(request) is BuildManifest:
        key = f"manifest:{identity.subject_id}:{request.key}"
        operation = _build
    elif type(request) is CompleteManifest:
        return _complete(cursor, identity, request)
    else:
        raise GuardRequired("exact typed preparation request required")
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"kl078:{key}",))
    return operation(cursor, identity, request)


class PreparationService:
    def __init__(self, connection: Connection[Any], identity: PreparationIdentity):
        if type(identity) is not PreparationIdentity:
            raise GuardRequired("trusted preparation identity required")
        identity.__post_init__()
        self.connection, self.identity = connection, identity

    def capture_source(self, factset_id: UUID) -> SourceBasis:
        from psycopg.pq import TransactionStatus

        if self.connection.info.transaction_status is not TransactionStatus.IDLE:
            raise GuardRequired("source capture requires idle connection")
        with self.connection.transaction():
            cursor = self.connection.cursor()
            _authenticate(cursor, self.identity)
            return _source(cursor, self.identity, factset_id)

    def record_projection(self, request: RecordProjection) -> Mapping[str, Any]:
        if type(request) is not RecordProjection:
            raise GuardRequired("typed RecordProjection required")
        return _execute_source_preparation(self.connection, self.identity, request)

    def build_manifest(self, request: BuildManifest) -> Mapping[str, Any]:
        if type(request) is not BuildManifest:
            raise GuardRequired("typed BuildManifest required")
        return _execute_source_preparation(self.connection, self.identity, request)

    def complete_manifest(self, request: CompleteManifest) -> Mapping[str, Any]:
        if type(request) is not CompleteManifest or type(request.build_id) is not UUID:
            raise GuardRequired("typed CompleteManifest required")
        return _execute_source_preparation(self.connection, self.identity, request)
