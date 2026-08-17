"""Create dedicated HistData candle and import audit tables."""

from alembic import op
import sqlalchemy as sa

revision = "20260817_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gold_price_candles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("candle_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("open_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("high_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("low_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("close_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("volume", sa.Numeric(20, 6)),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("source_file", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "symbol", "timeframe", "candle_time", name="uq_gold_price_candle"),
    )
    op.create_index(
        "idx_gold_price_candles_lookup", "gold_price_candles",
        ["symbol", "timeframe", "candle_time"],
    )
    op.create_table(
        "historical_data_imports",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("source_zip", sa.String(255), nullable=False),
        sa.Column("source_csv", sa.String(255)),
        sa.Column("file_checksum", sa.String(128)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("total_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("inserted_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("duplicate_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "idx_historical_import_lookup", "historical_data_imports",
        ["provider", "symbol", "timeframe", "source_zip"],
    )


def downgrade():
    op.drop_index("idx_historical_import_lookup", table_name="historical_data_imports")
    op.drop_table("historical_data_imports")
    op.drop_index("idx_gold_price_candles_lookup", table_name="gold_price_candles")
    op.drop_table("gold_price_candles")
