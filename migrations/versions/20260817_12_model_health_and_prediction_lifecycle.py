"""Add model health and complete prediction evaluation lifecycle.

Revision ID: 20260817_12
Revises: 20260817_11
"""
from alembic import op
import sqlalchemy as sa

revision = "20260817_12"
down_revision = "20260817_11"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("horizon_predictions", sa.Column("status_reason", sa.Text()))
    op.add_column("horizon_predictions", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("horizon_predictions", sa.Column("evaluation_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("horizon_predictions", sa.Column("last_evaluation_attempt", sa.DateTime(timezone=True)))
    op.add_column("horizon_predictions", sa.Column("failed_at", sa.DateTime(timezone=True)))
    op.add_column("horizon_predictions", sa.Column("unresolvable_reason", sa.Text()))
    op.create_index("idx_predictions_status", "horizon_predictions", ["status"])
    op.create_index("idx_predictions_evaluation_due", "horizon_predictions", ["status", "target_at"],
                    postgresql_where=sa.text("status IN ('PENDING', 'RETRYING')"))
    op.create_table(
        "model_health",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("horizon_minutes", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model_mae", sa.Float()), sa.Column("persistence_mae", sa.Float()),
        sa.Column("directional_accuracy", sa.Float()), sa.Column("sample_count", sa.Integer()),
        sa.Column("checked_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("alert_sent", sa.Boolean(), server_default=sa.false()),
    )


def downgrade():
    op.drop_table("model_health")
    op.drop_index("idx_predictions_evaluation_due", table_name="horizon_predictions")
    op.drop_index("idx_predictions_status", table_name="horizon_predictions")
    for column in ("unresolvable_reason", "failed_at", "last_evaluation_attempt", "evaluation_attempts", "max_retries", "status_reason"):
        op.drop_column("horizon_predictions", column)
