from __future__ import annotations

import copy
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Event
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
)
from kineticloop.persistence.protocol_execution import ProtocolExecutionService
from kineticloop.persistence.transactions import (
    RepositoryTransaction,
    RepositoryTransactionError,
    RestrictedSqlSession,
)
from kineticloop.protocol.execution import (
    ExecutionIdentity,
    FullCommitRequest,
    OrdinaryPause,
    binding_digest,
    digest,
)

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: str) -> Any:
    spec = spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P = load("kl077_sources", "tests/db/test_full_action_preparation.py")
N = load("kl077_namespace", "tests/unit/protocol/test_full_test_execution.py")
M = load("kl077_migrations", "tests/db/test_migrations.py")


def connect(url: str, **kwargs: Any) -> Any:
    expected = N.fixture_namespace(ROOT, P.current_head())
    if urlparse(url).path != "/" + expected.database_name:
        raise ValueError("foreign KL077 database URL")
    db = psycopg.connect(url, options="-c statement_timeout=12000 -c lock_timeout=10000", **kwargs)
    with db.transaction():
        assert db.execute("SELECT current_database()").fetchone() == (expected.database_name,)
    return db


P.connect = connect  # Source helpers accept explicit own URLs; no foreign fixture lifecycle.
P.TABLES = (
    *P.TABLES,
    "authorization_artifact_closure",
    "authorization_events",
    "control_events",
    "control_heads",
)


@pytest.fixture
def database_urls() -> Any:
    N.test_namespace(
        Path("/private/tmp/kl077-peer-root")
        if sys.platform == "darwin"
        else Path("/tmp/kl077-peer-root")
    )
    lifecycle = N.OwnedLifecycle(ROOT, P.current_head())
    selected = lifecycle.namespace
    start = time.monotonic()
    try:
        urls = lifecycle.bootstrap(M.bootstrap_two_phase)
        with connect(urls["admin"]) as db:
            assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
                M.HEAD_REVISION,
            )
        P.witness(
            "namespace",
            tested_commit=P.current_head(),
            resolved_root=str(ROOT),
            compose=selected.project_name,
            database=selected.database_name,
            migration=M.HEAD_REVISION,
            nested_routes=[
                "selected bootstrap",
                "reset",
                "start",
                "current_database",
                "finally own destroy",
            ],
        )
        yield urls
    finally:
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
        assert not any(remaining.values())
        P.witness(
            "cleanup",
            compose=selected.project_name,
            database=selected.database_name,
            inventory=lifecycle.inventory,
            remaining=remaining,
            elapsed=time.monotonic() - start,
        )


def auth(seed: Any) -> ExecutionIdentity:
    i = seed["identity"]
    return ExecutionIdentity(i.actor, i.subject_id, i.policy_id, i.environment_id, i.principal)


def service(db: Any, seed: Any) -> ProtocolExecutionService:
    return ProtocolExecutionService(db, auth(seed))


def seed_source(
    urls: dict[str, str],
    *,
    seconds: float = 3600,
    admission_seconds: float | None = None,
    runtime_seconds: float | None = None,
    full: bool = True,
    fact_changes: Any = None,
    config_changes: Any = None,
) -> dict[str, Any]:
    (
        subject,
        policy_id,
        program,
        environment,
        engine,
        runtime,
        builder,
        release,
        release_artifact,
        evidence,
        assertion,
        event,
        association,
        admission,
        fact,
    ) = [uuid4() for _ in range(15)]
    actor = P.RoleIdentity(str(uuid4()), P.ActorRole.TEST)
    identity = P.ProgressIdentity(actor, subject, policy_id, environment, "kl_test_subject_1_login")
    with connect(urls["admin"], autocommit=True) as db:
        clock = db.execute("SELECT clock_timestamp()").fetchone()
        assert clock is not None
        now = clock[0]
        end = now + timedelta(seconds=seconds)
        admission_end = now + timedelta(seconds=admission_seconds or seconds)
        runtime_end = now + timedelta(seconds=runtime_seconds or seconds)
        config = {
            "rules": copy.deepcopy(P.RULES),
            "window": [(now - timedelta(days=1)).isoformat(), end.isoformat()],
            "required_members": sorted(map(str, (association, admission, fact))),
            "reservations": {"prior-slot": 50},
            "valid_until": end.isoformat(),
        }
        if full:
            config.update(contract=P.FULL_VERSION, required_actions=["TRAINING", "NUTRITION"])
        config.update(config_changes or {})
        runtime_version = P.FULL_VERSION if full else P.VERSION
        runtime_hash = (
            digest({"version": P.FULL_VERSION, "rules": P.RULES}) if full else digest(P.RULES)
        )
        deps = (
            P.Dependency("COLLECTION", "fixture-facts", "all-fixture-facts-and-absence:v1"),
            P.Dependency("ENGINE", f"test:kl079-engine-{subject}:1"),
            P.Dependency("FACTSET", "sealed-input"),
            P.Dependency("POLICY", "selected-policy"),
            P.Dependency("PROGRAM", "selected-program"),
            P.Dependency("FACT", "actual-member", fact_id=fact),
        )
        body = {
            "deterministic_fixture": config,
            "fixture_runtime": {
                "id": str(runtime),
                "hash": runtime_hash,
                "version": runtime_version,
            },
            "factset_max_delta_depth": 1,
            "planning_context": {
                block: {
                    "status": "TEST_INPUT_ONLY",
                    "value": [str(fact)] if block == "recent_execution" else [],
                }
                for block in P.POLICY_BLOCKS
            },
            "planning_context_byte_budget": 65536,
            "planning_context_builder": {"id": str(builder), "hash": digest("context-builder")},
            "planning_admission": {
                "version": "kl024-v1",
                "purposes": ["TRAINING"],
                "triggers": ["USER_REQUEST"],
                "auto_root_triggers": [],
                "max_active_per_day": 1,
                "capacity_available": True,
                "hourly_roots": 10,
                "daily_roots": 10,
                "deadline_seconds": 3600,
                "calendar_policies": ["test:UTC-v1"],
                "root_limits": {"calls": 3, "tokens": 1000, "tools": 10},
            },
            "execution_calendar": {"policy": "test:UTC-v1", "timezone": "UTC"},
            "authorization_action_scopes": {"TRAINING": "TEST_ONLY"},
            "t2_invalidation_scopes": {
                "RecordActualExecution": "TEST_ONLY",
                "ApplyControl": "TEST_ONLY",
            },
            "manifest_projection_requirements": {
                "EXPOSURE": {
                    "projection_kind": "EXPOSURE",
                    "dependencies": [
                        {"kind": d.kind, "key": d.key, "collection": d.collection} for d in deps
                    ],
                }
            },
        }
        body["max_authorization_ttl_seconds"] = 300
        if full:
            body["authorization_action_scopes"] = {
                "TRAINING": "TEST_ONLY",
                "NUTRITION": "TEST_ONLY",
            }
        db.execute(
            "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) VALUES (%s,%s,'test:kl079','1',%s,%s)",
            (policy_id, subject, digest(body), Jsonb(body)),
        )
        db.execute(
            "INSERT INTO kineticloop.program_versions(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test:kl079',1)",
            (program, subject),
        )
        db.execute(
            "INSERT INTO kineticloop.user_decision_state(subject_id,input_frontier_hash,active_policy_bundle_id,active_program_id) VALUES (%s,%s,%s,%s)",
            (subject, digest("registered-source"), policy_id, program),
        )
        db.execute(
            "INSERT INTO kineticloop.evidence_revisions(id,subject_id,source_connection_identity,source_object_type,source_object_identity,source_revision,trust_class,source_class,command_authority) VALUES (%s,%s,'kl079-test','actual','fixture-actual','1','USER_REPORTED','USER','NONE')",
            (evidence, subject),
        )
        db.execute(
            "INSERT INTO kineticloop.candidate_assertions(id,subject_id,assertion_family_identity,ref_s09_id) VALUES (%s,%s,'fixture-actual',%s)",
            (assertion, subject, evidence),
        )
        db.execute(
            "INSERT INTO kineticloop.underlying_events(id,subject_id,event_identity) VALUES (%s,%s,'fixture-actual-event')",
            (event, subject),
        )
        assoc_body = {"fixture_association": "CONFIRMED", "event_id": str(event)}
        db.execute(
            "INSERT INTO kineticloop.event_association_decisions(id,subject_id,association_family_identity,association_state,ref_s11_id,content_hash,typed_payload) VALUES (%s,%s,'fixture-event','CONFIRMED',%s,%s,%s)",
            (association, subject, event, digest(assoc_body), Jsonb(assoc_body)),
        )
        admission_body = {"fixture_admission": "ADMITTED", "valid_until": admission_end.isoformat()}
        db.execute(
            "INSERT INTO kineticloop.admission_decisions(id,subject_id,action_scope,decision,ref_s05_id,ref_s09_id,ref_s10_id,content_hash,typed_payload) VALUES (%s,%s,'TEST_ONLY','ADMITTED',%s,%s,%s,%s,%s)",
            (
                admission,
                subject,
                policy_id,
                evidence,
                assertion,
                digest(admission_body),
                Jsonb(admission_body),
            ),
        )
        db.execute(
            "INSERT INTO kineticloop.evaluation_releases(id,subject_id,release_namespace,release_version,content_hash) VALUES (%s,%s,'test:kl079','1',%s)",
            (release, subject, digest("fixture-release")),
        )
        for artifact, kind, name, version, artifact_hash, payload, policy_ref, release_ref in (
            (
                engine,
                "POLICY_BUNDLE",
                f"test:kl079-engine-{subject}",
                "1",
                digest(body),
                {},
                policy_id,
                None,
            ),
            (
                runtime,
                "RUNTIME",
                f"test:kl079-runtime-{subject}",
                P.VERSION,
                digest(P.RULES),
                {"operation": "DETERMINISTIC_TEST_PREPARATION", "version": P.VERSION},
                None,
                release,
            ),
            (
                builder,
                "RUNTIME",
                f"test:kl079-builder-{subject}",
                "1",
                digest("context-builder"),
                {"operation": "CONTEXT_BUILDER"},
                None,
                release,
            ),
            (
                release_artifact,
                "PROMPT",
                f"test:kl079-release-{subject}",
                "1",
                digest("fixture-release"),
                {},
                None,
                release,
            ),
        ):
            if artifact == runtime and full:
                continue
            db.execute(
                "INSERT INTO kineticloop.safety_artifacts(id,artifact_kind,artifact_identity,artifact_version,content_hash,validity_kind,valid_from,valid_until,typed_payload,ref_s05_id,ref_s48_id) VALUES (%s,%s,%s,%s,%s,'BOUNDED',%s,%s,%s,%s,%s)",
                (
                    artifact,
                    kind,
                    name,
                    version,
                    artifact_hash,
                    now,
                    end,
                    Jsonb(payload),
                    policy_ref,
                    release_ref,
                ),
            )
        if full:
            with connect(urls["trusted_admin"]) as trusted:
                P.registered_runtime(
                    trusted,
                    runtime,
                    runtime_hash,
                    release,
                    now,
                    runtime_end,
                    (builder, release_artifact),
                )
        for dependency in (runtime, builder, release_artifact):
            if dependency == runtime and runtime_seconds is not None:
                continue
            db.execute(
                "INSERT INTO kineticloop.safety_artifact_dependencies(artifact_id,dependency_artifact_id) VALUES (%s,%s)",
                (engine, dependency),
            )
    with connect(urls["trusted_admin"], autocommit=True) as db:
        db.execute(
            "SELECT kineticloop.subject_scope_register(%s,'TEST',%s,%s,%s)",
            (subject, policy_id, environment, identity.principal),
        )
    seed = {
        "identity": identity,
        "program": program,
        "policy": body,
        "end": end,
        "admission_end": admission_end,
        "runtime_end": runtime_end,
        "now": now,
        "builder": builder,
        "deps": deps,
        "fact": fact,
        "association": association,
        "admission": admission,
        "assertion": assertion,
        "event": event,
        "runtime": runtime,
        "runtime_hash": runtime_hash,
        "full": full,
        "fact_changes": fact_changes or {},
        "engine": P.ArtifactIdentity(
            engine, "POLICY_BUNDLE", f"test:kl079-engine-{subject}", "1", digest(body)
        ),
    }
    with connect(urls["admin"]) as db:
        P.actual_input(db, seed, fact)
    return seed


def ready(urls: Any, **kwargs: Any) -> tuple[Any, Any]:
    seed = seed_source(urls, **kwargs)
    with connect(urls["admin"]) as db:
        P.upstream(db, seed)
        basis, refs = P.begin(db, seed)
        op, fullrefs = P.preparation_chain(db, seed, basis, refs)
        refs = P.prepare_validation(db, seed, op, fullrefs)
        P.commit_ready(db, seed, op, refs)
        sources = {**refs, "nutrition_resolution": fullrefs["nutrition_resolution"]}
        request = commit_request(db, seed, basis, sources)
    return seed, request


def commit_request(db: Any, seed: Any, basis: Any, sources: Any) -> FullCommitRequest:
    with db.transaction():
        manifest, generation, epoch, execution = db.execute(
            "SELECT current_manifest_id,decision_generation,authorization_epoch,execution_basis_event_id FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (basis.subject_id,),
        ).fetchone()
        closure = db.execute(
            "SELECT typed_payload->>'artifact_dependency_closure_hash' FROM kineticloop.decision_manifests WHERE id=%s",
            (manifest,),
        ).fetchone()[0]
    command = N.wire(
        auth(seed),
        CommitBundle,
        intent_id=str(basis.intent_id),
        attempt_id=str(basis.attempt_id),
        expected_request_revision=basis.request_revision,
        expected_owner_id=auth(seed).actor.identity_id,
        expected_fence=basis.fence,
        manifest_id=str(manifest),
        expected_generation=generation,
        expected_authorization_epoch=epoch,
        policy_id=str(auth(seed).policy_id),
        validation_id=sources["validation"]["id"],
        execution_basis_event_id=str(execution),
        artifact_dependency_closure_hash=closure,
        commit_identity=str(uuid4()),
        result_fingerprint=digest({"contract": "kl079-full-actions-v1", "sources": sources}),
    )
    request = FullCommitRequest(command, sources)
    seed.update(basis=basis, refs=sources)
    P.witness(
        "full_prepared_chain",
        subject=basis.subject_id,
        sources=sources,
        command=command.model_dump(mode="json"),
    )
    return request


def changed(command: Any, **values: Any) -> Any:
    payload = {**command.model_dump(mode="json"), **values}
    from kineticloop.protocol.execution import command_digest

    first = type(command).model_validate_json(json.dumps(payload))
    payload["request_hash"] = command_digest(first)
    return type(command).model_validate_json(json.dumps(payload))


def session_command(
    seed: Any,
    result: Any,
    model: Any = StartSession,
    *,
    session_id: str | None = None,
    binding: Any = None,
    member: int = 0,
) -> Any:
    m = result["members"][member]
    extras = {}
    if model == ContinueSession:
        extras = {"current_binding_id": binding["id"]}
    if model == ResumeSession:
        extras = {"prior_binding_id": binding["id"]}
    return N.wire(
        auth(seed),
        model,
        session_id=session_id or str(uuid4()),
        action_key=str(uuid4()),
        prescription_id=m["prescription_id"],
        authorization_id=m["authorization_id"],
        binding_revision=1
        if binding is None
        else binding["binding_revision"] + (1 if model == ResumeSession else 0),
        expected_authorization_epoch=seed["basis"].epoch,
        content_hash=m["content_hash"],
        artifact_dependency_closure_hash=result["artifact_dependency_closure_hash"],
        **extras,
    )


def current_binding(db: Any, seed: Any, session: str) -> Any:
    with db.transaction():
        return db.execute(
            "SELECT to_jsonb(b) FROM kineticloop.execution_bindings b WHERE subject_id=%s AND ref_s44_id=%s ORDER BY binding_revision DESC LIMIT 1",
            (auth(seed).subject_id, UUID(session)),
        ).fetchone()[0]


def pause_request(db: Any, seed: Any, session: str) -> OrdinaryPause:
    binding = current_binding(db, seed, session)
    with db.transaction():
        revision = db.execute(
            "SELECT execution_revision FROM kineticloop.workout_sessions WHERE subject_id=%s AND id=%s",
            (auth(seed).subject_id, UUID(session)),
        ).fetchone()[0]
    return OrdinaryPause(
        auth(seed),
        str(uuid4()),
        UUID(session),
        UUID(binding["id"]),
        binding_digest(binding),
        revision,
        "User requested break",
    )


def assert_event(db: Any, seed: Any, result: Any) -> None:
    with db.transaction():
        row = db.execute(
            "SELECT receipt.status,event.ref_s02_id,(SELECT count(*) FROM kineticloop.outbox_deliveries o WHERE o.subject_id=event.subject_id AND o.ref_s03_id=event.id) FROM kineticloop.command_receipts receipt JOIN kineticloop.domain_events event ON event.ref_s02_id=receipt.id AND event.subject_id=receipt.subject_id WHERE receipt.subject_id=%s AND receipt.id=%s AND event.id=%s",
            (auth(seed).subject_id, UUID(result["receipt_id"]), UUID(result["event_id"])),
        ).fetchone()
        assert row == ("SUCCEEDED", UUID(result["receipt_id"]), 1)


def test_full_bundle_commit(database_urls: Any) -> None:
    seed, request = ready(database_urls)
    with connect(database_urls["admin"]) as db:
        before = P.snapshot(db, auth(seed).subject_id)
        result = service(db, seed).commit_full(request)
        after = P.snapshot(db, auth(seed).subject_id)
        assert len(after["daily_bundle_revisions"]) == 1
        assert (
            len(after["prescription_revisions"])
            == len(after["bundle_prescription_members"])
            == len(after["authorization_issuances"])
            == 2
        )
        for order, m in enumerate(result["members"], 1):
            with db.transaction():
                row = db.execute(
                    "SELECT member.member_kind,member.session_slot,member.member_order,p.ref_s34_id,p.typed_payload,p.content_hash,a.ref_s36_id,a.ref_s37_id,a.validity_certificate,a.valid_until FROM kineticloop.bundle_prescription_members member JOIN kineticloop.prescription_revisions p ON p.id=member.ref_s40_id JOIN kineticloop.authorization_issuances a ON a.ref_s40_id=p.id WHERE member.subject_id=%s AND p.id=%s",
                    (auth(seed).subject_id, UUID(m["prescription_id"])),
                ).fetchone()
            action = "TRAINING" if order == 1 else "NUTRITION"
            proposal = request.sources["fitness" if order == 1 else "nutrition"]["id"]
            assert (
                row[:4] == (action, action + "_1", order, UUID(proposal))
                and digest(row[4]) == row[5] == m["content_hash"]
            )
            assert row[6:8] == (UUID(m["resolution_id"]), UUID(request.command.validation_id))
            resolution_ids = {
                x["identity"]
                for x in row[8]["dependencies"]
                if x["dependency_kind"] == "EVIDENCE_RESOLUTION"
            }
            assert resolution_ids == {
                request.sources[k]["id"] for k in ("resolution", "nutrition_resolution")
            }
        assert (
            after["planning_intents"][0][0]["status"] == "FOUND_VALID_PLAN"
            and after["planning_attempts"][0][0]["status"] == "COMMITTED"
        )
        for table in (
            "proposal_revisions",
            "prescription_demand_features",
            "evidence_resolutions",
            "validation_results",
        ):
            assert before[table] == after[table]
        assert_event(db, seed, result)
        for member in (0, 1):
            started = service(db, seed).start(session_command(seed, result, member=member))
            assert started["executable"]
            assert_event(db, seed, started)
        P.witness(
            "full_commit",
            result=result,
            persisted=after,
            exact_two_members=True,
            immutable_upstream=True,
        )


def perturb(db: Any, statement: str, params: Any) -> None:
    # Privileged, labeled negative corruption; never a positive owner trajectory.
    with db.transaction():
        db.execute(statement, params)


def denied(db: Any, seed: Any, operation: Any, cause: str, label: str) -> str:
    before = P.snapshot(db, auth(seed).subject_id)
    with pytest.raises((RepositoryTransactionError, psycopg.Error, ValueError)) as error:
        operation()
    message = str(error.value)
    assert cause in message, (label, cause, message)
    assert P.snapshot(db, auth(seed).subject_id) == before
    P.witness(
        "exact_zero_effect_denial",
        label=label,
        intended_cause=cause,
        actual_cause=message,
        persisted=before,
    )
    return message


@pytest.mark.parametrize(
    "case",
    [
        "legacy_downgrade",
        "fitness_id",
        "fitness_hash",
        "demand_id",
        "nutrition_id",
        "nutrition_hash",
        "training_resolution",
        "nutrition_resolution",
        "validation_hash",
        "policy",
        "subject",
        "epoch",
        "generation",
        "execution_basis",
        "fence",
        "lease",
        "deadline",
        "control",
        "runtime_revocation",
        "resolution_expiry",
        "missing_nutrition",
        "reordered",
        "foreign_certificate",
        "wrong_action",
        "wrong_proposal",
        "current_manifest",
        "current_attempt",
        "budget",
    ],
)
def test_full_bundle_denials(database_urls: Any, case: str) -> None:
    seed, request = ready(
        database_urls, **({"admission_seconds": 8} if case == "resolution_expiry" else {})
    )
    with connect(database_urls["admin"]) as db:
        command = request.command
        cause = ""

        def operation() -> Any:
            return service(db, seed).commit_full(request)

        if case == "legacy_downgrade":

            def operation() -> Any:
                return service(db, seed).commit(command)

            cause = "legacy downgrade denied"
        elif case in {
            "fitness_id",
            "fitness_hash",
            "demand_id",
            "nutrition_id",
            "nutrition_hash",
            "training_resolution",
            "nutrition_resolution",
            "validation_hash",
        }:
            names = {
                "fitness_id": "fitness",
                "fitness_hash": "fitness",
                "demand_id": "demand",
                "nutrition_id": "nutrition",
                "nutrition_hash": "nutrition",
                "training_resolution": "resolution",
                "nutrition_resolution": "nutrition_resolution",
                "validation_hash": "validation",
            }
            sources = {k: dict(v) for k, v in request.sources.items()}
            name = names[case]
            field = "hash" if case.endswith("hash") else "id"
            sources[name][field] = digest("stale") if field == "hash" else str(uuid4())
            command = changed(
                command, result_fingerprint=digest({"contract": P.FULL_VERSION, "sources": sources})
            )
            request = FullCommitRequest(command, sources)
            cause = (
                "immutable"
                if name != "nutrition_resolution"
                else "full exact action binding mismatch"
            )
        elif case in {"policy", "subject", "epoch", "generation", "execution_basis", "fence"}:
            fields = {
                "policy": "policy_id",
                "subject": "subject_id",
                "epoch": "expected_authorization_epoch",
                "generation": "expected_generation",
                "execution_basis": "execution_basis_event_id",
                "fence": "expected_fence",
            }
            value = 99 if case in {"epoch", "generation", "fence"} else str(uuid4())
            changed_values: dict[str, Any] = {fields[case]: value}
            if case in {"policy", "subject"}:
                scope = command.authorization_scope.model_dump(mode="json")
                scope[fields[case]] = value
                changed_values["authorization_scope"] = scope
            request = FullCommitRequest(changed(command, **changed_values), request.sources)
            cause = (
                "binding mismatch"
                if case == "subject"
                else "stale owner/fence"
                if case == "fence"
                else "mismatch"
                if case == "policy"
                else "exact current"
                if case == "epoch"
                else "current-basis expectations"
            )
        elif case in {"lease", "deadline"}:
            field = "lease_expires_at" if case == "lease" else "deadline"
            perturb(
                db,
                "UPDATE kineticloop.planning_intents SET "
                + field
                + "=clock_timestamp()-interval '1 second' WHERE id=%s",
                (UUID(command.intent_id),),
            )
            cause = "stale owner/fence"
        elif case == "control":
            P.apply_control(db, seed)
            cause = "KL_REGISTRY_AUTHORIZATION_INELIGIBLE"
        elif case == "runtime_revocation":
            P.revoke_runtime(database_urls, seed)
            cause = "KL_REGISTRY_ARTIFACT_REVOKED"
        elif case == "resolution_expiry":
            P.wait_db_time(db, seed["admission_end"])
            cause = "expired"
        elif case in {
            "missing_nutrition",
            "reordered",
            "foreign_certificate",
            "wrong_action",
            "wrong_proposal",
        }:
            sources = {k: dict(v) for k, v in request.sources.items()}
            if case == "missing_nutrition":
                sources["nutrition_resolution"]["id"] = str(uuid4())
                cause = "full exact action binding mismatch"
            elif case == "reordered":
                sources["resolution"], sources["nutrition_resolution"] = (
                    sources["nutrition_resolution"],
                    sources["resolution"],
                )
                cause = "earlier immutable prerequisite"
            elif case == "foreign_certificate":
                sources["validation"]["id"] = str(uuid4())
                command = changed(command, validation_id=sources["validation"]["id"])
                cause = "current immutable commit inputs missing"
            elif case == "wrong_action":
                sources["resolution"] = dict(sources["nutrition_resolution"])
                cause = "earlier immutable prerequisite"
            else:
                sources["fitness"] = dict(sources["nutrition"])
                cause = "earlier immutable prerequisite"
            request = FullCommitRequest(
                changed(
                    command,
                    result_fingerprint=digest({"contract": P.FULL_VERSION, "sources": sources}),
                ),
                sources,
            )
        elif case == "current_manifest":
            # Actual T3 publication with same immutable source; no target-output seed.
            from kineticloop.persistence.preparation import (
                BuildManifest,
                CompleteManifest,
                PreparationService,
                ProjectionBinding,
            )

            ingress = PreparationService(db, auth(seed))
            build = ingress.build_manifest(
                BuildManifest(
                    "replacement",
                    seed["source"],
                    (ProjectionBinding("EXPOSURE", UUID(seed["projection"]["projection_id"])),),
                    (seed["engine"].artifact_id,),
                )
            )
            complete = ingress.complete_manifest(CompleteManifest(UUID(build["build_id"])))
            P.publish(db, seed, seed["source"], complete, "replace-publication")
            cause = "current"
        elif case == "budget":
            with db.transaction():
                root = db.execute(
                    "SELECT typed_payload FROM kineticloop.planning_intents WHERE id=%s",
                    (UUID(command.intent_id),),
                ).fetchone()[0]
            root["reserved"]["calls"] = root["limits"]["calls"] + 1
            perturb(
                db,
                "UPDATE kineticloop.planning_intents SET typed_payload=%s WHERE id=%s",
                (Jsonb(root), UUID(command.intent_id)),
            )
            cause = "full planning root budget invalid"
        elif case == "current_attempt":
            perturb(
                db,
                "UPDATE kineticloop.planning_intents SET current_attempt_id=NULL WHERE id=%s",
                (UUID(command.intent_id),),
            )
            cause = "stale owner/fence"
        denied(db, seed, operation, cause, case)


@pytest.mark.parametrize(
    "case",
    [
        "positive",
        "wrong_revision",
        "wrong_binding",
        "wrong_hash",
        "wrong_session",
        "wrong_subject",
        "wrong_policy",
        "wrong_environment",
        "wrong_principal",
        "duplicate",
        "failure_session",
        "failure_basis",
        "failure_outcome",
        "after_control",
        "after_expiry",
        "after_head_change",
        "after_global_revocation",
        "registry_blocked",
        "generic_patch",
    ],
)
def test_ordinary_pause_owner(
    database_urls: Any, case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed, request = ready(
        database_urls, **({"admission_seconds": 8} if case == "after_expiry" else {})
    )
    with connect(database_urls["admin"]) as db:
        result = service(db, seed).commit_full(request)
        start = service(db, seed).start(session_command(seed, result))
        pause = pause_request(db, seed, start["session_id"])
        original_start = current_binding(db, seed, start["session_id"])
        if case.startswith("wrong_"):
            changes: dict[str, Any] = {
                "wrong_revision": {"expected_execution_revision": 99},
                "wrong_binding": {"binding_id": uuid4()},
                "wrong_hash": {"binding_hash": digest("foreign")},
                "wrong_session": {"session_id": uuid4()},
            }
            if case in changes:
                pause = replace(pause, **changes[case])
            else:
                field = case.removeprefix("wrong_")
                field = {
                    "subject": "subject_id",
                    "policy": "policy_id",
                    "environment": "environment_id",
                    "principal": "principal",
                }[field]
                value = "kl_test_subject_2_login" if field == "principal" else uuid4()
                identity_changes: dict[str, Any] = {field: value}
                pause = replace(pause, identity=replace(pause.identity, **identity_changes))
            cause = (
                "ordinary pause exact lifecycle/revision/current binding mismatch"
                if case in {"wrong_revision", "wrong_binding", "wrong_hash"}
                else "workout_sessions row does not exist"
                if case == "wrong_session"
                else "separately authenticated ordinary pause identity mismatch"
            )
            denied(db, seed, lambda: service(db, seed).pause(pause), cause, "pause-" + case)
            return
        if case == "after_control":
            P.apply_control(db, seed)
        if case == "after_global_revocation":
            P.revoke_runtime(database_urls, seed)
        if case == "generic_patch":
            original_update = RestrictedSqlSession.update

            def generic(self: Any, table: str, values: Any, where: Any) -> Any:
                return original_update(
                    self, table, {**values, "typed_payload": Jsonb({"arbitrary": True})}, where
                )

            monkeypatch.setattr(RestrictedSqlSession, "update", generic)
            denied(
                db,
                seed,
                lambda: service(db, seed).pause(pause),
                "cannot update columns",
                "ordinary-pause-generic-patch-denied",
            )
            return
        if case == "after_expiry":
            P.wait_db_time(db, seed["admission_end"])
        if case == "after_head_change":
            perturb(
                db,
                "UPDATE kineticloop.daily_plan_heads SET current_bundle_revision_id=NULL WHERE subject_id=%s",
                (auth(seed).subject_id,),
            )
        if case.startswith("failure_"):
            original = RestrictedSqlSession.update

            def update(self: Any, table: str, values: Any, where: Any) -> Any:
                value = original(self, table, values, where)
                if table == ("S44" if case == "failure_session" else "S01"):
                    raise ValueError("injected pause rollback")
                return value

            if case != "failure_outcome":
                monkeypatch.setattr(RestrictedSqlSession, "update", update)
            else:
                original_completion = RestrictedSqlSession.validate_completion

                def completion(self: Any) -> None:
                    original_completion(self)
                    raise ValueError("injected pause rollback")

                monkeypatch.setattr(RestrictedSqlSession, "validate_completion", completion)
            denied(
                db, seed, lambda: service(db, seed).pause(pause), "injected pause rollback", case
            )
            return
        before = P.snapshot(db, auth(seed).subject_id)
        traces = []
        original_finish = RepositoryTransaction.finish

        def finish(tx: Any) -> None:
            original_finish(tx)
            if tx.command_kind == "OrdinaryPause":
                traces.append(tx.lock_trace)

        monkeypatch.setattr(RepositoryTransaction, "finish", finish)
        if case == "registry_blocked":
            with connect(database_urls["admin"]) as registry:
                registry.execute(
                    "SELECT id FROM kineticloop.safety_registry_state WHERE id=1 FOR UPDATE"
                ).fetchone()
                started_at = time.monotonic()
                paused = service(db, seed).pause(pause)
                assert time.monotonic() - started_at < 2
        else:
            paused = service(db, seed).pause(pause)
        assert [[int(stage) for stage, _ in trace] for trace in traces] == [[20, 70, 80]]
        after = P.snapshot(db, auth(seed).subject_id)
        assert paused["execution_revision"] == 2 and paused["executable"] is False
        assert_event(db, seed, paused)
        assert current_binding(db, seed, start["session_id"]) == original_start
        for table in before:
            if table not in {
                "workout_sessions",
                "user_decision_state",
                "command_receipts",
                "domain_events",
                "outbox_deliveries",
            }:
                assert before[table] == after[table]
        with db.transaction():
            assert db.execute(
                "SELECT typed_payload->>'reason' FROM kineticloop.domain_events WHERE id=%s",
                (UUID(paused["event_id"]),),
            ).fetchone() == (pause.reason,)
        if case.startswith("after_"):
            from kineticloop.persistence.transactions import query_execution_eligibility

            with db.transaction():
                payload = db.execute(
                    "SELECT typed_payload FROM kineticloop.decision_manifests WHERE id=%s",
                    (UUID(request.command.manifest_id),),
                ).fetchone()[0]
            artifacts = service(db, seed)._artifacts(payload["artifact_closure_ids"])
            eligibility = query_execution_eligibility(
                db,
                command_kind="ResumeSession",
                subject_id=auth(seed).subject_id,
                artifact_ids=[a.artifact_id for a in artifacts],
                artifact_identities=artifacts,
                local_date=P.date.today(),
                session_id=UUID(start["session_id"]),
                prescription_id=UUID(start["prescription_id"]),
                authorization_id=UUID(start["authorization_id"]),
                execution_scope="TEST_ONLY",
            )
            assert not eligibility.is_executable and eligibility.non_bearer
        if case == "duplicate":
            denied(
                db,
                seed,
                lambda: service(db, seed).pause(replace(pause, key=str(uuid4()))),
                "session lifecycle",
                case,
            )
            historical = service(db, seed).pause(pause)
            assert historical["replayed"] and historical["execution_revision"] == 2
            denied(
                db,
                seed,
                lambda: service(db, seed).pause(replace(pause, reason="Changed payload")),
                "request hash mismatch",
                "changed-pause-key",
            )
        P.witness(
            "ordinary_pause",
            case=case,
            result=paused,
            original_binding=original_start,
            no_authority_grant=True,
            no_registry=True,
            lock_traces=traces,
            persisted=after,
        )


@pytest.mark.parametrize("mode", ["CONTINUE", "RESUME", "START"])
@pytest.mark.parametrize("change", ["positive", "STOP", "expiry"])
def test_continue_resume_rechecks(database_urls: Any, mode: str, change: str) -> None:
    seed, request = ready(database_urls, **({"admission_seconds": 8} if change == "expiry" else {}))
    with connect(database_urls["admin"]) as db:
        result = service(db, seed).commit_full(request)
        start_command = session_command(seed, result)
        started = service(db, seed).start(start_command)
        initial_binding = current_binding(db, seed, started["session_id"])
        if mode == "RESUME":
            pause = pause_request(db, seed, started["session_id"])
            service(db, seed).pause(pause)
        else:
            pause = None
        model = {"CONTINUE": ContinueSession, "RESUME": ResumeSession, "START": StartSession}[mode]
        command = session_command(
            seed,
            result,
            model,
            session_id=started["session_id"] if mode != "START" else None,
            binding=initial_binding if mode != "START" else None,
        )
        method: Any = {
            "CONTINUE": service(db, seed).continue_session,
            "RESUME": service(db, seed).resume,
            "START": service(db, seed).start,
        }[mode]
        if change != "positive" and mode in {"CONTINUE", "RESUME"}:
            before_loss = method(command)
            assert before_loss["executable"] and not before_loss["replayed"]
            if mode == "RESUME":
                initial_binding = current_binding(db, seed, started["session_id"])
                service(db, seed).pause(pause_request(db, seed, started["session_id"]))
                command = session_command(
                    seed, result, model, session_id=started["session_id"], binding=initial_binding
                )
            else:
                command = changed(
                    command,
                    command_id=str(uuid4()),
                    action_key=str(uuid4()),
                    idempotency_key=str(uuid4()),
                )
            P.witness(
                "actual_T7_before_authority_loss",
                mode=mode,
                result=before_loss,
                finite_source_end=seed["admission_end"],
                next_key=command.idempotency_key,
            )
        with db.transaction():
            lifecycle = db.execute(
                "SELECT lifecycle FROM kineticloop.workout_sessions WHERE subject_id=%s AND id=%s",
                (auth(seed).subject_id, UUID(started["session_id"])),
            ).fetchone()[0]
            assert lifecycle == ("PAUSED" if mode == "RESUME" else "IN_PROGRESS")
            if mode == "START":
                assert db.execute(
                    "SELECT count(*) FROM kineticloop.workout_sessions WHERE subject_id=%s AND id=%s",
                    (auth(seed).subject_id, UUID(command.session_id)),
                ).fetchone() == (0,)
            manifest_payload = db.execute(
                "SELECT typed_payload FROM kineticloop.decision_manifests WHERE id=%s",
                (UUID(request.command.manifest_id),),
            ).fetchone()[0]
        from kineticloop.persistence.transactions import query_execution_eligibility

        artifacts = service(db, seed)._artifacts(manifest_payload["artifact_closure_ids"])
        eligible = query_execution_eligibility(
            db,
            command_kind="ResumeSession" if mode == "RESUME" else "ContinueSession",
            subject_id=auth(seed).subject_id,
            artifact_ids=[a.artifact_id for a in artifacts],
            artifact_identities=artifacts,
            local_date=P.date.today(),
            session_id=UUID(started["session_id"]),
            prescription_id=UUID(command.prescription_id),
            authorization_id=UUID(command.authorization_id),
            execution_scope="TEST_ONLY",
        )
        assert eligible.is_executable and eligible.non_bearer
        P.witness(
            "lifecycle_current_preconditions",
            mode=mode,
            lifecycle=lifecycle,
            immutable_binding=initial_binding,
            eligibility_observed_at=eligible.observed_at,
            non_bearer=True,
            fresh_key=command.idempotency_key,
            distinct_absent_start=mode == "START",
        )
        if change == "STOP":
            P.apply_control(db, seed)
            with db.transaction():
                epoch = db.execute(
                    "SELECT authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
                    (auth(seed).subject_id,),
                ).fetchone()[0]
            command = changed(command, expected_authorization_epoch=epoch)
            denied(
                db,
                seed,
                lambda: method(command),
                "KL_REGISTRY_AUTHORIZATION_INELIGIBLE",
                mode + "-STOP",
            )
        elif change == "expiry":
            with db.transaction():
                expiry = db.execute(
                    "SELECT valid_until FROM kineticloop.authorization_issuances WHERE id=%s",
                    (UUID(command.authorization_id),),
                ).fetchone()[0]
                assert expiry == seed["admission_end"]
            P.wait_db_time(db, expiry)
            denied(
                db,
                seed,
                lambda: method(command),
                "KL_REGISTRY_AUTHORIZATION_INELIGIBLE",
                mode + "-expiry",
            )
        else:
            before = P.snapshot(db, auth(seed).subject_id)
            output = method(command)
            assert output["executable"] and not output["replayed"]
            assert_event(db, seed, output)
            after = P.snapshot(db, auth(seed).subject_id)
            assert initial_binding in [row[0] for row in after["execution_bindings"]]
            assert len(after["execution_bindings"]) - len(before["execution_bindings"]) == (
                0 if mode == "CONTINUE" else 1
            )
            if mode == "RESUME":
                latest = current_binding(db, seed, started["session_id"])
                assert latest["binding_kind"] == "RESUME" and latest["binding_revision"] == 2
                state = P.snapshot(db, auth(seed).subject_id)
                assert pause is not None
                replay = service(db, seed).pause(pause)
                assert (
                    replay["replayed"]
                    and replay["execution_revision"] == 2
                    and P.snapshot(db, auth(seed).subject_id) == state
                )
            historical = method(command)
            assert historical["replayed"] and not historical["executable"]
            P.witness(
                "current_T7",
                mode=mode,
                start_binding=initial_binding,
                result=output,
                persisted=after,
            )


@pytest.mark.parametrize(
    "case",
    [
        "history",
        "duplicate_commit",
        "member",
        "issuance",
        "head",
        "success",
        "outbox",
        "duplicate_pause",
    ],
)
def test_replay_and_atomicity(
    database_urls: Any, case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed, request = ready(database_urls)
    with connect(database_urls["admin"]) as db:
        if case == "history":
            original = service(db, seed).commit_full(request)
            start = session_command(seed, original)
            started = service(db, seed).start(start)
            P.apply_control(db, seed)
            before = P.snapshot(db, auth(seed).subject_id)
            historical = service(db, seed).commit_full(request)
            assert historical == {**original, "replayed": True, "executable": False}
            assert service(db, seed).start(start) == {
                **started,
                "replayed": True,
                "executable": False,
            }
            assert P.snapshot(db, auth(seed).subject_id) == before
            denied(
                db,
                seed,
                lambda: service(db, seed).commit_full(
                    replace(request, command=changed(request.command, commit_identity=str(uuid4())))
                ),
                "request hash mismatch",
                "changed-commit-key",
            )
            P.witness("historical_non_executable", commit=historical, start=started)
            return
        if case in {"duplicate_commit", "duplicate_pause"}:
            entered, release = Event(), Event()
            if case == "duplicate_pause":
                bundle = service(db, seed).commit_full(request)
                started = service(db, seed).start(session_command(seed, bundle))
                pause = pause_request(db, seed, started["session_id"])
            before = P.snapshot(db, auth(seed).subject_id)
            original_completion = RestrictedSqlSession.validate_completion

            def completion(self: Any) -> None:
                original_completion(self)
                if not entered.is_set():
                    entered.set()
                    assert release.wait(8), "bounded duplicate release missing"

            monkeypatch.setattr(RestrictedSqlSession, "validate_completion", completion)

            def contender(name: str) -> Any:
                with connect(database_urls["admin"], application_name=name) as other:
                    return (
                        service(other, seed).pause(pause)
                        if case == "duplicate_pause"
                        else service(other, seed).commit_full(request)
                    )

            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(contender, "kl077-first")
                try:
                    assert entered.wait(8)
                    second = pool.submit(contender, "kl077-second")
                    blocker = P.observe_blocked(database_urls["admin"], "kl077-second")
                finally:
                    release.set()
                one, two = first.result(timeout=12), second.result(timeout=12)
            assert one["replayed"] is False and two == {
                **one,
                "replayed": True,
                "executable": False,
            }
            after = P.snapshot(db, auth(seed).subject_id)
            assert len(after["command_receipts"]) - len(before["command_receipts"]) == 1
            assert len(after["domain_events"]) - len(before["domain_events"]) == 1
            assert len(after["outbox_deliveries"]) - len(before["outbox_deliveries"]) == 1
            P.witness(
                "observed_duplicate",
                case=case,
                blocker=blocker,
                original=one,
                replay=two,
                persisted=after,
            )
            return
        original_insert = RestrictedSqlSession.insert
        original_update = RestrictedSqlSession.update

        def insert(self: Any, table: str, values: Any) -> Any:
            value = original_insert(self, table, values)
            if (
                case == "member"
                and table == "S40"
                and values.get("prescription_kind") == "NUTRITION"
            ) or (case == "issuance" and table == "S42"):
                raise ValueError("injected full rollback " + case)
            return value

        def update(self: Any, table: str, values: Any, where: Any) -> Any:
            value = original_update(self, table, values, where)
            if (case == "head" and table == "S38") or (case == "success" and table == "S29"):
                raise ValueError("injected full rollback " + case)
            return value

        monkeypatch.setattr(RestrictedSqlSession, "insert", insert)
        monkeypatch.setattr(RestrictedSqlSession, "update", update)
        if case == "outbox":
            original_execute = psycopg.Cursor.execute

            def execute(self: Any, query: Any, *args: Any, **kwargs: Any) -> Any:
                value = original_execute(self, query, *args, **kwargs)
                if isinstance(query, str) and query.startswith(
                    "INSERT INTO kineticloop.outbox_deliveries"
                ):
                    raise ValueError("injected full rollback outbox")
                return value

            monkeypatch.setattr(psycopg.Cursor, "execute", execute)
        denied(
            db, seed, lambda: service(db, seed).commit_full(request), "injected full rollback", case
        )


@pytest.mark.parametrize("operation", ["T6", "START", "CONTINUE", "RESUME"])
def test_trusted_post_lock_expiry(database_urls: Any, operation: str) -> None:
    seed, request = ready(database_urls, admission_seconds=8)
    with connect(database_urls["admin"]) as db:
        if operation == "T6":
            target = UUID(request.command.attempt_id)
            table = "planning_attempts"
        else:
            bundle = service(db, seed).commit_full(request)
            started = service(db, seed).start(session_command(seed, bundle))
            initial = current_binding(db, seed, started["session_id"])
            if operation == "RESUME":
                service(db, seed).pause(pause_request(db, seed, started["session_id"]))
            model = {"START": StartSession, "CONTINUE": ContinueSession, "RESUME": ResumeSession}[
                operation
            ]
            command = session_command(
                seed,
                bundle,
                model,
                session_id=started["session_id"] if operation != "START" else None,
                binding=initial if operation != "START" else None,
            )
            target = UUID(command.session_id)
            # New START has no row to lock: S38 precedes first-use creation and guard.
            table = "daily_plan_heads" if operation == "START" else "workout_sessions"
            if operation == "START":
                target = UUID(bundle["head_id"])
        before = P.snapshot(db, auth(seed).subject_id)
        before_wait = P.wait_db_time(db, seed["admission_end"] - timedelta(seconds=0.5))
        assert before_wait < seed["admission_end"]
        with connect(database_urls["admin"]) as blocker:
            blocker.execute(
                sql.SQL("SELECT id FROM kineticloop.{} WHERE id=%s FOR UPDATE").format(
                    sql.Identifier(table)
                ),
                (target,),
            ).fetchone()

            def waiting() -> str:
                with connect(
                    database_urls["admin"], application_name="kl077-expiry-waiter"
                ) as waiter:
                    method = {
                        "T6": lambda: service(waiter, seed).commit_full(request),
                        "START": lambda: service(waiter, seed).start(command),
                        "CONTINUE": lambda: service(waiter, seed).continue_session(command),
                        "RESUME": lambda: service(waiter, seed).resume(command),
                    }[operation]
                    try:
                        method()
                    except (RepositoryTransactionError, psycopg.Error, ValueError) as error:
                        return str(error)
                    raise AssertionError("expired operation unexpectedly accepted")

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(waiting)
                observed = P.observe_blocked(database_urls["admin"], "kl077-expiry-waiter")
                # Reader is independent of blocked coordination transactions.
                with connect(database_urls["admin"]) as clock:
                    after_time = P.wait_db_time(clock, seed["admission_end"])
                blocker.commit()
                message = future.result(timeout=12)
        assert "expired" in message if operation == "T6" else "TIME_INELIGIBLE" in message, message
        assert P.snapshot(db, auth(seed).subject_id) == before
        P.witness(
            "trusted_post_lock_expiry_DC",
            operation=operation,
            observed_lock=observed,
            source_end=seed["admission_end"],
            trusted_before_wait=before_wait,
            trusted_after=after_time,
            actual_guard=message,
            other_bounds={"manifest_policy": seed["end"], "lease_seconds": 600},
            zero_effects=True,
        )


@pytest.mark.parametrize("case", ["f2", "existing_head"])
def test_full_repair_and_unsupported_replacement(database_urls: Any, case: str) -> None:
    seed, old = ready(database_urls)
    with connect(database_urls["admin"]) as db:
        original = P.snapshot(db, auth(seed).subject_id)
        if case == "existing_head":
            first = service(db, seed).commit_full(old)
        identity = seed["identity"]
        revised = P.LeaseService(
            db, P.PlanningIdentity(identity.actor, identity.subject_id)
        ).admit_or_revise(
            P.AdmitOrReviseIntent(
                identity.subject_id,
                "new-owned-request",
                P.date.today(),
                "TRAINING",
                "test:UTC-v1",
                {"equipment": [], "minutes": 20 if case == "f2" else 30},
            )
        )
        repair_parent = UUID(old.sources["fitness"]["id"])
        if case == "existing_head":
            initial_basis, initial_refs = P.acquired(db, seed, revised)
            initial_operation = P.request(initial_basis, initial_refs, "FITNESS")
            initial_f = P.run(db, seed["identity"], initial_operation)
            P.assert_legacy_output(db, seed, initial_operation, initial_f)
            repair_parent = UUID(initial_f["id"])
            # A new root starts at revision 1. Its actual structured revision 2
            # makes distinct F/D/N parameters without violating S36 natural identity.
            revised = P.LeaseService(
                db, P.PlanningIdentity(identity.actor, identity.subject_id)
            ).admit_or_revise(
                P.AdmitOrReviseIntent(
                    identity.subject_id,
                    "revised-owned-replacement",
                    P.date.today(),
                    "TRAINING",
                    "test:UTC-v1",
                    {"equipment": [], "minutes": 20},
                )
            )
            assert revised["request_revision"] == 2
        if case == "f2":
            assert (
                revised["intent_id"] == old.command.intent_id and revised["request_revision"] == 2
            )
        else:
            assert revised["intent_id"] != old.command.intent_id
        basis, refs = P.acquired(db, seed, revised)
        op, fullrefs = P.preparation_chain(db, seed, basis, refs, repair_parent)
        refs = P.prepare_validation(db, seed, op, fullrefs)
        P.commit_ready(db, seed, op, refs)
        sources = {**refs, "nutrition_resolution": fullrefs["nutrition_resolution"]}
        request = commit_request(db, seed, basis, sources)
        if case == "existing_head":
            denied(
                db,
                seed,
                lambda: service(db, seed).commit_full(request),
                "replacement/reauthorize/fallback/offline modes unsupported",
                case,
            )
            assert (
                P.snapshot(db, identity.subject_id)["daily_bundle_revisions"][0][0]["id"]
                == first["bundle_id"]
            )
        else:
            for name in (
                "fitness",
                "demand",
                "nutrition",
                "resolution",
                "nutrition_resolution",
                "validation",
            ):
                mixed = {k: dict(v) for k, v in request.sources.items()}
                mixed[name] = dict(old.sources[name])
                command = changed(
                    request.command,
                    result_fingerprint=digest({"contract": P.FULL_VERSION, "sources": mixed}),
                    **({"validation_id": mixed[name]["id"]} if name == "validation" else {}),
                )
                denied(
                    db,
                    seed,
                    lambda: service(db, seed).commit_full(FullCommitRequest(command, mixed)),
                    "full exact action binding mismatch"
                    if name == "nutrition_resolution"
                    else "earlier immutable prerequisite",
                    "mixed-F2-" + name,
                )
            result = service(db, seed).commit_full(request)
            after = P.snapshot(db, identity.subject_id)
            for table in (
                "proposal_revisions",
                "prescription_demand_features",
                "evidence_resolutions",
                "validation_results",
            ):
                for row in original[table]:
                    assert row in after[table]
            original_root = original["planning_intents"][0][0]
            root = after["planning_intents"][0][0]
            for field in ("deadline", "typed_payload"):
                assert root[field] == original_root[field]
            P.witness(
                "F2_full_commit",
                old_sources=old.sources,
                new_sources=sources,
                result=result,
                immutable_prior=True,
                same_root_budget=True,
            )


@pytest.mark.parametrize("model", [ContinueSession, ResumeSession])
@pytest.mark.parametrize("error", ["binding", "revision", "content", "prescription"])
def test_exact_session_binding(database_urls: Any, model: Any, error: str) -> None:
    seed, request = ready(database_urls)
    with connect(database_urls["admin"]) as db:
        bundle = service(db, seed).commit_full(request)
        started = service(db, seed).start(session_command(seed, bundle))
        binding = current_binding(db, seed, started["session_id"])
        if model == ResumeSession:
            service(db, seed).pause(pause_request(db, seed, started["session_id"]))
        command = session_command(
            seed,
            bundle,
            model,
            session_id=started["session_id"],
            binding=binding,
            member=1 if error == "prescription" else 0,
        )
        if error == "binding":
            command = changed(
                command,
                **{
                    "current_binding_id" if model == ContinueSession else "prior_binding_id": str(
                        uuid4()
                    )
                },
            )
        elif error == "revision":
            command = changed(command, binding_revision=99)
        elif error == "content":
            command = changed(command, content_hash=digest("wrong"))
        method = (
            service(db, seed).continue_session
            if model == ContinueSession
            else service(db, seed).resume
        )
        cause = (
            "exact latest immutable session binding required"
            if error == "binding" or (error == "prescription" and model == ResumeSession)
            else "session/binding expectation mismatch"
            if error == "revision"
            else "exact content/closure expectation mismatch"
            if error == "content"
            else "SESSION_RELATION_INELIGIBLE"
        )
        denied(
            db,
            seed,
            lambda: method(command),
            cause,
            "typed-session-" + model.__name__ + "-" + error,
        )


@pytest.mark.parametrize("shorten", [False, True])
def test_full_server_validity(database_urls: Any, shorten: bool) -> None:
    seed, request = ready(database_urls)
    with connect(database_urls["admin"]) as db:
        with db.transaction():
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        requested = now + timedelta(seconds=15 if shorten else 36000)
        result = service(db, seed).commit_full(request, requested_valid_until=requested)
        with db.transaction():
            rows = db.execute(
                "SELECT valid_from,valid_until,validity_certificate FROM kineticloop.authorization_issuances WHERE subject_id=%s ORDER BY id",
                (auth(seed).subject_id,),
            ).fetchall()
        assert len(rows) == 2 and rows[0][:2] == rows[1][:2]
        assert all(row[1] == requested if shorten else row[1] < requested for row in rows)
        for start, end, certificate in rows:
            ends = [
                P.datetime.fromisoformat(d["valid_until"])
                for d in certificate["dependencies"]
                if d.get("valid_until") is not None
            ]
            assert end == min(ends) and end > start
            assert any(d["identity"] == str(seed["admission"]) for d in certificate["dependencies"])
        P.witness(
            "server_full_validity",
            shorten=shorten,
            requested=requested,
            rows=rows,
            result=result,
            caller_cannot_extend=True,
        )
