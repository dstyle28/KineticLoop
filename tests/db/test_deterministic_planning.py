from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
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

import kineticloop.persistence.deterministic_planning as preparation
from kineticloop.identity import ActorRole, RoleIdentity
from kineticloop.persistence.factsets import (
    BeginBuild,
    BuilderIdentity,
    CanonicalViewService,
    CompleteFactset,
    SealFactset,
    WriteCandidate,
)
from kineticloop.persistence.planning import AcquireLease, AdmitOrReviseIntent, PlanningIdentity
from kineticloop.persistence.planning import PlanningWorkflowService as LeaseService
from kineticloop.persistence.planning_progress import (
    ContextService,
    PlanningWorkflowService,
    capture_context,
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
    RepositoryTransaction,
    RepositoryTransactionError,
    RestrictedSqlSession,
    execute_command,
    execute_preparation,
)
from kineticloop.protocol.execution import ExecutionIdentity, PublishReady
from kineticloop.protocol.factsets import EvidenceBasis, Member
from kineticloop.workflow.deterministic_planning import OWNERS, RULES, VERSION, PreparationRequest
from kineticloop.workflow.planning import PlanningDenied, digest
from kineticloop.workflow.planning_progress import (
    POLICY_BLOCKS,
    AdvanceAttempt,
    ProgressBasis,
    ProgressIdentity,
    RecordSnapshot,
)

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: str) -> Any:
    spec = spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Only the selected-lifecycle migration bootstrap is imported; no foreign fixture runs.
_MIGRATIONS = load("kl076_migrations", "tests/db/test_migrations.py")
_NAMESPACE = load("kl076_namespace", "tests/unit/workflow/test_deterministic_planning.py")
KINDS = tuple(OWNERS)
CALL_BOUNDS: dict[str, tuple[datetime, datetime]] = {}
TABLES = (
    "user_decision_state",
    "command_receipts",
    "domain_events",
    "outbox_deliveries",
    "factset_revisions",
    "factset_members",
    "projection_versions",
    "projection_dependencies",
    "manifest_builds",
    "decision_manifests",
    "manifest_projection_bindings",
    "decision_snapshots",
    "planning_intents",
    "planning_request_revisions",
    "planning_attempts",
    "proposal_revisions",
    "prescription_demand_features",
    "evidence_resolutions",
    "validation_results",
    "daily_plan_heads",
    "daily_bundle_revisions",
    "prescription_revisions",
    "bundle_prescription_members",
    "authorization_issuances",
    "execution_bindings",
    "workout_sessions",
)


def witness(kind: str, **data: Any) -> None:
    print(
        "FIXTURE_EVIDENCE " + json.dumps({"kind": kind, **data}, sort_keys=True, default=str),
        flush=True,
    )


def current_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def connect(url: str, **kwargs: Any) -> Any:
    expected = _NAMESPACE.fixture_namespace(ROOT, current_head())
    if urlparse(url).path != "/" + expected.database_name:
        raise ValueError("foreign/default KL076 database URL")
    connection = psycopg.connect(
        url, options="-c statement_timeout=12000 -c lock_timeout=10000", **kwargs
    )
    with connection.transaction():
        database_row = connection.execute("SELECT current_database()").fetchone()
        assert database_row is not None and database_row[0] == expected.database_name
    return connection


@pytest.fixture
def database_urls() -> Iterator[dict[str, str]]:
    _NAMESPACE.test_namespace(
        Path("/private/tmp/kl076-peer-root")
        if sys.platform == "darwin"
        else Path("/tmp/kl076-peer-root")
    )
    head = current_head()
    lifecycle = _NAMESPACE.OwnedLifecycle(ROOT, head)
    selected = lifecycle.namespace
    started = time.monotonic()
    try:
        urls = lifecycle.bootstrap(_MIGRATIONS.bootstrap_two_phase)
        with connect(urls["admin"]) as db:
            migration_row = db.execute("SELECT version_num FROM alembic_version").fetchone()
            assert migration_row is not None
            migration = migration_row[0]
        assert migration == _MIGRATIONS.HEAD_REVISION
        witness(
            "namespace",
            tested_commit=head,
            resolved_root=str(ROOT),
            compose=selected.project_name,
            database=selected.database_name,
            migration=migration,
            bootstrap_elapsed=time.monotonic() - started,
            nested_routes=[
                "bootstrap_two_phase(selected_lifecycle)",
                "reset",
                "start",
                "compose/_run",
                "validate_current_database_before_every_source/owner/reset",
                "finally_destroy",
            ],
        )
        yield urls
    finally:
        lifecycle.validate_target()
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
        witness(
            "cleanup",
            compose=selected.project_name,
            database=selected.database_name,
            inventory=lifecycle.inventory,
            remaining_resources=remaining,
            elapsed=time.monotonic() - started,
        )


def seed_source(urls: dict[str, str], *, seconds: float = 3600) -> dict[str, Any]:
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
    actor = RoleIdentity(str(uuid4()), ActorRole.TEST)
    identity = ProgressIdentity(actor, subject, policy_id, environment, "kl_test_subject_1_login")
    with connect(urls["admin"], autocommit=True) as db:
        clock = db.execute("SELECT clock_timestamp()").fetchone()
        assert clock is not None
        now = clock[0]
        end = now + timedelta(seconds=seconds)
        config = {
            "rules": copy.deepcopy(RULES),
            "window": [(now - timedelta(days=1)).isoformat(), end.isoformat()],
            "required_members": sorted(map(str, (association, admission, fact))),
            "reservations": {"prior-slot": 50},
            "valid_until": end.isoformat(),
        }
        deps = (
            Dependency("COLLECTION", "fixture-facts", "all-fixture-facts-and-absence:v1"),
            Dependency("ENGINE", f"test:kl076-engine-{subject}:1"),
            Dependency("FACTSET", "sealed-input"),
            Dependency("POLICY", "selected-policy"),
            Dependency("PROGRAM", "selected-program"),
            Dependency("FACT", "actual-member", fact_id=fact),
        )
        body = {
            "deterministic_fixture": config,
            "fixture_runtime": {"id": str(runtime), "hash": digest(RULES), "version": VERSION},
            "factset_max_delta_depth": 1,
            "planning_context": {
                block: {
                    "status": "TEST_INPUT_ONLY",
                    "value": [str(fact)] if block == "recent_execution" else [],
                }
                for block in POLICY_BLOCKS
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
        db.execute(
            "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) VALUES (%s,%s,'test:kl076','1',%s,%s)",
            (policy_id, subject, digest(body), Jsonb(body)),
        )
        db.execute(
            "INSERT INTO kineticloop.program_versions(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test:kl076',1)",
            (program, subject),
        )
        db.execute(
            "INSERT INTO kineticloop.user_decision_state(subject_id,input_frontier_hash,active_policy_bundle_id,active_program_id) VALUES (%s,%s,%s,%s)",
            (subject, digest("registered-source"), policy_id, program),
        )
        db.execute(
            "INSERT INTO kineticloop.evidence_revisions(id,subject_id,source_connection_identity,source_object_type,source_object_identity,source_revision,trust_class,source_class,command_authority) VALUES (%s,%s,'kl076-test','actual','fixture-actual','1','USER_REPORTED','USER','NONE')",
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
        assoc_body = {"fixture_association": "MATCHED", "event_id": str(event)}
        db.execute(
            "INSERT INTO kineticloop.event_association_decisions(id,subject_id,association_family_identity,association_state,ref_s11_id,content_hash,typed_payload) VALUES (%s,%s,'fixture-event','MATCHED',%s,%s,%s)",
            (association, subject, event, digest(assoc_body), Jsonb(assoc_body)),
        )
        admission_body = {"fixture_admission": "ELIGIBLE", "valid_until": end.isoformat()}
        db.execute(
            "INSERT INTO kineticloop.admission_decisions(id,subject_id,action_scope,decision,ref_s05_id,ref_s09_id,ref_s10_id,content_hash,typed_payload) VALUES (%s,%s,'TEST_ONLY','ELIGIBLE',%s,%s,%s,%s,%s)",
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
            "INSERT INTO kineticloop.evaluation_releases(id,subject_id,release_namespace,release_version,content_hash) VALUES (%s,%s,'test:kl076','1',%s)",
            (release, subject, digest("fixture-release")),
        )
        for artifact, kind, name, version, artifact_hash, payload, policy_ref, release_ref in (
            (
                engine,
                "POLICY_BUNDLE",
                f"test:kl076-engine-{subject}",
                "1",
                digest(body),
                {},
                policy_id,
                None,
            ),
            (
                runtime,
                "RUNTIME",
                f"test:kl076-runtime-{subject}",
                VERSION,
                digest(RULES),
                {"operation": "DETERMINISTIC_TEST_PREPARATION", "version": VERSION},
                None,
                release,
            ),
            (
                builder,
                "RUNTIME",
                f"test:kl076-builder-{subject}",
                "1",
                digest("context-builder"),
                {"operation": "CONTEXT_BUILDER"},
                None,
                release,
            ),
            (
                release_artifact,
                "PROMPT",
                f"test:kl076-release-{subject}",
                "1",
                digest("fixture-release"),
                {},
                None,
                release,
            ),
        ):
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
        for dependency in (runtime, builder, release_artifact):
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
        "now": now,
        "builder": builder,
        "deps": deps,
        "fact": fact,
        "association": association,
        "admission": admission,
        "assertion": assertion,
        "event": event,
        "engine": ArtifactIdentity(
            engine, "POLICY_BUNDLE", f"test:kl076-engine-{subject}", "1", digest(body)
        ),
    }
    # Actual T2 owner creates the canonical actual fact AND its execution-basis event.
    with connect(urls["admin"]) as db:
        actual_input(db, seed, fact)
    return seed


def actual_input(db: Any, seed: dict[str, Any], fact: UUID) -> Any:
    subject = seed["identity"].subject_id
    receipt_id = uuid4()
    event = EventWrite(
        event_id=uuid4(),
        aggregate_type="FIXTURE_ACTUAL",
        aggregate_identity=str(fact),
        event_type="RecordActualExecution",
        aggregate_revision=1,
        outbox_id=uuid4(),
        destination="evidence",
    )
    payload = {
        "exercise": "fixture:cycle",
        "semantic_class": "ACTUAL_EXECUTION",
        "lower_minutes": 10,
        "upper_minutes": 10,
        "contradicts": False,
        "replaces_slot": "prior-slot",
        "retracted": False,
        "association_id": str(seed["association"]),
    }

    def operation(tx: RepositoryTransaction) -> Any:
        tx.lock_subject()
        epoch = tx._coordination_context["authorization_epoch"]

        def write(session: RestrictedSqlSession) -> Any:
            session.insert(
                "S14",
                {
                    "id": fact,
                    "subject_id": subject,
                    "stable_fact_identity": str(fact),
                    "fact_kind": "WORKOUT_ACTUAL",
                    "fact_revision": 1,
                    "ref_s10_id": seed["assertion"],
                    "ref_s11_id": seed["event"],
                    "ref_s13_id": seed["admission"],
                    "content_hash": digest(payload),
                    "effective_at": seed["now"] - timedelta(hours=1),
                    "typed_payload": Jsonb(payload),
                },
            )
            session.insert(
                "S43",
                {
                    "id": uuid4(),
                    "subject_id": subject,
                    "event_kind": "EPOCH_INVALIDATED",
                    "scope": "TEST_ONLY",
                    "causation_key": str(fact),
                    "invalidated_epoch": epoch + 1,
                    "ref_s02_id": receipt_id,
                },
            )
            session.update(
                "S01",
                {"authorization_epoch": epoch + 1, "execution_basis_event_id": event.event_id},
                {"subject_id": subject},
            )
            return {"fact_id": str(fact), "event_id": str(event.event_id)}

        return tx.idempotent_outcome(
            receipt_id=receipt_id,
            actor_scope=seed["identity"].key,
            client_key=str(fact),
            request_hash=digest(payload),
            mutation=write,
            event=event,
            invalidation_scope="TEST_ONLY",
        )[0]

    return execute_command(db, "RecordActualExecution", subject, operation)


def upstream(db: Any, seed: dict[str, Any], key: str = "source") -> dict[str, Any]:
    identity = seed["identity"]
    subject = identity.subject_id
    cv = CanonicalViewService(db, BuilderIdentity(identity.actor, subject))
    with db.transaction():
        frontier, epoch = db.execute(
            "SELECT input_frontier_hash,authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (subject,),
        ).fetchone()
    factset_id = UUID(
        cv.begin_build(
            BeginBuild(
                subject,
                key,
                frontier,
                epoch,
                seed["program"],
                identity.policy_id,
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
        Member("ASSOCIATION", "fixture-event", "TEST_ONLY", seed["association"]),
        Member("ADMISSION", "fixture-admitted", "TEST_ONLY", seed["admission"]),
        Member("FACT", "fixture-actual", "TEST_ONLY", seed["fact"]),
    )
    for n, member in enumerate(members):
        cv.write_candidate(WriteCandidate(subject, f"member-{n}", factset_id, n, member))
    complete = cv.complete_factset(CompleteFactset(subject, "complete", factset_id, 3))
    cv.seal_factset(SealFactset(subject, "seal", factset_id, complete))
    ingress = PreparationService(
        db,
        ExecutionIdentity(
            identity.actor, subject, identity.policy_id, identity.environment_id, identity.principal
        ),
    )
    source = ingress.capture_source(factset_id)
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
    request = BuildManifest(
        "build",
        source,
        (ProjectionBinding("EXPOSURE", UUID(projection["projection_id"])),),
        (seed["engine"].artifact_id,),
    )
    build = ingress.build_manifest(request)
    ready = ingress.complete_manifest(CompleteManifest(UUID(build["build_id"])))
    result = publish(db, seed, source, ready, "publish")
    seed.update(source=source, projection=projection, ready=ready, manifest=result)
    witness(
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


def publish(db: Any, seed: dict[str, Any], source: Any, ready: Any, key: str) -> Any:
    identity = seed["identity"]
    return ProtocolExecutionService(
        db,
        ExecutionIdentity(
            identity.actor,
            identity.subject_id,
            identity.policy_id,
            identity.environment_id,
            identity.principal,
        ),
    ).publish(
        PublishReady(
            identity.subject_id,
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
    )


def advance(
    db: Any,
    identity: ProgressIdentity,
    basis: ProgressBasis,
    target: str,
    refs: Mapping[str, Mapping[str, str]],
    failure: str | None = None,
) -> Any:
    return PlanningWorkflowService(db, identity).advance_attempt(
        AdvanceAttempt(**asdict(basis), target_state=target, sources=refs, failure_code=failure)
    )


def acquired(
    db: Any, seed: dict[str, Any], admitted: Any, *, lease_seconds: int = 600
) -> tuple[ProgressBasis, dict[str, Any]]:
    identity = seed["identity"]
    service = LeaseService(db, PlanningIdentity(identity.actor, identity.subject_id))
    with db.transaction():
        owner, fence = db.execute(
            "SELECT lease_owner,fence_token FROM kineticloop.planning_intents WHERE id=%s",
            (UUID(admitted["intent_id"]),),
        ).fetchone()
    leased = service.acquire_lease(
        AcquireLease(
            identity.subject_id,
            "lease-" + admitted["attempt_id"],
            UUID(admitted["intent_id"]),
            owner,
            fence,
            admitted["request_revision"],
            UUID(admitted["attempt_id"]),
            lease_seconds,
        )
    )
    basis = ProgressBasis(
        subject_id=identity.subject_id,
        key="stage-" + admitted["attempt_id"],
        intent_id=UUID(admitted["intent_id"]),
        request_id=UUID(admitted["request_id"]),
        request_revision=admitted["request_revision"],
        attempt_id=UUID(admitted["attempt_id"]),
        expected_owner=identity.key,
        fence=leased["fence"],
        manifest_id=UUID(seed["manifest"]["manifest_id"]),
        epoch=seed["source"].epoch,
        source_state="CREATED",
    )
    advance(db, identity, basis, "LEASED", {})
    basis = replace(basis, key=basis.key + "-context", source_state="LEASED")
    advance(db, identity, basis, "BUILDING_CONTEXT", {})
    basis = replace(basis, key=basis.key + "-snapshot", source_state="BUILDING_CONTEXT")
    captured = capture_context(db, basis, seed["builder"])
    snapshot = ContextService(db, identity).record_snapshot(
        RecordSnapshot(**asdict(basis), builder_id=seed["builder"], **captured)
    )
    refs = {"snapshot": {"id": snapshot["snapshot_id"], "hash": captured["context_hash"]}}
    advance(db, identity, replace(basis, key=basis.key + "-fitness"), "FITNESS", refs)
    return replace(basis, source_state="FITNESS"), refs


def begin(
    db: Any, seed: dict[str, Any], *, lease_seconds: int = 600
) -> tuple[ProgressBasis, dict[str, Any]]:
    identity = seed["identity"]
    service = LeaseService(db, PlanningIdentity(identity.actor, identity.subject_id))
    admitted = service.admit_or_revise(
        AdmitOrReviseIntent(
            identity.subject_id,
            "admit",
            date.today(),
            "TRAINING",
            "test:UTC-v1",
            {"equipment": [], "minutes": 30},
        )
    )
    return acquired(db, seed, admitted, lease_seconds=lease_seconds)


def request(
    basis: ProgressBasis,
    refs: Any,
    kind: str,
    *,
    parent: UUID | None = None,
    key: str | None = None,
) -> PreparationRequest:
    return PreparationRequest(
        **{**asdict(basis), "key": key or (kind + "-" + str(basis.attempt_id))},
        kind=kind,
        sources=copy.deepcopy(refs),
        parent_id=parent,
    )


def run(db: Any, identity: ProgressIdentity, operation: PreparationRequest) -> Any:
    classes = {
        "FITNESS": (preparation.ProposalService, "record_proposal"),
        "NUTRITION": (preparation.ProposalService, "record_proposal"),
        "DEMAND": (preparation.DemandFeatureService, "record_demand_features"),
        "RESOLUTION": (preparation.EvidenceResolver, "resolve_evidence"),
        "VALIDATION": (preparation.ValidationService, "record_validation"),
    }
    owner, method = classes[operation.kind]
    with db.transaction():
        before = db.execute("SELECT clock_timestamp()").fetchone()[0]
    output = getattr(owner(db, identity), method)(operation)
    with db.transaction():
        after = db.execute("SELECT clock_timestamp()").fetchone()[0]
    old = CALL_BOUNDS.get(output["id"], (before, after))
    CALL_BOUNDS[output["id"]] = (min(before, old[0]), max(after, old[1]))
    return output


def until(
    db: Any,
    seed: dict[str, Any],
    basis: ProgressBasis,
    refs: Any,
    kind: str,
    *,
    parent: UUID | None = None,
) -> tuple[PreparationRequest, Any]:
    for current in KINDS:
        operation = request(basis, refs, current, parent=parent if current == "FITNESS" else None)
        if current == kind:
            return operation, refs
        output = run(db, seed["identity"], operation)
        refs = {
            **refs,
            {
                "FITNESS": "fitness",
                "DEMAND": "demand",
                "NUTRITION": "nutrition",
                "RESOLUTION": "resolution",
            }[current]: {"id": output["id"], "hash": output["hash"]},
        }
        if current in {"FITNESS", "DEMAND", "NUTRITION"}:
            target = {
                "FITNESS": "DEMAND_FEATURES",
                "DEMAND": "NUTRITION",
                "NUTRITION": "VALIDATING",
            }[current]
            advance(
                db, seed["identity"], replace(basis, key="advance-" + output["id"]), target, refs
            )
            basis = replace(basis, source_state=target)
    raise AssertionError(kind)


def snapshot(db: Any, subject: UUID) -> Any:
    with db.transaction():
        result = {}
        for table in TABLES:
            result[table] = db.execute(
                sql.SQL(
                    "SELECT to_jsonb(t) FROM kineticloop.{} t WHERE subject_id=%s ORDER BY to_jsonb(t)::text"
                ).format(sql.Identifier(table)),
                (subject,),
            ).fetchall()
    return result


def assert_no_execution(db: Any, subject: UUID) -> None:
    with db.transaction():
        for table in (
            "daily_plan_heads",
            "daily_bundle_revisions",
            "prescription_revisions",
            "bundle_prescription_members",
            "authorization_issuances",
            "execution_bindings",
            "workout_sessions",
        ):
            assert db.execute(
                sql.SQL("SELECT count(*) FROM kineticloop.{} WHERE subject_id=%s").format(
                    sql.Identifier(table)
                ),
                (subject,),
            ).fetchone() == (0,)
        assert db.execute(
            "SELECT status,result_bundle_revision_id,result_authorization_id FROM kineticloop.planning_intents WHERE subject_id=%s",
            (subject,),
        ).fetchone() == ("RUNNING", None, None)


def assert_output(db: Any, seed: dict[str, Any], operation: PreparationRequest, output: Any) -> Any:
    from kineticloop.workflow.deterministic_planning import (
        Demand,
        Fitness,
        Nutrition,
        Resolution,
        Validation,
        compute_demand,
        compute_nutrition,
        validate,
    )

    table = {
        "S34": "proposal_revisions",
        "S35": "prescription_demand_features",
        "S36": "evidence_resolutions",
        "S37": "validation_results",
    }[OWNERS[operation.kind][1]]
    with db.transaction():
        row = db.execute(
            sql.SQL(
                "SELECT to_jsonb(t) FROM kineticloop.{} t WHERE subject_id=%s AND id=%s"
            ).format(sql.Identifier(table)),
            (operation.subject_id, UUID(output["id"])),
        ).fetchone()[0]
        receipt = db.execute(
            "SELECT id,typed_payload FROM kineticloop.command_receipts WHERE subject_id=%s AND actor_scope=%s AND command_kind=%s AND client_key=%s",
            (operation.subject_id, seed["identity"].key, OWNERS[operation.kind][0], operation.key),
        ).fetchone()
        events = db.execute(
            "SELECT id,typed_payload FROM kineticloop.domain_events WHERE subject_id=%s AND ref_s02_id=%s",
            (operation.subject_id, receipt[0]),
        ).fetchall()
        assert len(events) == 1 and "guard_accepted_at" in events[0][1]
        accepted = datetime.fromisoformat(events[0][1]["guard_accepted_at"])
        before, after = CALL_BOUNDS[output["id"]]
        assert before <= accepted <= after
        assert db.execute(
            "SELECT count(*) FROM kineticloop.outbox_deliveries WHERE ref_s03_id=%s",
            (events[0][0],),
        ).fetchone() == (1,)
        assert row["content_hash"] == digest(row["typed_payload"]) == output["hash"]
        assert (
            receipt[1]["outcome"]["id"] == output["id"]
            and receipt[1]["outcome"]["executable"] is False
        )
        assert [s[0] for s in output["lock_trace"]] == [20, 40, 80, 90]
        assert row["typed_payload"]["snapshot_id"] == operation.sources["snapshot"]["id"]
        assert row["typed_payload"]["attempt_id"] == str(operation.attempt_id)
        assert row["typed_payload"]["manifest_id"] == str(operation.manifest_id)
        if operation.kind in {"FITNESS", "NUTRITION"}:
            assert row["revision"] == operation.request_revision and row["ref_s29_id"] == str(
                operation.attempt_id
            )
        models: Any = {
            "FITNESS": Fitness,
            "DEMAND": Demand,
            "NUTRITION": Nutrition,
            "RESOLUTION": Resolution,
            "VALIDATION": Validation,
        }
        artifact = models[operation.kind].model_validate_json(json.dumps(row["typed_payload"]))
        if operation.kind in {"DEMAND", "NUTRITION", "RESOLUTION", "VALIDATION"}:
            frow = db.execute(
                "SELECT typed_payload FROM kineticloop.proposal_revisions WHERE id=%s",
                (UUID(operation.sources["fitness"]["id"]),),
            ).fetchone()[0]
            fitness = Fitness.model_validate_json(json.dumps(frow))
            if operation.kind == "DEMAND":
                assert artifact == compute_demand(
                    fitness, artifact.id, seed["policy"]["deterministic_fixture"]
                )
                assert (
                    row["ref_s34_id"] == fitness.id
                    and row["basis_hash"] == fitness.content_hash
                    and row["feature_hash"] == artifact.content_hash
                )
            if operation.kind in {"NUTRITION", "VALIDATION"}:
                drow = db.execute(
                    "SELECT to_jsonb(t) FROM kineticloop.prescription_demand_features t WHERE id=%s",
                    (UUID(operation.sources["demand"]["id"]),),
                ).fetchone()[0]
                demand = Demand.model_validate_json(json.dumps(drow["typed_payload"]))
                if operation.kind == "NUTRITION":
                    assert artifact == compute_nutrition(
                        fitness, demand, artifact.id, seed["policy"]["deterministic_fixture"]
                    )
                    assert (
                        row["demand_feature_id"] == drow["id"] and drow["ref_s34_id"] == fitness.id
                    )
                else:
                    nrow = db.execute(
                        "SELECT typed_payload FROM kineticloop.proposal_revisions WHERE id=%s",
                        (UUID(operation.sources["nutrition"]["id"]),),
                    ).fetchone()[0]
                    rrow = db.execute(
                        "SELECT typed_payload FROM kineticloop.evidence_resolutions WHERE id=%s",
                        (UUID(operation.sources["resolution"]["id"]),),
                    ).fetchone()[0]
                    nutrition = Nutrition.model_validate_json(json.dumps(nrow))
                    resolution = Resolution.model_validate_json(json.dumps(rrow))
                    now = db.execute("SELECT clock_timestamp()").fetchone()[0]
                    assert (
                        validate(
                            fitness,
                            demand,
                            nutrition,
                            resolution,
                            seed["policy"]["deterministic_fixture"],
                            now,
                        )["rolling_minutes"]
                        == artifact.rolling_minutes
                    )
                    assert (
                        row["ref_s34_id"] == nutrition.id
                        and row["ref_s35_id"] == demand.id
                        and row["ref_s36_id"] == resolution.id
                    )
        witness(
            "output",
            owner=OWNERS[operation.kind][0],
            stage=operation.source_state,
            output_kind=operation.kind,
            id=output["id"],
            hash=output["hash"],
            receipt=str(receipt[0]),
            event=str(events[0][0]),
            guard_accepted_at=events[0][1]["guard_accepted_at"],
            observed_clock_bounds=[before, after],
            payload=row["typed_payload"],
        )
    return artifact


def full_pipeline(
    db: Any, seed: dict[str, Any], basis: ProgressBasis, refs: Any, parent: UUID | None = None
) -> tuple[Any, Any]:
    operation, refs = until(db, seed, basis, refs, "VALIDATION", parent=parent)
    output = run(db, seed["identity"], operation)
    refs = {**refs, "validation": {"id": output["id"], "hash": output["hash"]}}
    assert_output(db, seed, operation, output)
    final_basis = ProgressBasis(
        **{k: getattr(operation, k) for k in ProgressBasis.__dataclass_fields__}
    )
    advance(
        db,
        seed["identity"],
        replace(final_basis, key="commit-ready-" + str(basis.attempt_id)),
        "COMMIT_READY",
        refs,
    )
    return operation, refs


def test_owner_pipeline(database_urls: dict[str, str]) -> None:
    seed = seed_source(database_urls)
    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed)
        before = snapshot(db, basis.subject_id)
        root_before = before["planning_intents"]
        operation, refs = full_pipeline(db, seed, basis, refs)
        with db.transaction():
            assert db.execute(
                "SELECT status FROM kineticloop.planning_attempts WHERE id=%s", (basis.attempt_id,)
            ).fetchone() == ("COMMIT_READY",)
        assert snapshot(db, basis.subject_id)["planning_intents"] == root_before
        for kind, name in (
            ("FITNESS", "fitness"),
            ("DEMAND", "demand"),
            ("NUTRITION", "nutrition"),
            ("RESOLUTION", "resolution"),
        ):
            stage = {
                "FITNESS": "FITNESS",
                "DEMAND": "DEMAND_FEATURES",
                "NUTRITION": "NUTRITION",
                "RESOLUTION": "VALIDATING",
            }[kind]
            required = {
                "FITNESS": {"snapshot"},
                "DEMAND": {"snapshot", "fitness"},
                "NUTRITION": {"snapshot", "fitness", "demand"},
                "RESOLUTION": {"snapshot", "fitness", "demand", "nutrition"},
            }[kind]
            op = request(
                replace(basis, source_state=stage),
                {k: v for k, v in refs.items() if k in required},
                kind,
            )
            assert_output(
                db,
                seed,
                op,
                {
                    **refs[name],
                    "kind": kind,
                    "attempt_id": str(basis.attempt_id),
                    "executable": False,
                    "lock_trace": [(20, "S01"), (40, "S27"), (80, "S02"), (90, "S29")],
                },
            )
        assert_no_execution(db, basis.subject_id)
        original = snapshot(db, basis.subject_id)
        service = LeaseService(db, PlanningIdentity(seed["identity"].actor, basis.subject_id))
        revision = service.admit_or_revise(
            AdmitOrReviseIntent(
                basis.subject_id,
                "repair",
                date.today(),
                "TRAINING",
                "test:UTC-v1",
                {"equipment": [], "minutes": 20},
            )
        )
        assert (
            revision["intent_id"] == str(basis.intent_id)
            and revision["request_revision"] == 2
            and revision["attempt_id"] != str(basis.attempt_id)
        )
        repaired_basis, repaired_refs = acquired(db, seed, revision)
        # Mixed old closure cannot advance the new owner-created attempt.
        zero = snapshot(db, basis.subject_id)
        with pytest.raises((RepositoryTransactionError, PlanningDenied)):
            advance(
                db,
                seed["identity"],
                repaired_basis,
                "DEMAND_FEATURES",
                {"snapshot": repaired_refs["snapshot"], "fitness": refs["fitness"]},
            )
        assert snapshot(db, basis.subject_id) == zero
        _, new_refs = full_pipeline(
            db, seed, repaired_basis, repaired_refs, UUID(refs["fitness"]["id"])
        )
        after = snapshot(db, basis.subject_id)
        for table in (
            "proposal_revisions",
            "prescription_demand_features",
            "evidence_resolutions",
            "validation_results",
        ):
            assert all(old in after[table] for old in original[table])
        root = after["planning_intents"][0][0]
        oldroot = original["planning_intents"][0][0]
        assert (
            root["deadline"] == oldroot["deadline"]
            and root["typed_payload"] == oldroot["typed_payload"]
        )
        with db.transaction():
            parent = db.execute(
                "SELECT typed_payload,revision FROM kineticloop.proposal_revisions WHERE id=%s",
                (UUID(new_refs["fitness"]["id"]),),
            ).fetchone()
            assert (
                parent[0]["parent_id"] == refs["fitness"]["id"]
                and parent[0]["parent_hash"] == refs["fitness"]["hash"]
                and parent[1] == 2
            )
        witness(
            "repair",
            old_attempt=basis.attempt_id,
            new_attempt=repaired_basis.attempt_id,
            same_root=basis.intent_id,
            old_refs=refs,
            new_refs=new_refs,
            original_history_preserved=True,
            root_budget_deadline_preserved=True,
        )
        assert_no_execution(db, basis.subject_id)


def observe_blocked(url: str, name: str) -> Any:
    deadline = time.monotonic() + 8
    with connect(url, autocommit=True) as db:
        while time.monotonic() < deadline:
            row = db.execute(
                "SELECT pid,pg_blocking_pids(pid),query FROM pg_stat_activity WHERE application_name=%s AND cardinality(pg_blocking_pids(pid))>0",
                (name,),
            ).fetchone()
            if row:
                witness("blocked", application=name, pid=row[0], blocking_pids=row[1], query=row[2])
                return row
    raise AssertionError("expected bounded observed PostgreSQL lock wait")


def wait_db_time(db: Any, end: Any) -> Any:
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        with db.transaction():
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        if now >= end:
            return now
    raise AssertionError("trusted DB time did not cross fixture expiry within six seconds")


@pytest.mark.parametrize(
    "kind,denial",
    [
        (kind, denial)
        for kind in KINDS
        for denial in (
            "takeover",
            "revision",
            "epoch",
            "manifest",
            "expiry",
            "terminal",
            "principal",
            "policy",
            "environment",
            "missing_source",
        )
    ]
    + [
        (kind, "stale_" + source)
        for source, kinds in {
            "fitness": ("DEMAND", "NUTRITION", "RESOLUTION", "VALIDATION"),
            "demand": ("NUTRITION", "RESOLUTION", "VALIDATION"),
            "nutrition": ("RESOLUTION", "VALIDATION"),
        }.items()
        for kind in kinds
    ]
    + [
        ("RESOLUTION", "missing_nutrition"),
        ("VALIDATION", "missing_nutrition"),
        ("VALIDATION", "resolution_mismatch"),
    ],
)
def test_stale_and_incomplete(database_urls: dict[str, str], kind: str, denial: str) -> None:
    seed = seed_source(database_urls)
    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed, lease_seconds=3 if denial in {"takeover", "expiry"} else 600)
        old_refs = None
        if denial.startswith("stale_"):
            _, old_refs = full_pipeline(db, seed, basis, refs)
            identity = seed["identity"]
            revised = LeaseService(
                db, PlanningIdentity(identity.actor, basis.subject_id)
            ).admit_or_revise(
                AdmitOrReviseIntent(
                    basis.subject_id,
                    "repair-for-mixed-closure",
                    date.today(),
                    "TRAINING",
                    "test:UTC-v1",
                    {"equipment": [], "minutes": 20},
                )
            )
            basis, refs = acquired(db, seed, revised)
            operation, _ = until(
                db, seed, basis, refs, kind, parent=UUID(old_refs["fitness"]["id"])
            )
        else:
            operation, _ = until(db, seed, basis, refs, kind)
        identity = seed["identity"]
        if denial == "revision":
            LeaseService(db, PlanningIdentity(identity.actor, basis.subject_id)).admit_or_revise(
                AdmitOrReviseIntent(
                    basis.subject_id,
                    "new-request",
                    date.today(),
                    "TRAINING",
                    "test:UTC-v1",
                    {"equipment": [], "minutes": 20},
                )
            )
        elif denial == "epoch":
            actual_input(db, seed, uuid4())
        elif denial == "manifest":
            ingress = PreparationService(
                db,
                ExecutionIdentity(
                    identity.actor,
                    identity.subject_id,
                    identity.policy_id,
                    identity.environment_id,
                    identity.principal,
                ),
            )
            newbuild = ingress.build_manifest(
                BuildManifest(
                    "new-manifest",
                    seed["source"],
                    (ProjectionBinding("EXPOSURE", UUID(seed["projection"]["projection_id"])),),
                    (seed["engine"].artifact_id,),
                )
            )
            ready = ingress.complete_manifest(CompleteManifest(UUID(newbuild["build_id"])))
            publish(db, seed, seed["source"], ready, "new-publication")
        elif denial == "terminal":
            stage = ProgressBasis(
                **{k: getattr(operation, k) for k in ProgressBasis.__dataclass_fields__}
            )
            advance(
                db, identity, replace(stage, key="terminal"), "FAILED", {}, "FIXTURE_TEST_FAILURE"
            )
        elif denial == "principal":
            identity = replace(identity, principal="kl_test_subject_2_login")
        elif denial == "policy":
            identity = replace(identity, policy_id=uuid4())
        elif denial == "environment":
            identity = replace(identity, environment_id=uuid4())
        elif denial.startswith("stale_"):
            assert old_refs is not None
            source = denial.removeprefix("stale_")
            operation = replace(operation, sources={**operation.sources, source: old_refs[source]})
        elif denial == "resolution_mismatch":
            operation = replace(
                operation,
                sources={
                    **operation.sources,
                    "resolution": {**operation.sources["resolution"], "hash": "0" * 64},
                },
            )
        elif denial in {"missing_source", "missing_nutrition"}:
            changed = {name: dict(value) for name, value in operation.sources.items()}
            last = (
                {
                    "FITNESS": "snapshot",
                    "DEMAND": "fitness",
                    "NUTRITION": "demand",
                    "RESOLUTION": "nutrition",
                    "VALIDATION": "resolution",
                }[kind]
                if denial == "missing_source"
                else "nutrition"
            )
            changed[last]["id"] = str(uuid4())
            operation = replace(operation, sources=changed)
        if denial in {"takeover", "expiry"}:
            with db.transaction():
                expiry = db.execute(
                    "SELECT lease_expires_at FROM kineticloop.planning_intents WHERE id=%s",
                    (basis.intent_id,),
                ).fetchone()[0]
            if denial == "takeover":
                wait_db_time(db, expiry)
                newactor = RoleIdentity(str(uuid4()), ActorRole.TEST)
                takeover = LeaseService(
                    db, PlanningIdentity(newactor, basis.subject_id)
                ).acquire_lease(
                    AcquireLease(
                        basis.subject_id,
                        "takeover",
                        basis.intent_id,
                        seed["identity"].key,
                        basis.fence,
                        basis.request_revision,
                        basis.attempt_id,
                        600,
                    )
                )
                assert takeover["fence"] > basis.fence
            else:
                # Real post-S29-lock trusted clock crossing; no equality/mock-time DC claim.
                before = snapshot(db, basis.subject_id)
                with connect(database_urls["admin"]) as blocker:
                    blocker.execute("BEGIN")
                    blocker.execute(
                        "SELECT id FROM kineticloop.planning_attempts WHERE id=%s FOR UPDATE",
                        (basis.attempt_id,),
                    )

                    def waiting() -> Any:
                        with connect(
                            database_urls["admin"], application_name="kl076-expiry-" + kind
                        ) as worker:
                            return run(worker, identity, operation)

                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(waiting)
                        observe_blocked(database_urls["admin"], "kl076-expiry-" + kind)
                        observed = wait_db_time(db, expiry)
                        blocker.commit()
                        with pytest.raises((RepositoryTransactionError, PlanningDenied)):
                            future.result(timeout=8)
                assert snapshot(db, basis.subject_id) == before
                witness(
                    "denial",
                    writer=kind,
                    dimension="POST_LOCK_LEASE_EXPIRY_DC",
                    expiry=expiry,
                    observed=observed,
                    zero_effects=True,
                )
                return
        before = snapshot(db, basis.subject_id)
        with pytest.raises((RepositoryTransactionError, PlanningDenied)) as error:
            run(db, identity, operation)
        assert snapshot(db, basis.subject_id) == before
        assert_no_execution(db, basis.subject_id)
        witness(
            "denial",
            writer=kind,
            dimension=denial,
            exception=type(error.value).__name__,
            message=str(error.value),
            zero_effects=True,
            exact_source_refs=operation.sources,
        )


@pytest.mark.parametrize("kind", KINDS)
def test_immutable_replay_rollback(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    seed = seed_source(database_urls)
    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed)
        operation, _ = until(db, seed, basis, refs, kind)
        table = OWNERS[kind][1]
        prior = snapshot(db, basis.subject_id)
        original = RestrictedSqlSession.insert

        def fail_after(session: RestrictedSqlSession, logical: str, values: Any) -> Any:
            result = original(session, logical, values)
            if logical == table:
                raise RuntimeError("KL076 injected after immutable owner write")
            return result

        with monkeypatch.context() as scoped:
            scoped.setattr(RestrictedSqlSession, "insert", fail_after)
            with pytest.raises(RuntimeError, match="injected"):
                run(db, seed["identity"], operation)
        assert snapshot(db, basis.subject_id) == prior
        witness("atomicity", writer=kind, phase="after_owner_write", zero_effects=True)
        # Fault at receipt completion occurs after target/event/outbox writes.
        with db.transaction():
            db.execute(
                "CREATE OR REPLACE FUNCTION kineticloop.kl076_receipt_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.subject_id='"
                + str(basis.subject_id)
                + "'::uuid AND NEW.client_key='"
                + operation.key
                + "' AND NEW.status='SUCCEEDED' THEN RAISE EXCEPTION 'KL076 receipt finalization fault'; END IF; RETURN NEW; END $$"
            )
            db.execute(
                "CREATE TRIGGER kl076_receipt_fault BEFORE UPDATE ON kineticloop.command_receipts FOR EACH ROW EXECUTE FUNCTION kineticloop.kl076_receipt_fault()"
            )
        try:
            with pytest.raises(psycopg.errors.RaiseException, match="receipt finalization"):
                run(db, seed["identity"], operation)
        finally:
            with db.transaction():
                db.execute("DROP TRIGGER kl076_receipt_fault ON kineticloop.command_receipts")
                db.execute("DROP FUNCTION kineticloop.kl076_receipt_fault()")
        assert snapshot(db, basis.subject_id) == prior
        witness("atomicity", writer=kind, phase="receipt_finalization", zero_effects=True)
        held, release = Event(), Event()

        def hold_after(session: RestrictedSqlSession, logical: str, values: Any) -> Any:
            result = original(session, logical, values)
            if logical == table and not held.is_set():
                held.set()
                assert release.wait(8)
            return result

        def contender(name: str) -> Any:
            with connect(database_urls["admin"], application_name=name) as worker:
                return run(worker, seed["identity"], operation)

        with monkeypatch.context() as scoped:
            scoped.setattr(RestrictedSqlSession, "insert", hold_after)
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(contender, "kl076-first-" + kind)
                if not held.wait(8):
                    first.result(timeout=1)
                    raise AssertionError("first immutable output barrier not established")
                second = pool.submit(contender, "kl076-second-" + kind)
                try:
                    observe_blocked(database_urls["admin"], "kl076-second-" + kind)
                finally:
                    release.set()
                a, b = first.result(timeout=8), second.result(timeout=8)
        assert a["id"] == b["id"] and a["hash"] == b["hash"] and b["executable"] is False
        artifact = assert_output(db, seed, operation, a)
        winner = snapshot(db, basis.subject_id)
        actual_table = {
            "S34": "proposal_revisions",
            "S35": "prescription_demand_features",
            "S36": "evidence_resolutions",
            "S37": "validation_results",
        }[table]
        assert len(winner[actual_table]) == len(prior[actual_table]) + 1
        for collection in ("command_receipts", "domain_events", "outbox_deliveries"):
            assert len(winner[collection]) == len(prior[collection]) + 1
        for collection in TABLES:
            if collection not in {
                actual_table,
                "command_receipts",
                "domain_events",
                "outbox_deliveries",
            }:
                assert winner[collection] == prior[collection]
            else:
                assert all(old in winner[collection] for old in prior[collection])
        witness(
            "atomicity",
            writer=kind,
            phase="observed_duplicate_race",
            winner=a["id"],
            hash=artifact.content_hash,
            exact_single_output_receipt_event_outbox=True,
            stage_root_authority_unchanged=True,
        )
        # ACK loss survives later epoch loss; independent new key cannot obtain authority.
        actual_input(db, seed, uuid4())
        historical = snapshot(db, basis.subject_id)
        replay = run(db, seed["identity"], operation)
        assert (
            replay["id"] == a["id"]
            and replay["hash"] == a["hash"]
            and replay["executable"] is False
            and replay["replayed"] is True
        )
        assert snapshot(db, basis.subject_id) == historical
        with pytest.raises((RepositoryTransactionError, PlanningDenied)):
            run(db, seed["identity"], replace(operation, key="independent-" + kind))
        assert snapshot(db, basis.subject_id) == historical
        # Guarded owner capabilities still reject every generic insert/update path.
        for logical, owner in (
            ("S34", "RecordProposal"),
            ("S35", "RecordDemandFeatures"),
            ("S36", "ResolveEvidence"),
            ("S37", "RecordValidation"),
        ):
            with pytest.raises(RepositoryTransactionError):
                execute_preparation(
                    db,
                    owner,
                    basis.subject_id,
                    lambda session: session.insert(
                        logical,
                        {
                            "id": uuid4(),
                            "subject_id": basis.subject_id,
                            "typed_payload": Jsonb({"result": "PASS"}),
                        },
                    ),
                )
            with pytest.raises(RepositoryTransactionError):
                execute_preparation(
                    db,
                    owner,
                    basis.subject_id,
                    lambda session: session.update(
                        logical,
                        {"typed_payload": Jsonb({"result": "PASS"})},
                        {"id": UUID(a["id"]), "subject_id": basis.subject_id},
                    ),
                )
        assert (
            execute_preparation(
                db, "RecordProposal", basis.subject_id, lambda session: session.relation_locks()
            )
            is not None
        )
        assert snapshot(db, basis.subject_id) == historical
        assert_no_execution(db, basis.subject_id)
        witness(
            "replay",
            writer=kind,
            historical_id=a["id"],
            epoch_lost=True,
            generic_workflow_mutations_denied=True,
            zero_effects=True,
        )
