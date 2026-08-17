"""Deduplicate live quotes and enforce provider timestamp idempotency."""

from alembic import op

revision = "20260817_03"
down_revision = "20260817_02"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve the oldest copy of an identical provider market event. This is
    # deliberately scoped to live_api rows and cannot affect legacy sources.
    op.execute("""
        DELETE FROM prices duplicate
        USING prices keeper
        WHERE duplicate.source = 'live_api'
          AND keeper.source = 'live_api'
          AND duplicate.provider = keeper.provider
          AND duplicate.raw_symbol = keeper.raw_symbol
          AND duplicate."timestamp" = keeper."timestamp"
          AND duplicate.id > keeper.id
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_prices_live_provider_timestamp
        ON prices(provider, raw_symbol, "timestamp")
        WHERE source = 'live_api'
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_prices_live_provider_timestamp")
