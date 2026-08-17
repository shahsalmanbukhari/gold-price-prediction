"""Durable worker heartbeat, trust state and notification delivery.

Revision ID: 20260817_07
Revises: 20260817_06
"""
from alembic import op
import sqlalchemy as sa

revision = "20260817_07"
down_revision = "20260817_06"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "service_heartbeats",
        sa.Column("service_name", sa.String(100), primary_key=True),
        sa.Column("instance_id", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("last_live_quote_at", sa.DateTime(timezone=True)),
        sa.Column("last_prediction_at", sa.DateTime(timezone=True)),
        sa.Column("last_evaluation_at", sa.DateTime(timezone=True)),
        sa.Column("last_training_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("version", sa.String(50), nullable=False),
    )
    op.create_index("ix_service_heartbeats_last_heartbeat_at", "service_heartbeats", ["last_heartbeat_at"])
    op.create_table(
        "horizon_model_status",
        sa.Column("horizon_minutes", sa.Integer(), primary_key=True),
        sa.Column("model_version", sa.String(100), primary_key=True),
        sa.Column("algorithm", sa.String(100), nullable=False),
        sa.Column("trust_status", sa.String(20), nullable=False),
        sa.Column("offline_test_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("offline_improvement_pct", sa.Float()),
        sa.Column("rolling_sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rolling_mae", sa.Float()),
        sa.Column("rolling_baseline_mae", sa.Float()),
        sa.Column("rolling_directional_accuracy_pct", sa.Float()),
        sa.Column("alert_suppression_reason", sa.Text()),
        sa.Column("last_prediction_at", sa.DateTime(timezone=True)),
        sa.Column("next_target_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("horizon_predictions.id"), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_type", "prediction_id", "channel", name="uq_notification_delivery"),
    )
    op.create_index("ix_notification_deliveries_event_type", "notification_deliveries", ["event_type"])
    op.create_index("ix_notification_deliveries_prediction_id", "notification_deliveries", ["prediction_id"])
    op.create_index("ix_notification_deliveries_status", "notification_deliveries", ["status"])
    op.execute("UPDATE horizon_predictions SET latest_live_price_at = prediction_created_at WHERE latest_live_price_at IS NULL")
    op.alter_column("horizon_predictions", "latest_live_price_at", nullable=False)
    op.drop_constraint("uq_production_horizon_prediction", "horizon_predictions", type_="unique")
    op.create_unique_constraint(
        "uq_production_horizon_prediction", "horizon_predictions",
        ["symbol", "timeframe", "provider", "algorithm_name", "algorithm_version",
         "model_version", "feature_data_until", "latest_live_price_at", "horizon_minutes"],
    )


def downgrade():
    op.drop_constraint("uq_production_horizon_prediction", "horizon_predictions", type_="unique")
    op.create_unique_constraint(
        "uq_production_horizon_prediction", "horizon_predictions",
        ["symbol", "timeframe", "provider", "algorithm_name", "algorithm_version",
         "model_version", "feature_data_until", "horizon_minutes"],
    )
    op.alter_column("horizon_predictions", "latest_live_price_at", nullable=True)
    op.drop_table("notification_deliveries")
    op.drop_table("horizon_model_status")
    op.drop_index("ix_service_heartbeats_last_heartbeat_at", table_name="service_heartbeats")
    op.drop_table("service_heartbeats")
