"""Persist candidate bundle identity and production-change outcome."""

from alembic import op
import sqlalchemy as sa

revision = "20260817_06"
down_revision = "20260817_05"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("retraining_runs", sa.Column("candidate_path", sa.String(500)))
    op.add_column("retraining_runs", sa.Column("production_changed", sa.Boolean()))
    op.execute("""
        UPDATE retraining_runs
           SET production_changed = CASE WHEN status = 'completed' THEN TRUE ELSE FALSE END
         WHERE production_changed IS NULL
    """)


def downgrade():
    op.drop_column("retraining_runs", "production_changed")
    op.drop_column("retraining_runs", "candidate_path")
