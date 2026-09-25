"""Create the frozen KineticLoop S01-S51 PostgreSQL baseline.

Revision ID: 20260924_0001
Revises: none
"""

from typing import Sequence

from alembic import op

from kineticloop.persistence.metadata import (
    BASELINE_METADATA,
    install_baseline_protections,
)

revision: str = "20260924_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    BASELINE_METADATA.create_all(connection, checkfirst=False)
    install_baseline_protections(connection)


def downgrade() -> None:
    # Roles are cluster-scoped and may carry grants in another isolated test database.
    # Dropping this database's objects revokes its grants without disrupting neighbors.
    connection = op.get_bind()
    BASELINE_METADATA.drop_all(connection, checkfirst=False)
    connection.exec_driver_sql("DROP FUNCTION IF EXISTS guard_factset_member_mutation()")
    connection.exec_driver_sql("DROP FUNCTION IF EXISTS guard_factset_revision_mutation()")
    connection.exec_driver_sql("DROP FUNCTION IF EXISTS reject_immutable_history_mutation()")
