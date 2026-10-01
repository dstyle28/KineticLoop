from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

import kineticloop.persistence.deterministic_planning as preparation
from kineticloop.contracts.commands import (
    CommitBundle,
    ContinueSession,
    ResumeSession,
    StartSession,
)
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
)
from kineticloop.protocol.execution import (
    ExecutionIdentity,
    FullCommitRequest,
    OrdinaryPause,
    PublishReady,
    binding_digest,
    digest,
)
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
from kineticloop.workflow.planning import PlanningDenied
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


U = load("kl027_namespace", "tests/unit/protocol/test_test_only_demo.py")
M = load("kl027_bootstrap", "tests/db/test_migrations.py")
KINDS = tuple(OWNERS)
CALL_BOUNDS: dict[str, tuple[datetime, datetime]] = {}
TABLES = (
    "canonical_fact_revisions",
    "admission_decisions",
    "planning_quota_buckets",
    "authorization_artifact_closure",
    "authorization_events",
    "control_events",
    "control_heads",
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
    expected = U.fixture_namespace(ROOT, current_head())
    if urlparse(url).path != "/" + expected.database_name:
        raise ValueError("foreign KL027 database URL")
    db = psycopg.connect(url, options="-c statement_timeout=12000 -c lock_timeout=10000", **kwargs)
    with db.transaction():
        assert db.execute("SELECT current_database()").fetchone() == (expected.database_name,)
    return db


@pytest.fixture
def database_urls() -> Any:
    U.test_namespace_and_boundary(
        Path("/private/tmp/kl027-peer-root")
        if sys.platform == "darwin"
        else Path("/tmp/kl027-peer-root")
    )
    lifecycle = U.OwnedLifecycle(ROOT, current_head())
    selected = lifecycle.namespace
    start = time.monotonic()
    try:
        urls = lifecycle.bootstrap(M.bootstrap_two_phase)
        with connect(urls["admin"]) as db:
            assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
                M.HEAD_REVISION,
            )
        witness(
            "namespace",
            tested_commit=current_head(),
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
        witness(
            "cleanup",
            compose=selected.project_name,
            database=selected.database_name,
            inventory=lifecycle.inventory,
            remaining=remaining,
            elapsed=time.monotonic() - start,
        )


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
    audit = snapshot(db, subject)
    sealed = audit["factset_revisions"][0][0]
    assert sealed["status"] == "SEALED" and sealed["id"] == str(factset_id)
    assert sealed["membership_digest"] == complete["membership_digest"]
    assert sealed["member_revision"] == sealed["completed_member_revision"] == len(members)
    assert sealed["typed_payload"]["completion_certificate"] == complete["completion_certificate"]
    membership = {r[0]["member_kind"]: r[0] for r in audit["factset_members"]}
    for kind, ref, expected in (
        ("ASSOCIATION", "ref_s12_id", seed["association"]),
        ("ADMISSION", "ref_s13_id", seed["admission"]),
        ("FACT", "ref_s14_id", seed["fact"]),
    ):
        assert membership[kind][ref] == str(expected)
        assert membership[kind]["ref_s15_id"] == str(factset_id)
        assert membership[kind]["action_scope"] == "TEST_ONLY"
    projection_row = audit["projection_versions"][0][0]
    assert projection_row["id"] == projection["projection_id"]
    assert projection_row["input_basis_hash"] == projection["input_basis_hash"]
    assert projection_row["content_hash"] == digest(projection_row["typed_payload"]["result"])
    assert {r[0]["id"] for r in audit["projection_dependencies"]} == set(
        projection["dependency_ids"]
    )
    manifest = audit["decision_manifests"][0][0]
    assert (
        manifest["id"] == result["manifest_id"]
        and manifest["generation"] == result["generation"] == 1
    )
    assert manifest["ref_s15_id"] == str(factset_id) and manifest["ref_s23_id"] == ready["build_id"]
    assert manifest["ref_s05_id"] == str(identity.policy_id) and manifest["ref_s06_id"] == str(
        seed["program"]
    )
    assert (
        manifest["captured_epoch"] == source.epoch
        and manifest["input_frontier_hash"] == source.frontier
    )
    assert manifest["manifest_hash"] == ready["manifest_hash"]
    assert (
        manifest["typed_payload"]["artifact_dependency_closure_hash"]
        == ready["artifact_dependency_closure_hash"]
    )
    assert audit["user_decision_state"][0][0]["current_manifest_id"] == manifest["id"]
    assert_event(db, seed, result)
    seed.update(source=source, projection=projection, ready=ready, manifest=result)
    witness("sealed_source_and_published_basis", complete=complete, persisted=audit)
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
    result = PlanningWorkflowService(db, identity).advance_attempt(
        AdvanceAttempt(**asdict(basis), target_state=target, sources=refs, failure_code=failure)
    )
    witness("forward_stage", basis=asdict(basis), target=target, sources=refs, result=result)
    return result


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
            seed["now"].date(),
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
        assert_legacy_output(db, seed, operation, output)
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
    receipts = [r[0] for r in result["command_receipts"]]
    events = [r[0] for r in result["domain_events"]]
    outbox = [r[0] for r in result["outbox_deliveries"]]
    for receipt in receipts:
        assert receipt["status"] == "SUCCEEDED"
        linked = [e for e in events if e["ref_s02_id"] == receipt["id"]]
        assert len(linked) == 1, receipt
        assert len([o for o in outbox if o["ref_s03_id"] == linked[0]["id"]]) == 1
    assert len(receipts) == len(events) == len(outbox)
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
        command, f"test:kl027-runtime-{artifact}", FULL_VERSION, validity
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
            time.sleep(0.01)
    raise AssertionError("bounded observed lock waiter missing")


def wait_db_time(db: Any, end: Any) -> Any:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        with db.transaction():
            now = db.execute("SELECT clock_timestamp()").fetchone()[0]
        if now > end:
            return now
        time.sleep(0.01)
    raise AssertionError("bounded actual trusted clock crossing missing")


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

    before = snapshot(db, subject)
    execute_command(db, "ApplyControl", subject, operation)
    after = snapshot(db, subject)
    oldepoch = before["user_decision_state"][0][0]["authorization_epoch"]
    assert after["user_decision_state"][0][0]["authorization_epoch"] == oldepoch + 1
    assert after["user_decision_state"][0][0]["last_control_event_id"] == str(control)
    assert after["control_heads"][0][0]["ref_s17_id"] == str(control)
    assert after["control_events"][0][0]["ref_s02_id"] == str(receipt)
    invalidation = next(
        r[0] for r in after["authorization_events"] if r[0].get("ref_s17_id") == str(control)
    )
    assert invalidation["invalidated_epoch"] == oldepoch + 1 and invalidation["ref_s02_id"] == str(
        receipt
    )
    witness(
        "ApplyControl_locked_current_epoch",
        old_epoch=oldepoch,
        new_epoch=oldepoch + 1,
        control=control,
        receipt=receipt,
        persisted=after,
    )


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
    missing_required_evidence: bool = False,
    policy_overrides: Any = None,
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
        if missing_required_evidence:
            config["required_members"].append(str(uuid4()))
        runtime_version = FULL_VERSION if full else VERSION
        runtime_hash = digest({"version": FULL_VERSION, "rules": RULES}) if full else digest(RULES)
        deps = (
            Dependency("COLLECTION", "fixture-facts", "all-fixture-facts-and-absence:v1"),
            Dependency("ENGINE", f"test:kl027-engine-{subject}:1"),
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
                "deadline_seconds": deadline_seconds,
                "calendar_policies": ["test:UTC-v1"],
                "root_limits": {"calls": 3, "tokens": 1000, "tools": 10},
            },
            "execution_calendar": {"policy": "test:UTC-v1", "timezone": "UTC"},
            "authorization_action_scopes": {"TRAINING": "TEST_ONLY"},
            "t2_invalidation_scopes": {
                "RecordActualExecution": "TEST_ONLY",
                "ApplyControl": "TEST_ONLY",
                "AcceptFactRevision": "TEST_ONLY",
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
        body.update(policy_overrides or {})
        db.execute(
            "INSERT INTO kineticloop.policy_bundles(id,subject_id,policy_namespace,policy_version,content_hash,typed_payload) VALUES (%s,%s,'test:kl027','1',%s,%s)",
            (policy_id, subject, digest(body), Jsonb(body)),
        )
        db.execute(
            "INSERT INTO kineticloop.program_versions(id,subject_id,program_identity,program_revision) VALUES (%s,%s,'test:kl027',1)",
            (program, subject),
        )
        db.execute(
            "INSERT INTO kineticloop.user_decision_state(subject_id,input_frontier_hash,active_policy_bundle_id,active_program_id) VALUES (%s,%s,%s,%s)",
            (subject, digest("registered-source"), policy_id, program),
        )
        db.execute(
            "INSERT INTO kineticloop.evidence_revisions(id,subject_id,source_connection_identity,source_object_type,source_object_identity,source_revision,trust_class,source_class,command_authority) VALUES (%s,%s,'kl027-test','actual','fixture-actual','1','USER_REPORTED','USER','NONE')",
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
            "INSERT INTO kineticloop.evaluation_releases(id,subject_id,release_namespace,release_version,content_hash) VALUES (%s,%s,'test:kl027','1',%s)",
            (release, subject, digest("fixture-release")),
        )
        for artifact, kind, name, version, artifact_hash, payload, policy_ref, release_ref in (
            (
                engine,
                "POLICY_BUNDLE",
                f"test:kl027-engine-{subject}",
                "1",
                digest(body),
                {},
                policy_id,
                None,
            ),
            (
                runtime,
                "RUNTIME",
                f"test:kl027-runtime-{subject}",
                VERSION,
                digest(RULES),
                {"operation": "DETERMINISTIC_TEST_PREPARATION", "version": VERSION},
                None,
                release,
            ),
            (
                builder,
                "RUNTIME",
                f"test:kl027-builder-{subject}",
                "1",
                digest("context-builder"),
                {"operation": "CONTEXT_BUILDER"},
                None,
                release,
            ),
            (
                release_artifact,
                "PROMPT",
                f"test:kl027-release-{subject}",
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
            engine, "POLICY_BUNDLE", f"test:kl027-engine-{subject}", "1", digest(body)
        ),
    }
    with connect(urls["admin"]) as db:
        actual_input(db, seed, fact)
    with connect(urls["admin"]) as db:
        audit = snapshot(db, subject)
        for table in TABLES:
            if table not in {
                "user_decision_state",
                "canonical_fact_revisions",
                "admission_decisions",
                "command_receipts",
                "domain_events",
                "outbox_deliveries",
                "authorization_events",
            }:
                assert audit[table] == [], ("target output seeded", table)
        factrow = audit["canonical_fact_revisions"][0][0]
        assert factrow["ref_s13_id"] == str(admission) and factrow["ref_s10_id"] == str(assertion)
        assert factrow["content_hash"] == digest(factrow["typed_payload"])
        assert factrow["typed_payload"]["semantic_class"] == "ACTUAL_EXECUTION"
        assert audit["admission_decisions"][0][0]["decision"] == "ADMITTED"
        witness(
            "admitted_inputs_only",
            subject=subject,
            policy=policy_id,
            environment=environment,
            persisted=audit,
        )
    return seed


def ready(urls: Any, *, lease_seconds: int = 600, **kwargs: Any) -> tuple[Any, Any]:
    seed = seed_source(urls, **kwargs)
    with connect(urls["admin"]) as db:
        upstream(db, seed)
        basis, refs = begin(db, seed, lease_seconds=lease_seconds)
        op, fullrefs = preparation_chain(db, seed, basis, refs)
        refs = prepare_validation(db, seed, op, fullrefs)
        commit_ready(db, seed, op, refs)
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
    command = U.wire(
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
    witness(
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
    return U.wire(
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
    witness("atomic_receipt_event_outbox", result=result, row=row)


def denied(db: Any, seed: Any, operation: Any, cause: str, label: str) -> str:
    before = snapshot(db, auth(seed).subject_id)
    with pytest.raises((RepositoryTransactionError, psycopg.Error, ValueError)) as error:
        operation()
    message = str(error.value)
    assert cause in message, (label, cause, message)
    assert snapshot(db, auth(seed).subject_id) == before
    witness(
        "exact_zero_effect_denial",
        label=label,
        intended_cause=cause,
        actual_cause=message,
        persisted=before,
    )
    return message


def test_full_trajectory(database_urls: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[Any] = []
    original = RepositoryTransaction.evaluate_execution_authorization

    def observe_guard(tx: RepositoryTransaction, **values: Any) -> Any:
        decision = original(tx, **values)
        observed.append(decision)
        witness(
            "real_T7_current_eligibility_before_mutation",
            command=tx.command_kind,
            subject=tx.subject_id,
            identities=values,
            decision=asdict(decision),
        )
        return decision

    monkeypatch.setattr(RepositoryTransaction, "evaluate_execution_authorization", observe_guard)
    seed, request = ready(database_urls)
    with connect(database_urls["admin"]) as db:
        before = snapshot(db, auth(seed).subject_id)
        result = service(db, seed).commit_full(request)
        after = snapshot(db, auth(seed).subject_id)
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
            certificate = row[8]
            assert (
                certificate["authorization_epoch"] == request.command.expected_authorization_epoch
            )
            assert (
                certificate["closure_digest"]
                == digest(certificate["dependencies"])
                == result["artifact_dependency_closure_hash"]
            )
            assert row[9] == min(
                datetime.fromisoformat(d["valid_until"])
                for d in certificate["dependencies"]
                if d.get("valid_until") is not None
            )
            assert {
                d["identity"]
                for d in certificate["dependencies"]
                if d["dependency_kind"] == "EVIDENCE_ADMISSION_FRESHNESS"
            } == {str(seed["admission"])}
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
            assert observed[-1].is_executable and observed[-1].non_bearer
            assert_event(db, seed, started)
        original_start = current_binding(db, seed, started["session_id"])
        service(db, seed).pause(pause_request(db, seed, started["session_id"]))
        before_resume = snapshot(db, auth(seed).subject_id)
        resumed = service(db, seed).resume(
            session_command(
                seed,
                result,
                ResumeSession,
                session_id=started["session_id"],
                binding=original_start,
                member=1,
            )
        )
        assert resumed["executable"]
        assert_event(db, seed, resumed)
        resume_binding = current_binding(db, seed, started["session_id"])
        assert (
            resume_binding["binding_kind"] == "RESUME" and resume_binding["binding_revision"] == 2
        )
        after_resume = snapshot(db, auth(seed).subject_id)
        for table in (
            "proposal_revisions",
            "prescription_demand_features",
            "evidence_resolutions",
            "validation_results",
            "daily_bundle_revisions",
            "prescription_revisions",
            "bundle_prescription_members",
            "authorization_issuances",
            "authorization_artifact_closure",
        ):
            assert after_resume[table] == before_resume[table]
        assert original_start in [r[0] for r in after_resume["execution_bindings"]]
        assert (
            len(after_resume["execution_bindings"]) == len(before_resume["execution_bindings"]) + 1
        )
        assert original_start["ref_s42_id"] == resume_binding["ref_s42_id"]
        witness(
            "positive_ordinary_pause_resume",
            start=original_start,
            resume=resume_binding,
            result=resumed,
        )
        witness(
            "full_commit",
            result=result,
            persisted=after,
            exact_two_members=True,
            immutable_upstream=True,
        )


@pytest.mark.parametrize("mode", ["CONTINUE", "RESUME", "START"])
@pytest.mark.parametrize("change", ["positive", "STOP", "artifact"])
def test_revoke_then_deny(database_urls: Any, mode: str, change: str) -> None:
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
            witness(
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
            local_date=seed["now"].date(),
            session_id=UUID(started["session_id"]),
            prescription_id=UUID(command.prescription_id),
            authorization_id=UUID(command.authorization_id),
            execution_scope="TEST_ONLY",
        )
        assert eligible.is_executable and eligible.non_bearer
        witness(
            "lifecycle_current_preconditions",
            mode=mode,
            lifecycle=lifecycle,
            immutable_binding=initial_binding,
            eligibility_observed_at=eligible.observed_at,
            non_bearer=True,
            fresh_key=command.idempotency_key,
            distinct_absent_start=mode == "START",
            eligibility_session=started["session_id"],
            eligibility_observation="exact same P/A through existing lifecycle; fresh absent START rechecks in its own guard",
        )
        before_authority_loss = snapshot(db, auth(seed).subject_id)
        if change in {"STOP", "artifact"}:
            if change == "STOP":
                apply_control(db, seed)
            else:
                revoke_runtime(database_urls, seed)
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
                "KL_REGISTRY_AUTHORIZATION_INELIGIBLE"
                if change == "STOP"
                else "KL_REGISTRY_ARTIFACT_REVOKED",
                mode + "-" + change,
            )
        elif change == "expiry":
            with db.transaction():
                expiry = db.execute(
                    "SELECT valid_until FROM kineticloop.authorization_issuances WHERE id=%s",
                    (UUID(command.authorization_id),),
                ).fetchone()[0]
                assert expiry == seed["admission_end"]
            wait_db_time(db, expiry)
            denied(
                db,
                seed,
                lambda: method(command),
                "KL_REGISTRY_AUTHORIZATION_INELIGIBLE",
                mode + "-expiry",
            )
        else:
            before = snapshot(db, auth(seed).subject_id)
            output = method(command)
            assert output["executable"] and not output["replayed"]
            assert_event(db, seed, output)
            after = snapshot(db, auth(seed).subject_id)
            for table in (
                "proposal_revisions",
                "prescription_demand_features",
                "evidence_resolutions",
                "validation_results",
                "daily_bundle_revisions",
                "prescription_revisions",
                "bundle_prescription_members",
                "authorization_issuances",
                "authorization_artifact_closure",
            ):
                assert after[table] == before[table]
            assert initial_binding in [row[0] for row in after["execution_bindings"]]
            assert len(after["execution_bindings"]) - len(before["execution_bindings"]) == (
                0 if mode == "CONTINUE" else 1
            )
            if mode == "RESUME":
                latest = current_binding(db, seed, started["session_id"])
                assert latest["binding_kind"] == "RESUME" and latest["binding_revision"] == 2
                state = snapshot(db, auth(seed).subject_id)
                assert pause is not None
                replay = service(db, seed).pause(pause)
                assert (
                    replay["replayed"]
                    and replay["execution_revision"] == 2
                    and snapshot(db, auth(seed).subject_id) == state
                )
            historical = method(command)
            assert historical["replayed"] and not historical["executable"]
            witness(
                "current_T7",
                mode=mode,
                start_binding=initial_binding,
                result=output,
                persisted=after,
            )
        if change != "positive":
            loss_eligibility = query_execution_eligibility(
                db,
                command_kind=model.__name__,
                subject_id=auth(seed).subject_id,
                artifact_ids=[a.artifact_id for a in artifacts],
                artifact_identities=artifacts,
                local_date=seed["now"].date(),
                session_id=UUID(command.session_id),
                prescription_id=UUID(command.prescription_id),
                authorization_id=UUID(command.authorization_id),
                execution_scope="TEST_ONLY",
            )
            assert not loss_eligibility.is_executable
            historical = snapshot(db, auth(seed).subject_id)
            for table in (
                "canonical_fact_revisions",
                "factset_revisions",
                "factset_members",
                "decision_manifests",
                "decision_snapshots",
                "proposal_revisions",
                "prescription_demand_features",
                "evidence_resolutions",
                "validation_results",
                "daily_bundle_revisions",
                "prescription_revisions",
                "bundle_prescription_members",
                "authorization_issuances",
                "authorization_artifact_closure",
                "execution_bindings",
                "workout_sessions",
            ):
                assert historical[table] == before_authority_loss[table], (change, mode, table)
            replay_start = service(db, seed).start(start_command)
            replay_bundle = service(db, seed).commit_full(request)
            assert replay_start["replayed"] and not replay_start["executable"]
            assert replay_bundle["replayed"] and not replay_bundle["executable"]
            assert replay_start["binding_id"] == started["binding_id"]
            assert replay_bundle["bundle_id"] == result["bundle_id"]
            assert snapshot(db, auth(seed).subject_id) == historical
            assert initial_binding in [r[0] for r in historical["execution_bindings"]]
            witness(
                "historical_identity_only",
                loss=change,
                mode=mode,
                start=replay_start,
                bundle=replay_bundle,
                zero_effects=True,
            )


@pytest.mark.parametrize("mode", ["CONTINUE", "RESUME", "START"])
def test_expiry_then_deny(database_urls: Any, mode: str) -> None:
    test_revoke_then_deny(database_urls, mode, "expiry")


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
        before = snapshot(db, auth(seed).subject_id)
        before_wait = wait_db_time(db, seed["admission_end"] - timedelta(seconds=0.5))
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
                    database_urls["admin"], application_name="kl027-expiry-waiter"
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
                observed = observe_blocked(database_urls["admin"], "kl027-expiry-waiter")
                # Reader is independent of blocked coordination transactions.
                with connect(database_urls["admin"]) as clock:
                    after_time = wait_db_time(clock, seed["admission_end"])
                blocker.commit()
                message = future.result(timeout=12)
        assert "expired" in message if operation == "T6" else "TIME_INELIGIBLE" in message, message
        assert snapshot(db, auth(seed).subject_id) == before
        witness(
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


def test_fdn_repair(database_urls: dict[str, str]) -> None:
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
                seed["now"].date(),
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
            rejected = full_request(db, newbasis, wrong, "RESOLUTION", "TRAINING")
            before = snapshot(db, basis.subject_id)
            with pytest.raises((RepositoryTransactionError, PlanningDenied)):
                run(db, identity, rejected)
            assert snapshot(db, basis.subject_id) == before
        _, training = action_resolution(db, seed, newbasis, fdnrefs, "TRAINING")
        _, nutrition = action_resolution(db, seed, newbasis, fdnrefs, "NUTRITION")
        fullrefs = {**fdnrefs, "resolution": training, "nutrition_resolution": nutrition}
        newop = full_request(db, newbasis, fullrefs, "VALIDATION")
        for name in ("resolution", "nutrition_resolution"):
            wrong = {**fullrefs, name: oldfull[name]}
            rejected = full_request(db, newbasis, wrong, "VALIDATION")
            before = snapshot(db, basis.subject_id)
            with pytest.raises((RepositoryTransactionError, PlanningDenied)):
                run(db, identity, rejected)
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
        sources = {**readyrefs, "nutrition_resolution": fullrefs["nutrition_resolution"]}
        repaired = commit_request(db, seed, newbasis, sources)
        for name in ("fitness", "demand", "nutrition", "resolution", "validation"):
            mixed = {**sources, name: oldrefs[name]}
            command = changed(
                repaired.command,
                result_fingerprint=digest({"contract": FULL_VERSION, "sources": mixed}),
                **({"validation_id": mixed[name]["id"]} if name == "validation" else {}),
            )
            denied(
                db,
                seed,
                lambda: service(db, seed).commit_full(FullCommitRequest(command, mixed)),
                "earlier immutable prerequisite",
                "F2-mixed-commit-" + name,
            )
        result = service(db, seed).commit_full(repaired)
        assert_event(db, seed, result)
        assert service(db, seed).start(session_command(seed, result))["executable"]
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


@pytest.mark.parametrize(
    "case",
    [
        "identity_principal",
        "identity_environment",
        "identity_policy",
        "identity_subject",
        "identity_production_role",
        "identity_evaluation_role",
        "identity_shadow",
        "identity_production_scope",
        "identity_production_connection",
        "identity_evaluation_connection",
        "identity_test_connection",
        "identity_missing_snapshot",
        "identity_missing_nutrition",
        "identity_missing_validation",
        "input_revision",
        "context_missing_evidence",
        "context_mandatory_context",
        "context_fixture_policy",
        "context_shadow_policy",
        "context_production_policy",
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
        "control",
        "runtime_revocation",
        "missing_nutrition",
        "reordered",
        "foreign_certificate",
        "wrong_action",
        "wrong_proposal",
        "current_manifest",
    ],
)
def test_production_shadow_denials(database_urls: Any, case: str) -> None:
    if case == "input_revision":
        scope_input_revision(database_urls)
        return
    if case.startswith("identity_"):
        scope_identity(database_urls, case.removeprefix("identity_"))
        return
    if case.startswith("context_"):
        missing_upstream_context(database_urls, case.removeprefix("context_"))
        return
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
                command, result_fingerprint=digest({"contract": FULL_VERSION, "sources": sources})
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
        elif case == "control":
            apply_control(db, seed)
            cause = "KL_REGISTRY_AUTHORIZATION_INELIGIBLE"
        elif case == "runtime_revocation":
            revoke_runtime(database_urls, seed)
            cause = "KL_REGISTRY_ARTIFACT_REVOKED"
        elif case == "resolution_expiry":
            wait_db_time(db, seed["admission_end"])
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
                    result_fingerprint=digest({"contract": FULL_VERSION, "sources": sources}),
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
            publish(db, seed, seed["source"], complete, "replace-publication")
            cause = "current"
        denied(db, seed, operation, cause, case)


def scope_identity(database_urls: Any, case: str) -> None:
    seed, request = ready(database_urls)
    with connect(database_urls["admin"]) as db:
        result = service(db, seed).commit_full(request)
        command = session_command(seed, result)
        before = snapshot(db, auth(seed).subject_id)
        identity = auth(seed)
        if case in {"principal", "environment", "policy", "subject"}:
            fields = {
                "principal": "principal",
                "environment": "environment_id",
                "policy": "policy_id",
                "subject": "subject_id",
            }
            values: dict[str, Any] = {
                fields[case]: "kl_test_subject_2_login" if case == "principal" else uuid4()
            }
            identity = replace(identity, **values)
            denied(
                db,
                seed,
                lambda: ProtocolExecutionService(db, identity).start(command),
                "authenticated TEST registration mismatch"
                if case == "principal"
                else "binding mismatch",
                case,
            )
        elif case in {"production_role", "evaluation_role"}:
            role = ActorRole.SUBJECT if case == "production_role" else ActorRole.EVALUATION
            with pytest.raises(ValueError, match="authenticated TEST identity"):
                replace(identity, actor=RoleIdentity(str(uuid4()), role))
        elif case in {"shadow", "production_scope"}:
            payload = command.model_dump(mode="json")
            payload["authorization_scope"]["scope"] = "shadow" if case == "shadow" else "production"
            with pytest.raises(ValueError):
                StartSession.model_validate_json(json.dumps(payload))
        elif case.endswith("connection"):
            principal = {
                "production_connection": "production_subject",
                "evaluation_connection": "evaluation",
                "test_connection": "test",
            }[case]
            with connect(database_urls[principal]) as foreign:
                with pytest.raises(
                    (RepositoryTransactionError, psycopg.Error, ValueError)
                ) as error:
                    ProtocolExecutionService(foreign, identity).start(command)
            witness("foreign_principal_no_capability", principal=principal, cause=str(error.value))
        else:
            sources = dict(request.sources)
            sources.pop(case.removeprefix("missing_"))
            with pytest.raises(ValueError, match="exact full"):
                FullCommitRequest(request.command, sources)
        assert snapshot(db, auth(seed).subject_id) == before
        assert before["workout_sessions"] == before["execution_bindings"] == []
        witness(
            "scope_non_executable",
            case=case,
            attempted_session=command.session_id,
            no_new_authority=True,
            no_new_session=True,
            preserved_test_bundle=result,
        )


def missing_upstream_context(database_urls: Any, case: str) -> None:
    overrides = {
        "missing_evidence": {},
        "mandatory_context": {"planning_context": {}},
        "fixture_policy": {"fixture_runtime": {}},
        "shadow_policy": {
            "authorization_action_scopes": {"TRAINING": "SHADOW", "NUTRITION": "SHADOW"}
        },
        "production_policy": {
            "authorization_action_scopes": {"TRAINING": "PRODUCTION", "NUTRITION": "PRODUCTION"}
        },
    }[case]
    seed = seed_source(
        database_urls,
        policy_overrides=overrides,
        missing_required_evidence=case == "missing_evidence",
    )
    with connect(database_urls["admin"]) as db:
        upstream(db, seed)
        if case in {"shadow_policy", "production_policy"}:
            before = snapshot(db, auth(seed).subject_id)
            with pytest.raises(
                RepositoryTransactionError,
                match="current root action must have exact TEST_ONLY policy scope",
            ) as error:
                begin(db, seed)
            after = snapshot(db, auth(seed).subject_id)
            for table in (
                "factset_revisions",
                "factset_members",
                "projection_versions",
                "decision_manifests",
                "daily_plan_heads",
                "authorization_issuances",
                "execution_bindings",
                "workout_sessions",
            ):
                assert before[table] == after[table]
            witness(
                "policy_scope_rejects_forward_stage",
                cause=str(error.value),
                preceding_legal_admission_lease=True,
                persisted=after,
            )
        elif case == "missing_evidence":
            basis, refs = begin(db, seed)
            operation, refs = preparation_chain(db, seed, basis, refs)
            denied(
                db,
                seed,
                lambda: prepare_validation(db, seed, operation, refs),
                "missing/contradictory/incomplete/truncated/mismatched/expired resolution",
                case,
            )
        elif case == "mandatory_context":
            before = snapshot(db, auth(seed).subject_id)
            with pytest.raises(
                RepositoryTransactionError, match="all mandatory policy context blocks required"
            ):
                begin(db, seed)
            # Admission and legal preceding stages persist, but snapshot/authorities do not.
            after = snapshot(db, auth(seed).subject_id)
            for table in (
                "decision_snapshots",
                "proposal_revisions",
                "validation_results",
                "daily_plan_heads",
                "authorization_issuances",
                "execution_bindings",
            ):
                assert after[table] == before[table] == []
        else:
            basis, refs = begin(db, seed)
            operation = request(basis, refs, "FITNESS")
            denied(
                db,
                seed,
                lambda: run(db, seed["identity"], operation),
                "runtime" if case == "fixture_policy" else "both full policy action scopes",
                case,
            )
        assert_no_execution(db, auth(seed).subject_id)
        witness(
            "incomplete_source_no_authority",
            case=case,
            policy=seed["policy"],
            persisted=snapshot(db, auth(seed).subject_id),
        )


def input_revision(db: Any, seed: dict[str, Any], key: str) -> UUID:
    subject = seed["identity"].subject_id
    receipt, event, revision = uuid4(), uuid4(), uuid4()

    def operation(tx: RepositoryTransaction) -> Any:
        tx.lock_subject()
        row = db.execute(
            "SELECT authorization_epoch FROM kineticloop.user_decision_state WHERE subject_id=%s",
            (subject,),
        ).fetchone()
        assert row is not None
        epoch = row[0]

        def mutation(session: RestrictedSqlSession) -> Any:
            session.insert(
                "S14",
                {
                    "id": revision,
                    "subject_id": subject,
                    "stable_fact_identity": key,
                    "fact_kind": "HEALTH_OBSERVATION",
                    "fact_revision": 1,
                    "ref_s10_id": seed["assertion"],
                    "ref_s11_id": seed["event"],
                    "ref_s13_id": seed["admission"],
                },
            )
            session.insert(
                "S43",
                {
                    "id": uuid4(),
                    "subject_id": subject,
                    "event_kind": "EPOCH_INVALIDATED",
                    "invalidated_epoch": epoch + 1,
                    "scope": "TEST_ONLY",
                    "causation_key": key,
                    "ref_s02_id": receipt,
                },
            )
            session.update(
                "S01",
                {"input_frontier_hash": digest(key), "authorization_epoch": epoch + 1},
                {"subject_id": subject},
            )
            return {"fact_id": str(revision), "epoch": epoch + 1}

        return tx.idempotent_outcome(
            receipt_id=receipt,
            actor_scope=seed["identity"].key,
            client_key=key,
            request_hash=digest(key),
            mutation=mutation,
            invalidation_scope="TEST_ONLY",
            event=EventWrite(
                event, "FACT", str(revision), 1, "ACTUAL_INPUT_CHANGED", "canonical", uuid4()
            ),
        )

    execute_command(db, "AcceptFactRevision", subject, operation)
    return revision


def scope_input_revision(database_urls: Any) -> None:
    seed, request = ready(database_urls)
    with connect(database_urls["admin"]) as db:
        bundle = service(db, seed).commit_full(request)
        started = service(db, seed).start(session_command(seed, bundle))
        initial = current_binding(db, seed, started["session_id"])
        continuing = session_command(
            seed, bundle, ContinueSession, session_id=started["session_id"], binding=initial
        )
        assert service(db, seed).continue_session(continuing)["executable"]
        before = snapshot(db, auth(seed).subject_id)
        fact = input_revision(db, seed, "accepted-input-" + str(uuid4()))
        after = snapshot(db, auth(seed).subject_id)
        oldepoch = before["user_decision_state"][0][0]["authorization_epoch"]
        epoch = after["user_decision_state"][0][0]["authorization_epoch"]
        assert epoch == oldepoch + 1
        assert len(after["canonical_fact_revisions"]) == len(before["canonical_fact_revisions"]) + 1
        for table in (
            "proposal_revisions",
            "prescription_demand_features",
            "evidence_resolutions",
            "validation_results",
            "authorization_issuances",
            "execution_bindings",
            "workout_sessions",
        ):
            assert before[table] == after[table]
        fresh = changed(
            continuing,
            command_id=str(uuid4()),
            action_key=str(uuid4()),
            idempotency_key=str(uuid4()),
            expected_authorization_epoch=epoch,
        )
        denied(
            db,
            seed,
            lambda: service(db, seed).continue_session(fresh),
            "KL_REGISTRY_AUTHORIZATION_INELIGIBLE",
            "AcceptFactRevision-current-authority-loss",
        )
        witness(
            "AcceptFactRevision_locked_current_frontier_epoch",
            fact=fact,
            oldepoch=oldepoch,
            epoch=epoch,
            persisted=after,
        )
