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
from uuid import uuid4

import pytest
from pydantic import ValidationError

from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError, DatabaseNamespace
from kineticloop.workflow.deterministic_planning import (
    RULES,
    Basis,
    Demand,
    Fact,
    Fitness,
    Nutrition,
    Resolution,
    compute_demand,
    compute_fitness,
    compute_nutrition,
    resolve,
    validate,
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
    root: Path, head: str, label: str = "fixture", *, worktree_digest: str | None = None
) -> DatabaseNamespace:
    if root.resolve() != ROOT or not re.fullmatch(r"[0-9a-f]{40}", head) or label != "fixture":
        raise DatabaseLifecycleError("exact KL076 task/SHA/resolved-root/label required")
    token = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    if worktree_digest is not None and (
        not re.fullmatch(r"[0-9a-f]{12}", worktree_digest) or token != worktree_digest
    ):
        raise DatabaseLifecycleError("exact resolved worktree digest required")
    return DatabaseNamespace(
        f"kineticloop-kl076-{label}-{head[:7]}-{token}",
        f"kineticloop_kl076_{label}_{head[:7]}_{token}",
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
            raise DatabaseLifecycleError("foreign KL076 lifecycle/ambient target")

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
            admission="ELIGIBLE",
            association="MATCHED",
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


def chain(
    base: Basis,
    config: dict[str, Any],
    facts: tuple[Fact, ...],
    now: datetime,
    minutes: int = 30,
    parent: Fitness | None = None,
) -> tuple[Fitness, Demand, Nutrition, Resolution]:
    f = compute_fitness(base, str(uuid4()), {"minutes": minutes, "equipment": []}, parent)
    d = compute_demand(f, str(uuid4()), config)
    n = compute_nutrition(f, d, str(uuid4()), config)
    r = resolve(
        f,
        str(uuid4()),
        config,
        facts,
        manifest_hash=digest("manifest"),
        source_hash=digest("sealed"),
        members=tuple(config["required_members"]),
        expires_at=(now + timedelta(hours=1)).isoformat(),
    )
    return f, d, n, r


def test_fdn_identities() -> None:
    base, config, facts, now = source_case()
    f, d, n, r = chain(base, config, facts, now)
    assert validate(f, d, n, r, config, now)["rolling_minutes"] == 40
    assert d.fitness_hash == f.content_hash and n.demand_hash == d.content_hash
    assert n.fitness_id == d.fitness_id == f.id and n.policy_id == base.policy_id
    assert d.semantic_classes == (
        ("prescribed_minutes", "PRESCRIBED_QUANTITY"),
        ("target_units", "TARGET"),
        ("estimate_interval", "ESTIMATE"),
    )
    assert d.estimate_interval == (60, 61) and n.fuel_units == 90
    for artifact in (f, d, n, r):
        assert digest(artifact.payload()) == artifact.content_hash
        with pytest.raises(ValidationError):
            artifact.id = str(uuid4())
    for mutant in (
        Demand.model_validate_json(json.dumps({**d.payload(), "fitness_hash": digest("wrong")})),
        Demand.model_validate_json(json.dumps({**d.payload(), "subject_id": str(uuid4())})),
        Demand.model_validate_json(json.dumps({**d.payload(), "prescribed_minutes": 31})),
    ):
        with pytest.raises(PlanningDenied):
            compute_nutrition(f, mutant, n.id, config)
    with pytest.raises(ValidationError):
        Fitness.model_validate_json(json.dumps({**f.payload(), "actual_minutes": 30}))
    assert (
        json.loads((ROOT / "tests/fixtures/deterministic_planning.json").read_text())["rules"]
        == RULES
    )


def test_fitness_repair() -> None:
    base, config, facts, now = source_case()
    f1, d1, n1, _ = chain(base, config, facts, now)
    original = [item.payload() for item in (f1, d1, n1)]
    base2 = Basis.model_validate_json(
        json.dumps(
            {
                **base.payload(),
                "request_revision": 2,
                "attempt_id": str(uuid4()),
                "request_id": str(uuid4()),
                "snapshot_id": str(uuid4()),
                "context_hash": digest("new-context"),
            }
        )
    )
    f2, d2, n2, r2 = chain(base2, config, facts, now, 20, f1)
    assert f2.parent_id == f1.id and f2.parent_hash == f1.content_hash and f2.revision == 2
    assert d2.estimate_interval == (40, 41) and n2.fuel_units == 60
    assert validate(f2, d2, n2, r2, config, now)["rolling_minutes"] == 30
    with pytest.raises(PlanningDenied):
        validate(f2, d1, n1, r2, config, now)
    swapped = Demand.model_validate_json(
        json.dumps(
            {
                **d1.payload(),
                **base2.payload(),
                "fitness_id": f2.id,
                "fitness_hash": f2.content_hash,
            }
        )
    )
    with pytest.raises(PlanningDenied):
        compute_nutrition(f2, swapped, n2.id, config)
    swapped_n = Nutrition.model_validate_json(
        json.dumps(
            {
                **n1.payload(),
                **base2.payload(),
                "fitness_id": f2.id,
                "fitness_hash": f2.content_hash,
                "demand_id": d2.id,
                "demand_hash": d2.content_hash,
            }
        )
    )
    with pytest.raises(PlanningDenied):
        validate(f2, d2, swapped_n, r2, config, now)
    assert original == [item.payload() for item in (f1, d1, n1)]
    for parent in (None, f2):
        with pytest.raises(PlanningDenied):
            compute_fitness(base2, str(uuid4()), {"minutes": 20, "equipment": []}, parent)


def test_source_bound_validation() -> None:
    base, config, facts, now = source_case()
    f, d, n, r = chain(base, config, facts, now)
    assert r.supporting_events == (facts[0].event_id,)
    assert r.source_members == tuple(sorted(config["required_members"]))
    contrary = Fact.model_validate_json(
        json.dumps(
            {
                **facts[0].payload(),
                "fact_id": str(uuid4()),
                "event_id": str(uuid4()),
                "contradicts": True,
                "replaces_slot": None,
            }
        )
    )
    incomplete = resolve(
        f,
        r.id,
        config,
        facts,
        manifest_hash=r.manifest_hash,
        source_hash=r.source_hash,
        members=(),
        expires_at=r.resolution_expires_at,
    )
    conflicted = resolve(
        f,
        r.id,
        config,
        facts + (contrary,),
        manifest_hash=r.manifest_hash,
        source_hash=r.source_hash,
        members=r.source_members,
        expires_at=r.resolution_expires_at,
    )
    assert conflicted.contradicting_events == (contrary.event_id,)
    for bad in (
        incomplete,
        conflicted,
        Resolution.model_validate_json(
            json.dumps({**r.payload(), "truncation_status": "TRUNCATED"})
        ),
        Resolution.model_validate_json(
            json.dumps({**r.payload(), "fitness_hash": digest("wrong")})
        ),
        Resolution.model_validate_json(
            json.dumps(
                {**conflicted.payload(), "consistency": "CONSISTENT", "contradicting_events": []}
            )
        ),
    ):
        with pytest.raises(PlanningDenied):
            validate(f, d, n, bad, config, now)
    with pytest.raises(PlanningDenied):
        validate(f, d, n, r, config, instant_end := datetime.fromisoformat(r.resolution_expires_at))
    assert instant_end > now
    for change in (
        {"upper_minutes": None},
        {"semantic_class": "PRESCRIBED_QUANTITY"},
        {"scope": "PRODUCTION"},
        {"subject_id": str(uuid4())},
        {"exercise": "unsupported:activity"},
    ):
        bad_fact = Fact.model_validate_json(json.dumps({**facts[0].payload(), **change}))
        with pytest.raises(PlanningDenied):
            resolve(
                f,
                r.id,
                config,
                (bad_fact,),
                manifest_hash=r.manifest_hash,
                source_hash=r.source_hash,
                members=r.source_members,
                expires_at=r.resolution_expires_at,
            )
    future_fact = Fact.model_validate_json(
        json.dumps({**facts[0].payload(), "effective_at": (now + timedelta(minutes=1)).isoformat()})
    )
    future_resolution = resolve(
        f,
        r.id,
        config,
        (future_fact,),
        manifest_hash=r.manifest_hash,
        source_hash=r.source_hash,
        members=r.source_members,
        expires_at=r.resolution_expires_at,
    )
    with pytest.raises(PlanningDenied):
        validate(f, d, n, future_resolution, config, now)
    # Two admitted sources for the same underlying event retain both source refs but count actual once.
    duplicate = Fact.model_validate_json(
        json.dumps({**facts[0].payload(), "fact_id": str(uuid4())})
    )
    duplicate_config = {
        **config,
        "required_members": sorted([*config["required_members"], duplicate.fact_id]),
    }
    dedup = resolve(
        f,
        r.id,
        duplicate_config,
        facts + (duplicate,),
        manifest_hash=r.manifest_hash,
        source_hash=r.source_hash,
        members=tuple(duplicate_config["required_members"]),
        expires_at=r.resolution_expires_at,
    )
    assert validate(f, d, n, dedup, duplicate_config, now)["rolling_minutes"] == 40
    badconfig = {**config, "reservations": {"other-slot": 80}}
    with pytest.raises(PlanningDenied):
        validate(
            f,
            compute_demand(f, d.id, badconfig),
            compute_nutrition(f, compute_demand(f, d.id, badconfig), n.id, badconfig),
            r,
            badconfig,
            now,
        )
    with pytest.raises(PlanningDenied):
        compute_demand(f, d.id, {**config, "rules": {**RULES, "unknown_exposure": "ZERO"}})


def test_namespace(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    selected = fixture_namespace(ROOT, head)
    expected_digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
    assert selected.project_name == f"kineticloop-kl076-fixture-{head[:7]}-{expected_digest}"
    assert selected.database_name == f"kineticloop_kl076_fixture_{head[:7]}_{expected_digest}"
    for root, sha, label in (
        (tmp_path, head, "fixture"),
        (ROOT, head[:7], "fixture"),
        (ROOT, "G" * 40, "fixture"),
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
