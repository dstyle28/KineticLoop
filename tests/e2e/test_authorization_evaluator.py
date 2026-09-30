from __future__ import annotations

from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from kineticloop.contracts.safety_registry import revocation_payload_hash
from kineticloop.db.lifecycle import DatabaseLifecycle, DatabaseNamespace
from kineticloop.persistence.subject_scope import TEST_SUBJECT_LOGINS
from kineticloop.persistence.transactions import query_execution_eligibility

ROOT = Path(__file__).parents[2]
_TX_SPEC = spec_from_file_location(
    "kl022_e2e_transaction_seed", ROOT / "tests/db/test_transaction_interfaces.py"
)
assert _TX_SPEC is not None and _TX_SPEC.loader is not None
_TX: Any = module_from_spec(_TX_SPEC)
_TX_SPEC.loader.exec_module(_TX)


def test_test_subject_eligibility_query_is_current_and_non_bearer() -> None:
    lifecycle = DatabaseLifecycle(ROOT)
    lifecycle.namespace = DatabaseNamespace(
        project_name="kineticloop-kl022-e2e-08e743c",
        database_name="kineticloop_kl022_e2e_08e743c",
    )
    try:
        urls = _TX._MIGRATIONS.bootstrap_two_phase(lifecycle)
        _TX._SAFETY.seed(urls["admin"])
        _TX._seed_transaction_rows(urls["admin"])
        prescription_id, authorization_id = _TX._seed_current_t7_pair(urls["admin"])
        environment_id = UUID("00000000-0000-8000-8000-000000022405")
        with psycopg.connect(urls["admin"], autocommit=True) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE kineticloop.policy_bundles SET policy_namespace='test:kl022' "
                "WHERE id=%s",
                (_TX.POLICY,),
            )
            connection.execute(
                "INSERT INTO kineticloop.subject_scopes"
                "(subject_id,namespace,policy_id,environment_id) VALUES (%s,'TEST',%s,%s)",
                (_TX.SUBJECT, _TX.POLICY, environment_id),
            )
            connection.execute(
                "INSERT INTO kineticloop.subject_principal_bindings"
                "(principal_name,subject_id,namespace) VALUES (%s,%s,'TEST')",
                (TEST_SUBJECT_LOGINS[0], _TX.SUBJECT),
            )
            connection.execute("SET session_replication_role=origin")

        def current_query() -> Any:
            with psycopg.connect(urls["admin"]) as connection:
                return query_execution_eligibility(
                    connection,
                    command_kind="StartSession",
                    subject_id=_TX.SUBJECT,
                    artifact_ids=_TX._registry_ids(),
                    artifact_identities=_TX._registry_identities(),
                    local_date=date(2026, 9, 26),
                    session_id=_TX.SESSION,
                    prescription_id=prescription_id,
                    authorization_id=authorization_id,
                    execution_scope="EXECUTION",
                )

        first = current_query()
        assert first.is_executable and first.non_bearer
        assert not hasattr(first, "permission_token")
        with psycopg.connect(urls["admin"]) as connection:
            baseline = connection.execute(
                "SELECT (SELECT count(*) FROM kineticloop.execution_bindings),"
                "(SELECT count(*) FROM kineticloop.command_receipts),"
                "(SELECT count(*) FROM kineticloop.domain_events),"
                "(SELECT count(*) FROM kineticloop.outbox_deliveries)"
            ).fetchone()

        with psycopg.connect(urls["trusted_admin"]) as connection:
            effective_at_row = connection.execute("SELECT clock_timestamp()").fetchone()
            assert effective_at_row is not None
            effective_at = effective_at_row[0]
            revoked = connection.execute(
                "SELECT * FROM kineticloop.registry_revoke_artifact("
                "%s,%s,%s,%s,%s,%s,%s,%s,5000)",
                (
                    _TX.DEPENDENCY,
                    "b" * 64,
                    effective_at,
                    "KL022_E2E_REVOKE",
                    revocation_payload_hash(
                        effective_at=effective_at, reason_code="KL022_E2E_REVOKE"
                    ),
                    "kl022-e2e-revoke",
                    "e" * 64,
                    UUID("00000000-0000-8000-8000-000000022406"),
                ),
            ).fetchone()
            assert revoked is not None
            connection.commit()

        second = current_query()
        assert not second.is_executable and second.non_bearer
        with psycopg.connect(urls["admin"]) as connection:
            assert connection.execute(
                "SELECT (SELECT count(*) FROM kineticloop.execution_bindings),"
                "(SELECT count(*) FROM kineticloop.command_receipts),"
                "(SELECT count(*) FROM kineticloop.domain_events),"
                "(SELECT count(*) FROM kineticloop.outbox_deliveries)"
            ).fetchone() == baseline
            assert connection.execute(
                "SELECT namespace,policy_id,environment_id FROM kineticloop.subject_scopes "
                "WHERE subject_id=%s",
                (_TX.SUBJECT,),
            ).fetchone() == ("TEST", _TX.POLICY, environment_id)
    finally:
        lifecycle.destroy()
