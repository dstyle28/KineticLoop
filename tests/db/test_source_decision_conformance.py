from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from kineticloop.contracts.commands import (
    CommitBundle,
    ContinueSession,
    ResumeSession,
    StartSession,
)
from kineticloop.persistence.protocol_execution import ProtocolExecutionService
from kineticloop.persistence.transactions import (
    GuardRequired,
    RepositoryTransaction,
    RestrictedSqlSession,
    _cursor,
    _read_full_source_freshness,
)
from kineticloop.protocol.execution import (
    ExecutionIdentity,
    FullCommitRequest,
    command_digest,
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


N = load("kl080_namespace", "tests/unit/workflow/test_source_decision_conformance.py")
E = load("kl080_execution_builders", "tests/db/test_full_test_execution.py")
P = E.P
L = load("kl080_legacy_builders", "tests/db/test_deterministic_planning.py")
M = E.M


GUARD_TRACE: list[dict[str, Any]] = []


def witness(kind: str, **data: Any) -> None:
    if kind.startswith("kl080_") or kind in {
        "exact_zero_effect_denial",
        "F2_full_commit",
        "observed_duplicate",
        "historical_non_executable",
        "current_T7",
    }:
        print(
            "SOURCE_EVIDENCE "
            + json.dumps(
                {"kind": kind, **data, "guard_trace": list(GUARD_TRACE)},
                sort_keys=True,
                default=str,
            ),
            flush=True,
        )


P.witness = L.witness = witness

PG_CONNECT = psycopg.connect
TABLES = tuple(
    dict.fromkeys(
        (
            *P.TABLES,
            "evidence_revisions",
            "candidate_assertions",
            "underlying_events",
            "event_association_decisions",
            "admission_decisions",
            "canonical_fact_revisions",
        )
    )
)


def connect(url: str = "", **kwargs: Any) -> Any:
    expected = N.fixture_namespace(ROOT, P.current_head())
    actual = kwargs.get("dbname") or urlparse(url).path.removeprefix("/")
    if actual != expected.database_name:
        raise ValueError("foreign/default KL080 database URL")
    kwargs.setdefault("options", "-c statement_timeout=12000 -c lock_timeout=10000")
    db = PG_CONNECT(url, **kwargs)
    with db.transaction():
        assert db.execute("SELECT current_database()").fetchone() == (expected.database_name,)
    return db


E.connect = P.connect = L.connect = connect
E.P.TABLES = L.TABLES = TABLES


@pytest.fixture
def database_urls() -> Any:
    # Preflight precedes even bootstrap; no imported pytest lifecycle is invoked.
    N.test_namespace(ROOT / "foreign-peer-root")
    lifecycle = N.OwnedLifecycle(ROOT, P.current_head())
    selected = lifecycle.namespace
    original_connect = psycopg.connect
    original_timezone = os.environ.get("TZ")
    # Immutable builders use date.today(); their registered test calendar is UTC.
    # Align this fixture process with that actual calendar, without changing its clock.
    os.environ["TZ"] = "UTC"
    time.tzset()
    setattr(psycopg, "connect", connect)
    try:
        urls = lifecycle.bootstrap(M.bootstrap_two_phase)
        with connect(urls["admin"]) as db:
            assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
                M.HEAD_REVISION,
            )
        P.witness(
            "kl080_namespace",
            tested_commit=P.current_head(),
            root=str(ROOT.resolve()),
            compose=selected.project_name,
            database=selected.database_name,
            migration=M.HEAD_REVISION,
            nested_bootstrap="selected lifecycle",
            calendar_timezone="UTC",
        )
        yield urls
    finally:
        setattr(psycopg, "connect", original_connect)
        try:
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
                "kl080_cleanup",
                compose=selected.project_name,
                database=selected.database_name,
                inventory=lifecycle.inventory,
                remaining=remaining,
            )
        finally:
            if original_timezone is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_timezone
            time.tzset()


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
    deadline_seconds: int = 3600,
    full: bool = True,
    fact_changes: Any = None,
    config_changes: Any = None,
    admission_value: Any = "ELIGIBLE",
    association_value: Any = "MATCHED",
    scope: str = "TEST_ONLY",
    provenance: str = "USER_REPORTED",
    extra_fact_changes: Any = None,
    corrupt_admission_hash: bool = False,
    corrupt_association_hash: bool = False,
    wrong_source_policy: bool = False,
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
    extra_fact = uuid4() if extra_fact_changes is not None else None
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
        if extra_fact:
            config["required_members"].append(str(extra_fact))
            config["required_members"].sort()
        if full:
            config.update(contract=P.FULL_VERSION, required_actions=["TRAINING", "NUTRITION"])
        config.update(config_changes or {})
        runtime_version = P.FULL_VERSION if full else P.VERSION
        runtime_hash = (
            digest({"version": P.FULL_VERSION, "rules": P.RULES}) if full else digest(P.RULES)
        )
        deps: tuple[Any, ...] = (
            P.Dependency("COLLECTION", "fixture-facts", "all-fixture-facts-and-absence:v1"),
            P.Dependency("ENGINE", f"test:kl079-engine-{subject}:1"),
            P.Dependency("FACTSET", "sealed-input"),
            P.Dependency("POLICY", "selected-policy"),
            P.Dependency("PROGRAM", "selected-program"),
            P.Dependency("FACT", "actual-member", fact_id=fact),
        )
        if extra_fact:
            deps += (P.Dependency("FACT", "duplicate-event-fact", fact_id=extra_fact),)
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
                "deadline_seconds": deadline_seconds,
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
        source_policy = policy_id
        if wrong_source_policy:
            source_policy = uuid4()
            db.execute(
                "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) VALUES (%s,%s,'test:kl080-other-policy','1',%s,%s)",
                (source_policy, subject, digest(body), Jsonb(body)),
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
            "INSERT INTO kineticloop.evidence_revisions(id,subject_id,source_connection_identity,source_object_type,source_object_identity,source_revision,trust_class,source_class,command_authority) VALUES (%s,%s,'kl079-test','actual','fixture-actual','1',%s,'USER','NONE')",
            (evidence, subject, provenance),
        )
        db.execute(
            "INSERT INTO kineticloop.candidate_assertions(id,subject_id,assertion_family_identity,ref_s09_id) VALUES (%s,%s,'fixture-actual',%s)",
            (assertion, subject, evidence),
        )
        db.execute(
            "INSERT INTO kineticloop.underlying_events(id,subject_id,event_identity) VALUES (%s,%s,'fixture-actual-event')",
            (event, subject),
        )
        assoc_body = {"fixture_association": association_value, "event_id": str(event)}
        db.execute(
            "INSERT INTO kineticloop.event_association_decisions(id,subject_id,association_family_identity,association_state,ref_s11_id,content_hash,typed_payload) VALUES (%s,%s,'fixture-event',%s,%s,%s,%s)",
            (
                association,
                subject,
                association_value,
                event,
                digest("wrong-source-hash") if corrupt_association_hash else digest(assoc_body),
                Jsonb(assoc_body),
            ),
        )
        admission_body = {
            "fixture_admission": admission_value,
            "valid_until": admission_end.isoformat(),
        }
        db.execute(
            "INSERT INTO kineticloop.admission_decisions(id,subject_id,action_scope,decision,ref_s05_id,ref_s09_id,ref_s10_id,content_hash,typed_payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                admission,
                subject,
                scope,
                admission_value,
                source_policy,
                evidence,
                assertion,
                digest("wrong-source-hash") if corrupt_admission_hash else digest(admission_body),
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
        "extra_fact": extra_fact,
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
        if extra_fact:
            P.actual_input(db, {**seed, "fact_changes": extra_fact_changes}, extra_fact)
    return seed


def upstream_with_duplicate(db: Any, seed: Any, key: str = "source") -> Any:
    identity = seed["identity"]
    subject = identity.subject_id
    cv = P.CanonicalViewService(db, P.BuilderIdentity(identity.actor, subject))
    with db.transaction():
        frontier, epoch = db.execute(
            "SELECT input_frontier_hash,authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (subject,),
        ).fetchone()
    factset_id = UUID(
        cv.begin_build(
            P.BeginBuild(
                subject,
                key,
                frontier,
                epoch,
                seed["program"],
                identity.policy_id,
                P.EvidenceBasis(
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
    members: tuple[Any, ...] = (
        P.Member("ASSOCIATION", "fixture-event", "TEST_ONLY", seed["association"]),
        P.Member("ADMISSION", "fixture-admitted", "TEST_ONLY", seed["admission"]),
        P.Member("FACT", "fixture-actual", "TEST_ONLY", seed["fact"]),
    )
    members += (P.Member("FACT", "second-actual-same-event", "TEST_ONLY", seed["extra_fact"]),)
    members += tuple(
        P.Member("FACT", f"extra-fixture-{i}", "TEST_ONLY", seed["fact"])
        for i in range(seed.get("extra_members", 0))
    )
    for n, member in enumerate(members):
        cv.write_candidate(P.WriteCandidate(subject, f"member-{n}", factset_id, n, member))
    complete = cv.complete_factset(P.CompleteFactset(subject, "complete", factset_id, len(members)))
    cv.seal_factset(P.SealFactset(subject, "seal", factset_id, complete))
    ingress = P.PreparationService(
        db,
        ExecutionIdentity(
            identity.actor, subject, identity.policy_id, identity.environment_id, identity.principal
        ),
    )
    source = ingress.capture_source(factset_id)
    projection = ingress.record_projection(
        P.RecordProjection(
            source,
            "EXPOSURE",
            seed["engine"],
            tuple(seed["policy"]["deterministic_fixture"]["window"]),
            {
                "actual_minutes_lower": 10,
                "actual_minutes_upper": 10,
                "dedup_event_ids": [str(seed["event"])],
                "semantic_class": "ACTUAL_EXECUTION",
                "source_fact_ids": [str(seed["fact"]), str(seed["extra_fact"])],
            },
            seed["deps"],
            seed["end"],
        )
    )
    request = P.BuildManifest(
        "build",
        source,
        (P.ProjectionBinding("EXPOSURE", UUID(projection["projection_id"])),),
        (seed["engine"].artifact_id,),
    )
    build = ingress.build_manifest(request)
    ready = ingress.complete_manifest(P.CompleteManifest(UUID(build["build_id"])))
    result = P.publish(db, seed, source, ready, "publish")
    seed.update(source=source, projection=projection, ready=ready, manifest=result)
    P.witness(
        "upstream",
        subject=subject,
        factset=factset_id,
        membership_digest=complete["membership_digest"],
        projection=projection,
        ready=ready,
        publication=result,
        epoch=source.epoch,
    )
    return result


def ready(urls: Any, **kwargs: Any) -> tuple[Any, Any]:
    seed = seed_source(urls, **kwargs)
    with connect(urls["admin"]) as db:
        P.upstream(db, seed)
        basis, refs = P.begin(db, seed)
        op, fullrefs = P.preparation_chain(db, seed, basis, refs)
        refs = P.prepare_validation(db, seed, op, fullrefs)
        P.commit_ready(db, seed, op, refs)
        sources = {**refs, "nutrition_resolution": fullrefs["nutrition_resolution"]}
        request = E.commit_request(db, seed, basis, sources)
    return seed, request


def legacy_commit_request(db: Any, seed: Any, basis: Any, sources: Any) -> Any:
    with db.transaction():
        manifest, generation, epoch, execution = db.execute(
            "SELECT current_manifest_id,decision_generation,authorization_epoch,execution_basis_event_id "
            "FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (basis.subject_id,),
        ).fetchone()
        closure = db.execute(
            "SELECT typed_payload->>'artifact_dependency_closure_hash' FROM kineticloop.decision_manifests WHERE id=%s",
            (manifest,),
        ).fetchone()[0]
    seed.update(basis=basis, refs=sources)
    return E.N.wire(
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
        result_fingerprint=digest(
            {
                "proposal_id": sources["nutrition"]["id"],
                "proposal_hash": sources["nutrition"]["hash"],
                "validation_id": sources["validation"]["id"],
            }
        ),
    )


def source_rows(db: Any, seed: Any) -> Any:
    rows = P.snapshot(db, auth(seed).subject_id)
    assert rows["admission_decisions"][0][0]["decision"] == "ELIGIBLE"
    assert rows["event_association_decisions"][0][0]["association_state"] == "MATCHED"
    assert all(row["command_authority"] == "NONE" for (row,) in rows["evidence_revisions"])
    for table in ("admission_decisions", "event_association_decisions", "canonical_fact_revisions"):
        for (row,) in rows[table]:
            assert digest(row["typed_payload"]) == row["content_hash"]
    return rows


def duplicate_preparation_chain(db: Any, seed: Any, basis: Any, refs: Any) -> Any:
    """Own two-fact verifier; imported fixture assertions retain their original scope."""
    basis, refs = P.fdn(db, seed, basis, refs)
    resolutions = {}
    for action, name in (("TRAINING", "resolution"), ("NUTRITION", "nutrition_resolution")):
        operation = P.full_request(db, basis, refs, "RESOLUTION", action)
        output = P.run(db, seed["identity"], operation)
        assert_duplicate_resolution(db, seed, operation, output)
        resolutions[name] = {"id": output["id"], "hash": output["hash"]}
    refs = {**refs, **resolutions}
    return P.full_request(db, basis, refs, "VALIDATION"), refs


def assert_duplicate_resolution(db: Any, seed: Any, operation: Any, output: Any) -> None:
    with db.transaction():
        row = db.execute(
            "SELECT to_jsonb(t) FROM kineticloop.evidence_resolutions t WHERE subject_id=%s AND id=%s",
            (operation.subject_id, UUID(output["id"])),
        ).fetchone()[0]
        receipt = db.execute(
            "SELECT id,typed_payload FROM kineticloop.command_receipts WHERE subject_id=%s AND actor_scope=%s AND command_kind=%s AND client_key=%s",
            (
                operation.subject_id,
                seed["identity"].key,
                P.OWNERS[operation.kind][0],
                operation.key,
            ),
        ).fetchone()
        events = db.execute(
            "SELECT id,typed_payload FROM kineticloop.domain_events WHERE ref_s02_id=%s",
            (receipt[0],),
        ).fetchall()
        assert len(events) == 1
        accepted = datetime.fromisoformat(events[0][1]["guard_accepted_at"])
        before, after = P.CALL_BOUNDS[output["id"]]
        assert before <= accepted <= after
        assert db.execute(
            "SELECT count(*) FROM kineticloop.outbox_deliveries WHERE ref_s03_id=%s",
            (events[0][0],),
        ).fetchone() == (1,)
        assert row["content_hash"] == digest(row["typed_payload"]) == output["hash"]
        assert receipt[1]["outcome"]["id"] == output["id"]
        assert receipt[1]["outcome"]["executable"] is False
        assert [item[0] for item in output["lock_trace"]] == [20, 40, 80, 90]
        artifact = P.FullResolution.model_validate_json(json.dumps(row["typed_payload"]))
        assert artifact.contract == P.FULL_VERSION
        assert artifact.snapshot_id == operation.sources["snapshot"]["id"]
        assert row["action_type"] == operation.action_type == artifact.action_type
        assert (
            row["query_basis_hash"]
            == artifact.query_basis_hash
            == P.full_query_basis(artifact.payload())
        )
        assert row["action_parameters_hash"] == operation.action_parameters_hash
        assert row["ref_s24_id"] == str(operation.manifest_id)
        assert row["ref_s05_id"] == str(seed["identity"].policy_id)
        assert artifact.source_members == tuple(
            sorted(
                map(str, (seed["fact"], seed["extra_fact"], seed["association"], seed["admission"]))
            )
        )
        assert len(artifact.facts) == 2
        assert {fact.fact_id for fact in artifact.facts} == {
            str(seed["fact"]),
            str(seed["extra_fact"]),
        }
        assert all(fact.semantic_class == "ACTUAL_EXECUTION" for fact in artifact.facts)
        assert all(fact.admission == "ELIGIBLE" for fact in artifact.facts)
        assert all(fact.association == "MATCHED" for fact in artifact.facts)
        assert {fact.event_id for fact in artifact.facts} == {str(seed["event"])}
        assert artifact.supporting_events == (str(seed["event"]),)
        assert row["resolver_version"] == P.FULL_VERSION
        assert datetime.fromisoformat(row["resolution_expires_at"]) == datetime.fromisoformat(
            artifact.resolution_expires_at
        )
        P.witness(
            "kl080_duplicate_resolution",
            receipt=receipt[0],
            event=events[0][0],
            accepted_at=accepted,
            columns=row,
        )


@pytest.mark.parametrize("full", [False, True], ids=["legacy", "full"])
@pytest.mark.parametrize("duplicate", [False, True], ids=["single-event", "duplicate-event"])
def test_preparation_owners(database_urls: Any, full: bool, duplicate: bool) -> None:
    seed = seed_source(database_urls, full=full, extra_fact_changes={} if duplicate else None)
    with connect(database_urls["admin"]) as db:
        upstream_with_duplicate(db, seed) if duplicate else P.upstream(db, seed)
        basis, refs = P.begin(db, seed)
        if full:
            op, fullrefs = (
                duplicate_preparation_chain(db, seed, basis, refs)
                if duplicate
                else P.preparation_chain(db, seed, basis, refs)
            )
            refs = P.prepare_validation(db, seed, op, fullrefs)
            P.commit_ready(db, seed, op, refs)
        else:
            op, refs = L.full_pipeline(db, seed, basis, refs)
        rows = source_rows(db, seed)
        assert rows["planning_intents"][0][0]["status"] == "RUNNING"
        assert rows["planning_attempts"][0][0]["status"] == "COMMIT_READY"
        assert len(rows["evidence_resolutions"]) == (2 if full else 1)
        for (row,) in rows["evidence_resolutions"]:
            assert row["typed_payload"]["event_association_status"] == "CONFIRMED"
            assert row["typed_payload"]["facts"][0]["admission_id"] == str(seed["admission"])
        assert rows["validation_results"][0][0]["valid_until"] is not None
        assert rows["validation_results"][0][0]["typed_payload"]["rolling_minutes"] == 40
        assert len(rows["canonical_fact_revisions"]) == (2 if duplicate else 1)
        assert rows["validation_results"][0][0]["typed_payload"]["deduplicated_events"] == [
            str(seed["event"])
        ]
        P.assert_no_execution(db, auth(seed).subject_id)
        P.witness("kl080_preparation_owner", full=full, refs=refs, persisted=rows)


def test_canonical_full_t6(database_urls: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import kineticloop.persistence.transactions as transactions

    seen = []
    original = transactions._read_full_source_freshness

    def observe(cursor: Any, subject: Any, admission: Any, policy: Any) -> Any:
        row = original(cursor, subject, admission, policy)
        seen.append((str(subject), str(admission), str(policy), row))
        return row

    seed, request = ready(database_urls, admission_seconds=180)
    monkeypatch.setattr(transactions, "_read_full_source_freshness", observe)
    with connect(database_urls["admin"]) as db:
        before = source_rows(db, seed)
        result = service(db, seed).commit_full(request)
        after = source_rows(db, seed)
        assert seen and all(x[1] == str(seed["admission"]) and x[3] for x in seen)
        assert len(result["members"]) == len(after["authorization_issuances"]) == 2
        admission = before["admission_decisions"][0][0]
        for (row,) in after["authorization_issuances"]:
            certificate = row["validity_certificate"]
            sources = [
                d
                for d in certificate["dependencies"]
                if d["dependency_kind"] == "EVIDENCE_ADMISSION_FRESHNESS"
            ]
            assert len(sources) == 1
            assert sources[0]["identity"] == admission["id"]
            assert sources[0]["revision"] == admission["revision"]
            assert datetime.fromisoformat(sources[0]["valid_until"]) == seed["admission_end"]
            assert datetime.fromisoformat(row["valid_until"]) == min(
                datetime.fromisoformat(d["valid_until"])
                for d in certificate["dependencies"]
                if d.get("valid_until")
            )
            assert str(row["ref_s37_id"]) == request.sources["validation"]["id"]
            assert str(row["ref_s36_id"]) in {
                request.sources[k]["id"] for k in ("resolution", "nutrition_resolution")
            }
        for table in (
            "admission_decisions",
            "event_association_decisions",
            "canonical_fact_revisions",
            "evidence_resolutions",
            "validation_results",
        ):
            assert before[table] == after[table]
        E.assert_event(db, seed, result)
        P.witness(
            "kl080_canonical_full_t6_exact_freshness_reached",
            reached=seen,
            request=request.command.model_dump(mode="json"),
            persisted=after,
            result=result,
        )


def test_invalid_source_reconstruction(
    database_urls: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The protected deployment accepted precisely this pair. It runs unchanged in
    # a separate process; current guards are never patched or bypassed.
    revision = N.BASE_COMMIT
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, "HEAD"], cwd=ROOT, check=False
        ).returncode
        == 0
    )
    paths = [
        "src",
        "tests/db/test_full_test_execution.py",
        "tests/db/test_full_action_preparation.py",
        "tests/db/test_migrations.py",
        "tests/unit/protocol/test_full_test_execution.py",
        "tests/unit/workflow/test_full_action_preparation.py",
    ]
    archive = subprocess.check_output(["git", "archive", revision, *paths], cwd=ROOT)
    deployment = tmp_path / "prior-deployment"
    deployment.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(deployment, filter="data")
    verification = {}
    files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", revision, *paths], cwd=ROOT, text=True
    ).splitlines()
    for path in files:
        expected = subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT)
        assert (deployment / path).read_bytes() == expected
        verification[path] = hashlib.sha256(expected).hexdigest()
    script = r"""
import importlib.util,json,sys
from pathlib import Path
import psycopg
from urllib.parse import urlparse
root=Path(sys.argv[1]); current=Path(sys.argv[2]); urls=json.loads(sys.stdin.readline()); expected=sys.argv[3]
raw_connect=psycopg.connect
connections=[]
def connect(url='',**kwargs):
    assert (kwargs.get('dbname') or urlparse(url).path.removeprefix('/'))==expected
    db=raw_connect(url,**kwargs)
    with db.transaction(): assert db.execute('SELECT current_database()').fetchone()==(expected,)
    connections.append(expected)
    return db
psycopg.connect=connect
spec=importlib.util.spec_from_file_location('prior_owner',root/'tests/db/test_full_test_execution.py')
e=importlib.util.module_from_spec(spec);sys.modules[spec.name]=e;spec.loader.exec_module(e)
e.connect=e.P.connect=connect
e.ROOT=e.P.ROOT=current
seed,request=e.ready(urls)
identity=seed['identity']
with connect(urls['admin']) as db:
    assert db.execute('SELECT status FROM kineticloop.planning_attempts WHERE id=%s',
                     (seed['basis'].attempt_id,)).fetchone()==('COMMIT_READY',)
    assert db.execute('SELECT count(*) FROM kineticloop.authorization_issuances WHERE subject_id=%s',
                     (identity.subject_id,)).fetchone()==(0,)
result={'command':request.command.model_dump(mode='json'),'sources':request.sources,
        'identity': {'actor_id':identity.actor.identity_id,'subject_id':str(identity.subject_id),
          'policy_id':str(identity.policy_id),'environment_id':str(identity.environment_id),
          'principal':identity.principal},'connection_databases':connections}
print('PRIOR_OWNER_REQUEST '+json.dumps(result,sort_keys=True))
"""
    env = {**os.environ, "PYTHONPATH": str(deployment / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    expected_db = N.fixture_namespace(ROOT, P.current_head()).database_name
    child = subprocess.run(
        [sys.executable, "-c", script, str(deployment), str(ROOT), expected_db],
        input=json.dumps(database_urls) + "\n",
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
    )
    assert child.returncode == 0, child.stderr + child.stdout[-2500:]
    line = next(x for x in child.stdout.splitlines() if x.startswith("PRIOR_OWNER_REQUEST "))
    captured = json.loads(line.removeprefix("PRIOR_OWNER_REQUEST "))
    i = captured["identity"]
    seed = {
        "identity": P.ProgressIdentity(
            P.RoleIdentity(i["actor_id"], P.ActorRole.TEST),
            UUID(i["subject_id"]),
            UUID(i["policy_id"]),
            UUID(i["environment_id"]),
            i["principal"],
        )
    }
    request = FullCommitRequest(
        CommitBundle.model_validate_json(json.dumps(captured["command"])), captured["sources"]
    )
    import kineticloop.persistence.deterministic_planning as preparation
    import kineticloop.persistence.transactions as transactions

    reached = []
    original = preparation._verify_full_progress

    def reconstruction(*args: Any, **kwargs: Any) -> Any:
        reached.append("_progress_sources -> _verify_full_progress")
        return original(*args, **kwargs)

    monkeypatch.setattr(preparation, "_verify_full_progress", reconstruction)
    freshness = transactions._read_full_source_freshness

    def observe(*args: Any, **kwargs: Any) -> Any:
        reached.append("later freshness predicate")
        return freshness(*args, **kwargs)

    monkeypatch.setattr(transactions, "_read_full_source_freshness", observe)
    with connect(database_urls["admin"]) as db:
        before = P.snapshot(db, auth(seed).subject_id)
        assert before["admission_decisions"][0][0]["decision"] == "ADMITTED"
        assert before["event_association_decisions"][0][0]["association_state"] == "CONFIRMED"
        E.denied(
            db,
            seed,
            lambda: service(db, seed).commit_full(request),
            "declared admitted actual fixture evidence required",
            "earlier-source-reconstruction",
        )
        assert reached == ["_progress_sources -> _verify_full_progress"]
        assert P.snapshot(db, auth(seed).subject_id) == before
        P.witness(
            "kl080_prior_deployment_earlier_denial",
            protected_revision=revision,
            verified_blobs=verification,
            child_connection_databases=captured["connection_databases"],
            untouched_request=captured["command"],
            sources=request.sources,
            reached=reached,
            no_later_freshness_claim=True,
            immutable_rows=before,
        )


@pytest.mark.parametrize(
    "decision", ["ELIGIBLE", "NOT_ELIGIBLE", "UNRESOLVED", "ADMITTED", "ACCEPTED", "unknown", None]
)
def test_freshness_predicate_support(database_urls: Any, decision: Any) -> None:
    # Independently inserted immutable inputs only. This is query support, never
    # an end-to-end operation or a bypass around reconstruction.
    seed = seed_source(database_urls, admission_value=decision)
    with connect(database_urls["admin"]) as db:
        before = P.snapshot(db, auth(seed).subject_id)
        with db.transaction(), db.cursor() as cursor:
            exact = _read_full_source_freshness(
                cursor, auth(seed).subject_id, seed["admission"], auth(seed).policy_id
            )
            assert bool(exact) == (decision == "ELIGIBLE")
            for subject, admission, policy in (
                (uuid4(), seed["admission"], auth(seed).policy_id),
                (auth(seed).subject_id, uuid4(), auth(seed).policy_id),
                (auth(seed).subject_id, seed["admission"], uuid4()),
            ):
                assert _read_full_source_freshness(cursor, subject, admission, policy) is None
        assert P.snapshot(db, auth(seed).subject_id) == before
        P.witness(
            "kl080_exact_predicate_support_only",
            decision=decision,
            exact=exact,
            independent_source=before,
            wrong_subject_policy_id_denied=True,
            end_to_end_claim=False,
        )


def assert_mechanical_consumer_denial(
    db: Any, seed: Any, request: CommitBundle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Consume the untouched S37 at the actual dependency guard, never a construction error."""
    assert type(request) is CommitBundle
    auth(seed).require_wire(request)
    assert request.request_hash == command_digest(request)
    prepared = source_rows(db, seed)
    basis, refs = seed["basis"], seed["refs"]
    validation = prepared["validation_results"][0][0]
    demand = prepared["prescription_demand_features"][0][0]
    nutrition = next(
        row for (row,) in prepared["proposal_revisions"] if row["id"] == refs["nutrition"]["id"]
    )
    assert validation["result"] == "PASS"
    assert validation["id"] == request.validation_id == refs["validation"]["id"]
    assert validation["ref_s34_id"] == nutrition["id"]
    assert demand["ref_s34_id"] == refs["fitness"]["id"] != nutrition["id"]
    assert validation["ref_s35_id"] == demand["id"] == nutrition["demand_feature_id"]
    assert (
        digest(validation["typed_payload"])
        == validation["content_hash"]
        == refs["validation"]["hash"]
    )
    assert request.result_fingerprint == digest(
        {
            "proposal_id": nutrition["id"],
            "proposal_hash": nutrition["content_hash"],
            "validation_id": validation["id"],
        }
    )
    assert prepared["planning_attempts"][0][0]["status"] == "COMMIT_READY"
    assert prepared["planning_intents"][0][0]["status"] == "RUNNING"
    P.assert_no_execution(db, auth(seed).subject_id)
    untouched_wire = request.model_dump(mode="json")
    original = RepositoryTransaction.prepare_authorization_basis
    consumed = []

    def observe(tx: Any, **kwargs: Any) -> Any:
        # This is the current owner's native transaction: the first-use head is
        # visible here and must disappear when the actual guard aborts it.
        cursor = _cursor(tx)
        cursor.execute(
            "SELECT to_jsonb(h) FROM kineticloop.daily_plan_heads h WHERE subject_id=%s AND id=%s",
            (auth(seed).subject_id, kwargs["head_id"]),
        )
        head_row = cursor.fetchone()
        assert head_row is not None
        first_head = head_row[0]
        assert first_head["current_bundle_revision_id"] is None
        assert first_head["head_revision"] == 0
        assert kwargs["validation_id"] == UUID(validation["id"])
        assert kwargs["resolution_id"] == UUID(validation["ref_s36_id"])
        assert kwargs["intent_id"] == basis.intent_id
        record = {
            "guard": "prepare_authorization_basis",
            "first_use_head": first_head,
            "untouched_validation": validation,
            "status": "ENTERED",
        }
        consumed.append(record)
        try:
            return original(tx, **kwargs)
        except GuardRequired as error:
            record.update(status="DENIED", cause=str(error))
            raise

    monkeypatch.setattr(RepositoryTransaction, "prepare_authorization_basis", observe)
    cause = "policy, demand, and calendar authorization bounds must exist"
    with pytest.raises(GuardRequired, match=cause):
        service(db, seed).commit(request)
    assert len(consumed) == 1 and consumed[0]["status"] == "DENIED"
    trace = [r for r in GUARD_TRACE if r["command"] == "CommitBundle"]
    for guard in ("require_test_execution_ingress", "require_current_fence", "lock_daily_head"):
        assert any(r["guard"] == guard and r["status"] == "PASSED" for r in trace)
    assert any(
        r["guard"] == "prepare_authorization_basis"
        and r["status"] == "DENIED"
        and r["cause"] == cause
        for r in trace
    )
    assert not any(r["guard"] == "require_execution_request" for r in trace)
    after = P.snapshot(db, auth(seed).subject_id)
    assert after == prepared
    assert request.model_dump(mode="json") == untouched_wire
    P.assert_no_execution(db, auth(seed).subject_id)
    P.witness(
        "kl080_mechanical_s37_legacy_consumer_denial",
        command=untouched_wire,
        actual_cause=cause,
        reached=consumed,
        before=prepared,
        after=after,
        first_use_head_observed_then_rolled_back=True,
        no_construction_or_ingress_error=True,
        no_later_certificate_guard_claim=True,
    )


@pytest.mark.parametrize("full", [False, True], ids=["legacy", "full-fdn"])
def test_owner_trajectories(
    database_urls: Any, full: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    if full:
        seed, request = ready(database_urls)
    else:
        seed = seed_source(database_urls, full=False)
        with connect(database_urls["admin"]) as db:
            P.upstream(db, seed)
            basis, refs = P.begin(db, seed)
            _, refs = L.full_pipeline(db, seed, basis, refs)
            seed["basis"] = basis
            request = legacy_commit_request(db, seed, basis, refs)
    with connect(database_urls["admin"]) as db:
        if not full:
            assert_mechanical_consumer_denial(db, seed, request, monkeypatch)
            return
        before = source_rows(db, seed)
        result = service(db, seed).commit_full(request)
        assert {m["action_type"] for m in result["members"]} == {"TRAINING", "NUTRITION"}
        E.assert_event(db, seed, result)
        for member in range(2):
            expected = result["members"][member]
            started = service(db, seed).start(E.session_command(seed, result, member=member))
            assert started["executable"]
            E.assert_event(db, seed, started)
            original = E.current_binding(db, seed, started["session_id"])
            assert (
                original["ref_s40_id"],
                original["ref_s42_id"],
                original["ref_s44_id"],
                original["execution_scope"],
                original["binding_kind"],
                original["binding_revision"],
            ) == (
                expected["prescription_id"],
                expected["authorization_id"],
                started["session_id"],
                "TEST_ONLY",
                "START",
                1,
            )
            paused = service(db, seed).pause(E.pause_request(db, seed, started["session_id"]))
            assert paused["executable"] is False
            E.assert_event(db, seed, paused)
            resumed = service(db, seed).resume(
                E.session_command(
                    seed,
                    result,
                    ResumeSession,
                    session_id=started["session_id"],
                    binding=original,
                    member=member,
                )
            )
            assert resumed["executable"]
            E.assert_event(db, seed, resumed)
            binding = E.current_binding(db, seed, started["session_id"])
            assert (
                binding["ref_s40_id"],
                binding["ref_s42_id"],
                binding["ref_s44_id"],
                binding["execution_scope"],
                binding["binding_kind"],
                binding["binding_revision"],
            ) == (
                expected["prescription_id"],
                expected["authorization_id"],
                started["session_id"],
                "TEST_ONLY",
                "RESUME",
                2,
            )
            continued = service(db, seed).continue_session(
                E.session_command(
                    seed,
                    result,
                    ContinueSession,
                    session_id=started["session_id"],
                    binding=binding,
                    member=member,
                )
            )
            assert continued["executable"]
            E.assert_event(db, seed, continued)
            assert E.current_binding(db, seed, started["session_id"]) == binding
        after = source_rows(db, seed)
        for table in (
            "admission_decisions",
            "event_association_decisions",
            "canonical_fact_revisions",
            "evidence_revisions",
            "candidate_assertions",
            "underlying_events",
            "proposal_revisions",
            "prescription_demand_features",
            "decision_snapshots",
            "decision_manifests",
            "evidence_resolutions",
            "validation_results",
        ):
            assert before[table] == after[table]
        # Concrete non-executable peer namespaces, with no source or target outputs seeded.
        peers = []
        with connect(database_urls["admin"], autocommit=True) as admin:
            for namespace, principal, environment in (
                ("PRODUCTION", "kl_production_subject_1_login", None),
                ("EVALUATION", "kl_evaluation_subject_1_login", uuid4()),
            ):
                peer = uuid4()
                admin.execute(
                    "INSERT INTO kineticloop.user_decision_state(subject_id,input_frontier_hash) VALUES (%s,%s)",
                    (peer, digest("kl080-non-executable-" + str(peer))),
                )
                peers.append((peer, namespace, principal, environment))
        with connect(database_urls["trusted_admin"], autocommit=True) as trusted:
            for peer, namespace, principal, environment in peers:
                trusted.execute(
                    "SELECT kineticloop.subject_scope_register(%s,%s,NULL,%s,%s)",
                    (peer, namespace, environment, principal),
                )
        with db.transaction():
            for table in ("daily_plan_heads", "authorization_issuances", "execution_bindings"):
                for peer, _, _, _ in peers:
                    assert db.execute(
                        "SELECT count(*) FROM kineticloop." + table + " WHERE subject_id=%s",
                        (peer,),
                    ).fetchone() == (0,)
            assert db.execute(
                "SELECT count(*) FROM kineticloop.daily_plan_heads h "
                "JOIN kineticloop.subject_scopes s ON s.subject_id=h.subject_id WHERE s.namespace <> 'TEST'"
            ).fetchone() == (0,)
            assert db.execute(
                "SELECT count(*) FROM kineticloop.authorization_issuances a "
                "JOIN kineticloop.subject_scopes s ON s.subject_id=a.subject_id WHERE s.namespace <> 'TEST'"
            ).fetchone() == (0,)
        P.witness("kl080_owner_trajectory", full=full, result=result, persisted=after)


changed = E.changed
perturb = E.perturb
denied = E.denied
session_command = E.session_command
current_binding = E.current_binding
pause_request = E.pause_request
commit_request = E.commit_request
assert_event = E.assert_event


@pytest.mark.parametrize(
    "case",
    [
        "request_revision",
        "source_legacy_dedup_conflict",
        "source_legacy_admission_hash",
        "source_legacy_association_hash",
        "source_legacy_source_policy",
        "source_legacy_association_id",
        "source_legacy_unknown_association",
        "source_legacy_NOT_ELIGIBLE",
        "source_legacy_UNRESOLVED",
        "source_legacy_ADMITTED",
        "source_legacy_ACCEPTED",
        "source_legacy_unknown",
        "source_legacy_null_admission",
        "source_legacy_AMBIGUOUS",
        "source_legacy_RETRACTED",
        "source_legacy_CONFIRMED",
        "source_legacy_null_association",
        "source_legacy_scope",
        "source_legacy_provenance",
        "source_legacy_target",
        "source_legacy_unknown_actual",
        "source_legacy_contradiction",
        "source_legacy_retraction",
        "source_legacy_membership",
        "source_legacy_hash",
        "source_full_dedup_conflict",
        "source_full_admission_hash",
        "source_full_association_hash",
        "source_full_source_policy",
        "source_full_association_id",
        "source_full_unknown_association",
        "source_full_NOT_ELIGIBLE",
        "source_full_UNRESOLVED",
        "source_full_ADMITTED",
        "source_full_ACCEPTED",
        "source_full_unknown",
        "source_full_null_admission",
        "source_full_AMBIGUOUS",
        "source_full_RETRACTED",
        "source_full_CONFIRMED",
        "source_full_null_association",
        "source_full_scope",
        "source_full_provenance",
        "source_full_target",
        "source_full_unknown_actual",
        "source_full_contradiction",
        "source_full_retraction",
        "source_full_membership",
        "source_full_hash",
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
def test_current_denials(database_urls: Any, case: str) -> None:
    if case.startswith("source_"):
        _, profile, source_case = case.split("_", 2)
        source_preparation_denial(database_urls, source_case, profile == "full")
        return
    seed, request = ready(
        database_urls, **({"admission_seconds": 8} if case == "resolution_expiry" else {})
    )
    with connect(database_urls["admin"]) as db:
        command = request.command
        cause = ""

        def operation() -> Any:
            return service(db, seed).commit_full(request)

        if case == "request_revision":
            identity = seed["identity"]
            revised = P.LeaseService(
                db, P.PlanningIdentity(identity.actor, identity.subject_id)
            ).admit_or_revise(
                P.AdmitOrReviseIntent(
                    identity.subject_id,
                    "new-current-revision",
                    P.date.today(),
                    "TRAINING",
                    "test:UTC-v1",
                    {"equipment": [], "minutes": 20},
                )
            )
            assert (
                revised["intent_id"] == request.command.intent_id
                and revised["request_revision"] == 2
            )
            cause = "stale owner/fence"
        elif case == "legacy_downgrade":

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
            observed = P.wait_db_time(db, seed["admission_end"])
            P.witness(
                "kl080_trusted_clock_crossing",
                bound=seed["admission_end"],
                observed=observed,
                equality_claim=False,
            )
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


def source_preparation_denial(database_urls: Any, case: str, full: bool) -> None:
    values: dict[str, Any] = {"full": full}
    if case in ("NOT_ELIGIBLE", "UNRESOLVED", "ADMITTED", "ACCEPTED", "unknown", "null_admission"):
        values["admission_value"] = None if case == "null_admission" else case
    elif case in ("AMBIGUOUS", "RETRACTED", "CONFIRMED", "null_association"):
        values["association_value"] = None if case == "null_association" else case
    elif case == "unknown_association":
        values["association_value"] = "unknown"
    elif case == "scope":
        values["scope"] = "EXECUTION"
    elif case == "provenance":
        values["provenance"] = "PROVIDER_REPORTED"
    elif case == "target":
        values["fact_changes"] = {"semantic_class": "TARGET"}
    elif case == "unknown_actual":
        values["fact_changes"] = {"upper_minutes": None}
    elif case == "contradiction":
        values["fact_changes"] = {"contradicts": True}
    elif case == "retraction":
        values["fact_changes"] = {"retracted": True}
    elif case == "dedup_conflict":
        values["extra_fact_changes"] = {"lower_minutes": 11, "upper_minutes": 11}
    elif case == "admission_hash":
        values["corrupt_admission_hash"] = True
    elif case == "association_hash":
        values["corrupt_association_hash"] = True
    elif case == "source_policy":
        values["wrong_source_policy"] = True
    elif case == "association_id":
        values["fact_changes"] = {"association_id": str(uuid4())}
    elif case == "membership":
        values["config_changes"] = {"required_members": [str(uuid4())]}
    seed = seed_source(database_urls, **values)
    with connect(database_urls["admin"]) as db:
        upstream_with_duplicate(db, seed) if seed.get("extra_fact") else P.upstream(db, seed)
        basis, refs = P.begin(db, seed)
        if case == "hash":
            refs = {**refs, "snapshot": {**refs["snapshot"], "hash": digest("wrong")}}
        before = P.snapshot(db, auth(seed).subject_id)
        with pytest.raises((ValueError, psycopg.Error, RuntimeError)) as error:
            if full:
                op, fullrefs = P.preparation_chain(db, seed, basis, refs)
                P.prepare_validation(db, seed, op, fullrefs)
            else:
                L.full_pipeline(db, seed, basis, refs)
        after = P.snapshot(db, auth(seed).subject_id)
        # Earlier successful owners may append before a later validation denial.
        # The failed command itself is checked with the exact snapshot below via
        # the owner-call wrapper; immutable inputs never change.
        for table in (
            "admission_decisions",
            "event_association_decisions",
            "canonical_fact_revisions",
        ):
            assert before[table] == after[table]
        P.assert_no_execution(db, auth(seed).subject_id)
        P.witness(
            "kl080_source_preparation_denial",
            full=full,
            case=case,
            cause=str(error.value),
            persisted=after,
        )


@pytest.fixture(autouse=True)
def failed_owner_zero_effects(monkeypatch: pytest.MonkeyPatch) -> Any:
    GUARD_TRACE.clear()
    for name in (
        "require_test_execution_ingress",
        "require_current_fence",
        "lock_daily_head",
        "prepare_authorization_basis",
        "_progress_sources",
        "_prepare_full_execution",
        "require_execution_request",
        "require_execution_authorization",
    ):
        original_guard = getattr(RepositoryTransaction, name)

        def trace(
            tx: Any, *args: Any, _guard: Any = original_guard, _name: str = name, **kwargs: Any
        ) -> Any:
            record = {
                "guard": _name,
                "command": tx.command_kind,
                "subject": str(tx.subject_id),
                "status": "ENTERED",
            }
            GUARD_TRACE.append(record)
            try:
                result = _guard(tx, *args, **kwargs)
            except Exception as error:
                record.update(status="DENIED", cause=str(error))
                raise
            record["status"] = "PASSED"
            return result

        monkeypatch.setattr(RepositoryTransaction, name, trace)
    for module in (P, L):
        original = module.run

        def wrap(db: Any, identity: Any, operation: Any, _original: Any = original) -> Any:
            before = P.snapshot(db, identity.subject_id)
            try:
                return _original(db, identity, operation)
            except Exception:
                assert P.snapshot(db, identity.subject_id) == before
                P.witness(
                    "kl080_failed_owner_zero_effects",
                    output_kind=operation.kind,
                    subject=identity.subject_id,
                    before=before,
                )
                raise

        monkeypatch.setattr(module, "run", wrap)
    yield


def repair_f2(database_urls: Any) -> None:
    case = "f2"
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


@pytest.mark.parametrize(
    "case",
    [
        "source_input_invalidation",
        "runtime_revocation",
        "expiry_START",
        "expiry_CONTINUE",
        "expiry_RESUME",
        "f2",
        "history",
        "duplicate_commit",
        "duplicate_pause",
        "member",
        "issuance",
        "head",
        "success",
        "outbox",
    ],
)
def test_repair_replay_expiry(
    database_urls: Any, case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if case in {"source_input_invalidation", "runtime_revocation"}:
        seed, request = ready(database_urls)
        with connect(database_urls["admin"]) as db:
            result = service(db, seed).commit_full(request)
            start = session_command(seed, result)
            started = service(db, seed).start(start)
            immutable = P.snapshot(db, auth(seed).subject_id)
            if case == "source_input_invalidation":
                L.actual_input(db, seed, uuid4())
                cause = "KL_REGISTRY_AUTHORIZATION_INELIGIBLE"
            else:
                P.revoke_runtime(database_urls, seed)
                cause = "KL_REGISTRY_ARTIFACT_REVOKED"
            before = P.snapshot(db, auth(seed).subject_id)
            assert service(db, seed).commit_full(request) == {
                **result,
                "replayed": True,
                "executable": False,
            }
            assert service(db, seed).start(start) == {
                **started,
                "replayed": True,
                "executable": False,
            }
            binding = current_binding(db, seed, started["session_id"])
            continuation = session_command(
                seed, result, ContinueSession, session_id=started["session_id"], binding=binding
            )
            denied(db, seed, lambda: service(db, seed).continue_session(continuation), cause, case)
            assert P.snapshot(db, auth(seed).subject_id) == before
            for table in (
                "admission_decisions",
                "event_association_decisions",
                "canonical_fact_revisions",
                "proposal_revisions",
                "prescription_demand_features",
                "evidence_resolutions",
                "validation_results",
            ):
                assert all(row in before[table] for row in immutable[table])
            P.witness(
                "kl080_source_or_runtime_loss_and_receipt_only_replay",
                case=case,
                invalidation_owner="RecordActualExecution"
                if case == "source_input_invalidation"
                else "SafetyRegistry.RevokeArtifact",
                persisted=before,
            )
        return
    if case.startswith("expiry_"):
        current_execution_authority(database_urls, case.removeprefix("expiry_"), "expiry")
        return
    if case == "f2":
        repair_f2(database_urls)
        return
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


def current_execution_authority(database_urls: Any, mode: str, change: str) -> None:
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
            observed = P.wait_db_time(db, expiry)
            P.witness(
                "kl080_trusted_clock_crossing",
                bound=expiry,
                observed=observed,
                equality_claim=False,
            )
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
