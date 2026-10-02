"""KL028 mechanical PU/DC acceptance over immutable merged owners; no product E2E."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Event, local
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import Engine

from kineticloop.contracts.commands import ContinueSession, ResumeSession, RevokeArtifact
from kineticloop.contracts.safety_registry import RegistryDenied, revocation_payload_hash
from kineticloop.identity import ActorRole
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
    PreparationService,
    ProjectionBinding,
    RecordProjection,
)
from kineticloop.persistence.safety_registry import revoke_artifact
from kineticloop.persistence.transactions import (
    RepositoryTransaction,
    RepositoryTransactionError,
    execute_command,
    query_execution_eligibility,
)
from kineticloop.protocol.authorization import AUTHORIZATION_METHOD_VERSION
from kineticloop.protocol.execution import PublishReady, digest
from kineticloop.protocol.factsets import EvidenceBasis, Member

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: str) -> Any:
    spec = spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


N = load("kl028_namespace", "tests/unit/protocol/test_boundary_acceptance.py")
D = load("kl028_merged_demo_helpers", "tests/db/test_test_only_demo.py")
M = load("kl028_selected_bootstrap", "tests/db/test_migrations.py")
GLOBAL_TABLES = (
    "safety_artifacts",
    "safety_artifact_dependencies",
    "artifact_revocation_events",
    "safety_registry_state",
    "registry_management_receipts",
    "registry_audit_events",
    "registry_outbox",
)
ERRORS = (RepositoryTransactionError, psycopg.Error, ValueError, RegistryDenied)


def head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def witness(label: str, **values: Any) -> None:
    if "kind" in values:
        values["operation_kind"] = values.pop("kind")
    D.witness(label, tested_commit=head(), **values)


_ADMIN_URL: str | None = None
_ENDPOINT: tuple[str, int] | None = None
_ALLOWED_URLS: frozenset[str] = frozenset()
_LIFECYCLE: Any = None


class SelectedLifecycle(N.OwnedLifecycle):  # type: ignore[name-defined]  # Private loaded test module.
    def connection(self) -> Any:
        global _ENDPOINT
        selected = super().connection()
        _ENDPOINT = (selected.host, selected.port)
        return selected


def connect(url: str, *, bootstrap: bool = False, **kwargs: Any) -> Any:
    selected = N.fixture_namespace(ROOT, head())
    assert _LIFECYCLE is not None
    _LIFECYCLE.validate_target()
    parsed = urlparse(url)
    if (
        parsed.path != "/" + selected.database_name
        or (parsed.hostname, parsed.port) != _ENDPOINT
        or parsed.scheme != "postgresql"
        or parsed.query
        or parsed.fragment
        or (not bootstrap and url not in _ALLOWED_URLS)
    ):
        raise ValueError("foreign KL028 connection")
    db = psycopg.connect(
        url,
        connect_timeout=5,
        options="-c statement_timeout=12000 -c lock_timeout=10000 -c idle_in_transaction_session_timeout=15000",
        **kwargs,
    )
    try:
        with db.transaction():
            assert db.execute("SELECT current_database()").fetchone() == (selected.database_name,)
            assert db.execute("SHOW statement_timeout").fetchone() == ("12s",)
            assert db.execute("SHOW lock_timeout").fetchone() == ("10s",)
            if not bootstrap and url == _ADMIN_URL:
                assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
                    M.HEAD_REVISION,
                )
        if not bootstrap and url != _ADMIN_URL:
            assert _ADMIN_URL is not None
            with connect(_ADMIN_URL) as observer:
                assert observer.execute(
                    "SELECT current_database(),version_num FROM alembic_version"
                ).fetchone() == (selected.database_name, M.HEAD_REVISION)
        return db
    except BaseException:
        db.close()
        raise


D.connect = connect  # Private module instance, explicit KL028 URL, never D.database_urls.
M.psycopg = SimpleNamespace(connect=lambda url, **kw: connect(url, bootstrap=True, **kw))


_ORIGINAL_MIGRATION = M.run_alembic


def owned_migration(url: str, revision: str) -> None:
    _LIFECYCLE.validate_target()
    parsed = urlparse(url)
    selected = N.fixture_namespace(ROOT, head())
    assert parsed.path == "/" + selected.database_name
    assert (parsed.hostname, parsed.port) == _ENDPOINT
    assert parsed.query == "" and parsed.fragment == ""
    # Bound libpq connection establishment for the merged Alembic routine as well.
    _ORIGINAL_MIGRATION(url + "?connect_timeout=5", revision)


M.run_alembic = owned_migration


@pytest.fixture
def database_urls(tmp_path: Path) -> Any:
    global _ADMIN_URL, _LIFECYCLE, _ALLOWED_URLS
    N.test_boundary_namespace(tmp_path)
    lifecycle = SelectedLifecycle(ROOT, head())
    _LIFECYCLE = lifecycle
    selected = lifecycle.namespace

    def migration_connection(db: Any, record: Any) -> None:
        # The merged Alembic bootstrap opens SQLAlchemy connections; verify these too.
        with db.cursor() as cursor:
            cursor.execute("SET statement_timeout='12s'")
            cursor.execute("SET lock_timeout='10s'")
            cursor.execute("SET idle_in_transaction_session_timeout='15s'")
            cursor.execute("SELECT current_database()")
            assert cursor.fetchone() == (selected.database_name,)
        db.commit()

    sqlalchemy_event.listen(Engine, "connect", migration_connection)
    try:
        urls = lifecycle.bootstrap(M.bootstrap_two_phase)
        _ADMIN_URL = urls["admin"]
        _ALLOWED_URLS = frozenset(urls.values())
        with connect(urls["admin"]):
            witness(
                "owned_namespace",
                root=str(ROOT),
                compose=selected.project_name,
                database=selected.database_name,
                migration=M.HEAD_REVISION,
            )
        yield urls
    finally:
        sqlalchemy_event.remove(Engine, "connect", migration_connection)
        lifecycle.destroy()
        remaining = {
            kind: lifecycle._run(
                [
                    "docker",
                    kind,
                    "ls",
                    "--filter",
                    "label=com.docker.compose.project=" + selected.project_name,
                    "--quiet",
                ]
            ).stdout.strip()
            for kind in ("container", "volume", "network")
        }
        assert not any(remaining.values()), remaining
        witness(
            "exact_owned_cleanup",
            compose=selected.project_name,
            database=selected.database_name,
            inventory=lifecycle.inventory,
            remaining=remaining,
        )


def global_snapshot(db: Any) -> Any:
    with db.transaction():
        return {
            table: db.execute(
                sql.SQL(
                    "SELECT to_jsonb(t) FROM kineticloop.{} t ORDER BY to_jsonb(t)::text"
                ).format(sql.Identifier(table))
            ).fetchall()
            for table in GLOBAL_TABLES
        }


def snapshot(db: Any, seed: Any) -> Any:
    return D.snapshot(db, D.auth(seed).subject_id)


def denial(db: Any, seed: Any, operation: Any, cause: str) -> None:
    before, registry = snapshot(db, seed), global_snapshot(db)
    with pytest.raises(ERRORS) as error:
        operation()
    assert cause in str(error.value), str(error.value)
    assert snapshot(db, seed) == before and global_snapshot(db) == registry
    witness(
        "exact_guard_zero_effect",
        cause=str(error.value),
        intended=cause,
        persisted=before,
        global_history=registry,
    )


_ORIGINAL_SEED = D.seed_source
_REGISTER = D.registered_runtime


def seed_source(urls: Any, **kwargs: Any) -> Any:
    graph: dict[str, Any] = {}
    runtime_seconds = kwargs.pop("runtime_seconds", None)

    def register_graph(
        db: Any, artifact: Any, content_hash: Any, release: Any, now: Any, end: Any, deps: Any
    ) -> None:
        if runtime_seconds is not None:
            end = min(end, now + timedelta(seconds=runtime_seconds))
        b, c = uuid4(), uuid4()
        _REGISTER(db, c, digest(str(c)), release, now, end, ())
        _REGISTER(db, b, digest(str(b)), release, now, end, (c,))
        _REGISTER(db, artifact, content_hash, release, now, end, (*deps, b, c))
        graph.update(
            a=artifact, b=b, c=c, leaf_hash=digest(str(c)), release=release, runtime_end=end
        )

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(D, "registered_runtime", register_graph)
        seed = _ORIGINAL_SEED(urls, **kwargs)
    seed.update(graph)
    with connect(urls["admin"]) as db:
        rows = db.execute(
            "SELECT artifact_id,dependency_artifact_id FROM kineticloop.safety_artifact_dependencies WHERE artifact_id=ANY(%s)",
            ([graph[k] for k in ("a", "b", "c")],),
        ).fetchall()
        assert (graph["a"], graph["b"]) in rows and (graph["b"], graph["c"]) in rows
        assert (graph["a"], graph["c"]) in rows
    witness("registered_transitive_graph", graph=graph, actual_edges=rows)
    return seed


D.seed_source = seed_source


def revocation(
    seed: Any,
    effective: datetime | None = None,
    artifact: UUID | None = None,
    content_hash: str | None = None,
) -> tuple[Any, datetime]:
    effective = effective or seed["now"]
    key = str(uuid4())
    command = RevokeArtifact.model_validate(
        dict(
            schema_version="kineticloop-command-v1",
            command_kind="RevokeArtifact",
            boundary="T2-GLOBAL",
            command_id=str(uuid4()),
            actor={
                "schema": "kineticloop-role-identity-v1",
                "identity_id": str(uuid4()),
                "role": ActorRole.ADMIN,
            },
            idempotency_key=key,
            request_hash=digest(key),
            subject_id=None,
            explicit_scope="global:safety-registry",
            artifact_id=str(artifact or seed["c"]),
            artifact_content_hash=content_hash or seed["leaf_hash"],
            revocation_payload_hash=revocation_payload_hash(
                effective_at=effective, reason_code="BOUNDARY_EMERGENCY"
            ),
            causation_incident_id=str(uuid4()),
        )
    )
    return command, effective


def revoke(db: Any, request: Any) -> Any:
    command, effective = request
    return revoke_artifact(db, command, effective_at=effective, reason_code="BOUNDARY_EMERGENCY")


def revoked_cause(kind: str) -> str:
    return "registry artifact is revoked" if kind == "T3" else "KL_REGISTRY_ARTIFACT_REVOKED"


def revoke_now(urls: Any, seed: Any) -> Any:
    with connect(urls["trusted_admin"]) as db:
        return revoke(db, revocation(seed))


def build(db: Any, seed: Any, key: str = "boundary", *, complete: bool = True) -> Any:
    subject = D.auth(seed).subject_id
    cv = CanonicalViewService(db, BuilderIdentity(seed["identity"].actor, subject))
    with db.transaction():
        frontier, epoch = db.execute(
            "SELECT input_frontier_hash,authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (subject,),
        ).fetchone()
    identity = UUID(
        cv.begin_build(
            BeginBuild(
                subject,
                key,
                frontier,
                epoch,
                seed["program"],
                D.auth(seed).policy_id,
                EvidenceBasis(
                    (seed["association"],),
                    (seed["admission"],),
                    (),
                    seed["now"].isoformat(),
                    "TEST_ONLY",
                ),
                max_delta_depth=1,
            )
        )["build_id"]
    )
    members = (
        Member("ASSOCIATION", "event", "TEST_ONLY", seed["association"]),
        Member("ADMISSION", "admitted", "TEST_ONLY", seed["admission"]),
        Member("FACT", "actual", "TEST_ONLY", seed["fact"]),
    )
    for index, member in enumerate(members):
        cv.write_candidate(WriteCandidate(subject, str(index), identity, index, member))
    closed = (
        cv.complete_factset(CompleteFactset(subject, "complete", identity, 3)) if complete else None
    )
    return cv, identity, closed


def ready_publication(db: Any, seed: Any, factset: UUID | None = None) -> Any:
    if factset is None:
        cv, factset, closed = build(db, seed)
        cv.seal_factset(SealFactset(D.auth(seed).subject_id, str(uuid4()), factset, closed))
    ingress = PreparationService(db, D.auth(seed))
    source = ingress.capture_source(factset)
    projection = ingress.record_projection(
        RecordProjection(
            source,
            "EXPOSURE",
            seed["engine"],
            tuple(seed["policy"]["deterministic_fixture"]["window"]),
            {
                "actual_minutes_lower": 10,
                "actual_minutes_upper": 10,
                "dedup_event_ids": [str(seed["event"])],
                "semantic_class": "ACTUAL_EXECUTION",
                "source_fact_ids": [str(seed["fact"])],
            },
            seed["deps"],
            seed["end"],
        )
    )
    candidate = ingress.build_manifest(
        BuildManifest(
            str(uuid4()),
            source,
            (ProjectionBinding("EXPOSURE", UUID(projection["projection_id"])),),
            (seed["engine"].artifact_id,),
        )
    )
    ready = ingress.complete_manifest(CompleteManifest(UUID(candidate["build_id"])))
    request = PublishReady(
        D.auth(seed).subject_id,
        str(uuid4()),
        UUID(ready["build_id"]),
        source.factset_id,
        source.frontier,
        source.epoch,
        source.program_id,
        source.policy_id,
        ready["dependency_basis_hash"],
        ready["artifact_dependency_closure_hash"],
    )
    seed.update(source=source, ready=ready, publication_request=request)
    return request


def target(urls: Any, kind: str, **kwargs: Any) -> tuple[Any, Any]:
    if kind == "T3":
        seed = seed_source(urls, **kwargs)
        with connect(urls["admin"]) as db:
            request = ready_publication(db, seed)
        return seed, lambda db: D.service(db, seed).publish(request)
    seed, request = D.ready(urls, **kwargs)
    seed["full_request"] = request
    if kind == "T6":
        return seed, lambda db: D.service(db, seed).commit_full(request)
    with connect(urls["admin"]) as db:
        bundle = D.service(db, seed).commit_full(request)
    command = D.session_command(seed, bundle)
    seed.update(bundle=bundle, start_command=command)
    return seed, lambda db: D.service(db, seed).start(command)


def race(
    urls: Any,
    seed: Any,
    monkeypatch: Any,
    first: Any,
    second: Any,
    *,
    first_registry: bool = False,
    second_registry: bool = False,
    cause: str | None = None,
) -> Any:
    held, release, entered = Event(), Event(), Event()
    thread = local()
    pids: dict[str, int] = {}
    winners: dict[str, Any] = {}
    traces: list[Any] = []
    original_finish = RepositoryTransaction.finish
    with connect(urls["admin"]) as db:
        baseline = snapshot(db, seed)

    def wait_winner(db: Any) -> None:
        if thread.name == "winner":
            winners["state"] = baseline if first_registry else snapshot(db, seed)
            held.set()
            assert release.wait(8), "winner release deadline"

    def finish(tx: Any) -> None:
        original_finish(tx)
        traces.append({"command": tx.command_kind, "trace": tx.lock_trace})
        wait_winner(thread.db)

    class Cursor(psycopg.Cursor[Any]):
        def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
            result = super().execute(query, params, **kwargs)
            if "registry_revoke_artifact(" in str(query):
                wait_winner(self.connection)
            return result

    def run(operation: Any, name: str, registry: bool) -> Any:
        with connect(
            urls["trusted_admin"] if registry else urls["admin"],
            cursor_factory=Cursor,
            application_name="kl028-" + name,
        ) as db:
            thread.name, thread.db = name, db
            pids[name] = db.info.backend_pid
            if name == "loser":
                entered.set()
            try:
                return operation(db)
            except ERRORS as error:
                return error

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
        patch.setattr(RepositoryTransaction, "finish", finish)
        winner = pool.submit(run, first, "winner", first_registry)
        try:
            assert held.wait(8), (
                winner.result(timeout=1) if winner.done() else "winner guard missing"
            )
            loser = pool.submit(run, second, "loser", second_registry)
            assert entered.wait(8)
            with connect(urls["admin"], autocommit=True) as observer:
                deadline = time.monotonic() + 0.8
                blocked = None
                while time.monotonic() < deadline:
                    row = observer.execute(
                        "SELECT pg_blocking_pids(%s),clock_timestamp(),(SELECT query FROM pg_stat_activity WHERE pid=%s)",
                        (pids["loser"], pids["loser"]),
                    ).fetchone()
                    if pids["winner"] in row[0]:
                        blocked = row
                        break
                assert blocked is not None, "actual PostgreSQL blocking missing"
        finally:
            release.set()
        a, b = winner.result(timeout=12), loser.result(timeout=12)
    assert not isinstance(a, ERRORS), a
    if cause:
        assert isinstance(b, ERRORS) and cause in str(b), str(b)
        with connect(urls["admin"]) as db:
            assert snapshot(db, seed) == winners["state"]
    else:
        assert not isinstance(b, ERRORS), b
    for item in traces:
        if item["command"] in {"PublishManifest", "CommitBundle", "StartSession"}:
            assert [t[1] for t in item["trace"][:2]] == ["S51", "S01"]
    witness(
        "observed_real_race",
        winner=pids["winner"],
        loser=pids["loser"],
        blocked=blocked,
        first_registry=first_registry,
        second_registry=second_registry,
        first_result=a,
        second_result=str(b) if isinstance(b, ERRORS) else b,
        traces=traces,
        winner_uncommitted_history=winners["state"],
        zero_effects_after_winner=bool(cause),
    )
    return a, b


def assert_revoke(db: Any, before: Any, result: Any) -> None:
    after = global_snapshot(db)
    assert after["safety_artifacts"] == before["safety_artifacts"]
    assert after["safety_artifact_dependencies"] == before["safety_artifact_dependencies"]
    old = before["safety_registry_state"][0][0]
    state = after["safety_registry_state"][0][0]
    assert state["registry_revision"] == old["registry_revision"] + 1 == result.registry_revision
    assert state["last_revocation_id"] == result.revocation_id
    for table in (
        "artifact_revocation_events",
        "registry_management_receipts",
        "registry_audit_events",
        "registry_outbox",
    ):
        assert len(after[table]) == len(before[table]) + 1
        assert all(row in after[table] for row in before[table])
    rev = next(
        row[0]
        for row in after["artifact_revocation_events"]
        if row[0]["id"] == result.revocation_id
    )
    receipt = next(
        row[0]
        for row in after["registry_management_receipts"]
        if row[0]["revocation_id"] == result.revocation_id
    )
    audit = next(
        row[0]
        for row in after["registry_audit_events"]
        if row[0]["revocation_id"] == result.revocation_id
    )
    outbox = next(
        row[0]
        for row in after["registry_outbox"]
        if row[0]["revocation_id"] == result.revocation_id
    )
    assert rev["registry_revision"] == receipt["registry_revision"] == result.registry_revision
    assert rev["ref_s49_id"] == receipt["artifact_id"] == result.artifact_id
    assert (
        rev["command_key"] == receipt["command_key"]
        and rev["request_hash"] == receipt["request_hash"]
    )
    assert (
        rev["operator_identity"]
        == receipt["operator_identity"]
        == audit["operator_identity"]
        == "kl_trusted_admin_login"
    )
    assert (
        rev["causation_incident_id"]
        == receipt["causation_incident_id"]
        == audit["causation_incident_id"]
    )
    assert rev["outbox_delivery_id"] == receipt["outbox_delivery_id"] == outbox["delivery_id"]
    assert rev["effective_at"] == receipt["effective_at"] == result.effective_at.isoformat()
    assert rev["recorded_at"] == receipt["recorded_at"] == result.recorded_at.isoformat()
    witness("atomic_global_commit", result=asdict(result), before=before, after=after)


def test_b01_unsealed_canonical_denial(database_urls: Any) -> None:
    seed = seed_source(database_urls)
    with connect(database_urls["admin"]) as db:
        cv, identity, _ = build(db, seed, complete=False)
        subject = D.auth(seed).subject_id
        for status in ("BUILDING", "READY"):
            denial(db, seed, lambda: cv.read_canonical(subject, identity), "unsealed")
            denial(
                db,
                seed,
                lambda: PreparationService(db, D.auth(seed)).capture_source(identity),
                "SEALED factset required",
            )
            if status == "BUILDING":
                closed = cv.complete_factset(CompleteFactset(subject, "complete", identity, 3))
        cv.seal_factset(SealFactset(subject, "seal", identity, closed))
        canonical = cv.read_canonical(subject, identity)
        assert (
            canonical.membership_digest == closed["membership_digest"]
            and canonical.member_count == 3
        )
        publication = ready_publication(db, seed, identity)
        result = D.service(db, seed).publish(publication)
        D.assert_event(db, seed, result)
        witness(
            "sealed_positive",
            complete=closed,
            canonical=asdict(canonical),
            persisted=snapshot(db, seed),
        )


@pytest.mark.parametrize("update_first", [True, False])
def test_b02_stale_frontier_seal_race(
    database_urls: Any, monkeypatch: Any, update_first: bool
) -> None:
    seed = seed_source(database_urls)
    with connect(database_urls["admin"]) as db:
        _, identity, closed = build(db, seed)
    subject = D.auth(seed).subject_id

    def seal(db):
        return CanonicalViewService(
            db, BuilderIdentity(seed["identity"].actor, subject)
        ).seal_factset(SealFactset(subject, "seal", identity, closed))

    def update(db):
        return D.input_revision(db, seed, "input-" + str(uuid4()))

    race(
        database_urls,
        seed,
        monkeypatch,
        update if update_first else seal,
        seal if update_first else update,
        cause="factset completion basis is stale" if update_first else None,
    )
    with connect(database_urls["admin"]) as db:
        old = snapshot(db, seed)
        if update_first:
            assert old["factset_revisions"][0][0]["status"] == "READY"
            assert old["user_decision_state"][0][0]["current_factset_id"] is None
        else:
            historical = old["factset_revisions"][0][0]
            assert historical["status"] == "SEALED"
            current = old["user_decision_state"][0][0]
            assert (
                historical["typed_payload"]["captured_input_frontier"]
                != current["input_frontier_hash"]
            )
            assert historical["typed_payload"]["captured_epoch"] < current["authorization_epoch"]
            assert (
                CanonicalViewService(db, BuilderIdentity(seed["identity"].actor, subject))
                .read_canonical(subject, identity)
                .membership_digest
                == closed["membership_digest"]
            )
        cv, new, closed = build(db, seed, "fresh")
        cv.seal_factset(SealFactset(subject, "fresh-seal", new, closed))
        assert cv.read_canonical(subject, new).membership_digest == closed["membership_digest"]
        assert old["factset_revisions"][0] in snapshot(db, seed)["factset_revisions"]
        witness("fresh_frontier_rebuild", old=old, current=snapshot(db, seed))


def test_b03_sealed_immutability_ready_barrier(database_urls: Any) -> None:
    seed = seed_source(database_urls)
    with connect(database_urls["admin"]) as db:
        cv, identity, closed = build(db, seed)
        subject = D.auth(seed).subject_id

        def write():
            return cv.write_candidate(
                WriteCandidate(
                    subject,
                    str(uuid4()),
                    identity,
                    3,
                    Member("FACT", "correction", "TEST_ONLY", seed["fact"]),
                )
            )

        denial(db, seed, write, "expected BUILDING revision")
        cv.seal_factset(SealFactset(subject, "seal", identity, closed))
        original = snapshot(db, seed)
        denial(db, seed, write, "expected BUILDING revision")
        for statement in (
            "UPDATE kineticloop.factset_revisions SET content_hash='mutation' WHERE id=%s",
            'UPDATE kineticloop.factset_revisions SET typed_payload=typed_payload||\'{"completion_certificate":"mutation"}\'::jsonb WHERE id=%s',
            "UPDATE kineticloop.factset_members SET logical_member_key='mutation' WHERE ref_s15_id=%s",
        ):

            def mutate() -> None:
                with db.transaction():
                    db.execute(statement, (identity,))

            denial(
                db,
                seed,
                mutate,
                "KL_FACTSET_MEMBER_WRITE_GATE_REJECTED"
                if "factset_members" in statement
                else "KL_FACTSET_HISTORY_MUTATION_REJECTED",
            )
        revision = D.input_revision(db, seed, "correction-" + str(uuid4()))
        corrected = {**seed, "fact": revision}
        cv, new, complete = build(db, corrected, "correction")
        cv.seal_factset(SealFactset(subject, "correction-seal", new, complete))
        current = snapshot(db, seed)
        assert original["factset_revisions"][0] in current["factset_revisions"]
        assert all(row in current["factset_members"] for row in original["factset_members"])
        assert complete["membership_digest"] != closed["membership_digest"]
        witness("immutable_original_new_correction", before=original, after=current)


class GuardProbeComplete(ValueError):
    pass


def reauthorize_probe(db: Any, seed: Any, *, revoked: bool) -> None:
    with db.transaction():
        ids = db.execute(
            "SELECT typed_payload->'artifact_closure_ids' FROM kineticloop.decision_manifests WHERE subject_id=%s",
            (D.auth(seed).subject_id,),
        ).fetchone()[0]

    def probe(tx: Any) -> None:
        tx.acquire_registry_lease([UUID(x) for x in ids])
        witness(
            "Reauthorize_registry_guard_support_only",
            revision=tx._registry_revision,
            trace=tx.lock_trace,
            full_B04_DC="NOT_RUN",
            closure=ids,
        )
        # Explicit abort after the actual gate; never a successful no-op issuance.
        raise GuardProbeComplete("REA_AUTHORIZE_GUARD_OBSERVED_ONLY")

    denial(
        db,
        seed,
        lambda: execute_command(db, "Reauthorize", D.auth(seed).subject_id, probe),
        "KL_REGISTRY_ARTIFACT_REVOKED" if revoked else "REA_AUTHORIZE_GUARD_OBSERVED_ONLY",
    )


@pytest.mark.parametrize("revoked", [False, True])
def test_b04_relevant_revoke_issue_reauthorize(database_urls: Any, revoked: bool) -> None:
    seed, request = D.ready(database_urls)
    with connect(database_urls["admin"]) as db:
        reauthorize_probe(db, seed, revoked=False)
        if revoked:
            revoke_now(database_urls, seed)
            reauthorize_probe(db, seed, revoked=True)
            denial(
                db,
                seed,
                lambda: D.service(db, seed).commit_full(request),
                "KL_REGISTRY_ARTIFACT_REVOKED",
            )
        else:
            result = D.service(db, seed).commit_full(request)
            D.assert_event(db, seed, result)
            issued = snapshot(db, seed)
            assert len(issued["authorization_issuances"]) == 2
            for issuance in issued["authorization_issuances"]:
                assert_exact_certificate_sources(db, seed, request, issuance[0], issued)
            witness(
                "real_full_issuance_positive",
                result=result,
                persisted=snapshot(db, seed),
                full_B04_DC="NOT_RUN",
            )


def eligibility(
    db: Any, seed: Any, command: Any, session: str, kind: str = "ContinueSession"
) -> Any:
    with db.transaction():
        ids = db.execute(
            "SELECT typed_payload->'artifact_closure_ids' FROM kineticloop.decision_manifests WHERE subject_id=%s",
            (D.auth(seed).subject_id,),
        ).fetchone()[0]
    artifacts = D.service(db, seed)._artifacts(ids)
    return query_execution_eligibility(
        db,
        command_kind=kind,
        subject_id=D.auth(seed).subject_id,
        artifact_ids=[a.artifact_id for a in artifacts],
        artifact_identities=artifacts,
        local_date=seed["now"].date(),
        session_id=UUID(session),
        prescription_id=UUID(command.prescription_id),
        authorization_id=UUID(command.authorization_id),
        execution_scope="TEST_ONLY",
    )


def test_b05_unrelated_revoke_preserves_eligibility(database_urls: Any) -> None:
    seed, operation = target(database_urls, "T7")
    with connect(database_urls["admin"]) as db:
        started = operation(db)
        before = snapshot(db, seed)
        command = D.session_command(
            seed,
            seed["bundle"],
            ContinueSession,
            session_id=started["session_id"],
            binding=D.current_binding(db, seed, started["session_id"]),
        )
        assert eligibility(db, seed, command, started["session_id"]).is_executable
        unrelated = uuid4()
        with connect(database_urls["trusted_admin"]) as trusted:
            _REGISTER(
                trusted,
                unrelated,
                digest(str(unrelated)),
                seed["release"],
                seed["now"],
                seed["end"],
                (),
            )
            global_before = global_snapshot(db)
            result = revoke(
                trusted, revocation(seed, artifact=unrelated, content_hash=digest(str(unrelated)))
            )
        assert_revoke(db, global_before, result)
        assert all(
            row[0]["registry_revision_at_issue"] < result.registry_revision
            for row in before["authorization_issuances"]
        )
        assert all(
            row[0]["artifact_id"] != str(unrelated)
            for row in before["authorization_artifact_closure"]
        )
        observed = eligibility(db, seed, command, started["session_id"])
        assert observed.is_executable and observed.non_bearer
        positive = D.service(db, seed).start(D.session_command(seed, seed["bundle"]))
        D.assert_event(db, seed, positive)
        after = snapshot(db, seed)
        for table in (
            "authorization_issuances",
            "authorization_artifact_closure",
            "prescription_revisions",
        ):
            assert after[table] == before[table]
        assert all(row in after["execution_bindings"] for row in before["execution_bindings"])
        revoke_now(database_urls, seed)
        fresh = D.changed(
            command, command_id=str(uuid4()), idempotency_key=str(uuid4()), action_key=str(uuid4())
        )
        denial(
            db,
            seed,
            lambda: D.service(db, seed).continue_session(fresh),
            "KL_REGISTRY_ARTIFACT_REVOKED",
        )
        witness(
            "unrelated_revision_preserves_eligibility",
            decision=asdict(observed),
            before=before,
            after=after,
        )


@pytest.mark.parametrize("revoke_first", [True, False])
def test_b06_revoke_before_publish(
    database_urls: Any, monkeypatch: Any, revoke_first: bool
) -> None:
    _registry_race(database_urls, monkeypatch, "T3", revoke_first)


@pytest.mark.parametrize("mode", ["START", "CONTINUE", "RESUME"])
def test_b07_revoke_current_execution_denial(database_urls: Any, mode: str) -> None:
    _execution_loss(database_urls, mode, "registry")


def _execution_loss(urls: Any, mode: str, loss: str) -> None:
    seed, request = D.ready(urls)
    with connect(urls["admin"]) as db:
        bundle = D.service(db, seed).commit_full(request)
        started = D.service(db, seed).start(D.session_command(seed, bundle))
        initial = D.current_binding(db, seed, started["session_id"])
        if mode == "RESUME":
            D.service(db, seed).pause(D.pause_request(db, seed, started["session_id"]))
        model = {"START": D.StartSession, "CONTINUE": ContinueSession, "RESUME": ResumeSession}[
            mode
        ]

        def command() -> Any:
            return D.session_command(
                seed,
                bundle,
                model,
                session_id=started["session_id"] if mode != "START" else None,
                binding=D.current_binding(db, seed, started["session_id"])
                if mode != "START"
                else None,
            )

        method = {
            "START": D.service(db, seed).start,
            "CONTINUE": D.service(db, seed).continue_session,
            "RESUME": D.service(db, seed).resume,
        }[mode]
        positive = method(command())
        assert positive["executable"] and not positive["replayed"]
        D.assert_event(db, seed, positive)
        if mode == "RESUME":
            D.service(db, seed).pause(D.pause_request(db, seed, started["session_id"]))
        fresh = command()
        observed = eligibility(
            db,
            seed,
            fresh,
            started["session_id"],
            "ResumeSession" if mode == "RESUME" else "ContinueSession",
        )
        assert observed.is_executable and observed.non_bearer
        before = snapshot(db, seed)
        if loss == "registry":
            revoke_now(urls, seed)
            cause = "KL_REGISTRY_ARTIFACT_REVOKED"
        else:
            D.apply_control(db, seed)
            epoch = snapshot(db, seed)["user_decision_state"][0][0]["authorization_epoch"]
            fresh = D.changed(fresh, expected_authorization_epoch=epoch)
            cause = "KL_REGISTRY_AUTHORIZATION_INELIGIBLE"
        denial(db, seed, lambda: method(fresh), cause)
        after = snapshot(db, seed)
        for table in (
            "factset_revisions",
            "factset_members",
            "decision_manifests",
            "proposal_revisions",
            "prescription_demand_features",
            "evidence_resolutions",
            "validation_results",
            "daily_bundle_revisions",
            "prescription_revisions",
            "authorization_issuances",
            "authorization_artifact_closure",
            "execution_bindings",
            "workout_sessions",
        ):
            assert before[table] == after[table], table
        assert initial in [row[0] for row in after["execution_bindings"]]
        witness(
            "lifecycle_valid_fresh_authority_loss",
            mode=mode,
            loss=loss,
            positive=positive,
            fresh_key=fresh.idempotency_key,
            non_bearer=asdict(observed),
            before=before,
            after=after,
        )


def assert_exact_certificate_sources(
    db: Any, seed: Any, request: Any, issuance: Any, state: Any
) -> None:
    entries = issuance["validity_certificate"]["dependencies"]
    by_key = {(e["dependency_kind"], e["identity"]): e for e in entries}
    for table, kind, end_field in (
        ("decision_manifests", "MANIFEST", "valid_until"),
        ("projection_versions", "PROJECTION", "valid_until"),
        ("evidence_resolutions", "EVIDENCE_RESOLUTION", "resolution_expires_at"),
        ("validation_results", "VALIDATION_ADMISSION_FRESHNESS", "valid_until"),
    ):
        for row in state[table]:
            source = row[0]
            entry = by_key[(kind, source["id"])]
            assert entry["revision"] == source["revision"]
            assert datetime.fromisoformat(entry["valid_until"]) == datetime.fromisoformat(
                source[end_field]
            )
            starts = [
                datetime.fromisoformat(source[field])
                for field in ("recorded_at", "effective_at", "computed_at")
                if source.get(field)
            ]
            assert datetime.fromisoformat(entry["valid_from"]) == max(starts)
    freshness = by_key[("EVIDENCE_ADMISSION_FRESHNESS", str(seed["admission"]))]
    assert datetime.fromisoformat(freshness["valid_until"]) == seed["admission_end"]
    assert freshness["revision"] == state["admission_decisions"][0][0]["revision"]
    request_row = state["planning_request_revisions"][0][0]
    deadline = by_key[("REQUEST_DEADLINE", request_row["id"])]
    assert deadline["revision"] == request_row["request_revision"]
    assert datetime.fromisoformat(deadline["valid_until"]) == datetime.fromisoformat(
        state["planning_intents"][0][0]["deadline"]
    )
    start = datetime.fromisoformat(issuance["valid_from"])
    policy = by_key[("POLICY_TTL", str(D.auth(seed).policy_id))]
    assert datetime.fromisoformat(policy["valid_from"]) == start
    assert datetime.fromisoformat(policy["valid_until"]) == start + timedelta(
        seconds=seed["policy"]["max_authorization_ttl_seconds"]
    )
    plan_head = state["daily_plan_heads"][0][0]
    calendar = by_key[("CALENDAR", plan_head["id"])]
    assert calendar["revision"] == plan_head["local_date"]
    assert datetime.fromisoformat(calendar["valid_until"]) == datetime.fromisoformat(
        plan_head["typed_payload"]["calendar_valid_until"]
    )
    with db.transaction():
        actual = db.execute(
            "SELECT to_jsonb(a) FROM kineticloop.safety_artifacts a WHERE id=ANY(%s)",
            ([UUID(e["identity"]) for e in entries if e["dependency_kind"] == "ARTIFACT"],),
        ).fetchall()
    expected_artifacts = {e["identity"] for e in entries if e["dependency_kind"] == "ARTIFACT"}
    materialized = [
        row[0]
        for row in state["authorization_artifact_closure"]
        if row[0]["authorization_id"] == issuance["id"]
    ]
    assert {e["artifact_id"] for e in materialized} == expected_artifacts
    assert expected_artifacts == set(
        state["decision_manifests"][0][0]["typed_payload"]["artifact_closure_ids"]
    )
    for row in actual:
        source = row[0]
        entry = by_key[("ARTIFACT", source["id"])]
        assert entry["revision"] == source["revision"]
        assert entry["content_hash"] == source["content_hash"]
        assert entry["artifact_identity"] == source["artifact_identity"]
        assert entry["artifact_version"] == source["artifact_version"]
        for field in ("valid_from", "valid_until"):
            assert datetime.fromisoformat(entry[field]) == datetime.fromisoformat(source[field])
        member = next(e for e in materialized if e["artifact_id"] == source["id"])
        assert member["artifact_revision"] == entry["revision"]
        assert datetime.fromisoformat(member["valid_from"]) == datetime.fromisoformat(
            entry["valid_from"]
        )
        assert datetime.fromisoformat(member["valid_until"]) == datetime.fromisoformat(
            entry["valid_until"]
        )
    assert issuance["ref_s37_id"] == request.sources["validation"]["id"]
    assert issuance["ref_s36_id"] in {
        request.sources[k]["id"] for k in ("resolution", "nutrition_resolution")
    }


@pytest.mark.parametrize(
    "bound", ["default", "admission", "runtime", "deadline", "projection", "policy"]
)
@pytest.mark.parametrize("shorten", [False, True])
def test_b09_server_minimum_certificate(database_urls: Any, bound: str, shorten: bool) -> None:
    options: dict[str, Any] = {
        "admission": {"admission_seconds": 180},
        "runtime": {"runtime_seconds": 190},
        "deadline": {"deadline_seconds": 200},
        "projection": {"seconds": 210},
        "default": {},
        "policy": {"policy_overrides": {"max_authorization_ttl_seconds": 160}},
    }
    seed, request = D.ready(database_urls, **options[bound])
    with connect(database_urls["admin"]) as db:
        with db.transaction():
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        requested = now + timedelta(seconds=15 if shorten else 36000)
        result = D.service(db, seed).commit_full(request, requested_valid_until=requested)
        after = snapshot(db, seed)
        assert len(after["authorization_issuances"]) == 2
        for row in after["authorization_issuances"]:
            issuance = row[0]
            assert_exact_certificate_sources(db, seed, request, issuance, after)
            certificate = issuance["validity_certificate"]
            entries = certificate["dependencies"]
            ends = [
                datetime.fromisoformat(e["valid_until"]) for e in entries if e.get("valid_until")
            ]
            start, end = (
                datetime.fromisoformat(issuance["valid_from"]),
                datetime.fromisoformat(issuance["valid_until"]),
            )
            assert now <= start < end == min(ends)
            assert end == requested if shorten else end < requested
            assert certificate["method_version"] == AUTHORIZATION_METHOD_VERSION
            assert (
                hashlib.sha256(
                    json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                == certificate["closure_digest"]
            )
            kinds = {e["dependency_kind"] for e in entries}
            assert {
                "MANIFEST",
                "PROJECTION",
                "EVIDENCE_RESOLUTION",
                "VALIDATION_ADMISSION_FRESHNESS",
                "ARTIFACT",
                "POLICY_TTL",
                "REQUEST_DEADLINE",
                "CALENDAR",
            } <= kinds, kinds
            assert any(e["identity"] == str(seed["admission"]) for e in entries)
            assert all(
                str(seed[key]) in {e["identity"] for e in entries} for key in ("a", "b", "c")
            )
            assert entries == sorted(
                entries, key=lambda e: (e["dependency_kind"], e["identity"], str(e["revision"]))
            )
        D.assert_event(db, seed, result)
        with db.transaction():
            trusted_after = db.execute("SELECT clock_timestamp()").fetchone()[0]
        assert all(
            datetime.fromisoformat(row[0]["valid_from"]) < trusted_after
            for row in after["authorization_issuances"]
        )
        witness(
            "server_exact_minimum_full_certificate",
            trusted_after=trusted_after,
            declared_bounds=options[bound],
            client=requested,
            trusted_before=now,
            result=result,
            persisted=after,
        )


@pytest.mark.parametrize("kind", ["T3", "T6", "T7"])
@pytest.mark.parametrize("positive", [False, True])
def test_b11_backdated_revoke_commit_linearization(
    database_urls: Any, monkeypatch: Any, kind: str, positive: bool
) -> None:
    _timed_revoke(database_urls, monkeypatch, kind, False, positive)


@pytest.mark.parametrize("kind", ["T3", "T6", "T7"])
@pytest.mark.parametrize("positive", [False, True])
def test_b12_future_revoke_immediate_at_commit(
    database_urls: Any, monkeypatch: Any, kind: str, positive: bool
) -> None:
    _timed_revoke(database_urls, monkeypatch, kind, True, positive)


def _timed_revoke(urls: Any, monkeypatch: Any, kind: str, future: bool, positive: bool) -> None:
    seed, operation = target(urls, kind)
    with connect(urls["admin"]) as db:
        if positive:
            result = operation(db)
            D.assert_event(db, seed, result)
            witness(
                "unrevoked_timing_positive_control",
                kind=kind,
                future=future,
                result=result,
                persisted=snapshot(db, seed),
            )
            return
        if kind == "T7":
            started = operation(db)
            initial = D.current_binding(db, seed, started["session_id"])
            command = D.session_command(
                seed,
                seed["bundle"],
                ContinueSession,
                session_id=started["session_id"],
                binding=initial,
            )
            assert D.service(db, seed).continue_session(command)["executable"]
            command = D.changed(
                command,
                command_id=str(uuid4()),
                idempotency_key=str(uuid4()),
                action_key=str(uuid4()),
            )

            def operation(db):
                return D.service(db, seed).continue_session(command)

        before = global_snapshot(db)
        history = snapshot(db, seed)
        with db.transaction():
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
    request = revocation(seed, now + timedelta(days=1 if future else -1))
    result, _ = race(
        urls,
        seed,
        monkeypatch,
        lambda db: revoke(db, request),
        operation,
        first_registry=True,
        cause=revoked_cause(kind),
    )
    assert (result.effective_at > result.recorded_at) is future
    with connect(urls["admin"]) as db:
        assert_revoke(db, before, result)
        assert snapshot(db, seed) == history
        denial(db, seed, lambda: operation(db), revoked_cause(kind))
    witness(
        "effective_at_audit_only", future=future, kind=kind, result=asdict(result), history=history
    )


@pytest.mark.parametrize("kind", ["T3", "T6", "T7"])
def test_b13_revoke_rollback_zero_effects(database_urls: Any, kind: str) -> None:
    seed, operation = target(database_urls, kind)

    class FailAfterRoutine(psycopg.Cursor[Any]):
        def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
            result = super().execute(query, params, **kwargs)
            if "registry_revoke_artifact(" in str(query):
                row = self.fetchone()
                assert row and str(row[2]) == str(seed["c"])
                witness("all_revoke_writes_executed_before_injected_abort", returned=row)
                raise ValueError("KL028_INJECT_AFTER_GLOBAL_WRITES_BEFORE_COMMIT")
            return result

    with connect(database_urls["admin"]) as db:
        before = global_snapshot(db)
        with connect(database_urls["trusted_admin"], cursor_factory=FailAfterRoutine) as trusted:
            with pytest.raises(ValueError, match="KL028_INJECT_AFTER_GLOBAL_WRITES_BEFORE_COMMIT"):
                revoke(trusted, revocation(seed))
        assert global_snapshot(db) == before
        result = operation(db)
        D.assert_event(db, seed, result)
        witness(
            "rollback_complete_global_zero_effect_positive_owner",
            kind=kind,
            before=before,
            after=global_snapshot(db),
            result=result,
            persisted=snapshot(db, seed),
        )


@pytest.mark.parametrize("kind", ["T3", "T6", "T7"])
@pytest.mark.parametrize("fault", ["timeout", "unavailable", "positive"])
def test_b14_registry_failclosed_stop_support(database_urls: Any, kind: str, fault: str) -> None:
    seed, operation = target(database_urls, kind)
    if fault == "positive":
        with connect(database_urls["admin"]) as db:
            result = operation(db)
            D.assert_event(db, seed, result)
            witness(
                "registry_fault_unrevoked_positive_control",
                kind=kind,
                result=result,
                persisted=snapshot(db, seed),
            )
        return
    reached: list[Any] = []

    class Unavailable(psycopg.Cursor[Any]):
        def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
            if "registry_guard_" in str(query) or (
                "FROM kineticloop.safety_registry_state" in str(query) and "FOR SHARE" in str(query)
            ):
                reached.append(str(query))
                raise psycopg.OperationalError("KL028_REGISTRY_UNAVAILABLE_AT_ACTUAL_GATE")
            return super().execute(query, params, **kwargs)

    with connect(database_urls["admin"]) as db:
        registry_before = global_snapshot(db)
        if fault == "unavailable":
            with connect(database_urls["admin"], cursor_factory=Unavailable) as unavailable:
                denial(
                    db,
                    seed,
                    lambda: operation(unavailable),
                    "KL028_REGISTRY_UNAVAILABLE_AT_ACTUAL_GATE",
                )
                assert len(reached) == 1
            D.apply_control(db, seed)
        else:
            with connect(database_urls["admin"]) as blocker:
                blocker.execute(
                    "SELECT id FROM kineticloop.safety_registry_state WHERE id=1 FOR UPDATE"
                )

                def run() -> Any:
                    with connect(
                        database_urls["admin"], application_name="kl028-unavailable"
                    ) as waiter:
                        try:
                            return operation(waiter)
                        except ERRORS as error:
                            return error

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(run)
                    observed = D.observe_blocked(database_urls["admin"], "kl028-unavailable")
                    assert blocker.info.backend_pid in observed[1] and "registry" in observed[2]
                    D.apply_control(db, seed)  # Independent S01 while S51 remains exclusive.
                    before = snapshot(db, seed)
                    result = future.result(timeout=12)
                    assert isinstance(result, ERRORS) and (
                        "lock timeout" if kind == "T3" else "KL_REGISTRY_TIMEOUT"
                    ) in str(result), str(result)
                    assert snapshot(db, seed) == before
                    witness(
                        "actual_gate_timeout_STOP_support",
                        observed=observed,
                        cause=str(result),
                        persisted=before,
                    )
                blocker.rollback()
        assert global_snapshot(db) == registry_before
        witness(
            "DC_support_only_registry_fault_STOP",
            kind=kind,
            fault=fault,
            reached=reached,
            persisted=snapshot(db, seed),
            B14_WF="NOT_RUN",
            B14_E2E="NOT_RUN",
        )


@pytest.mark.parametrize("kind", ["T3", "T6", "T7"])
@pytest.mark.parametrize("revoke_first", [True, False])
def test_b15_fresh_registry_both_orders(
    database_urls: Any, monkeypatch: Any, kind: str, revoke_first: bool
) -> None:
    _registry_race(database_urls, monkeypatch, kind, revoke_first)


def _registry_race(urls: Any, monkeypatch: Any, kind: str, revoke_first: bool) -> None:
    seed, operation = target(urls, kind)
    request = revocation(seed)
    with connect(urls["admin"]) as db:
        before = global_snapshot(db)
    a, b = race(
        urls,
        seed,
        monkeypatch,
        (lambda db: revoke(db, request)) if revoke_first else operation,
        operation if revoke_first else (lambda db: revoke(db, request)),
        first_registry=revoke_first,
        second_registry=not revoke_first,
        cause=revoked_cause(kind) if revoke_first else None,
    )
    result = a if revoke_first else b
    with connect(urls["admin"]) as db:
        assert_revoke(db, before, result)
        if not revoke_first:
            D.assert_event(db, seed, a)
            if kind == "T7":
                command = D.session_command(
                    seed,
                    seed["bundle"],
                    ContinueSession,
                    session_id=a["session_id"],
                    binding=D.current_binding(db, seed, a["session_id"]),
                )
                denial(
                    db,
                    seed,
                    lambda: D.service(db, seed).continue_session(command),
                    revoked_cause(kind),
                )
            else:
                # A new key forces the actual fresh registry guard before replay handling.
                if kind == "T3":
                    next_request = replace(seed["publication_request"], key=str(uuid4()))
                    denial(
                        db,
                        seed,
                        lambda: D.service(db, seed).publish(next_request),
                        revoked_cause(kind),
                    )
                else:
                    request = seed["full_request"]
                    fresh_command = D.changed(
                        request.command, command_id=str(uuid4()), idempotency_key=str(uuid4())
                    )
                    fresh_request = D.FullCommitRequest(fresh_command, request.sources)
                    denial(
                        db,
                        seed,
                        lambda: D.service(db, seed).commit_full(fresh_request),
                        revoked_cause(kind),
                    )
        witness(
            "both_registry_orders",
            kind=kind,
            revoke_first=revoke_first,
            persisted=snapshot(db, seed),
        )


@pytest.mark.parametrize("mode", ["CONTINUE", "RESUME"])
@pytest.mark.parametrize("loss", ["registry", "epoch"])
def test_b16_continue_resume_after_invalidation(database_urls: Any, mode: str, loss: str) -> None:
    _execution_loss(database_urls, mode, loss)


@pytest.mark.parametrize("kind", ["T3", "T6", "T7"])
@pytest.mark.parametrize("revoked", [False, True])
def test_b17_transitive_revoke_denied(
    database_urls: Any, monkeypatch: Any, kind: str, revoked: bool
) -> None:
    seed, operation = target(database_urls, kind)
    with connect(database_urls["admin"]) as db:
        original = D.ProtocolExecutionService._artifacts

        def omit(self: Any, ids: Any) -> Any:
            return original(self, [x for x in ids if x != str(seed["c"])])

        with monkeypatch.context() as patch:
            patch.setattr(D.ProtocolExecutionService, "_artifacts", omit)
            denial(
                db,
                seed,
                lambda: operation(db),
                "registry artifact dependency closure is incomplete"
                if kind == "T3"
                else "KL_REGISTRY_DEPENDENCY_INCOMPLETE",
            )
        if revoked:
            history = snapshot(db, seed)
            revoke_now(database_urls, seed)
            denial(db, seed, lambda: operation(db), revoked_cause(kind))
            assert snapshot(db, seed) == history
            with db.transaction():
                assert db.execute(
                    "SELECT count(*) FROM kineticloop.artifact_revocation_events WHERE ref_s49_id=%s",
                    (seed["a"],),
                ).fetchone() == (0,)
            witness(
                "transitive_direct_unrevoked_leaf_revoked",
                kind=kind,
                direct=seed["a"],
                leaf=seed["c"],
                history=history,
            )
        else:
            positive = operation(db)
            D.assert_event(db, seed, positive)
            after = snapshot(db, seed)
            with db.transaction():
                payload = db.execute(
                    "SELECT typed_payload FROM kineticloop.decision_manifests WHERE subject_id=%s",
                    (D.auth(seed).subject_id,),
                ).fetchone()[0]
            assert all(str(seed[k]) in payload["artifact_closure_ids"] for k in ("a", "b", "c"))
            witness(
                "complete_unrevoked_transitive_positive",
                kind=kind,
                result=positive,
                persisted=after,
            )
