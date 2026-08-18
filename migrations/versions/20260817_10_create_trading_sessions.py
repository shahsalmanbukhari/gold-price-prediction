"""Create persisted trading-session metadata.

Revision ID: 20260817_10
Revises: 20260817_09
"""
from alembic import op
import sqlalchemy as sa

revision = "20260817_10"
down_revision = "20260817_09"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trading_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("session_start", sa.DateTime(), nullable=False),
        sa.Column("session_end", sa.DateTime(), nullable=False),
        sa.Column("candle_count", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_sessions_time", "trading_sessions", ["session_start", "session_end"])


def downgrade():
    op.drop_index("idx_sessions_time", table_name="trading_sessions")
    op.drop_table("trading_sessions")
