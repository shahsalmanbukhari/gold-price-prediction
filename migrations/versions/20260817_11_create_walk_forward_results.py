"""Create durable walk-forward fold results.

Revision ID: 20260817_11
Revises: 20260817_10
"""
from alembic import op
import sqlalchemy as sa

revision = "20260817_11"
down_revision = "20260817_10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "walk_forward_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_name", sa.String(100)),
        sa.Column("model_version", sa.String(50)),
        sa.Column("horizon_minutes", sa.Integer()),
        sa.Column("fold_id", sa.Integer()),
        sa.Column("train_start", sa.DateTime()),
        sa.Column("train_end", sa.DateTime()),
        sa.Column("test_start", sa.DateTime()),
        sa.Column("test_end", sa.DateTime()),
        sa.Column("train_rows", sa.Integer()),
        sa.Column("test_rows", sa.Integer()),
        sa.Column("mae", sa.Float()),
        sa.Column("rmse", sa.Float()),
        sa.Column("directional_accuracy", sa.Float()),
        sa.Column("persistence_mae", sa.Float()),
        sa.Column("mae_improvement_pct", sa.Float()),
        sa.Column("market_regime", sa.String(50)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("walk_forward_results")
