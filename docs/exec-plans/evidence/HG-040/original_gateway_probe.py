"""Reproduce the KL076 upstream blocker without a DB or lifecycle.

This is a pure capability diagnostic, never PostgreSQL/task acceptance evidence.
The connection double supplies only an idle transaction and recording cursor;
all gateway/session/column/binding checks are the actual merged implementation.
"""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

from psycopg.pq import TransactionStatus

from kineticloop.persistence.transactions import (
    GuardRequired,
    StatementRejected,
    execute_preparation,
)

ROOT = Path(__file__).resolve().parents[4]
SUBJECT, FACTSET, PROJECTION, POLICY, PROGRAM = [UUID(int=76000 + n) for n in range(5)]


def probe(owner, logical, values, expected_message):
    connection = MagicMock()
    connection.info.transaction_status = TransactionStatus.IDLE
    cursor = connection.cursor.return_value
    cursor.rowcount = 1
    try:
        execute_preparation(connection, owner, SUBJECT, lambda session: session.insert(logical, values))
    except (GuardRequired, StatementRejected) as error:
        assert expected_message in str(error), str(error)
        assert cursor.execute.call_count == 0
        print(json.dumps({"owner": owner, "table": logical, "exception": type(error).__name__,
            "message": str(error), "sql_calls": 0, "database_opened": False,
            "layer": "PURE_GATEWAY_DIAGNOSTIC", "classification": "UPSTREAM_CAPABILITY_BLOCKER"}, sort_keys=True))
    else:
        raise AssertionError("Expected the actual merged gateway to reject this required upstream write")


def main():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    print(json.dumps({"actual_revision": sha, "resolved_root": str(ROOT.resolve()),
        "scope": "no DB lifecycle, no PG assertions, no KL076 task/product PASS"}, sort_keys=True))
    projection = {"id": PROJECTION, "subject_id": SUBJECT, "projection_kind": "EXPOSURE", "input_basis_hash": "fixture-input-basis"}
    probe("RecordProjection", "S21", projection, "insert omits required fields ['revision']")
    probe("RecordProjection", "S21", {**projection, "revision": 1}, "cannot insert columns ['revision'] on S21")
    probe("RecordProjection", "S22", {"id": UUID(int=76100), "subject_id": SUBJECT,
        "dependency_kind": "FACTSET", "dependency_semantic_key": "current-factset",
        "ref_s21_id": PROJECTION, "ref_s15_id": FACTSET},
        "S22.ref_s15_id must bind an exact locked row")
    for status in ("BUILDING", "READY"):
        probe("BuildManifest", "S23", {"id": UUID(int=76200), "subject_id": SUBJECT,
            "build_identity": "test:kl076-upstream", "captured_epoch": 0, "status": status,
            "ref_s05_id": POLICY, "ref_s06_id": PROGRAM, "ref_s15_id": FACTSET,
            "ref_s21_id": PROJECTION}, "S23.ref_s15_id must bind an exact locked row")
    print("UPSTREAM_BLOCKER_REPRODUCED: 5 expected rejections, 0 SQL calls, no DB lifecycle")


if __name__ == "__main__":
    main()
