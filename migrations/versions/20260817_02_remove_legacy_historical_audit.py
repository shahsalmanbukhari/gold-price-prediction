"""Remove the empty audit table from the rejected prices-based importer."""

from alembic import op
import sqlalchemy as sa

revision = "20260817_02"
down_revision = "20260817_01"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("historical_import_audits")


def downgrade():
    op.create_table(
        "historical_import_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("directory", sa.String(1000), nullable=False),
        sa.Column("zip_filename", sa.String(500), nullable=False),
        sa.Column("csv_filename", sa.String(1000)),
        sa.Column("archive_checksum", sa.String(64)),
        sa.Column("csv_checksum", sa.String(64)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("total_rows", sa.Integer(), default=0),
        sa.Column("inserted_rows", sa.Integer(), default=0),
        sa.Column("duplicate_rows", sa.Integer(), default=0),
        sa.Column("invalid_rows", sa.Integer(), default=0),
        sa.Column("error_details", sa.Text()),
    )
