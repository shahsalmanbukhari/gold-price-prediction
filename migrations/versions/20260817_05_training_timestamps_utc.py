"""Make model-training lifecycle timestamps explicitly UTC-aware."""

from alembic import op

revision = "20260817_05"
down_revision = "20260817_04"
branch_labels = None
depends_on = None


def upgrade():
    for table, column in (
        ("retraining_runs", "requested_at"),
        ("retraining_runs", "started_at"),
        ("retraining_runs", "completed_at"),
        ("models", "trained_at"),
        ("models", "created_at"),
    ):
        op.execute(
            f'''ALTER TABLE {table} ALTER COLUMN "{column}" TYPE TIMESTAMPTZ
                USING "{column}" AT TIME ZONE 'UTC' '''
        )


def downgrade():
    raise RuntimeError("UTC timestamp conversion cannot be safely reversed")
