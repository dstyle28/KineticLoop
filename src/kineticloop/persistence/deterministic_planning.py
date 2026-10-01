"""Exact current-attempt TEST preparation owners; compute before coordination."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any
from uuid import UUID, uuid4, uuid5

from psycopg import Connection, Cursor, sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from kineticloop.persistence.factsets import BuilderIdentity, CanonicalViewService
from kineticloop.persistence.planning_progress import wire
from kineticloop.persistence.transactions import (
    _FIXTURE_TOKEN,
    EventWrite,
    GuardRequired,
    RepositoryTransaction,
    RestrictedSqlSession,
    TransactionStateError,
    _cursor,
)
from kineticloop.workflow.deterministic_planning import (
    OWNERS,
    VERSION,
    Basis,
    Demand,
    Fact,
    Fitness,
    Nutrition,
    PreparationRequest,
    Resolution,
    Validation,
    compute_demand,
    compute_fitness,
    compute_nutrition,
    instant,
    policy,
    resolve,
    validate,
)
from kineticloop.workflow.planning import digest
from kineticloop.workflow.planning_progress import AdvanceAttempt, ProgressIdentity

_NAMESPACE = UUID("dd042ed1-2ad9-4800-9d51-8833c4cddc0d")
_TABLES = {
    "snapshot": "decision_snapshots",
    "fitness": "proposal_revisions",
    "demand": "prescription_demand_features",
    "nutrition": "proposal_revisions",
    "resolution": "evidence_resolutions",
}


@dataclass(frozen=True)
class _Computed:
    capture_json: str
    payload_json: str


def _inputs(
    cursor: Cursor[Any], identity: ProgressIdentity, request: PreparationRequest
) -> dict[str, Any]:
    """Immutable bounded reads. Used outside coordination; persistence verifies their hashes."""
    rows: dict[str, Any] = {}
    for name, ref in request.sources.items():
        cursor.execute(
            sql.SQL(
                "SELECT to_jsonb(t) FROM kineticloop.{} t WHERE subject_id=%s AND id=%s"
            ).format(sql.Identifier(_TABLES[name])),
            (identity.subject_id, UUID(ref["id"])),
        )
        row = cursor.fetchone()
        if (
            not row
            or row[0]["content_hash"] != ref["hash"]
            or digest(row[0]["typed_payload"]) != ref["hash"]
        ):
            raise GuardRequired("immutable fixture source identity/hash missing or changed")
        rows[name] = row[0]
    cursor.execute(
        "SELECT to_jsonb(m),to_jsonb(p),s.execution_basis_event_id FROM kineticloop.decision_manifests m "
        "JOIN kineticloop.policy_bundles p ON p.subject_id=m.subject_id AND p.id=m.ref_s05_id "
        "JOIN kineticloop.user_decision_state s ON s.subject_id=m.subject_id WHERE m.subject_id=%s AND m.id=%s",
        (identity.subject_id, request.manifest_id),
    )
    found = cursor.fetchone()
    if not found or found[1]["id"] != str(identity.policy_id):
        raise GuardRequired("same-subject manifest/TEST policy required")
    manifest, policy_row, execution = found
    configuration = policy_row["typed_payload"].get("deterministic_fixture")
    if (
        not isinstance(configuration, dict)
        or digest(policy_row["typed_payload"]) != policy_row["content_hash"]
    ):
        raise GuardRequired("immutable explicit fixture policy required")
    policy(configuration)
    runtime = policy_row["typed_payload"].get("fixture_runtime")
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {"id", "hash", "version"}
        or runtime["version"] != VERSION
    ):
        raise GuardRequired("exact fixture runtime version required")
    cursor.execute(
        "SELECT to_jsonb(a),EXISTS (SELECT 1 FROM kineticloop.artifact_revocation_events r WHERE r.ref_s49_id=a.id) "
        "FROM kineticloop.safety_artifacts a WHERE id=%s",
        (UUID(runtime["id"]),),
    )
    artifact = cursor.fetchone()
    if (
        not artifact
        or artifact[1]
        or artifact[0]["artifact_kind"] != "RUNTIME"
        or artifact[0]["content_hash"] != runtime["hash"]
        or artifact[0]["artifact_version"] != VERSION
        or artifact[0]["typed_payload"]
        != {"operation": "DETERMINISTIC_TEST_PREPARATION", "version": VERSION}
        or artifact[0]["valid_from"] is None
        or artifact[0]["valid_until"] is None
    ):
        raise GuardRequired("known unrevoked bounded fixture runtime required")
    cursor.execute(
        "SELECT to_jsonb(f) FROM kineticloop.factset_revisions f WHERE subject_id=%s AND id=%s AND status='SEALED'",
        (identity.subject_id, UUID(manifest["ref_s15_id"])),
    )
    source = cursor.fetchone()
    if not source:
        raise GuardRequired("manifest must cite actual SEALED source")
    cursor.execute(
        "SELECT member_kind,coalesce(ref_s14_id,ref_s13_id,ref_s12_id)::text FROM kineticloop.factset_members "
        "WHERE subject_id=%s AND ref_s15_id=%s AND member_operation='SET' ORDER BY member_kind,id",
        (identity.subject_id, UUID(manifest["ref_s15_id"])),
    )
    members = cursor.fetchall()
    if not members or len(members) > 64 or any(not r[1] for r in members):
        raise GuardRequired("bounded FULL fixture member closure required")
    if source[0]["storage_mode"] != "FULL":
        raise GuardRequired("fixture domain requires FULL canonical membership")
    member_ids = {r[1] for r in members}
    facts: list[dict[str, Any]] = []
    for kind, member in members:
        if kind != "FACT":
            continue
        cursor.execute(
            "SELECT to_jsonb(f),to_jsonb(a),to_jsonb(e) FROM kineticloop.canonical_fact_revisions f "
            "JOIN kineticloop.admission_decisions a ON a.subject_id=f.subject_id AND a.id=f.ref_s13_id "
            "JOIN kineticloop.evidence_revisions e ON e.subject_id=a.subject_id AND e.id=a.ref_s09_id "
            "JOIN kineticloop.candidate_assertions c ON c.subject_id=f.subject_id AND c.id=f.ref_s10_id "
            "AND c.id=a.ref_s10_id AND c.ref_s09_id=e.id "
            "WHERE f.subject_id=%s AND f.id=%s",
            (identity.subject_id, UUID(member)),
        )
        fact_row = cursor.fetchone()
        if not fact_row:
            raise GuardRequired("source fact admission/provenance missing")
        f, a, e = fact_row
        data = f["typed_payload"]
        if (
            f["fact_kind"] != "WORKOUT_ACTUAL"
            or a["id"] not in member_ids
            or a["ref_s05_id"] != str(identity.policy_id)
            or e["command_authority"] != "NONE"
            or e["trust_class"] != "USER_REPORTED"
            or not isinstance(data, dict)
            or digest(data) != f["content_hash"]
            or digest(a["typed_payload"]) != a["content_hash"]
        ):
            raise GuardRequired("declared admitted actual fixture evidence required")
        cursor.execute(
            "SELECT to_jsonb(a) FROM kineticloop.event_association_decisions a WHERE subject_id=%s AND id=%s",
            (identity.subject_id, UUID(data["association_id"])),
        )
        association = cursor.fetchone()
        if (
            not association
            or association[0]["id"] not in member_ids
            or association[0]["ref_s11_id"] != f["ref_s11_id"]
            or digest(association[0]["typed_payload"]) != association[0]["content_hash"]
        ):
            raise GuardRequired("exact source event association required")
        assoc = association[0]
        fact = Fact(
            fact_id=f["id"],
            fact_hash=f["content_hash"],
            admission_id=a["id"],
            admission_hash=a["content_hash"],
            association_id=assoc["id"],
            association_hash=assoc["content_hash"],
            event_id=f["ref_s11_id"],
            subject_id=str(identity.subject_id),
            policy_id=str(identity.policy_id),
            exercise=data["exercise"],
            scope=a["action_scope"],
            admission=a["decision"],
            association=assoc["association_state"],
            semantic_class=data["semantic_class"],
            effective_at=f["effective_at"],
            valid_until=a["typed_payload"]["valid_until"],
            lower_minutes=data["lower_minutes"],
            upper_minutes=data["upper_minutes"],
            contradicts=data["contradicts"],
            replaces_slot=data["replaces_slot"],
            retracted=data["retracted"],
        )
        facts.append(fact.payload())
    parent = None
    if request.parent_id:
        cursor.execute(
            "SELECT to_jsonb(f) FROM kineticloop.proposal_revisions f WHERE subject_id=%s AND id=%s AND proposal_kind='FITNESS'",
            (identity.subject_id, request.parent_id),
        )
        prior = cursor.fetchone()
        if not prior or prior[0]["content_hash"] != digest(prior[0]["typed_payload"]):
            raise GuardRequired("actual immutable FITNESS repair parent required")
        parent = prior[0]
    return {
        "rows": rows,
        "manifest": manifest,
        "policy": policy_row,
        "runtime": artifact[0],
        "factset": source[0],
        "members": sorted(member_ids),
        "facts": sorted(facts, key=lambda x: x["fact_id"]),
        "parent": parent,
        "execution_basis_event_id": str(execution) if execution else None,
    }


def _compute(
    connection: Connection[Any], identity: ProgressIdentity, request: PreparationRequest
) -> _Computed:
    with connection.transaction():
        capture = _inputs(connection.cursor(), identity, request)
        now = connection.execute("SELECT clock_timestamp()").fetchone()[0]  # type: ignore[index]
    # Verify real sealed canonical reconstruction with the merged reader, outside coordination.
    canonical = CanonicalViewService(
        connection, BuilderIdentity(identity.actor, identity.subject_id)
    ).read_canonical(identity.subject_id, UUID(capture["manifest"]["ref_s15_id"]))
    if sorted(str(m.revision_id) for m in canonical.members) != capture["members"]:
        raise GuardRequired("physical source members must equal reconstructed canonical closure")
    rows = capture["rows"]
    config = capture["policy"]["typed_payload"]["deterministic_fixture"]
    snap = rows["snapshot"]
    base = Basis(
        subject_id=str(identity.subject_id),
        root_id=str(request.intent_id),
        attempt_id=str(request.attempt_id),
        request_id=str(request.request_id),
        request_revision=request.request_revision,
        snapshot_id=snap["id"],
        context_hash=snap["content_hash"],
        manifest_id=str(request.manifest_id),
        policy_id=str(identity.policy_id),
        policy_hash=capture["policy"]["content_hash"],
        captured_epoch=request.epoch,
    )
    output = str(uuid5(_NAMESPACE, f"{request.subject_id}:{request.attempt_id}:{request.kind}"))

    def typed(name: str, model: Any) -> Any:
        return model.model_validate_json(json.dumps(rows[name]["typed_payload"]))

    if request.kind == "FITNESS":
        parent = (
            Fitness.model_validate_json(json.dumps(capture["parent"]["typed_payload"]))
            if capture["parent"]
            else None
        )
        artifact: Any = compute_fitness(
            base, output, snap["typed_payload"]["blocks"]["constraints"], parent
        )
    else:
        fitness = typed("fitness", Fitness)
        if {k: fitness.payload()[k] for k in Basis.model_fields} != base.payload():
            raise GuardRequired("exact current F/snapshot/attempt/policy basis required")
        if request.kind == "DEMAND":
            artifact = compute_demand(fitness, output, config)
        elif request.kind == "NUTRITION":
            artifact = compute_nutrition(fitness, typed("demand", Demand), output, config)
        elif request.kind == "RESOLUTION":
            # F/D/N must already be coherent before resolving the action.
            if compute_nutrition(
                fitness, typed("demand", Demand), rows["nutrition"]["id"], config
            ) != typed("nutrition", Nutrition):
                raise GuardRequired("exact computed Nutrition required before resolution")
            artifact = resolve(
                fitness,
                output,
                config,
                tuple(Fact.model_validate_json(json.dumps(f)) for f in capture["facts"]),
                manifest_hash=capture["manifest"]["manifest_hash"],
                source_hash=digest(capture["factset"]),
                members=tuple(capture["members"]),
                expires_at=min(
                    instant(capture["manifest"]["valid_until"]),
                    instant(capture["runtime"]["valid_until"]),
                ).isoformat(),
            )
        else:
            demand, nutrition, resolution = (
                typed("demand", Demand),
                typed("nutrition", Nutrition),
                typed("resolution", Resolution),
            )
            mechanical = validate(fitness, demand, nutrition, resolution, config, now)
            if not capture["execution_basis_event_id"]:
                raise GuardRequired("actual upstream execution-basis event required")
            artifact = Validation.model_validate_json(
                json.dumps(
                    {
                        **base.payload(),
                        "id": output,
                        "fitness_hash": fitness.content_hash,
                        "demand_hash": demand.content_hash,
                        "nutrition_hash": nutrition.content_hash,
                        "resolution_hash": resolution.content_hash,
                        "execution_basis_event_id": capture["execution_basis_event_id"],
                        "valid_until": resolution.resolution_expires_at,
                        **mechanical,
                    }
                )
            )
    return _Computed(
        json.dumps(capture, sort_keys=True), json.dumps(artifact.payload(), sort_keys=True)
    )


class _Service:
    kinds: frozenset[str]

    def __init__(self, connection: Connection[Any], identity: ProgressIdentity):
        if type(identity) is not ProgressIdentity:
            raise GuardRequired("authenticated fixture TEST identity required")
        identity.__post_init__()
        self.connection, self.identity = connection, identity

    def _run(self, request: PreparationRequest) -> Mapping[str, Any]:
        if type(request) is not PreparationRequest or request.kind not in self.kinds:
            raise GuardRequired("exact typed fixture preparation request required")
        request = replace(request, sources=copy.deepcopy(dict(request.sources)))
        request.__post_init__()
        if (
            request.subject_id != self.identity.subject_id
            or request.expected_owner != self.identity.key
        ):
            raise GuardRequired("authenticated fixture subject/worker mismatch")
        if self.connection.info.transaction_status != TransactionStatus.IDLE:
            raise TransactionStateError("fixture preparation requires idle owner connection")
        command = OWNERS[request.kind][0]
        request_hash = digest(wire(asdict(request)))
        with self.connection.transaction():
            prior = self.connection.execute(
                "SELECT 1 FROM kineticloop.command_receipts WHERE subject_id=%s AND command_kind=%s AND actor_scope=%s AND client_key=%s",
                (request.subject_id, command, self.identity.key, request.key),
            ).fetchone()
        computed = None if prior else _compute(self.connection, self.identity, request)
        with self.connection.transaction():
            tx = RepositoryTransaction(self.connection.cursor(), command, request.subject_id)
            outcome = _persist_fixture(tx, self.identity, request, request_hash, computed)
            tx.finish()
            return outcome


class ProposalService(_Service):
    kinds = frozenset({"FITNESS", "NUTRITION"})

    def record_proposal(self, request: PreparationRequest) -> Mapping[str, Any]:
        return self._run(request)


class DemandFeatureService(_Service):
    kinds = frozenset({"DEMAND"})

    def record_demand_features(self, request: PreparationRequest) -> Mapping[str, Any]:
        return self._run(request)


class EvidenceResolver(_Service):
    kinds = frozenset({"RESOLUTION"})

    def resolve_evidence(self, request: PreparationRequest) -> Mapping[str, Any]:
        return self._run(request)


class ValidationService(_Service):
    kinds = frozenset({"VALIDATION"})

    def record_validation(self, request: PreparationRequest) -> Mapping[str, Any]:
        return self._run(request)


def _prepare_fixture(
    tx: RepositoryTransaction,
    identity: ProgressIdentity,
    request: PreparationRequest,
    computed: _Computed,
) -> None:
    request.__post_init__()
    if type(computed) is not _Computed or tx.command_kind != OWNERS[request.kind][0]:
        raise GuardRequired("exact fixture operation/computation required")
    chain = tx._prepare_current_progress(identity, request)
    capture = json.loads(computed.capture_json)
    if _inputs(_cursor(tx), identity, request) != capture:
        raise GuardRequired("immutable fixture computation/source basis changed")
    now = chain[-1]
    if (
        not instant(capture["runtime"]["valid_from"])
        <= now
        < instant(capture["runtime"]["valid_until"])
    ):
        raise GuardRequired("fixture runtime inactive/expired")
    subset = {name: value for name, value in request.sources.items() if name != "resolution"}
    target = {"FITNESS": "FITNESS", "DEMAND": "DEMAND_FEATURES", "NUTRITION": "NUTRITION"}.get(
        request.kind, "VALIDATING"
    )
    previous = {
        "FITNESS": "BUILDING_CONTEXT",
        "DEMAND_FEATURES": "FITNESS",
        "NUTRITION": "DEMAND_FEATURES",
        "VALIDATING": "NUTRITION",
    }[target]
    # Exact proxy retains the existing KL075 immutable source checker; no stage mutation occurs here.
    proxy = AdvanceAttempt(
        **{
            k: getattr(request, k)
            for k in (
                "subject_id",
                "key",
                "intent_id",
                "request_id",
                "request_revision",
                "attempt_id",
                "expected_owner",
                "fence",
                "manifest_id",
                "epoch",
            )
        },
        source_state=previous,
        target_state=target,
        sources=subset,
    )
    tx._progress_sources(proxy, chain[6], identity.policy_id, now)
    payload = json.loads(computed.payload_json)
    model: Any = {
        "FITNESS": Fitness,
        "DEMAND": Demand,
        "NUTRITION": Nutrition,
        "RESOLUTION": Resolution,
        "VALIDATION": Validation,
    }[request.kind]
    model.model_validate_json(computed.payload_json)
    if request.kind in {"RESOLUTION", "VALIDATION"}:
        expiry = payload.get("valid_until", payload.get("resolution_expires_at"))
        if now >= instant(expiry):
            raise GuardRequired("fixture source/certificate expired after preparation")
    output = UUID(payload["id"])
    table = OWNERS[request.kind][1]
    runtime = capture["policy"]["typed_payload"]["fixture_runtime"]
    values: dict[str, Any] = {
        "id": output,
        "subject_id": request.subject_id,
        "content_hash": digest(payload),
        "typed_payload": payload,
    }
    if table == "S34":
        values.update(
            proposal_kind=request.kind,
            proposal_family_identity=f"{request.intent_id}:{request.kind}",
            producer_artifact=f"{runtime['id']}:{runtime['version']}:{runtime['hash']}",
            ref_s26_id=UUID(request.sources["snapshot"]["id"]),
            ref_s29_id=request.attempt_id,
        )
        if request.kind == "NUTRITION":
            values["demand_feature_id"] = UUID(payload["demand_id"])
    elif table == "S35":
        values.update(
            method_version=VERSION,
            feature_hash=digest(payload),
            basis_hash=payload["fitness_hash"],
            ref_s34_id=UUID(payload["fitness_id"]),
        )
    elif table == "S36":
        values.update(
            action_type="TRAINING",
            action_parameters_hash=payload["action_parameters_hash"],
            resolver_version=VERSION,
            query_basis_hash=digest(
                {
                    "manifest_id": str(request.manifest_id),
                    "policy_id": str(identity.policy_id),
                    "fitness_hash": payload["fitness_hash"],
                    "action_type": "TRAINING",
                    "action_parameters_hash": payload["action_parameters_hash"],
                }
            ),
            resolution_expires_at=instant(payload["resolution_expires_at"]),
            ref_s05_id=identity.policy_id,
            ref_s24_id=request.manifest_id,
        )
    else:
        values.update(
            result="PASS",
            validator_artifact=f"{runtime['id']}:{runtime['version']}:{runtime['hash']}",
            valid_until=instant(payload["valid_until"]),
            ref_s03_id=UUID(payload["execution_basis_event_id"]),
            ref_s05_id=identity.policy_id,
            ref_s24_id=request.manifest_id,
            ref_s28_id=request.request_id,
            ref_s29_id=request.attempt_id,
            ref_s34_id=UUID(request.sources["nutrition"]["id"]),
            ref_s35_id=UUID(request.sources["demand"]["id"]),
            ref_s36_id=UUID(request.sources["resolution"]["id"]),
        )
    tx._coordination_context.update(
        fixture_token=_FIXTURE_TOKEN,
        fixture_values=values,
        fixture_table=table,
        fixture_revision=request.request_revision if table == "S34" else 1,
    )


def _persist_fixture(
    tx: RepositoryTransaction,
    identity: ProgressIdentity,
    request: PreparationRequest,
    request_hash: str,
    computed: _Computed | None,
) -> Mapping[str, Any]:
    tx._coordination_context["fixture_ingress_token"] = _FIXTURE_TOKEN
    tx.lock_subject()
    tx.require_progress_ingress(identity)
    prior = tx.progress_historical_outcome(
        actor_scope=identity.key, client_key=request.key, request_hash=request_hash
    )
    if prior is not None:
        return prior
    if computed is None:
        raise GuardRequired("historical preflight miss requires fresh outside-lock computation")
    tx.lock_intents((request.intent_id,))
    tx.require_current_fence(
        request.intent_id,
        owner_id=identity.key,
        fence=request.fence,
        expected_request_revision=request.request_revision,
        expected_attempt_id=request.attempt_id,
    )

    def mutation(session: RestrictedSqlSession) -> Mapping[str, Any]:
        context = tx._coordination_context
        values = context["fixture_values"]
        session.insert(
            context["fixture_table"], {**values, "typed_payload": Jsonb(values["typed_payload"])}
        )
        return {
            "id": str(values["id"]),
            "hash": values["content_hash"],
            "kind": request.kind,
            "attempt_id": str(request.attempt_id),
            "executable": False,
            "lock_trace": [(int(s), name) for s, name in tx.lock_trace],
        }

    outcome, replayed = tx.idempotent_outcome(
        receipt_id=uuid4(),
        actor_scope=identity.key,
        client_key=request.key,
        request_hash=request_hash,
        mutation=mutation,
        aggregate_locks={"planning_attempts": (request.attempt_id,)},
        fixture_identity=identity,
        fixture_request=request,
        fixture_computed=computed,
        event=EventWrite(
            event_id=uuid4(),
            aggregate_type="FIXTURE_PREPARATION",
            aggregate_identity=digest([identity.key, request.kind, request.key]),
            event_type=tx.command_kind,
            aggregate_revision=1,
            outbox_id=uuid4(),
            destination="planning",
        ),
    )
    return {**outcome, "replayed": True} if replayed else outcome
