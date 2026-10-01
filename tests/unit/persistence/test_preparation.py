from __future__ import annotations

from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest

from kineticloop.persistence.metadata import REQUIRED_FIELDS
from kineticloop.persistence.transactions import (
    GuardRequired,
    RestrictedSqlSession,
    StatementRejected,
    _source_preparation_session,
)

_spec = spec_from_file_location(
    "kl078_test_namespace", Path(__file__).resolve().parents[2] / "db/test_preparation.py"
)
assert _spec is not None and _spec.loader is not None
_namespace = module_from_spec(_spec)
_spec.loader.exec_module(_namespace)
AMBIENT, ROOT = _namespace.AMBIENT, _namespace.ROOT
OwnedLifecycle, owned_namespace = _namespace.OwnedLifecycle, _namespace.owned_namespace


class FakeCursor:
    rowcount = 1

    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    def execute(self, query: Any, values: Any = None) -> None:
        self.calls.append((query, values))


def test_server_revision() -> None:
    from dataclasses import replace

    from kineticloop.persistence.preparation import (
        Dependency,
        RecordProjection,
        SourceBasis,
        projection_identity,
    )
    from kineticloop.persistence.transactions import ArtifactIdentity

    source = SourceBasis(uuid4(), "source-hash", "frontier", 0, uuid4(), uuid4(), None, None)
    record = RecordProjection(
        source,
        "EXPOSURE",
        ArtifactIdentity(uuid4(), "ENGINE", "engine", "1", "hash"),
        ("start", "end"),
        {"actual": "UNKNOWN"},
        (Dependency("FACTSET", "source"),),
        datetime.now(timezone.utc),
    )
    subject_identity = uuid4()
    a = projection_identity(subject_identity, record)
    assert projection_identity(subject_identity, record) == a
    b = projection_identity(subject_identity, replace(record, content={"actual": 0}))
    assert b[:2] == a[:2] and b[2] != a[2]
    c = projection_identity(
        subject_identity, replace(record, source=replace(source, source_hash="new-source"))
    )
    assert c[0] != a[0]

    subject, projection = uuid4(), uuid4()
    values = {
        "id": projection,
        "subject_id": subject,
        "projection_kind": "EXPOSURE",
        "input_basis_hash": "exact-source",
        "computed_at": datetime.now(timezone.utc),
        "valid_until": datetime.now(timezone.utc),
    }
    cursor: Any = FakeCursor()
    session = _source_preparation_session(
        cursor, "RecordProjection", subject, {"S21": {projection: values}}
    )
    assert session.insert("S21", values) == 1
    assert "revision" in REQUIRED_FIELDS["S21"]
    assert "revision" in cursor.calls[0][0].as_string()
    assert 1 in cursor.calls[0][1]
    session.validate_completion()
    for override in ({"revision": 8}, {"typed_payload": {"provenance": "caller"}}):
        with pytest.raises(GuardRequired):
            session.insert("S21", values | override)
    assert len(cursor.calls) == 1


def test_exact_capabilities() -> None:
    subject, source, projection = uuid4(), uuid4(), uuid4()
    for kind, table in (
        ("RecordProjection", "S21"),
        ("RecordProjection", "S22"),
        ("BuildManifest", "S23"),
    ):
        cursor: Any = FakeCursor()
        session = RestrictedSqlSession(
            cursor,
            ("S21", "S22", "S23"),
            subject,
            command_kind=kind,
            locked_ids={
                "factset_revisions": frozenset({source}),
                "manifest_builds": frozenset({projection}),
            },
            coordination_context={"verified_source": source, "preparation_token": object()},
        )
        with pytest.raises(GuardRequired):
            session.insert(table, {"subject_id": subject, "id": projection, "ref_s15_id": source})
        assert cursor.calls == []
        assert not hasattr(session, "execute") and not hasattr(session, "cursor")
    session = RestrictedSqlSession(
        cast(Any, FakeCursor()), ("S21", "S22"), subject, command_kind="RecordProjection"
    )
    with pytest.raises(StatementRejected):
        session.insert("S23", {"subject_id": subject})
    with pytest.raises(GuardRequired):
        session.update("S21", {"typed_payload": {}}, {"subject_id": subject, "id": projection})

    from psycopg.pq import TransactionStatus

    from kineticloop.persistence.transactions import execute_command, execute_preparation

    class Connection:
        class Info:
            transaction_status = TransactionStatus.IDLE

        info = Info()

        def transaction(self) -> Any:
            raise AssertionError("public coordination must reject before transaction")

    for kind in ("RecordProjection", "BuildManifest"):
        with pytest.raises(GuardRequired):
            execute_command(Connection(), kind, subject, lambda tx: None)  # type: ignore[arg-type]
    with pytest.raises(GuardRequired):
        execute_preparation(Connection(), "RecordSnapshot", subject, lambda tx: None)  # type: ignore[arg-type]


def test_namespace(tmp_path: Any) -> None:
    head = (
        __import__("subprocess")
        .check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True)
        .strip()
    )
    selected = owned_namespace(ROOT, head)
    assert selected.project_name.startswith(f"kineticloop-kl078-prep-{head[:7]}-")
    assert selected.database_name.startswith(f"kineticloop_kl078_prep_{head[:7]}_")
    for root, sha, label in (
        (tmp_path, head, "prep"),
        (ROOT, "a" * 7, "prep"),
        (ROOT, "G" * 40, "prep"),
        (ROOT, head, "foreign"),
    ):
        with pytest.raises(_namespace.DatabaseLifecycleError):
            owned_namespace(root, sha, label)
    calls: list[Any] = []

    def runner(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        raise AssertionError("must not enter destructive runner")

    own = OwnedLifecycle(ROOT, head, environ={}, runner=runner)
    from kineticloop.db.lifecycle import DatabaseNamespace

    for namespace in (
        DatabaseNamespace("foreign", "postgres"),
        DatabaseNamespace(selected.project_name, "postgres"),
        DatabaseNamespace(selected.project_name, selected.database_name[:-1] + "g"),
    ):
        own.namespace = namespace
        for action in (own.bootstrap, own.start, own.reset, own.destroy):
            with pytest.raises(_namespace.DatabaseLifecycleError):
                action()
    own.namespace = selected
    for key in AMBIENT:
        with pytest.raises(_namespace.DatabaseLifecycleError):
            OwnedLifecycle(ROOT, head, environ={key: "foreign"}, runner=runner)
        own._base_environ[key] = "foreign"
        for action in (own.bootstrap, own.start, own.reset, own.destroy):
            with pytest.raises(_namespace.DatabaseLifecycleError):
                action()
        own._base_environ.pop(key)
    assert calls == []
