from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from kineticloop.db.lifecycle import DatabaseLifecycle
from kineticloop.persistence.transactions import (
    ArtifactIdentity,
    ArtifactIdentityRequired,
    DispatchNotPermitted,
    EventWrite,
    FenceLost,
    GuardRequired,
    LockOrderViolation,
    LockStage,
    RepositoryTransaction,
    StatementRejected,
    claim_outbox,
    execute_command,
    execute_factset_build,
    execute_preparation,
)

ROOT = Path(__file__).parents[2]
_MIGRATION_SPEC = spec_from_file_location(
    "kl015_test_migrations", ROOT / "tests/db/test_migrations.py"
)
assert _MIGRATION_SPEC is not None and _MIGRATION_SPEC.loader is not None
_MIGRATIONS: Any = module_from_spec(_MIGRATION_SPEC)
_MIGRATION_SPEC.loader.exec_module(_MIGRATIONS)

_SAFETY_SPEC = spec_from_file_location(
    "kl015_safety_seed", ROOT / "tests/db/test_safety_registry.py"
)
assert _SAFETY_SPEC is not None and _SAFETY_SPEC.loader is not None
_SAFETY: Any = module_from_spec(_SAFETY_SPEC)
_SAFETY_SPEC.loader.exec_module(_SAFETY)

SUBJECT = UUID(_SAFETY.SUBJECT_ID)
ARTIFACT = UUID(_SAFETY.ARTIFACT_ID)
DEPENDENCY = UUID(_SAFETY.DEPENDENCY_ID)
POLICY = UUID(_SAFETY.POLICY_ID)
MANIFEST = UUID(_SAFETY.MANIFEST_ID)
INTENT = UUID("00000000-0000-8000-8000-000000015027")
INTENT_2 = UUID("00000000-0000-8000-8000-000000015127")
REQUEST_RECEIPT = UUID("00000000-0000-8000-8000-000000015002")
REQUEST = UUID("00000000-0000-8000-8000-000000015028")
ATTEMPT = UUID("00000000-0000-8000-8000-000000015029")
QUOTA = UUID("00000000-0000-8000-8000-000000015030")
RESERVATION = UUID("00000000-0000-8000-8000-000000015031")
RESERVATION_2 = UUID("00000000-0000-8000-8000-000000015131")
DAILY_HEAD = UUID("00000000-0000-8000-8000-000000015038")
BUNDLE = UUID("00000000-0000-8000-8000-000000015039")
PRESCRIPTION = UUID("00000000-0000-8000-8000-000000015040")
BUNDLE_MEMBER = UUID("00000000-0000-8000-8000-000000015041")
ISSUANCE = UUID("00000000-0000-8000-8000-000000015042")
SUPERSESSION = UUID("00000000-0000-8000-8000-000000015043")
SESSION = UUID("00000000-0000-8000-8000-000000015044")
PROPOSAL = UUID("00000000-0000-8000-8000-000000015034")
DEMAND = UUID("00000000-0000-8000-8000-000000015035")
RESOLUTION = UUID("00000000-0000-8000-8000-000000015036")
VALIDATION = UUID("00000000-0000-8000-8000-000000015037")
FACTSET = UUID("00000000-0000-8000-8000-000000015015")
MANIFEST_BUILD = UUID("00000000-0000-8000-8000-000000015023")
NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def database_urls() -> Iterator[dict[str, str]]:
    lifecycle = DatabaseLifecycle(ROOT)
    urls = _MIGRATIONS.bootstrap_two_phase(lifecycle)
    _SAFETY.seed(urls["admin"])
    _seed_transaction_rows(urls["admin"])
    yield urls


def _seed_transaction_rows(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("SET session_replication_role=replica")
        connection.execute(
            "INSERT INTO kineticloop.command_receipts"
            "(id,subject_id,status,command_kind,client_key,actor_scope,request_hash) "
            "VALUES (%s,%s,'SUCCEEDED','AdmitOrReviseIntent','seed-request','subject','seed')",
            (REQUEST_RECEIPT, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_intents"
            "(id,subject_id,purpose,root_request_identity,local_date,status,fence_token,"
            "lease_owner,lease_expires_at,deadline) VALUES "
            "(%s,%s,'PLAN','root-1',DATE '2026-09-26','RUNNING',7,'worker-a',"
            "clock_timestamp()+interval '1 day',clock_timestamp()+interval '2 days'),"
            "(%s,%s,'PLAN','root-2',DATE '2026-09-27','RUNNING',7,'worker-a',"
            "clock_timestamp()+interval '1 day',clock_timestamp()+interval '2 days')",
            (INTENT, SUBJECT, INTENT_2, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_request_revisions"
            "(id,subject_id,request_revision,constraint_fingerprint,normalization_version,"
            "ref_s02_id,ref_s27_id) VALUES (%s,%s,1,'constraint','v1',%s,%s)",
            (REQUEST, SUBJECT, REQUEST_RECEIPT, INTENT),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_attempts"
            "(id,subject_id,attempt_no,status,captured_epoch,fence_token,ref_s24_id,"
            "ref_s27_id,ref_s28_id) VALUES (%s,%s,1,'RUNNING',0,7,%s,%s,%s)",
            (ATTEMPT, SUBJECT, MANIFEST, INTENT, REQUEST),
        )
        connection.execute(
            "INSERT INTO kineticloop.planning_quota_buckets"
            "(id,subject_id,quota_kind,window_start,window_end,admitted_count,quota_limit,ref_s05_id) "
            "VALUES (%s,%s,'DAILY',%s,%s,1,10,%s),"
            "(gen_random_uuid(),%s,'MONTHLY',%s,%s,1,100,%s)",
            (
                QUOTA,
                SUBJECT,
                NOW,
                NOW + timedelta(days=1),
                POLICY,
                SUBJECT,
                NOW,
                NOW + timedelta(days=30),
                POLICY,
            ),
        )
        connection.execute(
            "INSERT INTO kineticloop.call_reservations"
            "(id,subject_id,operation_slot,status,settlement_revision,dispatch_fence,"
            "ref_s27_id,ref_s29_id) VALUES "
            "(%s,%s,'slot-1','RESERVED',0,7,%s,%s),"
            "(%s,%s,'slot-2','RESERVED',0,7,%s,%s)",
            (RESERVATION, SUBJECT, INTENT, ATTEMPT, RESERVATION_2, SUBJECT, INTENT, ATTEMPT),
        )
        connection.execute(
            "INSERT INTO kineticloop.daily_plan_heads"
            "(id,subject_id,local_date,calendar_policy,day_lifecycle,head_revision) "
            "VALUES (%s,%s,DATE '2026-09-26','UTC','ACTIVE',0)",
            (DAILY_HEAD, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.workout_sessions"
            "(id,subject_id,session_identity,origin,lifecycle,execution_revision) "
            "VALUES (%s,%s,'session-1','PLANNED','READY',0)",
            (SESSION, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.proposal_revisions"
            "(id,subject_id,proposal_family_identity,proposal_kind,producer_artifact,revision) "
            "VALUES (%s,%s,'proposal-family','FITNESS','test',1)",
            (PROPOSAL, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.prescription_demand_features"
            "(id,subject_id,method_version,feature_hash,basis_hash,ref_s34_id) "
            "VALUES (%s,%s,'v1','feature','basis',%s)",
            (DEMAND, SUBJECT, PROPOSAL),
        )
        connection.execute(
            "INSERT INTO kineticloop.evidence_resolutions"
            "(id,subject_id,action_type,action_parameters_hash,resolver_version,query_basis_hash,"
            "ref_s05_id,ref_s24_id) VALUES (%s,%s,'PLAN','params','v1','basis',%s,%s)",
            (RESOLUTION, SUBJECT, POLICY, MANIFEST),
        )
        connection.execute(
            "INSERT INTO kineticloop.validation_results"
            "(id,subject_id,result,validator_artifact,valid_until,revision,ref_s05_id,"
            "ref_s24_id,ref_s28_id,ref_s29_id,ref_s34_id,ref_s35_id,ref_s36_id) "
            "VALUES (%s,%s,'PASS','validator',clock_timestamp()+interval '1 day',1,"
            "%s,%s,%s,%s,%s,%s,%s)",
            (VALIDATION, SUBJECT, POLICY, MANIFEST, REQUEST, ATTEMPT, PROPOSAL, DEMAND, RESOLUTION),
        )
        connection.execute(
            "INSERT INTO kineticloop.factset_revisions"
            "(id,subject_id,factset_identity,status,storage_mode,member_revision) "
            "VALUES (%s,%s,'build-1','BUILDING','FULL',0)",
            (FACTSET, SUBJECT),
        )
        connection.execute(
            "INSERT INTO kineticloop.manifest_builds"
            "(id,subject_id,build_identity,status,captured_epoch) "
            "VALUES (%s,%s,'manifest-build','READY',0)",
            (MANIFEST_BUILD, SUBJECT),
        )
        connection.execute("SET session_replication_role=origin")


def _registry_ids() -> tuple[UUID, UUID]:
    return ARTIFACT, DEPENDENCY


def _event(tag: int) -> EventWrite:
    return EventWrite(
        UUID(f"00000000-0000-8000-8000-{tag:012x}"),
        "PlanningIntent",
        f"kl015-{tag}",
        1,
        "KL015Mutation",
        "kl015-events",
        UUID(f"00000000-0000-8000-8000-{tag + 1:012x}"),
    )


def test_registry_lease_required_for_publish_commit_and_session_entry(
    database_urls: dict[str, str],
) -> None:
    for command in (
        "PublishManifest",
        "CommitBundle",
        "Reauthorize",
        "StartSession",
        "ResumeSession",
        "ContinueSession",
    ):
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(GuardRequired, match="shared S51"):
                execute_command(connection, command, SUBJECT, lambda tx: tx.lock_subject())
        with psycopg.connect(database_urls["admin"]) as connection:
            revision = execute_command(
                connection,
                command,
                SUBJECT,
                lambda tx: tx.acquire_registry_lease(_registry_ids()),
            )
            assert revision >= 0


def test_preparation_work_stays_outside_coordination_locks(
    database_urls: dict[str, str],
) -> None:
    for command in ("RecordProjection", "BuildManifest", "ResolveEvidence", "RecordValidation"):
        with psycopg.connect(database_urls["admin"]) as connection:
            observed = execute_preparation(
                connection, command, SUBJECT, lambda session: session.relation_locks()
            )
        assert "safety_registry_state" not in observed, command
        assert "user_decision_state" not in observed, command
        with psycopg.connect(database_urls["admin"]) as connection:
            with pytest.raises(StatementRejected):
                execute_preparation(
                    connection,
                    command,
                    SUBJECT,
                    lambda session: session.update(
                        "S01",
                        {"decision_generation": 1},
                        {"subject_id": SUBJECT},
                    ),
                )


def test_factset_build_stays_outside_subject_coordination(
    database_urls: dict[str, str],
) -> None:
    for command in ("BeginBuild", "WriteCandidate", "CompleteFactset"):
        with psycopg.connect(database_urls["admin"]) as connection:
            observed = execute_factset_build(
                connection,
                command,
                SUBJECT,
                FACTSET,
                lambda session: session.relation_locks(),
            )
        assert "factset_revisions" in observed, command
        assert "user_decision_state" not in observed, command
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(StatementRejected):
            execute_factset_build(
                connection,
                "CompleteFactset",
                SUBJECT,
                FACTSET,
                lambda session: session.update(
                    "S16",
                    {"member_operation": "SET"},
                    {"subject_id": SUBJECT},
                ),
            )


def test_subject_guard_required(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            assert not hasattr(
                RepositoryTransaction(connection.cursor(), "AdmitOrReviseIntent", SUBJECT),
                "cursor",
            )
        with pytest.raises(GuardRequired, match="S01"):
            execute_command(
                connection,
                "AdmitOrReviseIntent",
                SUBJECT,
                lambda tx: tx.lock_intents((INTENT,)),
            )
        with pytest.raises(StatementRejected, match="authenticated transaction subject"):
            execute_preparation(
                connection,
                "RecordProjection",
                SUBJECT,
                lambda session: session.update(
                    "S21",
                    {"projection_revision": 2},
                    {
                        "id": UUID("00000000-0000-8000-8000-000000015021"),
                        "subject_id": UUID("00000000-0000-8000-8000-000000015999"),
                    },
                ),
            )
        with pytest.raises(StatementRejected, match="cannot change"):
            execute_preparation(
                connection,
                "RecordProjection",
                SUBJECT,
                lambda session: session.update(
                    "S21",
                    {
                        "subject_id": UUID(
                            "00000000-0000-8000-8000-000000015999"
                        )
                    },
                    {
                        "id": UUID("00000000-0000-8000-8000-000000015021"),
                        "subject_id": SUBJECT,
                    },
                ),
            )


def test_complete_frozen_lock_order_enforced(database_urls: dict[str, str]) -> None:
    trace: tuple[tuple[LockStage, str], ...] = ()

    def operation(tx: RepositoryTransaction) -> None:
        nonlocal trace
        tx.acquire_registry_lease(_registry_ids())
        tx.lock_quota_buckets((("DAILY", NOW, NOW + timedelta(days=1)),))
        tx.lock_intents((INTENT,))
        tx.lock_reservations((RESERVATION,))
        tx.lock_daily_head(date(2026, 9, 26))
        tx.lock_execution((SESSION,))
        tx.lock_receipt("CommitBundle", "lock-order", "subject")
        tx.lock_remaining("validation_results", (VALIDATION,))
        trace = tx.lock_trace

    with psycopg.connect(database_urls["admin"]) as connection:
        execute_command(connection, "CommitBundle", SUBJECT, operation)
    assert [stage for stage, _ in trace] == sorted(stage for stage, _ in trace)
    assert [label.split(":", 1)[0] for _, label in trace] == [
        "S51",
        "S01",
        "S30",
        "S27",
        "S31",
        "S38",
        "S44",
        "S02",
        "S37",
    ]


def test_multi_key_lock_order_is_stable(database_urls: dict[str, str]) -> None:
    traces: list[tuple[tuple[LockStage, str], ...]] = []
    quota_keys = (
        ("DAILY", NOW, NOW + timedelta(days=1)),
        ("MONTHLY", NOW, NOW + timedelta(days=30)),
    )
    for quotas, intents, reservations in (
        (quota_keys, (INTENT, INTENT_2), (RESERVATION, RESERVATION_2)),
        (quota_keys[::-1], (INTENT_2, INTENT), (RESERVATION_2, RESERVATION)),
    ):
        with psycopg.connect(database_urls["admin"]) as connection:
            def operation(tx: RepositoryTransaction) -> None:
                tx.lock_subject()
                tx.lock_quota_buckets(quotas)
                tx.lock_intents(intents)
                tx.lock_reservations(reservations)
                traces.append(tx.lock_trace)

            execute_command(connection, "ReserveCall", SUBJECT, operation)
    assert traces[0] == traces[1]


@pytest.mark.parametrize(
    ("later", "earlier"),
    [
        ("quota", "subject"),
        ("intent", "quota"),
        ("reservation", "intent"),
        ("daily", "reservation"),
        ("execution", "daily"),
        ("receipt", "execution"),
        ("aggregate", "receipt"),
    ],
)
def test_reverse_lock_order_is_rejected(
    database_urls: dict[str, str], later: str, earlier: str
) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "ReserveCall", SUBJECT)
            tx.lock_subject()
            actions = {
                "subject": tx.lock_subject,
                "quota": lambda: tx.lock_quota_buckets((("DAILY", NOW, NOW + timedelta(days=1)),)),
                "intent": lambda: tx.lock_intents((INTENT,)),
                "reservation": lambda: tx.lock_reservations((RESERVATION,)),
                "daily": lambda: tx.lock_daily_head(date(2026, 9, 26)),
                "execution": lambda: tx.lock_execution((SESSION,)),
                "receipt": lambda: tx.lock_receipt("ReserveCall", "reverse", "subject"),
                "aggregate": lambda: tx.lock_remaining("validation_results", (VALIDATION,)),
            }
            actions[later]()
            with pytest.raises(LockOrderViolation):
                actions[earlier]()
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "CommitBundle", SUBJECT)
            tx.lock_subject()
            with pytest.raises(LockOrderViolation):
                tx.acquire_registry_lease(_registry_ids())
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "AdmitOrReviseIntent", SUBJECT)
            tx.lock_subject()
            tx.lock_intents((INTENT_2,))
            with pytest.raises(LockOrderViolation):
                tx.lock_intents((INTENT,))
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "AdmitOrReviseIntent", SUBJECT)
            tx.lock_subject()
            tx.lock_remaining("validation_results", (VALIDATION,))
            with pytest.raises(LockOrderViolation):
                tx.lock_remaining("factset_revisions", (FACTSET,))


def test_receipt_before_s01_is_rejected(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"]) as connection:
        with connection.transaction():
            tx = RepositoryTransaction(connection.cursor(), "ReserveCall", SUBJECT)
            with pytest.raises(GuardRequired, match="S01"):
                tx.lock_receipt("ReserveCall", "too-early", "subject")


def test_artifact_identity_required(database_urls: dict[str, str]) -> None:
    def operation(tx: RepositoryTransaction) -> None:
        tx.acquire_registry_lease(_registry_ids())
        with pytest.raises(ArtifactIdentityRequired):
            tx.require_artifact(
                ArtifactIdentity(ARTIFACT, "POLICY_BUNDLE", "wrong", "1", _SAFETY.CONTENT_HASH)
            )
        tx.require_artifact(
            ArtifactIdentity(
                ARTIFACT,
                "POLICY_BUNDLE",
                "artifact",
                "1",
                _SAFETY.CONTENT_HASH,
            )
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        execute_command(connection, "CommitBundle", SUBJECT, operation)


def test_direct_write_bypass_rejected(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["application"]) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "UPDATE kineticloop.planning_intents SET status='FAILED' WHERE id=%s",
                (INTENT,),
            )


@pytest.mark.parametrize(
    ("command", "tag"),
    [
        ("ReceiveEvidence", 0x15210),
        ("DecideAdmission", 0x15220),
        ("PublishManifest", 0x15230),
        ("AdmitOrReviseIntent", 0x15240),
        ("AcquireLease", 0x15250),
        ("CommitBundle", 0x15260),
        ("StartSession", 0x15270),
        ("SettleCall", 0x15280),
    ],
)
def test_event_outbox_atomicity_enforced(
    database_urls: dict[str, str], command: str, tag: int
) -> None:
    receipt = UUID(f"00000000-0000-8000-8000-{tag:012x}")
    event = _event(tag + 1)

    def mutate(session: Any) -> Mapping[str, Any]:
        if command == "ReceiveEvidence":
            session.insert(
                "S09",
                {
                    "id": UUID(f"00000000-0000-8000-8000-{tag + 9:012x}"),
                    "subject_id": SUBJECT,
                    "source_connection_identity": command,
                    "source_object_type": "TEST",
                    "source_object_identity": "object",
                    "source_revision": "1",
                    "trust_class": "SOURCE_REPORTED",
                    "source_class": "TEST",
                    "command_authority": "NONE",
                },
            )
        elif command == "DecideAdmission":
            session.update(
                "S01",
                {"decision_generation": 1},
                {"subject_id": SUBJECT},
            )
        elif command == "PublishManifest":
            session.update(
                "S23",
                {"captured_epoch": 1},
                {"id": MANIFEST_BUILD, "subject_id": SUBJECT},
            )
        elif command in {
            "AdmitOrReviseIntent",
            "AcquireLease",
            "SettleCall",
        }:
            session.update(
                "S27",
                {"typed_payload": psycopg.types.json.Jsonb({"atomic": command})},
                {"id": INTENT, "subject_id": SUBJECT},
            )
        elif command == "CommitBundle":
            session.update(
                "S38",
                {"head_revision": 1},
                {"id": DAILY_HEAD, "subject_id": SUBJECT},
            )
        else:
            session.update(
                "S44",
                {"execution_revision": 1},
                {"id": SESSION, "subject_id": SUBJECT},
            )
        return {"command": command}

    def acquire_guards(tx: RepositoryTransaction) -> None:
        if tx.spec.registry_required:
            tx.acquire_registry_lease(_registry_ids())
        elif tx.spec.subject_guard_required:
            tx.lock_subject()
        if command in {"AdmitOrReviseIntent", "AcquireLease", "SettleCall"}:
            tx.lock_intents((INTENT,))
        elif command == "CommitBundle":
            tx.lock_intents((INTENT,))
            tx.lock_reservations((RESERVATION_2,))
            tx.lock_daily_head(date(2026, 9, 26))
        elif command == "StartSession":
            tx.lock_daily_head(date(2026, 9, 26))
            tx.lock_execution((SESSION,))

    def aggregate_locks() -> Mapping[str, tuple[UUID, ...]] | None:
        if command == "PublishManifest":
            return {"manifest_builds": (MANIFEST_BUILD,)}
        if command == "CommitBundle":
            return {
                "planning_attempts": (ATTEMPT,),
                "validation_results": (VALIDATION,),
            }
        return None

    def operation(tx: RepositoryTransaction) -> None:
        acquire_guards(tx)

        def fail(session: Any) -> Mapping[str, Any]:
            mutate(session)
            raise RuntimeError("failure injection")

        tx.idempotent_outcome(
            receipt_id=receipt,
            actor_scope="subject",
            client_key="atomic-fail",
            request_hash="atomic-hash",
            mutation=fail,
            event=event,
            aggregate_locks=aggregate_locks(),
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(RuntimeError, match="failure injection"):
            execute_command(connection, command, SUBJECT, operation)
    with psycopg.connect(database_urls["admin"]) as connection:
        if command == "ReceiveEvidence":
            assert connection.execute(
                "SELECT count(*) FROM kineticloop.evidence_revisions "
                "WHERE source_connection_identity=%s",
                (command,),
            ).fetchone() == (0,)
        elif command == "DecideAdmission":
            assert connection.execute(
                "SELECT decision_generation FROM kineticloop.user_decision_state "
                "WHERE subject_id=%s",
                (SUBJECT,),
            ).fetchone() == (0,)
        elif command == "PublishManifest":
            assert connection.execute(
                "SELECT captured_epoch FROM kineticloop.manifest_builds WHERE id=%s",
                (MANIFEST_BUILD,),
            ).fetchone() == (0,)
        elif command in {"AdmitOrReviseIntent", "AcquireLease", "SettleCall"}:
            assert connection.execute(
                "SELECT typed_payload FROM kineticloop.planning_intents WHERE id=%s",
                (INTENT,),
            ).fetchone() == ({},)
        elif command == "CommitBundle":
            assert connection.execute(
                "SELECT head_revision FROM kineticloop.daily_plan_heads WHERE id=%s",
                (DAILY_HEAD,),
            ).fetchone() == (0,)
        else:
            assert connection.execute(
                "SELECT execution_revision FROM kineticloop.workout_sessions WHERE id=%s",
                (SESSION,),
            ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.command_receipts WHERE id=%s", (receipt,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.domain_events WHERE id=%s", (event.event_id,)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.outbox_deliveries WHERE id=%s", (event.outbox_id,)
        ).fetchone() == (0,)

    success_receipt = UUID(f"00000000-0000-8000-8000-{tag + 0x1000:012x}")
    success_event = _event(tag + 0x1001)

    def success(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
        acquire_guards(tx)
        return tx.idempotent_outcome(
            receipt_id=success_receipt,
            actor_scope="subject",
            client_key="atomic-success",
            request_hash="atomic-success-hash",
            mutation=mutate,
            event=success_event,
            aggregate_locks=aggregate_locks(),
        )

    with psycopg.connect(database_urls["admin"]) as connection:
        outcome, replayed = execute_command(connection, command, SUBJECT, success)
    assert outcome == {"command": command}
    assert not replayed
    with psycopg.connect(database_urls["admin"], autocommit=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.command_receipts WHERE id=%s",
            (success_receipt,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.domain_events WHERE id=%s",
            (success_event.event_id,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.outbox_deliveries WHERE id=%s",
            (success_event.outbox_id,),
        ).fetchone() == (1,)
        if command == "DecideAdmission":
            connection.execute(
                "UPDATE kineticloop.user_decision_state SET decision_generation=0 "
                "WHERE subject_id=%s",
                (SUBJECT,),
            )
        elif command == "PublishManifest":
            connection.execute(
                "UPDATE kineticloop.manifest_builds SET captured_epoch=0 WHERE id=%s",
                (MANIFEST_BUILD,),
            )
        elif command in {"AdmitOrReviseIntent", "AcquireLease", "SettleCall"}:
            connection.execute(
                "UPDATE kineticloop.planning_intents SET typed_payload='{}' WHERE id=%s",
                (INTENT,),
            )
        elif command == "CommitBundle":
            connection.execute(
                "UPDATE kineticloop.daily_plan_heads SET head_revision=0 WHERE id=%s",
                (DAILY_HEAD,),
            )
        elif command == "StartSession":
            connection.execute(
                "UPDATE kineticloop.workout_sessions SET execution_revision=0 WHERE id=%s",
                (SESSION,),
            )


def test_outbox_dispatcher_does_not_lock_subject_guard(
    database_urls: dict[str, str],
) -> None:
    blocker = psycopg.connect(database_urls["admin"])
    blocker.execute(
        "SELECT subject_id FROM kineticloop.user_decision_state "
        "WHERE subject_id=%s FOR UPDATE",
        (SUBJECT,),
    )
    outcome: dict[str, Any] = {}

    def worker() -> None:
        with psycopg.connect(
            database_urls["admin"], application_name="kl015-outbox-observer"
        ) as connection:
            outcome["ids"] = claim_outbox(connection, destination="authorization-events")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive(), "S01 contention must not block OutboxDispatcher"
    assert outcome["ids"]
    blocker.rollback()
    blocker.close()


def test_stale_fence_commit_is_rejected(database_urls: dict[str, str]) -> None:
    with psycopg.connect(database_urls["admin"], autocommit=True) as takeover:
        takeover.execute(
            "UPDATE kineticloop.planning_intents SET lease_owner='worker-b',fence_token=8," 
            "lease_expires_at=clock_timestamp()+interval '1 day' WHERE id=%s",
            (INTENT,),
        )
    with psycopg.connect(database_urls["admin"]) as connection:
        def operation(tx: RepositoryTransaction) -> None:
            tx.lock_subject()
            tx.lock_intents((INTENT,))
            tx.require_current_fence(INTENT, owner_id="worker-a", fence=7)

        with pytest.raises(FenceLost):
            execute_command(connection, "ReserveCall", SUBJECT, operation)


def test_dispatch_first_winner_and_replay_non_resend(database_urls: dict[str, str]) -> None:
    permit_receipt = UUID("00000000-0000-8000-8000-000000015502")
    permit_event = _event(0x15503)

    def permit(tx: RepositoryTransaction, permit_key: str) -> Any:
        tx.lock_subject()
        tx.lock_intents((INTENT,))
        tx.lock_reservations((RESERVATION,))
        return tx.permit_dispatch(
            RESERVATION,
            permit_key=permit_key,
            request_hash=f"hash-{permit_key}",
            receipt_id=permit_receipt,
            event=permit_event,
            fence=7,
        )

    barrier = threading.Barrier(2)
    outcomes: list[Any] = []
    errors: list[BaseException] = []

    def contender() -> None:
        try:
            barrier.wait(timeout=5)
            with psycopg.connect(database_urls["admin"]) as connection:
                outcomes.append(
                    execute_command(
                        connection,
                        "PermitDispatch",
                        SUBJECT,
                        lambda tx: permit(tx, "permit-1"),
                    )
                )
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=contender) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert sum(result.sendable for result in outcomes) == 1
    assert sum(result.replayed for result in outcomes) == 1
    with psycopg.connect(database_urls["admin"]) as connection:
        replay = execute_command(
            connection,
            "PermitDispatch",
            SUBJECT,
            lambda tx: permit(tx, "permit-1"),
        )
    assert not replay.sendable and replay.replayed
    with psycopg.connect(database_urls["admin"]) as connection:
        for table, object_id in (
            ("command_receipts", permit_receipt),
            ("domain_events", permit_event.event_id),
            ("outbox_deliveries", permit_event.outbox_id),
        ):
            assert connection.execute(
                f"SELECT count(*) FROM kineticloop.{table} WHERE id=%s", (object_id,)
            ).fetchone() == (1,)
    with psycopg.connect(database_urls["admin"]) as connection:
        with pytest.raises(DispatchNotPermitted):
            second_receipt = UUID("00000000-0000-8000-8000-000000015512")
            second_event = _event(0x15513)

            def conflicting(tx: RepositoryTransaction) -> Any:
                tx.lock_subject()
                tx.lock_intents((INTENT,))
                tx.lock_reservations((RESERVATION,))
                return tx.permit_dispatch(
                    RESERVATION,
                    permit_key="permit-2",
                    request_hash="hash-permit-2",
                    receipt_id=second_receipt,
                    event=second_event,
                    fence=7,
                )

            execute_command(
                connection,
                "PermitDispatch",
                SUBJECT,
                conflicting,
            )
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.command_receipts WHERE id=%s",
            (second_receipt,),
        ).fetchone() == (0,)


def test_ack_loss_replay_preserves_natural_uniqueness(database_urls: dict[str, str]) -> None:
    receipt = UUID("00000000-0000-8000-8000-000000015302")
    event = _event(0x15303)
    runs = 0

    def invoke() -> tuple[Mapping[str, Any], bool]:
        nonlocal runs

        def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
            tx.lock_subject()
            tx.lock_intents((INTENT_2,))

            def mutation(session: Any) -> Mapping[str, Any]:
                nonlocal runs
                runs += 1
                session.update(
                    "S27",
                    {"typed_payload": psycopg.types.json.Jsonb({"committed": True})},
                    {"id": INTENT_2, "subject_id": SUBJECT},
                )
                return {"intent_id": str(INTENT_2), "status": "COMMITTED"}

            return tx.idempotent_outcome(
                receipt_id=receipt,
                actor_scope="subject",
                client_key="ack-loss",
                request_hash="ack-loss-hash",
                mutation=mutation,
                event=event,
            )

        with psycopg.connect(database_urls["admin"]) as connection:
            return execute_command(connection, "AcquireLease", SUBJECT, operation)

    class CommitAcknowledgementLost(ConnectionError):
        pass

    first: Mapping[str, Any]
    with pytest.raises(CommitAcknowledgementLost):
        committed, replayed = invoke()
        assert not replayed
        first = committed
        # The database transaction has committed; only the caller's acknowledgement is lost.
        raise CommitAcknowledgementLost
    second, replayed = invoke()
    assert replayed and second == first and runs == 1
    with psycopg.connect(database_urls["admin"]) as connection:
        for table, object_id in (
            ("command_receipts", receipt),
            ("domain_events", event.event_id),
            ("outbox_deliveries", event.outbox_id),
        ):
            assert connection.execute(
                f"SELECT count(*) FROM kineticloop.{table} WHERE id=%s", (object_id,)
            ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.call_reservations "
            "WHERE ref_s27_id IN (%s,%s)",
            (INTENT, INTENT_2),
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.planning_intents "
            "WHERE id IN (%s,%s)",
            (INTENT, INTENT_2),
        ).fetchone() == (2,)


def test_t6_ack_loss_replay_returns_same_issuance(database_urls: dict[str, str]) -> None:
    receipt = UUID("00000000-0000-8000-8000-000000015402")
    event = _event(0x15403)
    runs = 0

    def invoke() -> tuple[Mapping[str, Any], bool]:
        def operation(tx: RepositoryTransaction) -> tuple[Mapping[str, Any], bool]:
            tx.acquire_registry_lease(_registry_ids())
            tx.lock_intents((INTENT,))
            tx.lock_reservations((RESERVATION_2,))
            tx.lock_daily_head(date(2026, 9, 26))

            def mutation(session: Any) -> Mapping[str, Any]:
                nonlocal runs
                runs += 1
                session.insert(
                    "S39",
                    {
                        "id": BUNDLE,
                        "subject_id": SUBJECT,
                        "local_date": date(2026, 9, 26),
                        "revision_no": 1,
                        "generation_mode": "AI_GENERATED_CURRENT",
                        "ref_s02_id": receipt,
                        "ref_s24_id": MANIFEST,
                        "ref_s27_id": INTENT,
                        "ref_s29_id": ATTEMPT,
                        "ref_s37_id": VALIDATION,
                        "ref_s38_id": DAILY_HEAD,
                    },
                )
                session.insert(
                    "S40",
                    {
                        "id": PRESCRIPTION,
                        "subject_id": SUBJECT,
                        "prescription_identity": "prescription-1",
                        "prescription_kind": "WORKOUT",
                        "prescription_revision": 1,
                        "ref_s34_id": PROPOSAL,
                        "ref_s49_id": ARTIFACT,
                    },
                )
                session.insert(
                    "S41",
                    {
                        "id": BUNDLE_MEMBER,
                        "subject_id": SUBJECT,
                        "member_kind": "PRESCRIPTION",
                        "session_slot": "primary",
                        "member_order": 1,
                        "ref_s39_id": BUNDLE,
                        "ref_s40_id": PRESCRIPTION,
                    },
                )
                session.insert(
                    "S42",
                    {
                        "id": ISSUANCE,
                        "subject_id": SUBJECT,
                        "bound_content_hash": "content",
                        "scope": "PRODUCTION",
                        "artifact_dependency_closure_hash": "closure",
                        "registry_revision_at_issue": 0,
                        "valid_from": NOW,
                        "valid_until": NOW + timedelta(days=1),
                        "validity_certificate": psycopg.types.json.Jsonb({}),
                        "ref_s02_id": receipt,
                        "ref_s05_id": POLICY,
                        "ref_s24_id": MANIFEST,
                        "ref_s36_id": RESOLUTION,
                        "ref_s37_id": VALIDATION,
                        "ref_s40_id": PRESCRIPTION,
                        "ref_s49_id": ARTIFACT,
                        "registry_state_id": 1,
                    },
                )
                session.insert(
                    "S43",
                    {
                        "id": SUPERSESSION,
                        "subject_id": SUBJECT,
                        "event_kind": "SUPERSEDED",
                        "scope": "PRODUCTION",
                        "causation_key": "t6-ack-loss",
                        "ref_s42_id": UUID(_SAFETY.AUTHORIZATION_ID),
                        "ref_s02_id": receipt,
                    },
                )
                session.update(
                    "S38",
                    {"head_revision": 1},
                    {"id": DAILY_HEAD, "subject_id": SUBJECT},
                )
                session.update(
                    "S27",
                    {"status": "FOUND_VALID_PLAN"},
                    {"id": INTENT, "subject_id": SUBJECT},
                )
                return {
                    "receipt_id": str(receipt),
                    "bundle_revision_id": str(BUNDLE),
                    "prescription_id": str(PRESCRIPTION),
                    "bundle_member_id": str(BUNDLE_MEMBER),
                    "authorization_issuance_id": str(ISSUANCE),
                    "supersession_id": str(SUPERSESSION),
                }

            return tx.idempotent_outcome(
                receipt_id=receipt,
                actor_scope="subject",
                client_key="t6-ack-loss",
                request_hash="t6-ack-loss-hash",
                mutation=mutation,
                event=event,
                aggregate_locks={
                    "planning_attempts": (ATTEMPT,),
                    "validation_results": (VALIDATION,),
                },
            )

        with psycopg.connect(database_urls["admin"]) as connection:
            return execute_command(connection, "CommitBundle", SUBJECT, operation)

    class CommitAcknowledgementLost(ConnectionError):
        pass

    first: Mapping[str, Any]
    with pytest.raises(CommitAcknowledgementLost):
        committed, replayed = invoke()
        assert not replayed
        first = committed
        raise CommitAcknowledgementLost
    second, replayed = invoke()
    assert replayed and second == first and runs == 1
    with psycopg.connect(database_urls["admin"]) as connection:
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.daily_bundle_revisions WHERE id=%s", (BUNDLE,)
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.authorization_issuances WHERE id=%s", (ISSUANCE,)
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.prescription_revisions WHERE id=%s",
            (PRESCRIPTION,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.bundle_prescription_members WHERE id=%s",
            (BUNDLE_MEMBER,),
        ).fetchone() == (1,)
        for table, object_id in (
            ("command_receipts", receipt),
            ("domain_events", event.event_id),
            ("outbox_deliveries", event.outbox_id),
        ):
            assert connection.execute(
                f"SELECT count(*) FROM kineticloop.{table} WHERE id=%s", (object_id,)
            ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.authorization_events WHERE id=%s",
            (SUPERSESSION,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT head_revision FROM kineticloop.daily_plan_heads WHERE id=%s",
            (DAILY_HEAD,),
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT status FROM kineticloop.planning_intents WHERE id=%s", (INTENT,)
        ).fetchone() == ("FOUND_VALID_PLAN",)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.call_reservations "
            "WHERE id IN (%s,%s)",
            (RESERVATION, RESERVATION_2),
        ).fetchone() == (2,)
        assert connection.execute(
            "SELECT count(*) FROM kineticloop.planning_attempts WHERE id=%s", (ATTEMPT,)
        ).fetchone() == (1,)
