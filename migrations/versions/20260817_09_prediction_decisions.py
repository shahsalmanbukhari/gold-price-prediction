"""Prediction alert-decision audit.

Revision ID: 20260817_09
Revises: 20260817_08
"""
from alembic import op
import sqlalchemy as sa

revision = "20260817_09"
down_revision = "20260817_08"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "prediction_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("horizon_predictions.id")),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False), sa.Column("provider", sa.String(50)),
        sa.Column("horizon_minutes", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(100)), sa.Column("model_version", sa.String(100)),
        sa.Column("reference_price", sa.Numeric(18, 6)), sa.Column("predicted_price", sa.Numeric(18, 6)),
        sa.Column("predicted_direction", sa.String(10)),
        sa.Column("acceptance_status", sa.String(20), nullable=False),
        sa.Column("acceptance_reason_code", sa.String(60), nullable=False),
        sa.Column("acceptance_reason_detail", sa.Text()),
        sa.Column("trust_status_at_decision", sa.String(20)),
        sa.Column("required_sample_count", sa.Integer()), sa.Column("actual_sample_count", sa.Integer()),
        sa.Column("required_directional_accuracy", sa.Float()), sa.Column("actual_directional_accuracy", sa.Float()),
        sa.Column("required_baseline_improvement", sa.Float()), sa.Column("actual_baseline_improvement", sa.Float()),
        sa.Column("required_prediction_magnitude", sa.Float()), sa.Column("actual_prediction_magnitude", sa.Float()),
        sa.Column("data_fresh", sa.Boolean()), sa.Column("missing_period_count", sa.Integer()),
        sa.Column("technical_context", sa.JSON()),
        sa.UniqueConstraint("prediction_id", name="uq_prediction_decision_prediction"),
    )
    op.create_index("ix_prediction_decisions_prediction_id", "prediction_decisions", ["prediction_id"])
    op.create_index("ix_prediction_decisions_decision_at", "prediction_decisions", ["decision_at"])
    op.create_index("ix_prediction_decisions_horizon_minutes", "prediction_decisions", ["horizon_minutes"])
    op.create_index("ix_prediction_decisions_model_version", "prediction_decisions", ["model_version"])
    op.create_index("ix_prediction_decisions_acceptance_status", "prediction_decisions", ["acceptance_status"])
    op.create_index("ix_prediction_decisions_acceptance_reason_code", "prediction_decisions", ["acceptance_reason_code"])
    op.create_index("ix_prediction_decisions_trust_status_at_decision", "prediction_decisions", ["trust_status_at_decision"])
    op.create_index("idx_prediction_decisions_filters", "prediction_decisions", ["decision_at", "horizon_minutes", "model_version", "acceptance_status"])


def downgrade():
    op.drop_table("prediction_decisions")
