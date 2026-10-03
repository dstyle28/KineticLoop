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
    FULL_VERSION,
    RULES,
    Basis,
    Fact,
    compute_demand,
    compute_fitness,
    compute_nutrition,
    resolve,
    resolve_full,
    validate,
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
    "KINETICLOOP_KL080_DATABASE",
    "KINETICLOOP_KL080_COMPOSE_PROJECT",
    "KINETICLOOP_KL079_DATABASE",
    "KINETICLOOP_KL079_COMPOSE_PROJECT",
    "KINETICLOOP_KL077_DATABASE",
    "KINETICLOOP_KL077_COMPOSE_PROJECT",
}


def fixture_namespace(
    root: Path, head: str, label: str = "source", *, worktree_digest: str | None = None
) -> DatabaseNamespace:
    if root.resolve() != ROOT or not re.fullmatch(r"[0-9a-f]{40}", head) or label != "source":
        raise DatabaseLifecycleError("exact KL080 task/SHA/resolved-root/label required")
    token = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    if worktree_digest is not None and (
        not re.fullmatch(r"[0-9a-f]{12}", worktree_digest) or token != worktree_digest
    ):
        raise DatabaseLifecycleError("exact resolved worktree digest required")
    return DatabaseNamespace(
        f"kineticloop-kl080-{label}-{head[:7]}-{token}",
        f"kineticloop_kl080_{label}_{head[:7]}_{token}",
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
            raise DatabaseLifecycleError("foreign KL080 lifecycle/ambient target")

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


def test_namespace(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    selected = fixture_namespace(ROOT, head)
    expected_digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
    assert selected.project_name == f"kineticloop-kl080-source-{head[:7]}-{expected_digest}"
    assert selected.database_name == f"kineticloop_kl080_source_{head[:7]}_{expected_digest}"
    for root, sha, label in (
        (tmp_path, head, "source"),
        (ROOT, head[:7], "source"),
        (ROOT, "G" * 40, "source"),
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


def pipeline(full: bool, facts: tuple[Fact, ...], config: Any, base: Any, now: Any) -> Any:
    config = {
        **config,
        **(
            {"contract": FULL_VERSION, "required_actions": ["TRAINING", "NUTRITION"]}
            if full
            else {}
        ),
    }
    f = compute_fitness(base, str(uuid4()), {"minutes": 30, "equipment": []}, None)
    d = compute_demand(f, str(uuid4()), config)
    n = compute_nutrition(f, d, str(uuid4()), config)
    args = dict(
        manifest_hash=digest("manifest"),
        source_hash=digest("source"),
        members=tuple(config["required_members"]),
        expires_at=config["valid_until"],
    )
    if full:
        resolutions = tuple(
            resolve_full(
                f, d, n, str(uuid4()), config, facts, action_type=a, source_id=str(uuid4()), **args
            )
            for a in ("TRAINING", "NUTRITION")
        )
        # Both actions bind the identical physical source closure.
        resolutions = (
            resolutions[0],
            resolve_full(
                f,
                d,
                n,
                resolutions[1].id,
                config,
                facts,
                action_type="NUTRITION",
                source_id=resolutions[0].source_id,
                **args,
            ),
        )
        result = validate_full(f, d, n, resolutions, config, now)
        assert all(r.event_association_status == "CONFIRMED" for r in resolutions)
    else:
        r = resolve(f, str(uuid4()), config, facts, **args)
        result = validate(f, d, n, r, config, now)
        assert r.event_association_status == "CONFIRMED"
    assert n.semantic_class == "TARGET" and f.action.semantic_class == "PRESCRIBED_QUANTITY"
    return result


@pytest.mark.parametrize("full", [False, True], ids=["legacy", "full"])
def test_source_matrix(full: bool) -> None:
    base, config, facts, now = source_case()
    assert pipeline(full, facts, config, base, now)["rolling_minutes"] == 40
    counts = {}
    for field, values in (
        ("admission", ["NOT_ELIGIBLE", "UNRESOLVED", "ADMITTED", "ACCEPTED", "unknown", None]),
        ("association", ["AMBIGUOUS", "RETRACTED", "CONFIRMED", "unknown", None]),
    ):
        for value in values:
            with pytest.raises((PlanningDenied, ValidationError)):
                changed = Fact.model_validate_json(json.dumps({**facts[0].payload(), field: value}))
                pipeline(full, (changed,), config, base, now)
        counts[field] = len(values)
    # S27 remains the separate admitted-intent state in the frozen workflow.
    from kineticloop.workflow.planning import ACTIVE

    assert "ADMITTED" in ACTIVE
    print(
        "SOURCE_MATRIX_PU",
        {
            "full": full,
            "denials": counts,
            "S13": "ELIGIBLE",
            "S12": "MATCHED",
            "S36": "CONFIRMED",
            "rules": RULES,
        },
    )


@pytest.mark.parametrize("full", [False, True], ids=["legacy", "full"])
def test_basis_and_actual_separation(full: bool) -> None:
    base, config, facts, now = source_case()
    changes: list[dict[str, Any]] = [
        {"subject_id": str(uuid4())},
        {"policy_id": str(uuid4())},
        {"scope": "EXECUTION"},
        {"semantic_class": "TARGET"},
        {"semantic_class": "PRESCRIBED_QUANTITY"},
        {"upper_minutes": None},
        {"contradicts": True},
        {"retracted": True},
        {"valid_until": now.isoformat()},
        {"effective_at": (now + timedelta(minutes=1)).isoformat()},
        {"replaces_slot": "unknown"},
        {"fact_id": str(uuid4())},
        {"association_id": str(uuid4())},
        {"admission_id": str(uuid4())},
    ]
    for change in changes:
        changed = Fact.model_validate_json(json.dumps({**facts[0].payload(), **change}))
        with pytest.raises((PlanningDenied, ValidationError)):
            pipeline(full, (changed,), config, base, now)
    with pytest.raises(PlanningDenied):
        pipeline(full, facts + facts, config, base, now)
    changed = Fact.model_validate_json(
        json.dumps(
            {
                **facts[0].payload(),
                "fact_id": str(uuid4()),
                "admission_id": str(uuid4()),
                "association_id": str(uuid4()),
                "lower_minutes": 11,
                "upper_minutes": 11,
            }
        )
    )
    members = [x for f in (*facts, changed) for x in (f.fact_id, f.admission_id, f.association_id)]
    with pytest.raises(PlanningDenied):
        pipeline(full, (*facts, changed), {**config, "required_members": members}, base, now)
    identical = changed.model_copy(update={"lower_minutes": 10, "upper_minutes": 10})
    assert (
        pipeline(full, (*facts, identical), {**config, "required_members": members}, base, now)[
            "rolling_minutes"
        ]
        == 40
    )
    # External immutable references reject malformed hashes at the closed request
    # boundary. Exact source hashes/membership are also checked by real owners.
    from uuid import UUID

    from kineticloop.workflow.deterministic_planning import PreparationRequest
    from kineticloop.workflow.planning_progress import ProgressBasis

    progress = ProgressBasis(
        subject_id=UUID(base.subject_id),
        key="source-hash",
        intent_id=UUID(base.root_id),
        request_id=UUID(base.request_id),
        request_revision=1,
        attempt_id=UUID(base.attempt_id),
        expected_owner="TEST:fixture",
        fence=1,
        manifest_id=UUID(base.manifest_id),
        epoch=0,
        source_state="FITNESS",
    )
    for invalid_hash in ("unknown", "0" * 63, "G" * 64):
        with pytest.raises((PlanningDenied, ValueError)):
            PreparationRequest(
                **{k: getattr(progress, k) for k in ProgressBasis.__dataclass_fields__},
                kind="FITNESS",
                sources={"snapshot": {"id": base.snapshot_id, "hash": invalid_hash}},
            )
    # Half-open expiry equality is a pure clock assertion, never a PG timing claim.
    expires = datetime.fromisoformat(config["valid_until"])
    assert pipeline(full, facts, config, base, expires - timedelta(microseconds=1))
    with pytest.raises(PlanningDenied):
        pipeline(full, facts, config, base, expires)
    print("SOURCE_BASIS_PU", {"full": full, "denials": len(changes) + 3, "equality": "PU_ONLY"})


BASE_COMMIT = "034d6301316d0dade784a61b159c027b83fbce3a"
FIXTURE_EDITS = {
    "tests/db/test_factsets.py": [
        ("'unresolved','UNRESOLVED'", "'unresolved','AMBIGUOUS'"),
        ("'ALL','DENIED'", "'ALL','NOT_ELIGIBLE'"),
    ],
    "tests/db/test_preparation.py": [
        ("'actual-event','UNRESOLVED'", "'actual-event','AMBIGUOUS'"),
        ("'TEST_ONLY','ADMITTED'", "'TEST_ONLY','ELIGIBLE'"),
    ],
    "tests/db/test_protocol_interleavings.py": [
        ("'TEST_ONLY','ACCEPTED'", "'TEST_ONLY','ELIGIBLE'")
    ],
    "tests/db/test_transaction_interfaces.py": [
        ("'EXECUTION','ADMITTED'", "'EXECUTION','ELIGIBLE'")
    ],
}


def test_fixture_content_guards() -> None:
    for path, pairs in FIXTURE_EDITS.items():
        original = subprocess.check_output(["git", "show", BASE_COMMIT + ":" + path], cwd=ROOT)
        expected = original
        for old, new in pairs:
            assert expected.count(old.encode()) == 1
            expected = expected.replace(old.encode(), new.encode())
        assert (ROOT / path).read_bytes() == expected, path
    print("SIX_SOURCE_LITERAL_EDITS_ONLY", list(FIXTURE_EDITS))
