from __future__ import annotations

import re
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
    GuardRequired,
    IdempotencyConflict,
    RepositoryTransaction,
    RestrictedSqlSession,
    execute_command,
)

ROOT = Path(__file__).parents[2]
_SPEC = spec_from_file_location("kl025_migrations", ROOT / "tests/db/test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_MIGRATIONS: Any = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATIONS)
SUBJECT, POLICY = UUID(int=25001), UUID(int=25005)
IDENTITY = PlanningIdentity(
    RoleIdentity("00000000-0000-8000-8000-000000025900", ActorRole.TEST), SUBJECT
)
OTHER = PlanningIdentity(
    RoleIdentity("00000000-0000-8000-8000-000000025901", ActorRole.TEST), SUBJECT
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
    "root_limits": {"calls": 3, "tokens": 1000, "tools": 10},
}


@pytest.fixture()
def database_urls() -> Iterator[dict[str, str]]:
    short = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if re.fullmatch(r"[0-9a-f]{7,12}", short) is None:
        raise ValueError("invalid ledger fixture commit suffix")
    lifecycle = DatabaseLifecycle(ROOT)
    lifecycle.namespace = DatabaseNamespace(
        f"kineticloop-kl025-{short}", f"kineticloop_kl025_{short}"
    )
    try:
        urls = _MIGRATIONS.bootstrap_two_phase(lifecycle)
        with psycopg.connect(urls["admin"], autocommit=True) as db:
            # Only trusted TEST scope, immutable policy and the prerequisite S01 are seeded.
            # Every positive S27/S28/S29/S30 operation below uses PlanningWorkflowService.
            db.execute(
                "INSERT INTO kineticloop.policy_bundles "
                "(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) "
                "VALUES (%s,%s,'test:kl025','1','kl025-policy',%s)",
                (POLICY, SUBJECT, Jsonb({"planning_admission": POLICY_BODY})),
            )
            db.execute(
                "INSERT INTO kineticloop.user_decision_state "
                "(subject_id,input_frontier_hash,active_policy_bundle_id) VALUES (%s,'basis-1',%s)",
                (SUBJECT, POLICY),
            )
            program, factset, build, artifact, manifest = (UUID(int=25010 + n) for n in range(5))
            db.execute(
                "INSERT INTO kineticloop.program_versions "
                "(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test:kl025',1)",
                (program, SUBJECT),
            )
            db.execute(
                "INSERT INTO kineticloop.factset_revisions "
                "(id,subject_id,factset_identity,status,storage_mode) VALUES (%s,%s,%s,'SEALED','FULL')",
                (factset, SUBJECT, str(factset)),
            )
            db.execute(
                "INSERT INTO kineticloop.manifest_builds "
                "(id,subject_id,build_identity,status,captured_epoch) VALUES (%s,%s,'test:kl025','PUBLISHED',0)",
                (build, SUBJECT),
            )
            db.execute(
                "INSERT INTO kineticloop.safety_artifacts "
                "(id,artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,ref_s05_id) "
                "VALUES (%s,'POLICY_BUNDLE','test:kl025','1','kl025-policy','BOUNDED',clock_timestamp(),clock_timestamp()+interval '1 day',%s)",
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
                (SUBJECT, POLICY, UUID(int=25902), "kl_test_subject_1_login"),
            )
        yield urls
    finally:
        lifecycle.destroy()



def test_planning_fixture_namespace_isolation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Exercise the actual planning selector and fixture before any database runner."""
    spec = spec_from_file_location("kl025_planning_fixture", ROOT / "tests/db/test_planning.py")
    assert spec is not None and spec.loader is not None
    planning: Any = module_from_spec(spec)
    spec.loader.exec_module(planning)
    selector = "KINETICLOOP_KL024_FIXTURE_OWNER"
    short = "abcdef1"
    monkeypatch.delenv(selector, raising=False)
    assert planning._planning_namespace(short) == DatabaseNamespace(
        "kineticloop-kl024-abcdef1", "kineticloop_kl024_abcdef1"
    )
    monkeypatch.setenv(selector, "KL-025")
    actual = planning._planning_namespace(short)
    suffix = DatabaseNamespace.for_worktree(ROOT).project_name[-12:]
    assert actual == DatabaseNamespace(
        f"kineticloop-kl025-plan-{short}-{suffix}",
        f"kineticloop_kl025_plan_{short}_{suffix}",
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(planning, "ROOT", tmp_path / "different-worktree")
        other = planning._planning_namespace(short)
    assert other != actual
    calls: list[tuple[str, DatabaseNamespace]] = []

    class BootstrapStop(RuntimeError):
        pass

    def reset(lifecycle: DatabaseLifecycle) -> None:
        calls.append(("reset", lifecycle.namespace))

    def destroy(lifecycle: DatabaseLifecycle) -> None:
        calls.append(("destroy", lifecycle.namespace))

    def bootstrap(lifecycle: DatabaseLifecycle) -> None:
        lifecycle.reset()
        raise BootstrapStop

    monkeypatch.setattr(planning.subprocess, "check_output", lambda *args, **kwargs: short)
    monkeypatch.setattr(DatabaseLifecycle, "reset", reset)
    monkeypatch.setattr(DatabaseLifecycle, "destroy", destroy)
    monkeypatch.setattr(planning._MIGRATIONS, "bootstrap_two_phase", bootstrap)
    fixture = planning.database_urls.__wrapped__
    with pytest.raises(BootstrapStop):
        next(fixture())
    assert calls == [("reset", actual), ("destroy", actual)]
    assert all("kl025" in ns.project_name and "kl025" in ns.database_name for _, ns in calls)
    print("PLANNING_NAMESPACE", actual.project_name, actual.database_name)
    calls.clear()
    for value in ("", "KL-024", "kl-025", "arbitrary", "KL-025 ", "../KL-025"):
        monkeypatch.setenv(selector, value)
        with pytest.raises(ValueError, match="owner"):
            next(fixture())
        assert calls == []
    monkeypatch.setenv(selector, "KL-025")
    for invalid in ("", "abcdef", "abcdef1234567", "ABCDEF1", "abcdex1", "abcdef1;"):
        monkeypatch.setattr(planning.subprocess, "check_output", lambda *a, _s=invalid, **k: _s)
        with pytest.raises(ValueError, match="suffix"):
            next(fixture())
        assert calls == []


def read(url: str, statement: str, args: Any = ()) -> list[Any]:
    with psycopg.connect(url, autocommit=True) as db:
        return db.execute(statement, args).fetchall()


def bookkeeping(url: str) -> tuple[int, ...]:
    return tuple(
        read(url, f"SELECT count(*) FROM kineticloop.{table}")[0][0]
        for table in (
            "call_reservations", "call_ledger_events", "command_receipts",
            "domain_events", "outbox_deliveries",
        )
    )


def root_payload(url: str) -> dict[str, Any]:
    return dict(read(url, "SELECT typed_payload FROM kineticloop.planning_intents")[0][0])


def request(key: str, **changes: Any) -> AdmitOrReviseIntent:
    return replace(AdmitOrReviseIntent(
        SUBJECT, key, date(2026, 9, 30), "TRAINING", "test:UTC-v1", {"minutes": 30}
    ), **changes)


def admission(url: str, key: str = "root", **changes: Any) -> Mapping[str, Any]:
    with psycopg.connect(url) as db:
        return PlanningWorkflowService(db, IDENTITY).admit_or_revise(request(key, **changes))


def acquire(
    url: str, root: Mapping[str, Any], key: str = "lease", *,
    identity: PlanningIdentity = IDENTITY, owner: str | None = None, fence: int = 0,
) -> Mapping[str, Any]:
    with psycopg.connect(url) as db:
        return PlanningWorkflowService(db, identity).acquire_lease(AcquireLease(
            SUBJECT, key, UUID(root["intent_id"]), owner, fence, root["request_revision"],
            UUID(root["attempt_id"]), 60,
        ))


def ledger(db: Any, identity: PlanningIdentity = IDENTITY, trusted: bool = True) -> Any:
    from kineticloop.persistence.call_ledger import CallLedgerService
    return CallLedgerService(db, identity, receipt_verifier=lambda receipt: trusted)


def reserve_command(
    root: Mapping[str, Any], key: str, slot: str | None = None, *, fence: int = 1,
    tokens: int = 100, tools: int = 1,
) -> Any:
    from kineticloop.persistence.call_ledger import ReserveCall
    from kineticloop.workflow.call_ledger import AccountingIdentity
    return ReserveCall(
        SUBJECT, key, UUID(root["intent_id"]), UUID(root["attempt_id"]),
        root["request_revision"], fence, slot or key,
        AccountingIdentity("fake-provider", "fake-model", "config-v1", "price-v1"),
        {"calls": 1, "tokens": tokens, "tools": tools},
    )


def reserve(url: str, command: Any, identity: PlanningIdentity = IDENTITY) -> Mapping[str, Any]:
    with psycopg.connect(url) as db:
        return ledger(db, identity).reserve(command)


def permit_command(root: Mapping[str, Any], reserved: Mapping[str, Any], key: str) -> Any:
    from kineticloop.persistence.call_ledger import PermitDispatch
    return PermitDispatch(
        SUBJECT, key, UUID(root["intent_id"]), UUID(reserved["reservation_id"]),
        UUID(root["attempt_id"]), root["request_revision"], 1,
    )


def cancel_command(root: Mapping[str, Any], reserved: Mapping[str, Any], key: str) -> Any:
    from kineticloop.persistence.call_ledger import CancelUndispatched
    return CancelUndispatched(SUBJECT, key, UUID(root["intent_id"]), UUID(reserved["reservation_id"]))


def unknown_command(root: Mapping[str, Any], reserved: Mapping[str, Any], key: str) -> Any:
    from kineticloop.persistence.call_ledger import MarkUnknown
    return MarkUnknown(SUBJECT, key, UUID(root["intent_id"]), UUID(reserved["reservation_id"]),
                       expected_transition="DISPATCH_INTENT", expected_revision=1)


def settlement_command(
    root: Mapping[str, Any], reserved: Mapping[str, Any], key: str, *,
    expected: str = "UNKNOWN", revision: int = 2, tokens: int = 80,
    receipt_id: str | None = None,
) -> Any:
    from kineticloop.persistence.call_ledger import SettleCall
    from kineticloop.workflow.call_ledger import AccountingIdentity, ReliableReceipt
    receipt = ReliableReceipt(
        UUID(reserved["reservation_id"]),
        AccountingIdentity("fake-provider", "fake-model", "config-v1", "price-v1"),
        {"calls": 1, "tokens": tokens, "tools": 1}, "PROVIDER_RECEIPT",
        receipt_id or key, f"provider-{reserved['reservation_id']}", "verified:test-evidence-v1",
    )
    return SettleCall(SUBJECT, key, UUID(root["intent_id"]), UUID(reserved["reservation_id"]),
                      receipt, expected_transition=expected, expected_revision=revision)


def invoke(url: str, method: str, command: Any, identity: PlanningIdentity = IDENTITY) -> Any:
    with psycopg.connect(url) as db:
        return getattr(ledger(db, identity), method)(command)


def observe_block(url: str, pid: int) -> None:
    until = time.monotonic() + 5
    with psycopg.connect(url, autocommit=True) as monitor:
        while time.monotonic() < until:
            row = monitor.execute(
                "SELECT wait_event_type,cardinality(pg_blocking_pids(pid)) "
                "FROM pg_stat_activity WHERE pid=%s", (pid,),
            ).fetchone()
            if row is not None and row[0] == "Lock" and row[1] > 0:
                return
            time.sleep(0.01)  # Poll actual PG locks; elapsed time is never the oracle.
    pytest.fail("PostgreSQL did not observe bounded lock blocking")


def test_competing_reservations_share_root_budget(database_urls: dict[str, str]) -> None:
    from kineticloop.workflow.call_ledger import LedgerDenied
    url = database_urls["admin"]
    root = admission(url)
    lease = acquire(url, root)
    old = reserve(url, reserve_command(root, "old-attempt", tokens=200, tools=2))
    original = root_payload(url)
    deadline = read(url, "SELECT deadline FROM kineticloop.planning_intents")[0][0]
    joined = admission(url, "join")
    assert joined["attempt_id"] == root["attempt_id"]
    revised = admission(url, "revision", constraints={"minutes": 31})
    with psycopg.connect(url) as db:
        PlanningWorkflowService(db, IDENTITY).renew_lease(RenewLease(
            SUBJECT, "renew-revised", UUID(root["intent_id"]), lease["fence"],
            revised["request_revision"], UUID(revised["attempt_id"]), 120,
        ))
    assert root_payload(url) == original
    assert read(url, "SELECT deadline FROM kineticloop.planning_intents")[0][0] == deadline
    before = bookkeeping(url)
    barrier, pids = Barrier(3), []

    def contender(key: str) -> Mapping[str, Any] | str:
        with psycopg.connect(url) as db:
            pids.append(db.info.backend_pid)
            barrier.wait(timeout=5)
            try:
                return ledger(db).reserve(reserve_command(revised, key, tokens=600, tools=6))
            except LedgerDenied as error:
                assert "budget" in str(error)
                return "DENIED"

    with psycopg.connect(url) as blocker, ThreadPoolExecutor(2) as pool:
        blocker.execute("SELECT subject_id FROM kineticloop.user_decision_state "
                        "WHERE subject_id=%s FOR UPDATE", (SUBJECT,))
        futures = [pool.submit(contender, key) for key in ("budget-a", "budget-b")]
        barrier.wait(timeout=5)
        for pid in pids:
            observe_block(url, pid)
        blocker.commit()
        results = [future.result(timeout=10) for future in futures]
    assert results.count("DENIED") == 1
    assert bookkeeping(url) == tuple(a + 1 for a in before)
    payload = root_payload(url)
    assert payload["reserved"] == {"calls": 2, "tokens": 800, "tools": 8}
    assert payload["settled"] == {"calls": 0, "tokens": 0, "tools": 0}
    assert payload["limits"] == original["limits"]
    assert read(url, "SELECT count(DISTINCT ref_s29_id) FROM kineticloop.call_reservations") == [(2,)]
    assert read(url, "SELECT count(*) FROM kineticloop.call_ledger_events WHERE event_type='RESERVED'") == [(2,)]
    winner = next(result for result in results if isinstance(result, Mapping))
    winner_key = "budget-a" if winner == results[0] else "budget-b"
    with pytest.raises((GuardRequired, IdempotencyConflict, LedgerDenied, psycopg.errors.UniqueViolation)):
        reserve(url, reserve_command(revised, "different-key", slot=winner_key, tokens=1, tools=1))
    assert bookkeeping(url) == tuple(a + 1 for a in before)
    assert old["reservation_id"] != winner["reservation_id"]
    with psycopg.connect(url, autocommit=True) as db:
        db.execute("UPDATE kineticloop.planning_intents SET lease_expires_at=clock_timestamp()")
    acquire(url, revised, "root-budget-takeover", identity=OTHER, owner=IDENTITY.key, fence=1)
    assert root_payload(url) == payload
    assert read(url, "SELECT deadline FROM kineticloop.planning_intents")[0][0] == deadline
    print("ROOT_BUDGET", payload)


def test_cancel_and_dispatch_have_one_winner(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kineticloop.persistence.transactions import DispatchNotPermitted, GuardRequired
    url = database_urls["admin"]
    root = admission(url)
    acquire(url, root)
    for winner_method in ("cancel", "permit"):
        reserved = reserve(url, reserve_command(root, f"reserve-{winner_method}"))
        commands = {"cancel": cancel_command(root, reserved, f"cancel-{winner_method}"),
                    "permit": permit_command(root, reserved, f"permit-{winner_method}")}
        loser_method = "permit" if winner_method == "cancel" else "cancel"
        entered, release, started = Event(), Event(), Event()
        original = RestrictedSqlSession.update
        before = bookkeeping(url)
        target = "CANCELLED_BEFORE_DISPATCH" if winner_method == "cancel" else "DISPATCH_INTENT"

        def pause(session: Any, logical: str, values: Mapping[str, Any], where: Mapping[str, Any]) -> int:
            result = original(session, logical, values, where)
            if logical == "S31" and values.get("status") == target:
                entered.set()
                assert release.wait(5)
            return result

        with monkeypatch.context() as scoped, ThreadPoolExecutor(2) as pool:
            scoped.setattr(RestrictedSqlSession, "update", pause)
            first = pool.submit(invoke, url, winner_method, commands[winner_method])
            assert entered.wait(5)
            scoped.setattr(RestrictedSqlSession, "update", original)
            pids: list[int] = []

            def waiter() -> str:
                with psycopg.connect(url) as db:
                    pids.append(db.info.backend_pid)
                    started.set()
                    try:
                        getattr(ledger(db), loser_method)(commands[loser_method])
                    except (DispatchNotPermitted, GuardRequired):
                        return "DENIED_AFTER_LOCK"
                    return "BAD"

            second = pool.submit(waiter)
            assert started.wait(5)
            observe_block(url, pids[0])
            release.set()
            first.result(timeout=10)
            assert second.result(timeout=10) == "DENIED_AFTER_LOCK"
        assert bookkeeping(url) == (before[0], *(n + 1 for n in before[1:]))
        assert read(url, "SELECT status,settlement_revision FROM kineticloop.call_reservations WHERE id=%s",
                    (reserved["reservation_id"],)) == [(target, 1)]
        assert read(url, "SELECT event_type,transition_revision FROM kineticloop.call_ledger_events "
                    "WHERE ref_s31_id=%s ORDER BY transition_revision", (reserved["reservation_id"],)) == [
                        ("RESERVED", 0), (target, 1)]
        assert root_payload(url)["reserved"]["calls"] == (0 if winner_method == "cancel" else 1)
    print("CANCEL_DISPATCH_LOCK_ORDERS", "cancel-first", "permit-first")


def test_stale_attempt_fence_and_deadline_deny(database_urls: dict[str, str]) -> None:
    from kineticloop.persistence.transactions import DispatchNotPermitted
    from kineticloop.workflow.planning import TERMINAL
    url = database_urls["admin"]
    root = admission(url)
    first = acquire(url, root)
    reserved = reserve(url, reserve_command(root, "reserved"))
    permitted = invoke(url, "permit", permit_command(root, reserved, "first-permit"))
    assert permitted.sendable
    waiting = reserve(url, reserve_command(root, "waiting"))
    # Negative fixture advances trusted server-time eligibility only; contenders remain services.
    with psycopg.connect(url, autocommit=True) as db:
        db.execute("UPDATE kineticloop.planning_intents SET lease_expires_at=clock_timestamp()")
    takeover = acquire(url, root, "takeover", identity=OTHER, owner=IDENTITY.key, fence=first["fence"])
    assert takeover["fence"] == 2
    before = bookkeeping(url)
    for command in (reserve_command(root, "old-owner"), reserve_command(root, "wrong-fence", fence=2)):
        with pytest.raises(FenceLost):
            reserve(url, command)
    with pytest.raises(FenceLost):
        invoke(url, "permit", permit_command(root, waiting, "stale-permit"))
    # Historical durable permit after authority changed is observation only.
    replay = invoke(url, "permit", permit_command(root, reserved, "first-permit"))
    assert not replay.sendable and replay.reservation_id == permitted.reservation_id
    with pytest.raises((FenceLost, DispatchNotPermitted)):
        invoke(url, "permit", replace(permit_command(root, reserved, "other-key"), fence=2), OTHER)
    assert bookkeeping(url) == before
    revised = admission(url, "revision", constraints={"minutes": 31})
    with psycopg.connect(url) as db:
        renewed = PlanningWorkflowService(db, OTHER).renew_lease(RenewLease(
            SUBJECT, "renew-new-attempt", UUID(root["intent_id"]), 2,
            revised["request_revision"], UUID(revised["attempt_id"]), 120,
        ))
    assert renewed["fence"] == 2
    with pytest.raises(FenceLost):
        reserve(url, reserve_command(root, "obsolete-request", fence=2), OTHER)
    with pytest.raises(FenceLost):
        invoke(url, "permit", replace(permit_command(root, waiting, "obsolete-attempt"), fence=2), OTHER)
    # Cancellation after lease/revision loss releases only an unpermitted reservation.
    invoke(url, "cancel", cancel_command(root, waiting, "obsolete-cancel"))
    assert root_payload(url)["reserved"]["calls"] == 1
    fresh = reserve(url, reserve_command(revised, "fresh", fence=2), OTHER)
    fresh_permit = replace(permit_command(revised, fresh, "fresh-permit"), fence=2)
    for table, statuses in (
        ("planning_attempts", ("COMMITTED", "STALE", "FAILED", "CANCELLED", "LEASE_LOST")),
        ("planning_intents", tuple(sorted(TERMINAL))),
    ):
        row_id = revised["attempt_id"] if table == "planning_attempts" else revised["intent_id"]
        original = "CREATED" if table == "planning_attempts" else "RUNNING"
        for status in statuses:
            with psycopg.connect(url, autocommit=True) as db:
                db.execute(f"UPDATE kineticloop.{table} SET status=%s WHERE id=%s", (status, row_id))
            state = bookkeeping(url)
            with pytest.raises(FenceLost):
                reserve(url, reserve_command(revised, f"terminal-{table}-{status}", fence=2), OTHER)
            with pytest.raises(FenceLost):
                invoke(url, "permit", replace(fresh_permit, key=f"permit-{table}-{status}"), OTHER)
            assert bookkeeping(url) == state
        with psycopg.connect(url, autocommit=True) as db:
            db.execute(f"UPDATE kineticloop.{table} SET status=%s WHERE id=%s", (original, row_id))
    current_fence = 2
    for field in ("lease_expires_at", "deadline"):
        with psycopg.connect(url, autocommit=True) as db:
            db.execute(f"UPDATE kineticloop.planning_intents SET {field}=clock_timestamp()")
        with pytest.raises(FenceLost):
            reserve(url, reserve_command(revised, f"equality-{field}", fence=current_fence), OTHER)
        with pytest.raises(FenceLost):
            invoke(url, "permit", replace(fresh_permit, key=f"permit-equality-{field}", fence=current_fence), OTHER)
        if field == "lease_expires_at":
            acquire(url, revised, "takeover-time", identity=OTHER, owner=OTHER.key, fence=2)
            current_fence = 3
            invoke(url, "cancel", cancel_command(revised, fresh, "cancel-expired-lease"))
            live_after_takeover = reserve(url, reserve_command(revised, "live-after-takeover", fence=3), OTHER)
            fresh_permit = replace(permit_command(revised, live_after_takeover, "live-deadline-permit"), fence=3)
    assert permitted.sendable  # A committed possible-send window survives loss of worker authority.
    with psycopg.connect(url) as db:
        def forbidden(tx: RepositoryTransaction) -> None:
            tx.lock_subject()
            tx.lock_intents((UUID(root["intent_id"]),))
            tx.require_current_fence(UUID(root["intent_id"]), owner_id=IDENTITY.key, fence=1,
                                     expected_request_revision=1, expected_attempt_id=UUID(root["attempt_id"]))
        with pytest.raises(FenceLost):
            execute_command(db, "CommitBundle", SUBJECT, forbidden)
    print("CURRENT_AUTHORITY", "old-owner/fence/request/attempt/terminal/time denied")


def persisted(url: str) -> tuple[Any, ...]:
    tables = ("planning_intents", "call_reservations", "call_ledger_events", "command_receipts",
              "domain_events", "outbox_deliveries")
    return tuple(read(url, f"SELECT to_jsonb(t) FROM kineticloop.{table} t ORDER BY id") for table in tables)


def test_ack_loss_and_payload_conflicts(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kineticloop.persistence.transactions import DispatchNotPermitted, GuardRequired
    from kineticloop.workflow.call_ledger import LedgerDenied
    url = database_urls["admin"]
    root = admission(url)
    acquire(url, root)
    reserve_cmd = reserve_command(root, "reserve-ack")
    reserved = reserve(url, reserve_cmd)
    with psycopg.connect(url) as db:
        view = ledger(db).read(UUID(reserved["reservation_id"]))
    assert view.intent_id == UUID(root["intent_id"]) and view.attempt_id == UUID(root["attempt_id"])
    assert view.status == "RESERVED" and view.actual is None
    assert view.bounds == {"calls": 1, "tokens": 100, "tools": 1}
    with pytest.raises(TypeError):
        view.bounds["tokens"] = 0
    before = persisted(url)
    assert reserve(url, reserve_cmd)["reservation_id"] == reserved["reservation_id"]
    assert persisted(url) == before
    with pytest.raises(IdempotencyConflict):
        reserve(url, replace(reserve_cmd, bounds={"calls": 1, "tokens": 99, "tools": 1}))
    with pytest.raises((GuardRequired, IdempotencyConflict, LedgerDenied, psycopg.errors.UniqueViolation)):
        reserve(url, replace(reserve_cmd, key="natural-duplicate"))
    assert persisted(url) == before
    cancel_cmd = cancel_command(root, reserved, "cancel-ack")
    invoke(url, "cancel", cancel_cmd)
    after_cancel = persisted(url)
    invoke(url, "cancel", cancel_cmd)
    assert persisted(url) == after_cancel
    with pytest.raises(IdempotencyConflict):
        invoke(url, "cancel", replace(cancel_cmd, reservation_id=uuid4()))
    dispatched = reserve(url, reserve_command(root, "dispatch-ack"))
    permit_cmd = permit_command(root, dispatched, "permit-ack")
    first = invoke(url, "permit", permit_cmd)
    assert first.sendable
    before = persisted(url)
    assert not invoke(url, "permit", permit_cmd).sendable
    assert persisted(url) == before
    with pytest.raises(IdempotencyConflict):
        invoke(url, "permit", replace(permit_cmd, fence=7))
    with pytest.raises(DispatchNotPermitted):
        invoke(url, "permit", replace(permit_cmd, key="different-permit"))
    unknown_cmd = unknown_command(root, dispatched, "unknown-ack")
    invoke(url, "mark_unknown", unknown_cmd)
    before = persisted(url)
    invoke(url, "mark_unknown", unknown_cmd)
    assert persisted(url) == before
    with pytest.raises(IdempotencyConflict):
        invoke(url, "mark_unknown", replace(unknown_cmd, expected_revision=99))
    settle_cmd = settlement_command(root, dispatched, "settle-ack")
    invoke(url, "settle", settle_cmd)
    before = persisted(url)
    invoke(url, "settle", settle_cmd)
    assert persisted(url) == before
    with pytest.raises(IdempotencyConflict):
        invoke(url, "settle", replace(settle_cmd, receipt=replace(settle_cmd.receipt, actual={"calls": 1, "tokens": 79, "tools": 1})))
    # Lost ACK preflight miss forces the receipt reread under S01 for every command owner.
    from kineticloop.persistence.call_ledger import CallLedgerService
    with monkeypatch.context() as scoped:
        scoped.setattr(CallLedgerService, "_replay", lambda *args: None)
        for method, command in (("reserve", reserve_cmd), ("cancel", cancel_cmd),
                                ("permit", permit_cmd), ("mark_unknown", unknown_cmd),
                                ("settle", settle_cmd)):
            outcome = invoke(url, method, command)
            if method == "permit":
                assert not outcome.sendable and outcome.replayed
            else:
                assert outcome["replayed"] is True
    assert persisted(url) == before
    target = reserve(url, reserve_command(root, "rollback-target"))
    target_permit = permit_command(root, target, "rollback-permit")
    cancel_target = cancel_command(root, target, "rollback-cancel")
    # Real PG executes each statement then an injected transport/worker failure aborts the tx.
    rollback_commands = [("reserve", reserve_command(root, "rollback-reserve")),
                         ("cancel", cancel_target), ("permit", target_permit)]
    for method, command in rollback_commands:
        boundaries = ["command_receipts", "domain_events", "outbox_deliveries"]
        boundaries += ["call_reservations", "call_ledger_events"]
        if method != "permit":
            boundaries += ["planning_intents"]
        for boundary in boundaries:
            print("ROLLBACK_BOUNDARY", method, boundary)
            before_failure = persisted(url)
            class FailingCursor(psycopg.Cursor[Any]):
                def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
                    result = super().execute(query, params, **kwargs)
                    text = query.as_string(self.connection) if hasattr(query, "as_string") else str(query)
                    if f"kineticloop.{boundary}" in text.replace(chr(34), "") and text.lstrip().upper().startswith(("INSERT", "UPDATE")):
                        raise RuntimeError(f"rollback-{boundary}")
                    return result
            with psycopg.connect(url, cursor_factory=FailingCursor) as db:
                with pytest.raises(RuntimeError, match="rollback"):
                    getattr(ledger(db), method)(command)
            assert persisted(url) == before_failure
    # Malicious owner callbacks cannot replace unrelated root fields or falsify exact amounts.
    original_update = RestrictedSqlSession.update
    def bad_root(session: Any, logical: str, values: Mapping[str, Any], where: Mapping[str, Any]) -> int:
        if logical == "S27":
            payload = dict(values["typed_payload"].obj)
            payload["reserved"] = {"calls": 0, "tokens": 0, "tools": 0}
            values = {"typed_payload": Jsonb(payload)}
        return original_update(session, logical, values, where)
    before_failure = persisted(url)
    with monkeypatch.context() as scoped:
        scoped.setattr(RestrictedSqlSession, "update", bad_root)
        with pytest.raises((GuardRequired, LedgerDenied)):
            reserve(url, reserve_command(root, "malicious-root"))
    assert persisted(url) == before_failure
    original_insert = RestrictedSqlSession.insert
    for corrupted_table in ("S31", "S32"):
        def bad_payload(session: Any, logical: str, values: Mapping[str, Any]) -> int:
            if logical == corrupted_table:
                values = {**values, "typed_payload": Jsonb({"fabricated": "zero occupation"})}
            return original_insert(session, logical, values)
        with monkeypatch.context() as scoped:
            scoped.setattr(RestrictedSqlSession, "insert", bad_payload)
            with pytest.raises(GuardRequired):
                reserve(url, reserve_command(root, f"malicious-{corrupted_table}"))
        assert persisted(url) == before_failure
    invoke(url, "permit", target_permit)
    unknown_target = unknown_command(root, target, "rollback-unknown")
    settlement_target = settlement_command(root, target, "rollback-settle", expected="DISPATCH_INTENT", revision=1)
    for method, command in (("mark_unknown", unknown_target), ("settle", settlement_target)):
        for boundary in ("command_receipts", "domain_events", "outbox_deliveries", "call_reservations", "call_ledger_events", "planning_intents"):
            print("ROLLBACK_BOUNDARY", method, boundary)
            before_failure = persisted(url)
            class FailingSettlementCursor(psycopg.Cursor[Any]):
                def execute(self, query: Any, params: Any = None, **kwargs: Any) -> Any:
                    result = super().execute(query, params, **kwargs)
                    text = query.as_string(self.connection) if hasattr(query, "as_string") else str(query)
                    if f"kineticloop.{boundary}" in text.replace(chr(34), "") and text.lstrip().upper().startswith(("INSERT", "UPDATE")):
                        raise RuntimeError(f"rollback-{boundary}")
                    return result
            with psycopg.connect(url, cursor_factory=FailingSettlementCursor) as db:
                with pytest.raises(RuntimeError, match="rollback"):
                    getattr(ledger(db), method)(command)
            assert persisted(url) == before_failure
    print("ACK_LOSS_AND_ROLLBACK", "all five owners and mutation/bookkeeping boundaries")


def test_unknown_and_late_settlement_are_accounting_only(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kineticloop.persistence.transactions import GuardRequired
    from kineticloop.workflow.call_ledger import LedgerDenied
    url = database_urls["admin"]
    root = admission(url)
    acquire(url, root)
    reserved = reserve(url, reserve_command(root, "possible-send", tokens=600, tools=6))
    invoke(url, "permit", permit_command(root, reserved, "permit"))
    initial_budget = root_payload(url)
    # There is deliberately no DISPATCHED diagnosis. A crash before send still occupies bounds.
    entered, release, started = Event(), Event(), Event()
    original_update = RestrictedSqlSession.update
    def pause_unknown(session: Any, logical: str, values: Mapping[str, Any], where: Mapping[str, Any]) -> int:
        result = original_update(session, logical, values, where)
        if logical == "S31" and values.get("status") == "OUTCOME_UNKNOWN":
            entered.set()
            assert release.wait(5)
        return result
    unknown = unknown_command(root, reserved, "unknown")
    with monkeypatch.context() as scoped, ThreadPoolExecutor(2) as pool:
        scoped.setattr(RestrictedSqlSession, "update", pause_unknown)
        winner = pool.submit(invoke, url, "mark_unknown", unknown)
        assert entered.wait(5)
        scoped.setattr(RestrictedSqlSession, "update", original_update)
        pids: list[int] = []
        def stale_waiter() -> str:
            with psycopg.connect(url) as db:
                pids.append(db.info.backend_pid)
                started.set()
                try:
                    ledger(db).settle(settlement_command(root, reserved, "stale-settlement", expected="DISPATCH_INTENT", revision=1))
                except GuardRequired:
                    return "STALE_AFTER_LOCK"
                return "BAD"
        waiter = pool.submit(stale_waiter)
        assert started.wait(5)
        observe_block(url, pids[0])
        release.set()
        winner.result(timeout=10)
        assert waiter.result(timeout=10) == "STALE_AFTER_LOCK"
    assert root_payload(url) == initial_budget
    assert read(url, "SELECT status,settlement_revision FROM kineticloop.call_reservations") == [("OUTCOME_UNKNOWN", 2)]
    assert initial_budget["settled"] == {"calls": 0, "tokens": 0, "tools": 0}
    before_occupied = persisted(url)
    with pytest.raises(LedgerDenied, match="budget"):
        reserve(url, reserve_command(root, "unknown-remains-occupied", tokens=500, tools=5))
    assert persisted(url) == before_occupied
    with pytest.raises(GuardRequired):
        invoke(url, "cancel", cancel_command(root, reserved, "cancel-after-possible-send"))
    # Reliable late evidence needs a trusted ingress verifier, even with a valid receipt shape.
    settlement = settlement_command(root, reserved, "late-settle", tokens=2000)
    before = persisted(url)
    with psycopg.connect(url) as db, pytest.raises(LedgerDenied):
        ledger(db, trusted=False).settle(settlement)
    assert persisted(url) == before
    entered.clear()
    release.clear()
    started.clear()
    pids.clear()
    def pause_revision(session: Any, logical: str, values: Mapping[str, Any], where: Mapping[str, Any]) -> int:
        result = original_update(session, logical, values, where)
        if logical == "S27" and "current_attempt_id" in values:
            entered.set()
            assert release.wait(5)
        return result
    with monkeypatch.context() as scoped, ThreadPoolExecutor(2) as pool:
        scoped.setattr(RestrictedSqlSession, "update", pause_revision)
        revision = pool.submit(admission, url, "revision", constraints={"minutes": 31})
        assert entered.wait(5)
        scoped.setattr(RestrictedSqlSession, "update", original_update)
        def settle_waiter() -> Mapping[str, Any]:
            with psycopg.connect(url) as db:
                pids.append(db.info.backend_pid)
                started.set()
                return ledger(db).settle(settlement)
        settlement_waiter = pool.submit(settle_waiter)
        assert started.wait(5)
        observe_block(url, pids[0])
        release.set()
        revised = revision.result(timeout=10)
        settlement_waiter.result(timeout=10)
    assert read(url, "SELECT current_request_revision_id,current_attempt_id FROM kineticloop.planning_intents") == [(UUID(revised["request_id"]), UUID(revised["attempt_id"]))]
    assert read(url, "SELECT status FROM kineticloop.planning_attempts WHERE id=%s", (root["attempt_id"],)) == [("STALE",)]
    payload = root_payload(url)
    assert payload["reserved"] == {"calls": 0, "tokens": 0, "tools": 0}
    assert payload["settled"] == {"calls": 1, "tokens": 2000, "tools": 1}
    assert {k: v for k, v in payload.items() if k not in {"reserved", "settled"}} == {k: v for k, v in initial_budget.items() if k not in {"reserved", "settled"}}
    assert read(url, "SELECT status,settlement_revision FROM kineticloop.call_reservations") == [("SETTLED", 3)]
    assert read(url, "SELECT event_type,transition_revision FROM kineticloop.call_ledger_events ORDER BY transition_revision") == [("RESERVED", 0), ("DISPATCH_INTENT", 1), ("OUTCOME_UNKNOWN", 2), ("SETTLED", 3)]
    before = persisted(url)
    invoke(url, "settle", settlement)
    assert persisted(url) == before
    # A second transport key cannot use a duplicate/conflicting provider receipt to refund again.
    for duplicate in (
        replace(settlement, key="duplicate-receipt"),
        replace(settlement, key="conflicting-receipt", receipt=replace(settlement.receipt, actual={"calls": 1, "tokens": 10, "tools": 1})),
    ):
        with pytest.raises((GuardRequired, IdempotencyConflict, LedgerDenied)):
            invoke(url, "settle", duplicate)
        assert persisted(url) == before
    # Overrun is immutable observed usage, never clamped; new requests fail closed.
    with pytest.raises(LedgerDenied, match="budget"):
        reserve(url, reserve_command(revised, "overrun-blocks"))
    assert persisted(url) == before
    with psycopg.connect(url, autocommit=True) as db:
        db.execute("UPDATE kineticloop.planning_intents SET status='CANCELLED',lease_expires_at=clock_timestamp()")
        db.execute("UPDATE kineticloop.planning_attempts SET status='CANCELLED' WHERE id=%s", (revised["attempt_id"],))
    control = read(url, "SELECT to_jsonb(t)-'typed_payload' FROM kineticloop.planning_intents t")
    attempts = read(url, "SELECT to_jsonb(t) FROM kineticloop.planning_attempts t ORDER BY id")
    subject_state = read(url, "SELECT to_jsonb(t) FROM kineticloop.user_decision_state t")
    authority = tuple(read(url, f"SELECT count(*) FROM kineticloop.{table}") for table in (
        "control_events", "control_heads", "authorization_issuances", "workout_sessions",
    ))
    invoke(url, "settle", settlement)
    assert control == read(url, "SELECT to_jsonb(t)-'typed_payload' FROM kineticloop.planning_intents t")
    assert attempts == read(url, "SELECT to_jsonb(t) FROM kineticloop.planning_attempts t ORDER BY id")
    assert subject_state == read(url, "SELECT to_jsonb(t) FROM kineticloop.user_decision_state t")
    assert authority == tuple(read(url, f"SELECT count(*) FROM kineticloop.{table}") for table in (
        "control_events", "control_heads", "authorization_issuances", "workout_sessions",
    ))
    # A second admitted root settles for the first time after takeover AND termination.
    late_root = admission(url, "terminal-root")
    acquire(url, late_root, "terminal-root-lease")
    late_reserved = reserve(url, reserve_command(late_root, "terminal-call"))
    invoke(url, "permit", permit_command(late_root, late_reserved, "terminal-permit"))
    invoke(url, "mark_unknown", unknown_command(late_root, late_reserved, "terminal-unknown"))
    with psycopg.connect(url, autocommit=True) as db:
        db.execute("UPDATE kineticloop.planning_intents SET lease_expires_at=clock_timestamp() WHERE id=%s", (late_root["intent_id"],))
    acquire(url, late_root, "terminal-takeover", identity=OTHER, owner=IDENTITY.key, fence=1)
    with psycopg.connect(url, autocommit=True) as db:
        db.execute("UPDATE kineticloop.planning_intents SET status='CANCELLED' WHERE id=%s", (late_root["intent_id"],))
        db.execute("UPDATE kineticloop.planning_attempts SET status='CANCELLED' WHERE id=%s", (late_root["attempt_id"],))
    late_control = read(url, "SELECT to_jsonb(t)-'typed_payload' FROM kineticloop.planning_intents t ORDER BY id")
    late_attempts = read(url, "SELECT to_jsonb(t) FROM kineticloop.planning_attempts t ORDER BY id")
    invoke(url, "settle", settlement_command(late_root, late_reserved, "terminal-late-settlement"))
    assert late_control == read(url, "SELECT to_jsonb(t)-'typed_payload' FROM kineticloop.planning_intents t ORDER BY id")
    assert late_attempts == read(url, "SELECT to_jsonb(t) FROM kineticloop.planning_attempts t ORDER BY id")
    assert subject_state == read(url, "SELECT to_jsonb(t) FROM kineticloop.user_decision_state t")
    assert authority == tuple(read(url, f"SELECT count(*) FROM kineticloop.{table}") for table in (
        "control_events", "control_heads", "authorization_issuances", "workout_sessions",
    ))
    assert read(url, "SELECT typed_payload->'reserved',typed_payload->'settled' FROM kineticloop.planning_intents WHERE id=%s", (late_root["intent_id"],)) == [({"calls": 0, "tokens": 0, "tools": 0}, {"calls": 1, "tokens": 80, "tools": 1})]
    # S32 immutable historical actuals reject a privileged negative control mutation.
    with psycopg.connect(url, autocommit=True) as db:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="IMMUTABLE"):
            db.execute("UPDATE kineticloop.call_ledger_events SET event_type='RESERVED' WHERE event_type='SETTLED'")
    print("UNKNOWN_LATE_ACCOUNTING", payload, "no control/authorization/attempt authority restored")
