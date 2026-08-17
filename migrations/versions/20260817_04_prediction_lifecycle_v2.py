"""Add UTC-aware, versioned prediction lifecycle and preserve legacy rows."""

from alembic import op
import sqlalchemy as sa

revision = "20260817_04"
down_revision = "20260817_03"
branch_labels = None
depends_on = None


def upgrade():
    # Existing timestamps were written as UTC-naive values. AT TIME ZONE 'UTC'
    # preserves the represented instant while converting to timestamptz.
    for table, column in (
        ("prices", "timestamp"), ("prices", "created_at"),
        ("horizon_predictions", "created_at"),
        ("horizon_predictions", "target_at"),
        ("horizon_predictions", "actual_at"),
        ("horizon_predictions", "evaluated_at"),
    ):
        op.execute(f'''ALTER TABLE {table} ALTER COLUMN "{column}" TYPE TIMESTAMPTZ USING "{column}" AT TIME ZONE 'UTC' ''')

    op.add_column("prices", sa.Column("provider_timestamp_raw", sa.String(100)))
    op.add_column("prices", sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

    columns = [
        sa.Column("symbol", sa.String(20)), sa.Column("timeframe", sa.String(10)),
        sa.Column("provider", sa.String(50)), sa.Column("algorithm_name", sa.String(100)),
        sa.Column("algorithm_version", sa.String(50)), sa.Column("feature_schema_version", sa.String(50)),
        sa.Column("prediction_created_at", sa.DateTime(timezone=True)),
        sa.Column("feature_data_until", sa.DateTime(timezone=True)),
        sa.Column("reference_price", sa.Numeric(18, 6)),
        sa.Column("predicted_return", sa.Numeric(20, 12)), sa.Column("baseline_price", sa.Numeric(18, 6)),
        sa.Column("interval_method", sa.String(50)), sa.Column("status", sa.String(20)),
        sa.Column("latest_live_price_at", sa.DateTime(timezone=True)),
        sa.Column("last_completed_candle_at", sa.DateTime(timezone=True)),
        sa.Column("missing_period_count", sa.Integer()), sa.Column("actual_provider", sa.String(50)),
        sa.Column("evaluation_delay_seconds", sa.Integer()), sa.Column("actual_tolerance_seconds", sa.Integer()),
        sa.Column("evaluator_version", sa.String(50)), sa.Column("absolute_error", sa.Numeric(18, 6)),
        sa.Column("percentage_error", sa.Numeric(20, 12)), sa.Column("baseline_absolute_error", sa.Numeric(18, 6)),
        sa.Column("model_improvement_over_baseline", sa.Numeric(18, 6)), sa.Column("failure_reason", sa.Text()),
        sa.Column("retry_count", sa.Integer()), sa.Column("direction_threshold", sa.Numeric(20, 12)),
        sa.Column("direction_policy_version", sa.String(50)),
    ]
    for column in columns:
        op.add_column("horizon_predictions", column)

    # Preserve old values and make their uncertain provenance explicit.
    op.execute("""
        UPDATE horizon_predictions SET
          symbol = 'XAUUSD', timeframe = '1m', provider = 'legacy_unknown',
          algorithm_name = CASE WHEN model_name = 'adaptive_momentum'
                                THEN 'adaptive_momentum_baseline' ELSE 'legacy_unknown' END,
          algorithm_version = 'legacy-v1', feature_schema_version = 'legacy_unknown',
          prediction_created_at = created_at, feature_data_until = created_at,
          reference_price = current_price, predicted_return = (predicted_price-current_price)/NULLIF(current_price,0),
          baseline_price = current_price, status = 'LEGACY',
          last_completed_candle_at = created_at, missing_period_count = 0,
          actual_tolerance_seconds = 90, retry_count = 0,
          direction_threshold = 0.0005, direction_policy_version = 'legacy_direction_unknown',
          absolute_error = CASE WHEN actual_price IS NULL THEN NULL ELSE ABS(actual_price-predicted_price) END,
          percentage_error = error_pct
    """)
    required = ["symbol", "timeframe", "provider", "algorithm_name", "algorithm_version",
                "feature_schema_version", "prediction_created_at", "feature_data_until", "reference_price",
                "predicted_return", "baseline_price", "status", "last_completed_candle_at",
                "missing_period_count", "actual_tolerance_seconds", "retry_count", "direction_threshold",
                "direction_policy_version"]
    for name in required:
        op.alter_column("horizon_predictions", name, nullable=False)

    op.alter_column("horizon_predictions", "predicted_price", type_=sa.Numeric(18, 6), postgresql_using="predicted_price::numeric")
    op.alter_column("horizon_predictions", "lower_bound", type_=sa.Numeric(18, 6), postgresql_using="lower_bound::numeric")
    op.alter_column("horizon_predictions", "upper_bound", type_=sa.Numeric(18, 6), postgresql_using="upper_bound::numeric")
    op.alter_column("horizon_predictions", "actual_price", type_=sa.Numeric(18, 6), postgresql_using="actual_price::numeric")

    op.create_check_constraint("ck_horizon_minutes", "horizon_predictions", "horizon_minutes IN (3,5,15,30,60,240)")
    op.create_check_constraint("ck_horizon_positive_prices", "horizon_predictions", "reference_price > 0 AND predicted_price > 0 AND baseline_price > 0")
    op.create_check_constraint("ck_horizon_status", "horizon_predictions", "status IN ('PENDING','EVALUATED','UNRESOLVABLE','FAILED','LEGACY')")
    op.create_check_constraint("ck_horizon_unresolvable_reason", "horizon_predictions", "status <> 'UNRESOLVABLE' OR failure_reason IS NOT NULL")
    op.create_check_constraint("ck_horizon_evaluated_fields", "horizon_predictions", "status <> 'EVALUATED' OR (actual_price IS NOT NULL AND actual_at IS NOT NULL AND evaluated_at IS NOT NULL AND absolute_error IS NOT NULL AND percentage_error IS NOT NULL)")
    op.create_unique_constraint("uq_production_horizon_prediction", "horizon_predictions", [
        "symbol", "timeframe", "provider", "algorithm_name", "algorithm_version", "model_version",
        "feature_data_until", "horizon_minutes",
    ])
    op.create_index("idx_horizon_pending_due", "horizon_predictions", ["status", "target_at"])
    op.create_table(
        "training_scheduler_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_candle_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_outcome_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_successful_training_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("INSERT INTO training_scheduler_state (id) VALUES (1)")


def downgrade():
    raise RuntimeError("Prediction lifecycle v2 is intentionally non-destructive and cannot be safely downgraded")
