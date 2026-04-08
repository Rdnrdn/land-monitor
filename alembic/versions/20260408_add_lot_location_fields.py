"""Add municipality/settlement fields to lots."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_add_lot_location_fields"
down_revision = "20260408_add_notice_classification_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lots", sa.Column("municipality_name", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("settlement_name", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("municipality_fias_guid", sa.Text(), nullable=True))
    op.add_column("lots", sa.Column("settlement_fias_guid", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lots", "settlement_fias_guid")
    op.drop_column("lots", "municipality_fias_guid")
    op.drop_column("lots", "settlement_name")
    op.drop_column("lots", "municipality_name")
