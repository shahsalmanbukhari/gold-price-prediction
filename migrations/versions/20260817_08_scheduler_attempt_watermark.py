"""Persist training attempt throttle.

Revision ID: 20260817_08
Revises: 20260817_07
"""
from alembic import op
import sqlalchemy as sa

revision = "20260817_08"
down_revision = "20260817_07"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("training_scheduler_state", sa.Column("last_training_attempt_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("training_scheduler_state", "last_training_attempt_at")
