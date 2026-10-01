from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError, DatabaseNamespace
from kineticloop.workflow.deterministic_planning import (
    FULL_VERSION,
    RULES,
    ActionBinding,
    Basis,
    Fact,
    FullPreparationRequest,
    FullResolution,
    FullValidation,
    Nutrition,
    binding,
    compute_demand,
    compute_fitness,
    compute_nutrition,
    full_query_basis,
    resolve_full,
    validate_full,
)
from kineticloop.workflow.planning import PlanningDenied, digest

ROOT = Path(__file__).resolve().parents[3]
AMBIENT = {
    "COMPOSE_PROJECT_NAME",
    "KINETICLOOP_DB_NAME",
    "COMPOSE_FILE",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DATABASE_URL",
    "KINETICLOOP_KL076_COMPOSE_PROJECT",
    "KINETICLOOP_KL076_DATABASE",
}


def fixture_namespace(
    root: Path, head: str, label: str = "full", *, worktree_digest: str | None = None
) -> DatabaseNamespace:
    if root.resolve() != ROOT or not re.fullmatch(r"[0-9a-f]{40}", head) or label != "full":
        raise DatabaseLifecycleError("exact KL079 task/SHA/resolved-root/label required")
    token = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    if worktree_digest is not None and (
        not re.fullmatch(r"[0-9a-f]{12}", worktree_digest) or token != worktree_digest
    ):
        raise DatabaseLifecycleError("exact resolved worktree digest required")
    return DatabaseNamespace(
        f"kineticloop-kl079-{label}-{head[:7]}-{token}",
        f"kineticloop_kl079_{label}_{head[:7]}_{token}",
    )


class OwnedLifecycle(DatabaseLifecycle):
    def __init__(
        self, root: Path, head: str, *, environ: Mapping[str, str] | None = None, **kwargs: Any
    ):
        selected = fixture_namespace(root, head)
        env = dict(os.environ if environ is None else environ)
        if AMBIENT & env.keys():
            raise DatabaseLifecycleError("ambient namespace/runtime override")
        self.head = head
        self.inventory: list[str] = []
        super().__init__(root, environ=env, **kwargs)
        self.namespace = selected
        self.validate_target()

    def validate_target(self) -> None:
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if (
            self.head != actual
            or self.namespace != fixture_namespace(self.root, self.head)
            or AMBIENT & self._base_environ.keys()
        ):
            raise DatabaseLifecycleError("foreign KL079 lifecycle/ambient target")

    def _run(self, command: Any, **kwargs: Any) -> Any:
        self.validate_target()
        return super()._run(command, **kwargs)

    def compose_command(self, *args: str) -> list[str]:
        self.validate_target()
        return super().compose_command(*args)

    def reset(self, *, timeout_seconds: float = 60) -> Any:
        self.validate_target()
        self.inventory.append("reset")
        return super().reset(timeout_seconds=timeout_seconds)

    def start(self, *, timeout_seconds: float = 60) -> None:
        self.validate_target()
        self.inventory.append("start")
        super().start(timeout_seconds=timeout_seconds)

    def connection(self) -> Any:
        self.validate_target()
        return super().connection()

    def destroy(self) -> None:
        self.validate_target()
        self.inventory.append("destroy")
        super().destroy()

    def bootstrap(self, selected_bootstrap: Callable[..., Any]) -> Any:
        self.validate_target()
        self.inventory.append("bootstrap_two_phase(selected_lifecycle)")
        return selected_bootstrap(self)


def source_case() -> tuple[Basis, dict[str, Any], tuple[Fact, ...], datetime]:
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    ids = [str(uuid4()) for _ in range(10)]
    base = Basis(
        subject_id=ids[0],
        root_id=ids[1],
        attempt_id=ids[2],
        request_id=ids[3],
        request_revision=1,
        snapshot_id=ids[4],
        context_hash=digest("context"),
        manifest_id=ids[5],
        policy_id=ids[6],
        policy_hash=digest("policy"),
        captured_epoch=0,
    )
    facts = (
        Fact(
            fact_id=ids[7],
            fact_hash=digest("actual"),
            admission_id=ids[8],
            admission_hash=digest("admitted"),
            association_id=ids[9],
            association_hash=digest("confirmed"),
            event_id=str(uuid4()),
            subject_id=base.subject_id,
            policy_id=base.policy_id,
            exercise="fixture:cycle",
            scope="TEST_ONLY",
            admission="ADMITTED",
            association="CONFIRMED",
            semantic_class="ACTUAL_EXECUTION",
            effective_at=(now - timedelta(hours=1)).isoformat(),
            valid_until=(now + timedelta(hours=1)).isoformat(),
            lower_minutes=10,
            upper_minutes=10,
            contradicts=False,
            replaces_slot="prior-slot",
        ),
    )
    config = {
        "rules": RULES,
        "window": [(now - timedelta(days=1)).isoformat(), (now + timedelta(hours=1)).isoformat()],
        "required_members": list(ids[7:]),
        "reservations": {"prior-slot": 50},
        "valid_until": (now + timedelta(hours=1)).isoformat(),
    }
    return base, config, facts, now


def test_namespace(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    selected = fixture_namespace(ROOT, head)
    expected_digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
    assert selected.project_name == f"kineticloop-kl079-full-{head[:7]}-{expected_digest}"
    assert selected.database_name == f"kineticloop_kl079_full_{head[:7]}_{expected_digest}"
    for root, sha, label in (
        (tmp_path, head, "full"),
        (ROOT, head[:7], "full"),
        (ROOT, "G" * 40, "full"),
        (ROOT, head, "progress"),
    ):
        with pytest.raises(DatabaseLifecycleError):
            fixture_namespace(root, sha, label)
    for token in ("bad", "0" * 12, "G" * 12):
        with pytest.raises(DatabaseLifecycleError):
            fixture_namespace(ROOT, head, worktree_digest=token)
    calls: list[Any] = []

    def runner(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    own = OwnedLifecycle(ROOT, head, environ={}, runner=runner)
    for namespace in (
        DatabaseNamespace("foreign", "postgres"),
        DatabaseNamespace(selected.project_name, "postgres"),
    ):
        own.namespace = namespace
        for action in (
            own.reset,
            own.start,
            own.destroy,
            own.connection,
            lambda: own.bootstrap(lambda lifecycle: None),
            lambda: own._run(["docker", "version"]),
        ):
            with pytest.raises(DatabaseLifecycleError):
                action()
    own.namespace = selected
    for key in AMBIENT:
        with pytest.raises(DatabaseLifecycleError):
            OwnedLifecycle(ROOT, head, environ={key: "foreign"}, runner=runner)
        own._base_environ[key] = "foreign"
        for action in (own.reset, own.destroy, lambda: own.bootstrap(lambda lifecycle: None)):
            with pytest.raises(DatabaseLifecycleError):
                action()
        own._base_environ.pop(key)
    assert not calls
    own.bootstrap(lambda lifecycle: lifecycle._run(["docker", "version"]))
    own.destroy()
    assert len(calls) == 2
    print(
        "NAMESPACE_PU",
        selected,
        "negative_controls=foreign_root,sha,digest,label,ambient,nested_cleanup",
        "nested_inventory",
        own.inventory,
    )


def full_case() -> tuple[Any, ...]:
    base, config, facts, now = source_case()
    config.update(contract=FULL_VERSION, required_actions=["TRAINING", "NUTRITION"])
    f = compute_fitness(base, str(uuid4()), {"minutes": 30, "equipment": []}, None)
    d = compute_demand(f, str(uuid4()), config)
    n = compute_nutrition(f, d, str(uuid4()), config)
    source_id = str(uuid4())
    resolutions = tuple(
        resolve_full(
            f,
            d,
            n,
            str(uuid4()),
            config,
            facts,
            action_type=action,
            manifest_hash=digest("manifest"),
            source_id=source_id,
            source_hash=digest("sealed"),
            members=tuple(config["required_members"]),
            expires_at=config["valid_until"],
        )
        for action in ("TRAINING", "NUTRITION")
    )
    return f, d, n, resolutions, config, now


def test_contract() -> None:
    from dataclasses import replace

    from kineticloop.contracts.commands import PUBLIC_COMMAND_MODELS
    from kineticloop.identity import ActorRole, RoleIdentity
    from kineticloop.workflow.planning_progress import ProgressBasis, ProgressIdentity

    f, d, n, resolutions, config, now = full_case()
    r, nr = resolutions
    assert len(PUBLIC_COMMAND_MODELS) == 39
    fixture = json.loads((ROOT / "tests/fixtures/full_action_preparation.json").read_text())
    assert set(fixture) == {
        "contract",
        "required_actions",
        "rules",
        "authorization_action_scopes",
        "nutrition_parameters",
        "mechanical_examples",
    }
    assert fixture["contract"] == FULL_VERSION and fixture["required_actions"] == [
        "TRAINING",
        "NUTRITION",
    ]
    assert fixture["rules"] == RULES
    assert fixture["nutrition_parameters"] == {
        "semantic_class": "TARGET",
        "units": "fixture_units",
        "fuel_rule": "F.action.minutes*3",
    }
    assert r.id != nr.id and r.content_hash != nr.content_hash
    assert r.proposal_id == f.id and nr.proposal_id == n.id
    assert nr.action_parameters_hash == digest(
        {"fuel_units": 90, "semantic_class": "TARGET", "units": "fixture_units"}
    )
    assert r.action_parameters_hash == digest(f.action.payload())
    assert r.query_basis_hash == full_query_basis(r.payload())
    assert nr.query_basis_hash == full_query_basis(nr.payload()) != r.query_basis_hash
    mechanical = validate_full(f, d, n, resolutions, config, now)
    certificate = FullValidation.model_validate_json(
        json.dumps(
            {
                **{k: f.payload()[k] for k in Basis.model_fields},
                "id": str(uuid4()),
                "fitness_hash": f.content_hash,
                "demand_hash": d.content_hash,
                "nutrition_hash": n.content_hash,
                "resolution_hash": r.content_hash,
                "execution_basis_event_id": str(uuid4()),
                **mechanical,
            }
        )
    )
    assert tuple(b.action_type for b in certificate.action_bindings) == ("TRAINING", "NUTRITION")
    assert certificate.resolution_hash == r.content_hash
    basis: dict[str, Any] = dict(
        subject_id=UUID(f.subject_id),
        key="full-request",
        intent_id=UUID(f.root_id),
        request_id=UUID(f.request_id),
        request_revision=1,
        attempt_id=UUID(f.attempt_id),
        expected_owner="TEST:owner",
        fence=1,
        manifest_id=UUID(f.manifest_id),
        epoch=0,
        source_state="VALIDATING",
    )
    refs = {
        name: {"id": obj.id, "hash": obj.content_hash}
        for name, obj in (("fitness", f), ("demand", d), ("nutrition", n))
    }
    refs["snapshot"] = {"id": f.snapshot_id, "hash": f.context_hash}
    request = FullPreparationRequest(
        **basis,
        kind="RESOLUTION",
        sources=refs,
        action_type="NUTRITION",
        proposal_id=UUID(n.id),
        proposal_hash=n.content_hash,
        action_parameters_hash=nr.action_parameters_hash,
    )
    change: dict[str, Any]
    for change in (
        {"action_type": "UNKNOWN"},
        {"proposal_id": uuid4()},
        {"proposal_hash": digest("wrong")},
        {"source_state": "COMMIT_READY"},
        {"subject_id": "caller"},
        {"sources": {}},
        {"action_bindings": (binding(r), binding(nr))},
    ):
        with pytest.raises((PlanningDenied, ValueError, TypeError)):
            replace(request, **change)
    for model, payload in (
        (FullResolution, r.payload()),
        (FullValidation, certificate.payload()),
        (ActionBinding, binding(nr).payload()),
    ):
        for key in ("caller_pass", "completeness", "fallback", "actual_fuel_units"):
            with pytest.raises(ValidationError):
                model.model_validate_json(json.dumps({**payload, key: True}))
    vr = FullPreparationRequest(
        **basis,
        kind="VALIDATION",
        sources={
            **refs,
            "resolution": {"id": r.id, "hash": r.content_hash},
            "nutrition_resolution": {"id": nr.id, "hash": nr.content_hash},
        },
        action_bindings=(binding(r), binding(nr)),
    )
    for bindings in (
        (),
        (binding(r),),
        (binding(nr), binding(r)),
        (binding(r), binding(r)),
        (binding(r), binding(nr), binding(nr)),
    ):
        with pytest.raises(PlanningDenied):
            replace(vr, action_bindings=bindings)
    assert ProgressBasis(**basis).subject_id == request.subject_id
    for role in (ActorRole.SUBJECT, ActorRole.ADMIN, ActorRole.EVALUATION):
        with pytest.raises(PlanningDenied):
            ProgressIdentity(
                RoleIdentity(str(uuid4()), role),
                uuid4(),
                uuid4(),
                uuid4(),
                "kl_test_subject_1_login",
            )
    with pytest.raises(PlanningDenied):
        ProgressIdentity(
            RoleIdentity(str(uuid4()), ActorRole.TEST), uuid4(), uuid4(), uuid4(), "foreign"
        )
    print(
        "FULL_CONTRACT_PU exact_order=TRAINING,NUTRITION singular_anchor=TRAINING commands=39 non_executable=true"
    )


def test_resolution_semantics() -> None:
    f, d, n, resolutions, config, now = full_case()
    assert validate_full(f, d, n, resolutions, config, now)["rolling_minutes"] == 40
    r, nr = resolutions
    for changes in ({"fuel_units": 91}, {"semantic_class": "ACTUAL_EXECUTION"}):
        with pytest.raises((PlanningDenied, ValidationError)):
            mutant = Nutrition.model_validate_json(json.dumps({**n.payload(), **changes}))
            validate_full(f, d, mutant, resolutions, config, now)
    for field, value in (
        ("proposal_id", f.id),
        ("proposal_hash", f.content_hash),
        ("action_parameters_hash", r.action_parameters_hash),
        ("demand_hash", digest("wrong")),
        ("nutrition_hash", digest("wrong")),
        ("subject_id", str(uuid4())),
        ("coverage", "COMPLETE_FOR_POLICY"),
        ("consistency", "CONFLICTED"),
        ("truncation_status", "TRUNCATED"),
        ("source_members", []),
        ("source_hash", digest("wrong")),
        ("manifest_hash", digest("wrong")),
    ):
        if nr.payload()[field] == value:
            continue
        mutant_resolution = FullResolution.model_validate_json(
            json.dumps({**nr.payload(), field: value})
        )
        with pytest.raises(PlanningDenied):
            validate_full(f, d, n, (r, mutant_resolution), config, now)
    for fact_changes in (
        {"contradicts": True},
        {"retracted": True},
        {"association": "UNRESOLVED"},
        {"upper_minutes": None},
        {"semantic_class": "TARGET"},
        {"policy_id": str(uuid4())},
        {"effective_at": (now + timedelta(minutes=1)).isoformat()},
    ):
        fact = Fact.model_validate_json(json.dumps({**r.facts[0].payload(), **fact_changes}))
        with pytest.raises(PlanningDenied):
            bad = tuple(
                resolve_full(
                    f,
                    d,
                    n,
                    str(uuid4()),
                    config,
                    (fact,),
                    action_type=a,
                    manifest_hash=r.manifest_hash,
                    source_id=r.source_id,
                    source_hash=r.source_hash,
                    members=r.source_members,
                    expires_at=r.resolution_expires_at,
                )
                for a in ("TRAINING", "NUTRITION")
            )
            validate_full(f, d, n, bad, config, now)
    for members in (
        (),
        r.source_members + (str(uuid4()),),
        r.source_members + (r.source_members[0],),
    ):
        bad = tuple(
            resolve_full(
                f,
                d,
                n,
                str(uuid4()),
                config,
                r.facts,
                action_type=a,
                manifest_hash=r.manifest_hash,
                source_id=r.source_id,
                source_hash=r.source_hash,
                members=members,
                expires_at=r.resolution_expires_at,
            )
            for a in ("TRAINING", "NUTRITION")
        )
        with pytest.raises(PlanningDenied):
            validate_full(f, d, n, bad, config, now)
    for bad in ((nr, r), (r, r), (r,), ()):
        with pytest.raises(PlanningDenied):
            validate_full(f, d, n, bad, config, now)
    with pytest.raises(PlanningDenied):
        validate_full(f, d, n, resolutions, config, datetime.fromisoformat(r.resolution_expires_at))
    for badconfig in (
        {k: v for k, v in config.items() if k not in {"contract", "required_actions"}},
        {**config, "required_actions": ["NUTRITION", "TRAINING"]},
    ):
        with pytest.raises(PlanningDenied):
            validate_full(f, d, n, resolutions, badconfig, now)
    print(
        "FULL_RESOLUTION_PU actual_membership=true target_never_actual=true equality_denies=true negative_controls=source,action,policy,contradiction,retraction,unknown,future,hash,ordering"
    )
