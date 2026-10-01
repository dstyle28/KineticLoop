"""Materialize frozen S27 active partition uniqueness (legacy PENDING = ADMITTED)."""

from alembic import op

revision = "e8c2f1a6b904"
down_revision = "d4c1a9e7b203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute(
        "CREATE UNIQUE INDEX uq_s27_active_partition ON "
        "kineticloop.planning_intents (subject_id,local_date,purpose) "
        "WHERE status IN ('ADMITTED','PENDING','RUNNING')"
    )


def downgrade() -> None:
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("DROP INDEX kineticloop.uq_s27_active_partition")
