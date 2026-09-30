from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier, Event
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.planning import (
    AcquireLease,
    AdmitOrReviseIntent,
    PlanningIdentity,
    PlanningWorkflowService,
    RenewLease,
)
from kineticloop.persistence.transactions import (
    FenceLost,
    IdempotencyConflict,
    RepositoryTransaction,
    RestrictedSqlSession,
    execute_command,
)
from kineticloop.workflow.planning import TERMINAL, PlanningDenied

ROOT = Path(__file__).parents[2]
_SPEC = spec_from_file_location("kl024_migrations", ROOT / "tests/db/test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_MIGRATIONS: Any = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATIONS)
SUBJECT, POLICY = UUID(int=24001), UUID(int=24005)
IDENTITY = PlanningIdentity(
    RoleIdentity("00000000-0000-8000-8000-000000024900", ActorRole.TEST), SUBJECT
)
OTHER = PlanningIdentity(
    RoleIdentity("00000000-0000-8000-8000-000000024901", ActorRole.TEST), SUBJECT
)
POLICY_BODY = {
    "version": "kl024-v1",
    "purposes": ["TRAINING", "NUTRITION"],
    "triggers": ["USER_REQUEST", "INPUT_EVENT"],
    "auto_root_triggers": [],
    "max_active_per_day": 1,
    "capacity_available": True,
    "hourly_roots": 3,
    "daily_roots": 3,
    "deadline_seconds": 3600,
    "calendar_policies": ["test:UTC-v1"],
    "root_limits": {"calls": 5, "tokens": 1000, "tools": 10},
}


@pytest.fixture()
def database_urls() -> Iterator[dict[str, str]]:
    short = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
    ).strip()
    lifecycle = DatabaseLifecycle(ROOT)
    lifecycle.namespace = DatabaseNamespace(
        f"kineticloop-kl024-{short}", f"kineticloop_kl024_{short}"
    )
    try:
        urls = _MIGRATIONS.bootstrap_two_phase(lifecycle)
        with psycopg.connect(urls["admin"], autocommit=True) as db:
            # Only trusted TEST scope, immutable policy and the prerequisite S01 are seeded.
            # Every positive S27/S28/S29/S30 operation below uses PlanningWorkflowService.
            db.execute(
                "INSERT INTO kineticloop.policy_bundles "
                "(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) "
                "VALUES (%s,%s,'test:kl024','1','kl024-policy',%s)",
                (POLICY, SUBJECT, Jsonb({"planning_admission": POLICY_BODY})),
            )
            db.execute(
                "INSERT INTO kineticloop.user_decision_state "
                "(subject_id,input_frontier_hash,active_policy_bundle_id) VALUES (%s,'basis-1',%s)",
                (SUBJECT, POLICY),
            )
            program, factset, build, artifact, manifest = (UUID(int=24010 + n) for n in range(5))
            db.execute(
                "INSERT INTO kineticloop.program_versions "
                "(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test:kl024',1)",
                (program, SUBJECT),
            )
            db.execute(
                "INSERT INTO kineticloop.factset_revisions "
                "(id,subject_id,factset_identity,status,storage_mode) VALUES (%s,%s,%s,'SEALED','FULL')",
                (factset, SUBJECT, str(factset)),
            )
            db.execute(
                "INSERT INTO kineticloop.manifest_builds "
                "(id,subject_id,build_identity,status,captured_epoch) VALUES (%s,%s,'test:kl024','PUBLISHED',0)",
                (build, SUBJECT),
            )
            db.execute(
                "INSERT INTO kineticloop.safety_artifacts "
                "(id,artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,ref_s05_id) "
                "VALUES (%s,'POLICY_BUNDLE','test:kl024','1','kl024-policy','BOUNDED',clock_timestamp(),clock_timestamp()+interval '1 day',%s)",
                (artifact, POLICY),
            )
            db.execute(
                "INSERT INTO kineticloop.decision_manifests "
                "(id,subject_id,generation,captured_epoch,manifest_hash,registry_revision_at_publish,valid_until,ref_s05_id,ref_s06_id,ref_s15_id,ref_s23_id,ref_s49_id,registry_state_id) "
                "VALUES (%s,%s,1,0,'test:manifest',0,clock_timestamp()+interval '1 day',%s,%s,%s,%s,%s,1)",
                (manifest, SUBJECT, POLICY, program, factset, build, artifact),
            )
            db.execute(
                "UPDATE kineticloop.user_decision_state SET current_manifest_id=%s WHERE subject_id=%s",
                (manifest, SUBJECT),
            )
        with psycopg.connect(urls["trusted_admin"], autocommit=True) as db:
            db.execute(
                "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
                (SUBJECT, POLICY, UUID(int=24902), "kl_test_subject_1_login"),
            )
        yield urls
    finally:
        lifecycle.destroy()


def service(db: Any, identity: PlanningIdentity = IDENTITY) -> PlanningWorkflowService:
    return PlanningWorkflowService(db, identity)


def request(key: str, **changes: Any) -> AdmitOrReviseIntent:
    return replace(
        AdmitOrReviseIntent(
            SUBJECT,
            key,
            date(2026, 9, 30),
            "TRAINING",
            "test:UTC-v1",
            {"equipment": ["band", "mat"], "minutes": 30},
        ),
        **changes,
    )


def read(url: str, statement: str, args: Any = ()) -> list[Any]:
    with psycopg.connect(url, autocommit=True) as db:
        return db.execute(statement, args).fetchall()


def counts(url: str) -> tuple[int, ...]:
    return tuple(
        read(url, f"SELECT count(*) FROM kineticloop.{table}")[0][0]
        for table in (
            "planning_intents",
            "planning_request_revisions",
            "planning_attempts",
            "planning_quota_buckets",
            "command_receipts",
            "domain_events",
            "outbox_deliveries",
        )
    )


def admission(url: str, command: AdmitOrReviseIntent) -> Mapping[str, Any]:
    with psycopg.connect(url) as db:
        return service(db).admit_or_revise(command)


def acquire(
    url: str,
    root: Mapping[str, Any],
    key: str = "lease",
    *,
    identity: PlanningIdentity = IDENTITY,
    owner: str | None = None,
    fence: int = 0,
    seconds: int = 60,
) -> Mapping[str, Any]:
    with psycopg.connect(url) as db:
        return service(db, identity).acquire_lease(
            AcquireLease(
                SUBJECT,
                key,
                UUID(root["intent_id"]),
                owner,
                fence,
                root["request_revision"],
                UUID(root["attempt_id"]),
                seconds,
            )
        )


def observe_block(url: str, pid: int) -> None:
    until = time.monotonic() + 5
    with psycopg.connect(url, autocommit=True) as monitor:
        while time.monotonic() < until:
            row = monitor.execute(
                "SELECT wait_event_type,cardinality(pg_blocking_pids(pid)) "
                "FROM pg_stat_activity WHERE pid=%s",
                (pid,),
            ).fetchone()
            if row is not None and row[0] == "Lock" and row[1] > 0:
                return
            time.sleep(0.01)  # Poll observed PG state; elapsed time never proves blocking.
    pytest.fail("PostgreSQL did not observe bounded blocking")


def test_active_partition_and_quota_are_atomic(database_urls: dict[str, str]) -> None:
    url = database_urls["admin"]
    barrier = Barrier(2)

    def contender(key: str) -> Mapping[str, Any]:
        barrier.wait(timeout=5)
        return admission(url, request(key))

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(contender, k) for k in ("root-a", "root-b")]
        results = [f.result(timeout=10) for f in futures]
    assert {r["mode"] for r in results} == {"ADMIT", "JOIN"}
    assert len({r["intent_id"] for r in results}) == 1
    assert counts(url) == (1, 1, 1, 2, 2, 2, 2)
    assert read(url, "SELECT admitted_count FROM kineticloop.planning_quota_buckets") == [
        (1,),
        (1,),
    ]
    with pytest.raises(PlanningDenied, match="concurrency"):
        admission(url, request("purpose", purpose="NUTRITION"))
    with pytest.raises(PlanningDenied, match="automatic"):
        admission(
            url,
            request("auto", local_date=date(2026, 10, 1), explicit=False, trigger="INPUT_EVENT"),
        )
    index = read(url, "SELECT indexdef FROM pg_indexes WHERE indexname='uq_s27_active_partition'")[
        0
    ][0]
    assert "UNIQUE" in index and all(s in index for s in ("ADMITTED", "PENDING", "RUNNING"))
    # Direct privileged writes are negative controls for the physical index, not service evidence.
    for status in ("ADMITTED", "PENDING", "RUNNING"):
        with psycopg.connect(url, autocommit=True) as db:
            with pytest.raises(psycopg.errors.UniqueViolation, match="uq_s27_active_partition"):
                db.execute(
                    "INSERT INTO kineticloop.planning_intents "
                    "(subject_id,purpose,root_request_identity,local_date,status,fence_token) "
                    "VALUES (%s,'TRAINING',%s,DATE '2026-09-30',%s,0)",
                    (SUBJECT, str(uuid4()), status),
                )
    admission(url, request("root-2", local_date=date(2026, 10, 1)))
    barrier = Barrier(2)

    def quota_contender(day: int) -> str:
        barrier.wait(timeout=5)
        try:
            admission(url, request(f"quota-{day}", local_date=date(2026, 10, day)))
            return "ADMIT"
        except PlanningDenied as error:
            assert "quota" in str(error)
            return "DENIED"

    with ThreadPoolExecutor(2) as pool:
        quota_futures = [pool.submit(quota_contender, d) for d in (2, 3)]
        assert sorted(f.result(timeout=10) for f in quota_futures) == ["ADMIT", "DENIED"]
    assert read(url, "SELECT admitted_count FROM kineticloop.planning_quota_buckets") == [
        (3,),
        (3,),
    ]
    assert counts(url) == (3, 3, 3, 2, 4, 4, 4)


def test_join_and_revision_preserve_root_authority(database_urls: dict[str, str]) -> None:
    url = database_urls["admin"]
    root = admission(url, request("root"))
    lease = acquire(url, root)
    # Seed nonzero ledger counters as a downstream-work prerequisite fixture;
    # revision assertions prove they persist, without claiming a dispatch/ledger test.
    with psycopg.connect(url, autocommit=True) as db:
        db.execute(
            "UPDATE kineticloop.planning_intents SET typed_payload="
            "jsonb_set(jsonb_set(typed_payload,'{reserved,calls}','2'),'{settled,tokens}','20')"
        )
    root_state = read(
        url,
        "SELECT deadline,typed_payload,fence_token,lease_owner,lease_expires_at "
        "FROM kineticloop.planning_intents",
    )[0]
    same = admission(
        url, request("join", constraints={"minutes": 30, "equipment": ["mat", "band", "band"]})
    )
    assert same == {**root, "mode": "JOIN"}
    assert counts(url) == (1, 1, 1, 2, 3, 3, 3)
    revision = admission(url, request("revise", constraints={"minutes": 31}))
    assert revision["intent_id"] == root["intent_id"] and revision["request_revision"] == 2
    assert (
        revision["attempt_id"] != root["attempt_id"]
        and revision["request_id"] != root["request_id"]
    )
    assert read(
        url, "SELECT status FROM kineticloop.planning_attempts WHERE id=%s", (root["attempt_id"],)
    ) == [("STALE",)]
    assert (
        root_state
        == read(
            url,
            "SELECT deadline,typed_payload,fence_token,lease_owner,lease_expires_at "
            "FROM kineticloop.planning_intents",
        )[0]
    )
    assert read(url, "SELECT admitted_count FROM kineticloop.planning_quota_buckets") == [
        (1,),
        (1,),
    ]
    assert read(
        url,
        "SELECT current_request_revision_id,current_attempt_id FROM kineticloop.planning_intents",
    )[0] == (UUID(revision["request_id"]), UUID(revision["attempt_id"]))
    for command in ("RenewLease", "ReserveCall", "CommitBundle"):
        with psycopg.connect(url) as db:

            def stale(tx: RepositoryTransaction) -> None:
                tx.lock_subject()
                tx.lock_intents((UUID(root["intent_id"]),))
                tx.require_current_fence(
                    UUID(root["intent_id"]),
                    owner_id=IDENTITY.key,
                    fence=lease["fence"],
                    expected_request_revision=1,
                    expected_attempt_id=UUID(root["attempt_id"]),
                )

            with pytest.raises(FenceLost):
                execute_command(db, command, SUBJECT, stale)
    assert admission(url, request("revise", constraints={"minutes": 31})) == revision
    with pytest.raises(IdempotencyConflict):
        admission(url, request("revise", constraints={"minutes": 32}))
    back = admission(url, request("back"))
    assert back["request_revision"] == 3 and back["attempt_id"] not in {
        root["attempt_id"],
        revision["attempt_id"],
    }
    # Change only the prerequisite basis as a negative fixture, to prove service rereads S01.
    with psycopg.connect(url, autocommit=True) as db:
        db.execute(
            "UPDATE kineticloop.user_decision_state SET authorization_epoch=authorization_epoch+1 WHERE subject_id=%s",
            (SUBJECT,),
        )
    basis = admission(url, request("new-basis"))
    assert basis["request_revision"] == 4
    assert read(
        url,
        "SELECT captured_epoch FROM kineticloop.planning_attempts WHERE id=%s",
        (basis["attempt_id"],),
    ) == [(1,)]
    assert (
        root_state[0:2]
        == read(url, "SELECT deadline,typed_payload FROM kineticloop.planning_intents")[0]
    )


def test_takeover_and_renew_fence_old_workers(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    url = database_urls["admin"]
    root = admission(url, request("root"))
    # Observe real S01 blocking for two initial lease contenders, each using expected CAS basis.
    with psycopg.connect(url) as blocker, ThreadPoolExecutor(2) as pool:
        blocker.execute(
            "SELECT subject_id FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
            (SUBJECT,),
        )
        started, pids = Barrier(3), []

        def compete(identity: PlanningIdentity) -> Mapping[str, Any] | str:
            with psycopg.connect(url) as db:
                pids.append(db.info.backend_pid)
                started.wait(timeout=5)
                try:
                    return service(db, identity).acquire_lease(
                        AcquireLease(
                            SUBJECT,
                            "acquire",
                            UUID(root["intent_id"]),
                            None,
                            0,
                            1,
                            UUID(root["attempt_id"]),
                            60,
                        )
                    )
                except FenceLost:
                    return "LOST"

        futures = [pool.submit(compete, i) for i in (IDENTITY, OTHER)]
        started.wait(timeout=5)
        for pid in pids:
            observe_block(url, pid)
        blocker.commit()
        results = [f.result(timeout=10) for f in futures]
    winners = [r for r in results if isinstance(r, Mapping)]
    assert len(winners) == 1 and results.count("LOST") == 1 and winners[0]["fence"] == 1
    winner = IDENTITY if winners[0]["owner"] == IDENTITY.key else OTHER
    loser = OTHER if winner == IDENTITY else IDENTITY
    with pytest.raises(FenceLost):
        acquire(url, root, "early-takeover", identity=loser, owner=winner.key, fence=1)
    # Time-boundary negative fixture: advance persisted expiry to exactly server time.
    with psycopg.connect(url, autocommit=True) as db:
        db.execute("UPDATE kineticloop.planning_intents SET lease_expires_at=clock_timestamp()")
    # Two real takeover contenders compare the same expired owner/fence.
    with psycopg.connect(url) as blocker, ThreadPoolExecutor(2) as pool:
        blocker.execute(
            "SELECT subject_id FROM kineticloop.user_decision_state WHERE subject_id=%s FOR UPDATE",
            (SUBJECT,),
        )
        race_start, takeover_pids = Barrier(3), []

        def takeover_contender(key: str) -> Mapping[str, Any] | str:
            with psycopg.connect(url) as db:
                takeover_pids.append(db.info.backend_pid)
                race_start.wait(timeout=5)
                try:
                    return service(db, loser).acquire_lease(
                        AcquireLease(
                            SUBJECT,
                            key,
                            UUID(root["intent_id"]),
                            winner.key,
                            1,
                            1,
                            UUID(root["attempt_id"]),
                            60,
                        )
                    )
                except FenceLost:
                    return "LOST"

        takeover_futures = [
            pool.submit(takeover_contender, k) for k in ("takeover-a", "takeover-b")
        ]
        race_start.wait(timeout=5)
        for pid in takeover_pids:
            observe_block(url, pid)
        blocker.commit()
        takeover_results = [f.result(timeout=10) for f in takeover_futures]
    assert takeover_results.count("LOST") == 1
    takeover = next(r for r in takeover_results if isinstance(r, Mapping))
    assert takeover["fence"] == 2
    with psycopg.connect(url) as db:
        with pytest.raises(FenceLost):
            service(db, winner).renew_lease(
                RenewLease(
                    SUBJECT,
                    "old-renew",
                    UUID(root["intent_id"]),
                    1,
                    1,
                    UUID(root["attempt_id"]),
                    120,
                )
            )
    # Pause winner after its owned update; renewal waiter must observe PostgreSQL lock and reread.
    entered, release, waiter_started = Event(), Event(), Event()
    original = RestrictedSqlSession.update

    def pause(
        session: RestrictedSqlSession,
        logical_id: str,
        values: Mapping[str, Any],
        where: Mapping[str, Any],
    ) -> int:
        result = original(session, logical_id, values, where)
        if logical_id == "S27" and "lease_expires_at" in values:
            entered.set()
            assert release.wait(5)
        return result

    monkeypatch.setattr(RestrictedSqlSession, "update", pause)

    def renew(key: str) -> Mapping[str, Any]:
        with psycopg.connect(url) as db:
            return service(db, loser).renew_lease(
                RenewLease(
                    SUBJECT, key, UUID(root["intent_id"]), 2, 1, UUID(root["attempt_id"]), 120
                )
            )

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(renew, "renew-winner")
        assert entered.wait(5)
        # Replacement hook only pauses first already-running operation.
        monkeypatch.setattr(RestrictedSqlSession, "update", original)
        pid_holder: list[int] = []

        def waiter() -> str:
            with psycopg.connect(url) as db:
                pid_holder.append(db.info.backend_pid)
                waiter_started.set()
                try:
                    service(db, loser).renew_lease(
                        RenewLease(
                            SUBJECT,
                            "renew-waiter",
                            UUID(root["intent_id"]),
                            2,
                            1,
                            UUID(root["attempt_id"]),
                            30,
                        )
                    )
                except PlanningDenied:
                    return "DENIED_POST_LOCK"
                return "BAD"

        second = pool.submit(waiter)
        assert waiter_started.wait(5)
        observe_block(url, pid_holder[0])
        release.set()
        renewed = first.result(timeout=10)
        assert second.result(timeout=10) == "DENIED_POST_LOCK"
    assert renewed["fence"] == 2 and renewed["lease_expires_at"] > takeover["lease_expires_at"]
    with psycopg.connect(url) as db:
        capped = service(db, loser).renew_lease(
            RenewLease(
                SUBJECT, "capped", UUID(root["intent_id"]), 2, 1, UUID(root["attempt_id"]), 99999
            )
        )
    deadline = read(url, "SELECT deadline FROM kineticloop.planning_intents")[0][0]
    assert capped["lease_expires_at"] == deadline.isoformat()
    for terminal in TERMINAL:
        with psycopg.connect(url, autocommit=True) as db:
            db.execute("UPDATE kineticloop.planning_intents SET status=%s", (terminal,))
        with pytest.raises(FenceLost):
            acquire(url, root, f"terminal-{terminal}", identity=loser, owner=loser.key, fence=2)
        with psycopg.connect(url) as db, pytest.raises(FenceLost):
            service(db, loser).renew_lease(
                RenewLease(
                    SUBJECT,
                    f"renew-{terminal}",
                    UUID(root["intent_id"]),
                    2,
                    1,
                    UUID(root["attempt_id"]),
                    99999,
                )
            )
    # Deadline and lease equality deny without a watchdog status change.
    with psycopg.connect(url, autocommit=True) as db:
        db.execute(
            "UPDATE kineticloop.planning_intents SET status='RUNNING',deadline=clock_timestamp(),lease_expires_at=clock_timestamp()"
        )
    with pytest.raises(FenceLost):
        acquire(url, root, "deadline", identity=loser, owner=loser.key, fence=2)


def test_atomicity_and_ack_loss_replay(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    url = database_urls["admin"]
    initial = counts(url)
    for table in ("S27", "S28", "S29"):
        original_insert = RestrictedSqlSession.insert

        def fail(session: RestrictedSqlSession, logical_id: str, values: Mapping[str, Any]) -> int:
            result = original_insert(session, logical_id, values)
            if logical_id == table:
                raise RuntimeError("injected rollback")
            return result

        with monkeypatch.context() as scoped:
            scoped.setattr(RestrictedSqlSession, "insert", fail)
            with pytest.raises(RuntimeError, match="injected"):
                admission(url, request(f"fail-{table}"))
        assert counts(url) == initial
    for table in ("S30", "S27"):
        original_update = RestrictedSqlSession.update

        def fail_update(
            session: RestrictedSqlSession,
            logical_id: str,
            values: Mapping[str, Any],
            where: Mapping[str, Any],
        ) -> int:
            result = original_update(session, logical_id, values, where)
            if logical_id == table:
                raise RuntimeError("injected rollback")
            return result

        with monkeypatch.context() as scoped:
            scoped.setattr(RestrictedSqlSession, "update", fail_update)
            with pytest.raises(RuntimeError, match="injected"):
                admission(url, request(f"fail-{table}"))
        assert counts(url) == initial
    command = request("ack-loss")
    outcome = admission(url, command)
    lease = acquire(url, outcome)
    renew_command = RenewLease(
        SUBJECT,
        "renew-ack",
        UUID(outcome["intent_id"]),
        1,
        outcome["request_revision"],
        UUID(outcome["attempt_id"]),
        120,
    )
    with psycopg.connect(url) as db:
        renewed = service(db).renew_lease(renew_command)
    after = counts(url)
    with psycopg.connect(url) as db:
        assert service(db).renew_lease(renew_command) == {**renewed, "replayed": True}
    assert admission(url, command) == {
        **outcome,
        "replayed": True,
    }  # Lost ACK: exact identities once.
    assert acquire(url, outcome) == {**lease, "replayed": True}
    assert counts(url) == after
    with pytest.raises(IdempotencyConflict):
        admission(url, replace(command, constraints={"minutes": 1}))
    # Revision rollback leaves immutable request, old attempt and pointer untouched.
    old_state = read(
        url,
        "SELECT current_request_revision_id,current_attempt_id,deadline,typed_payload FROM kineticloop.planning_intents",
    )
    original_insert = RestrictedSqlSession.insert

    def revision_failure(
        session: RestrictedSqlSession, logical_id: str, values: Mapping[str, Any]
    ) -> int:
        result = original_insert(session, logical_id, values)
        if logical_id == "S29":
            raise RuntimeError("revision rollback")
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(RestrictedSqlSession, "insert", revision_failure)
        with pytest.raises(RuntimeError, match="revision"):
            admission(url, request("bad-revision", constraints={"minutes": 31}))
    assert counts(url) == after and old_state == read(
        url,
        "SELECT current_request_revision_id,current_attempt_id,deadline,typed_payload FROM kineticloop.planning_intents",
    )
    assert read(url, "SELECT status FROM kineticloop.planning_attempts") == [("CREATED",)]
    changed = admission(url, request("changed", constraints={"minutes": 31}))
    back = admission(url, request("back"))
    assert (
        back["request_revision"] == 3
        and len({back["attempt_id"], changed["attempt_id"], outcome["attempt_id"]}) == 3
    )
    with psycopg.connect(url, autocommit=True) as db:
        db.execute("UPDATE kineticloop.planning_intents SET status='CANCELLED'")
    before_replay = counts(url)
    assert admission(url, command) == {**outcome, "replayed": True}
    assert acquire(url, outcome) == {
        **lease,
        "replayed": True,
    }  # Historical lease receipt conveys no renewed authority.
    with psycopg.connect(url) as db:
        assert service(db).renew_lease(renew_command) == {**renewed, "replayed": True}
    # Force preflight miss to exercise the under-S01 ACK-loss race path on all owners.
    with monkeypatch.context() as scoped:
        scoped.setattr(PlanningWorkflowService, "_replay", lambda *args: None)
        assert admission(url, command) == {**outcome, "replayed": True}
        assert acquire(url, outcome) == {**lease, "replayed": True}
        with psycopg.connect(url) as db:
            assert service(db).renew_lease(renew_command) == {**renewed, "replayed": True}
    assert counts(url) == before_replay
    with pytest.raises(PlanningDenied, match="explicit"):
        admission(url, request("terminal-auto", explicit=False, trigger="INPUT_EVENT"))
    new = admission(url, request("explicit-new"))
    assert new["intent_id"] != outcome["intent_id"] and new["request_revision"] == 1
    assert read(url, "SELECT admitted_count FROM kineticloop.planning_quota_buckets") == [
        (2,),
        (2,),
    ]


def test_bounded_owner_capabilities(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from kineticloop.persistence.transactions import GuardRequired, StatementRejected

    url = database_urls["admin"]
    original_update = RestrictedSqlSession.update
    quota_ids: list[UUID] = []

    def duplicate_quota_bypass(
        session: RestrictedSqlSession,
        logical_id: str,
        values: Mapping[str, Any],
        where: Mapping[str, Any],
    ) -> int:
        if logical_id == "S30":
            quota_ids.append(where["id"])
            where = {**where, "id": quota_ids[0]}
        return original_update(session, logical_id, values, where)

    initial = counts(url)
    with monkeypatch.context() as scoped:
        scoped.setattr(RestrictedSqlSession, "update", duplicate_quota_bypass)
        with pytest.raises(GuardRequired, match="every quota"):
            admission(url, request("duplicate-quota"))
    assert len(quota_ids) == 2 and len(set(quota_ids)) == 2
    assert counts(url) == initial  # Missing hour/day coverage rolls back the entire root.
    root = admission(url, request("root"))

    def invalidation_bypass(
        session: RestrictedSqlSession,
        logical_id: str,
        values: Mapping[str, Any],
        where: Mapping[str, Any],
    ) -> int:
        if logical_id == "S29":
            values = {"status": "COMMITTED"}
        return original_update(session, logical_id, values, where)

    before = counts(url)
    with monkeypatch.context() as scoped:
        scoped.setattr(RestrictedSqlSession, "update", invalidation_bypass)
        with pytest.raises(GuardRequired, match="invalidate"):
            admission(url, request("bad-revision", constraints={"minutes": 31}))
    assert counts(url) == before
    assert read(url, "SELECT status FROM kineticloop.planning_attempts") == [("CREATED",)]
    original_insert = RestrictedSqlSession.insert

    def root_budget_bypass(
        session: RestrictedSqlSession, logical_id: str, values: Mapping[str, Any]
    ) -> int:
        if logical_id == "S27":
            values = {**values, "typed_payload": Jsonb({"limits": {"calls": 999999}})}
        return original_insert(session, logical_id, values)

    with monkeypatch.context() as scoped:
        scoped.setattr(RestrictedSqlSession, "insert", root_budget_bypass)
        with pytest.raises(GuardRequired, match="budget"):
            admission(url, request("budget-bypass", local_date=date(2026, 10, 1)))
    assert counts(url) == before
    # Lease command capabilities remain S27-only even through callback instrumentation.
    with monkeypatch.context() as scoped:
        scoped.setattr(
            RestrictedSqlSession,
            "update",
            lambda session, logical_id, values, where: original_update(
                session,
                "S29",
                {"status": "COMMITTED"},
                {"subject_id": SUBJECT, "id": UUID(root["attempt_id"])},
            ),
        )
        with pytest.raises(StatementRejected):
            acquire(url, root, "lease-bypass")
    assert counts(url) == before
    # Legacy PENDING means ADMITTED, but new service writes never produce it.
    with psycopg.connect(url, autocommit=True) as db:
        db.execute("UPDATE kineticloop.planning_intents SET status='PENDING'")
    assert acquire(url, root, "legacy")["fence"] == 1


def test_command_identity_namespaces(database_urls: dict[str, str]) -> None:
    url = database_urls["admin"]
    command = request("shared-key")
    root = admission(url, command)
    with psycopg.connect(url) as db:
        joined = service(db, OTHER).admit_or_revise(command)
    assert joined == {**root, "mode": "JOIN"}
    leased = acquire(url, root, "shared-key")
    assert leased["fence"] == 1
    assert admission(url, command) == {**root, "replayed": True}
    with psycopg.connect(url) as db:
        assert service(db, OTHER).admit_or_revise(command) == {**joined, "replayed": True}
    assert acquire(url, root, "shared-key") == {**leased, "replayed": True}
    assert counts(url) == (1, 1, 1, 2, 3, 3, 3)
