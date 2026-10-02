from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from kineticloop.contracts.artifacts import (
    ArtifactBindingKind,
    ArtifactDependencyError,
    ArtifactValiditySpec,
    validate_complete_dependency_closure,
)
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseLifecycleError, DatabaseNamespace
from kineticloop.protocol.authorization import (
    AUTHORIZATION_METHOD_VERSION,
    AuthorizationEvaluationError,
    ExecutabilityBasis,
    ValidityDependency,
    evaluate_executability,
    evaluate_validity_closure,
)
from kineticloop.protocol.factsets import EvidenceBasis, Factset, FactsetError, Member, reconstruct

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
    "KINETICLOOP_KL027_DATABASE",
    "KINETICLOOP_KL027_COMPOSE_PROJECT",
    "KINETICLOOP_KL029_DATABASE",
    "KINETICLOOP_KL029_COMPOSE_PROJECT",
    "KINETICLOOP_KL028_DATABASE",
    "KINETICLOOP_KL028_COMPOSE_PROJECT",
    "PGDATABASE",
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "KINETICLOOP_DB_USER",
    "KINETICLOOP_DB_PASSWORD",
}


def fixture_namespace(
    root: Path, head: str, label: str = "boundary", *, worktree_digest: str | None = None
) -> DatabaseNamespace:
    if root.resolve() != ROOT or not re.fullmatch(r"[0-9a-f]{40}", head) or label != "boundary":
        raise DatabaseLifecycleError("exact KL028 task/SHA/resolved-root/label required")
    token = hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:12]
    if worktree_digest is not None and (
        not re.fullmatch(r"[0-9a-f]{12}", worktree_digest) or token != worktree_digest
    ):
        raise DatabaseLifecycleError("exact resolved worktree digest required")
    return DatabaseNamespace(
        f"kineticloop-kl028-{label}-{head[:7]}-{token}",
        f"kineticloop_kl028_{label}_{head[:7]}_{token}",
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
            raise DatabaseLifecycleError("foreign KL028 lifecycle/ambient target")

    def _run(self, command: Any, **kwargs: Any) -> Any:
        self.validate_target()
        kwargs.setdefault("timeout_seconds", 60)
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


def test_boundary_namespace(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    selected = fixture_namespace(ROOT, head)
    expected_digest = hashlib.sha256(os.fsencode(ROOT.resolve())).hexdigest()[:12]
    assert selected.project_name == f"kineticloop-kl028-boundary-{head[:7]}-{expected_digest}"
    assert selected.database_name == f"kineticloop_kl028_boundary_{head[:7]}_{expected_digest}"
    for root, sha, label in (
        (tmp_path, head, "boundary"),
        (ROOT, head[:7], "boundary"),
        (ROOT, "G" * 40, "boundary"),
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
    for stale_head in ("0" * 40, "f" * 40):
        if stale_head != head:
            with pytest.raises(DatabaseLifecycleError):
                OwnedLifecycle(ROOT, stale_head, environ={}, runner=runner)
    for action_name in ("reset", "start", "destroy", "connection"):

        def nested(lifecycle: Any) -> Any:
            lifecycle.namespace = DatabaseNamespace("foreign", "postgres")
            try:
                return getattr(lifecycle, action_name)()
            finally:
                lifecycle.destroy()  # Nested finally must fail before a runner call too.

        with pytest.raises(DatabaseLifecycleError):
            own.bootstrap(nested)
        own.namespace = selected
    own.root = tmp_path
    with pytest.raises(DatabaseLifecycleError):
        own.destroy()
    own.root = ROOT
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
    evidence(
        "namespace_guard_PU",
        tested_commit=head,
        resolved_root=str(ROOT),
        compose=selected.project_name,
        database=selected.database_name,
        rejected_ambient=sorted(AMBIENT),
        nested_routes=own.inventory,
        foreign_runner_calls=0,
        permitted_fake_runner_calls=len(calls),
    )


NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def evidence(label: str, **values: Any) -> None:
    print("BOUNDARY_PU " + json.dumps({"label": label, **values}, default=str, sort_keys=True))


def bounds() -> list[ValidityDependency]:
    return [
        ValidityDependency(
            kind, str(UUID(int=n)), n, NOW - timedelta(minutes=1), NOW + timedelta(seconds=300)
        )
        for n, kind in enumerate(
            (
                "MANIFEST",
                "PROJECTION",
                "RESOLUTION",
                "VALIDATION",
                "ADMISSION_FRESHNESS",
                "ARTIFACT",
                "POLICY_TTL",
                "REQUEST_DEADLINE",
                "CALENDAR_END",
            ),
            1,
        )
    ]


def closure(values: Any, requested: Any = None) -> Any:
    return evaluate_validity_closure(
        authoritative_now=NOW, dependencies=values, requested_absolute_end=requested
    )


def verify_certificate(result: Any, values: Any) -> None:
    assert result.valid_from == NOW and result.method_version == AUTHORIZATION_METHOD_VERSION
    assert {
        (x["dependency_kind"], x["identity"], x["revision"])
        for x in result.dependencies
        if x["dependency_kind"] != "REQUESTED_ABSOLUTE_END"
    } == {(x.dependency_kind, x.identity, x.revision) for x in values}
    entries = [dict(x) for x in result.dependencies]
    assert entries == sorted(
        entries, key=lambda x: (x["dependency_kind"], x["identity"], str(x["revision"]))
    )
    assert (
        hashlib.sha256(
            json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == result.closure_digest
    )
    evidence(
        "exact_certificate",
        valid_until=result.valid_until,
        dependencies=entries,
        digest=result.closure_digest,
        method=result.method_version,
    )


def test_b01_unsealed_canonical_denial() -> None:
    base = Factset(
        UUID(int=15),
        UUID(int=1),
        "BUILDING",
        "FULL",
        None,
        0,
        1,
        (Member("FACT", "actual", "TEST_ONLY", UUID(int=14)),),
        EvidenceBasis((), (), (), "cutoff", "TEST_ONLY"),
    )
    content = reconstruct(base, {}, max_depth=1)
    closed = replace(
        base, membership_digest=content.membership_digest, member_count=content.member_count
    )
    for status in ("BUILDING", "READY"):
        with pytest.raises(FactsetError, match="unsealed") as error:
            reconstruct(replace(closed, status=status), {}, max_depth=1, canonical=True)
        evidence("canonical_denial", status=status, cause=str(error.value))
    sealed = replace(closed, status="SEALED")
    assert reconstruct(sealed, {}, max_depth=1, canonical=True) == content
    delta = replace(sealed, id=UUID(int=16), mode="DELTA", parent_id=sealed.id, depth=1, members=())
    assert reconstruct(delta, {sealed.id: sealed}, max_depth=1, canonical=True) == content
    for status in ("BUILDING", "READY"):
        with pytest.raises(FactsetError, match="unsealed"):
            reconstruct(
                delta, {sealed.id: replace(sealed, status=status)}, max_depth=1, canonical=True
            )
    evidence(
        "sealed_exact_membership", digest=content.membership_digest, count=content.member_count
    )


def test_b08_missing_validity_denied() -> None:
    values = bounds()
    verify_certificate(closure(values), values)
    for index, value in enumerate(values):
        for change in (
            {"valid_from": None},
            {"valid_until": None},
            {"validity_kind": "UNKNOWN"},
            {"valid_from": NOW + timedelta(seconds=1)},
            {"valid_until": NOW},
            {"valid_until": NOW - timedelta(seconds=1)},
            {"valid_from": NOW, "valid_until": NOW},
        ):
            candidate = [*values]
            candidate[index] = replace(value, **change)
            with pytest.raises(AuthorizationEvaluationError) as error:
                closure(candidate)
            evidence(
                "required_validity_denied",
                identity=value.identity,
                revision=value.revision,
                change=change,
                cause=str(error.value),
            )


def test_b09_server_minimum_closure() -> None:
    values = bounds()
    for index, value in enumerate(values):
        candidate = [*values]
        candidate[index] = replace(value, valid_until=NOW + timedelta(seconds=20 + index))
        result = closure(candidate)
        assert result.valid_until == candidate[index].valid_until
        verify_certificate(result, candidate)
        reverse = closure(list(reversed(candidate)))
        assert (
            reverse.dependencies == result.dependencies
            and reverse.closure_digest == result.closure_digest
        )
        shortened = closure(candidate, NOW + timedelta(seconds=10))
        assert shortened.valid_until == NOW + timedelta(seconds=10)
        verify_certificate(shortened, candidate)
        assert closure(candidate, NOW + timedelta(hours=2)).valid_until == result.valid_until
        for change in ({"valid_until": None}, {"valid_until": NOW}):
            bad = [*candidate]
            bad[index] = replace(value, **change)
            with pytest.raises(AuthorizationEvaluationError):
                closure(bad)


def test_b10_expiry_without_status_job() -> None:
    end = NOW + timedelta(seconds=30)
    basis = ExecutabilityBasis(
        NOW,
        "subject",
        "subject",
        "content",
        "content",
        "TEST_ONLY",
        "TEST_ONLY",
        1,
        1,
        NOW,
        end,
        "ACTIVE",
        True,
        (),
        True,
        True,
        True,
    )
    for instant, expected in (
        (end - timedelta(microseconds=1), True),
        (end, False),
        (end + timedelta(microseconds=1), False),
    ):
        decision = evaluate_executability(replace(basis, authoritative_now=instant))
        assert decision.is_executable is expected and decision.non_bearer
        assert decision.denial_reasons == (() if expected else ("TIME_INELIGIBLE",))
        assert basis.target_state == "ACTIVE"
        evidence("half_open_PU", basis=asdict(basis), decision=asdict(decision))


def test_b17_transitive_closure_omission_denied() -> None:
    a, b, c = [str(UUID(int=n, version=4)) for n in (171, 172, 173)]
    graph = {a: (b,), b: (c,), c: ()}
    for partial in ((a,), (a, b)):
        with pytest.raises(ArtifactDependencyError):
            validate_complete_dependency_closure(partial, graph)
    assert set(validate_complete_dependency_closure((a, b, c), graph)) == {a, b, c}
    values = [
        ValidityDependency(
            "ARTIFACT",
            identity,
            1,
            NOW - timedelta(seconds=1),
            NOW + timedelta(minutes=1),
            dependency_ids=graph[identity],
        )
        for identity in (a, b, c)
    ]
    verify_certificate(closure(values), values)
    values[-1] = replace(values[-1], revoked=True)
    with pytest.raises(
        AuthorizationEvaluationError, match="current admission is unprovable"
    ) as error:
        closure(values)
    assert values[0].revoked is False and values[1].revoked is False
    evidence("transitive_leaf_denial", graph=graph, cause=str(error.value))


def test_b18_timeless_policy_reason_required() -> None:
    policy_id, static_id = str(UUID(int=181, version=4)), str(UUID(int=182, version=4))
    for policy, reason in ((None, "audited static"), (policy_id, None), (policy_id, "")):
        with pytest.raises(ValueError, match="approval policy and reason"):
            ArtifactValiditySpec(
                "TIMELESS",
                NOW,
                ArtifactBindingKind.EVALUATION_RELEASE,
                str(UUID(int=183, version=4)),
                timeless_approval_policy=policy,
                timeless_approval_reason=reason,
            )
    valid = ArtifactValiditySpec(
        "TIMELESS",
        NOW,
        ArtifactBindingKind.EVALUATION_RELEASE,
        str(UUID(int=183, version=4)),
        timeless_approval_policy=policy_id,
        timeless_approval_reason="audited static",
    )
    assert valid.canonical_payload()["valid_until"] is None
    approval = ValidityDependency(
        "ARTIFACT",
        policy_id,
        1,
        NOW - timedelta(seconds=1),
        NOW + timedelta(hours=1),
        artifact_kind="POLICY",
    )
    static = ValidityDependency(
        "ARTIFACT",
        static_id,
        1,
        NOW - timedelta(seconds=1),
        None,
        validity_kind="TIMELESS",
        artifact_kind="MODEL",
        timeless_approval_policy=policy_id,
        timeless_approval_reason="audited static",
        dependency_ids=(policy_id,),
    )
    finite = bounds()[0]
    verify_certificate(closure([approval, static, finite]), [approval, static, finite])
    assert closure([approval, static, finite]).valid_until == finite.valid_until
    for values in (
        [static, finite],
        [replace(approval, artifact_kind="MODEL"), static, finite],
        [replace(approval, revoked=True), static, finite],
        [replace(approval, admissible=None), static, finite],
        [approval, replace(static, dependency_ids=()), finite],
        [approval, replace(static, timeless_approval_reason=""), finite],
    ):
        with pytest.raises(AuthorizationEvaluationError) as error:
            closure(values)
        evidence("timeless_denied", cause=str(error.value), identities=[x.identity for x in values])
