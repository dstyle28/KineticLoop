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
from kineticloop.workflow.deterministic_planning import (
    FULL_VERSION,
    OWNERS,
    RULES,
    VERSION,
    FullPreparationRequest,
    FullResolution,
    FullValidation,
    PreparationRequest,
    binding,
    full_query_basis,
)
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
_MIGRATIONS = load("kl079_migrations", "tests/db/test_migrations.py")
_NAMESPACE = load("kl079_namespace", "tests/unit/workflow/test_full_action_preparation.py")
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
        raise ValueError("foreign/default KL079 database URL")
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
        Path("/private/tmp/kl079-peer-root")
        if sys.platform == "darwin"
        else Path("/tmp/kl079-peer-root")
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
    actor = RoleIdentity(str(uuid4()), ActorRole.TEST)
    identity = ProgressIdentity(actor, subject, policy_id, environment, "kl_test_subject_1_login")
    with connect(urls["admin"], autocommit=True) as db:
        clock = db.execute("SELECT clock_timestamp()").fetchone()
        assert clock is not None
        now = clock[0]
        end = now + timedelta(seconds=seconds)
        admission_end = now + timedelta(seconds=admission_seconds or seconds)
        runtime_end = now + timedelta(seconds=runtime_seconds or seconds)
        config = {
            "rules": copy.deepcopy(RULES),
            "window": [(now - timedelta(days=1)).isoformat(), end.isoformat()],
            "required_members": sorted(map(str, (association, admission, fact))),
            "reservations": {"prior-slot": 50},
            "valid_until": end.isoformat(),
        }
        if full:
            config.update(contract=FULL_VERSION, required_actions=["TRAINING", "NUTRITION"])
        config.update(config_changes or {})
        runtime_version = FULL_VERSION if full else VERSION
        runtime_hash = digest({"version": FULL_VERSION, "rules": RULES}) if full else digest(RULES)
        deps = (
            Dependency("COLLECTION", "fixture-facts", "all-fixture-facts-and-absence:v1"),
            Dependency("ENGINE", f"test:kl079-engine-{subject}:1"),
            Dependency("FACTSET", "sealed-input"),
            Dependency("POLICY", "selected-policy"),
            Dependency("PROGRAM", "selected-program"),
            Dependency("FACT", "actual-member", fact_id=fact),
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
        assoc_body = {"fixture_association": "MATCHED", "event_id": str(event)}
        db.execute(
            "INSERT INTO kineticloop.event_association_decisions(id,subject_id,association_family_identity,association_state,ref_s11_id,content_hash,typed_payload) VALUES (%s,%s,'fixture-event','MATCHED',%s,%s,%s)",
            (association, subject, event, digest(assoc_body), Jsonb(assoc_body)),
        )
        admission_body = {"fixture_admission": "ELIGIBLE", "valid_until": admission_end.isoformat()}
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
                VERSION,
                digest(RULES),
                {"operation": "DETERMINISTIC_TEST_PREPARATION", "version": VERSION},
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
                registered_runtime(
                    trusted,
                    runtime,
                    runtime_hash,
                    release,
                    now,
                    runtime_end,
                    (builder, release_artifact),
                )
        for dependency in (runtime, builder, release_artifact):
            # The planning runtime is independently policy-bound. Keep the projection
            # engine's valid registered closure longer for the isolated runtime test.
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
        "engine": ArtifactIdentity(
            engine, "POLICY_BUNDLE", f"test:kl079-engine-{subject}", "1", digest(body)
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

    payload.update(seed.get("fact_changes", {}))
    future = payload.pop("future", False)

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
                    "effective_at": seed["now"] + timedelta(minutes=1)
                    if future
                    else seed["now"] - timedelta(hours=1),
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
    members: tuple[Member, ...] = (
        Member("ASSOCIATION", "fixture-event", "TEST_ONLY", seed["association"]),
        Member("ADMISSION", "fixture-admitted", "TEST_ONLY", seed["admission"]),
        Member("FACT", "fixture-actual", "TEST_ONLY", seed["fact"]),
    )
    members += tuple(
        Member("FACT", f"extra-fixture-{i}", "TEST_ONLY", seed["fact"])
        for i in range(seed.get("extra_members", 0))
    )
    for n, member in enumerate(members):
        cv.write_candidate(WriteCandidate(subject, f"member-{n}", factset_id, n, member))
    complete = cv.complete_factset(CompleteFactset(subject, "complete", factset_id, len(members)))
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


def run(
    db: Any, identity: ProgressIdentity, operation: PreparationRequest | FullPreparationRequest
) -> Any:
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


def assert_legacy_output(
    db: Any, seed: dict[str, Any], operation: PreparationRequest, output: Any
) -> Any:
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


def legacy_pipeline(
    db: Any, seed: dict[str, Any], basis: ProgressBasis, refs: Any, parent: UUID | None = None
) -> tuple[Any, Any]:
    operation, refs = until(db, seed, basis, refs, "VALIDATION", parent=parent)
    output = run(db, seed["identity"], operation)
    refs = {**refs, "validation": {"id": output["id"], "hash": output["hash"]}}
    assert_legacy_output(db, seed, operation, output)
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


def registered_runtime(
    db: Any,
    artifact: UUID,
    content_hash: str,
    release: UUID,
    now: datetime,
    end: datetime,
    deps: tuple[UUID, ...],
) -> None:
    from kineticloop.contracts.artifacts import (
        ArtifactBindingKind,
        ArtifactRegistration,
        ArtifactValiditySpec,
    )
    from kineticloop.contracts.commands import RegisterArtifact, TransactionBoundary
    from kineticloop.persistence.artifact_registry import register_artifact

    validity = ArtifactValiditySpec(
        "BOUNDED", now, ArtifactBindingKind.EVALUATION_RELEASE, str(release), end
    )
    command = RegisterArtifact.model_validate(
        dict(
            schema_version="kineticloop-command-v1",
            command_kind="RegisterArtifact",
            boundary=TransactionBoundary.REGISTRY_MANAGEMENT,
            command_id=str(uuid4()),
            actor={
                "schema": "kineticloop-role-identity-v1",
                "identity_id": str(uuid4()),
                "role": ActorRole.ADMIN,
            },
            idempotency_key="register-" + str(artifact),
            request_hash=digest([str(artifact), content_hash]),
            subject_id=None,
            explicit_scope="global:safety-registry",
            artifact_id=str(artifact),
            artifact_kind="RUNTIME",
            content_hash=content_hash,
            dependency_ids=tuple(map(str, deps)),
            validity_spec_hash=validity.sha256(),
        )
    )
    registration = ArtifactRegistration(
        command, f"test:kl079-runtime-{artifact}", FULL_VERSION, validity
    )
    result = register_artifact(db, registration)
    assert result.artifact_id == str(artifact) and result.replayed is False
    assert register_artifact(db, registration).replayed is True
    witness(
        "runtime_registration",
        id=result.artifact_id,
        hash=content_hash,
        version=FULL_VERSION,
        owner="SafetyRegistry.RegisterArtifact",
        immutable_dependencies=list(map(str, deps)),
    )


def full_request(
    db: Any,
    basis: ProgressBasis,
    refs: Any,
    kind: str,
    action: str | None = None,
    key: str | None = None,
) -> FullPreparationRequest:
    values = {
        **asdict(basis),
        "key": key or (kind + "-" + str(action) + "-" + str(basis.attempt_id)),
    }
    if kind == "RESOLUTION":
        name = "fitness" if action == "TRAINING" else "nutrition"
        with db.transaction():
            payload = db.execute(
                "SELECT typed_payload FROM kineticloop.proposal_revisions WHERE id=%s",
                (UUID(refs[name]["id"]),),
            ).fetchone()[0]
        params = (
            payload["action"]
            if action == "TRAINING"
            else {
                "fuel_units": payload["fuel_units"],
                "semantic_class": "TARGET",
                "units": "fixture_units",
            }
        )
        return FullPreparationRequest(
            **values,
            kind=kind,
            sources=copy.deepcopy(refs),
            action_type=action,
            proposal_id=UUID(refs[name]["id"]),
            proposal_hash=refs[name]["hash"],
            action_parameters_hash=digest(params),
        )
    bindings = []
    with db.transaction():
        for name in ("resolution", "nutrition_resolution"):
            payload = db.execute(
                "SELECT typed_payload FROM kineticloop.evidence_resolutions WHERE id=%s",
                (UUID(refs[name]["id"]),),
            ).fetchone()[0]
            bindings.append(binding(FullResolution.model_validate_json(json.dumps(payload))))
    return FullPreparationRequest(
        **values, kind=kind, sources=copy.deepcopy(refs), action_bindings=tuple(bindings)
    )


def fdn(
    db: Any, seed: Any, basis: ProgressBasis, refs: Any, parent: UUID | None = None
) -> tuple[Any, Any]:
    operation, refs = until(db, seed, basis, refs, "RESOLUTION", parent=parent)
    basis = ProgressBasis(**{k: getattr(operation, k) for k in ProgressBasis.__dataclass_fields__})
    return basis, refs


def action_resolution(db: Any, seed: Any, basis: Any, refs: Any, action: str) -> tuple[Any, Any]:
    op = full_request(db, basis, refs, "RESOLUTION", action)
    output = run(db, seed["identity"], op)
    assert_full_output(db, seed, op, output)
    return op, {"id": output["id"], "hash": output["hash"]}


def preparation_chain(
    db: Any, seed: Any, basis: Any, refs: Any, parent: UUID | None = None
) -> tuple[Any, Any]:
    basis, refs = fdn(db, seed, basis, refs, parent)
    _, training = action_resolution(db, seed, basis, refs, "TRAINING")
    _, nutrition = action_resolution(db, seed, basis, refs, "NUTRITION")
    refs = {**refs, "resolution": training, "nutrition_resolution": nutrition}
    return full_request(db, basis, refs, "VALIDATION"), refs


def prepare_validation(db: Any, seed: Any, operation: Any, refs: Any) -> Any:
    output = run(db, seed["identity"], operation)
    assert_full_output(db, seed, operation, output)
    return {
        **{k: v for k, v in refs.items() if k != "nutrition_resolution"},
        "validation": {"id": output["id"], "hash": output["hash"]},
    }


def commit_ready(db: Any, seed: Any, operation: Any, refs: Any, key: str = "commit-ready") -> Any:
    basis = ProgressBasis(**{k: getattr(operation, k) for k in ProgressBasis.__dataclass_fields__})
    return advance(
        db, seed["identity"], replace(basis, key=key + str(basis.attempt_id)), "COMMIT_READY", refs
    )


def assert_full_output(db: Any, seed: Any, operation: Any, output: Any) -> Any:
    table = "evidence_resolutions" if operation.kind == "RESOLUTION" else "validation_results"
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
            "SELECT id,typed_payload FROM kineticloop.domain_events WHERE ref_s02_id=%s",
            (receipt[0],),
        ).fetchall()
        assert len(events) == 1
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
        assert [x[0] for x in output["lock_trace"]] == [20, 40, 80, 90]
        model = FullResolution if operation.kind == "RESOLUTION" else FullValidation
        artifact: Any = model.model_validate_json(json.dumps(row["typed_payload"]))
        assert (
            artifact.contract == FULL_VERSION
            and artifact.snapshot_id == operation.sources["snapshot"]["id"]
        )
        if operation.kind == "RESOLUTION":
            assert row["action_type"] == operation.action_type == artifact.action_type
            assert (
                row["query_basis_hash"]
                == artifact.query_basis_hash
                == full_query_basis(artifact.payload())
            )
            assert row["action_parameters_hash"] == operation.action_parameters_hash
            assert row["ref_s24_id"] == str(operation.manifest_id) and row["ref_s05_id"] == str(
                seed["identity"].policy_id
            )
            assert artifact.source_members == tuple(
                sorted(map(str, (seed["fact"], seed["association"], seed["admission"])))
            )
            assert artifact.facts[0].semantic_class == "ACTUAL_EXECUTION"
            assert row["resolver_version"] == FULL_VERSION
        else:
            assert tuple(b.action_type for b in artifact.action_bindings) == (
                "TRAINING",
                "NUTRITION",
            )
            assert artifact.action_bindings == operation.action_bindings
            assert row["ref_s36_id"] == operation.sources["resolution"]["id"]
            assert artifact.resolution_hash == operation.sources["resolution"]["hash"]
            assert row["ref_s34_id"] == operation.sources["nutrition"]["id"]
            assert row["ref_s35_id"] == operation.sources["demand"]["id"]
            execution = db.execute(
                "SELECT execution_basis_event_id FROM kineticloop.user_decision_state WHERE subject_id=%s",
                (operation.subject_id,),
            ).fetchone()[0]
            assert row["ref_s03_id"] == str(execution)
            assert (
                artifact.rolling_minutes == 40
                if operation.request_revision == 1
                else artifact.rolling_minutes == 30
            )
        assert datetime.fromisoformat(
            row.get("valid_until", row.get("resolution_expires_at"))
        ) == datetime.fromisoformat(
            artifact.valid_until
            if operation.kind == "VALIDATION"
            else artifact.resolution_expires_at
        )
        witness(
            "full_output",
            owner=OWNERS[operation.kind][0],
            id=output["id"],
            hash=output["hash"],
            receipt=receipt[0],
            event=events[0][0],
            accepted_at=accepted,
            payload=artifact.payload(),
            columns=row,
        )
    return artifact


def test_owner_pipeline(database_urls: dict[str, str]) -> None:
    seed = seed_source(database_urls)
    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed)
        original = snapshot(db, basis.subject_id)
        op, fullrefs = preparation_chain(db, seed, basis, refs)
        refs = prepare_validation(db, seed, op, fullrefs)
        result = commit_ready(db, seed, op, refs)
        after = snapshot(db, basis.subject_id)
        assert len(after["evidence_resolutions"]) == 2 and len(after["validation_results"]) == 1
        assert after["planning_intents"] == original["planning_intents"]
        assert after["user_decision_state"] == original["user_decision_state"]
        assert after["planning_attempts"][0][0]["status"] == "COMMIT_READY"
        assert set(after["planning_attempts"][0][0]["typed_payload"]["progress_sources"]) == {
            "snapshot",
            "fitness",
            "demand",
            "nutrition",
            "resolution",
            "validation",
        }
        assert_no_execution(db, basis.subject_id)
        witness(
            "full_commit_ready",
            result=result,
            refs=refs,
            two_distinct_resolutions=True,
            one_training_anchor=True,
            non_executable=True,
        )


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
    raise AssertionError("bounded observed lock waiter missing")


def wait_db_time(db: Any, end: Any) -> Any:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        with db.transaction():
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        if now > end:
            return now
    raise AssertionError("bounded actual trusted clock crossing missing")


@pytest.mark.parametrize(
    "denial",
    [
        "parameters_training",
        "parameters_nutrition",
        "proposal",
        "policy",
        "environment",
        "principal",
        "subject",
        "manifest",
        "epoch",
        "revision",
        "attempt",
        "fence",
        "lease",
        "deadline",
        "control",
        "runtime_revoked",
        "missing_resolution",
        "duplicate_resolution",
        "reordered_bindings",
        "foreign_resolution",
        "source_membership",
        "contradiction",
        "retraction",
        "unknown_exposure",
        "future_evidence",
        "truncation",
        "binding_hash",
        "terminal",
        "takeover",
        "wrong_action",
        *[
            "consumer_" + case
            for case in (
                "resolution_swap",
                "foreign_validation",
                "foreign_resolution",
                "runtime_revoked",
                "execution_basis",
                "epoch",
                "revision",
                "control",
                "deadline",
                "manifest",
                "attempt",
                "fence",
                "takeover",
                "lease",
                "source_before_expiry",
                "source_after_expiry",
                "runtime_before_expiry",
                "runtime_after_expiry",
                "validation_source_before_expiry",
                "validation_source_after_expiry",
                "validation_runtime_before_expiry",
                "validation_runtime_after_expiry",
            )
        ],
    ],
)
def test_basis_denials(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch, denial: str
) -> None:
    if denial.startswith("consumer_"):
        consumer_denial(database_urls, monkeypatch, denial.removeprefix("consumer_"))
        return
    facts = {
        "contradiction": {"contradicts": True},
        "retraction": {"retracted": True},
        "unknown_exposure": {"upper_minutes": None},
        "future_evidence": {"future": True},
    }
    config = {"required_members": [str(uuid4())]} if denial == "source_membership" else None
    seed = seed_source(database_urls, fact_changes=facts.get(denial), config_changes=config)
    if denial == "truncation":
        seed["extra_members"] = 64
    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed, lease_seconds=3 if denial in {"lease", "takeover"} else 600)
        if denial == "truncation":
            before = snapshot(db, basis.subject_id)
            with pytest.raises(
                RepositoryTransactionError, match="bounded FULL fixture member closure"
            ):
                fdn(db, seed, basis, refs)
            assert snapshot(db, basis.subject_id) == before
            witness(
                "denial",
                dimension="truncation",
                stage="FULL_SOURCE_CAPTURE_RECORD_PROPOSAL",
                zero_effects=True,
                actual_sealed_members=67,
            )
            return
        basis, refs = fdn(db, seed, basis, refs)
        identity = seed["identity"]
        phase = {"ingress": False, "current_chain": False}
        original_ingress = RepositoryTransaction.require_progress_ingress
        original_chain = RepositoryTransaction._prepare_current_progress

        def ingress(tx: Any, who: Any) -> Any:
            result = original_ingress(tx, who)
            phase["ingress"] = True
            return result

        def chain(tx: Any, who: Any, op: Any) -> Any:
            phase["current_chain"] = True
            return original_chain(tx, who, op)

        monkeypatch.setattr(RepositoryTransaction, "require_progress_ingress", ingress)
        monkeypatch.setattr(RepositoryTransaction, "_prepare_current_progress", chain)
        action = "TRAINING" if denial == "parameters_training" else "NUTRITION"
        op = full_request(db, basis, refs, "RESOLUTION", action)
        if denial.startswith("parameters_"):
            op = replace(op, action_parameters_hash=digest("wrong parameters"))
        elif denial == "wrong_action":
            op = full_request(db, basis, refs, "RESOLUTION", "TRAINING")
            op = replace(
                op,
                action_parameters_hash=digest(
                    {"fuel_units": 90, "semantic_class": "TARGET", "units": "fixture_units"}
                ),
            )
        elif denial == "terminal":
            advance(
                db, identity, replace(basis, key="terminal-denial"), "STALE", {}, "TEST_TERMINAL"
            )
        elif denial == "takeover":
            with db.transaction():
                expiry = db.execute(
                    "SELECT lease_expires_at FROM kineticloop.planning_intents WHERE id=%s",
                    (basis.intent_id,),
                ).fetchone()[0]
            wait_db_time(db, expiry)
            takeover = LeaseService(
                db, PlanningIdentity(RoleIdentity(str(uuid4()), ActorRole.TEST), basis.subject_id)
            ).acquire_lease(
                AcquireLease(
                    basis.subject_id,
                    "takeover-negative",
                    basis.intent_id,
                    identity.key,
                    basis.fence,
                    basis.request_revision,
                    basis.attempt_id,
                    600,
                )
            )
            assert takeover["fence"] > basis.fence
        elif denial == "proposal":
            # A source with exact valid ingress shape, but cross-action proposal content.
            op = replace(
                op,
                sources={**refs, "nutrition": refs["fitness"]},
                proposal_id=UUID(refs["fitness"]["id"]),
                proposal_hash=refs["fitness"]["hash"],
            )
        elif denial in {"policy", "environment", "principal", "subject"}:
            field = {
                "policy": "policy_id",
                "environment": "environment_id",
                "subject": "subject_id",
                "principal": "principal",
            }[denial]
            identity = replace(
                identity, **{field: "kl_test_subject_2_login" if denial == "principal" else uuid4()}
            )
        elif denial == "manifest":
            ingress_owner = PreparationService(
                db,
                ExecutionIdentity(
                    identity.actor,
                    identity.subject_id,
                    identity.policy_id,
                    identity.environment_id,
                    identity.principal,
                ),
            )
            build = ingress_owner.build_manifest(
                BuildManifest(
                    "new-manifest",
                    seed["source"],
                    (ProjectionBinding("EXPOSURE", UUID(seed["projection"]["projection_id"])),),
                    (seed["engine"].artifact_id,),
                )
            )
            ready = ingress_owner.complete_manifest(CompleteManifest(UUID(build["build_id"])))
            publish(db, seed, seed["source"], ready, "new-manifest-publication")
        elif denial == "epoch":
            actual_input(db, seed, uuid4())
        elif denial == "revision":
            LeaseService(db, PlanningIdentity(identity.actor, basis.subject_id)).admit_or_revise(
                AdmitOrReviseIntent(
                    basis.subject_id,
                    "revise-negative",
                    date.today(),
                    "TRAINING",
                    "test:UTC-v1",
                    {"equipment": [], "minutes": 20},
                )
            )
        elif denial == "attempt":
            with db.transaction():
                db.execute(
                    "UPDATE kineticloop.planning_intents SET current_attempt_id=NULL WHERE id=%s",
                    (basis.intent_id,),
                )
        elif denial == "fence":
            op = replace(op, fence=basis.fence + 1)
        elif denial == "deadline":
            with db.transaction():
                db.execute(
                    "UPDATE kineticloop.planning_intents SET deadline=clock_timestamp()-interval '1 second' WHERE id=%s",
                    (basis.intent_id,),
                )
        elif denial == "control":
            apply_control(db, seed)
        elif denial == "runtime_revoked":
            revoke_runtime(database_urls, seed)
        elif denial in {
            "missing_resolution",
            "duplicate_resolution",
            "reordered_bindings",
            "foreign_resolution",
            "binding_hash",
            "source_membership",
            "contradiction",
            "retraction",
            "future_evidence",
        }:
            _, training = action_resolution(db, seed, basis, refs, "TRAINING")
            _, nutrition = action_resolution(db, seed, basis, refs, "NUTRITION")
            allrefs = {**refs, "resolution": training, "nutrition_resolution": nutrition}
            op = full_request(db, basis, allrefs, "VALIDATION")
            if denial == "missing_resolution":
                # Existing but foreign immutable ID; exact closed input shape reaches the real reader.
                op = replace(
                    op,
                    sources={
                        **op.sources,
                        "nutrition_resolution": {"id": str(uuid4()), "hash": nutrition["hash"]},
                    },
                )
            elif denial == "duplicate_resolution":
                op = replace(op, sources={**op.sources, "nutrition_resolution": training})
            elif denial == "foreign_resolution":
                op = replace(
                    op,
                    sources={
                        **op.sources,
                        "resolution": {"id": str(uuid4()), "hash": training["hash"]},
                    },
                )
            elif denial == "reordered_bindings":
                # Closed request denies this before any database mutation.
                before = snapshot(db, basis.subject_id)
                with pytest.raises(PlanningDenied):
                    replace(op, action_bindings=tuple(reversed(op.action_bindings)))
                assert snapshot(db, basis.subject_id) == before
                witness("denial", dimension=denial, stage="CLOSED_REQUEST", zero_effects=True)
                return
            elif denial == "binding_hash":
                bad = op.action_bindings[1].model_copy(
                    update={"query_basis_hash": digest("truncated")}
                )
                op = replace(op, action_bindings=(op.action_bindings[0], bad))
        before = snapshot(db, basis.subject_id)
        phase.update(ingress=False, current_chain=False)
        if denial == "lease":
            with db.transaction():
                expiry = db.execute(
                    "SELECT lease_expires_at FROM kineticloop.planning_intents WHERE id=%s",
                    (basis.intent_id,),
                ).fetchone()[0]
            with connect(database_urls["admin"]) as blocker:
                blocker.execute(
                    "SELECT id FROM kineticloop.planning_attempts WHERE id=%s FOR UPDATE",
                    (basis.attempt_id,),
                )

                def worker() -> Any:
                    with connect(
                        database_urls["admin"], application_name="kl079-post-lock-lease"
                    ) as connection:
                        return run(connection, identity, op)

                with ThreadPoolExecutor(max_workers=1) as pool:
                    pending = pool.submit(worker)
                    blocked = observe_blocked(database_urls["admin"], "kl079-post-lock-lease")
                    crossed = wait_db_time(db, expiry)
                    blocker.commit()
                    with pytest.raises((RepositoryTransactionError, PlanningDenied)) as error:
                        pending.result(timeout=8)
            assert phase["ingress"] and phase["current_chain"]
            witness(
                "clock_crossing",
                expiry=expiry,
                observed=crossed,
                blockers=blocked[1],
                after_lock=True,
            )
        else:
            with pytest.raises(
                (RepositoryTransactionError, PlanningDenied, ValueError, KeyError)
            ) as error:
                run(db, identity, op)
        assert snapshot(db, basis.subject_id) == before
        assert_no_execution(db, basis.subject_id)
        if denial in {"manifest", "epoch", "revision", "attempt", "fence", "deadline", "control"}:
            assert phase["ingress"]
        witness(
            "denial",
            dimension=denial,
            exception=type(error.value).__name__,
            message=str(error.value),
            ingress_passed=phase["ingress"],
            current_guard_reached=phase["current_chain"],
            zero_effects=True,
        )


def apply_control(db: Any, seed: Any) -> None:
    subject = seed["identity"].subject_id
    control = uuid4()
    head = uuid4()
    receipt = uuid4()

    def operation(tx: Any) -> Any:
        tx.lock_subject()

        def write(session: Any) -> Any:
            session.insert(
                "S17",
                {
                    "id": control,
                    "subject_id": subject,
                    "scope": "TEST_ONLY",
                    "status": "STOP",
                    "control_identity": str(control),
                    "control_revision": 1,
                    "ref_s02_id": receipt,
                    "ref_s05_id": seed["identity"].policy_id,
                },
            )
            session.insert(
                "S18",
                {
                    "id": head,
                    "subject_id": subject,
                    "execution_scope": "TEST_ONLY",
                    "status": "ACTIVE",
                    "control_identity": str(control),
                    "head_revision": 1,
                    "ref_s17_id": control,
                },
            )
            epoch = tx._coordination_context["authorization_epoch"]
            session.insert(
                "S43",
                {
                    "id": uuid4(),
                    "subject_id": subject,
                    "event_kind": "EPOCH_INVALIDATED",
                    "scope": "TEST_ONLY",
                    "causation_key": str(control),
                    "invalidated_epoch": epoch + 1,
                    "ref_s17_id": control,
                    "ref_s02_id": receipt,
                },
            )
            session.update(
                "S01",
                {"authorization_epoch": epoch + 1, "last_control_event_id": control},
                {"subject_id": subject},
            )
            return {"id": str(control)}

        return tx.idempotent_outcome(
            receipt_id=receipt,
            actor_scope=seed["identity"].key,
            client_key=str(control),
            request_hash=digest(str(control)),
            mutation=write,
            event=EventWrite(
                event_id=uuid4(),
                aggregate_type="CONTROL",
                aggregate_identity=str(control),
                event_type="ApplyControl",
                aggregate_revision=1,
                outbox_id=uuid4(),
                destination="control",
            ),
            invalidation_scope="TEST_ONLY",
        )[0]

    execute_command(db, "ApplyControl", subject, operation)


def revoke_runtime(urls: Any, seed: Any) -> None:
    from kineticloop.contracts.commands import RevokeArtifact, TransactionBoundary
    from kineticloop.contracts.safety_registry import revocation_payload_hash
    from kineticloop.persistence.safety_registry import revoke_artifact

    now = seed["now"]
    command = RevokeArtifact.model_validate(
        dict(
            schema_version="kineticloop-command-v1",
            command_kind="RevokeArtifact",
            boundary=TransactionBoundary.T2_GLOBAL,
            command_id=str(uuid4()),
            actor={
                "schema": "kineticloop-role-identity-v1",
                "identity_id": str(uuid4()),
                "role": ActorRole.ADMIN,
            },
            idempotency_key="revoke-runtime",
            request_hash=digest("revoke-runtime"),
            subject_id=None,
            explicit_scope="global:safety-registry",
            artifact_id=str(seed["runtime"]),
            artifact_content_hash=seed["runtime_hash"],
            revocation_payload_hash=revocation_payload_hash(
                effective_at=now, reason_code="TEST_NEGATIVE"
            ),
            causation_incident_id=str(uuid4()),
        )
    )
    with connect(urls["trusted_admin"]) as trusted:
        revoke_artifact(trusted, command, effective_at=now, reason_code="TEST_NEGATIVE")


@pytest.mark.parametrize("action", ["TRAINING", "NUTRITION", "VALIDATION"])
def test_replay_and_atomicity(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    seed = seed_source(database_urls)
    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed)
        if action == "VALIDATION":
            op, _ = preparation_chain(db, seed, basis, refs)
        else:
            basis, refs = fdn(db, seed, basis, refs)
            op = full_request(db, basis, refs, "RESOLUTION", action)
        logical = "S37" if action == "VALIDATION" else "S36"
        table = "validation_results" if action == "VALIDATION" else "evidence_resolutions"
        before = snapshot(db, basis.subject_id)
        insert = RestrictedSqlSession.insert

        def fault(session: Any, name: str, values: Any) -> Any:
            result = insert(session, name, values)
            if name == logical:
                raise RuntimeError("KL079 injected after output")
            return result

        with monkeypatch.context() as scoped:
            scoped.setattr(RestrictedSqlSession, "insert", fault)
            with pytest.raises(RuntimeError, match="injected"):
                run(db, seed["identity"], op)
        assert snapshot(db, basis.subject_id) == before
        # A fault after target/event/outbox, before receipt SUCCEEDED must roll everything back.
        with db.transaction():
            db.execute(
                "CREATE FUNCTION kineticloop.kl079_receipt_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.subject_id='"
                + str(basis.subject_id)
                + "'::uuid AND NEW.client_key='"
                + op.key
                + "' AND NEW.status='SUCCEEDED' THEN RAISE EXCEPTION 'KL079 bookkeeping fault'; END IF; RETURN NEW; END $$"
            )
            db.execute(
                "CREATE TRIGGER kl079_receipt_fault BEFORE UPDATE ON kineticloop.command_receipts FOR EACH ROW EXECUTE FUNCTION kineticloop.kl079_receipt_fault()"
            )
        try:
            with pytest.raises(psycopg.errors.RaiseException, match="bookkeeping fault"):
                run(db, seed["identity"], op)
        finally:
            with db.transaction():
                db.execute("DROP TRIGGER kl079_receipt_fault ON kineticloop.command_receipts")
                db.execute("DROP FUNCTION kineticloop.kl079_receipt_fault()")
        assert snapshot(db, basis.subject_id) == before
        held, release = Event(), Event()

        def hold(session: Any, name: str, values: Any) -> Any:
            result = insert(session, name, values)
            if name == logical and not held.is_set():
                held.set()
                assert release.wait(8)
            return result

        def contender(name: str) -> Any:
            with connect(database_urls["admin"], application_name=name) as worker:
                return run(worker, seed["identity"], op)

        with monkeypatch.context() as scoped:
            scoped.setattr(RestrictedSqlSession, "insert", hold)
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(contender, "kl079-first-" + action)
                if not held.wait(8):
                    first.result(timeout=1)
                    raise AssertionError("output barrier not established")
                second = pool.submit(contender, "kl079-second-" + action)
                try:
                    blockers = observe_blocked(database_urls["admin"], "kl079-second-" + action)
                finally:
                    release.set()
                a, b = first.result(timeout=8), second.result(timeout=8)
        assert a["id"] == b["id"] and a["hash"] == b["hash"] and b["replayed"] is True
        assert_full_output(db, seed, op, a)
        after = snapshot(db, basis.subject_id)
        for name in TABLES:
            if name in {table, "command_receipts", "domain_events", "outbox_deliveries"}:
                assert len(after[name]) == len(before[name]) + 1 and all(
                    r in after[name] for r in before[name]
                )
            else:
                assert after[name] == before[name]
        if action == "VALIDATION":
            bad = replace(
                op,
                action_bindings=(
                    op.action_bindings[0],
                    op.action_bindings[1].model_copy(update={"query_basis_hash": digest("wrong")}),
                ),
            )
        else:
            bad = replace(op, action_parameters_hash=digest("changed"))
        with pytest.raises(RepositoryTransactionError, match="identity conflict"):
            run(db, seed["identity"], bad)
        assert snapshot(db, basis.subject_id) == after
        actual_input(db, seed, uuid4())
        historical = snapshot(db, basis.subject_id)
        replay = run(db, seed["identity"], op)
        assert (
            replay["id"] == a["id"]
            and replay["hash"] == a["hash"]
            and replay["executable"] is False
            and replay["replayed"] is True
        )
        with pytest.raises((RepositoryTransactionError, PlanningDenied)):
            run(db, seed["identity"], replace(op, key="fresh-after-loss"))
        assert snapshot(db, basis.subject_id) == historical
        assert_no_execution(db, basis.subject_id)
        witness(
            "atomicity_replay",
            action=action,
            blockers=blockers[1],
            output=a,
            ack_loss=replay,
            after_output_rollback=True,
            before_bookkeeping_rollback=True,
            exact_one_output_receipt_event_outbox=True,
            changed_same_key_conflicts=True,
            historical_non_executable=True,
        )


def test_f2_repair(database_urls: dict[str, str]) -> None:
    seed = seed_source(database_urls)
    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed)
        oldop, oldfull = preparation_chain(db, seed, basis, refs)
        oldrefs = prepare_validation(db, seed, oldop, oldfull)
        commit_ready(db, seed, oldop, oldrefs)
        original = snapshot(db, basis.subject_id)
        identity = seed["identity"]
        revised = LeaseService(
            db, PlanningIdentity(identity.actor, basis.subject_id)
        ).admit_or_revise(
            AdmitOrReviseIntent(
                basis.subject_id,
                "same-root-f2",
                date.today(),
                "TRAINING",
                "test:UTC-v1",
                {"equipment": [], "minutes": 20},
            )
        )
        assert (
            revised["intent_id"] == str(basis.intent_id)
            and revised["request_revision"] == 2
            and revised["attempt_id"] != str(basis.attempt_id)
        )
        newbasis, newrefs = acquired(db, seed, revised)
        before = snapshot(db, basis.subject_id)
        with pytest.raises((RepositoryTransactionError, PlanningDenied)):
            advance(
                db,
                identity,
                newbasis,
                "DEMAND_FEATURES",
                {"snapshot": newrefs["snapshot"], "fitness": oldrefs["fitness"]},
            )
        assert snapshot(db, basis.subject_id) == before
        newbasis, fdnrefs = fdn(db, seed, newbasis, newrefs, UUID(oldrefs["fitness"]["id"]))
        for name in ("demand", "nutrition"):
            wrong = {**fdnrefs, name: oldrefs[name]}
            denied = full_request(db, newbasis, wrong, "RESOLUTION", "TRAINING")
            before = snapshot(db, basis.subject_id)
            with pytest.raises((RepositoryTransactionError, PlanningDenied)):
                run(db, identity, denied)
            assert snapshot(db, basis.subject_id) == before
        _, training = action_resolution(db, seed, newbasis, fdnrefs, "TRAINING")
        _, nutrition = action_resolution(db, seed, newbasis, fdnrefs, "NUTRITION")
        fullrefs = {**fdnrefs, "resolution": training, "nutrition_resolution": nutrition}
        newop = full_request(db, newbasis, fullrefs, "VALIDATION")
        for name in ("resolution", "nutrition_resolution"):
            wrong = {**fullrefs, name: oldfull[name]}
            denied = full_request(db, newbasis, wrong, "VALIDATION")
            before = snapshot(db, basis.subject_id)
            with pytest.raises((RepositoryTransactionError, PlanningDenied)):
                run(db, identity, denied)
            assert snapshot(db, basis.subject_id) == before
        readyrefs = prepare_validation(db, seed, newop, fullrefs)
        for name in ("demand", "nutrition", "resolution", "validation"):
            before = snapshot(db, basis.subject_id)
            with pytest.raises((RepositoryTransactionError, PlanningDenied)):
                commit_ready(
                    db, seed, newop, {**readyrefs, name: oldrefs[name]}, "deny-old-" + name
                )
            assert snapshot(db, basis.subject_id) == before
        commit_ready(db, seed, newop, readyrefs)
        after = snapshot(db, basis.subject_id)
        for table in (
            "proposal_revisions",
            "prescription_demand_features",
            "evidence_resolutions",
            "validation_results",
        ):
            assert all(row in after[table] for row in original[table])
        root = after["planning_intents"][0][0]
        oldroot = original["planning_intents"][0][0]
        assert (
            root["deadline"] == oldroot["deadline"]
            and root["typed_payload"] == oldroot["typed_payload"]
        )
        with db.transaction():
            f = db.execute(
                "SELECT typed_payload FROM kineticloop.proposal_revisions WHERE id=%s",
                (UUID(readyrefs["fitness"]["id"]),),
            ).fetchone()[0]
            n = db.execute(
                "SELECT typed_payload FROM kineticloop.proposal_revisions WHERE id=%s",
                (UUID(readyrefs["nutrition"]["id"]),),
            ).fetchone()[0]
        assert (
            f["parent_id"] == oldrefs["fitness"]["id"]
            and f["parent_hash"] == oldrefs["fitness"]["hash"]
            and n["fuel_units"] == 60
        )
        before = snapshot(db, basis.subject_id)
        with pytest.raises((RepositoryTransactionError, PlanningDenied)):
            commit_ready(db, seed, oldop, oldrefs, "deny-old-attempt")
        with pytest.raises(PlanningDenied):
            advance(
                db, identity, replace(newbasis, source_state="COMMIT_READY"), "FITNESS", newrefs
            )
        assert snapshot(db, basis.subject_id) == before
        assert_no_execution(db, basis.subject_id)
        witness(
            "f2_repair",
            same_root=str(basis.intent_id),
            old_attempt=str(basis.attempt_id),
            new_attempt=str(newbasis.attempt_id),
            old_refs=oldfull,
            new_refs=fullrefs,
            immutable_history=True,
            budget_deadline_preserved=True,
        )


@pytest.mark.parametrize("full", [False, True])
def test_legacy_and_no_authority(database_urls: dict[str, str], full: bool) -> None:
    from uuid import uuid5

    seed = seed_source(database_urls, full=full)
    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed)
        if full:
            basis, refs = fdn(db, seed, basis, refs)
            before = snapshot(db, basis.subject_id)
            with pytest.raises(RepositoryTransactionError, match="no downgrade"):
                run(db, seed["identity"], request(basis, refs, "RESOLUTION"))
            assert snapshot(db, basis.subject_id) == before
            _, training = action_resolution(db, seed, basis, refs, "TRAINING")
            _, nutrition = action_resolution(db, seed, basis, refs, "NUTRITION")
            allrefs = {**refs, "resolution": training, "nutrition_resolution": nutrition}
            before = snapshot(db, basis.subject_id)
            with pytest.raises(RepositoryTransactionError, match="no downgrade"):
                run(
                    db,
                    seed["identity"],
                    request(
                        basis,
                        {k: v for k, v in allrefs.items() if k != "nutrition_resolution"},
                        "VALIDATION",
                    ),
                )
            assert snapshot(db, basis.subject_id) == before
            op = full_request(db, basis, allrefs, "VALIDATION")
            readyrefs = prepare_validation(db, seed, op, allrefs)
            commit_ready(db, seed, op, readyrefs)
        else:
            op, readyrefs = legacy_pipeline(db, seed, basis, refs)
            for kind, name in (
                ("FITNESS", "fitness"),
                ("DEMAND", "demand"),
                ("NUTRITION", "nutrition"),
                ("RESOLUTION", "resolution"),
                ("VALIDATION", "validation"),
            ):
                assert readyrefs[name]["id"] == str(
                    uuid5(preparation._NAMESPACE, f"{basis.subject_id}:{basis.attempt_id}:{kind}")
                )
            with db.transaction():
                rows = db.execute(
                    "SELECT typed_payload FROM kineticloop.evidence_resolutions WHERE subject_id=%s",
                    (basis.subject_id,),
                ).fetchall()
                assert (
                    len(rows) == 1
                    and rows[0][0]["action_type"] == "TRAINING"
                    and "contract" not in rows[0][0]
                )
            before = snapshot(db, basis.subject_id)
            fullop = full_request(
                db,
                replace(basis, source_state="VALIDATING"),
                {
                    k: v
                    for k, v in readyrefs.items()
                    if k in {"snapshot", "fitness", "demand", "nutrition"}
                },
                "RESOLUTION",
                "NUTRITION",
            )
            with pytest.raises((RepositoryTransactionError, PlanningDenied)):
                run(db, seed["identity"], fullop)
            assert snapshot(db, basis.subject_id) == before
        before = snapshot(db, basis.subject_id)
        for principal in ("production_subject", "evaluation", "test"):
            with connect(database_urls[principal]) as untrusted:
                with pytest.raises(
                    (RepositoryTransactionError, PlanningDenied, psycopg.Error)
                ) as role_error:
                    run(
                        untrusted,
                        seed["identity"],
                        replace(op, key="denied-principal-" + principal),
                    )
            assert snapshot(db, basis.subject_id) == before
            witness(
                "principal_denial",
                principal=principal,
                error=str(role_error.value),
                zero_effects=True,
            )
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
        assert snapshot(db, basis.subject_id) == before
        assert_no_execution(db, basis.subject_id)
        witness(
            "legacy_no_authority",
            profile=FULL_VERSION if full else VERSION,
            refs=readyrefs,
            exact_legacy_ids=True,
            legacy_fallback_denied=True,
            production_shadow_execution_disabled=True,
            planned_quantities_never_actual=True,
        )


def consumer_denial(
    database_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch, consumer: str
) -> None:
    clock_case = consumer.endswith("_expiry") or consumer == "lease"
    validation_clock = consumer.startswith("validation_")
    source_clock = "source_" in consumer
    runtime_clock = "runtime_" in consumer
    after_clock = consumer.endswith("after_expiry") or consumer == "lease"
    seed = seed_source(
        database_urls,
        admission_seconds=8 if source_clock else None,
        runtime_seconds=8 if runtime_clock else None,
    )
    phase = {
        "ingress": False,
        "current_chain": False,
        "current_live": False,
        "fence_guard": False,
        "full_consumer": False,
    }
    original_ingress = RepositoryTransaction.require_progress_ingress
    original_chain = RepositoryTransaction._prepare_current_progress
    original_full = preparation._verify_full_progress
    original_fence = RepositoryTransaction.require_current_fence

    def ingress(tx: Any, identity: Any) -> Any:
        result = original_ingress(tx, identity)
        phase["ingress"] = True
        return result

    def chain(tx: Any, identity: Any, request: Any) -> Any:
        phase["current_chain"] = True
        result = original_chain(tx, identity, request)
        phase["current_live"] = True
        return result

    def full_consumer(*args: Any) -> Any:
        phase["full_consumer"] = True
        return original_full(*args)

    def fence_guard(tx: Any, *args: Any, **kwargs: Any) -> Any:
        phase["fence_guard"] = True
        return original_fence(tx, *args, **kwargs)

    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed, lease_seconds=3 if consumer in {"lease", "takeover"} else 600)
        op, fullrefs = preparation_chain(db, seed, basis, refs)
        ready: Any = None if validation_clock else prepare_validation(db, seed, op, fullrefs)
        if consumer == "resolution_swap":
            ready = {**ready, "resolution": fullrefs["nutrition_resolution"]}
        elif consumer.startswith("foreign_"):
            name = consumer.removeprefix("foreign_")
            ready = {**ready, name: {"id": str(uuid4()), "hash": ready[name]["hash"]}}
        elif consumer == "runtime_revoked":
            revoke_runtime(database_urls, seed)
        elif consumer == "manifest":
            identity = seed["identity"]
            owner = PreparationService(
                db,
                ExecutionIdentity(
                    identity.actor,
                    identity.subject_id,
                    identity.policy_id,
                    identity.environment_id,
                    identity.principal,
                ),
            )
            build = owner.build_manifest(
                BuildManifest(
                    "consumer-new-manifest",
                    seed["source"],
                    (ProjectionBinding("EXPOSURE", UUID(seed["projection"]["projection_id"])),),
                    (seed["engine"].artifact_id,),
                )
            )
            manifest = owner.complete_manifest(CompleteManifest(UUID(build["build_id"])))
            publish(db, seed, seed["source"], manifest, "consumer-new-manifest-publication")
        elif consumer == "attempt":
            # Negative mutable current-pointer control; never creates an attempt/output.
            with db.transaction():
                db.execute(
                    "UPDATE kineticloop.planning_intents SET current_attempt_id=NULL WHERE id=%s",
                    (basis.intent_id,),
                )
        elif consumer == "fence":
            op = replace(op, fence=op.fence + 1)
        elif consumer == "takeover":
            with db.transaction():
                lease_end = db.execute(
                    "SELECT lease_expires_at FROM kineticloop.planning_intents WHERE id=%s",
                    (basis.intent_id,),
                ).fetchone()[0]
            wait_db_time(db, lease_end)
            acquired_lease = LeaseService(
                db, PlanningIdentity(RoleIdentity(str(uuid4()), ActorRole.TEST), basis.subject_id)
            ).acquire_lease(
                AcquireLease(
                    basis.subject_id,
                    "consumer-takeover",
                    basis.intent_id,
                    seed["identity"].key,
                    basis.fence,
                    basis.request_revision,
                    basis.attempt_id,
                    600,
                )
            )
            assert acquired_lease["fence"] > basis.fence
        elif consumer in {"epoch", "execution_basis"}:
            if consumer == "epoch":
                actual_input(db, seed, uuid4())
            else:
                # Persist a real noninvalidating publication event, then move only the mutable exposure basis.
                with db.transaction():
                    event = db.execute(
                        "SELECT id FROM kineticloop.domain_events WHERE subject_id=%s AND event_type='MANIFEST_PUBLISHED'",
                        (basis.subject_id,),
                    ).fetchone()[0]
                    db.execute(
                        "UPDATE kineticloop.user_decision_state SET execution_basis_event_id=%s WHERE subject_id=%s",
                        (event, basis.subject_id),
                    )
        elif consumer == "revision":
            LeaseService(
                db, PlanningIdentity(seed["identity"].actor, basis.subject_id)
            ).admit_or_revise(
                AdmitOrReviseIntent(
                    basis.subject_id,
                    "consumer-revise",
                    date.today(),
                    "TRAINING",
                    "test:UTC-v1",
                    {"equipment": [], "minutes": 20},
                )
            )
        elif consumer == "control":
            apply_control(db, seed)
        elif consumer == "deadline":
            with db.transaction():
                db.execute(
                    "UPDATE kineticloop.planning_intents SET deadline=clock_timestamp()-interval '1 second' WHERE id=%s",
                    (basis.intent_id,),
                )
        before = snapshot(db, basis.subject_id)
        monkeypatch.setattr(RepositoryTransaction, "require_progress_ingress", ingress)
        monkeypatch.setattr(RepositoryTransaction, "_prepare_current_progress", chain)
        monkeypatch.setattr(preparation, "_verify_full_progress", full_consumer)
        monkeypatch.setattr(RepositoryTransaction, "require_current_fence", fence_guard)
        if clock_case:
            with db.transaction():
                now = db.execute("SELECT clock_timestamp()").fetchone()[0]
                manifest_end = db.execute(
                    "SELECT valid_until FROM kineticloop.decision_manifests WHERE id=%s",
                    (basis.manifest_id,),
                ).fetchone()[0]
                lease_end, root_end = db.execute(
                    "SELECT lease_expires_at,deadline FROM kineticloop.planning_intents WHERE id=%s",
                    (basis.intent_id,),
                ).fetchone()
                expiry = (
                    lease_end
                    if consumer == "lease"
                    else seed["admission_end" if source_clock else "runtime_end"]
                )
                assert now < expiry < min(manifest_end, root_end)
                if consumer != "lease":
                    assert expiry < lease_end
                    persisted = db.execute(
                        "SELECT resolution_expires_at FROM kineticloop.evidence_resolutions WHERE subject_id=%s",
                        (basis.subject_id,),
                    ).fetchall()
                    assert len(persisted) == 2 and all(row[0] == expiry for row in persisted)
                    if not validation_clock:
                        assert (
                            db.execute(
                                "SELECT valid_until FROM kineticloop.validation_results WHERE id=%s",
                                (UUID(ready["validation"]["id"]),),
                            ).fetchone()[0]
                            == expiry
                        )
            with connect(database_urls["admin"]) as blocker:
                blocker.execute(
                    "SELECT id FROM kineticloop.planning_attempts WHERE id=%s FOR UPDATE",
                    (basis.attempt_id,),
                )
                name = "kl079-consumer-" + consumer

                def worker() -> Any:
                    with connect(database_urls["admin"], application_name=name) as connection:
                        if validation_clock:
                            return run(connection, seed["identity"], op)
                        return commit_ready(connection, seed, op, ready, name)

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(worker)
                    blocked = observe_blocked(database_urls["admin"], name)
                    crossed = wait_db_time(db, expiry) if after_clock else now
                    blocker.commit()
                    if after_clock:
                        with pytest.raises((RepositoryTransactionError, PlanningDenied)) as error:
                            future.result(timeout=8)
                    else:
                        result = future.result(timeout=8)
                        if validation_clock:
                            output = assert_full_output(db, seed, op, result)
                            assert output.valid_until == expiry.isoformat()
                        else:
                            assert result["state"] == "COMMIT_READY"
            assert phase["ingress"] and phase["current_chain"]
            if consumer != "lease":
                assert phase["current_live"]
                if not validation_clock:
                    assert phase["full_consumer"]
            with db.transaction():
                checked_at = db.execute("SELECT clock_timestamp()").fetchone()[0]
            assert checked_at < min(manifest_end, root_end)
            if consumer != "lease":
                assert checked_at < lease_end
            witness(
                "consumer_clock",
                case=consumer,
                expiry=expiry,
                observed=crossed,
                manifest_valid_until=manifest_end,
                lease_expires_at=lease_end,
                root_deadline=root_end,
                source_valid_until=seed["admission_end"],
                runtime_valid_until=seed["runtime_end"],
                blocking_pids=blocked[1],
                post_lock=True,
                **phase,
            )
            if not after_clock:
                assert_no_execution(db, basis.subject_id)
                return
        else:
            with pytest.raises((RepositoryTransactionError, PlanningDenied)) as error:
                commit_ready(db, seed, op, ready, "consumer-denial-" + consumer)
        assert snapshot(db, basis.subject_id) == before
        assert_no_execution(db, basis.subject_id)
        assert phase["ingress"]
        if consumer in {"manifest", "lease"}:
            assert phase["current_chain"] and not phase["current_live"]
        if consumer in {"attempt", "fence", "takeover"}:
            assert phase["fence_guard"] and not phase["current_live"]
        witness(
            "consumer_denial",
            dimension=consumer,
            error=str(error.value),
            zero_effects=True,
            stage="FULL_VALIDATION_OWNER" if validation_clock else "ACTUAL_COMMIT_READY_OWNER",
            **phase,
        )
