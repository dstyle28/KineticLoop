from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier, Event
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

import kineticloop.persistence.factsets as service_module
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.factsets import (
    BeginBuild,
    BuilderIdentity,
    CanonicalViewService,
    CompleteFactset,
    SealFactset,
    WriteCandidate,
)
from kineticloop.persistence.transactions import (
    EventWrite,
    GuardRequired,
    IdempotencyConflict,
    RepositoryTransaction,
    RestrictedSqlSession,
)
from kineticloop.protocol.factsets import EvidenceBasis, FactsetError, Member

ROOT = Path(__file__).parents[2]
_SPEC = spec_from_file_location("kl023_migrations", ROOT / "tests/db/test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_MIGRATIONS: Any = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATIONS)
SUBJECT, POLICY, PROGRAM, ASSOCIATION, ADMISSION, FACT = (UUID(int=23000 + n) for n in range(6))
EVIDENCE, CANDIDATE, UNDERLYING = (UUID(int=23100 + n) for n in range(3))
BASIS = EvidenceBasis((ASSOCIATION,), (ADMISSION,), (), "2026-09-30T00:00:00Z", "ALL")
BUILDER = BuilderIdentity(
    RoleIdentity("00000000-0000-8000-8000-000000023900", ActorRole.TEST), SUBJECT
)
MEMBERS = (
    Member("ASSOCIATION", "unresolved", "ALL", ASSOCIATION),
    Member("ADMISSION", "contrary", "ALL", ADMISSION),
    Member("FACT", "actual", "TEST_ONLY", FACT),
)


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    shortsha = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
    ).strip()
    lifecycle = DatabaseLifecycle(ROOT)
    lifecycle.namespace = DatabaseNamespace(
        f"kineticloop-kl023-{shortsha}", f"kineticloop_kl023_{shortsha}"
    )
    try:
        urls = _MIGRATIONS.bootstrap_two_phase(lifecycle)
        with psycopg.connect(urls["admin"], autocommit=True) as db:
            # Only immutable prerequisite inputs are seeded. All factsets, candidate
            # operations, completions, seals and racing T2-IN mutations use owners.
            db.execute(
                "INSERT INTO kineticloop.policy_bundles "
                "(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) "
                "VALUES (%s,%s,'test:kl023','1','kl023-test-policy',%s)",
                (
                    POLICY,
                    SUBJECT,
                    Jsonb(
                        {
                            "t2_invalidation_scopes": {
                                "AcceptFactRevision": "TEST_ONLY",
                                "ActivateApprovedProgram": "TEST_ONLY",
                            },
                            "factset_max_delta_depth": 1,
                        }
                    ),
                ),
            )
            db.execute(
                "INSERT INTO kineticloop.program_versions "
                "(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test-kl023',1)",
                (PROGRAM, SUBJECT),
            )
            db.execute(
                "INSERT INTO kineticloop.user_decision_state "
                "(subject_id,input_frontier_hash,active_policy_bundle_id,active_program_id) "
                "VALUES (%s,'frontier-0',%s,%s)",
                (SUBJECT, POLICY, PROGRAM),
            )
            db.execute(
                "INSERT INTO kineticloop.evidence_revisions "
                "(id,subject_id,source_connection_identity,source_object_type,source_object_identity,"
                "source_revision,trust_class,source_class,command_authority) "
                "VALUES (%s,%s,'kl023-test','observation','test-1','1','USER_REPORTED','USER','NONE')",
                (EVIDENCE, SUBJECT),
            )
            db.execute(
                "INSERT INTO kineticloop.candidate_assertions "
                "(id,subject_id,assertion_family_identity,ref_s09_id) "
                "VALUES (%s,%s,'test-assertion',%s)",
                (CANDIDATE, SUBJECT, EVIDENCE),
            )
            db.execute(
                "INSERT INTO kineticloop.underlying_events "
                "(id,subject_id,event_identity) VALUES (%s,%s,'test-underlying')",
                (UNDERLYING, SUBJECT),
            )
            db.execute(
                "INSERT INTO kineticloop.event_association_decisions "
                "(id,subject_id,association_family_identity,association_state) "
                "VALUES (%s,%s,'unresolved','UNRESOLVED')",
                (ASSOCIATION, SUBJECT),
            )
            db.execute(
                "INSERT INTO kineticloop.admission_decisions "
                "(id,subject_id,action_scope,decision,ref_s05_id,ref_s09_id,ref_s10_id) "
                "VALUES (%s,%s,'ALL','DENIED',%s,%s,%s)",
                (ADMISSION, SUBJECT, POLICY, EVIDENCE, CANDIDATE),
            )
            db.execute(
                "INSERT INTO kineticloop.canonical_fact_revisions "
                "(id,subject_id,stable_fact_identity,fact_kind,fact_revision,ref_s10_id,ref_s11_id,ref_s13_id) "
                "VALUES (%s,%s,'actual','HEALTH_OBSERVATION',1,%s,%s,%s)",
                (FACT, SUBJECT, CANDIDATE, UNDERLYING, ADMISSION),
            )
        with psycopg.connect(urls["trusted_admin"], autocommit=True) as db:
            db.execute(
                "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
                (SUBJECT, POLICY, UUID(int=23901), "kl_test_subject_1_login"),
            )
        yield urls
    finally:
        lifecycle.destroy()


def service(db: Any) -> CanonicalViewService:
    return CanonicalViewService(db, BUILDER)


def begin(
    db: Any, key: str, *, parent: UUID | None = None, depth: int = 1
) -> tuple[UUID, BeginBuild]:
    with db.transaction():
        row = db.execute(
            "SELECT input_frontier_hash,authorization_epoch,active_policy_bundle_id FROM "
            "kineticloop.user_decision_state WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone()
    assert row is not None
    command = BeginBuild(
        SUBJECT,
        key,
        row[0],
        row[1],
        PROGRAM,
        row[2],
        BASIS,
        parent_id=parent,
        max_delta_depth=depth,
    )
    result = service(db).begin_build(command)
    return UUID(result["build_id"]), command


def populate(db: Any, build: UUID) -> None:
    for i, member in enumerate(MEMBERS):
        service(db).write_candidate(WriteCandidate(SUBJECT, f"member-{i}", build, i, member))


def closed(db: Any, key: str) -> tuple[UUID, Mapping[str, Any]]:
    build, _ = begin(db, key)
    populate(db, build)
    return build, service(db).complete_factset(CompleteFactset(SUBJECT, "complete", build, 3))


def state(db: Any, build: UUID) -> Any:
    with db.transaction():
        return db.execute(
            "SELECT current_factset_id,authorization_epoch,input_frontier_hash,"
            "(SELECT row_to_json(s) FROM kineticloop.factset_revisions s WHERE id=%s),"
            "(SELECT count(*) FROM kineticloop.command_receipts WHERE subject_id=%s),"
            "(SELECT count(*) FROM kineticloop.domain_events WHERE subject_id=%s),"
            "(SELECT count(*) FROM kineticloop.outbox_deliveries WHERE subject_id=%s) "
            "FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (build, SUBJECT, SUBJECT, SUBJECT, SUBJECT),
        ).fetchone()


def test_build_replay_and_sealed_only_reads(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"]) as db:
        api = service(db)
        build, command = begin(db, "lifecycle")
        original = api.begin_build(command)
        assert original["build_id"] == str(build)
        gate = Barrier(2)
        simultaneous = replace(command, key="parallel-begin")

        def run_begin() -> Any:
            with psycopg.connect(database_urls["admin"]) as contender:
                gate.wait(timeout=8)
                return service(contender).begin_build(simultaneous)

        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(run_begin), pool.submit(run_begin)
            assert a.result(timeout=8) == b.result(timeout=8)
        with db.transaction():
            assert db.execute(
                "SELECT count(*) FROM kineticloop.factset_revisions "
                "WHERE subject_id=%s AND factset_identity='kl023:parallel-begin'",
                (SUBJECT,),
            ).fetchone() == (1,)
        with pytest.raises(FactsetError, match="policy"):
            api.begin_build(replace(command, key="bad-policy-bound", max_delta_depth=2))
        wrong_namespace = CanonicalViewService(
            db, replace(BUILDER, actor=RoleIdentity(str(uuid4()), ActorRole.SUBJECT))
        )
        with pytest.raises(GuardRequired, match="namespace"):
            wrong_namespace.begin_build(command)
        with pytest.raises(GuardRequired, match="builder"):
            BuilderIdentity(RoleIdentity(str(uuid4()), ActorRole.EVALUATION), SUBJECT)

        with pytest.raises(IdempotencyConflict):
            api.begin_build(replace(command, captured_input_frontier="changed"))
        with pytest.raises(GuardRequired, match="subject"):
            api.begin_build(replace(command, subject_id=uuid4()))
        alien = CanonicalViewService(
            db, replace(BUILDER, actor=RoleIdentity(str(uuid4()), ActorRole.TEST))
        )
        with pytest.raises(GuardRequired, match="ownership"):
            alien.begin_build(command)
        with pytest.raises(FactsetError, match="unsealed"):
            api.read_canonical(SUBJECT, build)
        first = WriteCandidate(SUBJECT, "member-0", build, 0, MEMBERS[0])
        original_member = api.write_candidate(first)
        assert api.write_candidate(first) == original_member
        member_state = state(db, build)
        with pytest.raises(psycopg.errors.UniqueViolation):
            api.write_candidate(
                replace(first, key="duplicate-logical-key", expected_member_revision=1)
            )
        assert state(db, build) == member_state

        with pytest.raises(IdempotencyConflict):
            api.write_candidate(replace(first, member=replace(MEMBERS[0], key="changed")))
        with pytest.raises(FactsetError, match="foreign"):
            api.write_candidate(
                replace(first, key="foreign", member=replace(MEMBERS[0], revision_id=uuid4()))
            )
        with pytest.raises(GuardRequired):
            alien.write_candidate(replace(first, key="alien"))
        for i in (1, 2):
            api.write_candidate(WriteCandidate(SUBJECT, f"member-{i}", build, i, MEMBERS[i]))
        complete = CompleteFactset(SUBJECT, "complete", build, 3)
        result = api.complete_factset(complete)
        before = state(db, build)
        assert api.complete_factset(complete) == result
        assert api.complete_factset(replace(complete, key="natural-complete")) == result
        with pytest.raises(GuardRequired):
            api.complete_factset(replace(complete, expected_member_revision=2))
        with pytest.raises(GuardRequired):
            api.write_candidate(WriteCandidate(SUBJECT, "late", build, 3, MEMBERS[0]))
        with pytest.raises(FactsetError, match="unsealed"):
            api.read_canonical(SUBJECT, build)
        assert state(db, build) == before
        seal = SealFactset(SUBJECT, "seal", build, result)
        sealed = api.seal_factset(seal)
        assert sealed["factset_id"] == str(build)
        assert api.complete_factset(complete) == result
        assert api.complete_factset(replace(complete, key="natural-complete-sealed")) == result
        assert api.seal_factset(replace(seal, key="natural-seal")) == sealed
        assert api.write_candidate(first) == original_member
        assert api.begin_build(command) == original
        canonical = api.read_canonical(SUBJECT, build)
        assert canonical.member_count == 3
        assert canonical.membership_digest == result["membership_digest"]
        assert {m.revision_id for m in canonical.members} == {FACT, ADMISSION, ASSOCIATION}
        assert state(db, build)[0] == build
        # Real DELTA REMOVE, then depth boundary checkpoint to FULL.
        delta, _ = begin(db, "delta", parent=build)
        api.write_candidate(
            WriteCandidate(
                SUBJECT,
                "remove",
                delta,
                0,
                replace(MEMBERS[2], operation="REMOVE", revision_id=None),
            )
        )
        dc = api.complete_factset(CompleteFactset(SUBJECT, "complete", delta, 1))
        api.seal_factset(SealFactset(SUBJECT, "delta-seal", delta, dc))
        checkpoint, checkpoint_command = begin(db, "checkpoint", parent=delta)
        assert api.begin_build(checkpoint_command)["storage_mode"] == "FULL"
        cc = api.complete_factset(CompleteFactset(SUBJECT, "complete", checkpoint, 0))
        assert cc["membership_digest"] == dc["membership_digest"]
        api.seal_factset(SealFactset(SUBJECT, "checkpoint-seal", checkpoint, cc))
        assert api.read_canonical(SUBJECT, checkpoint) == api.read_canonical(SUBJECT, delta)
        for target in (build, delta, checkpoint):
            with pytest.raises(psycopg.Error):
                with db.transaction():
                    db.execute(
                        "UPDATE kineticloop.factset_revisions SET membership_digest='bad' WHERE id=%s",
                        (target,),
                    )
            with pytest.raises(psycopg.Error):
                with db.transaction():
                    db.execute(
                        "INSERT INTO kineticloop.factset_members "
                        "(subject_id,ref_s15_id,member_kind,logical_member_key,action_scope,member_operation) "
                        "VALUES (%s,%s,'FACT','late','ALL','REMOVE')",
                        (SUBJECT, target),
                    )
        print(
            "persisted lifecycle: builder/key conflicts, READY/SEALED immutable, complete basis, DELTA/FULL identical"
        )


def observe_blocking(observer: Any, name: str) -> int:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        row = observer.execute(
            "SELECT pid,pg_blocking_pids(pid),query FROM pg_stat_activity "
            "WHERE application_name=%s AND cardinality(pg_blocking_pids(pid))>0",
            (name,),
        ).fetchone()
        if row:
            print(f"PostgreSQL barrier {name}: blocking_pids={row[1]}, query={row[2]}")
            return row[0]
    raise AssertionError("PostgreSQL did not observe bounded lock blocking")


@pytest.mark.parametrize("winner", ["complete", "writer"])
def test_complete_serializes_with_candidate_writer(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch, winner: str
) -> None:
    url = database_urls["admin"]
    with psycopg.connect(url) as db:
        build, _ = begin(db, f"race-{winner}")
        for i in (0, 1):
            service(db).write_candidate(
                WriteCandidate(SUBJECT, f"member-{i}", build, i, MEMBERS[i])
            )
    held, release = Event(), Event()
    original = service_module.execute_factset_build
    first_kind = "CompleteFactset" if winner == "complete" else "WriteCandidate"

    def instrument(
        connection: Any, kind: str, subject: UUID, build_id: UUID, operation: Any, **kwargs: Any
    ) -> Any:
        def hold(session: Any) -> Any:
            outcome = operation(session)
            if (
                kind == first_kind
                and connection.info.parameter_status("application_name") == f"kl023-{winner}"
            ):
                assert "user_decision_state" not in session.relation_locks()
                held.set()
                assert release.wait(8)
            return outcome

        return original(connection, kind, subject, build_id, hold, **kwargs)

    monkeypatch.setattr(service_module, "execute_factset_build", instrument)

    def run(kind: str, name: str) -> Any:
        with psycopg.connect(
            url, application_name=name, options="-c lock_timeout=10000 -c statement_timeout=15000"
        ) as db:
            api = service(db)
            if kind == "CompleteFactset":
                return api.complete_factset(CompleteFactset(SUBJECT, "complete", build, 2))
            return api.write_candidate(
                WriteCandidate(SUBJECT, "racing-writer", build, 2, MEMBERS[2])
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, first_kind, f"kl023-{winner}")
        if not held.wait(8):
            first.result(timeout=1)
            raise AssertionError("first owner failed to establish barrier")
        other_kind = "WriteCandidate" if winner == "complete" else "CompleteFactset"
        other_name = f"kl023-{winner}-loser"
        second = pool.submit(run, other_kind, other_name)
        try:
            with psycopg.connect(url, autocommit=True) as observer:
                observe_blocking(observer, other_name)
                # S01 remains immediately obtainable throughout bulk/build gating.
                with observer.transaction():
                    observer.execute(
                        "SELECT 1 FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE NOWAIT",
                        (SUBJECT,),
                    )
        finally:
            release.set()
        result = first.result(timeout=8)
        with pytest.raises(GuardRequired):
            second.result(timeout=8)
    with psycopg.connect(url) as db:
        if winner == "writer":
            assert result["member_revision"] == 3
            result = service(db).complete_factset(CompleteFactset(SUBJECT, "fresh", build, 3))
        with db.transaction():
            row = db.execute(
                "SELECT status,member_revision,completed_member_revision,membership_digest,typed_payload,"
                "(SELECT count(*) FROM kineticloop.factset_members WHERE ref_s15_id=%s) "
                "FROM kineticloop.factset_revisions WHERE id=%s",
                (build, build),
            ).fetchone()
        assert row is not None and row[0] == "READY"
        expected = 2 if winner == "complete" else 3
        assert row[1] == row[2] == row[5] == expected
        assert row[3] == result["membership_digest"] and row[4]["member_count"] == expected
        print(
            f"persisted race winner={winner}: closed revision/count={expected}, certificate={result['completion_certificate']}"
        )


def input_revision(db: Any, key: str) -> Any:
    receipt, event, association = uuid4(), uuid4(), uuid4()

    def operation(tx: RepositoryTransaction) -> Any:
        tx.lock_subject()
        epoch_row = db.execute(
            "SELECT authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (SUBJECT,),
        ).fetchone()
        assert epoch_row is not None
        epoch = epoch_row[0]

        def mutate(session: RestrictedSqlSession) -> Mapping[str, Any]:
            session.insert(
                "S14",
                {
                    "id": association,
                    "subject_id": SUBJECT,
                    "stable_fact_identity": key,
                    "fact_kind": "HEALTH_OBSERVATION",
                    "fact_revision": 1,
                    "ref_s10_id": CANDIDATE,
                    "ref_s11_id": UNDERLYING,
                    "ref_s13_id": ADMISSION,
                },
            )
            session.insert(
                "S43",
                {
                    "id": uuid4(),
                    "subject_id": SUBJECT,
                    "event_kind": "EPOCH_INVALIDATED",
                    "invalidated_epoch": epoch + 1,
                    "scope": "TEST_ONLY",
                    "causation_key": key,
                    "ref_s02_id": receipt,
                },
            )
            session.update(
                "S01",
                {
                    "input_frontier_hash": key,
                    "authorization_epoch": epoch + 1,
                },
                {"subject_id": SUBJECT},
            )
            return {"association_id": str(association), "epoch": epoch + 1}

        return tx.idempotent_outcome(
            receipt_id=receipt,
            actor_scope="test",
            client_key=key,
            request_hash=key,
            mutation=mutate,
            invalidation_scope="TEST_ONLY",
            event=EventWrite(
                event,
                "ASSOCIATION",
                str(association),
                1,
                "ASSOCIATION_DECIDED",
                "canonical",
                uuid4(),
            ),
        )

    return service_module.execute_command(db, "AcceptFactRevision", SUBJECT, operation)


class TraceCursor(psycopg.Cursor[Any]):
    trace: list[str] = []

    def execute(self, query: Any, *args: Any, **kwargs: Any) -> Any:
        self.trace.append(str(query))
        return super().execute(query, *args, **kwargs)


@pytest.mark.parametrize("winner", ["input", "seal"])
def test_seal_frontier_atomicity_and_old_replay(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch, winner: str
) -> None:
    url = database_urls["admin"]
    with psycopg.connect(url) as db:
        build, completion = closed(db, f"seal-race-{winner}")
        seal_command = SealFactset(SUBJECT, f"seal-race-{winner}", build, completion)
        before = state(db, build)
        # Mismatched identity/digest and injected failures leave all five surfaces unchanged.
        for field in (
            "membership_digest",
            "completion_identity",
            "completion_certificate",
            "domain_basis_digest",
            "program_revision_id",
            "captured_input_frontier",
        ):
            with pytest.raises(GuardRequired):
                service(db).seal_factset(
                    replace(
                        seal_command,
                        key=f"bad-{field}-{winner}",
                        completion=dict(completion) | {field: "wrong"},
                    )
                )
            assert state(db, build) == before
        update = RestrictedSqlSession.update

        def fail_after_pointer(self: Any, logical: str, values: Any, predicates: Any) -> Any:
            result = update(self, logical, values, predicates)
            if logical == "S01" and "current_factset_id" in values:
                raise RuntimeError("KL023 injected after pointer write")
            return result

        with monkeypatch.context() as patch:
            patch.setattr(RestrictedSqlSession, "update", fail_after_pointer)
            with pytest.raises(RuntimeError, match="injected"):
                service(db).seal_factset(seal_command)
        assert state(db, build) == before
        # READY is DB immutable as well as service immutable.
        with pytest.raises(psycopg.Error):
            with db.transaction():
                db.execute(
                    "UPDATE kineticloop.factset_revisions SET typed_payload='{}' WHERE id=%s",
                    (build,),
                )
        assert state(db, build) == before
    held, release = Event(), Event()
    original = service_module.execute_command
    first_kind = "AcceptFactRevision" if winner == "input" else "SealFactset"

    def instrument(connection: Any, kind: str, subject: UUID, operation: Any) -> Any:
        def hold(tx: Any) -> Any:
            result = operation(tx)
            if (
                kind == first_kind
                and connection.info.parameter_status("application_name") == f"kl023-first-{winner}"
            ):
                held.set()
                assert release.wait(8)
            return result

        return original(connection, kind, subject, hold)

    monkeypatch.setattr(service_module, "execute_command", instrument)

    def run(kind: str, name: str) -> Any:
        with psycopg.connect(
            url,
            application_name=name,
            cursor_factory=TraceCursor,
            options="-c lock_timeout=10000 -c statement_timeout=15000",
        ) as db:
            if kind == "SealFactset":
                return service(db).seal_factset(seal_command)
            return input_revision(db, f"input-{winner}")

    TraceCursor.trace = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, first_kind, f"kl023-first-{winner}")
        if not held.wait(8):
            first.result(timeout=1)
            raise AssertionError("first owner failed to establish barrier")
        other_kind = "SealFactset" if winner == "input" else "AcceptFactRevision"
        other_name = f"kl023-second-{winner}"
        second = pool.submit(run, other_kind, other_name)
        try:
            with psycopg.connect(url, autocommit=True) as observer:
                observe_blocking(observer, other_name)
        finally:
            release.set()
        first.result(timeout=8)
        if winner == "input":
            with pytest.raises(GuardRequired, match="stale"):
                second.result(timeout=8)
        else:
            second.result(timeout=8)
    assert not any("factset_members" in q for q in TraceCursor.trace), TraceCursor.trace
    seal_queries = [q for q in TraceCursor.trace if "jsonb_build_object" in q]
    assert seal_queries and all(
        "domain_basis'" not in q and "checkpoint'" not in q and "build_replays'" not in q
        for q in seal_queries
    )

    with psycopg.connect(url) as db:
        after = state(db, build)
        assert after[1] == before[1] + 1 and after[2] == f"input-{winner}"
        assert after[4:] == tuple(x + (1 if winner == "input" else 2) for x in before[4:])
        if winner == "input":
            assert after[0] == before[0] and after[3] == before[3]
            with pytest.raises(GuardRequired):
                service(db).seal_factset(seal_command)
            assert state(db, build) == after
        else:
            assert after[0] == build and after[3]["status"] == "SEALED"
            original_seal = service(db).seal_factset(seal_command)
            newer, newer_completion = closed(db, "newer-after-seal")
            service(db).seal_factset(SealFactset(SUBJECT, "newer-seal", newer, newer_completion))
            newer_state = state(db, build)
            # ACK-loss replay after a newer head returns only the original identity.
            assert service(db).seal_factset(seal_command) == original_seal
            assert (
                service(db).seal_factset(replace(seal_command, key="old-natural-seal"))
                == original_seal
            )
            assert (
                service(db).complete_factset(
                    CompleteFactset(SUBJECT, "old-natural-complete", build, 3)
                )
                == completion
            )

            assert state(db, build) == newer_state and newer_state[0] == newer
            with pytest.raises(IdempotencyConflict):
                service(db).seal_factset(
                    replace(seal_command, completion=dict(completion) | {"member_count": 999})
                )
            assert state(db, build) == newer_state
        print(
            f"persisted T2 serial outcome={winner}; all S01/S15/S02/S03/S04 atomic, seal member scans=0"
        )


def test_begin_replay_after_concurrent_frontier_change(database_urls: dict[str, str]) -> None:
    url = database_urls["admin"]
    with psycopg.connect(url) as db:
        with db.transaction():
            row = db.execute(
                "SELECT input_frontier_hash,authorization_epoch FROM "
                "kineticloop.user_decision_state WHERE subject_id=%s",
                (SUBJECT,),
            ).fetchone()
        assert row is not None
        command = BeginBuild(
            SUBJECT,
            "begin-frontier-race",
            row[0],
            row[1],
            PROGRAM,
            POLICY,
            BASIS,
            max_delta_depth=1,
        )
    captured, release = Event(), Event()

    class SnapshotBarrierConnection(psycopg.Connection[Any]):
        def execute(self, query: Any, *args: Any, **kwargs: Any) -> Any:
            if str(query).startswith(
                "SELECT input_frontier_hash,authorization_epoch,active_program_id,"
            ):
                # This is after the owner's initial absent-S15 replay read and before
                # S01 snapshot capture; no build or S01 row lock is held here.
                captured.set()
                assert release.wait(8)
            return super().execute(query, *args, **kwargs)

    def retry() -> Any:
        with SnapshotBarrierConnection.connect(
            url,
            application_name="kl023-begin-retry",
            options="-c lock_timeout=10000 -c statement_timeout=15000",
        ) as db:
            return service(db).begin_build(command)

    with ThreadPoolExecutor(max_workers=1) as pool:
        second = pool.submit(retry)
        assert captured.wait(8)
        try:
            with psycopg.connect(url, autocommit=True) as observer:
                rows = observer.execute(
                    "SELECT pid,state,query,pg_blocking_pids(pid) "
                    "FROM pg_stat_activity WHERE application_name='kl023-begin-retry'"
                ).fetchall()
                assert len(rows) == 1 and rows[0][1] == "idle in transaction"
                assert "factset_revisions" in rows[0][2] and rows[0][3] == []
                print(
                    f"PostgreSQL Begin barrier: state={rows[0][1]}, query={rows[0][2]}, blockers={rows[0][3]}"
                )
            with psycopg.connect(url) as first:
                original = service(first).begin_build(command)
                input_revision(first, "begin-frontier-advance")
                before = state(first, UUID(original["build_id"]))
        finally:
            release.set()
        assert second.result(timeout=8) == original
    with psycopg.connect(url) as db:
        assert service(db).begin_build(command) == original
        assert state(db, UUID(original["build_id"])) == before
        with db.transaction():
            assert db.execute(
                "SELECT count(*) FROM kineticloop.factset_revisions "
                "WHERE subject_id=%s AND factset_identity='kl023:begin-frontier-race'",
                (SUBJECT,),
            ).fetchone() == (1,)
        print(
            "persisted concurrent Begin replay: original identity survives newer frontier/epoch; no repeated mutations"
        )


def test_policy_depth_decrease_compacts_historical_parent(database_urls: dict[str, str]) -> None:
    zero_policy = UUID(int=23990)
    with psycopg.connect(database_urls["admin"], autocommit=True) as db:
        # Immutable policy input is seeded; every active-policy/head mutation uses owners.
        db.execute(
            "INSERT INTO kineticloop.policy_bundles "
            "(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) "
            "VALUES (%s,%s,'test:kl023','zero-depth','kl023-zero-depth',%s)",
            (
                zero_policy,
                SUBJECT,
                Jsonb(
                    {
                        "factset_max_delta_depth": 0,
                        "t2_invalidation_scopes": {"ActivateApprovedProgram": "TEST_ONLY"},
                    }
                ),
            ),
        )
    with psycopg.connect(database_urls["admin"]) as db:
        api = service(db)
        full, completion = closed(db, "policy-decrease-full")
        api.seal_factset(SealFactset(SUBJECT, "policy-decrease-full-seal", full, completion))
        delta, _ = begin(db, "policy-decrease-delta", parent=full)
        dc = api.complete_factset(CompleteFactset(SUBJECT, "complete", delta, 0))
        api.seal_factset(SealFactset(SUBJECT, "policy-decrease-delta-seal", delta, dc))
        canonical = api.read_canonical(SUBJECT, delta)

        def activate(policy: UUID, key: str) -> None:
            receipt, event = uuid4(), uuid4()

            def operation(tx: RepositoryTransaction) -> Any:
                tx.lock_subject()
                row = db.execute(
                    "SELECT authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
                    (SUBJECT,),
                ).fetchone()
                assert row is not None
                epoch = row[0] + 1

                def mutate(session: RestrictedSqlSession) -> Mapping[str, Any]:
                    session.insert(
                        "S43",
                        {
                            "id": uuid4(),
                            "subject_id": SUBJECT,
                            "event_kind": "EPOCH_INVALIDATED",
                            "invalidated_epoch": epoch,
                            "scope": "TEST_ONLY",
                            "causation_key": key,
                            "ref_s02_id": receipt,
                        },
                    )
                    session.update(
                        "S01",
                        {
                            "active_policy_bundle_id": policy,
                            "authorization_epoch": epoch,
                        },
                        {"subject_id": SUBJECT},
                    )
                    return {"policy_id": str(policy)}

                return tx.idempotent_outcome(
                    receipt_id=receipt,
                    actor_scope="test",
                    client_key=key,
                    request_hash=key,
                    mutation=mutate,
                    invalidation_scope="TEST_ONLY",
                    event=EventWrite(
                        event, "PROGRAM", str(event), 1, "PROGRAM_ACTIVATED", "canonical", uuid4()
                    ),
                )

            service_module.execute_command(db, "ActivateApprovedProgram", SUBJECT, operation)

        activate(zero_policy, "policy-decrease-activate")
        try:
            checkpoint, command = begin(db, "policy-decrease-checkpoint", parent=delta, depth=0)
            outcome = api.begin_build(command)
            assert outcome["storage_mode"] == "FULL" and outcome["delta_depth"] == 0
            cc = api.complete_factset(CompleteFactset(SUBJECT, "complete", checkpoint, 0))
            assert cc["membership_digest"] == dc["membership_digest"]
            api.seal_factset(
                SealFactset(SUBJECT, "policy-decrease-checkpoint-seal", checkpoint, cc)
            )
            assert api.read_canonical(SUBJECT, checkpoint) == canonical
            with db.transaction():
                row = db.execute(
                    "SELECT typed_payload->>'parent_factset_id',typed_payload->'max_delta_depth' "
                    "FROM kineticloop.factset_revisions WHERE id=%s",
                    (checkpoint,),
                ).fetchone()
            assert row == (None, 0)
            print(
                "persisted policy decrease: historical depth-1 chain validates at old bound; new depth-0 FULL preserves digest/count"
            )
        finally:
            activate(POLICY, "policy-decrease-restore")
