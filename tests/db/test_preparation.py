from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Event
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError, DatabaseNamespace
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.factsets import (
    BeginBuild,
    BuilderIdentity,
    CanonicalViewService,
    CompleteFactset,
    SealFactset,
    WriteCandidate,
)
from kineticloop.persistence.preparation import (
    BuildManifest,
    CompleteManifest,
    Dependency,
    PreparationService,
    ProjectionBinding,
    RecordProjection,
)
from kineticloop.persistence.protocol_execution import ProtocolExecutionService
from kineticloop.persistence.transactions import (
    ArtifactIdentity,
    EventWrite,
    GuardRequired,
    IdempotencyConflict,
    RepositoryTransaction,
    RestrictedSqlSession,
    execute_command,
    execute_preparation,
)
from kineticloop.protocol.execution import ExecutionIdentity, PublishReady, digest
from kineticloop.protocol.factsets import EvidenceBasis, Member

_spec = spec_from_file_location(
    "kl078_migrations", Path(__file__).resolve().with_name("test_migrations.py")
)
assert _spec is not None and _spec.loader is not None
_migrations = module_from_spec(_spec)
_spec.loader.exec_module(_migrations)
HEAD_REVISION = _migrations.HEAD_REVISION
bootstrap_two_phase = _migrations.bootstrap_two_phase

ROOT = Path(__file__).resolve().parents[2]
LABELS = {"prep"}
AMBIENT = {
    "COMPOSE_PROJECT_NAME",
    "KINETICLOOP_DB_NAME",
    "COMPOSE_FILE",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "KINETICLOOP_DB_USER",
    "KINETICLOOP_DB_PASSWORD",
}


def owned_namespace(root: Path, head: str, label: str = "prep") -> DatabaseNamespace:
    if root.resolve() != ROOT or not re.fullmatch(r"[0-9a-f]{40}", head) or label not in LABELS:
        raise DatabaseLifecycleError("task/SHA/resolved-root/label mismatch")
    token = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    return DatabaseNamespace(
        f"kineticloop-kl078-{label}-{head[:7]}-{token}",
        f"kineticloop_kl078_{label}_{head[:7]}_{token}",
    )


class OwnedLifecycle(DatabaseLifecycle):
    def __init__(
        self, root: Path, head: str, *, environ: Mapping[str, str] | None = None, **kwargs: Any
    ):
        selected = owned_namespace(root, head)
        env = dict(os.environ if environ is None else environ)
        if AMBIENT & env.keys():
            raise DatabaseLifecycleError("ambient namespace/runtime override")
        self.head = head
        self.inventory: list[str] = []
        super().__init__(root, environ=env, **kwargs)
        self.namespace = selected
        self.validate()

    def validate(self) -> None:
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if self.head != actual:
            raise DatabaseLifecycleError("tested SHA is not exact HEAD")
        if (
            self.namespace != owned_namespace(self.root, self.head)
            or AMBIENT & self._base_environ.keys()
        ):
            raise DatabaseLifecycleError("foreign namespace or ambient override")

    def start(self, *, timeout_seconds: float = 60) -> None:
        self.validate()
        self.inventory.append("start")
        super().start(timeout_seconds=timeout_seconds)

    def reset(self, *, timeout_seconds: float = 60) -> Any:
        self.validate()
        self.inventory.append("reset")
        return super().reset(timeout_seconds=timeout_seconds)

    def destroy(self) -> None:
        self.validate()
        self.inventory.append("destroy")
        super().destroy()

    def compose_command(self, *args: str) -> list[str]:
        self.validate()
        return super().compose_command(*args)

    def bootstrap(self) -> dict[str, str]:
        self.validate()
        self.inventory.append("bootstrap_two_phase(selected_lifecycle)")
        urls = bootstrap_two_phase(self)
        with psycopg.connect(urls["admin"]) as db:
            assert db.execute("SELECT current_database()").fetchone() == (
                self.namespace.database_name,
            )
            assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
                HEAD_REVISION,
            )
        print("NAMESPACE", self.namespace, "MIGRATION", HEAD_REVISION)
        return urls


@pytest.fixture
def database_urls() -> Iterator[dict[str, str]]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    lifecycle = OwnedLifecycle(ROOT, head)
    started = time.monotonic()
    try:
        yield lifecycle.bootstrap()
    finally:
        lifecycle.validate()
        lifecycle.destroy()
        print("LIFECYCLE", lifecycle.inventory, "CLEANUP_OK", "elapsed", time.monotonic() - started)
        assert time.monotonic() - started < 120


def seed_sources(
    urls: dict[str, str], principal: str = "kl_test_subject_1_login"
) -> dict[str, Any]:
    (
        subject,
        policy,
        program,
        environment,
        engine,
        association,
        evidence,
        assertion,
        underlying,
        admission,
        fact,
    ) = [uuid4() for _ in range(11)]
    dependencies = (
        Dependency("COLLECTION", "actual-facts", "actual-facts-and-absence:v1"),
        Dependency("ENGINE", f"test:kl078-engine-{subject}:1"),
        Dependency("FACTSET", "sealed-input"),
        Dependency("POLICY", "selected-policy"),
        Dependency("PROGRAM", "selected-program"),
        Dependency("FACT", "actual-member", fact_id=fact),
    )
    requirements = [
        {"kind": d.kind, "key": d.key, "collection": d.collection} for d in dependencies
    ]
    body = {
        "factset_max_delta_depth": 1,
        "t2_invalidation_scopes": {"AcceptFactRevision": "TEST_ONLY"},
        "manifest_projection_requirements": {
            "EXPOSURE": {"projection_kind": "EXPOSURE", "dependencies": requirements}
        },
    }
    with psycopg.connect(urls["admin"], autocommit=True) as db:
        now_row = db.execute("SELECT clock_timestamp()").fetchone()
        assert now_row is not None
        now = now_row[0]
        from datetime import timedelta

        end = now + timedelta(hours=1)
        db.execute(
            "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) VALUES (%s,%s,'test:kl078','1',%s,%s)",
            (policy, subject, digest(body), Jsonb(body)),
        )
        db.execute(
            "INSERT INTO kineticloop.program_versions(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test:kl078',1)",
            (program, subject),
        )
        # Initial registration basis only: no live output pointers/frontier mutations.
        db.execute(
            "INSERT INTO kineticloop.user_decision_state(subject_id,input_frontier_hash,active_policy_bundle_id,active_program_id) VALUES (%s,%s,%s,%s)",
            (subject, digest("initial-registered-input"), policy, program),
        )
        db.execute(
            "INSERT INTO kineticloop.evidence_revisions(id,subject_id,source_connection_identity,source_object_type,source_object_identity,source_revision,trust_class,source_class,command_authority) VALUES (%s,%s,'kl078-test','actual','observation','1','USER_REPORTED','USER','NONE')",
            (evidence, subject),
        )
        db.execute(
            "INSERT INTO kineticloop.candidate_assertions(id,subject_id,assertion_family_identity,ref_s09_id) VALUES (%s,%s,'actual-member',%s)",
            (assertion, subject, evidence),
        )
        db.execute(
            "INSERT INTO kineticloop.underlying_events(id,subject_id,event_identity) VALUES (%s,%s,'actual-event')",
            (underlying, subject),
        )
        db.execute(
            "INSERT INTO kineticloop.event_association_decisions(id,subject_id,association_family_identity,association_state) VALUES (%s,%s,'actual-event','UNRESOLVED')",
            (association, subject),
        )
        db.execute(
            "INSERT INTO kineticloop.admission_decisions(id,subject_id,action_scope,decision,ref_s05_id,ref_s09_id,ref_s10_id) VALUES (%s,%s,'TEST_ONLY','ADMITTED',%s,%s,%s)",
            (admission, subject, policy, evidence, assertion),
        )
        db.execute(
            "INSERT INTO kineticloop.canonical_fact_revisions(id,subject_id,stable_fact_identity,fact_kind,fact_revision,ref_s10_id,ref_s11_id,ref_s13_id) VALUES (%s,%s,'actual-member','HEALTH_OBSERVATION',1,%s,%s,%s)",
            (fact, subject, assertion, underlying, admission),
        )
        db.execute(
            "INSERT INTO kineticloop.safety_artifacts(id,artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,ref_s05_id) VALUES (%s,'POLICY_BUNDLE',%s,'1',%s,'BOUNDED',%s,%s,%s)",
            (engine, f"test:kl078-engine-{subject}", digest(body), now, end, policy),
        )
        release, release_artifact = uuid4(), uuid4()
        db.execute(
            "INSERT INTO kineticloop.evaluation_releases(id,subject_id,release_namespace,release_version,content_hash) VALUES (%s,%s,'test:kl078','1',%s)",
            (release, subject, digest("test-release")),
        )
        db.execute(
            "INSERT INTO kineticloop.safety_artifacts(id,artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,ref_s48_id) VALUES (%s,'PROMPT',%s,'1',%s,'BOUNDED',%s,%s,%s)",
            (
                release_artifact,
                f"test:kl078-release-{subject}",
                digest("test-release"),
                now,
                end,
                release,
            ),
        )
        db.execute(
            "INSERT INTO kineticloop.safety_artifact_dependencies(artifact_id,dependency_artifact_id) VALUES (%s,%s)",
            (engine, release_artifact),
        )
    with psycopg.connect(urls["trusted_admin"], autocommit=True) as db:
        db.execute(
            "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
            (subject, policy, environment, principal),
        )
    return {
        "identity": ExecutionIdentity(
            RoleIdentity(str(uuid4()), ActorRole.TEST),
            subject,
            policy,
            environment,
            principal,
        ),
        "basis": EvidenceBasis((association,), (admission,), (), now.isoformat(), "TEST_ONLY"),
        "members": (
            Member("ASSOCIATION", "actual-event", "TEST_ONLY", association),
            Member("ADMISSION", "actual", "TEST_ONLY", admission),
            Member("FACT", "actual-member", "TEST_ONLY", fact),
        ),
        "program": program,
        "deps": dependencies,
        "engine": ArtifactIdentity(
            engine, "POLICY_BUNDLE", f"test:kl078-engine-{subject}", "1", digest(body)
        ),
        "end": end,
        "assertion": assertion,
        "underlying": underlying,
        "admission": admission,
    }


def factset(db: Any, seed: dict[str, Any], key: str, stage: str = "SEALED") -> UUID:
    identity = seed["identity"]
    api = CanonicalViewService(db, BuilderIdentity(identity.actor, identity.subject_id))
    with db.transaction():
        frontier, epoch = db.execute(
            "SELECT input_frontier_hash,authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (identity.subject_id,),
        ).fetchone()
    build = UUID(
        api.begin_build(
            BeginBuild(
                identity.subject_id,
                key,
                frontier,
                epoch,
                seed["program"],
                identity.policy_id,
                seed["basis"],
                max_delta_depth=1,
            )
        )["build_id"]
    )
    for n, member in enumerate(seed["members"]):
        api.write_candidate(WriteCandidate(identity.subject_id, f"{key}-{n}", build, n, member))
    if stage == "BUILDING":
        return build
    completion = api.complete_factset(
        CompleteFactset(identity.subject_id, "complete", build, len(seed["members"]))
    )
    if stage == "SEALED":
        api.seal_factset(SealFactset(identity.subject_id, f"seal-{key}", build, completion))
    print("ACTUAL_SOURCE", build, stage)
    return build


def pipeline(db: Any, seed: dict[str, Any], key: str) -> tuple[Any, Any, Any, Any]:
    api = PreparationService(db, seed["identity"])
    source = api.capture_source(factset(db, seed, key))
    record = RecordProjection(
        source,
        "EXPOSURE",
        seed["engine"],
        ("actual-start", "actual-end"),
        {"actual_fact_ids": [str(seed["members"][-1].revision_id)], "upper": "UNKNOWN"},
        seed["deps"],
        seed["end"],
    )
    projection = api.record_projection(record)
    request = BuildManifest(
        key,
        source,
        (ProjectionBinding("EXPOSURE", UUID(projection["projection_id"])),),
        (seed["engine"].artifact_id,),
    )
    build = api.build_manifest(request)
    ready = api.complete_manifest(CompleteManifest(UUID(build["build_id"])))
    assert_prepared_rows(db, seed, record, projection, request, ready)
    return record, projection, request, ready


def json_value(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def assert_prepared_rows(
    db: Any,
    seed: dict[str, Any],
    record: RecordProjection,
    projection: Mapping[str, Any],
    request: BuildManifest,
    ready: Mapping[str, Any],
) -> None:
    """Independently read source/output rows and recompute the canonical candidate proofs."""
    from kineticloop.protocol.authorization import canonical_certificate_timestamp

    source = record.source
    subject = seed["identity"].subject_id
    with db.transaction():
        actual_source = db.execute(
            "SELECT f.status,f.membership_digest,f.typed_payload,f.ref_s20_id,m.ref_s19_id "
            "FROM kineticloop.factset_revisions f LEFT JOIN kineticloop.exercise_mapping_decisions m "
            "ON m.subject_id=f.subject_id AND m.id=f.ref_s20_id WHERE f.subject_id=%s AND f.id=%s",
            (subject, source.factset_id),
        ).fetchone()
        assert actual_source is not None and actual_source[0] == "SEALED"
        assert source.source_hash == digest(json_value([str(source.factset_id), *actual_source]))
        assert actual_source[2]["captured_epoch"] == source.epoch
        assert actual_source[2]["captured_input_frontier"] == source.frontier
        assert actual_source[2]["program_revision_id"] == str(source.program_id)
        assert actual_source[2]["policy_id"] == str(source.policy_id)
        members = db.execute(
            "SELECT ref_s14_id FROM kineticloop.factset_members WHERE subject_id=%s AND ref_s15_id=%s AND member_operation='SET' AND ref_s14_id IS NOT NULL",
            (subject, source.factset_id),
        ).fetchall()
        assert {r[0] for r in members} == {
            m.revision_id for m in seed["members"] if m.kind == "FACT"
        }
        projection_row = db.execute(
            "SELECT row_to_json(r) FROM kineticloop.projection_versions r WHERE subject_id=%s AND id=%s",
            (subject, UUID(projection["projection_id"])),
        ).fetchone()[0]
        assert projection_row["revision"] == 1
        assert projection_row["projection_kind"] == record.kind
        assert projection_row["valid_until"] == record.valid_until.isoformat()
        assert projection_row["content_hash"] == digest(json_value(record.content))
        assert projection_row["typed_payload"]["result"] == json_value(record.content)
        canonical_deps = [
            asdict(dep) for dep in sorted(record.dependencies, key=lambda d: (d.kind, d.key))
        ]
        expected_basis = digest(
            json_value({"source": asdict(source), "dependencies": canonical_deps})
        )
        assert (
            projection_row["input_basis_hash"] == projection["input_basis_hash"] == expected_basis
        )
        provenance = projection_row["typed_payload"]["preparation"]
        assert provenance["version"] == "kl078-v1" and provenance["owner"] == seed["identity"].key
        assert provenance["source"] == json_value(asdict(source))
        assert provenance["engine"] == json_value(asdict(record.engine))
        assert provenance["window"] == list(record.window)
        canonical_request = json_value(asdict(record))
        canonical_request["dependencies"] = json_value(canonical_deps)
        assert provenance["request_hash"] == digest(canonical_request)
        assert provenance["outcome"] == dict(projection)
        dep_rows = [
            r[0]
            for r in db.execute(
                "SELECT row_to_json(r) FROM kineticloop.projection_dependencies r WHERE subject_id=%s AND ref_s21_id=%s ORDER BY dependency_kind,dependency_semantic_key,id",
                (subject, UUID(projection["projection_id"])),
            ).fetchall()
        ]
        assert {(r["dependency_kind"], r["dependency_semantic_key"]) for r in dep_rows} == {
            (d.kind, d.key) for d in record.dependencies
        }
        assert len(dep_rows) == len(record.dependencies)
        assert sorted(r["id"] for r in dep_rows) == projection["dependency_ids"]
        dependency_proofs = []
        for row in dep_rows:
            dep = next(
                d
                for d in record.dependencies
                if (d.kind, d.key) == (row["dependency_kind"], row["dependency_semantic_key"])
            )
            expected = {
                "ref_s05_id": str(source.policy_id) if dep.kind == "POLICY" else None,
                "ref_s06_id": str(source.program_id) if dep.kind == "PROGRAM" else None,
                "ref_s14_id": str(dep.fact_id) if dep.kind == "FACT" else None,
                "ref_s15_id": str(source.factset_id)
                if dep.kind in {"FACTSET", "COLLECTION"}
                else None,
                "ref_s19_id": str(source.catalog_id) if dep.kind == "CATALOG" else None,
                "ref_s20_id": str(source.mapping_id) if dep.kind == "MAPPING" else None,
            }
            assert {key: row[key] for key in expected} == expected
            assert row["ref_s21_id"] == projection["projection_id"] and row["subject_id"] == str(
                subject
            )
            assert row["collection_signature"] == dep.collection
            assert row["typed_payload"] == {
                "source_hash": source.source_hash,
                "window": list(record.window),
                "collection_digest": source.source_hash if dep.collection else None,
            }
            dependency_proofs.append(
                {
                    "projection_id": projection["projection_id"],
                    "kind": dep.kind,
                    "key": dep.key,
                    "collection": dep.collection,
                    "policy": expected["ref_s05_id"],
                    "program": expected["ref_s06_id"],
                    "fact": expected["ref_s14_id"],
                    "factset": expected["ref_s15_id"],
                    "catalog": expected["ref_s19_id"],
                    "mapping": expected["ref_s20_id"],
                }
            )
        build_row = db.execute(
            "SELECT row_to_json(r) FROM kineticloop.manifest_builds r WHERE subject_id=%s AND id=%s",
            (subject, UUID(ready["build_id"])),
        ).fetchone()[0]
        assert build_row["status"] == "READY"
        assert (
            build_row["captured_epoch"] == source.epoch
            and build_row["captured_input_frontier"] == source.frontier
        )
        assert (
            build_row["ref_s05_id"],
            build_row["ref_s06_id"],
            build_row["ref_s15_id"],
            build_row["ref_s21_id"],
        ) == (
            str(source.policy_id),
            str(source.program_id),
            str(source.factset_id),
            projection["projection_id"],
        )
        candidate = build_row["typed_payload"]
        policy = db.execute(
            "SELECT typed_payload FROM kineticloop.policy_bundles WHERE subject_id=%s AND id=%s",
            (subject, source.policy_id),
        ).fetchone()[0]
        assert {b["role"] for b in candidate["projection_bindings"]} == set(
            policy["manifest_projection_requirements"]
        )
        assert candidate["projection_bindings"] == [
            {"id": projection["projection_id"], "role": "EXPOSURE", "basis_hash": expected_basis}
        ]
        expected_dependency_hash = digest(
            {
                "projections": [
                    {
                        "id": projection["projection_id"],
                        "role": "EXPOSURE",
                        "projection_kind": record.kind,
                        "validated_basis_hash": expected_basis,
                        "dependencies": dependency_proofs,
                    }
                ],
                "catalog_id": json_value(source.catalog_id),
                "mapping_id": json_value(source.mapping_id),
            }
        )
        assert (
            candidate["dependency_basis_hash"]
            == ready["dependency_basis_hash"]
            == expected_dependency_hash
        )
        artifact_rows = db.execute(
            "WITH RECURSIVE closure(id) AS (SELECT id FROM kineticloop.safety_artifacts WHERE id=ANY(%s) UNION SELECT e.dependency_artifact_id FROM closure c JOIN kineticloop.safety_artifact_dependencies e ON e.artifact_id=c.id) "
            "SELECT a.id,a.artifact_kind,a.artifact_identity,a.artifact_version,a.content_hash,a.revision,a.validity_kind,a.valid_from,a.valid_until,a.timeless_approval_policy,a.timeless_approval_reason FROM closure c JOIN kineticloop.safety_artifacts a ON a.id=c.id ORDER BY a.id",
            (list(request.artifact_roots),),
        ).fetchall()
        artifact_proofs = []
        for r in artifact_rows:
            edges = [
                str(e[0])
                for e in db.execute(
                    "SELECT dependency_artifact_id FROM kineticloop.safety_artifact_dependencies WHERE artifact_id=%s ORDER BY dependency_artifact_id",
                    (r[0],),
                ).fetchall()
            ]
            artifact_proofs.append(
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
                            str(r[0]),
                            *r[1:7],
                            canonical_certificate_timestamp(r[7], "from"),
                            canonical_certificate_timestamp(r[8], "until") if r[8] else None,
                            r[9],
                            r[10],
                        ),
                        strict=True,
                    )
                )
                | {"dependency_ids": edges}
            )
        assert candidate["artifact_closure_ids"] == [str(r[0]) for r in artifact_rows]
        assert candidate["artifact_root_ids"] == sorted(map(str, request.artifact_roots))
        assert (
            candidate["artifact_dependency_closure_hash"]
            == ready["artifact_dependency_closure_hash"]
            == digest(artifact_proofs)
        )
        content_candidate = {
            key: value
            for key, value in candidate.items()
            if key not in {"manifest_hash", "preparation"}
        }
        assert (
            candidate["manifest_hash"]
            == ready["manifest_hash"]
            == digest({"source": json_value(asdict(source)), **content_candidate})
        )
        assert candidate["preparation"]["owner"] == seed["identity"].key
        assert candidate["preparation"]["request"] == json_value(asdict(request))
        assert candidate["preparation"]["complete_outcome"] == dict(ready)
    print(
        "PERSISTED_PROOFS",
        json.dumps(
            {
                "source": str(source.factset_id),
                "source_hash": source.source_hash,
                "projection": projection_row["id"],
                "basis_hash": expected_basis,
                "dependency_ids": [r["id"] for r in dep_rows],
                "build": build_row["id"],
                "dependency_basis_hash": expected_dependency_hash,
                "artifact_closure_ids": candidate["artifact_closure_ids"],
                "artifact_hash": digest(artifact_proofs),
                "manifest_hash": candidate["manifest_hash"],
            },
            sort_keys=True,
        ),
    )


def publication(
    seed: dict[str, Any], request: BuildManifest, ready: Mapping[str, Any], key: str
) -> PublishReady:
    source = request.source
    return PublishReady(
        seed["identity"].subject_id,
        key,
        UUID(ready["build_id"]),
        source.factset_id,
        source.frontier,
        source.epoch,
        source.program_id,
        source.policy_id,
        ready["dependency_basis_hash"],
        ready["artifact_dependency_closure_hash"],
    )


def state(db: Any, subject: UUID, *, preparation: bool = False) -> Any:
    tables = [
        "command_receipts",
        "domain_events",
        "outbox_deliveries",
        "decision_manifests",
        "manifest_projection_bindings",
        "authorization_issuances",
        "daily_plan_heads",
        "workout_sessions",
        "execution_bindings",
        "planning_intents",
    ]
    if preparation:
        tables += ["projection_versions", "projection_dependencies", "manifest_builds"]
    with db.transaction():
        row = db.execute(
            "SELECT row_to_json(s) FROM kineticloop.user_decision_state s WHERE subject_id=%s",
            (subject,),
        ).fetchone()
        counts = [
            db.execute(
                f"SELECT count(*) FROM kineticloop.{table} WHERE subject_id=%s", (subject,)
            ).fetchone()[0]
            for table in tables
        ]
        rows = [
            db.execute(
                f"SELECT row_to_json(r) FROM kineticloop.{table} r WHERE subject_id=%s ORDER BY id",
                (subject,),
            ).fetchall()
            for table in tables
        ]
    return row, counts, rows


def history(db: Any, subject: UUID) -> Any:
    with db.transaction():
        return [
            db.execute(
                f"SELECT row_to_json(r) FROM kineticloop.{table} r WHERE subject_id=%s ORDER BY id",
                (subject,),
            ).fetchall()
            for table in ("projection_versions", "projection_dependencies", "manifest_builds")
        ]


def input_revision(db: Any, seed: dict[str, Any], key: str) -> UUID:
    subject = seed["identity"].subject_id
    receipt, event, revision = uuid4(), uuid4(), uuid4()

    def operation(tx: RepositoryTransaction) -> Any:
        tx.lock_subject()
        row = db.execute(
            "SELECT authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (subject,),
        ).fetchone()
        assert row is not None
        epoch = row[0]

        def mutation(session: RestrictedSqlSession) -> Any:
            session.insert(
                "S14",
                {
                    "id": revision,
                    "subject_id": subject,
                    "stable_fact_identity": key,
                    "fact_kind": "HEALTH_OBSERVATION",
                    "fact_revision": 1,
                    "ref_s10_id": seed["assertion"],
                    "ref_s11_id": seed["underlying"],
                    "ref_s13_id": seed["admission"],
                },
            )
            session.insert(
                "S43",
                {
                    "id": uuid4(),
                    "subject_id": subject,
                    "event_kind": "EPOCH_INVALIDATED",
                    "invalidated_epoch": epoch + 1,
                    "scope": "TEST_ONLY",
                    "causation_key": key,
                    "ref_s02_id": receipt,
                },
            )
            session.update(
                "S01",
                {"input_frontier_hash": digest(key), "authorization_epoch": epoch + 1},
                {"subject_id": subject},
            )
            return {"fact_id": str(revision), "epoch": epoch + 1}

        return tx.idempotent_outcome(
            receipt_id=receipt,
            actor_scope="test",
            client_key=key,
            request_hash=digest(key),
            mutation=mutation,
            invalidation_scope="TEST_ONLY",
            event=EventWrite(
                event, "FACT", str(revision), 1, "ACTUAL_INPUT_CHANGED", "canonical", uuid4()
            ),
        )

    execute_command(db, "AcceptFactRevision", subject, operation)
    return revision


def revoke(urls: dict[str, str], seed: dict[str, Any]) -> None:
    from kineticloop.contracts.commands import RevokeArtifact, TransactionBoundary, TrustedActor
    from kineticloop.contracts.safety_registry import revocation_payload_hash
    from kineticloop.persistence.safety_registry import revoke_artifact

    with psycopg.connect(urls["admin"]) as db:
        now_row = db.execute("SELECT clock_timestamp()").fetchone()
        assert now_row is not None
        now = now_row[0]
    command = RevokeArtifact(
        schema_version="kineticloop-command-v1",
        command_kind="RevokeArtifact",
        boundary=TransactionBoundary.T2_GLOBAL,
        command_id=str(uuid4()),
        actor=TrustedActor(
            schema="kineticloop-role-identity-v1", identity_id=str(uuid4()), role=ActorRole.ADMIN
        ),
        idempotency_key="kl078-revoke",
        request_hash=digest("kl078-revoke"),
        subject_id=None,
        explicit_scope="global:safety-registry",
        artifact_id=str(seed["engine"].artifact_id),
        artifact_content_hash=seed["engine"].content_hash,
        revocation_payload_hash=revocation_payload_hash(effective_at=now, reason_code="TEST"),
        causation_incident_id=str(uuid4()),
    )
    with psycopg.connect(urls["trusted_admin"]) as db:
        revoke_artifact(db, command, effective_at=now, reason_code="TEST")


def test_owner_pipeline(database_urls: dict[str, str]) -> None:
    seed = seed_sources(database_urls)
    with psycopg.connect(database_urls["admin"]) as db:
        api = PreparationService(db, seed["identity"])
        source = api.capture_source(factset(db, seed, "positive"))
        before = state(db, seed["identity"].subject_id)
        record = RecordProjection(
            source,
            "EXPOSURE",
            seed["engine"],
            ("actual-start", "actual-end"),
            {"upper": "UNKNOWN"},
            seed["deps"],
            seed["end"],
        )
        projection = api.record_projection(record)
        assert state(db, seed["identity"].subject_id) == before
        build_request = BuildManifest(
            "positive",
            source,
            (ProjectionBinding("EXPOSURE", UUID(projection["projection_id"])),),
            (seed["engine"].artifact_id,),
        )
        building = api.build_manifest(build_request)
        with db.transaction():
            captured_build_result = db.execute(
                "SELECT row_to_json(r) FROM kineticloop.manifest_builds r WHERE id=%s",
                (UUID(building["build_id"]),),
            ).fetchone()
            assert captured_build_result is not None
            captured_build = captured_build_result[0]
        assert captured_build["status"] == "BUILDING"
        assert state(db, seed["identity"].subject_id) == before
        ready = api.complete_manifest(CompleteManifest(UUID(building["build_id"])))
        assert state(db, seed["identity"].subject_id) == before
        with db.transaction():
            assert db.execute(
                "SELECT revision FROM kineticloop.projection_versions WHERE id=%s",
                (UUID(projection["projection_id"]),),
            ).fetchone() == (1,)
            assert db.execute(
                "SELECT count(*) FROM kineticloop.projection_dependencies WHERE ref_s21_id=%s",
                (UUID(projection["projection_id"]),),
            ).fetchone() == (len(seed["deps"]),)
        assert_prepared_rows(db, seed, record, projection, build_request, ready)
        with db.transaction():
            completed_build_result = db.execute(
                "SELECT row_to_json(r) FROM kineticloop.manifest_builds r WHERE id=%s",
                (UUID(building["build_id"]),),
            ).fetchone()
            assert completed_build_result is not None
            completed_build = completed_build_result[0]
        assert {
            k: v for k, v in completed_build.items() if k not in {"status", "typed_payload"}
        } == {k: v for k, v in captured_build.items() if k not in {"status", "typed_payload"}}
        ready_payload = json_value(completed_build["typed_payload"])
        ready_payload["preparation"].pop("complete_outcome")
        assert ready_payload == captured_build["typed_payload"]
        result = ProtocolExecutionService(db, seed["identity"]).publish(
            publication(seed, build_request, ready, "publish")
        )
        after = state(db, seed["identity"].subject_id)
        assert after[1][:5] == [n + 1 for n in before[1][:5]]
        assert after[1][5:] == before[1][5:]
        assert after[0][0]["current_manifest_id"] == result["manifest_id"]
        assert after[0][0]["decision_generation"] == before[0][0]["decision_generation"] + 1
        with db.transaction():
            manifest_result = db.execute(
                "SELECT row_to_json(r) FROM kineticloop.decision_manifests r WHERE id=%s",
                (UUID(result["manifest_id"]),),
            ).fetchone()
            assert manifest_result is not None
            manifest = manifest_result[0]
            bindings = db.execute(
                "SELECT projection_role,ref_s21_id,validated_basis_hash FROM kineticloop.manifest_projection_bindings WHERE ref_s24_id=%s",
                (UUID(result["manifest_id"]),),
            ).fetchall()
            assert bindings == [
                ("EXPOSURE", UUID(projection["projection_id"]), projection["input_basis_hash"])
            ]
            assert (
                manifest["ref_s15_id"],
                manifest["ref_s23_id"],
                manifest["ref_s05_id"],
                manifest["ref_s06_id"],
            ) == (
                str(source.factset_id),
                ready["build_id"],
                str(source.policy_id),
                str(source.program_id),
            )
            assert manifest["manifest_hash"] == ready["manifest_hash"]
            assert (
                manifest["input_frontier_hash"] == source.frontier
                and manifest["captured_epoch"] == source.epoch
            )
            assert manifest["dependency_closure_hash"] == digest(
                {
                    "dependency_basis_hash": ready["dependency_basis_hash"],
                    "artifact_dependency_closure_hash": ready["artifact_dependency_closure_hash"],
                }
            )
            assert db.execute(
                "SELECT status FROM kineticloop.manifest_builds WHERE id=%s",
                (UUID(ready["build_id"]),),
            ).fetchone() == ("PUBLISHED",)
            assert db.execute(
                "SELECT status FROM kineticloop.command_receipts WHERE id=%s",
                (UUID(result["receipt_id"]),),
            ).fetchone() == ("SUCCEEDED",)
            assert db.execute(
                "SELECT ref_s02_id FROM kineticloop.domain_events WHERE id=%s",
                (UUID(result["event_id"]),),
            ).fetchone() == (UUID(result["receipt_id"]),)
            assert db.execute(
                "SELECT count(*) FROM kineticloop.outbox_deliveries WHERE subject_id=%s AND ref_s03_id=%s",
                (seed["identity"].subject_id, UUID(result["event_id"])),
            ).fetchone() == (1,)
        print("OWNER_OUTPUT", projection, ready, result)


def test_basis_denials(database_urls: dict[str, str]) -> None:
    seed = seed_sources(database_urls)
    subject = seed["identity"].subject_id
    with psycopg.connect(database_urls["admin"]) as db:
        api = PreparationService(db, seed["identity"])
        for stage in ("BUILDING", "READY"):
            build = factset(db, seed, f"nonsealed-{stage}", stage)
            with pytest.raises(GuardRequired):
                api.capture_source(build)
        record, projection, request, ready = pipeline(db, seed, "basis")
        peer = seed_sources(database_urls, "kl_test_subject_2_login")
        peer_source = PreparationService(db, peer["identity"]).capture_source(
            factset(db, peer, "peer")
        )
        with pytest.raises(GuardRequired):
            api.record_projection(replace(record, source=peer_source))
        for missing in (None, uuid4()):
            with pytest.raises(GuardRequired):
                api.capture_source(missing)  # type: ignore[arg-type]
        before = state(db, subject, preparation=True)
        for bad_source in (
            replace(record.source, factset_id=uuid4()),
            replace(record.source, source_hash="foreign"),
            replace(record.source, epoch=99),
            replace(record.source, frontier="stale"),
            replace(record.source, program_id=uuid4()),
            replace(record.source, policy_id=uuid4()),
        ):
            with pytest.raises(GuardRequired):
                api.record_projection(replace(record, source=bad_source))
            assert state(db, subject, preparation=True) == before
        for bad in (
            replace(record, dependencies=()),
            replace(record, dependencies=record.dependencies[:-1]),
            replace(record, dependencies=record.dependencies + (record.dependencies[0],)),
            replace(
                record,
                dependencies=tuple(
                    replace(d, fact_id=uuid4()) if d.kind == "FACT" else d
                    for d in record.dependencies
                ),
            ),
        ):
            with pytest.raises((GuardRequired, IdempotencyConflict)):
                api.record_projection(bad)
            assert state(db, subject, preparation=True) == before
        for bad in (
            replace(request, key="missing", bindings=()),
            replace(request, key="duplicate", bindings=request.bindings * 2),
            replace(request, key="foreign", bindings=(ProjectionBinding("EXPOSURE", uuid4()),)),
            replace(request, key="role", bindings=(replace(request.bindings[0], role="OTHER"),)),
            replace(request, key="artifact", artifact_roots=(uuid4(),)),
            replace(
                request,
                key="foreign-artifact-policy",
                artifact_roots=(seed["engine"].artifact_id, peer["engine"].artifact_id),
            ),
        ):
            with pytest.raises(GuardRequired):
                api.build_manifest(bad)
            assert state(db, subject, preparation=True) == before
        alien = PreparationService(
            db, replace(seed["identity"], actor=RoleIdentity(str(uuid4()), ActorRole.TEST))
        )
        with pytest.raises(GuardRequired):
            alien.complete_manifest(CompleteManifest(UUID(ready["build_id"])))
        for values in (
            {"captured_epoch": 999},
            {"captured_input_frontier": digest("relabel")},
            {"status": "BUILDING"},
            {"typed_payload": Jsonb({})},
        ):

            def relabel(session: RestrictedSqlSession) -> Any:
                return session.update(
                    "S23", values, {"id": UUID(ready["build_id"]), "subject_id": subject}
                )

            with pytest.raises(GuardRequired):
                execute_preparation(db, "BuildManifest", subject, relabel)
            assert state(db, subject, preparation=True) == before
        pub = publication(seed, request, ready, "denials")
        execution = ProtocolExecutionService(db, seed["identity"])
        for bad in (
            replace(pub, expected_authorization_epoch=99),
            replace(pub, expected_input_frontier_hash=digest("stale")),
            replace(pub, sealed_factset_id=uuid4()),
            replace(pub, program_revision_id=uuid4()),
            replace(pub, policy_id=uuid4()),
            replace(pub, dependency_basis_hash=digest("foreign")),
            replace(pub, artifact_dependency_closure_hash=digest("foreign")),
            replace(pub, build_id=uuid4()),
        ):
            with pytest.raises((GuardRequired, ValueError)):
                execution.publish(bad)
            assert state(db, subject, preparation=True) == before

        # Real T2-IN invalidates captured epoch/frontier, without touching preparation history.
        original_history = history(db, subject)
        new_fact = input_revision(db, seed, "actual-input-update")
        after_input = state(db, subject, preparation=True)
        with pytest.raises(GuardRequired):
            execution.publish(replace(pub, key="actual-stale"))
        assert state(db, subject, preparation=True) == after_input
        assert history(db, subject) == original_history
        with pytest.raises(IdempotencyConflict):
            api.build_manifest(
                replace(request, source=replace(request.source, epoch=request.source.epoch + 1))
            )
        seed["members"] += (Member("FACT", "new-actual", "TEST_ONLY", new_fact),)
        fresh_record, fresh_projection, fresh_request, fresh_ready = pipeline(
            db, seed, "fresh-after-input"
        )
        assert fresh_projection["projection_id"] != projection["projection_id"]
        assert fresh_projection["revision"] == 1
        # Live projection expires according to real trusted PG time. No status/hash seeds.
        from datetime import timedelta

        with db.transaction():
            now_row = db.execute("SELECT clock_timestamp()").fetchone()
            assert now_row is not None
            now = now_row[0]
        expiry_source = api.capture_source(factset(db, seed, "expiry-source"))
        expires = replace(
            fresh_record, source=expiry_source, valid_until=now + timedelta(seconds=1)
        )
        exp_projection = api.record_projection(expires)
        exp_request = replace(
            fresh_request,
            key="expiry",
            source=expiry_source,
            bindings=(ProjectionBinding("EXPOSURE", UUID(exp_projection["projection_id"])),),
        )
        exp_build = api.build_manifest(exp_request)
        exp_ready = api.complete_manifest(CompleteManifest(UUID(exp_build["build_id"])))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with db.transaction():
                clock_row = db.execute("SELECT clock_timestamp()").fetchone()
                assert clock_row is not None
                clock = clock_row[0]
            if clock >= expires.valid_until:
                break
        assert clock >= expires.valid_until
        expired_baseline = state(db, subject, preparation=True)
        with pytest.raises(GuardRequired):
            execution.publish(publication(seed, exp_request, exp_ready, "expired"))
        assert state(db, subject, preparation=True) == expired_baseline
        # Fresh candidate is revoked through actual SafetyRegistry management owner.
        _, _, rev_request, rev_ready = pipeline(db, seed, "revoked-input")
        revoke(database_urls, seed)
        revoked_baseline = state(db, subject, preparation=True)
        with pytest.raises(GuardRequired):
            execution.publish(publication(seed, rev_request, rev_ready, "revoked"))
        assert state(db, subject, preparation=True) == revoked_baseline


def test_immutable_replay(database_urls: dict[str, str]) -> None:
    seed = seed_sources(database_urls)
    with psycopg.connect(database_urls["admin"]) as db:
        record, projection, request, ready = pipeline(db, seed, "replay")
        api = PreparationService(db, seed["identity"])
        before = history(db, seed["identity"].subject_id)
        for _ in range(2):
            assert api.record_projection(record) == projection
            assert api.build_manifest(request)["build_id"] == ready["build_id"]
            assert api.complete_manifest(CompleteManifest(UUID(ready["build_id"]))) == ready
        assert history(db, seed["identity"].subject_id) == before
        for bad in (
            replace(record, content={"upper": 0}),
            replace(record, window=("changed", "end")),
            replace(record, content={"revision": 9}),
            replace(record, content={"provenance": "caller"}),
        ):
            with pytest.raises((GuardRequired, IdempotencyConflict)):
                api.record_projection(bad)
        with pytest.raises(IdempotencyConflict):
            api.build_manifest(replace(request, artifact_roots=(uuid4(),)))
        execution = ProtocolExecutionService(db, seed["identity"])
        pub = publication(seed, request, ready, "publish-replay")
        first = execution.publish(pub)
        after = state(db, seed["identity"].subject_id, preparation=True)
        published_history = history(db, seed["identity"].subject_id)
        assert api.record_projection(record) == projection
        assert api.complete_manifest(CompleteManifest(UUID(ready["build_id"]))) == ready
        replay = execution.publish(pub)
        assert replay["manifest_id"] == first["manifest_id"] and replay["executable"] is False
        assert state(db, seed["identity"].subject_id, preparation=True) == after
        assert history(db, seed["identity"].subject_id) == published_history
        new_fact = input_revision(db, seed, "replay-actual-input")
        seed["members"] += (Member("FACT", "replay-new-actual", "TEST_ONLY", new_fact),)
        _, _, next_request, next_ready = pipeline(db, seed, "next-independent")
        second = execution.publish(publication(seed, next_request, next_ready, "next-publish"))
        second_state = state(db, seed["identity"].subject_id, preparation=True)
        assert second["manifest_id"] != first["manifest_id"]
        assert api.record_projection(record) == projection
        assert api.complete_manifest(CompleteManifest(UUID(ready["build_id"]))) == ready
        old_replay = execution.publish(pub)
        assert old_replay["manifest_id"] == first["manifest_id"]
        assert state(db, seed["identity"].subject_id, preparation=True) == second_state
        published_history = history(db, seed["identity"].subject_id)
        for kind, mutate in [
            (
                "RecordProjection",
                lambda s: s.update(
                    "S21",
                    {"typed_payload": Jsonb({})},
                    {
                        "subject_id": seed["identity"].subject_id,
                        "id": UUID(projection["projection_id"]),
                    },
                ),
            ),
            (
                "BuildManifest",
                lambda s: s.update(
                    "S23",
                    {"status": "BUILDING"},
                    {"subject_id": seed["identity"].subject_id, "id": UUID(ready["build_id"])},
                ),
            ),
        ]:
            with pytest.raises(GuardRequired):
                execute_preparation(db, kind, seed["identity"].subject_id, mutate)
        assert history(db, seed["identity"].subject_id) == published_history


def test_duplicate_rollback(database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    seed = seed_sources(database_urls)
    with psycopg.connect(database_urls["admin"]) as db:
        record, projection, request, ready = pipeline(db, seed, "rollback-base")
        before = state(db, seed["identity"].subject_id, preparation=True)
        original_insert, original_update = RestrictedSqlSession.insert, RestrictedSqlSession.update
        for fail_kind, ordinal in [("S21", 1), ("S22", 3)]:
            calls = 0

            def failing(self: Any, kind: str, values: Any) -> int:
                nonlocal calls
                result = original_insert(self, kind, values)
                if kind == fail_kind:
                    calls += 1
                    if calls == ordinal:
                        raise RuntimeError("injected closure failure")
                return result

            with monkeypatch.context() as patch:
                patch.setattr(RestrictedSqlSession, "insert", failing)
                # New window keeps natural identity and conflicts; new sealed basis is required.
                other = factset(db, seed, f"rollback-{fail_kind}")
                changed = replace(
                    record, source=PreparationService(db, seed["identity"]).capture_source(other)
                )
                baseline = state(db, seed["identity"].subject_id, preparation=True)
                with pytest.raises(RuntimeError):
                    PreparationService(db, seed["identity"]).record_projection(changed)
                assert state(db, seed["identity"].subject_id, preparation=True) == baseline
        api = PreparationService(db, seed["identity"])
        for phase in ("before", "after"):
            building = api.build_manifest(replace(request, key=f"rollback-ready-{phase}"))
            baseline = history(db, seed["identity"].subject_id)
            authority_baseline = state(db, seed["identity"].subject_id)

            def failing_update(self: Any, kind: str, values: Any, where: Any) -> int:
                if kind == "S23" and phase == "before":
                    raise RuntimeError("injected READY failure")
                result = original_update(self, kind, values, where)
                if kind == "S23":
                    raise RuntimeError("injected READY failure")
                return result

            with monkeypatch.context() as patch:
                patch.setattr(RestrictedSqlSession, "update", failing_update)
                with pytest.raises(RuntimeError):
                    api.complete_manifest(CompleteManifest(UUID(building["build_id"])))
            assert history(db, seed["identity"].subject_id) == baseline
            assert state(db, seed["identity"].subject_id) == authority_baseline
        # Actual T3 rollback even after its generation update, without replacing any guard.
        _, _, publish_request, publish_ready = pipeline(db, seed, "t3-rollback")
        authority_baseline = state(db, seed["identity"].subject_id, preparation=True)

        def fail_t3(self: Any, kind: str, values: Any, where: Any) -> int:
            result = original_update(self, kind, values, where)
            if kind == "S01":
                raise RuntimeError("injected after T3 head/generation")
            return result

        with monkeypatch.context() as patch:
            patch.setattr(RestrictedSqlSession, "update", fail_t3)
            with pytest.raises(RuntimeError):
                ProtocolExecutionService(db, seed["identity"]).publish(
                    publication(seed, publish_request, publish_ready, "t3-rollback")
                )
        assert state(db, seed["identity"].subject_id, preparation=True) == authority_baseline
        # Explicit row/advisory lock barriers, with observed PG waiting, no sleeps.
        for mode in ("projection", "build", "complete"):
            held, release, waiter_started = Event(), Event(), Event()
            new_source = api.capture_source(factset(db, seed, f"duplicate-{mode}"))
            duplicate_record = replace(record, source=new_source)
            duplicate_projection = (
                api.record_projection(duplicate_record) if mode != "projection" else None
            )
            duplicate_request = (
                replace(
                    request,
                    key=f"duplicate-{mode}",
                    source=new_source,
                    bindings=(
                        ProjectionBinding("EXPOSURE", UUID(duplicate_projection["projection_id"])),
                    ),
                )
                if duplicate_projection
                else None
            )
            raced_build: Any = None
            if mode == "complete":
                assert duplicate_request is not None
                raced_build = api.build_manifest(duplicate_request)
            pids: dict[str, int] = {}
            old_history = history(db, seed["identity"].subject_id)

            def action(contender: Any) -> Any:
                owner = PreparationService(contender, seed["identity"])
                if mode == "projection":
                    return owner.record_projection(duplicate_record)
                if mode == "build":
                    assert duplicate_request is not None
                    return owner.build_manifest(duplicate_request)
                return owner.complete_manifest(CompleteManifest(UUID(raced_build["build_id"])))

            def first() -> Any:
                with psycopg.connect(database_urls["admin"]) as contender:
                    pids["first"] = contender.info.backend_pid

                    # Pause after first actual write while the local lock remains held.
                    def block_insert(self: Any, kind: str, values: Any) -> int:
                        result = original_insert(self, kind, values)
                        if contender.info.backend_pid == pids["first"] and kind in {"S21", "S23"}:
                            held.set()
                            assert release.wait(8)
                        return result

                    def block_update(self: Any, kind: str, values: Any, where: Any) -> int:
                        result = original_update(self, kind, values, where)
                        if contender.info.backend_pid == pids["first"] and kind == "S23":
                            held.set()
                            assert release.wait(8)
                        return result

                    with monkeypatch.context() as patch:
                        patch.setattr(RestrictedSqlSession, "insert", block_insert)
                        patch.setattr(RestrictedSqlSession, "update", block_update)
                        return action(contender)

            def second() -> Any:
                with psycopg.connect(database_urls["admin"]) as contender:
                    pids["second"] = contender.info.backend_pid
                    waiter_started.set()
                    return action(contender)

            with ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(first)
                assert held.wait(8)
                b = pool.submit(second)
                assert waiter_started.wait(8)
                deadline = time.monotonic() + 5
                observed = False
                try:
                    while time.monotonic() < deadline:
                        with db.transaction():
                            blocked_row = db.execute(
                                "SELECT pg_blocking_pids(%s)", (pids["second"],)
                            ).fetchone()
                            assert blocked_row is not None
                            blockers = blocked_row[0]
                        if pids["first"] in blockers:
                            observed = True
                            break
                    assert observed
                    print("OBSERVED_LOCAL_BLOCKER", mode, pids)
                finally:
                    release.set()
                winner = a.result(timeout=8)
                assert winner == b.result(timeout=8)
            new_history = history(db, seed["identity"].subject_id)
            old_by_table = [{r[0]["id"]: r[0] for r in rows} for rows in old_history]
            new_by_table = [{r[0]["id"]: r[0] for r in rows} for rows in new_history]
            for table_index, old_rows in enumerate(old_by_table):
                for row_id, row in old_rows.items():
                    if mode == "complete" and table_index == 2 and row_id == winner["build_id"]:
                        compare = json_value(new_by_table[table_index][row_id])
                        compare["status"] = "BUILDING"
                        compare["typed_payload"]["preparation"].pop("complete_outcome")
                        assert compare == row
                    else:
                        assert new_by_table[table_index][row_id] == row
            if mode == "projection":
                assert [len(rows) for rows in new_history] == [
                    len(old_history[0]) + 1,
                    len(old_history[1]) + len(duplicate_record.dependencies),
                    len(old_history[2]),
                ]
                with db.transaction():
                    assert db.execute(
                        "SELECT count(*) FROM kineticloop.projection_versions WHERE id=%s",
                        (UUID(winner["projection_id"]),),
                    ).fetchone() == (1,)
                    assert db.execute(
                        "SELECT count(*) FROM kineticloop.projection_dependencies WHERE ref_s21_id=%s",
                        (UUID(winner["projection_id"]),),
                    ).fetchone() == (len(duplicate_record.dependencies),)
                assert api.record_projection(duplicate_record) == winner
                assert history(db, seed["identity"].subject_id) == new_history
            elif mode == "build":
                assert [len(rows) for rows in new_history] == [
                    len(old_history[0]),
                    len(old_history[1]),
                    len(old_history[2]) + 1,
                ]
                with db.transaction():
                    assert db.execute(
                        "SELECT count(*) FROM kineticloop.manifest_builds WHERE id=%s",
                        (UUID(winner["build_id"]),),
                    ).fetchone() == (1,)
                assert duplicate_request is not None
                assert api.build_manifest(duplicate_request) == winner
                assert history(db, seed["identity"].subject_id) == new_history
            else:
                assert [len(rows) for rows in new_history] == [len(rows) for rows in old_history]
                assert api.complete_manifest(CompleteManifest(UUID(winner["build_id"]))) == winner
                assert history(db, seed["identity"].subject_id) == new_history
            print("PERSISTED_DUPLICATE_CLOSURE", mode, winner, [len(rows) for rows in new_history])
        assert before[1][5:10] == state(db, seed["identity"].subject_id)[1][5:10]


def test_no_authority(database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    seed = seed_sources(database_urls)
    with psycopg.connect(database_urls["admin"]) as db:
        record, projection, request, ready = pipeline(db, seed, "no-authority")
        before = state(db, seed["identity"].subject_id, preparation=True)
        for identity in (
            replace(seed["identity"], principal="kl_test_subject_2_login"),
            replace(seed["identity"], policy_id=uuid4()),
            replace(seed["identity"], environment_id=uuid4()),
            replace(seed["identity"], subject_id=uuid4()),
        ):
            with pytest.raises(GuardRequired):
                PreparationService(db, identity).record_projection(record)
            assert state(db, seed["identity"].subject_id, preparation=True) == before
        for role in (ActorRole.SUBJECT, ActorRole.EVALUATION):
            with pytest.raises(ValueError):
                replace(seed["identity"], actor=RoleIdentity(str(uuid4()), role))
        for namespace, principal in [
            ("PRODUCTION", "kl_production_subject_1_login"),
            ("EVALUATION", "kl_evaluation_subject_1_login"),
        ]:
            foreign_subject = uuid4()
            with psycopg.connect(database_urls["trusted_admin"], autocommit=True) as trusted:
                trusted.execute(
                    "SELECT kineticloop.subject_scope_register(%s,%s,%s,%s,%s)",
                    (
                        foreign_subject,
                        namespace,
                        None,
                        uuid4() if namespace == "EVALUATION" else None,
                        principal,
                    ),
                )
            with pytest.raises(GuardRequired):
                PreparationService(
                    db, replace(seed["identity"], subject_id=foreign_subject)
                ).record_projection(record)
            assert state(db, seed["identity"].subject_id, preparation=True) == before
        with psycopg.connect(database_urls["test"]) as subject_connection:
            with pytest.raises((GuardRequired, psycopg.Error)):
                PreparationService(subject_connection, seed["identity"]).record_projection(record)
        assert state(db, seed["identity"].subject_id, preparation=True) == before
        original = RestrictedSqlSession.insert
        observed: list[frozenset[str]] = []

        def inspect_locks(self: Any, kind: str, values: Any) -> int:
            result = original(self, kind, values)
            if kind in {"S21", "S22", "S23"}:
                locks = self.relation_locks()
                observed.append(locks)
                assert not {"user_decision_state", "safety_registry_state"} & locks
            return result

        other = factset(db, seed, "independent")
        api = PreparationService(db, seed["identity"])
        changed = replace(record, source=api.capture_source(other))
        after_seal = state(db, seed["identity"].subject_id)
        waiter_started = Event()
        waiter_pid: list[int] = []

        def wait_on_subject() -> None:
            with psycopg.connect(database_urls["admin"]) as waiter:
                waiter_pid.append(waiter.info.backend_pid)
                waiter_started.set()
                with waiter.transaction():
                    waiter.execute("SET LOCAL statement_timeout='8000ms'")
                    waiter.execute(
                        "SELECT 1 FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
                        (seed["identity"].subject_id,),
                    )

        with ThreadPoolExecutor(max_workers=1) as pool:
            with psycopg.connect(database_urls["admin"]) as blocker:
                with blocker.transaction():
                    blocker.execute(
                        "SELECT 1 FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
                        (seed["identity"].subject_id,),
                    )
                    waiting = pool.submit(wait_on_subject)
                    assert waiter_started.wait(5)
                    deadline = time.monotonic() + 5
                    blocked = False
                    while time.monotonic() < deadline:
                        with db.transaction():
                            row = db.execute(
                                "SELECT pg_blocking_pids(%s)", (waiter_pid[0],)
                            ).fetchone()
                        assert row is not None
                        if blocker.info.backend_pid in row[0]:
                            blocked = True
                            break
                    assert blocked
                    print("OBSERVED_S01_BLOCKER", blocker.info.backend_pid, waiter_pid[0])
                    started = time.monotonic()
                    with monkeypatch.context() as patch:
                        patch.setattr(RestrictedSqlSession, "insert", inspect_locks)
                        result = api.record_projection(changed)
                        new_request = replace(
                            request,
                            key="independent",
                            source=changed.source,
                            bindings=(
                                ProjectionBinding("EXPOSURE", UUID(result["projection_id"])),
                            ),
                        )
                        build = api.build_manifest(new_request)
                        api.complete_manifest(CompleteManifest(UUID(build["build_id"])))
                    assert time.monotonic() - started < 2
            waiting.result(timeout=5)
        assert observed
        assert state(db, seed["identity"].subject_id) == after_seal
        with pytest.raises(GuardRequired):
            ProtocolExecutionService(db, seed["identity"]).publish(
                publication(seed, request, ready, "stale-factset")
            )
        assert state(db, seed["identity"].subject_id) == after_seal
        input_revision(db, seed, "no-authority-update")
        stale_state = state(db, seed["identity"].subject_id, preparation=True)
        trace: list[str] = []

        class TraceCursor(psycopg.Cursor[Any]):
            def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
                trace.append(query.as_string() if hasattr(query, "as_string") else str(query))
                return super().execute(query, params, **kwargs)

        with psycopg.connect(database_urls["admin"], cursor_factory=TraceCursor) as guarded:
            with pytest.raises(GuardRequired):
                ProtocolExecutionService(guarded, seed["identity"]).publish(
                    publication(
                        seed,
                        new_request,
                        PreparationService(db, seed["identity"]).complete_manifest(
                            CompleteManifest(UUID(build["build_id"]))
                        ),
                        "stale-owner-input",
                    )
                )
        registry_index = next(
            i for i, q in enumerate(trace) if "safety_registry_state" in q and "FOR SHARE" in q
        )
        subject_index = next(
            i
            for i, q in enumerate(trace)
            if i > registry_index and "user_decision_state" in q and "FOR UPDATE" in q
        )
        assert registry_index < subject_index
        assert state(db, seed["identity"].subject_id, preparation=True) == stale_state
        print("FROZEN_T3_LOCK_ORDER", registry_index, subject_index)
        assert result["executable"] is False
