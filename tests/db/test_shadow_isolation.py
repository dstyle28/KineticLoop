from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from kineticloop.contracts.commands import (
    CommitBundle,
    ContinueSession,
    ResumeSession,
    StartSession,
    parse_command,
)
from kineticloop.contracts.shadow import ShadowEvaluationArtifact
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.protocol_execution import ProtocolExecutionService
from kineticloop.persistence.subject_scope import (
    ScopedObjectKind,
    SubjectScopeDenied,
    read_scoped_object,
)
from kineticloop.persistence.transactions import GuardRequired, RepositoryTransaction
from kineticloop.protocol.execution import ExecutionIdentity, digest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: str) -> Any:
    spec = spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


U = load("kl029_namespace", "tests/unit/protocol/test_shadow_isolation.py")
D = load("kl029_readonly_demo_recipes", "tests/db/test_test_only_demo.py")
M = load("kl029_selected_bootstrap", "tests/db/test_migrations.py")
DEADLINE = float("inf")
HEAD_ADMIN_URL: str | None = None
RAW_CONNECT = psycopg.connect


def head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def witness(kind: str, **values: Any) -> None:
    print(
        "SHADOW_EVIDENCE "
        + json.dumps(
            {"kind": kind, "tested_commit": head(), **values}, default=str, sort_keys=True
        ),
        flush=True,
    )


def bootstrap_connection(lifecycle: Any, *args: Any, **kwargs: Any) -> Any:
    """Bound every nested bootstrap/migration Python connection before opening it."""
    lifecycle.validate_target()
    selected = lifecycle.namespace
    params = psycopg.conninfo.conninfo_to_dict(args[0] if args else "")
    database = kwargs.get("dbname", params.get("dbname"))
    if database != selected.database_name:
        raise ValueError("foreign nested bootstrap database")
    assert time.monotonic() < DEADLINE
    kwargs["connect_timeout"] = 5
    kwargs["options"] = (
        "-c statement_timeout=12000 -c lock_timeout=10000 -c idle_in_transaction_session_timeout=12000"
    )
    db = RAW_CONNECT(*args, **kwargs)
    try:
        with db.transaction():
            assert db.execute("SELECT current_database()").fetchone() == (selected.database_name,)
        return db
    except BaseException:
        db.close()
        raise


def connect(url: str, **kwargs: Any) -> Any:
    selected = U.fixture_namespace(ROOT, head())
    U.OwnedLifecycle(ROOT, head()).validate_target()
    assert time.monotonic() < DEADLINE, "bounded suite wall deadline"
    if urlparse(url).path != "/" + selected.database_name:
        raise ValueError("foreign KL029 database URL")
    db = RAW_CONNECT(
        url,
        connect_timeout=5,
        options="-c statement_timeout=12000 -c lock_timeout=10000 -c idle_in_transaction_session_timeout=12000",
        **kwargs,
    )
    try:
        with db.transaction():
            assert db.execute("SELECT current_database()").fetchone() == (selected.database_name,)
            assert db.execute(
                "SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout')"
            ).fetchone() == ("12s", "10s", "12s")
        if HEAD_ADMIN_URL is not None:
            with RAW_CONNECT(
                HEAD_ADMIN_URL,
                connect_timeout=5,
                options="-c statement_timeout=12000 -c lock_timeout=10000",
            ) as verifier:
                assert verifier.execute(
                    "SELECT current_database(),version_num FROM alembic_version"
                ).fetchone() == (selected.database_name, M.HEAD_REVISION)
        return db
    except BaseException:
        db.close()
        raise


@pytest.fixture
def database_urls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    global DEADLINE, HEAD_ADMIN_URL
    U.test_namespace_and_boundary(tmp_path)
    lifecycle = U.OwnedLifecycle(ROOT, head())
    selected = lifecycle.namespace
    DEADLINE = time.monotonic() + 180
    HEAD_ADMIN_URL = None
    try:
        with monkeypatch.context() as bootstrap_patch:
            bootstrap_patch.setattr(
                psycopg,
                "connect",
                lambda *args, **kwargs: bootstrap_connection(lifecycle, *args, **kwargs),
            )
            urls = lifecycle.bootstrap(M.bootstrap_two_phase)
        HEAD_ADMIN_URL = urls["admin"]
        with connect(urls["admin"]) as admin:
            assert admin.execute("SELECT version_num FROM alembic_version").fetchone() == (
                M.HEAD_REVISION,
            )
        # Only a connection adapter is substituted. All source/planning/protocol owners
        # and fixture operations run unchanged; no foreign fixture is ever requested.
        monkeypatch.setattr(D, "connect", connect)
        original_guard = RepositoryTransaction.evaluate_execution_authorization

        def observe_guard(tx: Any, **values: Any) -> Any:
            decision = original_guard(tx, **values)
            assert decision.is_executable
            witness(
                "actual_T7_positive_guard",
                command=tx.command_kind,
                subject=tx.subject_id,
                identities=values,
                decision=asdict(decision),
            )
            return decision

        monkeypatch.setattr(
            RepositoryTransaction, "evaluate_execution_authorization", observe_guard
        )
        witness(
            "namespace",
            root=str(ROOT.resolve()),
            compose=selected.project_name,
            database=selected.database_name,
            migration=M.HEAD_REVISION,
            lifecycle=lifecycle.inventory,
        )
        yield urls
    finally:
        HEAD_ADMIN_URL = None
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
        witness("cleanup", inventory=lifecycle.inventory, remaining=remaining)


def history(db: Any, seed: Any) -> Any:
    result = D.snapshot(db, D.auth(seed).subject_id)
    with db.transaction():
        for table in (
            "evidence_revisions",
            "candidate_assertions",
            "underlying_events",
            "event_association_decisions",
            "policy_bundles",
            "program_versions",
            "evaluation_releases",
            "tool_evidence_records",
            "call_reservations",
            "call_ledger_events",
        ):
            result[table] = db.execute(
                sql.SQL(
                    "SELECT to_jsonb(t) FROM kineticloop.{} t WHERE subject_id=%s ORDER BY to_jsonb(t)::text"
                ).format(sql.Identifier(table)),
                (D.auth(seed).subject_id,),
            ).fetchall()
        result["registry"] = db.execute(
            "SELECT to_jsonb(t) FROM kineticloop.safety_registry_state t ORDER BY id"
        ).fetchall()
        result["registry_artifacts"] = db.execute(
            "SELECT to_jsonb(t) FROM kineticloop.safety_artifacts t ORDER BY id"
        ).fetchall()
        result["registry_dependencies"] = db.execute(
            "SELECT to_jsonb(t) FROM kineticloop.safety_artifact_dependencies t ORDER BY artifact_id,dependency_artifact_id"
        ).fetchall()
        result["registry_revocations"] = db.execute(
            "SELECT to_jsonb(t) FROM kineticloop.artifact_revocation_events t ORDER BY id"
        ).fetchall()
        others = db.execute(
            "SELECT subject_id FROM kineticloop.subject_scopes WHERE namespace='TEST' AND subject_id<>%s ORDER BY subject_id",
            (D.auth(seed).subject_id,),
        ).fetchall()
        result["scope_registrations"] = db.execute(
            "SELECT to_jsonb(t) FROM kineticloop.subject_scopes t ORDER BY subject_id"
        ).fetchall()
        result["principal_bindings"] = db.execute(
            "SELECT to_jsonb(t) FROM kineticloop.subject_principal_bindings t ORDER BY subject_id"
        ).fetchall()
        result["evaluation_rows"] = {
            table: db.execute(
                sql.SQL("SELECT to_jsonb(t) FROM kineticloop.{} t ORDER BY id").format(
                    sql.Identifier(table)
                )
            ).fetchall()
            for table in ("replay_runs", "replay_artifacts")
        }
    result["other_TEST_subjects"] = {str(subject): D.snapshot(db, subject) for (subject,) in others}
    return result


def positive(urls: Any) -> tuple[Any, Any, Any]:
    seed, request = D.ready(urls)
    with connect(urls["admin"]) as db:
        before_commit = history(db, seed)
        result = D.service(db, seed).commit_full(request)
        after_commit = history(db, seed)
        for table in (
            "proposal_revisions",
            "prescription_demand_features",
            "evidence_resolutions",
            "validation_results",
        ):
            assert before_commit[table] == after_commit[table]
        for order, member in enumerate(result["members"], 1):
            with db.transaction():
                row = db.execute(
                    "SELECT member.member_kind,member.session_slot,member.member_order,p.ref_s34_id,p.typed_payload,p.content_hash,a.ref_s36_id,a.ref_s37_id,a.validity_certificate,a.valid_until FROM kineticloop.bundle_prescription_members member JOIN kineticloop.prescription_revisions p ON p.id=member.ref_s40_id JOIN kineticloop.authorization_issuances a ON a.ref_s40_id=p.id WHERE member.subject_id=%s AND p.id=%s",
                    (D.auth(seed).subject_id, UUID(member["prescription_id"])),
                ).fetchone()
            action = "TRAINING" if order == 1 else "NUTRITION"
            proposal = request.sources["fitness" if order == 1 else "nutrition"]["id"]
            assert row[:4] == (action, action + "_1", order, UUID(proposal))
            assert digest(row[4]) == row[5] == member["content_hash"]
            assert row[6:8] == (UUID(member["resolution_id"]), UUID(request.command.validation_id))
            certificate = row[8]
            assert (
                certificate["authorization_epoch"] == request.command.expected_authorization_epoch
            )
            assert (
                certificate["closure_digest"]
                == digest(certificate["dependencies"])
                == result["artifact_dependency_closure_hash"]
            )
            from datetime import datetime

            assert row[9] == min(
                datetime.fromisoformat(d["valid_until"])
                for d in certificate["dependencies"]
                if d.get("valid_until") is not None
            )
            assert {
                d["identity"]
                for d in certificate["dependencies"]
                if d["dependency_kind"] == "EVIDENCE_RESOLUTION"
            } == {request.sources[k]["id"] for k in ("resolution", "nutrition_resolution")}
        D.assert_event(db, seed, result)
        assert len(result["members"]) == 2
        command = D.session_command(seed, result)
        started = D.service(db, seed).start(command)
        assert started["executable"] and not started["replayed"]
        D.assert_event(db, seed, started)
        binding = D.current_binding(db, seed, started["session_id"])
        continued = D.service(db, seed).continue_session(
            D.session_command(
                seed, result, ContinueSession, session_id=started["session_id"], binding=binding
            )
        )
        assert continued["executable"]
        D.assert_event(db, seed, continued)
        paused = D.service(db, seed).pause(D.pause_request(db, seed, started["session_id"]))
        D.assert_event(db, seed, paused)
        resumed = D.service(db, seed).resume(
            D.session_command(
                seed, result, ResumeSession, session_id=started["session_id"], binding=binding
            )
        )
        assert resumed["executable"]
        D.assert_event(db, seed, resumed)
        state = history(db, seed)
        assert binding in [r[0] for r in state["execution_bindings"]]
        assert len(state["execution_bindings"]) == 2
        assert len(state["authorization_issuances"]) == 2
        assert state["planning_intents"][0][0]["status"] == "FOUND_VALID_PLAN"
        witness(
            "full_TEST_owner_trajectory",
            sources=request.sources,
            T6=result,
            START=started,
            CONTINUE=continued,
            PAUSE=paused,
            RESUME=resumed,
            immutable_history=state,
        )
    return seed, result, resumed


def deny(
    db: Any, seed: Any, operation: Any, exception: Any, cause: str, reach: str, **values: Any
) -> None:
    before = history(db, seed)
    with pytest.raises(exception, match=cause) as caught:
        operation()
    db.rollback()
    after = history(db, seed)
    assert before == after
    witness(
        "zero_effect",
        guard_reached=reach,
        actual_cause=str(caught.value),
        before=before,
        after=after,
        zero_new_receipt_event_outbox=True,
        **values,
    )


def register(urls: Any, namespace: str, key: str) -> Any:
    subject, environment, policy = uuid4(), uuid4(), uuid4()
    login = {
        "evaluation": "kl_evaluation_subject_1_login",
        "evaluation_2": "kl_evaluation_subject_2_login",
        "production_subject": "kl_production_subject_1_login",
        "test_2": "kl_test_subject_2_login",
    }[key]
    if namespace == "TEST":
        with connect(urls["admin"]) as db:
            db.execute(
                "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash) VALUES (%s,%s,'test:kl029-B','1',%s)",
                (policy, subject, digest("B")),
            )
            db.execute(
                "INSERT INTO kineticloop.user_decision_state(subject_id,input_frontier_hash,active_policy_bundle_id) VALUES (%s,%s,%s)",
                (subject, digest("isolated-B-initial-upstream"), policy),
            )
    with connect(urls["trusted_admin"]) as trusted:
        trusted.execute(
            "SELECT kineticloop.subject_scope_register(%s,%s,%s,%s,%s)",
            (
                subject,
                namespace,
                policy if namespace == "TEST" else None,
                None if namespace == "PRODUCTION" else environment,
                login,
            ),
        )
    witness(
        "trusted_registration",
        subject=subject,
        environment=environment,
        policy=policy if namespace == "TEST" else None,
        namespace=namespace,
        principal=login,
    )
    return {
        "subject": subject,
        "environment": environment,
        "policy": policy,
        "login": login,
        "actor": RoleIdentity(
            str(subject) if namespace == "PRODUCTION" else str(uuid4()),
            {
                "TEST": ActorRole.TEST,
                "EVALUATION": ActorRole.EVALUATION,
                "PRODUCTION": ActorRole.SUBJECT,
            }[namespace],
        ),
    }


def lookup(
    db: Any, identity: Any, kind: ScopedObjectKind, subject: Any, object_id: str, success: bool
) -> Any:
    row = db.execute(
        "SELECT kineticloop.subject_scope_lookup(%s,%s)", (kind.value, UUID(object_id))
    ).fetchone()
    kwargs = dict(
        actor=identity["actor"],
        actor_subject_id=str(identity["subject"]),
        target_subject_id=str(subject),
        object_kind=kind,
        object_id=object_id,
    )
    if success:
        assert row[0]["object_id"] == object_id and row[0]["subject_id"] == str(subject)
        obj = read_scoped_object(db, **kwargs)
        assert obj.object_id == object_id and obj.subject_id == str(subject)
        witness("positive_scoped_lookup", payload=row[0], wrapper=str(obj))
        return obj
    assert row == (None,)
    with pytest.raises(SubjectScopeDenied) as caught:
        read_scoped_object(db, **kwargs)
    denial = caught.value.denial
    assert denial.code == "SUBJECT_SCOPE_DENIED" and denial.timing_class == "BOUNDED_SCOPE_LOOKUP"
    assert dict(denial.payload) == {"error": "subject_scope_denied"}
    assert object_id not in repr(denial) and str(subject) not in repr(denial)
    witness(
        "scope_denial",
        guard_reached="DB_scope_lookup/application_scope",
        response=dict(denial.payload),
        code=denial.code,
        timing_class=denial.timing_class,
        measured_constant_time=False,
    )
    return denial


def live_objects(db: Any, seed: Any) -> Any:
    state = history(db, seed)
    return [
        (ScopedObjectKind.DAILY_PLAN_HEAD, "daily_plan_heads", state["daily_plan_heads"][0][0]),
        (
            ScopedObjectKind.AUTHORIZATION_ISSUANCE,
            "authorization_issuances",
            state["authorization_issuances"][0][0],
        ),
        (
            ScopedObjectKind.EXECUTION_BINDING,
            "execution_bindings",
            state["execution_bindings"][0][0],
        ),
    ]


def test_evaluation_principal_live_denials(database_urls: Any) -> None:
    urls = database_urls
    seed, _, _ = positive(urls)
    evaluation = register(urls, "EVALUATION", "evaluation")
    with connect(urls["admin"]) as admin:
        archive = declared_archive(admin, evaluation)
        with connect(urls["evaluation"]) as scoped:
            for kind, table in (
                (ScopedObjectKind.REPLAY_RUN, "replay_runs"),
                (ScopedObjectKind.REPLAY_ARTIFACT, "replay_artifacts"),
            ):
                lookup(scoped, evaluation, kind, evaluation["subject"], str(archive[table]), True)
        objects = live_objects(admin, seed)
        original = history(admin, seed)
        with connect(urls["test"]) as scoped:
            identity = {"actor": D.auth(seed).actor, "subject": D.auth(seed).subject_id}
            for kind, _, row in objects:
                lookup(scoped, identity, kind, identity["subject"], row["id"], True)
        with connect(urls["evaluation"]) as scoped:
            for kind, table, row in objects:
                denials = [
                    lookup(scoped, evaluation, kind, D.auth(seed).subject_id, target, False)
                    for target in (row["id"], str(uuid4()))
                ]
                assert denials[0] == denials[1]
                scoped.rollback()
                for verb in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    statement, params = {
                        "SELECT": (
                            f"SELECT * FROM kineticloop.{table} WHERE id=%s",
                            (UUID(row["id"]),),
                        ),
                        "INSERT": (
                            f"INSERT INTO kineticloop.{table} SELECT (jsonb_populate_record(NULL::kineticloop.{table},%s)).*",
                            (
                                Jsonb(
                                    {
                                        **row,
                                        "id": str(uuid4()),
                                        "subject_id": str(evaluation["subject"]),
                                    }
                                ),
                            ),
                        ),
                        "UPDATE": (
                            f"UPDATE kineticloop.{table} SET subject_id=%s WHERE id=%s",
                            (evaluation["subject"], UUID(row["id"])),
                        ),
                        "DELETE": (
                            f"DELETE FROM kineticloop.{table} WHERE id=%s",
                            (UUID(row["id"]),),
                        ),
                        "TRUNCATE": (f"TRUNCATE kineticloop.{table}", ()),
                    }[verb]
                    with pytest.raises(psycopg.errors.InsufficientPrivilege) as caught:
                        scoped.execute(statement, params)
                    scoped.rollback()
                    assert history(admin, seed) == original
                    witness(
                        "live_privilege_denial",
                        guard_reached="DB_table_privilege",
                        sqlstate=caught.value.sqlstate,
                        table=table,
                        verb=verb,
                        target=row["id"],
                        evaluation_subject=evaluation["subject"],
                        immutable_history=original,
                    )


def test_test_authorization_crossing_denials(database_urls: Any) -> None:
    urls = database_urls
    seed, result, _ = positive(urls)
    other = register(urls, "TEST", "test_2")
    evaluation = register(urls, "EVALUATION", "evaluation")
    production = register(urls, "PRODUCTION", "production_subject")
    auth = D.auth(seed)
    with connect(urls["admin"]) as db:
        for field, value in (
            ("principal", other["login"]),
            ("policy_id", uuid4()),
            ("environment_id", uuid4()),
        ):
            altered = replace(auth, **{field: value})
            template = D.session_command(seed, result)
            extras = template.model_dump(mode="json")
            for name in (
                "schema_version",
                "command_kind",
                "boundary",
                "command_id",
                "actor",
                "idempotency_key",
                "request_hash",
                "subject_id",
                "explicit_scope",
                "authorization_scope",
            ):
                extras.pop(name)
            command = U.wire(altered, StartSession, **extras)
            altered.require_wire(command)
            deny(
                db,
                seed,
                lambda: ProtocolExecutionService(db, altered).start(command),
                GuardRequired,
                "authenticated TEST registration mismatch",
                "registration_guard",
                field=field,
                command=command.model_dump(mode="json"),
            )
        for field in ("actor", "subject_id", "policy_id", "environment_id"):
            altered = replace(
                auth,
                **{
                    field: RoleIdentity(str(uuid4()), ActorRole.TEST)
                    if field == "actor"
                    else uuid4()
                },
            )
            command = D.session_command(seed, result)
            deny(
                db,
                seed,
                lambda: ProtocolExecutionService(db, altered).start(command),
                ValueError,
                "authenticated TEST command binding mismatch",
                "require_wire",
                field=field,
                command=command.model_dump(mode="json"),
            )
        command_hash_mismatch = D.changed(D.session_command(seed, result), request_hash="f" * 64)
        # Rebuild all other fields with a fresh key, then alter only its supplied hash.
        command_hash_mismatch = StartSession.model_validate_json(
            json.dumps({**command_hash_mismatch.model_dump(mode="json"), "request_hash": "f" * 64})
        )
        deny(
            db,
            seed,
            lambda: D.service(db, seed).start(command_hash_mismatch),
            ValueError,
            "authenticated TEST command binding mismatch",
            "require_wire",
            field="request_hash",
        )
        identity_b = ExecutionIdentity(
            other["actor"], other["subject"], other["policy"], other["environment"], other["login"]
        )
        m = result["members"][0]
        command_b = U.wire(
            identity_b,
            StartSession,
            session_id=str(uuid4()),
            action_key=str(uuid4()),
            prescription_id=m["prescription_id"],
            authorization_id=m["authorization_id"],
            binding_revision=1,
            expected_authorization_epoch=seed["basis"].epoch,
            content_hash=m["content_hash"],
            artifact_dependency_closure_hash=result["artifact_dependency_closure_hash"],
        )
        identity_b.require_wire(command_b)
        deny(
            db,
            seed,
            lambda: ProtocolExecutionService(db, identity_b).start(command_b),
            GuardRequired,
            "exact current bundle membership missing",
            "owner_current_bundle_pre_T7",
            command=command_b.model_dump(mode="json"),
        )
        before_reads = history(db, seed)
        for identity, key in ((evaluation, "evaluation"), (production, "production_subject")):
            with pytest.raises(ValueError, match="authenticated TEST"):
                replace(auth, actor=identity["actor"])
            with connect(urls[key]) as scoped:
                for kind, _, row in live_objects(db, seed):
                    lookup(scoped, identity, kind, auth.subject_id, row["id"], False)
        with connect(urls["test_2"]) as scoped:
            for kind, _, row in live_objects(db, seed):
                lookup(scoped, other, kind, auth.subject_id, row["id"], False)

        assert history(db, seed) == before_reads
        witness("crossing_reads_zero_effect", immutable_history=before_reads)


def test_shadow_payload_owner_denials(database_urls: Any) -> None:
    urls = database_urls
    seed, result, _ = positive(urls)
    artifact = ShadowEvaluationArtifact(str(uuid4()), str(uuid4()))
    with connect(urls["admin"]) as db:
        owner = D.service(db, seed)
        owner._guard(D.auth(seed).subject_id)
        for method, cause in (
            (owner.commit_full, "closed full commit request required"),
            (owner.commit, "strict CommitBundle required"),
            (owner.start, "strict StartSession required"),
            (owner.continue_session, "strict ContinueSession required"),
            (owner.resume, "strict ResumeSession required"),
        ):
            for payload in (artifact, artifact.to_payload()):
                deny(
                    db,
                    seed,
                    lambda: method(payload),
                    GuardRequired,
                    cause,
                    "strict_owner_ingress",
                    payload_hash=digest(artifact.to_payload()),
                    entrypoint=method.__name__,
                )
        for model in (CommitBundle, StartSession, ContinueSession, ResumeSession):
            with pytest.raises(ValueError):
                parse_command(artifact.to_json())
            with pytest.raises(ValueError):
                parse_command(json.dumps({**artifact.to_payload(), "command_kind": model.__name__}))
        command = D.session_command(seed, result)
        for field, value in (
            ("boundary", "T6"),
            ("authorization_scope", {"scope": "shadow_only", "subject_id": command.subject_id}),
        ):
            with pytest.raises(ValueError):
                parse_command(json.dumps({**command.model_dump(mode="json"), field: value}))


def declared_archive(db: Any, identity: Any) -> Any:
    """External archived evaluation inputs and only their required same-subject FK closure.

    These rows have no live S01 pointer, issuance, binding, tested owner certificate
    or replay API provenance. They are storage fixture inputs, never workflow outputs.
    """
    from datetime import timedelta

    subject = identity["subject"]
    ids = {
        table: uuid4()
        for table in (
            "policy_bundles",
            "program_versions",
            "factset_revisions",
            "projection_versions",
            "manifest_builds",
            "evaluation_releases",
            "safety_artifacts",
            "decision_manifests",
            "replay_runs",
            "replay_artifacts",
        )
    }
    with db.transaction():
        assert db.execute("SHOW session_replication_role").fetchone() == ("origin",)
        now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        revision = db.execute(
            "SELECT registry_revision FROM kineticloop.safety_registry_state WHERE id=1"
        ).fetchone()[0]
        source = {
            "source_ref": "external:kl029:archived-evaluation:" + str(subject),
            "knowledge_cutoff": now.isoformat(),
            "mode": "RECORDED_OUTPUT",
            "classification": "EXTERNAL_HISTORICAL_INPUT_ONLY",
            "execution_disposition": "NOT_EXECUTABLE",
        }
        h = digest(source)
        rows: dict[str, dict[str, Any]] = {
            "policy_bundles": dict(
                policy_namespace="evaluation:kl029-archive", policy_version="1", content_hash=h
            ),
            "program_versions": dict(
                program_identity="evaluation:kl029-archive", program_revision=1
            ),
            "factset_revisions": dict(
                factset_identity="archived",
                status="SEALED",
                storage_mode="FULL",
                membership_digest=digest([]),
                delta_depth=0,
                member_revision=0,
                completed_member_revision=0,
                sealed_at=now,
            ),
            "projection_versions": dict(
                projection_kind="ARCHIVED_EVALUATION",
                input_basis_hash=h,
                computed_at=now,
                valid_until=now + timedelta(days=1),
            ),
            "manifest_builds": dict(
                build_identity="external-archive",
                status="PUBLISHED",
                captured_epoch=0,
                ref_s05_id=ids["policy_bundles"],
                ref_s06_id=ids["program_versions"],
                ref_s15_id=ids["factset_revisions"],
                ref_s21_id=ids["projection_versions"],
            ),
            "evaluation_releases": dict(
                release_namespace="evaluation:kl029-archive", release_version="1", content_hash=h
            ),
            "safety_artifacts": dict(
                artifact_kind="POLICY_BUNDLE",
                artifact_identity="evaluation:kl029-archive:" + str(subject),
                artifact_version="1",
                content_hash=h,
                validity_kind="BOUNDED",
                valid_from=now,
                valid_until=now + timedelta(days=1),
                ref_s05_id=ids["policy_bundles"],
            ),
            "decision_manifests": dict(
                manifest_hash=h,
                generation=1,
                captured_epoch=0,
                dependency_closure_hash=digest([str(ids["safety_artifacts"])]),
                registry_revision_at_publish=revision,
                valid_until=now + timedelta(days=1),
                ref_s05_id=ids["policy_bundles"],
                ref_s06_id=ids["program_versions"],
                ref_s15_id=ids["factset_revisions"],
                ref_s23_id=ids["manifest_builds"],
                ref_s49_id=ids["safety_artifacts"],
                registry_state_id=1,
            ),
            "replay_runs": dict(
                replay_mode="RECORDED_OUTPUT",
                input_selection_hash=h,
                knowledge_cutoff=now,
                status="SUCCEEDED",
                ref_s24_id=ids["decision_manifests"],
                ref_s48_id=ids["evaluation_releases"],
            ),
            "replay_artifacts": dict(
                artifact_kind="RECORDED_OUTPUT",
                artifact_hash=h,
                knowledge_cutoff=now,
                ref_s46_id=ids["replay_runs"],
            ),
        }
        persisted = {}
        for table, values in rows.items():
            row = {"id": ids[table], "typed_payload": Jsonb(source), **values}
            if table != "safety_artifacts":
                row["subject_id"] = subject
            db.execute(
                sql.SQL("INSERT INTO kineticloop.{} ({}) VALUES ({})").format(
                    sql.Identifier(table),
                    sql.SQL(",").join(map(sql.Identifier, row)),
                    sql.SQL(",").join(sql.Placeholder() for _ in row),
                ),
                tuple(row.values()),
            )
            stored = db.execute(
                sql.SQL("SELECT to_jsonb(t) FROM kineticloop.{} t WHERE id=%s").format(
                    sql.Identifier(table)
                ),
                (ids[table],),
            ).fetchone()[0]
            persisted[table] = {"row": stored, "row_hash": digest(stored)}
        triggers = db.execute(
            "SELECT c.relname,t.tgname,t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='kineticloop' AND c.relname=ANY(%s) ORDER BY c.relname,t.tgname",
            (list(rows),),
        ).fetchall()
        assert triggers and all(row[2] in ("O", "A") for row in triggers)
        assert db.execute(
            "SELECT registry_revision FROM kineticloop.safety_registry_state WHERE id=1"
        ).fetchone() == (revision,)
    witness(
        "declared_external_evaluation_inputs",
        subject=subject,
        source=source,
        persisted=persisted,
        triggers=triggers,
        no_live_pointer_or_shadow_owner_output=True,
    )
    return ids


def test_declared_evaluation_storage_isolation(database_urls: Any) -> None:
    urls = database_urls
    seed, _, _ = positive(urls)
    a = register(urls, "EVALUATION", "evaluation")
    b = register(urls, "EVALUATION", "evaluation_2")
    production = register(urls, "PRODUCTION", "production_subject")
    with connect(urls["admin"]) as admin:
        before = history(admin, seed)
        ids_a = declared_archive(admin, a)
        ids_b = declared_archive(admin, b)
        # Registry fixture inputs add identities but never change the TEST source/output
        # rows or revision. Capture exact permitted additions separately.
        after_inputs = history(admin, seed)
        for table in before:
            if table not in ("registry_artifacts", "evaluation_rows"):
                assert before[table] == after_inputs[table], table
        assert len(after_inputs["registry_artifacts"]) == len(before["registry_artifacts"]) + 2
        test = {"actor": D.auth(seed).actor, "subject": D.auth(seed).subject_id}
        for identity, key, ids in ((a, "evaluation", ids_a), (b, "evaluation_2", ids_b)):
            with connect(urls[key]) as scoped:
                for kind, table in (
                    (ScopedObjectKind.REPLAY_RUN, "replay_runs"),
                    (ScopedObjectKind.REPLAY_ARTIFACT, "replay_artifacts"),
                ):
                    lookup(scoped, identity, kind, identity["subject"], str(ids[table]), True)
        for identity, key in (
            (b, "evaluation_2"),
            (test, "test"),
            (production, "production_subject"),
        ):
            with connect(urls[key]) as scoped:
                for kind, table in (
                    (ScopedObjectKind.REPLAY_RUN, "replay_runs"),
                    (ScopedObjectKind.REPLAY_ARTIFACT, "replay_artifacts"),
                ):
                    denials = [
                        lookup(scoped, identity, kind, a["subject"], target, False)
                        for target in (str(ids_a[table]), str(uuid4()))
                    ]
                    assert denials[0] == denials[1]
        for kind, table, row in live_objects(admin, seed):
            # A complete valid source row means this fails at storage namespace,
            # before a foreign-key or missing-required-field substitute can mask it.
            deny(
                admin,
                seed,
                lambda: admin.execute(
                    sql.SQL(
                        "INSERT INTO kineticloop.{} SELECT (jsonb_populate_record(NULL::kineticloop.{},%s)).*"
                    ).format(sql.Identifier(table), sql.Identifier(table)),
                    (Jsonb({**row, "id": str(uuid4()), "subject_id": str(a["subject"])}),),
                ),
                psycopg.errors.RaiseException,
                "KL_SUBJECT_SCOPE_LIVE_STORAGE_DENIED",
                "DB_storage_namespace",
                table=table,
            )
        for identity in (test, production):
            for table in ("replay_runs", "replay_artifacts"):
                source = admin.execute(
                    sql.SQL("SELECT to_jsonb(t) FROM kineticloop.{} t WHERE id=%s").format(
                        sql.Identifier(table)
                    ),
                    (ids_a[table],),
                ).fetchone()[0]
                admin.rollback()
                deny(
                    admin,
                    seed,
                    lambda: admin.execute(
                        sql.SQL(
                            "INSERT INTO kineticloop.{} SELECT (jsonb_populate_record(NULL::kineticloop.{},%s)).*"
                        ).format(sql.Identifier(table), sql.Identifier(table)),
                        (
                            Jsonb(
                                {
                                    **source,
                                    "id": str(uuid4()),
                                    "subject_id": str(identity["subject"]),
                                }
                            ),
                        ),
                    ),
                    psycopg.errors.RaiseException,
                    "KL_SUBJECT_SCOPE_EVALUATION_STORAGE_DENIED",
                    "DB_storage_namespace",
                    table=table,
                )
        assert history(admin, seed) == after_inputs
